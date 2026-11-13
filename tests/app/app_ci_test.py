"""ci/app_ci.py tested alone (the steps of the app's workflow): real keytool, real git, stand-ins for aapt2 and apksigner."""
import contextlib
import datetime
import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # the repository
spec = importlib.util.spec_from_file_location("app_ci", os.path.join(ROOT, "ci", "app_ci.py"))
ci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci)

failures = 0
SECRET = "KLIPPEYE_CHIAVE_PASSWORD"


def check(name, ok, detail=""):
    global failures
    if not ok:
        failures += 1
    print(("PASS " if ok else "FAIL ") + name + ("" if ok or not detail else " :: " + str(detail)))


def raises(function, word=""):
    """True when `function` stops with a CiError whose message has `word`."""
    try:
        function()
    except ci.CiError as error:
        return word.lower() in str(error).lower()
    return False


def write(path, content):
    with open(path, "wb" if isinstance(content, bytes) else "w") as f:
        f.write(content)


def read(path, binary=False):
    with open(path, "rb" if binary else "r") as f:
        return f.read()


def repo(version="1.0.0", published=None):
    root = tempfile.mkdtemp(prefix="repo-")
    os.makedirs(root + "/android")
    if version is not None:
        write(root + "/android/VERSION", version + "\n")
    if published:
        os.makedirs(root + "/apk")
        write(root + "/apk/KlippEye.apk", b"x" * 10)
        write(root + "/apk/version.json", json.dumps(published))
    return root, ci.paths(root)


# ---- version code: the same values tested in Gradle and in Kotlin ----
for text, expected in [("1.0.0", 10000), ("1.2.3", 10203), ("0.0.1", 1), ("99.99.99", 999999), (" 2.10.0 ", 21000), ("1.0", None), ("1.0.100", None), ("mk218", None), ("1.0.0-beta", None), ("", None), (None, None)]:
    check("version_code(%r) = %s" % (text, expected), ci.version_code(text) == expected)

# ---- decide ----
root, p = repo("1.0.0")
r = ci.decide(p)
check("decide: nothing published -> builds", r["build"] == "true" and r["version"] == "1.0.0" and r["code"] == 10000)
root, p = repo("1.0.0", {"version": "1.0.0"})
check("decide: same version -> does not build", ci.decide(p)["build"] == "false")
check("decide: same version but forced -> builds", ci.decide(p, force=True)["build"] == "true")
root, p = repo("1.0.1", {"version": "1.0.0"})
r = ci.decide(p)
check("decide: higher version -> builds", r["build"] == "true" and "1.0.1" in r["reason"] and "1.0.0" in r["reason"])
root, p = repo("1.0.0", {"version": "1.0.1"})
check("decide: lower version -> a clear error", raises(lambda: ci.decide(p), "older version"))
check("decide: lower version, forced too -> error", raises(lambda: ci.decide(p, force=True), "older version"))
root, p = repo("1.0.0", {"version": "1.0.0"})
os.remove(root + "/apk/KlippEye.apk")
check("decide: version.json is there but the APK is not -> builds", ci.decide(p)["build"] == "true")
root, p = repo("1.0.0")
os.makedirs(root + "/apk")
write(root + "/apk/version.json", "{broken")
write(root + "/apk/KlippEye.apk", b"x")
check("decide: damaged version.json -> builds", ci.decide(p)["build"] == "true")
root, p = repo("1.0.0")
r = ci.decide(p, event="push", password="")
check("decide: first upload (push) without the password -> does not build and says to create the secret", r["build"] == "false" and SECRET in r["reason"] and "docs/GUIDE.md" in r["reason"], r)
check("decide: push with the password -> builds", ci.decide(p, event="push", password="x" * 20)["build"] == "true")
check("decide: started by hand without the password -> builds (the 'key' step then says what is missing)", ci.decide(p, event="workflow_dispatch", password="")["build"] == "true")
root, p = repo("1.0.0", {"version": "1.0.0"})
check("decide: push without the password, version already published -> the version's reason, not the secret's", "already published" in ci.decide(p, event="push", password="")["reason"])
root, p = repo("0.9.0", {"version": "1.0.0"})
check("decide: push without the password, lower version -> still the version's error", raises(lambda: ci.decide(p, event="push", password=""), "older version"))
root, p = repo("what")
check("decide: android/VERSION not valid -> error", raises(lambda: ci.decide(p), "three numbers"))
root, p = repo(None)
check("decide: android/VERSION missing -> error", raises(lambda: ci.decide(p), "missing"))

# ---- key (real keytool) ----
root, p = repo()
good = "a long and secret sentence 2026"
check("key: no password", raises(lambda: ci.key(p, ""), SECRET))
check("key: password too short", raises(lambda: ci.key(p, "short123"), "too short"))
check("key: password with a line break", raises(lambda: ci.key(p, good + "\n"), "line break"))
check("key: the errors made no file", not os.path.exists(p["key"]))
check("key: made the first time", ci.key(p, good) == "created" and os.path.isfile(p["key"]))
listing = subprocess.run(["keytool", "-list", "-v", "-keystore", p["key"], "-storepass", good], capture_output=True, text=True).stdout
check("key: alias klippeye, PKCS12, RSA 4096", "Alias name: klippeye" in listing and "PKCS12" in listing and "4096-bit RSA" in listing, listing[:400])
valid = [line for line in listing.splitlines() if line.startswith("Valid from")]
check("key: valid for more than 90 years", bool(valid) and int(valid[0].split("until:")[1].split()[-1]) - int(valid[0].split("Valid from:")[1].split("until")[0].split()[-1]) >= 90, valid)
before = read(p["key"], binary=True)
check("key: the second time it is the same one", ci.key(p, good) == "existing" and read(p["key"], binary=True) == before)
check("key: wrong password -> an error with what to do", raises(lambda: ci.key(p, "another very long sentence"), "does not open the key"))
write(p["key"], b"not a keystore")
check("key: damaged file -> error", raises(lambda: ci.key(p, good), "does not open the key"))

# ---- google ----
root, p = repo()
os.makedirs(root + "/android/app")
check("google: no secret -> False, no file", ci.google(p, "") is False and ci.google(p, None) is False and not os.path.exists(p["google"]))
check("google: broken JSON", raises(lambda: ci.google(p, "{what"), "is not a google-services.json file"))
check("google: JSON of another kind", raises(lambda: ci.google(p, '{"a":1}'), "is not a google-services.json file"))
other = {"client": [{"client_info": {"android_client_info": {"package_name": "com.other.app"}}}]}
check("google: the app of another package", raises(lambda: ci.google(p, json.dumps(other)), "com.other.app"))
right = {"project_info": {"project_id": "x"}, "client": [{"client_info": {"android_client_info": {"package_name": "com.klippeye.app"}}}]}
check("google: the right file is written", ci.google(p, "  " + json.dumps(right) + "\n") is True and json.loads(read(p["google"])) == right)

# ---- tools ----
sdk = tempfile.mkdtemp(prefix="sdk-")
for version in ("9.0.0", "33.0.1", "34.0.0", "34.0.0-rc1"):
    folder = "%s/build-tools/%s" % (sdk, version)
    os.makedirs(folder)
    for name in ("aapt2", "apksigner"):
        write("%s/%s" % (folder, name), "#!/bin/sh\necho %s\n" % version)
        os.chmod("%s/%s" % (folder, name), 0o755)
os.environ["ANDROID_HOME"] = sdk
found = ci.find_tool("aapt2")
check("tools: the newest build-tools are chosen", "/34.0.0/" in found or "/34.0.0-rc1/" in found, found)
check("tools: one that is not there -> error", raises(lambda: ci.find_tool("not-there-xyz"), "was not found"))
del os.environ["ANDROID_HOME"]

# ---- publish (stand-ins for aapt2 and apksigner, with the output of the real ones) ----
tools = tempfile.mkdtemp(prefix="tools-")


def stand_in(name, body):
    path = tools + "/" + name
    write(path, "#!/bin/bash\n" + body)
    os.chmod(path, 0o755)
    return path


def aapt2(package="com.klippeye.app", code="10000", name="1.0.0", exits=0):
    return stand_in("aapt2", "echo \"package: name='%s' versionCode='%s' versionName='%s' platformBuildVersionName='14' platformBuildVersionCode='34' compileSdkVersion='34'\"\nexit %d\n" % (package, code, name, exits))


def apksigner(fingerprint="ab" * 32, exits=0):
    return stand_in("apksigner", "echo 'Signer #1 certificate DN: CN=KlippEye, O=KlippEye'\necho 'Signer #1 certificate SHA-256 digest: %s'\necho 'Signer #1 certificate SHA-1 digest: 0000'\nexit %d\n" % (fingerprint, exits))


def make_apk(path, manifest=True, dex=True, big=True):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as z:
        if manifest:
            z.writestr("AndroidManifest.xml", b"m")
        if dex:
            z.writestr("classes.dex", b"d")
        if big:
            z.writestr("resources.arsc", os.urandom(200 * 1024))
    return path


root, p = repo("1.0.0")
apk = make_apk(root + "/built.apk")
info = ci.publish(p, apk, aapt2(), apksigner(), source="0123456789abcdef0123", now=datetime.datetime(2026, 10, 22, 21, 15, 7, 999))
check("publish: apk/KlippEye.apk is the same file", read(p["apk"], binary=True) == read(apk, binary=True))
data = json.loads(read(p["info"]))
check("publish: version.json is right",
      data == {"version": "1.0.0", "code": 10000, "size": os.path.getsize(apk), "sha256": hashlib.sha256(read(apk, binary=True)).hexdigest(), "signature": "ab" * 32, "built": "2026-10-22T21:15:07Z", "source": "0123456789ab"}, data)
check("publish: no half-written file left", sorted(os.listdir(root + "/apk")) == ["KlippEye.apk", "version.json"], os.listdir(root + "/apk"))
check("publish: afterwards, decide says 'already published'", ci.decide(p)["build"] == "false")

# the same version built again with the same signature: fine; with another one: an error (unless it is wanted)
apk2 = make_apk(root + "/built2.apk")
ci.publish(p, apk2, aapt2(), apksigner())
check("publish: the same signature as before -> fine", True)
check("publish: another signature -> refused", raises(lambda: ci.publish(p, apk2, aapt2(), apksigner("cd" * 32)), "DIFFERENT key"))
check("publish: another signature did not touch the published files", json.loads(read(p["info"]))["signature"] == "ab" * 32)
new = ci.publish(p, apk2, aapt2(), apksigner("cd" * 32), allow_new_signature=True)
check("publish: another signature, wanted -> fine", new["signature"] == "cd" * 32)
# a version.json written before 1.116 calls the field "firma": the check still holds
write(p["info"], json.dumps({"version": "1.0.0", "firma": "ab" * 32}))
check("publish: the signature of an older version.json («firma») is still compared", raises(lambda: ci.publish(p, apk2, aapt2(), apksigner("cd" * 32)), "DIFFERENT key"))

root, p = repo("1.0.0")
apk = make_apk(root + "/c.apk")
check("publish: the APK has another version than android/VERSION", raises(lambda: ci.publish(p, apk, aapt2(code="10001", name="1.0.1"), apksigner()), "android/VERSION"))
check("publish: the APK is of another package", raises(lambda: ci.publish(p, apk, aapt2(package="com.other"), apksigner()), "com.other"))
check("publish: aapt2 does not answer", raises(lambda: ci.publish(p, apk, aapt2(exits=1), apksigner()), "cannot be read"))
check("publish: signature not valid (apksigner fails)", raises(lambda: ci.publish(p, apk, aapt2(), apksigner(exits=1)), "not signed properly"))
check("publish: missing file", raises(lambda: ci.publish(p, root + "/not-there.apk", aapt2(), apksigner()), "did not produce"))
write(root + "/zip.apk", os.urandom(200 * 1024))
check("publish: not a zip", raises(lambda: ci.publish(p, root + "/zip.apk", aapt2(), apksigner()), "not a valid APK"))
check("publish: a zip without the manifest", raises(lambda: ci.publish(p, make_apk(root + "/nm.apk", manifest=False), aapt2(), apksigner()), "manifest"))
check("publish: a zip without the code", raises(lambda: ci.publish(p, make_apk(root + "/nd.apk", dex=False), aapt2(), apksigner()), "the manifest or the code"))
check("publish: file too small", raises(lambda: ci.publish(p, make_apk(root + "/small.apk", big=False), aapt2(), apksigner()), "did not produce"))
check("publish: the errors published nothing", not os.path.exists(p["apk"]) and not os.path.exists(p["info"]))


# ---- save (real git, with a stand-in server in a folder) ----
def git(*a, cwd=None):
    r = subprocess.run(["git"] + list(a), cwd=cwd, capture_output=True, text=True)
    assert r.returncode == 0, (a, r.stderr)
    return r.stdout.strip()


FOLDERS = ["apk", "android/chiave"]
base = tempfile.mkdtemp(prefix="git-")
remote = base + "/remote.git"
git("init", "-q", "--bare", "-b", "main", remote)
seed = base + "/seed"
git("clone", "-q", remote, seed)
git("config", "user.email", "a@b.c", cwd=seed)
git("config", "user.name", "Seed", cwd=seed)
os.makedirs(seed + "/android")
write(seed + "/android/VERSION", "1.0.0\n")
write(seed + "/README.md", "hello\n")
git("add", "-A", cwd=seed)
git("commit", "-q", "-m", "start", cwd=seed)
git("push", "-q", "origin", "HEAD:main", cwd=seed)

url = "file://" + remote
shallow = base + "/shallow"
git("clone", "-q", "--depth", "1", "-b", "main", url, shallow)  # as actions/checkout does
os.makedirs(shallow + "/apk")
write(shallow + "/apk/KlippEye.apk", b"A" * 1000)
write(shallow + "/apk/version.json", '{"version":"1.0.0"}\n')
os.makedirs(shallow + "/android/chiave")
write(shallow + "/android/chiave/klippeye.p12", b"the-key")
check("save: pushes apk/ and the key", ci.save(shallow, "main", "App 1.0.0 [skip ci]", FOLDERS) is True)
check("save: the files are on the server", git("--git-dir", remote, "show", "main:apk/KlippEye.apk") == "A" * 1000 and "the-key" in git("--git-dir", remote, "show", "main:android/chiave/klippeye.p12"))
check("save: the message is the one given", git("--git-dir", remote, "log", "-1", "--format=%s", "main") == "App 1.0.0 [skip ci]")
check("save: the author is GitHub's robot", "actions@users.noreply.github.com" in git("--git-dir", remote, "log", "-1", "--format=%ae", "main"))
check("save: nothing changed, nothing pushed", ci.save(shallow, "main", "nothing", FOLDERS) is False and git("--git-dir", remote, "log", "-1", "--format=%s", "main") == "App 1.0.0 [skip ci]")
check("save: nothing else is touched (the rest of the repository is not in the commit)", git("--git-dir", remote, "show", "--stat", "--format=", "main").count("README") == 0)

# a race: while the workflow builds, somebody pushes something else
shallow2 = base + "/shallow2"
git("clone", "-q", "--depth", "1", "-b", "main", url, shallow2)
other = base + "/other"
git("clone", "-q", url, other)
git("config", "user.email", "x@y.z", cwd=other)
git("config", "user.name", "Person", cwd=other)
write(other + "/README.md", "hello, changed by the person\n")
os.makedirs(other + "/backend", exist_ok=True)
write(other + "/backend/new.py", "print(1)\n")
git("add", "-A", cwd=other)
git("commit", "-q", "-m", "the person's change", cwd=other)
git("push", "-q", "origin", "HEAD:main", cwd=other)
write(shallow2 + "/apk/KlippEye.apk", b"B" * 2000)
write(shallow2 + "/apk/version.json", '{"version":"1.0.1"}\n')
check("save: with a push that arrived meanwhile it still succeeds", ci.save(shallow2, "main", "App 1.0.1 [skip ci]", FOLDERS) is True)
check("save (race): the new file is on the server", git("--git-dir", remote, "show", "main:apk/KlippEye.apk") == "B" * 2000)
check("save (race): the person's change is still there", "changed by the person" in git("--git-dir", remote, "show", "main:README.md") and "print(1)" in git("--git-dir", remote, "show", "main:backend/new.py"))
check("save (race): the key is not gone", "the-key" in git("--git-dir", remote, "show", "main:android/chiave/klippeye.p12"))
check("save (race): a straight history with the two commits", git("--git-dir", remote, "log", "--format=%s", "main").splitlines()[:3] == ["App 1.0.1 [skip ci]", "the person's change", "App 1.0.0 [skip ci]"], git("--git-dir", remote, "log", "--format=%s", "main"))

# a server that always refuses the push (a protected branch, say): an error that can be understood, and not endless
closed = base + "/closed.git"
git("clone", "-q", "--bare", remote, closed)
write(closed + "/hooks/pre-receive", "#!/bin/sh\necho 'protected branch' >&2\nexit 1\n")
os.chmod(closed + "/hooks/pre-receive", 0o755)
shallow3 = base + "/shallow3"
git("clone", "-q", "--depth", "1", "-b", "main", "file://" + closed, shallow3)
os.makedirs(shallow3 + "/extra")
write(shallow3 + "/extra/x", "x")
check("save: push always refused -> a clear error after a few attempts", raises(lambda: ci.save(shallow3, "main", "x", ["extra"], attempts=2), "protected branch"))


# ---- command line ----
def run_main(*arguments):
    """-> (exit code, what was printed)."""
    printed = io.StringIO()
    with contextlib.redirect_stdout(printed), contextlib.redirect_stderr(io.StringIO()):
        code = ci.main(list(arguments))
    return code, printed.getvalue()


root, p = repo("1.0.2", {"version": "1.0.1"})
output = root + "/output.txt"
os.environ["GITHUB_OUTPUT"] = output
os.environ["KLIPPEYE_KEYSTORE_PASSWORD"] = "a very long sentence for the test"
code, printed = run_main("--root", root, "decide", "--event", "push")
written = read(output)
check("cli decide: code 0 and the outputs for GitHub", code == 0 and "build=true\n" in written and "version=1.0.2\n" in written and "code=10002\n" in written and "reason=" in written, written)
root, p = repo("1.0.0", {"version": "1.0.0"})
code, printed = run_main("--root", root, "decide")
check("cli decide: same version -> build=false and a notice that shows", code == 0 and "::notice" in printed, printed)
root, p = repo("1.0.0")
os.environ.pop("KLIPPEYE_KEYSTORE_PASSWORD")
code, printed = run_main("--root", root, "decide", "--event", "push")
check("cli decide: push without the secret -> code 0 (the run stays green) and a yellow annotation", code == 0 and "::warning title=App not built::" in printed and "build=false" in printed, printed)
root, p = repo("0.9.0", {"version": "1.0.0"})
code, printed = run_main("--root", root, "decide")
check("cli decide: lower version -> code 1 and a red annotation", code == 1 and "::error title=Android app::" in printed, printed)
os.environ.pop("GITHUB_OUTPUT")

print("ALL PASS" if failures == 0 else "FAILS: %d" % failures)
sys.exit(1 if failures else 0)
