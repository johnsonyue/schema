import python_jsonschema_objects as pjs
import os
import sys
import json

if len(sys.argv) < 1:
  sys.stderr.write("sch2obj <$conf_json> <$info_schema>\n")

confFileName = os.path.basename( sys.argv[1] )
conf = json.load( open(sys.argv[1]) )
schema = json.load( open(sys.argv[2]) )


# necessary shared infomation
taskType = conf['taskType']
task_id = sys.argv[1].rsplit('.', 1)[0]

# schema namespace
builder = pjs.ObjectBuilder( schema )
ns = builder.build_classes()
# classes in namespace
TaskGraph = ns.TaskGraph
Step = ns.Step; Task = ns.Task;

# taskGraph object
taskGraph = TaskGraph(id=task_id, steps=[])

# taskType is oneOf "traceroute", "pingscan", etc.
if taskType == "traceroute":
  targetSamplingMethod = conf["targetSamplingMethod"]["detail"]
  targetFile = conf["targetFile"]

  tracerouteMethod = conf["tracerouteMethod"]
  monitorList = conf["monitorList"]

  # traceroute step 1
  s1 = Step(name="target sampling", tasks=[])
  
  t = Task()
  t.inputs = [ os.path.join(task_id, task_id+".targets"), os.path.join(task_id, confFileName) ]
  t.outputs = [ os.path.join(task_id, task_id+".ip_list") ]
  t.command = "cat ${INPUTS[0]} | ./run.sh target -c ${INPUTS[1]} >${OUTPUTS[0]}"
  s1.tasks.append(t)
  
  taskGraph.steps.append(s1)

  # traceroute step 2
  s2 = Step(name="traceroute", tasks=[])
  for monitor in monitorList:
    monitor_dir = os.path.join(task_id, monitor)
    method = tracerouteMethod["method"]
    attemps = tracerouteMethod["attemps"]
    firstHop = tracerouteMethod["firstHop"]
    pps = tracerouteMethod["pps"]

    t = Task(monitorId=monitor)
    t.inputs = [ "%s;%s" % ( os.path.join(task_id, task_id+'.ip_list'), os.path.join(task_id, task_id+'.ip_list') ) ]
    t.outputs = [ "%s;%s" % ( os.path.join(monitor_dir, task_id+'.warts'), os.path.join(task_id, task_id+'.warts') ) ]
    t.command = "scamper -c 'trace -P %s' -p %d -O warts -o ${OUTPUTS[0]} -f ${INPUTS[0]}" % (method, pps)
    s2.tasks.append(t)
  
  taskGraph.steps.append(s2)

  # traceroute step 3
  s3 = Step(name="warts2iface", tasks=[])
  monitor_dirs = os.path.join(task_id, '*')

  t = Task()
  t.inputs = [ os.path.join(monitor_dirs, task_id+'.warts') ]
  t.outputs = [ os.path.join(task_id, task_id+'.ifaces'), os.path.join(task_id, task_id+'.links') ]
  t.command = "./analyze warts2iface ${INPUTS[0]} ${OUTPUTS[0]}"
  s3.tasks.append(t)
  
  taskGraph.steps.append(s3)

  # traceroute step 4
  s4 = Step(name="iffinder", tasks=[])
  for monitor in monitorList:
    monitor_dir = os.path.join(task_id, monitor)

    t = Task(monitorId=monitor)
    t.inputs = [ "%s;%s" % ( os.path.join(task_id, task_id+'.ifaces'), os.path.join(task_id, task_id+'.ifaces') ) ]
    t.outputs = [ "%s;%s" % ( os.path.join(monitor_dir, task_id+'.iffout'), os.path.join(task_id, task_id+'.iffout') ) ]
    t.command = "iffinder -c 100 -r %d -o $(echo ${OUTPUTS[0]} | sed 's/\.iffout//') ${INPUTS[0]}" % (pps)
    s4.tasks.append(t)
  
  taskGraph.steps.append(s4)

  # traceroute step 5
  s5 = Step(name="iffout2aliases", tasks=[])
  monitor_dirs = os.path.join(task_id, '*')

  t = Task()
  t.inputs = [ os.path.join(monitor_dirs, task_id+'.iffout') ]
  t.outputs = [ os.path.join(task_id, task_id+'.aliases') ]
  t.command = "cat ${INPUTS[0]} | grep -v '#' | awk '{ if(\$NF == \\\"D\\\") print \$1\\\" \\\"\$2}' | sort -u >${OUTPUTS[0]}"
  s5.tasks.append(t)
  
  taskGraph.steps.append(s5)

  # traceroute step 6
  s6 = Step(name="import", tasks=[])
  monitor_dirs = os.path.join(task_id, '*')

  t = Task()
  t.inputs = [ os.path.join(task_id, task_id+'.links'), os.path.join(task_id, task_id+'.ifaces') ]
  t.outputs = [ os.path.join(task_id, task_id+'.links.geo') ]
  t.command = "cat ${INPUTS[0]} | ./run.sh geo >${OUTPUTS[0]}; ./import.sh ${OUTPUTS[0]} ${INPUTS[1]} %s" % (task_id)
  s6.tasks.append(t)
  
  taskGraph.steps.append(s6)

print taskGraph.serialize(indent=2, sort_keys=True)
