"""
Where the notifications go (phase 5c, release 1.20.0): the channels of the notification service, as the dashboard sees
and sets them (Settings -> Notifications).

    ntfy      the free ntfy app listens to a private topic: a random name made here ("klippeye-" + 16 letters and digits,
              about 80 bits: nobody guesses it). Whoever knows the topic can read the notifications, so it is shown only
              to the dashboard. The server is https://ntfy.sh unless the person runs one of their own.
    Firebase  set up by hand (service-account.json and "topic" in notifier.json, guide appendix A): only shown here.

Everything lives in notifier.json in the data folder, the file the notification service reads (it notices the change by
itself, no restart). The other entries of the file are kept as they are.
"""
import json
import os
import re
import secrets
import string
import subprocess
import sys

NTFY_DEFAULT_SERVER = "https://ntfy.sh"
TOPIC_PREFIX = "klippeye-"
TOPIC_LETTERS = string.ascii_lowercase + string.digits
TOPIC_LENGTH = 16
TOPIC = re.compile(r"^[-_A-Za-z0-9]{1,64}$")
SERVER = re.compile(r"^https?://[A-Za-z0-9.\-]+(:\d{1,5})?(/[A-Za-z0-9._~\-/]*)?$")
TOKEN = re.compile(r"^[A-Za-z0-9._~+/=\-]{0,200}$")
TEST_TIMEOUT_S = 45


class ChannelError(ValueError):
    def __init__(self, text, **values):
        ValueError.__init__(self, text)
        self.values = values


# what this module may answer, for the dictionaries of the backend (bt translates them)
MESSAGES = (
    "notifier.json is damaged: fix it or delete it ({error})",
    "the server address must start with http:// or https://",
    "the access token has characters that are not allowed",
    "the address of the dashboard must start with http:// or https://",
)


def new_topic():
    return TOPIC_PREFIX + "".join(secrets.choice(TOPIC_LETTERS) for _ in range(TOPIC_LENGTH))


class NotifyChannels:
    def __init__(self, data_dir, repo_dir, write_json):
        self.path = os.path.join(data_dir, "notifier.json")
        self.data_dir = data_dir
        self.repo_dir = repo_dir
        self.write_json = write_json  # write_json_atomic of the backend

    def _raw(self):
        """notifier.json as it is ({} when there is none yet). ChannelError when it is damaged."""
        try:
            with open(self.path, encoding="utf-8") as handle:
                data = json.load(handle)
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as error:
            raise ChannelError(MESSAGES[0], error=error)
        if not isinstance(data, dict):
            raise ChannelError(MESSAGES[0], error="not a JSON object")
        return data

    def _firebase(self, raw):
        key = raw.get("service_account_file") or "service-account.json"
        if not isinstance(key, str):
            key = "service-account.json"
        key = key if os.path.isabs(key) else os.path.join(self.data_dir, key)
        return {"on": bool(raw.get("topic")) and os.path.isfile(key), "topic_set": bool(raw.get("topic")), "key_found": os.path.isfile(key)}

    def summary(self):
        """{ntfy: {enabled, server, topic, has_token, click, link}, firebase: {on, ...}, install_command}."""
        raw = self._raw()
        one = raw.get("ntfy") if isinstance(raw.get("ntfy"), dict) else {}
        server = str(one.get("server") or NTFY_DEFAULT_SERVER).rstrip("/")
        topic = str(one.get("topic") or "")
        ntfy = {
            "enabled": bool(one.get("enabled")) and bool(TOPIC.match(topic)),
            "server": server,
            "default_server": server == NTFY_DEFAULT_SERVER,
            "topic": topic,
            "has_token": bool(one.get("token")),
            "click": str(one.get("click") or ""),
            "link": subscribe_link(server, topic) if topic else "",
            "web": server + "/" + topic if topic else "",
        }
        return {"ntfy": ntfy, "firebase": self._firebase(raw), "install_command": "bash " + os.path.join(self.repo_dir, "scripts", "install.sh")}

    def set_ntfy(self, body):
        """{enabled: bool, new_topic: bool, server: str, token: str | null, click: str}: only the keys given change.
        Turning ntfy on the first time makes the private topic."""
        raw = self._raw()
        one = dict(raw.get("ntfy")) if isinstance(raw.get("ntfy"), dict) else {}
        if "server" in body:
            server = str(body.get("server") or "").strip().rstrip("/") or NTFY_DEFAULT_SERVER
            if not SERVER.match(server):
                raise ChannelError(MESSAGES[1])
            one["server"] = server
        if "token" in body:
            token = str(body.get("token") or "").strip()
            if not TOKEN.match(token):
                raise ChannelError(MESSAGES[2])
            one["token"] = token
        if "click" in body:
            click = str(body.get("click") or "").strip()
            if click and not re.match(r"^https?://\S{1,300}$", click):
                raise ChannelError(MESSAGES[3])
            one["click"] = click
        if body.get("enabled") is True or body.get("enabled") is False:
            one["enabled"] = body["enabled"]
        if body.get("new_topic") is True or (one.get("enabled") and not TOPIC.match(str(one.get("topic") or ""))):
            one["topic"] = new_topic()
        one.setdefault("server", NTFY_DEFAULT_SERVER)
        raw["ntfy"] = one
        self.write_json(self.path, raw, private=True)
        return self.summary()

    def send_test(self, python=None):
        """Runs the notification service's own test (every channel that is set up): {results: [{channel, ok, error}]}."""
        program = os.path.join(self.repo_dir, "notifier", "klippeye_notifier.py")
        try:
            done = subprocess.run([python or sys.executable, program, "--config", self.path, "--test", "--json"],
                                  capture_output=True, text=True, timeout=TEST_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            return {"results": [], "error": "timeout"}
        for line in reversed(done.stdout.strip().splitlines()):
            try:
                answer = json.loads(line)
            except ValueError:
                continue
            if isinstance(answer, dict) and isinstance(answer.get("results"), list):
                return {"results": answer["results"]}
        return {"results": [], "error": (done.stdout + done.stderr).strip()[-300:]}


def subscribe_link(server, topic):
    """The link that opens the ntfy app on the phone and subscribes to the topic (ntfy://host/topic?display=KlippEye)."""
    secure = server.startswith("https://")
    host = server.split("://", 1)[1]
    return "ntfy://%s/%s?display=KlippEye%s" % (host, topic, "" if secure else "&secure=false")
