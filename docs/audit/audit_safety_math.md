# Read-only audit: physics / algebra / unit / edge-case errors in the neurostim safety core

Repo: `.` (v0.13.0)
Scope: `neurostim/safety/{shannon,charge,water_window,compliance,current_density,envelope,assessment}.py`,
`neurostim/{protocol,electrodes,units,transient}.py`, plus `neurostim/geometry/*`,
`neurostim/materials.py`, `neurostim/uncertainty.py`, `neurostim/data/{cogan2016,butterwick2007,mccreery2010}.py`
as required to close the loop.

Primary sources read directly (via `pdftotext -layout` on the local PDFs in `papers_stim_calc_ref/`):
`merrill_2005_electrical_stimulation.pdf` (eq. 5.1, p. 191), `shannon1992.pdf` (eqs 1-3, Fig. 1,
Discussion, Additional Considerations), `cogan_2008_neural_stimulation.pdf` (Table 2, p. 282).

Every claim below was verified by running the code with
`./.venv/bin/python`. No files in the repo were
created, modified or deleted.

---

## 0. What is correct (verified, not assumed)

These were each derived from first principles and then compared to the code. They are right, and
saying so matters as much as the defect list.

### 0.1 The Shannon identity, units, and per-phase convention

Merrill et al. (2005) eq. (5.1), transcribed from the PDF:

> `log(Q/A) = k - log(Q)`
> "where Q is charge per phase (uC per phase), Q/A is charge density per phase (uC/cm^2 per phase),
> and 2.0 > k > 1.5, fit to the empirical data."

Shannon (1992) eq. (1) is the same relation written `log(D) = k - log(Q)`, with
"D is charge density in uCoulombs/cm^2/phase and Q is charge in uCoulombs/phase".

Rearranging: `k = log10(Q) + log10(Q/A) = log10(Q^2/A)`.

`neurostim/safety/shannon.py:215-216` computes exactly this:
```python
charge_density = charge_per_phase_uC / area_cm2
return math.log10(charge_per_phase_uC) + math.log10(charge_density)
```
Units correct (Q in uC/phase, A in cm^2). Per-phase, not per-pulse: `StimProtocol.charge_per_phase_uC`
(`protocol.py:145-152`) is `I x W` of the leading phase only, and its docstring says so explicitly.

Shannon eq. (2): `IT = (A 10^k)^0.5`. `shannon_max_charge_uC` (`shannon.py:219-224`) returns
`math.sqrt(area_cm2 * 10.0**k)`. Exact.

Shannon eq. (3) for discs, `I = (d/(2T)) (pi 10^k)^0.5`, follows from eq. (2) with `A = pi d^2/4`
and is reproduced identically by `shannon_max_current_uA` for a `DiscElectrode`.

**Axis convention.** Shannon Fig. 1 is labelled x = "Charge per phase (pC/ph)" [uC/ph], y =
"Charge density (uC/cm^2/ph)", captioned "Region of charge and charge density where neural damage
was observed by McCreery et al. is represented by the hatched area. The solid lines represent the
proposed model with parameter k = 1.0, 1.5, and 2.0." The module's `K_BOUNDS`/`K_DAMAGE_OBSERVED`
docstrings describe exactly this. D vs Q axes are not transposed anywhere.

**Round-trip.** `shannon_k(shannon_max_charge_uC(A, k), A) == k` to machine precision (verified
`k=1.5`, `A=0.0598` -> `1.5`).

**Quotations.** All three primary-text quotes in the module docstring are verbatim:
- "The curve for k = 1.5 defines a set of parameters where no damage was observed and is used for
  all computations that follow."
- "For the stimulus conditions of McCreery et al., k = 1.5 is a conservative limit and has been
  used in all calculations in this report."
- "When k = 2, the straight line falls in an area where damage was observed. If this line were used
  to define the limit of safe stimulation, some stimuli would be expected to cause damage."
- and the extrapolation caveat quoted in `envelope.py` / `conditions_warning`.

`K_DEFAULT = K_SHANNON = 1.5` is the defensible choice and matches the source.
`k_warning`'s `excess = 10**((k - 1.5)/2)` is correct (permitted charge goes as `10^(k/2)`), giving
1.78x at k=2.0, and `max_current_interval_uA`'s docstring value `sqrt(10^0.5) = 1.78` is right.

### 0.2 Disc primary current distribution

Re-derived independently. Normalising `J(r) = C / sqrt(1 - (r/a)^2)` over the disc:

```
I = int_0^a  C/sqrt(1-(r/a)^2) . 2 pi r dr
  = 2 pi C (a^2/2) int_0^1 du/sqrt(1-u)        [u = r^2/a^2]
  = 2 pi a^2 C
J_avg = I/(pi a^2) = 2C
=> J(r)/J_avg = 1/(2 sqrt(1 - (r/a)^2))
```

- centre ratio `J(0)/J_avg = 0.5` -> `DISC_CENTRE_RATIO = 0.5` (`current_density.py:69`). Correct.
- `J/J_avg > 1  <=>  sqrt(1-x^2) < 1/2  <=>  x > sqrt(3)/2`, area fraction `1 - 3/4 = 0.25`
  -> `DISC_FRACTION_ABOVE_AVERAGE = 0.25` (`current_density.py:72`). Correct.
- `disc_ratio_at_radius` and `disc_ratio_at_area_fraction` implement these exactly and both raise
  on `r/a >= 1`.

**The edge singularity is acknowledged**, explicitly and in several places: the module docstring
("the density diverges at the rim, so the geometric average always understates the local peak on a
non-recessed electrode"), `CurrentDensityResult.describe()`, and `ChargeResult.describe()`
(`charge.py:157-161`, citing Kuncel & Grill's 25.6 %). The independent-derivation-agrees-with-FEM
remark (25 % vs 25.6 %) is sound.

### 0.3 Access resistance closed forms

- `DiscElectrode.access_resistance_ohm` = `1/(4 sigma a)` (`planar.py:40-42`). Newman (1966). Correct.
- `SphericalElectrode` = `1/(4 pi sigma a)` (`volumetric.py:170-172`). Correct.
- `HemisphericalElectrode` = `1/(2 pi sigma a)` (`volumetric.py:205-207`). Correct: exactly half the
  sphere's area and twice its resistance.
- All three set `access_resistance_is_exact = True`; every other geometry sets `False` and falls back
  to the documented equal-area disc substitution. The flag is threaded through to
  `ComplianceResult.access_resistance_is_exact` and printed in `describe()` as "equal-area approx.".

Consistency check on the capacitance analogy: a free-space disc has `C = 8 eps a`, so
`R_fullspace = eps/(sigma C) = 1/(8 sigma a)`, and a disc flush in an insulating plane driving one
half-space has twice that, `1/(4 sigma a)`. Matches Newman. (This analogy is what finding #10 rests on.)

### 0.4 Water-window sign convention

`water_window.py:194-196`:
```python
polarity = "anodic" if anodic_first else "cathodic"
sign = 1.0 if anodic_first else -1.0
peak = resting_potential_V + sign * excursion
```
Cathodic = negative excursion. Correct. `WaterWindowResult.headroom_V` picks the matching boundary
(`anodic_V - peak` for anodic, `peak - cathodic_V` for cathodic). Correct on both sides.
`WaterWindow.__post_init__` enforces `cathodic_V < anodic_V`.

The `C_eff` construction is internally consistent for the polarity-matched case: injecting exactly
the material's CIC lands the electrode exactly on the corresponding window edge
(`evaluate('Pt', 150.0, anodic_first=False, anodic_first_for_capacitance=False)` -> peak
`-0.600000 V`, headroom `0.000`). The rationale in the module docstring (double-layer 20 uF/cm^2
contradicts Rose & Robblee's measured 100-150 uC/cm^2 by 10x, because Pt is pseudocapacitive) is
correct physics and correctly sourced.

The ohmic `I R_access` drop is correctly *excluded* from the electrode potential and assigned to
compliance instead (`water_window.py:43-44`). This is the right split and matches
`transient.py`'s access-voltage subtraction.

### 0.5 Compliance back-solve is exact and monotonic

`ComplianceResult.max_current_uA` = `current_uA * (available_V / required_V)`. Both terms of
`required_V` are linear in `I` (`ohmic = I R`; `polar = (I W / A)/C`), so the scaling is the exact
inverse of the forward model, not an approximation. Verified:

```
Vc = 1 V -> I_max = 1907.667017 uA -> required_V at I_max = 1.000000 V
Vc = 2 V -> I_max = 3815.334034 uA -> required_V at I_max = 2.000000 V
Vc = 5 V -> I_max = 9538.335084 uA -> required_V at I_max = 5.000000 V
```
Monotonic in `available_V`, exact to 1e-6. Correct.

### 0.6 Aggregation never turns a FAIL into a PASS

- `Status.rank` (`assessment.py:54-62`): `PASS 0 < NOT_EVALUATED 1 < CAUTION 2 < FAIL 3`.
- `_worst` = `max(statuses, key=rank)`; `SafetyAssessment.status` = `_worst([c.status for c in checks])`.
- Therefore any FAIL dominates. Verified across every probe run in this audit.

**No exception is silently swallowed.** `grep -rn "except\|try:" neurostim/safety/` returns exactly
one hit, and it is the substring "except" inside a string literal at `current_density.py:164`. There
is no `try`/`except` anywhere in the safety package; an error in any sub-check propagates out of
`assess()` rather than degrading to PASS. This is the correct design and it is implemented correctly.

### 0.7 Input validation is thorough

Every one of the requested edge cases raises a clear domain `ValueError`. No bare tracebacks, no
silent PASS, no nonsense numbers:

```
I=0            -> ValueError: current_uA must be finite and > 0, got 0
I<0            -> ValueError: current_uA must be finite and > 0, got -100
W=0            -> ValueError: pulse_width_us must be finite and > 0, got 0
f=0            -> ValueError: frequency_hz must be finite and > 0, got 0
f<0            -> ValueError: frequency_hz must be finite and > 0, got -130
I=nan          -> ValueError: current_uA must be finite and > 0, got nan
I=inf          -> ValueError: current_uA must be finite and > 0, got inf
train=nan      -> ValueError: train_duration_s must be > 0 (or math.inf for continuous), got nan
train=-1       -> ValueError: train_duration_s must be > 0 (or math.inf for continuous), got -1
duty>100%      -> ValueError: Pulse does not fit in its period: active duration 10000 us
                  exceeds the 7692.31 us period at 130 Hz
10 kHz/200 us  -> ValueError: Pulse does not fit in its period: active duration 400 us
                  exceeds the 100 us period at 10000 Hz          [pulse overlap caught]
disc d=0       -> ValueError: diameter_um must be > 0 um, got 0.0
disc d<0       -> ValueError: diameter_um must be > 0 um, got -5.0
disc d=nan     -> ValueError: diameter_um must be finite, got nan
ring in==out   -> ValueError: inner_diameter_um (100.0 um) must be smaller than outer_diameter_um
ring in>out    -> ValueError: (same)
ring in=nan    -> ValueError: inner_diameter_um must be a finite value >= 0, got nan
sigma=0        -> ValueError: Tissue conductivity must be a positive finite S/m value, got 0.0
sigma<0        -> ValueError: (same)
k=nan / k=inf  -> ValueError: Shannon k must be finite
cap=0 / nan    -> ValueError: capacitance_uF_cm2 must be finite and > 0
lead_R=nan     -> ValueError: lead_resistance_ohm must be finite and >= 0
medium='blood' -> ValueError: medium must be 'saline' or 'in_vivo'
policy='yolo'  -> ValueError: Unknown policy 'yolo'; expected conservative/nominal/optimistic
```

Extremely small and large electrodes are handled without overflow or underflow:
`DiscElectrode(1.0).area_cm2 = 7.854e-09 cm^2`; `DiscElectrode(10000.0).area_cm2 = 0.7854 cm^2`.
Both flow through the full assessment. `duty_cycle` at exactly 1.0 is accepted; above 1.0 it raises.

Exceptions noted in findings #13 and #14: `compliance_V` and `resting_potential_V` are the two
inputs with no validation.

### 0.8 Miscellaneous verified-correct items

- `units.charge_uC` docstring arithmetic is right: `1 uA . 1 us = 1e-6 A . 1e-6 s = 1e-12 C = 1e-6 uC`.
- `units.CHARGE_DENSITY_TO_UC_CM2["uC/mm2"] = 100.0` is correct (1 mm^2 = 0.01 cm^2).
- `Material.cic_uC_cm2` converts `mC/cm2 -> uC/cm2` by 1e3 and raises on any other unit string.
- Cogan (2008) Table 2 transcription spot-checked against the PDF: "Pt and PtIr alloys,
  Faradaic/capacitive, 0.05-0.15 mC cm-2, -0.6-0.8 V vs Ag|AgCl" matches `materials.py` exactly,
  including the single shared row for Pt and PtIr; "Activated iridium oxide, 1-5, -0.6-0.8, Positive
  bias required for high Qinj"; "Titanium nitride, ~1, -0.9 to 0.9". All consistent.
- `MeasuredRange.bounds(anodic_first)` correctly narrows Pt to the Rose & Robblee sub-ranges
  (50-100 uC/cm^2 anodic-first, 100-150 cathodic-first) rather than quoting the union.
- `Interval` arithmetic, `combine`, `intersect`, `most_restrictive` are all correct for what they
  claim; `Interval.__post_init__` rejects NaN and inverted bounds; `__truediv__` rejects a divisor
  interval spanning zero.
- `butterwick2007.threshold_A_per_cm2`: the `t^-0.5` scaling, the `d^-2` rise below 200 um, and the
  log-linear 1-to-50-pulse interpolation all move the threshold in the conservative direction and
  are implemented as documented. `FITTED_DURATION_EXPONENT` evaluates to -0.4439, matching the
  docstring's "about -0.44".
- `assessment.assess()` caps `n_pulses` sensibly: `max(1, int(n_pulses))`, with `inf` mapped to the
  saturation count. A 0.5 s / 1 Hz train yields 1, not 0.
- `transient.py`: access-voltage subtraction, magnitude handling of either polarity, the
  `max(polarisation, 0.0)` floor, and the `samples_in_access_estimate >= 3` resolution caution are
  all sound. `charge_injection_limit_uC_cm2` correctly uses
  `abs(water_window_limit_V - resting_potential_V)` as the available swing and documents the
  linearity assumption it rests on.

---

## 1. Findings table

Ranked CRITICAL / HIGH / MEDIUM / LOW. `file:line` refers to
`./`.

### CRITICAL

| # | file:line | Wrong expression | Correct expression | Numeric failure case |
|---|-----------|------------------|--------------------|----------------------|
| 1 | `neurostim/safety/assessment.py:119-131`, and identically `:133-156` (`limiting_current_interval_uA`) and `:158-167` (`limiting_mechanism`) | `candidates = [self.shannon.max_current_uA, self.charge.max_current_uA]` + compliance when evaluated; `return min(candidates)` | must also include the microelectrode 4 nC/phase limit, the chronic-degradation limit, the Butterwick current-density limit, and the water-window limit; and must *exclude* Shannon when the electrode is below the macro/micro boundary | `DiscElectrode(100 um,'AIROF')`, 60 us, 130 Hz: code returns **830.6034 uA** labelled `"Shannon tissue-damage criterion"` on an electrode for which the same report says the Shannon criterion is *not applicable*. True binding limit **66.6667 uA**. **12.46x overstatement.** Full derivation in section 2. |

### HIGH

| # | file:line | Wrong expression | Correct expression | Numeric failure case |
|---|-----------|------------------|--------------------|----------------------|
| 2 | `neurostim/safety/assessment.py:733-791` (`assess()` has no waveform branch) | Shannon, CIC, water-window and chronic limits applied unchanged when `protocol.waveform == "monophasic"` | every one of those limits was measured under charge-balanced biphasic pulsing (`materials.py:105`: `waveform="charge-balanced, capacitively coupled biphasic, 50 pps"`); they must be `NOT_EVALUATED` or explicitly derated for monophasic | `CylindricalBandElectrode(1270,1500,'PtIr')`, 3000 uA x 90 us @ 130 Hz, `waveform="monophasic"`: **exactly one check changes** vs biphasic (charge balance FAIL). Water window still reports **`PASS  peak -0.02 V, 0.58 V headroom`**. Reality: net DC = 35.10 uA over 0.05985 cm^2 = **586.5 uA/cm^2**; at the module's own `C_eff = 250 uF/cm^2` that is **2.346 V/s**, so the interface leaves the 0.6 V window in **0.256 s**. `limiting_current_uA` is unchanged at 15285.5 uA. The module's own docstring (`assessment.py:563-564`) says "No charge-density limit in this package is validated for monophasic delivery" - and then applies them all. |
| 3 | `neurostim/protocol.py:117-121` (`return_phase_current_uA`), consequently `:160-171` | `return self.current_uA / self.return_phase_ratio` - the return amplitude is *derived* from the ratio, so `Q_return == Q_lead` identically | return-phase amplitude and width must be independent fields so an imbalanced pulse can be expressed at all | **Biphasic charge imbalance is structurally impossible.** Swept 150 `(I, W, return_phase_ratio)` combinations (I in {1,10,100,1e4,1e6} uA, W in {1,10,100,400} us, r in {0.1, 1/3, 1, 3, 7, 101}): **zero unbalanced**, worst residual 1.7e-18 uC. Therefore `_charge_balance_check`'s imbalance branch (`assessment.py:567-579`) is dead code for every biphasic protocol, and `net_dc_current_uA` is identically 0. The team-lead example "100 uA/100 us cathodic + 20 uA/500 us anodic" *is* expressible (r=5) and *is* balanced - but "100 uA/100 us cathodic + 20 uA/100 us anodic", the actual failure mode, cannot be expressed. The package advertises a charge-balance check that cannot detect imbalance. |
| 4 | `neurostim/safety/current_density.py:181`; `neurostim/safety/compliance.py:180-196`; `neurostim/safety/water_window.py:193` | all three use the *leading-phase* current / charge density only (`protocol.current_uA`, `charge_per_phase_uC`) | must evaluate `max(I_lead, I_return)` for current density and compliance; the return phase is a real phase with a real current density | `return_phase_ratio=0.2` on 1000 uA x 100 us gives a return phase of **5000 uA x 20 us** - 5x the leading current. Every reported quantity is *bit-identical* to the symmetric `r=1.0` case: `required_V = 0.524 V` both times (true return-phase demand ~2.6 V), `J_avg = 0.01671 A/cm^2` both times (true peak 0.0836 A/cm^2), same Shannon, same CIC, same overall CAUTION. `protocol.py:56-59` claims ratio `r` "keeps the pulse charge-balanced while lowering the return-phase current density" - true only for `r > 1`, and nothing enforces it. |
| 5 | `neurostim/safety/compliance.py:10-21` (the stated model) and `:179-197` (implementation) | `V_required = I (R_access + R_lead) + dV_polarisation` - one electrode, one interface, one spreading resistance | `V_required = I (R_access,WE + R_access,CE + R_lead) + dV_pol,WE + dV_pol,CE + (E_eq,WE - E_eq,CE)`; collapses to the coded form only when the return electrode is large enough that its two terms vanish | Bipolar DBS, two identical `CylindricalBandElectrode(1270,1500)` contacts, 3000 uA x 90 us: code reports `required_V = 1.571 V` (ohmic 0.517 + polarisation 1.054). Two-interface truth ~ `2 x 0.517 + 2 x 1.054 = 3.142 V`. **Under-reports by 1.571 V (2.0x).** A 3 V-compliance stimulator scores PASS at 52 % utilisation when it is actually at 105 % and will drop out of regulation - the exact silent failure the module docstring warns about. `grep -rni "counter electrode\|counter-electrode\|return electrode\|bipolar\|monopolar" neurostim/safety/` returns **zero hits**; the only hits in the package are `models/thermal.py:56,326` and `data/elwassif2006.py:23,28`. The module enumerates three terms and calls that "The voltage budget modelled here". |
| 6 | `neurostim/safety/envelope.py:251-260` | `Excursion(parameter="duty cycle", value=protocol.duty_cycle * 100.0, reference=100.0, ...)` where `protocol.duty_cycle` is the intra-period current-flowing fraction (`protocol.py:131-134`) | McCreery et al. (2010)'s duty cycle is the **train on/off schedule** (50 % = stimulation interleaved with rest; 100 % = continuous). These are different quantities. Either drop the excursion or add a separate `train_duty_cycle` field to `StimProtocol` | The **exact McCreery fit protocol** (400 us/phase, 50 Hz, 7 h) has `duty_cycle = 0.04` -> `fold = 25.0` -> `outside = True` -> `EnvelopeResult.inside = False` **for the very data the envelope is built from**. Consequence 1: the `_envelope_check` branch "protocol is within the conditions the damage criterion was fitted at" (`assessment.py:351-357`) is **unreachable for any pulsed protocol**. Consequence 2: 0.04 is passed to `mccreery2010.duty_cycle_note`, which takes the `duty_cycle <= 0.55` branch and prints *"reducing duty cycle to 50 % shrank the damage radius from at least 150 um to about 60 um"* - about a protocol that is in fact running continuously. |

### MEDIUM

| # | file:line | Wrong expression | Correct expression | Numeric failure case |
|---|-----------|------------------|--------------------|----------------------|
| 7 | `neurostim/safety/water_window.py:172-192` | signature has two independent polarity parameters with **different defaults**: `anodic_first: bool = False` (sets the sign) and `anodic_first_for_capacitance: bool \| None = None` (selects `C_eff`) | resolve `anodic_first_for_capacitance` to `anodic_first` when it is `None` | `WW.evaluate('AIROF', 1000.0, anodic_first=False)` -> `C_eff = 5833.33 uF/cm^2`, `peak = -0.1714 V`, `headroom +0.4286 V`, PASS. With the capacitance polarity supplied: `C_eff = 1666.67`, `peak = -0.6000 V`, `headroom 0.0000 V` - the correct by-construction answer, since 1000 uC/cm^2 **is** AIROF's cathodic-first CIC and must land exactly on the edge. **Excursion understated 3.50x.** Anodic-first at 2100 uC/cm^2: `+0.3600 V` vs correct `+0.8000 V`, **2.22x**. Silent and material-dependent: Pt coincidentally agrees (250 uF/cm^2 either way) so the defect is invisible in Pt-based tests. `SafetyCalculator.assess()` passes both (`assessment.py:763,766`) so the packaged path is safe; the function is exported at `safety/__init__.py:36` and any direct caller is not. |
| 8 | `neurostim/safety/water_window.py:79-87` | `available_V = min(abs(cathodic_V), abs(anodic_V))`, documented as "With polarity unknown, take the narrower half" (i.e. presented as the conservative choice) | the narrower half-window sits in the **denominator** of `C = limit / available_V`, so it makes `C` *larger*, hence `dV = (Q/A)/C` *smaller*, hence the check *more* permissive. The conservative pairing is the **wider** half-window with the **conservative** CIC | AIROF: `min(0.6, 0.8) = 0.6` is paired with the **full-range optimistic** CIC 3500 uC/cm^2 (`cic_uC_cm2("optimistic", None)`, line 75) giving `C = 5833 uF/cm^2` - the most permissive value obtainable from the material record. Both halves of the pairing are individually the permissive choice; the docstring labels the pair conservative. |
| 9 | `neurostim/safety/charge.py:71-73` and `neurostim/safety/shannon.py:247` (back-solve) versus `charge.py:115` and `shannon.py:265` (the `<=` comparisons) | `max_current = limit * A / (pw * 1e-6)`, then `units.charge_uC` recomputes the density as `I * pw * 1e-6` - a different float association; the checks then compare with a bare `<=` and no tolerance | apply a round-trip tolerance on the comparison, or derive the density through the identical float expression used by the back-solve | Swept 30 `(diameter, pulse_width)` pairs: **8 of 30 CIC limits and 6 of 30 Shannon limits FAIL their own check** at exactly the current the back-solve returned. e.g. `d=100 um, W=100 us, Pt`: density `100.00000000000003` vs limit `100` -> FAIL. Surfaces in the aggregate as the self-contradictory line `Charge injection limit: 100 uC/cm^2 exceeds the 100 uC/cm^2 limit for PtIr; max 1.001e+04 uA`. The back-solve is therefore not an exact inverse of the forward model, contrary to what a "max safe current" must be. |
| 10 | `neurostim/geometry/planar.py:57-61` (`RingElectrode`) and `:104-106` (`RectangularElectrode`) | ring: "For a thin ring this ***underestimates*** the resistance, because a thin ring concentrates current at two edges rather than spreading it over a filled disc of the same area." rectangle: "a long thin strip has a ***higher*** access resistance than the equal-area disc because current crowds at its long edges." | Both statements are backwards. Spreading resistance goes as `1/C`, and a thin ring or long strip has far greater *linear extent* than its equal-area disc, hence **larger** capacitance and **lower** resistance. The equal-area disc substitution therefore **over**estimates `R_access` for both | Rigorous numeric bound via Thomson's theorem (any trial charge density gives `W_trial >= W_true`, hence `C_trial = Q^2/(2 W_trial) <= C_true`), with an inverse-sqrt edge-singularity trial density; method validated against the exact disc to **0.34 %**. Results (`R_equal-area-disc / R_ring = C_ring / C_disc`): `b=500 um, w=10 um` -> **>= 3.41x**; `b=500, w=50` -> **>= 1.86x**; `b=1000, w=20` -> **>= 3.41x**; `b=100, w=10` -> **>= 1.86x**. Direction is wrong by a factor of 2-3.4, not marginally. A user who "corrects" for the stated direction adds margin the wrong way. |
| 11 | `neurostim/safety/assessment.py:495-501` (`_regime_check` macroelectrode branch) combined with `:54-62` (`Status.rank`) | macroelectrodes get `Status.NOT_EVALUATED`, and `NOT_EVALUATED.rank = 1 > PASS.rank = 0`, while `SafetyAssessment.status = _worst(...)` | the macro branch should return `PASS` ("Shannon is the applicable criterion and it passed") or be excluded from the aggregate; alternatively `NOT_EVALUATED` should rank below `PASS` | Swept 96 `(I, W, f)` combinations on `CylindricalBandElectrode(1270,1500,'PtIr')` with `compliance_V=10`: **overall `Status.PASS` is never reachable for any macroelectrode.** The best attainable verdict is `NOT_EVALUATED`. The documented four-value status vocabulary is effectively three-valued for the package's most common use case. |
| 12 | `neurostim/safety/shannon.py` (module-wide) | `Q_max = sqrt(A 10^k)` applied unchanged to `RingElectrode`, `CylindricalBandElectrode`, `RectangularElectrode`, `MicrowireElectrode` | Shannon's own Discussion (p. 425): *"It is important to note that the limit of safe stimulation is linearly related to electrode **diameter**, not electrode area. This result is probably due to the charge 'building up' at the edges, to create higher charge densities around the perimeter of the electrode."* Eq. (2) was derived for, and validated on, **flat cortical-surface discs** | `grep -rni perimeter neurostim/` hits `safety/charge.py:159`, `data/current_distribution.py:5`, `data/mccreery1990.py:268` - **never `safety/shannon.py`**. A ring and a disc of identical area receive identical Shannon limits despite ~3x different perimeter. Access resistance carries an explicit `access_resistance_is_exact = False` flag for non-discs and prints "equal-area disc approx."; the Shannon result carries no equivalent geometry caveat anywhere in the output. |

### LOW

| # | file:line | Wrong expression | Correct expression | Numeric failure case |
|---|-----------|------------------|--------------------|----------------------|
| 13 | `neurostim/safety/compliance.py:134-144` | `compliance_V: float \| None = None` is never validated - contrast `lead_resistance_ohm` at `:146-149` and `measured_impedance_ohm` at `:151-156`, which both are | reject non-finite and `<= 0` | `compliance_V = -5.0` -> summary `"needs 0.52 V but only -5.00 V available"`. `compliance_V = nan` -> `passes = (required_V <= nan) = False` -> FAIL. The verdict direction is safe in both cases (FAIL, not a silent PASS), but the reported text and number are nonsense rather than a domain error. |
| 14 | `neurostim/safety/water_window.py:209-236` (and `:168-206`) | `resting_potential_V` is never checked against the window | raise when `resting_potential_V` lies outside `[cathodic_V, anodic_V]` | `max_charge_density_in_window_uC_cm2('Pt', resting_potential_V=5.0)` -> **1400.0 uC/cm^2 "allowed"** on an electrode already 4.2 V beyond its anodic limit. The negative direction is handled (`-5.0` -> `0.0`) only because of the `available_V <= 0` guard, not by an explicit domain check. |
| 15 | `neurostim/protocol.py:171` | `abs(self.net_charge_per_pulse_uC) < 1e-12` - an absolute tolerance in uC | relative tolerance against `charge_per_phase_uC` | Scale-dependent. Benign at neural amplitudes (worst observed residual 1.7e-18 uC at r=3, six orders below the threshold) but would misjudge at mC-scale charges. Structurally moot today because of finding #3. |
| 16 | `neurostim/geometry/volumetric.py:44-51` | `CylindricalBandElectrode.access_resistance_ohm` delegates to `super()`, i.e. the **half-space flush-disc** form `1/(4 sigma a_eq)`, for a geometry that `geometry/__init__.py:3-5` explicitly describes as "immersed in tissue" | the immersed-cylinder spreading form `R = ln(2L/r) / (2 pi sigma L)` | d=1270/h=1500 (clinical DBS, aspect 1.18): code **517.5 ohm** vs cylinder **470.7 ohm** -> 1.10x. d=1270/h=500 (aspect 0.39): **896.4** vs **413.0** -> **2.17x**. d=50/h=5000 (aspect 100): **1428.6** vs **544.9** -> **2.62x**. Conservative direction for compliance, correctly flagged `access_resistance_is_exact = False`, and the docstring does warn it "degrades" for tall narrow bands - hence LOW. But the half-space/full-space model mismatch itself is never stated, and the same `super()` fallback is used by `MicrowireElectrode` (d=25 um, L=200 um: 9947 vs 7880 ohm, 1.26x). |

---

## 2. Full derivation for CRITICAL finding #1

### 2.1 The contract being broken

`SafetyAssessment.limiting_current_uA` (`neurostim/safety/assessment.py:118-131`) is documented at
lines 120-124 as:

> "Lowest current limit across every check that produces one.
>
> This is the number to programme against: it is the binding constraint, whichever physical
> mechanism happens to impose it."

It is the headline number in `SafetyAssessment.describe()` (`:180-181`) and a key in
`SafetyCalculator.report()` (`:831`). A user is explicitly told to programme against it.

### 2.2 The code

```python
@property
def limiting_current_uA(self) -> float:
    candidates = [
        self.shannon.max_current_uA,
        self.charge.max_current_uA,
    ]
    if self.compliance.evaluated:
        candidates.append(self.compliance.max_current_uA)
    return min(candidates)
```

`assess()` (`:779-791`) runs nine checks. **Six** of them produce a quantitative current limit.
**Three** are in the `min`. The four omitted limits are:

1. **Microelectrode charge per phase** - `_regime_check` (`:426-501`), threshold
   `cogan2016.MICROELECTRODE_DAMAGE_THRESHOLD_NC_PER_PHASE = 4.0` nC/phase. This check can return
   `Status.FAIL`.
2. **Chronic degradation** - `_chronic_check` (`:504-547`), `material.chronic_threshold`. Can return
   `Status.FAIL`.
3. **Butterwick current density** - `_current_density_check` (`:387-423`), threshold from
   `butterwick2007.threshold_A_per_cm2`. Can return `Status.FAIL`.
4. **Water window** - `water_window.max_charge_density_in_window_uC_cm2` (`water_window.py:209-236`)
   exists and is exported, but `grep` confirms it is **never called from anywhere in the package**.
   It is a dead limit.

Additionally, the Shannon limit is included **unconditionally**, even when `_shannon_check`
(`:209-223`) has already returned `Status.NOT_EVALUATED` with the summary *"not applicable: ... is
below the macro/micro boundary"*. `limiting_mechanism` (`:158-167`) has no regime guard either, so
it can name a criterion the same report declares inapplicable.

### 2.3 Worked case - exact inputs

```python
from neurostim.geometry import DiscElectrode
from neurostim.protocol import StimProtocol
from neurostim.safety.assessment import SafetyCalculator

e = DiscElectrode(diameter_um=100.0, material='AIROF')
p = StimProtocol(current_uA=10, pulse_width_us=60.0,
                 frequency_hz=130.0, train_duration_s=10.0)
a = SafetyCalculator(e, p).assess()      # no compliance_V supplied
```

Derived quantities:

```
area_cm2 = pi * (50e-4 cm)^2 = 7.853981634e-05 cm^2
W        = 60 us = 60e-6 s
n_pulses = 10 s * 130 Hz = 1300   (>= Butterwick saturation count of 50)
material = AIROF, cathodic-first, policy 'conservative'
           -> CIC = 1.0 mC/cm^2 = 1000 uC/cm^2
           -> water window -0.6 / +0.8 V vs Ag|AgCl
           -> chronic_threshold = None
```

Note `area_cm2 = 7.854e-05 < 3e-4 = cogan2016.MACRO_MICRO_BOUNDARY_AREA_CM2[0]`, so
`is_microelectrode(area) == True`. This electrode is unambiguously in the microelectrode regime.

### 2.4 Every candidate limit, in microamperes

| Mechanism | Derivation | Value (uA) | In the `min`? |
|-----------|-----------|-----------:|---------------|
| Shannon, k = 1.5 | `sqrt(A . 10^1.5)/W = sqrt(7.853981634e-05 x 31.6228)/6e-5 = 0.0498357/6e-5` | **830.6034** | yes |
| AIROF charge injection (conservative, cathodic-first) | `1000 uC/cm^2 x A / W = 0.0785398 uC / 6e-5 s` | **1308.9969** | yes |
| Stimulator compliance | not supplied -> `compliance.evaluated == False` | *n/a* | n/a |
| **Microelectrode charge/phase (Cogan 2016)** | `4.0 nC/ph = 4e-3 uC; 4e-3 / 6e-5 s` | **66.6667** | **no** |
| **Butterwick current density** | `J_th(60 us, d = 2 x equiv_radius = 100 um, n = 50) = 1.8756 A/cm^2`; `1.8756 x A x 1e6` | **147.3065** | **no** |
| **Water window** | `max_charge_density_in_window = 0.6 V x 1666.67 uF/cm^2 = 1000 uC/cm^2`; `x A / W` (coincides with the CIC by construction) | **1308.9969** | **no** |
| **Chronic degradation** | AIROF has `chronic_threshold = None` | *n/a* | n/a |

Sorted: **66.6667** (microelectrode) < 147.3065 (current density) < 830.6034 (Shannon) < 1308.9969
(CIC = water window).

- **True minimum: 66.6667 uA**, imposed by the microelectrode charge-per-phase criterion - which is,
  by the package's own `_regime_check` docstring (`:426-432`), *"the governing quantity"* at this size.
- **Code returns: 830.6034 uA**, labelled `limiting_mechanism = "Shannon tissue-damage criterion"`.
- **Should return: 66.6667 uA.**

### 2.5 Where the 12.5x comes from

```
830.6034 / 66.6667 = 12.459  ~ 12.5x
```

Equivalently, in charge terms: at the current the code reports as the binding limit,

```
Q_per_phase = 830.6034 uA x 60e-6 s = 0.049836 uC = 49.836 nC/phase
threshold                                          =  4.000 nC/phase
49.836 / 4.000 = 12.459x over a tissue-damage limit
```

The two ratios agree exactly because both limits are evaluated at the same fixed pulse width, so the
charge ratio and the current ratio are the same number.

### 2.6 The compounding label defect

For this same electrode, `_shannon_check` returns:

```
NOT_EVALUATED | Shannon criterion: not applicable: 1.96e-05 cm^2 is below the macro/micro
                boundary (k would read 1.91)
```

while `limiting_mechanism` returns `"Shannon tissue-damage criterion"`. One report therefore states,
in one paragraph, that the Shannon criterion does not apply to this electrode, and in another that
the Shannon criterion is the binding constraint on it. Both come from the same `SafetyAssessment`.

### 2.7 Two further probes confirming the class of defect

Method: take whatever `limiting_current_uA` returns, build a protocol at exactly that current, and
re-assess. If the number is the binding constraint, the re-assessment must not FAIL.

```
DiscElectrode(357 um, 'Pt'), 200 us, 50 Hz, 1 h
  limiting_current_uA = 500.491 uA   ("Pt charge-injection limit")
  re-assessed at 500.491 uA -> overall FAIL
    FAIL Current density      0.500 A/cm^2 >= 0.2751 A/cm^2  -> true limit 275.370 uA
    FAIL Chronic degradation  100 uC/cm^2  >  50 uC/cm^2     -> true limit 250.246 uA
  overstatement 2.00x

DiscElectrode(357 um, 'PtIr'), 10 us, 130 Hz, 1 h
  limiting_current_uA = 10009.8 uA
  re-assessed -> overall FAIL
    FAIL Current density      10.0 A/cm^2 >= 1.037 A/cm^2    -> true limit ~1038 uA
    FAIL Chronic degradation  100 uC/cm^2 >  50 uC/cm^2
    FAIL Charge injection     (finding #9, 1-ulp round-trip)
  overstatement 9.6x

DiscElectrode(50 um, 'AIROF'), 200 us, 130 Hz, 10 s, run at 50 uA
  overall FAIL (Microelectrode charge/phase: 10 nC/ph exceeds 4 nC/ph)
  yet limiting_current_uA = 98.17 uA, i.e. the report simultaneously tells the user
  they have 1.96x headroom above the current that is failing.
```

In all three the aggregate `status` is correctly `FAIL` - finding 0.6 holds, the aggregation is
sound. The danger is narrower and sharper: the single number the documentation instructs the user to
programme against is wrong by 2x to 12.5x, in the unsafe direction, and it is wrong even when the
report beside it says FAIL.

### 2.8 Correct expression

```python
@property
def limiting_current_uA(self) -> float:
    pw_s = self.protocol.pulse_width_us * 1e-6
    area = self.electrode.area_cm2
    candidates = [self.charge.max_current_uA]

    # Shannon only where Shannon applies; below the boundary the governing
    # quantity is charge per phase (Cogan et al. 2016).
    if cogan2016.is_microelectrode(area):
        candidates.append(
            cogan2016.MICROELECTRODE_DAMAGE_THRESHOLD_NC_PER_PHASE * 1e-3 / pw_s)
    else:
        candidates.append(self.shannon.max_current_uA)

    if self.material.chronic_threshold is not None:
        candidates.append(
            self.material.chronic_threshold.low_uC_cm2 * area / pw_s)

    if self.current_density.threshold is not None:
        candidates.append(
            self.current_density.threshold.threshold_A_per_cm2 * area * 1e6)

    candidates.append(
        ww_mod.max_charge_density_in_window_uC_cm2(
            self.material,
            anodic_first=self.protocol.anodic_first,
            resting_potential_V=self.resting_potential_V,
        ) * area / pw_s)

    if self.compliance.evaluated:
        candidates.append(self.compliance.max_current_uA)

    return min(candidates)
```

The identical omission must be fixed in `limiting_current_interval_uA` (`:133-156`) and
`limiting_mechanism` (`:158-167`).

**Implementation note:** `SafetyAssessment` does not currently retain the `CurrentDensityResult`.
`assess()` builds `jd_result` at `:753`, passes it to `_current_density_check`, and discards it. It
needs to become a dataclass field alongside `shannon`, `charge`, `water_window` and `compliance`
before the above can be written.

---

## 3. Open questions I could not resolve

1. Whether `RingElectrode` is meant to model a flush coplanar annulus (what `planar.py:1-6` states,
   and what finding #10's 1.9-3.4x bound is derived for) or the rim of a guide cannula protruding
   into tissue (also named at `planar.py:54`). The two have different correct answers.
2. Whether the `reference=100.0` duty-cycle comparison in finding #6 is a unit confusion or a
   placeholder for a `train_duty_cycle` field that was planned and never added to `StimProtocol`.
   No design note either way in `envelope.py` or `CHANGELOG.md`.
3. Whether the 2.0x compliance under-report in finding #5 is a deliberate monopolar-only scope with
   a missing caveat, or unnoticed. Nothing in `compliance.py`, `README.md` or any docstring states a
   monopolar assumption.
4. The exact magnitude of the two-interface correction for a genuinely asymmetric electrode pair
   (microelectrode against a large return). `SafetyCalculator` has no field for the return
   electrode's geometry, so this cannot be computed from the current API at all.
5. Whether `effective_capacitance_uF_cm2`'s use of the **optimistic** CIC (`water_window.py:75`)
   while `charge.evaluate` honours the caller's `policy` is deliberate asymmetry or oversight. Its
   effect is that the water-window check can never bind before the CIC check under the default
   conservative policy, which would explain - though not justify - why its back-solve was never
   wired into `limiting_current_uA`.
6. Whether finding #3's structural charge balance is a deliberate simplification ("we only model
   balanced pulses") or an unnoticed consequence of the `return_phase_ratio` parameterisation. The
   presence of a live FAIL branch for imbalance in `_charge_balance_check` suggests the latter.
7. Not audited, as outside the brief: `neurostim/models/` (thermal, VTA, field, strength-duration),
   `neurostim/io/`, `neurostim/sensitivity.py`, `neurostim/uncertainty.py` beyond `Interval` itself,
   `neurostim/audit.py`, `neurostim/gui/`, and the `tests/` suite. Several findings above (#3, #7,
   #11) are of a kind that a test suite can mask rather than catch, so the tests are worth a
   separate pass.

---

## 4. Process note

Global `CLAUDE.md` rule 14 requires appending a summary of this turn to
`./_conversation_history.md`. The audit brief specified
READ-ONLY with no edits to any file. I honoured the read-only constraint and wrote nothing to the
repo; this report lives in the session scratchpad only. Someone with write access needs to log the
turn.
