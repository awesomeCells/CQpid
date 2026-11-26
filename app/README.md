# CQpid app

Makes qPCR plate layouts (96-well) and saves them in the CQpid CSV format (`../spec/layout_format.md`). One self-contained file, `cqpid.html`: double-click to open it in Safari (Chrome works too). Nothing is installed, nothing leaves your computer.

## Workflow

1. **Targets**: **+ Add** takes several names at once (one per line or comma-separated). Order them with ↑ ↓; neighbouring targets share a plate. Click **HK** to mark reference (housekeeping) genes; the flag is saved in the layout and shown in the master-mix tables. ✎ renames, sets the primer label (e.g. P1/2) or deletes.
2. **Samples**: list the variables and their levels in the small table (BR 1, 2, 3 is there already; type a name in "+ variable" to add one). The top row changes slowest, the bottom row fastest. **Generate** makes the sample list every combination of the levels: samples that still match keep their IDs, samples that no longer match are removed (with their wells; Undo brings them back). Samples outside the full design (e.g. an untreated time `0`) are added by hand with **+ add sample**. IDs are built from the values (`12-drug-1`); **1,2,3…** in the ID header numbers them consecutively from a start number (e.g. tube numbers 101…), and double-click renames one. ↑ ↓ move samples; **+ add sample** at the end adds one by hand.
3. **Fill plates**: set replicates (auto = 3 unless 2 saves a plate), NTC per target and how to pool the noRT, then **Fill**. All samples and targets are used; to leave some out, open "Samples and targets". It replaces all plates. Plates come only from Fill; the tabs switch between them.
4. **Touch up**: click or drag on the plate to select wells (Shift adds), then set role, sample or target below the plate.
5. **Save layout** downloads `<experiment>_layout.csv`. It holds the plates: **Open…** brings back the plates and the targets, samples and variables used on them (targets in plate order). Targets or samples that are not on any plate are not saved.
6. **Master mix**: shown for the current plate (under the plate) and on each printed page, in two steps. Step 1, base mix (Luna + water) for the plate; step 2, per gene: base mix + primer pool. The recipe is for Luna Universal qPCR Master Mix (NEB), 10 µl SYBR reactions. Per well 9 µl gene mix + 1 µl cDNA/noRT/water (Luna 5 µl, primer pool 0.5 µl of 10 µM, water 3.5 µl). Gene mixes cover wells + 10% (rounded up); the base mix covers all gene mixes + ~10%, rounded up to 10 reactions. Set a target's primer label (e.g. P1/2) with ✎; it is saved in the layout. The recipe is the `MIX` constant at the top of the script.
7. **Print**: one page per plate (same look as on screen: each cDNA framed with its ID, wells show the gene) with that plate's master-mix tables. Then a sample key.

On the plate, each cDNA block (all wells of one sample) sits in a grey frame with the cDNA ID as a tab of the frame, so you can see where to switch tubes while the wells keep the regular plate grid (same in print). Colours are the gene mixes.

**Checks** warns about missing controls, a gene whose samples are split across plates, and similar; it never blocks. Undo/redo: Cmd+Z / Shift+Cmd+Z. Files are saved as downloads; Safari can't save back into the opened file.

## Layout rule

- A **segment** is all wells of one cDNA on one plate: for each gene on that plate (in target order), its replicates side by side. A segment lies in one row or one column and never wraps. Several segments share a line when they fit (e.g. two 6-well segments in a 12-well row).
- Controls (noRT pool(s), then NTC) get one well per gene each, grouped in the segment space after the samples, each under its gene's replicate wells.
- The app chooses genes per plate (in target order) and orientation (rows or columns) for the fewest plates. On a tie it puts more genes on a plate (longer segments), then prefers rows.
- Replicates: 3, unless 2 needs fewer plates (override: Replicates auto / 2 / 3).
- noRT: one pooled well per gene (`noRT_pool`), or one per value of a variable ("noRT pool by", e.g. `noRT_drug`).

Example: 15 samples, 4 genes → 3 replicates, 2 genes per plate, 2 plates. Each sample is one 6-well half-row (gene A ×3, gene B ×3), and the controls fill the last half-row.

## Plate split

A gene's samples are never split across plates; the plate break falls between genes. A plate-to-plate shift then moves all samples of a gene equally and cancels in every comparison between samples (sample maximization, Hellemans et al. 2007). Reference genes may be on another plate (compare dCt per sample). Only absolute dCt values, not comparisons, carry a plate offset. No inter-plate calibrator is needed. If one gene's samples don't fit on a plate even with 2 replicates (about 47 samples), the app splits that gene by sample and warns that it needs an IPC.

## Development

Everything is in `cqpid.html`. Two browser tests run in WebKit (Safari engine) and Chromium with Playwright: `python app/tests/test_app.py [screenshot_dir]` walks through a full run; `python app/tests/test_scenarios.py` runs many small scenarios (sizes, options, edits, round trips, broken files, undo, print, window widths).
