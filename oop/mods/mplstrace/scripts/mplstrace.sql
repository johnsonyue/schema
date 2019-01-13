create database if not exists edges;
use edges;

drop table if exists edge_table;
create table if not exists edge_table(
  in_ip varchar(64),
  out_ip varchar(64),
  is_dest char(1),
  star integer,
  delay float,
  frequency integer,
  ttl varchar(10),
  monitor varchar(64),
  in_mpls varchar(10),
  out_mpls varchar(10),
  in_role varchar(10),
  out_role varchar(10),
  in_label varchar(255),
  out_label varchar(255),
  label varchar(255),
  primary key (in_ip, out_ip),
  key in_ip_index (in_ip),
  key out_ip_index (out_ip),
  key monitor_index (monitor)
) engine MyISAM;

load data local infile 'links.dsv'
into table edge_table
fields terminated by ' ';

drop table if exists node_table;
create table if not exists node_table(
  ip varchar(64),
  ip_int decimal(64,0) unsigned,
  is_end char(1),
  rtr_id integer,
  asn integer,
  pop_id integer,
  country varchar(255),
  region varchar(255),
  city varchar(255),
  label varchar(255),
  primary key (ip),
  key ip_int_index (ip_int),
  key rtr_id_index (rtr_id),
  key asn_index (asn),
  key pop_id_index (pop_id),
  key country_index (country),
  key city_index (city)
) engine MyISAM;

load data local infile 'nodes.dsv'
into table node_table
fields terminated by ' ';
