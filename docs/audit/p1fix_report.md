# Phase 1 blocker fixes — F2, F1, F3

Repo `.`, interpreter `.venv/bin/python`.
Baseline HEAD 36d3d6b, 780 passed.

## D2's settle budget, in one sentence

**The settle budget is directional: downward it is `STEP_BUDGET = 4` floats of the seed
(one ulp of back-solve/forward-comparison disagreement, plus slack), and upward it is a
*distance* `max(CLIMB_TOLERANCE × value, PLATEAU_ALLOWANCE × plateau)` — bracketed
exponentially in ulps then bisected — where `plateau` is the caller-declared width, in the
limit's own units, of one step of the predicate's own arithmetic (0.0 when the predicate
resolves every float).**

---

## Commit 1 — F2 (BLOCKER): `89a54b4` `fix(safety): bound the climb by the predicate's own resolution, not by the seed`

Ledger 88 opened and closed. Plan `docs/audit/FIX_PLAN_v2.md` D2 point 2 rewritten (it
described only the downward half) and D2 point 3 added for the plateau; §6 gains a
`C1.10 [88]` row; §9 gains row 88.

### Root cause, as fixed

`_climb_to_boundary` bounded the upward walk by `CLIMB_TOLERANCE` **relative to the seed**.
The water-window predicate adds the excursion to a *constant* `resting_potential_V` and
compares the sum against a window edge, so the run of amplitudes it cannot tell apart is
one ulp of **that sum**, converted back through `C·A/PW` — an absolute width, fixed by the
resting potential, not by the limit. Relative to the limit it therefore grows as `1/limit`,
without bound, so *no* value of `CLIMB_TOLERANCE` is sufficient; a larger one only moves the
headroom at which the raise starts.

Fix: `floor_to_pass`/`_climb_to_boundary` take `plateau: float = 0.0` — the smallest change
in the limit the predicate can resolve, in the limit's own units — and the climb budget
becomes `max(abs(value) * rel_tolerance, PLATEAU_ALLOWANCE * plateau)` with
`PLATEAU_ALLOWANCE = 4`. `_water_window_ceiling_uA` declares
`ulp(max(|resting|, |cathodic|, |anodic|)) * C * A / PW`. A seed further above than **both**
bounds still raises; the message now names the budget and the declared plateau instead of
asserting "a plateau is a few floats wide" (it was 4.2e7 floats wide and the back-solve was
correct).

Only the water window needed it. Every other back-solve in the package (`shannon`,
`charge`, `current_density`, `compliance`) compares quantities that are *products* of the
amplitude with no constant offset, so their plateau is relative (~1e-16) and
`CLIMB_TOLERANCE` already covers it — consistent with the reviewer finding every raise to
be `Water window`.

### RED (before the fix)

    $ .venv/bin/python -m pytest -q tests/test_verdict_core.py \
        -k TestTheClimbIsBoundedByThePredicatesOwnResolution
    FAILED ::test_a_resting_potential_just_inside_the_window_still_assesses
    FAILED ::test_the_settled_limit_is_the_water_window_boundary
    FAILED ::test_no_configuration_clustered_against_a_window_edge_raises
    FAILED ::test_the_helper_crosses_a_plateau_of_the_width_its_caller_declares
    FAILED ::test_a_seed_further_below_the_boundary_than_the_plateau_still_raises
    5 failed, 115 deselected in 1.68s

The sweep test's own red line:

    E   AssertionError: 298 of 1500 raised; first: AIROF at 0.7999999851096975:
        Water window: the back-solved limit 4.7422479984903854e-06 still passes its own
        check more than 1e-09 of its own size above it, at 4.742248005595812e-06.

The two helper-contract tests were red as `TypeError: floor_to_pass() got an unexpected
keyword argument 'plateau'`.

### GREEN (after the fix)

    $ .venv/bin/python -m pytest -q tests/test_verdict_core.py \
        -k TestTheClimbIsBoundedByThePredicatesOwnResolution
    5 passed, 115 deselected in 1.06s

Minimal reproduction, both polarities, now returns numbers:

    -0.59999999 cathodic-first  -> 4.0448005393678537e-07
    +0.79999999 anodic-first    -> 4.0448005842741614e-07
    -0.5999999  cathodic-first  -> 4.044800541613169e-06
    -0.6        cathodic-first  -> 0.0

Wider scratch sweep (40 000 edge-clustered draws, headroom `10**U(-16,-1)`, both edges,
9 windowed materials): **11 536 raises before, 0 after.**

### Gates at `89a54b4`

    pytest -q                                      785 passed
    ruff check neurostim tests examples scripts    All checks passed!
    mypy neurostim                                 Success: no issues found in 53 source files
    python scripts/ledger_check.py                 OK: 88 entries, 7 fields each
    python scripts/regenerate_example_output.py --check  OK: transcript matches

No committed number moved (these configurations produced no output at all before), so the
regeneration script had nothing to regenerate; `--check` is clean.

## Commit 2 — `f4276e0` `docs(ledger): record the commit that closed 88`

Ledger-only. Gates re-run: ledger_check OK.

---

## Commit 3 — F1 (BLOCKER): `d712995` `fix(sensitivity,examples): refuse, and floor, on the two surfaces Phase 1 missed`

Ledger 89 opened and closed. Plan §6 gains three rows (`C1.3 [89]` ×2, `C1.5 [89]`) — neither
file appeared in §6 at all; §9 gains row 89.

### (a) C1.5 / ledger 84 — the refusal, hoisted out of the render

`neurostim/sensitivity.py` gains `UnsafeAtAnyAmplitude(ValueError)` and `_refusal(calc)`,
which reads the assessment's own `unsafe_at_any_amplitude_note()` so this sixth surface
cannot disagree with `describe()`, the JSON, the PDF, the GUI and the figure.
`analyse()` raises (a list of rows *is* eight amplitudes); `describe()` prints the refusal
**in place of** the ranking, not beside it.

Checking the baseline calculator is sufficient because none of the four varied settings
(`k`, `policy`, `medium`, `tissue_conductivity_S_per_m`) is an input to a check outside
`LIMIT_BEARING` — charge balance is a property of the waveform, the validated envelope of
the protocol's timing. That is pinned by its own test rather than argued, so if it stops
being true the refusal has to move into `_limit`.

### (b) C1.3 / ledger 49 — flooring

`Sensitivity.describe` (`:60-61`) and the baseline line (`:167`) now go through
`format_limit`. `examples/worked_example.py` gains the same at all six of its amplitude
sites (`:57`, `:59`, `:60`, `:88`, `:89`, `:109`).

### RED (before the fix)

    $ .venv/bin/python -m pytest -q tests/test_verdict_core.py -k \
      "test_the_sensitivity_report_floors_its_baseline_and_every_row or \
       test_the_worked_example_never_prints_an_amplitude_above_the_limit or \
       TestSensitivityRefusesWhenNoAmplitudeIsSafe"
    FAILED ::TestEveryRenderSiteFloors::test_the_sensitivity_report_floors_its_baseline_and_every_row
    FAILED ::TestEveryRenderSiteFloors::test_the_worked_example_never_prints_an_amplitude_above_the_limit
    FAILED ::TestSensitivityRefusesWhenNoAmplitudeIsSafe::test_analyse_refuses_rather_than_ranking_an_amplitude_that_does_not_exist
    FAILED ::TestSensitivityRefusesWhenNoAmplitudeIsSafe::test_describe_prints_the_refusal_in_place_of_nine_amplitudes
    4 failed, 2 passed, 120 deselected

Red detail:

    E   AssertionError: assert '14.13' in '  baseline: 14.14 uA (Chronic degradation)'
    E   AssertionError: assert '472.7 uA' in '...' (the worked example's stdout)
    E   AttributeError: module 'neurostim.sensitivity' has no attribute 'UnsafeAtAnyAmplitude'
    E   AssertionError: assert 'no amplitude is safe' in 'Sensitivity of the binding current
        limit to each defensible choice\n  baseline: 1.529e+04 uA (Shannon criterion)\n ...'

(The two tests that passed red are the two preconditions — the assessment refusing, and
the varied settings not changing the refusal — which is what they are for.)

### GREEN

    $ .venv/bin/python -m pytest -q tests/test_verdict_core.py -k \
      "TestSensitivityRefusesWhenNoAmplitudeIsSafe or test_the_sensitivity_report_floors"
    5 passed, 121 deselected in 0.31s
    $ .venv/bin/python -m pytest -q tests/test_verdict_core.py -k \
      "test_the_worked_example_never_prints_an_amplitude_above_the_limit"
    1 passed, 125 deselected in 7.46s

### Gates at `d712995`

    pytest -q                                      791 passed
    ruff check neurostim tests examples scripts    All checks passed!
    mypy neurostim                                 Success: no issues found in 53 source files
    python scripts/ledger_check.py                 OK: 89 entries, 7 fields each
    python scripts/regenerate_example_output.py --check  OK: transcript matches

No committed number moves: `example_output/` is untracked (`.gitignore:29-34`) and the
README transcript is generated from `calc.describe()`, which this commit does not touch.

## Commit 4 — `9dd5bda` `docs(ledger): record the commit that closed 89`

Ledger-only. ledger_check OK.

---

## Commit 5 — F3 (MINOR): `658f431` `fix(oracles): a refused amplitude below the bracket narrows it, it does not crash it`

Ledger 90 opened and closed; plan §9 gains row 90. No §6 row — the defect is entirely in
`tests/oracles/fail_ceiling.py` and no package number moves.

`UNCONSTRUCTIBLE` entered the per-check suffix invariant as if it were a check name.
`_constructible_bracket()` now raises the lower end of the bracket to the smallest
constructible probe and hands what remains to the invariant; a refusal *above* an amplitude
is untouched (it is already a suffix, and treating it as failing is what keeps the ceiling
at the largest constructible amplitude). `amplitude_independent_failures` uses the same
narrowed bracket, or a ceiling of `0.0` above a floor would arrive with an empty witness.
A bracket with no constructible probe raises the new `NoConstructibleAmplitude` rather than
borrowing `0.0`, whose single meaning under ledger 84 is "a check FAILs at every amplitude".

`ScriptedCalculator` gains `rejects_below_uA` alongside `rejects_above_uA`.

### RED

    $ .venv/bin/python -m pytest -q tests/test_verdict_core.py \
        -k TestTheCeilingOracleSurvivesConstructionTimeValidation
    FAILED ::test_an_amplitude_below_a_future_floor_narrows_the_bracket
    FAILED ::test_a_floor_and_a_ceiling_together_still_leave_the_suffix_rule_in_force
    FAILED ::test_a_zero_ceiling_above_a_floor_still_names_the_check_that_makes_it_zero
    FAILED ::test_a_bracket_with_no_constructible_amplitude_is_reported_not_answered
    4 failed, 2 passed, 124 deselected

    E   oracles.fail_ceiling.NonMonotonePredicate: <amplitude refused at construction>
        FAILs at 1e-12 uA and does not FAIL at 1.77828 uA. ...

### GREEN

    6 passed, 124 deselected in 0.32s

### Gates at `658f431`

    pytest -q                                      795 passed
    ruff / mypy / ledger_check / regenerate --check   all clean (90 ledger entries)

## Commit 6 — `c8788f0` `docs(ledger): record the commit that closed 90`

---

# Package-wide grep for unfloored limit renders

`23` `format_limit` call sites outside `_limits.py` after this work. What remains, all of
it **charge-density / current-density / charge-per-phase limits, never an amplitude**:

**No µA limit is rendered raw anywhere.** Every amplitude limit in `neurostim/` and
`examples/` now goes through `format_limit` (or `Interval.describe(floor=True)`).
`gui/app.py:137` and `viz/plots.py:275` are the only amplitude renders in those modules and
both are floored; `viz/plots.py:427` is an *applied* current, not a limit.

Remaining raw renders of a non-amplitude limit — **not fixed, reported as instructed**:

| site | expression | overstates? |
|---|---|---|
| `neurostim/safety/charge.py:152` | `cic_limit_uC_cm2:.4g` | **YES** — Pt and PtIr, `medium="in_vivo"`, `policy="conservative"`: limit `7.142857142857143`, prints `7.143`, `format_limit` gives `7.142`. 2 of the swept (material × medium × policy) combinations |
| `neurostim/safety/assessment.py:811` and `:831` | `cic_limit_uC_cm2:.4g` inside the Charge-injection check message ("… exceeds the X uC/cm² limit") | **YES** — same two values, same surface defect as ledger 49 |
| `neurostim/io/report.py:324` | `cic_limit_uC_cm2:.4g` (PDF) | **YES** — same two values |
| `neurostim/safety/assessment.py:928`, `:938` and `neurostim/data/butterwick2007.py:198` | `threshold_A_per_cm2:.4g` (electroporation threshold) | **YES** — overstates at 4 of 7 pulse widths swept (10 µs `1.0367951…` → `1.037`; 100 µs `0.3739570…` → `0.374`; 400 µs → `0.2024`; 1000 µs → `0.1349`) |
| `neurostim/safety/assessment.py:1039`, `:1054`, `:1064`; `neurostim/materials.py:271`, `:273` | chronic-threshold band `low/high_uC_cm2:g` | no — `:g` is 6 significant digits and the stored band ends are round (20/50 µC/cm²). Latent if a non-round threshold is ever added |
| `neurostim/safety/assessment.py:967`, `:977`, `:990`, `:1010` | Cogan microelectrode `threshold:g` (4 nC/phase) | no — exact |
| `neurostim/models/thermal.py:599` | `limit_K:g` (ISO 14708-3, 1 K) | no — exact |
| `neurostim/safety/shannon.py:308` | `k_threshold:.2f` | no — `k` is a log-space constant, not a current ceiling |

Recommendation for whoever owns C1.3's remainder: the `cic_limit_uC_cm2` and
`threshold_A_per_cm2` rows are the same defect as ledger 49 on a different unit, with a
measured overstatement, and none of the five sites is booked in §6.

# §6 (blast radius) gaps found and closed

* `neurostim/sensitivity.py` and `examples/worked_example.py` were **absent from §6
  entirely** — §6's C1.3 rows book `gui/app.py:332`, `viz/plots.py:211` and
  `Interval.describe` and stop there, and its C1.5 rows book `describe()`, the JSON, the
  PDF and the GUI. Three rows added (two C1.3, one C1.5), marked **[89]**.
* F2's raise → number was unbooked. One row added, marked **[88]**.
* Still unbooked and **not** mine to close: the five non-amplitude limit render sites in
  the table above; and F5's rows from the review (the `limiting_mechanism` vocabulary
  change, `report()["limiting_mechanism"]` becoming prose, `checks[].ceiling_uA`,
  `report()["status"]`, and `limiting_current_uA` moving beyond the worked example).

# Observation, not a fix: the *downward* walk keeps its 4-float budget

`floor_to_pass`'s walk down is still a pure step count, so in principle a seed that lands
one *plateau* above the boundary would exhaust it. I could not produce one: over 199 937
edge-clustered water-window seeds, **0** required even one downward step — the seed's
construction (`edge - resting`, then ×C and ÷C) round-trips to within one ulp of a quantity
far finer than `ulp(sum)`, so the seed lands at or below the boundary. Per the "stop rather
than improvise" rule I did not add an untested exponential descent. If a case is ever
found, the `plateau` parameter is already there and the down walk is where it would go.

# Also closed, as a consequence

**F10** (the review's MINOR list, now in `docs/audit/review_p1.md:571`): "§2 D2 is now stale —
it states one 4-step budget whose exhaustion carries the step count". The F2 commit rewrites
D2 point 2 to state both halves and adds point 3 for the plateau, so the plan and the code
agree again.

Not touched (not assigned): F4, F5, F6, F7, F9, F11, F12, F13, F14.

# Confirmation of scope

`docs/audit/review_p1.md` (committed at `5652949`, concurrently with this work) was diffed
against the copy I was given: lines 1-136, which are F1, F2 and F3 in full, are byte-identical.
Nothing in the appended F7-F14 changes the three fixes.

# Final state

HEAD `c8788f0`. Working tree clean. 795 tests (from 780). All five gates clean at every
commit. Ledger entries 88, 89 and 90 opened and closed with their hashes recorded.

---
---

# PHASE 1b, SECOND HALF (items 4-8)

## Commit 7 — item (4) / B3 / review F6: `1292ec0` `fix(safety): make the water-window seed and its predicate one change, not two`

**The fix you asked for cannot land on its own, and I measured why rather than assuming.**
The review's arithmetic reproduces exactly on the main thread:

    pulse-peak seed (today's)            99745.56675147594 uA
    drift ceiling Q_window/(PW.f.T)        767.2735903959687 uA
    ratio                                  130.0   ( = f . T )
    0.6 V * 250 uF/cm2 * 0.05984734 cm2 = 8.9771 uC ; /35.1 uA = 0.25576 s  (plan: 0.2558 s)

I then applied the corrected seed `min(peak, drift)` as a scratch patch **with today's
predicate**, which has no drift clause:

    plan's monophasic band : LimitDidNotSettle (climb) -- seed 767.27 passes, boundary is 99745
    monophasic Pt disc     : LimitDidNotSettle (climb)
    biphasic control       : ceiling 58.90486225480862  (unchanged)

    swept 9 windowed materials x 5 diameters x 4 pulse widths:
      monophasic: 160 raise / 160 constructed
      biphasic:     0 raise / 160 constructed

A seed 130× below the live boundary passes, and `_climb_to_boundary` cannot climb 130× —
so landing it alone converts every monophasic protocol from a working number into a crash.
That is the same regression class as B1, in the opposite direction. **Seed and clause are
one change.** The review says the same ("B3 is a Phase-2 commit … it must land *inside*
C2.3 with the corrected seed"). Scratch patch reverted; tree was clean before the commit.

**What landed instead — the mechanism that makes forgetting impossible:**

* `_water_window_search(result, protocol, area_cm2) -> _WindowSearch(seed_uA, passes, plateau_uA)`
  — seed, predicate and plateau from one place, so a test can hand the seed to the
  predicate it seeds rather than re-deriving one side.
* `_water_window_seed_uA` is a `min` over a **named list of closed-form inverses**, one
  member today, whose docstring carries C2.3's drift term verbatim with its verified
  constants — that commit adds a line, not a derivation.
* `TestTheWaterWindowSeedInvertsItsOwnPredicate` (3 tests) asserts seed and predicate stay
  inverses to within `floor_to_pass`'s own budget in whichever direction the seed landed
  (one grid row genuinely overshoots by an ulp — that is what the walk down is for), pins
  the seed as the peak-excursion inverse, and pins today's `99745.56675147594` ceiling.

### RED

    E   ImportError: cannot import name '_water_window_search' from 'neurostim.safety.assessment'
    FAILED ::test_the_seed_inverts_the_predicate_it_seeds
    FAILED ::test_the_seed_is_a_minimum_over_the_clauses_the_check_actually_has
    2 failed, 1 passed, 130 deselected

### GREEN — `3 passed, 130 deselected in 0.59s`

### The tripwire is not vacuous — proved

Added C2.3's drift clause to the predicate **alone** in a scratch tree:

    E   Failed: the water-window seed no longer inverts the predicate it seeds, for
        ('PtIr', 1270.0, 3000.0, 90.0, 'monophasic'): Water window: the back-solved limit
        6749.062117423617 still fails its own check after 4 steps down ... A clause added
        to the forward check needs its closed-form inverse in _water_window_seed_uA, in
        the same commit.

Reverted.

### Gates at `1292ec0`

    pytest -q  798 passed · ruff clean · mypy clean · ledger 91 entries · regenerate --check clean

No number moves — refactor plus tests. §6 gains a `C2.3 [91]` row booking
99745.57 → 767.27 with the seed requirement attached; §9 gains row 91.

## Commit 8 — `40f50f2` `docs(ledger): record the commit that partially closed 91`

Ledger 91 is recorded as **PARTIAL**, with what is left stated in the Fix cell. The Commit
cell holds the bare hash so `ledger_check.py`'s `^[0-9a-f]{7,40}$` still resolves it — a
cell like `1292ec0 (partial)` silently drops out of that assertion.

## Commit 9 — items (5) and (8) / M2 / review F7: `15a943c` `refactor(safety)!: the headline refuses in its own type, and the raw ceiling gets a name`

Items (5) and (8) of your brief are the same finding (the review's **M2** *is* the
`limiting_current_uA` rename); done once.

    limit_bearing_ceiling_uA -> float          the raw minimum over LIMIT_BEARING
    limiting_current_uA      -> float | None   None exactly when unsafe_at_any_amplitude

**The enforcement worked as advertised.** Making the type change and running the gate
surfaced exactly the three unguarded consumers the review enumerated, and no others:

    neurostim/sensitivity.py:114: error: Incompatible return value type (got "float | None", expected "float")
    neurostim/sensitivity.py:238: error: Argument 1 to "format_limit" has incompatible type "float | None"
    neurostim/io/report.py:238:   error: Argument 1 to "format_limit" has incompatible type "float | None"
    neurostim/viz/plots.py:275:   error: Argument 1 to "format_limit" has incompatible type "float | None"
    neurostim/gui/app.py:137:     error: Argument 1 to "format_limit" has incompatible type "float | None"
    Found 5 errors in 4 files (checked 53 source files)

(`report.py`, `viz`, `gui` already branched correctly — mypy flagged them because the
branch was on the *note* rather than on the value; each now branches on the value, which
is also one fewer copy of the condition.)

### RED

    FAILED ::test_the_headline_is_none_exactly_when_no_amplitude_is_safe
    FAILED ::test_the_raw_quantity_survives_under_a_name_that_states_it
    FAILED ::test_the_decomposition_stays_reachable_when_the_headline_refuses
    FAILED ::test_report_reads_the_attribute_with_no_conditional_of_its_own
    FAILED ::test_the_sensitivity_helper_refuses_a_variant_with_no_safe_amplitude
    5 failed, 133 deselected
    E   Failed: DID NOT RAISE UnsafeAtAnyAmplitude

### GREEN — `5 passed, 133 deselected in 0.36s`

### Existing tests that asserted the attribute is a float

Exactly **one** of the 798: `test_the_restriction_to_limit_bearing_checks_is_load_bearing`
(`tests/test_verdict_core.py:1919`), which pinned the monophasic value —

    E   assert None == 15285.50941588086 ± 1.5e-05

re-pointed at `limit_bearing_ceiling_uA` (what the fail-ceiling oracle actually brackets,
and defined for every protocol) with the `is None` assertion kept beside it. The other 33
references are on protocols with a safe amplitude and were unaffected.

`sensitivity._limit` now raises `UnsafeAtAnyAmplitude` on the `None`, and that branch is
**tested directly** rather than argued unreachable — which also removes the dead-branch
worry I flagged in the F1 commit.

### Gates at `15a943c`

    pytest -q  803 passed · ruff clean · mypy clean · ledger 92 entries · regenerate --check clean

No value moves — `report()["limiting_current_uA"]` already emitted `null` for these
protocols. §6 gains a `C1.5 [92]` row (API change, booked); §9 gains row 92; ledger 92.

## Commit 10 — `746514b` `docs(ledger): record the commit that closed 92`

## Commit 11 — item (6) / M4 + M5(a): `a8bb45d` `test(limits): straddle both settle budgets so neither constant can move unnoticed`

Pinned by **straddling**, with the fixtures written as literals — a test that computes its
fixture from the constant it pins moves with the mutant and survives it, which is how these
two got this far.

    a walk down of exactly 4 floats settles; 5 raises      -> STEP_BUDGET pinned to 4
    a climb of 1e-9 of the seed settles; 2e-9 raises       -> CLIMB_TOLERANCE pinned to [1e-9, 2e-9)
    2e-9 settles at plateau=1e-9 and raises at plateau=1e-10

Transition measured first, and it is sharp (1e-9 settles, 2e-9 raises), so the bracket is a
factor of two rather than four decades. The third case pins that **only a declared plateau**
widens the climb — so ledger 88's fix cannot be reached by loosening the relative bound.

M5(a) is here too: `assert "4" in message` becomes `assert f"after {STEP_BUDGET} steps"`,
which pins the message's *shape* while the behavioural pair pins the number.

### RED/GREEN is a mutation result, both directions verified

    mutant STEP_BUDGET 4 -> 40,        new class DESELECTED : 307 passed   (survives)
    mutant STEP_BUDGET 4 -> 40,        full                 : 1 failed, 312 passed
        FAILED ::test_a_walk_down_of_five_floats_raises  -- Failed: DID NOT RAISE LimitDidNotSettle
    mutant CLIMB_TOLERANCE 1e-9 -> 1e-3, new class DESELECTED : 307 passed   (survives)
    mutant CLIMB_TOLERANCE 1e-9 -> 1e-3, full                 : 2 failed, 311 passed
        FAILED ::test_a_climb_of_two_parts_in_a_billion_raises
        FAILED ::test_the_declared_plateau_widens_the_climb_and_nothing_else_does

### Gates at `a8bb45d` — 809 passed · ruff · mypy · ledger 93 entries · regenerate clean

## Commit 12 — `208a84b` ledger hash for 93

## Commit 13 — item (7) / M5(b)(c): `da46d4a` `test(verdict): stop the by-kind test restating the implementation, and say what containment proves`

**(b)** `test_the_headline_is_the_minimum_of_the_per_kind_limits` built `expected` by
looping over the same `check.ceiling_uA` the implementation reads. Demonstrated on the main
thread with a 2× ceiling mutant:

    before: 1 passed          (the tautology, exactly as the review said)
    after : 1 failed  -- E   Expected: 20.0 ± 2.0e-11

A class-level `PER_KIND_uA` now carries the four ceilings as literals (20.0 tissue,
141.37166941154072 electrode-acute, 70.68583470577036 electrode-chronic, 965.3764143567779
instrument), each independently pinned by the fail-ceiling oracle. The companion test
asserts the **spread** between literals rather than repeating them, so a decomposition that
collapsed every kind onto the headline fails while still satisfying a minimum.

**(c)** `test_the_interval_contains_the_point_estimate` — no behaviour change, kept as a
real regression guard for the pre-C1.8 candidate-set divergence. Its docstring now carries
the proof that containment is a *theorem* about the two constructions and says what it
cannot catch; re-pointed at `limit_bearing_ceiling_uA`.

**(a)** landed in commit 11.

### Gates at `da46d4a` — 809 passed · all five clean

## Commit 14 — `d1b878e` ledger hash for 94

## Commit 15 — M3 (beyond your enumerated list, on the review's Phase 1b list): `7ec2006` `docs(plan): book the five unbooked movers, repair 67(b), and log the render sites still raw`

Documentation only. All five re-verified at HEAD before booking (the review measured them
at `505aea6`; I did not take them on trust). §9's ledger 67(b) row re-assigned C1.10 → C2.1,
with a note that it must not be used as a Phase-2 exit criterion against C1.10.
Ledger 95 closed; **ledger 96 opened as `pending`** for the non-amplitude render sites.

## Commit 16 — `3d74abe` ledger hash for 95

---

# Final package-wide grep for unfloored limit renders (at `3d74abe`)

**No amplitude limit is rendered raw anywhere in `neurostim/` or `examples/`.** 23
`format_limit` call sites outside `_limits.py`, plus `Interval.describe(floor=True)`. The
grep for any f-string formatting a `max_current` / `ceiling_uA` / `limiting_current` /
`limit_bearing_ceiling` / `binding_uA` returns nothing outside `format_limit` (the single
hit, `io/tabular.py:255`, is a dict key for the *applied* amplitude, not a limit).

**Still raw, all non-amplitude — now logged as ledger 96 (`pending`), not fixed:**

| overstates | site | measured |
|---|---|---|
| **YES** | `safety/charge.py:152`, `safety/assessment.py:934,954`, `io/report.py:328` — `cic_limit_uC_cm2:.4g` | Pt and PtIr at `medium="in_vivo"`, `policy="conservative"`: limit `7.142857142857143`, prints `7.143`, `format_limit` gives `7.142` |
| **YES** | `safety/assessment.py:1051,1061`, `data/butterwick2007.py:198` — `threshold_A_per_cm2:.4g` | 4 of 7 swept pulse widths: 10 µs `1.0367951010756424`→`1.037`; 100 µs `0.3739570834831887`→`0.374`; 400 µs→`0.2024`; 1000 µs→`0.1349` |
| no (latent) | `safety/assessment.py:1162,1177,1187`, `materials.py:271,273` — chronic band `:g` | 6 sig digits on stored round ends (20/50 µC/cm²) |
| no | `models/thermal.py:599` `limit_K:g`; Cogan 4 nC/phase `:g` | exact constants |

Not fixed because it is outside Phase 1b's scope and each site needs its own decision about
units and about whether `format_limit`'s 4-significant-digit promise is right for a
published charge density. Ledger 96 records it with the measurements.

---

# D2's settle budget, in one sentence (unchanged since the F2 commit)

**Directional: downward, `STEP_BUDGET = 4` floats of the seed; upward, a *distance*
`max(CLIMB_TOLERANCE × value, PLATEAU_ALLOWANCE × plateau)` — bracketed exponentially in
ulps, then bisected — where `plateau` is the caller-declared width, in the limit's own
units, of one step of the predicate's own arithmetic (0.0 when the predicate resolves every
float).** Both halves are now straddled by behavioural tests (ledger 93).

# Can Phase 2 proceed?

**Yes, with one condition that is already written into the code and a test.**

The review's NO-GO rested on four items. B1 (ledger 88), B2 (ledger 89) and M2 (ledger 92)
are closed, each with a red-before/green-after test and all five gates clean. M3 (ledger 95)
is booked. M4/M5 (ledger 93, 94) are closed with verified mutation kills.

**The condition is B3, and it is not closed — deliberately.** The corrected seed cannot land
before C2.3's clause: measured, it turns 160 of 160 monophasic configurations into
`LimitDidNotSettle` on the way *up*. What is in place instead is the mechanism that makes
landing it late impossible to miss: `_water_window_seed_uA` holds the required expression
with its verified constants, and `TestTheWaterWindowSeedInvertsItsOwnPredicate` fails —
proved non-vacuous against a simulated C2.3 — with a message naming the function to edit.
**C2.3 must add the drift term in the same commit as the drift clause.** §6 books the
99745.57 → 767.27 move with that requirement attached.

Two things the review flagged that I did **not** touch, both correctly out of scope:
M1 (`limits_incomplete`, withdrawn by you) and F11–F14.

---
---

# NEWLY ASSIGNED — the non-amplitude render class (ledger 96)

## Commit 17 — `5381185` `fix(safety): floor a limit whatever its unit, and gate the constants that look round`

### Seven sites, not six

Your brief named six. The grep for the fix turned up a **seventh**: `safety/charge.py`'s
`published range` line was hand-rolling `{lo:.4g}-{hi:.4g}` for the charge-injection band
**immediately beside a µA interval that already floored** (`describe('uA', floor=True)`).
It printed `7.143-10.71`; it now uses `Interval.describe('uC/cm^2', floor=True)` and prints
`7.142-10.71`. That is the one the first red output caught.

| site | was | now |
|---|---|---|
| `safety/charge.py` limit line | `7.143` | `7.142` |
| `safety/charge.py` published range **(7th)** | `7.143-10.71` | `7.142-10.71` |
| `safety/assessment.py` Charge-injection FAIL branch | `7.143` | `7.142` |
| `safety/assessment.py` Charge-injection CAUTION/PASS branch | `7.143` | `7.142` |
| `io/report.py` PDF row | `7.143` | `7.142` |
| `safety/assessment.py` Current-density FAIL branch | `:.4g` | `format_limit` |
| `safety/assessment.py` Current-density CAUTION/PASS branch | `0.3057` | `0.3056` |
| `data/butterwick2007.py` `ThresholdComparison.describe` | `:.4g` | `format_limit` |

`butterwick2007` imports `format_limit` **inside the function**: `neurostim.safety` imports
`neurostim.data` at module scope, so a top-level import closes the cycle.
`uncertainty.Interval.describe` already dodges it the same way.

### Two committed numbers moved — one of them was a real overstatement on the README headline

    - Current density: 0.2829 A/cm^2 of the 0.3057 A/cm^2 electroporation threshold ...
    + Current density: 0.2829 A/cm^2 of the 0.3056 A/cm^2 electroporation threshold ...
    - Charge injection limit: 56.59 uC/cm^2 of 100 uC/cm^2 (57 % used)
    + Charge injection limit: 56.59 uC/cm^2 of 100.0 uC/cm^2 (57 % used)

The worked example's own electroporation threshold is `0.3056762856382303` and the README
was printing `0.3057` — above it. Regenerated via `scripts/regenerate_example_output.py` in
the same commit; `--check` clean.

### The `:g` sites: made structurally safe, not argued safe

They do not overstate today **only** because every constant behind them is round — the kind
of assumption that stops being true silently. `test_every_constant_printed_with_g_renders_exactly`
asserts `float(f"{v:g}") == v` over **77 constants** (every material's chronic-band ends,
water-window bounds and CIC ends at both policies × three polarities, Cogan's 4 nC/phase,
the ISO 14708-3 2 K thermal limit): **0 failures today**. The two values this commit had to
floor — `7.142857142857143` and `9.348927087079717` — are asserted to *fail* the property
in the same test, so the gate is not vacuous. A non-round constant added later fails there,
and whoever adds it chooses between flooring the site and widening the format.

A fifth test pins that **applied** quantities are *not* floored (`0.3979` stays, `0.3978`
asserted absent) — flooring one understates what is being delivered.

### RED

    FAILED ::test_the_derated_charge_injection_limit_floors_on_every_surface
    FAILED ::test_the_pdf_charge_injection_row_floors
    FAILED ::test_the_electroporation_threshold_floors
    3 failed, 2 passed, 144 deselected

    E   AssertionError: 0.3979 A/cm^2 of the 9.349 A/cm^2 electroporation threshold ...
        assert '9.348' in '... the 9.349 A/cm^2 electroporation threshold ...'
    E   '7.143' is contained here: ... published range 7.143-10.71 uC/cm^2 ...   <- the 7th site

(The two that passed red are the gate and the applied-quantity pin — neither is a repair.)

### GREEN — `5 passed, 144 deselected in 1.40s`

### Gates at `5381185`

    pytest -q  814 passed · ruff clean · mypy clean · ledger 96 entries · regenerate --check clean

`_limits.py`'s module docstring now states the rule is about maxima and not about
microamps, with both measurements. §6 gains three `[96]` rows.

## Commit 18 — `aaf3c85` `docs(ledger): record the commit that closed 96`

# Final grep, at `aaf3c85`

No limit in any unit is rendered raw except the six `:g` sites now covered by the
round-trip gate: `materials.py:271,273`, `models/thermal.py:599`,
`safety/assessment.py:1162,1177,1187` — all chronic-band ends or the ISO limit, all exact.
