#!/usr/bin/perl
#
# linkmerge -- merge a batch of link files
# =============================================================================
# USAGE: linkmerge file1 file2 ... 
# INPUT: a batch of link (text or gzip) file names from STDIN or @ARGV
#        
# INPUT/OUTPUT format: CSV text
#         1.in 2.out 3.is_dest 4.star 5.delay 6.freq 7.ttl 8.monitor
#         1. the IP address of the ingress interface, e.g., 1.2.3.4
#         2. the IP address of the outgress interface, e.g., 5.6.7.8
#         3. whether the outgress node is the destination, e.g., Y or N
#         4. the number of anonymous (*) hops inbetween, e.g., 0 for directed link
#         5. the minimal delay in ms > 0, e.g., 10
#         6. the cumulative frequence of link observed, e.g., 5000
#         7. the minimal TTL of the ingress interface, e.g., 7
#         8. the monoitor which observed the link at the minimal TTL, e.g., 9.0.1.2 
#
# AUTHORS:
# - yuzhang at hit.edu.cn 2017.8.29
#
# CHANGE LOG:
# - 2017.8.29 - Alpha
# - 2017.9.5  - read multiple lines at one time from a file
#               replace all hashtables with arrays
#
# Examples of input
#
#
# Examples of output
#

use strict;
use warnings;

my $NLINE = 1000;
my @FH = (); # file handle array
my @CL; # current line array
my @NL; # number of lines left in CL 

sub openfile($);  # just open, remember to close later 
sub readfile($);  # read $NLINE lines from file No. $f, and push to @CL

# open files and add handle to @FH;
my @files = @ARGV; 
@files = <STDIN> unless (@files);
my %h = map { $_ , 1 } @files;
@files = keys %h; # remove duplicate file 
foreach (@files) { chomp; my $fh = &openfile($_); push @FH, $fh; }

# merge all files: 
#   1. read $NLINE lines from each file, put lines into @CL and sort @CL
#   2. while @CL is not empty
#   3.   get top 2 lines, and shift @CL 
#   4.   if 2 lines are different links
#   5.      output top 1 line
#   6.   else 
#   7.      merge 2 lines into $CL[0]
#   8.   if no more line from top 1 line's file left in @CL 
#   9       read $NLINE lines from top 1 line's file, insert into @CL and sort @CL 

# read lines from each file, and push into @CL
foreach (0 .. $#FH) { &readfile($_); }
@CL = sort @CL;

while (scalar(@CL)) {

  # get top two lines from $CL
  my $al = $CL[0];
  my @a = split / /, $al;
  my $af = $a[-1];
  $NL[$af]--;
  shift @CL;

  # only one file left, just print the rest of the file
  if (scalar(@CL) == 0) { 
    $al =~ s/ \d+$//;
    print "$al\n";
    my $fh = $FH[$af];
    while(<$fh>) {print "$_";}
    last;
  }

  my $bl = $CL[0];
  my @b = split / /, $bl;
  my $bf = $b[-1];
 
  # 0.in 1.out 2.is_dest 3.star 4.delay 5.freq 6.ttl 7.monitor

  if ("$a[0] $a[1]" ne "$b[0] $b[1]") {  # top 2 links are different
    $al =~ s/ \d+$//;
    print "$al\n";
  } else {                               # the same link, merge two lines
    $b[2] = "N" if $a[2] eq "N";
    $b[3] = $a[3] if $b[3] > $a[3]; 
    $b[4] = $a[4] if $b[4] > $a[4]; 
    $b[5] += $a[5]; 
    @b[6,7] = @a[6,7] if ($b[6] > $a[6] or ($b[6] == $a[6] and $a[7] lt $b[7])); 
    $CL[0] = join(" ", @b);
  }
 
  @CL = sort @CL if ($NL[$af] == 0 and &readfile($af)); # read more from $af and sort
}

foreach (@FH) {close $_;}
exit 0;

#==== sub routine

sub openfile($) {         # just open, remember to close later 
  my $openstr = shift;
  if ($openstr =~ /\.g?z$/) {          # .gz or .z
     $openstr = "gzip -dc $openstr";
  } else {                             # expect it is uncompressed 
     $openstr = "cat $openstr";
  } 
  my $fh;
  open($fh, '-|', $openstr) or die "Can not open file $openstr: $!";
  return $fh;
}

sub readfile($) {  # reand $NLINE lines from file No. $f
  my $f = shift;
  my $fh = $FH[$f];
  my $i = 0;
  while ($i < $NLINE and $_ = <$fh>) {
    chomp;
    push @CL, "$_ $f";
    $i++;
  }
  $NL[$f] = $i; 
  return $i;
}

# END MARK
