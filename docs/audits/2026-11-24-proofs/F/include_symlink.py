"""Proof: printer.cfg kept as a link into a config repository is replaced by a plain file when KlippEye adds its
include (atomic.write_text does os.replace on the link itself)."""
import os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../../backend"))
import printer_macros
root = tempfile.mkdtemp(); repo = os.path.join(root, "my-config"); cfg = os.path.join(root, "config"); os.makedirs(repo); os.makedirs(cfg)
open(os.path.join(repo, "printer.cfg"), "w").write("[printer]\nkinematics: corexy\n")
os.symlink(os.path.join(repo, "printer.cfg"), os.path.join(cfg, "printer.cfg"))
store = printer_macros.PrinterMacros(tempfile.mkdtemp(), lambda: cfg, commands=lambda: [])
store.set_macro("KLIPPEYE_PARK", printer_macros.template("park")[1])
print("printer.cfg still a link:", os.path.islink(os.path.join(cfg, "printer.cfg")))
print("the repository's printer.cfg has the include:", "klippeye_macros" in open(os.path.join(repo, "printer.cfg")).read())
