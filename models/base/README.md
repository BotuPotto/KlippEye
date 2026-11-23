# KlippEye's local model

This folder holds the local model that comes with KlippEye: `model.onnx`, `model.json` and `CREDITS.md` (the public
datasets it was trained on, with their licences). It is made with `ml/` (see `ml/README.md`) and runs on the Raspberry
with OpenCV (`backend/local_model.py`). If the folder had no model, the monitor would work without it.

The model here (1.135.0, version `20261118-2036`): MobileNetV3-Small, 224 px, trained on Kaggle with `ml/` on 40,400
pictures (`CREDITS.md`): 20 Roboflow collections, 344 Bambu timelapses of prints going well plus the last picture of the
43 that failed (`bambu-failed.txt`), look-alikes of a failure drawn on fine pictures (purge lines, blobs, single strands,
brims: `ml/hard_cases.py`), and 10 judged prints of one printer (a VzBot with a close fisheye camera, the bed area).
Its scores are calibrated (a 70% is right about 7 times in 10); on the pictures kept aside, at the threshold 0.90:
precision 0.976, recall 0.763, 2.8% of fine pictures taken for failures. Its own levels (`model.json` → `levels`): in
doubt from 80%, sure from 90%, used while the settings are the defaults.

Measured on 9 prints of that printer it never saw (4 failed, 5 fine, 2.5 hours, `ml/evaluate.py`, the bed area):

| | model 20261116-1408 (before) | this model |
|---|---|---|
| the local model's own asks («monitor») | 10.5 false an hour, 3 of 4 failures | 0 false, 1 of 4 |
| with the motion triggers recorded live («+ motion») | 4.8 false an hour, 2 of 4 | 0 false, 2 of 4 |

On the fine prints its highest score fell from 0.89–0.94 to 0.04–0.49 (one print under orange light still reaches
0.94). It catches failures later and fewer of them by itself; with motion detection and the online AI it caught as
many. This is one printer and few prints: it is a trial, and `git log models/base` gives the previous model back.
The small layer each printer learns (Settings → AI monitor → Local model → *Learn from this printer's prints*) adapts
the model to each camera.

A model of your own goes in KlippEye's data folder, `model/` (for example `~/printer_data/klippeye/model/`): it is used
instead of this one. After copying it: Settings → AI monitor, or `POST /api/local_model {"reload": true}`.
