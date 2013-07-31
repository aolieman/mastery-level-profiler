#! /usr/bin/env python
import urllib2, os, json
import socket, cgi, logging
import SimpleHTTPServer as sise
import SocketServer
from pseudosecret import PS

PORT = 8080
rootpath = os.getcwd()
servepath = os.path.join(os.getcwd(), "to_serve")
logging.basicConfig(filename='rserv.log',level=logging.INFO)

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
            logging.info(('GET remote: ', newPath))
            try:
                self.copyfile(urllib2.urlopen(newPath), self.wfile)
            except IOError as e:
                logging.error(("ERROR:   ", e))
        elif self.path.startswith("/review"):
            self.path = "/index.html"
            sise.SimpleHTTPRequestHandler.do_GET(self)
        # Retrieve json statements from a non-public file
        elif self.path.startswith("/statements"):
            try:
                pseudo_id = self.path.split("?")[1].split("=")
                if PS[pseudo_id[0]] == pseudo_id[1]:
                    self.copyfile(open("../json/%s.json" % pseudo_id[0]),
                                  self.wfile)
                else: self.send_error(401)
            except KeyError as ke:
                logging.error(("KeyError:   ", ke))
                self.send_error(401)
            except IOError as e:
                logging.error(("ERROR:   ", e))
                self.send_error(404)
        else:
            # Serve files normally
            if "%" in self.path:
                self.path = urllib2.unquote(self.path).decode('utf8')
            sise.SimpleHTTPRequestHandler.do_GET(self)
        return

    def do_POST(self):
        try:
            logging.info(self.headers)
            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={'REQUEST_METHOD':'POST',
                         'CONTENT_TYPE':self.headers['Content-Type'],
                         })
            logging.info(self.path)
            json_resp = json.loads(form.value)
            with open("../json/posted/%s.json" % self.path[1:], "wb") as ofile:
                json.dump(json_resp, ofile, indent=4, sort_keys=True)
            # Send success response
            self.send_response(200)
            self.send_header("Content-type:", "text/plain")
            self.wfile.write("\n")
            json.dump({"success": "post saved"}, self.wfile)
        except Exception as e:
            # Send failed response
            logging.error(("Failed POST:", e))
            self.send_error(500)

    def log_message(self, format, *args):
        """Log an arbitrary message.
        """
        logging.info("%s - - [%s] %s\n" %
                         (self.address_string(),
                          self.log_date_time_string(),
                          format%args))

class ThreadedTCPServer(SocketServer.ThreadingMixIn, SocketServer.TCPServer):
    pass

def main():
    try:
        os.chdir(servepath)
        next_free_port = get_next_free_port(PORT)
        server = ThreadedTCPServer(('',next_free_port), ReviewServer)
        logging.info(('server started at port ', next_free_port))
        print ('server started at port ', next_free_port)
        server.serve_forever()
    except KeyboardInterrupt:
        server.socket.close()
        logging.shutdown()

if __name__=='__main__':
    main()
