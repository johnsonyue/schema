MATCH (:<node>)-[e:<edge>]->(:<node>) DELETE e;
MATCH (n:<node>) DELETE n;

USING PERIODIC COMMIT 1000
LOAD CSV WITH HEADERS FROM '<nodes>' AS line
CREATE (:<node> {ip: line.ip});

CREATE INDEX ON :<node>(ip);

USING PERIODIC COMMIT 1000
LOAD CSV WITH HEADERS FROM '<links>' AS line
MATCH (in:<node> {ip:line.in_ip})
MATCH (out:<node> {ip:line.out_ip})
MERGE (in)-[e:<edge>]->(out);
