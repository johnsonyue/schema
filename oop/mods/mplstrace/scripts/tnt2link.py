#!/usr/bin/env python

# ====================================================================================================================
# tnt2link.py -- extract IP-level links containing the MPLS tunnels's information from TNT's text files
# INPUT:  text from the command --  tnt -d1 *.warts 
# OUTPUT: 
#         line-foramat: 1.in 2.out 3.is_dest 4.star 5.delay 6.freq 7.ttl 8.monitor 9.in_mpls 10.out_mpls 11.in_role 12.out_role 13.in_labels 14.out_labels
#         1. the IP address of the ingress interface, e.g., 1.2.3.4
#         2. the IP address of the outgress interface, e.g., 5.6.7.8
#         3. whether the outgress node is the destination and is not observed in the middle of the path, e.g., Y or N
#         4. the number of anonymous (*) hops inbetween, e.g., 0 for directed link
#         5. the minimal delay in ms > 0, e.g., 10
#         6. the cumulative frequence of link observed, e.g., 5000
#         7. the minimal TTL of the ingress interface, e.g., 7, H1(exist in inv MPLS)
#         8. the monoitor which observed the link at the minimal TTL, e.g., 9.0.1.2
#         9. the MPLS type of ingress node, default as *, e.g., EXP
#        10. the MPLS type of outgress node, default as *, e.g., EXP
#        11. the role in LSP of ingress node, default as *, e.g., LSR
#        12. the role in LSP of outgress node, default as *, e.g., LSR
#        13. the MPLS labels of ingress node, default as *, e.g., 35634T1|24238T2  
#        14. the MPLS labels of outgress node, default as *, e.g., 0T1|24238T3
#
#
# DATE: 2018/12/16
# AUTHOR: kimii
# ====================================================================================================================
def min_ttl(t1, t2):
    if t1 == t2:
        return t1
    if 'H' in t1 and 'H' in t2:
        mt = 'H' + str(min(int(t1[1:]), int(t2[1:])))
    elif 'H' in t1 or 'H' in t2:
        mt = t1 if 'H' in t1 else t2
    else:
        mt = min(int(t1), int(t2))
    return str(mt)

def merge_labels(l1, l2):
    if l1 == l2:
        return l1
    if l1 == '*':
        return l2
    if l2 == '*':
        return l1
    l_dict = {}
    for subl in l1.split('|'):
        subl_split = subl.split('T')
        if subl_split[0] not in l_dict:
            l_dict[subl_split[0]] = subl_split[1]
        else:
            l_dict[subl_split[0]] = str(min(int(subl_split[1]), int(l_dict[subl_split[0]])))
    for subl in l2.split('|'):
        subl_split = subl.split('T')
        if subl_split[0] not in l_dict:
            l_dict[subl_split[0]] = subl_split[1]
        else:
            l_dict[subl_split[0]] = str(min(int(subl_split[1]), int(l_dict[subl_split[0]])))
    ml = '|'.join([k+'T'+v for k,v in l_dict.items()])
    return ml
           
def tnt2link():
    TUN_TYPE = ["*", "INF", "EXP", "IMP", "OPA", "INV"]
    NODE_TYPE = ["*", "LSR", "ING", "EGR"]
    link_dict = {}
    star_num = 0
    while True:
      try:
        line = raw_input().strip().split()
      except:
        break
      if not line:
          continue
      if 'trace' == line[0]:
          monitor = line[-3]
          dst = line[-1]
          nodes = set()
          ing = []
          outg = []
          is_loop = 0
      else:
          if not ing:
              if line[1] == '*':
                  continue
              is_loop = 1 if line[1] in nodes else 0
              nodes.add(line[1])
              ing = line
          elif not outg:
              if line[1] == '*':
                  star_num += 1
                  continue
              is_loop = 1 if line[1] in nodes else 0
              nodes.add(line[1])
              outg = line
              # node -> link
              link_key = (ing[1], outg[1])
              # 0.is_dest 1.star 2.delay 3.freq 4.ttl 5.monitor 
              # 6.in_mpls 7.out_mpls 8.in_role 9.out_role 10.in_labels 11.out_labels
              link_value = []
              is_dest = 'Y' if outg[1] == dst else 'N'
              delay = float(float(outg[2]) - float(ing[2])) / 2.0
              delay = delay if delay > 0 else 0
              # 0.in_mpls 1.out_mpls 2.in_role 3.out_role 4.in_labels 5.out_labels
              mpls_info = ['*'] * 6
              # mpls_info for in
              for i in range(4, len(ing)):
                  elmt = ing[i]
                  if "MPLS" in elmt:
                      elmt_list = elmt[1:-1].split(',')
                      for sube in elmt_list:
                          # tunnel type
                          if sube in TUN_TYPE:
                              mpls_info[0] = sube
                          # node type
                          elif sube in NODE_TYPE:
                              mpls_info[2] = sube         
                  elif elmt == "Labels":
                      mpls_info[4] = ''.join(ing[i+1:]).replace('mTTL=', 'T')
                      break
              # mpls_info for out
              for i in range(4, len(outg)):
                  elmt = outg[i]
                  if "MPLS" in elmt:
                      elmt_list = elmt[1:-1].split(',')
                      for sube in elmt_list:
                          # tunnel type
                          if sube in TUN_TYPE:
                              mpls_info[1] = sube
                          elif sube in NODE_TYPE:
                              mpls_info[3] = sube         
                  elif elmt == "Labels":
                      mpls_info[5] = ''.join(outg[i+1:]).replace('mTTL=', 'T')
                      break
              
              link_value = [is_dest, star_num, delay, 1, ing[0], monitor]
              link_value.extend(mpls_info)
              
              if not is_loop:
                  if link_key not in link_dict:
                      link_dict[link_key] = link_value
                  else:
                      l = link_value
                      t = link_dict[link_key]
                      # 0.is_dest 1.star 2.delay 3.freq 4.ttl 5.monitor 
                      # 6.in_mpls 7.out_mpls 8.in_role 9.out_role 10.in_labels 11.out_labels
                      t[0] = 'N' if l[0] == 'N' else t[0]
                      t[1] = l[1] if t[1] > l[1] else t[1]
                      t[2] = l[2] if t[2] > l[2] else t[2]
                      t[3] += 1
                      t[4] = min_ttl(t[4], l[4])
                      t[5] = l[5] if t[4] == l[4] else t[5]
                      t[6] = t[6] if t[6] == l[6] else TUN_TYPE[max(TUN_TYPE.index(t[6]), TUN_TYPE.index(l[6]))]
                      t[7] = t[7] if t[7] == l[7] else TUN_TYPE[max(TUN_TYPE.index(t[7]), TUN_TYPE.index(l[7]))]
                      t[8] = t[8] if t[8] == l[8] else NODE_TYPE[max(NODE_TYPE.index(t[8]), NODE_TYPE.index(l[8]))]
                      t[9] = NODE_TYPE[max(NODE_TYPE.index(t[9]), NODE_TYPE.index(l[9]))]
                      t[10] = merge_labels(t[10], l[10])
                      t[11] = merge_labels(t[11], l[11])
                      link_dict[link_key] = t
              star_num = 0
              ing = outg
              outg = []
    # dump link
    for k,v in link_dict.items():
        tmp_link = []
        tmp_link.extend(list(k))
        tmp_link.extend(v)
        print (' '.join([str(i) for i in tmp_link]))
            

if __name__ == "__main__":
    import sys
    tnt2link()
