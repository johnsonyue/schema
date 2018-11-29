MATCH (:<node>)-[e:<edge>]->(:<node>) DELETE e;
MATCH (n:<node>) DELETE n;

USING PERIODIC COMMIT 1000
LOAD CSV WITH HEADERS FROM 'file:///<nodes>' AS line
CREATE (:<node> {ip: line.ip, is_end: line.is_end});

CREATE INDEX ON :<node>(ip);

USING PERIODIC COMMIT 1000
LOAD CSV WITH HEADERS FROM 'file:///<links>' AS line
MATCH (in:<node> {ip:line.in_ip})
MATCH (out:<node> {ip:line.out_ip})
MERGE (in)-[e:<edge>]->(out)
ON CREATE set
  e.is_dest = line.is_dest,
  e.star = line.star,
  e.delay = line.delay,
  e.freq = line.freq,
  e.ttl = line.ttl,
  e.monitor = line.monitor,
  e.firstseen = line.firstseen,
  e.lastseen = line.lastseen;
