import os
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

from pipeline import run_pipeline, OBSERVATORY_REGISTRY

# reads PORT from environment (Render sets this automatically; defaults to 8001 locally)
PORT = int(os.environ.get("PORT", 8001))

# directory where this script lives — used to serve static files
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class RequestHandler(BaseHTTPRequestHandler):

    #CORS pre-flight 
    def do_OPTIONS(self):
        self._send_cors(200)
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
            self._send_cors(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Missing RA or Dec"}).encode())
            return

        try:
            airmass_limit = float(airmass_str)
        except ValueError:
            airmass_limit = 2.5

        try:
            result = run_pipeline(
                ra, dec,
                start_date   = start_date,
                end_date     = end_date,
                airmass_limit= airmass_limit,
                optical_key  = optical_key,
                radio_key    = radio_key,
            )
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

    # suppress default request logs— comment out to re-enable
    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), RequestHandler)
    print(f"Server running at http://localhost:{PORT}")
    server.serve_forever()