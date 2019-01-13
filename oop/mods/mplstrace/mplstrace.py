import os
import json

prefix = 'mods/mplstrace/scripts'

def generate_task_info(parent):
  # classes
  TaskGraph, Step, Task = parent.__get_class_from_schema__()
  # taskGraph object
  task_graph = TaskGraph(id=parent.task_id, steps=[])

  # mplstrace dependencies
  mplstrace_method = parent.conf["mplstraceMethod"]
  scheduling_strategy = parent.conf["schedulingStrategy"]["detail"]
  monitor_list = parent.conf["monitorList"]["detail"]

  # mplstrace step 1
  s1 = Step(name="target sampling", tasks=[])

  target_filepath = parent.conf['targetInput']['detail']
  if len(target_filepath.split('://')) > 1:
    target_filepath += '#%s' % (os.path.basename(target_filepath))

  t = Task()
  if scheduling_strategy == "split":
    t.inputs = [ target_filepath, os.path.realpath(parent.conf_filepath) ]
    t.outputs = [ parent.task_id+".ip_list", os.path.join("*", parent.task_id+".ip_list") ]
    t.command = "cat ${INPUTS[0]} | ./run.sh target -c ${INPUTS[1]} >${OUTPUTS[0]};\n"
    t.command += "./run.sh split -c ${INPUTS[1]} ${OUTPUTS[0]}"
  else:
    t.inputs = [ target_filepath, os.path.realpath(parent.conf_filepath) ]
    t.outputs = [ parent.task_id+".ip_list" ]
    t.command = "cat ${INPUTS[0]} | ./run.sh target -c ${INPUTS[1]} >${OUTPUTS[0]}"
  s1.tasks.append(t)

  task_graph.steps.append(s1)

  # mplstrace step 2
  s2 = Step(name="mplstrace", tasks=[])
  for monitor in monitor_list:
    method = mplstrace_method["method"]

    t = Task(monitorId=monitor)
    if scheduling_strategy == "split":
      t.inputs = [ "%s;%s" % ( os.path.join(monitor, parent.task_id+'.ip_list'), parent.task_id+'.ip_list' ) ]
    else:
      t.inputs = [ "%s;%s" % ( parent.task_id+'.ip_list', parent.task_id+'.ip_list' ) ]
    t.outputs = [ "%s;%s" % ( os.path.join(monitor, parent.task_id+'.warts'), parent.task_id+'.warts' ) ]
    t.command = "port=$(ps -ef | grep 'scamper -D' | grep -v 'grep' | awk '{for(i=1;i<=NF;i++){ if($i==\"-P\"){print $(i+1)} }}' | head -n 1);\n"
    t.command += "test -z \"$port\" && port=$(ss -tln | awk 'NR > 1{gsub(/.*:/,"",$4); print $4}' | sort -un | awk -v n=1080 '$0 < n {next}; $0 == n {n++; next}; {exit}; END {print n}') && scamper -D -P $port -p 150;\n"
    t.command += "sc_tnt -m %s -o ${OUTPUTS[0]} -a ${INPUTS[0]} -p $port" % (method)
    s2.tasks.append(t)

  task_graph.steps.append(s2)

  # mplstrace step 3
  s3 = Step(name="warts2link", tasks=[])

  t = Task()
  t.inputs = [ os.path.join("*", parent.task_id+'.warts') ]
  t.outputs = [ parent.task_id+'.links' ]
  t.command = 'cd %s; ./analyze "${INPUTS[0]}" ${OUTPUTS[0]}' % (prefix)
  s3.tasks.append(t)

  task_graph.steps.append(s3)

  # mplstrace step 4
  s4 = Step(name="import", tasks=[])

  t = Task()
  t.inputs = [ parent.task_id+'.links' ]
  t.outputs = []
  t.command = 'cd %s; ./import ${INPUTS[0]} %s >&2' % (prefix, parent.task_id)
  s4.tasks.append(t)

  task_graph.steps.append(s4)

  # return task_graph object
  return json.loads(task_graph.serialize())
