#! /usr/bin/env python
import urllib2, os, json
import socket, cgi, logging
import SimpleHTTPServer as sise
import SocketServer
from pseudosecret import PS

PORT = 8080
rootpath = os.getcwd()
servepath = os.path.join(os.getcwd(), "to_serve")

def get_next_free_port(port):
    s = socket.socket()
    try:
        s.connect(('localhost', port))
        return get_next_free_port(port + 1)
    except socket.error:
        return port

class ReviewServer(sise.SimpleHTTPRequestHandler):
    def do_GET(self):
        # Is this a skill query?
        if self.path.startswith("/skill"):
            # Forward to LinkedIn
            newPath = "http://www.linkedin.com/ta/"+self.path
            print ('GET remote: ', newPath)
            try:
                self.copyfile(urllib2.urlopen(newPath), self.wfile)
            except IOError as e:
                print ("ERROR:   ", e)
        # Retrieve json statements from a non-public file
        elif self.path.startswith("/statements"):
            try:
                pseudo_id = self.path.split("?")[1].split("=")
                if PS[pseudo_id[0]] == pseudo_id[1]:
                    self.copyfile(open("../json/%s.json" % pseudo_id[0]),
                                  self.wfile)
            except KeyError as ke:
                print "KeyError:   ", ke
            except IOError as e:
                print "ERROR:   ", e
        else:
            # Serve files normally
            if "%" in self.path:
                self.path = urllib2.unquote(self.path).decode('utf8')
            sise.SimpleHTTPRequestHandler.do_GET(self)
        return

    def do_POST(self):
                logging.warning(self.headers)
                form = cgi.FieldStorage(
                    fp=self.rfile,
                    headers=self.headers,
                    environ={'REQUEST_METHOD':'POST',
                             'CONTENT_TYPE':self.headers['Content-Type'],
                             })
                print self.path
                json_resp = json.loads(form.value)
                with open("../json/%s.json" % self.path[1:], "wb") as ofile:
                    json.dump(json_resp, ofile, indent=4, sort_keys=True)
                
                # Think of a better response
                sise.SimpleHTTPRequestHandler.do_GET(self)

class ThreadedTCPServer(SocketServer.ThreadingMixIn, SocketServer.TCPServer):
    pass

def main():
    try:
        os.chdir(servepath)
        next_free_port = get_next_free_port(PORT)
        server = ThreadedTCPServer(('',next_free_port), ReviewServer)
        print ('server started at port ', next_free_port)
        server.serve_forever()
    except KeyboardInterrupt:
        server.socket.close()

if __name__=='__main__':
    main()
