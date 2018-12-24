import os
import sys
import json
import time
from celery import Celery

import ft

url = 'https://topo-data.caida.org/team-probing/list-7.allpref24/team-1/daily/'
pattern = ["${% >= '2018'}/${% >= 'cycle-20181210'}"]
dst = '/media/disk/new/ftp/team-1'

def fsync():
  # file system helper
  fh = ft.FSHelper(); fh(dst)

  # scraper
  if not os.path.exists('test.json'):
    sc = ft.Scraper(); sc(url, pat=pattern)
  else:
    sc = ft.Scraper(); sc.tree.root = json.load(open('test.json'))

  # update
  ft.Syncer.update( sc, '', ["${% > '2018'}"]) # check for new year
  ft.Syncer.update( sc, '2018', ["${% >= 'cycle-20181210'}"]) # check for new date

  # persistence
  json.dump( json.loads(sc.tree.serialize()), open('test.json', 'w') )

  # print tasks
  return ft.Syncer.sync( fh, sc )

if __name__ == "__main__":
  app = Celery(
    'tasks',
    backend = "redis://%s:%s@%s:%s" % ('', '', 'localhost', 6379),
    broker = "redis://%s:%s@%s:%s" % ('', '', 'localhost', 6379)
  )
  while True:
    app.control.purge()
    for t in sorted(  fsync(), key = lambda x: [ x.split('/')[i] for i in (1,2) ] ):
      r = app.send_task( 'worker.run', [ t ], queue="download" )
    time.sleep(60*60)
