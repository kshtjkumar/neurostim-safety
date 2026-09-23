# Phase 1 — the verdict core. Execution report.

Repo `.`, branch at start `f068a8d`,
interpreter `.venv/bin/python` (3.14.7).

Baseline gates, re-run before touching anything:
`650 passed, 1 skipped` · ruff clean · `mypy: Success: no issues found in 52 source files`
· `ledger_check.py: OK: 87 entries, 7 fields each`.

(Note: `mypy` is not on PATH; it is `.venv/bin/python -m mypy neurostim`.)

## Status

- [ ] C1.1 rank NOT_EVALUATED below PASS
- [ ] C1.2 reject out-of-window resting potential
- [ ] C1.3 floor every reported limit
- [ ] C1.4 margin / kind / provisional for every limit-bearing check
- [ ] C1.5 unsafe_at_any_amplitude
- [ ] C1.6 limiting current = min over LIMIT_BEARING
- [ ] C1.7 limiting_mechanism names a check that ran
- [ ] C1.8 widen the interval
- [ ] C1.9 non-finite settings rejected, row errors recorded
- [ ] C1.10 pin a FAIL and both boundary sides
- [ ] C1.11 monotonicity, containment, dimensional consistency

---

## C1.1 — `7f344db` — rank NOT_EVALUATED below PASS

`fix(safety): rank NOT_EVALUATED below PASS and surface unevaluated checks everywhere`

**Test first.** New file `tests/test_verdict_core.py`, 8 tests.
RED (before the fix), `pytest -q tests/test_verdict_core.py` → `8 failed in 1.35s`:

```
E  AssertionError: assert 1 < 0   (NOT_EVALUATED.rank=1, PASS.rank=0)
E  AssertionError: assert <Status.NOT_EVALUATED> is <Status.PASS>        (T17)
E  AssertionError: assert <Status.NOT_EVALUATED> is <Status.PASS>        (worst-that-ran)
E  AttributeError: 'SafetyAssessment' object has no attribute 'not_evaluated'
E  AssertionError: assert 'PASS' in 'Overall: NOT_EVALUATED'
E  KeyError: 'not_evaluated'                                             (report_to_json)
E  AssertionError: assert '3 checks not evaluated' in '... Overall assessment: NOT_EVALUATED ...'
E  AttributeError: 'SafetyAssessment' object has no attribute 'not_evaluated'
```

GREEN after: `8 passed in 1.35s`.

**Gates after the commit:** `658 passed, 1 skipped` (650 → 658, +8) · ruff `All checks
passed!` · mypy `Success: no issues found in 52 source files` · ledger
`OK: 87 entries, 7 fields each`.

**Numbers that moved** (§6 row "C1.1 | overall status of every macroelectrode"):

| surface | before | after |
|---|---|---|
| `describe()` overall line, worked example | `Overall: FAIL` | `Overall: FAIL (1 check not evaluated: Shannon criterion)` |
| overall status, any macroelectrode with every applicable check passing | `NOT_EVALUATED` | `PASS` |
| `report_to_json` payload | no `not_evaluated` key | top-level `not_evaluated: [...]` |
| PDF header | `Overall assessment: NOT_EVALUATED · limiting current ...` | `... (3 checks not evaluated: ...) · limiting current ...` |
| GUI headline | same shape | same shape + the note |

Regenerated with `scripts/regenerate_example_output.py` in the same commit (README
quick-start block; `example_output/` is untracked by design).

**Deviation from §6, reported as required.** §6's C1.1 row names "README status table" as
a surface to update. There is no status table in README.md — `grep -n NOT_EVALUATED
README.md` finds only the generated transcript, which the script owns. Nothing else moved.

**Ledger.** Entry 11 Fix + Commit filled. 67(c) is closed by this commit but 67 stays
`pending` until C1.10 closes (a) and (b) — the gate parses one hash per row.

---

## C1.2 — `339fabe` — reject an out-of-window resting potential

`fix(safety): reject a resting potential outside the material's own water window`

**Test first.** 8 tests added to `tests/test_verdict_core.py`
(`TestRestingPotentialIsInsideTheWindow`). RED on the 5 that assert the new behaviour;
the 3 negative controls (boundary value accepted, Ta2O5 accepted, in-window still works)
pass before and after, which is the point of having them.

```
5 failed, 11 passed in 1.41s
E  Failed: DID NOT RAISE ValueError   x5
FAILED ...::test_the_calculator_refuses_a_resting_potential_past_the_anodic_limit
FAILED ...::test_the_message_names_the_window_it_is_outside
FAILED ...::test_the_calculator_refuses_a_resting_potential_past_the_cathodic_limit
FAILED ...::test_the_module_function_refuses_what_it_used_to_answer
FAILED ...::test_the_evaluate_entry_point_refuses_it_too
```

After adding the validator, the two oracle guard tests broke exactly as the plan
predicted — second red, on the pre-existing tests:

```
FAILED tests/test_oracles.py::TestFailCeiling::test_a_non_monotone_predicate_is_reported_not_bisected
FAILED tests/test_oracles.py::TestFailCeiling::test_a_band_narrower_than_one_probe_step_is_reported
E  ValueError: resting_potential_V = 0.95 V is outside Pt's water window [-0.6, 0.8] V ...
2 failed, 664 passed, 1 skipped
```

Re-pointed both at a scripted calculator → GREEN: `tests/test_oracles.py` `40 passed,
1 skipped`.

**Gates after the commit:** `666 passed, 1 skipped` (658 → 666, +8) · ruff clean · mypy
clean · ledger OK · `regenerate_example_output.py --check`: `OK: the README transcript
matches the package's own output` (nothing regenerated — C1.2 moves no worked-example
number, and §6 does not list it as a numeric commit).

**Numbers that moved** (§6 row C1.2):

| call | before | after |
|---|---|---|
| `SafetyCalculator(..., resting_potential_V=0.9)` on Pt | constructs | `ValueError` naming the window |
| `max_charge_density_in_window_uC_cm2("Pt", resting_potential_V=5.0)` | `1400.0` | `ValueError` |
| `water_window.evaluate("Pt", q, resting_potential_V=0.9)` | returns a result | `ValueError` |

**The scripted calculator.** Lives in `tests/test_oracles.py` (`ScriptedCalculator`,
`scripted_calculator`). The script travels in the `electrode` slot so `rebuild_at` and the
per-check suffix invariant are exercised whole; `neurostim.SafetyCalculator` is
monkeypatched for the test's duration so the oracle builds it, and
`_assert_constructor_is_frozen` still runs against the stub's own signature — which is why
that signature repeats `SafetyCalculator`'s argument for argument. Every carried argument
is a non-default value asserted on arrival (fixture rule), so a dropped forward fails
rather than scripting the same answer.

**Two §6 items that do not exist, reported as required.** §6's C1.2 row names "README
settings table" and "GUI field validation" as same-commit updates. Neither surface exists:
`grep -n resting README.md neurostim/gui/app.py` returns nothing — the GUI's
`_build_calculator` does not expose `resting_potential_V` at all. Nothing was changed for
them.

**One thing I now believe is wrong, outside Phase 1 and not in the ledger.** SS316LVM's
`WaterWindow` is stored with `scale="of polarisation from rest (measured vs SCE)"` — the
bounds are a polarisation *magnitude relative to rest*, not absolute potentials on a
reference scale, and the stored note says so. But `water_window.evaluate` computes
`peak = resting + sign*excursion` and tests `window.contains(peak)`, which is only correct
for an absolute window; for 316LVM the correct test is `|excursion| <= 1.2`, independent of
rest. My new validator inherits the same conflation (it rejects a 316LVM resting potential
outside +/-1.2 V, which on that material's own scale is not the right question). I kept
the existing convention rather than changing a verdict Phase 1 does not own, but this looks
like an unlogged defect worth a ledger entry and a Phase 4 commit.

---

## C1.3 — `e0833d1` — floor every reported limit, at every render site

`fix(safety): floor every reported limit, at every render site`

**Test first.** 18 tests added (`TestFloorToPass`, `TestFormatLimit`,
`TestEveryBackSolvedLimitPassesItsOwnCheck`, `TestEveryRenderSiteFloors`).
RED: `16 failed, 18 passed in 2.58s`

```
FAILED ...TestFloorToPass::test_it_steps_down_to_the_largest_passing_value
FAILED ...TestFloorToPass::test_it_steps_up_when_the_back_solve_undershot
FAILED ...TestFloorToPass::test_the_returned_value_is_asserted_to_be_the_boundary
FAILED ...TestFloorToPass::test_exhausting_the_step_budget_raises_and_names_the_check
FAILED ...TestFloorToPass::test_a_non_finite_or_non_positive_value_is_returned_unchanged
FAILED ...TestFormatLimit::test_the_worked_example_headline_floors
FAILED ...TestFormatLimit::test_the_shannon_limit_floors
FAILED ...TestFormatLimit::test_the_printed_number_never_exceeds_the_value_it_floors
FAILED ...TestFormatLimit::test_four_significant_digits_are_kept
FAILED ...TestFormatLimit::test_it_does_not_invent_a_number_for_infinity
FAILED ...TestEveryBackSolvedLimitPassesItsOwnCheck::test_the_charge_injection_limit_is_the_boundary
FAILED ...TestEveryBackSolvedLimitPassesItsOwnCheck::test_the_compliance_limit_is_the_boundary
FAILED ...TestEveryRenderSiteFloors::test_describe_floors_the_headline
FAILED ...TestEveryRenderSiteFloors::test_describe_floors_both_ends_of_the_published_range
FAILED ...TestEveryRenderSiteFloors::test_the_pdf_floors_every_limit_it_prints
FAILED ...TestEveryRenderSiteFloors::test_the_figure_annotation_floors
E  ImportError: cannot import name '_limits' from 'neurostim.safety'
E  AssertionError: ('Pt', 'conservative', False, 39.26990816987242)      <- charge limit FAILs its own check
E  AssertionError: (DiscElectrode(100.0,'Pt'), 1.0, 59.40996385380656)   <- compliance limit is not the boundary
```

GREEN after: `tests/test_verdict_core.py` `34 passed`; then the README gate fired exactly
as §6 predicted (second red, on a pre-existing test):

```
E  -Limiting current: 141.4 uA (Pt charge-injection limit)
E  +Limiting current: 141.3 uA (Pt charge-injection limit)
E  -  across published ranges: 141.4-212.1 uA ...
E  +  across published ranges: 141.3-212.0 uA ...
FAILED tests/test_build_gates.py::TestGeneratedReadmeTranscript::test_the_committed_transcript_is_what_the_package_prints
FAILED tests/test_build_gates.py::TestGeneratedReadmeTranscript::test_check_exits_zero_on_the_committed_readme
```
→ regenerated in the same commit.

**Gates after the commit:** `684 passed, 1 skipped` (666 → 684, +18) · ruff clean · mypy
`Success: no issues found in 53 source files` · ledger OK · README transcript OK.

**Numbers that moved.** Strings first (this is ledger 49):

| surface | before | after |
|---|---|---|
| `describe()` headline | `Limiting current: 141.4 uA` | `141.3 uA` |
| `describe()` published range | `141.4-212.1 uA` | `141.3-212.0 uA` |
| PDF "Shannon current limit" | `472.8 µA` | `472.7 µA` |
| PDF "Charge-injection current limit" / header | `141.4 µA` | `141.3 µA` |
| figure annotation (`viz/plots.py`) | `binding limit 141 µA` (`:.3g`) | `binding limit 141.3 µA` |
| GUI headline | `141.4 uA` | `141.3 uA` |
| `charge.describe()` published-range current interval | `141.4-212.1 uA` | `141.3-212.0 uA` |

Values (ledger 9), worked example, all one ulp:

| quantity | before | after |
|---|---|---|
| `max_current_shannon_uA` | `472.78772824642175` | `472.7877282464217` |
| `max_charge_shannon_uC` | `0.09455754564928434` | `0.09455754564928433` |
| `compliance.max_current_uA` | `965.3764143567778` | `965.3764143567779` |
| `charge.max_current_uA` / `max_current_cic_uA` / `limiting_current_uA` | `141.37166941154072` | unchanged |

Across the sweep: 12 of 108 charge/Shannon limits moved down one ulp, 4 up one ulp; 6 of
36 compliance limits moved down, 14 up.

**Three deviations from the plan, reported as required.**

1. **`format_limit` keeps trailing zeros.** My first implementation rendered through
   `:.{sig}g`, giving `format_limit(212.05750411731108) == "212"` and
   `format_limit(20.0) == "20"`. §6 writes the expected outputs as `212.0` and `20.00`,
   so I changed it to emit exactly `sig` significant digits with trailing zeros, keeping
   `%g`'s fixed/scientific threshold (15285.5 still reads `1.528e+04`). This makes the
   plan's two stated renderings both come out right; it also means a printed limit of
   `100.0` no longer reads `100`.
2. **Compliance was floored too, and `ComplianceResult` grew three fields.** §6's C1.3 row
   says "any back-solved limit at its own boundary" but never names compliance, and
   ledger 9 names only `charge.py` and `shannon.py`. I measured 6 of 36 compliance limits
   FAILing their own check, which C1.6's T2b (`not at_limit.failed`) would have tripped
   over. Doing it needed one expression shared by the back-solve and the forward check, so
   `compliance.required_voltage_V()` is new and `ComplianceResult` now carries
   `pulse_width_us`, `area_cm2`, `capacitance_uF_cm2`. Nothing constructs
   `ComplianceResult` by hand outside `evaluate`.
3. **`ChargeResult.max_charge_uC` is floored as well** (same class, not listed in §6).
   `0.028274333882308142` on the ring — unchanged in value there.

Also: the README **Uncertainty** section (`:146-153`) was hand-written and stale by a whole
release — it showed `70.69 uA` where the package prints `141.3`. §6's C1.3 row points at
README `:136`/`:140` for the interval; I corrected the block and added one sentence saying
limit intervals floor. It will move again at C1.6 and C1.8.

**Interval.describe** takes `floor: bool = False` rather than always flooring: most
intervals in the package are measurements or published ranges, and rounding a measurement
down is not conservative, it is wrong. Only limit intervals pass `floor=True`.

---

## C1.4 — `7e9bd3c` — margin, kind and provisional for every limit-bearing check

`fix(safety): give every limit-bearing check a margin, a kind and a provisional flag`

**Test first.** 4 oracle pins added to `tests/test_oracles.py` + 10 package tests in
`tests/test_verdict_core.py`.
RED: `10 failed, 35 passed in 2.74s`

```
FAILED ...TestEveryLimitBearingCheckHasAMargin::test_every_limit_bearing_margin_is_its_own_fail_ceiling
FAILED ...TestEveryLimitBearingCheckHasAMargin::test_the_water_window_margin_is_positive_where_the_naive_reading_is_negative
FAILED ...TestEveryLimitBearingCheckHasAMargin::test_the_two_checks_that_had_no_margin_now_have_one
FAILED ...TestEveryLimitBearingCheckHasAMargin::test_the_checks_that_bear_no_limit_keep_an_infinite_margin
FAILED ...TestCheckKindAndProvisional::test_every_check_declares_one_of_the_four_kinds
FAILED ...TestCheckKindAndProvisional::test_the_kind_of_each_check_is_the_one_its_source_measures
FAILED ...TestCheckKindAndProvisional::test_the_current_density_limit_is_always_provisional
FAILED ...TestCheckKindAndProvisional::test_a_caveated_charge_injection_limit_is_provisional
FAILED ...TestCheckKindAndProvisional::test_a_verified_limit_at_its_measured_conditions_is_not_provisional
FAILED ...TestCheckKindAndProvisional::test_kind_and_provisional_reach_the_json
E  ImportError: cannot import name 'LIMIT_BEARING' from 'neurostim.safety'
E  KeyError: 'kind'            (report_to_json check rows)
E  AttributeError / margin == inf where a ceiling was expected
```

GREEN after: `tests/test_verdict_core.py` `45 passed`.

**Gates after the commit:** `700 passed` — **0 skipped**, down from 1: the oracle's
`LIMIT_BEARING` drift guard, parked since Phase 0b, now runs (650 → 700, +50 across the
phase; +16 this commit) · ruff clean · mypy clean · ledger OK · README transcript
unchanged and OK.

**The five plan constants reproduce exactly**, `DiscElectrode(100,"Pt")` at 80 µA/200 µs,
through `check_fail_ceiling_uA`:

| check | oracle | plan | margin × 80 µA |
|---|---|---|---|
| Microelectrode charge/phase | `20.0` | 20.0 | `20.0` |
| Chronic degradation | `19.634954084936204` | 19.634954084936204 | same |
| Charge injection limit | `39.26990816987241` | 39.26990816987241 | same |
| Water window | `58.90486225480862` | 58.90486225480862 | same |
| Current density | `86.42793360039114` | 86.42793360039114 | same |

(Charge injection's oracle value is the *post-C1.3* floored limit; before C1.3 the package
answered `39.26990816987242`, one ulp high, which FAILed its own check.)

**Numbers that moved** (§6 rows "C1.4 assessment.json checks[].margin" and "Check schema"):

| quantity | before | after |
|---|---|---|
| `Water window` margin (100 µm Pt disc @ 80 µA) | `inf` (JSON `null`) | `0.7363107781851077` (ceiling 58.905 µA) |
| `Chronic degradation` margin | `inf` (JSON `null`) | `0.24543692606170255` (ceiling 19.635 µA) |
| `Microelectrode charge/phase` margin | `0.25` | `0.25` (now exactly ceiling/current) |
| `Current density` margin | `1.0803491700048893` | same value, now floored to the strict `<` boundary |
| `Shannon criterion` margin on a macroelectrode | `max_charge/charge` | `max_current/current` (same to <1 ulp) |
| `report_to_json` check rows | name/status/summary/margin | **+ kind, ceiling_uA, provisional** |

**One deviation from the plan, reported as required.** §6 books "`Check` schema gains
`kind`, `provisional`". I added a **third** field, `ceiling_uA`. Reason: D3 explicitly
drops v1's `min(c.margin * I …)` form, and C1.6's minimum has to be over the actual
ceilings — a product that is one ulp high names a limit that FAILs its own check, which is
the defect Phase 1 exists to remove. `margin` is then `ceiling_uA / current_uA`. It is a
new JSON key (`ceiling_uA`, `null` for `inf`).

**Two smaller design choices worth flagging.** `kind` is a read-only property over a single
`CHECK_KINDS` table rather than a constructor argument — there are 28 `Check(...)` sites in
`assessment.py`, up to four per check, and a per-branch `kind` is four places for the same
check to disagree about what it is. And the ceiling is attached in `assess()` for the same
reason, with one rule the plan does not state but the oracle requires: **a NOT_EVALUATED
check imposes no ceiling** whatever its own back-solve says — Shannon's `max_current_uA` is
a finite number on a microelectrode, where the check does not apply. The transition-band
microelectrode check needed the same treatment explicitly, since it reports CAUTION (not
NOT_EVALUATED) at every amplitude.

**Provisional fixtures.** My first draft asserted "some material has `cic.verified ==
False`" — none does. Replaced with three fixtures whose premises are asserted from the
database in the test itself: TIROF (CIC stored with no pulse width), Pt at 2000 µs (ten
times its measured 200 µs), SS316LVM at `policy="optimistic"` (its source endorses
conservative).

---

## C1.5 — `e704d8a` — refuse a limiting current when no amplitude is safe

`fix(safety): refuse to report a limiting current for a protocol unsafe at any amplitude`

**Test first.** 7 tests (`TestUnsafeAtAnyAmplitude`).
RED: `5 failed, 2 passed in 2.87s` — the 2 passing are the oracle-witness precondition and
the negative control (the worked example still prints its number).

```
FAILED ...::test_unsafe_at_any_amplitude_names_the_check_the_oracle_names
FAILED ...::test_describe_prints_no_number_and_names_the_check
FAILED ...::test_report_to_json_refuses_the_number_too
FAILED ...::test_the_pdf_header_refuses_the_number
FAILED ...::test_the_gui_headline_refuses_the_number
E  AttributeError: 'SafetyAssessment' object has no attribute 'unsafe_at_any_amplitude'
E  KeyError: 'unsafe_at_any_amplitude'
E  ImportError: cannot import name 'headline_text' from 'neurostim.gui.app'
```

GREEN after: `52 passed`.

**Gates after the commit:** `707 passed` (700 → 707, +7) · ruff clean · mypy clean ·
ledger OK · README transcript unchanged and OK (the worked example is biphasic).

**Numbers that moved** (§6 rows "C1.5 [84]"), monophasic
`CylindricalBandElectrode(1270,1500,"PtIr")` at 3000 µA / 90 µs / 130 Hz:

| surface | before | after |
|---|---|---|
| `describe()` | `Limiting current: 1.528e+04 uA (Shannon tissue-damage criterion)` + a `across published ranges:` line | `Limiting current: none -- no amplitude is safe: Charge balance FAILs at every amplitude` (interval line suppressed) |
| PDF header | `... · limiting current 1.528e+04 µA (Shannon …)` | `... · no amplitude is safe: Charge balance FAILs at every amplitude` |
| GUI headline | same shape as the PDF | same refusal |
| `report()["limiting_current_uA"]` | `15285.50941588086` | `None` |
| `report()["limiting_mechanism"]` | `"Shannon tissue-damage criterion"` | the refusal sentence |
| `report_to_json` payload | — | **+ top-level `unsafe_at_any_amplitude: ["Charge balance"]`** |

Oracle agreement, re-measured this session: `amplitude_independent_failures` →
`('Charge balance',)`; unrestricted `fail_ceiling_uA` → `0.0`; restricted to
`LIMIT_BEARING` → `15285.50941588086`, which is exactly what the package's
`limiting_current_uA` attribute still returns (it was `15285.509415880857` before C1.3's
flooring — the plan's figure — and the floored value now matches the oracle bit for bit).

**Two deviations, reported as required.**

1. **`report()` is a surface I changed that §6 does not list for C1.5.** §6 names
   "`describe()` golden, `report_to_json` schema, PDF header, GUI headline". But
   `report_to_json`'s `results` block *is* `calc.report()`, and leaving `15285.5` there
   while the top level says "unsafe" hands a machine consumer the number the commit exists
   to withhold. So `limiting_current_uA` is `None` and `limiting_mechanism` carries the
   sentence. Consequence not in §6: **a batch/sweep CSV row for a monophasic protocol now
   has an empty `limiting_current_uA` cell.** No committed artifact is affected — the
   worked example is biphasic.
2. **The absence is asserted on the headline block, not the whole rendering.** The Shannon
   check's own detail block still prints `current limit 1.528e+04 uA`, and the PDF's
   Computed-quantities table still has a "Shannon current limit" row. Those are true
   statements about that criterion; what was false was calling it *the* limiting current.
   My first draft asserted `"1.528e+04" not in text` over all of `describe()` and failed on
   exactly that line — a case where the too-strong assertion would have forced a wrong fix.

---

## C1.6 — `2d63aa2` — THE HEADLINE: limiting current = min over LIMIT_BEARING

`fix(safety): the limiting current is the minimum over every limit-bearing check`

**Test first.** 12 tests (`TestLimitingCurrentIsTheMinimumOverLimitBearingChecks`,
`TestLimitsIncompleteAndByKind`). RED: `12 failed, 53 passed in 5.63s`

```
FAILED ...::test_the_worked_example_limit_is_twenty_microamps
FAILED ...::test_the_mechanism_names_the_check_that_binds
FAILED ...::test_the_named_mechanism_is_always_a_check_that_ran
FAILED ...::test_the_pedef_case_moves_to_the_check_that_actually_binds
FAILED ...::test_reassessing_at_the_reported_limit_fails_nothing
FAILED ...::test_limits_incomplete_is_set_when_a_limit_bearing_check_did_not_run
FAILED ...::test_limits_incomplete_is_clear_when_every_limit_bearing_check_ran
FAILED ...::test_the_headline_is_the_minimum_of_the_per_kind_limits
FAILED ...::test_the_per_kind_limits_disagree_where_it_matters
FAILED ...::test_describe_states_both
FAILED ...::test_the_json_carries_both
FAILED ...::test_the_pdf_and_the_gui_headline_say_the_limit_may_be_lower
E  assert 141.37166941154072 == 20.0 ± 2.0e-05
E  AttributeError: 'SafetyAssessment' object has no attribute 'limits_incomplete'
E  AttributeError: 'SafetyAssessment' object has no attribute 'limiting_current_by_kind'
```

GREEN after: `tests/test_verdict_core.py` `65 passed`; full suite `719 passed, 1 xfailed`.

**T1's `names=LIMIT_BEARING` point, verified as the lead flagged.** On the ring both oracle
forms answer `20.0`. On the monophasic companion they diverge:
`fail_ceiling_uA(calc)` → `0.0`, `fail_ceiling_uA(calc, names=LIMIT_BEARING)` →
`15285.50941588086`, which is what the package's attribute returns. A test written against
the unrestricted form would demand 0.0 there and would still pass on the ring.

**Gates after the commit:** `719 passed, 1 xfailed` (707 → 719, +12) · ruff clean · mypy
clean · ledger OK · README regenerated.

**Numbers that moved** (§6 rows for C1.6, plus C1.7 which this commit subsumes — see below):

| quantity | before | after |
|---|---|---|
| **worked example `limiting_current_uA`** | **`141.37166941154072`** | **`20.0`** (7.0686×) |
| worked example `limiting_mechanism` | `"Pt charge-injection limit"` | `"Microelectrode charge/phase"` |
| `DiscElectrode(40,"PEDOT")` @200 µs limit | `99.67240473569454` "(Shannon…, NOT_EVALUATED)" | `20.0` "(Microelectrode charge/phase)" |
| `describe()` | 1 limiting line + interval | + `by kind: tissue 20.00 uA, electrode-acute 141.3 uA, electrode-chronic 70.68 uA, instrument 965.3 uA` + `INCOMPLETE: 1 limit-bearing check did not run (Shannon criterion)…` |
| `report_to_json` | — | + `limits_incomplete`, `limiting_current_by_kind` |
| PDF header / GUI headline | — | + the INCOMPLETE clause |
| `current_sweep.csv` `limiting_current_uA`, `limiting_mechanism` | per-row 141-ish / `Pt charge-injection limit` | per-row ceilings / check names |

README quick-start regenerated; README **Uncertainty** block and **CHANGELOG** updated —
the CHANGELOG entry carries the recall notice naming the 7.07× figure, as §6 requires.

**C1.7 IS SUBSUMED BY C1.6 — this is the one plan step that did not survive contact.**
C1.7's T3 is `DiscElectrode(40,"PEDOT")` at 200 µs reporting 99.6724 µA "(Shannon
tissue-damage criterion)" while Shannon is NOT_EVALUATED. I measured T3 red at
`e704d8a` (pre-C1.6) and it is green at `2d63aa2` — because `limiting_mechanism` can no
longer be computed from a separate three-string `options` dict once the minimum is over
`Check.ceiling_uA`, and a NOT_EVALUATED check carries `ceiling_uA = inf` so it cannot be
the minimum. Leaving `limiting_mechanism` on the old dict for one commit would have
shipped a state where the named mechanism is not even the binding one. So T3 and its value
assertion landed here, red-before/green-after, and **C1.7 has no remaining work**. I have
not fabricated a commit for it. §6's C1.7 row (`limiting_mechanism` value where the named
check did not run) is discharged by the row above.

**Four existing tests moved, each because its premise stopped holding:**

1. `tests/test_core.py::test_limiting_mechanism_matches_limiting_current` — this *is*
   ledger 66's tautology (it recomputed `min()` over the code's own three candidates).
   Rewritten to look the named check up and assert that check's own ceiling is the
   headline. The value pin is in `test_verdict_core.py` against the oracle.
2. `tests/test_core.py::test_charge_limited_case_makes_the_material_matter` — its fixture
   (500 µm Pt disc, 200 µs) is **no longer charge-limited**: platinum's dissolution
   threshold binds at 490.87 µA, below the CIC ceiling at every policy. Moved to Ta2O5 at
   1 ms, which is, and the test now asserts that before reading the fold. **Finding worth
   recording: with the full candidate set, the charge-injection limit almost never binds —
   I swept 9 materials × 5 diameters × 5 pulse widths and it bound in 2 of 225 cases.**
3. + 4. `tests/test_gui.py::test_k_changes_the_shannon_verdict` and
   `::test_anodic_first_is_wired_through` read the headline to prove a widget is live. A
   minimum over seven checks hides a widget that moves exactly one of them. They now read
   the ceiling of the check the widget controls.
5. `tests/test_oracles.py::test_the_package_headline_is_seven_times_the_ceiling` recorded
   the defect; renamed to `..._now_agrees_with_the_ceiling`, keeping 7.0686 as a historical
   ratio against the superseded value so the record is not lost.
6. `tests/test_uncertainty.py::test_point_estimate_sits_at_the_conservative_end` is
   **`xfail(strict=True)`** — the point estimate (20.0) now sits below the interval
   (141.37–212.06), which is exactly the 18/18 gap the plan says C1.8 closes. Strict, so
   C1.8 cannot land without removing the marker.

---

## C1.7 — NOT COMMITTED. Subsumed by C1.6.

Measured at `e704d8a` (post-C1.5, pre-C1.6): `DiscElectrode(40,"PEDOT")` at 80 µA/200 µs
reported `limiting_current_uA = 99.67240473569454`, `limiting_mechanism = "Shannon
tissue-damage criterion"`, with the Shannon check `NOT_EVALUATED`. That is T3's red, and
it is in C1.6's red output (`test_the_named_mechanism_is_always_a_check_that_ran`).
At `2d63aa2` the same case reports `20.0` / `"Microelectrode charge/phase"`.

Why it cannot be a separate commit: `limiting_mechanism` was computed from its own
three-string `options` dict, independent of the minimum. Once the minimum is over
`Check.ceiling_uA`, the mechanism must be the name of the check holding that minimum or
the two disagree — so rewriting one without the other would ship a commit whose named
mechanism is not the binding one. And because a NOT_EVALUATED check carries
`ceiling_uA = inf`, it can never hold the minimum: C1.7's defect is unreachable by
construction, not by a second guard, so there is no test left that can fail first.

T3 and its value assertion landed in C1.6. §6's C1.7 row is discharged there. **No commit
was fabricated for C1.7.**

---

## C1.8 — `a5dbe52` — widen the interval to the same candidate set

`fix(safety): widen the limiting-current interval to the same candidate set as the point estimate`

**Test first.** 4 tests (`TestTheIntervalContainsThePointEstimate`).
RED: `4 failed in 0.64s`, 19 assertion lines.

```
FAILED ...::test_the_interval_contains_the_point_estimate
FAILED ...::test_the_worked_example_interval_moves_down_with_its_point_estimate
FAILED ...::test_a_published_range_still_widens_the_interval
FAILED ...::test_a_check_that_did_not_run_does_not_narrow_the_interval
E  assert False = contains(20.0) where Interval(low=141.37166941154072, high=212.05750411731108)
E  AssertionError: ('Pt', 'conservative', False, 19.634954084936204, (39.26990816987242, 58.90486225480862))
```
**54 of 54** swept (material × policy × polarity) combinations failed containment — the
plan predicted 18/18 on its own parametrisation.

GREEN after: `4 passed`; full suite `724 passed` (and the strict xfail C1.6 planted is now
removed, as it was designed to force).

**Gates after the commit:** `724 passed, 0 xfailed` (719+1x → 724, +5 net: +4 new, +1 the
xfail returning to a pass) · ruff clean · mypy clean · ledger OK · README regenerated.

**Numbers that moved** (§6 row "C1.8 [+] `limiting_current_interval_uA` and its
`describe()` line"):

| quantity | before | after |
|---|---|---|
| worked-example interval | `[141.37166941154072, 212.05750411731108]` | `[20.0, 20.0]` — collapsed |
| worked-example `describe()` range line | `141.3-212.0 uA (Shannon k 1.5-2.0, full material range)` | `20.00 uA (unchanged: Microelectrode charge/phase has no published range; Shannon k 1.5-2.0 and the material range were propagated and do not bind)` |
| `DiscElectrode(100,"Pt")` @80 µA interval | `[39.26990816987242, 58.90486225480862]` | `[7.853981633974484, 19.634954084936204]` |
| `contains(limit)` over 54 combinations | 0/54 | 54/54 |

**One thing §6 does not anticipate.** On the worked example the interval **collapses to a
point**, because the binding check (Cogan's 4 nC/phase) is a single published number with
no range. §6's row says "an interval that contains 20.00", which it does — degenerately. I
changed the `describe()` parenthetical rather than leave it claiming a spread the
literature does not supply; the old fixed string would have read "across published ranges:
20.00 uA (Shannon k 1.5-2.0, full material range)", which is false about what bounds the
answer.

**Two existing tests moved, both because their premise stopped holding:**

1. `test_platinum_range_reaches_the_final_limit` → `..._reaches_the_charge_injection_ceiling`.
   Rose & Robblee's 100–150 µC/cm² sub-range no longer reaches the *final* limit because
   4 nC/phase binds below platinum's whole band. It still reaches
   `charge.max_current_interval_uA`, where the test now reads it, with the same three
   assertions (141.4, 212.1, fold 1.5).
2. `test_point_estimate_sits_at_the_conservative_end` — `xfail(strict=True)` removed. That
   is what the strict marker was planted for.

---

## C1.9 — `659b3a9` — reject non-finite settings at construction; the oracle guard

`fix(safety): reject non-finite settings at construction, and record row errors`

**Test first.** 19 tests (14 parametrised + 5).
RED: `16 failed, 3 passed in 1.98s` (the 3 that passed are the two negative controls and
`resting_potential_V=nan`, which C1.2 already refused).

```
FAILED ...test_the_setting_is_refused_at_construction[compliance_V-nan]
FAILED ...[compliance_V-inf] [compliance_V--5.0] [compliance_V-0.0]
FAILED ...[tissue_conductivity_S_per_m-nan] [-0.0] [--0.35]
FAILED ...[lead_resistance_ohm-nan] [--1.0]
FAILED ...[measured_impedance_ohm-nan] [-0.0]
FAILED ...[capacitance_uF_cm2-nan] [-0.0]
FAILED ...::test_a_blank_compliance_cell_becomes_an_error_row_not_a_verdict
FAILED ...::test_an_amplitude_the_constructor_refuses_is_not_a_passing_amplitude
FAILED ...::test_the_guard_does_not_hide_a_misspelled_check_name
E  Failed: DID NOT RAISE <class 'ValueError'>   (x13)
E  assert 499.99999999999994 == 50.0            (oracle guard)
```

GREEN after: `19 passed`; full suite `743 passed`.

**Gates after the commit:** `743 passed` (724 → 743, +19) · ruff clean · mypy clean ·
ledger OK · README unchanged and OK.

**Numbers that moved.** None reported — this commit only turns silent wrong answers into
raises. The one measured behaviour change:

| case | before | after |
|---|---|---|
| batch row with a blank `compliance_V` cell | `status=FAIL`, `limiting_current_uA=19.634954`, `error=""` — **identical to the 10 V row** | `status=ERROR`, `error="ValueError: compliance_V must be finite and > 0, got nan"` |
| `SafetyCalculator(..., compliance_V=-5.0)` etc. (13 settings/values) | constructs, produces a verdict | `ValueError` naming the setting |

**Ledger 52 re-measured on today's code**, since the entry describes the pre-Phase-1 shape:
the NaN compliance ceiling was being silently dropped by `min()` exactly as recorded, and
the two rows above were indistinguishable. Root-caused at the input rather than patched at
the `min()`: no `Check.ceiling_uA` can be NaN now, so the order-dependence has no input.

**The oracle guard.** `tests/oracles/fail_ceiling.UNCONSTRUCTIBLE` is a reserved
angle-bracketed stand-in name returned when `rebuild_at` raises `ValueError`. It is
returned regardless of the `names` restriction (an amplitude that cannot be built is not
one at which a named check passes), and the `try` wraps the rebuild alone so the
unknown-check-name `ValueError` still surfaces — asserted by its own test. Pinned with a
scripted calculator that refuses above 50 µA while its checks pass below 500: the oracle
answers `50.0`, not `499.99999999999994` and not a stack trace.

---

## C1.10 — `7930620` — pin a FAIL and both boundaries for every check; fix the plateau

`fix(safety): find a ceiling across a plateau, and pin a FAIL and both boundaries for every check`

**Test first.** 17 tests (`TestEveryCheckHasAPinnedFailure` ×8,
`TestBothSidesOfEveryBoundary` ×9 incl. 7 parametrised).
RED: `2 failed, 15 passed in 0.76s`

```
FAILED ...TestEveryCheckHasAPinnedFailure::test_the_water_window_fails_when_the_peak_leaves_it
FAILED ...TestBothSidesOfEveryBoundary::test_a_water_window_ceiling_is_found_even_when_the_predicate_plateaus
E  neurostim.safety._limits.LimitDidNotSettle: Water window: the back-solved limit
   122.71846303085117 still passes its own check 4 steps above 122.71846303085123,
   so it is not the boundary and the reported limit would be lower than the limit.
```

GREEN after: `105 passed` in the file, `760 passed` overall.

**Gates after the commit:** `760 passed` (743 → 760, +17) · ruff clean · mypy clean ·
ledger OK · README transcript **byte-identical** (no reported number moved).

**A REGRESSION I INTRODUCED AT C1.4, FOUND BY THIS COMMIT'S OWN FIXTURE.** Since C1.4 the
water-window ceiling goes through `floor_to_pass`. For a resting potential near a window
edge, `assess()` **raised `LimitDidNotSettle` on valid input** — measured **7 of 216**
valid (material, resting potential, polarity, diameter) configurations, e.g.
`DiscElectrode(500,"Pt")` + `resting_potential_V=-0.55`. It shipped in `7e9bd3c`,
`e704d8a`, `2d63aa2`, `a5dbe52`, `659b3a9` and is fixed here.

Cause: a **plateau**, not a bad back-solve. The predicate is
`cathodic <= resting + excursion <= anodic`. At `resting = -0.55 V` the excursion at the
boundary is 0.05 V, so the sum is two numbers of very different magnitude and its ulp is
an order of magnitude larger than the excursion's — a run of consecutive amplitudes maps to
the same peak float, all passing, and the seed sits more than four floats below the top of
that run.

**Deviation from D2, reported as required.** D2 point 2 specifies a single 4-step budget
that raises when exhausted. The two directions now differ:
- **down** keeps `STEP_BUDGET = 4` — that direction corrects a one-ulp association error,
  and five steps genuinely means the back-solve does not invert its forward comparison
  (ledger 9);
- **up** is bounded *relatively* by `CLIMB_TOLERANCE = 1e-9` of the value — exponential
  bracket in ulps, then bisection — because a plateau's length is a property of the
  check's arithmetic, not evidence about the back-solve. A seed further than 1e-9
  relatively below the boundary still raises.

No previously settled limit moves: both routes return the largest passing float. Verified
by the README transcript being byte-identical and all five oracle constants still exact.

**Ledger.** 63 and 64 closed. **67 is NOT closed** and its Commit stays `pending`: (c) was
closed at C1.1, but (a) the envelope's inside-PASS needs C2.5's duty-cycle repair and (b)
the unbalanced-biphasic FAIL needs C2.1 to make imbalance expressible. The plan's C1.10 row
claims 67(a,b); those two branches are structurally unreachable in Phase 1, so C1.10 pinned
a FAIL for every check that *has* a reachable one (eight of nine) and recorded the rest.

**Not verified here:** the plan's claim that C1.10 "kills S3, C2, P3, A5, A3, A4". No
mutation harness is installed and the instruction was to install nothing.

---

## C1.11 — `505aea6` — monotonicity, containment, dimensional consistency

`test: pin monotonicity, interval containment and dimensional consistency`

**Test-only commit — no red-before is possible**, because these invariants already hold;
ledger 69's defect is that nothing asserted them. Non-vacuity was demonstrated instead, by
mutating the package and watching each test fail:

```
=== MUTANTS IN PLACE ===
FAILED ...TestMoreCurrentIsNeverSafer::test_no_check_gains_margin_as_current_rises
       (_margin_from_ceiling multiplies instead of dividing above 500 uA)
FAILED ...TestDimensionalConsistency::test_the_activated_volume_is_the_sphere_of_the_activation_radius
       E  Obtained: 2852297.6151921498 / Expected: 0.0028522976151921496   (1e-3 dropped)
2 failed, 7 passed
=== RESTORED === 9 passed

=== MUTANTS IN PLACE ===
FAILED ...TestMoreCurrentIsNeverSafer::test_a_ceiling_does_not_depend_on_the_amplitude_that_asked_for_it
       (a ceiling offset by current_uA * 1e-9)
FAILED ...TestTheIntervalContainsThePointEstimate::test_a_published_range_still_widens_the_interval
       E  Obtained: 1.0 / Expected: 2.5   (interval drops chronic degradation)
2 failed, 7 passed
=== RESTORED === 115 passed
```

GREEN: `10 passed` for the new classes; full suite `770 passed`.

**Gates after the commit:** `770 passed` (760 → 770, +10) · ruff clean · mypy clean ·
ledger OK · README unchanged and OK.

**Numbers that moved:** none. Test-only.

**One invariant stronger than the plan asks for.** T15 as written in `audit_tests.md`
compares statuses and margins. I added `test_a_ceiling_does_not_depend_on_the_amplitude_
that_asked_for_it` and `test_the_limiting_current_does_not_depend_on_the_amplitude_
requested`: over five decades every `Check.ceiling_uA` is **bit-identical** and
`limiting_current_uA` takes exactly one value. That is what makes the headline meaningful
at all, and it is the property a `headroom`-style reading of `margin` would fail.

**Ledger 69 is PARTIAL, not closed** — its Commit stays `pending`. §9 maps it to C0.2,
C0.5, C1.11 **and C3.5** (T18). Phase 1 discharges everything but T18.

---

# Phase 1 complete

`f068a8d..505aea6`, **10 commits** (C1.7 subsumed by C1.6 — see its section).

Final gates, all four, re-run on `505aea6`:
- `.venv/bin/python -m pytest -q` → **`770 passed`** (baseline 650 passed 1 skipped; +120 tests, and the one Phase-0b skip now runs)
- `ruff check neurostim tests examples scripts` → `All checks passed!`
- `.venv/bin/python -m mypy neurostim` → `Success: no issues found in 53 source files`
- `.venv/bin/python scripts/ledger_check.py` → `OK: 87 entries, 7 fields each, every package defect scheduled in the plan`
- plus `scripts/regenerate_example_output.py --check` → `OK: the README transcript matches the package's own output`

Working tree clean apart from `_conversation_history.md`, which is the lead's and was not
touched.

| commit | hash | tests after |
|---|---|---|
| C1.1 | `7f344db` | 658 |
| C1.2 | `339fabe` | 666 |
| C1.3 | `e0833d1` | 684 |
| C1.4 | `7e9bd3c` | 700 |
| C1.5 | `e704d8a` | 707 |
| C1.6 | `2d63aa2` | 719 (+1 xfail) |
| C1.7 | — subsumed | — |
| C1.8 | `a5dbe52` | 724 |
| C1.9 | `659b3a9` | 743 |
| C1.10 | `7930620` | 760 |
| C1.11 | `505aea6` | 770 |

## Ledger

Closed with hashes: **1, 9, 11, 13, 14, 49, 52, 63, 64, 66, 84**.
Left open with recorded progress: **30** (partial — `ChronicThreshold` still has no
`verified` field; C4.1), **67** (c closed at C1.1; a and b need C2.5 and C2.1), **69**
(partial — T18 at C3.5).

## §6 targets that do not exist

Reported per instruction. Each was searched for and is absent from the repo:
- C1.1 "README status table" — README has no status table.
- C1.2 "README settings table" and "GUI field validation" — the GUI does not expose
  `resting_potential_V` at all.
- C1.4 / C1.5 "JSON consumer docs" — `docs/` contains only `audit/`; README does not
  mention `report_to_json` or `assessment.json`.
