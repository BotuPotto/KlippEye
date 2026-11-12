# KlippEye's local model

The folder of the base local model that comes with KlippEye: `model.onnx`, `model.json` and `CREDITS.md` (the public
datasets it was trained on, with their licences). It is made with `ml/` (see `ml/README.md`) and runs on the Raspberry
with OpenCV (`backend/local_model.py`). While this folder has no model, the monitor works without one.

A model of your own goes in KlippEye's data folder, `model/` (for example `~/printer_data/klippeye/model/`): it is used
instead of this one. After copying it: Settings → AI monitor, or `POST /api/local_model {"reload": true}`.
