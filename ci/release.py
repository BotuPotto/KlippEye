#!/usr/bin/env python3
"""
Tags a KlippEye release once its tests passed: the tag vX.Y.Z (from VERSION) is what the "stable" update channel of
Moonraker installs, and a GitHub release with the CHANGELOG section goes with it.

Run by .github/workflows/release.yml after the "Tests" workflow (or the "App Android" one) finished on main:

    python3 ci/release.py --tested-sha SHA [--repo DIR] [--dry-run]

The commit that gets the tag is the tip of origin/main, and only when:
  * the tests passed on SHA, and between SHA and the tip only the app built by GitHub (apk/) changed: the app workflow
    commits the new APK after the merge, and that commit does not run the tests again;
  * the Android app is not waiting to be built: when android/VERSION is newer than apk/version.json the tag waits for the
    app workflow, so a release never reaches the printers without its app;
  * the tag v<VERSION> does not exist yet (a release is tagged once; the next release needs a new number in VERSION).
Otherwise it says why and ends without error.

Standard library and git only. With GITHUB_REPOSITORY and GH_TOKEN set it also creates the GitHub release.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request

RELEASE = re.compile(r"^\d{1,2}\.\d{1,2}\.\d{1,3}$")


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, check=True).stdout.strip()


def git_ok(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True).returncode == 0


def file_at(repo, sha, path):
    """The text of `path` at commit `sha`, or None."""
    r = subprocess.run(["git", "-C", repo, "show", "%s:%s" % (sha, path)], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def changelog_section(text, version):
    """The lines under "## <version>" of CHANGELOG.md, up to the next "## " heading ("" when there is none)."""
    out, inside = [], False
    for line in (text or "").splitlines():
        if line.startswith("## "):
            if inside:
                break
            inside = line[3:].strip() == version
            continue
        if inside:
            out.append(line)
    return "\n".join(out).strip()


def decide(repo, tested_sha, tip="origin/main"):
    """{"tag": bool, "reason": text, "sha", "version", "notes"}: whether and what to tag (nothing is changed here)."""
    tip_sha = git(repo, "rev-parse", tip)
    if not git_ok(repo, "cat-file", "-e", tested_sha + "^{commit}"):
        return dict(tag=False, reason="the tested commit %s is not in the repository" % tested_sha[:8])
    if not git_ok(repo, "merge-base", "--is-ancestor", tested_sha, tip_sha):
        return dict(tag=False, reason="the tested commit %s is not on main any more" % tested_sha[:8])
    changed = [p for p in git(repo, "diff", "--name-only", tested_sha, tip_sha).splitlines() if p]
    untested = [p for p in changed if not p.startswith("apk/")]
    if untested:
        return dict(tag=False, reason="main has changes newer than the tested commit (%s): their own tests will tag them" % ", ".join(untested[:5]))
    version = (file_at(repo, tip_sha, "VERSION") or "").strip()
    if not RELEASE.match(version):
        return dict(tag=False, reason="VERSION does not hold a release number (%r)" % version)
    app_version = (file_at(repo, tip_sha, "android/VERSION") or "").strip()
    if app_version:
        try:
            built = json.loads(file_at(repo, tip_sha, "apk/version.json") or "{}").get("version")
        except ValueError:
            built = None
        if built != app_version:
            return dict(tag=False, reason="the Android app %s is not built yet (apk/ has %s): the tag waits for the App Android workflow" % (app_version, built or "nothing"))
    tag = "v" + version
    if git_ok(repo, "rev-parse", "-q", "--verify", "refs/tags/" + tag):
        return dict(tag=False, reason="%s already exists (raise VERSION for a new release)" % tag)
    notes = changelog_section(file_at(repo, tip_sha, "CHANGELOG.md"), version)
    return dict(tag=True, reason="release %s: tests passed on %s" % (version, tested_sha[:8]), sha=tip_sha, version=version, notes=notes)


def create_github_release(repository, token, tag, version, notes):
    body = json.dumps({"tag_name": tag, "name": "KlippEye " + version, "body": notes or "See CHANGELOG.md.", "draft": False, "prerelease": False}).encode()
    req = urllib.request.Request("https://api.github.com/repos/%s/releases" % repository, data=body, method="POST",
                                 headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode()).get("html_url", "")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--tested-sha", required=True, help="the commit whose tests passed")
    parser.add_argument("--repo", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    parser.add_argument("--tip", default="origin/main")
    parser.add_argument("--dry-run", action="store_true", help="say what would happen, change nothing")
    args = parser.parse_args(argv)
    result = decide(args.repo, args.tested_sha, args.tip)
    if not result["tag"]:
        print("::notice title=No release tagged::" + result["reason"])
        return 0
    tag = "v" + result["version"]
    print("Tagging %s on %s (%s)" % (tag, result["sha"][:8], result["reason"]))
    if args.dry_run:
        print(result["notes"])
        return 0
    git(args.repo, "-c", "user.name=github-actions[bot]", "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com",
        "tag", "-a", tag, result["sha"], "-m", "KlippEye " + result["version"])
    git(args.repo, "push", "origin", "refs/tags/" + tag)
    repository, token = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GH_TOKEN")
    if repository and token:
        try:
            print("GitHub release: " + create_github_release(repository, token, tag, result["version"], result["notes"]))
        except Exception as error:  # noqa: BLE001 - the tag is what counts; the release page is a nicety
            print("::warning title=GitHub release not created::%s" % error)
    return 0


if __name__ == "__main__":
    sys.exit(main())
