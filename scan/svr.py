import SocketServer
import os
import json
import subprocess

err={
  -1:"format error",
  0:"success",
  1:"action not provided",
  2:"target not specified",
  3:"duration not specified",
  4:"invalid action",
  5:"server error"
}

class MyTCPHandler(SocketServer.BaseRequestHandler):
  def handle(self):
    # self.request is the TCP socket connected to the client
    self.data = self.request.recv(1024).strip()
    #print "{} wrote:".format(self.client_address[0])
    #print self.data
    
    ret={}
    try:
      obj=json.loads(self.data)
    except:
      return
      
    if not obj.has_key("action"):
      ret["status"]=1
      ret["msg"]=err[1]
      self.request.sendall(json.dumps(ret))
      return
    
    action = obj["action"]
    if action == "start":
      config_fileurl = obj['url']
      config_filepath = os.path.basename( config_fileurl )
      subprocess.Popen("curl -s -o %s %s" % (config_filepath, config_fileurl), shell = True).communicate()
      h = subprocess.Popen("python do.py %s" % (config_filepath), shell=True, stdout=subprocess.PIPE)
      ret["status"]=0
      ret["msg"]=err[0]
      l = h.stdout.readline().strip()
      ret["data"]=json.loads(l)
      self.request.sendall(json.dumps(ret))
      return

    else:
      ret["status"]=4
      ret["msg"]=err[4]
      self.request.sendall(json.dumps(ret))

if __name__ == "__main__":
  HOST, PORT = "10.10.222.135", 9998

  server = SocketServer.TCPServer((HOST, PORT), MyTCPHandler)

  server.serve_forever()
