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
> analytic approximations with narrow, documented validity ranges. Values that could not
> be confirmed against a primary source are flagged `PROVISIONAL` wherever they surface.

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
protocol  = StimProtocol(80, 200, 130, 1)       # µA, µs, Hz, s
calc = SafetyCalculator(electrode, protocol, compliance_V=10.0)

print(calc.describe())
```

```
Overall: FAIL
Limiting current: 70.69 uA (Pt charge-injection limit)

[         PASS] Shannon criterion: k = -0.04 at threshold 1.70, 7.44x headroom
[         FAIL] Charge injection limit: 56.59 uC/cm^2 exceeds the 50 uC/cm^2 limit for Pt
[         FAIL] Water window: peak -2.83 V leaves the window by 2.23 V
[         PASS] Charge balance: biphasic, fully charge-balanced
[         PASS] Compliance voltage: 3.43 V of 10.00 V (34 % used)
```

The `report()` dictionary from the 0.1.0 prototype still works and returns a superset of
its original keys.

## Desktop application

```bash
neurostim-gui          # or: python -m neurostim.gui
```

Electrode and protocol inputs on the left, live results on the right: status table, full
text assessment, and an embedded Shannon safe-operating-area plot. Recomputes on every
change. Exports the PDF report and the four-panel summary figure.

## What it computes

| Check | Basis | Source |
|---|---|---|
| Shannon criterion | `k = log₁₀(Q²/A)`, damage separatrix | Shannon 1992; Merrill 2005 eq. 5.1 |
| Charge-injection limit | Material CIC vs applied charge density | Cogan 2008 Table 2 |
| Water window | Interfacial potential excursion vs electrolysis limits | Cogan 2008; Merrill 2005 |
| Charge balance | Net DC per pulse and over the train | Merrill 2005 |
| Compliance voltage | `I(R_access + R_lead) + ΔV_polarisation` | Newman 1966 |

Plus models, each documenting its own validity range:

- **Field** — point-source potential and gradient, exact for a sphere
- **Thermal** — Pennes bioheat, analytic steady state plus an implicit transient solver
- **Strength–duration** — Lapicque and Weiss forms, with fitting routines
- **VTA** — current–distance activation radius (the weakest model here; read its docstring)

Geometries: disc, ring, rectangle, cylindrical band, microwire (flat/hemispherical/conical
tip), sphere, hemisphere, plus linear and grid arrays.

## Corrections to the 0.1.0 prototype

Tracing every constant to its primary source changed four of the five material values:

| Material | 0.1.0 | current | Why |
|---|---|---|---|
| `SS` | 0.05 mC/cm² | 0.02–0.04 | Traced to Riedy & Walter 1996; 40 µC/cm² safe, 20 non-faradaic. Stainless steel is absent from Cogan Table 2 |
| `Pt` | 0.10 | 0.05–0.15 | Cogan reports a range, from Rose & Robblee 1990 at 200 µs |
| `PtIr` | 0.15 | 0.05–0.15 | Cogan gives **one** row for "Pt and PtIr alloys". The separate higher value was not supported |
| `PEDOT` | 5.0 | 3.6–15.0 | Cogan's 15 mC/cm² is from a **conference abstract**; the low end is Nyberg et al.'s peer-reviewed value |
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

## Uncertainty

Published limits are ranges, not numbers. Cogan gives platinum as a factor of three.
Rather than hide that behind the `policy` setting, the assessment reports both:

```
Limiting current: 70.69 uA (Pt charge-injection limit)
  across published ranges: 70.69-212.1 uA (Shannon k 1.5-2.0, full material range)
```

```python
assessment.limiting_current_interval_uA     # Interval(70.69, 212.1)
assessment.charge.limit_interval_uC_cm2     # Interval(50.0, 150.0)
```

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
compare_with_point_source(field, current_uA=100)     # sanity-check units and validity
```

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

## Tests

```bash
pytest -q                              # 220 tests
ruff check neurostim tests examples    # clean
mypy neurostim                         # clean
python scripts/provenance_audit.py     # provenance status report
```

`tests/test_literature.py` pins the package to its sources: every Cogan Table 2 row and
its measurement pulse width, the Merrill eq. 5.1 identity, the Rose & Robblee platinum
range, the IT'IS tissue values and their unit conversion, Newman's disc resistance, and
the 0.06 cm² clinical DBS contact area. If a constant drifts from its publication,
one of these fails with the citation in the message. The model tests check each analytic
solution against an independent limit — the Pennes steady state against both its
classical unperfused form and a finite-difference solve, the point-source field against
the electrode's own access resistance.

## Known limitations

- **Shannon** — an empirical separatrix through cat cortex histology, largely from
  macroelectrodes at frequencies below clinical rates. `k` is a choice, not a measurement.
- **Charge-injection limits** — quoted at their published pulse widths with **no** scaling
  applied. A caution is raised when your protocol is more than 2× from those conditions.
  Cogan also reports ~20 % temperature dependence (20 °C vs 37 °C) and strong area
  dependence for SIROF; neither is corrected for.
- **PEDOT's headline limit is not peer reviewed** — it comes from a meeting abstract, and
  is flagged `NOT PEER REVIEWED` at every point of use.
- **Water window** — models the interface as a pure double-layer capacitance. Conservative
  for pseudocapacitive materials such as Pt and iridium oxide, where part of the injected
  charge goes into reversible surface reactions instead.
- **Thermal** — spreading-resistance heating only. Tissue properties are now IT'IS v4.2
  with uncertainty, but the model still omits electrode and lead self-heating and any
  encapsulation layer. Gives millikelvin rises for clinical DBS parameters, well below the
  ~0.8 K peak Elwassif et al. (2006) report from a full finite element model. **That gap is
  not reconciled.** Treat the output as an order-of-magnitude floor.
- **VTA** — a sphere is the wrong shape, `k` spans an order of magnitude across studies,
  and the default value was read from a secondary summary. Fit your own.

## References

Full bibliography with DOIs in `neurostim/references.py`:

```python
from neurostim import bibliography
print(bibliography())
```

Primary sources: Shannon 1992; McCreery et al. 1990; Merrill, Bikson & Jefferys 2005;
Cogan 2008; Rose & Robblee 1990; Riedy & Walter 1996; Brummer & Turner 1977; Rand & Woods
1971; Newman 1966; Pennes 1948; Elwassif et al. 2006; Lapicque 1907; Weiss 1901; Stoney
et al. 1968; Tehovnik et al. 2006; Kuncel & Grill 2004.

## Licence

MIT.
