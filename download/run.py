import sys
import json
import time

import ft

if __name__ == "__main__":
  fh = ft.FSHelper(); fh('/media/disk/new/ftp/team-1/')

  url = 'https://topo-data.caida.org/team-probing/list-7.allpref24/team-1/daily/'
  pattern = ["${% >= '2018'}/${% >= 'cycle-20181210'}"]
  # sc = ft.Scraper(); sc(url, pat=pattern)
  # print sc.tree.serialize(); exit()

  sc = ft.Scraper(); sc.tree.root = json.load(open('test.json'))
  ft.Syncer.update( sc, '', ["${% > '2018'}"])
  ft.Syncer.update( sc, '2018', ["${% >= 'cycle-20181210'}"])
  # print sc.tree.serialize()

  ft.Syncer.sync( fh, sc )
