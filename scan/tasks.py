import subprocess
import sys
import os
import json

import time

from celery import Celery
from celery import Task
import pika

o = json.load(open('secrets.json'))
broker = o['broker']; backend = o['backend']
username = broker['username']; broker_ip = broker['IP_addr']
password = broker['password']; port = broker['port']

backend_username = backend['username']; backend_ip = backend['IP_addr']
backend_password = backend['password']; database = backend['database']

app = Celery(
  'tasks',
  backend = "db+mysql://%s:%s@%s/%s" % (backend_username, backend_password, backend_ip, database),
  broker = "amqp://%s:%s@%s:%s" % (username, password, broker_ip, port)
)

@app.task
def run(task_id, pkg_fileurl, root):
  task_dir = os.path.join( root, task_id );
  if not os.path.exists(task_dir):
    os.makedirs(task_dir)
  pkg_filename = os.path.basename( pkg_fileurl ); pkg_filepath = os.path.join(task_dir, pkg_filename)

  if len(pkg_fileurl.split('://')) > 1:
    subprocess.Popen( 'curl -v -o %s %s' % (pkg_filepath, pkg_fileurl), shell=True ).communicate()
  subprocess.Popen( 'tar zxf %s -C %s' % (pkg_filepath, task_dir), shell=True ).communicate()

  conf = json.load( open("%s/config.json" % (task_dir)) )
  command = conf['command']
  sys.stderr.write( command + '\n' )
  p = subprocess.Popen( command, shell=True )
  p.wait()
  
  return p.returncode
