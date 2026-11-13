#!/usr/bin/env python3
"""
The steps of .github/workflows/app.yml that need some thinking: the workflow builds the Android app's APK on GitHub's
computer. They are here (and not written inside the workflow file) so that they can be tested alone, without GitHub.

    app_ci.py decide     is a new APK needed? (compares android/VERSION with apk/version.json)
    app_ci.py key        the key that signs the APK: made the first time, then checked against the password
    app_ci.py google     writes app/google-services.json (the notifications) from the secret GOOGLE_SERVICES_JSON, if any
    app_ci.py publish    checks the built APK and puts it in apk/ with apk/version.json
    app_ci.py save       commits what changed and pushes it to GitHub

Python's standard library only. On GitHub the errors become red annotations ("::error::") whose text is written for a
person, not for a programmer; what the later steps need goes to $GITHUB_OUTPUT.
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

PACKAGE = "com.klippeye.app"
KEY_ALIAS = "klippeye"
VERSION_FORMAT = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{1,2})$")
MIN_PASSWORD = 16
BUILT_APK = os.path.join("android", "app", "build", "outputs", "apk", "release", "app-release.apk")
# The folder and the secret keep the names they were given at the start (the key is in the repository under that path,
# and the secret is in the settings of whoever builds the app): renaming them would only break what works.
KEY_FOLDER = os.path.join("android", "chiave")
PASSWORD_SECRET = "KLIPPEYE_CHIAVE_PASSWORD"
GUIDE = "docs/GUIDE.md, «Building your own Android app»"
MISSING_SECRET = "the secret %s is missing: create it (%s) and then start the «Android app» workflow by hand" % (PASSWORD_SECRET, GUIDE)


class CiError(Exception):
    """A problem the person can solve: the message is for them."""


def paths(root):
    return {
        "root": root,
        "app_version": os.path.join(root, "android", "VERSION"),
        "key": os.path.join(root, KEY_FOLDER, "klippeye.p12"),
        "google": os.path.join(root, "android", "app", "google-services.json"),
        "apk": os.path.join(root, "apk", "KlippEye.apk"),
        "info": os.path.join(root, "apk", "version.json"),
    }


def version_code(text):
    """1.2.3 -> 10203 (the same formula as android/app/build.gradle and the app's own update check); None for another format."""
    found = VERSION_FORMAT.match((text or "").strip())
    if not found:
        return None
    major, minor, patch = (int(x) for x in found.groups())
    return major * 10000 + minor * 100 + patch


def read_version(p):
    try:
        with open(p["app_version"], encoding="utf-8") as f:
            text = f.read().strip()
    except OSError:
        raise CiError("The file android/VERSION is missing (it holds the version number, for example 1.0.0).") from None
    code = version_code(text)
    if code is None:
        raise CiError("android/VERSION must hold three numbers from 0 to 99 separated by dots (for example 1.0.1): found «%s»." % text[:40])
    return text, code


def read_published(p):
    """What apk/version.json says, when it is valid, or None (missing, damaged, or the APK is not there)."""
    try:
        with open(p["info"], encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or version_code(data.get("version")) is None:
            return None
        if not os.path.isfile(p["apk"]):
            return None
        return data
    except (OSError, ValueError):
        return None


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_outputs(**values):
    """For the next steps of the workflow ($GITHUB_OUTPUT); outside GitHub they are only printed."""
    lines = "".join("%s=%s\n" % (k, v) for k, v in values.items())
    target = os.environ.get("GITHUB_OUTPUT")
    if target:
        with open(target, "a", encoding="utf-8") as f:
            f.write(lines)
    print(lines, end="")


# ---------------------------------------------------------------------------------------------------- decide
def decide(p, force=False, event="", password=""):
    """
    To build or not? `event` is what started the workflow ("push" or "workflow_dispatch"). A push without the key's
    password is not an error (it is the first upload: the secret is created afterwards): nothing is built, and it says so.
    A start by hand without the password is an error instead: a person asked for it.
    """
    outcome = _decide(p, force)
    if outcome["build"] == "true" and event == "push" and not password:
        return dict(build="false", version=outcome["version"], code=outcome["code"], reason=MISSING_SECRET)
    return outcome


def _decide(p, force):
    version, code = read_version(p)
    published = read_published(p)
    if published is None:
        return dict(build="true", version=version, code=code, reason="no app published so far")
    old = published["version"]
    old_code = version_code(old)
    if code < old_code:
        raise CiError("android/VERSION says %s but the app already published is %s: Android never installs an older version over a newer one. "
                      "Write a number higher than %s." % (version, old, old))
    if code > old_code:
        return dict(build="true", version=version, code=code, reason="new version: %s instead of %s" % (version, old))
    if force:
        return dict(build="true", version=version, code=code, reason="%s built again on request" % version)
    return dict(build="false", version=version, code=code, reason="%s is already published: for a new app raise the number in android/VERSION" % version)


# ---------------------------------------------------------------------------------------------------- key
def keytool(arguments, password):
    environment = dict(os.environ, KLIPPEYE_KEYSTORE_PASSWORD=password)
    return subprocess.run(["keytool"] + arguments, capture_output=True, text=True, env=environment)


def check_password(password):
    if not password:
        raise CiError("The secret %s is missing: on GitHub go to Settings → Secrets and variables → Actions → New repository secret, "
                      "call it %s and write a long sentence as its value (see %s)." % (PASSWORD_SECRET, PASSWORD_SECRET, GUIDE))
    if "\n" in password or "\r" in password:
        raise CiError("The password in the secret %s has a line break: write it again on one line." % PASSWORD_SECRET)
    if len(password) < MIN_PASSWORD:
        raise CiError("The password in the secret %s is too short (%d characters): at least %d are needed, because the key is in the repository "
                      "and only the password protects it. A sentence of four or five words is fine." % (PASSWORD_SECRET, len(password), MIN_PASSWORD))


def key(p, password):
    """Makes the signing key when it is missing; when it is there, checks that the password opens it. -> "created" or "existing"."""
    check_password(password)
    key_file = p["key"]
    shown = "%s/klippeye.p12" % KEY_FOLDER.replace(os.sep, "/")
    if os.path.isfile(key_file):
        r = keytool(["-list", "-keystore", key_file, "-storetype", "PKCS12", "-storepass:env", "KLIPPEYE_KEYSTORE_PASSWORD", "-alias", KEY_ALIAS], password)
        if r.returncode != 0:
            raise CiError("The password in the secret %s does not open the key %s. If you changed it, put the earlier one back. "
                          "If you lost it, delete %s on GitHub: a new key will be made, but the apps already installed will not be able to "
                          "update over it (uninstall and install them again, once) and the start by hand needs «new_key»." % (PASSWORD_SECRET, shown, shown))
        return "existing"
    os.makedirs(os.path.dirname(key_file), exist_ok=True)
    r = keytool([
        "-genkeypair", "-keystore", key_file, "-storetype", "PKCS12", "-alias", KEY_ALIAS,
        "-keyalg", "RSA", "-keysize", "4096", "-validity", "36500", "-dname", "CN=KlippEye, O=KlippEye",
        "-storepass:env", "KLIPPEYE_KEYSTORE_PASSWORD", "-keypass:env", "KLIPPEYE_KEYSTORE_PASSWORD",
    ], password)
    if r.returncode != 0 or not os.path.isfile(key_file):
        raise CiError("The signing key could not be made: %s" % (r.stderr.strip() or r.stdout.strip() or "unknown error"))
    return "created"


# ---------------------------------------------------------------------------------------------------- google
def google(p, content):
    """Writes google-services.json from the secret. -> True when written, False when there was none (an app without notifications)."""
    content = (content or "").strip()
    if not content:
        return False
    try:
        data = json.loads(content)
        packages = [client["client_info"]["android_client_info"]["package_name"] for client in data["client"]]
    except (ValueError, KeyError, TypeError):
        raise CiError("The secret GOOGLE_SERVICES_JSON is not a google-services.json file: paste the whole content of the file downloaded from Firebase, "
                      "from the first brace to the last.") from None
    if PACKAGE not in packages:
        raise CiError("The google-services.json in the secret GOOGLE_SERVICES_JSON belongs to another app (%s): in Firebase add an Android app called %s, "
                      "download the new google-services.json and paste its content in the secret GOOGLE_SERVICES_JSON." % (", ".join(packages) or "none", PACKAGE))
    with open(p["google"], "w", encoding="utf-8") as f:
        f.write(content + "\n")
    return True


# ---------------------------------------------------------------------------------------------------- publish
def find_tool(name, extra_folders=()):
    """aapt2 / apksigner: in the build-tools of the Android SDK (the highest version), then in the PATH."""
    candidates = list(extra_folders)
    for variable in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        root = os.environ.get(variable)
        if root and os.path.isdir(os.path.join(root, "build-tools")):
            versions = sorted(os.listdir(os.path.join(root, "build-tools")), key=lambda v: [int(x) if x.isdigit() else 0 for x in re.split(r"[.\-]", v)], reverse=True)
            candidates += [os.path.join(root, "build-tools", v) for v in versions]
    for folder in candidates:
        path = os.path.join(folder, name)
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    found = shutil.which(name)
    if found:
        return found
    raise CiError("«%s» was not found in the Android SDK of GitHub's computer." % name)


def read_apk_data(apk, aapt2):
    r = subprocess.run([aapt2, "dump", "badging", apk], capture_output=True, text=True)
    found = re.search(r"package: name='([^']*)' versionCode='(\d+)' versionName='([^']*)'", r.stdout)
    if r.returncode != 0 or not found:
        raise CiError("The built APK cannot be read (aapt2: %s)." % (r.stderr.strip()[:200] or "no answer"))
    return found.group(1), int(found.group(2)), found.group(3)


def read_signature(apk, apksigner):
    """The SHA-256 fingerprint of the certificate that signed the APK (and checks that the signature is valid)."""
    r = subprocess.run([apksigner, "verify", "--print-certs", apk], capture_output=True, text=True)
    found = re.search(r"certificate SHA-256 digest:\s*([0-9a-fA-F]{64})", r.stdout)
    if r.returncode != 0 or not found:
        raise CiError("The built APK is not signed properly (apksigner: %s)." % ((r.stderr or r.stdout).strip()[:300] or "no answer"))
    return found.group(1).lower()


def publish(p, apk, aapt2, apksigner, allow_new_signature=False, source="", now=None):
    version, code = read_version(p)
    if not os.path.isfile(apk) or os.path.getsize(apk) < 100 * 1024:
        raise CiError("The build did not produce the APK (%s)." % os.path.basename(apk))
    try:
        with zipfile.ZipFile(apk) as z:
            names = set(z.namelist())
    except zipfile.BadZipFile:
        raise CiError("The built file is not a valid APK.") from None
    if "AndroidManifest.xml" not in names or not any(n.endswith(".dex") for n in names):
        raise CiError("The built file is not a valid APK (the manifest or the code is missing).")
    package, apk_code, apk_version = read_apk_data(apk, aapt2)
    if package != PACKAGE or apk_code != code or apk_version != version:
        raise CiError("The built APK says «%s %s (%d)» but android/VERSION says «%s %s (%d)»." % (package, apk_version, apk_code, PACKAGE, version, code))
    signature = read_signature(apk, apksigner)
    previous = read_published(p) or {}
    previous_signature = previous.get("signature") or previous.get("firma")  # "firma": the name of this field up to 1.116
    if previous_signature and previous_signature != signature and not allow_new_signature:
        raise CiError("This APK is signed with a DIFFERENT key from the app published before: the phones that already have the app could not "
                      "update (Android refuses) and would have to uninstall and install it again. If that is what you want, start the workflow "
                      "by hand again and tick «new_key». Otherwise put back the key and the password of before.")
    os.makedirs(os.path.dirname(p["apk"]), exist_ok=True)
    temporary = p["apk"] + ".part"
    shutil.copyfile(apk, temporary)
    os.replace(temporary, p["apk"])
    built = (now or datetime.datetime.now(datetime.timezone.utc)).replace(microsecond=0, tzinfo=None).isoformat() + "Z"
    info = {
        "version": version,
        "code": code,
        "size": os.path.getsize(p["apk"]),
        "sha256": sha256_file(p["apk"]),
        "signature": signature,
        "built": built,
        "source": source[:12],
    }
    with open(p["info"] + ".part", "w", encoding="utf-8") as f:
        json.dump(info, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(p["info"] + ".part", p["info"])
    return info


# ---------------------------------------------------------------------------------------------------- save
def git(root, *arguments, check=True):
    r = subprocess.run(["git", "-C", root] + list(arguments), capture_output=True, text=True)
    if check and r.returncode != 0:
        raise CiError("git %s: %s" % (" ".join(arguments[:2]), (r.stderr or r.stdout).strip()[:300]))
    return r


def _copy(source, target):
    """A folder or a file from `source` to `target` (nothing when `source` is not there)."""
    if os.path.isdir(source):
        shutil.copytree(source, target)
    elif os.path.isfile(source):
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(source, target)


def _stage(root, existing):
    """Stages `existing`. -> False when nothing changed."""
    git(root, "add", "-A", "--", *existing)
    return git(root, "diff", "--cached", "--quiet", check=False).returncode != 0


def save(root, branch, message, folders, attempts=4, user=("KlippEye (GitHub Actions)", "actions@users.noreply.github.com")):
    """
    Commits `folders` (the only things the workflow changes) and pushes. When somebody pushed something else meanwhile the
    push is refused: then it starts again from GitHub's latest state and puts the same content on top (no rebase, which
    can fail on the shallow copy made by actions/checkout). -> True when something was pushed, False when there was nothing.
    """
    git(root, "config", "user.name", user[0])
    git(root, "config", "user.email", user[1])
    existing = [folder for folder in folders if os.path.exists(os.path.join(root, folder))]
    if not _stage(root, existing):
        return False
    git(root, "commit", "-q", "-m", message)
    last = ""
    for _ in range(attempts):
        r = git(root, "push", "origin", "HEAD:refs/heads/" + branch, check=False)
        if r.returncode == 0:
            return True
        last = (r.stderr or r.stdout).strip()[:300]
        # done again on top of GitHub's latest state: the files are set aside, the branch restarts from its tip, they are put back
        aside = tempfile.mkdtemp(prefix="save-")
        try:
            for folder in existing:
                _copy(os.path.join(root, folder), os.path.join(aside, folder))
            git(root, "fetch", "-q", "--depth=1", "origin", branch)
            git(root, "reset", "-q", "--hard", "FETCH_HEAD")
            for folder in existing:
                target = os.path.join(root, folder)
                if os.path.isdir(target):
                    shutil.rmtree(target)
                _copy(os.path.join(aside, folder), target)
            if not _stage(root, existing):
                return False
            git(root, "commit", "-q", "-m", message)
        finally:
            shutil.rmtree(aside, ignore_errors=True)
    raise CiError("The APK could not be saved on GitHub after %d attempts: %s" % (attempts, last))


# ---------------------------------------------------------------------------------------------------- command line
def default_root():
    return os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def truthy(text):
    return str(text).strip().lower() in ("1", "true", "yes")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.strip().split("\n")[0])
    parser.add_argument("--root", default=default_root(), help="the repository's folder")
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("decide")
    s.add_argument("--force", default="false")
    s.add_argument("--event", default=os.environ.get("GITHUB_EVENT_NAME", ""))
    sub.add_parser("key")
    sub.add_parser("google")
    s = sub.add_parser("publish")
    s.add_argument("--apk", default=None)
    s.add_argument("--new-key", default="false")
    s.add_argument("--source", default=os.environ.get("GITHUB_SHA", ""))
    s = sub.add_parser("save")
    s.add_argument("--branch", required=True)
    s.add_argument("--message", required=True)
    args = parser.parse_args(argv)
    p = paths(os.path.abspath(args.root))

    try:
        if args.command == "decide":
            outcome = decide(p, truthy(args.force), args.event, os.environ.get("KLIPPEYE_KEYSTORE_PASSWORD", ""))
            write_outputs(**outcome)
            if outcome["build"] == "false":
                level = "warning" if outcome["reason"] == MISSING_SECRET else "notice"
                print("::%s title=App not built::%s" % (level, outcome["reason"]))
        elif args.command == "key":
            outcome = key(p, os.environ.get("KLIPPEYE_KEYSTORE_PASSWORD", ""))
            print("Signing key: %s (%s/klippeye.p12)" % (outcome, KEY_FOLDER.replace(os.sep, "/")))
            write_outputs(key=outcome)
        elif args.command == "google":
            if google(p, os.environ.get("GOOGLE_SERVICES_JSON", "")):
                print("Notifications: google-services.json written, the app will have notifications.")
            else:
                print("::warning title=App without notifications::the secret GOOGLE_SERVICES_JSON is missing: the app is built anyway, without notifications (see %s)" % GUIDE)
        elif args.command == "publish":
            apk = args.apk or os.path.join(p["root"], BUILT_APK)
            info = publish(p, apk, find_tool("aapt2"), find_tool("apksigner"), truthy(args.new_key), args.source)
            print("Published apk/KlippEye.apk: version %s, %d bytes, sha256 %s" % (info["version"], info["size"], info["sha256"]))
        elif args.command == "save":
            pushed = save(p["root"], args.branch, args.message, ["apk", KEY_FOLDER])
            print("Saved on GitHub." if pushed else "Nothing changed: nothing to save.")
    except CiError as error:
        print("::error title=Android app::%s" % str(error).replace("\n", " "))
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
