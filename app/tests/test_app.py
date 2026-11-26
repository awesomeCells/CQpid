"""Browser test for the CQpid app (Playwright, WebKit and Chromium).

    pip install playwright && python -m playwright install webkit chromium
    python app/tests/test_app.py [screenshot_dir]

Runs the acceptance layout end to end through the UI: targets added in one go and
reordered, samples generated (BR pre-filled, readable IDs) plus extra ones,
Fill -> 2 plates with every position checked, the layout rule on other designs,
noRT pooled by a variable, checks, touch-up edit, undo/redo, save -> re-open
restoring the whole run, CSV format, print. Fails on any JS error.
"""
import pathlib, sys, tempfile
from playwright.sync_api import sync_playwright

APP = pathlib.Path(__file__).resolve().parents[1] / "cqpid.html"
SHOTS = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else None
ACC_IDS = [f"{t}-{h}-{b}" for t in ["drug", "ctrl"] for h in ["12", "24"] for b in "123"] + ["0-1", "0-2", "0-3"]


def generate(page, rows):
    """Type levels into the design table (adding variables as needed), then Generate."""
    for var, levels in rows:
        names = page.eval_on_selector_all("#designTable input.dv", "xs => xs.map(x => x.value)")
        if var not in names:
            new = page.locator("#designTable tr.new input.dv"); new.fill(var); new.press("Enter")
            names = page.eval_on_selector_all("#designTable input.dv", "xs => xs.map(x => x.value)")
        page.locator("#designTable input.dl").nth(names.index(var)).fill(levels)
    page.click("#btnGenSamples")


def add_samples(page, samples):
    """Samples outside the full design (e.g. untreated time 0), added as + add sample would, with IDs."""
    page.evaluate("xs => { commit(); xs.forEach(([id, v]) => state.samples.push({id, v})); renderAll(); }", samples)


def state(page):
    return page.evaluate("JSON.parse(JSON.stringify(state))")


def cell(w):
    return (w["role"], w["sample"], w["target"]) if w else None


def wid(r, c):
    return f"{'ABCDEFGH'[r]}{c + 1:02d}"


def layout(page, n, targets, pool="", reps=0, values="(i) => ({})"):
    """layoutPlates on synthetic samples S1..Sn, variables from values(i); NTC 1."""
    return page.evaluate(f"""(() => {{
        const saved = state.samples;
        state.samples = Array.from({{length: {n}}}, (_, i) => ({{id: 'S' + (i + 1), v: ({values})(i)}}));
        const L = layoutPlates(state.samples.map(s => s.id), {targets!r}, {reps}, {pool!r}, 1);
        state.samples = saved; return L; }})()""")


def check_two_gene_plate(w, ids, genes):
    """Each sample one 6-well half-row: gene A x3, gene B x3; 2 samples per row."""
    for k, s in enumerate(ids):
        for j, t in enumerate(genes):
            for i in range(3):
                assert cell(w[wid(k // 2, (k % 2) * 6 + j * 3 + i)]) == ("sample", s, t), (s, t, i)


def ACCEPT(d):
    d.accept()


def run(browser, name, out):
    errors = []
    ctx = browser.new_context(accept_downloads=True, viewport={"width": 1500, "height": 1300})
    page = ctx.new_page()
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("dialog", ACCEPT)
    page.goto(APP.as_uri())

    # logo and favicon (inline SVG, works from file://)
    assert page.locator("header h1 svg path").count() == 6
    fav = page.get_attribute("link[rel=icon]", "href")
    assert fav.startswith("data:image/svg+xml,") and "#" not in fav

    # targets: several at once (duplicates ignored), then reorder
    page.click("#btnAddTarget")
    page.fill("#modal textarea", "gapdh\ngeneA, actb\ngeneB\ngapdh")
    page.click("#modal button.primary")
    page.locator("#targetList .item", has_text="actb").locator("button[title='Move up']").click()
    assert state(page)["targets"] == ["gapdh", "actb", "geneA", "geneB"]
    assert "No reference (HK) gene marked" not in page.inner_text("#checks")   # only once wells exist
    for g in ["gapdh", "actb"]:
        page.locator("#targetList .item", has_text=g).locator("button.hk").click()
    assert state(page)["refs"] == {"gapdh": True, "actb": True}
    assert page.locator("#btnSaveTargets").count() == 0

    # samples: BR 1-3 pre-filled; 12 factorial, then 3 more appended (0 h untreated)
    assert page.locator("#designTable input.dv").nth(0).input_value() == "BR" and page.locator("#designTable input.dl").nth(0).input_value() == "1, 2, 3"
    generate(page, [("treatment", "drug, ctrl"), ("time", "12, 24")])
    add_samples(page, [[f"0-{b}", {"treatment": "none", "time": "0", "BR": b}] for b in "123"])
    s = state(page)
    assert [x["id"] for x in s["samples"]] == ACC_IDS and s["vars"] == ["treatment", "time", "BR"]
    assert s["samples"][12]["v"] == {"treatment": "none", "time": "0", "BR": "1"}
    info = page.inner_text("#fillInfo")
    assert info.startswith("188 wells, 2 plates · 3 reps, 2 genes per plate"), info

    # Tab in a sample cell moves to the next cell (table is not rebuilt)
    page.locator("#sampleTable input").nth(0).fill("drug"); page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement === document.querySelectorAll('#sampleTable input')[1]")

    # Fill: acceptance layout, each sample one half-row (gene A x3, gene B x3), controls in H7-H11
    page.click("#btnFill")
    s = state(page)
    assert [p["id"] for p in s["plates"]] == ["1", "2"]
    p1, p2 = s["plates"][0]["wells"], s["plates"][1]["wells"]
    assert len(p1) == len(p2) == 94
    check_two_gene_plate(p1, ACC_IDS, ["gapdh", "actb"])
    check_two_gene_plate(p2, ACC_IDS, ["geneA", "geneB"])
    assert cell(p1["H07"]) == ("noRT", "noRT_pool", "gapdh") and cell(p1["H08"]) == ("NTC", "", "gapdh")
    assert cell(p1["H10"]) == ("noRT", "noRT_pool", "actb") and cell(p1["H11"]) == ("NTC", "", "actb")
    assert "H09" not in p1 and "H12" not in p1
    assert page.inner_text("#checks") == "No problems found.", page.inner_text("#checks")
    assert page.locator("#plateTabs button").count() == 0          # plates only come from Fill
    if SHOTS:
        for i in range(2):
            page.locator("#plateTabs .tab").nth(i).click()
            page.locator("main").screenshot(path=str(SHOTS / f"{name}_plate{i + 1}.png"))
        page.locator("#plateTabs .tab").nth(0).click()

    # save layout
    page.fill("#expName", "acceptance")
    page.dispatch_event("#expName", "change")
    with page.expect_download() as d:
        page.click("#btnSave")
    assert d.value.suggested_filename == "acceptance_layout.csv"
    (out / name).mkdir()
    csv_path = out / name / "acceptance_layout.csv"
    d.value.save_as(csv_path)
    lines = csv_path.read_text().splitlines()
    assert lines[0] == "#cqpid layout v1" and lines[1] == "plate,well,role,sample,target,reference,treatment,time,BR"
    assert len(lines) == 2 + 188
    assert lines[2] == "1,A01,sample,drug-12-1,gapdh,TRUE,drug,12,1"
    assert "1,H07,noRT,noRT_pool,gapdh,TRUE,,," in lines and "1,H08,NTC,,gapdh,TRUE,,," in lines
    assert "2,H06,sample,0-3,geneB,,none,0,3" in lines

    # print: one page per plate, two-step master mix, sample key
    page.evaluate("window.print = () => {}")
    page.click("#btnPrint")
    assert page.locator("#printArea .pp").count() == 2
    rows = page.evaluate("[...document.querySelectorAll('#printArea .pp')[0].querySelectorAll('tr')].map(r => [...r.cells].map(c => c.textContent).join('|'))")
    assert rows == ["Component|Volume", "Luna Master Mix|600 µl", "Water|420 µl", "Total|1020 µl",
                    "Gene|Base mix|Primers (10 µM)|Total|Wells",
                    "gapdh (HK)|442 µl|26 µl|468 µl|47 · cols 1–3, 7–9", "actb (HK)|442 µl|26 µl|468 µl|47 · cols 4–6, 10–12"], rows
    assert "plate 1" in page.text_content("#printArea .pp h3") and "Sample key" in page.text_content("#printArea")
    if SHOTS:
        page.emulate_media(media="print")
        page.screenshot(path=str(SHOTS / f"{name}_print.png"), full_page=True)
        if name == "chromium":
            page.pdf(path=str(SHOTS / "print.pdf"), format="Letter")
        page.emulate_media(media="screen")

    # 5 targets: auto picks 2 reps (2 plates: 3 genes, full plate + 2 genes); forcing 3 reps gives 3 plates
    page.click("#btnAddTarget"); page.fill("#modal textarea", "geneD"); page.click("#modal button.primary")
    assert page.inner_text("#fillInfo").startswith("160 wells, 2 plates · 2 reps, 3 genes per plate"), page.inner_text("#fillInfo")
    page.click("#btnFill")
    s = state(page)
    assert [len(p["wells"]) for p in s["plates"]] == [96, 64]
    assert [cell(s["plates"][0]["wells"][wid(0, c)])[2] for c in range(6)] == ["gapdh"] * 2 + ["actb"] * 2 + ["geneA"] * 2
    page.select_option("#fillReps", "3"); page.click("#btnFill")
    s = state(page)
    assert len(s["plates"]) == 3 and len(s["plates"][2]["wells"]) == 15 * 3 + 2
    assert cell(s["plates"][2]["wells"]["A04"]) == ("sample", "drug-12-2", "geneD")
    page.select_option("#fillReps", "0")
    page.click("#btnUndo"); page.click("#btnUndo"); page.click("#btnUndo")
    assert len(state(page)["plates"]) == 2 and state(page)["targets"] == ["gapdh", "actb", "geneA", "geneB"]

    # noRT pooled by treatment through the UI: one pool per value, carrying that value
    page.select_option("#fillPool", "treatment"); page.click("#btnFill")
    # 4 control wells per gene need a 17th slot, so auto drops to 2 reps: 3 samples per row (4 wells each)
    assert "· 2 reps, 2 genes per plate" in page.inner_text("#fillInfo")
    w = state(page)["plates"][0]["wells"]
    assert cell(w["A05"]) == ("sample", "drug-12-2", "gapdh") and cell(w["E12"]) == ("sample", "0-3", "actb")
    assert cell(w["F01"]) == ("noRT", "noRT_drug", "gapdh") and w["F01"]["v"] == {"treatment": "drug"}
    assert cell(w["F05"]) == ("noRT", "noRT_none", "gapdh") and cell(w["F06"]) == ("NTC", "", "gapdh")
    assert cell(w["F08"]) == ("NTC", "", "actb")
    assert "1,F02,noRT,noRT_ctrl,gapdh,TRUE,ctrl,," in page.evaluate("layoutCSV()")
    page.click("#btnUndo"); page.select_option("#fillPool", "")

    # layout rule, other designs
    # (b) 12 samples, 4 genes, noRT pooled by time (3 pools), NTC 1 -> 3 reps, 2 genes/plate, 2 plates
    b = layout(page, 12, ["g1", "g2", "g3", "g4"], pool="time", values="(i) => ({time: ['0', '12', '24'][Math.floor(i / 4)]})")
    assert (b["reps"], b["g"], b["o"], len(b["plates"])) == (3, 2, "rows", 2), b
    bw = b["plates"][0]
    check_two_gene_plate(bw, [f"S{i + 1}" for i in range(12)], ["g1", "g2"])
    assert [bw[wid(6, c)]["sample"] for c in range(3)] == ["noRT_0", "noRT_12", "noRT_24"]
    assert cell(bw["G07"]) == ("NTC", "", "g1") and cell(bw["G10"]) == ("NTC", "", "g2") and len(bw) == 12 * 6 + 8
    # (c) 6 samples, 2 genes -> 1 plate, 3 reps
    c = layout(page, 6, ["g1", "g2"])
    assert (c["reps"], c["g"], len(c["plates"])) == (3, 2, 1), c
    # 4 genes, 6 samples -> all 4 genes on one plate, one full row per sample
    d4 = layout(page, 6, ["g1", "g2", "g3", "g4"])
    assert (d4["reps"], d4["g"], len(d4["plates"])) == (3, 4, 1) and d4["plates"][0]["A12"]["target"] == "g4"
    # 3 reps would need more plates than 2 reps -> auto picks 2
    e = layout(page, 20, ["g1", "g2", "g3"])
    assert e["reps"] == 2 and len(e["plates"]) < len(layout(page, 20, ["g1", "g2", "g3"], reps=3)["plates"]), e
    # too many samples for one plate per gene -> split by sample, flagged
    assert layout(page, 40, ["g1"])["reps"] == 2                  # 40 fit with 2 reps (48 slots)
    big = layout(page, 60, ["g1"])
    assert not big["fits"] and len(big["plates"]) == 2

    # touch-up: click a well, set its sample; drag-select two wells and clear them; undo
    well = lambda r, c: page.locator(f"#plate .well[data-r='{r}'][data-c='{c}']")
    well(0, 0).click()
    page.select_option("#inspSample", "drug-12-2")
    page.click("#inspApply")
    assert cell(state(page)["plates"][0]["wells"]["A01"]) == ("sample", "drug-12-2", "gapdh")
    assert "drug-12-1/gapdh (2)" in page.inner_text("#checks")
    a, z = well(7, 6).bounding_box(), well(7, 7).bounding_box()
    page.mouse.move(a["x"] + 5, a["y"] + 5); page.mouse.down()
    page.mouse.move(z["x"] + 5, z["y"] + 5, steps=4); page.mouse.up()
    assert page.inner_text("#inspWells") == "2 well(s)"
    page.click("#inspClear")
    assert "noRT and NTC missing for gene gapdh" in page.inner_text("#checks")
    page.click("#btnUndo"); page.click("#btnUndo")
    assert cell(state(page)["plates"][0]["wells"]["A01"]) == ("sample", "drug-12-1", "gapdh")
    page.click("#btnRedo")
    assert cell(state(page)["plates"][0]["wells"]["A01"]) == ("sample", "drug-12-2", "gapdh")
    page.click("#btnUndo")
    page.keyboard.press("Escape")

    # split gene check
    page.evaluate("state.plates[1].wells.H12 = {role: 'sample', sample: 'drug-12-1', target: 'gapdh'}; renderAll()")
    assert "Gene gapdh: samples split across plates 1, 2 (needs IPC)" in page.inner_text("#checks")
    page.evaluate("delete state.plates[1].wells.H12; renderAll()")

    # re-open the saved layout after a full reset: the whole run comes back
    before = state(page)
    page.evaluate("state = emptyState(); renderAll()")
    page.set_input_files("#fileInput", str(csv_path))
    page.wait_for_function("state.samples.length > 0")
    s = state(page)
    for k in ["targets", "refs", "vars", "samples", "plates", "name"]:
        assert s[k] == before[k], k
    assert page.evaluate("layoutCSV()") == csv_path.read_text()
    assert page.inner_text("#checks") == "No problems found."

    # Master mix: 5 genes, duplicates, 15 samples -> volumes checked by hand
    page.evaluate("state = emptyState(); renderAll()")
    page.click("#btnAddTarget"); page.fill("#modal textarea", "gapdh, actb, geneA, geneB, geneC"); page.click("#modal button.primary")
    for g in ["gapdh", "actb"]:
        page.locator("#targetList .item", has_text=g).locator("button.hk").click()
    for i, pr in enumerate(["P1/2", "P3/4", "P5/6", "P7/8", "P9/10"]):
        page.locator("#targetList .name").nth(i).click()
        page.locator("#modal input").nth(1).fill(pr); page.click("#modal button.primary")
    generate(page, [("time", "12, 24"), ("treatment", "ctrl, drug")])
    add_samples(page, [[f"0-{b}", {"time": "0", "BR": b}] for b in "123"])
    page.evaluate("commit(); state.samples.unshift(...state.samples.splice(12)); renderAll()")
    ids = [x["id"] for x in state(page)["samples"]]
    assert ids == ["0-1", "0-2", "0-3"] + [f"{h}-{t}-{b}" for h in ["12", "24"] for t in ["ctrl", "drug"] for b in "123"], ids
    assert state(page)["vars"] == ["time", "treatment", "BR"]
    # reorder + number IDs (tube numbers 101-115), fill options collapsed
    assert page.locator("#fillPick").get_attribute("open") is None
    page.locator("#sampleTable tr").nth(2).locator("button[title='Move up']").click()
    assert [x["id"] for x in state(page)["samples"]][:2] == ["0-2", "0-1"]
    page.locator("#sampleTable tr").nth(2).locator("button[title='Move up']").click()
    page.once("dialog", lambda d: d.accept("101"))
    page.remove_listener("dialog", ACCEPT)
    page.click("#sampleTable th button")
    page.on("dialog", ACCEPT)
    assert [x["id"] for x in state(page)["samples"]] == [str(i) for i in range(101, 116)]
    page.locator("#sampleTable button.link").click()
    assert len(state(page)["samples"]) == 16
    page.click("#btnUndo")
    page.select_option("#fillReps", "2"); page.click("#btnFill")
    assert cell(state(page)["plates"][0]["wells"]["A01"]) == ("sample", "101", "gapdh")
    def mix_text(i):
        page.locator("#plateTabs .tab").nth(i).click(); return page.inner_text("#mixBox")
    m1, m2 = mix_text(0), mix_text(1)
    for x in ["Plate 1 (gapdh, actb, geneA)", "Luna Master Mix\t600 µl", "Water\t420 µl", "1020 µl",
              "gapdh (HK)\t306 µl\t18 µl P1/2\t324 µl", "geneA\t306 µl\t18 µl P5/6\t324 µl"]:
        assert x in m1, (x, m1)
    for x in ["Plate 2 (geneB, geneC)", "Luna Master Mix\t400 µl", "Water\t280 µl", "680 µl",
              "geneC\t306 µl\t18 µl P9/10\t324 µl"]:
        assert x in m2, (x, m2)
    assert page.evaluate("state.primers")["geneB"] == "P7/8"
    csv = page.evaluate("layoutCSV()")
    assert csv.splitlines()[1].startswith("plate,well,role,sample,target,primer,reference,"), csv.splitlines()[1]
    before = state(page)
    p2 = out / f"{name}_mix_layout.csv"; p2.write_text(csv)
    page.evaluate("state = emptyState(); renderAll()")
    page.set_input_files("#fileInput", str(p2)); page.wait_for_function("state.samples.length > 0")
    assert state(page)["refs"] == {"gapdh": True, "actb": True}
    assert state(page)["primers"] == before["primers"] and page.evaluate("layoutCSV()") == csv
    if SHOTS: page.screenshot(path=str(SHOTS / f"{name}_mix.png"))

    ctx.close()
    return errors


with sync_playwright() as pw:
    out = pathlib.Path(tempfile.mkdtemp(prefix="cqpid_test_"))
    failed = False
    for name in ["webkit", "chromium"]:
        browser = getattr(pw, name).launch()
        try:
            errs = run(browser, name, out)
            print(f"{name}: {'OK' if not errs else 'JS errors: ' + str(errs)}")
            failed |= bool(errs)
        except AssertionError:
            import traceback; traceback.print_exc()
            print(f"{name}: FAILED")
            failed = True
        browser.close()
    print("files in", out)
sys.exit(1 if failed else 0)
