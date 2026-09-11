"""Allowlisted spectator website and health endpoint; no wallet controls."""
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
from cloud_observatory import Observatory, ROOT

ASSETS = {'/fly-logo.png': ('fly-logo.png', 'image/png'), '/': ('index.html', 'text/html; charset=utf-8'),
          '/index.html': ('index.html', 'text/html; charset=utf-8'),
          '/observatory.css': ('observatory.css', 'text/css; charset=utf-8'),
          '/observatory.js': ('observatory.js', 'text/javascript; charset=utf-8')}

def start_health(garden, observatory=None):
    observer = observatory if observatory is not None else Observatory()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def respond(self, payload, content_type, status=200):
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(payload)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(payload)
        def json(self, value, status=200):
            self.respond(json.dumps(value).encode(), 'application/json', status)
        def do_GET(self):
            path = urlsplit(self.path).path
            if path == '/healthz':
                self.json({'service': 'Garden of Flies', 'status': garden.status, 'round': garden.round},
                          200 if garden.status != 'stopped' else 503)
            elif path in ASSETS:
                name, content_type = ASSETS[path]
                self.respond((ROOT / 'web' / name).read_bytes(), content_type)
            elif path == '/api/status':
                try:
                    self.json(observer.status())
                except Exception:
                    self.json({'error': 'Live data is temporarily unavailable. No estimated balances are substituted.'}, 503)
            else:
                self.json({'error': 'Not found'}, 404)
        def do_POST(self):
            self.json({'error': 'Read-only website'}, 405)
        do_PUT = do_DELETE = do_PATCH = do_POST
    server = ThreadingHTTPServer(('0.0.0.0', int(os.environ['PORT'])), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
