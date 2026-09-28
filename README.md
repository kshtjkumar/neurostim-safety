# neurostim-safety

Electrode safety and stimulation modelling for neural interfaces.

Every literature-derived constant in this package carries its primary source **and the
conditions under which it was measured**. That is the point of the package. A charge
injection limit is not a material constant — it depends on pulse width, waveform
polarity, interpulse bias, electrolyte, and whether the normalising area was geometric
or roughness-corrected. Most calculators quote a single scalar per material and discard
all of that. This one does not.

> **Not validated for clinical or regulatory use.** The tissue-damage criterion is an
> empirical separatrix fitted to animal histology. The thermal and activation models are
> analytic approximations with narrow, documented validity ranges. Anything that rests on
> an unconfirmed constant or model -- your own measurement, a capacitance derived from it,
> a criterion extrapolated beyond the geometry it was fitted on -- is marked `PROVISIONAL`
> wherever it surfaces.

## Install

```bash
pip install -e ".[all]"     # library + PyQt6 GUI + PDF reports
pip install -e .            # library only
```

Python ≥ 3.10. Core dependencies: numpy, scipy, matplotlib, pandas.

## Quick start

```python
from neurostim import RingElectrode, StimProtocol, SafetyCalculator

electrode = RingElectrode(330, 270, "Pt")       # outer µm, inner µm, material
protocol  = StimProtocol(80, 200, 130, 1)       # µA, µs per phase, Hz, s
calc = SafetyCalculator(electrode, protocol, compliance_V=10.0)

print(calc.describe())
```

The pulse width is **per phase**: the width of the leading phase alone. A symmetric
biphasic pulse of 200 µs per phase lasts 400 µs plus any interphase gap.

<!-- BEGIN GENERATED: quickstart-transcript -->

```
Overall: FAIL (1 check not evaluated: Shannon criterion)
Limiting current: 20.00 uA (Microelectrode charge/phase)
  across published ranges: 20.00 uA (unchanged: Microelectrode charge/phase has no published range; Shannon k 1.5-2.0 and the material range were propagated and do not bind)
  by kind: tissue 20.00 uA, electrode-acute 141.3 uA, electrode-chronic 70.68 uA, instrument 965.3 uA
  INCOMPLETE: 1 limit-bearing check did not run (Shannon criterion), so the true limit may be lower

[NOT_EVALUATED] Shannon criterion: not applicable: 0.000283 cm^2 is below the macro/micro boundary (k would read -0.04)
[      CAUTION] Charge injection limit: 56.59 uC/cm^2 of 100.0 uC/cm^2 (57 % used)
[         PASS] Water window: peak -0.23 V, 0.37 V headroom
[      CAUTION] Validated envelope: frequency 2.6x outside the fit conditions in a direction that reduces margin
[         FAIL] Current density: 0.2829 A/cm^2 is at or above the 0.2751 A/cm^2 electroporation threshold
[         FAIL] Microelectrode charge/phase: 16 nC/phase exceeds the 4 nC/phase microelectrode damage threshold
[         FAIL] Chronic degradation: 56.59 uC/cm^2 exceeds the 50 uC/cm^2 platinum dissolution threshold
[         PASS] Charge balance: biphasic, fully charge-balanced
[      CAUTION] Compliance voltage: 0.83 V of 10.0 V (8 % used); monopolar single-interface budget assumed -- supply counter_electrode for a two-terminal estimate
```

Each check also prints the conditions its limit was measured under and the
source it came from; that detail is elided above.

<!-- END GENERATED: quickstart-transcript -->

The `report()` dictionary from the 0.1.0 prototype still works and returns a superset of
its original keys. Its values are finite numbers or `None`. `report_to_json` writes strict
JSON (no `Infinity`), and a `null` that stands for an unbounded quantity is explained in
`null_reasons`:

- `protocol.train_duration_s` is `null` for continuous stimulation;
- `results.required_compliance_V` is `null` when no finite voltage suffices.

`protocol_from_report(payload)` reads the protocol back, with a continuous train restored
to `math.inf`. `protocol_from_dict` refuses a bare `null` duration by name rather than
guessing that it means a continuous train. In `assess_batch` and `current_sweep` frames,
`limiting_current_uA` and `required_compliance_V` hold a float or `None` in every row
(object dtype), as `report()` does. Two columns qualify the limit:
- `limit_is_provisional` is true when the binding check rests on an unconfirmed constant
  or model, the same condition as the PROVISIONAL headline, and `None` when there is no
  limit;
- `limits_incomplete` is true when a limit-bearing check did not run, so the true limit
  may be lower.

In `assess_batch` a row that fails to build has status `ERROR`, its message in `error`,
and `None` in every result column. The batch then emits `BatchRowsFailedWarning` and lists
the failed labels in `frame.attrs["rows_failed"]`, because pandas skips missing values
when it aggregates: exclude those rows before taking a minimum. The attribute does not
survive `write_csv` or most pandas operations. The lasting record is the `status` column
(`ERROR`) and the `error` text, which `write_csv` writes and warns about again. Count a
failure as `status == "FAIL"`, and a pass as `status.isin(["PASS", "CAUTION"])`, not as
`status != "FAIL"`, which counts `ERROR` rows as passing. `read_batch_csv` raises
`ValueError` naming the file when it cannot parse the file, or when the file has a header
and no rows.
A batch row can specify a counter electrode with the same electrode columns prefixed
`counter_`, plus `counter_separation_um`. `max_current_cic_uA` is derated in vivo, as the
Charge injection check is, and is `None` when that check does not run.

The JSON's `provenance` object gives each applied constant's reference key, `verified`
and `peer_reviewed` flags, stored note and `inherited_from` (`cic`, `water_window`,
`chronic_threshold`, or `null` where the material has none), and `material_verified`,
which is true only when all three are verified. `package_version` and the full `settings`
are recorded beside it. The PDF prints the same settings and the audit digest.

## Desktop application

```bash
neurostim-gui          # or: python -m neurostim.gui
```

Electrode and protocol inputs on the left, live results on the right: status table, full
text assessment, and an embedded Shannon safe-operating-area plot. Recomputes on every
change. An optional counter electrode makes the assessment two-terminal. It has the same
geometry as the active electrode (a second 3389 band beside a DBS band), with its own
size, material and centre-to-centre separation. Any error on the way to the view, the plot included,
is shown in the results pane with its traceback, and the view never shows half an
update. Exports the PDF report and the four-panel summary figure.

## What it computes

| Check | Basis | Source |
|---|---|---|
| Shannon criterion | `k = log₁₀(Q²/A)`, damage separatrix | Shannon 1992; Merrill 2005 eq. 5.1 |
| Charge-injection limit | Material CIC vs applied charge density. NOT_EVALUATED for monophasic delivery, because every CIC was measured biphasic | each material's primary source (in the provenance); Cogan 2008 Table 2 as the review; Merrill 2005 |
| Water window | Peak interfacial excursion vs electrolysis limits, plus DC drift: when the charge a waveform leaves behind (with each pulse riding on it) reaches the edge, against the train duration | Cogan 2008; Riedy & Walter 1996 (316LVM) |
| Charge balance | Fraction of charge recovered and the resulting net DC. FAIL only when nothing is recovered; CAUTION for a partial recovery, whose consequence is judged by Water window | Merrill 2005 |
| Counter charge injection | Only with a `counter_electrode`: the counter's larger phase charge density against its own material's CIC for the mirrored waveform (a cathodic-first protocol is anodic-first at the counter) | Cogan 2008 Table 2; Merrill 2005 |
| Compliance voltage | `I(R_access + R_lead) + ΔV_polarisation`; with a `counter_electrode`, `I(R_a + R_c − 2/(Gσd) + R_lead) + ΔV_a + ΔV_c`. An unbalanced train adds the DC offset its first `N − 1` pulses leave behind, capped at the water-window headroom on the active electrode. Without a counter, CAUTION: a single-interface budget is assumed | Newman 1966 |

Plus models, each documenting its own validity range:

- **Field** — point-source potential and gradient: half-space (`2π`) for electrodes flush in
  an insulating plane, full-space (`4π`) for immersed ones, read from the electrode's
  `environment`. Exact for a sphere; the far-field limit for a disc
- **Thermal** — Pennes bioheat, analytic steady state plus an implicit transient solver
- **Strength–duration** — Lapicque and Weiss forms, with fitting routines that report a
  95 % interval on the chronaxie (calibrated for Weiss; Lapicque's can under-cover on
  designs whose widths do not span the chronaxie, and is withheld, with the reason, when
  every width is far above it or the whole interval lies below the shortest width; the
  Lapicque fit is weighted by threshold and its interval is log-scale; a design spanning
  under 8x, or an interval spanning over 1000x, carries a coverage caveat)
- **VTA** — current–distance activation radius (the weakest model here; read its docstring)

Geometries: disc, ring, rectangle, cylindrical band, microwire (flat/hemispherical/conical
tip), sphere, hemisphere, plus linear and grid arrays.

## Corrections to the 0.1.0 prototype

Tracing every constant to its primary source changed all five of the prototype's material
values (the database now holds nine materials):

| Material | 0.1.0 | current | Why |
|---|---|---|---|
| `SS` | 0.05 mC/cm² | 0.02–0.04 | Traced to Riedy & Walter 1996; 40 µC/cm² safe, 20 non-faradaic. Stainless steel is absent from Cogan Table 2 |
| `Pt` | 0.10 | 0.05–0.15 | Cogan reports a range, from Rose & Robblee 1990 at 200 µs |
| `PtIr` | 0.15 | 0.05–0.15 | Cogan gives **one** row for "Pt and PtIr alloys". The separate higher value was not supported |
| `PEDOT` | 5.0 | 2.3–3.6 | Cui & Zhou 2007, peer reviewed. Cogan's 15 mC/cm² is from a **conference abstract** and is not used |
| `SIROF` | 2.0 | 1.0–5.0 | Now carries the published range rather than a midpoint |

The prototype's README example (80 µA into a 330/270 µm stainless ring) exceeds the
charge-injection limit by roughly 3×, and also leaves the water window. It passes the
Shannon criterion comfortably — which is exactly the failure mode this package exists to
catch: clearing the tissue-damage line says nothing about whether the electrode can
deliver the charge reversibly.

## Batch assessment

```python
from neurostim.io import read_batch_csv, current_sweep, write_csv

results = read_batch_csv("protocols.csv")            # one result row per input row
write_csv(results, "assessed.csv")

sweep = current_sweep(electrode, protocol, range(10, 200, 10))
```

Rows that fail to build are reported in an `error` column rather than aborting the batch.

## Reports and figures

```python
from neurostim.io import build_report
from neurostim.viz import safety_summary, save_publication

build_report(calc, "report.pdf")                     # methods-ready, with bibliography

fig, _ = safety_summary(calc)
save_publication(fig, "figure_1")                    # SVG + PDF + TIFF at 600 dpi
```

Figures follow a publication contract: 7 pt sans-serif, editable text in vector output,
no top/right spines, and red/green reserved strictly for pass/fail rather than spent on
ordinary categorical series.

The figure is a render surface of the same assessment the report is, and is drawn at the
calculator's own settings rather than the library defaults. Panel (b) draws every
limit-bearing check that ran at its own ceiling, labelled with the check's name, and takes
its binding amplitude and the mechanism that sets it from `calc.assess()` — so the number
on the figure is the number in the report, and the mechanism it names is a curve you can
find. A protocol unsafe at *every* amplitude gets the sentence naming the check in place
of a number here too.

## Uncertainty

Published limits are ranges, not numbers. Cogan gives platinum as a factor of three.
Rather than hide that behind the `policy` setting, the assessment reports both:

```
Limiting current: 19.63 uA (Chronic degradation)
  across published ranges: 7.853-19.63 uA (Shannon k 1.5-2.0, full material range, chronic threshold band)
```

```python
assessment.limiting_current_interval_uA     # Interval(7.85398, 19.63495)
assessment.charge.limit_interval_uC_cm2     # Interval(100.0, 150.0)
```

The interval is over the same candidate set as the point estimate, so it always contains
it. When the check that binds has no published range of its own — Cogan's 4 nC/phase
microelectrode threshold is a single number — the interval collapses onto the point
estimate and says so, rather than reporting a spread the literature does not supply.

Both ends of a limit interval are printed **floored** to four significant digits, not
rounded to nearest: rounding a maximum to nearest rounds it up, and programming the
printed figure would then fail the check it is the maximum for.

This is interval arithmetic, not uncertainty quantification: it assumes inputs can sit
at their extremes simultaneously and does not track correlation. A wide result is not a
defect — it is what the literature supports. Narrowing it means characterising your own
electrodes.

## External field solutions

The analytic field model assumes a homogeneous isotropic medium. For real geometry,
anisotropy or encapsulation, import a finite element solution:

```python
from neurostim.io import load_field, compare_with_point_source

field = load_field("comsol_export.csv", current_uA=100, position_scale_to_um=1e6)
compare_with_point_source(field, current_uA=100)     # raises on a unit-scale mistake
```

`compare_with_point_source` raises when the far-field ratio to the point source is off by
more than a decade, which is what a potential in mV or positions in metres produce. Pass
the `electrode` the field was solved for, so that a planar electrode is compared against
the half-space source.

Solver-native binary formats are deliberately unsupported — a CSV export cannot be
silently misparsed by a version mismatch.

## Using your own characterisation

Literature limits are a starting point, not a substitute for measuring your electrodes.

```python
from neurostim import get_material, with_measured_cic

my_pt = with_measured_cic(get_material("Pt"), 62.0, pulse_width_us=100,
                          note="EIS + voltage transient, batch 2026-03")
calc = SafetyCalculator(electrode, protocol, material=my_pt)
```

The result is marked unverified against the literature and carries your note, which is
the honest state of affairs: it is your measurement, not a published one.

Only the charge-injection limit is yours. The base material's water window and chronic
threshold stay in force by default, because dropping them would remove limits. Every
report says they are "published for Platinum (<reference>), not measured on this
electrode". To replace one with your own value, pass
`water_window=(cathodic_V, anodic_V)` or `chronic_threshold=(low_uC_cm2, high_uC_cm2)`,
which is then cited as your measurement. To drop one, pass `None`: that check then does
not run, and the incomplete-limits note says you dropped it.

## API reference

Generated from the docstrings with pdoc, and not hosted: build it locally with

```bash
python scripts/build_api_docs.py       # then open docs/api/index.html
```

CI builds it with every warning an error.

## Tests

```bash
pytest -q                              # the full suite
ruff check neurostim tests examples    # clean
mypy neurostim tests                   # clean, tests included
python scripts/provenance_audit.py     # provenance status report; --strict gates CI
python scripts/verify_transcriptions.py --strict --require-papers  # release gate; needs the local paper library
```

`tests/test_literature.py` pins the package to its sources: every Cogan Table 2 row and
its measurement pulse width, the Merrill eq. 5.1 identity, the Rose & Robblee platinum
range, the IT'IS tissue values and their unit conversion, Newman's disc resistance, and
the 0.06 cm² clinical DBS contact area. If a constant drifts from its publication,
one of these fails with the citation in the message. The model tests check each analytic
solution against an independent limit — the Pennes steady state against both its
classical unperfused form and a finite-difference solve, the point-source field against
the electrode's own access resistance.

`python scripts/mutation.py` checks that the suite notices wrong arithmetic (26 named and 160 generated
mutants; results in `docs/audit/mutation_results.json`). `CONTRIBUTING.md` has the gates, the
merge policy the mistakes ledger depends on, and the release checklist.

## Known limitations

- **Shannon** — an empirical separatrix through cat cortex histology, largely from
  macroelectrodes at frequencies below clinical rates. `k` is a choice, not a measurement.
  It is written in area and fit on discs, while Shannon states the safe limit follows
  electrode *diameter*, because charge builds up at the edges. For any non-disc geometry
  the limit is an extrapolation: the check is at best CAUTION and the limit is marked
  provisional. Its value is unchanged, since no source gives a perimeter form.
- **Charge-injection limits** — quoted at their published pulse widths with **no** scaling
  applied. A caution is raised when your protocol is more than 2× from those conditions.
  Cogan also reports ~20 % temperature dependence (20 °C vs 37 °C) and strong area
  dependence for SIROF; neither is corrected for.
- **PEDOT** — its limit is Cui & Zhou 2007's peer-reviewed 2.3–3.6 mC/cm². The 15 mC/cm²
  in Cogan 2008 comes from a meeting abstract and is not used.
- **Water window** — models the interface as a linear capacitance `C_eff`, derived from
  the material's own charge-injection limit and window. Injecting exactly the CIC then
  reaches the window edge, and the 20 µF/cm² double-layer value, which ignores
  pseudocapacitance and would contradict the measured CIC tenfold for Pt, is not used. So
  the peak clause is not an independent test of charge density. What it adds is the effect
  of a resting potential or bias. Supply a measured `capacitance_uF_cm2` to override the
  derivation.
- **DC drift** — the interface is a leak-free capacitor charged by the net unrecovered
  current, so drift times are lower bounds. The capacitor has the `C_eff` of the polarity
  the offset heads for, which for over-recovery is the one opposite the leading phase. A real interface leaks and can reach a steady
  state (Merrill 2005 §2.4). A continuous train with *any* unrecovered charge therefore
  gets a zero water-window ceiling and the headline refuses a number. That is a bound from
  the model, not a sourced damage threshold. The drift runs over the train's on-time,
  `train_duration_s × train_duty_cycle`, because the model's offset grows only while
  pulses are delivered. A real interface also relaxes during the off-time, so this is
  still conservative.
- **Monophasic delivery** — no charge-injection limit is applied, because none was
  measured on such a waveform. Charge balance FAILs, so the headline refuses a number. The
  limit-bearing ceiling is still computed, and is capped at what the same electrode and
  protocol would report biphasic.
- **Access resistance of immersed geometries** — there is no exact form for a band on an
  insulating shaft or a microwire. The equal-area sphere is used. Against a converged
  finite-volume solve it is high at every aspect, so it errs toward a larger compliance
  requirement. It is +0.3 to +1.2 % from aspect 1 to 2 (the clinical 3389 contact reads
  329.5 Ω against 327.6 Ω), +7 to +10 % at aspect 0.39–0.5, and +17 to +23 % at aspects 10
  and 0.2. A microwire takes the sphere too: within about ±1.4 % for a flat tip with
  0.25–5 wire radii of exposed shaft (−1.3 % at 2 radii), and high for longer exposures
  (+17 % at 20 radii). A flat tip with no shaft takes Newman's half-space disc instead,
  an upper bound, because the sphere is 8 % low there. Hemispherical and conical tips with
  no shaft stay on the sphere and are not checked against a solve. Ring and rectangle
  take Newman's equal-area disc, which *over*estimates them. The disc is the most
  resistive plane shape of its area, so the substitution is an upper bound: 1.34× high
  for a 10:1 strip, 4.3× for a ring 1 % as wide as it is across.
- **Compliance voltage** — without a `counter_electrode` the budget has one interface and
  one spreading resistance, which under-estimates a two-terminal pair, so the check is
  CAUTION at best. With a counter the mutual term is first-order superposition of two
  compact sources, not a solved two-body problem. The equilibrium-potential difference
  between two dissimilar materials is not modelled. No compliance-voltage measurement in
  this bibliography pins the two-terminal model. An unbalanced train's DC offset uses the
  water window's leak-free capacitor, so it is an upper bound, with one exception.
  Under over-recovery, once a leading phase already passes the window edge, the excess
  goes to electrolysis and the budget can be low. That happens only where Water window
  FAILs, so no limiting current is affected; the bound is in the compliance module
  docstring. On the active electrode it
  is capped at the window headroom, where the Water window check FAILs anyway. It is not
  capped on the counter, whose window is not assessed, or on a material with no window, so
  a continuous unbalanced train with either permits no current.
- **Counter electrode's own limits** — with a counter supplied, its charge injection is
  checked and can bind the limiting current. Its water window and chronic dissolution
  threshold are **not** assessed. A counter smaller than the active electrode carries the
  same charge at a higher density, so check those separately.
- **Thermal** — spreading-resistance heating only. Thermal tissue properties are IT'IS
  v4.2 with uncertainty; the electrical conductivity defaults to Elwassif et al.'s
  0.35 S/m, the DBS modelling convention, not IT'IS's grey-matter value, so pass the one
  you intend. The model still omits electrode and lead self-heating and any
  encapsulation layer. Gives millikelvin rises for clinical DBS parameters, well below the
  ~0.8 K peak Elwassif et al. (2006) report from a finite element model. The gap is the
  protocol's power, not missing physics: their continuous 1.56 V RMS bipolar drive
  dissipates about 5.6 mW, and fed that drive the model returns 0.83 K against their
  0.82 K (two contacts as spheres 2 mm apart, an equal power split: our modelling
  choice, not theirs). The source radius is the electrode's own electro-thermal radius,
  `1/(4πσR_access)`.
- **VTA** — a sphere is the wrong shape, and `k` spans a factor of ninety across cortical
  elements (300–27 000 µA/mm²; the result reports the radius and volume across it). The
  default is Stoney et al. 1968's pyramidal-tract mean, read from Tehovnik et al. 2006's
  figure. Fit your own.

## References

Full bibliography with DOIs in `neurostim/references.py`:

```python
from neurostim import bibliography
print(bibliography())
```

`bibliography()` is the list of record: every constant names its source there, and a PDF
report lists exactly the sources its text cites. It is generated, not maintained here,
because a hand-written list here fell eleven sources behind the code.

## Licence

MIT, in `LICENSE`. Copyright (c) 2026 Kshitij Kumar, Indian Institute of Technology Kanpur.
