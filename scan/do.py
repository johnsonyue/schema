import subprocess
import threading
import json
import datetime
import time
import sys
import os

from celery import Celery
import pika

def usage():
  sys.stderr.write("python do.py <$task_info>\n")

def current_time():
  datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S")

def eval_command(command, inputs, outputs):
  # add prefix
  inputs = map( lambda x: os.path.join(manager_root, x), inputs )
  outputs = map( lambda x: os.path.join(manager_root, x), outputs )

  inputs_str = ' '.join(map( lambda x: '"'+x+'"', inputs ))
  outputs_str = ' '.join(map( lambda x: '"'+x+'"', outputs ))
  p = subprocess.Popen('INPUTS=(%s); OUTPUTS=(%s); echo "%s"' % (inputs_str, outputs_str, command), executable='/bin/bash', shell=True, stdout=subprocess.PIPE)
  
  return p.stdout.read()

def execute_step(step):
  name = step["name"]
  tasks = step["tasks"]

  # step start time
  step['startTime'] = current_time()

  # case 1. local task
  if not tasks[0].has_key('monitorId'):
    for task in tasks:
      command = eval_command( task['command'], task['inputs'], task['outputs'] )
      subprocess.Popen(command, shell=True).communicate()
      # step end time
      step['endTime'] = current_time()
      print json.dumps(task_info)
      return
  
  # case 2. remote task(s)
  monitor_to_info = {} # lookup dictionaries for callbacks
  taskid_to_monitor = {} # reverse lookup
  monitor_list = []
  task_dir = os.path.join( manager_root, task_id )
  
  ## preparing task info
  for task in tasks:
    monitor_id = task['monitorId']; monitor_list.append(monitor_id)
    monitor_to_info[monitor_id] = {}
    monitor_to_info[monitor_id]['monitor_root'] = monitor_db[monitor_id]['WorkDirectory']
    monitor_to_info[monitor_id]['task_id'] = '' # task is not dispatched yet

    monitor_to_info[monitor_id]['local_inputs'] = local_inputs = map( lambda x: x.split(';')[0], task['inputs'] )
    monitor_to_info[monitor_id]['remote_inputs'] = remote_inputs = map( lambda x: x.split(';')[1], task['inputs'] )
    monitor_to_info[monitor_id]['local_outputs'] = local_outputs = map( lambda x: x.split(';')[0], task['outputs'] )
    monitor_to_info[monitor_id]['remote_outputs'] = remote_outputs = map( lambda x: x.split(';')[1], task['outputs'] )
    monitor_to_info[monitor_id]['command'] = eval_command( task['command'], remote_inputs, remote_outputs )
    
    ## monitor_dir
    monitor_dir = os.path.join( task_dir, monitor_id )
    monitor_to_info[monitor_id]['monitor_dir'] = monitor_dir
    if not os.path.exists( monitor_dir ):
      os.makedirs( monitor_dir )

    ## make package
    def make_package(monitor_id):
      monitor_dir = monitor_to_info[monitor_id]['monitor_dir']
      monitor_root = monitor_to_info[monitor_id]['monitor_root']
      remote_taskdir = os.path.join( monitor_root, task_id )
      local_inputs = map( lambda x: os.path.join(manager_root, x), monitor_to_info[monitor_id]['local_inputs'] )
      remote_inputs = map( lambda x: os.path.join(monitor_root, x), monitor_to_info[monitor_id]['remote_inputs'] )
      command = monitor_to_info[monitor_id]['command']

      ## run script
      run = "#!/bin/bash\n"
      for i in range(len(local_inputs)):
        fr = os.path.join( os.path.join(monitor_root, task_id), os.path.basename(local_inputs[i]) )
        to = remote_inputs[i]
        if fr != to:
          run += "mv %s %s\n" % (fr, to)
      run += command+'\n'
      run_filename = name+'.sh'
      run_filepath = os.path.join( remote_taskdir, run_filename )
      open(run_filepath, 'w').write(run)
      
      ## tar input files into one dir
      tar_filename = os.path.join(monitor_id+'.'+name+'.tar.gz')
      tar_filepath = os.path.join(task_dir, tar_filename)
      tar = "tar --transform 's,.*/,,g' -zcf %s -P %s" % (
        tar_filepath,
        ' '.join(local_inputs + [run_filepath])
      )
      subprocess.Popen(tar, shell=True).communicate()
      return tar_filepath, run_filename
  
    tar_filepath, run_filename = make_package(monitor_id)
    monitor_to_info[monitor_id]['tar_filepath'] = tar_filepath
    monitor_to_info[monitor_id]['run_filename'] = run_filename
  
  #print json.dumps( monitor_to_info, indent=2 )

  ## dispatch tasks
  ### task control functions
  def on_run_message(taskid, t): # t is only a place holder
    monitor_id = taskid_to_monitor[taskid]
    monitor_root = monitor_to_info[monitor_id]['monitor_root']
    local_outputs = map( lambda x: os.path.join(monitor_root, x), monitor_to_info[monitor_id]['local_outputs'] )
    remote_outputs = map( lambda x: os.path.join(monitor_root, x), monitor_to_info[monitor_id]['remote_outputs'] )

    for i in range(len(remote_outputs)):
      get = "./run.sh ssh -n %s get -l %s -r %s 1>&2" % ( monitor_id, local_outputs[i], remote_outputs[i])
      h = subprocess.Popen(get, shell=True)
      h.wait()
    # task end time
    step['endTime'] = current_time()
    print json.dumps(task_info)
    return

  def target_func(monitor_id, package_fileurl, remote_taskdir, run_filename):
    r = celery.send_task( 'tasks.run', [package_fileurl, remote_taskdir, run_filename], queue="vp.%s.run" % (monitor_id) )
    taskid_to_monitor[r.task_id] = monitor_id;
    r.get( callback=on_run_message, propagate=False )

  def wait_taskid():
    while True:
      is_done = True
      for v in taskid_to_monitor.values():
        if not v:
          is_done = False
          break
      if not is_done:
        time.sleep(1)
      else:
        break
    print json.dumps(ret_dict); sys.stdout.flush()

  def run_tasks(step):
    thread_list = []
    for monitor in monitor_list:
      monitor_dir = monitor_to_info[monitor]['monitor_dir']
      tar_filepath = monitor_to_info[monitor]['tar_filepath']
      run_filename = monitor_to_info[monitor]['run_filename']

      if not is_manager_push:
        package_fileurl = 'http://%s:%s/%s' % (manager_ip, free_port, tar_filepath)
      else:
        monitor_root = monitor_to_info[monitor]['monitor_root']
        remote_taskdir = os.path.join( monitor_root, task_id )
        tar_filename = os.path.basename(tar_filepath)
        package_fileurl = os.path.join( remote_taskdir, tar_filename )

      # tell worker 3 things: package url, where to unpack, which script to run
      t = threading.Thread( target=target_func, args=(monitor, package_fileurl, remote_taskdir, run_filename) )
      thread_list.append(t)
      t.start()
      ## task start time
      #step['startTime'] = current_time()
    
    [ t.join() for t in thread_list ]
    # step end time
    #step['endTime'] = current_time()
    print json.dumps(task_info)
  
  ### main process
  ### case 1. manager push
  if is_manager_push:
    for monitor in monitor_list:
      tar_filepath = monitor_to_info[monitor_id]['tar_filepath']
      monitor_root = monitor_to_info[monitor_id]['monitor_root']
      remote_taskdir = os.path.join( monitor_root, task_id )
      mkdirs = "./run.sh ssh -n %s mkdirs -r %s 1>&2" % ( monitor, remote_taskdir )
      subprocess.Popen(mkdirs, shell=True).communicate()
      put = "./run.sh ssh -n %s put -l %s -r %s 1>&2" % ( monitor, tar_filepath, remote_taskdir )
      subprocess.Popen(put, shell=True).communicate()
    run_tasks(step)
    return

  ### case 2. worker pull
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
      if not GET.has_key('monitorId'):
        return
      monitor_id = GET['monitorId'][0]
      self.server.is_monitor_visited[monitor_id] = True
      if is_all_true( self.server.is_monitor_visited ):
        self.server.shutdown()
    
  class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    def __init__(self, (HOST,PORT), handler, monitor_list):
      HTTPServer.__init__(self, (HOST, PORT), handler)
      self.is_monitor_visited = { m: False for m in monitor_list }
    
  # parent process as File Server
  import socket
  from contextlib import closing

  def find_free_port():
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
      s.bind(('', 0))
      return s.getsockname()[1]

  free_port = find_free_port()

  if not os.fork():
    server = ThreadedHTTPServer((manager_ip, free_port), Handler, monitor_list)
    server.serve_forever()
  # child process send remote tasks.
  else:
    run_tasks(step)

if __name__ == "__main__":
  if len(sys.argv) < 2:
    usage()
    exit()

  # manager infomation
  monitor_db = { e['Name']: e for e in json.load( open('db.json') ) }

  manager_info = monitor_db['Manager']
  manager_root = manager_info['WorkDirectory']
  manager_ip = manager_info['IP_addr']

  #is_manager_push = manager_info['isManagerPush'] if manager_info.has_key('isManagerPush') else True
  is_manager_push = True

  # task information
  task_info_filepath = sys.argv[1]
  task_info = json.load( open(task_info_filepath) )
  task_id = task_info["id"]
  steps = task_info["steps"]

  ## task start time
  task_info['startTime'] = current_time()
  ## make task directory
  task_dir = os.path.join( manager_root, task_id )
  if not os.path.exists(task_dir):
    os.makedirs( task_dir )

  ## prepare task queue for remote tasks
  secrets = json.load( open('secrets.json') )
  broker = secrets['broker']; backend = secrets['backend']
  broker_username = broker['username']; broker_ip = broker['IP_addr']
  broker_password = broker['password']; broker_port = broker['port']

  backend_username = backend['username']; backend_ip = backend['IP_addr']
  backend_password = backend['password']; backend_database = backend['database']

  celery = Celery()
  celery.conf.update(
    broker_url = "amqp://%s:%s@%s:%s" % (broker_username, broker_password, broker_ip, broker_port),
    result_backend = "db+mysql://%s:%s@%s/%s" % (backend_username, backend_password, backend_ip, backend_database)
  )

  ## execute task steps
  for step in steps:
    execute_step(step)

  ## task end time
  task_info['endTime'] = current_time()
  print json.dumps(task_info)
