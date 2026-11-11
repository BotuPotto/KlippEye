# The AI monitor's local model

A small model that runs **on the Raspberry**, with no internet and no cost, and says how likely a picture shows a failed
print (spaghetti, a part off the bed…). You train it **once** on a computer or on Google Colab with public pictures and,
if you like, your own; then you measure it on your prints before using it.

The network is MobileNetV3-Small (BSD licence): it starts from what it already knows about pictures (ImageNet) and learns
only what a failed print looks like. On the Raspberry it runs with OpenCV, already installed with KlippEye.

1. **Pictures** — failed prints and fine prints:
   - public datasets: [Roboflow Universe](https://universe.roboflow.com), search «3D print failure», «spaghetti»; Download
     Dataset → **YOLOv8** format. Check each dataset's licence (many are CC BY 4.0). For example
     [FDM Failures – Spaghetti](https://universe.roboflow.com/bu-engme500-vision-project/fdm-failures-spaghetti),
     [3D Printing Defects](https://universe.roboflow.com/3d-printing-monitoring-system-team-129-spring-2024-survm/3d-printing-defects-e2fsz),
     [3D Print Failure Detection](https://universe.roboflow.com/om-sakharkar-d0y3z/3d-print-failure-detection-pbxw5);
   - your own prints: copy KlippEye's data folder from the Raspberry (`scp -r pi@ADDRESS:~/printer_data/klippeye ./klippeye-data`):
     the labelled recordings and the answers to «How did the print go?»;
   - pictures you sorted: a folder with `ok/` and `fail/`.
2. **The list**: `pip install -r ml/requirements.txt` then
   `python ml/datasets.py --yolo ./spaghetti --klippeye ./klippeye-data --out ml/work`
   (`--fail-classes a,b` to name the failure classes of a dataset; `--empty-is-ok` when its pictures without boxes are fine prints).
3. **Training**: `python ml/train.py --manifest ml/work/manifest.csv --out ml/out/model` — minutes to an hour on a CPU,
   much less on [Google Colab](https://colab.research.google.com) with its free GPU. It writes `model.onnx` + `model.json`
   (the threshold: the lowest that keeps at least 9 alarms out of 10 right) and checks that OpenCV answers as PyTorch does.
4. **Measuring**: `python ml/evaluate.py --model ml/out/model --data ./klippeye-data` — for several thresholds, the false
   alarms per hour on fine prints and the failed prints caught (and how late). It also runs on the Raspberry.

`ml/tests/test_tools.py` (no PyTorch, part of `tests/run_all.sh`) and `ml/tests/smoke_train.py` (the CI's «Local model»
job) check the chain on synthetic pictures.
