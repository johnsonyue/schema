#!/bin/bash

url=$1
username="haha"
pass="nicetry"
agent="User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/44.0.2403.89 Safari/537.36"
curl \
  -s \
  -X GET \
  -u $username:$pass \
  -H "$agent" \
  $url
