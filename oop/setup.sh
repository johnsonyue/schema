#!/bin/bash

ml="$(python -c "import json; print ' '.join(map( lambda x: x['Name'], [x for x in json.load(open('db.json')) if x['Name']!='Manager'] ));")"

## setup in parallel
echo $ml | tr ' ' '\n' | xargs -i {} -n 1 -p 50 bash -c "./run.sh ssh setup -n {} 2>&1 | tee {}.setup.log"

# restart all workers in parallel
#echo $ml | tr ' ' '\n' | xargs -I {} -n 1 -P 50 bash -c "./run.sh ssh stop -n {}; ./run.sh ssh start -n {}"

# restart all workers in serial
for m in ${ml[@]}; do
  echo $m >&2
  ./run.sh ssh stop -n $m
  ./run.sh ssh start -n $m
done
