import os as _os; ROOT = _os.environ.get("KE_ROOT") or _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "../../../.."))
"""install.sh is_printing() (lines 235-245) on a Moonraker that is printing but answers in 5 s (a busy 32-bit Pi):
the timeout counts as "not printing", so install.sh / --undo / --uninstall restart Moonraker in the middle of the print."""
import json
import re
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Slow(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        time.sleep(5)
        body = json.dumps({"result": {"status": {"print_stats": {"state": "printing"}}}}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


srv = ThreadingHTTPServer(("127.0.0.1", 0), Slow)
threading.Thread(target=srv.serve_forever, daemon=True).start()
url = "http://127.0.0.1:%d" % srv.server_address[1]
src = open(ROOT + "/scripts/install.sh").read()
body = re.search(r"is_printing\(\) \{.*?<<'PY'\n(.*?)\nPY", src, re.S).group(1)
r = subprocess.run(["python3", "-", url + "/printer/objects/query?print_stats=state"], input=body, text=True)
print("Moonraker says: printing.  is_printing exit code:", r.returncode, "->", "printing" if r.returncode == 0 else "NOT printing (Moonraker gets restarted)")
