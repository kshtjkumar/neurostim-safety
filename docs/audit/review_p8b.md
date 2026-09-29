# Phase 8b Review — `git log d007772..227d60d` (final round)

Status: COMPLETE

**VERDICT: GO for release candidate at 227d60d** -- 0 BLOCKER, 0 MAJOR, 3 MINOR (n1-n3). All Phase 8 findings (B1, B2, M1, m1-m5) verified closed by execution.

Repo: .. HEAD 227d60d. All executions in a clean
detached worktree of 227d60d (scratchpad wt8b); baseline worktree at cda2133 (wt0).

## Findings

No BLOCKER or MAJOR. Three MINOR, none affecting a computed safety number:


### n1 — MINOR — two stale Lapicque coverage sentences survive the rewrite
`neurostim/models/strength_duration.py:125-129` (StrengthDurationFit docstring, first paragraph:
"0.82 at 20 % noise with widths only 50-200 us, 0.85 with widths only 400-3200 us, 0.90 at 10 %
noise on 50-200 us", ledger 170's unweighted linear-interval figures) and `:366` (`fit_lapicque`
docstring: "0.82 and 0.85 in the cases StrengthDurationFit lists"). The same docstring's table
now gives 0.687-1.000 for 400-3200 and 0.725-0.988 for 50-200. Numbers describe a superseded
estimator; no computed value is wrong. Fix: delete or replace with a pointer to the table.

### n2 — MINOR (pre-existing, not introduced in range) — numpy scalar inputs crash the audit record and PDF
`neurostim/audit.py:118` / `neurostim/safety/_limits.py:303`. `RingElectrode(np.int64(330), 215,
...)` makes `Check.provisional` a `numpy.bool` and the limiting current a `numpy.float64`;
`audit.record` (hence `build_report`) then raises `TypeError: Object of type bool is not JSON
serializable`. `compliance_V=np.float32(7)` makes `assess()` raise `TypeError: conversion from
numpy.float32 to Decimal is not supported`. Identical at cda2133. Loud, never a wrong number;
v5's float canonicalisation (m4) does not reach it because the crash is earlier. Fix: coerce
geometry/protocol/setting scalars with `float()` at construction.

### n3 — MINOR — the two uncertainty.py:81 "equivalent" judgements rest on a false premise
`scripts/mutation.py` JUDGEMENTS for `return cls(mean - k * sd, mean + k * sd)` (`+ -> -`, and the
new `- -> +`): "sd and k are checked finite above, so k*sd is finite". Finite k and sd can
overflow: `Interval.from_mean_sd(inf, 1e200, 1e200)` computes `inf - inf = nan` and raises
"Interval bounds must not be NaN, got [nan, inf]" (executed); the `- -> +` mutant returns
`[inf, inf]` instead, so it is not equivalent at k*sd > 1.8e308. Unreachable from any safety
path, so the score is unaffected in practice; relabel both "NOT proven (equivalent unless k*sd
overflows)". shannon.py:273 (`2.0 -> 4.0` in `_metric_plateau_uC`) is labelled NOT proven, which
is accurate: the plateau width is only read on the descend-across-plateau path.

## Verification log
- B1 (cd86395) executed, 227d60d vs cda2133, same scripts:
  - 6804-case grid (9 shapes incl. two ring widths, flat and hemispherical microwire, sphere,
    hemisphere, band; 12 sizes 20-1000 um straddling 200; Pt/AIROF/TiN; 10/100/500 us;
    n = 1, 3, 10, 30, 49, 50, 130): CD ceiling raised **0**, limiting current raised **0**,
    CD lowered 1638.
  - The Phase 8 1728-case grid (all 9 materials, ring/rect 210-500 um, n 1/5/20): raised **0**
    (CD and limit), lowered 396. Was 684 CD / 163 limit raised at d007772.
  - Ring 330/270 Pt, 80 uA, 100 us: n = 1-20 back to 0.4155 A/cm^2, 117.48 uA (cda2133 value);
    n = 49/50 0.3777/0.3739 (lower than cda2133's 0.4155).
  - Every Butterwick call site goes through `butterwick_size_candidates` + `_lowest_comparison`
    (assessment.py:2107; return phase uses the same candidates); the ceiling back-solve reads the
    result's thresholds (assessment.py:1228-1270). B1 CLOSED.
- M1/m1/m2 (b77e594, 9fbf8f2) executed at 227d60d, my harness, independent seed 424242, 600
  replicates/cell, chronaxie 50/100/200/500 us x 5 designs x 4 noise levels:
  - Weighting present (`sigma=i`). Span >= 8 (uncaveated) minimum **0.692** (400-3200, c = 50,
    20 %); quoted "0.69-1.00" reproduces. 20-3200 / 20 % 0.888-0.930, 50-800 >= 0.928 (per-design
    table minima 0.918 / 0.943 are one-seed minima; mine are 1-2 SE lower, within sampling noise
    of a minimum over 16 cells; the headline range holds). Before the fix 20-3200 covered 0.835 at
    c = 50 at 2 % noise; now 0.965.
  - Caveated span-4 designs go as low as 0.172 (2000-8000, c = 50, 20 %); the caveat now says
    "can be far below nominal" with no floor -- honest. m1 CLOSED.
  - Vacuous intervals: 0 reported intervals with upper end inf, lower end <= 0, or ratio > 1000
    across all 80 cells (were up to 268/555). m2 CLOSED.
  - Docs: NARROW_SPAN/VACUOUS_RATIO docstrings, class table, CHANGELOG, paper.md:103-108,
    README:138-143 consistent with this, except n1. M1 CLOSED.
- Core-safety regression, 227d60d vs cda2133, 4000 random assessments (7 shapes x 9 materials,
  mono/biphasic, polarity, return ratio 1-4, recovery 0.9-1.05, IPG, duty 0.5, counters,
  compliance, k 1.5-2, all 3 policies, n from 1 pulse to continuous): 578 identical refusals, 0
  refusal differences; of 3422 assessed, **only Current density changes** (301 rows); limiting
  current raised **0**, lowered 53, every one of them now bound by Current density; CD status
  moves PASS->CAUTION 29, CAUTION->FAIL 22, PASS->FAIL 19 and nothing in the other direction;
  overall status CAUTION->FAIL 10, nothing looser. No other check's status or ceiling moved.
- m4 (2fb74b8) executed: `record()` writes payload version 5; `(40, 100, 130, 2)/7` and
  `(40.0, ...)/7.0` now give the same digest. Old records: 3 records written at cda2133 (v4) load
  at HEAD with `digest_matches` True (v4 digest recomputed the v4 way); `reproduces` reports only
  the model-constant hashes of compliance and envelope (the 185 verdict constant and 174 citation
  constants), plus for the ring 330/270 at 130 pulses the intended 186 mover (CD ceiling 86.43 ->
  77.79, CAUTION -> FAIL). That is the documented semantics. v5 records reproduce at HEAD.
- m5 (bb1a114) executed: the five report PDFs re-built at 227d60d from the recovered inputs; the
  digest is set in Courier (pdffonts) and on one line in all five (pdftotext); page 1 of report 2
  rendered at 80 dpi and inspected: digest on one line inside the table, nothing clipped.
- Regression grids, all in the clean 227d60d worktree (`git status` empty): residual_sweep 6240,
  312 WW FAIL on balanced (baseline); lds_rate 16200, 0 raises; ww98 20000 clean. The scratch
  scripts unbal_rt, oracle_rt3, contain, leak and k1 had been deleted from the scratchpad again;
  in their place I wrote `rt8b.py` (the refusal contract round-trip, which those covered): 1500
  random assessments (5 shapes x 9 materials, counters, compliance, 3 policies, 1 pulse to
  continuous, seed 8, 385 inputs refused): at the limiting current **0** limit-bearing FAILs; at
  1.02x the limit a limit-bearing FAIL in **1500/1500**; 0 infinite limits; `report_to_json`
  strict-parses in 1500/1500. The 4000-case core grid and the 6804/1728-case B1 grids above cover
  the remaining regression vs cda2133.
- B2 (de4052e, c71d4b8): `HARNESS_TESTS = ("tests/test_build_gates.py::TestTheMutationGate",)`
  deselected in every workspace pytest (scripts/mutation.py:600-615). Record: head 31a8db4, seed
  20260930, 137/160 = 0.8562 (135 killed + 2 timeouts, counted as kills by the harness, both
  `_limits.py:202`), 23 survivors all judged (10 REAL, 7 equivalent, 6 NOT proven), `corrections`
  field explains 143 -> 139 -> 137; `GENERATED_FLOOR = 0.85`; paper, CHANGELOG, CONTRIBUTING, §10
  G2, harness docstring all quote 85.6 %. No stale 89.4 / 86.9 left as current.
- B2 spot-check at 227d60d (lead's instruction; full independent run stopped at 101/186): 10
  mutants through the harness's own `run_one` (HARNESS_TESTS deselected) in clean clones of
  227d60d: the 6 reclassified -- assessment 1134, assessment 1262, compliance 502,
  current_density 347 (now line 372, same judged fragment), shannon 273, uncertainty 81 --
  **all survived** the full suite (233-418 s each); 4 randomly drawn recorded kills (protocol 384,
  _limits 272, field 252, envelope 172) **all killed**. From the stopped run: named 26/26 killed,
  and the 25 generated mutants that also appear in the record agree with it. B2 CLOSED;
  record and floor consistent. See n3 for the uncertainty:81 wording.

## Verdict

**GO** for the release candidate at 227d60d.

- B1 closed: 0 raised thresholds or limiting currents vs cda2133 over 6804 + 1728 + 4000 cases,
  every pulse count; only Current density moves, always stricter.
- B2 closed: harness deselects its own tests; 137/160 record and 0.85 floor consistent with a
  10-mutant spot-check at HEAD.
- M1/m1/m2 closed: weighted fit; quoted 0.69-1.00 reproduces on an independent seed across
  chronaxies 50-500 us; caveat has no floor; no vacuous interval reported.
- m3/m4/m5 closed: judged record; v5 float-canonical digest, old records still verify; digest on
  one line in Courier.
- Open, MINOR only: n1 stale Lapicque sentences (strength_duration.py:125-129, :366); n2 numpy
  scalar inputs crash the audit record/PDF (pre-existing, loud); n3 uncertainty:81 judgement
  premise false at k*sd overflow (unreachable from safety paths).

Process note: I do not append to `_conversation_history.md` (CLAUDE.md rule 14); the lead's
read-only rule limits my writes to this report. Scratch worktrees and clones removed.
