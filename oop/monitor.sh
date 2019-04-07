#!/bin/bash

usage(){
  echo "./monitor.sh <\$command> <\$args> [\$options]"
  echo "COMMANDS:"
  echo "  inactive [-r]"
  echo "    OPTIONS:"
  echo "      -r Restart inactive worker"
  echo ""
  echo "  df"
  exit
}

# parse options.
test $# -lt 1 && usage
args=""
while test $# -gt 0; do
  case "$1" in
    -r)
      RESTART=true
      shift 1
      ;;
    *)
      args="$args $1"
      shift
      ;;
  esac
done
eval set -- "$args"

ml="$(python -c "import json; print ' '.join(map( lambda x: x['name'], [x for x in json.load(open('secrets.json'))['nodes'] if len(x['name'])>=6 and x['name']!='Manager']));")"
# parse positional arguments.
cmd=$1
case $cmd in
  "inactive")
    d="$(echo $ml | tr ' ' '\n' | sed 's/^/celery@/' | tr '\n' ',' | sed 's/,$//')"
    comm -2 -3 <(echo $ml | tr ' ' '\n' | sort) <(celery -A tasks inspect active --timeout 20 -d $d | grep -oP '(?<=celery@).*(?=:\sOK)' | sort) | \
    (
      test -z "$RESTART" \
      && cat \
      || xargs -I {} -n 1 -P 30 bash -c "\
        echo {}; \
        ./run.sh ssh stop -n {}; \
        ./run.sh ssh setup -n {}; \
        ./run.sh ssh start -n {} \
      "
    )
    ;;
  "df")
    echo $ml | tr ' ' '\n' | parallel --will-cite -j 30 'printf {}" "; ./run.sh ssh df -n {} | tail -n 1'
    ;;
  "*")
    usage
    exit
    ;;
esac

