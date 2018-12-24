import subprocess
import time

from celery import Celery
from celery import Task

app = Celery(
  'tasks',
  backend = "redis://%s:%s@%s:%s" % ('', '', 'localhost', 6379),
  broker = "redis://%s:%s@%s:%s" % ('', '', 'localhost', 6379)
)

@app.task
def run(cmd):
  print cmd
  p = subprocess.Popen( '%s' % (cmd), shell=True )
  p.wait()

  return p.returncode
