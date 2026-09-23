# Phase 3 Review — `git log 39331bf..278932b`

Status: COMPLETE

Repo: .
HEAD: 278932b (f376a27 plus one ledger-text commit). The main tree was not modified. A
scratch worktree was created under the session scratchpad and removed. All independent
solvers used below live in the scratchpad (`fv_band.py`, `fv_disc.py`, `fv_pair.py`,
`fv_tip.py`, `oracle_rt3.py`). None imports `neurostim`, except where a script compares
against it.

## Commits in scope
```
278932b docs(ledger): tell C4.2 to re-check the counter's 2x relation for Pt and PtIr
114604a docs(safety): state Shannon's diameter-not-area finding where it applies          (C3.6, 12)
978c1da feat(safety): model the counter electrode and the lead resistance ...               (C3.5, 5, 69/T18)
d5136df fix(geometry): reject NaN pitch, coincident sites and contradictory tip parameters (C3.4, 28, 29)
c327cee fix(geometry): correct the direction of the equal-area substitution error          (C3.3, 10)
0c3e79a fix(safety): report the current distribution of the actual geometry                (C3.2, 18)
a010103 fix(geometry): settle one half-space/full-space convention per geometry            (C3.1, 17, 20, 21; 16 doc)
5dc9eb1 fix(safety): the water-window detail states both clauses' verdict ...               (C3.0, 108)
96ccae5 / 9e2087b  Phase 2b doc fixes (113, 121, 122, 123) and ledger commits
```

## Gates at HEAD (executed)
`pytest -q`: **994 passed**. The main thread reports ruff, mypy, the ledger gate and the README
check as green; I re-ran pytest only.

## Summary

| # | Sev | Where | One line |
|---|---|---|---|
| H1 | MAJOR | tests/oracles/fd_band.py; geometry/base.py:93-100, volumetric.py:52-58, compliance.py:17-19; README; CHANGELOG | The FD band reference table is under-resolved. Its own generator, refined, falls from 335.1 toward ~327.7 Ω (clinical) and from 739.9 toward ~654 Ω (aspect 0.2). An independent solve, validated to 0.05 % on Newman's disc, puts the equal-area sphere **+10.1 % at aspect 0.39 and +6.9 % at 0.5**, not "within 2 %". Pin C's 5 % claim fails at 0.39–0.5, and every published "335.1 Ω / −1.7 %" is wrong. The error direction is conservative |
| H2 | MAJOR | io/tabular.py:231 only | `Check.provisional` reaches only the JSON. The C3.6 purpose ("so a caveated limit is visible when it binds") and C1.4's §6 promise ("JSON, PDF check table, GUI table") are unmet. When Shannon binds on the 3389 band, the describe/PDF/GUI headline shows no caveat |
| H3 | MINOR | geometry/volumetric.py (MicrowireElectrode) | A flat-tipped microwire with no exposed shaft takes the full-space sphere at 0.159/(σa). An independent solve of a disc on the end of an insulating rod gives ~0.175. The sphere is **9 % low, anti-conservative** for the compliance budget |
| H4 | MINOR | safety/compliance.py:489-500 | The separation guard uses equal-area *sphere* radii. Two 1500 µm bands on one shaft are accepted at a centre spacing of 1390–1499 µm, where they physically overlap, and the package returns a resistance (334 Ω at 1400 µm) |
| H5 | MINOR | safety/compliance.py:176-187 | The return phase reuses the counter's leading-phase capacitance. For AIROF and PEDOT with cathodic-first pulsing this under-states the counter's return-phase polarisation by 1.575× and 1.5× (anti-conservative where the return phase binds). The active electrode has the same pre-existing simplification |
| H6 | MINOR | water_window.py:350-360 | A drift-CAUTION Water-window check prints the detail header "-> PASS (peak within window; drift reaches the edge after the train)". This is the 108 pattern in its milder form |
| H7 | MINOR | compliance / scope | The counter electrode's own charge density, CIC and water window are never assessed, although its area and material are now inputs. A small counter can be driven far past its limits, and nothing says so. The docs do not state this scope limit |

Counts: **0 BLOCKER, 2 MAJOR, 5 MINOR** (6 MINOR with H8; see the addendum on 278932b).

---

## H1 — MAJOR — the FD band reference is not converged, so the published sphere accuracy is wrong

`tests/oracles/fd_band.py` claims convergence of "335 ± 1.5 Ω, about ±0.45 %" at the
clinical aspect. Its generator (`scripts/fd_band_reference.py`) refines `nr` and `nz` together.
The first radial spacing is fixed relative to the shaft radius (geometric out to 2000 r0), so
the singular band edge is under-resolved radially. This gets worse as the band shortens.

**Their own solver, radially refined** (executed, σ = 0.35 S/m, d = 1270 µm):

```
aspect 0.2 :  500x500 739.88 | 1000x500 703.07 | 2000x500 679.55 | 2000x1000 688.42 | 3000x1000 (domain 500) 674.74
aspect 1.181: 500x500 335.06 | 1000x500 330.88 | 2000x500 328.72 | 2000x1000 330.11 | 3000x1000 (domain 500) 328.48
```

**Independent solve.** `fv_band.py` is an axisymmetric finite-volume solver: geometric grids
clustered at the band edge from both sides, first cell h/1000, the far box extrapolated in
1/box. The same scheme on Newman's flush disc (exact 1/(4σa)) converges from above:
+0.88 %, +0.30 %, +0.10 %, +0.05 % at four resolutions.

```
aspect  FV (converged)   oracle table   package sphere   sphere vs FV   sphere vs oracle (as claimed)
0.20    653.7            739.9          800.6            +22.5 %        +8.2 %
0.39    520.6            559.8          573.3            +10.1 %        +2.4 %
0.50    473.9            502.2          506.4            +6.9 %         +0.8 %
1.00    353.9            363.7          358.1            +1.2 %         -1.6 %
1.181   327.8            335.1          329.5            +0.5 %         -1.7 %
2.00    252.5            255.0          253.2            +0.3 %         -0.7 %
4.00    171.9            172.1          --               --             --
10.0    96.7             96.3           113.2            +17.1 %        +17.6 %
```

The oracle agrees with an independent solve only at aspect 4 and above, where the band is long
compared with the radial cell.

**Consequences.**
* Every "within 2 % from aspect 0.39 to 2.0" statement is false at 0.39 (+10.1 %) and 0.5
  (+6.9 %). These appear in `geometry/base.py:99`, `volumetric.py:56`, `compliance.py:18`, the
  README Known limitations, the CHANGELOG, ledger 16/20 and D4.
* Pin C's "within 5 %" test passes only because it is compared against the wrong table.
* "335.1 Ω" and "−1.7 %" are wrong. At the clinical contact the sphere is actually **+0.5 %
  high**, which is better than claimed and conservative.
* `TestKuncelGrill2004` scales the same 335.1. Its assertion still holds against the
  corrected value (sphere 578.8 against a true ~573.6 at 0.2 S/m, +0.9 %), but only by
  coincidence.

The sphere overestimates R at every aspect I solved, so every package number errs toward a
higher required compliance voltage. No safety number is anti-conservative. The defect is an
unsourced accuracy claim, and an oracle that certifies it.

**Fix.** Regenerate the table with radial resolution tied to the band height (first cell ≲
h/500 and clustered at the edge). Use a convergence study that refines r alone, then z alone.
Restate the accuracy (+0.3 to +1.2 % for aspect 1–2; +7 to +10 % at 0.39–0.5; +17 to +23 % at
the extremes, all high). Re-pin Pin C and correct every doc and ledger site that quotes 335.1,
−1.7 % or "within 2 %".

## H2 — MAJOR — `provisional` never reaches a headline

Executed: an AST scan of `neurostim/` finds `.provisional` read in exactly one place,
`io/tabular.py:231` (the JSON `checks[]`). Then, with `dbs_3389` at 3000 µA/60 µs/130 Hz and
10 V compliance, Shannon binds and is provisional:

```
describe(): Limiting current: 2.292e+04 uA (Shannon criterion)
GUI:        CAUTION (...) - limiting current 2.292e+04 uA (Shannon criterion) - INCOMPLETE: ...
JSON:       checks[Shannon].provisional = true
PDF text:   contains "fit on discs" (check row) but no "provisional"; headline carries no caveat
```

C3.6's plan row says the flag exists "so a caveated limit is visible when it binds" (physics
m6). C1.4's §6 row booked it into the "PDF check table, GUI table". Neither is rendered. The
CAUTION status and its note "fit on discs, not this geometry" do appear in the check list, so
the information is on the page. It is just not attached to the number a user programmes.
**Fix:** render a provisional marker beside the limiting current whenever the binding check
(or the cap's binder) is provisional, on describe, PDF, GUI and figure. Schedule it explicitly
at C4.3, which is already the provisional-propagation commit.

## H3 — MINOR — flat-tip microwire: the sphere is anti-conservative

`fv_tip.py` solves a disc on the end of a semi-infinite insulating rod of the same radius,
with an optional conducting shaft of length ℓ. Results in units of R·σ·a:

```
ℓ = 0   : FV 0.1755  package (full-space sphere) 0.1592   -9.3 %  (low: anti-conservative)
ℓ = 2a  : FV 0.0722  package 0.0712                         -1.4 %
ℓ = 10a : FV 0.0326  package 0.0347                         +6.4 %
bounds  : two-sided disc 0.125 < FV < half-space disc 0.25
```

`MicrowireElectrode(d, 0, "flat")` is accepted (the code even notes that it "is just a disc").
It is the one immersed configuration where the sphere under-states R. **Fix:** document the
flat-tip error, or treat ℓ = 0 on a flat tip as the half-space disc (conservative) until a
better form is sourced.

## H4 — MINOR — the separation guard admits overlapping bands

`validate_counter` requires `d > a_eq(active) + a_eq(counter)` using equal-area sphere radii
(690 µm for a 3389 contact). The bands are 1500 µm long, so any centre spacing below 1500 µm
on one shaft overlaps. Executed:

```
sep 1300 refused | 1390 accepted, R 331.8 | 1400 accepted, R 334.1 | 1499 accepted, R 355.6
```

Near the guard the formula is conservative. Checked against an independent two-band solve on
one shaft (`fv_pair.py`, antisymmetry plane at V = 0):

```
sep 1550: FV 306.3, formula 365.5 (+19 %) | 1600: 336.6 vs 374.7 (+11 %) | 1800: 397.1 vs 406.3 (+2 %)
sep 2000: FV ~430.4, formula 431.56 (+0.3 %) | 3000: 510.1 vs 507.3 (-0.6 %) | 6000: 581.8 vs 583.1
```

So D7's first-order superposition is excellent at the clinical 2 mm spacing (0.3 %). The
overlapping inputs, though, are physically meaningless and still return a number.
**Fix:** for elongated geometries, guard on the largest half-dimension, or document the
spacing below which no answer is given.

## H5 — MINOR — return-phase counter polarisation uses the wrong polarity

`required_V_at` passes `counter_capacitance_uF_cm2`, derived for the counter's polarity during
the leading phase, to the return-phase term too. During the return phase the counter carries
the leading polarity. Per-material `C_eff` (executed):

```
AIROF 1666.7 (cathodic) / 2625.0 (anodic)   PEDOT 4000 / 6000   Pt, PtIr 250 / 125   SIROF 8333 / 6250   TIROF 1667 / 1250   TiN, SS equal
```

For cathodic-first AIROF and PEDOT, the counter's return-phase polarisation is under-stated by
1.575× and 1.5×. That matters only when the return phase binds (`return_phase_ratio < 1`).
For Pt, PtIr, SIROF and TIROF the direction is conservative. The active electrode's own
return-phase term has had the same simplification since C2.2. **Fix:** give each phase its own
polarity-correct capacitance on both electrodes, or document the simplification with its
direction per material. This fits ledger 278932b's C4.2 recheck.

## H6 — MINOR — CAUTION check, "PASS" detail header

```
[      CAUTION] Water window: ... reaches the edge in 452.4 s -- after the 1 s train
    Water window (Pt, cathodic phase) -> PASS (peak within window; drift reaches the edge after the train)
```

C3.0 fixed the FAIL case. The CAUTION case still leads with "PASS". **Fix:** use "-> CAUTION (…)"
when the drift lands after the train.

## H7 — MINOR — the counter electrode is not itself assessed

C3.5 takes the counter's geometry and material for the voltage budget but runs no charge-density,
CIC or water-window check on it. A small counter carrying the same charge can far exceed its own
limits and pass silently. D7 did not require this, but the README and compliance docstring do not
say it is out of scope. **Fix:** state it, or add a counter-side charge-density check.

---

## Verification of the lead's focus items

**1. C3.1 physics.**
* The 2π/4π factor is read from `Electrode.environment`: 2π for disc, ring, rectangle and
  hemisphere; 4π for sphere, band, microwire and full-space stand-ins.
* The planar potential doubles to 45.47284088339866 mV at the booked point. The point source
  against the exact disc `(2/π)IR·arcsin(a/r)` is 0.99833 at 10a and 0.99998 at 100a.
* The ×2/π for band and microwire is exact by construction (sphere against Newman's disc of
  equal area).
* The sphere against an independent solve is the subject of H1.
* The Kuncel & Grill rewrite is faithful to the paper. Every quote was checked in extracted
  text: "conductivity around 0.2 S/m"; "The impedance is estimated conservatively to be 500 Ω";
  "1.26 mm in diameter ... set to 3 V, 25.6 % ... average value of 0.0993 A/cm²". The 508.8 Ω
  back-solve is the test's inference, labelled as such.
* Presets: all four re-tagged resistances reproduce (9994.030963384324, 18009.045894415314,
  dbs_kuncel 330.7662466870746, 3389 329.4614437836306); `rose_robblee_typeA` stays half-space
  and exact.

**2. C3.3 oracle.**
* `planar_bounds.py` imports nothing from `neurostim`.
* The formula is right: `R = K(e)/(2πσa)` follows from the elliptic disc's full-space capacity
  `4πε0a/K(e)` and `R = 2ε0/(σC)`. K(0) recovers 1/(4σa), and K is computed by AGM.
* The thin ring uses the torus capacity `2π²ε0D/ln(8D/d)` with a strip taken as a wire of
  diameter w/2, which is standard.
* The direction claim is the Pólya–Szegő isoperimetric inequality (the disc minimises capacity
  among plane regions of given area), so the equal-area disc is an upper bound. Correct.
* 50 634 Ω is the equal-area disc of a 200 µm × 1 µm ring, as stated.

**3. C3.5.**
* The mutual term `2/(Gσd)` is right in both environments. For two flush electrodes on one
  insulating plane, a surface point at distance d from a flush source sits at `I/(2πσd)`
  (image doubling), hence `2/(2πσd)`. Two coplanar 500 µm discs tend to exactly 2R at large
  separation (0.99998 at 10 m).
* Booked numbers reproduce exactly: monopolar 1.0064302461581618 V, bipolar
  1.3488137938726137 V, ohmic 431.5586831502678 Ω, counter polarisation 0.036 V against 0.018 V
  active.
* Lead resistance: 2 kΩ adds exactly 6.0 V at 3 mA and lowers `max_current_uA`
  22241.77 → 4082.29 µA.
* `max_current_uA` is consistent with `required_V`: at the ceiling `required_V` = 10.0 V and
  the check passes; one float above, it fails.
* The refusals fire: mixed environment, counter with measured Z, each half-input alone, and a
  NaN separation.
* Consumers: an AST scan of every `SafetyCalculator(`, `potential_V(` and
  `required_voltage_V(` call.
  * `viz.safety_summary` forwards the counter automatically through `_calculator_settings`,
    which reads the constructor signature.
  * `sensitivity`, `_biphasic_cap` (via `copy.copy`), the fail-ceiling oracle and
    `io.fem.compare_with_point_source` all carry it.
  * The only non-carrying surfaces are those ledger 126 lists: batch, GUI, JSON/audit settings.
  * Nothing else silently drops the counter. `material_comparison` rebuilds calculators at
    library defaults, but that is pre-existing and only plots charge limits.
* **Independent round-trip:** 1 200 random configurations over all seven geometries, 60 %
  with a same-environment counter, lead resistance 0–5 kΩ and compliance 1–10 V (576 bound by
  compliance). The package's `limit_bearing_ceiling_uA` matches the bisection oracle in
  **1 200 of 1 200** at rel 1e-9.

**4. C3.6.**
* Every non-disc geometry and stand-in disc gets CAUTION plus `provisional = True`, and the
  value is unchanged (the code path does not touch it).
* `provisional` does not reach the headline renders (H2).

**5. Bookings and docs.**
* Every §6 digit I executed matches:
  * band `required_V` 0.3354767487193873 and 1.6533225238539098;
  * worked-example mechanism Compliance → Shannon; thermal 3.435 mK at 46.26 µW;
  * the three preset resistances; the C3.5 values above.
* README and CHANGELOG describe the code, except for the FD-accuracy sentences (H1).
* Earlier-phase test edits are justified and not weakened:
  * `test_core` moves 10 → 3 V with the premise now asserted.
  * The C2.2 goldens were re-measured, with the old value kept in the docstring.
  * `test_models_io_viz` passes the site electrode.
  * `TestDiscSurfacePotential` flips 0.5 → 0.999983, which matches the oracle's half-space
    factor.

**Non-vacuity.** Each commit's tests were run against its parent package:
* C3.0: 2 failed.
* C3.1: 27 + 1 + 1 failed.
* C3.2: 11 failed.
* C3.3: 2 failed. The oracle tests pass on the parent, correctly, because they test the oracle.
* C3.4: 5 failed.
* C3.5: 15 + 15 failed.
* C3.6: 7 failed.

**6. Regressions.** Phase 2/2b grids re-run at HEAD:
* residual sweep: 6 240/6 240 exact zero net, 0 raises;
* lds_rate: 0 of 16 200 raise;
* the two repros are ok;
* ww98: 20 000 configurations, 0 raises and 0 predicate/status disagreements;
* disc oracle round-trip: 1 000 configurations, 843 agree and 157 are both zero, 0 disagree.

No regression.

## Addendum — 278932b (docs-only, ledger 8 row and §9 row 8)

**It names a real test.** `tests/test_space_convention.py::TestTheCounterElectrodeEntersTheVoltageBudget`
exists and passes: 13 tests. Its
`test_far_apart_two_identical_interfaces_need_exactly_twice_one` pins exactly 2× on TiN only,
with the premise asserted that TiN's two polarities give equal `C_eff`. The 2× counter
polarisation for Pt is real: I executed 0.036 V against 0.018 V (H5 / C3.5 above).

**H8 — MINOR — the stated cause is only half right, and it points at the wrong code path.**
The row says the Pt/PtIr asymmetry comes from "this half-window asymmetry". Executed: Pt and
PtIr store an optimistic CIC of 150 µC/cm² cathodic against 100 anodic, with half-windows of
0.6 V and 0.8 V. So `C_eff` = 150/0.6 = 250 against 100/0.8 = 125. The CIC's polarity
dependence contributes 1.5× and the half-window 1.33×.

Ledger 8's own defect is the `min(|cathodic|, |anodic|)` branch, taken only when
`anodic_first is None`. The counter path always passes a boolean
(`anodic_first=not protocol.anodic_first`), so fixing ledger 8 at C4.2 need not touch the
counter relation at all. That makes the scheduled re-check likely a no-op.

**Fix:** reword the note so the 2× follows from the polarity-specific CIC and half-window
together. Say that C4.2's ledger-8 fix does not reach the counter path unless C4.2 also changes
`effective_capacitance_uF_cm2`'s boolean branches. Otherwise, move the re-check to wherever
the polarity-specific `C_eff` is revisited (ledger 7, also C4.2).

This does not change the verdict. Counts become **0 BLOCKER, 2 MAJOR, 6 MINOR**.

## Process note
Per the brief, this review wrote only this file. The reviewer did not update
`_conversation_history.md` (CLAUDE.md rule 14).

# VERDICT: **GO** for Phase 4, with one condition

The Phase 3 code is sound:
* the convention is consistent;
* the counter model matches an independent two-band solve to 0.3 % at the clinical spacing;
* 1 200 of 1 200 mixed-geometry configurations round-trip against the bisection oracle;
* every booked digit reproduces;
* no earlier grid regresses.

**Condition:** fix H1 before Phase 4 closes. Regenerate the FD table at adequate radial
resolution, restate the sphere's accuracy, and correct the "within 2 % / 335.1 Ω" sentences.
Phase 4 is the provenance phase, and publishing an accuracy claim certified by an unconverged
oracle is exactly what it exists to prevent. H2 should be written into C4.3's scope. The
MINORs can be scheduled normally, with H3 and H5 as the anti-conservative ones.
