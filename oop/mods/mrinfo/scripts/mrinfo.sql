use edges;

drop table if exists edge_table;
create table if not exists edge_table(
  in_ip varchar(16),
  out_ip varchar(16),
  primary key (in_ip, out_ip),
  key in_ip_index (in_ip),
  key out_ip_index (out_ip)
) engine = MyISAM;

load data local infile 'links.dsv'
into table edge_table
fields terminated by ' ';

drop table if exists node_table;
create table if not exists node_table(
  ip varchar(16),
  ip_int bigint(16),
  key ip_int_index (ip_int),
  primary key (ip)
) engine = MyISAM;

load data local infile 'nodes.dsv'
into table node_table
fields terminated by ' ';
