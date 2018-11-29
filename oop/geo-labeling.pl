#!/usr/local/bin/perl

use strict;

my $geolite_block_file = $ARGV[0] ? $ARGV[0] : "-";
my $geolite_location_file = $ARGV[1] ? $ARGV[1] : "-";

use Net::Patricia;
my $block_tb = new Net::Patricia;
my %location_tb;

&load_geolite_country();

while(<STDIN>) {
  chomp;
  my @s = split / /, $_;
  print "@s ". &get_geo($s[0]) . " " . &get_geo($s[1]) ."\n";
}

sub get_geo {
  my $ip_addr = shift;
  my $ret = $block_tb->match_string($ip_addr);
  return ($ret and $location_tb{$ret}) ?  $location_tb{$ret} : "--";
}

sub load_geolite_country {
  open my $fh, "<", $geolite_block_file or die "Can not open file: $!\n";
  while(<$fh>){
    chomp;
    my @F = split /,/;
    next if ($F[0] !~ /^[\d\.]+\/\d+$/);
    $block_tb->add_string($F[0], $F[1]);
  }
  close $fh;

  open my $fh, "<", $geolite_location_file or die "Can not open file: $!\n";
  while(<$fh>){
    chomp;
    my @F = split /,/;
    next if ($F[0] !~ /^\d+$/);
    $location_tb{$F[0]} = $F[4];
  }
  close $fh;
}

sub isIPv4 {
  my $ip = shift;
  my @m = grep $_ <256, $ip =~ /^([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})$/;
  if (@m != 4) {
    return 0;
  }
  return 1;
}
