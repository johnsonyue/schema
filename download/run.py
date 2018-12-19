import ft

if __name__ == "__main__":
  fh = FSHelper(); fh('/media/disk/temp')
  #sc = Scraper(5); sc('https://topo-data.caida.org/team-probing/list-7.allpref24/team-1/daily/', pat=["${% >= '2018'}/${% >= 'cycle-20181210'}"])
  #print sc.tree.serialize()
  sc = Scraper(5)
  sc.tree.root = json.load(open('test.json'))
  sc.pat = ["${% >= '2018'}/${% >= 'cycle-20181210'}"]

  Syncer.sync( fh, sc )
  #Syncer.update( sc, lazy=False )
  #Syncer.sync( fh, sc )
