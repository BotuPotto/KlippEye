#!/usr/bin/env python3
"""KlippEye at the Raspberry's own address (1.94): http://<raspberry> (and https://<raspberry>), without a port.

The Raspberry's web server (nginx) answers on port 80, the one a browser uses when no port is written; the other
interface installed with Klipper usually sits there. `main` puts KlippEye there instead:

- the sites that listened on port 80 (and 443) move to the next free port from 81 (and 8444): they keep working
  there, untouched otherwise; a copy of each file is kept first in <nginx>/klippeye-backup;
- a site "klippeye" listens on 80 (and, with --https, on 443 with KlippEye's certificate) and hands everything to the
  KlippEye service (127.0.0.1:8085), except what goes straight to Moonraker (its WebSocket, the uploads of files, the
  slicers' upload through Moonraker's compatible API) and the camera, whose locations are copied from the site that had port 80;
- nginx checks the new configuration (nginx -t) before reloading; on an error everything goes back as it was.

`restore` puts the copies back and removes the site. `status` says what is in place (JSON).
Run as root (sudo): scripts/install.sh, the `klippeye web` command and the dashboard (sudo -n) call it.
"""

import json
import os
import re
import shutil
import subprocess
import sys

NGINX = os.environ.get("KLIPPEYE_NGINX_DIR", "/etc/nginx")
TEST = os.environ.get("KLIPPEYE_NGINX_TEST", "nginx -t")
RELOAD = os.environ.get("KLIPPEYE_NGINX_RELOAD", "systemctl reload nginx")
SITE = "klippeye"
MARK = "# KlippEye (scripts/web_front.py):"
BACKEND = "127.0.0.1:8085"
MOONRAKER = "127.0.0.1:7125"
LISTEN_RE = re.compile(r"^(\s*listen\s+)((?:\[::\]:|[\d.]+:)?)(\d+)(\b[^;]*;)", re.MULTILINE)


def paths():
    available, enabled = os.path.join(NGINX, "sites-available"), os.path.join(NGINX, "sites-enabled")
    if os.path.isdir(enabled):
        return os.path.join(available, SITE), os.path.join(enabled, SITE)
    return os.path.join(NGINX, "conf.d", SITE + ".conf"), None


def backup_dir():
    return os.path.join(NGINX, "klippeye-backup")


def enabled_files():
    """The files nginx reads for its sites (sites-enabled resolved, conf.d/*.conf), without ours."""
    out = []
    for folder in (os.path.join(NGINX, "sites-enabled"), os.path.join(NGINX, "conf.d")):
        if not os.path.isdir(folder):
            continue
        for name in sorted(os.listdir(folder)):
            if name in (SITE, SITE + ".conf") or (folder.endswith("conf.d") and not name.endswith(".conf")):
                continue
            full = os.path.realpath(os.path.join(folder, name))
            if os.path.isfile(full) and full not in out:
                out.append(full)
    return out


def read(path):
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        return handle.read()


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".klippeye-new", "w", encoding="utf-8") as handle:
        handle.write(text)
    os.replace(path + ".klippeye-new", path)


def ports_in(text):
    return {int(match.group(3)) for match in LISTEN_RE.finditer(text)}


def camera_locations(text):
    """The `location /webcam…{ … }` blocks of a site, as they are (the camera keeps working at the same path)."""
    blocks = []
    for match in re.finditer(r"^[ \t]*location\s+[^{]*?/webcam[^{]*\{", text, re.MULTILINE):
        depth, index = 0, match.end() - 1
        while index < len(text):
            if text[index] == "{":
                depth += 1
            elif text[index] == "}":
                depth -= 1
                if depth == 0:
                    blocks.append(text[match.start():index + 1].rstrip())
                    break
            index += 1
    return blocks


def site_text(cameras, https=None):
    """Our site. https: (cert, key) or None."""
    tls = ""
    if https:
        tls = ("    listen 443 ssl default_server;\n    listen [::]:443 ssl default_server;\n"
               "    ssl_certificate %s;\n    ssl_certificate_key %s;\n    ssl_protocols TLSv1.2 TLSv1.3;\n"
               "    ssl_session_cache shared:klippeye:1m;\n    ssl_session_timeout 1d;\n") % https
    camera = "\n\n".join(cameras) if cameras else "    location /webcam/ {\n        proxy_pass http://127.0.0.1:8080/;\n    }"
    to_moonraker = ("        proxy_pass http://%s;\n        proxy_http_version 1.1;\n        proxy_set_header Host $http_host;\n"
                    "        proxy_set_header X-Real-IP $remote_addr;\n        proxy_set_header X-Forwarded-For $remote_addr;\n"
                    "        proxy_set_header X-Forwarded-Proto $scheme;\n") % MOONRAKER
    return """%s KlippEye at the Raspberry's own address. `klippeye web restore` puts back what was here.
map $http_upgrade $klippeye_upgrade {
    default upgrade;
    '' close;
}

server {
    listen 80 default_server;
    listen [::]:80 default_server;
%s    server_name _;
    client_max_body_size 0;

    # Moonraker's WebSocket (the console and the notifications, live)
    location /websocket {
%s        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $klippeye_upgrade;
        proxy_read_timeout 86400;
    }

    # the uploads of print files (dashboard and slicers) straight to Moonraker, without holding them in memory
    location = /server/files/upload {
%s        proxy_request_buffering off;
        proxy_read_timeout 600;
    }
    location /api/files/ {
%s        proxy_request_buffering off;
        proxy_read_timeout 600;
    }

    # the camera, as the previous page had it
%s

    # everything else: the KlippEye service (the dashboard, its API, Moonraker's API through it)
    location / {
        proxy_pass http://%s;
        proxy_http_version 1.1;
        proxy_set_header Host $http_host;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $klippeye_upgrade;
        proxy_buffering off;
        proxy_read_timeout 600;
    }
}
""" % (MARK, tls, to_moonraker, to_moonraker, to_moonraker, camera, BACKEND)


def run(command):
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    return result.returncode == 0, (result.stderr or result.stdout).strip()


def status():
    available, enabled = paths()
    ours = os.path.exists(available) and MARK in read(available)
    moved = sorted(name for name in os.listdir(backup_dir()) if not name.endswith(".path")) if os.path.isdir(backup_dir()) else []
    others = {}
    for path in enabled_files():
        text = read(path)
        others[os.path.basename(path)] = sorted(ports_in(text))
    return {"nginx": os.path.isdir(NGINX), "main": bool(ours and (enabled is None or os.path.lexists(enabled))),
            "https": bool(ours and "listen 443 ssl" in read(available)), "moved": moved, "sites": others}


def move_ports(path, text, from_port, used, start):
    """`text` with its listen lines on `from_port` moved to a free port from `start`; (text, new port or None)."""
    if from_port not in ports_in(text):
        return text, None
    port = start
    while port in used:
        port += 1
    used.add(port)

    def replace(match):
        if int(match.group(3)) != from_port:
            return match.group(0)
        return match.group(1) + match.group(2) + str(port) + match.group(4)
    return LISTEN_RE.sub(replace, text), port


def main(https=None):
    """Puts KlippEye on port 80 (and 443 with https=(cert, key)). Returns (ok, message)."""
    if not os.path.isdir(NGINX):
        return False, "nginx is not installed"
    os.makedirs(backup_dir(), exist_ok=True)
    files = enabled_files()
    used = set()
    for path in files:
        used |= ports_in(read(path))
    used |= {80, 443, 8085, 7125}
    cameras, changed, report = [], [], []
    available, enabled = paths()
    if os.path.exists(available) and MARK in read(available):  # already ours: keep the camera blocks it has
        cameras = camera_locations(read(available))
    for path in files:
        text = read(path)
        if not cameras and 80 in ports_in(text):
            cameras = camera_locations(text)
        new = text
        moved = []
        for port, start in ((80, 81), (443, 8444)) if https else ((80, 81),):
            new, to = move_ports(path, new, port, used, start)
            if to:
                moved.append("%d→%d" % (port, to))
        if new != text:
            saved = os.path.join(backup_dir(), os.path.basename(path))
            if not os.path.exists(saved):
                shutil.copy2(path, saved)
                with open(saved + ".path", "w", encoding="utf-8") as handle:
                    handle.write(path)
            write(path, new)
            changed.append(path)
            report.append("%s: %s" % (os.path.basename(path), ", ".join(moved)))
    write(available, site_text(cameras, https))
    if enabled and not os.path.lexists(enabled):
        os.symlink(available, enabled)
    ok, message = run(TEST)
    if not ok:
        restore(reload=False)
        return False, "nginx refused the new configuration, everything was put back: " + message[-400:]
    ok, message = run(RELOAD)
    if not ok:  # the files on disk would otherwise disagree with what nginx serves: put the previous ones back
        restore()
        return False, "nginx did not reload, everything was put back: " + message[-300:]
    return True, "KlippEye is at the Raspberry's own address" + ("; moved: " + "; ".join(report) if report else "")


def restore(reload=True):
    available, enabled = paths()
    for one in (enabled, available):
        if one and os.path.lexists(one) and (os.path.islink(one) or MARK in read(one)):
            os.remove(one)
    folder = backup_dir()
    if os.path.isdir(folder):
        for name in os.listdir(folder):
            if name.endswith(".path"):
                continue
            target_file = os.path.join(folder, name + ".path")
            target = read(target_file).strip() if os.path.exists(target_file) else None
            if target:
                shutil.copy2(os.path.join(folder, name), target)
        shutil.rmtree(folder, ignore_errors=True)
    if reload:
        ok, message = run(TEST)
        if not ok:
            return False, "nginx refuses the restored configuration: " + message[-400:]
        ok, message = run(RELOAD)
        if not ok:
            return False, "nginx did not reload: " + message[-300:]
    return True, "the previous page is back at the Raspberry's own address"


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "status"
    if command == "status":
        print(json.dumps(status()))
        sys.exit(0)
    if command == "main":
        https = None
        if "--https" in sys.argv:
            index = sys.argv.index("--https")
            https = (sys.argv[index + 1], sys.argv[index + 2])
        done, text = main(https)
    elif command == "restore":
        done, text = restore()
    else:
        print("usage: web_front.py status | main [--https CERT KEY] | restore")
        sys.exit(2)
    print(text)
    sys.exit(0 if done else 1)
