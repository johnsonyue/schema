import os
import json

def generate_task_info(parent):
  # classes
  TaskGraph, Step, Task = parent.__get_class_from_schema__()
  # taskGraph object
  task_graph = TaskGraph(id=parent.task_id, steps=[])

  # parseconf dependencies
  conf_package_url = parent.conf['targetInput']['detail']

  # mplstrace step 1
  s1 = Step(name="parse conf", tasks=[])

  t = Task()
  t.inputs = [ conf_package_url+'#'+os.path.basename(conf_package_url) ]
  t.outputs = [ 'result/']
  # t.command = "cd /home/yupeng/; ./backend.sh 10.10.222.135 /home/yupeng/conf %s >&2" % (parent.task_id)
  t.command = "cd /home/yupeng/; ./backend.sh 10.10.222.135 ${INPUTS[0]} ${OUTPUTS[0]} %s >&2" % (parent.task_id)
  s1.tasks.append(t)

  task_graph.steps.append(s1)

  # return task_graph object
  return json.loads(task_graph.serialize())
