"""For the e2e test of the installer (scenario "deps"): makes the Python modules in KLIPPEYE_TEST_HIDE ("cv2 numpy")
look not installed, until the fake apt-get "installs" their Debian package (FAKE_SYSTEMD_STATE/apt_installed)."""
import os
import sys

PACKAGE = {"cv2": "python3-opencv", "numpy": "python3-numpy", "flask": "python3-flask", "requests": "python3-requests"}
hidden = set(os.environ.get("KLIPPEYE_TEST_HIDE", "").split())
try:
    with open(os.path.join(os.environ.get("FAKE_SYSTEMD_STATE", ""), "apt_installed")) as handle:
        installed = set(handle.read().split())
except OSError:
    installed = set()
hidden = {name for name in hidden if PACKAGE.get(name) not in installed}


class _Hide:
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in hidden:
            raise ImportError("hidden by the test: " + name)
        return None


if hidden:
    sys.meta_path.insert(0, _Hide())
