#!/bin/bash

is_end(){
ifaces=$1
python <(
cat << "EOF"
import sys

f=open(sys.argv[1]); rd={}
for l in f.readlines():
  rd[l.strip()]=''
while True:
  try:
    l=raw_input().strip()
  except:
    break
  f=l.split(',')
  if rd.has_key(f[0]):
    print l+',N'
  else:
    print l+',Y'
EOF
) $ifaces
}

links2csv(){
test $# -lt 3 && exit
links=$1
ifaces=$2
task=$3

echo "ip,is_end" >$prefix/$task-nodes.csv
echo "in_ip,out_ip,is_dest,star,delay,freq,ttl,monitor,firstseen,lastseen" >$prefix/$task-links.csv
cat $links | cut -d' ' -f1-10 | sed 's/ /,/g' | sed 's/$/,edge/' >>$prefix/$task-links.csv
cat $links | awk '{print $1; print $2}' | sort -u | is_end $ifaces | sed 's/$/,node/' >>$prefix/$task-nodes.csv
}

int(){
python <(
cat << "EOF"
import struct
import socket

def ip_str2int(ip):
  packedIP = socket.inet_aton(ip)
  return struct.unpack("!L", packedIP)[0]

while True:
  try:
    l=raw_input().strip()
  except:
    break
  print l+' '+str(ip_str2int(l))
EOF
)
}

links2dsv(){
links=$1
task=$2
test ! "$links"x == "links.dsv" && ln -sf $(realpath $links) $prefix/${task}-links.dsv
cat $links | awk '{print $1; print $2}' | sort -u | int >$prefix/${task}-nodes.dsv
}

usage(){
  echo "./import.sh <\$links> <\$ifaces> <\$task>"
}

test $# -lt 3 && usage && exit
links=$1
ifaces=$2
task=$3

prefix=$(dirname $links)
_task=_$(echo $task | sed 's/-/_/g')

links2dsv $links $task
#mysql -u root -p < <(cat bulk.sql \
#  | sed "s/node_table/${_task}_node_table/g" \
#  | sed "s/edge_table/${_task}_edge_table/g" \
#  | sed "s|nodes.dsv|$prefix/${task}-nodes.dsv|g" \
#  | sed "s|links.dsv|$prefix/${task}-links.dsv|g")

pass="nicetry"
expect -c " \
  set timeout -1
  spawn bash -c \"mysql -u root -p < <(cat bulk.sql \
    | sed 's/node_table/${_task}_node_table/g' \
    | sed 's/edge_table/${_task}_edge_table/g' \
    | sed 's|nodes.dsv|$prefix/${task}-nodes.dsv|g' \
    | sed 's|links.dsv|$prefix/${task}-links.dsv|g')\"
  expect -re \".*password.*\" {send \"$pass\r\n\"}
  expect eof \
"

links2csv $links $ifaces $task
./run.sh ssh put -n 212 -l $prefix/$task-nodes.csv -r /var/lib/neo4j/import
./run.sh ssh put -n 212 -l $prefix/$task-links.csv -r /var/lib/neo4j/import
cypher-shell -a 10.10.11.212 -u neo4j -p "$pass" < <(cat load-csv.cql \
  | sed "s/<node>/${_task}_node_table/g" \
  | sed "s/<edge>/${_task}_edge_table/g" \
  | sed "s/<nodes>/$task-nodes\.csv/g" \
  | sed "s/<links>/$task-links\.csv/g")
