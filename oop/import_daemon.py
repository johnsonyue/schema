import subprocess
import threading
import argparse
import json
import time
import sys
import os
import re

import MySQLdb as mdb

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

secrets = json.load( open('import-daemon.json') )
backend = secrets['backend']
backend_username = backend['username']; backend_ip = backend['IP_addr']
backend_password = backend['password']; backend_database = backend['database']

def import_thread_func(_conf_filepath, conf_filepath, dir_path, dirs_importing, task_info):
  # save config object
  conf = json.load(open(_conf_filepath))

  # create config file without "<$size>-" prefix
  sys.stderr.write("cp %s %s\n" % ( _conf_filepath,  conf_filepath))
  subprocess.Popen("cp %s %s" % ( _conf_filepath,  conf_filepath), shell=True).communicate()

  subprocess.Popen("python run.py -m import %s" % (conf_filepath), shell=True).communicate()

  # remove all config files
  sys.stderr.write("rm %s %s\n" % (_conf_filepath, conf_filepath))
  subprocess.Popen("rm %s %s" % (_conf_filepath, conf_filepath), shell=True).communicate()
  del dirs_importing[dir_path]

  # insert/update corresponding entry in "celery_task_list" table
  try:
    con = mdb.connect(backend_ip, backend_username, backend_password, backend_database)
    cur = con.cursor()
    task_info = json.dumps( task_info )
    task_id = os.path.basename(conf_filepath).rsplit('.', 1)[0]
    task_type = conf['user_config']['taskType']
    config = json.dumps( conf, indent=4 )
    status = 'complete'
    sql = "INSERT INTO task_list (task_name, task_id, task_type, config, task_info, status) VALUES (%s, %s, %s, %s, %s, %s) ON DUPLICATE KEY UPDATE task_info=%s, status=%s"
    sys.stderr.write('%s\n' % (sql))
    cur.execute(sql, (task_id, task_id, task_type, config, task_info, status, task_info, status))
  except mdb.Error, e:
    print 'error', e
    pass
  finally:
    if con:
      con.commit()
      con.close()

if __name__ == "__main__":
  parser = argparse.ArgumentParser()
  parser.add_argument(
    "sync_root", 
    type=str,
    help="path to sync_folder"
  )
  args = parser.parse_args()

  sync_root = args.sync_root

  dirs_importing = {}
  # try:
  while True:
    fh = FSHelper(); fh(sync_root)
    for d in filter(lambda x: x['properties']['type'] == 'dir', fh.tree.ls('/')['children']):
      dir_path = d['properties']['path']
      if dir_path in dirs_importing:
        sys.stderr.write( 'Directory: %s still syncing\n' % (d['properties']['path']) )
        continue
      conf_file = filter(lambda x: re.match('.+\.(conf|config)$', x['properties']['name']), d['children'])
      if not conf_file or conf_file[0]['properties']['size'] != conf_file[0]['properties']['name'].split('-')[0]:
        sys.stderr.write( 'Not yet synced or already imported: %s\n' % (d['properties']['path']) )
        continue
      _conf_filepath = conf_file[0]['properties']['path']
      conf_filename = os.path.basename(_conf_filepath).split('-', 1)[1]
      conf_filepath = os.path.join(os.path.dirname(_conf_filepath), conf_filename)

      log_file = filter(lambda x: re.match('.+\.(log)$', x['properties']['name']), d['children'])
      if not log_file:
        sys.stderr.write( 'No log file provided: %s\n' % (d['properties']['path']) )
        continue
      log_filepath = log_file[0]['properties']['path']
      task_info = json.load(open(log_filepath))

      t = threading.Thread( target=import_thread_func, args=(_conf_filepath, conf_filepath, dir_path, dirs_importing, task_info, ) )
      dirs_importing[dir_path] = None # set dir_path to "syncing"
      sys.stderr.write( 'Start importing directory: %s\n' % (d['properties']['path']) )
      t.start()

    time.sleep(5)
  # except Exception, e:
  #   sys.stderr.write('%s\n' % (e))
  #   exit()
  # except KeyboardInterrupt:
  #   sys.stderr.write('Ctrl+C\n')
  #   exit()
