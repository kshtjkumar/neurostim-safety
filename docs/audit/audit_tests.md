# Test-Suite Rigor Audit — `neurostim_safety`

Read-only audit. No file under `.` was modified.
All mutation work ran on the throwaway copy at
`<scratchpad>`.

**Environment.** Local venv is Python **3.14.7**. `pytest-cov` is **NOT installed**
(`ModuleNotFoundError: No module named 'pytest_cov'`) and nothing was installed. Coverage was
measured with the surviving `sys.monitoring` harness (`$SCRATCH/cov.py` → `$SCRATCH/cov.json`,
`cov.pkl`), re-post-processed here into `$SCRATCH/cov_real.json`.

**Read-only confirmation.** Verified after the fact: every file under `neurostim/`, `tests/`,
`scripts/`, `examples/`, `.github/` and `pyproject.toml` is byte-untouched since before this audit
began (`find ... -newermt` returns empty for all of them). The mutation copy was diffed back to the
repo after the run — `MUT COPY PRISTINE`, all 42 mutations reverted. Three paths in the repo *did*
change during my session window — `_conversation_history.md`, `CODE_MISTAKES_LOG.md` and
`example_output/*` — none written by me; the first two are the session's own bookkeeping and the
third is what `examples/worked_example.py` emits when someone runs it (relevant to §9b.4).

**Baseline.** `522 passed in 22.44s` locally, exit code 0, no skips (this machine has
`pdftotext` and PyQt6). Under instrumentation the suite still returns rc=0, so the coverage
numbers describe the real green run.

---

## 0. VERDICT — the green is SPLIT: the bibliography is EARNED, the safety maths is HOLLOW

The suite is two suites welded together, and they are of opposite quality. One verdict for the
whole thing would be wrong in both directions.

**The literature layer is EARNED.** `test_literature.py` (1350 lines) and
`test_published_cases.py` (721 lines) do the thing almost nobody does: quote the source sentence
in the docstring and assert the stored constant against it. Cogan 2008 Table 2 row by row;
Shannon's own "k = 1.5 … used in all calculations"; McCreery 1990 Table I; IT'IS v4.2;
ISO 14708-3 Table 101; Riedy & Walter; Rose 1985. Several go further and are genuine independent
derivations: Kuncel & Grill's 0.0993 A/cm² reconstructed through three independent steps
(lateral area → Newman access resistance → Ohm's law) to 2 %; McCreery eq. (1) at 60 µm giving
160 µC/cm²; Elwassif's perfusion sweep matched by analytic `1/(1 + a/L)` to 10 %; Pennes closed
form against a separately written finite-difference solve to 1e-4. The mutation run confirms this
independently — the 29 killed mutants are concentrated almost entirely in the literature and
physics layers. **The README's provenance claim is defensible for the constants.**

**The decision layer is HOLLOW.** The README says the tests "pin the package to its sources".
They pin the *inputs*. They barely constrain the code that turns those inputs into a verdict:

| evidence | measured |
|---|---|
| line coverage | 89.2 % |
| **true branch coverage** (PEP-649 artefacts excluded) | **46.7 %** (338/724) |
| branch coverage of `safety/current_density.py` | **9.1 %** (1/11) |
| **mutation score** (42 mutants, full suite each) | **69 %** — **13 survivors** |
| `Status.FAIL` assertions in the entire 522-test suite | **3** |
| of 9 safety checks, how many have a failing case pinned | **3 of 9** |
| uses of `.passes` / `.failed` / `.cautions` / `.status.value` in tests | **0** |
| confirmed defects the suite does not catch | **13** |
| provably dead branches blessed by a passing test | **3** |

Three findings carry the verdict:

1. **Every boundary comparison in a safety check is unprotected.** `<=` → `<` survives in
   Shannon (S3), charge injection (C2) and compliance (P3), and `>` → `>=` survives in chronic
   degradation (A5). This follows directly from having no failing case: if nothing ever crosses a
   limit, the limit's inclusivity is unobservable. `CAUTION_MARGIN` can be **halved** (A2) and the
   suite stays green.

2. **Dropped unit conversions survive.** Four mutations of the form "delete a 10⁻⁶ / 10⁻³ / 4⁄3"
   pass all 522 tests (C4, M5, M10, M4) — because the tests that cover those functions assert a
   *ratio* or a *sign*, in which the constant cancels. `neurostim/units.py`, which owns every
   conversion in a package whose answers are unit-critical, has **0 of 2 real branches covered and
   no test file importing it**.

3. **The headline output is pinned by a tautology, and is wrong.** `limiting_current_uA` —
   documented as "the number to programme against" — is asserted by a test that recomputes the
   same `min` over the same three candidates the code uses, so it is structurally incapable of
   noticing the four omitted limits. Measured: `DiscElectrode(100 µm, "Pt")` at 200 µs reports
   **39.27 µA** while the assessment simultaneously prints `FAIL` for *Microelectrode charge/phase*
   (ceiling **20.0 µA**) and *Chronic degradation* (ceiling **19.63 µA**). On another electrode it
   attributes the limit to "Shannon tissue-damage criterion" while the Shannon check reads
   `NOT_EVALUATED`. And re-assessing at the package's own reported limit **fails its own forward
   check in 17 of 54 material × policy × polarity combinations** (`100.00000000000001 > 100.0`).

Beyond those, three branches are **provably dead while a passing test blesses them**: the
envelope's `inside` PASS (unreachable over a 300,000-protocol sweep — the McCreery envelope
rejects its own fit protocol because the duty-cycle reference is 100 % where the fit was 4 %); the
unbalanced-biphasic FAIL (imbalance is structurally inexpressible, and the one test asserting
`is_charge_balanced` certifies that rather than exposing it); and overall `PASS` for any
macroelectrode (`NOT_EVALUATED` outranks `PASS`, and the microelectrode check is always
`NOT_EVALUATED` for a macroelectrode).

**Assume hollow until proven otherwise** was the right prior for the safety maths and the wrong
prior for the bibliography. The gap between them is the actionable finding: this project already
knows how to write a test that cannot pass by accident — §5's kill list shows it — and simply
never applied that standard to the code that decides whether a protocol is safe. §10 lists 26
tests, ranked, that would close all 13 defects and all 13 mutation survivors.

**One caveat on my own numbers.** The raw harness reported 29.7 % branch coverage. The venv is
Python 3.14, where PEP 649 gives every annotated `def` a hidden `__annotate__` code object with an
uncoverable branch — 413 phantom branches of 1137. Reporting 29.7 % would have overstated the
problem. **46.7 %** is the honest figure and is what §2 uses throughout.

---

## 1. TAUTOLOGIES

### 1a. Classification of the literature assertions

Every assertion in `test_literature.py` and `test_published_cases.py` was classified.

**(a) against an independently-stated published number — the bulk, and they are sound.**
`TestCogan2008Table2` (CIC rows, pulse widths, water windows), `TestShannon1992Primary`
(K_SHANNON, K_DAMAGE_OBSERVED, FIT_* conditions), `TestMcCreery1990Dataset` (TABLE_I size,
CONTROL_SITES=23, TOTAL_SITES_EXAMINED=64), `TestITISDatabase` (κ=0.547, ρ=1044.5, c=3695.8),
`TestISO14708_3` (39 °C, CEM43 thresholds 2/40/40/21/16), `TestMcCreery2010` (2 vs 4 nC/ph,
150 vs 60 µm radii), `TestRiedyWalter1996`, `TestBeebeRose1988Primary`, `TestGabriel1996PartIII`
(Cole-Cole Table 1 quadruples), `TestButterwick2007` anchors, `TestStoneyTehovnikCurrentDistance`
(1292, 1037-1547, 300-27000). These cite the sentence, quote the number, and assert it. Good.

**(b) against an independent derivation — fewer, and the strongest tests in the repo.**

- `test_published_cases.py::TestKuncelGrill2004::test_current_density_predicted_from_geometry_and_voltage`
  — 0.0993 A/cm² reconstructed through three independent steps. This is the model test.
- `test_literature.py::TestMcCreery1990Dataset::test_local_charge_density_falls_with_depth` —
  eq. (1) at 60 µm under a 45 µm facet: `800·(1 − 60/√(45²+60²)) = 800·0.2 = 160`. Derivable by hand.
- `test_published_cases.py::TestInternalConsistency::test_pennes_analytic_equals_finite_difference_solve`
  — closed form vs a separately written numerical solve, rel=1e-4.
- `test_literature.py::TestElwassif2006Validation::test_perfusion_attenuation_matches_the_analytic_form`
  — analytic `1/(1+a/L)` vs their FEM sweep, rel=0.10.
- `test_core.py::TestCurrentDensity::test_outer_quarter_of_a_disc_exceeds_its_own_average` —
  `J/J_avg > 1 ⟺ r/a > √3/2 ⟹ 25 %`, derivation stated in the docstring.
- `test_literature.py::TestStainlessSteel::test_nonfaradaic_limit_is_consistent_with_double_layer_capacitance`
  — `20 µC/cm² ÷ 1.2 V ≈ 20 µF/cm²`, a real cross-check that two independently transcribed
  constants were read correctly.
- `test_published_cases.py::TestRose1985Ta2O5::test_etched_tantalum_roughness_factor` — only
  reproduces if the smooth baseline is thickness-corrected 5 V → 10 V first. A genuine trap.

**(c) against the code's own output — THE COMPLETE LIST.**

| # | test | why it is circular |
|---|---|---|
| C1 | `test_published_cases.py::TestWaterWindowConsistency::test_injecting_the_cic_reaches_the_window_edge_and_no_further` | `effective_capacitance_uF_cm2` **is defined as** `cic/available_V` (`water_window.py:90`). `max_charge_density_in_window_uC_cm2` returns `available_V * capacitance` = `available_V * cic/available_V` = `cic`. Algebraic identity. Cannot fail for any material with a window. 10 parametrised cases, zero information. The docstring even concedes "must hold by design". |
| C2 | `test_published_cases.py::TestComplianceConsistency::test_polarisation_at_the_cic_equals_the_half_window` | `polarisation_V(cic, cic/\|V_cath\|)` = `\|V_cath\|`. Same identity, 4 parametrised cases. |
| C3 | `test_published_cases.py::TestWaterWindowConsistency::test_polarisation_can_never_exceed_the_window_within_the_cic` | reduces to `min(\|V_cath\|,\|V_anod\|) ≤ \|V_cath\|+\|V_anod\|`. True for all reals. |
| C4 | `test_published_cases.py::TestComplianceConsistency::test_required_voltage_is_ohmic_plus_polarisation` | asserts `required_V == ohmic_drop_V + polarisation_V`; `compliance.py:205` literally constructs `required_V=ohmic + polar`. Verified exact float equality — this is `a == a`. **This is the test that should have caught "compliance models one interface, not two".** |
| C5 | `test_core.py::TestAssessment::test_limiting_mechanism_matches_limiting_current` | asserts `limiting_current_uA == min(shannon, charge, compliance)`; `assessment.py:125-131` computes exactly that `min` over exactly those three. The test restates the bug. **This is the test that should have caught "limiting current omits four computed limits".** |
| C6 | `test_core.py::TestShannon::test_max_charge_formula` | asserts `shannon_max_charge_uC(1e-2, 1.7) == sqrt(1e-2 * 10**1.7)`; `shannon.py:224` is `math.sqrt(area_cm2 * 10.0**k)`. Character-for-character the same expression. |
| C7 | `test_core.py::TestVoltageTransient::test_separates_polarisation_from_the_ohmic_step` (2nd assert) | `max_polarisation_V == abs(peak) - abs(access)` re-states the module's own subtraction at rel=1e-6. |
| C8 | `test_models_io_viz.py::TestThermal::test_penetration_depth_formula` | recomputes `sqrt(κ/W)` from the object's own `.perfusion_conductance_W_per_m3K`, which is the same intermediate the property uses. |
| C9 | `test_models_io_viz.py::TestThermal::test_evaluate_uses_rms_current` | `result.power_W == (I_rms*1e-6)**2 * R` restates `ohmic_power_W`. |
| C10 | `test_models_io_viz.py::TestStrengthDuration::test_chronaxie_tau_relationship` (1st assert) | `chronaxie_from_tau_us(200) == 200*log(2)` restates line 110 exactly. |
| C11 | `test_core.py::TestShannon::test_max_charge_round_trip` | `shannon_k(shannon_max_charge_uC(A,k), A) == k` — an inverse-function pair sharing the same `10**k`. A common sign/exponent error in **both** passes it. Weak, though not strictly (c). |
| C12 | `test_models_io_viz.py::TestStrengthDuration::test_weiss_fit_recovers_its_own_parameters`, `test_lapicque_fit_recovers_its_own_parameters`, `TestVTA::test_fit_recovers_its_own_parameters`, `TestVTA::test_radius_threshold_round_trip` | data generated by the forward model, fitted by the inverse model, compared to the generating parameters. Tests the optimiser, not the physics; a wrong shared constant round-trips perfectly. `test_published_cases.py::TestAsanuma1976::test_a_weiss_fit_to_the_measured_chronaxie_round_trips` is the same shape dressed in a citation. |
| C13 | `test_core.py::TestBackwardCompatibility::test_original_numeric_results_unchanged` | `shannon_metric == -0.043152417` (rel=1e-6) is back-filled from observed output. It is *checkable* by hand (log₁₀(0.016²/2.827e-4) = −0.0432) but no derivation is stated, so as written it is a regression lock on whatever the code printed. Same for `test_shannon_current_limit_changed_with_the_default_k` (472.7877282, 595.2044855). |
| C14 | `test_uncertainty.py::TestPropagationIntoAssessment::test_platinum_range_reaches_the_final_limit` | 141.4 / 212.1 µA are the code's output. Derivable (100 µC/cm² × 2.827e-4 cm² ÷ 200 µs = 141.4 µA), but unstated — and crucially it pins the interval **only over the same three mechanisms**, so it too is blind to the four omitted limits. |
| C15 | `test_literature.py::TestButterwick2007::test_anchor_points_reproduce_from_the_fitted_power_law` and `test_published_cases.py::TestButterwick2007::test_both_retina_anchors_reproduce` | the power law is *fitted through* those two anchors, so passing through them is guaranteed by construction. rel=1e-6 on a self-consistency identity. Duplicated across two files. |

Fifteen circular assertions, of which **C4 and C5 are the two that were supposed to catch two of
the six known defects.**

### 1b. The structural tautology

`test_core.py::TestProtocol::test_asymmetric_return_phase_stays_balanced` asserts
`StimProtocol(80,200,130,1, return_phase_ratio=4.0).is_charge_balanced`. Measured on the real
package: `return_phase_current_uA = I/r` and `return_phase_width_us = W·r`, so
`return_charge = (I/r)·(W·r)·1e-6 ≡ I·W·1e-6 ≡ charge_per_phase`. Net charge is **exactly 0.0
for every ratio**:

```
ratio  0.25: lead 80uA x 100us | return  320uA x   25us | net 0 uC | balanced=True
ratio   0.5: lead 80uA x 100us | return  160uA x   50us | net 0 uC | balanced=True
ratio     2: lead 80uA x 100us | return   40uA x  200us | net 0 uC | balanced=True
ratio    10: lead 80uA x 100us | return    8uA x 1000us | net 0 uC | balanced=True
```

The test does not verify charge balance; it certifies that imbalance is **inexpressible**. That
is why `assessment.py:567` (`if not protocol.is_charge_balanced:`) is one-sided in coverage and
lines 568-576 are dead.

---

## 2. COVERAGE — measured, line AND branch, per module

`pytest-cov` is absent, so this is the `sys.monitoring` harness: `events.LINE` for lines,
`BRANCH_LEFT`/`BRANCH_RIGHT` for edges, against statements from `co_lines()` and conditional
jump targets from `dis`. A branch counts covered only when **both** sides fired.
`unknown_hits` (runtime hits with no static counterpart) = 0, so the static model is exact.

**One correction to the raw harness output.** The venv is Python 3.14, where PEP 649 gives
every annotated `def` a hidden `__annotate__` code object containing an uncoverable
`if format != 1: raise` branch. Those inflate the denominator by 413 phantom branches
(1137 → 724 real). Reporting them would overstate the problem, so **all branch figures below
exclude `__annotate__` objects**. Raw-harness branch coverage was 29.7 %; the honest figure is
**46.7 %**.

| module | stmts | hit | **line %** | branches | both sides | **branch %** |
|---|---:|---:|---:|---:|---:|---:|
| `neurostim/__init__.py` | 48 | 47 | 97.9 | 0 | 0 | -- |
| `neurostim/audit.py` | 113 | 99 | 87.6 | 12 | 4 | 33.3 |
| `neurostim/data/__init__.py` | 5 | 4 | 80.0 | 0 | 0 | -- |
| `neurostim/data/asanuma1976.py` | 118 | 106 | 89.8 | 9 | 2 | 22.2 |
| `neurostim/data/butterwick2007.py` | 113 | 98 | 86.7 | 14 | 5 | 35.7 |
| `neurostim/data/cogan2016.py` | 73 | 71 | 97.3 | 2 | 0 | 0.0 |
| `neurostim/data/current_distribution.py` | 17 | 15 | 88.2 | 0 | 0 | -- |
| `neurostim/data/elwassif2006.py` | 68 | 65 | 95.6 | 0 | 0 | -- |
| `neurostim/data/gabriel1996.py` | 73 | 68 | 93.2 | 5 | 2 | 40.0 |
| `neurostim/data/iso14708_3.py` | 64 | 56 | 87.5 | 9 | 3 | 33.3 |
| `neurostim/data/mccreery1990.py` | 179 | 174 | 97.2 | 20 | 17 | 85.0 |
| `neurostim/data/mccreery1995.py` | 68 | 67 | 98.5 | 4 | 4 | 100.0 |
| `neurostim/data/mccreery2010.py` | 38 | 33 | 86.8 | 2 | 1 | 50.0 |
| `neurostim/data/riedy_walter1996.py` | 93 | 87 | 93.5 | 2 | 0 | 0.0 |
| `neurostim/data/ta2o5_capacitor.py` | 170 | 150 | 88.2 | 7 | 0 | 0.0 |
| `neurostim/electrodes.py` | 108 | 100 | 92.6 | 4 | 2 | 50.0 |
| `neurostim/geometry/__init__.py` | 7 | 6 | 85.7 | 0 | 0 | -- |
| `neurostim/geometry/arrays.py` | 101 | 73 | 72.3 | 24 | 12 | 50.0 |
| `neurostim/geometry/base.py` | 47 | 45 | 95.7 | 6 | 6 | 100.0 |
| `neurostim/geometry/planar.py` | 73 | 70 | 95.9 | 3 | 2 | 66.7 |
| `neurostim/geometry/volumetric.py` | 125 | 118 | 94.4 | 12 | 7 | 58.3 |
| `neurostim/gui/__init__.py` | 4 | 3 | 75.0 | 0 | 0 | -- |
| `neurostim/gui/__main__.py` | 5 | 0 | 0.0 | 1 | 0 | 0.0 |
| `neurostim/gui/app.py` | 284 | 270 | 95.1 | 21 | 14 | 66.7 |
| `neurostim/io/__init__.py` | 7 | 6 | 85.7 | 0 | 0 | -- |
| `neurostim/io/fem.py` | 168 | 91 | 54.2 | 32 | 5 | 15.6 |
| `neurostim/io/report.py` | 256 | 247 | 96.5 | 26 | 16 | 61.5 |
| `neurostim/io/tabular.py` | 159 | 134 | 84.3 | 27 | 15 | 55.6 |
| `neurostim/materials.py` | 431 | 399 | 92.6 | 46 | 23 | 50.0 |
| `neurostim/models/__init__.py` | 43 | 42 | 97.7 | 0 | 0 | -- |
| `neurostim/models/field.py` | 135 | 92 | 68.1 | 25 | 6 | 24.0 |
| `neurostim/models/strength_duration.py` | 129 | 89 | 69.0 | 16 | 4 | 25.0 |
| `neurostim/models/thermal.py` | 346 | 272 | 78.6 | 51 | 13 | 25.5 |
| `neurostim/models/vta.py` | 133 | 108 | 81.2 | 20 | 2 | 10.0 |
| `neurostim/protocol.py` | 125 | 113 | 90.4 | 21 | 12 | 57.1 |
| `neurostim/references.py` | 511 | 506 | 99.0 | 10 | 1 | 10.0 |
| `neurostim/safety/__init__.py` | 10 | 9 | 90.0 | 0 | 0 | -- |
| `neurostim/safety/assessment.py` | 523 | 489 | 93.5 | 67 | 47 | 70.1 |
| `neurostim/safety/charge.py` | 181 | 152 | 84.0 | 33 | 15 | 45.5 |
| `neurostim/safety/compliance.py` | 129 | 115 | 89.1 | 21 | 7 | 33.3 |
| `neurostim/safety/current_density.py` | 79 | 69 | 87.3 | 11 | 1 | 9.1 |
| `neurostim/safety/envelope.py` | 157 | 154 | 98.1 | 32 | 22 | 68.8 |
| `neurostim/safety/shannon.py` | 148 | 132 | 89.2 | 19 | 8 | 42.1 |
| `neurostim/safety/water_window.py` | 115 | 99 | 86.1 | 21 | 10 | 47.6 |
| `neurostim/sensitivity.py` | 119 | 109 | 91.6 | 12 | 8 | 66.7 |
| `neurostim/transient.py` | 112 | 94 | 83.9 | 13 | 5 | 38.5 |
| `neurostim/uncertainty.py` | 100 | 95 | 95.0 | 22 | 18 | 81.8 |
| `neurostim/units.py` | 79 | 58 | 73.4 | 2 | 0 | 0.0 |
| `neurostim/viz/__init__.py` | 6 | 5 | 83.3 | 0 | 0 | -- |
| `neurostim/viz/plots.py` | 373 | 347 | 93.0 | 37 | 17 | 45.9 |
| `neurostim/viz/style.py` | 113 | 106 | 93.8 | 3 | 2 | 66.7 |
| **TOTAL** | **6681** | **5957** | **89.2** | **724** | **338** | **46.7** |

**89.2 % line, 46.7 % branch.** The 42-point gap is the finding in one number:
the suite *executes* the package but does not *decide* it.

### 2a. The specific uncovered branches that carry safety logic

Named, with file:line and what the missing side means. "one-sided" = the condition was only ever
evaluated one way across all 522 tests.

**`neurostim/safety/assessment.py` — 70.1 % branch (47/67); missing lines 200-205, 240-248, 352-356, 396-400, 568-576**

| line | branch | what is never exercised |
|---|---|---|
| `assessment.py:239` | `if not result.passes:` one-sided | **The Shannon FAIL branch.** Lines 240-248 never run. In 522 tests no protocol has ever exceeded the Shannon line. The package's flagship criterion has no failing case. |
| `assessment.py:351` | `if result.inside:` one-sided | **Dead.** Lines 352-356, the only path that emits `"protocol is within the conditions the damage criterion was fitted at"`, never executes — see §9.6. |
| `assessment.py:567` | `if not protocol.is_charge_balanced:` one-sided | **Dead.** Lines 568-576, the unbalanced-biphasic FAIL, are unreachable — §1b. |
| `assessment.py:209` | `if area_cm2 is not None and is_microelectrode(...)` one-sided | the `area_cm2 is None` path (Shannon evaluated with no regime guard) never taken. |
| `assessment.py:229` | `if protocol is not None:` one-sided | `_shannon_check` without a protocol — no conditions warning — never taken. |
| `assessment.py:256` | `outside_envelope = envelope is not None and ...` one-sided | `_shannon_check` with `envelope=None` never taken. |
| `assessment.py:259` | `CAUTION if (stretched or thin) else PASS` one-sided | one of the two outcomes of the Shannon status ternary is never produced. |
| `assessment.py:111` | `failed` property | **never called by any test.** The list of FAIL checks is an untested accessor. |
| `assessment.py:116` | `cautions` property | **never called by any test.** |
| `assessment.py:150` | `if self.charge.max_current_interval_uA is not None:` one-sided | the `None` fallback is `# pragma: no cover`, fine. |
| `assessment.py:461`, `:475` | `threshold / charge_nC if charge_nC else inf` one-sided | zero-charge guard never hit. |

**`neurostim/safety/current_density.py` — 9.1 % branch (1/11). The worst module in the package.**

| line | branch | what is never exercised |
|---|---|---|
| `current_density.py:90` | `if not isfinite(area_cm2) or area_cm2 <= 0` one-sided ×2 | neither validation arm ever fires. |
| `current_density.py:92` | `if not isfinite(current_uA)` one-sided | NaN current is never rejected in a test. |
| `current_density.py:104` | `if not 0.0 <= fraction_of_radius < 1.0` one-sided | only the `>= 1.0` rim case is tested (`test_density_diverges_at_the_rim`); **negative radius fraction is never rejected**. |
| `current_density.py:118` | `if not 0.0 < area_fraction <= 1.0` one-sided ×2 | `disc_ratio_at_area_fraction` is never called with an invalid argument. |
| `current_density.py:156` | `if self.edge_concentrates:` one-sided | |
| `current_density.py:192`, `:193` | `0.0 if recessed else DISC_FRACTION_ABOVE_AVERAGE` / `1.0 if recessed else DISC_CENTRE_RATIO` one-sided | **`recessed=True` is never passed anywhere in the suite.** The entire recessed-electrode path — the documented mitigation for edge concentration — is untested. |
| `current_density.py:165` | `if self.threshold is not None:` one-sided | |

**`neurostim/safety/compliance.py` — 33.3 % branch (7/21)**

| line | branch | what is never exercised |
|---|---|---|
| `compliance.py:73` | `return self.required_V <= self.available_V` — the FAIL side | **no test ever drives compliance to INSUFFICIENT.** `assessment.py:624` `if not result.passes:` is never taken. |
| `compliance.py:109` | `if self.lead_resistance_ohm:` one-sided | **`lead_resistance_ohm` is never non-zero in any test.** The parameter is accepted, documented, summed into `total_r`, and never exercised. |
| `compliance.py:146` | `if lead_resistance_ohm < 0 or not isfinite(...)` one-sided ×2 | negative/NaN lead resistance never rejected. |
| `compliance.py:152` | `if not isfinite(measured_impedance_ohm) or <= 0` one-sided ×2 | invalid measured impedance never rejected. |
| `compliance.py:85`, `:96` | `available_V is None or available_V <= 0` one-sided ×4 | `compliance_V=0` and the `required_V <= 0` guard are never reached. |
| `compliance.py:192` | `if capacitance_uF_cm2 is None:` one-sided | a caller-supplied capacitance never reaches compliance. |

**`neurostim/safety/water_window.py` — 47.6 % branch (10/21)**

| line | branch | what is never exercised |
|---|---|---|
| `water_window.py:234` | `if available_V <= 0: return 0.0` one-sided | **a resting potential already at or past the window edge returns a zero limit — never tested.** This is the one physical situation the module says it exists to model ("what it adds is the effect of anything that shifts the starting potential"). |
| `water_window.py:101` | `if not isfinite(capacitance) or <= 0` one-sided ×2 | |
| `water_window.py:133`, `:140` | `if self.window is None` in `passes` / `headroom_V` one-sided | the no-window branch of these two properties never runs. |
| `water_window.py:223` | `if capacitance_uF_cm2 is None:` one-sided | |
| `assessment.py:327` | `if not result.passes:` (water-window FAIL) | **never taken** — no protocol in the suite leaves the water window. |

**`neurostim/safety/shannon.py` — 42.1 % branch (8/19)** — every validation guard
(`:120`, `:206`, `:211`, `:222`, `:243`) is one-sided, i.e. the raise arm fires but the
`shannon_max_charge_uC`/`shannon_max_current_uA` guards are never hit from their own entry points;
`:176` `if frequency_hz is not None` one-sided; `:279` `current_margin` zero-charge guard one-sided.

**`neurostim/safety/charge.py` — 45.5 % branch (15/33)** — `:125` `if charge_density <= 0` one-sided;
`:154` `elif medium == "in_vivo" and derating_note` one-sided; `:162` `if not self.verified`
one-sided (**no unverified material is ever rendered**); `:229` `scale = 1e3 if units=="mC/cm2"`
one-sided; `:242` `if recommendation_note` one-sided; `:260` polarity ternary one-sided.

**`neurostim/safety/envelope.py` — 68.8 % branch (22/32)** — `:79` `if reference == 0 or value == 0`
one-sided ×2; `:141` `inside` one-sided; `:162` area-out-of-range rendering one-sided;
`:234` duration direction ternary one-sided; `:257` `"conservative" if duty < 0.95 else "inside"`
one-sided — **the `"inside"` duty-cycle direction is never produced**, see §9.6.

**`neurostim/protocol.py` — 57.1 % branch (12/21)** — `:231`
`if return_phase_ratio != 1.0 and waveform == "biphasic"` is **never taken at all** (the asymmetric
return phase is never rendered in `describe()`); `:237` `if not is_charge_balanced` one-sided.

**`neurostim/units.py` — 0 of 2 real branches, 58/79 lines.** No test file imports
`neurostim.units`. Every `_convert` table (`CHARGE_TO_UC`, `CURRENT_TO_UA`, `TIME_TO_US`,
`LENGTH_TO_UM`, `AREA_TO_CM2`, `CHARGE_DENSITY_TO_UC_CM2`), every public `to_*` wrapper
(lines 89, 94, 99, 104, 109, 114), the `KeyError → ValueError` translation (lines 79-84),
`cm2_to_m2`, `mC_cm2_to_uC_cm2`, `uC_cm2_to_mC_cm2`, `current_uA_from_charge` (155-157),
`celsius_to_kelvin`, `kelvin_to_celsius` — **all uncovered**. The module that owns every unit
conversion in a package whose answers are unit-critical has no direct test.

**`neurostim/models/vta.py` — 10.0 % branch (2/20)**, `models/field.py` — 24.0 %,
`models/strength_duration.py` — 25.0 %, `models/thermal.py` — 25.5 %, `io/fem.py` — 15.6 %.

---

## 3. MISSING NEGATIVE TESTS — the pass/fail pinning matrix

*A limit is untested unless something crosses it.* Across 522 tests there are exactly **three**
`Status.FAIL` assertions, and **zero** uses of `.passes`, `.failed`, `.cautions` or
`status.value` on an assessment (grep verified — all four return no hits in `tests/`).

| check | PASS pinned? | CAUTION pinned? | **FAIL pinned?** | NOT_EVALUATED pinned? | verdict |
|---|---|---|---|---|---|
| **Shannon criterion** | yes — `test_core.py:512` | yes — `test_core.py:502` | **NO** | yes — `test_core.py:276` | **limit untested** |
| **Charge injection limit** | yes — `test_published_cases.py:294`, `test_literature.py:660` | yes — `test_core.py:348` (pulse-width), `test_published_cases.py:684` (policy) | **NO** | n/a | **limit untested** |
| **Water window** | yes — `test_published_cases.py:295` | **NO** (the `headroom_V < 0.1` gate is never crossed) | **NO** | yes — `test_core.py:338` (Ta2O5) | **limit untested** |
| **Charge balance** | yes — `test_literature.py:1318` | n/a | yes — `test_core.py:303` (monophasic only) | n/a | **half-pinned**: the monophasic arm is pinned, the unbalanced-biphasic arm is dead code (§1b) |
| **Compliance voltage** | implied only | **NO** (the `utilisation > 0.8` gate is never crossed) | **NO** | yes — `test_core.py:323` | **limit untested** |
| **Current density** | yes — `test_literature.py:1318` | yes | yes — `test_literature.py:1010` | n/a | **fully pinned** ✅ |
| **Microelectrode charge/phase** | no explicit PASS | yes (transition band, implied) | yes — `test_core.py:277` | yes — `test_core.py:284` | **mostly pinned** |
| **Chronic degradation** | yes — implied | yes — `test_literature.py:661` | **NO** | n/a | **limit untested** |
| **Validated envelope** | yes — `test_core.py:511` | yes — `test_core.py:504` | n/a (no FAIL state) | n/a | **pinned for what it has** |

**Six of the nine checks have no failing case at all.** Every one of those FAIL states is
*reachable* — I constructed each on the real package, so these are omissions, not impossibilities:

```
Shannon FAIL          CylindricalBandElectrode(1270,1500,"SIROF"), StimProtocol(20000,400,50,1)
Charge-injection FAIL DiscElectrode(500,"Pt"),  StimProtocol(3000,200,50,1)
Water-window FAIL     DiscElectrode(500,"Pt"),  StimProtocol(300,200,50,1), resting_potential_V=-0.55
Compliance FAIL       DiscElectrode(50,"Pt"),   StimProtocol(50,200,50,1), compliance_V=1.0
Chronic FAIL          DiscElectrode(500,"Pt"),  StimProtocol(3000,200,50,1)
```

Two boundary gates are *never crossed in either direction*: `assessment.py:337`
`headroom_V < 0.1` (water window CAUTION) and `assessment.py:635` `utilisation > 0.8`
(compliance CAUTION). Both are pure magic numbers with no test on either side.

### The specific per-check gaps you asked about

- **Shannon** — passing pinned, failing NOT. Also unpinned: the exact boundary. Nothing asserts
  that a protocol at `k_metric == k_threshold` passes and one an epsilon above fails.
- **Charge injection** — passing pinned (`Pt` at 22 µC/cm² vs 50), failing NOT. The
  `charge_density <= cic_limit` boundary at `charge.py:115` is never approached.
- **Water window** — passing pinned, failing NOT, and the passing case is the tautology C1.
- **Charge balance** — monophasic FAIL pinned (`test_core.py:303`). Biphasic PASS pinned. The
  unbalanced-biphasic FAIL is unreachable by construction, so the branch is dead.
- **Compliance** — NOT_EVALUATED pinned, PASS implied, FAIL and CAUTION both absent. There is no
  test in which a stimulator runs out of voltage — the failure mode the module's own docstring
  calls out as "silent in most hardware".
- **Current density** — the one check done properly: `test_literature.py:1010` drives 1 mA into a
  100 µm disc (~12.7 A/cm²) and asserts FAIL, and `test_literature.py:995`/`1318` pin the
  non-failing side. Use this test as the template for the other five.

---

## 4. UNPINNED INVARIANTS

None of the following is asserted anywhere in the suite. Each is a property that must hold for
*every* input, and each is a cheap property test.

**4.1 Monotonicity — "more current is never safer". UNPINNED.**
Nothing asserts that raising `current_uA` can only make each check's status worse-or-equal, or
that `margin` is non-increasing in current. The closest is
`test_gui.py::TestLiveRecompute::test_raising_current_lowers_the_headroom`, which asserts only
that the *detail text changes* (`low != high`) — a string-inequality check that would pass if the
status went from FAIL to PASS. `test_uncertainty.py` never varies current at all.

**4.2 Limiting-current round-trip. UNPINNED, and this is the big one.**
Nothing asserts that setting `I = assessment.limiting_current_uA` lands *exactly on* the boundary —
i.e. that re-assessing at the reported limit gives every check a margin of exactly 1.0 and no FAIL.
Measured on the real package, it does not: for `DiscElectrode(100,"Pt")` + `StimProtocol(40,200,50,1)`
the reported limit is **39.27 µA** while `Microelectrode charge/phase` and `Chronic degradation`
both already read **FAIL** at 40 µA with ceilings of **20.0 µA** and **19.63 µA**. The round-trip
invariant is violated by a factor of 2, and the only test in the area (C5) asserts the wrong `min`.

**4.3 Unit round-trips. UNPINNED.**
`neurostim/units.py` has no test file importing it. Not one of `to_uC`, `to_uA`, `to_us`, `to_um`,
`to_cm2`, `to_uC_cm2` is ever called. `charge_uC(I, W)` → `current_uA_from_charge(Q, W)` → `I` is
never round-tripped, and `current_uA_from_charge` is never called at all. Nor is
`um2_to_cm2`/`cm2_to_m2` consistency (`AREA_TO_CM2["um2"] == 1e-8`) cross-checked against
`CHARGE_DENSITY_TO_UC_CM2["uC/mm2"] == 100.0`.

**4.4 Interval containment — point estimate inside the reported interval. PARTIALLY PINNED, and
pinned too strongly.**
`test_uncertainty.py::TestPropagationIntoAssessment::test_point_estimate_sits_at_the_conservative_end`
asserts `limiting_current_uA == interval.low` for one fixture. That is stronger than containment
and is *false in general*: the point estimate uses `k=1.5` and `policy="conservative"` while the
interval spans `k∈[1.5,2.0]` and the full material range, so with `k=1.7` or
`policy="optimistic"` the point estimate sits strictly inside, not at the low end. Nothing
asserts the weaker, always-true property `interval.contains(limiting_current_uA)` across
policies and `k`. `test_uncertainty.py::TestShannonBand::test_band_brackets_the_default_k` does
this correctly for the Shannon band alone.

**4.5 Dimensional consistency. UNPINNED.**
No test asserts that `charge_density_uC_cm2 × area_cm2 == charge_per_phase_uC`, that
`max_current_uA × pulse_width_us × 1e-6 == max_charge_uC`, or that
`average_current_density_A_per_cm2(I, A) × A × 1e6 == I`. Every one of these would have been
killed by the surviving unit-conversion mutants in §5.

**4.6 Scaling laws on the safety path. UNPINNED.**
`test_core.py` checks that Shannon's current limit halves when pulse width doubles, but nothing
checks the corresponding law for the CIC limit, the electroporation limit, or the compliance
limit. `test_core.py::TestShannon::test_smaller_electrodes_permit_higher_charge_density`
is the only area-scaling assertion on a limit.

**4.7 Status ordering / aggregation. UNPINNED beyond one case.**
`test_core.py::TestAssessment::test_overall_status_is_worst_check` recomputes
`max(c.status.rank)` — the same expression as `_worst` (`assessment.py:84-85`), so it is itself
category (c). `Status.rank` (`assessment.py:57-62`) — the ordering that decides whether
NOT_EVALUATED outranks CAUTION — is never asserted directly.

---

## 5. MUTATION — empirical, on the throwaway copy only

**Method.** `$SCRATCH/mutate2.py` on `$SCRATCH/mut/` (verified byte-identical to the repo before
the run, and every mutation reverted immediately after its pytest invocation — the real repo was
never touched). Each mutant: apply one textual edit, run the **full** suite
(`pytest -q --tb=no tests/`), restore, record exit code. "SURVIVED" = the suite still exits 0.

**Result: 42 mutants — 29 killed, 13 SURVIVED, 0 skipped. Mutation score 69 %.**
Machine-readable at `$SCRATCH/mut_results.json`; full log at `$SCRATCH/mut_log.txt`.

### The 13 survivors

| id | file | mutation | why nothing catches it |
|---|---|---|---|
| **S3** | `safety/shannon.py:265` | `k_metric <= k_threshold` → `<` | The Shannon PASS/FAIL **boundary** is never tested. No protocol sits at `k_metric == k_threshold`, so flipping the inclusive comparison changes no verdict in 522 tests. §3: Shannon has no failing case at all. |
| **C2** | `safety/charge.py:115` | `charge_density <= cic_limit` → `<` | Same for charge injection. Nothing is ever exactly at the CIC. Compounded by defect N2 below, where the package's *own* back-solved limit lands at `100.00000000000001` and so is already on the wrong side of this comparison. |
| **C4** | `safety/charge.py:71` | drop the `* 1e-6` µs→s conversion in `cic_max_current_uA` | **A dropped unit conversion — a 10⁶ error — survives the entire suite.** `cic_max_current_uA` is reachable only via the 0.1.0-compat `SafetyCalculator.max_current_cic_uA`, and the one test that touches it (`test_core.py::TestBackwardCompatibility::test_original_import_and_call_pattern`) asserts only that the dictionary *key exists*. `charge.evaluate` computes `max_current_uA` independently at line 256, so the assessment path masks the bug. |
| **P1** | `safety/compliance.py:179` | `total_r = access_r + lead_R` → `access_r - lead_R` | **`lead_resistance_ohm` is never non-zero in any test** (corroborated by coverage: `compliance.py:109` one-sided). A sign flip on a term that is always 0 is invisible. |
| **P3** | `safety/compliance.py:73` | `required_V <= available_V` → `<` | The compliance PASS/FAIL boundary is never approached; §3 shows compliance has neither a FAIL nor a CAUTION case. |
| **A2** | `safety/assessment.py:42` | `CAUTION_MARGIN = 2.0` → `1.0` | The single constant that decides when a passing check is downgraded to CAUTION — used in `_shannon_check`, `_charge_check`, `_current_density_check` and `_regime_check` — can be **halved** and every test still passes. Nothing pins a margin either side of 2.0. |
| **A3** | `safety/assessment.py:337` | water-window CAUTION gate `headroom_V < 0.1` → `< 0.0` | The gate is never crossed in either direction (§3). A magic number with no test on either side. |
| **A4** | `safety/assessment.py:635` | compliance CAUTION gate `utilisation > 0.8` → `> 2.0` | Same — and `> 2.0` is unreachable in practice, so this mutation silently deletes the compliance CAUTION state entirely. |
| **A5** | `safety/assessment.py:513` | chronic FAIL `> threshold.high` → `>=` | The chronic-degradation FAIL branch has no test (§3), so its boundary is free. |
| **M1** | `models/field.py:135` | `current_density_A_per_m2`: `r_m**2` → `r_m**3` | `field.current_density_*` is never asserted numerically. `test_models_io_viz.py::TestField` checks `potential_V` (1/r) and `field_V_per_m` (1/r²) but never the current-density function, so its exponent is unconstrained. |
| **M4** | `models/vta.py:152` | activated volume `(4/3)·π·r³` → `4·π·r³` | The only volume test, `TestVTA::test_volume_scales_as_current_to_the_three_halves`, asserts a **ratio** of two volumes — the constant cancels exactly. A 3× error in absolute activated volume passes. |
| **M5** | `models/vta.py:151` | µm→mm `* 1e-3` → `* 1e-6` | Same ratio-only test; the unit factor cancels. **Two independent 10³ unit errors in the VTA volume survive** (`vta.py` is 10.0 % branch-covered, the lowest in `models/`). |
| **M10** | `models/strength_duration.py:103` | `weiss_threshold_charge_uC`: drop `* 1e-6` | The only test, `TestStrengthDuration::test_threshold_charge_rises_with_pulse_width`, asserts `np.diff(...) > 0` — a sign, not a magnitude. The unit conversion is untested. |

### What the survivors have in common

Three clean patterns, and they line up exactly with §3 and §4:

1. **Every boundary comparison in a safety check is free** (S3, C2, P3, A5, and the gates A3, A4).
   `<=` → `<` survives in Shannon, charge injection and compliance. This is the direct
   consequence of having no failing case: if nothing ever crosses a limit, the limit's
   inclusivity is unobservable.
2. **Unit conversions survive wherever only a ratio or a sign is asserted** (C4, M5, M10, and M4's
   `4/3`). Four separate mutations of the form "delete a 10⁻⁶ / 10⁻³ / 4⁄3" pass the suite. This
   is §4.3 and §4.5 — no unit round-trip, no dimensional-consistency assertion — cashed out
   empirically.
3. **Parameters that are never given a non-default value are unprotected** (P1: `lead_resistance_ohm`
   always 0; A2: `CAUTION_MARGIN` never probed either side).

### What the kills tell us (the suite's real strengths)

The 29 kills are concentrated in the literature and physics layers, which is consistent with §0:
the Shannon exponent (S1), the `log+log` metric (S2), the mC/cm² scale factor (C1), the in-vivo
derating direction (C3), the µA→A conversion in current density (J1, killed by the *good*
Kuncel & Grill reconstruction), the disc rim ratio (J2), the water-window sign (W3), the
geometry factor (M3), the Pennes 4πκa (M6), `I²R` (M7), the perfusion 1/60 (M8), and `τ·ln2` (M9).
Where the suite reproduces a published number through independent steps, it kills mutants well.

One instructive nuance: **W1** (`C_eff = limit/V` → `limit*V`) *was* killed — by tautology **C2**
from §1. A circular assertion of the form `f(g(x)) == x` does constrain the two halves to remain
each other's inverse, so it catches a change to one side alone. What it can never do is tell you
whether the identity is the right physics. That is the precise sense in which C1-C5 are hollow:
they are self-consistency locks, not measurements.

---

## 6. FLOAT TOLERANCE

Full tolerance census across `tests/*.py` (239 bare `pytest.approx` calls at the default
`rel=1e-6`, plus explicit tolerances):

```
 12 rel=1e-6    11 abs=0.01     6 rel=1e-3     5 rel=0.02     4 rel=1e-4
  4 rel=0.05     3 rel=0.01     2 rel=0.10     2 abs=0.3      2 abs=0.03
  2 abs=0.02     2 abs=0.001    1 rel=1e-9     1 rel=1e-12    1 rel=0.25
  1 rel=0.2      1 rel=0.16     1 rel=0.1      1 rel=0.06     1 rel=0.03
  1 abs=1e-6     1 abs=0.15     1 abs=0.1      1 abs=0.005
```

**Nothing as loose as `rel=0.5`.** The loosest tolerances are defensible and the file header
claims "every tolerance here is the agreement actually achieved, not a target chosen to pass" —
which the docstrings back up case by case. Assessed individually:

| tolerance | test | verdict |
|---|---|---|
| `rel=0.25` | `test_published_cases.py:364` Stoney activation radius (176 µm) vs McCreery damage radius (150 µm) | **justified** — two experiments 42 years apart; the docstring says "within about 20 %". It is a corroboration, not a pin on code. |
| `rel=0.2` | `test_literature.py:216` implied double-layer capacitance 16.7 vs 20 µF/cm² | **justified** — cross-source consistency check, stated as such. |
| `rel=0.16` | `test_published_cases.py:543` Riedy & Walter chronic current | **justified** — docstring names the cause ("to within the tip-area ambiguity"). |
| `rel=0.10` | `test_literature.py:544` **and** `test_published_cases.py:114` perfusion attenuation | **justified but duplicated** — the same assertion appears in two files with the same tolerance. One of them is dead weight. |
| `abs=0.3` on 12.0 and 30.0 | `test_published_cases.py:455-456` Ta₂O₅ roughness | 1-2.5 % relative. **tight.** |

**The real tolerance problem is the opposite of looseness: over-tight tolerances on circular
assertions.** `rel=1e-6` on C6 (`shannon_max_charge_formula`), `rel=1e-6` on C7
(`max_polarisation_V`), `rel=1e-6` on C15 (Butterwick anchors), `rel=1e-12` on the Pennes
unperfused limit, `rel=1e-9` on the Shannon band width — these look like precision but are
identities, so the tolerance carries no information at all. Tight tolerance on a tautology is
still a tautology.

### Float `==` on computed values

Most `==` comparisons are against stored literals (`shannon.K_SHANNON == 1.5`,
`iso.threshold_for("brain") == 2.0`, `m.DAMAGE_RADIUS_CONTINUOUS_UM == 150.0`) — exactly
representable, no arithmetic, safe. Four compare **computed** floats with `==` and should use
`approx`:

- `tests/test_published_cases.py:595` — `az.threshold_ratio_at(row.median_us, row.median_us) == 2.0`
  (a computed ratio; survives only because `(w+c)/c` with `w == c` is exact for these inputs).
- `tests/test_models_io_viz.py:136` — `rise[0] == 0.0` on the output of a finite-difference solve.
- `tests/test_uncertainty.py:25` — `i.width == 0` on `Interval.exact(3.0)`.
- `tests/test_literature.py:531` — `unperfused.perfusion_per_s == 0.0` (stored, but read through
  a dataclass field that other code divides by).

Also `tests/test_core.py:408` — `calc.k == shannon.K_SHANNON == 1.5` chains an identity
comparison with a float literal; harmless here, brittle in principle.

---

## 7. CI — `.github/workflows/ci.yml`

**Triggers.** `push` to `[main, master]`, `pull_request` (all branches), `workflow_dispatch`.
`permissions: contents: read`, `concurrency` with `cancel-in-progress`. The header comment
correctly notes no `github.event.*` interpolation into `run:`. **This part is well done.**

**Three jobs.**

| job | what it runs | gate? |
|---|---|---|
| `test` | `pytest -q` | yes |
| `lint` | `ruff check neurostim tests examples` then `mypy neurostim` | yes |
| `literature` | `pytest tests/test_literature.py -v`, `pytest tests/test_published_cases.py -v`, `python scripts/provenance_audit.py`, `python scripts/verify_transcriptions.py` | **partly — see below** |

**Matrix.** `ubuntu-latest` × `["3.10","3.11","3.12","3.13"]`, plus one `macos-latest` × `3.12`.
`fail-fast: false`. `lint` and `literature` pin `3.12` only.

### Gap 1 — `provenance_audit.py` runs WITHOUT `--strict`, so it can never fail the build

`ci.yml` step *"Report provenance gaps"* is `python scripts/provenance_audit.py`. The script's own
docstring (lines 7-8) says: *"Without `--strict` this always exits 0: it is a status report."*
Confirmed in the source — `return 0` at line 95 and line 105; `return 1` only under
`if args.strict:` at line 101-103. **Answer to your question: no, `ci.yml` does not fail the build
on `--strict`; it does not pass `--strict` at all.** A new unsourced constant is reported in the
log and merged green.

### Gap 2 — `verify_transcriptions.py` is likewise non-gating, and additionally a no-op in CI

Same story (`--strict` absent), *and* the step's own comment concedes "Papers are not
redistributed with the repo, so this is informational in CI". The script returns at line 242/247
before doing any work when the papers directory is missing. The step is a 20-second `apt-get
install poppler-utils` followed by nothing.

### Gap 3 — 16 tests silently SKIP in the `test` job on every Python version

The `test` job never installs `poppler-utils`; only the `literature` job does, and it installs it
*after* the two pytest invocations that don't need it. `tests/test_gui.py:311` and `:463` call
`pytest.skip("pdftotext (poppler) not available")`. Measured by re-running the suite with
`pdftotext` removed from `PATH`:

```
local (pdftotext present):  522 passed
CI `test` job (no poppler): 506 passed, 16 skipped
```

The 16 are all of `TestPdfReport` (13) and `TestReportShowsSourceCaveats` (3) — every assertion
about the PDF deliverable, including the HTML-entity, truncation, bibliography-duplication and
"limitations contradict the interface model" regressions those tests were written for. **Those
regressions are unguarded in CI.** `pytest -q` prints `506 passed, 16 skipped`, which is green.

### Gap 4 — no lockfile, no pinned dependencies

`pyproject.toml` pins nothing but floors: `numpy>=1.24`, `scipy>=1.10`, `matplotlib>=3.7`,
`pandas>=2.0`, `pytest>=7.4`, `PyQt6>=6.5`, `reportlab>=4.0`, `ruff>=0.6`, `mypy>=1.11`. There is
no `requirements.txt`, no `uv.lock`, no `poetry.lock`, no `constraints.txt`. Every CI run resolves
the latest compatible release. A new `ruff` minor adds rules and reddens `lint`; a new `numpy`
changes a `float` repr or a `np.isscalar` edge and reddens `test`; neither is a change to this
repo. `actions/setup-python`'s `cache: pip` caches the wheel download, not the resolution.

### Gap 5 — the Python version gap you flagged: local 3.14.7, matrix stops at 3.13

Confirmed and real. `pyproject.toml` declares `requires-python = ">=3.10"` and classifiers up to
`Programming Language :: Python :: 3.13`. The matrix is `3.10`-`3.13`. The venv these 522 tests
actually pass in is **3.14.7**, which CI never exercises. This is not hypothetical for this
codebase: 3.14 changes annotation evaluation (PEP 649), which is exactly the mechanism that
distorted the branch-coverage denominator in §2, and `neurostim` uses `from __future__ import
annotations` plus `TYPE_CHECKING` guards throughout. Either add `"3.14"` to the matrix and the
classifier, or cap `requires-python` — running development on a version CI has never seen is a
gap in both directions.

### Gap 6 — `mypy` checks only `neurostim`, `ruff` checks `tests` too

`mypy neurostim` leaves 4046 lines of test code untyped-checked while `ruff check neurostim tests
examples` does lint them. Minor, but a type error in a test is a test that may not be asserting
what it reads as.

### Gap 7 — no coverage gate, and no coverage measurement at all

There is no `--cov` anywhere in `ci.yml`, no `pytest-cov` in the `dev` extra, no Codecov step, no
minimum-coverage threshold. The 46.7 % branch coverage in §2 is invisible to the project. Adding
`pytest-cov` to `dev` and `--cov=neurostim --cov-branch --cov-fail-under=` would make every gap in
this report a build failure instead of a report.

---

## 8. DETERMINISM

Overall the suite is unusually well behaved here. The real risks are three.

**8.1 `grep` subprocess with an implicit CWD dependency — the one genuine flake.**
`tests/test_gui.py:438-452`, `TestReferenceRegistry::test_every_key_is_reachable_from_the_package`:

```python
hits = subprocess.run(
    ["grep", "-rho", "-E", "[a-z0-9_]+", "--include=*.py", "neurostim"],
    capture_output=True, text=True,
).stdout.split()
used = set(hits)
unused = [k for k in REFERENCES if k not in used]
assert unused == []
```

Three problems. (i) The relative path `neurostim` resolves against pytest's **current working
directory**, not the repo root; run `pytest tests/test_gui.py` from anywhere else and `grep`
finds nothing, `used` is empty, and the test fails listing every reference key. (ii) `check=` is
not set, so a missing or non-GNU `grep` fails silently into the same empty-`used` state. (iii)
`-r` + `--include` + `-o` + `-h` combined is BSD-vs-GNU sensitive. It passes in CI only because
`pytest -q` is invoked from the checkout root on `ubuntu-latest`. Use
`pathlib.Path(__file__).resolve().parents[1] / "neurostim"` and `.rglob("*.py")` instead of a
subprocess.

**8.2 External binary dependence: `pdftotext`.**
`shutil.which("pdftotext")` gates 16 tests (§7 Gap 3). Not a flake — it skips cleanly — but it
means the same commit reports 522 or 506 passing depending on the machine, and the CI number is
the lower one. `subprocess.run(..., check=True)` on `pdftotext` will also raise, not skip, if
poppler is present but the PDF is malformed.

**8.3 Wall clock in `audit.py` — correctly excluded from the digest, worth keeping that way.**
`neurostim/audit.py:143` stamps `datetime.now(timezone.utc).isoformat(timespec="seconds")` into
every record. `test_core.py::TestAuditRecord::test_same_configuration_gives_the_same_digest` and
`test_digest_ignores_operator_and_note` pass, so the timestamp is outside the digest. But nothing
asserts *that* directly — no test pins "the digest must not depend on the timestamp". Two records
taken a second apart happen to agree today; a refactor that folds `timestamp_utc` into the hashed
payload would make `test_same_configuration_gives_the_same_digest` flaky at the second boundary
rather than failing outright. That is the worst kind of regression.

**Clean — checked and found no risk:**

- **Unseeded RNG:** none. The only three RNG uses are all explicitly seeded —
  `np.random.default_rng(0)`, `(1)`, `(2)` at `test_models_io_viz.py:331, 355, 362`.
- **Dict ordering:** no test depends on `dict`/`set` iteration order producing a particular
  sequence. `test_core.py:263` compares a `set` of check names to a `set` literal (order-free).
  `test_published_cases.py:697` asserts `opinionated == ["SS316LVM"]` from a list comprehension
  over `list_materials()`, which is a tuple/list with defined order — this one *would* break if
  the material registry became a `set`, but it is deterministic today.
- **Matplotlib backend:** handled. `tests/test_models_io_viz.py:17` calls `matplotlib.use("Agg")`
  at import time, and `ci.yml` sets `MPLBACKEND: Agg`. No test asserts on rendered pixels; the
  figure tests assert on axis scales, panel counts and file existence/size.
- **Qt platform:** handled. `tests/test_gui.py:21` sets `QT_QPA_PLATFORM=offscreen` via
  `os.environ.setdefault` before importing PyQt6, and CI sets it too. The `qapp` fixture is
  module-scoped with `QApplication.instance() or QApplication([])`, which is the correct pattern.
- **Temp paths:** all file I/O uses the `tmp_path` fixture. No hardcoded `/tmp`, no writes into
  the repo. `test_cancelled_dialog_writes_nothing` asserts `list(tmp_path.iterdir()) == []`,
  which is sound because `tmp_path` is per-test.
- **Locale:** no `strftime`/`%f`/`locale`-dependent parsing. `test_gui.py:341-359` normalises with
  `unicodedata.normalize("NFKC", ...)` before comparing glyphs, which is the *correct* handling of
  the U+2126 vs U+03A9 substitution rather than a workaround — the docstring says so and is right.
- **Test ordering / shared state:** the `window` fixture is function-scoped and closes the window;
  no module-level mutable state is written by tests. `-p no:cacheprovider` runs identically.

---

## 9. THE SIX KNOWN DEFECTS — which test SHOULD have caught each

All six re-confirmed empirically on the real package (read-only) before being attributed.

### 9.1 `limiting_current_uA` omits four computed limits

`assessment.py:125-131` takes `min` over Shannon, CIC and (if evaluated) compliance only. Four
further limits are computed *in the same assessment* and excluded: water window, electroporation
(Butterwick), microelectrode charge/phase (4 nC/ph), chronic dissolution.

Measured, `DiscElectrode(100.0,"Pt")` + `StimProtocol(40,200,50,1)`:

```
reported limiting_current_uA = 39.27 uA   (mechanism: "Pt charge-injection limit")
  [         FAIL] Microelectrode charge/phase   -> ceiling  20.00 uA
  [         FAIL] Chronic degradation           -> ceiling  19.63 uA
  [         PASS] Water window                  -> ceiling  58.90 uA
  [         PASS] Current density               -> ceiling  86.43 uA
```

The package prints two FAILs and still reports a limit **2.0× above** the tightest one.

> **SHOULD have caught it:** `tests/test_core.py::TestAssessment::test_limiting_mechanism_matches_limiting_current`
> (tautology **C5**). It asserts `limiting_current_uA == min(shannon, charge, compliance)` — the
> code's own expression, over the code's own three candidates. It is structurally incapable of
> noticing a missing candidate.
> **Secondary:** `tests/test_uncertainty.py::TestPropagationIntoAssessment::test_platinum_range_reaches_the_final_limit`
> (**C14**) pins 141.4-212.1 µA, an interval built from the same three mechanisms.
> **Tertiary:** `tests/test_core.py::TestElectrodePresets::test_preset_drives_an_assessment` asserts
> only `limiting_current_uA > 0`.

### 9.2 Monophasic protocols receive biphasic limits

`charge_mod.evaluate` and `shannon_mod.evaluate` never read `protocol.waveform`. Measured:

```
biphasic   DiscElectrode(500,'Pt') 10uA/200us: shannon 1245.91  cic 981.748  limiting 981.748
monophasic same:                               shannon 1245.91  cic 981.748  limiting 981.748  (identical)
```

Every published CIC in the database was measured under charge-balanced biphasic pulsing, and
`_charge_balance_check`'s own detail text says "No charge-density limit in this package is
validated for monophasic delivery" — while the limits are handed over unchanged.

> **SHOULD have caught it:** `tests/test_core.py::TestAssessment::test_monophasic_fails_charge_balance`
> (line 303). It is the one monophasic test and it inspects exactly one check. It never looks at
> `assessment.limiting_current_uA`, `assessment.charge.cic_limit_uC_cm2`, or
> `assessment.shannon.max_current_uA` — the values the monophasic waveform invalidates.
> **Secondary:** `tests/test_core.py::TestProtocol::test_monophasic_is_not_charge_balanced` stops at
> the protocol object and never reaches an assessment.

### 9.3 Unbalanced biphasic pulses are structurally inexpressible; the FAIL branch is dead

`protocol.py:114/121` define `return_phase_width_us = W·r` and `return_phase_current_uA = I/r`, so
`return_charge_uC ≡ charge_per_phase_uC` for every `r`. `net_charge_per_pulse_uC` is exactly `0.0`
for `r ∈ {0.25, 0.5, 1, 2, 4, 10}` (measured). `assessment.py:567` `if not
protocol.is_charge_balanced:` is one-sided in coverage and lines **568-576 never execute**.

> **SHOULD have caught it:** `tests/test_core.py::TestProtocol::test_asymmetric_return_phase_stays_balanced`.
> It asserts `p.is_charge_balanced` for `return_phase_ratio=4.0` — which certifies the
> inexpressibility instead of exposing it. A test suite that could express an unbalanced pulse
> would have a failing case for the charge-balance check's second arm; this one cannot.
> **Secondary:** `test_core.py::TestProtocol::test_invalid_protocols_rejected` parametrises
> `return_phase_ratio: 0` but never a ratio that ought to unbalance the pulse.

### 9.4 Return-phase current ignored when `return_phase_ratio != 1`

Every downstream check reads `protocol.current_uA` (the leading phase) only. With `r < 1` the
return phase carries **higher** current over a shorter window — `r=0.25` gives a 400 µA return
against a 100 µA lead — and the current-density check, the compliance budget and the water-window
excursion all still see 100 µA. Measured:

```
ratio=1     return  100 uA; reported J = 0.3183 A/cm^2
ratio=0.25  return  400 uA; reported J = 0.3183 A/cm^2   (unchanged)
```

Coverage corroborates: `protocol.py:231` (`if return_phase_ratio != 1.0 and waveform ==
"biphasic"`) is **never taken at all** — the asymmetric return phase is never even rendered.

> **SHOULD have caught it:** `tests/test_core.py::TestProtocol::test_asymmetric_return_phase_stays_balanced`
> — the only test that sets `return_phase_ratio`, and it uses `4.0`, the direction in which the
> return current *falls*. No test anywhere uses `return_phase_ratio < 1.0`.
> **Secondary:** `tests/test_core.py::TestProtocol::test_rms_current_of_symmetric_biphasic` tests
> `rms_current_uA` only at `r=1`, where the asymmetry term vanishes.

### 9.5 Compliance models one interface, not two

`compliance.py:179` `total_r = access_r + lead_resistance_ohm` and `:205` `required_V = ohmic +
polar`. A real bipolar circuit crosses **two** electrode-tissue interfaces: two access
resistances and two polarisation terms. Measured for `DiscElectrode(200,"Pt")` at 100 µA:
`access_R 7142.9 Ω, total_R 7142.9 Ω, required 0.9689 V` = `ohmic 0.7143 + polar 0.2546` **exactly**.

> **SHOULD have caught it:** `tests/test_published_cases.py::TestComplianceConsistency::test_required_voltage_is_ohmic_plus_polarisation`
> (tautology **C4**). It asserts the code's own two-term sum. A test that instead reproduced a
> *published* compliance-voltage measurement — a stated stimulator output for a stated electrode
> pair — would have revealed the missing counter-electrode terms immediately. The suite has
> exactly this pattern elsewhere and it works (`TestKuncelGrill2004::test_current_density_predicted_from_geometry_and_voltage`);
> it just was not applied here.
> **Secondary:** `tests/test_gui.py::TestLiveRecompute::test_disabling_compliance_removes_that_constraint`
> asserts only `unconstrained >= constrained`, which holds under any number of interfaces.

### 9.6 The McCreery envelope rejects its own fit protocol

`envelope.py:251-260` defines the duty-cycle excursion with `value = duty_cycle × 100` against
`reference = 100.0`. The McCreery experiment behind the Shannon fit was 400 µs biphasic at 50 Hz —
a **4 %** duty cycle, not 100 %. So the fit protocol itself sits 25× from its own reference:

```
EXACT FIT PROTOCOL StimProtocol(50, 400, 50, 7*3600), area 0.1 cm2:
  inside = False
  outside = [('duty cycle', 25.0, 'conservative')]
  duty cycle = 4.0 % vs reference 100 %
```

Because `EnvelopeResult.inside` requires `not self.outside`, and being "inside" on duty cycle
requires ≥ 50 % duty, which in turn requires ≥ 312 Hz at the longest in-tolerance pulse width —
which is itself 6× outside the frequency tolerance — **`inside` is unreachable for every
protocol.** Proven by exhaustive sweep: pulse width 20-2000 µs × frequency 1-3000 Hz (300,000
protocols) at 7 h and 0.1 cm², `inside` is `True` zero times. `assessment.py:352-356` is
provably dead code.

> **SHOULD have caught it:** `tests/test_core.py::TestValidatedEnvelope::test_matched_protocol_supports_an_unqualified_pass`.
> It uses the exact fit protocol `StimProtocol(50, 400, 50, 7*3600)` — and then asserts only
> `supports_unqualified_pass` and `duty.direction == "conservative"`, never `result.inside`. The
> docstring even narrates the bug as if it were intended: *"Duty cycle is necessarily far below
> McCreery's continuous stimulation for any realistic pulse train."* It is not "far below
> McCreery's" — it **is** McCreery's; the 100 % reference is the error.
> **Secondary:** `tests/test_core.py::TestValidatedEnvelope::test_matched_protocol_gives_a_clean_shannon_pass`
> asserts `checks["Validated envelope"].status is Status.PASS`, which passes via the *second*
> PASS branch (`assessment.py:360-368`, "all in the safer direction") and so never reveals that
> the first one is unreachable.

---

## 9b. SEVEN FURTHER CONFIRMED DEFECTS — which test SHOULD have caught each

Each independently reproduced on the real package (read-only) before being attributed. Where my
measured figure differs from the one reported to me, I give **my own measurement** and say so.

### 9b.1 `limiting_mechanism` names a check that did not run

`assessment.py:161-167` builds its `options` dict unconditionally from `shannon.max_current_uA`,
regardless of whether `_shannon_check` returned `NOT_EVALUATED`. Measured,
`DiscElectrode(80.0,"SIROF")` + `StimProtocol(50,200,50,1)`:

```
area 5.03e-05 cm2   limiting_current_uA = 199.3 uA
mechanism reported  = "Shannon tissue-damage criterion"
Shannon CHECK status = NOT_EVALUATED       <-- the criterion the package just declined to apply
```

This is the same root cause as §9.1 (the `min` is taken over the wrong candidate set) seen from
the label side: the package attributes its headline number to a criterion it has explicitly
refused to evaluate, on exactly the microelectrodes where Cogan 2016 says Shannon does not hold.

> **SHOULD have caught it:** `tests/test_core.py::TestAssessment::test_limiting_mechanism_matches_limiting_current` (**C5**).
> It asserts the mechanism's *value* agrees with the `min` — never that the named mechanism's
> **check** actually ran. One extra line would have caught it:
> `assert checks[mechanism_name].status is not Status.NOT_EVALUATED`.
> **Secondary:** `tests/test_core.py::TestAssessment::test_shannon_defers_to_the_microelectrode_criterion_below_the_boundary`
> asserts `Shannon criterion` is `NOT_EVALUATED` on a microelectrode — and then never looks at
> `limiting_mechanism`, which on that same object still says "Shannon".

### 9b.2 The back-solved `max_current_uA` fails the package's own forward check

`charge.py:256` computes `max_current_uA = (limit * area) / (pw * 1e-6)`; feeding that current
back in gives a charge density that floating-point rounding puts *above* the limit, and
`ChargeResult.passes` (`<=`) then reports failure. Measured over 54 material × policy × polarity
combinations:

```
re-assessing at the reported max_current_uA FAILS its own check in 17 of 54 cases
example Pt/conservative: limit = 100.0   applied-at-limit = 100.00000000000001   passes = False
```

(My sweep covered 9 materials × 3 policies × 2 polarities = 54; the 60-case sweep reported to me
found 54 failures. Either way the defect is the same and the majority of cases are affected —
the exact count depends on which combinations are enumerated.)

This is §4.2's round-trip invariant failing in the most basic possible way, and it makes mutant
**C2** (`<=` → `<`) doubly invisible: the comparison is already wrong at the boundary.

> **SHOULD have caught it:** nothing in the suite. There is no round-trip test anywhere.
> The nearest miss is `tests/test_core.py::TestShannon::test_max_charge_round_trip` (**C11**),
> which round-trips `shannon_max_charge_uC` ↔ `shannon_k` — proving the authors knew the pattern
> and applied it to the one place it was least needed, never to the charge-injection limit that
> feeds `limiting_current_uA`.

### 9b.3 `_geometry_factor` uses 4π for half-space sources — an exact 2× error

`models/field.py:73` returns `2π` for `HemisphericalElectrode` and `4π` for everything else.
Measured:

```
DiscElectrode           4.0 pi      <-- planar, sits ON a half-space boundary; should be 2 pi
RingElectrode           4.0 pi      <-- same
RectangularElectrode    4.0 pi      <-- same
SphericalElectrode      4.0 pi      correct (full space)
HemisphericalElectrode  2.0 pi      correct (half space)
```

A disc electrode on the cortical surface or a planar site on a shank injects into a half-space,
not a full space, so `potential_V`, `field_V_per_m` and `current_density_A_per_m2` are all
**exactly 2× low** for the three planar geometries. Note the package gets this right in
`electrodes.py` — `DiscElectrode.access_resistance_ohm` uses Newman's `1/(4κa)`, the *half-space*
disc result — so the two modules disagree with each other about the same electrode.

> **SHOULD have caught it:** `tests/test_published_cases.py::TestNewman1966::test_sphere_potential_equals_current_times_access_resistance`
> and `tests/test_models_io_viz.py::TestField::test_sphere_surface_potential_equals_current_times_access_resistance`.
> Both cross-check `field.potential_V` against `electrode.access_resistance_ohm` — the exact
> consistency check that would expose this — **but only for `SphericalElectrode`**, the one
> geometry where `4π` is right. Running the identical assertion for `DiscElectrode(200.0)` fails
> by exactly 2. (Mutant **M3**, which swaps the two factors, was killed by these tests *because*
> they cover the sphere; a mutation making disc and sphere agree would survive.)
> **Secondary:** `test_models_io_viz.py::TestField::test_hemisphere_doubles_the_potential` asserts
> the 2× ratio between hemisphere and default — it locks the wrong default in place.

### 9b.4 `examples/worked_example.py` feeds a disc's equal-area radius into a sphere solution

`thermal.peak_temperature_rise_K` is the Pennes sphere result `P/(4πκa)`. The worked example
passes it the equal-area radius of a **disc**, which is a different geometry with a different
shape factor, so the reported rise is low by the sphere/disc factor. Reported to me as
**5.396 mK printed vs 24.06 mK geometry-consistent** (a 4.5× understatement). I did not re-derive
the geometry-consistent value here, so I report it as received rather than as my own measurement;
the structural error — sphere formula, disc radius, no correction — is visible in the source.

> **SHOULD have caught it:** nothing — `examples/worked_example.py` has **no test at all**. It is
> linted (`ruff check neurostim tests examples`) and never executed. `pyproject.toml`'s
> `testpaths = ["tests"]` excludes it, and `ci.yml` never runs it. A four-line smoke test that
> imports and runs the example, asserting its printed thermal rise against
> `thermal.peak_temperature_rise_K` computed for the same geometry, would have caught it.
> **Related:** `tests/test_models_io_viz.py::TestThermal` tests `peak_temperature_rise_K` only
> with `radius_um` treated as a genuine sphere radius, so the misuse is invisible from inside.

### 9b.5 An unverified user CIC silently loosens the water-window check

`with_measured_cic` correctly sets `cic.verified = False` and stamps `PROVISIONAL` into
`cic.describe()`. But `water_window.effective_capacitance_uF_cm2` derives `C_eff = cic/available_V`
from that same unverified number, so raising the user's CIC *raises* the modelled capacitance and
*lowers* the predicted excursion. Measured, `DiscElectrode(500,"Pt")` at 50 µA / 200 µs:

```
stored Pt (cic 100, verified)      : peak potential -0.020 V   Water window = PASS
user cic 600 (verified = False)    : peak potential -0.005 V   Water window = PASS
water-window check detail contains "PROVISIONAL": False
```

The excursion shrinks fourfold on the strength of an unverified user number, and the water-window
check reports a clean PASS with no provisional marker anywhere in its status, summary or detail.
The charge-injection check *does* degrade to CAUTION via `_charge_check`'s `not result.verified`
(`assessment.py:302`) — the water-window check has no equivalent.

> **SHOULD have caught it:** `tests/test_literature.py::TestProvenanceIsAlwaysPresent::test_user_measurement_is_never_attributed_to_a_paper`.
> It checks the *provenance string* thoroughly (reference key, "not published literature",
> "PROVISIONAL" in `describe()`) and never builds a `SafetyCalculator` with the measured material,
> so it never observes that the unverified number silently propagates into a second, unflagged
> check. Coverage corroborates: `charge.py:162` (`if not self.verified`) is one-sided — **no
> unverified material is ever rendered in an assessment.**

### 9b.6 `NOT_EVALUATED` outranks `PASS`, so overall `PASS` is unreachable for any macroelectrode

`assessment.py:57-62`:

```
ranks: PASS 0, NOT_EVALUATED 1, CAUTION 2, FAIL 3
```

`SafetyAssessment.status` is `_worst(...)` = `max(rank)`, so a single `NOT_EVALUATED` check floors
the overall verdict at `NOT_EVALUATED`. For a macroelectrode, `_regime_check` (`assessment.py:495-501`)
*always* returns `NOT_EVALUATED` ("area … is a macroelectrode; the Shannon criterion applies").
Measured on a deliberately benign macro case, `DiscElectrode(2000,"SIROF")` + `StimProtocol(20,400,50,3600)`:

```
overall = NOT_EVALUATED
NOT_EVALUATED checks: Microelectrode charge/phase, Chronic degradation, Compliance voltage
```

Every check that ran returned PASS. **No macroelectrode can ever report an overall PASS**, because
the microelectrode check structurally cannot apply to one. The docstring at `assessment.py:56`
says "NOT_EVALUATED sits below CAUTION" — true, but it also sits *above* PASS, which is the part
that makes the overall verdict unreachable.

> **SHOULD have caught it:** `tests/test_core.py::TestAssessment::test_overall_status_is_worst_check`.
> It asserts `assessment.status.rank == max(c.status.rank for c in checks)` — recomputing
> `_worst`'s own expression (a category-(c) tautology), so it validates the aggregation
> *mechanism* while saying nothing about whether the *ordering* is right. `Status.rank` itself is
> never asserted. And `tests/test_core.py::TestValidatedEnvelope::test_matched_protocol_gives_a_clean_shannon_pass`
> is the closest anything comes to a clean-PASS scenario — it inspects two individual checks and
> never looks at `assessment.status`.

### 9b.7 `fit_weiss` returns a negative chronaxie with `rss ≈ 0` and no error

`strength_duration.py:174-178` explicitly guards `slope <= 0` ("fitted rheobase is non-positive")
but applies no guard to the intercept, and line 191 converts the result with
`tau_from_chronaxie_us(chronaxie) if chronaxie > 0 else math.nan` — so the author knew the
intercept could be non-positive and chose to emit NaN rather than raise. Measured, feeding data
generated from an unphysical `t_c = −60 µs` Weiss curve (all widths and thresholds strictly positive,
so the existing validation passes):

```
rheobase 20 uA   chronaxie -60 us   tau_m nan us   rss 5.404e-22
```

A perfect fit (`rss ~ 1e-22`) to a physically impossible curve, returned as a `StrengthDurationFit`
and printed by `describe()` as `chronaxie  -60 us`. Every downstream consumer —
`az.plausible_cortical_chronaxie`, `vta`, the strength-duration figure — receives a negative
chronaxie with no signal that anything is wrong.

> **SHOULD have caught it:** `tests/test_models_io_viz.py::TestStrengthDuration::test_fit_needs_two_points`
> is the **only** negative test for `fit_weiss`, and it covers the trivial arity guard. The
> validation tests that exist (`test_weiss_fit_recovers_its_own_parameters`,
> `test_published_cases.py::TestAsanuma1976::test_a_weiss_fit_to_the_measured_chronaxie_round_trips`)
> are both category **C12** self-round-trips on data the forward model generated from *physical*
> parameters, so they can never reach the unphysical branch.
> **Secondary:** `tests/test_published_cases.py::TestAsanuma1976::test_implausible_chronaxie_is_flagged`
> asserts `not az.plausible_cortical_chronaxie(3000.0)` and `(10.0)` — it tests the *plausibility
> predicate* on hand-written numbers, never on a fit result, so the two halves of the guard are
> never connected.

---

## 10. TESTS TO ADD — ranked, each as a concrete assertion with what pins it

Ranked by (defect severity × how cheaply the test closes it). Every "pin against" is either a
published number, a hand derivation, or a physical invariant — never the code's own output.

### Tier 1 — closes a confirmed defect that ships a wrong number

**T1. The limiting current must be the minimum over *every* check that produces one.**
```python
# pins: the definition of "binding constraint" in assessment.py:120-124 docstring
a = SafetyCalculator(DiscElectrode(100.0, "Pt"), StimProtocol(40, 200, 50, 1)).assess()
implied = {c.name: c.margin * a.protocol.current_uA for c in a.checks if math.isfinite(c.margin)}
assert a.limiting_current_uA == pytest.approx(min(implied.values()))
assert a.limiting_current_uA <= 20.0   # 4 nC/phase over 200 us = 20 uA (Cogan 2016 / McCreery 2010)
```
Closes §9.1. Measured today: reports 39.27 µA against a 20.0 µA microelectrode ceiling. Pin the
20 µA against McCreery 2010's 4 nC/phase, which the package already stores as
`cogan2016.MICROELECTRODE_DAMAGE_THRESHOLD_NC_PER_PHASE`. Replaces tautology **C5**.

**T2. The reported limiting current must itself assess clean.**
```python
# invariant: setting I to the reported limit must sit exactly ON the boundary, not past it
a = SafetyCalculator(e, p).assess()
at_limit = SafetyCalculator(e, replace(p, current_uA=a.limiting_current_uA)).assess()
assert not at_limit.failed                       # no check may FAIL at the reported limit
assert min(c.margin for c in at_limit.checks) == pytest.approx(1.0, rel=1e-9)
```
Closes §4.2 **and** §9b.2 in one assertion. Parametrise over the 9 materials × 3 policies × 2
polarities; today 17 of 54 combinations fail their own forward check
(`100.00000000000001 > 100.0`). The fix is `math.nextafter` or a relative tolerance in
`ChargeResult.passes`, not a looser test.

**T3. `limiting_mechanism` must name a check that actually ran.**
```python
a = SafetyCalculator(DiscElectrode(80.0, "SIROF"), StimProtocol(50, 200, 50, 1)).assess()
by_name = {c.name: c for c in a.checks}
assert "Shannon" not in a.limiting_mechanism or \
       by_name["Shannon criterion"].status is not Status.NOT_EVALUATED
```
Closes §9b.1. Today the mechanism reads "Shannon tissue-damage criterion" on an electrode where
the Shannon check is `NOT_EVALUATED` — pinned against Cogan 2016's macro/micro boundary, which
the package already encodes.

**T4. A monophasic protocol must not receive biphasic-derived limits.**
```python
# pins: charge.py module docstring + _charge_balance_check detail, "No charge-density limit in
# this package is validated for monophasic delivery" (Merrill 2005)
bi  = SafetyCalculator(DiscElectrode(500., "Pt"), StimProtocol(10, 200, 50, 1)).assess()
mono= SafetyCalculator(DiscElectrode(500., "Pt"),
                       StimProtocol(10, 200, 50, 1, waveform="monophasic")).assess()
assert mono.limiting_current_uA < bi.limiting_current_uA
```
Closes §9.2. Measured today: **identical** (981.748 µA both). Whether the right behaviour is a
derating or `NOT_EVALUATED` is a design call — but "silently identical" is not defensible when
every stored CIC was measured biphasic.

**T5. Planar electrodes must inject into a half-space.**
```python
# pins: Newman (1966) half-space disc result, which electrodes.py already uses
for el in (DiscElectrode(200.), RingElectrode(330., 270.), RectangularElectrode(200., 500.)):
    assert field_mod.potential_V(100.0, el.equivalent_radius_um, 0.35, electrode=el) == \
           pytest.approx(100e-6 * el.access_resistance_ohm(0.35), rel=0.05)
```
Closes §9b.3 — exactly the assertion `test_published_cases.py::TestNewman1966::test_sphere_potential_equals_current_times_access_resistance`
already makes, extended past the one geometry where the bug hides. Today fails by exactly 2×.
Also kills mutant **M1**.

**T6. `fit_weiss` must reject an unphysical fit instead of returning NaN tau.**
```python
widths = np.array([100., 200., 400., 800., 1600.])
thresholds = 20.0 * (1.0 + (-60.0) / widths)      # all > 0, generated from t_c = -60 us
with pytest.raises(ValueError, match="chronaxie"):
    sd.fit_weiss(widths, thresholds)
```
Closes §9b.7. Today returns `chronaxie_us = -60.0`, `membrane_tau_us = nan`, `rss = 5.4e-22`,
silently. Pin against Asanuma 1976's measured cortical range, which the package already stores
as `az.plausible_cortical_chronaxie`.

**T7. An unverified CIC must mark every check it touches as provisional.**
```python
measured = with_measured_cic(get_material("Pt"), 600.0, pulse_width_us=200)
a = SafetyCalculator(DiscElectrode(500., "Pt"), StimProtocol(50, 200, 50, 1),
                     material=measured).assess()
for name in ("Charge injection limit", "Water window", "Compliance voltage"):
    check = next(c for c in a.checks if c.name == name)
    assert check.status is not Status.PASS or "PROVISIONAL" in check.detail
```
Closes §9b.5. Today the water-window check returns a clean `PASS` with the excursion reduced
fourfold (−0.020 V → −0.005 V) on an unverified number, with no provisional marker.

### Tier 2 — closes a whole class of untested logic

**T8. A failing case for each of the six unpinned checks.** Six tests, one per check, on the
template of the one that is already done right
(`test_literature.py::TestButterwick2007::test_exceeding_the_threshold_fails`). All six FAIL
states are reachable — verified:
```
Shannon FAIL     CylindricalBandElectrode(1270,1500,"SIROF"), StimProtocol(20000,400,50,1)
Charge-inj FAIL  DiscElectrode(500,"Pt"),  StimProtocol(3000,200,50,1)
Water-win FAIL   DiscElectrode(500,"Pt"),  StimProtocol(300,200,50,1), resting_potential_V=-0.55
Compliance FAIL  DiscElectrode(50,"Pt"),   StimProtocol(50,200,50,1), compliance_V=1.0
Chronic FAIL     DiscElectrode(500,"Pt"),  StimProtocol(3000,200,50,1)
Charge-bal FAIL  (biphasic arm) — blocked until T12 makes imbalance expressible
```
Pin each threshold against its stored source: Shannon `k=1.5` (Shannon 1992); Pt CIC 50-150 µC/cm²
(Rose & Robblee 1990); Pt window −0.6/+0.8 V (Cogan 2008); Pt dissolution 20-50 µC/cm²
(Rose & Robblee 1990). Closes §3 and kills mutants **S3, C2, P3, A5**.

**T9. Boundary tests, one each side, for every limit.**
```python
# exactly at the Shannon line must PASS; one ulp above must FAIL
q = shannon.shannon_max_charge_uC(area, k=1.5)
assert shannon.evaluate(q,            area, 200.0, k=1.5).passes
assert not shannon.evaluate(math.nextafter(q, math.inf) * 1.0001, area, 200.0, k=1.5).passes
```
The mutation survivors **S3, C2, P3, A5** are all `<=` → `<` on a boundary nothing approaches.
Repeat for `ChargeResult.passes`, `ComplianceResult.passes`, `_chronic_check`.

**T10. `neurostim/units.py` needs a test file at all.**
```python
# round-trip: pins charge_uC/current_uA_from_charge against each other AND against the SI chain
assert units.current_uA_from_charge(units.charge_uC(80.0, 200.0), 200.0) == pytest.approx(80.0)
assert units.charge_uC(1.0, 1.0) == pytest.approx(1e-6)     # 1 uA x 1 us = 1e-12 C = 1e-6 uC
# table self-consistency, pinned against SI, not against each other's code path
assert units.to_cm2(1.0, "mm2") == pytest.approx(1e-2)
assert units.to_uC_cm2(1.0, "uC/mm2") == pytest.approx(100.0)   # 1 mm^2 = 0.01 cm^2
assert units.to_uC(1.0, "mC") == pytest.approx(1e3)
with pytest.raises(ValueError, match="Unknown charge unit"):
    units.to_uC(1.0, "kC")
```
Closes §4.3. The module has **0 of 2 real branches** covered and no importing test. Kills **C4**,
and the dimensional variants kill **M5** and **M10**.

**T11. Dimensional-consistency invariants across the assessment.**
```python
a = SafetyCalculator(e, p).assess()
assert a.charge.charge_density_uC_cm2 * e.area_cm2 == pytest.approx(a.charge.charge_per_phase_uC)
assert a.charge.max_current_uA * p.pulse_width_us * 1e-6 == pytest.approx(a.charge.max_charge_uC)
assert jd.average_current_density_A_per_cm2(I, A) * A * 1e6 == pytest.approx(I)
assert vta.CurrentDistanceModel().activated_volume_mm3(I) == pytest.approx(
    (4.0/3.0) * math.pi * (vta.CurrentDistanceModel().activation_radius_um(I) * 1e-3)**3)
```
Closes §4.5. The last line kills **M4** and **M5** — the two surviving VTA mutants that the
existing ratio-only test cannot see. Pin the `4/3 π r³` against the sphere volume formula, not
against `vta.py`.

**T12. Make charge imbalance expressible, then pin its FAIL.**
`return_phase_ratio` currently scales width and current inversely, so `net_charge ≡ 0` for every
ratio (measured over r ∈ {0.25, 0.5, 1, 2, 4, 10}). Add an independent
`return_phase_amplitude_ratio` (or accept an explicit return current), then:
```python
p = StimProtocol(80, 200, 130, 1, return_phase_ratio=1.0, return_phase_amplitude_ratio=0.9)
assert p.net_charge_per_pulse_uC == pytest.approx(0.1 * p.charge_per_phase_uC)
assert not p.is_charge_balanced
assert next(c for c in SafetyCalculator(e, p).assess().checks
            if c.name == "Charge balance").status is Status.FAIL
```
Closes §9.3 and revives the dead branch at `assessment.py:568-576`. Pin the 10 % residual against
Merrill 2005's treatment of unrecovered charge as a DC offset.

**T13. The return phase must be assessed, not just the leading phase.**
```python
sym  = StimProtocol(100, 200, 50, 1, return_phase_ratio=1.0)
asym = StimProtocol(100, 200, 50, 1, return_phase_ratio=0.25)   # return carries 400 uA
j_sym  = next(c for c in SafetyCalculator(e, sym ).assess().checks if c.name == "Current density")
j_asym = next(c for c in SafetyCalculator(e, asym).assess().checks if c.name == "Current density")
assert j_asym.margin < j_sym.margin
```
Closes §9.4. Today both report `0.3183 A/cm²` — identical. Pin the 4× against the protocol's own
`return_phase_current_uA`, which the package already computes and never uses.

**T14. Fix the envelope's duty-cycle reference, then pin `inside`.**
```python
# McCreery 1990 was 400 us biphasic at 50 Hz = 4 % duty, NOT 100 %
assert envelope.DUTY_CYCLE_REFERENCE == pytest.approx(
    2 * 400e-6 * 50)                                   # = 0.04, from the fit conditions
fit = StimProtocol(50, 400, 50, 7 * 3600)
assert envelope.evaluate(fit, area_cm2=0.1).inside
```
Closes §9.6. `EnvelopeResult.inside` is proven unreachable over a 300,000-protocol sweep
(pulse width 20-2000 µs × frequency 1-3000 Hz), making `assessment.py:352-356` dead code. Pin the
4 % against `shannon.FIT_PULSE_WIDTH_US` and `FIT_FREQUENCY_HZ`, which the package already stores.

### Tier 3 — hardening

**T15. Monotonicity: more current is never safer.**
```python
prev = None
for I in (1, 10, 100, 1000, 10000):
    a = SafetyCalculator(e, StimProtocol(I, 200, 50, 1), compliance_V=10.0).assess()
    if prev is not None:
        assert a.status.rank >= prev.status.rank
        for c, pc in zip(a.checks, prev.checks, strict=True):
            assert c.margin <= pc.margin + 1e-12
    prev = a
```
Closes §4.1. The existing `test_gui.py::TestLiveRecompute::test_raising_current_lowers_the_headroom`
asserts only that a *string* changed.

**T16. Interval containment, across policies and k — the weak invariant, always true.**
```python
for policy in ("conservative", "nominal", "optimistic"):
    for k in (1.5, 1.7, 2.0):
        a = SafetyCalculator(e, p, k=k, policy=policy, compliance_V=10.0).assess()
        assert a.limiting_current_interval_uA.contains(a.limiting_current_uA)
```
Closes §4.4. Replaces `test_point_estimate_sits_at_the_conservative_end`, which asserts the
stronger `== interval.low` and is false away from the default `k`/policy.

**T17. Pin `Status.rank` ordering directly, and decide what PASS means.**
```python
assert Status.PASS.rank < Status.NOT_EVALUATED.rank < Status.CAUTION.rank < Status.FAIL.rank
a = SafetyCalculator(DiscElectrode(2000., "SIROF"), StimProtocol(20, 400, 50, 3600)).assess()
assert a.status is Status.PASS          # fails today: returns NOT_EVALUATED
```
Closes §9b.6. A macroelectrode can never report overall PASS because `_regime_check` always
returns `NOT_EVALUATED` for one. Either exclude structurally-inapplicable checks from the
aggregate or rank `NOT_EVALUATED` below `PASS` — but the ordering must be asserted either way.
Also kills **A2** if extended to probe `CAUTION_MARGIN` either side of 2.0.

**T18. `lead_resistance_ohm` and `compliance_V` must actually do something.**
```python
base = SafetyCalculator(e, p, compliance_V=10.0).assess().compliance
lead = SafetyCalculator(e, p, compliance_V=10.0, lead_resistance_ohm=2000.0).assess().compliance
assert lead.required_V == pytest.approx(base.required_V + p.current_uA * 1e-6 * 2000.0)
assert lead.max_current_uA < base.max_current_uA
```
Kills **P1**. `lead_resistance_ohm` is never non-zero anywhere in the suite today.

**T19. Smoke-test `examples/worked_example.py`.**
```python
# add examples/ to testpaths, or:
def test_worked_example_runs_and_is_geometry_consistent(capsys):
    runpy.run_path("examples/worked_example.py", run_name="__main__")
    ...  # assert the printed thermal rise matches thermal.peak_temperature_rise_K
         # computed for the SAME geometry as the electrode it describes
```
Closes §9b.4. The example is linted and never executed; `pyproject.toml` `testpaths = ["tests"]`
excludes it and `ci.yml` never runs it.

**T20. Replace the `grep` subprocess in `test_every_key_is_reachable_from_the_package`.**
```python
root = pathlib.Path(__file__).resolve().parents[1] / "neurostim"
used = {w for f in root.rglob("*.py") for w in re.findall(r"[a-z0-9_]+", f.read_text())}
```
Closes §8.1 — removes the CWD dependency, the silent-empty-on-missing-grep failure mode, and the
GNU-vs-BSD flag sensitivity.

### Tier 4 — CI changes that make the above enforceable

| # | change | closes |
|---|---|---|
| **T21** | add `poppler-utils` to the `test` job (or make the 16 PDF tests fail rather than skip) | §7 Gap 3 — 16 tests silently skip on every CI Python version |
| **T22** | pass `--strict` to `scripts/provenance_audit.py` in `ci.yml` | §7 Gap 1 — the provenance gate currently always exits 0 |
| **T23** | add `pytest-cov` to the `dev` extra; run `--cov=neurostim --cov-branch --cov-fail-under=` and ratchet | §7 Gap 7 — 46.7 % branch coverage is invisible to the project |
| **T24** | add `"3.14"` to the matrix and the classifier list, or cap `requires-python` | §7 Gap 5 — development runs on 3.14.7, CI stops at 3.13 |
| **T25** | add a lockfile / constraints file and pin `ruff` and `mypy` exactly | §7 Gap 4 — every run resolves latest; a ruff minor reddens CI with no repo change |
| **T26** | `mypy neurostim tests` | §7 Gap 6 |

### Summary of what these close

| target | closed by |
|---|---|
| 6 known defects (§9) | T1, T4, T12, T13, T5†, T14 |
| 7 further defects (§9b) | T3, T2, T5, T19, T7, T17, T6 |
| 13 mutation survivors (§5) | T8+T9 (S3, C2, P3, A5), T10 (C4), T18 (P1), T17 (A2), T8 (A3, A4), T5 (M1), T11 (M4, M5), T10 (M10) |
| 15 tautologies (§1) | T1 replaces C5, T11 replaces C4/C7/C8/C9/C10, T2 replaces C11, T16 replaces C14 |
| unpinned invariants (§4) | T15 (4.1), T2 (4.2), T10 (4.3), T16 (4.4), T11 (4.5), T9 (4.6), T17 (4.7) |

† T5 closes the `_geometry_factor` defect; the compliance two-interface defect (§9.5) needs a
published compliance-voltage measurement to pin against and is the one gap this list cannot close
from inside the repo — it needs a source, on the model of
`TestKuncelGrill2004::test_current_density_predicted_from_geometry_and_voltage`.

