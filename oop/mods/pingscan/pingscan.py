import os
import json

prefix = 'mods/pingscan/scripts'
def generate_task_info(parent):
  # classes
  TaskGraph, Step, Task = parent.__get_class_from_schema__()
  # taskGraph object
  task_graph = TaskGraph(id=parent.task_id, steps=[])

  # pingscan dependencies
  ping_method = parent.conf["pingMethod"]
  monitor_list = parent.conf["monitorList"]["detail"]

  # pingscan step 1
  s1 = Step(name="cp target", tasks=[])

  target_filepath = parent.conf['targetInput']['detail']
  if len(target_filepath.split('://')) > 1:
    target_filepath += '#%s' % (os.path.basename(target_filepath))

  t = Task()
  t.inputs = [ target_filepath ]
  t.outputs = [ parent.task_id+".ip_list" ]
  t.command = "cp ${INPUTS[0]} ${OUTPUTS[0]}"
  s1.tasks.append(t)

  task_graph.steps.append(s1)

  # pingscan step 2
  s2 = Step(name="ping", tasks=[])

  for monitor in monitor_list:
    method = ping_method["method"]
    opt = {
      "tcp-ack": "-PA",
      "tcp-syn": "-PS443",
      "udp": "-PU",
      "sctp-init": "-PY",
      "ip": "-PO2,4",
      "icmp-echo": "-PE",
      "icmp-ts": "-PP",
      "icmp-addr-mask": "-PM"
    }
    opt_str = ' '.join( map( lambda m: opt[m], method ) )

    t = Task(monitorId=monitor)
    t.inputs = [ "%s;%s" % ( parent.task_id+'.ip_list', parent.task_id+'.ip_list' ) ]
    t.outputs = [ "%s;%s" % ( os.path.join(monitor, parent.task_id+'.xml'), parent.task_id+'.xml' ) ]
    t.command = "nmap -sn %s -n -iL ${INPUTS[0]} -oX ${OUTPUTS[0]}" % (opt_str)
    s2.tasks.append(t)

  task_graph.steps.append(s2)

  # pingscan step 3
  s3 = Step(name="xml2nodes", tasks=[])

  t = Task()
  t.inputs = [ os.path.join("*", parent.task_id+'.xml') ]
  t.outputs = [ parent.task_id+'.nodes' ]
  t.command = 'cd %s; ./analyze "${INPUTS[0]}" ${OUTPUTS[0]}' % (prefix)
  s3.tasks.append(t)

  task_graph.steps.append(s3)

  # pingscan step 4
  s4 = Step(name="import", tasks=[])

  t = Task()
  t.inputs = [ parent.task_id+'.nodes' ]
  t.outputs = []
  t.command = 'cd %s; ./import ${INPUTS[0]} %s >&2' % (prefix, parent.task_id)
  s4.tasks.append(t)

  task_graph.steps.append(s4)

  return json.loads(task_graph.serialize())
