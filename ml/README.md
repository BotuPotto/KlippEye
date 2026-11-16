# The AI monitor's local model

*In italiano: [LEGGIMI.md](LEGGIMI.md).*

The local model is a small image model that runs on the Raspberry, without internet and at no cost, and says how likely a
picture shows a failed print (spaghetti, a part off the bed…). KlippEye already comes with one (`models/base/`): this folder
holds the tools that make it. You only need them to train a model of your own, on a computer or on Google Colab, with public
pictures and, if you like, your own; then you measure it on your prints before using it.

The network is MobileNetV3-Small (BSD licence): it starts from what it already knows about pictures (ImageNet) and learns
only what a failed print looks like. On the Raspberry it runs with OpenCV, already installed with KlippEye.

The simplest way: open [the Colab notebook](https://colab.research.google.com/github/BotuPotto/KlippEye/blob/main/ml/KlippEye_local_model.ipynb)
and run its cells from top to bottom (a free Roboflow key is all it needs).

1. Pictures of failed prints and of fine prints:
   - every public dataset of `ml/sources.json` at once: `ROBOFLOW_API_KEY=… python ml/download.py` (into `ml/data/`, with
     `CREDITS.md` listing each licence), then `python ml/datasets.py --auto ml/data …`. The classes are read by their
     names: failures that ruin a print count as failed, normal prints as fine, quality defects are left out;
   - public datasets: [Roboflow Universe](https://universe.roboflow.com), search «3D print failure», «spaghetti»; Download
     Dataset → YOLOv8 format. Check each dataset's licence (many are CC BY 4.0). For example
     [FDM Failures – Spaghetti](https://universe.roboflow.com/bu-engme500-vision-project/fdm-failures-spaghetti),
     [3D Printing Defects](https://universe.roboflow.com/3d-printing-monitoring-system-team-129-spring-2024-survm/3d-printing-defects-e2fsz),
     [3D Print Failure Detection](https://universe.roboflow.com/om-sakharkar-d0y3z/3d-print-failure-detection-pbxw5);
   - your own prints: copy KlippEye's data folder from the Raspberry (`scp -r pi@ADDRESS:~/printer_data/klippeye ./klippeye-data`):
     the labelled recordings and the answers to «How did the print go?»;
   - pictures you sorted: a folder with `ok/` and `fail/`.
   - prints going well, from many printers (1.130): `python ml/download.py --bambu` (or `--bambu-only`, no Roboflow key)
     also downloads the [Bambu Timelapse Dataset](https://huggingface.co/datasets/v2thegreat/bambu-timelapse-dataset)
     (CC BY 4.0, ~3 GB) and takes 8 pictures from each timelapse. A timelapse whose last picture the current model takes
     for a failure is left out by itself (`doubtful.txt`); name more in `ml/data/bambu-timelapses/failed.txt` after
     looking at `last-pictures/` (`python ml/contact_sheet.py ml/data/bambu-timelapses/last-pictures` puts them
     on numbered sheets). `--auto` reads them as fine prints.

   **The base model, the one shipped to everyone, is trained only on public, varied pictures**: never on one printer's.
   Each printer's own prints go to its personal layer, which KlippEye learns on the Raspberry. Collections whose licence
   does not let the model be shared (ShareAlike, NonCommercial, private) are deleted again by `download.py`.
2. The list of pictures: `pip install -r ml/requirements.txt` then
   `python ml/datasets.py --yolo ./spaghetti --klippeye ./klippeye-data --out ml/work`
   (`--fail-classes a,b` to name the failure classes of a dataset; `--empty-is-ok` when its pictures without boxes are fine prints).
   For a model that works on every printer add `--hard-cases 0.3` (look-alikes of a failure that are not failures — a
   purge line, a purge blob, a single loose strand, a brim outline — drawn on 30% of the fine pictures, and on a few failed
   ones too, so that a drawing says nothing by itself) and `--mine models/base` (the fine pictures the current model takes
   for failures weigh 3 times as much in training: its mistakes).
   Public datasets are nearly all failures: pieces of the same photos away from the boxes become the fine examples, the
   whole photo is kept only when the failure covers at least a fifth of it, and each dataset gives at most 3000 pictures
   (`--max-per-dataset`).
3. Training: `python ml/train.py --manifest ml/work/manifest.csv --out ml/out/model`. It takes minutes to an hour on a CPU,
   much less on [Google Colab](https://colab.research.google.com) with its free GPU. It writes `model.onnx` + `model.json`
   and checks that OpenCV answers as PyTorch does. The scores are calibrated (temperature scaling, put inside the model:
   a 70% is right about 7 times in 10), and the threshold is the lowest that keeps 9 alarms out of 10 right while taking
   at most 3 fine pictures in 100 for failures.
4. Measuring: `python ml/evaluate.py --model ml/out/model --data ./klippeye-data` gives, for several thresholds, the false
   alarms per hour on fine prints and the failed prints caught (and how late). It also runs on the Raspberry.

`ml/tests/test_tools.py` (no PyTorch, part of `tests/run_all.sh`) and `ml/tests/smoke_train.py` (the CI's «Local model»
job) check the chain on synthetic pictures.
