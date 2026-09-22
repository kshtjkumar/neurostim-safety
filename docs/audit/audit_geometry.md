# Geometry / Materials / Units / Interval-Arithmetic Audit

Repo: `.` — **read-only audit, no repo files modified.**
Interpreter: `./.venv/bin/python`
Scripts: `$SCRATCH/g1_areas.py` … `$SCRATCH/gf_cd.py` (every number below was produced by running code, not asserted).

Files read in full: `neurostim/geometry/{base,planar,volumetric,arrays,__init__}.py`,
`neurostim/{electrodes,materials,units,uncertainty}.py`, plus the consumers needed to trace
blast radius (`safety/{shannon,charge,assessment,water_window,current_density}.py`,
`models/field.py`, `io/report.py`, `protocol.py`).

Heeding the prior run's correction: **the protocol default is cathodic-first**, and for Pt that
*raises* the applicable CIC band, it does not lower it — verified against the primary text below.

---

## 0. Headline

**Every surface-area formula in the package is correct.** All twelve were derived by hand first
and then compared against the code; all twelve match to machine precision (§1). There is no
CRITICAL area bug. The area→charge-density→verdict chain is sound.

The real defects are in what surrounds the areas: a factor-2 half-space/full-space error in the
field model's geometry dispatch, a disc-only current-distribution claim broadcast to every shape
including spheres, an unverified user CIC that silently loosens a *different* safety check, and
two docstrings that state the sign of their own approximation error backwards.

---

## 1. Findings table

| # | Sev | Location | Wrong | Correct | Demonstration |
|---|-----|----------|-------|---------|---------------|
| 1 | **HIGH** | `models/field.py:71-73` `_geometry_factor` | Returns `4*pi` for `DiscElectrode`, `RingElectrode`, `RectangularElectrode`. These are documented (`geometry/planar.py:1-6`, `geometry/__init__.py:3-4`) as flush in an **insulating plane** → current enters a **half-space**. | `2*pi` for all three, as already done for `HemisphericalElectrode`. | `V(1 mm, 100 uA, 0.35 S/m)` for a 500 um disc: code **22.7364 mV**, true `I/(2*pi*sigma*r)` = **45.4728 mV**. Ratio exactly **0.500**. |
| 2 | **HIGH** | `models/field.py:71-73` vs `geometry/planar.py:40-46` | Same class is internally inconsistent: `DiscElectrode.access_resistance_ohm` uses the **half-space** Newman `1/(4*sigma*a)`, while the field model treats it as **full-space**. | One convention per geometry. | 500 um disc, 100 uA: `I*R_access` = **285.71 mV**; field model at `r=a` = **90.95 mV**. Ratio **3.1416**. The legitimate disc-vs-sphere surface ratio is `pi/2 = 1.571`; the excess factor is exactly **2** — finding #1. |
| 3 | **HIGH** | `safety/current_density.py:30-45,69,109,120` dispatched for every electrode | The disc primary-distribution result (`J(r)/J_avg = 0.5/sqrt(1-(r/a)^2)`, centre `0.5x`, outer 25 % above average, "density diverges at the rim") is emitted **verbatim for every geometry**. | For a sphere and for a hemisphere flush in a plane the primary current distribution is **uniform**: `J = I/A` everywhere, no edge, no divergence. Band/microwire crowd at their real edges but not with disc numbers. | `gf_cd.py`: identical "centre 0.50x average (primary distribution) \| outer 25 % … diverges at the rim" printed for `Disc`, `Sphere`, `Hemisphere`, `CylindricalBand`, `Microwire`, `Rectangular`. |
| 4 | **HIGH** | `materials.py:758-787` + `safety/water_window.py:75,189-193` | An **unverified** `with_measured_cic` value silently feeds `effective_capacitance_uF_cm2`, which uses `mat.cic_uC_cm2("optimistic", …)`. Raising the user CIC 100→500 uC/cm² moves `C_dl` 250→833 uF/cm² and shrinks the modelled polarisation 4x — **loosening** the water-window check. The `WaterWindowResult` carries **no** provisional marker. | Propagate `cic.verified` into every result derived from the CIC, and downgrade a water-window PASS built on an unverified CIC to CAUTION. | `gc_ww2.py`: published Pt → excursion 0.004074 V, `C_dl` 250; user 500 uC/cm² → excursion 0.001222 V, `C_dl` 833.3. `"PROVISIONAL" in water_window.describe()` → **False** in both cases. |
| 5 | MEDIUM | `geometry/planar.py:59-62` (Ring docstring) | "For a thin ring this **underestimates** the resistance". | It **overestimates**. | Thin annulus `w/b = 0.01`: equal-area disc **50 634 Ω** vs thin-ring **≈11 682 Ω** → substitution is **4.33x too high**. At `w/b = 0.05`, 2.45x. |
| 6 | MEDIUM | `geometry/planar.py:104-107` (Rect docstring) | "a long thin strip has a **higher** access resistance than the equal-area disc". | **Lower.** Spreading resistance scales with the largest linear dimension, not `sqrt(area)`; at fixed area the disc is the *most* resistive planar shape (classical Pólya–Szegő capacity-minimising-disc result). | Exact elliptic-disc solution `R = K(e)/(2*pi*sigma*a)` (validated: `K(0)/(2*pi) = 0.2500000000` reproduces Newman). Aspect 10 → true **5314 Ω** vs equal-area disc **7143 Ω** (**1.344x too high**); aspect 50 → **2.096x too high**. |
| 7 | MEDIUM | `geometry/base.py:63-75` used by `volumetric.py:44-51` (band) and `MicrowireElectrode` (no override) | The default substitutes an equal-area disc and applies **Newman's half-space** `1/(4*sigma*a)` to geometries that are **fully immersed in tissue** (full space). Documented only as a *shape* approximation; the half/full-space category error is not mentioned. | Equal-area **sphere** `1/(4*pi*sigma*a)` is the right full-space reference. | DBS band 1270x1500 um: code **517.5 Ω**, equal-area sphere **329.5 Ω** → ratio **1.571 = pi/2**, exactly, for every immersed geometry. Microwire d=50, L=500, hemi tip: code **4408.7 Ω** vs thin-cylinder full-space `ln(2L/r)/(2*pi*sigma*L)` = **3354.9 Ω** (1.31x). Its equal-area disc radius is **1380 um** for a lead of physical radius 635 um. |
| 8 | MEDIUM | `electrodes.py:107-122, 124-134, 144-154` | Presets that model a **non-disc** physical electrode as an equal-area `DiscElectrode` inherit `access_resistance_is_exact = True`, so `describe()` prints "**(exact)**" for a conical iridium facet, a penetrating microelectrode and an immersed iridium **wire**. | The area substitution is honestly documented in each `note`; the `(exact)` R label contradicts it. | `gd_presets.py`: `mccreery_microelectrode … R_access 15699 ohm (exact)`, `beebe_iridium_wire … R_access 6255 ohm (exact)`, `mccreery2010_chronic … 28289 ohm (exact)`. |
| 9 | MEDIUM | `geometry/arrays.py:4-6, 56-64` | Module docstring promises the array models "the caution that simultaneous stimulation on neighbouring sites does not simply share charge in proportion to area". **No such caution exists anywhere** (`grep -rn "sharing\|simultaneous"` hits only this docstring). `total_area_cm2` / `mean_area_cm2` are public and unguarded — dividing total charge by total area is exactly the error the docstring names. | Either implement the warning or delete the promise; there is no array-level safety API at all (`SafetyCalculator` takes one `Electrode`). | Field **superposition is** implemented and caveated (`models/field.py:211-250`) — the omission is on the safety side only. `total_area_cm2` of 100 **coincident** sites returns `0.001963 cm²` with no complaint. |
| 10 | MEDIUM | `uncertainty.py:100-126` | `_binary` treats both operands as independent, so `I*I` is the **dependency problem**, not a square. For an interval spanning zero the result is both spurious and **impossible** (negative). No `__pow__`, `square`, `log10`, `exp` or `abs` exists, so the Shannon `k = log10(Q^2/A)` path **cannot** be run on intervals today — the hazard is latent, not live. | A `square()` with the interior extremum at 0, and outward-rounded elementary functions, before anyone extends this. | `I = [-2,3]`: `I*I` → `[-6, 9]`; true range of `x^2` → `[0, 9]`. `I = [-1,1]`: `I*I` → `[-1,1]`; true `[0,1]`. Feeding that low bound to `log10` → `ValueError: expected a positive input`. |
| 11 | MEDIUM | `materials.py:84-90` `MeasuredRange.__post_init__` | `if self.high < self.low` is **NaN-blind** (every NaN comparison is False), so a NaN bound is accepted. | Reject non-finite bounds explicitly. | `MeasuredRange(1.0, nan, …)` and `MeasuredRange(nan, 1.0, …)` both construct. `with_measured_cic(Pt, 100, high=nan).cic_uC_cm2("optimistic")` → **nan**; `"nominal"` → **nan**. `high=inf` → **inf**. |
| 12 | MEDIUM | `materials.py:787` `return replace(material, cic=measured)` | Only the **CIC** is replaced. The original material's `water_window`, `chronic_threshold` and `note` survive **with their original citations**, so a user-measured coating still reports Rose & Robblee's platinum-dissolution threshold as its own. | Clear or re-flag the other constants, or document the carry-over. | `ga_flag.py` report text: `[PASS] Chronic degradation: 1.019 uC/cm^2 is below the 20 uC/cm^2 platinum dissolution threshold … (platinum dissolution, rose_robblee1990)` — printed for a material whose CIC came from `user_measurement`. |
| 13 | LOW | `uncertainty.py` (whole module) | No **outward rounding**; arithmetic uses round-to-nearest. The README (line 144) and module docstring (line 16-18) promise the interval "contains every possible result". | Directed rounding, or soften the claim. | `Interval(0.1,0.1)*3` → `[0.30000000000000004, 0.30000000000000004]`; `0.3 in` that interval → **False**. |
| 14 | LOW | `units.py:87-114, 144-157, 166-173` | Every `to_*` converter passes **NaN and inf** straight through. `charge_uC` validates **nothing** — a negative or zero pulse width silently returns a charge — while its inverse `current_uA_from_charge` *does* guard (asymmetric), and that guard is itself NaN-blind. `celsius_to_kelvin(-300)` → −26.85 K. | Finite/positive guards, symmetric across the pair. | `charge_uC(100, -200)` → **−0.02 uC**; `charge_uC(nan,200)` → **nan**; `current_uA_from_charge(1, nan)` → **nan**; `to_uA(inf,'uA')` → **inf**. Mitigation: `StimProtocol` **does** reject non-finite/non-positive current and pulse width, so this is reachable only via the direct function API. |
| 15 | LOW | `geometry/arrays.py:110-112, 136-139` | `pitch_um <= 0` is NaN-blind. Coincident sites are accepted. | Finite check; reject zero pitch between distinct sites. | `linear_array(disc, 3, nan).min_pitch_um()` → **nan**. Two sites at the same coordinates → `min_pitch_um()` → **0.0**. |
| 16 | LOW | `geometry/volumetric.py:82-103` | `cone_height_um` is **silently ignored** when `tip_shape` is `flat` or `hemispherical`. | Reject the contradictory combination. | `MicrowireElectrode(50, 0, "flat", 999999.).area_um2` == `MicrowireElectrode(50, 0, "flat").area_um2` == **1963.4954**. |
| 17 | LOW | `materials.py:294-298` | `Material.verified` checks `cic.verified` and `water_window.verified` but **not** `chronic_threshold` — which has no `verified` field at all. | Add the field, include it in the roll-up. | `ChronicThreshold` dataclass (`materials.py:244-266`) has no `verified`. |
| 18 | LOW | `uncertainty.py:56-61` | `from_mean_sd(mean, sd, k)` accepts `sd = inf` → `[-inf, inf]`, and a **negative k** raises a misleading message about bound ordering rather than about `k`. | Guard `k >= 0` and finite `sd`. | `from_mean_sd(1, inf)` → `Interval(-inf, inf)`. `from_mean_sd(1, 0.5, -2)` → `ValueError: Interval high (0.0) must be >= low (2.0)`. |

---

## 2. Areas and access resistances — derivations, then comparison

Each formula was derived independently before reading the code; `g1_areas.py` then compared the
two to `rel_tol = 1e-12`. **All twelve matched.**

| Geometry | Hand derivation | Code | file:line | Verdict |
|---|---|---|---|---|
| Disc | `A = pi*r^2`, exposed face only | `math.pi * radius_um**2` | `planar.py:38` | ✔ |
| Ring / annulus | `A = pi*(r_o^2 - r_i^2)` | `math.pi * (ro**2 - ri**2)` | `planar.py:84-86` | ✔ — **not** a circumference mistake. The circumference error would give `2*pi*r_o = 628 um` where the code correctly gives `23 561.94 um²`. |
| Rectangle | `A = w*l` | `width_um * length_um` | `planar.py:119` | ✔ |
| Cylindrical band | lateral only, `A = pi*d*h`; end caps excluded because the band sleeves an insulating shaft | `math.pi * diameter_um * height_um` | `volumetric.py:42` | ✔ and **documented** (`volumetric.py:22-24`). Adding end caps would give 0.08518 cm² instead of 0.05985 — **+42 %**, i.e. a 42 % inflation of every charge-density headroom. |
| Microwire shaft | `pi*d*L` | `math.pi * diameter_um * exposed_length_um` | `volumetric.py:113` | ✔ |
| Microwire flat tip | `pi*r^2` | `math.pi * r**2` | `volumetric.py:120` | ✔ |
| Microwire hemispherical tip | `2*pi*r^2` | `2.0 * math.pi * r**2` | `volumetric.py:122` | ✔ |
| Microwire conical tip | lateral cone `pi*r*s`, **slant** `s = sqrt(r^2 + h^2)` | `slant = math.sqrt(r**2 + cone_height_um**2); math.pi * r * slant` | `volumetric.py:125-126` | ✔ — **the slant is computed, not the height.** For r=25, h=100: slant **103.0776**, tip **8095.70 um²**; the height-for-slant mistake would give **7853.98 um²** (−3.0 %). Cone base is correctly *not* added (it joins the shaft). |
| Sphere | `4*pi*r^2` | `4.0 * math.pi * radius_um**2` | `volumetric.py:168` | ✔ |
| Hemisphere | `2*pi*r^2` | `2.0 * math.pi * radius_um**2` | `volumetric.py:203` | ✔ — **hemisphere is 2πr², not 4πr².** Measured ratio hemi/sphere = **0.5** exactly. |
| Disc R_access | Newman half-space `R = 1/(4*sigma*a) = rho/(4a)` | `1.0/(4.0*sigma*um_to_m(radius_um))` | `planar.py:40-42` | ✔ exact, correctly flagged `is_exact = True` |
| Sphere R_access | full space `1/(4*pi*sigma*a)` | same | `volumetric.py:170-172` | ✔ exact |
| Hemisphere R_access | half space `1/(2*pi*sigma*a)` | same | `volumetric.py:205-207` | ✔ exact. Measured hemi/sphere R ratio = **2.0** exactly, matching "half the area, twice the resistance". |

### Newman reuse — who inherits it and is the error bounded?

`Electrode.access_resistance_ohm` (`base.py:63-75`) substitutes an equal-area disc and applies
`1/(4*sigma*a_eq)`. It is inherited, unoverridden, by **Ring, Rectangle, CylindricalBand and
Microwire**. `access_resistance_is_exact` correctly returns `False` for all four, so the
*approximation* is flagged. What is **not** bounded or correctly documented:

**(a) Planar cases (Ring, Rectangle) — the documented error direction is backwards (findings #5, #6).**

Exact check used: the elliptic disc. Via the electrostatic analogy `R_halfspace = 2*eps0/(sigma*C)`
and `C_ellipse = 4*pi*eps0*a/K(e)`, so

```
R_ellipse(half-space) = K(e) / (2*pi*sigma*a_major),    e = sqrt(1 - (b/a)^2)
```

Validation of the identity: `K(0)/(2*pi) = 0.2500000000`, reproducing Newman's `1/(4*sigma*a)`
in the circular limit, and the code agrees at aspect 1.0 to 3 decimals (7142.9 Ω both ways).

```
aspect  1: R_true=7142.9  R_equal-area-disc=7142.9   ratio 1.000
aspect  2: R_true=6934.1  R_equal-area-disc=7142.9   ratio 1.030
aspect  5: R_true=6133.6  R_equal-area-disc=7142.9   ratio 1.165
aspect 10: R_true=5314.2  R_equal-area-disc=7142.9   ratio 1.344
aspect 50: R_true=3407.5  R_equal-area-disc=7142.9   ratio 2.096
```

Thin annulus (thin-ring capacitance `C = 2*pi^2*eps0*D/ln(8D/d)`), b = 100 um:

```
w/b=0.50: R_eq= 8247.9  R_ring~ 6019.8   -> 1.37x too high
w/b=0.20: R_eq=11904.8  R_ring~ 7346.0   -> 1.62x too high
w/b=0.05: R_eq=22875.5  R_ring~ 9352.6   -> 2.45x too high
w/b=0.01: R_eq=50634.4  R_ring~11682.2   -> 4.33x too high
```

Physical reason the docstrings get the sign wrong: spreading resistance is set by the electrode's
**largest linear dimension**, not by `sqrt(area)`. Elongating a shape at fixed area *increases* its
largest dimension and therefore *lowers* R. The disc is the most compact planar shape of a given
area and hence the most resistive one. The substitution is therefore an **upper bound** on R for
any planar electrode — conservative for compliance voltage, but the code tells the reader the
opposite, and a reader adding margin in the stated direction would double-count.

**(b) Immersed 3-D cases (Band, Microwire) — a half-space result applied to a full-space problem
(finding #7).**

`1/(4*sigma*a)` is the resistance of a disc backed by an **insulator**, with current confined to
2π steradians. A DBS band and a microwire tip are surrounded by tissue on all sides (4π). The
resulting bias is exactly `pi/2` relative to the equal-area sphere, for **every** immersed
geometry, because `a_disc/a_sphere = sqrt(A/pi)/sqrt(A/4pi) = 2`:

```
R_disc/R_sphere = [1/(4*sigma*a_d)] / [1/(4*pi*sigma*a_s)] = pi*a_s/a_d = pi/2 = 1.5708
```

Measured: DBS band 517.5 / 329.5 = **1.571**; microwire 4408.7 / 2806.6 = **1.571**. Against a
sharper microwire reference (thin cylinder in full space, `ln(2L/r)/(2*pi*sigma*L)` = 3354.9 Ω)
the code is **1.31x** high. Direction is conservative for compliance voltage; the point is that a
`pi/2` systematic offset is reported as a shape approximation rather than a coordinate-system one.

A side effect worth naming: `equivalent_radius_um` for the DBS band is **1380 um**, larger than
the lead's physical radius of 635 um. That radius is also the characteristic length the field
model falls back on (`base.py:52-59`).

---

## 3. Arrays — superposition and current sharing (task item 2)

**Field superposition IS implemented and IS caveated** — not a silent omission.
`models/field.py:211-250` sums point-source potentials per site, validates the current vector
length (`strict=True` zip), rejects coincident field points, and states the breakdown condition:
"it assumes each site behaves as an independent point source. That breaks down when sites are
close relative to their size, because the presence of a neighbouring conductor redistributes
current."

**Current sharing on the safety side is silently absent (finding #9).** `arrays.py:4-6` claims the
module models "the caution that simultaneous stimulation on neighbouring sites does not simply
share charge in proportion to area". `grep -rn "sharing\|simultaneous"` across the package hits
**only that docstring** — no warning is ever emitted, no check consumes an `ElectrodeArray`, and
`SafetyCalculator` accepts a single `Electrode`. Meanwhile `total_area_cm2` and `mean_area_cm2`
are public and unguarded, and dividing a total charge by a total array area is precisely the
proportional-sharing assumption the docstring says is wrong. A promised safeguard that does not
exist is worse than an absent one, because the docstring invites reliance on it.

Array adversarial results (`g5_adv.py`):

```
ElectrodeArray(())              -> ValueError: An ElectrodeArray needs at least one site   [good]
1-site array min_pitch          -> inf, rendered "n/a" in describe()                       [good]
linear_array n=0                -> ValueError                                              [good]
linear_array pitch=0            -> ValueError                                              [good]
grid 0x0                        -> ValueError                                              [good]
linear_array pitch=nan          -> min_pitch nan                                           [finding #15]
two COINCIDENT sites            -> min_pitch 0.0, accepted                                 [finding #15]
100 coincident sites            -> total_area_cm2 0.001963, accepted                       [finding #9/#15]
```

---

## 4. units.py — every factor re-derived (task item 3)

All **26** conversion factors across the 6 tables were re-derived by hand and compared
(`g7_units.py`). **Zero mismatches, zero missing or extra keys.**

```
CHARGE_TO_UC            C 1e6   mC 1e3   uC 1     nC 1e-3   pC 1e-6        all OK
CURRENT_TO_UA           A 1e6   mA 1e3   uA 1     nA 1e-3                  all OK
TIME_TO_US              s 1e6   ms 1e3   us 1     ns 1e-3                  all OK
LENGTH_TO_UM            m 1e6   cm 1e4   mm 1e3   um 1      nm 1e-3        all OK
AREA_TO_CM2             m2 1e4  cm2 1    mm2 1e-2 um2 1e-8  nm2 1e-14      all OK
CHARGE_DENSITY_TO_UC_CM2  C/cm2 1e6  mC/cm2 1e3  uC/cm2 1  nC/cm2 1e-3
                          uC/mm2 1e2  mC/mm2 1e5                           all OK
```

Spot-checks of the two that are easiest to get wrong:
- `um2 -> cm2 = 1e-8`: 1 um = 1e-4 cm, squared = **1e-8** ✔ (matches `um2_to_cm2`, `units.py:121`).
- `nm2 -> cm2 = 1e-14`: 1 nm = 1e-7 cm, squared = **1e-14** ✔.
- `uC/mm2 -> uC/cm2 = 100`: 1 mm² = 0.01 cm², so 1 uC/mm² = **100 uC/cm²** ✔.
- `charge_uC`: 1 uA × 1 us = 1e-6 A × 1e-6 s = 1e-12 C = **1e-6 uC** ✔ (`units.py:150`). The
  docstring at `units.py:147` is garbled ("uA*us = picocoulomb*1e6… explicitly:") but the code and
  the second sentence are right.

**mC/cm² ↔ uC/cm² round-trip drift** (`uC_cm2_to_mC_cm2 ∘ mC_cm2_to_uC_cm2` and the reverse):
`0.0` for v ∈ {1.0, 1e9, 0.1}; `+2.07e-25` at v=1e-9; `+1.42e-14` at v=123.456. Pure float
representation noise, ~1 ulp — **no systematic drift**. `charge_uC ∘ current_uA_from_charge`
round-trips to 0 drift except the same 1.42e-14 at v=123.456.

**S/m ↔ S/cm (task item 3):** there is **no such conversion function, and none is needed** —
`grep -rn "S_per_cm\|S/cm\|ohm.cm\|ohm_cm" neurostim/` returns only two **free-text medium
strings** in `materials.py:448` ("80 ohm.cm") and `materials.py:608` ("300 ohm.cm"), which are
never parsed or converted. Every conductivity in code is named `sigma_S_per_m` and is S/m
throughout. No unit ambiguity found on this axis.

**Bare floats where the unit is ambiguous:** none found in `units.py` — every public converter
takes an explicit `unit` string, and the round-trip helpers encode both units in their names
(`um2_to_cm2`, `mC_cm2_to_uC_cm2`, `um_to_m`). Unknown unit strings raise with the supported list.
The converters are, however, **whitespace- and case-sensitive** and reject `'cm^2'` / `'uC/cm^2'`
spellings — a usability edge, not a correctness one, and it fails loudly:

```
to_uA(1,'mA ')     -> ValueError: Unknown current unit 'mA '
to_uA(1,'MA')      -> ValueError: Unknown current unit 'MA'
to_cm2(1,'cm^2')   -> ValueError: Unknown area unit 'cm^2'
```

The one real gap is non-finite pass-through and the asymmetric `charge_uC` guard — finding #14.

---

## 5. uncertainty.py — is the interval arithmetic SOUND? (task item 4)

**Verdict: sound for every path the package actually ships; not sound as a general-purpose
interval library, and the README's containment guarantee is broader than the implementation.**

### 5.1 The shipped paths are sound — verified exhaustively

There are exactly **three** places in the package that do interval arithmetic:

| Call site | Expression | Monotone? | Variable reused? |
|---|---|---|---|
| `safety/charge.py:245-248` | `Interval(lo*scale/derating, hi*scale/derating) * area_cm2 / (pw*1e-6)` | yes (positive scalars) | **no** — `limit_interval` appears once |
| `safety/shannon.py:311-314` | `Interval(f(k_lo), f(k_hi))` with `f = sqrt(A*10^k)/(pw*1e-6)` | yes, strictly increasing in `k` | **no** — endpoint evaluation is valid here |
| `safety/assessment.py:145-156` | `most_restrictive([shannon_iv, charge_iv, exact(compliance)])` | elementwise `min` | **no** |

`most_restrictive` is the interval extension of `min` and is **provably correct**: for independent
`a ∈ A`, `b ∈ B`, the range of `min(a,b)` is `[min(A.lo,B.lo), min(A.hi,B.hi)]`. Brute-forced over
a 501×501 grid: `most_restrictive([[100,500],[200,300]])` → `[100, 300]`; brute-force range of
`min(a,b)` → `[100.000, 300.000]`. ✔ It also cannot produce a reversed interval: for
`j = argmin(highs)`, `min(lows) <= lo_j <= hi_j = min(highs)`.

The module docstring's claim at `uncertainty.py:23-25` — "Nothing here subtracts an interval from
itself" — **holds**: I traced all three sites and none subtracts, divides, or otherwise reuses one
interval variable. The **dependency problem is therefore not live** in any user-facing number.

### 5.2 Multiplication / division across zero — correct

Corner evaluation is *exact* for `*` (bilinear → extrema at corners) and for `/` once the divisor
is known not to span zero. Brute-forced over 201×201 grids:

```
(-2,3)*(-5,7)  -> [-15,21]   brute [-15.0000, 21.0000]   contained=True
(-2,-1)*(3,4)  -> [-8,-3]    brute [-8.0000, -3.0000]    contained=True
(-2,3)*(-2,3)  -> [-6,9]     brute [-6.0000,  9.0000]    contained=True   (as a PRODUCT of two
                                                                            independent vars)
```

Division by an interval containing zero is **correctly rejected in every form**, including the
open-ended and scalar cases:

```
[1,2]/[-1,1]  -> ZeroDivisionError   [1,2]/[0,1] -> ZeroDivisionError
[1,2]/[-1,0]  -> ZeroDivisionError   [1,2]/0.0   -> ZeroDivisionError
[1,2]/[-2,-1] -> [-2.0,-0.5]   (all-negative divisor, correct)
1.0/[-2,-1]   -> [-1.0,-0.5]   (__rtruediv__, correct)
```

### 5.3 NON-MONOTONIC maps — the square, and the Shannon `k` path (finding #10)

`Interval` has **no** non-monotonic operation at all:

```
Interval.__pow__ ABSENT   .log10 ABSENT   .log ABSENT   .exp ABSENT   .square ABSENT   .__abs__ ABSENT
```

So `k = log10(Q^2/A)` **cannot currently be evaluated on intervals** — `shannon_k`
(`safety/shannon.py:193-216`) takes bare floats and guards them positive and finite. The exact path
named in the brief is therefore *latent*, not live. But the trap is laid: with no `__pow__`, the
natural way to square is `I*I`, and `_binary` treats the two occurrences as independent:

```
I=(-2,3):  I*I = [-6, 9]   TRUE range of x^2 = [0, 9]        SPURIOUS + IMPOSSIBLE (negative)
I=(-1,1):  I*I = [-1, 1]   TRUE range of x^2 = [0, 1]        SPURIOUS + IMPOSSIBLE
I=(-3,-1): I*I = [1, 9]    TRUE [1, 9]                       ok (interval does not span 0)
I=(1,2):   I*I = [1, 4]    TRUE [1, 4]                       ok
math.log10(Interval(-2,3)*Interval(-2,3)).low  ->  ValueError: expected a positive input
```

The correct extension needs the interior extremum at `x = 0`:
`sq([lo,hi]) = [0, max(lo^2,hi^2)]` when `lo <= 0 <= hi`, else the endpoint square.

Mitigating fact: charge per phase is physically positive, so a *realistic* `Q` interval never spans
zero and `I*I` would happen to be right. The defect is that nothing enforces or documents that
precondition, and `sqrt()` (the one non-linear method that exists, `uncertainty.py:147-151`) does
guard its domain — so the inconsistency is visible in the module itself.

### 5.4 The dependency problem — measured

```
x = [71, 212]
x - x    -> [-141, 141]      (true answer: exactly 0)
x / x    -> [0.3349, 2.986]  (true answer: exactly 1)
x*2 - x  -> [-70, 353]       (true answer: [71, 212])
```

As above, no shipped expression triggers this. It is a hazard for the next contributor, and the
module docstring already warns about it — correctly.

### 5.5 Degenerate, reversed and NaN intervals — well handled

```
Interval(2,1)          -> ValueError: Interval high (1) must be >= low (2)     [good]
Interval(nan,1)        -> ValueError: bounds must not be NaN                   [good]
Interval(1,nan)        -> ValueError: bounds must not be NaN                   [good]
Interval.exact(nan)    -> ValueError                                           [good]
Interval(-inf,inf)     -> ACCEPTED                                             [finding #18]
from_mean_sd(1,nan)    -> ValueError                                           [good]
from_mean_sd(1,inf)    -> Interval(-inf, inf)                                  [finding #18]
from_mean_sd(1,.5,-2)  -> ValueError, but the message blames the bounds, not k [finding #18]
combine([]) / intersect([]) / most_restrictive([])  -> ValueError each         [good]
intersect([[1,2],[5,6]]) -> None  (caller must handle; no caller exists today) [ok]
```

Degenerate (exact) intervals are first-class: `is_exact`, and `describe()` collapses them to one
number. `fold_range` returns `inf` for a zero low bound rather than dividing by zero.

### 5.6 Does the implementation deliver the README's guarantee?

README line 144: *"it assumes inputs can sit at their extremes simultaneously"*.

- **For the three shipped expressions: YES.** Each interval variable occurs once and every map is
  monotone, so corner evaluation is exactly the true range. The reported
  `limiting_current_interval_uA` genuinely contains every combination.
- **As a property of the `Interval` class: NO**, on two counts —
  (a) repeated use of one variable (§5.3, §5.4) returns a hull that is both too wide and, for a
  square, partly impossible; (b) **no outward rounding** (finding #13):
  `Interval(0.1,0.1)*3` → `[0.30000000000000004, 0.30000000000000004]`, which does **not** contain
  the exact decimal 0.3. A true containment guarantee requires directed rounding.

---

## 6. materials.py — CIC ranges, the measured override, and flag propagation (task item 5)

### 6.1 CIC values checked against the primary texts

| Material | Code | Primary text | Verdict |
|---|---|---|---|
| Pt / PtIr union | 0.05–0.15 mC/cm² | Rose & Robblee 1990 abstract: "charge injection limits of a Pt electrode using 0.2 ms charge balanced, biphasic current pulses ranged from **50 to 150** uC/cm²" (`txt/rose1990.txt:90-92`) | ✔ |
| Pt **anodic-first** | (0.05, 0.10) | "the charge injection limit for anodic-first pulses is about **50-100** uC/cm² geom" (`txt/rose1990.txt:200-201`) | ✔ |
| Pt **cathodic-first** | (0.10, 0.15) | "the charge injection limit for cathodic-first pulses is about **100-150** uC/cm²" (`txt/rose1990.txt:201-202`) | ✔ |
| AIROF union | 1.0–3.5 mC/cm² | Beebe & Rose 1988: "**2.1 and 1.0** mC/cm² geometric for anodic-first and cathodic-first, respectively, 0.2 ms balanced charge biphasic … up to **3.5** mC/cm² geometric with monophasic cathodal pulses" (`txt/beebe1988.txt:41-44`) | ✔ |
| AIROF anodic / cathodic | (2.1, 2.1) / (1.0, 1.0) | same | ✔ |

**On the prior run's correction.** Confirmed and quantified. `StimProtocol` defaults to
**cathodic-first** (the assessment header prints "biphasic cathodic-first"), and
`MeasuredRange.bounds(anodic_first=False)` selects the polarity sub-range. For Pt this **narrows
0.05–0.15 to 0.10–0.15**, which *raises* the conservative limit from 50 to **100 uC/cm²** — i.e.
cathodic-first is the **more permissive** polarity for platinum. Note the opposite sign for AIROF
(cathodic-first 1.0 vs anodic-first 2.1 mC/cm²) and for 316LVM corrosion, where cathodic-first is
the one that pitted. Any brute force over CIC ranges must therefore select the polarity sub-range
per material rather than applying one direction globally.

Unit handling: `cic_uC_cm2` (`materials.py:300-309`) converts `mC/cm2 → uC/cm2` by `×1e3` and
raises on any other unit string. All nine shipped materials use `mC/cm2`; all nine convert
correctly and all report `verified=True`:

```
Pt       50.0-150.0   PtIr     50.0-150.0   AIROF   1000.0-3500.0
SIROF  1000.0-5000.0  TIROF  1000.0-1000.0  TiN     1000.0-1000.0
PEDOT  2300.0-3600.0  Ta2O5     88.0-150.0  SS316LVM  20.0-40.0   (uC/cm^2)
```

### 6.2 `with_measured_cic` — what it gets right

- Rebuilds `MeasuredRange` from scratch, so the published `anodic_first_range` /
  `cathodic_first_range` are correctly **cleared to None** (confirmed) — the user's number is not
  silently re-split by a polarity the user never measured.
- Sets `verified=False` and `reference="user_measurement"`; `describe()` renders both
  "(your measurement, not published literature)" and "**PROVISIONAL**".
- `low_uC_cm2 * 1e-3` is the correct uC/cm² → mC/cm² conversion; `cic_uC_cm2` round-trips it back
  to the input (500 in → 500 out).
- Rejects `low <= 0`, negative and NaN `low`; rejects `high < low`.
- The flag **survives a second override** (`verified` still False, reference still
  `user_measurement`).
- `Material.verified` goes False, and `ChargeResult.verified` is False.

### 6.3 `with_measured_cic` — what it gets wrong (findings #4, #11, #12)

1. **The unverified number silently loosens the water-window check, with no flag on that result**
   (finding #4, HIGH). `safety/water_window.py:75` derives the interfacial capacitance from
   `mat.cic_uC_cm2("optimistic", …)` — note it hardcodes the **optimistic** end regardless of the
   assessment's `policy`. Measured end to end:

   ```
   published Pt  -> C_dl 250.0 uF/cm^2, excursion 0.004074 V, headroom +0.596 V, PASS
   user 500      -> C_dl 833.3 uF/cm^2, excursion 0.001222 V, headroom +0.599 V, PASS
   "PROVISIONAL" in water_window.describe() -> False   (both cases)
   ```
   A 5x unverified CIC bought a 3.3x larger modelled capacitance and a 3.3x smaller predicted
   polarisation — the check got *easier to pass* on the strength of an unverified input, and
   nothing on that result says so.

2. **NaN bounds are accepted** (finding #11). `MeasuredRange.__post_init__` tests `high < low`,
   which is False for NaN:
   ```
   with_measured_cic(Pt, 100, high=nan).cic_uC_cm2("optimistic") -> nan
   with_measured_cic(Pt, 100, high=nan).cic_uC_cm2("nominal")    -> nan
   with_measured_cic(Pt, 100, high=inf).cic_uC_cm2("optimistic") -> inf
   MeasuredRange(1.0, nan, ...)  and  MeasuredRange(nan, 1.0, ...)  both construct
   MeasuredRange(-5.0, 1.0, ...).value("conservative")           -> -5.0   (no positivity check)
   ```
   `high_uC_cm2` gets none of the `math.isfinite` / `> 0` checking that `low_uC_cm2` gets.

3. **The other constants carry over with their original citations** (finding #12). Only `cic` is
   replaced; `water_window`, `chronic_threshold` and `note` survive. In the assessment for a
   user-measured material the report still prints:
   ```
   [PASS] Chronic degradation: 1.019 uC/cm^2 is below the 20 uC/cm^2 platinum dissolution threshold
       20-50 uC/cm^2 (platinum dissolution, rose_robblee1990) -- Rose & Robblee report ...
   ```
   The docstring says the function exists so that "displaying a published reference next to a
   number that did not come from that paper would misattribute your measurement" — that protection
   is applied to the CIC line and to nothing else.

### 6.4 Does the flag reach every downstream result and report?

| Surface | Carries the flag? |
|---|---|
| `Material.verified`, `MeasuredRange.verified` | ✔ False |
| `MeasuredRange.describe()` | ✔ "PROVISIONAL" + "(your measurement, not published literature)" |
| `ChargeResult.verified` | ✔ False |
| `SafetyAssessment.describe()` | ✔ "PROVISIONAL" ×2 |
| PDF via `io/report.py` | ✔ but **only as prose** — `build_report` embeds `assessment.describe()` text; `grep PROVISIONAL\|verified` over `io/report.py`, `io/tabular.py`, `gui/app.py` finds **no structured field**, only the `user_measurement` bibliography skip at `io/report.py:92`. |
| `WaterWindowResult` | ✘ **no flag** (finding #4) |
| `ChronicThreshold` | ✘ has no `verified` field at all (finding #17) |

---

## 7. Adversarial input battery — full results

`g5_adv.py`. **Geometry validation is the strongest part of this package**: 24 of 27 hostile
constructions raise a clear, specific `ValueError`.

```
RAISED CLEANLY (good):
  Ring(100,200) r_in>r_out   -> "inner_diameter_um (200.0 um) must be smaller than outer_diameter_um (100.0 um)"
  Ring(100,100) zero area    -> same message
  Ring(100,-50)              -> "inner_diameter_um must be a finite value >= 0"
  Ring(nan,50) / Ring(inf,50)-> "outer_diameter_um must be finite"
  Disc(0) / Disc(-10) / Disc(nan) / Disc(inf)
  Rect(0,10) / Rect(-1,10)
  Band(1270,0) / Band(-1,1)
  MW conical h=0             -> "cone_height_um must be > 0 um"
  MW conical h=None          -> "cone_height_um is required when tip_shape='conical'"
  MW conical h=-5 / nan / inf
  MW exposed_length = -5 / nan / inf
  MW tip_shape='HEMISPHERICAL' (case)  -> lists the three legal values
  access_resistance(sigma = 0 / -1 / nan)  on Disc, Band and the base class
  ElectrodeArray(()) ; linear_array n=0 ; linear_array pitch=0 ; grid_array 0x0

RETURNED A NUMBER INSTEAD OF RAISING:
  Ring(100, 0)                          -> 7853.98 um^2   [correct: a zero-bore ring IS a disc]
  MicrowireElectrode(50, 0, "flat")     -> 1963.50 um^2   [correct: documented as a disc, allowed]
  MicrowireElectrode(50,0,"flat",1e6)   -> 1963.50 um^2   [finding #16: cone_height silently ignored]
  linear_array(disc, 3, pitch=nan)      -> min_pitch nan  [finding #15]
  two coincident ArraySites             -> min_pitch 0.0  [finding #15]
  100 coincident sites total_area_cm2   -> 0.001963       [finding #9]
  MeasuredRange(1.0, nan) / (nan, 1.0)  -> constructs     [finding #11]
  MeasuredRange(-5.0, 1.0).value()      -> -5.0           [finding #11]
  with_measured_cic(Pt,100,high=nan)    -> nan limits     [finding #11]
  with_measured_cic(Pt,100,high=inf)    -> inf limit      [finding #11]
  to_uA(nan,'uA') / to_uA(inf,'uA')     -> nan / inf      [finding #14]
  charge_uC(nan,200)                    -> nan            [finding #14]
  charge_uC(100, -200)                  -> -0.02 uC       [finding #14]
  charge_uC(100, 0)                     -> 0.0            [finding #14]
  current_uA_from_charge(1, nan)        -> nan            [finding #14]
  celsius_to_kelvin(-300)               -> -26.85 K       [finding #14]
  Interval(-inf, inf) ; from_mean_sd(1, inf)              [finding #18]
  Interval(-2,3) * Interval(-2,3)       -> [-6,9]         [finding #10]
```

`StimProtocol` independently rejects non-finite / non-positive current and pulse width, so the
`units.py` gaps are only reachable through the direct function API, not through an assessment.

---

## 8. Electrode presets — areas cross-checked against their own stated values

`gd_presets.py`. **All ten match**, which also confirms the disc and band area formulas against
numbers taken from the papers:

```
dbs_3389 / dbs_3387   Band 1270x1500  -> 0.059847 cm^2   stated 0.06    OK (Cogan Table 1 fn b)
dbs_kuncel            Band 1260x1500  -> 0.059376 cm^2   (1.26 x 1.5 mm)
mccreery_surface_smallest  Disc 1128.4 -> 0.010000 cm^2  stated 0.01    OK
mccreery_surface_largest   Disc 7978.8 -> 0.499990 cm^2  stated 0.5     OK
mccreery_microelectrode    Disc 91.0   -> 6.5039e-05     stated 6.5e-5  OK
mccreery2010_chronic       Disc 50.5   -> 2.003e-05      stated 2000 um^2 OK
rose_robblee_typeA         Disc 1100   -> 9.5033e-03     stated 9.5e-3  OK
beebe_iridium_wire         Disc 228.4  -> 4.0972e-04     stated 4.1e-4  OK
weiland_tin                Disc 71.4   -> 4.0039e-05     stated 4000 um^2 OK
```

The one problem is the `(exact)` label on the substituted discs (finding #8):

```
mccreery_microelectrode  Disc [AIROF] 91 um   -> R_access 15699 ohm (exact)
beebe_iridium_wire       Disc [AIROF] 228.4   -> R_access  6255 ohm (exact)
mccreery2010_chronic     Disc [AIROF] 50.5    -> R_access 28289 ohm (exact)
```

None of these three is a disc flush in an insulating plane. The first is "a 75 um iridium wire
ground to a conical point with an ellipsoidal facet … at 45 degrees to the shaft" (the preset's own
`context`); the second is a wire in saline; the third is a penetrating microelectrode. Newman's
result does not apply to any of them, yet `describe()` asserts exactness because
`access_resistance_is_exact` is a property of the *class*, not of the modelling choice. The band
presets correctly print "(equal-area disc approx.)".

Also note the beebe preset's R is computed at the package default 0.35 S/m while its own material
record states the measurement medium was "80 ohm.cm". Converting: 1/80 = 0.0125 S/cm = **1.25 S/m**,
i.e. **3.6x** the package default, so that preset's quoted access resistance is ~3.6x the value in
the medium it was actually measured in. (Ta2O5's "300 ohm.cm" converts to 0.333 S/m, which happens
to sit within 5 % of the default.) These strings are free text and are never parsed — see §4.

---

## 9. What I checked and found correct

Recorded so this is not re-audited:

- All 12 area / access-resistance closed forms (§2) — exact to machine precision.
- Annulus is `pi*(ro^2 - ri^2)`, **not** a circumference.
- Conical tip uses the **computed slant height**, not the cone height.
- Hemisphere is `2*pi*r^2` and sphere `4*pi*r^2`; hemisphere R is exactly 2x sphere R.
- Band excludes end caps, and the choice is documented and correct for a sleeve on an insulating
  shaft (including them would inflate area 42 %).
- Band area reproduces Cogan's 0.06 cm² for a clinical DBS contact (0.059847).
- `equivalent_radius_um = sqrt(A/pi)` is the correct equal-area disc radius.
- All 26 unit conversion factors; no S/m ↔ S/cm ambiguity exists in the package.
- Pt and AIROF CIC ranges and their polarity sub-ranges, against the primary texts.
- `most_restrictive`, `combine`, `intersect` — sound, and `most_restrictive` cannot return a
  reversed interval.
- Corner evaluation for `*` and `/`, and rejection of every zero-spanning divisor.
- The claim "nothing here subtracts an interval from itself" — verified across all three call sites.
- Reversed-bound and NaN-bound `Interval` construction is rejected.
- Field **superposition** in `models/field.py` is implemented, validated and correctly caveated.
- The disc primary-distribution formula itself (`0.5/sqrt(1-(r/a)^2)`) and its 25 %-of-area
  corollary (`J/J_avg > 1 ⟺ r/a > sqrt(3)/2 ⟺ 1 - 3/4 = 25 %`) are both correct — the defect is
  only that they are applied to non-disc geometries.
- Geometry constructor validation: 24 of 27 adversarial inputs rejected with specific messages.

---

## 10. Scope note

Findings #1, #2 and #3 sit in `models/field.py` and `safety/current_density.py`, which belong to the
models and safety-math auditors. They are reported here because both are **geometry-class dispatch**
bugs — `_geometry_factor` and the current-distribution text select behaviour by electrode type — and
because #2 is a direct contradiction between two files in my scope. Worth cross-checking with
`audit-models` / `audit-safety-math` before anyone edits.

`audit_safety_math.md` already exists in the scratchpad from a sibling agent; I did not read or
modify it, so overlapping findings there were reached independently.
