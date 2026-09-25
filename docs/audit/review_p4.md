# Phase 4 Review (provenance) — `git log c89fdf4..507ab91`

Status: COMPLETE

Repo: .
HEAD: 507ab91. The main tree was not modified. A scratch worktree at c89fdf4 was created
under the session scratchpad and removed.

Every literature claim below was checked against the PDFs in `papers_stim_calc_ref/`. All 33
were text-extracted and identified by their own title page, not by filename. Riedy & Walter is
`10.495287.pdf`; McCreery 2010 is `nihms209066.pdf`. Where the text layer drops glyphs,
the page image was rendered (Riedy & Walter p. 663, Butterwick p. 2264, Leung p. 853).

## Summary

| # | Sev | Where | One line |
|---|---|---|---|
| M1 | MAJOR | audit.py `record` / `reproduces` | The digest does not cover results or the model constants Phase 1–4 changed (in-vivo derating, drift model, Butterwick exponent), and `package_version` is still 0.15.0. So a record whose answer changed **still "reproduces"**. Executed: a c89fdf4 record of Pt 500 µm in vivo (limiting current 70.12483601762932 µA) reproduces at HEAD (`(True, [])`), where the answer is now 112.84456370652995 µA (+61 %, C4.5). This is the failure the module docstring says the digest exists to prevent |
| M2 | MAJOR | cogan2016 `IN_VIVO_DERATING` (C4.5) | 8.7× is not the largest in-vivo reduction in Leung's own data. The acute suprachoroidal value at **100 µs is 3.84 µC/cm²** (abstract and results; Fig. 4, p. 853) against 34–35 in vitro, so **8.85–9.1×**. The paper's "8.7 times less (200 μs)" does not match its Fig. 4 at 200 µs (≈6×). Leung also states the reduction grows at short pulse widths, and gives no data below 100 µs. The 8.7× cap is therefore mildly non-conservative at 100 µs, unbounded below it, and not pulse-width-aware |
| M3 | MAJOR (pre-existing) | assessment.py `max_current_cic_uA` → `report()` / batch CSV | The 0.1.0-compat column ignores `medium`. For Pt 500 µm in vivo it reports **981.7477042468105 µA** while the Charge injection check's own in-vivo ceiling is **112.84456370652995 µA**: 8.7× high in every in-vivo batch row |
| M4 | MINOR | report()/batch CSV | The headline PROVISIONAL marker reaches describe, GUI and PDF, and the JSON `checks[].provisional`. It does not reach the CSV/`report()` (no provisional column), where `limiting_current_uA` is read by machine consumers. `limits_incomplete` is likewise absent there |
| M5 | MINOR | butterwick2007 docstring | Fig. 6's caption says 0.12 mm while the text says 0.115 mm. The module quotes 0.115 without noting the discrepancy. No number is affected |

Counts: **0 BLOCKER, 3 MAJOR (1 pre-existing), 2 MINOR.**

---

## M1 — MAJOR — the audit digest certifies a changed answer

`payload()` covers the package version, electrode, protocol, settings, the base CIC, window and
chronic constants, and (v2) the CIC conditions. It does not cover `results`, the in-vivo
derating table, the drift model or the Butterwick parameters. `__version__` has stayed at
`0.15.0` through Phases 1–4. Executed:

```
record made at c89fdf4: DiscElectrode(500,"Pt"), StimProtocol(50,200,130,1), medium="in_vivo"
  results: cic_limit 7.142857142857143, limiting_current_uA 70.12483601762932
at HEAD: cic_limit 11.49425287356322, limiting_current_uA 112.84456370652995
audit.reproduces(old_record, calc) -> (True, [])
```

The version handling C4.4 added works as designed. Four c89fdf4 records (ring, continuous
SIROF, TiN, Pt in vivo) load, `digest_matches` is True, and they reproduce. New v2 records
round-trip through strict JSON, and their digest moves with the counter, duty, recovery,
resting potential, capacitance, medium, policy, lead resistance and compliance.

But "reproduces" is now true for an assessment whose answer moved by 61 %. **Fix:** include a
digest of `results` in the payload (the cheapest complete fix). Alternatively, add a
model/constants version that every numeric commit bumps, plus the derating table and model
parameters.

## M2 — MAJOR — Leung's 8.7× is not his largest factor, and it is applied at every pulse width

Leung et al., IEEE TBME 62(3):849–857:
* p. 852: "suprachoroidal Qinj in vivo was between 8.7 times less (200μs pulsewidth) and 3.2
  times less (3200-μs pulsewidth) ... dividing the in vitro Qinj by the mean in vivo Qinj at
  the respective pulsewidths" — quoted correctly.
* Also p. 852: "The mean suprachoroidal Qinj in the acutely implanted animals was between 3.84
  to 16.6 μC/cm2 for pulsewidths of 100 to 3200 μs (n = 18)". Chronic: 6.99–15.8 for **200**
  to 3200 µs.
* In vitro: "35 to 54 μC/cm2 for respective pulse widths of 100 to 3200 μs" (abstract), and
  "34 to 54" (results).
* Fig. 4 (rendered, p. 853): acute in-vivo ≈3.8 at 100 µs, ≈5.7 at 200 µs; in-vitro ≈34 at
  100–200 µs.

So the matched factor at 100 µs is 34/3.84 = **8.85** or 35/3.84 = **9.11**. At 200 µs the
figure gives about 6. The "8.7 (200 μs)" in the text matches 100 µs, not 200, and 8.7 equals
the "11.5 %" of p. 854.

Leung also writes that "The reduction in the in vivo Qinj was greater at short pulsewidths".
The cortical (subdural) point is 12.7 % at 400 µs (7.9×), where the suprachoroidal value is
about 4.7×.

Consequences:
* The conservative end of 8.7× is up to about 5 % non-conservative at 100 µs.
* It is not bounded by any data below 100 µs, where the trend says the reduction is larger.
* It is applied unchanged at 3200 µs, where 3.2× is measured (conservative there).

C4.5's ×1.609 relaxation is sourced to the sentence, but not to the paper's own numbers at the
shortest pulse.

**Fix:** a pulse-width-dependent derating from Fig. 4's matched pairs, taking the 100 µs
factor (≥ 9.1×) at and below 100 µs. At minimum set the high end to 9.1, and mark in-vivo Pt
limits provisional below 100 µs. Record the text/figure discrepancy in the evidence string.

## M3 — MAJOR (pre-existing) — `max_current_cic_uA` ignores the medium

`SafetyCalculator.max_current_cic_uA` calls `charge.cic_max_current_uA` without `medium`, so
the batch/CSV column is the saline figure:

```
saline:  report max_current_cic_uA 981.7477042468105 | check ceiling 981.7477042468105
in_vivo: report max_current_cic_uA 981.7477042468105 | check ceiling 112.84456370652995 (cic_limit 11.494...)
```

The headline is correct. The number labelled "charge-injection-permitted current" beside it in
every in-vivo row is 8.7× high. **Fix:** pass `medium` (and, since C2.4, NOT_EVALUATED →
`None` for monophasic, ledger 114).

---

## Verification of the focus items

**(1) Changed constants against the PDFs.**
* **Riedy & Walter**, IEEE TBME 43(6):660–663:
  * All four stored quotes match the text layer: the abstract "reported to be 40 pC/cm2";
    p. 662 "provided that the charge injection is kept below 20 pC/cm2 ... [ 5 ]"; p. 662
    "reversible charge injection limit [8] ... 1.2 V for 316LVM [ 5 ]"; p. 663 "0.2 pC/mm2
    (20 pC/cm2) [8]. Based on this report".
  * The OCR "p" is the micro sign, as the module says.
* **McCreery 2010** (nihms209066): every quote verified: "biased to + 0.6 volts ... increase
  their charge capacity"; "2,000 ± 150 μm2"; "laser-ablated from their tips"; "responsible for
  most of the neuronal loss within 150 μm ... 50% duty cycle"; "approximately 60 μm"; "at least
  150 μm"; "348 to 1,282 days" against the abstract's "450 to 1282".
* **Elwassif 2006** Table I: κt 0.45/0.50/0.55/0.60, so the range (0.45, 0.6) is right.
* **Butterwick** p. 2264 (image): "t^−0.52 and t^−0.48 in the chronic regime, and t^−0.49 and
  t^−0.41 with the single shots". Fig. 4 labels −0.48 on retina sustained and −0.52 on CAM
  sustained, so retina = −0.48 is correct. "139 μA on retina and 55 μA on CAM", "only one
  pulse of duration 60 μs on CAM and 600 μs on the retina", and "t^−0.48 for the large pipette
  and t^−0.29 for the small one" are all correct; see M5 for the 0.115/0.12 mm discrepancy.
* **Leung**: see M2.

**(2) Leung's 100 µs.** Yes: the 100 µs reduction (8.85–9.1×) exceeds 8.7×, and nothing
bounds shorter pulses (M2).

**(3) The two relaxations.**
* **C4.2b (on-time drift): sound.** For a leak-free capacitor, off-periods neither add nor
  remove charge, so the pulses actually delivered are the right count. A real interface leaks
  during the off-time, so on-time is still an upper bound on the drift.
* Executed: ledger 109's case (band, 3000 µA, 20 % duty, 1 s) is now CAUTION, "0.2558 s of
  on-time ... after the train (0.2 s of on-time)". That is correct: 7.02 µC delivered against
  8.977 µC.
* The Phase 3c "capped ⇒ Water window FAIL" property still holds with duty < 1. The unbalanced
  sweep includes duty 0.1–0.5: 651 of 651 capped cases are FAIL.
* **C4.5**: sourced to the sentence, but not bounded at short pulses (M2).

**(4) Riedy & Walter reference numbering: recounted from the page image.**
* [1] Loeb, [2] Brindley, [3] Glenn & Phelps, [4] Kiwerski, **[5] Lan, Daroux & Mortimer**,
  "Pitting corrosion ... J. Electrochem. Soc. 136, 947–954, 1981".
* [6] Brummer & McHardy, [7] Robblee, Cogan & Kimball, **[8] Robblee & Rose**, "Electrochemical
  guidelines ...", Agnew & McCreery (eds), Prentice-Hall 1990, pp. 25–66.
* [9] Durand, [10] Riedy & Walter 1994, [11] Mortimer, [12] Gamble, [13] Donaldson,
  [14] Peterson.
* The package's [5] and [8] are correct.

**(5) Butterwick.**
* **−0.48 cap.** The default is `min(ratio^−0.48, ratio^−0.443)`, anchored at 6 ms. Below 6 ms
  the two-anchor line is the smaller, so thresholds are unchanged to the bit. Above 6 ms the
  published slope is lower (conservative). Executed ratios: 0.9893755444377782 at 8 ms,
  0.9812123731039051 at 10 ms, 0.9562823171994247 at 20 ms, all as booked.
* **S-13.** d^−2 from the large-electrode density sits below Fig. 5's small-electrode data:
  0.676 A/cm² at 100 µm against measured 1.47–1.72, and 0.169 against 0.44 at 200 µm. So
  keeping d^−2 is conservative.
* **154.** Withholding single-pulse relief below 200 µm is conservative. Fig. 3's
  pulse-count data are from the 1 mm pipette only.

**(6) C4.3 provisional.**
* When a provisional check binds, the marker appears on describe ("PROVISIONAL: the binding
  check (Shannon criterion) rests on ..."), the GUI headline and the PDF headline. The JSON
  carries it per check. This closes my Phase 3 H2.
* It does not over-flag: a binding non-provisional check (the SIROF and Pt cases executed)
  shows no marker, and the README transcript is unchanged.
* Not in CSV (M4).
* The 894/1536 count was not re-derived.

**(7) C4.4 digest versioning.** Old records verify and reproduce, and new ones cover the new
fields (executed above). The digest's coverage gap is M1.

**(8) §6 digits (executed).**
* C4.2b: ledger 109 CAUTION and 0.255757863465323 s.
* C4.7b: three Butterwick ratios exact.
* C4.9a: `separating_k_range` = (1.6989700043360187, 2.1072099696478683); Elwassif (0.45, 0.6).
* C4.5: 100/8.7 = 11.49425287356322.
* Docs match the code, except where M2 affects the claim.

**(9) Regression grids at HEAD.** All clean:

| Grid | Result |
|---|---|
| Unbalanced sweep (seeds 7, 8) | 3 000/3 000 agree; 651 capped, all FAIL |
| Residual sweep | 6 240/6 240 |
| lds_rate | 0 of 16 200 |
| Repros | ok |
| ww98 | 20 000, clean |
| Mixed geometries with counters | 1 200/1 200 |
| Containment | 0 of 3 000 outside |
| inf/nan leak scan | 400 configurations, 0 leaks |
| K1 far-side sweep | 0 of 96 000 raise |

## Process note
Per the brief, this review wrote only this file. The reviewer did not update
`_conversation_history.md` (CLAUDE.md rule 14).

# VERDICT: **GO** for Phase 5, with conditions

The provenance work is largely faithful to its sources. Every quotation checked is verbatim,
Riedy & Walter's reference numbering is right, the Butterwick and McCreery corrections are
conservative and correct, and no regression grid moved.

**Conditions:**
1. **M1 before release.** A provenance package whose audit says "reproduces" across a 61 %
   change in the answer undercuts its own claim.
2. **M2 before Phase 5 closes.** Adopt the 100 µs factor (≥ 9.1×) or a pulse-width-dependent
   derating, and flag in-vivo Pt below 100 µs as provisional.
3. **M3 with ledger 114 in Phase 5's io work (C5.5).** It is pre-existing, but it is an 8.7×
   overstated safety number in every in-vivo CSV row.
