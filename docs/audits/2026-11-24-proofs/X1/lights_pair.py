"""Rule written twice: backend/printer_lights.py vs frontend 13-capabilities.js (deriveParts) + 16a-printer-functions.js
(detectLights, resolveLightItem, lightCommands, lightIsOn). Random printers; compares the resolved lights and on/off.
Run: python3 -I .superpowers/audit/proofs/X1/lights_pair.py"""
import json, random, re, subprocess, sys
sys.path.insert(0, "backend")
import printer_lights as pl
def src(p): return open("frontend/src/app/" + p).read()
def slice_between(t, a, b): i = t.index(a); return t[i:t.index(b, i)]
s16, s13, s16a = src("16-settings.js"), src("13-capabilities.js"), src("16a-printer-functions.js")
js = "\n".join([
 'const tx = (s) => s; const clamp=(v,a,b)=>Math.min(b,Math.max(a,v)); const ACTION_FUNCTIONS=["park","wipe","load","unload"]; const LIGHT_HEX=/^#[0-9a-f]{6}$/;',
 'const LIGHT_HOWS = ["object", "macro", "gcode"]; const LIGHT_NAME_MAX = 30; const FUNCTION_GCODE_MAX = 4000; const MACRO_NAME = /^[A-Za-z_][A-Za-z0-9_]{0,63}$/;',
 re.search(r"const isPlainObject.*\n", s16).group(0), re.search(r"const asBool.*\n", s16).group(0),
 re.search(r"const pickOne.*\n", s16).group(0), re.search(r"const cleanMacroName.*\n", s16).group(0),
 re.search(r"const cleanGcode.*\n", s16).group(0), re.search(r"const cleanObjectName.*\n", s16).group(0),
 slice_between(s16, "function cleanLightItem", "/**\n * The lights (1.37)"),
 slice_between(s13, "const LIGHT_KINDS", "/** \"bed\" or \"toolhead\""),
 slice_between(s16a, "const LIGHT_WORDS", "const lightByObject"),
 s16a[s16a.index("const lightByObject"):s16a.index("/** \"#rrggbb\" -> [r, g, b]")],
 s16a[s16a.index("/** Is the light on?"):s16a.index("/** The query of Moonraker")],
 """
const cases = JSON.parse(require('fs').readFileSync(0,'utf8'));
const out = cases.map(c => {
  const parts = deriveParts(c.configfile, c.commands, c.objects);
  const caps = { ...parts, known: true };
  const lights = c.lights.configured ? { configured: true, items: c.lights.items.map(cleanLightItem) } : { configured: false, items: [] };
  const fn = resolveFunctions({ park:{mode:"off"}, wipe:{mode:"off"}, load:{mode:"off"}, unload:{mode:"off"}, lights }, caps);
  return { outputs: parts.lights.map(l => ({object:l.object, kind:l.kind, name:l.name, effects:l.effects})), macros: parts.macros,
    lights: fn.lights.map(l => ({id:l.id, name:l.name, on:l.on, off:l.off, object: l.object ? l.object.object : null,
      state: l.object ? lightIsOn(c.status, l.object) : null })) };
});
console.log(JSON.stringify(out));
"""])
random.seed(7)
NAMES = ["LUCI", "case_light", "buzzer", "chamber_led", "lamp", "stealthburner", "Case", "fan_pin", "LED", "strip-1"]
def mk():
    objs = []
    for _ in range(random.randint(0, 5)):
        objs.append(random.choice(["neopixel", "output_pin", "led", "dotstar", "pca9533", "pca9632", "heater_fan"]) + " " + random.choice(NAMES))
    objs = sorted(set(objs))
    effs = []
    cfg = {}
    for i in range(random.randint(0, 2)):
        e = "led_effect fx%d" % i; effs.append(e)
        tgt = random.choice(objs).replace(" ", ":") if objs else "neopixel:X"
        cfg[e] = {"leds": random.choice([tgt, tgt + " (1-5)", tgt.upper(), "neopixel:LUCI, " + tgt])}
    objects = objs + effs + ["extruder"]
    macros = random.sample(["LUCI_ON", "LUCI_OFF", "LIGHTS_ON", "LIGHTS_OFF", "KLIPPEYE_LIGHT_ON", "KLIPPEYE_LIGHT_OFF", "CASE_LIGHT_ON", "CASE_LIGHT_OFF", "PARK", "STARTON", "STARTOFF", "LAMPON", "LAMPOFF", "_HIDDEN"], random.randint(0, 8))
    settings = {"gcode_macro " + m.lower(): {} for m in macros}
    settings["printer"] = {}
    for o in objs:
        settings[o.lower()] = {"pwm": random.choice([True, "true", False]), "color_order": random.choice(["GRB", "GRBW", "RGB"])}
    cmds = {"STOP_LED_EFFECTS": ""} if random.random() < 0.6 else {}
    lights = {"configured": False}
    if random.random() < 0.5:
        items = []
        for k in range(random.randint(0, 3)):
            mode = random.choice(["object", "macro", "gcode"])
            it = {"id": "i%d" % k, "name": random.choice(["", "Strip", "x" * 40]), "mode": mode, "main": True,
                  "object": random.choice(objs) if objs and random.random() < .8 else "neopixel Missing",
                  "onMacro": random.choice(["LUCI_ON", "LIGHTS_ON", "NOPE_ON", ""]), "offMacro": random.choice(["LUCI_OFF", "LIGHTS_OFF", ""]),
                  "onGcode": random.choice(["M106", " ", "SET_PIN PIN=a VALUE=1"]), "offGcode": random.choice(["M107", "", "SET_PIN PIN=a VALUE=0"]),
                  "stateFrom": random.choice(["auto", "", random.choice(objs) if objs else "auto"])}
            items.append(it)
        lights = {"configured": True, "items": items}
    status = {}
    for o in objs + effs:
        if o.startswith("output_pin"): status[o] = {"value": random.choice([0, 0.5, 1])}
        elif o.startswith("led_effect"): status[o] = {"enabled": random.random() < .3}
        else: status[o] = {"color_data": [[random.choice([0, 0, 1])] * 4]}
    return {"objects": objects, "configfile": {"settings": settings, "config": cfg}, "commands": cmds, "lights": lights, "status": status}
cases = [mk() for _ in range(1500)]
r = subprocess.run(["node", "-e", js], input=json.dumps(cases), capture_output=True, text=True)
if r.returncode: print(r.stderr[:1500]); sys.exit(1)
out = json.loads(r.stdout)
bad = other = 0
for c, j in zip(cases, out):
    outputs = pl.outputs_from(c["objects"], c["configfile"])
    macros = pl.macros_from(c["configfile"])
    py = pl.resolve(c["lights"], outputs, macros, c["commands"])
    pyl = [{"id": l["id"], "name": l["name"], "on": l["on"], "off": l["off"], "object": l["object"]["object"] if l["object"] else None,
            "state": pl.is_on(c["status"], l) if l["object"] else None} for l in py]
    pyo = [{"object": o["object"], "kind": o["kind"], "name": o["name"], "effects": o["effects"]} for o in outputs]
    why = None
    if pyo != j["outputs"]: why = "outputs"
    elif macros != j["macros"]: why = "macros"
    elif pyl != j["lights"]: why = "lights"
    if why and not any(o.startswith('pca') for o in c['objects']):
        other += 1
        print('NON-PCA DIFF', why)
    if why:
        bad += 1
        if bad <= 2: print("DIFF", why, json.dumps(c["lights"])[:300], "\n  py", json.dumps(pyl)[:400], "\n  js", json.dumps(j["lights"])[:400])
print(len(cases), "random printers,", bad, "differ,", other, "of them without a pca9533/pca9632 output")
