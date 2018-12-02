import python_jsonschema_objects as pjs
from contextlib import closing
import socket
import subprocess
import threading
import json
import datetime
import time
import sys
import os

from celery import Celery
import pika

from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler
from SocketServer import ThreadingMixIn
import cgi
import random
import urlparse

def usage():
  sys.stderr.write("python do.py <$conf_filename>\n")

def current_time():
  return datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S")

def get_celery_object():
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

  return celery

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
    filepath = os.path.join( self.server.task_root, parsed.path.lstrip('/') )

    self.wfile.write( open(filepath).read() )

    GET = urlparse.parse_qs( parsed.query )
    if not GET.has_key('monitorId'):
      return
    monitor_id = GET['monitorId'][0]
    self.server.is_monitor_visited[monitor_id] = True
    if is_all_true( self.server.is_monitor_visited ):
      self.server.shutdown()
  
class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
  def __init__(self, (HOST,PORT), handler, task_root, monitor_list):
    HTTPServer.__init__(self, (HOST, PORT), handler)
    self.task_root = task_root
    self.is_monitor_visited = { m: False for m in monitor_list }
    

class TaskConfigParser():
  def __init__(self, conf_filepath, schema_filepath):
    self.conf_filepath = conf_filepath
    self.conf_filename = os.path.basename(conf_filepath)
    self.conf = json.load( open(conf_filepath) )['user_config']
    self.schema = json.load( open(schema_filepath) )
    self.task_id = os.path.basename(conf_filepath).rsplit('.', 1)[0]
  
  def __get_class_from_schema__(self):
    # schema namespace
    builder = pjs.ObjectBuilder( self.schema )
    ns = builder.build_classes()
    # classes in namespace
    TaskGraph = ns.TaskGraph
    Step = ns.Step; Task = ns.Task;
    
    return TaskGraph, Step, Task
  
  def generate_task_info(self):
    # necessary shared infomation
    task_type = self.conf['taskType']

    # task_type is oneOf "traceroute", "pingscan", etc.
    if task_type == "traceroute":
      task_info = self._generate_traceroute_info_()
    elif task_type == "pingscan":
      task_info = self._generate_pingscan_info_()

    # return json string
    return task_info

  def _generate_traceroute_info_(self):
    # classes
    TaskGraph, Step, Task = self.__get_class_from_schema__()
    # taskGraph object
    task_graph = TaskGraph(id=self.task_id, steps=[])

    # traceroute dependencies
    traceroute_method = self.conf["tracerouteMethod"]
    monitor_list = self.conf["monitorList"]["detail"]

    # traceroute step 1
    s1 = Step(name="target sampling", tasks=[])
    
    target_filepath = self.conf['targetInput']['detail']
    if len(target_filepath.split('://')) > 1:
      target_filepath += '#%s' % (os.path.basename(target_filepath))
    
    t = Task()
    t.inputs = [ target_filepath, os.path.realpath(self.conf_filepath) ]
    t.outputs = [ self.task_id+".ip_list" ]
    t.command = "cat ${INPUTS[0]} | ./run.sh target -c ${INPUTS[1]} >${OUTPUTS[0]}"
    s1.tasks.append(t)
    
    task_graph.steps.append(s1)

    # traceroute step 2
    s2 = Step(name="traceroute", tasks=[])
    for monitor in monitor_list:
      method = traceroute_method["method"]
      attemps = traceroute_method["attemps"]
      firstHop = traceroute_method["firstHop"]
      pps = traceroute_method["pps"]

      t = Task(monitorId=monitor)
      t.inputs = [ "%s;%s" % ( self.task_id+'.ip_list', self.task_id+'.ip_list' ) ]
      t.outputs = [ "%s;%s" % ( os.path.join(monitor, self.task_id+'.warts'), self.task_id+'.warts' ) ]
      t.command = "scamper -c 'trace -P %s' -p %d -O warts -o ${OUTPUTS[0]} -f ${INPUTS[0]}" % (method, pps)
      s2.tasks.append(t)
    
    task_graph.steps.append(s2)

    # traceroute step 3
    s3 = Step(name="warts2iface", tasks=[])

    t = Task()
    t.inputs = [ os.path.join("*", self.task_id+'.warts') ]
    t.outputs = [ self.task_id+'.ifaces', self.task_id+'.links' ]
    t.command = "./analyze warts2iface ${INPUTS[0]} ${OUTPUTS[0]}"
    s3.tasks.append(t)
    
    task_graph.steps.append(s3)

    # traceroute step 4
    s4 = Step(name="iffinder", tasks=[])
    for monitor in monitor_list:
      t = Task(monitorId=monitor)
      t.inputs = [ "%s;%s" % ( self.task_id+'.ifaces', self.task_id+'.ifaces' ) ]
      t.outputs = [ "%s;%s" % ( os.path.join(monitor, self.task_id+'.iffout'), self.task_id+'.iffout' ) ]
      t.command = "iffinder -c 100 -r %d -o $(echo ${OUTPUTS[0]} | sed 's/\.iffout//') ${INPUTS[0]}" % (pps)
      s4.tasks.append(t)
    
    task_graph.steps.append(s4)
    # traceroute step 5

    s5 = Step(name="iffout2aliases", tasks=[])

    t = Task()
    t.inputs = [ os.path.join("*", self.task_id+'.iffout') ]
    t.outputs = [ self.task_id+'.aliases' ]
    t.command = "cat ${INPUTS[0]} | grep -v '#' | awk '{ if(\$NF == \\\"D\\\") print \$1\\\" \\\"\$2}' | sort -u >${OUTPUTS[0]}"
    s5.tasks.append(t)
    
    task_graph.steps.append(s5)

    # traceroute step 6
    s6 = Step(name="import", tasks=[])

    t = Task()
    t.inputs = [ os.path.join("*", self.task_id+'.links'), self.task_id+'.ifaces' ]
    t.outputs = [ self.task_id+'.links.geo' ]
    t.command = "cat ${INPUTS[0]} | ./run.sh geo >${OUTPUTS[0]}; ./import.sh ${OUTPUTS[0]} ${INPUTS[1]} %s" % (self.task_id)
    s6.tasks.append(t)
    
    task_graph.steps.append(s6)
    
    # return task_graph object
    return json.loads(task_graph.serialize())

  def _generate_pingscan_info_(self):
    return

class TaskRunner():
  def __init__(self, task_info, monitor_info):
    # keep a copy of task_info for logging
    self.task_info = task_info

    # task info
    self.task_id = self.task_info['id']
    self.steps = self.task_info["steps"]

    # monitor info
    self.monitor_db = { e['Name']: e for e in monitor_info }
    manager_info = self.monitor_db['Manager']
    self.manager_root = manager_info['WorkDirectory']
    self.manager_ip = manager_info['IP_addr']
    #self.is_manager_push = manager_info['isManagerPush'] if manager_info.has_key('isManagerPush') else True
    self.is_manager_push = False

    # celery
    self.celery = get_celery_object()
  
  ## helper functions

  # get full path from relative local[;remote] path
  # relative to $<task_root>, $<remote_task_root>
  def __real_paths__(self, path, monitor_id=''):
    ## case 1. absolute path return as is
    if path and path[0] == '/':
      return path,

    ## case 2. relative path
    task_root = os.path.join( self.manager_root, self.task_id )
    f = path.split(';')
    local_path = f[0]; local_path = os.path.join(task_root, local_path)
    
    # give only 1 path
    if len(f) == 1:
      return local_path,

    monitor_root = self.monitor_root[monitor_id]
    remote_task_root = os.path.join( monitor_root, self.task_id )
    remote_path = f[1]; remote_path = os.path.join(remote_task_root, remote_path)

    return local_path, remote_path
  
  def __eval_command__(self, inputs, outputs, command):
    # add prefix
    inputs_str = ' '.join(map( lambda x: '"'+x+'"', inputs ))
    outputs_str = ' '.join(map( lambda x: '"'+x+'"', outputs ))
    p = subprocess.Popen('INPUTS=(%s); OUTPUTS=(%s); echo "%s"' % (inputs_str, outputs_str, command), executable='/bin/bash', shell=True, stdout=subprocess.PIPE)
    
    return p.stdout.read()
  def __find_free_port__(self):
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
      s.bind(('', 0))
      return s.getsockname()[1]

  ## make package:
  #    1. package: put local inputs into one directory
  #    2. transfer: send package to <$self.task_id>/ directory
  #    3. make script: put each file in the package to corresponding path, then run command
  ## params:
  #    $inputs: what to pack,
  #    $outputs: referenced by command
  #    $command: used to make run script
  #    $step_name, $monitor_id: for whom and which step
  def _make_package_(self, monitor_id, inputs, outputs, command, step_name):
    ## get real path
    local_inputs = map( lambda x: self.__real_paths__(x, monitor_id)[0], inputs )
    remote_inputs = map( lambda x: self.__real_paths__(x, monitor_id)[1], inputs )

    remote_outputs = map( lambda x: self.__real_paths__(x, monitor_id)[1], outputs )
    command = self.__eval_command__(remote_inputs, remote_outputs, command)

    ## froms, <$self.task_id>/<$local_input.basename>
    frs = map( lambda x: self.__real_paths__(';'+os.path.basename(x), monitor_id)[1], local_inputs )
    ## make run script
    run = "#!/bin/bash\n"
    for i in range(len(local_inputs)):
      fr = frs[i]
      to = remote_inputs[i]
      if fr != to:
        run += "mv %s %s\n" % (fr, to)
    run += command+'\n'
    run_filename = '%s.sh' % (step_name)
    run_filepath = self.__real_paths__( os.path.join(monitor_id, run_filename), monitor_id )[0]
    open(run_filepath, 'w').write(run)
    
    ## tar input files into one dir
    package_filename = "%s.%s.tar.gz" % (monitor_id, step_name)
    package_filepath = self.__real_paths__(package_filename)[0]
    tar = "tar --transform 's,.*/,,g' -zcf %s -P %s" % (
      package_filepath,
      ' '.join(local_inputs + [run_filepath])
    )
    subprocess.Popen(tar, shell=True).communicate()
    return package_filepath, run_filename

  def on_run_message(self, taskid, t): # t is only a place holder
    monitor_id = self.taskid_to_monitor[taskid]
    monitor_root = self.monitor_root[monitor_id]
    monitor_task = self.monitor_task[monitor_id]
    outputs = monitor_task['outputs']

    ## get real path
    local_outputs = map( lambda x: self.__real_paths__(x, monitor_id)[0], outputs)
    remote_outputs = map( lambda x: self.__real_paths__(x, monitor_id)[1], outputs)

    ## manager pull results.
    for i in range(len(remote_outputs)):
      get = "./run.sh ssh -n %s get -l %s -r %s 1>&2" % ( monitor_id, local_outputs[i], remote_outputs[i])
      h = subprocess.Popen(get, shell=True)
      h.wait()
    return

  def task_thread_func(self, task, monitor_id, package_fileurl, remote_task_root, run_filename):
    r = self.celery.send_task( 'tasks.run', [package_fileurl, remote_task_root, run_filename], queue="vp.%s.run" % (monitor_id) )
    self.taskid_to_monitor[r.task_id] = monitor_id;
    r.get( callback=self.on_run_message, propagate=False )

    task['endTime'] = current_time()
    print json.dumps(self.task_info)

  def run_tasks(self, tasks):
    thread_list = []
    for task in tasks:
      task['startTime'] = current_time()
      print json.dumps(self.task_info)

      monitor_id = task['monitorId']
      # where to get package, which script to run
      package_filepath, run_filename = self.monitor_task[monitor_id]['packageInfo']
      package_filename = os.path.basename( package_filepath )

      if not self.is_manager_push:
        package_fileurl = 'http://%s:%s/%s?monitorId=%s' % (self.manager_ip, self.free_port, package_filename, monitor_id)
      else:
        package_filename = os.path.basename( package_filepath )
        package_fileurl = self.__real_paths__(';'+package_filename, monitor_id)[1]

      # where to unpack
      remote_task_root = self.__real_paths__(';', monitor_id)[1]

      t = threading.Thread( target=self.task_thread_func, args=(task, monitor_id, package_fileurl, remote_task_root, run_filename) )
      thread_list.append(t)
      t.start()
    
    [ t.join() for t in thread_list ]

  def run_step(self, step):
    step['startTime'] = current_time()
    print json.dumps(self.task_info)

    tasks = step['tasks']

    # download inputs that are urls
    for task in tasks:
      for i in range(len(task['inputs'])):
        input = task['inputs'][i].split(';')[0]
        f = input.split('#')
        if len(f) > 1:
          url = f[0]; input = f[1]
          realpath = self.__real_paths__(input)[0]
          if not os.path.exists(realpath):
            subprocess.Popen( "curl -s -o %s %s" % (realpath, url), shell=True).communicate()
          task['inputs'][i] = input

    # case 1. local task
    if not tasks[0].has_key('monitorId'):
      for task in tasks:
        inputs = map( lambda x: self.__real_paths__(x)[0], task['inputs'] )
        outputs = map( lambda x: self.__real_paths__(x)[0], task['outputs'] )
        command = self.__eval_command__( inputs, outputs, task['command'] )
        subprocess.Popen(command, shell=True).communicate()

        step['endTime'] = current_time()
        print json.dumps(self.task_info)
        return

    # case 2. remote tasks
    step_name = step["name"]
    monitor_tasks = step["tasks"]
    
    self.monitor_root = {}
    self.monitor_task = { t['monitorId']: t for t in monitor_tasks }
    self.taskid_to_monitor = {} # reverse lookup

    ## prepare task
    for task in monitor_tasks:
      monitor_id = task['monitorId']
      inputs = task['inputs']
      outputs = task['outputs']
      command = task['command']
  
      self.monitor_root[monitor_id] = self.monitor_db[monitor_id]['WorkDirectory']

      ## make monitor sub-directory
      monitor_dir = self.__real_paths__(monitor_id)[0]
      if not os.path.exists(monitor_dir):
        os.makedirs( monitor_dir )
      
      ## make package
      self.monitor_task[monitor_id]['packageInfo'] = package_filepath, run_filename = self._make_package_(monitor_id, inputs, outputs, command, step_name)
      
    ## dispatch task
    ## case 1. manager push
    if self.is_manager_push:
      ## push packages
      for task in monitor_tasks:
        monitor_id = task['monitorId']
        package_filepath = self.monitor_task[monitor_id]['packageInfo'][0]
        remote_task_root = self.__real_paths__(';', monitor_id)[1]

        mkdirs = "./run.sh ssh -n %s mkdirs -r %s 1>&2" % ( monitor_id, remote_task_root )
        subprocess.Popen(mkdirs, shell=True).communicate()

        put = "./run.sh ssh -n %s put -l %s -r %s 1>&2" % ( monitor_id, package_filepath, remote_task_root )
        subprocess.Popen(put, shell=True).communicate()
      ## run tasks
      self.run_tasks(monitor_tasks)

      step['endTime'] = current_time()
      print json.dumps(self.task_info)
      return

    ## case 2. worker pull
    self.free_port = self.__find_free_port__()
    monitor_list = map( lambda x: x['monitorId'], monitor_tasks )
    task_root = self.__real_paths__('')[0]
    # parent process serves packages
    pid = os.fork()
    if pid:
      server = ThreadedHTTPServer((self.manager_ip, self.free_port), Handler, task_root, monitor_list)
      server.serve_forever()
      os.waitpid(pid, 0) # important! wait for step to finish
    # child process send remote tasks
    else:
      self.run_tasks(monitor_tasks)

      step['endTime'] = current_time()
      print json.dumps(self.task_info)

  def run(self):
    ## make task root directory
    task_root = os.path.join( self.manager_root, self.task_id )
    if not os.path.exists(task_root):
      os.makedirs( task_root )

    self.task_info['startTime'] = current_time()
    print json.dumps(self.task_info)

    ## run task steps
    for step in self.steps:
      self.run_step(step)

    self.task_info['endTime'] = current_time()
    print json.dumps(self.task_info)

if __name__ == "__main__":
  if len(sys.argv) < 2:
    usage()
    exit()

  conf_filepath = sys.argv[1]
  # task info
  task_config_parser = TaskConfigParser(conf_filepath, 'info.schema')
  task_info = task_config_parser.generate_task_info()
  # monitor info
  monitor_info = json.load( open('db.json') )
  # run task
  task_runner = TaskRunner(task_info, monitor_info)
  task_runner.run()