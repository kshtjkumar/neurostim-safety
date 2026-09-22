# Adversarial review of `docs/audit/FIX_PLAN.md` — physics and decisions

Read-only. No repo file modified. Every number below was produced by running code under
`./.venv/bin/python`; scripts are in
`$SCRATCH/p1_disc.py` … `$SCRATCH/p13.py`. Primary sources read from
`$SCRATCH/txt/*.txt`.

The plan is competent and most of it survives. Five things in it will produce a wrong
result if executed as written, and four of the five are in section 0, where everything
downstream inherits them.

---

## BLOCKERS

### B1 — §0 D4 / §2 C3.1 / §4 R2: the T5 invariant is false for six of seven geometries, and its stated failure magnitude is wrong

**The claim.** D4: "the invariant `V(r=a) == I·R_access` (T5) is what proves both halves
consistent." C3.1: "`potential_V(100, el.equivalent_radius_um, 0.35, electrode=el) ≈
100e-6 × el.access_resistance_ohm(0.35)` for Disc, Ring, Rectangular; **fails by exactly
2× today**. Extend to band/microwire/sphere." R2: "the excess factor is currently exactly
2.0000 and **must become exactly 1.0000**."

**The error.** Newman's `1/(4σa)` is the resistance of an *equipotential* disc — its
surface potential is uniform at `V0 = I·R`. The point-source formula is the disc's
*asymptotic far field*, and it is simply not the disc's potential at `r = a`. The exact
half-space disc solution is `V(r) = (2V0/π)·arcsin(a/r)`, which I checked against both
ends:

```
r/a=  1.0  V_exact=142.857 mV   V_pointsrc(2π)= 90.946 mV   ratio 0.636620 (=2/π)
r/a=  2.0  V_exact= 47.619     V_pointsrc(2π)= 45.473       ratio 0.954930
r/a=100.0  V_exact=  0.90947   V_pointsrc(2π)=  0.90946     ratio 0.999983
V_exact(a) = 142.857 mV  ==  I·R = 142.857 mV     (exactly)
```

So the 2π point source is the **correct** far field (ratio → 1), and `I·R / V_pointsrc(a)
= π/2` is a permanent, physically correct residual, not a bug. Measured across the class
hierarchy (`p1_disc.py`):

| geometry | `I·R / V(a)` today (4π) | after D4's space fix | true invariant? |
|---|---|---|---|
| Disc | 3.14159 | **1.57080** | no — off by π/2 |
| Ring | 3.14159 | **1.57080** | no |
| Rectangular | 3.14159 | **1.57080** | no |
| Hemispherical | 2.82843 | **1.41421** | no — off by √2 |
| Spherical | 2.00000 (4π) | **2.00000** | no |
| CylindricalBand | 3.14159 | arbitrary | no |
| Microwire | 3.14159 | arbitrary | no |

Two independent defects are stacked here.

1. **The invariant only holds for sphere and hemisphere**, and only when the field is
   evaluated at the *physical* radius. The plan evaluates at `el.equivalent_radius_um`,
   which is the **equal-area disc radius** — for a sphere that is `2r`, for a hemisphere
   `r√2`. That is why the two geometries where the physics *is* exact come out at 2.000
   and 1.414 above. So T5 fails for **every** geometry including the two it should pass.
2. **"fails by exactly 2× today" is wrong** — it fails by π (3.14159) for the planar
   geometries. The plan has read the geometry audit's decomposition ("the legitimate
   disc-vs-sphere surface ratio is π/2; the excess factor is exactly 2") and turned the
   *excess* into the *total*. R2 then names double-correcting as the failure mode to
   avoid and commits it in the same paragraph: enforcing `→ 1.0000` demands the removal
   of a π/2 that the audit had already identified as legitimate.

**What breaks if it is enforced.** T5 is the *only* stated proof of correctness for
C3.1, the plan's second-highest-risk commit. A developer running it red will make it
green the only way available: change `DiscElectrode.access_resistance_ohm` from Newman's
exactly-correct `1/(4σa)` to `1/(2πσa)` — a 57 % reduction in every disc access
resistance, which propagates to compliance (`required_V`), the thermal source term, and
the Kuncel & Grill pin. That is a CRITICAL regression manufactured by a test.

**Correction.** Replace T5 with the two invariants that are actually true:

- *Surface identity* (sphere, hemisphere only, at the **physical** radius, not
  `equivalent_radius_um`): `potential_V(I, r_phys, σ, electrode=el) == I·R_access`, to
  machine precision.
- *Asymptotic identity* (every geometry): `potential_V(I, r, σ, electrode=el) /
  V_exact(r) → 1` as `r/a → ∞`; concretely, for the disc assert
  `V_ps(100a)/[(2/π)·I·R·arcsin(1/100)] == approx(1, rel=1e-4)`.
- For the disc specifically, pin the closed form the package should arguably ship:
  `V(r) = (2/π)·I·R_access·arcsin(a/r)`, which reduces to `I·R` at `r=a` and to the 2π
  point source at large `r`. That single function makes the "invariant" true by
  construction and removes the need for a cross-module fudge.

Keep D4's **space assignment** — 2π for flush planar, 4π for immersed. That half is
right, and the `22.7364 → 45.4728 mV` doubling in §3 is correct.

---

### B2 — §0 D4: the immersed-cylinder override is worse physics than the equal-area sphere it displaces, and it is non-monotonic

**The claim.** "`CylindricalBandElectrode` and the `MicrowireElectrode` shaft override
with the immersed-cylinder form `ln(2L/r)/(2πσL)` where `L/r ≥ 2`, falling back to the
equal-area sphere below that… for a clinical DBS band it gives 470.7 Ω against 329.5 Ω
for the sphere — the direction that is both physically right and closer to measured DBS
impedance."

**The test.** I solved the actual problem — an axisymmetric finite-volume Laplace solve
for a conducting band of height `h` on an *infinite insulating shaft* of radius `r₀`,
σ = 0.35 S/m, with grid and domain refinement (`p2_fd.py`). Converged to 0.1 %:

```
nr=300 Rmax/r0=300   R = 334.69 ohm
nr=500 Rmax/r0=1000  R = 334.55 ohm
nr=700 Rmax/r0=3000  R = 334.24 ohm      <- Medtronic-3389 band, d=1270 h=1500
```

Sweep against every candidate closed form:

```
aspect h/d   h_um   FD true    eq-disc    eq-sphere   ln(2L/r)   ln(2L/r)-1
     0.200    254     739.9     1257.6       800.6         n/a        n/a
     0.390    495     559.8      900.6       573.3       408.3        n/a
     0.500    635     502.2      795.4       506.4       496.4        n/a
     1.000   1270     363.7      562.4       358.1       496.4      138.3
     1.181   1500     335.1      517.5       329.5       470.7      167.6   <- clinical DBS
     2.000   2540     255.0      397.7       253.2       372.3      193.2
     4.000   5080     172.1      281.2       179.0       248.2      158.7
    10.000  12700      96.3      177.9       113.2       132.1       96.3
```

Findings, all contrary to the plan:

- **The equal-area sphere is within 2 % of truth** over aspect 0.39–2.0 (−1.7 % at the
  clinical DBS aspect) and within 18 % out to aspect 10. It is the best closed form the
  package could use, by a wide margin. The plan rejects it.
- **The plan's chosen form is 37–46 % high** over the entire range where its own `L/r ≥
  2` bound says it is valid (aspect ≥ 1.0). At the clinical DBS band it is +40.5 %.
- **The `L/r ≥ 2` bound is not derived and does not hold.** The formula is asymptotic in
  `ln(2L/r)`; at `L/r = 2` that logarithm is `ln 4 = 1.386`, so the neglected `O(1)` end
  correction is ~72 % of the retained term. The clinical DBS band sits at `L/r = 2.36` —
  just inside the claimed bound and in the formula's worst region.
- **The formula is non-monotonic in height.** `d/dh [ln(2h/r)/(2πσh)] = [1 −
  ln(2h/r)]/(2πσh²)`, zero at `h = e·r/2` (aspect 0.679). Above that it decreases,
  below it *increases with h* — a taller band with more area would be reported as more
  resistive. It returns **exactly 496.4 Ω for both aspect 0.5 and aspect 1.0**
  (`ln4/2 = ln2` exactly), so `access_resistance_ohm` becomes a two-to-one map. The FD
  column is strictly monotone decreasing, as it must be.
- **The fallback creates a step discontinuity.** At `L/r = 2` (aspect 1.0) the cylinder
  branch gives 496.4 Ω and the sphere branch 358.1 Ω — a 39 % jump in
  `access_resistance_ohm` across an infinitesimal change in `height_um`, which
  propagates straight into `required_V` and the compliance limit.
- **The end correction is missing.** For a full-space cylinder the standard result (the
  Dwight ground-rod formula, halved out of half-space) is `[ln(2L/r) − 1]/(2πσL)`. My FD
  confirms it: at aspect 10 (`L/r = 20`) it gives 96.3 Ω against an FD-true 96.3 Ω,
  exact. The plan's form omits the −1 and is 37 % high there.
- **The stated rationale is unsupported.** "Closer to measured DBS impedance" compares an
  access resistance against a clinical 1 kHz *electrode impedance*, which includes the
  interfacial and encapsulation terms this module deliberately models separately
  (`compliance.py` docstring says so explicitly). It is not a validation.
- **It contradicts the plan's own evidence.** Ledger 16 is the cylinder-form entry;
  ledger 20 is the equal-area-sphere entry and ends "**Supersedes and generalises defect
  16.**" D4 adopts the superseded entry as primary and demotes its successor to a
  fallback.

**Correction.** Use the equal-area sphere `1/(4πσa_sphere)` as the single full-space
form for band and microwire, flagged `access_resistance_is_exact = False`, with the
measured accuracy stated in the docstring ("within 2 % of a numerical solution for a band
on an insulating shaft at aspect ratios 0.4–2; degrades to ~18 % by aspect 10"). Keep
ledger 16 open as a documented limitation, or — if a long-thin form is wanted for the
microwire shaft — use `[ln(2L/r) − 1]/(2πσL)` and gate it at `L/r ≥ 20`, not 2, where I
measured it exact. Do not ship a non-monotonic resistance.

---

### B3 — §4 R2's second "independent published pin" does not test what the plan says, and goes red under D4 either way

**The claim.** "the existing `TestKuncelGrill2004::test_current_density_predicted_from_
geometry_and_voltage` reconstructs 0.0993 A/cm² through lateral area → Newman → Ohm to
2 % — it must still pass unchanged, **which it will only if the convention change is
consistent across both modules**."

**The error, twice over.**

*It is not a cross-module test.* The test body (`tests/test_published_cases.py:36`) is
`current_A = 3.0 / contact.access_resistance_ohm(0.35)`. It never calls `potential_V`
and never touches `_geometry_factor`. It constrains one module. It is structurally
incapable of detecting the double-correction R2 names as the failure mode.

*It fails under D4.* Measured (`p10_kg.py`), assertion is `rel=0.03`:

```
equal-area disc (today)            R= 519.6  J=0.09725  err  2.07%  PASS
equal-area sphere (D4 fallback)    R= 330.8  J=0.15275  err 53.83%  FAIL
plan cylinder ln(2L/r)             R= 473.1  J=0.10679  err  7.55%  FAIL
cylinder ln(2L/r)-1                R= 170.0  J=0.29728  err199.37%  FAIL
```

*And the pin itself is not what the test docstring claims.* Kuncel & Grill state grey
matter is 0.2 S/m and that "the impedance is estimated **conservatively to be 500 Ω**"
(`1-s2.0-S1388245704002287-main.txt:257-261`). Their 0.0993 A/cm² is `3 V / 500 Ω /
0.06 cm²` — back-solving their own numbers gives 503.5 Ω. It is an assumed clinical
impedance, not a FEM spreading resistance. Today's 2 % agreement is a coincidence of two
errors: the equal-area disc's +55 % bias evaluated at the wrong conductivity (0.35
instead of their 0.2) lands near their assumed 500 Ω. At **their** conductivity the
physics gives 586 Ω (FD) / 579 Ω (equal-area sphere) — mutually consistent to 1.5 %, and
17 % above their conservative estimate, which is the correct and reportable finding.

**Correction.** Do not cite this test as a guard on C3.1. Rewrite it to what it can
honestly assert — that at Kuncel & Grill's own stated 0.2 S/m the geometric access
resistance is 579 Ω against their conservatively assumed 500 Ω (+16 %) — and fix its
docstring, which currently attributes 0.0993 A/cm² to their finite element model. If a
cross-module guard is wanted, it must be the asymptotic invariant of B1.

---

### B4 — §2 C2.4 / §4 R4: T4 is unsatisfiable, and the fix makes monophasic protocols report a *more permissive* limit than biphasic

**The claim.** C2.4: for monophasic protocols the charge-injection and water-window
checks return `NOT_EVALUATED` and "their limits leave the `limiting_current_uA` candidate
set". Test T4: "`mono.limiting_current_uA < bi.limiting_current_uA`".

**The error is arithmetic.** Under D3 the reported limit is a **minimum over a candidate
set**. C2.4 **removes two candidates** from the monophasic set. Removing elements from a
minimum can never lower it. `min(S \ {a,b}) ≥ min(S)` for all `S`. T4 asserts the strict
opposite, so it can never pass, and the developer following the plan's "red on the test
alone, green after the fix" rule is stuck — with the only escape being exactly the
derating factor C2.4 forbids as "an unsourced number".

**It is worse than unsatisfiable: it is inverted.** Simulating C2.4 + D3 over a grid of
7 diameters × 9 materials × 6 pulse widths × 3 compliance settings (`p13.py`) found
**110 combinations where the monophasic reported limit is strictly higher than the
biphasic one**:

```
Disc d=150um SS316LVM pw=200us   biphasic 17.67 uA -> monophasic 20.00 uA   1.13x MORE permissive
Disc d=150um SS316LVM pw=100us   biphasic 35.34 uA -> monophasic 40.00 uA   1.13x
Disc d=150um SS316LVM pw= 30us   biphasic117.81 uA -> monophasic133.33 uA   1.13x
```

This is precisely the regression R4 was written to prevent, and R4's own mitigation (T4)
is the thing that fails. R4's second clause — assert `mono.status is Status.FAIL` — does
hold, because charge balance FAILs. But the *headline number* is the thing the plan calls
"the single most prominent number in every output", and it moves the wrong way.

**Correction.** Two changes, both needed:

1. Replace T4 with `mono.limiting_current_uA <= bi.limiting_current_uA` **and**
   `mono.status is Status.FAIL` **and** an explicit assertion that the monophasic
   assessment's `not_evaluated` tuple names the two dropped checks. Then add the real
   guard: `bi.limiting_current_uA` recomputed with the monophasic candidate set must
   equal `mono.limiting_current_uA`, so the removal is visible rather than silent.
2. Better: do not silently drop the candidates. Carry them as `NOT_EVALUATED` checks
   *and* make `limiting_current_uA` refuse to return a number when a limit-bearing check
   could not be evaluated for the protocol as given — return the value with an explicit
   `limits_incomplete` flag that `describe()`, the PDF and the JSON all render. A limit
   computed over a knowingly-incomplete candidate set is exactly the defect of ledger 1,
   reintroduced in a new place.

---

### B5 — §0 D5: pulse duty is not an envelope dimension; the new comparison both masks real excursions and fabricates false ones

**The claim.** "The envelope excursion compares pulse duty against the **fit protocol's
own** pulse duty, `2 × PULSE_WIDTH_US × FREQUENCY_HZ × 1e-6 = 0.04`."

**The arithmetic is right.** `2 × 400 × 50 × 1e-6 = 0.04`, and this matches
`StimProtocol.duty_cycle` for a symmetric biphasic pulse. McCreery 1990 confirms the fit
protocol: "pulsed continuously for 7 h using charge balanced, current regulated,
**symmetric pulse pairs, 400 µs per phase**, at a repetition rate of **50 Hz**"
(`mccreery1990.txt:20-27`). The plan's diagnosis of the original bug is also right:
McCreery 2010's duty is a train on/off schedule ("one second on, one second off",
`data/mccreery2010.py`), so comparing a pulse duty against it is a category error.

**The error is that the replacement comparison carries no information.** For a symmetric
biphasic pulse, `duty = 2·PW·f·1e-6`, so

```
duty_fold  =  duty / 0.04  =  (PW/400) · (f/50)  =  pw_fold · f_fold
```

exactly. The duty excursion is the **product of two excursions the envelope already
reports**. Measured (`p9_duty.py`):

```
 PW=  400 f=  50  duty_fold=1.000   pw_fold=1.00  f_fold=1.00
 PW=  100 f= 200  duty_fold=1.000   pw_fold=4.00  f_fold=4.00   <- reports "inside"
 PW=  800 f=  25  duty_fold=1.000   pw_fold=2.00  f_fold=2.00   <- reports "inside"
 PW=  600 f=  75  duty_fold=2.250   pw_fold=1.50  f_fold=1.50   <- reports "outside"
```

- **Masking.** 100 µs at 200 Hz is 4× outside the fit on pulse width and 4× outside on
  frequency, and the new duty excursion reports it *inside*. That is a clinically
  ordinary DBS-adjacent setting.
- **Fabrication.** 600 µs at 75 Hz is inside the 2× tolerance on **both** real axes, yet
  duty_fold = 2.25 > `TOLERANCE_FOLD`. If the direction is `non_conservative` (duty above
  the reference), `EnvelopeResult.concerning` becomes non-empty,
  `supports_unqualified_pass` goes False, and `_shannon_check` downgrades PASS → CAUTION
  for a protocol no source says anything adverse about. A fabricated downgrade from a
  derived quantity is the mirror image of the defect being fixed, and the package's whole
  claim is that it invents nothing.
- **The stated justification does not discriminate.** D5 says the change "makes
  `EnvelopeResult.inside` reachable (T14)". Deleting the excursion outright also makes it
  reachable — T14 (`StimProtocol(50,400,50,7*3600)`, area 0.1) passes under either, so it
  cannot distinguish the right fix from the wrong one.

**Correction.** Drop the pulse-duty excursion entirely and say why in the module
docstring: at fixed waveform symmetry it is the product of the pulse-width and frequency
excursions, which are already reported with their own sourced directions, and it has no
independent evidential basis in Shannon or McCreery 1990. Keep only the **train** duty
excursion against McCreery 2010's continuous protocol, which is the comparison that
source actually supports. Then T14 must additionally assert that the excursion *list*
contains no duty entry, so the deletion is pinned.

---

## MAJOR

### M1 — §0 D3: a single scalar limiting current is defensible, but three specific choices inside it are not

I **agree with the core of D3** and verified it: the worked example
(`RingElectrode(330,270,"Pt")`, 80 µA/200 µs/130 Hz) reports 141.37 µA today while the
microelectrode check FAILs; a binary search for the highest amplitude at which no check
FAILs returns exactly 20.0 µA (`p8_worked.py`), matching the plan's §3 claim. I also
confirmed the plan's mechanism note: only 4 of 9 checks expose a finite margin. And I
agree a single scalar should be the headline — a per-class report alone would let a user
programme above a binding limit, which is worse than conflation.

Three things inside it are wrong or undecided.

**(a) The compliance limit is not a safety limit and should not set the safety headline.**
It is already in the min today and D3 keeps it. When it binds, `limiting_current_uA`
means "your stimulator cannot deliver more", not "more is unsafe", yet the docstring says
"This is the number to programme against". The user who upgrades the stimulator will read
a different "safety" number from the same electrode and protocol. Separate
`limiting_current_uA` (tissue + electrode) from `deliverable_current_uA` (instrument),
and report the binding one of each. On the worked example the instrument limit is 965 µA
against a safety limit of 20 µA, so nothing moves — but on the DBS band example I ran,
compliance binds at 19 174 µA and *is* the reported mechanism.

**(b) The chronic check's limit is ambiguous and the plan does not say which boundary to
use.** `_chronic_check` has two thresholds: above `low` → CAUTION, above `high` → FAIL.
Pt/PtIr are `(20, 50) µC/cm²`. For ledger 66's own example (`DiscElectrode(100,"Pt")`,
200 µs) the FAIL boundary gives 19.63 µA and the CAUTION boundary 7.85 µA — a 2.5×
difference in the headline, unspecified. (Ledger 66 quotes 19.63, i.e. the FAIL boundary;
the plan should say so explicitly, because every other check's margin is margin-to-FAIL
and this one has a second tier.)

**(c) A chronic-degradation limit should not bind an acute protocol.** The check's own
detail text says "Relevant to chronic implants, not to a single acute session". The
worked example's `train_duration_s` is **1 second**. D3 would let a platinum-dissolution
threshold set the binding amplitude for a one-second train. Either gate the chronic check
on train duration (with a stated cut-off and its source), or carry a `kind` on each
`Check` (`tissue` / `electrode-chronic` / `electrode-acute` / `instrument`) and have
`describe()`/JSON/PDF print the binding limit per kind alongside the scalar. The `kind`
field is cheap and settles (a) and (c) together.

### M2 — §0 D2: 4 ulp is empirically enough for today's paths, but the contract is incomplete and D3 adds two predicates it cannot handle

I set out to disprove the 4-ulp bound and **could not**. Measured over 2 646
material × policy × polarity × area × pulse-width combinations, the worst number of ulp
steps in the *current* domain needed to satisfy the forward charge-density check is **2**
(`p6_ulp.py`); over 192 Shannon combinations, **1** (`p3_ulp.py`). A 40 000-trial
randomised search over resting potentials found a worst case of **2** for the
water-window round trip (`p5_search.py`). The reason is structural: each IEEE operation
is monotone, and these forward paths are near-linear in current, so the round-trip
overshoot and the per-ulp sensitivity scale together. **The budget survives scrutiny for
the paths D2 was written for, and refusing to loosen `ChargeResult.passes` with a
tolerance is the right call.**

Three gaps remain, and D3 walks into all three by widening the candidate set.

**(a) Exhaustion behaviour is unspecified.** The docstring says "At most 4 ulp steps" and
the plan never says what happens on the fifth. Returning the failing value is a silent
failure; raising turns a legitimate input into an exception. State it: raise a named
error carrying the check, the value and the step count, so a future non-linear check
cannot degrade quietly.

**(b) The water-window predicate is non-monotonic in current.** `passes` is
`window.contains(resting + sign·excursion)` — a two-sided containment. With a resting
potential outside the window the predicate is False–True–False (`p4_floor.py`, Pt,
anodic-first, `resting_potential_V = -0.70 V`):

```
Q=  0.0 uC/cm2  peak=-0.7000 V  passes=False
Q= 25.0          peak=-0.6000 V  passes=True
Q=200.0          peak=+0.1000 V  passes=True
Q=400.0          peak=+0.9000 V  passes=False
```

`resting_potential_V` is validated nowhere (ledger 14). "Largest float ≤ value that
satisfies the check" is then not the safe answer — there is a *lower* forbidden region
the floor loop will never see.

**(c) There are inputs for which no value passes.** When `available_V ≤ 0`,
`max_charge_density_in_window_uC_cm2` returns `0.0`, and `passes(0.0)` is False.
`floor_to_pass(0.0, …)` then steps into negative denormals: budgeted, it returns a
negative "limit"; unbudgeted, it does not terminate.

**Correction.** Require every predicate handed to `floor_to_pass` to be declared
monotone-decreasing in current, assert it in debug (`passes(v) ⇒ passes(nextafter(v,
-inf))` at the returned point), validate `resting_potential_V` against the window at
construction (this also closes ledger 14, currently deferred to C1.6 as a NaN-only fix),
and define exhaustion as a raise. Keep the 4-step budget — I could not break it — but
make it a checked contract rather than a comment.

### M3 — §0 D6: `return_phase_amplitude_ratio` is not an amplitude ratio, and the revived FAIL branch is a cliff

The parameterisation is **not** redundant — I checked. With `r_w` the width multiplier
and `r_a` the new field, the map `(r_w, r_a) → (width = W·r_w, amplitude = I·r_a/r_w)` is
a bijection for `r_w > 0`, so the user cannot express a physical waveform two ways or set
the pair inconsistently. That part of the design is sound.

The **name is wrong**, and it will be mis-set. Under the plan's own formula the return
charge is `I·W·r_a`, so `r_a` is the **fraction of injected charge recovered** — the
plan's own T12 says so ("`return_phase_amplitude_ratio=0.9` gives `net_charge ≈ 0.1 ×
charge_per_phase`"). But the obvious reading of "amplitude ratio" is
amplitude-to-amplitude, and that is only true when `r_w = 1`. A user setting
`return_phase_ratio=0.25, return_phase_amplitude_ratio=0.9` intending "return phase at
90 % amplitude" gets a return amplitude of `3.6·I` and an imbalance of 10 %, not the
`0.9·I` they asked for.

**Correction.** Name it `charge_recovery_ratio: float = 1.0`. It is exactly what every
downstream consumer reads (`net_charge_per_pulse_uC`, `net_dc_current_uA`,
`is_charge_balanced`), it is dimensionless and unambiguous, and it removes the
interaction with `return_phase_ratio` from the user's mental model entirely.

Separately: D6 revives the FAIL branch at `assessment.py:567`, so **any** non-zero
imbalance becomes an overall FAIL. At 80 µA / 200 µs / 130 Hz a 0.1 % imbalance is 2.1 nA
of net DC — below anything this bibliography treats as damaging, and below what a
series blocking capacitor or a shorting phase removes in practice. A binary FAIL at
`abs(net) > tol` turns a float tolerance into a safety threshold. Give the branch a
sourced criterion on **net DC current density** (or state explicitly that no source in
this bibliography bounds it, and make the check CAUTION with the DC value reported — the
treatment the package already gives every other unsourced quantity).

### M4 — §0 D7 / §2 C3.4: the default is the anti-conservative one, and "exactly double" pins the wrong model

**On the default.** Under-estimating `required_V` is the anti-conservative direction —
`compliance.py`'s own docstring says the stimulator drops out of regulation "silently, in
most hardware" and that "every safety margin computed elsewhere in this package then
describes a protocol that was never actually delivered". "States the assumption" puts the
caveat in prose while the **status** stays `PASS`, and it is the status that propagates
to the headline, the PDF and the JSON. Everywhere else this package refuses exactly that
trade: an unverified CIC downgrades to CAUTION (C4.2), a non-disc Shannon downgrades to
CAUTION (C3.5). The counter electrode should get the same treatment: `None` keeps today's
arithmetic — the plan is right to refuse silent doubling — but the compliance check
returns **CAUTION**, not PASS, with "monopolar single-interface budget assumed; supply
`counter_electrode` for a two-terminal estimate". That is consistent, non-breaking for
the numbers, and visible.

**On the test.** C3.4: "a supplied identical counter electrode must **exactly double** the
ohmic + polarisation budget". Doubling is right for the *polarisation* terms (interfaces
do not couple through the medium). It is wrong for the *ohmic* term whenever the two
electrodes are not far apart. First-order superposition for two compact electrodes of
equivalent radius `a` at centre separation `d` gives

```
R_two-terminal = (1/(2πσ))·(1/a − 1/d) ,   not  2/(4πσa)
```

For two adjacent Medtronic-3389 contacts (`a_sphere = 690 µm` from area, `d = 2.0 mm`)
that is **431.7 Ω against 659.0 Ω** for the naive series sum — the mutual term removes
**34.5 %**. Pinning "exactly double" as a test enshrines the far-field-only model and
forbids the correction. §3's "bipolar required compliance 1.571 → ~3.142 V (2.0×)" is an
upper bound, not the value.

**Correction.** Either model the mutual term (it is one subtraction and the geometry
already exposes `equivalent_radius_um`; separation becomes a required argument), or state
`2×` as an explicit upper bound with the assumption "counter electrode far compared with
its own size" printed in the result, and write the test as `1.0 < ratio <= 2.0 +
tolerance` with a separate exact test at large separation.

### M5 — §0 D4: `environment` keyed by geometry class silently mis-tags five shipped presets

D4 assigns the space convention by class: "Flush planar (Disc, Ring, Rectangular) and
Hemispherical are `half_space`". But `electrodes.py` models several **immersed, non-planar
physical electrodes** as `DiscElectrode` for their area:

```
mccreery_microelectrode  DiscElectrode(91.0,  "AIROF")  # 75 um iridium wire, conical point, 45-deg facet
mccreery2010_chronic     DiscElectrode(50.5,  "AIROF")  # penetrating microelectrode, 2000 um^2
beebe_iridium_wire       DiscElectrode(228.4, "AIROF")  # iridium wire in saline
rose_robblee_typeA       DiscElectrode(1100., "Pt")     # (genuinely a planar disc — fine)
weiland_tin              DiscElectrode(71.4,  "TiN")    # porous TiN, 4000 um^2
```

Under D4 all of these become `half_space` and their potentials halve, for electrodes
surrounded by tissue on all sides. C3.1 already touches these presets to flip
`access_resistance_is_exact` to `False` (ledger 21) but says nothing about `environment`.

**Correction.** Make `environment` an instance field with a class-appropriate default,
not a class property, and set it explicitly on each preset that substitutes a disc for an
immersed geometry — in the same commit as the `is_exact` flip, since it is the same
mis-modelling.

### M6 — §2 C2.4: `NOT_EVALUATED` for the monophasic water window discards a computable conservative answer

Ledger 2's finding is not "the limit is unvalidated for monophasic", it is that the
answer is affirmatively wrong in the unsafe direction: "3000 µA/90 µs/130 Hz monophasic
reports water-window PASS with 0.58 V headroom; **real DC drift exits the window in
0.256 s**". That drift time is computable from quantities the package already has
(`net_dc_current_uA`, `effective_capacitance_uF_cm2`, the window half-width). Returning
`NOT_EVALUATED` replaces a wrong PASS with no answer, when a *correct and conservative*
answer is available.

C2.4's reasoning is right for **charge injection** — a CIC is a per-pulse reversible
charge measured biphasic, and no source transfers it — and I agree with `NOT_EVALUATED`
there. It is wrong for the **water window**, which is a potential-excursion model the
package can integrate over time. Report the drift time and FAIL (or CAUTION with the
time, if the drift model is judged too coarse to FAIL on). This also fixes half of B4:
the monophasic candidate set regains a limit, and it is a *lower* one.

### M7 — §0 D5: `train_duty_cycle` reaches only the citation string, not the thermal path

`StimProtocol`'s own docstring says "**Duty cycle** governs average power dissipation,
which is what the thermal model integrates". `rms_current_uA` and `average_current_uA`
divide by `period_us` only — they know nothing about a train schedule. D5 wires
`train_duty_cycle` into `mccreery2010.duty_cycle_note` and nowhere else, so a user setting
`train_duty_cycle=0.5` gets an unchanged RMS current, an unchanged temperature rise and
an unchanged average power, while a sentence elsewhere in the report tells them the duty
cycle halved. That is exactly the "dataclass field that no serialiser writes… a new silent
failure" C2.1's note warns against, one commit later.

**Correction.** Either wire `train_duty_cycle` into `average_current_uA`, `rms_current_uA`
(as `sqrt(train_duty)·`) and `n_pulses`, with the thermal blast radius listed in §3, or
name it `train_duty_cycle_reported_only` and document in the field docstring that no
model consumes it. The first is correct; the second is at least honest.

---

## MINOR

**m1 — the `D1 → D3` hard edge is not real.** §1: "`limiting_current_uA` must skip checks
that did not run; **that decision is the rank change**." It is not. Skipping non-run
checks is `c.status is not Status.NOT_EVALUATED`, which is available today at any rank
order. The rank change alters which status *wins the aggregate*; it provides no
ran/did-not-run predicate that did not already exist. This matters practically: C1.4 is
not blocked if C1.1 turns out contentious.

**m2 — the `D2 → D3` reason misattributes its own evidence.** §1: "The four newly-included
limits fail their own forward check in 17/54 … combinations until the back-solve floors
(ledger 9, 66)." Ledger 66's 17/54 is about the **currently reported** limit
(charge-injection), not the four to be added — those limits do not exist until C1.3/C1.4.
The ordering (floor, then widen) is still the right one, but for a different reason:
`floor_to_pass` cannot be applied to the four new limits until D3 has defined their
forward predicates as functions of current, so the generic helper lands at C1.2 and its
*application* to the new limits must land inside C1.4. Say that, so the C1.2 → C1.4 gap
does not get treated as "already done".

**m3 — C1.5's blast radius is missing from §3.** C1.5 is framed as making
`limiting_mechanism` "name a check that ran". It is also a **value** change. Measured
(`p13.py` head): `DiscElectrode(40, "PEDOT")` at 200 µs today reports "Limiting current:
99.67 µA (Shannon tissue-damage criterion)" while the Shannon check itself is
`NOT_EVALUATED` ("not applicable: microelectrode"). `self.shannon.max_current_uA` is an
unconditional candidate in `limiting_current_uA` regardless of the check's status. §3 has
no row for C1.5.

**m4 — §3's C3.1 row names the wrong consumer.** "field.py docstrings, **VTA (consumes the
field)**, README". `models/vta.py` imports only `math`, `numpy` and `dataclasses`; it uses
a current-distance (Stoney `k`) relation and never calls `potential_V` or `field_V_per_m`.
The real consumers are `neurostim/io/fem.py:251-262` (`compare_with_point_source`) and
`neurostim/viz/plots.py:309-334`, neither of which is listed. Worse,
`compare_with_point_source` calls `potential_V(current_uA, r_keep, sigma)` with **no
`electrode=`**, so after D4 it silently stays full-space while every planar assessment
becomes half-space — a new 2× inconsistency inside the very utility that C7.3's FEM-
validation claim rests on. Thread the electrode through, or state the convention in that
function's docstring. This also makes C3.1 → C5.10 and C3.1 → C7.3 real edges the graph
does not carry.

**m5 — "fails by exactly 2× today" is π.** Covered in B1; noted separately because §2's
C3.1 row and §4's R2 both repeat the number and both would need editing.

**m6 — §5's ledger-12 fix changes the status but not the limit.** C3.5 makes the Shannon
check CAUTION for non-disc geometries. But `shannon.max_current_uA` still enters D3's
minimum with no confidence marker, so an unqualified Shannon limit can still *bind the
headline number* for a band or ring. This is the same under-reach R5 identifies for
provenance. Give `Check` an `inexact`/`provisional` flag that travels with the margin, and
have `limiting_mechanism` say so when the binding limit carries one.

---

## Decisions that survived scrutiny — stated explicitly

- **D1, the rank reorder.** Correct, and the alternative the plan rejects (a per-check
  applicability predicate) really would have to be hand-maintained. I traced the
  consequence: the *only* behavioural change is `{PASS…} ∪ {NOT_EVALUATED} → PASS`; any
  set containing a CAUTION or FAIL is untouched, because today `NOT_EVALUATED` already
  sits below CAUTION. Confirmed that macroelectrodes currently cannot reach PASS
  (`p7_rank.py`). The `not_evaluated` tuple plus the `describe()` line is the right
  mitigation. The only permissiveness regression I found does **not** come from the rank
  change — it comes from C2.4 + D3 (B4).
- **D4's space assignment.** 2π for flush planar, 4π for immersed is right, and the
  `22.7364 → 45.4728 mV` doubling in §3 is correct. I verified the 2π point source is the
  disc's exact asymptote (ratio 0.999983 at `r/a = 100`). Only the invariant (B1) and the
  cylinder override (B2) are wrong.
- **D2's principle.** "A reported limit always floors; the forward inequality stays
  exact", and specifically the refusal to loosen `ChargeResult.passes` with a tolerance.
  I tried to break the 4-ulp bound over ~43 000 cases across three code paths and could
  not. See M2 for the three contract gaps.
- **D3's core claim.** The minimum is too narrow and the worked example's 141.37 µA is
  wrong; the independent binary search returns exactly 20.0 µA, matching the plan. The
  observation that `_chronic_check` and `_water_window_check` carry no margin is correct
  and I confirmed only 4 of 9 checks expose a finite one.
- **D5's diagnosis.** McCreery 2010's duty is genuinely a train on/off schedule, the
  existing comparison is genuinely a category error, and `2 × 400 × 50 × 1e-6 = 0.04` is
  arithmetically correct and matches `StimProtocol.duty_cycle`. Only the conclusion drawn
  from it (B5) is wrong.
- **D6's parameterisation.** Bijective, not redundant; symmetric protocols stay
  byte-identical. Only the name (M3) is wrong.
- **C3.2.** A sphere's primary current distribution is uniform, and a hemisphere flush in
  an insulating plane is the image-symmetric half of a sphere, so it is uniform too. The
  plan's assertion is correct physics.
- **C0.3 as load-bearing.** Agree without reservation. Seven hand-edited artifacts across
  a dozen numeric commits is where doc drift is manufactured.
- **§5, all five refusals.** Ledger 12: Shannon's own text is "the limit of safe
  stimulation is linearly related to electrode **diameter**, not electrode area… probably
  due to the charge 'building up' at the edges" (`shannon1992.txt:103`) — a mechanism,
  not a functional form, and there is none in this bibliography for a ring, band or
  rectangle. Declining to invent one is right (see m6 for the one amendment). Ledger 22,
  45, 23 and 36: agree, for the reasons given. I looked for something in §5 that must be
  fixed and found nothing above MINOR.

**Being fixed that should not be:** D4's cylinder override (B2) — it replaces a
conservative +55 % error with a +40 % error of the same sign, breaks a published pin, and
makes `access_resistance_ohm` non-monotonic. And D5's re-referenced pulse-duty excursion
(B5) — the right action is deletion, not correction.
