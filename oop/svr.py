import SocketServer
import threading
import os
import json
import subprocess
import MySQLdb as mdb

config_root = 'conf'

secrets = json.load( open('secrets.json') )
backend = secrets['backend']
backend_username = backend['username']; backend_ip = backend['IP_addr']
backend_password = backend['password']; backend_database = backend['database']

err={
  0:"success",
  1:"invalid action",
  2:"server error",
  3:"wrong format"
}

class MyTCPServer(SocketServer.TCPServer):
  def __init__(self, (HOST, PORT), handler):
    SocketServer.TCPServer.__init__(self, (HOST, PORT), handler)
    self.task_stdout = {}
    self.thread_list = []

class MyTCPHandler(SocketServer.BaseRequestHandler):
  def task_thread(self, p, task_id):
    while True:
      line = p.stdout.readline()
      if not line:
        break
      self.server.task_stdout[task_id] = line
      # json.dump( json.loads(self.server.task_stdout[task_id]), open(os.path.join(config_root,task_id+'.log'), 'w') )

      lock = threading.Lock()
      lock.acquire()

      try:
        con = mdb.connect(backend_ip, backend_username, backend_password, backend_database)
        cur = con.cursor()
        escaped = json.dumps( json.loads(self.server.task_stdout[task_id]) )
        sql = "UPDATE celery_task_list SET task_info=%s WHERE task_id=%s"
        cur.execute(sql, (escaped, task_id ))
      except mdb.Error, e:
        print 'error', self.server.task_stdout[task_id]
        pass
      finally:
        if con:
          con.commit()
          con.close()

      lock.release()

  def reply(self, status, msg, data=''):
    ret = {}
    ret["status"] = status
    ret["msg"] = msg
    if data:
      ret["data"] = data
    self.request.sendall(json.dumps(ret))

  def handle(self):
    self.data = self.request.recv(1024).strip()
    
    ret={}
    try:
      obj=json.loads(self.data)
    except Exception, e:
      self.reply(3, err[3])
      return
      
    if not obj.has_key("action"):
      self.reply(1, err[1])
      return
    
    action = obj["action"]
    if action == "start_task":
      config_fileurl = obj['url']
      config_filename = os.path.basename( config_fileurl )
      task_id = os.path.splitext(config_filename)[0]
      config_filepath = os.path.join( config_root, config_filename )
      subprocess.Popen("curl -s -o %s %s" % (config_filepath, config_fileurl), shell = True).communicate()

      ## only starts the process
      try:
        p = subprocess.Popen("python run.py %s" % (config_filepath), shell=True, stdout=subprocess.PIPE)
      except:
        self.reply(2, err[2])
        return
      self.reply(0, err[0])

      ## keep reading stdout in a thread
      t = threading.Thread( target=self.task_thread, args=(p, task_id) )
      t.start()
      self.server.thread_list.append(t)
      return

    elif action == "query_state":
      task_id = obj['task_id']
      
      # logged
      log_filepath = os.path.join( config_root, task_id+".log" )
      if os.path.exists(log_filepath):
        self.reply( 0, err[0], json.load(open(log_filepath)) )
        return

      if not self.server.task_stdout.has_key(task_id):
        self.reply(2, err[2])
        return
      
      self.reply( 0, err[0], json.loads(self.server.task_stdout[task_id]) )

    else:
      self.reply(1, err[1])

if __name__ == "__main__":
  HOST, PORT = "10.10.222.135", 9998

  if not os.path.exists(config_root):
    os.makedirs(config_root)
  server = MyTCPServer((HOST, PORT), MyTCPHandler)

  server.serve_forever()
  [ t.join for t in server.thread_list ]
