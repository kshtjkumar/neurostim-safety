# Phase 7b Review — `git log c1a846a..408af5b`

Status: COMPLETE

Repo: .
HEAD: 408af5b. The main tree was not modified. A clean scratch worktree was used for the
coverage check and then removed.

## Summary

| # | Sev | Where | One line |
|---|---|---|---|
| T1 | MINOR | models/strength_duration.py (S4 fix) | The new identifiability rule removes every near-zero SE and never withholds on an informative design (0–1 of 600 withheld on 50–800, 20–3200 and 50–200 µs designs). But on the non-identifiable long design (widths 2–8 ms) the CIs it still reports cover only **0.71–0.86** (5 % noise: 0.705 over n = 149), against 0.41 before. The cut, the singular-value ratio at √ε, is a numerical-rank test, so it catches only the fully degenerate fits. The docstring's under-coverage warning covers this; a stricter cut (for example the ratio against 1e-3) would withhold the rest |
| T2 | MINOR (process / G2) | scripts/mutation.py `GENERATED_FLOOR` | The official pre-registered score is **86.9 %** (139/160, seed 20260929, measured at clean 02bfdc7). The gate was lowered from 0.90 to 0.86 to match it. Exit criterion G2 (≥ 90 %) is therefore **not met**, only held against regression. That was the user's decision, and it is recorded as ledger 182 |
| T3 | MINOR | official survivors (not judged) | Among the 21 survivors of seed 20260929, several are real test gaps rather than equivalents: `uncertainty.py:81` (`from_mean_sd`'s upper bound, both `+ → -` and `* → /`, so no test checks its width); `charge.py:101` (`cic_max_current_uA`'s `<=` boundary); `compliance.py:698` (`evaluate`'s negative-lead guard, reachable through the module API); `assessment.py:568` (`monotonicity_capped` at exact equality, reachable on Ta2O5 where the cap binds at equality). All are bounded by ledger 182. None changes a package number, since every one is a boundary, a guard or a width |

Counts: **0 BLOCKER, 0 MAJOR, 3 MINOR.**

## Verification of the focus items

**(1) S1, CI (ledger 175): closed.**
* The coverage job now installs poppler and the Qt runtime libraries, as the test job does.
* `test_gui.py` calls `importorskip(..., exc_type=ImportError)`. Executed with a stub PyQt6
  whose import raises ImportError, as a runner without libEGL would: 1 skipped, no
  collection error.
* Clean checkout, no paper library, poppler and Qt present (the CI coverage job as written
  now): 1 613 passed, 27 skipped; `branch_floor.py --min 84.0 --module-min 60` **OK at
  85.71 %** (570/665).
* **api-docs job:** `pdoc==16.0.0` is pinned in `dev`. `scripts/build_api_docs.py
  --output-dir <tmp>` with `QT_QPA_PLATFORM=offscreen` exits 0: **53 pages for 52
  modules**, every warning an error. The script walks `pkgutil.walk_packages`, skips only
  `__main__`, and raises if any module is left uncovered.
* Not verifiable without network: that the pins and PyQt6 install on the runners.

**(2) S3, recall notice (ledger 177): complete.** The notice now has a separate "not
conservative" list. It covers every class from my Phase 7 S3 and more:
* monophasic;
* asymmetric return phase;
* zero-ceiling and continuous trains;
* the riding-charge drift;
* ×2/π and ×π/2 access resistance;
* planar field ×2;
* Butterwick below 200 µm;
* over-recovery drift C;
* early transients;
* status vocabulary.

Spot-checked at HEAD:
* return ratio 0.2 band: compliance 1.647 V and limit 9565.66 µA (Current density), as
  stated ("0.52 → 1.65 V");
* `mccreery_microelectrode` at 10 µA / 100 µs, one pulse: Current density ceiling
  117.48 µA;
* transient at 0.1 s (1 mW, 500 µm, brain): 0.0640 K.

**(3) S4, Lapicque identifiability (ledger 178).** 600 replicates per cell:

```
design          noise  accepted refused withheld  coverage of reported CIs  near-zero SE
long 2-8 ms     0.02     300      300     188       0.759 (n=112)               0
long 2-8 ms     0.05     284      316     135       0.705 (n=149)               0
long 2-8 ms     0.20     322      278     128       0.861 (n=194)               0
long 400-3200   0.02     600        0       0       0.938                       0
long 400-3200   0.05     585       15      12       0.934                       0
long 400-3200   0.20     438      162      62       0.955                       0
50-800 x6       0.02/.05/.20  600/600/600  0/0/1   0.960 / 0.930 / 0.912        0
20-3200 x8      0.02/.05/.20  600/600/599  0/0/0   0.982 / 0.987 / 0.932        0
50-200 x4       0.02/.05/.20  600/600/497  0/0/1   0.933 / 0.925 / 0.829        0
```

It does not over-withhold on informative designs. What remains is T1.

**(4) S5, VTA tolerance (ledger 179): sound.**
* 0 of 1 000 exact zero-offset designs refused (64 of 200 before).
* The tolerance is `√ε · max(I)`. For thresholds up to 320 µA that is 4.8e-6 µA: −1e-6 and
  −1e-9 µA offsets are zeroed, while −1e-3 µA is still refused.
* An offset that small is below any measurement's resolution, so no physically meaningful
  negative offset can be masked.

**(5) Mutation provenance (ledgers 176, 181, 182).**
* **S2 fixed.** The maxfev `* → /` mutant is no longer judged equivalent. d6ac5d3 adds a fit
  needing more than 20 evaluations.
* **Three records**, each with `uncommitted_paths: []` and `measured: "commit X exactly"`:

  | Seed | Status | Measured at | Score | Record |
  |---|---|---|---|---|
  | 20260927 | tuned | 1a47bd4 | 93.13 % | `mutation_results_seed20260927_tuned.json` |
  | 20260928 | fresh | 90c5cf1 | 80.63 % | `mutation_results_seed20260928.json` |
  | 20260929 | official | 02bfdc7 | 86.88 % | `mutation_results.json` |

* **Pre-registration.** Each fresh seed is named "PRE-REGISTERED, before any run with it" in
  the commit message of the very commit it was measured at: 20260928 in 90c5cf1 at 19:57,
  20260929 in 02bfdc7 at 23:55. The official record is dated 2026-09-28, after 02bfdc7.
  The chain is consistent. A trial run before the pre-registration commit cannot be
  excluded from the repository alone.
* **The new equivalence claims.**
  * Six are marked "NOT proven equivalent" and honestly say so.
  * The rest were argued, and each argument holds:
    * `_limits.py:184` (reach 0 raises either way);
    * `assessment.py:246` (the rank value only orders statuses);
    * `assessment.py:2314` (counter_result is None exactly when there is no counter);
    * `charge.py:301` (fold 1 prints nothing);
    * `compliance.py:820` (a zero return factor gives 0 V either way);
    * `current_density.py:329` (width comparison);
    * `field.py:111` (np.float64).
* The official survivors that are not judged are T3.

**(6) API docs.** See (1): the build is clean and covers all 52 modules.

**(7) Regression grids (executed at HEAD).** Three scripts lost from the scratchpad
(residual, lds_rate, ww98) were recreated from their Phase 2 definitions.

| Grid | Result |
|---|---|
| Unbalanced sweep | 1 500/1 500 agree, 319 capped, all FAIL |
| Residual sweep | 6 240 balanced configurations. No drift anywhere: all 312 Water window FAILs are genuine peak-clause FAILs at high current, and none is a drift FAIL on a balanced pulse |
| lds_rate | 0 of 16 200 raise |
| ww98 | 20 000 edge-clustered configurations: 0 raises, 0 ceilings failing their predicate, 0 passing successors, 0 status/ceiling disagreements |
| Mixed geometries with counters | 1 200/1 200 agree with the bisection oracle |
| Containment | 0 of 3 000 outside |
| inf/nan leak scan | 300 configurations, 0 leaks |
| K1 far-side sweep | 0 of 96 000 raise |

## Process note
Per the brief, this review wrote only this file. The reviewer did not update
`_conversation_history.md` (CLAUDE.md rule 14).

# VERDICT: **GO** for the release candidate, conditional on the pending author items

The author items are LICENSE, paper.md, the code of conduct, and the CITATION authors,
repository, date and DOI.

All three Phase 7 conditions are closed:
* the coverage job passes in a clean CI-like checkout at 85.71 %;
* the mutation record is honest: each record is from a clean commit, the seeds were
  pre-registered in the measured commit, and no survivor is falsely called equivalent;
* the recall notice now lists every non-conservative class.

The API reference builds cleanly over all 52 modules, and no regression grid moved.

The MINORs:
* T1 is a coverage caveat already documented.
* T2 records that G2 is held at 86.9 % rather than met at 90 %, by the user's decision.
* T3 lists the real survivors ledger 182 should close.

None blocks the RC.
