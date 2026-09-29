---
title: 'neurostim-safety: electrode and tissue safety limits for neural stimulation, each traced to its source'
tags:
  - Python
  - neural stimulation
  - electrochemistry
  - charge injection
  - deep brain stimulation
  - neural engineering
authors:
  - name: Kshitij Kumar
    affiliation: 1
    corresponding: true
affiliations:
  - name: Indian Institute of Technology Kanpur, India
    index: 1
date: 28 September 2026
bibliography: paper.bib
---

# Summary

`neurostim-safety` is a Python package that assesses whether a stimulation protocol is
safe for the tissue and the electrode that deliver it. Given an electrode (geometry and
material) and a protocol (current, pulse widths, rate, train and recovery), it runs
nine checks:

- the Shannon tissue-damage criterion [@shannon1992; @mccreery1990];
- the material's charge-injection limit [@cogan2008; @rose_robblee1990];
- the water window, with the DC drift of an unbalanced train;
- the envelope of the data behind the Shannon fit;
- current density [@butterwick2007; @kuncel_grill2004];
- the microelectrode charge-per-phase threshold [@cogan2016];
- chronic degradation;
- charge balance [@merrill2005];
- the stimulator's compliance voltage.

It reports the highest amplitude at which none of the limit-bearing checks fails. A
counter electrode adds a tenth check. The number is floored, so the amplitude printed
passes the checks it names. The package refuses to print a number when no amplitude is
safe, for example for a waveform that recovers no charge.

Every constant carries its primary source and the conditions it was measured under:
pulse width, polarity, electrolyte and area. Those conditions follow the value into
every report. A ceiling taken outside them is flagged as provisional, not silently
applied. A published range, such as the spread of a material's limit or of Shannon's
*k*, is carried through as an interval.

Supporting models:

- steady and transient Pennes bioheat heating. Given the drive of @elwassif2006, it
  returns a peak rise of 0.83 K, against the 0.82 K of their finite element model;
- access resistance from exact or bounding geometry solutions [@newman1966];
- strength-duration fits with confidence intervals;
- a current-distance activation estimate.

# Statement of need

Charge-injection and tissue-damage limits are scattered across the electrochemistry
and neurophysiology literature. They are routinely quoted without the pulse width,
polarity or medium they depend on. A limit measured in saline at 200 µs need not hold in
tissue at 50 µs; in vivo, platinum's charge-injection capacity is several-fold lower
[@leung2015]. Tissue and electrode limits can bind in either order, depending on
electrode size [@cogan2016]. Without a tool, these limits have to be recomputed by hand,
one at a time. The package gives one reproducible calculation in which every number can
be traced to a page of a paper.

Each report carries the package version, every setting, and a SHA-256 digest of the
inputs, constants and answer. A report can therefore be regenerated and checked.

# Verification

The package was audited and repaired before this submission, and the record is in the
repository (`CODE_MISTAKES_LOG.md`, `docs/audit/`). The test suite checks:

- constants against their sources;
- published results reproduced from published inputs;
- the headline limit against an independent binary search over the checks' own
  verdicts;
- models against closed forms and independent finite-difference solutions.

Continuous integration gates branch-point coverage (84.8 %), type checking of the
package and its tests, a provenance audit, and a byte-for-byte check of the README's
generated transcript. A mutation harness kills all 26 named mutants recovered from the
audit, and 85.6 % of 160 generated mutants on a seed registered before it was run.

# Limitations

The package is a research and design aid, not a regulatory tool. Its limits are the
published ones, with their known weaknesses:

- **Provisional flags.**
  - The Shannon criterion was fit on disc electrodes, so for any other geometry it is at
    best CAUTION.
  - Every current-density verdict is provisional.
  - A compliance check without a counter electrode assumes a monopolar budget and is
    never an unqualified PASS.
  - A limit whose in-vivo derating was never measured at the requested pulse width is
    marked provisional.
- **Open gaps in the record.**
  - The generated mutation score, 85.6 %, is below its 90 % target (ledger 182), and ten
    of its survivors are untested behaviour (ledger 188).
  - The Lapicque confidence interval is withheld when it lies below every width tested,
    or when it does not bound the chronaxie, and carries a caveat on designs spanning
    less than 8x, where its measured coverage can be far below nominal (ledger 183;
    ledger 192). Designs spanning 8x or more cover 0.69-1.00 over chronaxies 50-500 us
    and 2-20 % noise in the validation grid, lowest when every width is well above the
    chronaxie.
  - Three data gaps have no source: TIROF's and SS316LVM's pulse widths, and Ta₂O₅'s
    water window.
- **Values not verified against their primary source.**
  - Titanium nitride's charge-injection limit is Cogan's table value; its underlying
    measurement [@weiland2002] was not read from the paper.
  - The tissue thermal properties come from the IT'IS database [@itis_v42], cited as
    Hasgall et al. (2025). The record its DOI resolves to lists the IT'IS Foundation,
    2024.
  - Two limits for 316LVM stainless steel rest on sources that @riedy_walter1996 cite as
    their references 5 and 8, which were not read. They are recorded as cited through
    that paper.

# AI usage disclosure

Generative AI was used extensively in this work. Claude (Anthropic; models Claude Opus 5
and Claude Opus 5.5, run through the Claude Code command-line tool) carried out the
pre-publication audit and most of the subsequent changes: it read the package and its
primary sources, logged the defects in `CODE_MISTAKES_LOG.md`, planned and wrote the
fixes, wrote most of the test suite, the mutation harness and the continuous-integration
configuration, independently reviewed each phase of changes, and drafted the
documentation and this manuscript. Every AI-assisted commit carries a `Co-Authored-By:
Claude` trailer, and the audit trail (`docs/audit/`) records each finding, decision and
review. Modelling and source choices that the literature did not settle were made by the
author, and are recorded in the fix plan.

<!-- AUTHOR: before submitting, (1) add any other AI tools used during the package's
initial development, and (2) replace this comment with a statement you can truthfully
make, e.g. "The author reviewed, modified and validated all AI-generated code,
documentation and text, and takes full responsibility for the content." -->

# References
