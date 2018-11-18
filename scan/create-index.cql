create index on :node(ip);
create index on :node(rtr_id);

match (n:node) where n.is_end = "N" with count(n) as cnt merge (c:count { is_end : "N", count : cnt });
