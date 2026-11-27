"""Scenario tests for the CQpid app (Playwright, WebKit and Chromium).

    python app/tests/test_scenarios.py

Complements test_app.py (one full walk-through) with many small scenarios inside the app's scope:
empty and minimal layouts, sizes up to a gene that no longer fits a plate, fill options, edits after
Fill, sample generation and numbering, save/open round trips, hand-written and broken files, undo/redo,
touch-up, print, narrow windows and dialogs. After every step it checks invariants: no JS error, valid
state, no "undefined"/"NaN" on screen, one frame per cDNA block, no sideways page scroll.
"""
import json, pathlib, sys
from playwright.sync_api import sync_playwright

APP = (pathlib.Path(__file__).resolve().parents[1] / "cqpid.html").as_uri()
FAILS = []


def check(cond, msg):
    if not cond:
        FAILS.append(msg)
        print("  FAIL:", msg)


class App:
    def __init__(self, browser, width=1500, scheme="light"):
        self.page = browser.new_page(viewport={"width": width, "height": 1000}, color_scheme=scheme)
        self.errors = []
        self.page.on("pageerror", lambda e: self.errors.append(str(e)))
        self.page.on("console", lambda m: self.errors.append(m.text) if m.type == "error" else None)
        self.answer = None   # next prompt() answer; None = accept default
        self.page.on("dialog", self._dialog)
        self.page.goto(APP)
        self.page.evaluate("() => { window.print = () => { window.__printed = (window.__printed || 0) + 1; }; }")

    def _dialog(self, d):
        if d.type == "prompt" and self.answer is not None:
            d.accept(self.answer); self.answer = None
        else:
            d.accept()

    def js(self, code, arg=None):
        return self.page.evaluate(code, arg) if arg is not None else self.page.evaluate(code)

    def state(self):
        return self.js("JSON.parse(JSON.stringify(state))")

    def toast(self):
        return self.js("$('toast').textContent")

    def setup(self, targets, samples, vars=None):
        """samples: list of ids or (id, {var: value}) pairs."""
        ss = [s if isinstance(s, (list, tuple)) else (s, {}) for s in samples]
        self.js("""([t, s, v]) => { state.targets = t; state.vars = v; state.levels = {};
            state.samples = s.map(([id, vv]) => ({id, v: vv})); renderAll(); }""", [targets, ss, vars or []])

    def fill(self, reps="0", ntc="1", pool=""):
        self.page.select_option("#fillReps", reps)
        self.page.fill("#fillNTC", str(ntc)); self.page.dispatch_event("#fillNTC", "input")
        self.page.select_option("#fillPool", pool)
        self.page.click("#btnFill")

    def inv(self, label):
        r = self.js("""() => {
          const out = {};
          try { renderAll(); } catch (e) { out.render = String(e); }
          out.json = JSON.stringify(state).length > 0;
          out.badWells = state.plates.flatMap((p) => Object.keys(p.wells)).filter((id) => !/^[A-H](0[1-9]|1[0-2])$/.test(id));
          const txt = ["left", "center", "right"].map((id) => $(id).innerText).join("\\n");
          out.junk = /\\bundefined\\b|\\bNaN\\b|\\[object/.test(txt);
          out.frames = document.querySelectorAll("#plate .cf").length;
          out.blocks = state.plates.length ? cdnaBlocks(plate()).length : 0;
          out.emptyLabels = [...document.querySelectorAll("#plate .cf .lab")].filter((l) => !l.textContent.trim()).length;
          out.scroll = document.documentElement.scrollWidth - window.innerWidth;
          return out; }""")
        check(not self.errors, f"{label}: JS errors {self.errors[:3]}")
        self.errors.clear()
        check("render" not in r, f"{label}: renderAll threw {r.get('render')}")
        check(not r["badWells"], f"{label}: invalid well ids {r['badWells'][:5]}")
        check(not r["junk"], f"{label}: 'undefined'/'NaN' shown on the page")
        check(r["frames"] == r["blocks"], f"{label}: {r['frames']} frames for {r['blocks']} cDNA blocks")
        check(r["emptyLabels"] == 0, f"{label}: empty cDNA labels")
        check(r["scroll"] <= 1, f"{label}: page scrolls sideways by {r['scroll']} px")

    def close(self):
        self.page.close()


def layout_invariants(app, label, reps=None):
    """Every sample x target has the same replicate count on one plate; controls per gene; no duplicates."""
    s = app.state()
    ws = [(p["id"], wid, w) for p in s["plates"] for wid, w in p["wells"].items()]
    pairs = {}
    for pid, wid, w in ws:
        if w["role"] == "sample":
            pairs.setdefault((w["sample"], w["target"]), []).append(pid)
    counts = {len(v) for v in pairs.values()}
    check(len(counts) <= 1, f"{label}: replicate counts differ {counts}")
    if reps:
        check(counts <= {reps}, f"{label}: expected {reps} reps, got {counts}")
    for (smp, t), pids in pairs.items():
        check(len(set(pids)) == 1, f"{label}: {smp}/{t} spread over plates {set(pids)}")
    return s, pairs


def scenario(name):
    def deco(fn):
        fn.scenario = name
        return fn
    return deco


@scenario("empty app: every button")
def s_empty(b):
    a = App(b)
    a.page.click("#btnFill"); check("No samples yet" in a.toast(), f"fill on empty: {a.toast()}")
    a.page.click("#btnGenSamples"); a.page.click("#btnFill"); check("No targets yet" in a.toast(), f"fill without targets: {a.toast()}")
    check("No targets yet" in a.page.inner_text("#fillInfo"), "fill info names the missing targets")
    a.js("state.targets = ['gapdh']; renderAll(); document.querySelectorAll('#fillSamples input').forEach(i => i.checked = false); fillInfo()")
    a.page.click("#btnFill"); check("No samples ticked" in a.toast(), f"none ticked: {a.toast()}")
    a.js("state = emptyState(); renderAll()")
    a.page.click("#btnSave"); check("empty" in a.toast(), "save on empty: toast")
    a.page.click("#btnPrint"); check("Nothing to print" in a.toast(), "print on empty: toast")
    a.page.click("#btnUndo"); a.page.click("#btnRedo")
    a.page.click("#btnHelp"); a.page.keyboard.press("Escape")
    a.page.click("#btnNew")
    a.page.click("#btnGenSamples")
    a.page.click("#inspApply"); a.page.click("#inspClear")
    a.page.click("#sampleTable button.icon")   # numbering with no samples
    a.inv("empty"); a.close()


@scenario("one target, one sample")
def s_minimal(b):
    a = App(b)
    a.setup(["gapdh"], ["S1"])
    a.fill()
    s = a.state()
    check(len(s["plates"]) == 1, "minimal: one plate")
    roles = sorted(w["role"] for w in s["plates"][0]["wells"].values())
    check(roles == ["NTC", "noRT", "sample", "sample", "sample"], f"minimal: wells {roles}")
    m = a.js("mixPlan(plate())")
    check(m["genes"][0]["n"] == 6 and m["nb"] == 10 and m["luna"] == 50, f"minimal: mix {m['genes'][0]['n']}, {m['nb']}")
    a.inv("minimal"); a.close()


@scenario("sizes: 1-14 genes, 1-100 samples")
def s_sizes(b):
    a = App(b)
    for ng in [1, 2, 4, 5, 12, 14]:
        for ns in [1, 7, 15, 24, 36, 46, 47, 48, 60, 100]:
            a.setup([f"g{i}" for i in range(ng)], [f"S{i}" for i in range(ns)])
            a.fill()
            label = f"{ng} genes x {ns} samples"
            s, pairs = layout_invariants(a, label) if ns <= 47 else (a.state(), None)
            if ns <= 47:
                check(len(pairs) == ng * ns, f"{label}: {len(pairs)} sample/target pairs placed")
            total = sum(len(p["wells"]) for p in s["plates"])
            check(total == a.js("allWells().length"), f"{label}: well count")
            if ns > 47:
                check("split across plates" in a.page.inner_text("#checks"), f"{label}: split warning")
            a.inv(label)
    a.close()


@scenario("fill options: replicates, NTC, noRT pools")
def s_options(b):
    a = App(b)
    smp = [(f"S{i}", {"t": ["0", "12", "24"][i % 3], "BR": str(i % 3 + 1)}) for i in range(12)]
    a.setup(["gapdh", "actb", "geneA"], smp, ["t", "BR"])
    for reps in ["2", "3"]:
        a.fill(reps=reps); layout_invariants(a, f"reps {reps}", int(reps)); a.inv(f"reps {reps}")
    for ntc in ["0", "2", "1.5", "-3", ""]:
        a.fill(ntc=ntc)
        n = sum(1 for p in a.state()["plates"] for w in p["wells"].values() if w["role"] == "NTC" and w["target"] == "gapdh")
        exp = {"0": 0, "2": 2, "1.5": 1, "-3": 0, "": 0}[ntc]
        check(n == exp, f"NTC {ntc!r}: {n} NTC wells per gene, expected {exp}")
        a.inv(f"ntc {ntc}")
    a.fill(pool="t")
    pools = sorted({w["sample"] for p in a.state()["plates"] for w in p["wells"].values() if w["role"] == "noRT"})
    check(pools == ["noRT_0", "noRT_12", "noRT_24"], f"pool by t: {pools}")
    a.inv("pool by t"); a.close()


@scenario("edits after Fill: targets, samples, variables")
def s_edits(b):
    a = App(b)
    a.setup(["gapdh", "actb"], [("S1", {"BR": "1"}), ("S2", {"BR": "2"})], ["BR"])
    a.fill()
    # rename target via the dialog
    a.page.locator("#targetList .item", has_text="gapdh").locator("button[title*='Rename']").click() if a.page.locator("#targetList .item button[title*='Rename']").count() else a.js("editTarget(0)")
    a.page.fill("#modal input >> nth=0", "GAPDH"); a.page.click("#modal button.primary")
    check(a.js("allWells().some(w => w.target === 'GAPDH') && !allWells().some(w => w.target === 'gapdh')"), "rename target: wells follow")
    a.inv("rename target")
    # rename to an existing name is refused
    a.js("editTarget(0)"); a.page.fill("#modal input >> nth=0", "actb"); a.page.click("#modal button.primary")
    check("taken" in a.toast(), "rename to existing target refused")
    a.page.keyboard.press("Escape"); a.inv("rename clash")
    # delete target: wells lose their target, checks warn
    a.js("editTarget(1)"); a.page.click("#modal button >> text=Delete")
    check("Wells without a target" in a.page.inner_text("#checks"), "delete target: checks warn")
    a.inv("delete target")
    # rename sample, then delete it
    a.answer = "S9"; a.js("renameSample(0)")
    check(a.js("allWells().some(w => w.sample === 'S9')"), "rename sample: wells follow")
    a.answer = "S2"; a.js("renameSample(0)"); check("exists" in a.toast(), "rename to existing sample refused")
    a.answer = "a,b"; a.js("renameSample(0)"); check("comma" in a.toast(), "comma in sample id refused")
    a.js("deleteSample(0)")
    check(not a.js("allWells().some(w => w.sample === 'S9')"), "delete sample: wells removed")
    a.inv("delete sample")
    # variables: reserved names refused, rename/move/remove
    for bad in ["primer", "dilution", "plate", "target", "BR"]:
        a.js(f"addVar({bad!r})")
        check(a.js("state.vars.filter(v => v === %r).length" % bad) <= 1 and bad not in ["primer", "dilution", "plate", "target"] or bad not in a.js("state.vars"), f"variable {bad!r} refused")
    a.js("addVar('time')"); a.js("renameVar(state.vars.indexOf('time'), 'day')")
    check("day" in a.js("state.vars") and "time" not in a.js("state.vars"), "rename variable")
    a.js("renameVar(state.vars.indexOf('day'), 'primer')"); check("day" in a.js("state.vars"), "rename to reserved refused")
    a.js("moveVar(0, 1)"); a.js("moveVar(0, -1)"); a.js("moveVar(5, 1)")
    a.js("removeVar(state.vars.indexOf('day'))"); check("day" not in a.js("state.vars"), "remove variable")
    a.inv("variables"); a.close()


@scenario("generate and number samples")
def s_generate(b):
    a = App(b)
    a.js("state.levels.BR = ''; renderAll()")
    check(a.js("genCount()") is None or "0" in a.page.inner_text("#btnGenSamples") or a.js("genCombos().length") == 0, "no levels: nothing to generate")
    a.page.click("#btnGenSamples"); check(a.js("state.samples.length") == 0, "generate with no levels adds nothing")
    a.js("addVar('trt'); state.levels.trt = ' a,, b , '; state.levels.BR = '1,2'; renderAll()")
    check(a.js("genCombos().length") == 4, f"messy levels: {a.js('genCombos().length')} combos")
    a.page.click("#btnGenSamples"); a.page.click("#btnGenSamples")
    ids = [s["id"] for s in a.state()["samples"]]
    check(ids == ["a-1", "a-2", "b-1", "b-2"], f"generate twice: same list, no duplicates {ids}")
    a.inv("generate")
    # removing a level removes its samples (and their wells); matching samples keep their (renamed) IDs
    a.js("state.samples[0].id = 'x1'; state.targets = ['gapdh']; renderAll()"); a.fill()
    check(a.js("allWellObjs().some(w => w.sample === 'b-1')"), "b-1 on the plate")
    a.js("state.levels.trt = 'a'; renderAll()"); a.page.click("#btnGenSamples")
    check([s["id"] for s in a.state()["samples"]] == ["x1", "a-2"], f"level removed: {[s['id'] for s in a.state()['samples']]}")
    check(not a.js("allWellObjs().some(w => w.sample === 'b-1' || w.sample === 'b-2')"), "wells of removed samples cleared")
    a.js("undo()"); check(len(a.state()["samples"]) == 4 and a.js("allWellObjs().some(w => w.sample === 'b-1')"), "undo restores them")
    a.js("state.levels.trt = 'a, b, c'; state.levels.BR = '1'; renderAll()"); a.page.click("#btnGenSamples")
    check([s["id"] for s in a.state()["samples"]] == ["x1", "b-1", "c-1"], f"level added/BR removed: {[s['id'] for s in a.state()['samples']]}")
    a.js("addVar('day'); state.levels.day = '2'; renderAll()"); a.page.click("#btnGenSamples")
    check([s["id"] for s in a.state()["samples"]] == ["a-2-1", "b-2-1", "c-2-1"], f"variable added: {[s['id'] for s in a.state()['samples']]}")
    a.inv("regenerate")
    a.fill(); ws = a.js("allWellObjs().map(w => w.sample)"); check("Filled" in a.toast() and all(ws.count(x) == 3 for x in ["a-2-1", "b-2-1", "c-2-1"]), f"Fill works after regenerating: {a.toast()}")
    a.answer = "abc"; a.js("numberIds()"); check(a.js("state.samples[0].id") == "a-2-1", "numbering with text: no change")
    a.setup(["gapdh"], ["S1", "S2"]); a.fill()
    a.js("plate().wells.H12 = {role: 'noRT', sample: 'S1', target: 'gapdh'}; renderAll()")   # a per-sample noRT
    a.answer = "101"; a.js("numberIds()")
    check([s["id"] for s in a.state()["samples"]] == ["101", "102"], "numbering 101..")
    check(a.js("plate().wells.H12.sample") == "101", "numbering renames the per-sample noRT too")
    a.inv("numbering"); a.close()


def roundtrip(b, label, setup):
    a = App(b); setup(a)
    csv1 = a.js("layoutCSV()"); s1 = a.state()
    a2 = App(b); a2.js("([n, t]) => importText(n, t)", ["x_layout.csv", csv1])
    s2 = a2.state(); csv2 = a2.js("layoutCSV()")
    check(csv1 == csv2, f"{label}: CSV changes after save -> open")
    check([p["wells"] for p in s1["plates"]] == [p["wells"] for p in s2["plates"]], f"{label}: plates differ after open")
    placed = {w["sample"] for p in s1["plates"] for w in p["wells"].values() if w["role"] == "sample"}
    norm = lambda ss: [(x["id"], {k: v for k, v in x["v"].items() if v}) for x in ss]   # empty values aren't saved
    check(norm([s for s in s1["samples"] if s["id"] in placed]) == norm(s2["samples"]), f"{label}: samples differ after open")
    check(s1["primers"] == s2["primers"] and s1["refs"] == s2["refs"], f"{label}: primers/HK differ")
    a2.inv(label + " (re-opened)"); a.close(); a2.close()


@scenario("save -> open round trips")
def s_roundtrip(b):
    def plain(a):
        smp = [(f"S{i}", {"trt": ["ctrl", "drug"][i % 2], "BR": str(i % 3 + 1)}) for i in range(15)]
        a.setup(["gapdh", "actb", "geneA", "geneB"], smp, ["trt", "BR"]); a.js("state.refs = {gapdh: true}; state.primers = {actb: 'P1/2'}"); a.fill(pool="trt")
    def odd(a):
        smp = [('s "1"', {"note": "a, b", "BR": "1"}), ("µ-ß-2", {"note": "line", "BR": "2"}), ("x;y", {"note": "", "BR": "3"})]
        a.setup(['gene "A"', "actb, x".replace(",", ""), "ünï"], smp, ["note", "BR"]); a.js("state.primers = {'ünï': 'P1/2, rev'}"); a.fill(reps="2", ntc="2")
    def touched(a):
        a.setup(["gapdh"], ["S1", "S2", "S3"]); a.fill()
        a.js("plate().wells.H12 = {role: 'IPC', sample: 'cal', target: 'gapdh'}; delete plate().wells.A01; renderAll()")
    roundtrip(b, "plain", plain); roundtrip(b, "odd characters", odd); roundtrip(b, "touched up", touched)


@scenario("opening hand-written and broken files")
def s_import(b):
    a = App(b)
    cases = {
        "minimal": ("plate,well,role,target\n1,A1,sample,gapdh\n1,a2,sample,gapdh\n1,B01,ntc,actb\n", 3),
        "roles": ("plate,well,role,sample,target\n1,A1,SAMPLE,S1,g\n1,A2,nort,S1,g\n1,A3,ntc,,g\n1,A4,empty,,\n", 3),
        "crlf+bom": ("\ufeffplate,well,role,sample,target,BR\r\n1,A01,sample,S1,g,1\r\n1,A02,sample,S2,g,2\r\n", 2),
        "384 wells": ("plate,well,role,target\n1,A01,sample,g\n1,P24,sample,g\n1,M13,sample,g\n", 1),
        "blank lines": ("plate,well,role,target\n\n1,A01,sample,g\n,,,\n", 1),
        "empty role on an empty well": ("plate,well,role,sample,target\n1,A01,sample,S1,g\n1,A02,,,\n", 1),
        "quoted comma": ('plate,well,role,sample,target\n1,A01,sample,"S1, left",g\n', 1),
    }
    for name, (text, nwells) in cases.items():
        a.js("([n, t]) => importText(n, t)", [name + ".csv", text])
        check(a.js("allWells().length") == nwells, f"open {name}: {a.js('allWells().length')} wells, expected {nwells}")
        a.inv(f"open {name}")
    before = a.state()
    bad = {"v2": "#cqpid layout v2\nplate,well,target\n1,A1,g\n", "no target column": "plate,well\n1,A1\n",
           "empty": "", "semicolons": "plate;well;target\n1;A1;g\n", "garbage": "\x00\x01PK\x03\x04 binary",
           "no role column": "plate,well,sample,target\n1,A01,S1,g\n1,A02,,g\n",
           "duplicate well": "plate,well,role,sample,target\n1,A01,sample,S1,g\n1,A1,NTC,,g\n",
           "unclosed quote": 'plate,well,role,sample,target\n1,A01,sample,S1,g\n1,A02,sample,S1,"geneB\n1,A03,sample,S1,g\n',
           "unknown role": "plate,well,role,sample,target\n1,A01,weird,S1,g\n",
           "missing role": "plate,well,role,sample,target\n1,A01,,S1,g\n"}
    for name, text in bad.items():
        a.js("([n, t]) => importText(n, t)", [name + ".csv", text])
        check(a.state() == before, f"open {name}: layout changed")
        check(a.toast(), f"open {name}: no message")
        a.inv(f"open {name}")
    # std wells keep their dilution through open -> save -> open, and dilution is not a sample variable
    std = "#cqpid layout v1\nplate,well,role,sample,target,dilution\n1,A01,std,pool1,g,1\n1,B01,std,pool1,g,10\n1,C01,std,pool1,g,100\n1,H01,NTC,,g,\n"
    a.js("([n, t]) => importText(n, t)", ["std.csv", std])
    check(a.js("state.vars") == [], f"dilution is not a variable: {a.js('state.vars')}")
    out = a.js("layoutCSV()")
    check(out == std, "std layout saves unchanged:\n" + out)
    a.js("() => { ui.selected = new Set(['A01']); renderInspector(); $('inspRole').value = 'sample'; inspectorApply(); }")
    check("dilution" not in a.js("plate().wells.A01"), "dilution dropped when a well stops being std")
    a.inv("std round trip")
    a.close()


@scenario("undo/redo chain")
def s_undo(b):
    a = App(b)
    s0 = a.state()
    steps = ["state.targets.length || (commit(), state.targets.push('g1','g2'), renderAll())",
             "addSample()", "addSample()", "addSample()", "runFill()", "toggleRef('g1')", "moveTarget(0, 1)",
             "addVar('trt')", "moveSample(0, 1)", "deleteSample(0)"]
    snaps = [s0]
    for st in steps:
        a.js("() => { " + st + " }"); snaps.append(a.state())
    a.page.fill("#expName", "run 1"); a.page.dispatch_event("#expName", "change")
    a.page.click("#btnUndo"); check(a.js("state.name") == "", "undo reverts the name change")
    for k in range(len(steps)):
        a.page.click("#btnUndo")
    end = a.state(); end["active"] = s0["active"]
    check(end == s0, "undo all: back to the start")
    for k in range(len(steps)):
        a.page.click("#btnRedo")
    check(a.state()["samples"] == snaps[-1]["samples"] and a.state()["plates"] == snaps[-1]["plates"], "redo all: back to the end")
    a.inv("undo chain")
    # no undo while a dialog is open
    n = a.js("state.plates.length"); a.js("editTarget(0)"); a.page.focus("#modal button.primary")
    a.page.keyboard.press("Meta+z"); a.page.keyboard.press("Control+z")
    check(a.js("state.plates.length") == n and a.js("$('modalBg').classList.contains('on')"), "undo blocked while a dialog is open")
    a.page.keyboard.press("Escape"); a.inv("dialog undo"); a.close()


@scenario("touch-up on the plate")
def s_touchup(b):
    a = App(b)
    a.setup(["gapdh", "actb"], ["S1", "S2", "S3"]); a.fill()
    box = a.page.locator("#plate .well[data-r='0'][data-c='0']").bounding_box()
    box2 = a.page.locator("#plate .well[data-r='1'][data-c='2']").bounding_box()
    a.page.mouse.move(box["x"] + 5, box["y"] + 5); a.page.mouse.down()
    a.page.mouse.move(box2["x"] + 5, box2["y"] + 5, steps=5); a.page.mouse.up()
    check(a.js("ui.selected.size") == 6, f"drag selects a rectangle: {a.js('ui.selected.size')}")
    a.page.select_option("#inspSample", "")   # (none)
    a.page.locator("#plate .well[data-r='0'][data-c='0']").click(modifiers=["Shift"])
    check(a.page.eval_on_selector("#inspSample", "s => s.value") == "", "inspector keeps (none) while selecting")
    a.page.select_option("#inspRole", "NTC"); a.page.click("#inspApply")
    a.inv("set NTC")
    a.page.locator("#plate .well[data-r='7'][data-c='11']").click()
    a.page.select_option("#inspRole", "sample"); a.page.select_option("#inspSample", "S1"); a.page.select_option("#inspTarget", "actb")
    a.page.click("#inspApply"); check(a.js("plate().wells.H12 && plate().wells.H12.sample") == "S1", "fill an empty well")
    a.page.click("#inspClear"); check(not a.js("plate().wells.H12"), "clear a well")
    a.page.keyboard.press("Escape"); check(a.js("ui.selected.size") == 0, "Escape clears the selection")
    # after Apply the inspector goes back to (keep): the next edit changes only what is picked again
    a.page.locator("#plate .well[data-r='0'][data-c='0']").click()
    a.page.select_option("#inspRole", "NTC"); a.page.click("#inspApply")
    check(all(a.page.eval_on_selector(f"#{x}", "s => s.value") == "__keep" for x in ["inspRole", "inspSample", "inspTarget"]), "inspector back to (keep) after Apply")
    w = a.js("plate().wells.A04"); a.page.locator("#plate .well[data-r='0'][data-c='3']").click()
    a.page.select_option("#inspTarget", "gapdh"); a.page.click("#inspApply")
    w2 = a.js("plate().wells.A04")
    check(w2["role"] == w["role"] and w2["sample"] == w["sample"] and w2["target"] == "gapdh", f"target-only edit keeps role and sample: {w} -> {w2}")
    a.inv("touch-up"); a.close()


@scenario("print")
def s_print(b):
    a = App(b)
    smp = [(f"S{i}", {"BR": str(i % 3 + 1)}) for i in range(15)]
    a.setup(["gapdh", "actb", "geneA", "geneB"], smp, ["BR"]); a.fill()
    a.page.click("#btnPrint")
    n = a.js("state.plates.length")
    check(a.js("window.__printed") == 1, "print called once")
    check(a.js("document.querySelectorAll('#printArea .pp').length") == n, "one print page per plate")
    nf = a.js("document.querySelectorAll('#printArea .cf').length")
    check(nf == 30, f"print frames: {nf}, expected 30 (15 samples x 2 plates)")
    check(a.js("document.querySelectorAll('#printArea table.grid tr').length") > 15, "sample key printed")
    a.page.emulate_media(media="print")
    w = a.js("Math.max(...[...document.querySelectorAll('#printArea .plate')].map(p => p.scrollWidth))")
    check(w <= 700, f"printed plate {w}px wide (A4/Letter printable width ~700px)")
    a.page.emulate_media(media="screen"); a.inv("print"); a.close()


@scenario("window widths and dark mode")
def s_widths(b):
    for width in [1600, 1400, 1280, 1100, 900, 700]:
        for scheme in ["light", "dark"]:
            a = App(b, width=width, scheme=scheme)
            smp = [(f"ctrl-day2-{i}", {"BR": str(i % 3 + 1)}) for i in range(15)]
            a.setup(["gapdh", "actb", "geneA", "geneB", "geneC"], smp, ["BR"]); a.js("state.primers = {gapdh: 'P101/102 long label'}"); a.fill()
            a.inv(f"{width}px {scheme}"); a.close()


@scenario("misc: New, HK/primer on rename, undo after Open, tabs, blank pools, long names, editing values")
def s_misc(b):
    a = App(b)
    a.setup(["gapdh", "actb"], [("S1", {"BR": "1"}), ("S2", {"BR": "2"})], ["BR"])
    a.js("() => { state.refs = {gapdh: true}; state.primers = {gapdh: 'P1/2'}; }"); a.fill()
    a.js("editTarget(0)"); a.page.fill("#modal input >> nth=0", "GAPDH"); a.page.click("#modal button.primary")
    check(a.js("state.refs") == {"GAPDH": True} and a.js("state.primers") == {"GAPDH": "P1/2"}, "HK and primer follow a renamed target")
    a.page.click("#btnNew")
    s = a.state()
    check(s["targets"] == ["GAPDH", "actb"] and not s["samples"] and not a.js("allWells().length"), "New keeps targets only")
    a.page.click("#btnUndo"); check(a.js("allWells().length") > 0, "undo New")
    before = a.state()
    a.js("([n, t]) => importText(n, t)", ["other.csv", "plate,well,role,target\n1,A1,sample,x\n"])
    a.page.click("#btnUndo"); check(a.state()["plates"] == before["plates"], "undo after Open restores the layout")
    a.setup(["g1", "g2", "g3", "g4", "g5"], [(f"S{i}", {"t": ["0", "", "12"][i % 3]}) for i in range(30)], ["t"])
    a.fill(pool="t")
    pools = sorted({w["sample"] for p in a.state()["plates"] for w in p["wells"].values() if w["role"] == "noRT"})
    check(pools == ["noRT_0", "noRT_12", "noRT_blank"], f"pools with a blank value: {pools}")
    n = a.js("state.plates.length")
    if n > 1:
        a.page.locator("#plateTabs .tab").nth(1).click(); a.js("toggleRef('g1')"); a.page.click("#btnUndo")
        check(a.js("state.active") == 1, "undo keeps the open plate tab")
    a.inv("blank pools")
    long = "a-very-long-target-name-for-testing"
    a.setup([long, "actb"], [("ctrl-day2-rep-1-extra-long", {}), ("S2", {})]); a.fill()
    a.js("() => { state.primers = {[%r]: 'P1/2-very-long-primer-label'}; renderAll(); }" % long)
    a.inv("long names")
    a.setup(["gapdh"], [("S1", {"BR": "1"})], ["BR"]); a.fill()
    inp = a.page.locator("#sampleTable input").first; inp.fill("7"); inp.press("Tab")
    check(",7" in a.js("layoutCSV()").splitlines()[2], "edited sample value is saved")
    a.inv("edit values"); a.close()


def main():
    names = sys.argv[1:] or ["webkit", "chromium"]
    scenarios = [f for f in globals().values() if callable(f) and hasattr(f, "scenario")]
    ok = True
    with sync_playwright() as p:
        for name in names:
            browser = getattr(p, name).launch()
            for sc in scenarios:
                n0 = len(FAILS)
                print(f"[{name}] {sc.scenario}")
                try:
                    sc(browser)
                except Exception as e:
                    FAILS.append(f"{sc.scenario}: crashed: {e}"); print("  CRASH:", e)
                ok &= len(FAILS) == n0
            browser.close()
            print(f"{name}: {'OK' if not FAILS else 'FAILED'}")
    print(f"\n{len(FAILS)} failure(s)")
    for f in FAILS:
        print(" -", f)
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
