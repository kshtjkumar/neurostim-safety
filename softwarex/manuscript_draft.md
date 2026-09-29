<!--
DRAFT PRODUCED WITH GENERATIVE AI (Claude, Anthropic) FOR THE AUTHOR TO REWRITE.
Elsevier policy: AI may not generate manuscript sections without genuine author
contribution. Before submitting, rewrite every section in your own words and judgment,
check every claim, fill every [AUTHOR: ...] marker, delete this comment, and paste the
result into the official template (softwarex-osp-template.docx, version 6, March 2026).
Word limit 4000 (sections 1-5; metadata, tables, figures and references excluded).
This draft is ~1,330 words in sections 1-5 (room to expand, especially Impact). Figures: figures/figure1_architecture.* and
figures/figure2_dbs3389_summary.* (max 6 allowed).
-->

# neurostim-safety: electrode and tissue safety limits for neural stimulation, each traced to its source

Kshitij Kumar
Indian Institute of Technology Kanpur, India
[AUTHOR: postal address and e-mail for the author line, as the template asks]

## Abstract

`neurostim-safety` is an open-source Python package that assesses whether a
neural-stimulation protocol is safe for the tissue and for the electrode that delivers
it. From an electrode's geometry and material and a protocol's current, pulse width,
rate, train and charge recovery, it evaluates nine established tissue-damage,
electrochemical and instrument limits and reports the highest current at which none of
them fails, or refuses to report one when no current is safe. Every constant carries its
primary source and the conditions it was measured under, and those conditions travel
into every report, flagging a limit applied outside them as provisional. Text, PDF,
JSON, CSV, figure and desktop outputs are provided. (≈100 words)

## Keywords

neural stimulation; charge injection; electrode safety; deep brain stimulation;
Shannon criterion; Python

## Code metadata

| Nr | Code metadata description | Metadata |
|---|---|---|
| C1 | Current code version | v0.16.0 (https://github.com/kshtjkumar/neurostim-safety/releases/tag/v0.16.0) |
| C2 | Permanent link to code/repository used for this code version | https://github.com/kshtjkumar/neurostim-safety |
| C3 | Legal code license | MIT License |
| C4 | Code versioning system used | git |
| C5 | Software code languages, tools and services used | Python (≥ 3.10); NumPy, SciPy, Matplotlib, pandas; optional PyQt6 (desktop GUI) and ReportLab (PDF reports); pytest, Ruff, mypy and GitHub Actions for testing |
| C6 | Compilation requirements, operating environments and dependencies | Pure Python, no compilation. Linux, macOS (tested in CI on Python 3.10–3.14 and 3.12 respectively); Windows expected but not tested. `pip install -e ".[all]"` installs the library, GUI and PDF support |
| C7 | If available, link to developer documentation/manual | https://github.com/kshtjkumar/neurostim-safety#readme (README); API reference generated from docstrings with `python scripts/build_api_docs.py` [AUTHOR: host the API reference, e.g. GitHub Pages, if you want a public link] |
| C8 | Support email for questions | https://github.com/kshtjkumar/neurostim-safety/issues [AUTHOR: SoftwareX may insist on an e-mail address here] |

## 1. Motivation and significance

Electrical stimulation of the nervous system — deep brain stimulation, cortical and
spinal microstimulation, cochlear and retinal prostheses — is bounded by two families of
limits. Tissue limits describe the charge that damages neurons, most prominently the
Shannon criterion fitted to McCreery's cat-cortex data [1, 2]. Electrode limits describe
the charge an electrode can inject reversibly before irreversible Faradaic reactions,
gas evolution or dissolution begin [3, 4]. Which family binds depends on electrode size
[5]: large clinical contacts are usually limited by the tissue, microelectrodes by the
electrode or by a charge-per-phase threshold that the Shannon criterion does not
capture.

These limits are scattered across the electrochemistry and neurophysiology literature
and are routinely quoted as single numbers, stripped of the conditions under which they
were measured. A charge-injection capacity measured in saline at 200 µs need not hold in
tissue at 50 µs: in vivo, platinum's capacity is several-fold lower than in vitro [6].
Checking a protocol therefore means recomputing each limit by hand, from several papers,
for each electrode, and it is easy to apply a value outside the conditions it was
measured under without noticing. [AUTHOR: add one or two sentences on why this mattered
in your own work — e.g. the rodent motor-cortex microstimulation and MER experiments —
and what you did before writing the package.]

`neurostim-safety` performs this calculation once, reproducibly, with every number
traceable to a page of a paper. A user describes the electrode and the protocol; the
package evaluates every applicable limit, reports which one binds and at what current,
and states explicitly when a limit is applied outside the conditions it was measured
under. The intended users are experimenters designing stimulation protocols, engineers
choosing electrode materials and sizes, and reviewers checking the safety argument of a
methods section.

Related work. [AUTHOR: verify and complete. Suggested starting points: finite-element
environments (COMSOL, Sim4Life) model fields and heating but do not encode the
literature's damage and charge-injection limits; DBS toolboxes such as Lead-DBS and
OSS-DBS estimate volumes of tissue activated rather than safety limits; published
calculators and spreadsheets typically quote one limit per material without its
measurement conditions. State what, to your knowledge, does not exist.]

## 2. Software description

### 2.1 Software architecture

The package is organised in layers (Fig. 1).

*Inputs.* Electrode geometries (disc, ring, rectangle, cylindrical band, microwire,
sphere, hemisphere and arrays of these) each compute their area and access resistance,
using exact solutions where they exist (e.g. Newman's disc [7]) and bounding
approximations, flagged as such, otherwise. Nine electrode materials are built in, each
with its charge-injection range, water window and chronic threshold; a user-measured
charge-injection capacity can be supplied, with the base material's other limits kept
and labelled as inherited. A protocol specifies current, pulse width per phase,
frequency, train duration and duty cycle, waveform, return-phase ratio and charge
recovery.

*Safety core.* Nine checks are evaluated for every assessment: the Shannon criterion
[1]; the material charge-injection limit [3, 4]; the water window, including the DC drift
of an incompletely recovered train; the validated envelope of the data behind the
Shannon fit; current density against an electroporation threshold [8, 9]; the
microelectrode charge-per-phase threshold [5]; chronic degradation; charge balance
[10]; and the stimulator's compliance voltage, optionally with a counter electrode, which
adds a tenth check on the counter's own charge injection. Each check returns a status,
the current at which it would fail, the published range of that ceiling, and whether it
rests on an unconfirmed constant or model.

*Result.* The limiting current is the highest amplitude at which no limit-bearing check
fails. It is floored to the printed precision, so the printed value passes the checks it
names, and it is accompanied by an interval across the published ranges (for example
Shannon's k from 1.5 to 2.0). When no amplitude is safe — for example a monophasic
waveform that recovers no charge — the package reports a refusal naming the check rather
than a number. PROVISIONAL and INCOMPLETE flags mark results that rest on unconfirmed
inputs or on a check that could not run.

*Supporting layers.* Literature data modules hold every constant with its source, page
and measurement conditions (pulse width, polarity, electrolyte, area basis); these
conditions are compared with the protocol at assessment time. Models include steady and
transient Pennes bioheat heating, strength–duration fits with confidence intervals, a
current–distance activation estimate and an interval-arithmetic layer with outward
rounding. Finite-element field solutions can be imported and compared with the analytic
estimates.

*Outputs.* The same assessment is rendered as a text summary, a PDF report with methods
text and bibliography, JSON and an audit record carrying a SHA-256 digest of inputs,
constants and answer, batch CSV tables and current sweeps, publication figures
(SVG/PDF/TIFF), and a PyQt6 desktop application.

[Figure 1 here. Caption: Architecture of neurostim-safety. Sourced inputs are evaluated
by nine safety checks; the result is a single floored limiting current with its interval
and flags, or a refusal, which every output renders identically.]

### 2.2 Software functionalities

- **Protocol assessment**: `SafetyCalculator(electrode, protocol, ...).assess()` returns
  every check and the limiting current; `.describe()` prints them with the conditions
  and source of each limit.
- **Traceability**: `neurostim.bibliography()` lists every source used; each check's
  detail names its constant, citation and measurement conditions.
- **Condition checking**: a limit applied outside its measured pulse width, polarity or
  medium is flagged provisional; the in-vivo derating of platinum is applied from the
  measured in-vitro/in-vivo ratio [6].
- **Uncertainty**: published ranges propagate to an interval on the limiting current.
- **Batch and sweeps**: CSV input of many protocols and current sweeps, with failed rows
  reported rather than silently dropped.
- **Reports and reproducibility**: PDF reports and JSON audit records whose digest lets
  a report be regenerated and verified with a later version.
- **Desktop GUI** for interactive use without programming.

### 2.3 Sample code snippet

```python
from neurostim import SafetyCalculator, StimProtocol, get_preset
from neurostim.io import build_report

contact = get_preset("dbs_3389").electrode          # 1.27 mm x 1.5 mm PtIr band
protocol = StimProtocol(3000, 60, 130, 1)           # uA, us per phase, Hz, s
calc = SafetyCalculator(contact, protocol, compliance_V=10.0, medium="in_vivo")
print(calc.describe())
build_report(calc, "dbs_report.pdf")
```

## 3. Illustrative examples

*Example 1: a deep brain stimulation contact.* For a Medtronic 3389-style contact
(PtIr cylindrical band, 1.27 mm diameter, 1.5 mm height, 0.0598 cm²) driven at 3 mA,
60 µs per phase and 130 Hz in vivo, the package reports an overall CAUTION with a
limiting current of 10.94 mA, set by the in-vivo-derated platinum-iridium
charge-injection limit; the interval across published ranges is 10.94–16.41 mA. The
Shannon criterion passes with 7.6-fold headroom but is marked as applied outside its
validated envelope, because the criterion was fitted on disc electrodes and this contact
is a band. The limit is flagged PROVISIONAL because the binding constant carries a
caveat. Fig. 2 shows the package's own summary figure for this case.

[Figure 2 here. Caption: Output of neurostim-safety for a DBS contact (3 mA, 60 µs per
phase, 130 Hz, in vivo). (a) The protocol on the Shannon safe-operating plane with
McCreery's data. (b) Permitted current per check against requested current, with the
binding limit. (c) Material charge-injection limits under the conservative policy. (d)
Potential and field around the contact.]

*Example 2: a cortical microelectrode.* [AUTHOR: replace with your own experiment, e.g.
a stainless-steel ring (330/270 µm, 0.000283 cm²) in rodent motor cortex at 100 µs per
phase and 130 Hz. Because the area is below the micro/macro boundary, the Shannon
criterion is not applied and the microelectrode charge-per-phase threshold (≈4 nC)
binds: the limiting current is 40 µA, so a 40 µA protocol sits exactly at the limit.
State what this changed in your protocol.]

## 4. Impact

[AUTHOR: this is the section reviewers weigh most. It must describe real use; do not
state anything that has not happened. Suggested content, to be written from your own
experience:]

- **Research questions it enables**: systematic comparison of electrode materials and
  sizes against every applicable limit at once; checking where tissue versus electrode
  limits bind across a design space; auditing published protocols against the limits
  with their measurement conditions.
- **Improvement over existing practice**: one reproducible calculation replaces
  hand-computed limits from several papers; the conditions of each limit are checked
  rather than assumed; reports record inputs, constants and a digest so that a methods
  section's safety argument can be regenerated.
- **Correctness and verification**: the package was audited before release, and the
  full record of findings, fixes and independent reviews is in the repository. The test
  suite (≈1,700 tests) checks constants against their sources, reproduces published
  results from published inputs (for example, the Pennes model gives a 0.83 K peak rise
  for the drive of Elwassif et al. [11] against their finite-element 0.82 K), checks the
  headline limit against an independent search, and is gated in continuous integration
  on branch coverage (84.8 %) and mutation testing (85.6 % of pre-registered generated
  mutants killed).
- **Use**: [AUTHOR: your own studies using it (rodent motor-cortex stimulation, MER
  datasets), collaborators or labs using it, any talks or preprints. If the package is
  new and not yet used beyond your work, say so plainly.]

## 5. Conclusions

`neurostim-safety` brings the tissue-damage, electrochemical and instrument limits on
neural stimulation into one reproducible calculation, with every constant traceable to
its source and its measurement conditions checked against the protocol. It reports a
single, floored limiting current with its uncertainty, flags where a limit is applied
outside its evidence, and refuses to report a number when no amplitude is safe. Its
limits are the published ones, with their known weaknesses, documented in the
repository: it is a research and design aid, not a regulatory or clinical tool.
[AUTHOR: planned extensions, if any.]

## Declaration of competing interest

[AUTHOR: e.g. "The author declares no known competing financial interests or personal
relationships that could have appeared to influence the work reported in this paper."]

## Acknowledgements

[AUTHOR: optional — colleagues, funding.]

## Declaration of generative AI and AI-assisted technologies in the manuscript preparation process

[AUTHOR: must be truthful and specific. Suggested wording, edit to match what you did:]
During the preparation of this work the author used Claude (Anthropic; Claude Opus 5 and
Opus 5.5, via Claude Code) to audit and repair the software, to write most of its test
suite and continuous-integration configuration, to review each change independently, and
to produce an initial draft of this manuscript and its figures. The author substantially
rewrote the manuscript, made the modelling and source decisions recorded in the
repository, and reviewed and validated the code and text. After using this tool, the
author reviewed and edited the content as needed and takes full responsibility for the
content of the publication.

## References

[1] R.V. Shannon, A model of safe levels for electrical stimulation, IEEE Trans. Biomed.
Eng. 39 (1992) 424–426. https://doi.org/10.1109/10.126616
[2] D.B. McCreery, W.F. Agnew, T.G.H. Yuen, L. Bullara, Charge density and charge per
phase as cofactors in neural injury induced by electrical stimulation, IEEE Trans.
Biomed. Eng. 37 (1990) 996–1001. https://doi.org/10.1109/10.102812
[3] S.F. Cogan, Neural stimulation and recording electrodes, Annu. Rev. Biomed. Eng. 10
(2008) 275–309. https://doi.org/10.1146/annurev.bioeng.10.061807.160518
[4] T.L. Rose, L.S. Robblee, Electrical stimulation with Pt electrodes. VIII.
Electrochemically safe charge injection limits with 0.2 ms pulses, IEEE Trans. Biomed.
Eng. 37 (1990) 1118–1120. https://doi.org/10.1109/10.61038
[5] S.F. Cogan, K.A. Ludwig, C.G. Welle, P. Takmakov, Tissue damage thresholds during
therapeutic electrical stimulation, J. Neural Eng. 13 (2016) 021001.
https://doi.org/10.1088/1741-2560/13/2/021001
[6] R.T. Leung, M.N. Shivdasani, D.A.X. Nayagam, R.K. Shepherd, In vivo and in vitro
comparison of the charge injection capacity of platinum macroelectrodes, IEEE Trans.
Biomed. Eng. 62 (2015) 849–857. https://doi.org/10.1109/TBME.2014.2366514
[7] J. Newman, Resistance for flow of current to a disk, J. Electrochem. Soc. 113 (1966)
501. https://doi.org/10.1149/1.2424003
[8] A. Butterwick, A. Vankov, P. Huie, Y. Freyvert, D. Palanker, Tissue damage by pulsed
electrical stimulation, IEEE Trans. Biomed. Eng. 54 (2007) 2261–2267.
https://doi.org/10.1109/TBME.2007.908310
[9] A.M. Kuncel, W.M. Grill, Selection of stimulus parameters for deep brain
stimulation, Clin. Neurophysiol. 115 (2004) 2431–2441.
https://doi.org/10.1016/j.clinph.2004.05.031
[10] D.R. Merrill, M. Bikson, J.G.R. Jefferys, Electrical stimulation of excitable
tissue: design of efficacious and safe protocols, J. Neurosci. Methods 141 (2005)
171–198. https://doi.org/10.1016/j.jneumeth.2004.10.020
[11] M.M. Elwassif, Q. Kong, M. Vazquez, M. Bikson, Bio-heat transfer model of deep brain
stimulation induced temperature changes, in: Proc. 28th Annu. Int. Conf. IEEE EMBS,
2006, pp. 3580–3583. https://doi.org/10.1109/IEMBS.2006.259425
[12] [AUTHOR: software citation — the Zenodo DOI of the v0.16.0 release, once archived]

[AUTHOR: every reference above was taken from the package's paper.bib; check author
lists, volumes and pages against each paper before submitting.]
