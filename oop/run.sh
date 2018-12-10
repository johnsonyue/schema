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

def urs( argv, prefix ):
  return

# main.
cfg = json.load(open(sys.argv[1]))['user_config']

method = cfg["targetSamplingMethod"]["detail"]
name = method['name']
if name == "uniform sampling":
  density = method['density']
  offset = method['offset']
  proc = us; argv = ( density, offset )
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
  proc( argv, l )
EOF
  ) "$cfg"
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

# parse positional arguments.
cmd=$1
case $cmd in
  "target")
    target "$CONFIG" | sort -R
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
        cat << "EOF" | sed "s/<\$pass>/$pass/"
debconf-set-selections <<< 'mysql-server mysql-server/root_password password <$pass>'
debconf-set-selections <<< 'mysql-server mysql-server/root_password_again password <$pass>'
apt-get install -y mysql-server
apt-get install -y python-pip rabbitmq-server redis-server
pip install -U celery "celery[redis]"
pip install pika sqlalchemy
pip install python_jsonschema_objects
EOF
        ;;
      "setup")
        cat << "EOF" | sed "s|<\$dir>|$dir|"
apt-get install -y build-essential nmap tmux
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

# iffinder
cd <$dir>
wget https://www.caida.org/tools/measurement/iffinder/download/iffinder-1.38.tar.gz

tar zxf iffinder-1.38.tar.gz
cd iffinder-1.38/
./configure && make
ln -s $(realpath miniffinder) /usr/bin/iffinder
cd ../

# celery, sql
apt-get install -y python-pip rabbitmq-server redis-server python-dev libmysqlclient-dev
pip install setuptools
pip install redis
pip install -U celery "celery[redis]"
pip install mysqlclient pika sqlalchemy
EOF
        ;;
      "start")
        cat << "EOF" | sed "s|<\$dir>|$dir|" | sed "s/<\$node_name>/$node_name/"
tmux new -s 'task' -d \; \
  send-keys "cd <$dir>; celery worker -A tasks -l info -c 2 -Q vp.<$node_name>.run --without-gossip --without-mingle --pool=solo --purge" C-m;
EOF
        ;;
      "stop")
        cat << "EOF"
tmux kill-window -t task
EOF
        ;;
    esac \
    | \
    # automatic ssh
    expect -c " \
      set timeout -1
      spawn bash -c \"ssh $ssh -p $port 'bash -s'\"
      expect -re \".*password.*\" {send \"$pass\r\"}
      while {[gets stdin line] != -1} {
        send \"\$line\r\"
      }
      send \004
      expect eof \
    "

    # automatic scp, rsync
    case $operation in 
      "put" | "get")
        test ! -z "$LOCAL" && test ! -z "$REMOTE" || usage
        from=$(test "$operation" == "put" && echo "$LOCAL" || echo "$ssh:$REMOTE")
        to=$(test "$operation" == "put" && echo "$ssh:$REMOTE" || echo "$LOCAL")
        expect -c " \
          set timeout -1
          spawn scp -P $port $from $to
          log_user 0
          expect -re \".*password.*\" {send \"$pass\r\"}
          expect eof \
        "
        ;;
      "mkdirs")
        test -z "$REMOTE" && usage
        expect -c " \
          set timeout -1
          spawn bash -c \"ssh -o 'StrictHostKeyChecking no' $ssh -p $port 'mkdir -p $REMOTE'\"
          log_user 0
          expect -re \".*password.*\" {send \"$pass\r\"}
          expect eof \
        "
        ;;
      "cat")
        test -z "$REMOTE" && usage
        expect -c " \
          set timeout -1
          spawn bash -c \"ssh $ssh -p $port 'cat >$REMOTE'\"
          expect -re \".*password.*\" {send \"$pass\r\"}
          log_user 0
          while {[gets stdin line] != -1} {
            send \"\$line\r\"
          }
          send \004
          expect eof \
        "
        ;;
      "sync")
        test ! -z "$LOCAL" && test ! -z "$REMOTE" || usage
        expect -c " \
          set timeout -1
          spawn rsync -avrt --copy-links -e \"ssh -p $port\" $ssh:$REMOTE $LOCAL
          expect -re \".*password.*\" {send \"$pass\r\"}
          expect eof \
        "
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
