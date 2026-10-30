"""
Where the camera's single photo (the "snapshot") is taken from (1.23.0). The AI monitor, the camera calibration and the
recordings use it, and later the timelapse. It is chosen in the dashboard (Settings -> Camera -> Snapshot) like in Mainsail:
empty = automatic, worked out from the camera's address; a path on the Raspberry ("/webcam/?action=snapshot") or a full
address ("http://192.168.1.20:8080/?action=snapshot").

"/webcam/?action=snapshot" is the address every streamer of crowsnest answers (ustreamer, camera-streamer, mjpg-streamer)
behind the nginx of Mainsail / Fluidd; before 1.23.0 the backend always asked "/webcam/snapshot", which mjpg-streamer does
not have. The same rules are in the dashboard (16-settings.js, defaultSnapshot): keep the two the same.
"""
import re

DEFAULT = "/webcam/?action=snapshot"
LOCAL_BASE = "http://127.0.0.1"   # the backend runs on the Raspberry: a path is asked to its own nginx (port 80)
_PATH = re.compile(r"^/[^\s]{0,299}$")
_FULL = re.compile(r"^https?://[^/?#\s]+[^\s]{0,280}$", re.IGNORECASE)


def clean(value):
    """A path or a full http(s) address, or "" (automatic) for anything else."""
    if not isinstance(value, str):
        return ""
    text = value.strip()
    if _FULL.match(text) or _PATH.match(text):
        return text
    return ""


def automatic(method, address):
    """The snapshot that goes with the camera: "/webcam2/webrtc" -> "/webcam2/?action=snapshot", the adaptive method's own
    address, "...?action=stream" -> "...?action=snapshot"; a page of any kind -> the usual crowsnest one."""
    address = clean(address)
    if not address:
        return DEFAULT
    if method == "adaptive":
        return address
    if "action=stream" in address:
        return address.replace("action=stream", "action=snapshot")
    match = re.match(r"^(.*/)(webrtc|stream)/?(\?.*)?$", address)
    if match and (method in ("webrtc", "mjpeg") or match.group(2) == "webrtc"):
        return match.group(1) + "?action=snapshot"
    return DEFAULT


def chosen(settings):
    """The snapshot address the dashboard's settings describe (the "settings" document of Moonraker's database)."""
    camera = settings.get("camera") if isinstance(settings, dict) else None
    if not isinstance(camera, dict):
        return DEFAULT
    own = clean(camera.get("snapshot"))
    if own:
        return own
    method = camera.get("method") if camera.get("method") in ("webrtc", "mjpeg", "adaptive", "iframe") else "webrtc"
    urls = camera.get("urls") if isinstance(camera.get("urls"), dict) else {}
    return automatic(method, urls.get(method) or "")


def absolute(address, base=LOCAL_BASE):
    """A path becomes an address of the Raspberry itself (`base`: its nginx)."""
    return address if address.lower().startswith(("http://", "https://")) else base.rstrip("/") + address
