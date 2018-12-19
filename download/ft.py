import subprocess
import threading
import urlparse
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
  
  # merge new into old by traversing new along with old
  @staticmethod
  def merge(old, new, sim=False):
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
          d = FTree.merge(co[name], c, sim)
          diff.extend( map(lambda x: os.path.join(name, x), d) )
        elif not co.has_key(name):
          if not sim:
            old['children'].append(c)
          diff.append( name )

    return diff
  
  # same as merge but only simulate it
  @staticmethod
  def diff(old, new):
    return FTree.merge(old, new, sim=True)


class Scraper():
  def __init__(self, mtn=6):
    self.tree = FTree()
    self.mtn = mtn

  def __call__(self, seed, dep=0, pat=[]):
    self.tree = FTree()
    self.dep = dep
    self.pat = pat

    # each element in queue contains: (<$full_url>, <$dst_dir>, <$index>, <$depth>)
    self.q = []; self.visited = []
    self.tl = []; self.done = []

    self.tree.root['properties']['url'] = seed
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

  def _has_pat_(self, dst, pat):
    dst = os.path.dirname(dst)
    dl = dst.split('/'); pl = pat.split('/')

    for i in range(len(dl)):
      if i < len(dl):
        d = dl[i]; p = pl[i]

        # 1. if ${} expression, eval
        r = re.search(r'\$\{(.*?)\}', p)
        if r and eval( r.group(1).replace('%', "'%s'" % (d)) ):
          continue

        # 2. string, compare
        elif r or d != p:
          return False

    return True

  def _match_(self, d):
    if not self.pat:
      return True
    
    for p in self.pat:
      if self._has_pat_(d, p):
        return True
    
    return False
    
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
      d = os.path.join(dst, l['name'])
      if not self._match_( d ):
        continue
      if l['type'] == 'file':
        self.tree.touch( d, l )
      else:
        self.tree.mkdirs( d, l )
        # add dirs to queue.
        if not self.dep or depth+1 < self.dep:
          self.q.append( (u, d, len(self.q), depth+1) )
          self.visited.append(False)

    self.done[i] = True

    lock.release()


class FSHelper():
  def __init__(self):
    self.tree = FTree()

  def __call__(self, path):
    self.tree = FTree()

    # each element in queue contains: (<$full_url>, <$dst_dir>, <$index>, <$depth>)
    self.q = []; self.visited = []

    self.tree.root['properties']['path'] = path
    self.q.append( (path, '') )

    while self.q:
      path, dst = self.q.pop(0)
      for l in self.get(path):
        p = self._real_path_(path, l['name'])
        l['path'] = p
        # save result
        if l['type'] == 'file':
          self.tree.touch( os.path.join(dst, l['name']), l )
        else:
          d = os.path.join(dst, l['name'])
          self.tree.mkdirs( d, l )
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


# update FSTree from site
# sync site to fs
class Syncer():
  # simply 1. scrape url, 2. merge new into old
  @staticmethod
  def _reload_(root, mtn, pat):
    url = root['properties']['url']
    sc = Scraper(mtn); sc(url, pat=pat)
    FTree.merge(root, sc.tree.root)

  @staticmethod
  def _sync_(r, path):
    p = r['properties']
    tp = p['type']; name = p['name']

    if tp == 'file':
      print './run.sh %s >%s' % ( p['url'], path )
    else:
      print 'mkdir -p %s' % (path)
      for c in r['children']:
        Syncer._sync_( c, os.path.join(path, c['properties']['name']) )

  @staticmethod
  def update(sc, lazy=True):
    t, m, p = sc.tree, sc.mtn, sc.pat

    url = t.root['properties']['url']
    if lazy:
      sc = Scraper(sc.mtn); sc(url, dep=1, pat=p) # only scrape the 'surface'
      diff = FTree.merge(t.root, sc.tree.root)

      # only reload diff
      for d in diff:
        d = os.path.join( path, d )
        r = t.ls(d)['properties']
        if r['type'] == 'dir':
          Syncer._reload_(r, m, p)
    else:
      Syncer._reload_(t.root, m, p)
  
  @staticmethod
  def sync(fh, sc):
    ft, st = fh.tree, sc.tree
    # compare, then sync missing to the file system
    for path in FTree.diff(ft.root, st.root):
      r = st.ls(path)
      Syncer._sync_( r, os.path.join(ft.root['properties']['path'], path) )
