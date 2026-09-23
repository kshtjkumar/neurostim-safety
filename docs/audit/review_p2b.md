# Phase 2b Review — `git log e07114d..39331bf`

Status: COMPLETE

Repo: .
HEAD: 39331bf (master). The main tree was not modified. Scratch worktrees under the session
scratchpad were created and removed.

## Commits in scope
```
39331bf docs(ledger): record the commit that closed 107
3bd56f0 docs,feat(gui): write down what Phase 2 changed, and give train_duty_cycle its form input   (107, F5)
d92a8ff docs(ledger): record the commit that closed 106
4dbca6e docs(plan): book every Phase 2 mover section 6 missed, with the package's own digits          (106, F4)
0e605ce docs(ledger): record the commit that closed 105 and 110
1fc2cbc fix(safety): spend the drift budget on the pulse that rides on the offset first              (105, F3; 110)
24edb39 docs(ledger): record the commit that closed 103, 104, 112 and 115
f4f08b8 fix(protocol): compute the unrecovered charge as one product, and gate drift on balance      (103, 104, 112, 115, 117-nan)
c339ce0 docs: log the Phase 2 review's sixteen findings, preserve the review
```

## Gates at HEAD (executed)
* `pytest -q`: **908 passed** (85 s). `ruff`: clean. `mypy neurostim`: clean (53 files).
* `ledger_check.py`: OK, 118 entries. `regenerate_example_output.py --check`: README transcript
  matches.

## Summary

| # | Sev | Where | One line |
|---|---|---|---|
| G1 | MINOR | water_window.py:369-429 | The module-level `water_window.evaluate` still reproduces both F1 (drift on a "balanced" pulse) and F3 (a new `recovered_charge_uC = 0.0` default gives the old anti-conservative budget). Only `SafetyCalculator.assess` is gated. Belongs in ledger 117 (C4.2) |
| G2 | MINOR | assessment.py:1963 | `report()["net_dc_current_uA"]` prints a non-zero DC (1.04e-12 µA) for a protocol that Charge balance and Water window both treat as balanced |
| G3 | MINOR | FIX_PLAN_v2.md §6 C2.2 [106] row | The row labels the fixture `compliance_V = 250`, while ledger 4's case is `capacitance_uF_cm2 = 250`. The value is unaffected (executed under both settings and with neither) |
| G4 | MINOR | README.md:238-240 | A pre-existing "pure double-layer capacitance" bullet contradicts `water_window.py`'s CIC-derived `C_eff`. It now sits directly above the new DC-drift bullet |
| G5 | MINOR | FIX_PLAN_v2.md §9 | Scheduling comments: 108 at C5.11 is late for a verdict-contradicting text; 113 has no commit |

Counts: **0 BLOCKER, 0 MAJOR, 5 MINOR.** No regression found.

---

## Verification of the builder's claims

### f4f08b8: F1, F2, F10, F13 and the nan part of F15 — **CLOSED**

`net_charge_at_uA = charge_uC(I, W) * (1 - recovered_fraction)` (`protocol.py:319`) and
`is_charge_balanced = |1 - r_a| <= 1e-12` (`protocol.py:343`). The water window receives
`0.0` net DC whenever `is_charge_balanced` (`assessment.py:1826-1828`). The seed raises
`LimitDidNotSettle` instead of producing `nan` (`assessment.py:881-886`).

I re-ran my Phase 2 grids unchanged:

```
residual_sweep (6 240 balanced, r in 13 ratios, T in {inf,3600,1}): exact-zero net 6240, 0 raises,
                                                                    0 spurious WW verdicts, 0 limits above a FAIL
lds_rate (16 200 ordinary partial-recovery): 0 raises          (was 576 at e07114d)
lds_repro (500 um Pt, 10 uA/50 us/130 Hz, r_a 0.99 and 0.999): ok, ok
ww98 edge-clustered, 20 000 then 60 000 configurations: 0 raises, 0 ceilings failing their own
  predicate, 0 passing successors, 0 fails sampled below a ceiling, 0 status/ceiling disagreements
```

**Independent round-trip.** I drew 1 500 random configurations: 9 materials, diameter
20–2000 µm, r_a ∈ {0, .3, .5, .9, .99, .999, 1−1e-9, 1−5e-13, 1.05, 1.5},
r ∈ {1, .3, .7, 3}, T ∈ {0.05, 1, 10, 3600, inf}, mixed polarity and 10 % monophasic. For each,
the package's own-check ceiling was compared with `oracles.fail_ceiling_uA(names=LIMIT_BEARING)`,
a bisection over `assess().failed`. Result: **1 267 agree to rel 1e-9, 233 are both zero, 0
disagree, 0 `NonMonotonePredicate`.** At e07114d the same oracle raised `NonMonotonePredicate`
on the F1 case.

**D3 invariant.** Over 768 configurations (Pt, SIROF, Ta2O5, PEDOT; r_a including 1−5e-13 and
1−2e-12; r ∈ {0.3, 1, 3}; both waveforms; T ∈ {1, inf}), no non-limit-bearing verdict moves
between 1e-12 and 1e6 µA. Nothing raises. F10 is closed.

**What moved.** I ran a 10 368-configuration water-window grid at e07114d and at 24edb39
(F1 only). 2 544 ceilings moved, by at most **1.93e-14 relative**. 48 configurations that
raised `LimitDidNotSettle` now return numbers. This matches the C2.8 row's "last-digit moves
only". The row's example reproduces exactly: AIROF 40 µm, 50 µs, r_a 0.9, 1 s, 19.332877868244893
at e07114d and 19.332877868244886 at 24edb39.

**Is the gate placement sufficient?** Every package path that renders a verdict goes through
`SafetyCalculator.assess`. I executed a near-balanced continuous protocol
(`r_a = 1−5e-13`, `DiscElectrode(500,"Pt")`, T = inf) through each of them:

```
assess: Water window PASS, Charge balance PASS, limit 490.87385212340524
sensitivity.analyse: 4 rows, no raise
assess_batch: status CAUTION, limiting_current_uA 490.87385212340524, mechanism Chronic degradation
```

The GUI builds a `SafetyCalculator`, so it is gated the same way. The gate is sufficient for
package output. The remaining gaps are G1 (public module API) and G2 (a `report()` column).

Mutants: removing the gate is killed. The `nan` guard is pinned by
`test_the_seed_refuses_a_drift_it_cannot_invert`. Non-vacuity: with the package at f4f08b8^,
all 8 tests in `TestTheUnrecoveredChargeIsExactlyLinear` fail.

### 1fc2cbc: F3 — **CLOSED**

**Physics.** Under the capacitive model, pulse n's leading phase peaks at
`offset(n−1) + e = offset(n) + r_a·e`, so the offset can spend `Q_window − r_a·Q`. The code
implements exactly that: `DcDrift.time_to_exit_s = max(Qw − riding, 0)/|I_dc|`, with
`riding = r_a·Q` only when the offset heads for the leading edge. The seed inverts it exactly:
`Qw / (r_a·W + (1−r_a)·W·f·T)` per µA.

I derived the discrete exit pulse by hand as `floor(n*) + 1`, where
`n* = (Qw − r_a·Q)/((1−r_a)·Q)`. That agrees with the closed form to within one pulse.
Over-recovery (drift toward the opposite edge, nothing riding) is also correct: the return
phase's trough is the offset itself.

**Oracle independence.** `partial_recovery_exit_time_s` (`tests/oracles/drift.py:91-132`)
imports nothing from `neurostim` and evaluates no closed form. It steps the potential through
both phases of every pulse and checks the leading edge after the leading phase and the
opposite edge after the return phase. It is genuinely independent.

**Package against oracle.** I compared 2 516 random configurations: Pt, PtIr, SIROF, AIROF,
TiN; random in-window resting potentials; both polarities; r_a ∈ {0, .3, .8, .95, .99, 1.02,
1.2, 1.8}. **Every drift time is within one pulse** (max |Δ| = 0.99986 pulses). 441 were
excluded because the peak clause fails; 43 exceed 2 M pulses in the oracle.

**The review case.** Water window: CAUTION "2.4 s" became **FAIL "0.42 s"**. Ceiling:
**1472.6215563702156 → 988.3366150135672 µA**. Both exact.

**"None rise".** I ran my own 10 368-configuration grid at 24edb39 and at 1fc2cbc:
**3 072 ceilings fall, 0 rise**, and 16 verdicts go CAUTION → FAIL (none in the other
direction). The builder's 2 090 of 9 504 is a different grid. The direction claim holds on
mine. The C2.9 example reproduces: Pt 500 µm, 50 µs, r_a 0.5, 1 s:
90.62286500739789 → 89.93108741192157.

**The 2× → 260/131 change.** The ceiling ratio to monophasic is
`fT / (r_a + (1−r_a)·fT)`. At r_a = 0.5 that is `2fT/(fT+1)`, which is 260/131 at fT = 130.
The new assertion is the model's own consequence, derived in the comment. It is not a
number chosen to make the test pass.

**Mutants.** The two survivors from my Phase 2 review now die: ignoring the over-recovery sign,
and `<` → `<=` in `exits_during_train`. So do two new mutants: riding applied to over-recovery
too, and a seed that ignores riding. Removing the `max(..., 0)` floor survives. That mutant is
equivalent: both forms give `t ≤ 0 < T`, so the verdict is FAIL either way, and the peak clause
already FAILs there. Non-vacuity: with the package at 1fc2cbc^, 3 of 5 tests fail. The two that
pass are the boundary and direction pins for code that predates this commit.

### 4dbca6e: F4 bookings — **CLOSED** (one label slip, G3)

Checked by execution, at HEAD and against the pre-change trees:

| row | booked | executed |
|---|---|---|
| C2.3 [91] | 767.2735903959689 | 767.2735903959689 |
| C2.4 | 19.634954084936204 → 0.4531143250369894, `limiting_current_uA` None, cap Chronic degradation | same |
| C2.2 [106] | 15285.50941588086 → 9565.660239570918 (Current density); 998.0887516949169 → 461.0459210402362 | 9565.660239570918 Current density |
| C2.8 | AIROF 40 µm example …893 → …886 | …893 at e07114d, …886 at 24edb39 |
| C2.9 | 1472.6215563702156 → 988.3366150135672; 90.62286500739789 → 89.93108741192157 | same |
| C2.3a / C2.4 schema | `permits_no_current`, `monotonicity_capped`, `biphasic_*` | present in JSON and attributes |

The C2.7 [98] row now also books the water-window raise-to-number movement, and ledger 115's
sentence is in D2 point 2.

### 3bd56f0: F5 — **CLOSED for committed artefacts**

* README "What it computes" table: updated for monophasic CIC NOT_EVALUATED, the drift clause
  and Charge balance semantics. Known limitations gain DC drift (no-leak bound, Merrill §2.4,
  wall-clock/duty caveat, matching ledger 109) and Monophasic.
* CHANGELOG has a Phase 2 section. Its numbers agree with execution: 0.52 → 2.59 V,
  15.3 → 9.57 mA, 0.256 s.
* `charge.py` and `water_window.py` module docstrings are updated.
* GUI: a `train_duty_cycle` spin box seeded from `DEFAULT_TRAIN_DUTY_CYCLE`, pinned by 3 tests
  that fail at 3bd56f0^.
* **example_output/**: I regenerated it to scratch and compared. All 7 artefacts are
  byte-identical to the local `example_output/`. It is gitignored by design (see the
  regenerate script's docstring), so the only way it can drift is in someone's local
  checkout. It is not shipped. The committed derived artefact is the README transcript, which
  passes `--check`. My F5 "stale example_output" point is therefore closed. It was never a
  shipped-artefact defect. The committed-document drift that remains is G4, and it predates
  Phase 2.

---

## G1 — MINOR — the public `water_window.evaluate` keeps both old behaviours

The balance gate and the riding charge are supplied only by `SafetyCalculator.assess`. A
direct caller of the module function passes `net_dc_current_uA` and may omit the new
`recovered_charge_uC`, which defaults to `0.0`:

```
p = StimProtocol(80,200,130,inf, charge_recovery_ratio=1-5e-13)   # is_charge_balanced True
ww.evaluate("Pt", ..., net_dc_current_uA=p.net_dc_current_uA, area_cm2=..., train_duration_s=inf)
  -> drift.drifts True, exits_during_train True      (assess() says PASS / PASS)
p2 = review case (1227.18 uA, r_a 0.99, 1 s), recovered_charge_uC omitted
  -> time_to_exit_s 2.3999999999999977, exits False  (assess() says 0.42 s, FAIL)
```

No package surface reaches this. It is the same argument-contract class as ledger 117, which
is scheduled at C4.2. **Fix:** at C4.2, make the drift inputs a single object or make
`recovered_charge_uC` required whenever `net_dc_current_uA` is given, and apply the balance
tolerance inside the function. Add the new default to ledger 117's text.

## G2 — MINOR — a DC column for a balanced pulse

For `r_a = 1−5e-13`, Charge balance reports PASS "fully charge-balanced" and the water window
receives 0 DC. `report()["net_dc_current_uA"]`, which is a batch CSV column, is still
`1.0400924566056348e-12`. That is harmless in size but inconsistent across one row. **Fix:**
report 0.0 when `is_charge_balanced`, or document the column as the raw residue.

## G3 — MINOR — mislabelled fixture in the C2.2 [106] row

The row says `compliance_V = 250`. Ledger 4 and my Phase 2 repro used
`capacitance_uF_cm2 = 250`. I executed all three variants (compliance 250, C 250, neither) and
each gives 9565.660239570918 µA (Current density), so no number is wrong. **Fix:** relabel.

## G4 — MINOR — README contradicts the water-window model (pre-existing)

`README.md:238-240` says the water window "models the interface as a pure double-layer
capacitance. Conservative for pseudocapacitive materials such as Pt". `water_window.py` says
the opposite: it rejects the 20 µF/cm² double-layer value and derives `C_eff` from the
material's CIC (250 µF/cm² for Pt), precisely so that pseudocapacitance is included. The
bullet predates Phase 2, but Phase 2b edited the lines around it. **Fix:** rewrite the bullet
to describe the CIC-derived `C_eff`, and ledger it if it is not already recorded.

## G5 — MINOR — scheduling comments on §9 rows 103–118

Most of the scheduling is reasonable. 103–107, 110, 112 and 115 are closed and verified above.
109, the duty-versus-wall-clock decision, is conservative and README-disclosed, with its
decision pinned to the Phase 3 start. 111, 114, 116, 117 and 118 are all named to specific
commits. Two comments:

* **108** (a FAIL check whose detail says "-> PASS … headroom +0.582 V") is scheduled at C5.11,
  about twenty commits away. It is a one-line change in `WaterWindowResult.describe()`, and it
  is the ledger-2 text reappearing under a FAIL, including in the PDF. Consider landing it with
  the first Phase 3 commit alongside 111.
* **113** is "unscheduled — fix with the next change to the interval". No commit is named, so
  it can be lost. Name one, or narrow the docstring now, which costs a single edit.

## Regression sweep (executed): nothing found

* The full suite, `ruff`, `mypy`, the ledger gate and the README transcript are all green.
* `_limits.py` and `shannon.py` are unchanged in Phase 2b, so the Phase 2 results for option A
  (byte-identical at plateau 0, Shannon exact over 100 000) carry over.
* I checked the monophasic path, the balanced symmetric goldens, ledger 2's 0.2558 s and
  767.2735903959689 µA, and the refusal contract on zero ceilings. The 1 500-configuration
  oracle round-trip and the 768-configuration invariant sweep above cover these.

## Process note
Per the brief, this review wrote only this file. The reviewer did not update
`_conversation_history.md` (CLAUDE.md rule 14).

# VERDICT: **GO** for Phase 3

Both Phase 2 BLOCKERs are fixed at their source and verified:

* 0 raises across 16 200 + 6 240 + 80 000 swept configurations.
* 0 disagreements with an independent bisection over 1 500 random configurations.
* Drift times match an independent two-phase pulse loop to within one pulse over 2 516
  configurations.

F3's physics is correct and conservative-only (0 ceilings rise). The bookings reproduce to the
digit, and the committed documentation now matches the code.

The five MINORs can ride with Phase 3. G1 should be folded into ledger 117 before C4.2 is
written.
