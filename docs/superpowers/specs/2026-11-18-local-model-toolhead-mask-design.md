# Local model: hide the toolhead from its views (design)

## Why

With a close camera (the owner's VzBot: fisheye on the frame, toolhead large in the picture) the local model gives
false «sure» looks from the first layers on. The views that contain the toolhead score 70–85%: «bed» (the bed and the
space above it up to the nozzle) and «part» (a square around the expected part, where the nozzle is while it prints).
The «change» view, where the motion detection's machine masks already leave the toolhead out, scores low and matches
the real state. A black picture scores fine and any lit one does not: the toolhead, its braided cable sleeve and tubes
look like tangles to a model trained on public pictures taken from farther away. With only the local model, three
«sure» looks propose a pause, so the owner gets many false alarms.

## Goal, non-goals, anti-goals

- Goal: the local model never sees the toolhead and the gantry in the «bed» and «part» views when the camera is
  calibrated, so false «sure» looks caused by the machine go away.
- Non-goals: changing the thresholds, the rules of `_local_look`, the online AI, the motion detection.
- Anti-goals: losing real failures (a blob or spaghetti next to the nozzle that only the model sees); slowing the Pi;
  anything that assumes the owner's printer (it must work for every calibrated camera).

## Constraints

- Calibrated camera only (`camera_cal.monitor_mask`); without it the views stay as today.
- Lightness: one extra mask and fill per look (every `local_every` s, not every check), OpenCV 4.6 on a 32-bit Pi.
- The base model is about to be retrained on Colab (branch `paste-failures`). The mask is applied at run time and does
  not depend on the model: it must be measured with the current base model and again with the new one.
- Changing what the model sees changes the embeddings: the false-alarm memory and the personal layer must notice it.

## Approaches (chosen: A)

- **A. Cover the toolhead in the model's views** (chosen by the owner). The machine mask at the positions read around the
  snapshot, filled before cropping, like the purge cover (`_without_purge`). Fixes the cause; helps every close camera.
  Risk: a failure right at the nozzle is hidden in those two views; the «change» view still sees it.
- B. Let «bed»/«part» count as «sure» only when «change» is at least «in doubt». Little code, but loses slow failures the
  motion detection misses.
- C. Retrain (personal layer on all views, or close toolhead pictures in the base model). Longest; the personal layer
  helps only one printer.

## Design

1. In `local_judge`, after `_without_purge`, cover the machine mask (`camera_cal.monitor_mask` with `meta["live"]`,
   `meta["live2"]`, at the frame's size, slightly dilated) for the «bed» and «part» views; «change» unchanged (it is a
   crop the motion detection already found outside the masks).
2. Fill: `cv2.inpaint` on a reduced picture (builder's call, Claude's proposal: cheap, no colour background to keep,
   no risk of pasting an old toolhead). If the measurement shows the fill itself raises the score, try a flat fill with
   the bed's median colour instead.
3. The false-alarm memory's key (`memory_version`) gains a mark for «toolhead covered», so it is rebuilt once (one-time
   loss of the remembered false alarms). The personal layer keeps its signature: its examples carry no positions to
   cover them, so a new signature would retrain it on the same uncovered pictures (shortcut, noted in the code).
4. Measure first, ship only if better: on the owner's judged recordings, scores of the views with and without the mask,
   with `models/base` now and with the retrained model when it exists; `ml/evaluate.py` «monitor» row. Ship only if the
   false asks on fine prints go down and the caught failures do not. The recordings need the toolhead positions per
   frame to rebuild the mask: if they do not have them, add them to `recorder.py` and measure on new recordings.
5. One test that fails without the change (a synthetic frame with a «toolhead» that the model stub scores high, fine once
   covered); VERSION, CHANGELOG, 9 translations only if a text changes, the guide's note on the local model.

## Left to the builder

The mask's dilation, the reduced size for inpainting, where exactly the shared helper lives (next to
`purge_marks.cover` is the natural place).
