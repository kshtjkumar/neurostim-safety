# Phase 6 Review (physical models) — `git log f9e33a0..e2ea0ec`

Status: COMPLETE

Repo: .
HEAD: e2ea0ec. The main tree was not modified and no worktree was needed. The independent
tools are in the scratchpad and import no `neurostim` code:
* `elw_fv.py`: an axisymmetric finite-volume solve of Elwassif's bipolar configuration with
  volumetric Joule heating.
* An analytic transient comparison.
* CI coverage and interval-rounding sweeps.

## Summary

| # | Sev | Where | One line |
|---|---|---|---|
| R1 | MINOR | models/strength_duration.py `fit_lapicque` CI | The Lapicque 95 % CI under-covers on weakly informative designs. Executed (1 500 replicates each): **0.82** at 20 % noise with widths 50–200 µs, **0.85** with widths 400–3200 µs only, **0.90** at 10 % with 50–200 µs. The fit also refuses up to 29 % of replicates there, so coverage is conditional on acceptance. The result's docstring quotes the Weiss figure (94 % at 5 %, widths 50–800 µs), which holds: Weiss is 0.94–0.98 in every cell tried |
| R2 | MINOR | models/thermal.py `pennes_transient_sphere` | Early-time accuracy is limited by the spatial grid, not by `STEP_FRACTION`. Against the analytic unperfused solution `P/(4πκa)[1 − e^τ erfc √τ]` at default settings (20 cells per radius): **−67 % at τ = αt/a² = 1e-4, −20 % at 1e-3, −1.4 % at 1e-2**, and ≤ 0.15 % from τ = 0.1. For a 3389 contact τ = 1e-3 is t ≈ 3 ms. An early rise read low is non-conservative, though small in absolute terms. Refining the step alone barely helps (−19 % at 1e-3 even at STEP_FRACTION 0.0025); 80 cells per radius gives −2.3 % |
| R3 | MINOR | uncertainty.py | The module now says every rounded result is widened outward. `Interval.sqrt` and `Interval.from_mean_sd` are not: in 49 944 of 100 000 random `sqrt`s the low end sits above the true root. There are no in-package consumers, but it is public API with a documented guarantee it does not meet |
| R4 | MINOR (flag for C7.3) | CITATION.cff lines 18–20 | "Pennes bioheat modelling validated ..." and "validated envelope" wording, as the lead noted. The README now says the model is an upper estimate compared against one FEM case, which is not validation |

Counts: **0 BLOCKER, 0 MAJOR, 4 MINOR.**

---

## Verification

**(1) C6.3 thermal source radius: sound.**
* **The analogy.** Steady heat and current conduction share the Laplace operator and the
  geometry. For an electrode taken as an isothermal/equipotential source, the thermal
  resistance is `R_access · σ/κ` exactly, and the sphere solution then needs
  `a = 1/(4πσR_access)`. That makes the rise exact for a sphere and exact up to the access
  resistance's own accuracy elsewhere.
* **Direction by geometry.** Every non-exact resistance in the package is an upper bound
  or high:
  * band: +0.6 % at the clinical aspect (my Phase 3 solve);
  * ring and rectangle: the Pólya–Szegő upper bound;
  * bare flat microwire tip: the Newman upper bound, against a true 0.1731;
  * microwire with an exposed shaft: within 1.4 % (−1.3 % at 2 radii, the one mildly low
    region).
  * A larger R gives a smaller `a` and a larger rise, so the substitution is conservative
    everywhere except that 1.3 % band. Perfusion breaks the exact analogy, and the
    `1/(1 + a/L)` factor at the electro-thermal radius is an approximation, as the module
    says.
* **The lumped surface source.** It overestimates the volumetric Joule peak by 2× for an
  isolated sphere. I derived this: volumetric gives `I²/(32π²σκa²)` against surface
  `I²/(16π²σκa²)`, which the docstring states.
* **Elwassif's setup, checked in the PDF.** "the voltage between the two energized
  electrodes ... 1 and 2 ... was set to Vrms" (1.56 V). "The DBS electrode shaft was modeled
  as electrically and thermally insulated". Outer brain boundary at 37 °C. Table I peak row
  σ 0.35, κ 0.527, ωb 0 gives 37.82 °C. The package's two contacts 2.0 mm apart (1.5 mm band
  + 0.5 mm gap) match the 3389 geometry the paper gives.
* **Independent solve (`elw_fv.py`)**: the two bands on an insulated shaft at ±0.78 V,
  volumetric `σ|∇V|²` heating, adiabatic shaft, T = 0 at the box. Coarse to fine, 50 to
  100 mm box:

```
R 439.2 -> 433.6 -> 433.7 ohm   P 5.540 -> 5.612 -> 5.612 mW   peak dT 0.776 -> 0.796 -> 0.804 K
package: R 431.56 ohm, P 5.639 mW, two_sphere_peak_rise_K 0.8298 K; Elwassif FEM 0.82 K
```

  The two-sphere pin agrees with an independent volumetric solve to about 3 % (and with
  their FEM to 1.2 %), on the high side. The surface source's 2× excess is offset, in this
  configuration, by the insulated shaft and the partner contact. So the pin is physically
  supported, not a coincidence of the arithmetic.
* **Digits.** `SOURCE_RADIUS_M` = 690.108687092113 µm = `thermal.source_radius_um(dbs_3389)`.
  431.6 Ω, 5.639 mW and 0.8298 K reproduce. The worked example gives 8.061 mK at 46.26 µW.
* **Other thermal consumers.** A search finds no remaining use of the equal-area disc radius
  for heating. `examples/worked_example.py` uses `thermal.source_radius_um`, and
  `thermal.evaluate` and `plots.thermal_profile` take the radius explicitly.
  `equivalent_radius_um` survives only in the Butterwick size correction, the compliance
  guard and the field-panel start, none of which are thermal.

**(2) C6.1 CI calibration (executed).** For each case, 1 500 replicates at noise 2, 5, 10 and
20 %, over five designs (50–800 × 6, 20–3200 × 8, 50–200 × 4, n = 3, 400–3200 only):
* **Weiss** (delta method, t with n − 2 degrees of freedom): coverage **0.938–0.982**,
  well calibrated.
* **Lapicque** (curve_fit covariance): 0.92–0.99 at 2–5 % noise, falling to 0.82–0.90 on
  narrow or long-only designs at 10–20 % (R1).
* Rank-deficient designs raise (C6.2). A non-positive fitted chronaxie raises, which is the
  source of the refusal counts.

**(3) C6.4 transient.**
* Order-independence is fixed: t = 1e-3 s gives 0.0021610048338391408 alone and inside
  `logspace(-3, 3.5, 60)`, identical.
* The perfused late-time value matches `pennes_steady_state_sphere` to 2.4e-7 relative.
* STEP_FRACTION convergence is first-order where the grid resolves the penetration depth:
  at τ = 0.1 the error goes −0.39, −0.23, −0.15, −0.10, −0.08 % as the fraction halves from
  0.04 to 0.0025.
* The early-time limit is R2.
* The `ThermalResolutionWarning` for a clamped grid is present.

**(4) C6.6 conditional outward rounding: sound, and better than an unconditional pad.**
* `_outward` compares `op(Fraction(a), Fraction(b))` with the float result and pads one ulp
  outward only when they differ. For correctly rounded `+ − × ÷` the true value is within
  half an ulp, so one ulp outward always contains it. Choosing min and max by float values
  stays sound, because a different pair's true value lies within half an ulp of its float.
* Executed: **0 containment failures** in 200 000 random interval `+ − ×` operations and
  integer powers 2, 3 and 5, checked against exact rationals.
* Exact inputs stay exact (`[0.5, 1.5] × 2 = [1, 3]`). Division by an interval spanning zero
  raises.
* The gap is `sqrt` and `from_mean_sd` (R3).

**(5) Docs and §6.**
* The README thermal bullet matches the code (5.6 mW, 0.83 against 0.82 K, electro-thermal
  radius).
* The CITATION wording is R4.
* §6 digits for C6.3 reproduce.
* C6.0a: the compliance available voltage is now floored in every branch; the README
  transcript shows "10.0 V", consistent with that.

**Regression grids (executed at HEAD):**

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

# VERDICT: **GO** for Phase 7

The thermal source-radius change is physically right and conservative. Its external pin is
confirmed by an independent volumetric finite-volume solve (0.80 K against the package's
0.83 K and Elwassif's 0.82 K). The Weiss CI is calibrated, the transient is order-independent
and accurate past τ = 0.1, and the outward rounding is sound for every operation it covers.

The four MINORs:
* R1: say that the Lapicque interval under-covers on poor designs, or bootstrap it.
* R2: refine the grid with √(αt), or warn below τ = 0.01.
* R3: round `sqrt` and `from_mean_sd` outward.
* R4: C7.3's wording pass.
