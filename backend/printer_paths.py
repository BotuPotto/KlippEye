"""
Where this printer keeps its files (roadmap phase 5: KlippEye on any Klipper machine, any user, not only "pi").

Moonraker knows the real folders: GET /server/files/roots lists its roots ("config", "logs", "gcodes"...) with their paths,
also on installations with another user, several printers (printer_1_data...) or the old layout (~/klipper_config). They are
asked once and remembered; when Moonraker does not answer yet the usual places in the home folder of the user that runs
KlippEye are used (and Moonraker is asked again a minute later).

No path in KlippEye names a user: tests/test_no_fixed_paths.py fails if a fixed home folder comes back in the code.
"""
import os
import threading
import time

ASK_AGAIN_S = 60.0
_lock = threading.Lock()
_known = {"time": float("-inf"), "roots": {}}


def _ask(moonraker_url, requests):
    response = requests.get(moonraker_url + "/server/files/roots", timeout=3)
    response.raise_for_status()
    roots = {}
    for item in response.json().get("result") or []:
        if isinstance(item, dict) and item.get("name") and item.get("path"):
            roots[str(item["name"])] = os.path.expanduser(str(item["path"]))
    return roots


def roots(moonraker_url=None, requests=None, now=None):
    """Moonraker's roots {name: path}; {} when it has never answered."""
    now = time.time() if now is None else now
    with _lock:
        fresh = _known["roots"] and now - _known["time"] < 24 * 3600
        tried_lately = now - _known["time"] < ASK_AGAIN_S
        if fresh or tried_lately or moonraker_url is None or requests is None:
            return dict(_known["roots"])
        _known["time"] = now
    try:
        found = _ask(moonraker_url, requests)
    except Exception:
        found = {}
    with _lock:
        if found:
            _known["roots"] = found
        return dict(_known["roots"])


def forget():
    """Ask Moonraker again next time (tests, a new installation)."""
    with _lock:
        _known.update(time=float("-inf"), roots={})


def _home():
    return os.path.expanduser("~")


def _first_existing(candidates):
    for path in candidates:
        if path and os.path.isdir(path):
            return path
    return candidates[0]


def config_dir(moonraker_url=None, requests=None):
    """The folder of printer.cfg."""
    found = roots(moonraker_url, requests).get("config")
    if found:
        return found
    home = _home()
    return _first_existing([os.path.join(home, "printer_data", "config"), os.path.join(home, "klipper_config")])


def logs_dir(moonraker_url=None, requests=None):
    """The folder of klippy.log and moonraker.log."""
    found = roots(moonraker_url, requests).get("logs")
    if found:
        return found
    home = _home()
    return _first_existing([os.path.join(home, "printer_data", "logs"), os.path.join(home, "klipper_logs")])


def macro_dirs(moonraker_url=None, requests=None):
    """Where the macro files may be: the config folder, then Klippain Shake&Tune's own folder if it is installed."""
    home = _home()
    out = [config_dir(moonraker_url, requests), os.path.join(home, "klippain_shaketune"), os.path.join(home, "klippain_shaketune", "shaketune")]
    return [p for i, p in enumerate(out) if p not in out[:i]]


def shaketune_dirs(moonraker_url=None, requests=None):
    """Where Shake&Tune may keep its files."""
    home = _home()
    config = config_dir(moonraker_url, requests)
    out = [os.path.join(config, "shaketune"), os.path.join(home, "klippain_shaketune"), os.path.join(home, "klippain_shaketune", "shaketune"),
           os.path.join(home, "klippain_shaketune", "config")]
    return [p for i, p in enumerate(out) if p not in out[:i]]
