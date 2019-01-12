import os
import json

prefix = 'mods/mrinfo'

def generate_task_info(parent):
  # classes
  TaskGraph, Step, Task = parent.__get_class_from_schema__()
  # taskGraph object
  task_graph = TaskGraph(id=parent.task_id, steps=[])

  # mrinfo dependencies
  mrinfo_method = parent.conf["mrinfoMethod"]
  scheduling_strategy = parent.conf["schedulingStrategy"]["detail"]
  monitor_list = parent.conf["monitorList"]["detail"]

  # mrinfo step 1
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

  # mrinfo step 2
  s2 = Step(name="mrinfo", tasks=[])
  for monitor in monitor_list:
    timeout = mrinfo_method["timeout"]

    t = Task(monitorId=monitor)
    if scheduling_strategy == "split":
      t.inputs = [ "%s;%s" % ( os.path.join(monitor, parent.task_id+'.ip_list'), parent.task_id+'.ip_list' ) ]
    else:
      t.inputs = [ "%s;%s" % ( parent.task_id+'.ip_list', parent.task_id+'.ip_list' ) ]
    t.outputs = [ "%s;%s" % ( os.path.join(monitor, parent.task_id+'.mrinfo'), parent.task_id+'.mrinfo' ) ]
    t.command = "cat ${INPUTS[0]} | xargs -n 1 -P 1 -I {} bash -c 'echo \"mrinfo to {}\"; mrinfo -r0 -t %s' >${OUTPUTS[0]}\n" % (timeout)
    s2.tasks.append(t)

  task_graph.steps.append(s2)

  # mrinfo step 3
  s3 = Step(name="mrinfo2link", tasks=[])

  t = Task()
  t.inputs = [ os.path.join("*", parent.task_id+'.mrinfo') ]
  t.outputs = [ parent.task_id+'.links' ]
  t.command = '%s "${INPUTS[0]}" ${OUTPUTS[0]}' % (os.path.join(prefix, 'scripts/analyze'))
  s3.tasks.append(t)

  task_graph.steps.append(s3)

  # mrinfo step 4
  s4 = Step(name="import", tasks=[])

  t = Task()
  t.inputs = [ parent.task_id+'.links' ]
  t.outputs = []
  t.command = '%s ${INPUT[0]}' % (os.path.join(prefix, 'scripts/import'))
  s4.tasks.append(t)

  task_graph.steps.append(s4)

  # return task_graph object
  return json.loads(task_graph.serialize())
