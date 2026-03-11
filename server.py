import os
import sys
import json
import mimetypes
import datetime
import traceback
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from urllib.parse import urlparse, parse_qs

from pipeline import run_pipeline, OBSERVATORY_REGISTRY

# reads PORT from environment (Render sets this automatically; defaults to 8001 locally)
PORT = int(os.environ.get("PORT", 8001))

# directory where this script lives — used to serve static files
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# threading server (for long computations)
class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    """Each request runs in its own thread so long /compute calls
    never block /observatories or index.html fetches."""
    daemon_threads = True


#logging helpers
def _now() -> str:
    """Timezone-aware UTC timestamp (replaces deprecated datetime.utcnow)."""
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

def _log(label: str, value: str):
    print(f"{label:<22}: {value}", flush=True)

def _sep(char="─", n=58):
    print(char * n, flush=True)

class RequestHandler(BaseHTTPRequestHandler):

    #CORS pre-flight 
    def do_OPTIONS(self):
        self._send_cors(200)
        self.end_headers()

    # Render health-checker and some browsers send HEAD — without this Python returns 501.
    def do_HEAD(self):
        self._send_cors(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()

    #main GET handler 
    def do_GET(self):
        parsed = urlparse(self.path)
        path   = parsed.path

        #1-observatory registry (used by frontend dropdowns)
        if path == "/observatories":
            self._json(OBSERVATORY_REGISTRY)
            return

        #2- compute endpoint
        if path == "/compute":
            self._handle_compute(parse_qs(parsed.query))
            return

        #3 serve static files (index.html, any .png/.css/.js placed alongside)
        self._serve_static(path)

    #/compute
    def _handle_compute(self, params):
        ra          = params.get("ra",          [None])[0]
        dec         = params.get("dec",         [None])[0]
        start_date  = params.get("date",        [None])[0]
        end_date    = params.get("end_date",    [None])[0]
        airmass_str = params.get("airmass",     ["2.5"])[0]
        optical_key = params.get("optical_obs", ["GTC"])[0]
        radio_key   = params.get("radio_obs",   ["GBO"])[0]

        if not ra or not dec:
            self._json({"error": "Missing RA or Dec"}, status=400)
            return

        try:
            airmass_limit = float(airmass_str)
        except ValueError:
            airmass_limit = 2.5

        #request header log
        tid = threading.current_thread().name
        print(f"[{datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC] [{tid}] NEW COMPUTE REQUEST", flush=True)
        print(f"[{tid}] RA : {ra}", flush=True)
        print(f"[{tid}] Dec : {dec}", flush=True)
        print(f"[{tid}] Date range : {start_date} → {end_date}", flush=True)
        print(f"[{tid}] Airmass : {airmass_limit}", flush=True)
        print(f"[{tid}] Optical : {optical_key}", flush=True)
        print(f"[{tid}] Radio : {radio_key}", flush=True)

        try:
            t0 = datetime.datetime.now(datetime.timezone.utc)
            result = run_pipeline(
                ra, dec,
                start_date   = start_date,
                end_date     = end_date,
                airmass_limit= airmass_limit,
                optical_key  = optical_key,
                radio_key    = radio_key,
            )
            elapsed = (datetime.datetime.now(datetime.timezone.utc) - t0).total_seconds()
            nights  = len(result.get("next_7_days", []))
            hits    = sum(1 for d in result.get("next_7_days", []) if d.get("windows"))
            print(f"[{tid}] DONE: {nights} nights in {elapsed:.1f}s — {hits} nights with joint window", flush=True)
            self._json(result)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self._json({"error": str(e)}, status=500)

    #static file server
    def _serve_static(self, path):
        # default to index.html for root and unknown paths
        if path in ("/", ""):
            path = "/index.html"

        file_path = os.path.join(BASE_DIR, path.lstrip("/"))

        #safety: don't allow directory traversal
        if not os.path.realpath(file_path).startswith(os.path.realpath(BASE_DIR)):
            self._send_cors(403); self.end_headers(); return

        if not os.path.isfile(file_path):
            self._send_cors(404)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Not found")
            return

        mime, _ = mimetypes.guess_type(file_path)
        mime = mime or "application/octet-stream"
        self._send_cors(200)
        self.send_header("Content-Type", mime)
        self.end_headers()
        with open(file_path, "rb") as f:
            self.wfile.write(f.read())

    # helpers
    def _send_cors(self, status):
        self.send_response(status)
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json(self, data, status=200):
        payload = json.dumps(data).encode()
        self._send_cors(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    #all requests appear in Render logs
    def log_message(self, fmt, *args):
        sys.stderr.write("%s - - [%s] %s\n" % (
            self.address_string(),
            self.log_date_time_string(),
            fmt % args
        ))


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", PORT), RequestHandler)
    server.socket.settimeout(None)
    # server = HTTPServer(("0.0.0.0", PORT), RequestHandler)
    print(f"Server started — http://0.0.0.0:{PORT}", flush=True)
    server.serve_forever()