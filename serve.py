"""Local server for the dashboard.

Serves output/ at http://localhost:8642 (the root shows the dashboard) and
handles POST /refresh by running the fast update pipeline: new results are
applied to cached ratings and the tournament re-simulates; the full
historical model is not rebuilt.

Run: python3 serve.py   then open http://localhost:8642
"""

import http.server
import json
import os
import subprocess
import sys
import threading
import time
import webbrowser

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "output")
PORT = 8642
REFRESH_LOCK = threading.Lock()


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=OUT, **kwargs)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self.path = "/dashboard.html"
        return super().do_GET()

    def _send_json(self, code, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/refresh":
            self._send_json(404, {"ok": False, "error": "unknown endpoint"})
            return
        if not REFRESH_LOCK.acquire(blocking=False):
            self._send_json(409, {"ok": False,
                                  "error": "a refresh is already running"})
            return
        try:
            started = time.time()
            r = subprocess.run(
                [sys.executable, os.path.join(BASE, "update.py")],
                capture_output=True, text=True, timeout=600, cwd=BASE)
            seconds = round(time.time() - started, 1)
            out = (r.stdout or "") + (r.stderr or "")
            summary = next(
                (ln.strip() for ln in out.splitlines()
                 if ln.strip().startswith("incremental:")), "refreshed")
            if r.returncode != 0:
                self._send_json(500, {"ok": False, "seconds": seconds,
                                      "error": out[-600:]})
                return
            self._send_json(200, {"ok": True, "seconds": seconds,
                                  "summary": f"{summary} ({seconds}s)"})
        except subprocess.TimeoutExpired:
            self._send_json(500, {"ok": False, "error": "update timed out"})
        finally:
            REFRESH_LOCK.release()

    def log_message(self, fmt, *args):
        # Keep the terminal quiet apart from refreshes.
        if "refresh" in (args[0] if args else ""):
            super().log_message(fmt, *args)


def main():
    url = f"http://localhost:{PORT}"
    try:
        server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError:
        # Already running (e.g. the launcher was double-clicked twice):
        # just bring the existing dashboard up.
        print(f"Dashboard already running at {url}")
        if not os.environ.get("WC_NO_BROWSER"):
            webbrowser.open(url)
        return
    print(f"Dashboard: {url}  (Ctrl+C to stop)")
    no_browser = "--no-browser" in sys.argv or os.environ.get("WC_NO_BROWSER")
    if not no_browser:
        threading.Timer(0.8, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
