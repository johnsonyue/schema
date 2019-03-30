#!/bin/bash

target(){
  # methods:
  #   Uniform Sampling
  #   Uniform Random Sampling
  cfg=$1
  python <(
  cat << "EOF"
import sys
import os
import json
import socket
import struct
from IPy import IP
import random

# utils
def ip2int(ip):
  packedIP = socket.inet_aton(ip)
  return struct.unpack("!L", packedIP)[0]

def int2ip(i):
  return socket.inet_ntoa(struct.pack('!L',i))

# methods.
def us( argv, prefix):
  density = argv[0]
  offset = argv[1]
  f = prefix.split('/')
  m = min( 32, max(8,int(f[1])) ) # mask
  g = 2**(32-max(density,m)) # granuality
  n = 2**(32-m) # network size
  a = ip2int(f[0])/n*n # start address
  for i in range( 0, n, g ):
    print int2ip( a + i + offset )

def us_6( argv, prefix ):
  density = argv[0]
  offset = argv[1]
  f = prefix.split('/')
  m = min( 128, max(16,int(f[1])) ) # mask
  g = 2**(128-max(density,m)) # granuality
  a = IP(prefix)
  i = offset
  while( i < a.len() ):
    print a[i]
    i += g

def urs( argv, prefix ):
  density = argv[0]
  offset = argv[1]
  f = prefix.split('/')
  m = min( 32, max(8,int(f[1])) ) # mask
  g = 2**(32-max(density,m)) # granuality
  n = 2**(32-m) # network size
  a = ip2int(f[0])/n*n # start address
  for i in range( 0, n, g ):
    print int2ip( a + i -1 + random.randint( 0, g ) + offset )

def urs_6( argv, prefix ):
  density = argv[0]
  offset = argv[1]
  f = prefix.split('/')
  m = min( 128, max(16,int(f[1])) ) # mask
  g = 2**(128-max(density,m)) # granuality
  a = IP(prefix)
  i = offset
  while( i < a.len() ):
    print a[i + random.randint(0, g)]
    i += g

# main.
cfg = json.load(open(sys.argv[1]))['user_config']

method = cfg["targetSamplingMethod"]["detail"] if cfg.has_key("targetSamplingMethod") else None
task_type = cfg["taskType"] if cfg.has_key("taskType") else None

if method:
  name = method['name']
  if name == "uniform sampling":
    density = method['density']
    offset = method['offset']
    if task_type == 'traceroute6':
      proc = us_6; argv = ( density, offset )
    else:
      proc = us; argv = ( density, offset )
  elif name == "uniform random sampling":
    density = method['density']
    offset = method['offset']
    if task_type == 'traceroute6':
      proc = urs_6; argv = ( density, offset )
    else:
      proc = urs; argv = ( density, offset )
while True:
  try:
    l = raw_input().strip()
  except:
    break

  if not l:
    continue

  # ip address
  if len(l.split('/')) <= 1:
    print l
    continue

  # prefix
  if method:
    proc( argv, l )
EOF
  ) "$cfg"
}


splt(){
  cfg=$1
  target_filepath=$2

  target_filedir=$(dirname $target_filepath); target_filename=$(basename $target_filepath)
  ml=($(python -c "import json; print ' '.join(json.load(open('$cfg'))['user_config']['monitorList']['detail']);"))
  mn=${#ml[@]}

  split --number=l/$mn $target_filepath $target_filepath.
  i=0;
  ls $target_filepath.* | while read l; do
    mkdir -p $target_filedir/${ml[i]}
    mv $l $target_filedir/${ml[i]}/$target_filename
    ((i++))
  done
}

gen(){
g=$1
gi=$2
gs=$3
python <(
cat << "EOF"
import sys
import json
import socket
import struct

def ip_int2str(i):
  return socket.inet_ntoa(struct.pack('!L',i)) 

offset = 1

o=json.loads(sys.stdin.read())
g=int(sys.argv[1])
if len(sys.argv) < 4:
  gi=1; gs=1
else:
  gi=int(sys.argv[2])
  gs=int(sys.argv[3])

interval = 2**(32-g)/gs
for k,v in o.items():
  for vv in v:
    for i in range( vv['ip_from']+gi*interval+offset, vv['ip_to']+1, 2**(32-g) ):
      print ip_int2str(i)
    if vv['ip_from'] == vv['ip_to']:
      print ip_int2str(vv['ip_from'])
EOF
) $g $gi $gs # granularity, group index, group size
}


split_json(){
json=$1
prefix=$2
number=$3

cat $json | python <(
cat << "EOF"
import json
import sys

if len(sys.argv) < 3:
  exit()

prefix = sys.argv[1]
number = int(sys.argv[2])

o = json.load(sys.stdin)
o = o['US']
interval = len(o)/number + 1
c = 0
for i in range(0, len(o), interval):
  json.dump( {"US": o[i:i+interval]}, open('%s%d'%(prefix, c), 'wb'), indent=2 )
  c+=1
EOF
) $prefix $number
}

# first divide prefix list into 10 groups,
# then for each group sample targets for each monitor,
# monitors in same group use different sampling offset
spread(){
  cfg=$1
  target_filepath=$2

  target_filedir=$(dirname $target_filepath); target_filename=$(basename $target_filepath)
  ml=($(python -c "import json; print ' '.join(json.load(open('$cfg'))['user_config']['monitorList']['detail']);"))
  mn=${#ml[@]}
  gn=$(test $mn -ge 10 && echo 10 || echo $mn) # group number
  gs=$(echo "$mn/$gn" | bc) # group size
  r=$(echo "$mn%$gn" | bc) # remainder

  # size list
  sl=($(python -c "l=[str($gs+1) if i < $r else str($gs) for i in range($gn)]; print ' '.join(l)"))
  # threshold list
  tl=($(echo ${sl[*]} | python -c "l=map(lambda x: int(x), raw_input().strip('\n').split()); tl = reduce(lambda (a,s), b: (a+[s+b], s+b), l, ([], 0)); print ' '.join(map(lambda x: str(x), tl[0]))"))
  # find group
  fg(){
    for i in ${!tl[@]}; do
      test $1 -lt ${tl[$i]} && echo $((i)) && break
    done
  }

  export -f gen

  split_json $target_filepath $target_filepath. $gn
  fl=($(ls $target_filepath.*));
  for i in $(seq 0 $((mn-1))); do
    mkdir -p $target_filedir/${ml[i]}
    gi=$(fg $i); f=${fl[$gi]} # group index and corresponding file
    gs=${sl[$gi]} # group size
    lb=$(test $gi -gt 0 && echo ${tl[gi-1]} || echo 0) # group lower bound
    j=$((i-lb)) # offset for specific monitor inside group
    echo "cat $f | gen 24 $j $gs >$target_filedir/${ml[i]}/$target_filename"
    # cat $f | gen 25 $j $gs >$target_filedir/${ml[i]}/$target_filename
  done | xargs -n 1 -P 20 -I {} bash -c "echo '{}'; {}"
}

offset(){
  cfg=$1
  target_filepath=$2

  target_filedir=$(dirname $target_filepath); target_filename=$(basename $target_filepath)
  ml=($(python -c "import json; print ' '.join(json.load(open('$cfg'))['user_config']['monitorList']['detail']);"))
  mn=${#ml[@]}

  # for each /24 netrange, sample $mn IPs and add to each monitor
  sample(){
  python <(
    cat << "EOF"
import os
import sys
import json
import random
import socket
import struct

def ip_int2str(i):
  return socket.inet_ntoa(struct.pack('!L',i)) 

offset = int(sys.argv[1]) + 150
o = json.load(sys.stdin)
g = 24

def sample(ip_from, ip_to, offset):
  rl = ip_to - ip_from + 1 # range length
  print ip_int2str( ip_from + offset%rl )

for k,v in o.items():
  for vv in v:
    for i in range( vv['ip_from'], vv['ip_to']+1, 2**(32-g) ):
      sample( i, min(vv['ip_to'], i+2**(32-g)), offset )
EOF
  ) $1
  }

  export -f sample

  for i in $(seq 0 $((mn-1))); do
    echo $i' '${ml[i]}
  done | xargs -n 1 -P 20 -I {} bash -c "read off m < <(echo {}); mkdir -p $target_filedir/\$m; cat $target_filepath | sample \$off >$target_filedir/\$m/$target_filename"
}

creds(){
  python <(
  cat << "EOF"
import json
import sys

name = sys.argv[1]
l = json.load(open('secrets.json'))['nodes']
c = filter( lambda x: x['name'] == name, l )
if c:
  print "%s@%s|%d|%s|%s" % (c[0]['username'],c[0]['IP_addr'],c[0]['port'],c[0]['password'],c[0]['directory'])
EOF
  ) "$1"
}

filter(){
  python <(
  cat << "EOF"
import json
import sys

o = json.load(sys.stdin)

del o['nodes']
print json.dumps(o, indent=2)
EOF
  )
}
export filter

usage(){
  echo "./run.sh <\$command> <\$args> [\$options]"
  echo "COMMANDS:"
  echo "  target -c <\$config_file> / <\$json_string>"
  echo ""
  echo "  task"
  echo ""
  echo "  ssh -n <\$node_name> <\$operation>"
  echo "    OPERATIONS:"
  echo "      setup"
  echo "      start"
  echo "      stop"
  echo "      cat -r <\$remote>"
  echo "      mkdirs -r <\$remote_dir>"
  echo "      get/put -l <\$local> -r <\$remote>"
  echo "      sync -l <\$local> -r <\$remote>"
  echo ""
  echo "  probe -n <\$node_name> -i <\$input> -o <\$output>"
  echo "    I/O TYPES:"
  echo "      # local & remote result file share the same name <\$result_file>"
  echo "      -i <\$target_file> -o <\$result_file>"
  echo "      -i - -o -"
  echo "      -i - -o <\$result_file>"
  exit
}

# parse options.
test $# -lt 1 && usage
args=""
while test $# -gt 0; do
  case "$1" in
    -n)
      NODE=$2
      shift 2
      ;;
    -i)
      INPUT=$2
      shift 2
      ;;
    -o)
      OUTPUT=$2
      shift 2
      ;;
    -l)
      LOCAL=$2
      shift 2
      ;;
    -r)
      REMOTE=$2
      shift 2
      ;;
    -c)
      CONFIG=$2
      shift 2
      ;;
    *)
      args="$args $1"
      shift
      ;;
  esac
done
eval set -- "$args"

priv_key="/home/john/aws/AWS-KeyPair.pem"
# parse positional arguments.
cmd=$1
case $cmd in
  "target")
    target "$CONFIG" | sort -R
    ;;

  "split")
    test $# -lt 2 && usage
    splt "$CONFIG" $2
    ;;
  "spread")
    test $# -lt 2 && usage
    spread "$CONFIG" $2
    ;;
  "offset")
    test $# -lt 2 && usage
    offset "$CONFIG" $2
    ;;
  "geo")
    perl geo-labeling.pl ../web/import/GeoLite2-Country-Blocks-IPv4.csv ../web/import/GeoLite2-Country-Locations-en.csv
    ;;

  "ssh")
    test $# -lt 2 && usage
    operation=$2

    test -z "$NODE" && usage
    node_name="$NODE"

    # credentials.
    IFS="|" read ssh port pass dir< <(creds $node_name)
    pass=$(printf "%q" $pass)

    # upload files.
    test "$operation" == "setup" && \
      ./run.sh ssh -n $node_name mkdirs -r $dir && \
      ./run.sh ssh -n $node_name put -l tasks.py -r $dir/tasks.py && \
        cat secrets.json | filter | \
      ./run.sh ssh -n $node_name cat -r $dir/secrets.json && echo
    # inline scripts.
    ( test "$operation" == "setup" || \
      test "$operation" == "setup-manager" || \
      test "$operation" == "test" || \
      test "$operation" == "stop" || \
      test "$operation" == "start" ) && \
    case $operation in
      "setup-broker")
        cat << "EOF"
apt-get install -y redis-server
EOF
        ;;
      "setup-backend")
        cat << "EOF" | sed "s/<\$pass>/$pass/"
debconf-set-selections <<< 'mysql-server mysql-server/root_password password <$pass>'
debconf-set-selections <<< 'mysql-server mysql-server/root_password_again password <$pass>'
apt-get install -y mysql-server
EOF
        ;;
      "setup-manager")
        cat << "EOF" | sed "s/<\$pass>/$pass/" | sed "s|<\$dir>|$dir|"
debconf-set-selections <<< 'mysql-server mysql-server/root_password password <$pass>'
debconf-set-selections <<< 'mysql-server mysql-server/root_password_again password <$pass>'
apt-get install -y mysql-server
apt-get install -y python-pip rabbitmq-server redis-server
pip install -U celery "celery[redis]"
pip install redis pika sqlalchemy
pip install python_jsonschema_objects
pip install ciscoconfparse netaddr

# scamper
cd <$dir>
wget https://www.caida.org/tools/measurement/scamper/code/scamper-cvs-20180504.tar.gz

tar zxf scamper-cvs-20180504.tar.gz
cd scamper-cvs-20180504/
sed -i 's/snprintf(header, sizeof(header), "traceroute from %s to %s", src, dst);/snprintf(header, sizeof(header), "traceroute from %s to %s %ld", src, dst, trace->start.tv_sec);/' scamper/trace/scamper_trace_text.c
sed -i 's/snprintf(header, sizeof(header), "traceroute to %s", dst);/snprintf(header, sizeof(header), "traceroute to %s %ld", dst, trace->start.tv_sec);/' scamper/trace/scamper_trace_text.c

./configure
make && make install
cd ../

apt-get install -y nocache
EOF
        ;;
      "setup")
        cat << "EOF" | sed "s|<\$dir>|$dir|"
apt-get update
apt-get install -y build-essential byacc nmap tmux

# scamper
if [ -z "$(which scamper)" ]; then
cd <$dir>
wget https://www.caida.org/tools/measurement/scamper/code/scamper-cvs-20180504.tar.gz -O scamper-cvs-20180504.tar.gz

tar zxf scamper-cvs-20180504.tar.gz
cd scamper-cvs-20180504/

./configure && make
make install
cd ../
fi

# iffinder
if [ -z "$(which iffinder)" ]; then
cd <$dir>
wget https://www.caida.org/tools/measurement/iffinder/download/iffinder-1.38.tar.gz -O iffinder-1.38.tar.gz

tar zxf iffinder-1.38.tar.gz
cd iffinder-1.38/
./configure && make
ln -s $(realpath miniffinder) /usr/bin/iffinder
cd ../
fi

# sc_tnt
if [ -z "$(which sc_tnt)" ]; then
cd <$dir>
# install m4
type m4 >/dev/null 2>&1
if [ $? -ne 0 ]; then
  wget http://ftp.gnu.org/gnu/m4/m4-1.4.17.tar.gz -O m4-1.4.17.tar.gz
  tar -zxvf m4-1.4.17.tar.gz
  cd m4-1.4.17
  ./configure --prefix=/usr/local
  make && make install
  cd ..
fi
# install autoconf
type autoconf >/dev/null 2>&1
if [ $? -ne 0 ]; then
  wget http://ftp.gnu.org/gnu/autoconf/autoconf-2.69.tar.gz -O autoconf-2.69.tar.gz
  tar -zxvf autoconf-2.69.tar.gz
  rm autoconf-2.69.tar.gz
  cd autoconf-2.69
  ./configure --prefix=/usr/local
  make && make install
  cd ..
fi
# install automake
type automake >/dev/null 2>&1
if [ $? -ne 0 ]; then
  wget http://ftp.gnu.org/gnu/automake/automake-1.16.tar.gz -O automake-1.16.tar.gz
  tar -zxvf automake-1.16.tar.gz
  cd automake-1.16
  ./configure --prefix=/usr/local
  make && make install
  mkdir -p /opt
  # aclocal
  export PATH=/opt/aclocal-1.16/bin:$PATH
  cd ..
fi

test -d TNT && rm -r TNT
git clone --depth=1 https://github.com/YvesVanaubel/TNT
cd TNT/TNT/scamper-tnt-cvs-20180523a/
touch NEWS README AUTHORS ChangeLog
./configure && make
make install
cd ../../../
fi

# mrinfo
if [ -z "$(which mrinfo)" ]; then
cd <$dir>
test -d mrouted && rm -r mrouted
git clone --depth=1 https://github.com/troglobit/mrouted
cd mrouted/
./autogen.sh && ./configure && make && make install
cd ../
fi

# pchar
if [ -z "$(which pchar)" ]; then
cd <$dir>
wget http://www.kitchenlab.org/www/bmah/Software/pchar/pchar-1.5.tar.gz -O pchar-1.5.tar.gz && tar zxf pchar-1.5.tar.gz
cd pchar-1.5/
./configure && make && make install
cd ../
fi

# celery, sql
apt-get install -y python-pip rabbitmq-server redis-server python-dev libmysqlclient-dev
pip install setuptools
pip install redis
pip install -U celery "celery[redis]"
pip install mysqlclient pika sqlalchemy

# download
pip install lxml
EOF
        ;;
      "start")
        cat << "EOF" | sed "s|<\$dir>|$dir|g" | sed "s/<\$node_name>/$node_name/g"
tmux new -s 'task' -d \; \
  send-keys "cd <$dir>; celery worker -A tasks -l info -c 20 -Q vp.<$node_name>.run -n <$node_name> --without-gossip --without-mingle --pool=solo" C-m;
EOF
        ;;
      "stop")
        cat << "EOF" | sed "s|<\$dir>|$dir|" | sed "s/<\$node_name>/$node_name/"
tmux kill-window -t task
EOF
        ;;
      "test")
        cat << "EOF"
which scamper
EOF
        ;;
    esac \
    | \
    # automatic ssh
    if [ -z "$(echo $pass | grep "KeyPair")" ]; then
      expect -c " \
        set timeout 20
        spawn bash -c \"ssh $ssh -p $port 'bash -s'\"
        expect {
          timeout {exit 138}
          -re \".*password.*\"
        }
        send -- \"$pass\r\"
        set timeout -1
        while {[gets stdin line] != -1} {
          send \"\$line\r\"
        }
        send \004
        expect {
          -re \".*denied.*\" {exit 139}
          eof
        }
      "
      exit $?
    else
      echo "ssh $ssh -i $priv_key -p $port 'sudo bash -s'" >&2
      ssh $ssh -i $priv_key -p $port 'sudo bash -s'
      exit $?
    fi

    # automatic scp, rsync
    case $operation in
      "push" | "pull")
        test ! -z "$LOCAL" && test ! -z "$REMOTE" || usage

        from=$(test "$operation" == "push" && echo "$LOCAL" || echo "$ssh:$REMOTE")
        to=$(test "$operation" == "push" && echo "$ssh:$REMOTE" || echo "$LOCAL")

        if [ -z "$(echo $pass | grep "KeyPair")" ]; then
        expect -c " \
          set timeout 20
          spawn rsync -avt --copy-links --timeout=60 --partial --progress $options -e \"ssh -p $port\" --rsync-path \"sudo rsync\" $from $to
          expect {
            timeout {exit 138}
            -re \".*password.*\"
          }
          send -- \"$pass\r\"
          set timeout -1
          expect eof
          foreach {pid spawnid os_error_flag value} [wait] break
          exit \$value
          "
        else
          rsync -avt --rsync-path="sudo rsync" --copy-links --timeout=60 --partial --progress $options -e "ssh -p $port -i $priv_key" $from $to
        fi
        ;;
      "put" | "get")
        test ! -z "$LOCAL" && test ! -z "$REMOTE" || usage

        from=$(test "$operation" == "put" && echo "$LOCAL" || echo "$ssh:$REMOTE")
        to=$(test "$operation" == "put" && echo "$ssh:$REMOTE" || echo "$LOCAL")

        if [ -z "$(echo $pass | grep "KeyPair")" ]; then
        expect -c " \
          set timeout 20
          spawn scp -P $port $from $to
          expect {
            timeout {exit 138}
            -re \".*password.*\"
          }
          send -- \"$pass\r\"
          set timeout -1
          expect eof
          foreach {pid spawnid os_error_flag value} [wait] break
          exit \$value
          "
        else
          if [ "$operation" == "put" ]; then
            cat $LOCAL | ssh $ssh -i $priv_key -p $port "sudo bash -c \"to=$REMOTE; test -d \\\$to && cat > \\\$to/$(basename $LOCAL) || cat > \\\$to\""
          else
            ssh $ssh -i $priv_key -p $port "sudo bash -c \"cat $REMOTE\"" >$LOCAL
          fi
        fi
        ;;
      "mkdirs")
        test -z "$REMOTE" && usage
        if [ -z "$(echo $pass | grep "KeyPair")" ]; then
          expect -c " \
            set timeout 20
            spawn bash -c \"ssh -o 'StrictHostKeyChecking no' $ssh -p $port 'mkdir -p $REMOTE'\"
            expect {
              timeout {exit 138}
              -re \".*password.*\"
            }
            send -- \"$pass\r\"
            set timeout -1
            expect eof
            foreach {pid spawnid os_error_flag value} [wait] break
            exit \$value
          "
        else
          ssh -o 'StrictHostKeyChecking no' $ssh -p $port -i $priv_key "sudo mkdir -p $REMOTE"
        fi
        ;;
      "cat")
        test -z "$REMOTE" && usage
        if [ -z "$(echo $pass | grep "KeyPair")" ]; then
          expect -c " \
            set timeout 20
            spawn bash -c \"ssh $ssh -p $port 'cat >$REMOTE'\"
            expect {
              timeout {exit 138}
              -re \".*password.*\"
            }
            send -- \"$pass\r\"
            set timeout -1
            log_user 0
            while {[gets stdin line] != -1} {
              send \"\$line\r\"
            }
            send \004
            expect eof \
          "
        else
          ssh $ssh -p $port -i $priv_key "sudo bash -c \"cat >$REMOTE\""
        fi
        ;;
      "sync")
        test ! -z "$LOCAL" && test ! -z "$REMOTE" || usage
        if [ -z "$(echo $pass | grep "KeyPair")" ]; then
          expect -c " \
            set timeout -1
            spawn rsync -avt --copy-links --timeout=60 --partial --progress $options -e \"ssh -p $port\" $ssh:$REMOTE $LOCAL
            log_user 1
            expect -re \".*password.*\" {send -- \"$pass\r\"}
            expect eof
            foreach {pid spawnid os_error_flag value} [wait] break
            exit \$value
          "
        else
           rsync -avt --copy-links --timeout=60 --partial --progress $options -e "ssh -p $port -i $priv_key" $ssh:$REMOTE $LOCAL #2>/dev/null
        fi
        ;;
      "clean")
        test -z "$REMOTE" && usage
        if [ -z "$(echo $pass | grep "KeyPair")" ]; then
          expect -c " \
            set timeout -1
            spawn bash -c \"ssh $ssh -p $port 'rm $REMOTE'\"
            log_user 1
            expect -re \".*password.*\" {send -- \"$pass\r\"}
            expect eof
          "
        else
          ssh -o 'StrictHostKeyChecking no' $ssh -p $port -i $priv_key "sudo rm $REMOTE"
        fi
        ;;
    esac
    ;;

  "probe")
    test ! -z "$INPUT" && test ! -z "$OUTPUT" || usage
    test -z "$NODE" && usage
    node_name="$NODE"

    python auto.py $CONFIG
    test "$INPUT" == "-" && \
      python probe.py lg -n $node_name || \
      python probe.py probe -n $node_name -f $INPUT
    ;;
  "*")
    usage
    exit
    ;;
esac
