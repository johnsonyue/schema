create database if not exists edges;
use edges;

drop table if exists node_table;
create table if not exists node_table(
  ip varchar(64),
  ip_int decimal(64,0) unsigned,
  reason varchar(16),
  ttl integer,
  primary key (ip),
  key ip_int_index (ip_int),
  key reason_index (reason),
  key rtt_index (rtt)
) engine MyISAM;

load data local infile 'nodes.dsv'
into table node_table
fields terminated by ' ';
