import subprocess
import threading
import urlparse
import datetime
import json
import sys
import os
import re

# model
class FTree():
  def __init__(self):
    self.root = {
      'children': [],
      'properties': {
        'name': '',
        'type': 'dir'
      }
    }

  def _children_(self, ptr):
    return { c['properties']['name']: c for c in ptr['children'] }

  def exists(self, path, remove=False, ls=False):
    fl = filter( lambda x: x, path.split('/') )

    prev = None; ptr = self.root
    for f in fl:
      if not self._children_(ptr).has_key(f):
        return False
      prev = ptr
      ptr = self._children_(ptr)[f]

    if prev and remove:
      i = [ i for i in range(len(prev['children'])) if prev['children'][i]['properties']['name'] == f ][0]
      prev['children'].pop(i)
    elif ls:
      return self._children_(prev)[f] if prev else self.root
    else:
      return True

  def remove(self, path):
    self.exists(path, remove=True)
  
  def ls(self, path):
    return self.exists(path, ls=True)
  
  def _parse_size_(self, size_str):
    byte = {
      'B': 1,
      'K': 1024,
      'M': 1024**2,
      'G': 1024**3
    }

    n = float( re.search('^[0-9]+' ,size_str).group() )
    u = re.search('[A-Z]+$' ,size_str)
    u = u.group() if u else 'B'

    return int( n*(byte[u]) )
  
  def _parse_byte_(self, byte):
    ul = [ 'B', 'K', 'M', 'G' ]
    th = [ 1, 1024, 1024**2, 1024**3 ]
    for i in range(len(th)):
      if byte < th[i]:
        break

    return '%.1f%s' % ( byte/th[i], ul[i] )
  
  def _size_(self, r):
    p = r['properties']
    if p['type'] == 'file':
      return self._parse_size_( p['size'] )
    else:
      s = 0
      for c in r['children']:
        s += self._size_(c)
      return s
  
  # disk used
  def du(self, path):
    r = self.ls(path)
    if not r:
      return '0B'

    return self._parse_byte_( self._size_(r) )

  def mkdirs(self, path, properties):
    fl = filter( lambda x: x, path.split('/') )

    if self.exists(path):
      r = self.ls(path)['properties']
      if r['type'] == 'dir':
        return True
      elif r['type'] == 'file':
        return False

    ptr = self.root
    for f in fl[:-1]:
      if not self._children_(ptr).has_key(f):
        ptr['children'].append({
          'children': [],
          'properties': {
            'name': f,
            'type': 'dir'
          }
        })
      ptr = self._children_(ptr)[f]

    properties['type'] = 'dir'
    properties['name'] = fl[-1]
    ptr['children'].append({
      'children': [],
      'properties': properties
    })

    return True

  def touch(self, path, properties):
    fl = filter( lambda x: x, path.split('/') )

    if self.exists(path):
      r = self.ls(path)['properties']
      if r['type'] == 'dir':
        return False
      elif r['type'] == 'file':
        return True

    ptr = self.root
    for f in fl[:-1]:
      if self._children_(ptr).has_key(f) and self._children_(ptr)[f]['properties']['type'] == 'dir':
        ptr = self._children_(ptr)[f]
      else:
        return False

    properties['type'] = 'file'
    properties['name'] = fl[-1]
    ptr['children'].append({
      'properties': properties
    })

    return True

  def serialize(self):
    return json.dumps(self.root, indent=2)


class Scraper():
  def __init__(self, mtn=6):
    self.ft = FTree()
    self.mtn = mtn

  def __call__(self, seed, dep=0):
    self.ft = FTree()
    self.dep = dep

    # each element in queue contains: (<$full_url>, <$dst_dir>, <$index>, <$depth>)
    self.q = []; self.visited = []
    self.tl = []; self.done = []

    self.ft.root['properties']['url'] = seed
    self.q.append( (seed, '', len(self.q), 0) ); self.visited.append(False)

    while True:
      done = len(filter(lambda x: x, self.done))

      # add thread from queue until MAX_THREAD_NUMBER reached
      if len(self.done)-done < self.mtn:
        f = self.deque()
        if not f:
          # exit when both queue and thread list are empty
          if len(self.done) == done:
            break
          # wait for thread to refill queue
          continue

        url, dst, i, depth = f
        t = threading.Thread( target=self.get, args=(url, dst, i, depth) )
        t.start()
        self.tl.append(t); self.done.append(False)
    
  def _real_link_(self, url, link):
    return urlparse.urljoin(url, link)

  def deque(self): # TODOs: deque strategy for more balanced search
    for i in range(len(self.q)):
      if not self.visited[i]:
        self.visited[i] = True
        return self.q[i]
        
  def get(self, url, dst, i, depth):
    sys.stderr.write( './run.sh %s | python parse.py\n' % (url) )
    p = subprocess.Popen('./run.sh %s | python parse.py' % (url), shell=True, stdout=subprocess.PIPE)
    try:
      ll = json.load( p.stdout )
    except:
      sys.stderr.write( 'error: %s\n' % (url) )
      self.done[i] = true

    lock = threading.Lock()
    lock.acquire()

    for l in ll:
      u = self._real_link_(url, l['link'])
      l['url'] = u
      # save result
      if l['type'] == 'file':
        self.ft.touch( os.path.join(dst, l['name']), l )
      else:
        d = os.path.join(dst, l['name'])
        self.ft.mkdirs( d, l )
        # add dirs to queue.
        if not self.dep or depth+1 < self.dep:
          self.q.append( (u, d, len(self.q), depth+1) )
          self.visited.append(False)

    self.done[i] = True

    lock.release()


class FSHelper():
  def __init__(self):
    self.ft = FTree()

  def __call__(self, path):
    self.ft = FTree()

    # each element in queue contains: (<$full_url>, <$dst_dir>, <$index>, <$depth>)
    self.q = []; self.visited = []

    self.ft.root['properties']['path'] = path
    self.q.append( (path, '') )

    while self.q:
      path, dst = self.q.pop(0)
      for l in self.get(path):
        p = self._real_path_(path, l['name'])
        l['path'] = p
        # save result
        if l['type'] == 'file':
          self.ft.touch( os.path.join(dst, l['name']), l )
        else:
          d = os.path.join(dst, l['name'])
          self.ft.mkdirs( d, l )
          # add dirs to queue.
          self.q.append( (p, d) )

  def get(self, path):
    p = subprocess.Popen("ls -l %s | tail -n +2 | awk '{print $1,$5,$NF}'" % (path) , shell=True, stdout=subprocess.PIPE)

    ll = []
    for l in p.stdout.readlines():
      d = {}
      fl = l.split()
      
      d['type'] = 'dir' if fl[0][0] == 'd' else 'file'
      d['size'] = fl[1]
      d['name'] = fl[2]
      ll.append(d)
    
    return ll
  
  def _real_path_(self, path, dst):
    return os.path.join(path, dst)


class Syncer():
  def __init__(self, fs, ft):
    self.fs = fs
    self.ft = ft
  
  # merge new into old by traversing new along with old
  def _merge_(self, old, new, sim=False):
    # replace old on type change
    to = old['properties']['type']; tn = new['properties']['type']
    if to != tn:
      if not sim:
        old = new
      return [ '' ]

    # merge children iteratively
    diff = []
    if tn == 'dir':
      co = { c['properties']['name']: c for c in old['children'] }
      for c in new['children']:
        name = c['properties']['name']
        tp = c['properties']['type']
        if co.has_key(name) and tp == 'dir':
          d = self._merge_(co[name], c, sim)
          diff.extend( map(lambda x: os.path.join(name, x), d) )
        elif not co.has_key(name):
          if not sim:
            old['children'].append(c)
          diff.append( name )

    return diff
  
  # same as merge but only simulate it
  def _diff_(self, old, new):
    return self._merge_(old, new, sim=True)
  
  # simply 1. scrape url, 2. merge new into old
  def reload(self, path):
    root = self.ft.ls(path)
    if not root:
      return

    url = root['properties']['url']
    sc = Scraper(4); sc(url)
    self._merge_(root, sc.ft.root)
  
  def update(self, path):
    root = self.ft.ls(path)
    if not root:
      return

    url = root['properties']['url']
    sc = Scraper(4); sc(url, dep=1) # only scrape the 'surface'
    diff = self._merge_(root, sc.ft.root)

    # only reload diff
    for d in diff:
      d = os.path.join( path, d )
      if self.ft.ls(d)['properties']['type'] == 'dir':
        self.reload(d)
  
  def _sync_(self, r, path):
    p = r['properties']
    tp = p['type']; name = p['name']

    if tp == 'file':
      print './run.sh %s >%s' % ( p['url'], os.path.join(path, name) )
    else:
      print 'mkdir -p %s' % (path)
      for c in r['children']:
        
        self._sync_( c, os.path.join(path, c['properties']['name']) )

  def sync(self):
    # compare, then sync missing to the file system
    for path in self._diff_(self.fs.root, self.ft.root):
      r = self.ft.ls(path)
      self._sync_( r, os.path.join(self.fs.root['properties']['path'], path) )
  
if __name__ == "__main__":
  '''
  ft = FTree(); ft.root = json.load(open('test.json'))
  ft.remove('/2018/12')
  sync = Syncer(ft)
  sync.update('/2018')
  print sync.ft.serialize()
  '''

  '''
  ft = FTree(); ft.root = json.load(open('test.json'))
  print ft.du('/')
  '''

  '''
  sc = Scraper(5); sc('https://topo-data.caida.org/prefix-probing/')
  print sc.ft.serialize()
  
  fs = FSHelper(); fs('/media/disk/temp')
  print fs.ft.serialize()
  '''

  fs = FTree(); fs.root = json.load(open('test2.json'))
  ft = FTree(); ft.root = json.load(open('test.json'))

  sync = Syncer(fs, ft)
  sync.sync()
