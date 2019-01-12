import os
import json

prefix = 'mods/pchar'

def generate_task_info(parent):
  # classes
  TaskGraph, Step, Task = parent.__get_class_from_schema__()
  # taskGraph object
  task_graph = TaskGraph(id=parent.task_id, steps=[])

  # pchar dependencies
  pchar_method = parent.conf["pcharMethod"]
  scheduling_strategy = parent.conf["schedulingStrategy"]["detail"]
  monitor_list = parent.conf["monitorList"]["detail"]

  # pchar step 1
  s1 = Step(name="cp target", tasks=[])

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

  # pchar step 2
  s2 = Step(name="pchar", tasks=[])
  for monitor in monitor_list:
    method = pchar_method["method"]

    t = Task(monitorId=monitor)
    if scheduling_strategy == "split":
      t.inputs = [ "%s;%s" % ( os.path.join(monitor, parent.task_id+'.ip_list'), parent.task_id+'.ip_list' ) ]
    else:
      t.inputs = [ "%s;%s" % ( parent.task_id+'.ip_list', parent.task_id+'.ip_list' ) ]
    t.outputs = [ "%s;%s" % ( os.path.join(monitor, parent.task_id+'.pchar'), parent.task_id+'.pchar' ) ]
    t.command = "cat ${INPUTS[0]} | xargs -n 1 -P 1 -I {} bash -c 'pchar -n -I 400 -R 3 -t 2 -p %s {}' >${OUTPUTS[0]}\n" % (method)
    s2.tasks.append(t)

  task_graph.steps.append(s2)

  # pchar step 3
  s3 = Step(name="pchar2link", tasks=[])

  t = Task()
  t.inputs = [ os.path.join("*", parent.task_id+'.pchar') ]
  t.outputs = [ parent.task_id+'.links' ]
  t.command = '%s "${INPUTS[0]}" ${OUTPUTS[0]}' % (os.path.join(prefix, 'scripts/analyze'))
  s3.tasks.append(t)

  task_graph.steps.append(s3)

  # pchar step 4
  s4 = Step(name="import", tasks=[])

  t = Task()
  t.inputs = [ parent.task_id+'.links' ]
  t.outputs = []
  t.command = '%s ${INPUT[0]}' % (os.path.join(prefix, 'scripts/import'))
  s4.tasks.append(t)

  task_graph.steps.append(s4)

  # return task_graph object
  return json.loads(task_graph.serialize())
