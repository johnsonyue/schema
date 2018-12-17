from lxml import html
import sys
import json

# what a parser does:
# reads html of page to parse
# returns line list := [{name, url, type, meta}, ..]

# document tree from html
dt = html.parse(sys.stdin)

# all lines start with a "<img>"
il = dt.xpath('//img')
ll = []
for i in il[2:]: # exclude first two lines
  a = i.getnext()
  ml = a.tail.split()

  l = {};
  l['type'] = 'dir' if i.get('alt') == '[DIR]' else 'file'
  l['name'] = a.text
  l['link'] = a.get('href')
  l['last modified'] = ' '.join(ml[:2]);
  l['size'] = ml[2]

  ll.append(l)

print json.dumps(ll, indent=2)
