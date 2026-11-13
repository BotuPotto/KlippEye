# KlippEye's local model

This folder holds the local model that comes with KlippEye: `model.onnx`, `model.json` and `CREDITS.md` (the public
datasets it was trained on, with their licences). It is made with `ml/` (see `ml/README.md`) and runs on the Raspberry
with OpenCV (`backend/local_model.py`). If the folder had no model, the monitor would work without it.

The model here (1.114.0, version `20261112-1614`): MobileNetV3-Small, 224 px, trained on Google Colab with `ml/` on
38,247 pictures from 19 public datasets (`CREDITS.md`). On the pictures kept aside: precision 0.948, recall 0.952 at
the threshold 0.30 (see `model.json`). The public photos come from other cameras; the small layer each printer learns
(Settings → AI monitor → Local model → *Learn from this printer's prints*) adapts the model to yours.

A model of your own goes in KlippEye's data folder, `model/` (for example `~/printer_data/klippeye/model/`): it is used
instead of this one. After copying it: Settings → AI monitor, or `POST /api/local_model {"reload": true}`.
