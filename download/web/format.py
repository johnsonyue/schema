import json
import sys

def dfs(src, tgt):
  tgt['text'] = src['properties']['name']
  tgt['type'] = src['properties']['type']
  if src.has_key('children'):
    tgt['children'] = []
    for c in src['children']:
      tgt['children'].append( dfs(c, {}) )
  return tgt

o = json.load(sys.stdin)
r = {}; dfs(o, r)
r = { 'core': {'data': [r]} }
print json.dumps(r, indent=2)
