# KlippEye's local model

This folder holds the local model that comes with KlippEye: `model.onnx`, `model.json` and `CREDITS.md` (the public
datasets it was trained on, with their licences). It is made with `ml/` (see `ml/README.md`) and runs on the Raspberry
with OpenCV (`backend/local_model.py`). If the folder had no model, the monitor would work without it.

The model here (1.130.0, version `20261116-1408`): MobileNetV3-Small, 224 px, trained on Google Colab with `ml/` on
46,656 pictures, public only (`CREDITS.md`): 20 Roboflow collections, 344 Bambu timelapses of prints going well (the 43
that failed were looked at and left out: `bambu-failed.txt`), and 4,403 look-alikes of a failure drawn on fine pictures
(purge lines, blobs, single strands, brims: `ml/hard_cases.py`). Its scores are calibrated (a 70% is right about 7 times
in 10); on the pictures kept aside, at the threshold 0.86: precision 0.978, recall 0.826, 2.8% of fine pictures taken for
failures. Its own levels (`model.json` → `levels`): in doubt from 75%, sure from 86%, used while the settings are the
defaults.

Measured on prints it never saw (14 judged prints of one printer with a close fisheye camera, the bed area): 1.5 false
alarms an hour on the prints that went well (the previous model: 38), 3 of the 4 failed prints with pictures after the
failure caught. The small layer each printer learns (Settings → AI monitor → Local model → *Learn from this printer's
prints*) adapts the model to each camera.

A model of your own goes in KlippEye's data folder, `model/` (for example `~/printer_data/klippeye/model/`): it is used
instead of this one. After copying it: Settings → AI monitor, or `POST /api/local_model {"reload": true}`.
