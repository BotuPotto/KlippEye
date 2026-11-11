"""
Trains the AI monitor's local model on the pictures listed by ml/datasets.py and writes the folder the Raspberry uses
(model.onnx + model.json, see backend/local_model.py).

The network is MobileNetV3-Small (torchvision, BSD licence), started from its ImageNet weights: it already knows edges,
textures and shapes, and learns here only what a failed print looks like. It gives a score (failed / fine) and the
1024 numbers it describes a picture with (the embedding, for each printer's personal layer).

Usage (a computer with Python, or Google Colab — see ml/README.md):
    pip install -r ml/requirements.txt
    python ml/train.py --manifest ml/work/manifest.csv --out ml/out/model
Then copy ml/out/model to the Raspberry (see ml/README.md).
"""
import argparse
import csv
import json
import os
import random
import sys
import time

import numpy as np
import torch
from PIL import Image
from torch import nn
from torch.utils.data import DataLoader, Dataset, WeightedRandomSampler
from torchvision import models, transforms

MEAN, STD = [0.485, 0.456, 0.406], [0.229, 0.224, 0.225]
WANTED_PRECISION = 0.9   # the threshold: the lowest that keeps 9 alarms out of 10 right on the pictures kept aside


class Monitor(nn.Module):
    """MobileNetV3-Small: the picture -> (logit, embedding)."""

    def __init__(self, pretrained=True):
        super().__init__()
        weights = models.MobileNet_V3_Small_Weights.IMAGENET1K_V1 if pretrained else None
        net = models.mobilenet_v3_small(weights=weights)
        self.features, self.pool = net.features, net.avgpool
        self.embed = nn.Sequential(net.classifier[0], net.classifier[1])     # Linear(576, 1024) + Hardswish
        self.drop = nn.Dropout(0.3)
        self.head = nn.Linear(net.classifier[0].out_features, 1)

    def forward(self, x):
        x = torch.flatten(self.pool(self.features(x)), 1)
        embedding = self.embed(x)
        return self.head(self.drop(embedding)), embedding


class Pictures(Dataset):
    def __init__(self, rows, transform):
        self.rows, self.transform = rows, transform

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, i):
        path, label = self.rows[i]
        image = Image.open(path).convert("RGB")
        return self.transform(image), torch.tensor([float(label)])


def read_manifest(path):
    train, val = [], []
    with open(path, encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if os.path.isfile(row["path"]):
                (val if row["split"] == "val" else train).append((row["path"], int(row["label"])))
    return train, val


def scores_of(model, loader, device):
    model.eval()
    out, labels = [], []
    with torch.no_grad():
        for x, y in loader:
            logit, _ = model(x.to(device))
            out += torch.sigmoid(logit).reshape(-1).tolist()
            labels += y.reshape(-1).tolist()
    return np.array(out), np.array(labels)


def measure(scores, labels, threshold):
    predicted = scores >= threshold
    tp = int(np.sum(predicted & (labels == 1)))
    fp = int(np.sum(predicted & (labels == 0)))
    fn = int(np.sum(~predicted & (labels == 1)))
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"threshold": round(float(threshold), 3), "precision": round(precision, 3), "recall": round(recall, 3), "f1": round(f1, 3),
            "false_alarms": fp, "missed": fn}


def choose_threshold(scores, labels):
    """The lowest threshold that keeps the precision at WANTED_PRECISION (the most failures caught with few false
    alarms); if none does, the one with the best F1."""
    grid = [round(t, 2) for t in np.arange(0.3, 0.991, 0.01)]
    rows = [measure(scores, labels, t) for t in grid]
    good = [r for r in rows if r["precision"] >= WANTED_PRECISION and r["recall"] > 0]
    return min(good, key=lambda r: r["threshold"]) if good else max(rows, key=lambda r: r["f1"])


def export(model, size, out, info):
    os.makedirs(out, exist_ok=True)
    model.eval().cpu()
    dummy = torch.randn(1, 3, size, size)
    path = os.path.join(out, "model.onnx")
    # opset 13: Hardswish becomes HardSigmoid x Mul, which OpenCV's DNN module runs
    torch.onnx.export(model, dummy, path, input_names=["image"], output_names=["logit", "embedding"], opset_version=13, do_constant_folding=True,
                      dynamo=False)
    with open(os.path.join(out, "model.json"), "w", encoding="utf-8") as handle:
        json.dump(info, handle, indent=1)
    # the same answer from OpenCV as from PyTorch (what the Raspberry will run)
    try:
        import cv2
        net = cv2.dnn.readNetFromONNX(path)
        net.setInput(dummy.numpy())
        outs = net.forward(list(net.getUnconnectedOutLayersNames()))
        logit_cv = [o for o in outs if np.asarray(o).size == 1][0].reshape(-1)[0]
        with torch.no_grad():
            logit_torch = float(model(dummy)[0].reshape(-1)[0])
        print("check with OpenCV: logit %.4f (PyTorch %.4f)" % (logit_cv, logit_torch))
        if abs(logit_cv - logit_torch) > 1e-2 * max(1.0, abs(logit_torch)):
            print("WARNING: OpenCV gives another answer than PyTorch")
            return False
    except ImportError:
        print("OpenCV not installed: the model was not checked as the Raspberry will run it")
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    here = os.path.dirname(os.path.abspath(__file__))
    parser.add_argument("--manifest", default=os.path.join(here, "work", "manifest.csv"))
    parser.add_argument("--out", default=os.path.join(here, "out", "model"))
    parser.add_argument("--epochs", type=int, default=12)
    parser.add_argument("--size", type=int, default=224, help="the side of the picture the model sees (224 on a Raspberry 4)")
    parser.add_argument("--batch", type=int, default=32)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--no-pretrained", action="store_true", help="start from nothing (only for tests: much worse)")
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args(argv)
    random.seed(args.seed)
    torch.manual_seed(args.seed)
    train_rows, val_rows = read_manifest(args.manifest)
    if not train_rows or not val_rows:
        print("The manifest has no pictures for training or for measuring: run ml/datasets.py first.")
        return 1
    print("training on %d pictures (%d failed), measuring on %d (%d failed)" % (
        len(train_rows), sum(l for _, l in train_rows), len(val_rows), sum(l for _, l in val_rows)))
    train_tf = transforms.Compose([
        transforms.RandomResizedCrop(args.size, scale=(0.55, 1.0), ratio=(0.75, 1.33)),
        transforms.RandomHorizontalFlip(),
        transforms.RandomRotation(8),
        transforms.ColorJitter(0.35, 0.35, 0.3, 0.04),
        transforms.RandomGrayscale(0.05),
        transforms.ToTensor(),
        transforms.Normalize(MEAN, STD),
    ])
    val_tf = transforms.Compose([transforms.Resize((args.size, args.size)), transforms.ToTensor(), transforms.Normalize(MEAN, STD)])
    # the two kinds equally often in each batch (there are usually far more fine pictures)
    labels = [l for _, l in train_rows]
    counts = {0: labels.count(0) or 1, 1: labels.count(1) or 1}
    sampler = WeightedRandomSampler([1.0 / counts[l] for l in labels], num_samples=len(labels), replacement=True)
    train_loader = DataLoader(Pictures(train_rows, train_tf), batch_size=args.batch, sampler=sampler, num_workers=args.workers)
    val_loader = DataLoader(Pictures(val_rows, val_tf), batch_size=args.batch, num_workers=args.workers)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = Monitor(pretrained=not args.no_pretrained).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    schedule = torch.optim.lr_scheduler.OneCycleLR(optimizer, max_lr=args.lr, total_steps=max(1, args.epochs * len(train_loader)))
    loss_fn = nn.BCEWithLogitsLoss()
    best, best_state = None, None
    for epoch in range(1, args.epochs + 1):
        model.train()
        started, total = time.time(), 0.0
        for x, y in train_loader:
            optimizer.zero_grad()
            logit, _ = model(x.to(device))
            loss = loss_fn(logit, y.to(device))
            loss.backward()
            optimizer.step()
            schedule.step()
            total += float(loss) * len(x)
        scores, val_labels = scores_of(model, val_loader, device)
        chosen = choose_threshold(scores, val_labels)
        print("epoch %d/%d: loss %.4f, on the pictures kept aside %s (%.0fs)" % (epoch, args.epochs, total / len(train_rows), chosen, time.time() - started))
        key = (chosen["f1"], chosen["recall"])
        if best is None or key > (best["f1"], best["recall"]):
            best, best_state = chosen, {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
    model.load_state_dict(best_state)
    info = {"format": 1, "version": time.strftime("%Y%m%d-%H%M"), "size": args.size, "mean": MEAN, "std": STD,
            "threshold": best["threshold"], "embedding": model.head.in_features, "network": "mobilenet_v3_small",
            "trained_on": {"pictures": len(train_rows), "failed": counts[1], "fine": counts[0]}, "measured": best}
    ok = export(model, args.size, args.out, info)
    print("model written to %s: threshold %.2f, %s" % (args.out, best["threshold"], best))
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
