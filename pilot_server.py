"""Local control panel for the neural paper pilot. Never exposes secret files."""
import copy
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import secrets
import threading
import time
from urllib.parse import urlsplit
from pilot_runtime import Pilot, STATE

ROOT=Path(__file__).parent

class Controller:
    def __init__(self,pilot):
        self.pilot=pilot
        self.latest=copy.deepcopy(pilot.state)
        self.running=False
        self.busy=False
        self.error=None
        self.lock=threading.Lock()
        self.control_token=secrets.token_urlsafe(32)

    def status(self):
        preflight_path=STATE/'preflight.json'
        checks=json.loads(preflight_path.read_text()) if preflight_path.exists() else {'ready_to_fund':False,'blockers':['Preflight has not run']}
        return {'runtime':'local_neural_paper','running':self.running,'busy':self.busy,'error':self.error,
                'control_token':self.control_token,'state':self.latest,'preflight':checks}

    def start(self,once=False):
        with self.lock:
            if self.busy or self.error:return False
            self.busy=True;self.running=not once;self.error=None
        def loop():
            try:
                while True:
                    result=self.pilot.tick()
                    self.latest=copy.deepcopy(result)
                    if not self.running:break
                    time.sleep(1)
            except Exception:
                # Recovery reloads the last atomic checkpoint, never a partial tick.
                self.error='Pilot stopped after a runtime error. Restart from the last saved checkpoint.'
                self.running=False
            finally:
                with self.lock:self.busy=False
        threading.Thread(target=loop,daemon=True).start()
        return True

def serve(port=8767):
    from pilot_paper_market import PaperMarket
    controller=Controller(Pilot(market=PaperMarket()))
    expected=f'127.0.0.1:{port}'
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass

        def reply(self,code,body,mime='application/json'):
            payload=body if isinstance(body,bytes) else json.dumps(body).encode()
            self.send_response(code);self.send_header('Content-Type',mime)
            self.send_header('Content-Length',str(len(payload)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'")
            self.end_headers();self.wfile.write(payload)

        def do_GET(self):
            if self.headers.get('Host')!=expected:return self.reply(403,{'error':'Host rejected'})
            path=urlsplit(self.path).path
            if path=='/api/pilot':return self.reply(200,controller.status())
            files={'/':('pilot.html','text/html; charset=utf-8'),'/pilot.html':('pilot.html','text/html; charset=utf-8'),
                   '/pilot.js':('pilot.js','text/javascript'),'/pilot.css':('pilot.css','text/css')}
            if path not in files:return self.reply(404,{'error':'Not found'})
            name,mime=files[path]
            self.reply(200,(ROOT/'dist'/name).read_bytes(),mime)

        def do_POST(self):
            if self.headers.get('Host')!=expected or self.headers.get('Origin')!=f'http://{expected}' or self.headers.get('X-Garden-Control')!=controller.control_token:
                return self.reply(403,{'error':'Local same-origin control required'})
            if self.headers.get('Content-Length','0')!='0':return self.reply(400,{'error':'No body expected'})
            path=urlsplit(self.path).path
            if path=='/api/start':ok=controller.start()
            elif path=='/api/step':ok=controller.start(once=True)
            elif path=='/api/pause':controller.running=False;ok=True
            else:return self.reply(404,{'error':'Unknown action'})
            self.reply(200 if ok else 409,{'ok':ok})
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    print(f'Neural paper pilot: http://{expected}',flush=True)
    try:server.serve_forever()
    finally:controller.running=False;server.server_close()

if __name__=='__main__':serve()
