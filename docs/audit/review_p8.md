# Phase 8 Review — `git log cda2133..d007772`

Status: COMPLETE

**VERDICT: NO-GO for release candidate at d007772** -- 2 BLOCKER (B1, B2), 1 MAJOR (M1), 5 MINOR (m1-m5).

Repo: .
HEAD: d007772.

## Findings

### B1 — BLOCKER — 186 raises the Current-density threshold (and the limiting current) for sub-saturation trains
`neurostim/safety/current_density.py` `butterwick_size_um`; `neurostim/data/butterwick2007.py:203-206`.

The approved invariant was "max of the two diameters -> min threshold; no geometry gets a raised
threshold". That holds only at the saturated pulse count. `threshold_A_per_cm2` gates the
single-pulse relief on the size: `if n_pulses < PULSE_COUNT_SATURATION and not small` (ledger
154 withholds relief below 200 um). Moving a ring or rectangle from its equal-area diameter
(< 200 um) to its largest dimension (>= 200 um) switches the relief **on**, up to 7x on retina.
The commit's "a larger size only lowers the threshold" and "no limiting current in the sweep
moves" are true only because the sweep uses 130 Hz x 1 s = 130 pulses (saturated).

Executed (scratch worktree at cda2133 vs HEAD, same script):
- Ring 330/270 Pt, 80 uA, 100 us, 130 Hz, n = 1 pulse: threshold 0.4155 -> **2.617 A/cm^2**,
  CD ceiling 117.48 -> **740.14 uA**, status CAUTION -> **PASS**. n = 10: 235.45 uA (was 117.48).
  n = 49: 106.8 (was 117.48). Only n >= 50 lowers.
- 336-case grid (7 geometries x 8 sizes x 3 widths x {1, 130} pulses): CD ceiling raised in
  15 cases, all 1-pulse ring/rectangle (ring250 x5.67, rect190 x5.36, rect150 x3.34, ring190 x3.27).
- 1728-case grid (all materials, ring/rect with outer 210-500 um, widths 10-1000 us, n in
  {1, 5, 20} at 50 Hz): CD ceiling raised in 684, **limiting current raised in 163**. Example:
  Pt ring 210/126 um, 10 us, 1 pulse: limiting 325.72 uA (Current density binding) ->
  **400.00 uA** (CD ceiling 325.7 -> 1608.8; Microelectrode charge/phase now binds).
  Same for ring 330/297, rect 260 at 20 pulses, etc.

The relief was measured on a 1 mm pipette (the reason ledger 154 withholds it below 200 um).
A 30 um-wide ring whose outer diameter is 330 um is not that electrode; the enclosing-sphere
diameter is a conservative choice for the d^-2 branch only, and the opposite for the relief gate.
None of the four new tests use n_pulses < 50, so nothing catches it.

Doc drift from the same cause: CHANGELOG 186 says "The threshold is now the minimum over the
equal-area diameter and the shape's largest dimension ... In practice that is the threshold at
the larger of the two" -- the code computes only the second, which is not the minimum below 50
pulses; CHANGELOG and §6 C8.1b say "no limiting current changes"; the 3c32ea6 message says "a
larger size only lowers the threshold". The §6 C8.1b digits themselves reproduce exactly
(executed at HEAD and cda2133: 0.3056 -> 0.2751, 86.4279 -> 77.7851; 7.202 -> 4.401, 52.8209;
0.2880 -> 0.2751, 82.5326; README ring 80 uA CAUTION "92.6 % used" -> FAIL "0.2829 ... 0.2751"),
because they are all at 130 pulses.

Fix: keep the regime decision per branch. Use `max(d_eq, d_largest)` for the d^-2 scaling but
gate the pulse-count relief on `min(d_eq, d_largest) >= 200` (or on the pre-186 equal-area
diameter), i.e. take `min` over both thresholds computed at the actual count, which is what the
approved rule literally says ("the minimum over the equal-area-diameter threshold and the
largest-dimension threshold"). Add a test: HEAD threshold <= cda2133 threshold for every geometry
at n in {1, 10, 49, 50, 130}.


### M1 — MAJOR — 183's coverage claims hold only at the one true chronaxie simulated (200 us)
`neurostim/models/strength_duration.py:221-229` (`NARROW_SPAN` docstring), the
`StrengthDurationFit` docstring table, `docs/audit/lapicque_coverage.txt`, CHANGELOG 183 L.

The docstring states "every design of span >= 8 covers >= 0.935 at 2-20 % noise". The
validation grid varies design and noise but fixes the true chronaxie at 200 us. Coverage
depends strongly on the true chronaxie. Executed (my own harness, same generative model:
rheobase 20 uA, multiplicative Gaussian noise; `fit_lapicque` at HEAD):

| design 20-3200 us (span 160, no caveat) | c = 50 | c = 100 | c = 150 | c = 200 | c = 300 |
|---|---|---|---|---|---|
| 2 % noise, n = 2000 | **0.835** +-0.016 | **0.909** +-0.013 | 0.951 | 0.969 | 0.986 |
| 10 % noise | **0.830** +-0.018 | **0.909** +-0.013 | 0.948 | 0.966 | 0.983 |

At c = 100 us (seed 7, 600/cell) 20-3200 covers 0.892-0.902 at every noise level, and
400-3200 / 20 % covers 0.901; none carries a caveat. Chronaxies of 50-150 us are ordinary for
myelinated axons, so this is the realistic regime, not a corner.

Cause, confirmed: `curve_fit` is unweighted while the noise is proportional to the threshold,
so the covariance assumes the wrong error model; the short widths (largest thresholds) are
the ones that pin a short chronaxie. Re-fitting the same replicates with `sigma=thresholds`
(relative weighting) and the same log-Wald interval gives 0.946 / 0.948 / 0.944 at
c = 50 / 100 / 200 us (2000 replicates, 2 % noise, 20-3200).

Fix: either weight the fit by the thresholds (`sigma=i`, which also changes the point estimate
slightly: a mover to book), or add a chronaxie axis (e.g. 50, 100, 200, 500 us) to
`scripts/lapicque_coverage.py` and restate the docstring and caveat as the measured
minimum over it. Either way the ">= 0.935" sentence is not true as written. It also appears in CHANGELOG
(183 L, "every design without the caveat covers >= 0.935 at 2-20 % noise") and §6 C8.3b
("unflagged coverage >= 0.935").

### m1 — MINOR — the narrow-design caveat's quoted "0.79-1.00" does not reproduce
`strength_duration.py:395-399`. Same script logic, seed 20260928, c = 200 us: 2000-8000 / 20 %
covers **0.755** (155 reported). At c = 100 us: **0.613** (137 reported); 50-200 at c = 600 us /
20 %: 0.825. The quoted range is one seed's point estimate at one chronaxie. Quote it as a
measured band with its conditions ("0.61-1.00 over chronaxies 100-600 us in the validation
grid"), or phrase it without a floor. The same "0.79-1.00" is in paper.md:104-105 and CHANGELOG 183 L.

### m2 — MINOR — vacuous "0-inf" intervals are reported and counted as covering
`_log_interval` (`strength_duration.py:232-245`): when `half > 745`, `exp(-half)` underflows and
the lower end prints as 0, so the "positive" log interval reads "95 % CI 0-inf us". Example (seed
183, 50-800, 20 %): rheobase 0.01811 uA, chronaxie 2.711e+05 us, SE 3.23e+08 us, CI (0.0, inf),
reported, not withheld. Per 600-replicate cell, intervals that are infinite or span > 1000x:
50-200 / 20 % at c = 200: 55 inf + 146 wide of 471; 50-800 / 20 % at c = 600: 137 inf + 131 wide
of 555. The committed coverage counts all of them as covered. Excluding them, 50-200 / 20 %
falls 0.928 -> 0.874 (seed 183) and 50-200 / 10 % at c = 600 falls 0.865 -> 0.765. Fix: withhold
(with a note) when the upper end is infinite or the ratio exceeds a stated bound, or report
coverage alongside the fraction of vacuous intervals.

### m4 — MINOR — the audit digest depends on int-vs-float input typing
`neurostim/audit.py` `compute_digest` (`json.dumps` of the raw dicts). The same calculation
entered as `StimProtocol(40, 100, 130, 2)` / `compliance_V=7` and as `(40.0, 100.0, 130.0, 2.0)`
/ `7.0` gives digests 632a8f2ce290... and 777e476f9da5...; `audit.reproduces` returns
`(True, [])` across them, so nothing is wrong semantically, but the printed "Digest" a user
compares by eye differs for identical inputs. It is why the four regenerated PDFs only match
with T and compliance typed as recovered (below). Fix: canonicalise numbers to float before
dumping (a payload version bump), or document it next to the Digest row.

### m5 — MINOR — the PDF wraps the 64-hex digest onto a second line
`neurostim/io/report.py:354`. In `neurostim_report_2.pdf` the digest renders as
"...5a18d893771879215cf" with the final "3" on the next line (same in `_B`); copy-paste yields
a broken hash. Fix: a monospace cell wide enough, or split it deliberately in two labelled halves.

### B2 — BLOCKER — the 89.4 % score of record counts 4 mutants killed only by the judgement-staleness test; the real score is 139/160 = 86.9 %, under the new 0.89 floor
`scripts/mutation.py:586-600` (`_pytest` deselects only `_OWN_RESULTS_TEST`), and
`tests/test_build_gates.py::TestTheMutationGate::test_every_judgement_still_names_a_site`
(added in 4216162, so present at 31a8db4).

A mutant placed at a site that already carries a judgement changes that site's source text, so
the staleness test no longer finds the judged fragment and fails. The harness counts that as a
kill. It is not a test of the arithmetic: it is the harness observing its own bookkeeping, which
is exactly why `_OWN_RESULTS_TEST` is deselected.

Executed: `enumerate_sites()` at 31a8db4 (28 judgements) finds 4 record mutants at judged sites,
all recorded "killed":
`G:assessment.py:1134:53882` (<= -> <), `G:assessment.py:1262:59708` (>= -> >),
`G:compliance.py:502:24741` (<= -> <), `G:current_density.py:347:16051` (> -> >=); their
judgements say "NOT proven equivalent" (2) and equivalent (2). Each re-run in a 31a8db4
worktree with the full suite:
- as the harness runs it (`--deselect` own-results test only): **1 failed, 1655 passed** -- the
  single failure is `test_every_judgement_still_names_a_site`, every time;
- with that test also deselected: **1655 passed, 0 failed**, all four.

So all four survive the real suite: generated 143 - 4 = **139/160 = 86.9 %**, below
`GENERATED_FLOOR = 0.89` set by d007772, and the same as the seed-20260929 record. The gate at
HEAD passes only because the committed JSON carries the inflated count. The 89.4 % is quoted in
paper.md, CHANGELOG, CONTRIBUTING, §10 G2, mutation.yml and the harness docstring.

Fix: deselect the staleness test (and any test that reads `scripts/mutation.py` or the results)
inside the workspace, alongside `_OWN_RESULTS_TEST`; add a harness test that a mutant at a judged
site is not killed by it; re-run the pre-registered seed 20260930 at a clean commit (it is still
un-tuned: no test was written against these four), and set the floor from that result. The 4 will
then need judgements in the results (2 already say equivalent), which also resolves m3.

### m3 — MINOR — the results of record carry no judgements
`docs/audit/mutation_results.json`: all 17 `generated_survivors` read `"judged": "not judged"`;
the judgements exist only in `JUDGEMENTS` (d007772, after the run). A reader of the record cannot
see which survivors are equivalent. Regenerate the `judged` field from `JUDGEMENTS` when writing
the rerun B2 needs.

## Verification log

- 186 per-geometry `largest_dimension_um` executed: disc 150 -> 150 (diameter); ring 330/270 ->
  330 (outer diameter; d_eq 189.74); rect 30x40 -> 50 (diagonal); band 1270x1500 -> 1965.43 =
  hypot; flat microwire d25/L100 -> 103.08 = 2 hypot(12.5, 50); hemispherical tip -> 115.24 =
  2 hypot(12.5, 56.25) (true Feret 112.5, +2.4 % over, as the commit says); sphere 150 -> d_eq
  300 used; hemisphere 150 -> d_eq 212.13 used. Definitions correct as enclosing-sphere diameters.
- 185 executed: 3000-case random sweep (disc/ring/microwire x 8 materials, with/without counter
  at 3-20 mm, compliance None/0.2-15 V): CAUTION/CAUTION 650, PASS/PASS 425, FAIL/FAIL 207,
  NOT_EVALUATED 1187 (no arrow word printed), 531 rejected inputs; **0 mismatches** between the
  detail's "-> WORD" and the check status. The status gate's literal 0.8 and
  `CAUTION_UTILISATION` agree; README transcript's compliance detail reads "-> CAUTION". Clean.
- 187 executed: `describe()` protocol line reads "80 uA x 200 us per phase"; PDF label
  "Pulse width per phase" (report.py diff); GUI label "Pulse width per phase (us)" + tooltip;
  `StimProtocol` and `assess_batch` docstrings say per phase; README comment "µA, µs per phase".
  Remaining 48 unqualified "pulse width" hits in package/README/paper are the concept (e.g.
  "depends on pulse width"), not a value label. No CLI argument names a width. Clean.
- 174 opened `papers_stim_calc_ref/mccreery1990.pdf` (title page "Charge Density and Charge Per
  Phase as Cofactors in ...", IEEE TBME 37(10)); PDF page 2 carries page number 997 and reads
  "Disk-shaped platinum stimulating electrodes ... The geometric areas of the electrode surfaces
  facing the pia were 0.01,0.02,0.1, and 0.5 cm2." `AREA_RANGE_QUOTE` matches verbatim. Same page:
  "the duration (400 us) of each [phase]", consistent with the envelope's 400 us reference. Clean.
- 183 independent-seed rerun (seed 20260928, 600/cell, c = 200 us): uncaveated cells
  0.943-0.983 (claim >= 0.935 holds at c = 200); withheld counts track the committed file
  (400-3200: 600/567/303/127; 2000-8000: 293/280/236/148); 50-200 caveated 0.923-0.958.
- 183 Weiss: 400 random designs (2-7 widths, 10 % noise, seed 5) through `fit_weiss` at HEAD and
  cda2133: `describe()` text and every field of `repr` identical once the new empty
  `coverage_caveat=''` field is removed (4 identical raises). Weiss byte-identical. Clean.
- 182/188 provenance: `mutation_results.json` records head 31a8db4, `uncommitted_paths` [],
  "commit 31a8db4 exactly", seed 20260930, 143/160 = 0.8938, named 26/26. 31a8db4 (15:30:58)
  only edits FIX_PLAN ledger 182 to pre-register seed 20260930; a record whose head is 31a8db4
  cannot predate it. `git diff 31a8db4 d007772 -- neurostim` is empty, so the record measures
  HEAD's package; only tests/test_build_gates.py changed (the floor pins).
- 17 record survivors map through HEAD `JUDGEMENTS` to 4 equivalent + 3 NOT proven + 10 REAL
  (9 distinct gaps: assessment 1675/1689 share one judgement), matching the commit and ledger 188.
  The results file itself still says `judged: "not judged"` for all 17 (judgements were added
  after the run); harmless but see m3.
- Executed the 4 "equivalent" and 2 of the 3 "NOT proven" mutants in a HEAD worktree against a
  1133-assessment + 600-fit describe() digest (sweep detects the `for scale` REAL-gap mutant:
  digest changes): all 6 leave the digest bit-identical. Consistent with the claims. compliance:839
  is equivalent for the stated reason via `return_phase_current_at_uA` (monophasic -> 0 factor;
  otherwise width = pw x ratio > 0).
- Staleness test `test_every_judgement_still_names_a_site` is non-vacuous: rewriting a judged
  fragment (`self.low < 0` -> `< 0.0`) fails it.
- Regenerated PDFs (`~/Downloads/neurostim_report_{1,2,4,A,B}.pdf`, all "Pulse width per
  phase 100 µs", package 0.16.0): re-built at HEAD with `build_report` from the recovered inputs
  (SS316LVM rings 314/216, 330/215, 330/215, 330/270, 330/215; 40/40/40/60/40 uA; 130 Hz;
  T 1.54/1.54/2/1/2 s; k 3/1/1.5/1.5/1.5; policy nominal/nominal/conservative/conservative/
  nominal; 7 V). `pdftotext -layout` text identical line for line except "Generated"; all five
  stored digests reproduced exactly by `audit.record` (1 and 2 need T = 1.54, k as float; 4 and
  A need T as float; see m4). `_B` is already at 100 µs per phase and also reproduces.
  Headlines: 1 CAUTION 81.58 uA (Chronic degradation); 2 and B CAUTION 98.44 uA; 4 CAUTION
  98.44 uA (Charge injection limit, PROVISIONAL); A FAIL 40.00 uA (Microelectrode).
- 186 on the reports: A's ring 330/270 is at 130 pulses (saturated), so B1 does not touch any
  of the five PDFs; 1 (314/216, 200 pulses) likewise.
- Regression grids (main tree, run finished 21:53:34, before 749e4c7/cd86395; HEAD then
  d007772 -- the builder may have had uncommitted edits in the tree, so residual_sweep was also
  rerun in a clean d007772 worktree with the same result): unbal_rt seed 7 1500/1500 agree, 319
  capped, 375 refused; residual_sweep 6240, 312 WW FAIL on balanced (all peak, no drift key, as
  baseline); lds_rate 16200, 0 raises; ww98 20000 clean; oracle_rt3 1200/1200 agree (477
  compliance-binding); contain 3000, 0 violations; leak 2000, 0 leaks (9 batch rows); k1 87000
  ok / 9000 rejected, 0 LDS. All match the Phase 7b baselines.

## Verdict

**NO-GO** for the release candidate at d007772.

- B1: 186 raises the Current-density threshold and limiting current below 50 pulses (163 of
  1728 grid cases move the limiting current up; e.g. Pt ring 210/126, 10 us, 1 pulse:
  325.72 -> 400.00 uA). Contradicts the approved "min threshold" decision.
- B2: 4 of the 143 recorded kills come from the judgement-staleness test alone; the real score
  is 139/160 = 86.9 % < the 0.89 floor. The published 89.4 % is not a measurement of the suite.
- M1: Lapicque ">= 0.935 uncaveated coverage" holds only at chronaxie 200 us; 0.83-0.91 at
  50-100 us; relative weighting fixes it.
- Clean: 185, 187, 174 (PDF quote verified), Weiss byte-identity, pre-registration ordering,
  equivalence claims (executed), staleness test non-vacuous, all five PDFs reproduce text and
  digest, §6 C8.1b digits, regression grids.

Process note: I do not append to `_conversation_history.md` (CLAUDE.md rule 14) because the lead's
read-only rule limits my writes to this file. Scratch worktrees removed after the run. A B1 fix
landed afterwards (cd86395); it is outside this range and not reviewed here.
