import subprocess
import threading
import urlparse
import datetime
import json
import sys
import os

class FTree():
  def __init__(self):
    self.ft = {
      'children': [],
      'properties': {
        'name': '',
        'type': 'dir'
      }
    }

  def _children_(self, ptr):
    return { c['properties']['name']: c for c in ptr['children'] }

  def exists(self, path, remove=False):
    fl = filter( lambda x: x, path.split('/') )

    prev = None; ptr = self.ft
    for f in fl:
      if not self._children_(ptr).has_key(f):
        return False
      prev = ptr
      ptr = self._children_(ptr)[f]

    if not prev:
      return
    if remove:
      i = [ i for i in range(len(prev['children'])) if prev['children'][i]['properties']['name'] == f ][0]
      prev['children'].pop(i)
    else:
      return self._children_(prev)[f]['type']

  def remove(self, path):
    self.exists(path, remove=True)

  def mkdirs(self, path, properties):
    fl = filter( lambda x: x, path.split('/') )

    r = self.exists(path)
    if r == 'dir':
      return True
    elif r == 'file':
      return False

    ptr = self.ft
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

    r = self.exists(path)
    if r == 'dir':
      return False
    elif r == 'file':
      return True

    ptr = self.ft
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
    return json.dumps(self.ft, indent=2)


class Scraper():
  def __init__(self, mtn=6):
    self.ft = FTree()
    self.mtn = mtn

  def __call__(self, seed):
    self.ft = FTree()

    self.q = []; self.visited = []
    self.tl = []; self.done = []

    self.ft.ft['properties']['url'] = seed
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

        url = f[0]; dst = f[1]; i = f[2]
        t = threading.Thread( target=self.get, args=(url, dst, i,) )
        t.start()
        self.tl.append(t); self.done.append(False)
    
  def _real_link_(self, url, link):
    return urlparse.urljoin(url, link)

  def deque(self): # not balanced
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
      sys.stderr.write( 'erro: %s\n' % (url) )
      self.done[i] = true

    lock = threading.Lock()
    lock.acquire()

    for l in ll:
      # save result
      if l['type'] == 'file':
        self.ft.touch( os.path.join(dst, l['name']), l )
      else:
        d = os.path.join(dst, l['name'])
        self.ft.mkdirs( d, l )
        # add dirs to queue.
        u = self._real_link_(url, l['link'])
        self.q.append( (u, d, len(self.q)) )
        self.visited.append(False)

    self.done[i] = True

    lock.release()

if __name__ == "__main__":
  s = Scraper(); s('https://topo-data.caida.org/ITDK/')
  print s.ft.serialize()
