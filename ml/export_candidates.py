"""The networks that could replace the local model's MobileNetV3-Small, exported to ONNX only to time them on a Raspberry
(scripts/benchmark.py --models). Their weights are random: how fast a network runs does not depend on what it learnt, and
nothing has to be downloaded to make them. Never use these files as a model.

    pip install torch torchvision timm onnx opencv-python-headless
    python ml/export_candidates.py --out ml/out/candidates

Each file is written as <name>.onnx, with the same input as the local model (1 x 3 x 224 x 224, RGB, normalised) and two
outputs like it: the score (one number) and the picture's description (the pooled features). Each one is then run once
with OpenCV, as on the Raspberry: a network OpenCV cannot run is left out and said so.
"""
import argparse
import json
import os
import sys

# name -> (where it comes from, the model's name there). MobileNetV3-Small is the network used now: the reference.
CANDIDATES = {
    "mobilenetv3_small": ("torchvision", "mobilenet_v3_small"),
    "mobilenetv4_conv_small": ("timm", "mobilenetv4_conv_small"),
    "efficientnet_lite0": ("timm", "efficientnet_lite0"),
}
SIZE = 224


def build(source, name):
    import torch

    if source == "torchvision":
        import torchvision

        net = getattr(torchvision.models, name)(weights=None)   # as ml/train.py: pooled features, then Linear(576, 1024) + Hardswish
        features = torch.nn.Sequential(net.features, net.avgpool, torch.nn.Flatten(), net.classifier[0], net.classifier[1])
    else:
        import timm

        features = timm.create_model(name, pretrained=False, num_classes=0)   # num_classes=0: the pooled features
    with torch.no_grad():   # the width as it comes out (some networks add a last layer after the one they announce)
        width = int(features.eval()(torch.zeros(1, 3, SIZE, SIZE)).shape[-1])

    class Scored(torch.nn.Module):   # the local model's two outputs: score and description
        def __init__(self):
            super().__init__()
            self.features = features
            self.head = torch.nn.Linear(width, 1)

        def forward(self, x):
            embedding = self.features(x)
            return self.head(embedding), embedding

    return Scored().eval()


def export(name, out):
    import torch

    source, model_name = CANDIDATES[name]
    model = build(source, model_name)
    path = os.path.join(out, name + ".onnx")
    with torch.no_grad():
        torch.onnx.export(model, torch.zeros(1, 3, SIZE, SIZE), path, input_names=["picture"], output_names=["logit", "embedding"],
                          opset_version=13, dynamo=False)
    return path


def runs_in_opencv(path):
    """None when OpenCV runs the file, else why not."""
    import cv2
    import numpy as np

    try:
        net = cv2.dnn.readNetFromONNX(path)
        net.setInput(np.zeros((1, 3, SIZE, SIZE), np.float32))
        outs = net.forward(net.getUnconnectedOutLayersNames())
        if not any(np.asarray(o).size == 1 for o in outs):
            return "no score among the outputs"
        return None
    except Exception as error:  # noqa: BLE001 - OpenCV's own errors
        return str(error).splitlines()[0][:200]


def main(argv=None):
    parser = argparse.ArgumentParser(description="Export the candidate networks to ONNX (random weights: for timing only).")
    parser.add_argument("--out", default="ml/out/candidates")
    parser.add_argument("--only", default="", help="comma-separated names (default: all)")
    args = parser.parse_args(argv)
    os.makedirs(args.out, exist_ok=True)
    names = [n for n in args.only.split(",") if n] or list(CANDIDATES)
    written = {}
    for name in names:
        path = export(name, args.out)
        problem = runs_in_opencv(path)
        if problem:
            os.remove(path)
            print("%-24s left out: OpenCV cannot run it (%s)" % (name, problem))
            continue
        written[name] = {"file": os.path.basename(path), "bytes": os.path.getsize(path), "source": CANDIDATES[name][0]}
        print("%-24s %6.1f MB" % (name, written[name]["bytes"] / 1048576))
    with open(os.path.join(args.out, "candidates.json"), "w", encoding="utf-8") as handle:
        json.dump({"size": SIZE, "random_weights": True, "models": written}, handle, indent=1)
    return 0 if written else 1


if __name__ == "__main__":
    sys.exit(main())
