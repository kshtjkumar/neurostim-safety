# Phase 4b Review — `git log 507ab91..5fc68c2`

Status: COMPLETE

Repo: .
HEAD: 5fc68c2 (version 0.16.0). The main tree was not modified and no worktree was needed.
Scratch work: Leung Fig. 4 was re-digitised independently from the embedded raster (with
`pdfimages`), and the audit break attempts were in-process monkeypatches, restored after
each.

## Summary

| # | Sev | Where | One line |
|---|---|---|---|
| N1 | MINOR | audit.py `answer_of` | The v3 answer omits `limiting_current_interval_uA` (and `limiting_current_by_kind`, though that is derived from the check ceilings, which are covered). A change in the code of a band provider moves the rendered "across published ranges" line with `reproduces` still True. Executed: `shannon.max_current_interval_uA` scaled by 0.5, so the 3389 interval moved from 19949.11–28061.90 µA to 11464.13–20386.43 µA, and `reproduces(v3_record) == (True, [])`. Function bodies are not hashed (callables canonicalise to their qualname), so only the answer can catch a code change, and this answer lacks the interval |
| N2 | MINOR | audit.py `reproduces`, by design | Records at v1 and v2 compare only their stored `report()` keys, so a change confined to a single check's status is invisible to them. Executed: forcing Water window PASS → CAUTION on a SIROF disc gives v1 True, v2 True, v3 False (it names `answer.checks.Water window.status`). This is inherent to what old records stored. The docstring says results are compared "key by key", which is accurate, but it should state this limit |

Counts: **0 BLOCKER, 0 MAJOR, 2 MINOR.**

---

## Verification

**M1 (ledger 155): closed for what matters.**
* The four c89fdf4 records from my Phase 4 review, re-checked at HEAD: ring, continuous SIROF
  and TiN reproduce (their answers did not move).
* The Pt in-vivo record now **fails**, naming `package_version: '0.15.0' -> '0.16.0'`,
  `results.cic_limit_uC_cm2: 7.142857142857143 -> 10.971428571428572` and
  `results.limiting_current_uA: 70.12483601762932 -> 107.71174812307864`.

Break attempts:
* **Constant coverage.** An AST scan of every loaded `neurostim` module with capital-named
  constants: none that `neurostim.safety`, `materials`, `protocol` or `uncertainty` read is
  outside `MODEL_CONSTANT_MODULES`. The uncovered data modules (`riedy_walter1996`,
  `mccreery1990`, `elwassif2006`, `current_distribution`, `ta2o5_capacitor`, `iso14708_3`,
  `asanuma1976`, `models.*`) are imported by none of them. Their values reach the assessment,
  if at all, through the `Material` objects that `materials` holds, and those are hashed.
* **Code changes.** These are caught through the v3 answer except where the answer does not
  reach: the interval (N1).
* **Older payload versions.** See N2.

**M2 (ledger 156): closed.**
* **Independent digitisation of Fig. 4** (800 × 945 raster):
  * In-vivo zero at row 867, gridlines every 82 px per 4 µC/cm² (20.5 px per µC/cm²).
  * In-vitro zero at row 419, 6.80 px per µC/cm² (from 3200 µs = 54).
  * My centroids: in vitro 100 µs **33.57**; acute 100 µs **3.86**, 200 µs **6.00**, 400 µs
    **7.70**, 1600 µs **12.30**; intracochlear 400 µs **10.82**; subdural 400 µs **4.64**.
  * The recorded table (33.51, 3.883, 6.032, 7.692, 12.357, 10.818, and 4.63 quoted) agrees
    to within about one pixel.
* **9.11 is the maximum.** Every matched pair is smaller:
  * suprachoroidal 8.63 (Fig. 4) or 8.85–9.11 (quoted) at 100 µs;
  * about 5.7 at 200 µs;
  * chronic 4.87 at 200 µs;
  * intracochlear 3.35 at 400 µs;
  * cortex 7.84 at 400 µs.
  * 35/3.84 uses the larger in-vitro figure (abstract 35 against results 34), so it is the
    largest factor the quoted numbers support.
* **Provisional below 100 µs, executed on both electrodes.** A 500 µm Pt disc in vivo with a
  300 µm Pt counter at 50 µs sets `derating_provisional` and the check's `provisional` on both
  the active and the counter check; at 100 and 200 µs, on neither. The CIC is
  10.971428571428572 at all three widths.
* **No stale 8.7 in the package.** A search found only "8.7e17 ulps" (unrelated) and the
  CHANGELOG's historical C4.5 entry, which is followed by its 8.7 → 9.11 correction.

**M4 (ledger 158): closed.**
* `report()`, the JSON `results`, and batch rows carry `limit_is_provisional` and
  `limits_incomplete`.
* Executed: `dbs_3389` gives True/True. A monophasic row has no limit and gives None/True.
* Both keys are documented in the README (lines 76 and 79) and the CHANGELOG.

**§6 digits.**
* Pt 500 µm in vivo: `limiting_current_uA` 107.71174812307864 and CIC 10.971428571428572
  (= 100/(35/3.84)), matching the booked numbers.
* The ×0.9545 relaxation-reversal (8.7/9.11) is consistent.

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
| inf/nan leak scan | 400 configurations, 0 leaks |
| K1 far-side sweep | 0 of 96 000 raise |

## Process note
Per the brief, this review wrote only this file. The reviewer did not update
`_conversation_history.md` (CLAUDE.md rule 14).

# VERDICT: **GO** for Phase 5

All three Phase 4 conditions are met:
* An old record whose answer moved now fails and names the value.
* The in-vivo derating is Leung's largest matched factor, confirmed by an independent
  digitisation, and is provisional where he measured nothing.
* The flat report carries the qualifiers.

N1 is cheap: add the interval, and optionally the by-kind table, to `answer_of`. It should
ride with the next audit change. N2 needs one docstring sentence.
