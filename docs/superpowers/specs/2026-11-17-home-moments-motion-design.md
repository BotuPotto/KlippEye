# Home by moment and motion (1.134.0)

## Intent

The owner likes KlippEye's current look but worried people would find it dull or clumsy over time. What they liked
in another phone app: it changes with the moment and shows only what can help then. They also wanted motion like the
Mac's. Three full redesigns were shown as demos and turned down; the current style stays.

## Decisions (the owner's)

- Home changes with the moment of the print. The order and the hidden cards of Settings → Appearance → Cards stay the
  person's: a moment only leaves cards out. An alarm always puts the camera first.
- Motion: the «Mac» combination of the motion demo, without the view of all pages at once. A spring with a barely
  visible bounce; cards slide to their new places; dialogs grow from the tapped point; pages come in from the side of
  the tab; the AI badge hops on an alarm; the camera can go into a small window ("genie" motion).

## Approaches considered for the card order

1. Moments filter, the order stays the person's (chosen: smallest, keeps existing settings).
2. Each moment has a fixed layout (the Cards page would lose its meaning on a phone).
3. A layout per moment in the Cards page (six layouts for three kinds of device: too much to set).

## What 1.134.0 builds (the builder's calls)

- Only the cards Home already has. Heating: print, camera, heaters, temperatures, multi-material. Printing and alarm:
  the same plus movement (the Z-offset). Idle and paused: everything, as before.
- «Finished» is not a moment yet: Klipper keeps `complete` for hours, so hiding cards there would hide them until the
  next print.
- Heating is told by the print being under 1% with a heater more than 3 °C below its target.
- The spring is a CSS `linear()` curve with the old curve as fallback. Cards that leave just go; the ones that stay
  slide; new ones rise as before. A demo with fading copies of the leaving cards flickered.
- Phone only. The computer's Home is unchanged.

## Left for later

New Home cards from the approved table (next in queue, recent files, filament load/unload and park in a pause,
speed/flow on Home); the computer's Home (cards set aside go to the side column); the «finished» moment.
