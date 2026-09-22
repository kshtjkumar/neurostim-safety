# Audit: physical & numerical models — `neurostim_safety`

Read-only audit. No repo files modified. All numbers below were produced by running
`./.venv/bin/python`; scripts are in
`$SCRATCH/models/`: `n1_field_pennes.py`, `n2_lumped.py`, `n3_elwassif.py`, `n4_transient.py`,
`n4b.py`, `n5_sd_vta.py`, `n5b.py`.

---

# HEADLINE VERDICT: **SCOPE**, not BUG — but the README is right for the wrong reason, and CITATION.cff is the lie

## The one-line answer

The millikelvin-vs-0.8 K gap is **a protocol-power difference, nothing else**. Feed
Elwassif's *own* stated parameters through *this repo's own analytic solution* and it
returns **0.830 K against their FEM's 0.820 K — 1.2 % agreement.**

```
Elwassif 2006: Vrms = 1.56 V CONTINUOUS bipolar, contacts 1&2, sigma=0.35, kappa=0.527, wb=0
  R(two spheres, a=690.11 um, d=2.0 mm) = 431.6 ohm   ->  P = 5.639 mW
  rise at contact from its own half-power       0.6169 K
  + superposed heat from partner contact, 2 mm  0.2129 K
  = TOTAL                                       0.8298 K
  Elwassif 2006 Table I (3389, sigma .35, w=0)  0.8200 K      <-- 1.2 % apart
```

The repo's own clinical-DBS figure (3 mA, 60 us, 130 Hz monopolar) dissipates
**72.7 uW — 78x less power**. 0.82 K / 78 is ~10 mK. There is no missing physics.

## Therefore, on the specific hypotheses the brief asked me to rule on

| Hypothesis for the gap | Verdict | Evidence |
|---|---|---|
| Lead/electrode self-heating missing | **NOT the cause** | Tissue Joule heating alone reproduces 0.82 K to 1.2 %. Adding self-heating would *overshoot* the paper. |
| Encapsulation missing | **NOT the cause** | Same. |
| Lumped vs distributed source | **NOT the cause — and it is conservative** | `P = I^2*R_access` is *exactly* `∫sigma·E^2 dV` (ratio 1.000000000000). Lumping that power onto the surface **overestimates** peak dT by exactly **2x** (unperfused; 2.25x perfused). It cannot produce an underestimate. |
| Unit error | **No** | Field and thermal units verified end to end; analytic steady state matches an independently-written FD solve to 1.7e-7. |
| Protocol power (duty cycle + monopolar vs bipolar) | **THIS IS THE WHOLE GAP** | 78x in power, 152x in reported rise (the extra 2x is finding M-1 below). |

## Which document is lying

- **README.md:210-214** — *"That gap is **not reconciled**."* → **Stale, not false.** The gap
  *is* reconcilable, and this audit reconciles it to 1.2 %. The README understates the model.
- **CITATION.cff:27** — *"Pennes bioheat modelling **validated against a published finite
  element model**"* → **Overclaim as written.** What the repo actually tests is three
  *scalings* (linear in sigma, 1/kappa, perfusion attenuation). It never tested an absolute
  temperature against Elwassif, and its own stated reconciliation arithmetic
  (`implied_power_W`, "7.5 mW", "~325 ohm") is **wrong by 2x** (finding M-2). The claim is
  *now* defensible on the strength of this audit's Step 2, but it was not earned by any
  code in the repo.

**So: the physics core is sound and the headline gap is SCOPE. The defects that do exist are
elsewhere, are geometric, and all point the same way — the package under-reports temperature.**

---

# Findings table

| # | Sev | Location | Wrong | Correct | Reproducible case |
|---|-----|----------|-------|---------|-------------------|
| **H-1** | **HIGH** (non-conservative) | `examples/worked_example.py:125-126`; enabled by `neurostim/models/thermal.py:618` (`evaluate`) and `:347` (`pennes_steady_state_sphere`) | Feeds `dbs.equivalent_radius_um` = √(A/π) = **1380.2 µm** (equal-area **disc** radius) as the `a` of a **sphere** solution that requires 4πa²=A | Either the equal-area sphere `a=√(A/4π)=690.1 µm`, or the geometry-exact form `ΔT = P·R_access·σ/κ` | DBS 3 mA/60 µs/130 Hz: code prints **5.396 mK**; equal-area sphere **12.663 mK** (2×); exact disc **24.060 mK** (π×) |
| **H-2** | **HIGH** | `neurostim/models/strength_duration.py:153-201` (`fit_weiss`) | Returns a fit with **negative chronaxie** and `membrane_tau_us = nan`, `rss ≈ 1e-24`; no error | Reject `intercept ≤ 0` at fit time, as slope ≤ 0 already is (line 176) | `fit_weiss([100,200,400],[10,15,17.5])` → `chronaxie_us=-50.0`, `rss=1.36e-24`; `.threshold_uA(150)` only then raises `ValueError` |
| **M-1** | MED | `neurostim/data/elwassif2006.py:143` | `source_radius_m: float = 1.3803e-3` — undocumented magic number, the disc radius again; propagates "7.5 mW"/"~325 Ω" into 3 docstrings (`elwassif2006.py:25-26`, `elwassif2006.py:148`, `thermal.py:56`, `thermal.py:326`) | 5.639 mW at 431.6 Ω (two-sphere, d=2.0 mm), or 3.693 mW at 658.9 Ω (isolated spheres) | `implied_power_W()` → 7.496 mW ⇒ 324.7 Ω; both exactly 2× off, in compensating directions |
| **M-2** | MED | `neurostim/models/thermal.py:486-487` | `dt = times.max()/max(200, times.size*20)` — the time step for *early* samples is set by the *latest* requested time | Step size from local accuracy, or refine per output time | `t=1e-3 s` requested alone: **-0.1 %**. The same `t=1e-3` inside `logspace(-3, 3.5, 60)`: **-15.0 %**. The answer depends on which other times you asked for. |
| **M-3** | MED | `neurostim/models/thermal.py:472-476` + docstring `:437` | Docstring says of `domain_extent_factor` "**Increase it if you need better**" — but `max_cells=20000` clamps `dr` so the added domain is unresolved and accuracy saturates | Scale `max_cells` with the extent, or warn | Unperfused truncation deficit: 400a→0.249 %, 1000a→0.101 %, 2000a→**0.075 %**, 5000a→**0.075 %**, 20000a→**0.075 %** (ideal 0.005 %). Stops improving. |
| **M-4** | MED | `strength_duration.py:211` (`params, _ = curve_fit`), `:120-151` (`StrengthDurationFit`) | `curve_fit`'s covariance is computed then **discarded**; `fit_weiss` reports only an unnormalised `rss`. No SE, no CI, no R². | Return `pcov` diagonal / bootstrap SEs | 4000 replicates, 5 % multiplicative noise on I, true `t_c=200 µs` → recovered sd **27 µs**, 95 % CI **[153, 258]**. Caller sees none of it. |
| **M-5** | MED | `strength_duration.py:176-180` | Rank-deficient design (all pulse widths equal) yields numbers behind a bare numpy `RankWarning` | Raise on degenerate design matrix | `fit_weiss([100,100,100],[40,41,39])` → `rheobase=20, chronaxie=100`, fabricated |
| **M-6** | MED | `neurostim/models/vta.py:113` (`verified: bool = True`), `:155-165` (`describe`), `:214-249` (`VTAResult`) | Default `CurrentDistanceModel(verified=True)` ⇒ `describe()` prints **no** caution; `VTAResult` has no uncertainty field. The documented 90× `k` span never reaches any output. | Surface the span at every point of use | `k` 300–27000 µA/mm² ⇒ at 100 µA, r = **60.9–577.4 µm**, V = **9.4e-4 – 8.1e-1 mm³** (854× in volume). `evaluate(100).describe()` reports a bare `radius 278.2 um, volume 0.0902 mm^3`. |
| **M-7** | MED | `neurostim/sensitivity.py:98-172` | Docstring claims to cover "Every limit this package reports"; `analyse()` sweeps only Shannon k, CIC policy, medium, σ | Add thermal (κ, perfusion, source radius) and the VTA `k` | The 854×-in-volume VTA `k` — the widest spread in the package — is absent from the ranking |
| **M-8** | MED | `neurostim/models/vta.py:194` | `offset = max(float(intercept), 0.0)` silently clamps a negative fitted offset | Report the clamp | `fit_current_distance([100,200,300],[5,30,90])` → `offset=0.0`, no indication the raw intercept was negative |
| **L-1** | LOW | `thermal.py:474-476` | `max_cells` clamp is silent | Warn | a=10 µm requests 79006 cells, silently gets 20000 (5.06 cells/radius). Measured impact small (≤1.7e-4 rel). |
| **L-2** | LOW | `neurostim/models/field.py:139-151` | `distance_for_potential_um` skips the `sigma > 0` check its two sibling functions perform | Same guard as `potential_V` | `distance_for_potential_um(100, 1.0, -0.35)` → **-22.74 µm**, returned silently |
| **L-3** | LOW | `thermal.py:336` vs `:320` | `ohmic_power_W` accepts `R=0`; `voltage_driven_power_W` rejects it | Consistent guards | `ohmic_power_W(100, 0.0)` → 0.0; `voltage_driven_power_W(1, 0)` → `ValueError` |
| **L-4** | LOW | `elwassif2006.py:50`, `elwassif2006.py:23-24` | Restates the paper's "10 V, 185 pps, 210 µs → 1.56 V RMS" as if it checks out | Note that it does not | 10·√(185×210e-6) = **1.971 V**, not 1.56 V. 1.56 V implies 131.5 µs at 185 pps. Repo transcribes 1.56 faithfully; the paper's own arithmetic is unreproducible. |

---

# What is CORRECT (verified, not asserted)

These were derived from first principles before the code was read, then checked numerically.
Everything in this section passed.

### 1. Point source — `models/field.py`

V(r) = I/(4πσr), E = −dV/dr = I/(4πσr²), J = I/(4πr²).

- **Units end to end.** With I in µA, r in µm, σ in S/m the 1e-6 factors cancel exactly:
  `V[V] = I[µA]/(4π σ r[µm])` and `E[V/m] = 1e6·I[µA]/(4π σ r[µm]²)`.
  At I=100 µA, σ=0.2 S/m, r=100 µm: code **0.3978874 V / 3978.874 V/m**, identical to both
  a hand SI calculation and the closed-form mixed-unit expression.
- **E = −dV/dr**: central difference agrees to **6.6e-11** relative.
- **J = σE**: ratio **1.000000000000**.
- **Hemisphere factor**: exactly **2.000000** (2π vs 4π) — correct for a source confined to a half-space.
- **r→0**: `potential_V`/`field_V_per_m`/`current_density_A_per_m2` all raise `ValueError` rather than
  returning `inf`. `array_potential_V` raises on a field point coincident with a site. Correct.
- **σ≤0 / non-finite**: rejected in `potential_V` and `field_V_per_m` (but see L-2).

**"Exact for a sphere" — true, and the docstring states the condition correctly.** For a perfectly
conducting sphere of radius `a` injecting total current I into an unbounded homogeneous isotropic
medium with the return at infinity, the exterior solution of Laplace's equation with spherical
symmetry is A/r; matching total flux gives A = I/(4πσ), so V(r)=I/(4πσr) is exact **for r ≥ a**.
Conditions: single electrode, return at infinity, homogeneous isotropic σ, quasi-static. The module
docstring names the right failure modes (edge crowding on discs/bands, white-matter anisotropy,
encapsulation) and does not overclaim.

### 2. Pennes bioheat — analytic steady state is correct

ρc ∂T/∂t = k∇²T − W(T−T_a) + q_m + q_ext, W = w_b ρ_b c_b.

Substituting T' = u/r turns the spherical operator into u'' = u/L², giving u = A e^{−r/L}, so
T' = (A/r)e^{−r/L}. Imposing that all power P crosses the sphere r=a:

**ΔT(r) = P·e^{−(r−a)/L} / (4πκr(1+a/L))**,  **L = √(κ/W)**,  **ΔT(a) = P/(4πκa(1+a/L))**

- **Verified against an independently written finite-difference BVP solve** (2nd-order FD on T
  directly — a *different* discretisation from the repo's u=rT substitution):
  - grey-matter perfusion: analytic **2.525937e-01 K**, independent FD **2.525936e-01 K**, rel **1.7e-07**
  - unperfused: analytic **2.909597e-01**, FD **2.908579e-01**, rel **3.5e-04** — exactly the expected
    1/4000 truncation of the finite outer domain used in the check
  - repo's `pennes_steady_state_sphere` matches the analytic value to printed precision at both.
- **L = √(κ/(w_b ρ_b c_b))**: units [W/(m·K)]/[W/(m³·K)] = m² ✓. Grey matter: W = **50477.2411 W/m³/K**,
  L = **3.2919 mm** — code identical.
- **w_b → 0**: L → ∞, formula degenerates to P/(4πκa) = **0.2909597 K**, the classical unperfused
  point-source result. Handled explicitly (`math.isinf(L)` branches), no NaN.
- **r = a exactly**: accepted (tolerance `a*(1-1e-12)`); r < a raises. Correct.

### 3. THE LUMPED vs DISTRIBUTED QUESTION — settled

**(a) The total power is exactly right.** The true Joule source is distributed, q(r) = J²/σ =
I²/(16π²σr⁴). Integrating over the tissue:

∫_a^∞ q·4πr² dr = I²/(4πσ)·∫_a^∞ dr/r² = I²/(4πσa) = **I²·R_spread**

Numerically: `I²R_spread = 4.09255568e-03 W`, `∫σE²dV = 4.09255568e-03 W`, **ratio 1.000000000000**.
So `ohmic_power_W`'s `P = I_rms²·R_access` is not an approximation of the volumetric source — it *is*
its exact volume integral. This is the same source term Elwassif use (σ|∇V|²).

**(b) Lumping it onto the surface is CONSERVATIVE by exactly 2×.** Solving the distributed problem
with an adiabatic electrode gives ΔT(a) = I²/(32π²σκa²); the lumped problem gives P/(4πκa) =
I²/(16π²σκa²). Ratio exactly 2. Numerically (κ=0.547, a=500 µm, σ=0.35, I=3 mA):

| | numeric | analytic |
|---|---|---|
| lumped ΔT(a) | 1.190104 K | 1.190769 K |
| distributed ΔT(a) | 5.951882e-01 K | 5.953843e-01 K |
| **ratio** | **1.999542** | **2.000000** |

With grey-matter perfusion the ratio is **2.254**. **The lumped source overestimates the peak rise.
It cannot be the cause of an underestimate, and this disposes of the hypothesis the previous run was
pursuing.**

### 4. Transient solver — genuinely implicit, correct order, converges to the analytic steady state

`pennes_transient_sphere`, backward Euler on `du/dt = αu'' − βu` with u=rT, tridiagonal `solve_banded`.

I re-derived the inner boundary condition independently and it matches the code exactly:
−κ dT/dr|_a = P/(4πa²), and with T=u/r that is u'(a) = u(a)/a − a·flux/κ, eliminated through a ghost
node u_{−1} = u_1 − 2dr·u'(a), giving diag[0] = 1+2λ+βdt+2λdr/a, upper[0] = −2λ, rhs[0] += 2λ·dr·gs.
Both the uniform and the variable-step branches assemble banded storage correctly
(`ab[0,1:]=upper[:-1]`, `ab[2,:-1]=lower[1:]`, including the `ab_s[0,1]` and `ab_s[2,-2]` fixups).

**Convergence tests (run, not asserted):**

*Space — halve dr:*
| cells/radius | dr | ΔT | abs err | **err ratio** |
|---|---|---|---|---|
| 10 | 50.000 µm | 0.25259271 | 9.605e-07 | — |
| 20 | 25.000 µm | 0.25259343 | 2.401e-07 | **4.000** |
| 40 | 12.500 µm | 0.25259361 | 6.003e-08 | **4.000** |
| 80 | 6.250 µm | 0.25259365 | 1.501e-08 | **3.999** |
| 160 | 3.125 µm | 0.25259367 | 3.757e-09 | **3.996** |
| 320 | 1.562 µm | 0.25259367 | 9.354e-10 | **4.016** |

**Second-order in space, confirmed (ratio 4 per halving).**

*Time — halve dt:*
| n_steps | dt | ΔT(0.5 s) | err vs finest | **ratio** |
|---|---|---|---|---|
| 200 | 2.50e-3 s | 0.11625155 | 8.114e-05 | — |
| 400 | 1.25e-3 s | 0.11629276 | 3.993e-05 | **2.032** |
| 800 | 6.3e-4 s | 0.11631337 | 1.932e-05 | **2.067** |
| 1600 | 3.1e-4 s | 0.11632367 | 9.016e-06 | **2.143** |

**First-order in time, confirmed — exactly what backward Euler should give, and what the docstring claims.**

*Joint refinement (dr and dt halved together) against the analytic steady state:* error ratio
**4.000, 4.000, 3.999, 3.996** — space-limited, as expected once dt is small.

*Unconditional stability:* at cells/radius=20 the explicit limit is dt < dr²/(2α) = **2.205e-03 s**.
The solver runs at **dt = 5.0 s = 2267× the explicit limit** and returns **0.25259343 K**, bounded, no
oscillation, no overshoot above the steady state. **Genuinely implicit.**

*t → ∞:* ΔT(3162 s) = 0.25259343 vs analytic 0.25259367, rel **9.5e-07**. Converges to the analytic
steady state. (A −1.2e-14 K non-monotonicity appears at the last sample — pure floating-point noise,
not a defect.)

*Unperfused truncation:* the docstring predicts a (1−a/R) deficit. Measured at the default 400 radii:
**0.249 %** against a predicted **0.250 %**. Honest and accurate. (The docstring's advice to raise the
factor is what fails — M-3.)

*Extremes:* `power_W=0` → all zeros; `t=0` → 0.0; `t=1e9` → the steady state; negative power, r<a,
σ=0, r=0 all raise `ValueError`.

### 5. Strength-duration — the two forms are mutually consistent and correctly cited

- The repo uses **Lapicque** in the exponential form `I = I_rh/(1−e^{−W/τ_m})`. Checked against the
  primary text: this is **Merrill et al. (2005) eq. (4.2)**, attributed there to Lapicque (1907).
  The repo's citation is accurate.
- **Weiss self-consistency**: `Q = I_rh(W+t_c)` and `I = I_rh(1+t_c/W)` satisfy Q = I·W with
  **max relative deviation 0.00e+00**. Q is exactly linear in W (2nd difference 4e-03 on values ~1e4).
- **Chronaxie definitions agree**: Lapicque at W=t_c=τ·ln2 gives exactly **2·I_rh**. Merrill's Fig. 7
  caption confirms chronaxie = the width at twice rheobase. `chronaxie_from_tau_us`/`tau_from_chronaxie_us`
  are exact inverses.
- **The docstring's divergence table is correct.** Recomputing (1+1/x)(1−2^{−x}):
  x=0.33 → **0.824** (doc 0.83), x=1 → **1.0000** (doc 1.00), x=6.7 → **1.1382** (doc 1.14).
- The docstring's refusal to ship default rheobase/chronaxie values, on the grounds that they depend on
  electrode-to-target distance, is directly supported by Merrill ("depend upon factors such as the
  distance between the neuron population of interest and the electrode, and are determined empirically").

### 6. VTA — units correct

`r = √(I/k)`: I [µA] / k [µA/mm²] = mm² → √ = mm, converted by ×1e3 to µm. At k=1292 µA/mm²:
I=10 µA → **87.98 µm**, I=100 → **278.21 µm**, I=1000 → **879.77 µm**, all matching √(I/k)·1e3 by hand.
`activated_volume_mm3` is (4/3)πr³ with r in mm. Sub-threshold currents clamp to r=0 rather than
producing NaN. The module docstring is unusually honest about the model's weakness — the problem
(M-6) is that none of that honesty reaches the output.

### 7. Other data modules — spot-checked clean

- `gabriel1996.py`: the four-Cole-Cole parameters match the published Table 1 set for grey/white
  matter, blood and muscle. The conductivity extraction `σ = −Im(ε̂)·ωε₀` is correct for the
  `σ_i/(jωε₀)` sign convention used (the ionic term alone recovers σ_i exactly). Grey matter at a
  60 µs pulse (f_eff = 8.33 kHz) → **0.1135 S/m** vs IT'IS 0.419 → **3.69×**, supporting
  `sensitivity.py`'s "factor of four" to within rounding.
- `current_distribution.py`: pure documented constants with no computation; the Kuncel & Grill
  25.6 %-above-average figure and its "the 30 µC/cm² limit is *liberal*" framing are stated correctly.
- `perfusion_per_s` unit conversion (ml/min/kg → 1/s via tissue density) is correct and the docstring
  correctly identifies it as the most likely ~1000× transcription trap.

---

# The headline question, in full

## What Elwassif et al. (2006) actually did

Read from `$SCRATCH/txt/elwassif2006.txt` (IEEE EMBS conf. paper, pp. 3580-3583):

- Bioheat equation **identical** to the repo's: `ρCp ∂T/∂t = ∇(k∇T) − ρ_b ω_b C_b(T−T_b) + Q_m + σ|∇V|²`
- Source term **σ|∇V|²** — distributed, from a separate Laplace solve `∇·(σ∇V)=0`
- **Vrms = 1.56 V, CONTINUOUS**, applied **between contacts 1 and 2** (bipolar), stated as the RMS
  reduction of a "high" clinical setting of 10 V, 185 pps, 210 µs
- DBS shaft **electrically and thermally insulated**; outer brain boundary fixed at 37 °C; **Q_m = 0**
- Steady state only. σ = 0.15–0.35 S/m, k_t = 0.5–0.6 W/m°C, ω_b = 0–0.012 ml/s/ml
- Table I peak: **37.82 °C at σ=0.35, k_t=0.527, ω=0, lead 3389 → rise 0.82 K**

The repo's `data/elwassif2006.py` transcribes Table I, both leads, all twelve rows, **correctly** —
I checked every value against the paper text.

**The paper never reports a power or an impedance.** The repo's "7.5 mW / 325 Ω" is the repo's own
inference, and it is wrong by 2× (M-1).

## Reproducing their number through this code

The paper's setup is fully determined, so the power can be derived rather than fitted. Contact:
1270 µm × 1500 µm band, A = 5.9847e-06 m², equal-area sphere **a = 690.11 µm**. Contacts 1 and 2 of a
3389 are 1.5 mm tall with 0.5 mm spacing → centre separation **d = 2.0 mm**.

Two-sphere bipolar resistance: R = (1/2πσ)(1/a − 1/d) = **431.6 Ω** → **P = V²/R = 5.639 mW**, I = 3.615 mA.

Pushing that through **the repo's own `pennes_steady_state_sphere`**, with the power split equally
between the two energised contacts and the partner's contribution superposed:

```
rise at a contact from its own half-power (P/2 at r=a)   0.6169 K
+ superposed heat from the partner contact at d = 2 mm   0.2129 K
-------------------------------------------------------- --------
TOTAL peak rise, this code                               0.8298 K
Elwassif 2006 FEM, Table I row 4 (3389)                  0.8200 K
                                                          1.2 % apart
```

**Robustness.** The 1.2 % is partly fortuitous — the equal-power split and two-sphere R are modelling
choices. Using the isolated-sphere resistance instead (658.9 Ω, P = 3.693 mW) gives **0.543 K**. So the
defensible range is **~0.54–0.83 K**. Either way the answer is **order 1 K, not order 1 mK**, and it is
produced by tissue spreading-resistance Joule heating alone.

## Why the repo reports millikelvin

Different protocol, not different physics:

| | Elwassif 2006 | repo's DBS example |
|---|---|---|
| drive | 1.56 V **continuous**, **bipolar** | 3 mA, 60 µs, 130 Hz, **monopolar** |
| duty cycle | **1.0** | **0.0156** |
| RMS current | 3.615 mA | 374.70 µA |
| **power** | **5.639 mW** | **72.66 µW** — **78× less** |
| rise | 0.82 K | 5.40 mK (code) / 24.06 mK (geometry-corrected) |

**78× in power.** The residual between 78× (power) and 152× (reported rise) is finding H-1: the disc
radius, worth another ~2×. Correct the radius and the two ratios agree.

## Verdict: SCOPE

**The thermal core is not buggy.** The analytic solution is right, it matches an independent solve to
1.7e-7, `I²R` is the exact volume integral of the distributed source, the lumped treatment is
conservative by 2×, and the model reproduces Elwassif's own headline number to within a few percent
when given Elwassif's own power. The mK-vs-0.8 K gap is entirely explained by comparing a duty-cycled
microampere monopolar protocol against a continuous bipolar voltage drive — the `thermal.py` module
docstring's own advice, **"Compare power, not amplitude,"** is correct and is the whole answer.

**But the repo does not currently earn the claim.** It states the right conclusion with the wrong
arithmetic (M-1: 7.5 mW/325 Ω should be 5.6 mW/432 Ω), and it feeds the wrong radius into the right
formula (H-1), which is why its own DBS number is a further 2× low.

## Which document is the lie

- **`CITATION.cff:27`** — "Pennes bioheat modelling **validated against a published finite element
  model**". **This is the overclaim.** No code in the repo compares an absolute temperature against
  Elwassif. What it validates is three *scalings* — and I confirmed those hold:
  linear in σ to **0.43 %** (docstring claims 0.7 %), as 1/κ to **0.57 %** (claims 0.9 %), perfusion
  attenuation 1/(1+a/L) to **7.0–7.8 %** (claims 7–8 %). Note the perfusion figures reproduce *only*
  with the **disc** radius 1380 µm; with the geometrically correct sphere radius they are **2.7–7.7 %**,
  i.e. better. The scalings are validated; the *model* is not, on the repo's own evidence.
- **`README.md:213-214`** — "**That gap is not reconciled.**" **Stale, and now false.** The gap is
  reconciled above to 1.2 %. The README also attributes the gap to Elwassif's model including "lead and
  electrode self-heating" (`examples/worked_example.py:131` repeats this) — **that attribution is
  wrong**: the paper models the shaft as thermally insulated and its source term is σ|∇V|² in tissue
  only. Tissue Joule heating alone reproduces their number; adding self-heating would *overshoot* it.

Both documents should say the same thing: *the scalings are validated against Elwassif; the absolute
rise reproduces their 0.82 K to within a few percent at matched power; the difference in reported
numbers is duty cycle and monopolar-vs-bipolar drive, not missing physics.*

---

# Honest validity ranges (what the docs should say)

| Model | Valid | Not valid |
|---|---|---|
| Point source `V=I/4πσr` | **Exact** for a sphere, r ≥ a, unbounded homogeneous isotropic medium, return at infinity, quasi-static. Good to a few % beyond ~2–3 electrode radii for other shapes. | Within ~1 radius of a disc/band (edge crowding — real field is *higher*); bipolar with a near return; anisotropic white matter (~10× along vs across fibre); encapsulated chronic implants |
| Pennes analytic steady state | Spherical source, unbounded perfused medium, uniform properties, isothermal or uniform-flux surface. Verified to 1.7e-7. | Non-spherical electrodes **without the σ/κ duality correction**; multiple energised contacts (superpose); transients shorter than a²/α (=1.76 s at a=500 µm) |
| Pennes transient | 2nd order in space, 1st in time, unconditionally stable, converges to the analytic steady state to 9.5e-07. | Early times inside a wide log sweep (M-2, up to −15 %); unperfused domains beyond ~1000a (M-3) |
| Lumped `P = I_rms²R` | **Exact** as total power. Peak ΔT conservative by exactly 2× (2.25× perfused). | Nothing — this is the strongest part of the model |
| Weiss / Lapicque | Interpolating measured thresholds for one preparation. Mutually consistent; agree exactly at chronaxie. | Predicting thresholds for a new preparation; ≤2 points (H-2, M-4); mixing a rheobase from one form with a chronaxie from the other |
| VTA `r=√(I/k)` | Order-of-magnitude scale only. | Anything quantitative: k spans 90× (300–27000 µA/mm²) ⇒ **854× in volume**; sphere is the wrong shape; says nothing about *which* element is activated |

# The one expression worth adding

The electrical spreading problem ∇·(σ∇V)=0 and the thermal one ∇·(κ∇T)=0 are the same boundary-value
problem, so R_thermal = R_access·(σ/κ) for **any** geometry. Hence, unperfused, isothermal electrode:

> **ΔT_peak = P · R_access · σ / κ**

- sphere: R = 1/(4πσa) → ΔT = P/(4πκa) — **recovers the repo's formula exactly**, confirming it
- disc (Newman, the repo's own `access_resistance_ohm`): R = 1/(4σa) → ΔT = P/(4κa)

This closes H-1 for every geometry the package already knows the access resistance of, with no new
constants — and `thermal.evaluate` is already given `access_resistance_ohm`, so it has everything it
needs.

---

*Scripts: `$SCRATCH/models/{n1_field_pennes,n2_lumped,n3_elwassif,n4_transient,n4b,n5_sd_vta,n5b}.py`.
Interpreter: `./.venv/bin/python`. No repo file modified.*
