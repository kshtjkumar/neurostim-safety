# Phase 5b Review — `git log 98ae5dd..f9e33a0`

Status: COMPLETE

Repo: .
HEAD: f9e33a0. The main tree was not modified and no worktree was needed. The GUI was
driven offscreen with PyQt6. Five figures were rendered and inspected by eye: the worked
example, DBS, the refusal case, the "k = 3.31" repro, and the GUI Shannon panel.

## Summary

| # | Sev | Where | One line |
|---|---|---|---|
| Q1 | MINOR | assessment.py `_compliance_check`, PASS/CAUTION summary | The stimulator's available voltage, a capacity the requirement must stay under, is still printed round-to-nearest outside the FAIL branch. Executed: **491 of 3 000** random compliance settings print it above the value given (e.g. `compliance_V = 14.5171` shows "14.35 V of **14.52** V"). Verdicts are unaffected and no PASS reads as exceeding, because rounding is monotone. It is the D2 floor rule on a user-settable bound, which C5.6 applied only to FAIL |
| Q2 | MINOR | viz/plots.py `shannon_safe_operating_area` | The operating-point label's white backing can cover a McCreery data point. In DBS panel (a), "k = −0.27" sits on the no-damage circle at Q = 1 µC. On the worked example, "Shannon not applied (microelectrode)" touches the "points: McCreery …" caption (their bounding boxes overlap; both stay legible) |

Counts: **0 BLOCKER, 0 MAJOR, 2 MINOR.**

---

## Verification

**P1 (ledger 163): closed.**
* `format_setting` prints k as given ("1.749"), and `format_against` keeps the applied value
  on the verdict's side of the printed bound.
* Sweep of 3 000 configurations: k at 1, 2, 3, 4 or 6 decimals, k_metric placed ±1e-5 to ±0.1
  around k, three disc sizes, random compliance.
* **0** Shannon summaries whose printed threshold differs from k, **0** FAILs whose printed
  applied value is not above it, **0** PASS/CAUTIONs whose printed applied value is above it,
  and **0** inconsistent PDF "Shannon k" rows.
* Other user-settable bounds: compliance is Q1. The policy and medium set no printed bound. A
  CIC floors through `format_limit`. The microelectrode and chronic thresholds are stored
  constants rendered `:g`.

**P2 (ledger 164): closed.** With the counter ticked in the offscreen GUI, all seven geometries
(ring, disc, rectangle, band, microwire, sphere, hemisphere) assess at 3 mm. The counter is
the active electrode's class, with its environment. For each, the GUI's limiting current equals
the API's `SafetyCalculator` built from the same objects. At 50 µm each shows the separation
guard's message as "Invalid input", which is correct.

**P3 (ledger 165): closed.** Detection matrix:
* Exports: regular grids 11³, 21³ and 41³, and log-radial refined meshes; box 5, 20 and 100 mm;
  free space and grounded boundary.
* **36 of 36 valid exports pass.**
* **180 of 180 unit errors raise:** mV, mm read as µm, cm read as µm, µm read as m, and a
  1000× current mismatch.
* Known limit: a bipolar solution's dipole far field will also trip it, and `check_scale=False`
  is the documented escape.

**P4 (ledgers 162, 166).**
* On the four summary figures and the GUI panel, no text is below 5 pt.
* A text-versus-text and text-versus-legend bounding-box scan finds one touch, on the worked
  example (Q2).
* Fixed by eye:
  * the legends sit below the axes;
  * the refusal sentence is whole;
  * the DBS binding-limit label clears the line cluster;
  * the "applied" label is in the legend, not on a bar;
  * "V falls as 1/r" sits off its line;
  * "k = 3.31" sits below-left of its point, clear of the legend (162);
  * a NOT_EVALUATED Shannon is labelled "k = 1.50 (this k, not applied)" and "Shannon not
    applied (microelectrode)".
* **Figure size.** 183 × 125 mm is a double-column width, and 125 mm is well inside a journal
  page depth (Nature's is about 247 mm). It is not meant for a single 89 mm column.

**P5 (ledger 167): closed.**
* `write_csv` warns when the frame still holds ERROR rows (`BatchRowsFailedWarning` naming the
  file), and it is silent after `df[df.status != "ERROR"]`.
* The status and error columns are the persistent record. The justification for no comment
  header or sidecar (it breaks plain CSV readers) is reasonable.

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

# VERDICT: **GO** for Phase 6

Both Phase 5 conditions (P1, P2) are closed, as are P3–P5 and ledger 162. The rendered figures
are publication-clean, apart from Q2's one marginal overlap. Q1 is a one-line change: floor the
available voltage in the PASS/CAUTION summary, as the FAIL branch already does. It can ride with
the next compliance edit.
