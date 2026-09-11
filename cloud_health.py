"""Small deployment health endpoint. Never exposes balances, keys, or controls."""
import json
import os
import threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer

def start_health(garden):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            if self.path not in ('/','/healthz'):
                self.send_error(404);return
            payload=json.dumps({'service':'Garden of Flies','status':garden.status,'round':garden.round}).encode()
            self.send_response(200 if garden.status!='stopped' else 503)
            self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
    server=ThreadingHTTPServer(('0.0.0.0',int(os.environ['PORT'])),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    return server
