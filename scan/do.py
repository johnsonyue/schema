import subprocess
import json
import time
import sys
import os

from celery import Celery
import pika

def usage():
  sys.stderr.write("python do.py <$conf_filepath>\n")

if len(sys.argv) < 2:
  usage()
  exit()

# configuration
conf_filepath = sys.argv[1]

## config filename as task id.
secrets = json.load(open('secrets.json'))
root = secrets['root']
site_url = secrets['site_url']
nodes = { n['name']: n for n in secrets['nodes'] }
## make task directory
task_id = os.path.basename(conf_filepath).rstrip('.json').rstrip('.config')

task_dir = os.path.join(root, task_id)
if not os.path.exists(task_dir):
  os.makedirs( task_dir )

conf = json.load(open(conf_filepath))

## push
push = conf['push'] if conf.has_key('push') else True

## cmd
params = conf['parameters']
cmd = params['cmd'];

## target
target_fileurl = conf['target_fileurl']
target_filepath = os.path.join(task_dir, task_id+".target_list"); iplist_filepath = os.path.join(task_dir, task_id+".iplist")
analyze_result_filepath = os.path.join(task_dir, task_id+".links")
geo_result_filepath = os.path.join(task_dir, task_id+".geo")

sys.stderr.write("generating ip list ... \n")
subprocess.Popen("curl -s -o %s %s" % (target_filepath, target_fileurl), shell = True).communicate()
if cmd == 'trace':
  subprocess.Popen("cat %s | ./run.sh target -c %s >%s" % (target_filepath, conf_filepath, iplist_filepath), shell = True).communicate()
else:
  subprocess.Popen("cp %s %s" % (target_filepath, iplist_filepath), shell = True).communicate()

## node deps.
nl = conf['nodes'].split(',')
node_info = {}
for n in nl:
  ### command.
  node_root = nodes[n]['directory']
  if cmd == 'trace':
    method = params['method'] if params.has_key('method') else 'udp-paris'
    pps = int(params['pps']) if params.has_key('pps') else 100

    node_iplist_filepath = os.path.join(task_id, task_id+".iplist"); node_iplist_filepath = os.path.join(node_root, node_iplist_filepath)
    node_result_filepath = os.path.join(task_id, task_id+".warts"); node_result_filepath = os.path.join(node_root, node_result_filepath)
    node_analyze_result_filepath = os.path.join(task_id, task_id+".links"); node_analyze_result_filepath = os.path.join(node_root, node_analyze_result_filepath)

    command = "scamper -c '%s -P %s' -p %d -O warts -o %s -f %s" % (cmd, method, pps, node_result_filepath, node_iplist_filepath)
  elif cmd == 'iffinder':
    concurrency = int(params['concurrency']) if params.has_key('concurrency') else 100
    pps = int(params['pps']) if params.has_key('pps') else 100
    node_iplist_filepath = os.path.join(task_id, task_id+".iplist"); node_iplist_filepath = os.path.join(node_root, node_iplist_filepath)
    node_result_filepath = os.path.join(task_id, task_id+".iffout"); node_result_filepath = os.path.join(node_root, node_result_filepath)
    node_result_filepath_prefix = node_result_filepath.rstrip('.iffout')
    command = "iffinder -c %d -r %d -o %s %s && rm %s.ifferr" % (concurrency, pps, node_result_filepath_prefix, node_iplist_filepath, node_result_filepath_prefix, node_result_filepath_prefix)
  elif cmd == 'pingscan':
    node_iplist_filepath = os.path.join(task_id, task_id+".iplist"); node_iplist_filepath = os.path.join(node_root, node_iplist_filepath)
    node_result_filepath = os.path.join(task_id, task_id+".xml"); node_result_filepath = os.path.join(node_root, node_result_filepath)
    command = "nmap -sn -PA -PS443 -PU -PY -PO2,4 -PE -PP -PM -n -iL %s -oX %s" % (node_iplist_filepath, node_result_filepath)

  ### packaging.
  #### iplist
  node_dir = os.path.join(task_dir, n)
  if not os.path.exists(node_dir):
    os.makedirs( node_dir )

  info = {}; info['node_dir'] = node_dir; info['result_filepath'] = node_result_filepath;
  info['analyze_result_filepath'] = node_analyze_result_filepath;
  info['command'] = command;
  node_info[n] = info

  subprocess.Popen("cp %s %s" % (iplist_filepath, node_dir), shell = True).communicate()
  #### config
  node_config_filepath = os.path.join(node_dir, 'config.json')
  node_conf = {'command': command}
  json.dump( node_conf, open(node_config_filepath, 'wb'), indent=2 )

  package_filepath = os.path.join( task_dir, n+".tar.gz" )
  subprocess.Popen("tar zcf %s -C %s ." % (package_filepath, node_dir), shell = True).communicate()

# task deps
task_id_dict = { n: '' for n in nl }
def id_2_nodename(d, Id):
  for k,v in d.items():
    if v == Id:
      return k
## callback
def on_run_message(Id, task):
  node_name = id_2_nodename( task_id_dict, Id )
  node_dir = node_info[node_name]['node_dir']
  node_result_filepath = node_info[node_name]['result_filepath']

  get = "./run.sh ssh -n %s get -l %s -r %s 1>&2" % ( node_name, node_dir, node_result_filepath )
  h = subprocess.Popen(get, shell=True)
  h.wait()
  return os.path.basename(node_result_filepath)

## start remote task
broker = secrets['broker']; backend = secrets['backend']
username = broker['username']; broker_ip = broker['IP_addr']
password = broker['password']; port = broker['port']

backend_username = backend['username']; backend_ip = backend['IP_addr']
backend_password = backend['password']; database = backend['database']

celery = Celery()
celery.conf.update(
  broker_url = "amqp://%s:%s@%s:%s" % (username, password, broker_ip, port),
  result_backend = "db+mysql://%s:%s@%s/%s" % (backend_username, backend_password, backend_ip, database)
)

import threading
def target_func(node_name, node_root, package_fileurl):
  r = celery.send_task( 'tasks.run', [task_id, package_fileurl, node_root], queue="vp.%s.run" % (node_name) )
  task_id_dict[node_name] = r.task_id;
  r.get( callback=on_run_message, propagate=False )

def run_tasks(push):
  thread_list = []
  for n in nl:
    package_filepath = n+".tar.gz"
    if push:
      node_root = nodes[n]['directory']
      package_fileurl = '%s' % ( os.path.join(node_root, package_filepath) )
    else:
      package_fileurl = 'http://%s:%s/%s?node=%s' % (mngr_ip, free_port, package_filepath, n)
    node_root = nodes[n]['directory']

    t = threading.Thread( target=target_func, args=(n, node_root, package_fileurl) )
    thread_list.append(t)
    t.start()
  
  while True:
    is_done = True
    for v in task_id_dict.values():
      if not v:
        is_done = False
        break
    if not is_done:
      time.sleep(1)
    else:
      break
  ret_dict = { n: {'task_id': task_id_dict[n], 'command': node_info[n]['command'], 'result_filepath': node_info[n]['result_filepath'], 'analyze_result_filepath': node_info[n]['analyze_result_filepath'], 'node_ip_addr': nodes[n]['IP_addr']} for n in nl }
  ret_dict['combined'] = {}
  ret_dict['combined']['analyze_result_filepath'] = analyze_result_filepath
  ret_dict['combined']['site_url'] = os.path.join(site_url, '?task='+task_id)

  log_filepath = os.path.join(task_dir, task_id+".log");
  json.dump( ret_dict, open(log_filepath, 'w') )

  print json.dumps(ret_dict); sys.stdout.flush()
  [ t.join() for t in thread_list ]

# analyze
def warts2link(warts_filepath):
  subprocess.Popen("./analyze warts2link %s" % (warts_filepath), shell = True).communicate()
def analyze():
  if cmd == 'trace':
    # warts2link
    thread_list = []
    for n in nl:
      node_dir = os.path.join(task_dir, n); result_filepath = os.path.join( node_dir, task_id+'.warts' )
      t = threading.Thread( target=warts2link, args=(result_filepath,) )
      thread_list.append(t)
      t.start()
    [ t.join() for t in thread_list ]
    
    # merge
    h = subprocess.Popen("perl linkmerge.pl >%s" % (analyze_result_filepath), shell = True, stdin=subprocess.PIPE)
    for n in nl:
      node_dir = os.path.join(task_dir, n); node_analyze_result_filepath = os.path.join( node_dir, task_id+'.links' )
      h.stdin.write( node_analyze_result_filepath + '\n' )
    h.stdin.close()
    h.wait()
    
    # iface.
    ifaces_filepath = analyze_result_filepath.rstrip('.links') + '.ifaces'
    subprocess.Popen("./analyze link2iface %s" % (analyze_result_filepath), shell = True).communicate()
    subprocess.Popen("cat %s | perl geo-labeling.pl ../web/import/GeoLite2-Country-Blocks-IPv4.csv ../web/import/GeoLite2-Country-Locations-en.csv >%s" % (analyze_result_filepath, geo_result_filepath), shell = True).communicate()
    subprocess.Popen("./import.sh %s %s %s" % (geo_result_filepath, ifaces_filepath, task_id), shell = True).communicate()

# push
if push:
  for n in nl:
    ### command.
    node_root = nodes[n]['directory']
    package_filepath = os.path.join( task_dir, n+".tar.gz" )
    remote_task_dir = os.path.join( node_root, task_id )
    remote_package_filepath = os.path.join( remote_task_dir, n+".tar.gz" )

    mkdirs = "./run.sh ssh -n %s mkdirs -r %s 1>&2" % (n, remote_task_dir)
    h = subprocess.Popen(mkdirs, shell=True)
    h.wait()

    put = "./run.sh ssh -n %s put -l %s -r %s 1>&2" % ( n, package_filepath, remote_package_filepath )
    h = subprocess.Popen(put, shell=True)
    h.wait()
  run_tasks(push=True)
  analyze()
  exit()

# pull
from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler
from SocketServer import ThreadingMixIn
import random
import urlparse

def is_all_true(d):
  for v in d.values():
    if not v:
      return False
  return True

class Handler(BaseHTTPRequestHandler):
  def do_GET(self):
    self.send_response(200)
    self.end_headers()
    parsed = urlparse.urlparse( self.path )
    filepath = os.path.join( task_dir, parsed.path.lstrip('/') )

    self.wfile.write( open(filepath).read() )

    GET = urlparse.parse_qs( parsed.query )
    if not GET.has_key('node'):
      return
    node = GET['node'][0]
    self.server.node_dict[node] = True
    if is_all_true( self.server.node_dict ):
      self.server.shutdown()
  
class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
  def __init__(self, (HOST,PORT), handler, node_list):
    HTTPServer.__init__(self, (HOST, PORT), handler)
    self.node_dict = { n: False for n in node_list }
    self.stop = False
  
# parent process as File Server
import socket
from contextlib import closing

def find_free_port():
  with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
    s.bind(('', 0))
    return s.getsockname()[1]

mngr_ip = secrets['mngr_ip']
free_port = find_free_port()

if not os.fork():
  server = ThreadedHTTPServer((mngr_ip, free_port), Handler, nl)
  server.serve_forever()
# child process send remote tasks.
else:
  run_tasks(push=False)
  analyze()
