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
  result_db_short_lived_sessions = True,
  backend = "db+mysql://%s:%s@%s/%s" % (backend_username, backend_password, backend_ip, database),
  broker_transport_options = {'visibility_timeout': 864000},
  broker_connection_max_retries = 50,
  broker = "redis://%s:%s@%s:%s" % (username, password, broker_ip, port)
)

@app.task
def run(package_fileurl, remote_task_root, run_filename):
  print vars(run.request)
  if vars(run.request).has_key('redelivered') and vars(run.request)['redelivered']:
    return 1

  if len(package_fileurl.split('://')) > 1:
    os.chdir(remote_task_root)
    package_filename = os.path.basename( package_fileurl.split('?')[0] )
    subprocess.Popen( "curl -s -o %s %s" % (package_filename, package_fileurl), shell=True, executable='/bin/bash' ).communicate()
    package_fileurl = os.path.join(remote_task_root, package_filename)

  subprocess.Popen( 'tar zxf %s -C %s' % (package_fileurl, remote_task_root), shell=True ).communicate()

  p = subprocess.Popen( 'bash %s' % (os.path.join(remote_task_root, run_filename)), shell=True )
  p.wait()
  
  return p.returncode
