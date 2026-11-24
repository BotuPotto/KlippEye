# Zone A proof 3: requests.get(url, timeout=4) on an MJPEG stream never returns (the timeout is per read, a stream never ends).
import threading, time, requests
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        self.send_response(200); self.send_header("Content-Type", "multipart/x-mixed-replace;boundary=f"); self.end_headers()
        try:
            while True:
                self.wfile.write(b"--f\r\nContent-Type: image/jpeg\r\n\r\n" + b"\xff" * 20000 + b"\r\n"); time.sleep(0.2)
        except Exception: pass
s = ThreadingHTTPServer(("127.0.0.1", 0), H); threading.Thread(target=s.serve_forever, daemon=True).start()
url = "http://127.0.0.1:%d/webcam/?action=stream" % s.server_address[1]
done = []
def get():
    t = time.time(); requests.get(url, timeout=4); done.append(time.time() - t)
th = threading.Thread(target=get, daemon=True); th.start(); th.join(30)
print("returned after %.1f s" % done[0] if done else "still waiting after 30 s with timeout=4 (the monitor loop would be stuck here)")
