# Phase 5 Review (io, viz, GUI) — `git log 5fc68c2..98ae5dd`

Status: COMPLETE

Repo: .
HEAD: 98ae5dd (51cae98 plus the ledger-162 log). The main tree was not modified. A scratch
worktree was created under the session scratchpad and removed. The GUI was driven
offscreen with PyQt6 (`QT_QPA_PLATFORM=offscreen`). Figures were rendered to PNG at 200 dpi
and inspected by eye.

## Summary

| # | Sev | Where | One line |
|---|---|---|---|
| P1 | MAJOR | io/report.py:405; assessment.py:1337 and the PASS summary | A Shannon threshold with a third decimal, which C5.8's 3-decimal k box now makes enterable, is printed with `:.2f`, so it can round **up**. Executed at k = 1.749 with k_metric 1.7491: the check FAILs, and both its summary and the PDF row print **"k = 1.7491 exceeds the 1.75 threshold"**. The applied value reads below the printed threshold, which is ledger 50's own defect, and the bound is printed high (the D2 / ledger-49 class). The PASS summary likewise prints "at threshold 1.75" |
| P2 | MAJOR | gui/app.py (counter group, C5.8) | The GUI counter is always a half-space `DiscElectrode`, so `validate_counter` refuses it for every full-space electrode. With the box ticked, **Cylindrical band (DBS), Microwire and Sphere all show "Invalid input: counter_electrode is half_space and electrode is full_space ..."**. Ring, Disc, Rectangle and Hemisphere work. Ledger 126's GUI part is not closed for the clinical geometry, and the README's desktop paragraph does not say so |
| P3 | MINOR | io/fem.py `compare_with_point_source` | False positive on valid input. A correctly scaled FEM solution with a grounded outer boundary, `V = I/(4πσ)(1/r − 1/R)`, exported on a regular 41³ grid gives a far-half median ratio of 0.0931, and the default `check_scale` raises "a unit-scale mistake is likely". The median is taken over the farther half by point count, which a uniform grid concentrates near the grounded boundary. True positives work: mV potentials and mm-as-µm positions are flagged. A 3× error is not flagged, as documented |
| P4 | MINOR | viz/plots.py | Layout collisions on rendered figures (ledger 162 is only one of them). (a) Worked-example and refusal panels (b): the legend occludes ceiling lines, and on the refusal figure it clips the refusal sentence ("Water window permit[s] no current at all"). (b) DBS panel (b): "binding limit 2.292e+04 µA (Shannon criterion), provisional" is drawn across the cluster of ceiling lines. (c) Panel (c): the "applied ... µC/cm²" label sits on the SS316LVM bar. (d) Panel (d): "V falls as 1/r" is drawn on its own line. (e) Panel (a) annotates "k = 1.50 (this assessment)" when Shannon is NOT_EVALUATED (the worked example is a microelectrode), with no "not applied" mark |
| P5 | MINOR | io/tabular.py `assess_batch` | Failed-row semantics rest on a `BatchRowsFailedWarning` and on `df.attrs["rows_failed"]`. The attrs do not survive `write_csv` or most pandas operations. `(df.status != "FAIL").sum()` still counts ERROR rows as not failing, and `df.limiting_current_uA.min()` silently skips them. The persistent signal is the `status == "ERROR"` column plus the `error` text, which is adequate but relies on the reader |

Counts: **0 BLOCKER, 2 MAJOR, 3 MINOR.**

---

## P1 — MAJOR — a 3-decimal k prints a threshold rounded up

```
DiscElectrode(1000,"Pt"), k = 1.749, charge chosen for k_metric = 1.7491
Shannon check: FAIL, summary "k = 1.7491 exceeds the 1.75 threshold; max 3319 uA"
PDF Computed row: "1.7491 (threshold 1.75; Shannon 1992, Merrill 2005 eq. 5.1)"
PASS case: "k = 1.56 at threshold 1.75, 1.25x headroom ..."
```

`format_exceeding(applied, f"{k:.2f}")` cannot help. The printed bound "1.75" is above the true
1.749, so no number of applied digits exceeds it, and the loop falls through to `repr`. The
format was harmless while k had two decimals. C5.8 raised the box to three, which made this
reachable from the GUI, and it was always reachable from the API. **Fix:** print k at the
precision it was given (`:g`, or three decimals) in every summary and PDF row, and add a test
at k = 1.749.

## P2 — MAJOR — the GUI counter cannot pair with a full-space electrode

Executed offscreen with "Two-terminal (counter disc)" ticked, for each geometry:

```
Ring, Disc, Rectangle, Hemisphere -> an assessment
Cylindrical band (DBS), Microwire, Sphere -> "Invalid input | ValueError: counter_electrode is half_space and electrode is full_space ..."
```

**Fix:** build the counter disc with the active electrode's `environment` (a full-space
stand-in disc for band, microwire and sphere). Otherwise, disable the group with a stated
reason for full-space electrodes. Say which in the README desktop paragraph.

## P3 — MINOR — FEM scale check: false positive on a grounded boundary

```
regular 41^3 grid to R = 20 mm, 100 uA, 0.35 S/m, points 50 um < r < R
free-space solution: ok, far-half median ratio 1.000
grounded boundary (1 - r/R): RAISED "far-field FEM/point-source ratio has median 0.0931 ..."
mV potentials: flagged | positions mm-as-um: flagged | 3x potential error: not flagged (documented)
```

**Fix:** take the median over a distance band, for example between 5 electrode radii and R/3,
rather than the farther half by count. Alternatively, report the ratio profile and raise only
when the whole profile sits off by more than a decade.

## P4 and P5 — see the table.

On P4 (e): the panel should say "Shannon not applied (microelectrode)" when the check is
NOT_EVALUATED, as the PDF rows now do (C5.11a).

---

## Verification of the lead's items

**(a) C5.11a stacked mutants.** The 833aae4 package diff was reviewed line by line against its
stated intent (M1, M2, M3, 125, 102). It contains only those changes. I re-applied each fix's
reverse in a worktree and ran the suite. **Each is killed by a committed test:**
* M1 not-applied suffix off: 1 failed;
* M2 old provenance row: 1 failed;
* M3 detail says PASS under CAUTION: 1 failed;
* 125 uniform note off: 1 failed;
* 102 endorsed end underated: 1 failed.

No residual mutant remains.

**(b) C5.10 README.** The README change in 0822cbe describes the scale check correctly.
`regenerate_example_output.py --check` passes. The claim "raises on a unit-scale mistake" is
true, with P3's false-positive caveat.

**Ledger 162.** It was logged after C5.11 closed and is scheduled at its own slot, C5.11d. It
was never in C5.11b's scope, and it is still pending. P4 lists the further overlaps found by
rendering.

**GUI atomicity and exception paths.** `recompute` computes the assessment, headline text,
describe text and plot before touching any widget. Either failure path calls `_show_failure`,
which clears the table, the text and the figure and redraws the canvas. No stale text/canvas
pairing is possible. `export_pdf` and `export_figure` catch and report.

**Batch.** An empty CSV raises a named `ValueError`. Failed rows carry `None` results,
`status = "ERROR"` and the message, and they emit the warning (P5).

**`format_exceeding`.**
* Correct wherever the bound is printed floored: CIC via `format_limit`, microelectrode
  `4 nC` via `:g`, chronic via `:g` of a stored integer, and the compliance available voltage
  floored to 3 s.f.
* Wrong for a k threshold that rounds up (P1).

**Citations (C5.7).** A scan of the PDF for every material × saline/in vivo compared the
author/year citations in the body with the reference list. **No cited-but-unlisted and no
listed-but-uncited author** (the only heuristic hits were line-wrapped journal names and the
"Generated 2026" byline).

**TIFF (C5.9).**
* The package TIFF is RGB, LZW, 4306 × 2759 px at 600 dpi: 946 KB, against 47 001 446 bytes
  before.
* It is **pixel-identical (0 pixels differ, max diff 0)** to matplotlib's own raw RGBA TIFF of
  the same figure, flattened against white.
* The old and new files are not comparable directly, because C5.11b changed the figure
  content between them.

**Figures.**
* Every text object, tick label and legend entry on three rendered summary figures (worked
  example, DBS, refusal) is ≥ 5 pt.
* Pass/fail is carried by shape as well as colour: open circle / triangle / square in
  panel (a), hatch in panel (c). The colour pairs are distinguishable in greyscale.
* Layout issues are in P4.

**§6 digits (executed).**
* C5.5b: in-vivo `max_current_cic_uA` = **107.71174812307864** (= the check ceiling);
  monophasic `max_current_cic_uA` and `cic_limit_uC_cm2` → None; `net_dc_current_uA` → 0.0
  for r_a = 1 − 5e-13.
* C5.8's k decimals and pulse-width floor are as booked.
* This closes my Phase 4 M3.

**Regression grids (executed at HEAD):**

| Grid | Result |
|---|---|
| Unbalanced sweep | 1 500/1 500 agree, 319 capped, all FAIL |
| Residual sweep | 6 240/6 240 |
| lds_rate | 0 of 16 200 |
| Repros | ok |
| ww98 | 20 000, clean |
| Mixed geometries with counters | 1 200/1 200 |
| Containment | 0 of 3 000 outside |
| inf/nan leak scan | 300 configurations, 0 leaks |
| K1 far-side sweep | 0 of 96 000 raise |

## Process note
Per the brief, this review wrote only this file. The reviewer did not update
`_conversation_history.md` (CLAUDE.md rule 14).

# VERDICT: **GO** for Phase 6, with two conditions

The io work is sound:
* strict JSON;
* derated and nullable CSV columns;
* citations resolved without over-citation;
* a pixel-identical compressed TIFF;
* an atomic GUI view;
* every C5.11a mutant killed by a committed test.

**Conditions, before release (they can run alongside Phase 6):**
1. **P1.** Print k at its own precision. A FAIL that reads "1.7491 exceeds the 1.75 threshold"
   is ledger 50 again, now reachable from the GUI.
2. **P2.** Make the GUI counter pair with full-space electrodes, or disable it with a stated
   reason. As shipped it errors on the DBS band, the package's headline geometry.

P3–P5 and ledger 162 are MINOR and can be scheduled together as the figure and io polish pass.
