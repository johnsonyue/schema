import subprocess
import threading
import urlparse
import datetime
import json
import sys
import os

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

  def __call__(self, seed):
    self.ft = FTree()

    # each element in queue contains: (<$full_url>, <$dst_dir>, <$index>)
    self.q = []; self.visited = []
    self.tl = []; self.done = []

    self.ft.root['properties']['url'] = seed
    self.q.append( (seed, '', len(self.q)) ); self.visited.append(False)

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

        url, dst, i = f
        t = threading.Thread( target=self.get, args=(url, dst, i,) )
        t.start()
        self.tl.append(t); self.done.append(False)
    
  def _real_link_(self, url, link):
    return urlparse.urljoin(url, link)

  def deque(self): # TODOs: deque strategy for more balanced search
    for i in range(len(self.q)):
      if not self.visited[i]:
        self.visited[i] = True
        return self.q[i]
        
  def get(self, url, dst, i):
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
        self.q.append( (u, d, len(self.q)) )
        self.visited.append(False)

    self.done[i] = True

    lock.release()


class Syncer():
  def __init__(self, ft):
    self.ft = ft
  
  # merge new into old by traversing new along with old
  def _merge_(self, old, new):
    # replace old on type change
    to = old['properties']['type']; tn = new['properties']['type']
    if to != tn:
      old = new
      return

    # merge children iteratively
    if tn == 'dir':
      co = { c['properties']['name']: c for c in old['children'] }
      for c in new['children']:
        name = c['properties']['name']
        tp = c['properties']['type']
        if co.has_key(name) and tp == 'dir':
          self._merge_(co[name], c)
        elif not co.has_key(name):
          old['children'].append(c)
  
  def update(self, path):
    root = self.ft.ls(path)
    url = root['properties']['url']

    sc = Scraper(2); sc(url)
    self._merge_(root, sc.ft.root)

if __name__ == "__main__":
  '''
  sc = Scraper(2); sc('https://topo-data.caida.org/ITDK/')
  print sc.ft.serialize()
  '''

  ft = FTree(); ft.root = json.load(open('test.json'))
  ft.remove('/ITDK-2018-03/README.txt')

  sync = Syncer(ft)
  sync.update('/ITDK-2018-03')
  print sync.ft.serialize()
