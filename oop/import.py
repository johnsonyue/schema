from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler
from SocketServer import ThreadingMixIn
from contextlib import closing
import urlparse
import socket
import json
import sys
import os

def find_free_port():
  with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
    s.bind(('', 0))
    return s.getsockname()[1]

class Handler(BaseHTTPRequestHandler):
  def do_GET(self):
    self.send_response(200)
    self.end_headers()
    parsed = urlparse.urlparse( self.path )
    filepath = os.path.join( self.server.task_root, parsed.path.lstrip('/') )

    self.wfile.write( open(filepath).read() )
    self.server.shutdown()

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
  def __init__(self, (HOST,PORT), handler, task_root):
    HTTPServer.__init__(self, (HOST, PORT), handler)
    self.task_root = task_root

def usage():
  sys.stderr.write('import <$task_id> <$links_filepath>\n')

host_ip = "10.10.222.135"
free_port = find_free_port()
server_ip = "10.10.11.140"
server_port = 4000

if __name__ == "__main__":
  if len(sys.argv) < 3:
    usage()
    exit()

  task_id = sys.argv[1]
  links_filepath = sys.argv[2]
  af = 4 if len(sys.argv) < 4 else sys.argv[3]

  task_id = task_id.replace('-', '_')
  task_root = os.path.dirname( links_filepath )
  links_filename = os.path.basename( links_filepath )

  # parent process serves packages
  pid = os.fork()
  if pid:
    server = ThreadedHTTPServer((host_ip, free_port), Handler, task_root)
    server.serve_forever()
    os.waitpid(pid, 0) # important! wait for step to finish

  # child process send remote tasks
  else:
    # Create a TCP/IP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    # Connect the socket to the port where the server is listening
    server_address = (server_ip, server_port)
    sock.connect(server_address)

    # Prepare msg
    msg = {}
    if af == '6':
      msg['action'] = 'ipv6_links'
    else:
      msg['action'] = 'links'
    msg['task_id'] = task_id
    msg['url'] = 'http://%s:%s/%s' % (host_ip, free_port, links_filename)

    # Send data
    try:
      sock.sendall(json.dumps(msg))

      # Wait for response
      res = sock.recv(1024)
    except:
      sys.stderr.write( 'failed to import\n' )
      sock.close()
    finally:
      sys.stderr.write( res + '\n' )
      sock.close()
