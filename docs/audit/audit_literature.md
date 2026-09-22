# Literature Audit — `neurostim_safety`

**Scope.** Every literature-derived numeric constant in `neurostim/materials.py`,
`neurostim/references.py`, all twelve `neurostim/data/*.py` modules, `neurostim/audit.py`,
the conductivity constants in `models/field.py` and `models/thermal.py`, and the README
tables — checked against the primary source each one cites. Sources read from the PDFs in
`papers_stim_calc_ref/` (plain-text extractions, PDF pages where the extraction was
garbled); 15 DOIs resolved against Crossref plus one against DataCite. Read-only: no file
in the repository was modified.

---

## Summary

### Counts by verdict

Counted per table row below (one row ≈ one constant, condition set, or DOI); ≈300 checks.

| verdict | count | note |
|---|---|---|
| **MATCH** | ≈258 | value, units and conditions agree with the source |
| **CONDITION-DROPPED** | 9 | number right, a condition that sets it is not recorded |
| **MISMATCH** | 8 | code disagrees with the source it cites |
| **DERIVED** (presented as read) | 7 | computed by the package, not printed in the source |
| **UNVERIFIABLE** | 24 | source absent or inaccessible; see section 17 |
| **UNIT-ERROR** | **0** | every unit conversion recomputed by hand was correct |

**No unit errors were found anywhere.** mC/cm^2 ↔ uC/cm^2, uC/mm^2 ↔ uC/cm^2, nC/phase over
um^2 → uC/cm^2, ps/ns/us/ms → s, mm → cm, S/m, ml/min/kg → 1/s, and °C → K were each
recomputed independently and all agree.

### The package's central claim

> "Every literature-derived constant carries its primary source **and the conditions under
> which it was measured**."

**Largely true, with four real exceptions.** The Cogan 2008 Table 2 transcription is exact;
the deliberate departures from Cogan to the primaries (AIROF, PEDOT, Ta2O5) are each
documented and each checks out against the primary text; Gabriel Part III Table 1, McCreery
1990 Table I, McCreery 1995, Riedy & Walter's Table I, ISO Table 101 and Elwassif Table I
are transcribed without a single numeric error. The exceptions are S-1, S-2, S-3 and S-6
below.

### Not-a-MATCH findings, severity ranked

| # | severity | finding | where |
|---|---|---|---|
| **S-1** | **high** | **Pt in-vivo derating 2-14x contradicts the source that publishes its own.** Leung et al. (2014) state "in vivo was between **8.7 times less (200 us) and 3.2 times less (3200 us)** ... determined by dividing the in vitro Qinj by the mean in vivo Qinj **at the respective pulsewidths**". The code's 2 and 14 come from dividing best-in-vitro by worst-in-vivo **across mismatched pulse widths** — the exact comparison the authors pre-empted. Low bound too permissive (2 vs 3.2), high bound above even Cogan 2016's "as much as a factor of 10" | `data/cogan2016.py:112-118`, F-10 |
| **S-2** | **high** | **The 316LVM recommendation is misattributed, and it gates behaviour.** The package says three times that Riedy & Walter's "own year-long experiment concludes 20 uC/cm^2 is the maximum feasible density". The paper says "It has recently been suggested that **tissue surrounding the stimulating electrode is not damaged** ... below 0.2 uC/mm^2 (20 uC/cm^2) **[8]**. **Based on this report**, 20 uC/cm^2 appears to be the maximum..." — a **tissue-damage** figure from a cited book chapter, not their corrosion result. Their corrosion conclusion is the milder "20 uC/cm^2 may still be suitable for many long-term intermittent in vivo applications". Drives `recommended_policy` and `exceeds_recommendation()` | `data/riedy_walter1996.py:8-13`, `materials.py:672-692`, F-26 |
| **S-3** | **high** | **The SS316LVM `MeasuredRange` attaches one experiment's conditions to another experiment's numbers.** Riedy & Walter never measured a 316LVM charge-injection capacity: 40 uC/cm^2 "has been reported" (their refs 5-7) and 20 uC/cm^2 is what "is available for nonfaradic charge transfer" (their ref 8). The stored 100 us / 60 pps / interstitial-fluid / 0.016 cm^2 conditions describe the **corrosion** experiment run at those densities. Nothing in the record says so | `materials.py:653-686`, F-27 |
| **S-4** | **high** | **README PEDOT row is stale by 4.2x at the top end.** README "Corrections" table says PEDOT is now **3.6-15.0 mC/cm^2**; `materials.py` holds **2.3-3.6**, referenced to Cui & Zhou, with a note explicitly rejecting the 15 mC/cm^2 abstract value | README:91 vs `materials.py:534-539`, F-46 |
| **S-5** | **high** | **Elwassif provenance defect: the citation resolves to a different paper than the one transcribed.** `data/elwassif2006.py` states its values are "read from the conference paper" (Proc. 28th IEEE EMBS 2006, pp. 3580-3583) — and the repo PDF is that paper — but `references.py` defines `elwassif2006` as the **J Neural Eng 3(4):306-315** article, with that journal's DOI, pages, volume and PMID. Verified: the DOI resolves to the journal article. All 12 Table I rows render a citation to the wrong publication | `references.py:701-714`, F-18 |
| **S-6** | **medium** | **Butterwick: the module re-fits an exponent the source publishes.** `FITTED_DURATION_EXPONENT = -0.4429` is derived from two abstract anchor points and used as the **default**. Butterwick prints the actual fits: "the power fit slopes are **t^-0.52 and t^-0.48 in the chronic regime**, and t^-0.49 and t^-0.41 with the single shots on CAM and retina". For the exact case modelled — retina, sustained — the source's own fit is **-0.48**, which appears nowhere in the module | `data/butterwick2007.py:70-73`, F-14 |
| **S-7** | **medium** | **AIROF derating evidence string misquotes Hu et al. (2006).** The code says "in vitro 3-4 mC/cm^2 is about ten times what **the same films deliver in vivo**". Hu says 3-4 mC/cm^2 is "about ten times larger than what **Pt microelectrodes** can typically produce", citing another paper; Hu's *own* in vitro values are 1.18 and 1.69 mC/cm^2. The separate in-vivo sentence ("the in vivo value is about 10 % of the in vitro ones") does support the factor of 10 — the number survives, the sentence welds two different claims together | `data/cogan2016.py:119-124`, F-10 |
| **S-8** | **medium** | **SIROF derating range widened past its cited source.** Kane et al. (2013) state "the maximum charge capacity in vivo was reduced by a **factor of 2-3**". The code stores **2-4** with `evidence` naming only Kane; the 4 is Cogan 2016's review figure | `data/cogan2016.py:125-130`, F-10 |
| **S-9** | **medium** | **README claims two provenance flags that never fire.** "Values that could not be confirmed ... are flagged `PROVISIONAL` wherever they surface" — **no shipped value carries the flag** (run output: `not verified: []`). "PEDOT's headline limit ... is flagged `NOT PEER REVIEWED` at every point of use" — the abstract value **is not used at all**, and nothing in the database has an unreviewed CIC reference (`not peer reviewed: []`). The machinery works; the README describes a state the code left behind | README:15, 205-206, F-38/F-39 |
| **S-10** | **medium** | **`audit.py` omits the provenance and conditions from the reproducibility record.** The `constants` block captures low/high/units/reference/pulse_width only. `cic.verified` (the PROVISIONAL flag), `area_basis`, `waveform`, `bias`, `medium`, `temperature_C`, `measured_area_cm2`, the polarity sub-ranges and `recommended_policy` are all absent from the digest payload — i.e. exactly the conditions the package's opening paragraph says are the point | `audit.py:121-139`, F-40 |
| **S-11** | **medium** | **Two Ta2O5 designs carry a pulse width they were not measured at.** The etched-Ta 2.6 uC/mm^2 is Table III's best-reported column, which `materials.py` itself argues is "a **slow-charge figure**, not a pulsed one" — the two modules contradict each other. The etched-Ti 6.3 uC/mm^2 was measured with an **AC capacitance bridge** (Table I, "1570 (AC)"; footnote d). Both are tagged `pulse_width_us=200.0` | `data/ta2o5_capacitor.py:219,234`, F-30 |
| **S-12** | **medium** | **McCreery 2010 drops the four conditions that make 4 nC/phase mean anything**: pulse width **200 us**, interpulse bias **+0.6 V** (applied specifically to raise charge capacity), electrode area **2000 +/- 150 um^2**, and **cathodic** pulses. Separately, `DAMAGE_RADIUS_HALF_DUTY_UM = 60` is presented as a stimulation damage radius when the source says control (insertion) loss "was responsible for **most of the neuronal loss within 150 um** of the electrodes pulsed with the 50 % duty cycle" | `data/mccreery2010.py`, F-8/F-9 |
| **S-13** | **medium** | **Butterwick's d^-2 size correction was measured on single pulses only** ("These measurements were performed with **only one pulse** of duration 60 us on CAM and 600 us on the retina"), and its absolute anchors (139 uA on retina, 55 uA on CAM below 200 um) are not carried. The code applies the correction unconditionally, on top of the 50-pulse saturated default. The source also shows the duration exponent itself varies with size (t^-0.48 at 1 mm vs t^-0.29 at 0.115 mm), so the two corrections are not independent as the code assumes | `data/butterwick2007.py:145-150`, F-15 |
| **S-14** | **low** | `separating_k_range()` returns a **zero-width band**: highest safe surface point k = log10(5)+log10(10) = **1.69897**, lowest damaging/partial k = log10(1)+log10(50) = **1.69897**. The docstring's claim that "any separatrix has to fall inside this band" would admit only k = 1.699 and exclude every k the package and literature use | `data/mccreery1990.py:241-253`, F-3 |
| **S-15** | **low** | Ta2O5 docstring is **2x off** on a derived density: "5 nC ... on a 1e-4 mm^2 electrode, **which is 10,000 uC/cm^2 and 50 A/cm^2**". Those densities are the paper's, but for its introduction's **0.5e-6 cm^2 = 5e-5 mm^2** electrode. On the coded 1e-4 mm^2 it is 5,000 uC/cm^2 and 25 A/cm^2. The constant itself (Table III's idealized area) is correct | `data/ta2o5_capacitor.py:48-50`, F-28 |
| **S-16** | **low** | `THERMAL_CONDUCTIVITY_RANGE_W_PER_MK = (0.5, 0.6)` **narrows** Elwassif's Table I sweep, which runs 0.45, 0.50, 0.55, 0.60 — excluding the lowest value, which produces the hottest result in that block | `data/elwassif2006.py:108`, F-20 |
| **S-17** | **low** | `PEAK_RISE_K`'s docstring conflates two rows: it says the 0.82 K case is "highest tissue conductivity, **lowest thermal conductivity in the sweep**, and zero perfusion". That row is sigma = 0.35 at k = **0.527**, not the sweep's lowest k (0.45) | `data/elwassif2006.py:96-99`, F-19 |
| **S-18** | **low** | Unsupported comparative claim: "TiO2 buys **5-10x** the storage of Ta2O5 and pays about the same factor in leakage". Rose et al. say "a factor of **as much as 4**"; Table III gives 2.6 vs 6.3 uC/mm^2 (**2.4x**) and 0.07 vs 0.10 nA/nF (**1.4x**). It also conflicts with the module's own line 73 ("2-4x the permittivity ... 1-2 orders more leakage") | `data/ta2o5_capacitor.py:236-241`, F-31 |
| **S-19** | **low** | `leung2014` dated **2014**; the paper is IEEE TBME **62(3):849-857, 2015** (Crossref, and Cogan 2016 cites it as "Leung et al 2015") | `references.py:307-323`, F-35 |
| **S-20** | **low** | `itis2025` dated **2025** and titled "Version 4.2"; the DOI resolves correctly but IT'IS gives v4.2's release date as **04/06/2024**. The cited spreadsheet is not in the repo | `references.py:665-681`, F-36 |
| **S-21** | **low** | `user_measurement` has no `source_type`, so it defaults to `"journal"` and **`peer_reviewed` returns `True`** for a user's own measurement. `citation()` contains `if ... self.source_type != "user"`, showing `"user"` was intended and never set. Display is saved only because `describe()` special-cases the key by name | `references.py:609-618`, F-37 |
| **S-22** | **low** | Two `DERIVED` values sit in fields named for measurements: `measured_area_cm2=4.1e-4` for AIROF is the **midpoint** of Beebe & Rose's stated 3.7-4.5e-4 cm^2; `forming_voltage_V=2.5` for the Schaldach Ta wire is **back-solved** from the paper's 2 V breakdown / 0.8. Contrast `asanuma1976.py`, which labels its midpoints as midpoints — the right pattern | `materials.py:444`, `ta2o5_capacitor.py:159`, F-29/F-32 |
| **S-23** | **low** | `LEAD_3389_CONTACT_DIAMETER_UM = 1270` sits under `REFERENCE = "elwassif2006"` in a block headed "the authors' stated tissue parameters", but the conference paper never states a contact diameter — it is the Medtronic datasheet figure, with no manufacturer reference in `references.py`. Relatedly, `implied_power_W`'s default `source_radius_m = 1.3803e-3` is the equal-area sphere of **four** contacts while the protocol energises **two**, which is what makes the docstring's "325 ohm" come out (two contacts give ~230 ohm) | `data/elwassif2006.py:113,143`, F-21/F-22 |
| **S-24** | **low** | README, other stale or imprecise claims: "four of the five material values" (the table lists five changes; the database has nine materials); "Charge-injection limit — Source: Cogan 2008 Table 2" (most rows actually trace to primaries, which is better than claimed); "Water window — Cogan 2008; **Merrill 2005**" (no `WaterWindow` cites Merrill); "**That gap is not reconciled**" for the Elwassif 0.8 K figure (both `thermal.py` and `data/elwassif2006.py` reconcile it at length); the Primary-sources list omits ~11 sources that supply constants; and the default conductivity is **0.35 S/m from Elwassif**, not the IT'IS 0.419 S/m the "Thermal" bullet implies | README:64-70, 84, 213-214, 227-230, F-42/F-47 |
| **S-25** | **low** | Secondary chains not recorded in `references.py`: Wang & Weiland (2012) for the 240 uC/cm^2 edge corrosion (recorded as "via Cogan" in `current_distribution.py` but **not** in `cogan2016.py`); McCreery (2008) for the 1-2 nC/ph physiological threshold; Lan et al. (1981) for the 1.2 V 316LVM limit; Robblee & Rose (1990) for the 20 uC/cm^2 recommendation | F-12, F-25, F-26 |

### What the audit confirms outright

- **Gabriel et al. (1996) Part III Table 1** — all four tissues (grey matter, white matter,
  blood, muscle), all fourteen parameters each, transcribed exactly, with every ps/ns/us/ms
  conversion correct. The derived 0.104 S/m at 2500 Hz, and the "roughly a third of 0.35" /
  "a quarter of the IT'IS value" comparisons, all reproduce by running the code.
- **McCreery et al. (1990) Table I** — all twelve pulsed rows and all eleven stated
  conditions exact, including the 23/64/41 site counts and the 6.5 +/- 3e-5 cm^2 area.
- **Riedy & Walter (1996)** — all nine Table I cells, all four one-year drift values, all
  eleven protocol constants, verbatim electrolyte and discharge-circuit descriptions. The
  `wire_area_cm2` docstring's "about 5 %" and "about 15 %" claims both recompute correctly.
- **ISO 14708-3:2017** — all seven Table 101 CEM43 thresholds, Formula (1), both R values,
  the 39-57 °C validity range, and the Table 102 2 °C MRI criterion.
- **Elwassif et al. (2006) Table I** — all twelve rows, both leads, cell for cell.
- **Cogan 2008 Table 2** — all seven rows, both Qinj and potential-limit columns, plus the
  comment column, exact. Including the blank Ta2O5 potential-limits cell, which the code
  correctly mirrors as `water_window=None`.
- **Rose & Robblee (1990)** and **Beebe & Rose (1988)** primaries — the Pt 50-100/100-150
  polarity split, the -0.60/+0.90 V vs SCE limits, the 250 uC/cm^2 at 1 ms, the 600 uC/cm^2
  at +0.9 V bias, and AIROF's 2.1/1.0/3.5 mC/cm^2 — all exact.
- **The Cogan 2016 "k = 1.4" slip** the package flags is real: log10(6)+log10(12) = **1.857**,
  while the paper's other worked example (60 uC/cm^2 on 0.005 cm^2, "k ~ 1.25") evaluates to
  **1.2553**. The package's correction is right and is documented at the point of use.
- **The Rose & Robblee "VIII vs VII" catch** is real: Crossref confirms paper **VIII** at
  37:1118-1120, so Cogan 2008's ref. 71 is the one in error.
- **15 of 16 DOIs resolve to exactly the paper claimed**, with matching volume, issue, pages
  and authors. The two exceptions are year fields (S-19, S-20), not wrong papers.
- **`pennes1948` DOI handling is exemplary** — it leaves `doi=""` and states in the note that
  the widely cited 1998 reprint DOI belongs to the reprint "and must not be attached to this
  record".

---

## Verdict vocabulary used in the per-module tables below

- **MATCH** — code value and units equal the source value and units, conditions recorded.
- **CONDITION-DROPPED** — number is right, but a measurement condition the source states and
  that materially changes the number is not recorded in the code.
- **MISMATCH** — code value disagrees with the source.
- **UNIT-ERROR** — conversion between the source's units and the code's units is wrong.
- **UNVERIFIABLE** — no primary source available locally or online; cannot be confirmed.
- **DERIVED** — code presents a number as read from the source, but it was computed by the
  package from source numbers (not itself printed in the source).

---

## 1. `neurostim/data/gabriel1996.py` — Gabriel et al. (1996) Part III Cole-Cole parameters

Source: S Gabriel, R W Lau, C Gabriel, *The dielectric properties of biological tissues:
III. Parametric models for the dielectric spectrum of tissues*, Phys Med Biol 41:2271-2293
(1996). **Table 1, p. 2291.**

Source Table 1 row (grey matter):
`4.0 | 45.0 | 7.96 ps | 0.10 | 400 | 15.92 ns | 0.15 | 2.0e5 | 106.10 us | 0.22 | 4.5e7 | 5.305 ms | 0.00 | 0.0200`

| file:line | constant | code value | source value | source loc | verdict |
|---|---|---|---|---|---|
| gabriel1996.py:87-97 | GREY_MATTER | eps_inf 4.0; sigma_i 0.0200 S/m; (45.0, 7.96e-12, 0.10), (400.0, 15.92e-9, 0.15), (2.0e5, 106.10e-6, 0.22), (4.5e7, 5.305e-3, 0.00) | identical, with tau in ps/ns/us/ms | Table 1 p.2291 | **MATCH** |
| gabriel1996.py:99-109 | WHITE_MATTER | 4.0; 0.0200; (32.0, 7.96e-12, .10), (100.0, 7.96e-9, .10), (4.0e4, 53.05e-6, .30), (3.5e7, 7.958e-3, .02) | identical | Table 1 p.2291 | **MATCH** |
| gabriel1996.py:111-121 | BLOOD | 4.0; 0.7000; (56.0, 8.38e-12, .10), (5200.0, 132.63e-9, .10), zeros | identical; source prints blank (no 3rd/4th dispersion), code encodes as 0.0 and skips | Table 1 p.2291 | **MATCH** |
| gabriel1996.py:123-133 | MUSCLE | 4.0; 0.2000; (50.0, 7.23e-12, .10), (7000.0, 353.68e-9, .10), (1.2e6, 318.31e-6, .10), (2.5e7, 2.274e-3, .00) | identical | Table 1 p.2291 | **MATCH** |
| gabriel1996.py:48 | EPS_0 = 8.8541878128e-12 F/m | CODATA value | physical constant, not literature | — | **MATCH** |

Unit conversions recomputed by hand: ps -> 1e-12 s, ns -> 1e-9 s, us -> 1e-6 s, ms -> 1e-3 s.
All four tissues correct. **No unit errors.** This is the cleanest transcription in the package.

`effective_frequency_hz = 1/(2W)` (line 145-152) is explicitly labelled a convention, not a
source result — correctly flagged, nothing to verify.

---

## 2. `neurostim/data/mccreery1990.py` — McCreery et al. (1990) Table I

Source: McCreery, Agnew, Yuen, Bullara, *Charge density and charge per phase as cofactors
in neural injury induced by electrical stimulation*, IEEE TBME 37(10):996-1001 (1990).
**Table I, p. 999.**

All 12 pulsed rows transcribed. Source Table I vs code:

| area cm^2 | Q/A uC/cm^2 | Q uC | animals | sites | source severity | code | verdict |
|---|---|---|---|---|---|---|---|
| 6.5e-5 | 800 | 0.05 | 3 | 6 | no damage | none/none | **MATCH** |
| 6.5e-5 | 1600 | 0.1 | 1 | 4 | no damage | none/none | **MATCH** |
| 0.01 | 100 | 1.0 | 1 | 4 | 3 sites mild-moderate, 1 not damaged | partial/moderate | **MATCH** |
| 0.02 | 50 | 1.0 | 3 | 6 | 5 not damaged, 1 moderate | partial/moderate | **MATCH** |
| 0.10 | 10 | 1.0 | 5 | 9 | no damage | none/none | **MATCH** |
| 0.5 | 10 | 5 | 3 | 3 | no damage | none/none | **MATCH** |
| 0.5 | 12 | 6 | 3 | 3 | 2 minimal, 1 no damage | partial/minimal | **MATCH** |
| 0.5 | 16 | 8 | 2 | 2 | mild to moderate | damage/moderate | **MATCH** |
| 0.5 | 20 | 10 | 1 | 1 | mild to moderate | damage/moderate | **MATCH** |
| 0.5 | 25 | 12.5 | 1 | 1 | mild to moderate | damage/moderate | **MATCH** |
| 0.5 | 30 | 15 | 1 | 1 | moderate to severe | damage/severe | **MATCH** |
| 0.5 | 36 | 18 | 1 | 1 | moderate to severe | damage/severe | **MATCH** |

Conditions, all verified in the Methods section (p. 997):

| constant | code | source | verdict |
|---|---|---|---|
| PULSE_WIDTH_US = 400.0 | 400 us/phase | "400 us per phase in duration" | **MATCH** |
| FREQUENCY_HZ = 50.0 | 50 Hz | "pulsed continuously for 7 h at 50 Hz" | **MATCH** |
| DURATION_H = 7.0 | 7 h | "7 h of continuous stimulation" | **MATCH** |
| CONTROL_SITES = 23 | 23 | "23 were unstimulated (control) sites" (Results) | **MATCH** |
| TOTAL_SITES_EXAMINED = 64 | 64, 22 animals, 41 pulsed | "64 electrodes from 22 animals ... 41 sites had been stimulated" | **MATCH** |
| docstring: anodic first | anodic first | "anodic first, charge balanced, constant current, symmetric pulse pairs" | **MATCH** |
| docstring: >=10 days implanted | >=10 days | "At least ten days after implantation" | **MATCH** |
| docstring: perfused within 20 min | 20 min | "Within 20 min after the end of the 7 h" | **MATCH** |
| docstring: microelectrode area 6.5 +/- 3e-5 cm^2 | 6.5 +/- 3e-5 | "geometric area of 6.5 +/- 3 x 10^-5 cm^2" | **MATCH** |
| docstring: threshold 50-100 at 1 uC/ph, 10-12 at 5 uC/ph | as stated | Discussion p.999 verbatim | **MATCH** |
| docstring: three stated limits | LM sensitivity, frequency/pulse count held fixed, recovery within 7 days | Discussion p.999 verbatim | **MATCH** |

### Findings in this module

**F-1 (minor, CONDITION-DROPPED).** The two microelectrode rows use Table I's rounded
0.05 / 0.1 uC per phase. The Methods and Discussion text gives the actual values as
**0.052 and 0.104 uC/ph**. Using the rounded values shifts `shannon_k` for those points by
0.017 (log10(0.052/0.05)). Immaterial numerically, but the module claims to transcribe
Table I and does so faithfully — so this is the paper rounding, not the code. Recorded for
completeness only.

**F-2 (paper-internal, worth a code comment).** `CONTROL_SITES = 23` matches the Results
text. Table I's own unpulsed rows sum to **24 sites** (4+2+6+5+7) from 16 animals, and the
Table I footnote says "In all, **23 animals** are represented in this table" against the
Results text's "22 animals". The paper is internally inconsistent; the code follows the
Results text, which is the defensible choice, but does not record that the table disagrees.

**F-3 (real, affects a derived quantity).** `separating_k_range()` (line 241-253) returns a
**zero-width band**. Computed from the surface-electrode points only:
highest-k safe point = (0.5 cm^2, 10 uC/cm^2, 5 uC) -> k = log10(5)+log10(10) = **1.69897**;
lowest-k damaging/partial point = (0.02 cm^2, 50 uC/cm^2, 1 uC) -> k = log10(1)+log10(50) =
**1.69897**. The two coincide exactly. The docstring asserts "Any separatrix has to fall
inside this band to be consistent with the data" — under that assertion the *only*
admissible k is 1.69897, and every k the package and the literature actually use
(Shannon 1.5-2.0, Cogan's 1.85, the DBS-derived 1.75) falls outside it. The function is
literature-faithful in its inputs but its docstring claim is not supportable; the data are
not separable by a single k line, which is precisely Cogan 2016's point.

**F-4 (paper-internal, code is faithful).** `local_charge_density_uC_cm2` implements
McCreery eq. (1) `QD_x = QD_s (1 - x/sqrt(R^2+x^2))` **exactly as printed** (p. 1000).
The caveat in the code's docstring ("assumes uniform current density over the facet, whereas
real discs concentrate current at the perimeter, so it *under*-estimates") is a verbatim
paraphrase of the paper. However, the paper's own worked example is not reproducible from
its own equation: with QD_s = 800 uC/cm^2, R = 45 um, x = 60 um the equation gives
800 x (1 - 60/75) = **160 uC/cm^2**, while the paper states "approximately 130". The 1600 /
0.1 uC/ph case likewise gives 320 against the paper's stated 260 (same 0.8125 ratio, so a
consistent difference in R or x, not a typo in one number). The code does not carry the
130/260 figures, so it inherits no error — but anyone checking the code against the paper's
prose will hit this. **Verdict on the code: MATCH to the printed equation.**

---

## 3. `neurostim/data/mccreery1995.py` — McCreery et al. (1995) frequency dependence

Source: McCreery, Agnew, Yuen, Bullara, *Relationship between stimulus amplitude, stimulus
frequency and neural damage during electrical stimulation of sciatic nerve of cat*,
Med Biol Eng Comput 33(3):426-429 (1995).

| file:line | constant | code | source | source loc | verdict |
|---|---|---|---|---|---|
| :65 | PULSE_WIDTH_US | 100.0 | "Each phase of the biphasic pair is 100 us in duration" | Methods p.427 | **MATCH** |
| :66 | INTERPHASE_GAP_US | 400.0 | "with a 400 us delay between the first and second phases" | Methods p.427 | **MATCH** |
| :67 | DURATION_H | 8.0 | "stimulated continuously for 8 h" | Methods p.427 | **MATCH** |
| :68 | ASSESSMENT_DELAY_DAYS | 7 | "Seven days after stimulation ... perfused" | Methods p.427 | **MATCH** |
| :69 | PREPARATION | cat sciatic, helical Pt band | "HMRI bidirectional helical stimulating electrode array ... a pair of platinum bands, 0.5 mm in width" | Methods p.426 | **MATCH** |
| :92-104 | 20 Hz point | slope 0.003, threshold None, R 0.07, n 8 | "0.003% EAD per alpha unit and R is .07"; "Eight nerves were stimulated at 20 Hz" | Results p.427-8 | **MATCH** |
| :105-112 | 50 Hz point | slope 0.37, threshold 1.1, R 0.87, n 15 | "0.37% EAD per alpha unit at 50 Hz"; "1.1 times that of full alpha recruitment"; "R = 0.87 when f = 50 Hz"; "additional 15 nerves ... at 50 Hz" | Results p.427-8 | **MATCH** |
| :113-119 | 100 Hz point | slope 1.1, threshold 0.8, R 0.85, n 9 | "1.1% EAD per alpha unit at 100 Hz"; "0.8 times that of full alpha recruitment ... at 100 Hz"; "R = 0.85 when f = 100 Hz"; "nine at 100 Hz" | Results p.428 | **MATCH** |
| :122 | SLOPE_RATIO_50_TO_100 = 1.1/0.37 | 2.973 | paper says slope increased; ratio not printed | Results | **DERIVED** (correct arithmetic; "tripled" is the package's word, the paper says only "an increase in the slope") |
| :125 | THRESHOLD_RATIO_50_TO_100 = 0.8/1.1 | 0.727 | paper says "reduced slightly"; ratio not printed | Results | **DERIVED** (correct arithmetic) |
| :128 | LOW_FREQUENCY_SAFE_HZ | 20.0 | "continuous low-frequency stimulation ... (e.g. at 20 Hz) induces little or no neural injury" | Discussion p.428 | **MATCH** |
| :131 | R_SQUARED_UNEXPLAINED | 0.25 | "R^2 = 0.75 (75%) when f = 50 Hz and R^2 = 0.72 (72%) when f = 100 Hz" | Results p.428 | **MATCH** (1 - 0.75; docstring says "roughly a quarter", correct for both) |
| docstring | 22 000 axons normalisation | 22 000 | "normalised on 22 000 (the average number of myelinated axons in a cat's sciatic nerve)" | Methods p.427 | **MATCH** |
| docstring | "<0.2 % of axons" | <0.2 % | "(< 0.2% of the total contingent)" | Discussion p.428 | **MATCH** |
| docstring | margin-of-safety quote | verbatim | "the margin of safety ... can be greatly increased by reducing the stimulus frequency to the absolute minimum required to obtain the desired clinical results" | Discussion p.428 | **MATCH** |

### Findings

**F-5 (minor attribution).** The docstring attributes to *this paper* the statement that
"the correlation between neural damage and stimulus amplitude is poor when the stimulus is
expressed simply as charge per phase or as current". The sentence does appear in the paper
(Methods, p. 427) but is there **cited to McCreery et al. 1992**, not presented as this
study's own finding. The code says "the authors ... state", which is literally true but
reads as a result of this experiment. Minor.

**F-6 (minor, DERIVED wording).** "Tripled" (docstring and `describe_frequency_risk`) is the
package's characterisation of 1.1/0.37 = 2.97. The paper states only that the primary effect
of raising frequency "was to cause an increase in the slope". Arithmetic correct; attribution
of the word "tripled" to the authors is not.

**F-7 (three weeks, not recorded).** The implantation-to-stimulation interval, "Three weeks
or more after implantation of the electrodes" (Methods p. 426), is not recorded. Also not
recorded: electrode migration of 0.5-6 mm proximally found at autopsy, which the authors
report and which bears on where the damage was scored. CONDITION-DROPPED (mild).

---

## 4. `neurostim/data/mccreery2010.py` — McCreery, Pikov & Troyk (2010)

Source: *Neuronal loss due to prolonged controlled-current stimulation with chronically
implanted microelectrodes in the cat cerebral cortex*, J Neural Eng 7(3):036005 (2010).
Read from the NIH author manuscript (`nihms209066.txt`).

| file:line | constant | code | source | source loc | verdict |
|---|---|---|---|---|---|
| :48 | NO_DAMAGE_NC_PER_PHASE | 2.0 | "Continuous stimulation at 2 nC/phase and with a geometric charge density of 100 uC/cm2" -> no detectable change | Abstract; Results | **MATCH** |
| :51 | DAMAGE_NC_PER_PHASE | 4.0 | "pulsing with a continuous (100% duty cycle) at 4 nC/ph ... induced loss of cortical neurons" | Abstract | **MATCH** |
| :58 | NO_DAMAGE_CHARGE_DENSITY_UC_CM2 | 100.0 | "geometric charge density of 100 uC/cm2" | Abstract | **MATCH** |
| :59 | DAMAGE_CHARGE_DENSITY_UC_CM2 | 200.0 | "geometric charge density of 200 uC/cm2" | Abstract | **MATCH** |
| :61 | DAMAGE_RADIUS_CONTINUOUS_UM | 150.0 | "over a radius of at least 150 um from the electrode tips" | Abstract | **MATCH** |
| :64 | DAMAGE_RADIUS_HALF_DUTY_UM | 60.0 | "approximately 60 um from the center of the electrode tips" | Abstract | **MATCH** (but see F-9) |
| :70 | IMPLANT_DURATION_DAYS | (450, 1282) | "implanted for 450 to 1282 days" | Abstract | **MATCH** |
| :71 | PULSING_HOURS | 240.0 | "pulsed for 240 hours (8 hours per day for 30 days)" | Abstract | **MATCH** |
| :72 | FREQUENCY_HZ | 50.0 | "at 50 Hz" / "pulsed at 50 pps" | Abstract; Methods | **MATCH** |
| :73 | N_ANIMALS | 7 | "7 adult domestics cats" | Abstract | **MATCH** |
| :74 | PREPARATION | activated Ir, cat sensorimotor cortex | matches | Abstract | **MATCH** |
| :75 | UNPULSED_CONTROLS_ALSO_DAMAGED | True | "there also was significant loss of neurons surrounding the unpulsed electrodes" | Abstract | **MATCH** |
| :67 | DUTY_CYCLE_RADIUS_RATIO = 150/60 | 2.5 | not printed in source | — | **DERIVED** (correct arithmetic; the 150 is a lower bound, so the ratio is a lower bound too, and the docstring correctly says "at least this factor") |

### Findings

**F-8 (CONDITION-DROPPED, material).** Four conditions that set these numbers are stated in
the source and are **absent from the module**:
- **Pulse width 200 us** ("cathodic pulses 200 us in duration and 10 or 20 uA", Methods).
  Without it, 4 nC/phase cannot be connected to a current or compared to any other study.
- **Interpulse bias +0.6 V** vs a platinum indifferent electrode, applied specifically "in
  order to increase their charge capacity" (Methods). The whole AIROF regime here is a
  biased one.
- **Electrode geometric surface area 2000 +/- 150 um^2** (Methods). This is what makes
  4 nC/phase equal 200 uC/cm^2 — recomputed: 4e-9 C / 2e-5 cm^2 = 2.0e-4 C/cm^2 =
  200 uC/cm^2. **Unit conversion correct**, but the area it depends on is not recorded.
- **Cathodic (monophasic-first) pulses**, not a symmetric biphasic pair.

The package's stated thesis is that constants carry their measurement conditions. For this
module that claim does not hold: the four conditions that make 4 nC/phase mean something
are all missing.

**F-9 (overstatement risk).** `DAMAGE_RADIUS_HALF_DUTY_UM = 60.0` is documented as "At 50 %
duty cycle the same stimulus damaged only about this radius". The source's abstract
qualifies this immediately: the unpulsed-control loss "was responsible for **most of the
neuronal loss within 150 um of the electrodes pulsed with the 50% duty cycle**". The module
docstring does mention control-electrode loss, but in a separate "caution" section, and it
does not say that the control loss accounts for most of the 50 %-duty result. Taken at face
value the constant attributes to stimulation a radius the authors largely attribute to the
implant. CONDITION-DROPPED.

---

## 5. `neurostim/data/cogan2016.py` — Cogan, Ludwig, Welle & Takmakov (2016)

Source: *Tissue damage thresholds during therapeutic electrical stimulation*, J Neural Eng
13(2):021001 (2016). Read from `nihms854736.txt`.

| file:line | constant | code | source | source loc | verdict |
|---|---|---|---|---|---|
| :36 | MICROELECTRODE_DAMAGE_THRESHOLD_NC_PER_PHASE | 4.0 | "a 4 nC/ph tissue damage threshold, which is indicated in figure 5 by the vertical dashed line (McCreery et al 1994, 2010)" | s."Microelectrodes" | **MATCH** |
| :45 | MICROELECTRODE_PHYSIOLOGICAL_THRESHOLD_NC_PER_PHASE | (1.0, 2.0) | "physiological thresholds of about 1-2 nC/ph have been reported for ~1000 um2 electrodes, this results in a threshold charge density of 100-200 uC cm-2 (McCreery 2008)" | s."Regulatory considerations" | **MATCH**; conversion recomputed: 1e-9 C / 1e-5 cm^2 = 100 uC/cm^2 ✓ |
| :53 | MACRO_MICRO_BOUNDARY_DIAMETER_UM | (200.0, 300.0) | "macro-to-microelectrode boundary between 200 um and 300 um diameter" | s."Shannon limitations" | **MATCH** |
| :59 | MACRO_MICRO_BOUNDARY_AREA_CM2 | (3e-4, 7e-4) | "(3 x 10-4 cm2 and 7 x 10-4 cm2)" — printed in the source | same sentence | **MATCH**; independently recomputed pi(0.010 cm)^2 = 3.14e-4, pi(0.015 cm)^2 = 7.07e-4 ✓ |
| :62 | FAR_FIELD_DISTANCE_ELECTRODE_DIAMETERS | (2.0, 5.0) | "this distance is about 2-5 times the largest exposed electrode dimension (Suesserman and Spelman 1993, McIntyre and Grill 2001)" | s."far-field" | **MATCH** (see F-11 on the constant's name) |
| :65 | MICROELECTRODE_POINT_SOURCE_DISTANCE_UM | 50.0 | "for typical microelectrodes with a GSA range of 200-2000 um2, point source behavior is observed for distances greater than about 50 um" | s."far-field" | **MATCH** |
| :158 | DBS_APPROVED_CHARGE_DENSITY_UC_CM2 | 30.0 | "approved with a maximum charge density of 30 uC cm-2"; origin "extending the charge density/charge per phase line for a typical macroelectrode GSA (0.06 cm2 ...) to the Shannon line for k ~ 1.75" | s."Origin of the 30 uC cm-2 damage threshold" | **MATCH** (all three sub-facts: 0.06 cm^2, k~1.75, Kuncel & Grill 2004) |
| :166 | DBS_TYPICAL_CLINICAL_CHARGE_DENSITY_UC_CM2 | 8.0 | "Based on an assumed electrode resistance of 1100 Ohm, we estimate a maximum charge/phase and charge density of 0.5 uC and 8 uC cm-2 from the data of Burbaud et al (2002) and Haberler et al (2000)" | same section | **MATCH** (1100 Ohm, 0.5 uC/ph and both citations carried) |
| :174 | SMOOTH_PT_SALINE_CIC_UC_CM2 | (35.0, 100.0) | "on the order of 35-100 uC cm-2 for smooth platinum" | s."electrochemical" | **MATCH** |
| :177 | POROUS_PT_SALINE_CIC_UC_CM2 | 1000.0 | "as high as 1 mC cm-2 for some porous" | same sentence | **MATCH**; 1 mC/cm^2 = 1000 uC/cm^2 ✓ |
| :180 | PT_EDGE_CORROSION_CHARGE_DENSITY_UC_CM2 | 240.0 | "preferential corrosion at the edge of platinum disk electrodes subjected to high charge density pulsing (240 uC cm-2) has been reported (Wang and Weiland 2012)" | s."non-uniform currents" | **MATCH**, but see F-12 |
| :183 | AIROF_BIAS_SAFE_CHARGE_NC_PER_PHASE | 3.6 | "electrodes pulsed at modest intensities (<=3.6 nC/ph) (McCreery et al 1992, 2010)" | s."AIROF" | **MATCH** |
| :186 | COGAN_FIGURE_1_K | 1.85 | "A k value of 1.85 was chosen for figure 1 as it provides a good qualitative boundary"; "A more conservative estimate of damage thresholds would use a lower k" | p. before fig 1 | **MATCH**, quote verbatim |
| :192 | CLINICAL_DEVICES_RESPECT_K_RANGE | (1.5, 1.8) | "clinical neural stimulation devices respect this threshold at a k-value between about 1.5 and 1.8" | s."clinical devices" | **MATCH** |

### The docstring's "discrepancy noticed while transcribing" — independently checked and correct

Source text: "caused by a high charge per phase (6 uC/phase) even though the k value for this
stimulus intensity is only 1.4" and, two sentences later, "charge densities up to 60 uC cm-2
(k ~ 1.25 for a 0.005 cm2 electrode)".

Recomputed by hand:
- 12 uC/cm^2 at 6 uC/phase: log10(6) + log10(12) = 0.77815 + 1.07918 = **1.8573**, not 1.4.
- 60 uC/cm^2 on 0.005 cm^2: Q = 60e-6 x 0.005 = 3.0e-7 C = 0.3 uC;
  log10(0.3) + log10(60) = -0.52288 + 1.77815 = **1.2553** ~ the paper's 1.25. ✓

So the relation used in the paper is the standard one and the "1.4" is a slip, exactly as
the module's docstring says. **The package's correction is right.** Good catch by the author
and it is documented at the point of use.

### Findings

**F-10 (DERIVED, presented as reported — the most consequential finding in this module).**
`IN_VIVO_DERATING["Pt"] = Derating(2.0, 14.0, ...)`. Cogan 2016 states the in vivo derating
as "**as much as a factor of 10 lower for platinum and AIROF, and a factor of four lower
with SIROF**". The code's **2-14x for platinum is not in Cogan 2016** — it is the package's
own ratio computed from Leung et al. (2014)'s reported ranges (34/16.6 = 2.05 and
54/3.84 = 14.06). Two problems:
1. The high end, **14x, exceeds the "factor of 10" the cited review states**, and it is
   obtained by dividing the best in vitro case by the worst in vivo case — a
   ratio-of-extremes, not a matched-pair derating. Leung measured in vitro and in vivo at
   matched pulse widths; a matched ratio at a single pulse width would be the defensible
   number and is not what is stored.
2. `Derating.describe()` renders this as "2-14x lower in vivo than in saline (Leung et al.
   2014: ...)", which reads as Leung's reported figure. It is not; it is a derived envelope.
`IN_VIVO_DERATING["PtIr"] = Derating(2.0, 14.0, "assumed to follow platinum; not measured
separately")` inherits the same problem, and correctly flags the assumption.
`IN_VIVO_DERATING["SIROF"] = Derating(2.0, 4.0, ...)`: the 4 matches Cogan's "factor of four
lower with SIROF"; **the lower bound 2.0 has no stated source** — Kane 2013's cited evidence
(8 nC/phase electrodes approaching water reduction in vivo) is qualitative and yields no
factor of 2. **UNVERIFIABLE** for the 2.0.
`IN_VIVO_DERATING["AIROF"] = Derating(10.0, 10.0, Hu 2006)` matches Cogan's "factor of 10"
and Hu's "about ten times". **MATCH.**

**F-11 (naming).** `FAR_FIELD_DISTANCE_ELECTRODE_DIAMETERS` names the multiplier as being of
*diameters*; the source says "largest exposed electrode **dimension**". For a non-circular
contact (a DBS cylinder, a band) these differ. The docstring gets it right; the constant name
does not.

**F-12 (secondary citation not recorded).** `PT_EDGE_CORROSION_CHARGE_DENSITY_UC_CM2 = 240`
is Wang & Weiland (2012) as cited *by* Cogan 2016. The module's `REFERENCE = "cogan2016"` and
`references.py` has no entry for Wang & Weiland 2012, so the number is attributed to the
review, not the study that measured it. Same pattern for `MACRO_MICRO_BOUNDARY_*`
(Butterwick 2007 via Cogan — though here the package does also hold Butterwick as a primary
source, see section 6) and for `MICROELECTRODE_PHYSIOLOGICAL_THRESHOLD_NC_PER_PHASE`
(McCreery 2008 via Cogan, no `references.py` entry).

**F-13 (quote truncated in a way that changes it).** The module docstring quotes: *"It is
possible to stimulate below 30 uC/cm^2 and generate tissue damage; conversely, it is possible
to stimulate up above that level and not produce tissue damage."* The source sentence
continues: "...and not produce tissue damage **that results in a decline in functional
performance**." The qualifier is the whole point of the second clause and is dropped.

### F-10 corrected and sharpened after reading Leung, Hu and Kane directly

The three derating entries were checked against the underlying primary papers, not just
against Cogan 2016. All three are wrong in a way that matters.

**Pt — `Derating(2.0, 14.0, "Leung et al. 2014 ...")` — MISMATCH.**
Leung et al. (2014) **publishes its own pulse-width-matched derating** and the code
ignores it. Source, Results p. 851: *"suprachoroidal Qinj in vivo was between **8.7 times
less (200-us pulsewidth) and 3.2 times less (3200-us pulsewidth)** than that measured in
vitro. **These factors were determined by dividing the in vitro Qinj by the mean in vivo
Qinj at the respective pulsewidths.**"*
The code's 2.0 and 14.0 are obtained by dividing best-in-vitro by worst-in-vivo **across
mismatched pulse widths** — 34/16.6 = 2.05 and 54/3.84 = 14.06 — which is the exact
comparison the authors pre-empted by matching pulse widths. Recomputing matched pairs from
the code's own quoted ranges gives 34/3.84 = 8.9 at 100 us and 54/16.6 = 3.3 at 3200 us,
i.e. **3.3-8.9x**, consistent with the paper's stated 3.2-8.7x. So:
- the stored low bound **2.0 is too permissive** (real minimum ~3.2);
- the stored high bound **14.0 is too alarming** (real maximum ~8.7), and it also exceeds
  the "as much as a factor of 10" of Cogan 2016, the review the module is named for.
- the `evidence` string quotes Leung's raw ranges, so it reads as if 2-14 were Leung's
  figure. It is not; Leung's figure is 3.2-8.7 and is in the same paragraph as the ranges
  the code did quote.

**AIROF — `Derating(10.0, 10.0, "Hu et al. 2006: in vitro 3-4 mC/cm^2 is about ten times
what the same films deliver in vivo")` — evidence string MISQUOTES the source; the factor
survives by coincidence.**
Hu et al. (2006) Introduction: *"It is not unusual to achieve an in vitro charge density of
about 3-4 mC/cm2, **about ten times larger than what Pt microelectrodes can typically
produce** [2]."* The "ten times" in that sentence compares **AIROF to platinum**, not
in vitro to in vivo, and the 3-4 mC/cm^2 is a general literature statement carrying its own
citation [2] — it is **not Hu's measurement**. Hu's own measured values (unnumbered table,
p. 888) are:

| electrode | in vitro (PBS) | in vitro (1/16 PBS) | in vivo (bird brain) | ratio |
|---|---|---|---|---|
| MPA06 | 1.69 mC/cm^2 | 1.33 mC/cm^2 | 0.14 mC/cm^2 | 12.1 |
| MPA08 | 1.18 mC/cm^2 | 1.04 mC/cm^2 | 0.15 mC/cm^2 | 7.9 |

The in vitro/in vivo statement Hu actually makes is: *"For the chosen compliance limit, the
**in vivo value is about 10% of the in vitro ones** for both electrodes."* That supports the
stored factor of 10. So the **number is defensible, the sentence attached to it is not**:
it welds the headline of one sentence onto the subject of another, and attributes to Hu a
3-4 mC/cm^2 in vitro value that Hu measured as 1.18-1.69.
Conditions dropped: in vivo preparation is **bird brain** (songbird), 300 us integration
window, compliance-limited current-pulse drive, activation between +0.9 and -0.6 V vs
Ag|AgCl. None recorded.

**SIROF — `Derating(2.0, 4.0, "Kane et al. 2013 ...")` — range widened beyond the cited
source.** Kane et al. (2013), Results: *"Using the Emc = -0.6 V (versus Ag|AgCl) criterion,
the maximum charge capacity in vivo was reduced by a **factor of 2-3**, with the larger
reduction observed at more positive bias levels."* Kane's own range is **2-3**, not 2-4.
The 4 is Cogan 2016's review-level "a factor of four lower with SIROF microelectrodes".
The code stores 2-4 with `evidence` naming only Kane, so a range that blends two sources is
attributed to one of them, and the high end is 33 % above what that source reports. The
quoted evidence sentence itself ("electrodes delivering 8 nC/phase in vitro approached or
exceeded water reduction in vivo") is accurate to Kane but is not the source of either number.
Conditions dropped: 2000 um^2 SIROF sites, 400 us pulse width, interpulse bias 0.0-0.6 V,
cat cortex, day 154 post-implant.

---

## 6. `neurostim/data/butterwick2007.py` — Butterwick et al. (2007)

Source: *Tissue damage by pulsed electrical stimulation*, IEEE TBME 54(12):2261-2267 (2007).

| file:line | constant | code | source | source loc | verdict |
|---|---|---|---|---|---|
| :58 | RETINA_THRESHOLD_AT_6MS_A_PER_CM2 | 0.061 A/cm^2 | "threshold current density for repeated exposure on the retina varied between 0.061 A/cm2 at 6 ms" | Abstract | **MATCH** |
| :61 | RETINA_THRESHOLD_AT_6US_A_PER_CM2 | 1.3 A/cm^2 | "...to 1.3 A/cm2 at 6 us" | Abstract | **MATCH** |
| :67 | QUOTED_DURATION_EXPONENT | -0.5 | "scaled with pulse duration as approximately 1/t^0.5, characteristic of electroporation" | Abstract; Discussion p.2265 | **MATCH** |
| :77 | SIZE_INDEPENDENT_ABOVE_UM | 300.0 | "independent of electrode size for diameters greater than 300 um" | Abstract | **MATCH** |
| :80 | CONSTANT_CURRENT_BELOW_UM | 200.0 | "scaled as 1/d^2 for electrodes smaller than 200 um" | Abstract | **MATCH** |
| :85 | PULSE_COUNT_SATURATION | 50 | "as the number of pulses increased from 1 to 50, and remained constant for a higher number of pulses" | Abstract | **MATCH** |
| :88 | REPEATED_EXPOSURE_FACTOR_RETINA | 7.0 | "dropping by a factor of 14 on the CAM and 7 on the retina" | Abstract | **MATCH** |
| :91 | REPEATED_EXPOSURE_FACTOR_CAM | 14.0 | same sentence | Abstract | **MATCH** |
| :94 | PREPARATION | chick CAM in vivo, chick retina in vitro | "chorioallantoic membrane (CAM) in vivo and chick retina in vitro ... verified by repeating some measurements on porcine retina in-vitro" | Abstract | **MATCH** |
| :132 | CAM factor `base /= 3.0` | 3.0, inline literal | "The current density threshold for damage in retinal tissue appears to be **three times higher** than that for damage in CAM" | Discussion p.2265 | **MATCH** value, but see F-16 |
| docstring | McCreery agreement quote | verbatim | "very similar to that measured during chronic in vivo stimulation of the cat cortex using a large (0.5 cm^2) electrode" | Discussion p.2265 | **MATCH** |
| docstring | thermal, "order millikelvin", "no hyperthermia can be expected as a result of chronic stimulation" | verbatim | "For r = 0.5 mm, nu = 25 Hz, j = 0.17 A/cm^2, and t = 1 ms, dT = 22 mK. Therefore, no hyperthermia can be expected as a result of chronic stimulation..." (and 17 mK single pulse at j = 1 A/cm^2, t = 1 ms) | Discussion p.2265 | **MATCH** |

### Findings

**F-14 (MISMATCH — the module re-fits an exponent the source already publishes).**
`FITTED_DURATION_EXPONENT` (line 70-73) is computed from the two abstract anchor points:
`ln(1.3/0.061)/ln(6/6000) = 3.0594 / -6.9078 = -0.4429`. The docstring says this is "about
-0.44, close to the -0.5 they quote; both are recorded here."

But Butterwick **prints the actual power-fit exponents** (p. 2264, text beside Fig. 4):
*"the power fit slopes are t^-0.52 and t^-0.48 in the chronic regime, and t^-0.49 and
t^-0.41 with the single shots on CAM and retina, respectively."*
So for the exact case the module models — **retina, sustained/repeated exposure — the
source's own fit is -0.48**, not the module's re-derived -0.4429 and not the rounded -0.5.
Neither of the two exponents the module "records" is the one the source published for this
condition. `threshold_A_per_cm2` uses the re-fitted -0.4429 **by default**. At 200 us this
returns 0.275 A/cm^2 against 0.312 A/cm^2 from the source's -0.48 — 12 % low (conservative
in direction, wrong in provenance). The module should carry the four printed slopes.

**F-15 (CONDITION-DROPPED — the size scaling was measured on single pulses only).**
Source, p. 2264: *"The effect of electrode size on the damage threshold during sustained
repetitive stimulation is shown in Fig. 5. These measurements were performed with **only one
pulse** of duration **60 us on CAM and 600 us on the retina**. Different pulse durations were
used for the two different tissues to yield similar damage thresholds on large electrodes."*
`threshold_A_per_cm2` applies the `(200/d)^2` correction unconditionally, including on top of
the saturated 50-pulse default and at any pulse width. Neither the single-pulse condition nor
the tissue-specific pulse durations are recorded anywhere in the module.

Related and also dropped: Fig. 5 gives the **absolute** small-electrode anchor — *"In the
regime of constant current, electrodes smaller than 200 um, the threshold value of total
current for damage is **139 uA on retina and 55 uA on CAM**."* The module carries neither.
Its implicit assumption is that the threshold current density at exactly 200 um equals the
large-electrode plateau, so the d^-2 branch can start from `base`. Recomputing from the
source's own figure: 139 uA over pi(0.010 cm)^2 = 3.1416e-4 cm^2 gives **0.442 A/cm^2** at
200 um, against a retina plateau in Fig. 5 of roughly 0.17-0.20 A/cm^2 — a factor of about
2.5 discontinuity the module's formula does not reproduce. (Direction is conservative: the
module returns a lower threshold than the source's own anchor.)

Also dropped: the Fig. 5 model places target cells at **57 um (CAM) and 125 um (retina)**
from the electrode; the plotted "current density at the tissue" is a modelled quantity at
those depths, not a surface density.

Also dropped: Fig. 6 shows the duration exponent itself **depends on electrode size** —
*"the slopes are also t^-0.48 for the large pipette and t^-0.29 for the small one"* (1.0 mm
and 0.115 mm). `threshold_A_per_cm2` applies one size-independent exponent and then a
separate d^-2 factor, which is not how the source's data behave. The two corrections are
not independent in the source.

**F-16 (minor, inconsistent with the module's own discipline).** The CAM/retina factor of 3
is an inline literal `base /= 3.0` at line 132 with a comment, while every other literature
value in this module is a named module-level constant with a docstring. The value is correct
(Discussion p. 2265) but it is the one number here a reader cannot find by scanning the
constants, and it carries no reference field.

**F-17 (electrode diameter of the anchor points not recorded).** The 0.061 / 1.3 A/cm^2
anchors come from the strength-duration curve measured *"with a pipette of 1-mm diameter"*
(p. 2264). Since the module then applies a size correction relative to those anchors, the
1 mm basis is load-bearing and is not stored.

---

## 7. `neurostim/data/current_distribution.py` — Kuncel & Grill (2004)

Source: Kuncel AM, Grill WM, *Selection of stimulus parameters for deep brain stimulation*,
Clin Neurophysiol 115(11):2431-2441 (2004).

| file:line | constant | code | source | source loc | verdict |
|---|---|---|---|---|---|
| :59 | DBS_FRACTION_ABOVE_AVERAGE | 0.256 | "25.6% of the contact surface is operating at a current density above the average value" | p.2438, and Fig.7 caption | **MATCH** |
| :65 | DBS_AVERAGE_CURRENT_DENSITY_A_PER_CM2 | 0.0993 | "average value of 0.0993 A/cm2" | p.2438, Fig.7 caption | **MATCH** |
| :68 | DBS_MODELLED_CONTACT_DIAMETER_MM | 1.26 | "an electrode 1.26 mm in diameter" | p.2438 | **MATCH** |
| :69 | DBS_MODELLED_CONTACT_LENGTH_MM | 1.5 | "with a single contact 1.5 mm in length" | p.2438 | **MATCH** |
| :70 | DBS_MODELLED_VOLTAGE_V | 3.0 | "set to 3 V" | p.2438 | **MATCH** |
| :72 | PT_EDGE_CORROSION_OBSERVED_UC_CM2 | 240.0 | Wang & Weiland 2012 **via** Cogan 2016 | — | **MATCH**, and here the "via" **is** recorded (contrast cogan2016.py:180, F-12) |
| docstring | three reasons the limit is liberal | frequency; post-mortem below limit; non-uniform distribution | p.2438: "First, the data from which this limit was extracted were collected at frequencies much lower than those used in DBS, and a frequency-dependent threshold for neural damage has been found (Agnew et al., 1983). Second, ... The charge and charge density used in these studies were significantly below the recommended charge density limit ... The last confound ... is the uneven distribution of the charge density" | p.2438 | **MATCH**, all three |
| docstring | "liberal estimate" | as stated | Abstract: "The recommended charge density limit for DBS represents a **liberal estimate** for non-damaging stimulation." | Abstract | **MATCH** |
| docstring | 0.06 cm^2 DBS contact area | 0.06 cm^2 | "which is 0.06 cm2 for the DBS contact" | p.2438 | **MATCH** (consistent with cogan2016.py) |

This module is the cleanest provenance record in the package: the primary source is used
directly (`REFERENCE = "kuncel_grill2004_full"`), the secondary chain for the one borrowed
number is stated, and the mitigations section attributes each claim to the paper that made it.
No findings.

---

## 8. `neurostim/data/elwassif2006.py` — Elwassif et al. (2006)

Source actually transcribed: **Elwassif, Kong, Vazquez, Bikson, "Bio-Heat Transfer Model of
Deep Brain Stimulation Induced Temperature changes", Proc. 28th IEEE EMBS Annual
International Conference, New York City, Aug 30 - Sept 3 2006, paper FrD08.1.** This is what
is in `papers_stim_calc_ref/elwassif2006.pdf` and what the module docstring says it read.

Table I, all 12 rows checked cell by cell:

| block | swept param | code row | source row (3389 / 3387) | verdict |
|---|---|---|---|---|
| I | sigma 0.15 | 37.35 / 37.21 | 37.35 / 37.21 | **MATCH** |
| I | sigma 0.20 | 37.47 / 37.28 | 37.47 / 37.28 | **MATCH** |
| I | sigma 0.30 | 37.70 / 37.42 | 37.70 / 37.42 | **MATCH** |
| I | sigma 0.35 | 37.82 / 37.48 | 37.82 / 37.48 | **MATCH** |
| II | k 0.45 | 37.82 / 37.48 | 37.82 / 37.48 | **MATCH** |
| II | k 0.50 | 37.74 / 37.44 | 37.74 / 37.44 | **MATCH** |
| II | k 0.55 | 37.67 / 37.40 | 37.67 / 37.40 | **MATCH** |
| II | k 0.60 | 37.62 / 37.37 | 37.62 / 37.37 | **MATCH** |
| III | w 0.000 | 37.70 / 37.42 | 37.70 / 37.42 | **MATCH** |
| III | w 0.004 | 37.61 / 37.34 | 37.61 / 37.34 | **MATCH** |
| III | w 0.008 | 37.57 / 37.31 | 37.57 / 37.31 | **MATCH** |
| III | w 0.012 | 37.54 / 37.29 | 37.54 / 37.29 | **MATCH** |

Other constants:

| file:line | constant | code | source | verdict |
|---|---|---|---|---|
| :44 | BASELINE_C | 37.0 | "Tb is the body core temperature = 37 C" | **MATCH** |
| :47 | V_RMS | 1.56 | "using a constant Vrms of 1.56" | **MATCH** |
| :50 | CLINICAL_SETTING | 10 V, 185 pps, 210 us | "a 'high' clinical DBS electrical setting (10 V, 185 pps and 210 usec) [21]" | **MATCH** |
| :52 | METABOLIC_HEAT_ASSUMED_ZERO | True | "Qm is the metabolic heat source (we assumed Qm = 0 in this paper)" | **MATCH** |
| :95 | PEAK_RISE_K | 0.82 | 37.82 - 37.00; abstract "up to ~0.8 C" | **MATCH** value, see F-19 on the docstring |
| :104 | TISSUE_DENSITY_KG_PER_M3 | 1040 | "(kg/m3) = 1040" | **MATCH** |
| :105 | TISSUE_SPECIFIC_HEAT_J_PER_KGK | 3650 | "Cp is the specific heat of brain tissue (J/kg C) = 3650" | **MATCH** |
| :106 | BLOOD_DENSITY_KG_PER_M3 | 1057 | "the blood (kg/m3) = 1057" | **MATCH** |
| :107 | BLOOD_SPECIFIC_HEAT_J_PER_KGK | 3600 | "Cb is the specific heat of blood (J/kg C) = 3600" | **MATCH** |
| :108-110 | parameter sweep ranges | k (0.5,0.6); sigma (0.15,0.35); w (0.004,0.012) | Table I sweeps | **MATCH** for sigma and w; see F-20 for k |
| :114 | LEAD_3389_CONTACT_HEIGHT_UM | 1500 | "the 3389 DBS lead with 1.5 mm electrodes" | **MATCH** |
| :115 | LEAD_3389_SPACING_UM | 500 | "0.5 mm spacing between electrodes" | **MATCH** |
| :116 | LEAD_3387_SPACING_UM | 1500 | "the 3387 DBS lead with 1.5 mm electrodes and 1.5 spacing" | **MATCH** |
| :117-120 | docstring: 3387 runs ~0.2 K cooler because of wider spacing | as stated | "temperature using Lead 3387 was roughly 0.2 C lower than that using Lead 3389; this was because the Lead 3387 has a larger spacing distance between adjacent electrodes" | **MATCH** |
| :113 | LEAD_3389_CONTACT_DIAMETER_UM | 1270 | **not stated anywhere in this paper** | **UNVERIFIABLE** — see F-21 |

### Findings

**F-18 (PROVENANCE DEFECT — the citation resolves to a different paper than the one
transcribed).** `references.py:701-714` defines `elwassif2006` as:
`venue="Journal of Neural Engineering", volume="3(4)", pages="306-315",
doi="10.1088/1741-2560/3/4/008", pmid="17946574"` and, by omission, `source_type="journal"`
so `peer_reviewed` is `True`.
But `elwassif2006.py` states in its own "Note on the source" section: *"This is the IEEE
EMBS conference paper (Proc. 28th IEEE EMBS, New York, 2006, pp. 3580-3583). The authors
also published a longer treatment in J. Neural Eng. 3(4). **The values here are read from
the conference paper.**"* The repo's PDF is likewise the conference paper (first line of
`elwassif2006.txt`: "Proceedings of the 28th IEEE EMBS Annual International Conference").
So every one of these 12 Table I rows renders a citation to a **journal article that is not
where they came from**, with a DOI, page range, volume and PMID that belong to the other
paper. This is precisely the misattribution the package's own `with_measured_cic` docstring
says the package exists to prevent. The module noticed the split and documented it in prose;
the machine-readable provenance was not updated to match, and the code has no second key
(e.g. `elwassif2006_embs`) to point at.

**F-19 (docstring conflates two rows).** `PEAK_RISE_K`'s docstring says the 0.82 K row is a
worst case combining "highest tissue conductivity, **lowest thermal conductivity in the
sweep**, and zero perfusion". It is not: that row is sigma = 0.35 at **k = 0.527**, which is
not the lowest k in the sweep. The lowest-k row (k = 0.45, sigma = 0.30) independently
reaches the same 37.82 C. The rise is right; the characterisation of which conditions produce
it is wrong.

**F-20 (range narrower than the table).** `THERMAL_CONDUCTIVITY_RANGE_W_PER_MK = (0.5, 0.6)`
but Table I block II sweeps k over **0.45, 0.50, 0.55, 0.60** — the range as coded excludes
the lowest value actually simulated, which is the one that produces the hottest result in
that block. Should be (0.45, 0.60). By the audit's definition this is a coded range that
does not span what the source reports: **narrowed**.

**F-21 (UNVERIFIABLE — device spec presented as a paper value).**
`LEAD_3389_CONTACT_DIAMETER_UM = 1270.0` sits in a block headed "the authors' stated tissue
parameters" and under `REFERENCE = "elwassif2006"`. The conference paper gives contact
**length** (1.5 mm) and **spacing** (0.5 / 1.5 mm) but nowhere states a contact diameter.
1.27 mm is the Medtronic 3387/3389 datasheet figure (the paper cites "Implant Manual.
Medtronic 3387, 3389 lead kit" as its ref [21], but does not quote a diameter from it).
The number is almost certainly right as a device fact; it is **not** traceable to the cited
source, and no manufacturer reference exists in `references.py`.

**F-22 (undocumented geometry assumption in `implied_power_W`).** The default
`source_radius_m = 1.3803e-3` is unexplained. Recomputed: the equal-area sphere for the
lateral area of **four** 1.27 mm x 1.5 mm cylindrical contacts is
`r = sqrt(4 * pi * 1.27e-3 * 1.5e-3 / (4 pi)) = sqrt(2.3939e-5 / 12.566) = 1.38024e-3 m`,
which reproduces the constant to 5 significant figures. So the radius is built from **all
four** contacts of the lead, while the protocol being inverted energises **two adjacent
contacts** (the module's own docstring says so: "they energise two adjacent contacts on a
thermally insulated shaft"). Using the two-contact area instead gives r = 9.76e-4 m and an
implied power of 5.3 mW rather than 7.5 mW, and hence ~230 ohm rather than the quoted
325 ohm. The "sensible bipolar impedance" conclusion in the docstring therefore depends on an
unstated and internally inconsistent choice of four contacts. Flagged as a
literature-adjacent derivation, not a transcription error.

---

## 9. `neurostim/data/iso14708_3.py` — ISO 14708-3:2017 clause 17.1

Source: ISO 14708-3:2017(E), clause 17.1 (Replacement), Table 101, Formula (1), Table 102.
Read from `papers_stim_calc_ref/ISO-14708-3-2017.pdf`.

| file:line | constant | code | source text | source loc | verdict |
|---|---|---|---|---|---|
| :55 | MAX_OUTER_SURFACE_C | 39.0 | "a) no outer surface greater than 39 °C," | cl. 17.1(a) | **MATCH** |
| :64 | CEM43_VALID_RANGE_C | (39.0, 57.0) | "Formula (1) is valid for temperatures between 39 °C and 57 °C." | after Formula (1) | **MATCH** |
| :67-75 | CEM43_THRESHOLDS | muscle 40, fat 40, peripheral nerve 40, skin 21, bone 16, brain 2, BBB 15 | Table 101 prints exactly: muscle 40, fat 40, peripheral nerve 40, skin 21, bone 16, brain 2, BBB (blood brain barrier) 15 | Table 101 | **MATCH**, all seven rows |
| :78 | R_BELOW_43 | 0.25 | "R is 0,25 for T <43 °C" | Formula (1) defs | **MATCH** |
| :81 | R_AT_OR_ABOVE_43 | 0.5 | "and 0,5 for T >= 43 °C" | Formula (1) defs | **MATCH** |
| :61 | MRI_NO_RATIONALE_RISE_C | 2.0 | "If temperature rise is <=2 °C, then no further scientific rationale is needed." | Table 102, rows 8 and 9 | **MATCH** |
| :87-117 | `cem43()` formula | `sum(t_i * R**(43 - T_i))` | `CEM43 = sum_{i=1..n} t_i x R^(43-T_i)`, t_i in minutes, T_i the average tissue temperature in °C | Formula (1) | **MATCH**, exact |
| docstring | the three alternative conditions (a/b/c) | as stated | "shall comply with at least one of the following conditions (a, b, or c) when implanted, and when in normal operation, including recharge" | cl. 17.1 | **MATCH** |
| :58 | MAX_RISE_K = 2.0 | 39.0 - 37.0 | the standard states no baseline | — | **DERIVED**, and correctly labelled ("the 2 K design target implied by clause 17.1(a) at a 37 C baseline") |

`references.py:119-136` note for `iso14708_3_2017` — "Clause 17.1 gives the heat requirement:
no outer surface above 39 C, or no tissue above the Table 101 CEM43 dose thresholds, or
manufacturer justification. Brain threshold is 2 CEM43, twentyfold stricter than muscle or
peripheral nerve." — **MATCH**, and 2 vs 40 is exactly twentyfold.

### Findings

**F-23 (minor, wording).** Clause 17.1(c) reads "manufacturer's evidence that a higher
temperature rise, **than indicated in Table 101**, is justified for a particular
application". The module docstring drops the "than indicated in Table 101" clause, which
makes (c) read as a general escape hatch from (a) as well as (b). It is an escape from the
Table 101 dose thresholds specifically.

**F-24 (type-system, feeds into the flag question in section 14).** `iso14708_3_2017` is
declared `source_type="standard"`, which is not one of the six values the `SourceType`
docstring (`references.py:16-22`) lists, and is not in `PEER_REVIEWED`. So
`Reference.citation()` appends **"[STANDARD - not peer reviewed]"** to the ISO citation.
Technically true of a consensus standard, but a published ISO standard is not "unreviewed"
in the sense that label is meant to convey (a meeting abstract). Verified by running the
code.

---

## 10. `neurostim/data/riedy_walter1996.py` — Riedy & Walter (1996)

Source: Riedy LW, Walter JS, *Effects of low charge injection densities on corrosion
responses of pulsed 316LVM stainless steel electrodes*, IEEE TBME 43(6):660-663 (1996).

**Protocol constants — all MATCH:**

| file:line | constant | code | source | verdict |
|---|---|---|---|---|
| :58 | PULSE_WIDTH_US | 100.0 | "100 us pulses at a repetition rate of 60 pps" | **MATCH** |
| :59 | PULSE_RATE_PPS | 60.0 | same | **MATCH** |
| :60 | WAVEFORM | capacitor-coupled monophasic, either polarity | "The capacitor coupled monophasic stimulation protocol"; "Monophasic, anodic-first or cathodic-first current pulses" | **MATCH** |
| :61 | DISCHARGE_CAPACITOR_UF | 0.47 | "the capacitance (0.47 uF)" | **MATCH** |
| :62-63 | DISCHARGE_TIME_CONSTANT_MS + its docstring | 0.96; "0.47 uF into access + 1.8 kohm shunt + 100 ohm sense" | "The 0.96-ms time constant of the discharge circuit was calculated from the product of the capacitance (0.47 uF) and the resistance of the discharge circuit, which consisted of the sum of the access resistance of the electrodes, a 1.8-kOhm shunt resistor across the output of the stimulator, and a 100-Ohm current sensing resistor" | **MATCH**, verbatim |
| :65-67 | CHRONIC_* | 20 uC/cm^2, 3.8 mA, 365 days | "one-year to evaluate the corrosion response at a charge injection density of 20 uC/cm2 (3.8 mA)" | **MATCH** |
| :69-71 | PROTEIN_STUDY_* | 40 uC/cm^2, 11.2 mA, 10 days | "pulsed for 10 days"; "charge injection density which was increased to 40 uC/cm2 (11.2 mA)" | **MATCH** |
| :73-74 | WIRE_DIAMETER_MM + docstring | 0.17 mm; 7 mil, annealed, 670 MPa | "Single-strand 316LVM wire (7 mil, 0.17 mm in diameter) ... annealed condition with a tensile strength of 670 MPa" | **MATCH** |
| :75-76 | EXPOSED_LENGTH_* | 3.0 / 5.0 mm | "exposed length of 3 mm for the one-year study and 5 mm for the protein study" | **MATCH** |
| :78 | ALLOY_COMPOSITION_PERCENT | Cr 17, Ni 12, Mo 2.5, Fe balance | "17 Cr, 12 Ni, 2.5 Mo, and Fe balance" | **MATCH** |
| :80-84 | ELECTROLYTE | 29 mM bicarb / 3 mM phos / 137 mM NaCl, 5% CO2 / 6% O2, pH 7.4, weekly | "29 mM bicarbonate ..., 3 mM phosphate ..., and 137 mM NaCl ..., purged with 5% CO2/6% O2 gas to a pH of 7.4 ... replaced weekly"; SCE reference | **MATCH**, verbatim |

**Results constants — all MATCH:**

| file:line | constant | code | source | verdict |
|---|---|---|---|---|
| :88 | RECOMMENDED_LIMIT_UC_CM2 | 40 | "The safe charge injection density for pulsing of 316LVM electrodes has been reported to be 40 uC/cm2" | **MATCH** |
| :91 | NONFARADAIC_LIMIT_UC_CM2 | 20 | "only 20 uC/cm2 is available for nonfaradic charge transfer and double layer charge injection" | **MATCH** |
| :94 | REVERSIBLE_INJECTION_LIMIT_V | 1.2 | "reversible charge injection limit [8] and is reported to be 1.2 V for 316LVM [5]" | **MATCH** — but secondary, see F-25 |
| :101 | ANODIC_FIRST_SAFE_AT_LOW_DENSITY | True | "The SEM did reveal signs of pitting corrosion around the tip for the cathodically pulsed electrode. However, the SEM did not reveal any evidence of corrosion for the anodically pulsed electrode" | **MATCH** |
| :104 | TARNISH_ONSET_DAYS | 15 | "resulted in tarnishing ... after 15 days of continuous pulsing ... As the stimulation period continued, there was no further increase in the corrosion response" | **MATCH** |
| :107 | PROTEIN_AFFECTS_CORROSION | False | "The protein did not alter the corrosion response compared to electrodes stimulated in a protein-free environment" | **MATCH** |
| :122-127 | ONE_YEAR_DRIFT | E_acc +0.47 (A), +0.55 (C); E_max +0.73 (A), +0.63 (C) | "With anodic-first pulsing, E_acc(A) increased by 0.47 V over one-year of pulsing; with cathodic-first pulsing, E_acc(C) increased by 0.55 V ... With anodic-first pulsing, E_max(A) increased by 0.73 V; with cathodic-first pulsing, E_max(C) increased by 0.63 V" | **MATCH**, all four |
| :129 | INTERIM_EXTREME_V_VS_SCE | 2.0 | "interim extremes in electrode potential of approximately 1.5 V at the beginning of the period to bring the electrode potential to 2 V versus SCE" | **MATCH** |
| :132 | SUSTAINED_POTENTIAL_V_VS_SCE | 1.8 | "the subsequent 3000-h period during which the potential averaged about 1.8 V versus SCE" | **MATCH** |
| :136 | MAX_INTERPULSE_POTENTIAL_V | 0.7 | "E_ipp varied widely but at low voltages (less than 0.7 V). Since both the anodic and cathodic first pulses indicate similar corrosion responses, we do not feel that E_ipp values are causal in corrosion" | **MATCH**, and the non-causality claim is verbatim |

**Table I (protein study, n = 4) — all nine rows MATCH cell for cell:**

| bath | parameter | code initial / final | source initial / final |
|---|---|---|---|
| no protein | E_max | 1.10 +/- 0.08 -> 2.01 +/- 0.24 | 1.10 +/- 0.08 -> 2.01 +/- 0.24 |
| no protein | E_acc | 1.37 +/- 0.24 -> 2.09 +/- 0.36 | same |
| no protein | E_ipp | -0.25 +/- 0.07 -> -0.01 +/- 0.44 | same |
| interstitial | E_max | 1.34 +/- 0.18 -> 2.21 +/- 0.25 | same |
| interstitial | E_acc | 1.31 +/- 0.10 -> 1.69 +/- 0.22 | same |
| interstitial | E_ipp | -0.06 +/- 0.04 -> -0.11 +/- 0.09 | same |
| 10x interstitial | E_max | 1.24 +/- 0.12 -> 1.70 +/- 0.32 | same |
| 10x interstitial | E_acc | 1.29 +/- 0.10 -> 1.55 +/- 0.29 | same |
| 10x interstitial | E_ipp | -0.10 +/- 0.08 -> -0.08 +/- 0.03 | same |

`wire_area_cm2`'s docstring claim independently recomputed and **correct**:
- protein study, L = 5 mm: A = pi x 0.017 cm x 0.5 cm = 0.026704 cm^2;
  Q = 40 x 0.026704 = 1.068 uC; I = 1.068 uC / 100 us = **10.68 mA** vs the paper's
  11.2 mA -> 4.6 % low ("about 5 %"). ✓
- one-year study, L = 3 mm: A = 0.016022 cm^2; Q = 0.3204 uC; I = **3.204 mA** vs 3.8 mA
  -> 15.7 % low ("about 15 %"). ✓
The 0.016 cm^2 also matches `materials.py`'s `measured_area_cm2=1.6e-2` for SS316LVM. ✓

### Findings

**F-25 (secondary source, chain not recorded).** `REVERSIBLE_INJECTION_LIMIT_V = 1.2` is
*reported by* Riedy & Walter, citing their ref [5] (Lan, Daroux & Mortimer,
J. Electrochem. Soc. 136:947-954). It is not their measurement. `references.py` has no entry
for Lan et al., so the chain stops at the wrong paper. The code's docstring does say
"Reported reversible charge injection limit", which is honest; the machine-readable
provenance is not.

**F-26 (MISATTRIBUTION — the package's central claim about this paper is wrong, and it
gates behaviour).** The package states, in three places, that Riedy & Walter's **own
year-long experiment** concluded that 20 uC/cm^2 is the maximum feasible density:

- `riedy_walter1996.py:8-13` — "They then ran the experiment the recommendation was missing:
  365 days of continuous pulsing at 20 uC/cm^2. **Their conclusion is the one this package
  uses**: 20 uC/cm^2 is the maximum charge injection density feasible for functional
  neuromuscular stimulation";
- `materials.py:672-681` (`recommendation_note`) — "**Their own year-long experiment at
  20 uC/cm^2 concludes that 20 is the maximum feasible density** for functional
  stimulation";
- `materials.py:687-692` (`note`) — "**Their own year-long experiment at 20 uC/cm^2
  concludes that this is the maximum feasible density** for functional stimulation, so the
  conservative end here is the authors' recommendation rather than merely the low end of a
  range."

What the paper actually says (Discussion, p. 662, verbatim):

> "It has recently been suggested that **tissue surrounding the stimulating electrode is not
> damaged** as long as the charge density for biphasic pulses is kept below 0.2 uC/mm^2
> (20 uC/cm^2) **[8]**. **Based on this report**, 20 uC/cm^2 appears to be the maximum charge
> injection density feasible for FNS application."

The 20 uC/cm^2 recommendation is therefore based on **reference [8]** — a **tissue-damage**
criterion from a book chapter (Robblee & Rose, *Electrochemical guidelines for selection of
protocols and electrode materials for neural stimulation*, in Neural Prostheses: Fundamental
Studies, 1990, pp. 25-66; [8] is also the source of the 20 uC/cm^2 non-faradaic figure, the
access-voltage definition and the 316LVM flexibility statement in the same paper). It is
**not** a conclusion of the corrosion experiment.

What the corrosion experiment itself concluded is, if anything, the opposite in direction:

> "Despite the observed tarnishing for electrodes pulsed with either anodic- or cathodic-first
> pulses, **20 uC/cm^2 may still be suitable for many long-term intermittent in vivo
> applications with short duty cycles**. The tarnishing layer may be functioning as a
> passivation layer reducing further corrosion responses. Therefore, FNS applications
> requiring chronic stimulation may demand lower charge injection limits than those currently
> recommended."

This matters because `MeasuredRange.recommended_policy="conservative"` and
`exceeds_recommendation()` are driven by it: the package raises a warning whenever a user
selects `nominal` or `optimistic` for stainless steel, on the stated ground that the authors'
own experiment endorses 20. The two *other* planks of the argument **are** the paper's own
and do hold: "the safe use of 40 uC/cm2 may be optimistic since it was based on a relatively
short pulsing period of **one hour**" (Introduction) and "only 20 uC/cm2 is available for
nonfaradic charge transfer" (Abstract). The recommendation is defensible; the sentence
justifying it misdescribes its source, and `references.py` carries no entry for Robblee &
Rose 1990 so the real chain is invisible.

**F-27 (CONDITION-DROPPED, structural — the SS316LVM `MeasuredRange` describes the wrong
experiment).** `materials.py:653-686` stores SS316LVM's charge-injection limit as a
`MeasuredRange(low=0.02, high=0.04, units="mC/cm2", reference="riedy_walter1996",
pulse_width_us=100.0, waveform="capacitor-coupled monophasic, 60 pps, either polarity",
medium="...", measured_area_cm2=1.6e-2, area_basis="geometric")`.

**Riedy & Walter never measured a charge-injection capacity for 316LVM.** 40 uC/cm^2 "has
been reported" (their refs [5]-[7]); 20 uC/cm^2 is what "is available for nonfaradic charge
transfer" (their ref [8]). Both are carried into the paper, not produced by it. What the
100 us / 60 pps / interstitial-fluid / 0.016 cm^2 conditions describe is the **corrosion
experiment they ran at those two densities** — a different experiment from the one that
determined the densities. So this record attaches one experiment's conditions to another
experiment's numbers, which is precisely the failure mode the package's own README opens by
saying it exists to prevent. Every other `MeasuredRange` in the database ties conditions to
the measurement that produced the number; this one does not, and nothing in the record says so.

---

## 11. `neurostim/data/ta2o5_capacitor.py` — Rose et al. (1985) and Schmidt et al. (1982)

Sources: Rose TL, Kelliher EM, Robblee LS, *Assessment of capacitor electrodes for
intracortical neural stimulation*, J Neurosci Methods 12:181-193 (1985); Schmidt EM,
Hambrecht FT, McIntosh JS, *Intracortical capacitor electrodes: preliminary evaluation*,
J Neurosci Methods 5:33-39 (1982).

**Rose et al. (1985) constants:**

| file:line | constant | code | source | source loc | verdict |
|---|---|---|---|---|---|
| :68 | DIELECTRIC_CONSTANT_TA2O5 | 25.0 | "Ta2O5 has a dielectric constant of 25" | p.184 | **MATCH** |
| :71-72 | TIO2 rutile / anatase | 100 / 50 | "The rutile form of TiO2 has a dielectric constant of 100, which is 4 times that of Ta2O5; even the anatase modification has a dielectric constant of 50 which would provide a factor of two improvement" | p.186 | **MATCH** |
| :75 | SAFE_FRACTION_OF_FORMING_VOLTAGE | 0.8 | "For films formed anodically, the safe value is about 80% of the formation voltage" | p.183 | **MATCH** |
| :78 | SMOOTH_TA_CAPACITANCE_NF_MM2_AT_5V | 22.0 | "for a 5 V film on smooth Ta, the capacitance has been determined experimentally to be 22 nF/mm2 (Robblee et al, 1983c)" | p.184 | **MATCH** |
| :81 | MAX_LEAKAGE_CURRENT_NA | 10.0 | "it is generally accepted that the leakage current should not exceed 1-10 nA during operation of the electrode" | p.183 | **MATCH** |
| :87-89 | INTRACORTICAL_TARGET_* | 5 nC, 200 us, 1e-4 mm^2 | "we will use 5 nC delivered with a 200 us constant current pulse as an appropriate operational value (Brummer et al., 1983)"; Table III last column header "on 1 x 10^-4 mm^2 electrode / 200 us constant current pulse" | p.182; Table III p.191 | **MATCH** — but see F-28 |
| :92 | PORE_RESISTANCE_MAX_REDUCTION | 0.8 | "For short pulse durations, the capacitance of the real electrode can be reduced by as much as 80% of the value obtained by slow charging" | p.183 | **MATCH** |
| :146 | smooth Ta, 0.088 uC/mm^2, V_f 5 | 0.088 | "For operation at 80% of the formation voltage, the charge storage density is 0.088 uC/mm2" | p.184 | **MATCH**; note "22 nF/mm^2 at 4 V" is consistent (0.8 x 5 V) |
| :158-161 | Schaldach roughened Ta wire, 1.5 uC/mm^2 | 1.5 | "Schaldach (1971) reported use of a roughened tip of an anodized 2 mm diameter Ta wire for cardiac pacemakers. The charge storage was about 1.5 uC/mm2 at breakdown voltage of 2 V" | p.184 | **MATCH** for the charge; `forming_voltage_V=2.5` is **DERIVED** (2 V / 0.8), not in the source — see F-29 |
| :167 | Guyton & Hambrecht sintered disc, 7.0 uC/mm^2 | 7.0 | "Guyton and Hambrecht (1973, 1974) developed a high capacity electrode for surface stimulation based on an anodized porous disk of sintered tantalum. They achieved a charge storage of 7 uC/mm2 at 80% of the forming voltage" | p.184 | **MATCH**; = 700 uC/cm^2 ✓, and the note's identification of this as Merrill's 700 uC/cm^2 macroelectrode is sound |
| :182-191 | Lerner sintered Ta microelectrode | 1.5 uC/mm^2, area 0.26 mm^2, V_f 5, 100 us | "anodized to 5 V in 0.015 M H2SO4"; "capacitance ... 0.10 +/- 0.01 uF using constant current pulses as short as 100 us. When charging the electrodes to 4 V, 80% of their formation voltage, the charge storage density obtained was 1.5 uC/mm2. The area enhancement ... about a factor of 17 ... with 50 us pulses, the effective capacitance dropped to 80% of the maximum" | p.185 | **MATCH**; area 0.26 mm^2 is consistent (0.10 uF x 4 V / 1.5 uC/mm^2 = 0.267 mm^2) |
| :200-211 | etched Ta microelectrode, pulsed | 0.88 uC/mm^2, area 0.12 mm^2, V_f 10, 100 us | "a cone shaped tip with a roughened surface having a geometric area of about 0.12 mm2 ... anodized to 10 V vs SCE in 0.1 vol% H3PO4. The capacitance values ... ranged from 0.13 to 0.33 uF/mm2 corresponding to surface enhancement ratios of 12 to 30. At 80% of the formation voltage, the charge storage for pulses of 0.1 ms was 0.88 to 1.4 uC/mm2. Leakage currents at 8 V were on the order of 2 nA ... Prolonged soaking in protein-saline solution for up to 200 h resulted in no degradation ... no in vivo testing has been done with the etched electrodes" | p.186 | **MATCH**, every clause of the note verbatim |
| :217-218 | etched Ta best reported | 2.6 uC/mm^2, area 0.057 mm^2 | Table III row "Ta/Ta2O5 wire (etched): smallest areas tested 0.057 mm^2, highest charge density 2.6 uC/mm^2, lowest leakage 0.07 nA/nF, 0.26 nC on 1e-4 mm^2" | Table III p.191 | **MATCH** for value and area; `pulse_width_us=200.0` is **CONTRADICTED**, see F-30 |
| :232-233 | etched Ti best reported | 6.3 uC/mm^2, area 0.27 mm^2 | "Very high charge storage values of 6.3 uC/mm2 were obtained on etched Ti surfaces using 0.015 M H2SO4 ... etched ... at an elevated temperature of 55 °C ... This electrode had a geometric area of 0.27 mm2"; Table I col. 5 gives 1570 nF/mm^2 (AC), roughness 31, 0.4 nA/nF | p.188; Table I | **MATCH** for value, area and the 0.4 nA/nF; `pulse_width_us=200.0` is **CONTRADICTED**, see F-30 |
| :247-248 | sputtered BaTiO3 | 0.07 uC/mm^2, area 100 mm^2 | Table III row "Pt/BaTiO3 planar sheet (smooth): 100 mm^2, 0.07 uC/mm^2, 0.2 nA/nF, 0.007 nC" | Table III | **MATCH** |
| :259-266 | IN_VIVO_* | 0.94 uC/mm^2, 1.3 mA/mm^2; 0.5 ms, 50 Hz, 3.8 mA/mm^2; less damage than metal or carbon | "The electrodes were tested in vivo at current densities as high as 1.3 mA/mm2 and charge densities as high as 0.94 uC/mm2 ... The authors concluded that the Ta/Ta2O5 electrodes resulted in less tissue damage than that associated with metal or carbon electrodes under comparable stimulation parameters of 0.5 ms, 50 Hz, 3.8 mA/mm2 geometric" | p.184-5 | **MATCH**, verbatim |
| :107-109 | `to_uC_per_cm2` | x 100 | 1 mm^2 = 0.01 cm^2 | — | **MATCH**, conversion correct |
| :164-175 | `parallel_plate_capacitance_F` worked case | 10 nm BaTiO3, k=7000, 1e-4 mm^2, 4 V -> ~2.4 nC | "an electrode with a geometric area of 10^-4 mm2 coated with a 10 nm BaTiO3 film having a dielectric constant of 7000 and pulsed to 4 V would store only 2.4 nC in a 0.2 ms pulse" | p.192 | **MATCH**; recomputed: C = 7000 x 8.854e-12 x 1e-10 / 1e-8 = 6.198e-10 F, Q = 2.48 nC ✓ |
| :126-137 | `smooth_capacitance_nF_mm2` thickness correction | 22 x 5 / V_f | the paper's "12 to 30" for 0.13-0.33 uF/mm^2 at 10 V is reproducible only with the correction: 22/2 = 11 nF/mm^2, 130/11 = 11.8, 330/11 = 30 | p.186 vs p.184 | **MATCH** — the module's reasoning is right and the arithmetic checks |
| :183-185 | `best_design()` | returns the 7.0 uC/mm^2 Guyton & Hambrecht disc | highest value in DESIGNS | — | **MATCH** with its docstring, and consistent with the Ti note's "Only the Guyton & Hambrecht surface macroelectrode stores more" |

**Schmidt et al. (1982) constants — all MATCH:**

| file:line | constant | code | source | verdict |
|---|---|---|---|---|
| :70 | SCHMIDT_PULSE_WIDTH_US | 100.0 | "Trains of 17 cathodal, 0.1 ms pulses at 400 Hz" | **MATCH** |
| :71 | SCHMIDT_PULSE_RATE_HZ | 400.0 | same | **MATCH** |
| :72 | SCHMIDT_PULSES_PER_TRAIN | 17 | same | **MATCH** |
| :73 | SCHMIDT_TRAIN_INTERVAL_S | 2.0 | "were delivered every 2 s using a constant current stimulator" | **MATCH** |
| :74 | SCHMIDT_ANODIC_BIAS_V | 4.2 | "anodically biasing the capacitor electrodes at +4.2 V DC and then pulsing them cathodically" | **MATCH** |
| :75 | SCHMIDT_THRESHOLD_UA | 35.0 | "The minimum threshold current for muscular activation with capacitor electrodes was 35 uA" | **MATCH** |
| :76 | SCHMIDT_IMPLANT_DAYS | 57 | "over a period of 57 days following implantation" | **MATCH** |
| :77 | SCHMIDT_TIP_EXPOSURE_UM | 500.0 | "carefully removed with a scalpel from the terminal 500 um of the tip region" | **MATCH** |
| :78 | SCHMIDT_MAX_DIAMETER_UM | 190.0 | "190 um (see Fig. 1A)" | **MATCH** |
| :80-88 | CAPACITOR_REQUIRES_ANODIC_BIAS docstring, "44.5 % lower" | 44.5 % | "Threshold currents were reduced by as much as 44.5%, compared with anodic pulsing" | **MATCH** |
| :90-94 | SCHMIDT_THREE_ELEMENT_TRANSIENT | access resistance, lumped pore resistance, lumped capacitance | "the access resistance, the lumped pore resistance of the electrode and the lumped capacitance as defined by Guyton and Hambrecht (1974) were determined" | **MATCH**, exact names |
| :95 | its docstring, "a single 100 uA, 0.1 ms pulse" | 100 uA, 0.1 ms | "passing a single 100 uA, 0.1 ms current pulse through each electrode" | **MATCH** |

### Findings

**F-28 (factor-of-2 error in a derived quantity in the module docstring).**
`ta2o5_capacitor.py:48-50` states: "Rose et al. set the target for intracortical
single-neuron stimulation at 5 nC in a 0.2 ms pulse on a **1e-4 mm^2** electrode, **which is
10,000 uC/cm^2 and 50 A/cm^2**."

The constant `INTRACORTICAL_TARGET_AREA_MM2 = 1e-4` is correct — that is Table III's
idealized area, stated twice in the paper. But the two densities come from a **different
area**. Source, p. 182: "we will use 5 nC delivered with a 200 us constant current pulse ...
The corresponding densities on electrodes with a geometric area of **0.5 x 10^-6 cm^2** as
used by Schmidt and McIntosh (1979) are 10,000 uC/cm^2 for the charge and 50 A/cm^2 for the
current."

0.5e-6 cm^2 = **5e-5 mm^2**, half the coded area. Recomputed on the coded area:
5 nC / 1e-6 cm^2 = **5,000 uC/cm^2**, and 25 uA / 1e-6 cm^2 = **25 A/cm^2**. The docstring
welds the introduction's densities onto Table III's area and is 2x off on both. The
constants themselves and `scaled_to_microelectrode_nC` (0.26 nC for Ta, 0.63 nC for Ti,
both matching Table III exactly) are unaffected.

**F-29 (DERIVED value stored in a field named for a measured one).**
`DESIGNS[1].forming_voltage_V = 2.5` for the Schaldach roughened Ta wire. The paper gives
only "1.5 uC/mm2 at **breakdown voltage of 2 V**" and no forming voltage. 2.5 is 2/0.8,
back-solved so that `safe_operating_voltage_V()` returns the paper's 2 V. The note flags the
oddity ("Quoted at a 2 V breakdown voltage rather than at 80 % of forming") but the field
still presents a number the source does not contain. Anything reading `forming_voltage_V`
programmatically gets an invented value. **UNVERIFIABLE** as a source value.

**F-30 (CONDITION MISMATCH — a pulse width asserted on two values that were not pulsed).**
Two `DESIGNS` entries carry `pulse_width_us=200.0`:

1. *etched Ta, best reported* (2.6 uC/mm^2). This is Table III's "**Highest charge
   density**" column, which the paper introduces as "the **best that have been reported for
   each property**" across different electrodes — the 200 us in Table III's header qualifies
   only the **last** column (the extrapolated nC). `materials.py:618-624` reaches the
   opposite conclusion about this very number and says so explicitly: "it agrees with the DC
   capacitance (0.33 uF/mm^2 x 8 V), so it is a **slow-charge figure**, not a pulsed one".
   The two modules therefore contradict each other about the same datum.
2. *etched Ti, best reported* (6.3 uC/mm^2). Table I records its capacitance as
   **1570 nF/mm^2 (AC)** and the table's own footnote d says "AC indicates measurement made
   with **capacitance bridge**", i.e. not a pulsed measurement at all. Table I's pulsed
   columns are marked (0.1) or (0.2); this one is not.

**F-31 (unsupported comparative claim).** `DESIGNS[6].note` says "**TiO2 buys 5-10x the
storage of Ta2O5** and pays about the same factor in leakage." The paper says TiO2 increases
charge storage "by a factor of **as much as 4**" (p. 186), and Table III's best values are
Ta 2.6 vs Ti 6.3 uC/mm^2 = **2.4x**, with lowest leakage 0.07 vs 0.10 nA/nF = **1.4x**.
Neither "5-10x" nor "about the same factor in leakage" is supported by anything I found in
the source. It also conflicts with the module's own `DIELECTRIC_CONSTANT_TIO2_*` docstring at
line 73 ("2-4x the permittivity ... at 1-2 orders more leakage current"), whose "2-4x" **is**
right and whose "1-2 orders" is likewise unsupported by the nA/nF column.

---

## 12. `neurostim/data/asanuma1976.py` — Asanuma, Arnold & Zarzecki (1976)

Source: *Further study on the excitation of pyramidal tract cells by intracortical
microstimulation*, Exp Brain Res 26(5):443-461 (1976).

| file:line | constant | code | source | source loc | verdict |
|---|---|---|---|---|---|
| :56 | PULSE_WIDTH_US | 200.0 cathodal | "0.2 msec duration" pulses used throughout | p.445 | **MATCH** |
| :102-110 | cell bodies | 0.12-0.2 ms, median 0.14, n = 4 | "Altogether 4 curves were constructed for cell bodies and 7 for fibers. The chronaxies for cell bodies ranged from 0.12-0.2 msec (median: 0.14 msec)" | p.451 | **MATCH** |
| :111-119 | axons | 0.06-0.13 ms, median 0.085, n = 7 | "those for fibers ranged from 0.06-0.13 msec (median: 0.085 msec)" | p.451 | **MATCH** |
| :118 | Mann-Whitney p < 0.012 | p<0.012 | "significantly longer than those for fibers (Mann-Whitney U test, p<0.012)" | p.451 | **MATCH** |
| :120-131 | Stoney 1968 PT cells | 0.12-0.4 ms | "compatible with the values previously obtained for PT cells (Stoney et al., 1968: 0.12-0.4 msec)" | p.451 | **MATCH** for the range; median 0.26 is the midpoint and **is labelled as such** in the note ✓; `n_curves=3` is **UNVERIFIABLE** from this paper — Asanuma states no n for Stoney's curves |
| :132-143 | spinal cord fibres | 0.04-0.08 ms | "Fibers in the spinal cord are shown to have short chronaxies ranging from about 0.04-0.08 msec (BeMent and Ranck, 1969; Jankowska and Roberts, 1972; Jankowska and Smith, 1973)" | p.451 | **MATCH**; median 0.06 labelled as the midpoint ✓ |
| :146 | PAIRED_SAME_NEURON_MS | cell_body 0.13, fibre 0.10 | "The chronaxie was longer (0.13 msec) at the cell body than at the fiber (0.10 msec)" | p.451 | **MATCH** |
| :154 | MIN_AXON_THRESHOLD_UA | 0.4 | "the minimum current obtained was 0.4 ua" | p.452 | **MATCH** |
| :155 | TYPICAL_AXON_THRESHOLD_CEILING_UA | 5.0 | "thresholds were frequently less than 5.0 ua" | p.452 | **MATCH** |
| :160 | COLLATERAL_REACH_MM | 1.0 | "These axon collaterals extended as far as 1.0 mm horizontally from [the cell body]" | Abstract, p.443 | **MATCH** |
| :163 | LOW_THRESHOLD_CYLINDER_RADIUS_MM | 1.0 | "found within a radially oriented cylindrical cortical region with a radius of about 1 mm, centered at the recorded PT cells" | p.450 | **MATCH** |
| :166 | SURFACE_LOW_THRESHOLD_AREA_MM2 | (2.0, 4.0) | "the area of low thresholds for activating the PT cell expands to as wide as 2.0-4.0 mm2" | p.451 (Discussion) | **MATCH** to the body text; the **Abstract says 3-4 mm2** — paper-internal, code follows the body |
| :169 | SURFACE_EXTENT_AT_HIGH_CURRENT_MM | (4.0, 5.0) | "the effective extent on the surface becomes 4-5 mm" | p.~455 | **MATCH** |
| :170 | SURFACE_HIGH_CURRENT_UA | (400.0, 500.0) | 400 ua appears twice ("this trial was 400 ua"; "repetitive surface anodal stimulation with intensity of 400 ua"); **500 ua not located** | — | **PARTIALLY UNVERIFIABLE** — the 400 is sourced, the 500 is not |
| :178 | MONOSYNAPTIC_SPREAD_SUPERFICIAL_MM | 0.4 | "superficial layers are stimulated (~0.4 mm) although the spread is wider in the [deeper layers]" | p.~456 | **MATCH** |
| :183 | NOXIOUS_CURRENT_UA | 80.0 | "Same response 1 min after delivering ICMS of 80 ua" (Fig. legend) | p.~449 | **MATCH** |
| :195 | OPTIMAL_TRAIN_FREQUENCY_HZ | (300.0, 400.0) | "300-400 cy/sec used for previous ICMS experiments"; "In all, 5 curves from the surface and 7 curves from the depth ... 300-400 cy/sec" | p.~453 | **MATCH** |
| :197-200 | TRAIN_DURATION_TO_MIN_THRESHOLD_MS | surface (8, 18, 11.8); depth (20, 32, 27.2) | "The values for the surface ranged from 8-18 msec and the average was 11.8 msec. Those for the depth ranged from 20-32 msec, the average being 27.2" | p.~454 | **MATCH** |
| :208 | I_WAVE_PLATEAU_MS | (15.0, 20.0) | "These I-waves grew significantly larger after 15-20 msec from the [start of the train]" | Abstract; p.~453 | **MATCH** |
| :44-47 | Fig. 4 typo note | "20, 2.5 and 1.0 ua", suspected slip for 2.0 | the flagging is a package judgement, and `rheobase_fibres_ua(as_printed=True)` preserves the printed value | Fig. 4 caption | **correctly handled** — value stored as printed, correction offered explicitly rather than silently applied |

`threshold_ratio_at` returns `1 + t_c/W`, which equals 2 at chronaxie for both the Weiss and
Lapicque forms — a definitional identity, not a literature value. Its docstring caution (that
the published curves reach 4-5x rheobase at 0.1 ms where the fitted chronaxies predict
1.9-2.4x) is consistent with Fig. 4 as printed.

`ELECTRODE_TIP_UM = (10.0, 15.0)` and `PREPARATION` — **not located** in the extracted text;
see the unverified list in section 17.

---

## 13. `neurostim/materials.py` — the material database

### 13a. Cogan (2008) Table 2, "Charge-injection limits of electrode materials for stimulation in the CNS", p. 282

Transcribed from the source table cell by cell:

| source row | source Qinj (mC/cm^2) | source limits (V vs Ag\|AgCl) | source refs | code | verdict |
|---|---|---|---|---|---|
| Pt and PtIr alloys, faradaic/capacitive | 0.05-0.15 | -0.6-0.8 | 71 | Pt and PtIr both 0.05-0.15, `_PT_IR_WINDOW` -0.6/+0.8 | **MATCH** |
| Activated iridium oxide, faradaic | 1-5 | -0.6-0.8 | 72, 73 | AIROF **1.0-3.5** (Beebe & Rose primary), note says "Cogan 2008 Table 2 rounds this row to 1-5" | **MATCH** (deliberate, documented departure to the primary) |
| Thermal iridium oxide, faradaic | ~1 | -0.6-0.8 V | 74 | TIROF 1.0, `approximate=True`, ref `robblee1986_tirof` | **MATCH**, and "No pulse width is stated for this row in either source" is correct — the table has no pulse-width column at all |
| Sputtered iridium oxide, faradaic | 1-5 | -0.6-0.8 V | 75 + unpublished | SIROF 1.0-5.0, ref `cogan2004_sirof` | **MATCH** |
| Tantalum/Ta2O5, capacitive | ~0.5 | **(cell blank)** | 76, 77 | Ta2O5 **0.088-0.15** from Rose 1985 primary; `water_window=None` | **MATCH** (departure documented); the `None` window correctly mirrors the blank cell |
| Titanium nitride, capacitive | ~1 | -0.9 to 0.9 | 78 | TiN 1.0 `approximate=True`, window -0.9/+0.9, ref `weiland2002_tin` | **MATCH** |
| PEDOT, faradaic | 15 | -0.9 to 0.6 | 79 | PEDOT **2.3-3.6** from Cui & Zhou primary; window -0.9/+0.6 ref `cogan2008` | **MATCH** for the window; the Qinj departure is deliberate and documented |

Table 2 comment column also checks out verbatim: "Positive bias required for high Qinj.
Damaged by extreme negative potentials (<-0.6 V)" (AIROF/SIROF), "Requires large positive
bias" (Ta2O5), "Oxidized at positive potentials" (TiN), "Benefits from positive bias"
(SIROF, PEDOT) — each reproduced in the corresponding `note` or `bias` field.
The TiN window's note ("water reduction and oxidation at -0.9 V and 0.9 V by slow-sweep
cyclic voltammetry") is verbatim from p. 282: "water reduction and oxidation potentials of
-0.9 V and 0.9 V (versus Ag|AgCl), respectively, as measured by slow-sweep-rate cyclic
voltammetry". **MATCH.**

**Stainless steel is indeed absent from Cogan Table 2** — confirmed by reading the table.
The README's and `materials.py`'s claim on that point is correct.

### 13b. Rose & Robblee (1990) — the Pt row, read from the primary

| file:line | constant | code | source | verdict |
|---|---|---|---|---|
| :358-362 | Pt cic low/high | 0.05-0.15 mC/cm^2 | Abstract: "charge injection limits of a Pt electrode using 0.2 ms charge balanced, biphasic current pulses ranged from **50 to 150 uC/cm^2** geometric" | **MATCH**; 50 uC/cm^2 = 0.05 mC/cm^2 ✓ |
| :369 | `anodic_first_range` | (0.05, 0.10) | "the charge injection limit for anodic-first pulses is about **50-100 uC/cm^2 geom**" | **MATCH** |
| :370 | `cathodic_first_range` | (0.10, 0.15) | "and the charge injection limit for cathodic-first pulses is about **100-150 uC/cm^2**" | **MATCH** |
| :363 | pulse_width_us | 200.0 | "The pulse width was 0.2 ms, and the repetition rate was 50 pps" | **MATCH** |
| :364 | waveform | charge-balanced, capacitively coupled biphasic, 50 pps | "capacitively coupled with either cathodic-first (CF) or anodic-first (AF) polarity"; 50 pps | **MATCH** |
| :366 | area_basis | geometric | "The values are normalized to the geometric area of the electrode" | **MATCH** |
| note | potential limits -0.60 / +0.90 V **vs SCE** | as stated | "These limits were **-0.60 and +0.90 V versus SCE**, respectively" | **MATCH** — the package's SCE-vs-Ag\|AgCl caveat is well founded, and Cogan's table does print -0.6-0.8 vs Ag\|AgCl |
| note | 1 ms lifts CF limit to 250 uC/cm^2 | 250 | "Type A electrodes injected **250 uC/cm^2 with CF pulses** and 225 uC/cm^2 with AF pulses when the pulse duration was increased to **1 ms**" | **MATCH** |
| note | +0.9 V vs SCE bias lifts it to 600 uC/cm^2 | 600 | "the type C electrode was biased at 0.9 V versus SCE, up to **600 uC/cm^2 geom** could be injected with 0.2 ms cathodal pulses" | **MATCH** |
| note | Brummer & Turner 300-350 uC/cm^2 real area at >0.6 ms | 300-350 | "electrochemically safe values of **300-350 uC/cm^2 real surface area**" | **MATCH** |
| :381-391 | ChronicThreshold Pt 20-50 uC/cm^2 | 20-50 | "We have shown previously that some Pt dissolution occurs even at charge densities of **20-50 uC/cm^2 geom** [9], [13]" | **MATCH**, though note it is Rose & Robblee reporting their own *earlier* work, cited to refs [9]/[13], neither of which is in `references.py` |

### 13c. Beebe & Rose (1988) — the AIROF row, read from the primary

| file:line | constant | code | source (Abstract, p. 494) | verdict |
|---|---|---|---|---|
| :437-438 | cic low/high | 1.0-3.5 mC/cm^2 | "...was **2.1 and 1.0 mC/cm^2 geometric for anodic-first and cathodic-first**, respectively, 0.2 ms balanced charge biphasic current pulses. Electrodes biased at +0.8 V versus SCE accepted charge up to **3.5 mC/cm^2 geometric** with monophasic cathodal pulses" | **MATCH** |
| :448-449 | anodic/cathodic sub-ranges | (2.1, 2.1) / (1.0, 1.0) | same sentence | **MATCH**, exact |
| :442 | bias | "+0.8 V vs SCE for the 3.5 mC/cm^2 monophasic cathodal figure" | same sentence | **MATCH**, and correctly scoped to the 3.5 figure only |
| :441 | pulse_width_us / waveform | 200 us, biphasic 50 pps | "All pulsing was done with 0.2 ms pulses per phase and a repetition rate of 50 pulses/s" | **MATCH** |
| :443 | medium | bicarbonate buffered saline, pH 7.3 | "in bicarbonate buffered saline (0.1M NaCl + 0.023M NaHCO3)"; Fig. 1 caption "at pH 7.3" | **MATCH** (the "80 ohm.cm" resistivity was not located in the extraction — see section 17) |
| note | potential limits -0.6 / +0.8 **vs SCE** | as stated | "potential limits of -0.6 V and +0.8 V versus SCE" | **MATCH** |
| note | wire area 3.7-4.5e-4 cm^2 | as stated | "The areas ranged from **3.7 to 4.5 x 10^-4 cm^2**" | **MATCH** |
| :444 | `measured_area_cm2` | 4.1e-4 | **not printed** — it is the midpoint of 3.7-4.5e-4 | **DERIVED** (see F-32) |

### 13d. Other material rows

| file:line | constant | code | source | verdict |
|---|---|---|---|---|
| :515-519 | TiN, Weiland et al. 2002 | 0.9 mC/cm^2 in vitro, 0.5 ms, 4000 um^2 | via Cogan 2008 ref 78 and `references.py` note | **MATCH** to what the package itself records; **not independently verified** — Weiland 2002 is not in `papers_stim_calc_ref/` (section 17). Note the stored `cic` is 1.0 (Cogan's "~1"), not Weiland's 0.9, and the note says so explicitly ✓ |
| :540-555 | PEDOT peer-reviewed cluster | 2.3 (Cui & Zhou 2007), 2.5 +/- 0.1 (Luo 2011), 3.6 (Nyberg 2007, 1 ms, ITO) | Cui & Zhou DOI resolves to the right paper; Nyberg DOI resolves to the right paper; 3.6 mC/cm^2 for PEDOT-PSS on ITO at 1 ms is recorded in `references.py` | **MATCH** for the sources' identity; the three individual Qinj values were **not independently read** from Cui & Zhou, Luo or Nyberg — those PDFs are absent (Luo is present as `nihms-292839`, the other two are not). See section 17 |
| :555 | PEDOT `pulse_width_us` | 400.0 | Cui & Zhou's pulse width was not read | **UNVERIFIABLE** (see section 17) |
| :26-37 | AIROF_TEMPERATURE_GAIN = 2.0/1.67 | Qinj 1.67 -> 2.0 mC/cm^2 between 20 C and 37 C at 0.1 ms; R_access 5360 -> 4052 ohm | Cogan 2008 body text | **MATCH** to what `references.py` records; the specific Cogan sentence was not re-located in this pass (the claim is repeated identically in `materials.py:449-451` and README) |
| :23 | BODY_TEMPERATURE_C = 37.0 | 37 C | physiological constant | **MATCH** |

### Findings

**F-32 (DERIVED midpoint in a field named for a measurement).** `measured_area_cm2=4.1e-4`
on the AIROF row is the arithmetic midpoint of Beebe & Rose's stated 3.7-4.5e-4 cm^2 range.
The source prints a range; the code stores a single number in a field whose name asserts it
was measured. Harmless numerically (nothing divides by it), but it is the same category of
silent derivation the package elsewhere flags explicitly (contrast `asanuma1976.py`, which
labels its midpoints as midpoints — the right pattern).

**F-33 (the Cogan-vs-primary departures are all sound).** Three material rows deliberately
disagree with Cogan Table 2 — AIROF (1-3.5 not 1-5), PEDOT (2.3-3.6 not 15), Ta2O5
(0.088-0.15 not ~0.5). Each departure is documented in the row's `note`, each cites the
primary that supports it, and in each case the reasoning checks out against the primary text
I read. This is the strongest part of the package and it does what the README claims.

**F-34 (recap of F-26/F-27).** The SS316LVM row is the exception: its number is secondary
inside its cited source, its conditions belong to a different experiment, and its
`recommendation_note` misattributes the recommendation. Detail in section 10.

---

## 14. `neurostim/references.py` — DOI spot-checks and the provenance flags

### DOI resolution — 15 checked against Crossref, plus the IT'IS DataCite DOI

| key | DOI in code | resolves to | code metadata | verdict |
|---|---|---|---|---|
| shannon1992 | 10.1109/10.126616 | Shannon, "A model of safe levels for electrical stimulation", IEEE TBME 39(4):424-426, 1992 | 39(4), 424-426, 1992 | **MATCH** |
| mccreery1990 | 10.1109/10.102812 | McCreery, Agnew, Yuen, Bullara, "Charge density and charge per phase as cofactors...", IEEE TBME 37(10):996-1001, 1990 | 37(10), 996-1001, 1990 | **MATCH** |
| merrill2005 | 10.1016/j.jneumeth.2004.10.020 | Merrill, Bikson, Jefferys, "Electrical stimulation of excitable tissue...", J Neurosci Methods 141(2):171-198, 2005 | 141(2), 171-198, 2005 | **MATCH** |
| cogan2008 | 10.1146/annurev.bioeng.10.061807.160518 | Cogan, "Neural Stimulation and Recording Electrodes", Annu Rev Biomed Eng 10:275-309, 2008 | 10, 275-309, 2008 | **MATCH** |
| rose_robblee1990 | 10.1109/10.61038 | Rose & Robblee, "Electrical stimulation with Pt electrodes. **VIII**. ... 0.2 ms pulses", IEEE TBME 37(11):1118-1120, 1990 | 37(11), 1118-1120, 1990, "VIII" | **MATCH** — and this **confirms the package's claim** that Cogan 2008 ref. 71 printing "VII" at 37:1119-20 is an error in Cogan's reference list |
| beebe_rose1988 | 10.1109/10.2122 | Beebe & Rose, "Charge injection limits of activated iridium oxide electrodes with 0.2 ms pulses in bicarbonate buffered saline", IEEE TBME 35(6):494-495, 1988 | vol "35", 494-495, 1988 | **MATCH** (issue number 6 not recorded; volume and pages correct) |
| riedy_walter1996 | 10.1109/10.495287 | Riedy & Walter, "Effects of low charge injection densities on corrosion responses of pulsed 316LVM stainless steel electrodes", IEEE TBME 43(6):660-663, 1996 | 43(6), 660-663, 1996 | **MATCH** |
| newman1966 | 10.1149/1.2424003 | Newman, "Resistance for Flow of Current to a Disk", J Electrochem Soc 113(5):501, 1966 | 113(5), 501-502, 1966 | **MATCH** |
| rand_woods1971 | 10.1016/0368-1874(71)80004-7 | Rand & Woods, "The nature of adsorbed oxygen on rhodium, palladium and gold electrodes", J Electroanal Chem 31(1):29-38, 1971 | 31(1), 29-38, 1971 | **MATCH** |
| nyberg2007_pedot | 10.1016/j.jneumeth.2006.08.008 | Nyberg, Shimada, Torimitsu, "Ion conducting polymer microelectrodes for interfacing with neural networks", J Neurosci Methods 160(1):16-25, 2007 | 160(1), 16-25, 2007 | **MATCH** |
| cui_zhou2007 | 10.1109/TNSRE.2007.909811 | Cui & Zhou, "Poly(3,4-Ethylenedioxythiophene) for Chronic Neural Stimulation", IEEE TNSRE 15(4):502-508, 2007 | 15(4), 502-508, 2007 | **MATCH** |
| rose1985_capacitor | 10.1016/0165-0270(85)90001-9 | Rose, Kelliher, Robblee, "Assessment of capacitor electrodes for intracortical neural stimulation", J Neurosci Methods 12(3):181-193, 1985 | vol "12", 181-193, 1985 | **MATCH** |
| stoney1968 | 10.1152/jn.1968.31.5.659 | Stoney Jr, Thompson, Asanuma, "Excitation of pyramidal tract cells by intracortical microstimulation: effective extent of stimulating current", J Neurophysiol 31(5):659-669, 1968 | 31(5), 659-669, 1968 | **MATCH** |
| itis2025 | 10.13099/VIP21000-04-2 | redirects to IT'IS "Tissue Properties Database V4.2", release date **04/06/2024** | `year=2025` | **DOI resolves; YEAR MISMATCH** — see F-36 |
| elwassif2006 | 10.1088/1741-2560/3/4/008 | Elwassif, Kong, Vazquez, Bikson, "Bio-heat transfer model of deep brain stimulation-induced temperature changes", **J Neural Eng 3(4):306-315, 2006** | 3(4), 306-315, 2006 | **DOI and metadata internally consistent — but it is the wrong paper for the values stored.** See F-18 |
| leung2014 | 10.1109/TBME.2014.2366514 | Leung, Shivdasani, Nayagam, Shepherd, "In Vivo and In Vitro Comparison of the Charge Injection Capacity of Platinum Macroelectrodes", IEEE TBME 62(3):849-857, **2015** | `year=2014`, vol 62(3), 849-857 | **YEAR MISMATCH** — see F-35 |

A deliberately malformed DOI (`10.1016/j.jmeth.placeholder`) returned HTTP 404, confirming
the check would have caught a bad DOI.

### Findings

**F-35 (MISMATCH, minor).** `leung2014` is dated 2014 in the code; Crossref, and the journal
issue (IEEE TBME vol 62, issue 3), date it **2015**. Cogan 2016 itself cites it as
"Leung et al 2015". The reference key, the `year` field and every rendered citation are off
by a year. Volume, issue, pages, title and authors are all correct.

**F-36 (MISMATCH, minor).** `itis2025` carries `year=2025` and a note saying the values were
"read from materialparameterdatabasecurrent20250821.xls, the release current at 2026-08".
The DOI resolves to IT'IS "Tissue Properties Database **V4.2**", whose release date the IT'IS
download page gives as **04/06/2024**. Either the version or the year is wrong: a 2025 file
is not v4.2's release, and the title field says "Version 4.2". The cited spreadsheet is
**not present in the repository**, so the specific numbers cannot be traced (section 17).

**F-37 (`user_measurement` is flagged peer-reviewed).** `references.py:609-618` defines
`user_measurement` with no `source_type`, so it defaults to `"journal"` and
`cite("user_measurement").peer_reviewed` returns **`True`** (verified by running the code).
`Reference.citation()` even contains `if not self.peer_reviewed and self.source_type != "user"`,
which shows the author intended `source_type="user"` — the `SourceType` docstring lists
`user` as a valid value — and it was never set. The consequence is contained today only
because `MeasuredRange.describe()` special-cases the key by name
(`materials.py:176`: `if not self.peer_reviewed and self.reference != "user_measurement"`),
so the display is right by a second mechanism. Any code that asks the reference itself
whether a user measurement is peer-reviewed gets the wrong answer.

**F-38 (`PROVISIONAL` never fires in the shipped database).** The README states, in the
opening warning box: *"Values that could not be confirmed against a primary source are
flagged `PROVISIONAL` wherever they surface."* Verified by running the code:

```
not verified: []          # no Material has verified == False
not peer reviewed: []     # no Material's CIC reference has peer_reviewed == False
```

Every one of the nine `MeasuredRange` records and every `WaterWindow` takes the default
`verified=True`. The only path that ever produces `PROVISIONAL` is
`with_measured_cic()`, which sets `verified=False` on a **user's own** measurement — i.e. the
flag fires only for values that are not literature at all. That is not wrong (the
`PROVISIONAL` machinery works, and it is exercised), but the README sentence implies a class
of literature values carrying the flag, and there are none. The same is true of
`TissueThermalProperties`: `fully_verified` returns `True` for the shipped defaults.

**F-39 (`NOT PEER REVIEWED` never fires either, and the README claims it does).** README,
Known limitations: *"**PEDOT's headline limit is not peer reviewed** — it comes from a meeting
abstract, and is flagged `NOT PEER REVIEWED` at every point of use."* Both halves are wrong
as the code now stands:
- The headline 15 mC/cm^2 abstract value **is not used at all**. `materials.py` PEDOT
  references `cui_zhou2007`, a peer-reviewed journal paper, at 2.3-3.6 mC/cm^2, and its note
  says in terms "Cogan's headline 15 mC/cm^2 ... is not used here".
- Consequently nothing is flagged: `cui_zhou2007.peer_reviewed` is `True`, so
  `MeasuredRange.describe()` appends nothing. Run output above confirms **no** material in
  the database has an unreviewed CIC reference.
`cogan2007_pedot` is correctly typed `source_type="abstract"` (peer_reviewed `False`) and is
still in the bibliography — so the machinery is right and the label would render if the value
were used. It is the README that is stale.

**F-40 (`audit.py` does not record the provenance flags it exists to preserve).**
`audit.py:121-139` builds the `constants` block from `material.key`, `cic.units`, `cic.low`,
`cic.high`, `cic.reference`, `cic.pulse_width_us`, `shannon_k_default`, the water window and
the chronic threshold. It does **not** capture `cic.verified`. Two runs — one on a literature
material, one on a `with_measured_cic` copy that happens to carry the same low/high — differ
in `cic.reference` (so the digest does change, which saves it), but the `PROVISIONAL` status
itself is absent from the record. Also absent from the digest payload:
`area_basis`, `waveform`, `bias`, `medium`, `temperature_C`, `measured_area_cm2`, the
polarity sub-ranges and `recommended_policy` — i.e. exactly the measurement conditions the
package's opening paragraph says are the point. A record reproduced years later proves the
*numbers* were the same; it does not record the conditions under which they were measured.

**F-41 (`source_type="standard"` is undeclared).** See F-24. `SourceType`'s docstring lists
six values; the code uses eight (`standard` and, intended but unset, `user`). `standard` is
not in `PEER_REVIEWED`, so ISO 14708-3 renders as "[STANDARD - not peer reviewed]".

---

## 15. Gabriel 1996 vs IT'IS v4.2 — which is actually in the code

**Both are, for different quantities, and the README does misstate one of them.**

| quantity | value in code | source key | where |
|---|---|---|---|
| default electrical conductivity for field/access-resistance calculations | **0.35 S/m** | `elwassif2006` (the DBS-modelling convention) | `field.py:42` `BRAIN_CONDUCTIVITY_S_PER_M` — the **package default**, used by `potential_V` and everything downstream |
| grey-matter electrical conductivity, alternative | **0.419 S/m** (sd 0.230, n = 214) | IT'IS v4.2 | `field.py:52` `GREY_MATTER_CONDUCTIVITY_S_PER_M` — offered, **not** the default |
| white-matter electrical conductivity | **0.348 S/m** (sd 0.194, n = 194) | IT'IS v4.2 | `field.py:59` |
| blood electrical conductivity | **0.662 S/m** (sd 0.107, n = 33) | IT'IS v4.2 | `field.py:67` |
| frequency-dependent complex permittivity and conductivity | four-Cole-Cole parameters | **Gabriel 1996 Part III**, `gabriel1996_iii` | `data/gabriel1996.py` — a **standalone module, wired into no calculation**; nothing in `safety/`, `models/` or `transient.py` calls it |
| thermal conductivity, density, specific heat, perfusion, blood properties, metabolic heat | 0.547 W/m/K, 1044.5 kg/m^3, 3695.8 J/kg/K, 0.013294 1/s, 1049.75 kg/m^3, 3617 J/kg/K, 16230 W/m^3 | IT'IS v4.2, `source="itis2025"` | `models/thermal.py:124-153`, with sd and n per field |

So: **IT'IS v4.2 supplies the thermal properties and the alternative electrical
conductivities; Gabriel Part III supplies a dispersion model that is exposed but not used;
and the actual default conductivity for every field and compliance calculation is 0.35 S/m
from Elwassif, which is neither of them.**

The `gabriel1996.py` module docstring is honest about all three and says why
(`0.35 S/m` is kept "for comparability with published DBS work"). Its arithmetic checks out —
running the code:

```
effective freq for a 200 us pulse (1/2W): 2500 Hz
  grey matter   sigma = 0.1043 S/m
  white matter  sigma = 0.0645 S/m
  blood         sigma = 0.7000 S/m
  muscle        sigma = 0.3316 S/m
0.35 / 0.1043 = 3.36    0.419 / 0.1043 = 4.02
```

`references.py:378-386` claims "Evaluated at the effective frequency of a 200 us pulse this
gives grey matter **0.104 S/m**, roughly **a third** of the 0.35 S/m DBS-modelling convention
and **a quarter** of the IT'IS value." **All three numbers verified: MATCH.**

### Findings

**F-42 (README misstatement, item 4 of the brief).** README, Known limitations:
*"**Thermal** — spreading-resistance heating only. **Tissue properties are now IT'IS v4.2 with
uncertainty**..."* — this is **correct** for `models/thermal.py`. But the README's **What it
computes** table attributes the compliance-voltage / access-resistance path to "Newman 1966"
and says nothing about which conductivity feeds it, and nowhere does the README say that the
**default electrical conductivity is 0.35 S/m from Elwassif, not the IT'IS 0.419 S/m**. A
reader of the README would reasonably conclude the package runs on IT'IS values throughout.
Since access resistance scales as 1/sigma, the undocumented default makes every compliance
number about **20 % higher** than the IT'IS-sourced alternative would give. The source code
documents this properly; the README does not.

**F-43 (Gabriel Part III is dead code with respect to every safety number).** `data/gabriel1996.py`
transcribes Table 1 perfectly (section 1) and computes a conductivity three to four times
lower than anything the package actually uses — and no calculation consumes it. It is a
documented comparison, not an input. That is defensible, but the README's Primary-sources
list does **not** mention Gabriel at all, while `references.py` holds two Gabriel entries, so
a reader checking provenance from the README will not find the module.

**F-44 (Gabriel Part I entry — its stated use is a caveat, not a value).** `references.py:170-188`
(`gabriel1996`, Part I) correctly states "Part I is a graphical survey with **no tabulated
values**; the parametric Cole-Cole model is in Part III". No numeric constant in the package
is sourced to Part I. The two caveats attributed to it (temperature coefficients of 1-2 %/C
at low frequencies; grey/white matter well characterised only above 10 kHz) were **not
re-verified against the Part I text** in this pass — see section 17.

**F-45 (the IT'IS numbers themselves are UNVERIFIABLE from here).** The IT'IS values in
`field.py` and `thermal.py` — 0.419/0.348/0.662 S/m, 0.547 W/m/K, 1044.5 kg/m^3,
3695.8 J/kg/K, 0.013294 1/s, 1049.75 kg/m^3, 3617 J/kg/K, 16230 W/m^3, and all the paired
(sd, n) values — could **not** be confirmed. The IT'IS database web pages render their tables
from JavaScript and returned no numbers to a fetch; the cited spreadsheet
(`materialparameterdatabasecurrent20250821.xls`) is not in the repository; and web search did
not surface the individual figures. The DOI resolves and the database is real, so this is an
access limitation, not evidence of an error. Two internal consistency checks that **do** pass:
- `perfusion_per_s` inverted on the stored 0.013294 1/s and 1044.5 kg/m^3 gives
  **763.7 ml/min/kg**, a round, plausible IT'IS-style grey-matter figure — the ml/min/kg ->
  1/s conversion (`x 1e-6 / 60 x rho`) is dimensionally correct and the docstring's warning
  about the factor-of-1000 density trap is right.
- the derived penetration depth `L = sqrt(kappa/W) = 3.29 mm` is physically sensible for
  perfused grey matter.

---

## 16. README verification

### 16a. "Corrections to the 0.1.0 prototype" table vs `materials.py` as it stands

| README row | README "current" | actual `materials.py` value | verdict |
|---|---|---|---|
| `SS` 0.05 -> | 0.02-0.04 mC/cm^2 | `SS316LVM` cic 0.02-0.04 mC/cm^2 | **MATCH** |
| `Pt` 0.10 -> | 0.05-0.15 | `Pt` cic 0.05-0.15 | **MATCH** |
| `PtIr` 0.15 -> | 0.05-0.15 | `PtIr` cic 0.05-0.15 | **MATCH** |
| **`PEDOT` 5.0 ->** | **3.6-15.0** | **`PEDOT` cic 2.3-3.6** | **MISMATCH** |
| `SIROF` 2.0 -> | 1.0-5.0 | `SIROF` cic 1.0-5.0 | **MATCH** |

**F-46 (README MISMATCH — the PEDOT row describes a version of the code that no longer
exists).** The README says PEDOT is now **3.6-15.0 mC/cm^2** and explains that "Cogan's
15 mC/cm^2 is from a **conference abstract**; the low end is Nyberg et al.'s peer-reviewed
value". `materials.py:534-539` actually holds **2.3-3.6 mC/cm^2**, referenced to
`cui_zhou2007`, with a note that rejects the 15 mC/cm^2 abstract value outright. The two
ranges overlap at a single point (3.6). Anyone reading the README to find the package's
PEDOT limit gets a number **4.2x** too high at the top end. Verified by running the code:
`PEDOT cic=2.3-3.6 mC/cm2 ref=cui_zhou2007`.

**F-47 (README arithmetic).** "Tracing every constant to its primary source changed **four of
the five** material values". The table immediately below lists **five** rows, all five of
which changed; and `materials.py` now ships **nine** materials (Pt, PtIr, AIROF, SIROF,
TIROF, TiN, PEDOT, Ta2O5, SS316LVM), so "the five" no longer describes the database either.

### 16b. Other README claims checked

| README claim | status |
|---|---|
| "Values that could not be confirmed against a primary source are flagged `PROVISIONAL` wherever they surface" | **stale/misleading** — no shipped value carries the flag (F-38) |
| "PEDOT's headline limit ... is flagged `NOT PEER REVIEWED` at every point of use" | **false as the code stands** — the abstract value is not used, and nothing is flagged (F-39) |
| "Charge-injection limit — Source: **Cogan 2008 Table 2**" (What it computes table) | **understates the code** — Pt/PtIr trace to `rose_robblee1990`, AIROF to `beebe_rose1988`, Ta2O5 to `rose1985_capacitor`, SS to `riedy_walter1996`; only SIROF, TIROF and TiN sit on Cogan's refs. The code went to the primaries; the README credits the review |
| "Water window — Source: Cogan 2008; **Merrill 2005**" | **no `WaterWindow` in the package references Merrill**; the windows cite `cogan2008` and `riedy_walter1996` |
| "Cogan gives platinum as a factor of three" (Uncertainty section) | **MATCH** — 0.05-0.15 mC/cm^2 is exactly 3x |
| "`charge.limit_interval_uC_cm2 # Interval(50.0, 150.0)`" | **MATCH** — 0.05-0.15 mC/cm^2 = 50-150 uC/cm^2 ✓ conversion correct |
| "Cogan also reports ~20 % temperature dependence (20 °C vs 37 °C)" | **MATCH** to `AIROF_TEMPERATURE_GAIN = 2.0/1.67 = 1.198`, i.e. +19.8 % ✓ arithmetic correct |
| "strong area dependence for SIROF; neither is corrected for" | **MATCH** — `materials.py` SIROF note records 5 mC/cm^2 on 2000 um^2 vs 750 uC/cm^2 on 0.05 cm^2 vs 100 uC/cm^2 for 200 nm SIROF at 10 ms, and no scaling is applied anywhere |
| "the ~0.8 K peak Elwassif et al. (2006) report ... **That gap is not reconciled**" | **stale** — `data/elwassif2006.py` and `models/thermal.py` **do** reconcile it at length (power ratio ~100x; "Compare power, not amplitude"). The README still says it is unreconciled |
| "VTA ... the default value was read from a **secondary summary**" | **MATCH and commendable** — `tehovnik2006`'s k ~ 675 uA/mm^2 is confirmed present in Tehovnik et al. 2006 ("K = 675 uA/mm^2", derived there as I/R^2 from 50 and 100 uA at 0.286 and 0.368 mm), and the README flags the weakness rather than hiding it |
| "Stainless steel is absent from Cogan Table 2" | **MATCH** — confirmed by reading Table 2 |
| "`tests/test_literature.py` pins ... the IT'IS tissue values and their unit conversion" | the test exists; the **underlying IT'IS numbers remain unverified against IT'IS** (F-45), so the test pins the code to itself for those rows |
| Primary-sources list (Shannon; McCreery 1990; Merrill; Cogan 2008; Rose & Robblee; Riedy & Walter; Brummer & Turner; Rand & Woods; Newman; Pennes; Elwassif; Lapicque; Weiss; Stoney; Tehovnik; Kuncel & Grill) | **incomplete** — omits Beebe & Rose 1988, Rose et al. 1985, Schmidt et al. 1982, Butterwick 2007, Cogan 2016, McCreery 1995, McCreery 2010, Asanuma 1976, Gabriel (both parts), IT'IS and ISO 14708-3, all of which supply constants |

---

## 17. What I could NOT verify, and why

Everything below is **UNVERIFIABLE** from this audit. None of it is evidence of an error —
it is where the trail stopped.

### 17a. Sources with no local copy and no accessible online text

| constant(s) | file:line | source needed | why it stopped |
|---|---|---|---|
| IT'IS grey/white/blood conductivity 0.419 / 0.348 / 0.662 S/m and their (sd, n) = (0.230, 214), (0.194, 194), (0.107, 33) | `models/field.py:52,59,67` | IT'IS v4.2 spreadsheet | The IT'IS web tables render from JavaScript and returned no numbers to WebFetch; the cited file `materialparameterdatabasecurrent20250821.xls` is **not in the repository**; web search did not surface the individual figures. The DOI resolves and the database is real |
| IT'IS thermal properties 0.547 W/m/K, 1044.5 kg/m^3, 3695.8 J/kg/K, 0.013294 1/s, 1049.75 kg/m^3, 3617 J/kg/K, 16230 W/m^3 and all six (sd, n) pairs | `models/thermal.py:124-153` | same | same. Two internal consistency checks pass (see F-45): the perfusion back-converts to 763.7 ml/min/kg and L = 3.29 mm is physically sensible |
| Weiland et al. (2002): 0.9 mC/cm^2 in vitro, 0.5 ms, 4000 um^2 | `materials.py:515-519`, `references.py:539-553` | Weiland, Anderson & Humayun, IEEE TBME 49:1574-1579 (2002) | not in `papers_stim_calc_ref/`; reachable only through Cogan 2008 ref 78, which prints only "~1" |
| Cui & Zhou (2007) 2.3 mC/cm^2 and its 400 us pulse width | `materials.py:534,538` | Cui & Zhou, IEEE TNSRE 15(4):502-508 | PDF absent. The **DOI resolves to the correct paper**; the Qinj value and the pulse width were not read from it |
| Nyberg et al. (2007) 3.6 mC/cm^2 on ITO at 1 ms, GSA 2500 um^2 | `references.py:586-595`, `materials.py` PEDOT note | Nyberg, Shimada & Torimitsu, J Neurosci Methods 160(1):16-25 | PDF absent. **DOI resolves to the correct paper**; the value was not read from it |
| Luo et al. (2011) 2.5 +/- 0.1 mC/cm^2, n = 4 | `references.py:296-306` | PDF **is** present (`nihms-292839`) | not read in this pass — ran out of scope, not out of source |
| Robblee et al. (1986) thermal iridium oxide "~1" | `references.py:492-503` | MRS Symp Proc 55:303-310 | conference proceedings, not online; reachable only through Cogan Table 2, which is what the code cites |
| Cogan et al. (2004) SIROF 1-5 mC/cm^2 | `references.py:517-530` | IEEE EMBS 2004 proceedings | not in the repo; reachable only through Cogan Table 2 |
| Cogan et al. (2007) PEDOT abstract 15 mC/cm^2 | `references.py:557-572` | MRS meeting abstract QQ2.7 | a meeting abstract with no DOI. **This is the package's own point** — it is correctly typed `source_type="abstract"` and correctly not used |
| Rose et al. (1985) 0.26 mm^2 area for the Lerner sintered electrode | `ta2o5_capacitor.py:183` | Rose 1985 | the paper gives 0.10 +/- 0.01 uF and 1.5 uC/mm^2 at 4 V, from which 0.267 mm^2 follows; the area itself was not located printed |
| Beebe & Rose (1988) electrolyte resistivity "80 ohm.cm" | `materials.py:443` | Beebe & Rose 1988 | not found in the text extraction; the rest of the medium string (bicarbonate buffered saline, pH 7.3) **is** confirmed |
| Cogan 2008 AIROF temperature sentence (1.67 -> 2.0 mC/cm^2, R_access 5360 -> 4052 ohm, 20 C -> 37 C at 0.1 ms) | `materials.py:26-37,449-451` | Cogan 2008 body | not re-located in this pass; the claim is internally consistent across three places in the package and the derived +19.8 % matches the README's "~20 %" |
| Gabriel Part I caveats (1-2 %/C temperature coefficients; grey/white matter characterised only above 10 kHz) | `references.py:181-187` | C Gabriel et al. 1996 Part I (PDF **is** present) | not read in this pass. No numeric constant depends on it |
| Stoney et al. (1968) n = 3 chronaxie curves | `asanuma1976.py:125` | Stoney 1968 (PDF **is** present) | Asanuma quotes Stoney's 0.12-0.4 ms range but states no n; Stoney itself not read for the count. **DOI resolves to the correct paper** |
| Tehovnik (2006) "quoted for **surface electrodes**" | `references.py:775-782` | Tehovnik 2006 (PDF present) | the value **K = 675 uA/mm^2 is confirmed** in the text (derived there from 50 and 100 uA at 0.286 and 0.368 mm); whether it is specifically the surface-electrode constant was not established |
| Asanuma 500 uA upper bound | `asanuma1976.py:170` | Asanuma 1976 | 400 uA appears twice in the text and "the effective extent on the surface becomes 4-5 mm" is confirmed; **500 uA was not located** |
| Asanuma `ELECTRODE_TIP_UM = (10.0, 15.0)` and `PREPARATION` | `asanuma1976.py:59,62` | Asanuma 1976 | not located in the extraction |
| Medtronic 3389 contact diameter 1.27 mm | `elwassif2006.py:113` | Medtronic implant manual | not stated in the cited conference paper; no manufacturer reference in `references.py` (F-21) |
| Lan, Daroux & Mortimer (1981) 1.2 V reversible limit for 316LVM | via `riedy_walter1996.py:94` | J Electrochem Soc 136:947-954 | the number is confirmed *as reported by* Riedy & Walter; the originating paper is not in the repo or in `references.py` (F-25) |
| Robblee & Rose (1990) book chapter — the actual source of the 20 uC/cm^2 recommendation | via `riedy_walter1996.py` and `materials.py` SS316LVM | Neural Prostheses: Fundamental Studies, pp. 25-66 | a book chapter, not online. Its role is established from Riedy & Walter's citation `[8]` (F-26); its own content was not read |
| Wang & Weiland (2012) 240 uC/cm^2 edge corrosion | `cogan2016.py:180`, `current_distribution.py:72` | via Cogan 2016 | not in the repo, no `references.py` entry (F-12) |
| McCreery (2008) 1-2 nC/ph physiological threshold | via `cogan2016.py:45` | via Cogan 2016 | not in the repo, no `references.py` entry |
| Pennes (1948), Lapicque (1907), Weiss (1901) | `references.py:687-700, 716-735` | originals | Pre-DOI. **No numeric constant in the package is sourced to any of them** — they carry equation forms only, so there is nothing numeric to check. The `pennes1948` entry's handling is exemplary: it states that the widely cited 1998 reprint DOI (10.1152/jappl.1998.85.1.5) belongs to the reprint "and must not be attached to this record", and correctly leaves `doi=""` |

### 17b. Things I chose not to re-derive

- The four `Derating` **numbers** for Pt/PtIr/AIROF/SIROF were checked against Leung, Hu,
  Kane and Cogan 2016 and are reported in F-10. What I did **not** do is recompute a
  pulse-width-matched derating for every material and propose replacements — that is a fix,
  not an audit finding.
- `safety/`, `transient.py`, `uncertainty.py`, `sensitivity.py`, `geometry/`, `io/`, `viz/`
  and `gui/` were out of scope for this audit except where a literature constant is consumed
  there. The Shannon/charge-density arithmetic itself belongs to the safety-math audit.
- `tests/test_literature.py` was not executed. Note that for the IT'IS rows it can only pin
  the code to itself, since the underlying numbers are unverified (F-45).

### 17c. One paper-internal problem worth repeating

McCreery et al. (1990) eq. (1) is transcribed correctly by the code, but the **paper's own
worked example does not follow from its own equation** — with QD_s = 800 uC/cm^2, R = 45 um,
x = 60 um it gives 160 uC/cm^2 against the paper's stated "approximately 130" (and 320 vs
260 for the 1600 uC/cm^2 case; the same 0.8125 ratio, so a consistent difference in R or x
rather than a single typo). The code carries only the equation, so it inherits no error, but
anyone checking the module against the paper's prose will hit this. Detail in F-4.
