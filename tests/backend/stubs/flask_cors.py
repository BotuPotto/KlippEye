"""Test-only stand-in for flask_cors (not installed in the sandbox): adds the same open CORS headers."""
def CORS(app, resources=None, **kw):
    @app.after_request
    def _cors(resp):
        resp.headers.setdefault("Access-Control-Allow-Origin", "*")
        return resp
    return app
