# Phase 7 Review (release, docs, CI) — `git log e2ea0ec..c1a846a`

Status: COMPLETE

Repo: .
HEAD: c1a846a. The main tree was not modified. A scratch worktree at HEAD, a clean checkout
without the gitignored paper library, as CI sees it, was created under the session
scratchpad and removed.

GitHub Actions were not run. The CI jobs were reproduced locally by simulating the runner's
missing tools:
* a `PATH` without `pdftotext`;
* a stub `PyQt6` whose import raises the `ImportError` a runner without `libEGL` gives.

## Summary

| # | Sev | Where | One line |
|---|---|---|---|
| S1 | MAJOR | .github/workflows/ci.yml `coverage` job | The job that enforces the branch floor installs **neither poppler nor the Qt runtime libraries**; only the `test` job does. Reproduced in a clean checkout without `pdftotext`: the suite passes (1532, 56 skipped), but `branch_floor.py --min 84.0 --module-min 60` **exits 1**. `neurostim/references.py` falls to 16.67 %, below the per-module floor, and the total is 84.01 %, one hundredth above its floor. With poppler present the same checkout passes. Separately, on a runner without `libEGL`, `tests/test_gui.py` errors at collection: under pytest 9.1.1, `importorskip` re-raises an `ImportError` that is not `ModuleNotFoundError`, which would fail the whole run. The gate as committed is likely red on its first GitHub run |
| S2 | MAJOR | scripts/mutation.py `JUDGED_EQUIVALENT`; CHANGELOG "8 are argued equivalent" | One of the eight is **not equivalent**. `strength_duration.py:304 "* -> /"` turns `maxfev = max_iter * 10` (2000) into 20. Executed with `fit_lapicque(..., max_iter=2)`, which gives the same 20 evaluations: **511 of 2 306 fits that succeed at the default raise**, over four designs at 0/5/20 % noise. The mutant survives only because no test fits a design that needs more than 20 evaluations. So the reported 93.75 % includes a killable survivor mislabelled as equivalent |
| S3 | MAJOR | CHANGELOG 0.16.0 recall notice | "Regenerate everything" is right, and the 7.07× headline defect is described accurately. The list of "other headline numbers" that move omits several non-conservative classes a holder of an old report most needs to know about (see below) |
| S4 | MINOR | models/strength_duration.py `fit_lapicque` | The ledger-174 "unproven" survivor (`dof >= 1 and` → `or`) points at a real false-precision mode. When the widths all sit far above the chronaxie, `curve_fit` returns a degenerate covariance. Executed: widths 2–8 ms at 5 % noise, 246 fits accepted, **124 report a near-zero SE**, and **145 of 246 CIs miss the true 200 µs** (coverage 0.41). Constant thresholds at 0.1–0.3 s give SE 0.0 and a zero-width CI at a chronaxie of 7e-11 µs. The R1 docstring warns of under-coverage generally but quotes 0.82–0.90. **Fix:** refuse, or return `None`, when the chronaxie falls well below the shortest width or the covariance is singular |
| S5 | MINOR | models/vta.py:196 (C6.5) | The `< → <=` survivor is equivalent as judged, but the guard it sits on refuses **noise-free** zero-offset data. For 200 random exact `I = k r²` designs, **64** raise "fitted threshold offset is negative" on an intercept of about −1e-14. **Fix:** a tolerance relative to the data scale |
| S6 | MINOR (author items) | CITATION.cff | Authors "neurostim-safety contributors", `repository-code: https://github.com/example/...`, no `date-released` or DOI, and `license: MIT` with LICENSE still pending. G8 ("free of placeholders") is not met. These are presumably the pending author items, so they are listed rather than scored |
| S7 | MINOR | docs/audit/mutation_results.json | The committed results record `head: e31dd81` with 9 uncommitted paths, including the four test files the run depended on. The record cannot be reproduced from any single commit. It should be re-measured at a clean commit (the weekly job will do so) |

Counts: **0 BLOCKER, 3 MAJOR, 4 MINOR** (S6 author-dependent).

---

## S3 — what the recall notice omits

The notice correctly tells every pre-0.16.0 user to regenerate. Its list of other moved
numbers covers the in-vivo derating, on-time drift, the compliance offset and counter, the
floored available voltage, and heating. It omits these, each executed or booked in §6 and
each **non-conservative** in the old release:

1. **Monophasic protocols.** The old release applied biphasic CICs and reported the water
   window as PASS with 0.58 V headroom. It now refuses a number: Charge balance FAILs, the
   drift clause FAILs at 0.256 s, and the headline was 15.3 mA before (ledgers 2 and 84).
2. **Asymmetric return phases.** The return phase was never evaluated. The clinical band
   at r = 0.2 went from 15285.51 to 9565.66 µA (ledger 4), and compliance for the return
   phase from 0.52 V to 2.59 V at the time.
3. **Continuous or any unbalanced train.** It now refuses a number, or FAILs on drift,
   where the old release printed a limit (ledgers 3, 99, 105).
4. **Immersed-electrode access resistance.** Band and microwire resistance went ×2/π
   (C3.1). The compliance ceiling rises, and the DBS worked example's binding check moves
   from compliance to Shannon.
5. **Planar field and VTA values double** (C3.1, 22.74 → 45.47 mV), on every field panel and
   `potential_V` call for disc, ring and rectangle.
6. **Status vocabulary.** Macroelectrodes now show PASS/CAUTION where they showed
   NOT_EVALUATED. A monopolar Compliance check is never PASS. A non-disc Shannon check is
   never an unqualified PASS.

**Fix:** add these as bullets, each with its one-line example.

---

## Verification of the focus items

**(1) The 8 "equivalent" mutants.** Each was read at its site in e31dd81 and argued or
executed:

| Site | Mutant | Finding |
|---|---|---|
| field.py:131 | `or` → `and` | **Equivalent.** A 0-d array result is `np.float64`, a `float` subclass. It differs only in `type(x) is float` |
| strength_duration.py:304 | `* → /` | **NOT equivalent (S2)** |
| strength_duration.py:304 | `10 → 20` | Equivalent in practice. `maxfev` 4000 against 2000 never binds for accepted fits |
| vta.py:196 | `< → <=` | Equivalent. It differs only at an exact 0.0 intercept (but see S5) |
| _limits.py:356 | `18 → 36` | Equivalent. The loop always returns within 17 places |
| compliance.py:500 | `<= → <` | Equivalent. At equality both branches give `cap/active_slope`, and `floor_to_pass` settles any ulp |
| compliance.py:736 | `and → or` | Equivalent. `validate_counter` runs first and forbids half an input |
| current_density.py:204 | `> → >=` | Equivalent. A biphasic return phase with current has positive width |
| The unproven one | `dof >= 1 and` → `or` | Real behaviour (S4) |
| envelope.py:78 | area range | Correctly left as a gap (ledger 174) |

`mutation.py --check-anchors`: "all 26 named anchors occur exactly once".

**(2) G3 tests assert independent values.**
* Read: every test in `test_model_contracts.py` checks one of:
  * a closed form (CEM43's 2× and 0.25×, 1/(2W), 1/V_f, 1/r, the midpoint cancellation);
  * a published number (the IT'IS 0.013294 1/s, the 5.639 mW, Rose's BaTiO3 case);
  * a guard's own message.
* Five scratch mutants on the covered modules:
  * CEM43 R below 43 → 0.3: killed.
  * Ta capacitance ∝ V_f^-1.1: killed.
  * `1/(2.1W)`: killed.
  * Perfusion ÷ 61: killed.
  * VTA negative-offset guard disabled: **survives `test_model_contracts.py`, killed by
    the full suite**.
* The G3 file tests contracts rather than merely executing code. Some guards are pinned
  only elsewhere.

**(3) mypy fixes (506c589).** 16 assertions removed and 70 added. Every removed one returns
in a stronger form, `x is not None and <original>`. There are no new `type: ignore` or
`cast`. Nothing is weakened.

**(4) CI workflows.**
* **Test job:**
  * matrix 3.10–3.14 on Ubuntu plus macOS 3.12;
  * poppler and the Qt libraries installed;
  * pip cache;
  * `permissions: contents: read`.
* **Python 3.10.** Every source, test, script and example compiles under the locally
  installed CPython 3.10.0 and 3.11.16. A search found no 3.11+ stdlib API.
* **Lint job:** `fetch-depth: 0` for the ledger gate.
* **Literature job:** it runs `verify_transcriptions.py` informationally, which is correct
  since the papers are not redistributed.
* **Mutation workflow:** weekly and dispatch, a 300 min timeout, the system libraries
  installed, and anchors checked before the run.
* **Coverage job:** S1.
* Not verifiable without network: that the exact pins (pytest 9.1.1, mypy 2.3.0, coverage
  7.16.1, ruff 0.16.1) and PyQt6 install on 3.10 and 3.14.

**(5) CHANGELOG.** The 7.07× defect, the affected-versions statement and the
"Reproducibility section" tell-tale are accurate. Its numbers reproduce:
* ÷14 → ÷9.11 is ×1.536;
* 0.326 → 0.589 V;
* 1.006 → 1.349 V;
* 3.435 → 8.061 mK.

Omissions are S3; the mutation claim is S2.

**(6) README / CITATION / CONTRIBUTING.**
* `__version__`, `pyproject` and CITATION all say 0.16.0, and `__version__` reads
  `importlib.metadata`.
* The CITATION thermal sentence now states the 0.83 K against 0.82 K reproduction, not
  "validated", consistent with my Phase 6 independent solve (0.80 K).
* CONTRIBUTING's release commands match the CI steps.
* README `--check` passes.
* Placeholders remain (S6).

**(7) JOSS readiness beyond the pending LICENSE, paper and CoC:**
* the CITATION placeholders (S6);
* the coverage job likely red on first push (S1);
* a committed mutation record not tied to a clean commit (S7);
* no hosted or API documentation beyond README and docstrings. JOSS accepts a thorough
  README plus docstrings, but reviewers will look for an API reference;
* the paper library cannot be redistributed, so the release gate `--require-papers` is
  local-only. That is disclosed in CONTRIBUTING and the workflow, which is the honest
  arrangement.

**(8) Regression grids (executed at HEAD):**

| Grid | Result |
|---|---|
| Unbalanced sweep | 1 500/1 500 agree, 319 capped, all FAIL |
| Residual sweep | 6 240/6 240 |
| lds_rate | 0 of 16 200 |
| ww98 | 20 000, clean |
| Mixed geometries with counters | 1 200/1 200 |
| Containment | 0 of 3 000 outside |
| inf/nan leak scan | 300 configurations, 0 leaks |
| K1 far-side sweep | 0 of 96 000 raise |

## Process note
Per the brief, this review wrote only this file. The reviewer did not update
`_conversation_history.md` (CLAUDE.md rule 14).

# VERDICT: **GO** for a release candidate, conditional on the pending author items and three fixes

The numerical core is unchanged and clean on every regression grid. The documentation now
describes the code, the version is single-sourced, and the mypy work strengthened rather than
weakened the tests.

Before tagging the RC:
1. **S1.** Install poppler and the Qt runtime libraries in the coverage job, as the test job
   does. Consider leaving more than 0.01 % of headroom on the floor.
2. **S2.** Move the `maxfev` `* → /` mutant out of `JUDGED_EQUIVALENT`, add a fit that needs
   more than 20 evaluations, and restate 93.75 %.
3. **S3.** Add the omitted non-conservative classes to the recall notice's list.

S4–S7 can ride with the RC; S6 closes with the author items.
