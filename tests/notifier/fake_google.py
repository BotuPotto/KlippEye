"""A stand-in for Google, shared by the notifier tests: the OAuth2 token endpoint (it VERIFIES the RS256 signature and the
claims of the sign-in) and the FCM send endpoint (it checks the bearer token and records what was sent)."""
import base64, json, re, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes

ISSUER = "firebase-adminsdk@vzbot-test.iam.gserviceaccount.com"


class Google:
    def __init__(self, key, port):
        self.key = key; self.port = port
        self.lock = threading.Lock(); self.reset(); self.server = None
    def reset(self):
        with self.lock:
            self.messages = []; self.token_requests = 0; self.send_attempts = 0
            self.fail = []            # statuses to answer with (one per send attempt) before accepting
            self.reject_token_once = False; self.token_error = False; self.valid = set(); self.sign_errors = []
    def start(self):
        g = self
        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def _json(self, status, obj):
                data = json.dumps(obj).encode(); self.send_response(status); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                with g.lock:
                    if self.path == "/token":
                        g.token_requests += 1
                        form = parse_qs(body.decode())
                        if g.token_error:
                            return self._json(400, {"error": "invalid_grant", "error_description": "Invalid JWT Signature."})
                        assertion = form["assertion"][0]; header, claims, signature = assertion.split(".")
                        pad = lambda s: s + "=" * (-len(s) % 4)
                        try:
                            g.key.public_key().verify(base64.urlsafe_b64decode(pad(signature)), (header + "." + claims).encode(), padding.PKCS1v15(), hashes.SHA256())
                            c = json.loads(base64.urlsafe_b64decode(pad(claims))); h = json.loads(base64.urlsafe_b64decode(pad(header)))
                            assert form["grant_type"][0] == "urn:ietf:params:oauth:grant-type:jwt-bearer"
                            assert h == {"alg": "RS256", "typ": "JWT"}
                            assert c["iss"] == ISSUER and c["scope"] == "https://www.googleapis.com/auth/firebase.messaging"
                            assert c["aud"] == "http://127.0.0.1:%d/token" % g.port and c["exp"] - c["iat"] == 3600 and abs(c["iat"] - time.time()) < 30
                        except Exception as error:
                            g.sign_errors.append(repr(error)); return self._json(400, {"error": "invalid_grant", "error_description": "bad assertion %r" % error})
                        token = "tok-%d" % g.token_requests; g.valid.add(token)
                        return self._json(200, {"access_token": token, "expires_in": 3600, "token_type": "Bearer"})
                    m = re.match(r"^/v1/projects/([^/]+)/messages:send$", self.path)
                    if m:
                        g.send_attempts += 1
                        auth = self.headers.get("Authorization", "")
                        if g.reject_token_once:
                            g.reject_token_once = False; g.valid.clear()
                            return self._json(401, {"error": {"code": 401, "message": "Request had invalid authentication credentials.", "status": "UNAUTHENTICATED"}})
                        if not auth.startswith("Bearer ") or auth[7:] not in g.valid:
                            return self._json(401, {"error": {"code": 401, "message": "bad token"}})
                        if g.fail:
                            status = g.fail.pop(0)
                            return self._json(status, {"error": {"code": status, "message": "stand-in failure %d" % status, "status": "ERR"}})
                        g.messages.append({"project": m.group(1), "payload": json.loads(body), "token": auth[7:]})
                        return self._json(200, {"name": "projects/%s/messages/%d" % (m.group(1), len(g.messages))})
                self._json(404, {"error": "no"})
        for _ in range(50):
            try:
                self.server = ThreadingHTTPServer(("127.0.0.1", self.port), H); break
            except OSError: time.sleep(0.2)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
    def stop(self):
        self.server.shutdown(); self.server.server_close()
    def kinds(self): 
        with self.lock: return [m["payload"]["message"]["data"]["type"] for m in self.messages]
    def bodies(self):
        with self.lock: return [m["payload"]["message"]["notification"]["body"] for m in self.messages]

