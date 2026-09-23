# Phase 1b Review — `git diff 36d3d6b..aaf3c85`

Status: IN PROGRESS (written incrementally)

Repo: .
HEAD: aaf3c850438cbdb1d1374293b0a26c27f80a0033

## Commits in scope
```
aaf3c85 docs(ledger): record the commit that closed 96
5381185 fix(safety): floor a limit whatever its unit, and gate the constants that look round
3d74abe docs(ledger): record the commit that closed 95
7ec2006 docs(plan): book the five unbooked movers, repair 67(b), and log the render sites still raw
d1b878e docs(ledger): record the commit that closed 94
da46d4a test(verdict): stop the by-kind test restating the implementation, and say what containment proves
208a84b docs(ledger): record the commit that closed 93
a8bb45d test(limits): straddle both settle budgets so neither constant can move unnoticed
746514b docs(ledger): record the commit that closed 92
15a943c refactor(safety)!: the headline refuses in its own type, and the raw ceiling gets a name
40f50f2 docs(ledger): record the commit that partially closed 91
1292ec0 fix(safety): make the water-window seed and its predicate one change, not two
c8788f0 docs(ledger): record the commit that closed 90
658f431 fix(oracles): a refused amplitude below the bracket narrows it, it does not crash it
9dd5bda docs(ledger): record the commit that closed 89
d712995 fix(sensitivity,examples): refuse, and floor, on the two surfaces Phase 1 missed
f4276e0 docs(ledger): record the commit that closed 88
89a54b4 fix(safety): bound the climb by the predicate's own resolution, not by the seed
5652949 docs: preserve Phase 1 review and reports
```

## Findings so far
(none yet — reading)

---

## 1. The settle mechanism (B1/F2)

### 1(a) Is the plateau expression correct?

`neurostim/safety/assessment.py:719-728`:
```python
plateau_uA = (
    math.ulp(max(abs(result.resting_potential_V), abs(window.cathodic_V), abs(window.anodic_V)))
    * result.capacitance_uF_cm2 * area_cm2 / (protocol.pulse_width_us * 1e-6)
)
```
Units check out: V * (uF/cm^2) * cm^2 / s = uC/s = uA. The inverse chain is exactly the
predicate's own chain (`excursion = I*PW/(A*C)` => `I = excursion*A*C/PW`). Correct.

Error budget, worked through:
* the predicate rounds `resting + sign*excursion` to nearest, so the effective boundary in
  excursion is displaced by up to 0.5*ulp(sum). At the boundary the sum IS the window edge,
  so that is <= 0.5*ulp(max(|cath|,|anod|)) = 0.5 plateau.
* the seed's `available_V = edge - resting` is correctly rounded, error <= 0.5*ulp(available_V).
  `available_V` is the excursion at the boundary, which can exceed the edge when the resting
  potential sits on the FAR side (Pt cathodic-first at resting=+0.8 gives excursion 1.4 V).
  Window width <= 2*max(|cath|,|anod|) for every material on record, so
  ulp(available_V) <= 2 * plateau. Contribution <= 1.0 plateau.
* the rest (3 float ops in each chain) is relative, ~1e-16, dwarfed by CLIMB_TOLERANCE=1e-9.

Total <= ~1.5 plateau against PLATEAU_ALLOWANCE=4. **Sound, with ~2.7x margin.**
NOT sound by inspection alone though: the declared plateau can be a factor of 2 SMALLER
than the predicate's true resolution (ulp(excursion) vs ulp(edge)) whenever the resting
potential sits on the far side of the window. That case is safe only because the *relative*
budget dominates there (large headroom => 1e-9*seed >> 4*plateau). Recorded as a MINOR
fragility below, not a defect.

Correct for anodic-first as well: the expression is sign-free and takes a max over both
edges, so it bounds ulp of the sum in either drift direction. Correct for every material:
`max(|cathodic|,|anodic|)` >= the binding edge by construction; all nine windows checked.

### 1(d) Sweep

`scratchpad/p1b/sweep_ww.py`: 299,520 configurations =
9 materials-with-windows x 2 polarities x {0, both edges, nextafter(both edges),
midpoint, edge+-10^-e for e in 0..17 on both sides, 10 random interior} x
C in {derived, 1e-3, 1, 20, 250, 1e4, 1e8, 1e12, 1e-6, 1e18} x
A in {1e-8 .. 100 cm^2} x PW in {1 .. 1e5 us}.
Result: **0 raises, 0 non-boundary returns.** Every finite positive ceiling both passes and
has a failing successor. The 12,240 zero ceilings are all `resting == the edge in the drift
direction` (available_V == 0), which is the correct answer.

NOTE ON MY OWN FIRST RUN: the first version of this sweep silently skipped every
configuration (StimProtocol requires train_duration_s; the TypeError was swallowed by a
bare `except Exception: continue`) and printed "0 failures" over 299,520 vacuous rows.
Fixed before the numbers above were taken. Flagging it because it is the same failure mode
this review is hunting.

### 1(c) Is every other back-solve purely relative?

Module by module, verified against each predicate's arithmetic:
* `safety/shannon.py:232,264` -- `shannon_k(Q,A) = log10(Q^2/A) <= k`. A log DOES have an
  additive-constant shape (ulp of the metric is fixed while d(metric)/dQ ~ 1/Q), but the
  metric at the boundary equals `k`, and `validate_k` bounds k, so ulp(metric) is bounded
  and the plateau in Q is `~Q * ulp(k) * ln10/2 ~ 2.5e-16 * Q` -- proportional to Q, i.e.
  relative, ~2.5e-16 << 1e-9. Claim holds, but for a subtler reason than "no constant".
* `safety/charge.py:82,274,282` -- products/quotients only. Relative.
* `safety/assessment.py:_density_ceiling_uA`, `_current_density_ceiling_uA`,
  `_microelectrode_ceiling_uA` -- products/quotients only. Relative.
* `safety/compliance.py:130` -- `I*R + I*PW/(A*C) <= available_V`. Both terms linear in I,
  no additive constant; at the boundary the sum equals `available_V` so ulp(sum) is
  relative to the boundary value. Relative.
**Claim 1(c) verified true.**

### 1(b) Can a caller declare a plateau that is wrong?

* **Too SMALL -> raise.** Reproduced (`scratchpad/p1b/plateau_1b.py`): a predicate resolving
  only multiples of 1e-3, seeded 0.5 plateau below its boundary, settles at plateau=1e-3 and
  raises at plateau=1.25e-4 and at 0.0. Inside the package no caller can do this: the
  water-window plateau over-estimates the required budget by ~2.7x (above) and 299,520
  configurations produced 0 raises.
* **Too LARGE -> silently wrong ceiling: only via a non-monotone predicate.** For a monotone
  predicate the bisection converges on the exact boundary whatever the budget (verified at
  plateau = 0, 1e-9, 1e-3, 1e3 -- all return the same boundary). But the climb's exponential
  bracket *skips* the interval it jumps over, so a narrow FAIL band above the seed is
  invisible once the offset has grown past it. Constructed: predicate passing on
  [0, 1+1e-9], failing on a 1e-15-wide band, passing again to 2.0 -- with plateau=0 or 1e-9
  it raises; with plateau=1.0 it returns **2.0**, twice the true ceiling, silently.
  Guarded today only by the monotonicity precondition (`validate_resting_potential_V`).
  Recorded as MINOR-structural: it is the failure mode a future non-monotone clause (C2.3's
  drift term, C2.1's imbalance) would hit, and a larger declared plateau makes it more
  likely, not less.

## 6. Numbers that moved -- checked before the rest, because it is falsifiable

Method: `git archive 36d3d6b` into the scratchpad, then one render-corpus script
(`scratchpad/p1b/corpus.py`) run against both trees, importing each by sys.path
(confirmed by `neurostim.__file__`). Corpus = 250k lines: `SafetyAssessment.describe`,
`gui.headline_text`, `report_to_json`, `sensitivity.describe` over
7 diameters x 9 materials x 4 pulse widths x {biphasic, monophasic} x both polarities,
plus the band electrode, plus standalone `charge.describe`/`shannon.describe`/butterwick
over their own grids.

**Result: 46 distinct changed line-shapes, every one inside a booked class.**
* charge-injection limit renders (ledger 96)
* electroporation-threshold renders (ledger 96)
* `published range` interval (ledger 96)
* sensitivity `baseline:`/row renders and the new refusal block (ledger 89)
Zero changes to: `Limiting current:` lines, water-window, compliance, microelectrode,
chronic, Shannon renders, `limiting_current_uA`/`ceiling_uA` JSON, `max current` lines.

Gates at HEAD, run here: **814 passed**, ruff clean, `mypy neurostim` clean (53 files),
`ledger_check.py` OK (97 entries), `regenerate_example_output.py --check` OK.
**No unbooked mover found.**

## 4. B3 tripwire -- VERIFIED REAL

Method: `git archive aaf3c85` into `scratchpad/c23`, patched `stays_in_window`
(`assessment.py:700`) with C2.3's DC-drift clause exactly as the seed docstring specifies --
`net_fraction * I * PW_s * f * T <= headroom_V * C * A`, `net_fraction` 1.0 monophasic /
0.0 balanced biphasic. No repo file touched.

Result: **the tripwire fires, with the message it promises.**
```
FAILED TestTheWaterWindowSeedInvertsItsOwnPredicate::test_the_seed_inverts_the_predicate_it_seeds
E  Failed: the water-window seed no longer inverts the predicate it seeds, for
   ('PtIr', 1270.0, 3000.0, 90.0, 'monophasic'): Water window: the back-solved limit
   6749.062117423617 still fails its own check after 4 steps down to 6749.062117423613 ...
   A clause added to the forward check needs its closed-form inverse in
   _water_window_seed_uA, in the same commit.
```
A second test in the class (`..._is_the_pulse_peak_inverse_today`) also goes red. The
builder's claim is accurate and the guard is not vacuous.

Context worth having: the patched tree fails **28 tests across 4 files**, not 2 --
`test_oracles.py::TestDriftTime::test_the_package_currently_reports_a_pass_here`,
`test_figure_surface.py::TestNoBareNumberWhenNoAmplitudeIsSafe` (2),
`TestSensitivityRefusesWhenNoAmplitudeIsSafe` (4), `TestUnsafeAtAnyAmplitude` (6),
`TestTheHeadlineRefusesInItsOwnType` (5), and more. So C2.3's author will not see the
tripwire's diagnostic in isolation; it will be one message in a wall. Not a defect --
adding a real clause changes real behaviour -- but the "discovered as a crash inside C2.3"
risk the docstring says it removes is only partly removed. MINOR.

## 5. Test quality -- mutation results

All mutants applied to `git archive aaf3c85` in `scratchpad/mut`; the repo was never touched.
Harness: `scratchpad/p1b/mutate.sh`.

| # | mutant | outcome |
|---|--------|---------|
| A | `STEP_BUDGET` 4 -> 40 | KILLED by `test_a_walk_down_of_five_floats_raises` |
| D | `STEP_BUDGET` 4 -> 3 | KILLED by `test_a_walk_down_of_exactly_four_floats_settles` |
| B | `CLIMB_TOLERANCE` 1e-9 -> 1e-3 | KILLED by 2 tests |
| C | `PLATEAU_ALLOWANCE` 4 -> 4000 | KILLED by `test_the_declared_plateau_widens_the_climb_and_nothing_else_does` |
| E | `PLATEAU_ALLOWANCE` 4 -> 1 | KILLED by the same test |
| F | `plateau=search.plateau_uA` -> `plateau=0.0` (undo B1 at its call site) | KILLED by 3 tests in `TestTheClimbIsBoundedByThePredicatesOwnResolution` |
| G | `ceiling_uA=ceiling` -> `2.0*ceiling` (ledger 94's own mutant) | KILLED -- 28 tests, including `test_the_headline_is_the_minimum_of_the_per_kind_limits`, the test that previously SURVIVED it |

So the two constants the builder says it pinned are pinned **in both directions**, the B1
call-site is pinned, and the ledger-94 repair genuinely discriminates. Verified, not taken
on trust.

Note on the companion test: `test_the_per_kind_limits_disagree_where_it_matters` asserts a
*ratio* between literals, so it survives mutant G (a uniform scaling preserves ratios). Its
docstring only claims to catch a *collapse*, which it does, so this is correct as written --
recording it so the next reviewer does not read it as a second guard on the values.

### FINDING (MINOR): the `:g` round-trip gate skips one of the three valid policies -- and is RED if you add it

`tests/test_verdict_core.py:1494-1497` loops
```python
for policy in ("conservative", "optimistic"):
```
but `materials.Policy` is `Literal["conservative", "nominal", "optimistic"]`. Adding
`"nominal"` to that tuple turns the gate red **at HEAD**:
```
E  AssertionError: ('Pt', 'nominal', True, 75.00000000000001)
```
`Pt` and `PtIr` at `policy="nominal", anodic_first=True` are 75.00000000000001 uC/cm^2, which
`:g` prints as "75". Benign in direction (it renders *low*, not high), but the test's own
docstring says the gate exists so that "adding a constant that does not survive its own
rendering fails here" -- and a value that does not survive it is already present and
unnoticed. The gate covers 2 of 3 policies.

### FINDING (MINOR): the same gate asserts a literal where it claims to gate a constant

`tests/test_verdict_core.py:1533` is `assert renders_exactly(2.0)  # thermal.ThermalResult.limit_K, ISO 14708-3`.
That is `float(f"{2.0:g}") == 2.0` -- true by construction and with no link to
`neurostim/models/thermal.py:560`, which is the constant actually rendered with `:g` at
`thermal.py:599`. Changing `limit_K` to a non-round default leaves this green. It should read
the module's own value (`thermal.ThermalResult.limit_K` or the `evaluate` default), the way
the loop above it reads `MATERIALS`.

### FINDING (MINOR): `charge.py:257` renders a derated limit with `:g`, outside the new gate

```python
policy_warning = (
    f"the '{policy}' policy applies {limit:g} uC/cm^2, but the source for this "
```
`limit` here is the **derated** CIC (`limit = limit / derating` at `charge.py:222`) -- exactly
the `stored constant / derating factor` shape ledger 96's own test docstring calls "round only
by accident". Measured: every Pt/PtIr derated value fails the round-trip property and
overstates -- 7.142857142857143 -> "7.14286", 10.714285714285714 -> "10.7143". Unreachable
today only because `SS316LVM` is the single material with a `recommended_policy` and
`cogan2016.derating_for("SS316LVM")` is `None`. The new gate cannot catch it: the gate walks
*stored* constants, and this value is a quotient. Ledger 96's claim that "the benign `:g` sites
are made structurally safe rather than argued safe" is therefore not true of this one.
(Separately and pre-existing: the `{endorsed:g}` half of that same sentence is *not* derated,
so under `medium="in_vivo"` the sentence compares a derated number against an underated one.
Out of scope, not introduced here.)

## 2. The API change (M2) -- `limiting_current_uA: float | None`

Exercised at runtime, not read: `scratchpad/p1b/m2_consumers.py` on
`DiscElectrode(100,"Pt")` + monophasic 20 uA/200 us/130 Hz + `compliance_V=10`, the protocol
for which `limiting_current_uA is None`.

| consumer | site | handles None | prints "None"? |
|---|---|---|---|
| `SafetyAssessment.describe` | assessment.py:532 | branch on `is None`, refusal replaces the line AND the interval line | no |
| `SafetyCalculator.report()` | assessment.py:1573 | unconditional read, so it cannot disagree with the attribute | n/a (dict value) |
| `report_to_json` | io/tabular.py:182 | `json.dumps` -> `null` | no |
| PDF `build_report` | io/report.py:232 | branch on `is None`; `incomplete` suffix suppressed | no -- PDF built, 11738 bytes |
| GUI `headline_text` | gui/app.py:131 | branch on `is None` | no |
| `viz.current_limit_sweep` | viz/plots.py:252 | branch on `is None`; no `axhline`, no `fill_between` | no |
| `viz.safety_summary` | viz/plots.py | inherits the above | no |
| `sensitivity._limit` | sensitivity.py:125 | raises `UnsafeAtAnyAmplitude` | no |
| `sensitivity.analyse` / `describe` | sensitivity.py:142/231 | raises / refusal block; `" uA"` absent from the text | no |
| `examples/worked_example.py` | :65, :101 | branch on `is None` at both sites | no |
| batch `current_sweep` + `write_csv` | io/tabular.py | pandas writes an empty cell | no |

**No surface prints "None".** Every `format_limit` call site was re-checked and every one
takes a maximum (`max_current_uA`, `max_charge_uC`, `cic_limit_uC_cm2`,
`threshold_A_per_cm2`, `limiting_current_uA`, `by_kind[...]`, the sensitivity limits,
`binding_uA`, `material.cic_uC_cm2('conservative')`) -- 30 sites, none an applied value.

### FINDING (MAJOR): the new docstring's "None **exactly when**" is false for a zero ceiling

`assessment.py:307-334` now promises "Highest amplitude that is **safe to programme**, or
``None`` when none is", and "``None`` **exactly when** :attr:`unsafe_at_any_amplitude` is
non-empty". But `unsafe_at_any_amplitude` (`assessment.py:282-286`) only collects FAILing
checks **outside** `LIMIT_BEARING`. A limit-bearing check whose ceiling is exactly `0.0`
therefore yields a number, not a refusal:

```
SafetyCalculator(DiscElectrode(100,'Pt'), StimProtocol(80,200,130,1),
                 resting_potential_V=-0.6).assess()
-> limiting_current_uA == 0.0, limiting_mechanism 'Water window'
   describe():  "Limiting current: 0 uA (Water window)"
   GUI:         "... - limiting current 0 uA (Water window) - INCOMPLETE: ..."
   sensitivity: "baseline: 0 uA (Water window)"
```
`resting_potential_V = -0.6` is exactly platinum's cathodic limit and
`validate_resting_potential_V` accepts it deliberately ("Inclusive at both ends, matching
:meth:`WaterWindow.contains`"). `StimProtocol` rejects `current_uA <= 0`, so 0 uA is not an
amplitude anyone can programme -- this is the "no amplitude is safe" case wearing a number,
which is the whole of ledger 84.

**Behaviour is unchanged from 36d3d6b** (verified: the baseline tree prints the same line),
so this is not a Phase 1b regression and not a blocker. What Phase 1b changed is that the
attribute now *documents* a promise it does not keep, and M2's stated purpose was to make
that promise structural. The cheap repair is to treat a `0.0` limit-bearing ceiling as a
refusal (or to state the exclusion in the docstring); it is the same one-line shape as the
`None` branch. My swept 299,520 water-window configurations produced 12,240 zero ceilings,
all of this form, so the input class is not exotic.

## 3. The render class (ledger 96) -- direction check

Eight renders across seven sites, each verified against the direction of its own comparison:

| site | quantity | comparison | flooring is |
|---|---|---|---|
| charge.py:152 | `cic_limit_uC_cm2` | `density <= limit` | conservative |
| charge.py:164 | `limit_interval_uC_cm2` both ends | both ends are limits | conservative |
| assessment.py:934 | `cic_limit_uC_cm2` (FAIL branch) | `density <= limit` | conservative |
| assessment.py:954 | `cic_limit_uC_cm2` (CAUTION/PASS) | same | conservative |
| assessment.py:1051 | `threshold_A_per_cm2` (FAIL) | FAIL at `applied >= threshold` | conservative |
| assessment.py:1061 | `threshold_A_per_cm2` (PASS/CAUTION) | same | conservative |
| io/report.py:328 | `charge.cic_limit_uC_cm2` (PDF row) | same | conservative |
| butterwick2007.py:210 | `threshold_A_per_cm2` | same | conservative |

**No site was floored in the unsafe direction.** No floor was applied to a quantity where
larger is safer: `available_V`, `headroom_V`, `required_V`, `margin` and `utilisation` all
keep their original formats (checked in the diff and by grep). Applied quantities confirmed
untouched at all four sites (`charge_density_uC_cm2`, `applied_A_per_cm2` x2, and the
`applied` line in `ThresholdComparison.describe`), which the builder's
`test_the_applied_quantities_are_not_floored` also pins on a value where the two forms
differ (0.3979 vs 0.3978).

**The `:g` round-trip gate is non-vacuous as claimed** -- `tests/test_verdict_core.py:1499-1501`
asserts `not renders_exactly(7.142857142857143)` and `not renders_exactly(9.348927087079717)`
before the loop. Verified by reading and by the mutation in section 5. Its *coverage* is
narrower than advertised -- see the three MINOR findings in section 5.

### MINOR: `Interval.describe(floor=)`'s docstring contradicts its newest caller

`uncertainty.py:155-166` says floor "is opt-in because most intervals here are measurements
or **published ranges**, and rounding a measurement down is not more conservative -- it is
just wrong." `charge.py:164` now passes `floor=True` for `limit_interval_uC_cm2`, which *is*
the published CIC band. The direction is still conservative (both ends are ceilings, and
`charge.py:160-161` says so), so this is a documentation conflict, not a defect -- but the
two comments now disagree in the same repository about the same call.

---

## THE FINDING: claim 1(c) is false -- Shannon has the same non-relative plateau, and it raises

`neurostim/safety/shannon.py:232` and `neurostim/safety/_limits.py:144`.

Phase 1b's whole argument for confining the `plateau` parameter to one caller is that
"every other back-solve has a purely relative plateau". **It does not.** `shannon_k` is not
`log10(Q^2/A)` as its own docstring says -- `shannon.py:215` computes it as

```python
charge_density = charge_per_phase_uC / area_cm2
return math.log10(charge_per_phase_uC) + math.log10(charge_density)
```

a **sum of two logs**. The resolution of that sum is set by the larger addend
`log10(Q/A)`, not by the result `k` -- which is exactly the shape ledger 88 is written
about, with `log10(Q/A)` playing the part `resting_potential_V` plays in the water window.
Once the charge density crosses `1e4 uC/cm^2`, `log10(Q/A)` enters the `[4, 8)` binade and
its ulp is **4x** the ulp of `k in [1,2)`. The seed `sqrt(A * 10**k)` then overshoots the
forward boundary by **5 floats** against `STEP_BUDGET = 4`, and `floor_to_pass` raises.

Measured, not argued:
* `log10(Q/A)` at every observed failure: **4.007 to 4.375**; over all draws: 1.304 to 4.546.
  Every failure is above 4.0 and none below it.
* `math.ulp(log10(Q/A)) / math.ulp(k)` at a failure: **exactly 4.0**.
* Ulps the seed overshoots by, walked one `nextafter` at a time: **5**.

Public-API reproduction, on a tree built from `git archive aaf3c85` (no repo file touched):
```python
from neurostim import DiscElectrode, StimProtocol, SafetyCalculator
SafetyCalculator(DiscElectrode(5.586476331363039, "Pt"),
                 StimProtocol(10.0, 200.0, 130.0, 1.0),
                 k=1.642880206146527).assess()
# neurostim.safety._limits.LimitDidNotSettle: Shannon criterion: the back-solved limit
# 0.003281882339347544 still fails its own check after 4 steps down to 0.003281882339347542.
```
`k = 1.642880206146527` is inside `K_BOUNDS = (1.5, 2.0)` and `validate_k` accepts it;
a 5.6 um disc is inside everything the package accepts. The user gets no assessment at all.

**Exposure, measured:**
| population | rate |
|---|---|
| random disc 3.2-3162 um x random k in [1.5,2.0] | 138 / 200 000 (0.07 %) |
| random disc 4-8 um x random k in [1.5,2.0] | 195 / 50 000 (0.4 %) |
| **fixed 6 um disc x random k in [1.5,2.0]** | **351 / 30 000 (1.17 %)** |
| any disc 0.5-50 um at `k = K_DEFAULT` (1.5) | 0 / 40 000 |
| ditto at `K_SHANNON` 1.5, `K_DAMAGE_OBSERVED` 2.0, both `K_BOUNDS` ends | 0 / 30 000 each |

So it needs **a user-supplied non-round `k` AND an electrode below ~9.5 um**
(the boundary is `A <= 10**k / 1e8`, i.e. 9.494 um at k=1.85). Every `k` the package itself
uses is exactly representable, which is why 814 tests, the README, the worked example and the
builder's 40 000-draw sweep all miss it -- none of them varies `k` off a round value on a
sub-10 um electrode. `k` is nevertheless the first constructor argument of `SafetyCalculator`.

**Not a Phase 1b regression.** Verified identical on `36d3d6b`: the same three cases raise
there too. It is a **Phase 1 regression** -- before `floor_to_pass` existed there was no
raise -- of *precisely* the class F2/B1 was rated BLOCKER for, left open because Phase 1b
cleared Shannon by inspection instead of by sweep.

**The fix is the mechanism Phase 1b already built**: declare Shannon's plateau. One ulp of
the sum converted back through the predicate's own chain is
`plateau_Q = ulp(max(|log10(Q)|, |log10(Q/A)|)) * Q * ln(10) / 2`, passed as `plateau=` at
`shannon.py:232` and `:264`. Widening `STEP_BUDGET` would be the wrong answer for the reason
`_climb_to_boundary`'s own docstring gives about `CLIMB_TOLERANCE`.

**My attack list said: "assume Phase 1b has introduced a regression somewhere until you have
evidence otherwise." It has not. What it has done is declare a class closed on the strength
of a module-by-module claim it did not sweep, and the class is not closed.**

## Ledger 97 (`_ceiling_interval_uA`) -- I agree, and would raise it

The builder rates it and the fix direction is right. Two things strengthen the case:
1. The failure mode is not hypothetical. Ledger **95(a)** records that `Check.name` *already
   changed* once in this repair -- "Shannon tissue-damage criterion" -> "Shannon criterion",
   "SS316LVM charge-injection limit" -> "Charge injection limit". Had `_ceiling_interval_uA`
   existed in its current form across that rename, it would have silently fallen through to
   `Interval.exact` for Shannon and charge injection. The precedent is in the ledger.
2. The silent direction is **narrowing** -- a published band collapses to a point -- so the
   report understates its own uncertainty while every number in it stays plausible. There is
   no number to notice, which is the ledger 19/59/60 shape the M2 docstring itself invokes.
`CHECK_KINDS` next door is the model: a name->property table with a raising `KeyError`. A
two-line gate (`set(CHECK_KINDS) == {c.name for c in checks}`, plus the three interval-bearing
names asserted in `LIMIT_BEARING`) closes it structurally.

---

# RANKED FINDINGS

## BLOCKER
None introduced by Phase 1b.

## MAJOR

**M-1. `shannon_max_charge_uC` raises `LimitDidNotSettle` on accepted input; claim 1(c) is false.**
`neurostim/safety/shannon.py:232` (and `:264` by the same mechanism), via `_limits.py:144`.
`shannon_k` is a **sum of two logs**, so its resolution is set by `log10(Q/A)`, not by `k`.
Above a charge density of `1e4 uC/cm^2` that addend's ulp is 4x `ulp(k)` and the seed
overshoots by 5 floats against `STEP_BUDGET = 4`.
Failure case:
`SafetyCalculator(DiscElectrode(5.586476331363039,"Pt"), StimProtocol(10.0,200.0,130.0,1.0), k=1.642880206146527).assess()`
raises; `k` is inside `K_BOUNDS` and the electrode inside everything the package accepts.
Rate 1.17 % on a 6 um disc over random `k`; 0 at every `k` the package itself uses.
Pre-existing (identical at 36d3d6b), so **not a Phase 1b regression** -- but it is the class
Phase 1b declared closed, cleared by inspection rather than by sweep.
Fix: declare Shannon's plateau, the mechanism Phase 1b already built.

**M-2. `limiting_current_uA`'s new "None **exactly when**" contract is false for a zero ceiling.**
`neurostim/safety/assessment.py:307-334` vs `:282-286`.
`unsafe_at_any_amplitude` collects only FAILing checks *outside* `LIMIT_BEARING`, so a
limit-bearing ceiling of exactly `0.0` returns a number.
`SafetyCalculator(DiscElectrode(100,'Pt'), StimProtocol(80,200,130,1), resting_potential_V=-0.6).assess()`
-> `limiting_current_uA == 0.0`, and every surface prints "limiting current 0 uA (Water window)".
`StimProtocol` rejects `current_uA <= 0`, so that is not an amplitude anyone can programme.
Behaviour unchanged from 36d3d6b -- what changed is that the attribute now documents a
promise it does not keep, and making that promise structural was M2's stated purpose.
12 240 of my 299 520 swept water-window configurations produce a zero ceiling.

**M-3. (already ledger 97) `_ceiling_interval_uA` string dispatch.** I agree with the finding
and the fix; I would rate it MAJOR rather than lower, because `Check.name` already changed
once inside this repair (ledger 95(a)) and the silent direction is a narrowed uncertainty band.

## MINOR

1. `tests/test_verdict_core.py:1494` -- the `:g` round-trip gate loops only
   `("conservative", "optimistic")`; `Policy` has three values. Adding `"nominal"` turns the
   gate **red at HEAD**: `AssertionError: ('Pt', 'nominal', True, 75.00000000000001)`.
2. `tests/test_verdict_core.py:1533` -- `assert renders_exactly(2.0)` is a literal standing in
   for `thermal.ThermalResult.limit_K` (`models/thermal.py:560`, rendered `:g` at `:599`).
   Tautologically true; changing the constant leaves it green.
3. `neurostim/safety/charge.py:257` -- `{limit:g}` renders the **derated** CIC, the
   `stored / derating` shape the gate's own docstring calls "round only by accident"
   (Pt in vivo: 7.142857142857143 -> "7.14286", overstating). Unreachable today only because
   `SS316LVM` is the sole material with a `recommended_policy` and has no derating. The new
   gate cannot catch it -- it walks stored constants, and this is a quotient. So ledger 96's
   "structurally safe rather than argued safe" is not true of this site.
4. `neurostim/uncertainty.py:155-166` -- `Interval.describe(floor=)`'s docstring says floor is
   *not* for published ranges; `charge.py:164` now passes `floor=True` for the published CIC
   band. Direction is still conservative; the two comments disagree.
5. `_climb_to_boundary`'s exponential bracket **skips** the interval it jumps, so a larger
   declared plateau makes a non-monotone predicate more dangerous, not less. Constructed: a
   1e-15-wide FAIL band above the seed returns **2.0** for a true ceiling of 1.0 at
   `plateau=1.0`, silently. Guarded today only by `validate_resting_potential_V`. Worth a line
   in `floor_to_pass`'s contract before C2.1/C2.3 add clauses.
6. `tests/test_verdict_core.py::test_the_varied_settings_cannot_create_or_remove_that_refusal`
   claims its variants are "built here with the same settings `_limit` uses"; `_limit`
   (`sensitivity.py:106-123`) also propagates `lead_resistance_ohm`, `compliance_V`,
   `measured_impedance_ohm`, `resting_potential_V`, `capacitance_uF_cm2`, which the test omits.
   Harmless on this fixture (all defaults); silently divergent on any other.
7. The B3 tripwire fires, but under a simulated C2.3 clause **28 tests across 4 files** go red,
   so its diagnostic arrives inside a wall rather than alone.

## Verified as claimed (no finding)

* Plateau expression correct, sign-free, correct for anodic-first and for all nine windows;
  error budget <= ~1.5 plateau against `PLATEAU_ALLOWANCE = 4`. **0 raises / 0 non-boundary
  returns over 299 520 water-window configurations** and 0 over a 19 023-configuration
  edge-clustered sweep of the whole `assess()` path (the only raises in the latter were M-1).
* All nine `float | None` consumers handle `None` structurally; **no surface prints "None"**.
* All eight floored renders floor in the conservative direction; applied quantities are not
  floored at any of the four sites.
* The `:g` gate is non-vacuous -- it asserts two known values fail the property.
* The B3 tripwire is real and fires with the exact message it promises.
* `STEP_BUDGET`, `CLIMB_TOLERANCE`, `PLATEAU_ALLOWANCE` and the water-window `plateau=`
  call site are each killed by mutation in **both** directions; ledger 94's own 2x-ceiling
  mutant now dies.
* No unbooked number moved: 46 changed line-shapes across a 250 000-line two-tree render
  corpus, every one inside a booked class. Gates at aaf3c85: 814 passed, ruff, mypy,
  ledger, README transcript all clean.

# VERDICT: **GO** for Phase 2 -- with two conditions

Phase 1b is sound work. It did not introduce a regression: I attacked the settle mechanism
with 300 k targeted configurations and a 19 k full-path edge-clustered sweep and found
nothing wrong with what it built. The B3 tripwire is genuine, the mutants are dead, the API
change is handled on every surface, and nothing moved unbooked.

Do **not** stop Phase 2. M-1 is pre-existing, lives in `shannon.py`, and is untouched by
Phase 2's subject matter (`protocol.py`, the assessment, C2.3's drift clause); halting
mid-phase would not fix it and would cost a restart.

Conditions:
1. **B1/F2 must not be recorded as closed.** Open a ledger entry for M-1 with the repro
   above, and land the Shannon `plateau=` declaration before Phase 2's exit gate, not its
   start. Note for the record: by the precedent of Phase 1's own review -- which rated F2 a
   BLOCKER for a crash on accepted input -- M-1 qualifies as one. I am calling it MAJOR only
   because it is pre-existing and orthogonal to Phase 2's work, and that is a scheduling
   judgement, not a technical one. If you would rather apply the precedent literally, stop.
2. **Phase 2 must not read `limiting_current_uA is None` as "no safe amplitude" (M-2).**
   C2.1 widens the refusal to unbalanced biphasic protocols and will touch exactly this
   attribute; the `0.0` case has to be decided now rather than inherited.
