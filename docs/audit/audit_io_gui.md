# Audit — the path from computed result to human reader

Repo `.`, package **neurostim 0.15.0**.
Interpreter `./.venv/bin/python`
(CPython 3.14.7, matplotlib 3.10.8, pandas 2.3.3, numpy 2.4.1, reportlab 5.0.0, PyQt6 6.11.0).

**READ-ONLY: no file inside the repo was created, modified or deleted.** All artefacts
written under `$SCRATCH/io2/`. GUI exercised with `QT_QPA_PLATFORM=offscreen`; no window
was opened.

Read in full: `neurostim/io/{report,tabular,fem,__init__}.py`,
`neurostim/viz/{plots,style,__init__}.py`, `neurostim/gui/{app,__main__,__init__}.py`,
`neurostim/audit.py`, `examples/worked_example.py`,
`scripts/{provenance_audit,verify_transcriptions}.py`, plus the supporting
`safety/assessment.py`, `safety/charge.py`, `materials.py`, `references.py` needed to
trace numbers to their source.

Every finding below was produced by **executing** code. Nothing is asserted from reading
alone. Reproductions are copy-pasteable and were run.

---

## 0. Headline

The numeric transcription itself is sound — all twelve numbers traced in §3 arrive in the
PDF with the right value and a unit attached. The defects are elsewhere, and three of them
are serious:

1. **The single most prominent number in the report and the GUI — "limiting current" —
   ignores three of the nine safety checks.** It prints 141.4 µA for a protocol that FAILS
   from 22 µA. Its own docstring calls it "the number to programme against".
2. **The exported four-panel figure computes panel (b) at library defaults, not at the
   settings being assessed.** It prints "binding limit 6.88e+03 µA" on its face when the
   assessment's binding limit is 4869.59 µA — 41 % permissive.
3. **Limits are rendered with round-to-nearest, so a printed maximum can exceed the real
   one.** Programming the exact number the report gives as the maximum produces a FAIL.

---

## 1. Findings

Severity is assigned by *what a reader would wrongly conclude*, not by code smell.


> Reproductions for every ID are in **§4**, keyed by the same identifier (C1, C2, C3, H1 …). Each was executed; the transcript output is quoted inline.

### CRITICAL

| # | Location | Failure |
|---|----------|---------|
| **C1** | `safety/assessment.py:118-131` (rendered at `io/report.py:228-230`, `gui/app.py:331-334`) | `limiting_current_uA` takes `min()` over **only** Shannon, charge-injection and compliance. The `Microelectrode charge/phase`, `Chronic degradation` and `Current density` checks contribute no candidate. For the package's own worked example (330/270 µm Pt ring, 200 µs, 130 Hz) the PDF headline reads **"limiting current 141.4 µA"** while the assessment returns FAIL from **22 µA** — the headline is **7.1× the highest amplitude at which no check fails**. The docstring is explicit that this is "the number to programme against". |
| **C2** | `viz/plots.py:511-513` | `safety_summary` calls `current_limit_sweep(calc.e, calc.p, ax=ax_b, compliance_V=…)` and forwards **neither `k`, nor `policy`, nor `tissue_conductivity_S_per_m`**. All three curves in panel (b) are recomputed at the library defaults (k=1.5, conservative, σ=0.35) while the figure's suptitle carries the user's verdict. With `k=1.2, σ=0.10` the panel annotates **"binding limit 6.88e+03 µA"**; the assessment's real binding limit is **4869.59 µA**. The drawn Shannon limit is 1.41× and the drawn compliance limit 3.44× the true ones — both in the permissive direction. This figure is what the README tells users to put in a manuscript. |
| **C3** | `io/report.py:229,302,311`; `safety/assessment.py:245,291`; `safety/charge.py:138` | Safety **limits** are formatted with `:.4g` / `:.2f`, i.e. round-to-nearest, which rounds a maximum **up**. True charge-injection maximum 141.37167 µA prints as **"141.4 µA"** in the headline, in Computed quantities, and in the check summary "max 141.4 uA". Setting the amplitude to 141.4 µA — the number the report names as the maximum — yields `FAIL`. Same class: Shannon max 472.78773 → "472.8". A limit must floor. |

### HIGH

| # | Location | Failure |
|---|----------|---------|
| **H1** | `safety/assessment.py:290-293`, `244-246`, `517-520` | Applied value and limit are printed at identical precision, producing self-refuting sentences. At 141.428 µA: **`100 uC/cm^2 exceeds the 100 uC/cm^2 limit for Pt; max 141.4 uA`**. At k_metric = 1.500043: **`k = 1.50 exceeds the 1.50 threshold; max 6878 uA`**. The PDF's *Computed quantities* table prints charge density "100" and charge-injection limit "100" on adjacent rows. A reader checking the arithmetic sees equality where there is an exceedance. |
| **H2** | `io/tabular.py:168-171` | `read_batch_csv` on a header-only or truncated CSV returns a DataFrame with **zero rows and zero columns** — no exception, no `status` column, no `error` column. "Nothing was assessed" is indistinguishable from "nothing failed", and any downstream `len(df[df.status=="FAIL"])` raises `KeyError` rather than reporting the real problem. |
| **H3** | `safety/assessment.py:122-131` | `limiting_current_uA` is `min()` over a Python list, and `nan < x` is `False`, so a **NaN candidate is silently discarded**. A blank `compliance_V` cell in a batch CSV becomes NaN; the Compliance check then reports `FAIL — "needs 9.32 V but only nan V available"` while `limiting_current_uA` reports 141.37 µA as though compliance were satisfied. Order-dependent too: `min([141.0, 212.0, nan]) == 141.0` but `min([nan, 141.0, 212.0]) is nan`. |
| **H4** | `io/report.py:70-103` | The bibliography generator matches a source either by bare key or by `surname … year` within 40 characters. Rendered report text contains **"Brummer & Turner's 300-350 uC/cm^2 real-area figure"** with no year; `brummer_turner1977` **exists** in `references.py`; the bibliography has **no entry for it**. This is precisely the dangling-citation defect the function's own docstring says it was written to eliminate, in a report whose entire claim is traceable provenance. |
| **H5** | `io/report.py:200-413` | The PDF records **no package version**, no digest, and omits 4 of the 11 `SafetyCalculator` settings: `medium`, `lead_resistance_ohm`, `measured_impedance_ohm`, `resting_potential_V`. Two reports built with `resting_potential_V=0.0/0.35` and `lead_resistance_ohm=0/2000` render **byte-identical Electrode, Protocol and Computed-settings sections** but different peak potential (−0.226 V vs +0.124 V) and different required compliance (0.829 V vs 0.989 V). The report cannot be reproduced from its own face. `neurostim/audit.py` already builds exactly the record needed (version, all settings, constants, SHA-256 digest) and `build_report` never calls it. |
| **H6** | `viz/plots.py:38-42, 85-98, 100-115` | The Shannon safe-operating-area plot draws separatrices at the **module constants** `K_SHANNON/K_MODERATE/K_DAMAGE_OBSERVED` (1.5/1.7/2.0) and never at `calc.k`. The operating point's colour comes from `calc.k`. Both contradictions were produced: with `calc.k=2.0` and k_metric=1.750 the point is drawn **above** the solid k=1.5 line and coloured **green**; with `calc.k=1.2` and k_metric=1.350 it is drawn **below** that line and coloured **red**. The line that actually decided the verdict is not on the chart. |
| **H7** | `viz/plots.py:103-115`, `454-460`; `gui/app.py:330` | Pass/fail is carried by **colour alone**. Verified by scraping the artists: the `protocol` point is `marker='o', markersize=5` whether it passes or fails — only `markerfacecolor` changes (`#1a7f37` ↔ `#b62324`). `material_comparison` bars: `hatch=None` on every bar, facecolour is the only difference. On the McCreery series, "no damage" and "some damage" are both `'o'` at the same size, distinguished only by fill. A deuteranopic reader cannot read the hero panel. Greyscale printing loses it too (#1a7f37 and #b62324 have near-identical luminance). |
| **H8** | `gui/app.py:349-352` | The plot is rebuilt **outside** the `try/except` at 317-328. Any exception from `shannon_safe_operating_area` escapes the slot; PyQt6 aborts the process. Measured: **exit code 134 (SIGABRT)** — `except BaseException` in the caller's own frame never runs. The module docstring promises "The window never hides a failure … surfaces the exception text in the results pane rather than silently reverting". It does that for input errors and not for plot errors. Additionally the update is non-atomic: headline/table/detail are written at 331-347, the canvas at 349-352, so between them the pane describes the new protocol while the canvas still holds the old one. |
| **H9** | `viz/style.py:162-164` | `save_publication` strips whatever follows the last dot: `base.with_suffix("")`. `save_publication(fig, "shannon_k1.5")` and `save_publication(fig, "shannon_k1.8")` **both write `shannon_k1.svg`**; the second silently destroys the first. Verified — one file on disk, carrying the k=1.8 title. Any figure named after a decimal parameter value collides. |
| **H10** | `io/tabular.py:182-217` | `report_to_json` — the machine-readable twin of the PDF — records `"material": "Pt"` and `cic_limit_uC_cm2: 62.0` for a **user-measured, unverified** limit. Every provenance flag the PDF does reproduce (`PROVISIONAL`, `NOT PEER REVIEWED`, `your measurement, not published literature`, the user's note, the `verified` bit, the reference key) is **absent from the JSON**. A downstream consumer cannot tell a literature limit from an unpublished bench measurement. No package version either. |
| **H11** | `io/report.py:313-317` (peak potential), `:333-334` (water-window provenance), `:347-354` (interface model); derivation at `safety/water_window.py:58-68` | **Provenance flags stop at one row.** With a user-measured, unverified CIC (`with_measured_cic(get_material("Pt"), 62.0, …)`) the PDF flags the *Charge-injection limit* row `PROVISIONAL` — and then renders every quantity derived from that unverified number with no marker at all: `Interface model … C_eff = 103 µF/cm²` (103, not the literature 250, precisely because it is derived from the user's 62 µC/cm²), `Peak electrode potential -0.548 V vs Ag|AgCl`, and `Water window CAUTION — peak -0.55 V, 0.05 V headroom`. Worse, the *Water window* provenance row attributes itself to **`(cogan2008)`** — a peer-reviewed citation — beside a headroom figure that came off the user's own bench. A reader sees a published source next to an unpublished number. Repro: §4 / `$SCRATCH/io2/C.txt` lines 38, 60, 66, 72. |

### MEDIUM

| # | Location | Failure |
|---|----------|---------|
| **M1** | `io/report.py:294-303` | *Computed quantities* prints `Shannon k -0.043 (threshold 1.50)` and `Shannon current limit 472.8 µA` with no caveat when the Shannon check is `NOT_EVALUATED`. The same PDF says, twelve lines earlier, *"not applicable: 0.000283 cm^2 is below the macro/micro boundary"*. Worse, that same un-applicable `shannon.max_current_uA` is still a live candidate in `limiting_current_uA` (see C1). |
| **M2** | `io/report.py:330-332` + `materials.py:158-189` | The Provenance row prints the **full** published range in **mC/cm²** (`0.05-0.15 mC/cm2`) directly beside a Computed-quantities limit of `100 µC/cm²`. Different unit, and the cathodic-first sub-range (100–150) that actually produced 100 appears only in prose further down. On the page the conservative policy appears to have selected 100 from a range whose low end is 50. |
| **M3** | `io/report.py:357-374` + `safety/charge.py:131-134` | The *Warnings and caveats* block for a **CAUTION** check renders detail beginning `Charge injection (Pt, conservative, cathodic-first) -> PASS`. `ChargeResult.describe()` derives its verdict from `self.passes`, which does not know about the CAUTION downgrade. A warning that announces PASS. |
| **M4** | `io/tabular.py:159-163` | Errored batch rows carry `status="ERROR"` (good) but **every numeric column is NaN**. Verified on a 4-row CSV with 3 bad rows: `df.limiting_current_uA.min()` returns 141.37 (pandas skips NaN by default) — the binding limit of the one row that ran, presented as the batch minimum. `df[df.status != "FAIL"]` returns the three errored rows as not-failing. |
| **M5** | `io/fem.py:238-272` | `compare_with_point_source` is documented as a "sanity check on units" but **evaluates nothing** — no ratio test, no flag, no summary, no return-value verdict. A potential column off by 10⁶ returns a clean 400-row frame with `ratio ≡ 1e6` and no error. Positions off by 10⁶ likewise (`ratio ≡ 1e6`). *Credit where due:* the opposite scale error (metres read as µm, 10⁻⁶) **is** caught, by the `min_distance_um` guard at 254-259. |
| **M6** | `io/fem.py:33-46, 201-215` | `_match_column` returns the **first** alias that matches, with no ambiguity check. A file carrying both `x,y,z` (metres) and `x_um,y_um,z_um` silently takes the metre columns and ignores the micrometre ones — verified: bounds came back as `0 … 0.0003 µm`. No warning, and `describe()` is the only place the mistake is visible. |
| **M7** | `io/fem.py:59-75` | No duplicate-position check. 20 rows at 10 unique positions with **contradictory** potentials loads as `n_points=20`; `griddata` then returns an arbitrary blend (measured 0.01070 V where the two inputs were 0.01070 and 0.05348). |
| **M8** | `io/fem.py:143-157` | `describe()` is the documented way to catch an import-scale mistake (`load_field` docstring: "the resulting bounds are worth checking … `FEMField.describe` prints them"). A **single NaN** in the potential column collapses it to `potential nan to nan V` — the diagnostic the docs point you at is destroyed by the condition it exists to reveal. `bounds_um` has the same exposure for NaN positions. |
| **M9** | `io/fem.py:181-197, 217-222, 225-235` | `save_field` writes `current_uA` into the `.npz`; `load_field`'s npz branch **never reads it back** — `current_uA` comes only from the function argument. Verified round-trip: saved 250.0 µA, reloaded `None`; `note` is lost too. The loss is silent at load and only surfaces later as `scale_to_current` refusing to run. A user re-supplying `current_uA=` by hand can supply a *different* value than was saved and nothing cross-checks. |
| **M10** | `examples/worked_example.py:66-70, 91-97` | Hard-coded narration contradicting the script's own stdout, in the same run: (a) *"the tissue-damage criterion is satisfied with 7x headroom"* printed eleven lines after `[NOT_EVALUATED] Shannon criterion: not applicable` — and the ratio is 3.34× (472.8/141.4) or 5.9× (472.8/80), never 7×; (b) *"the interface is driven roughly 2.8 V from rest … which leaves every published water window regardless of material"* printed while the same script reports `[PASS] Water window: peak -0.23 V, 0.37 V headroom`. |
| **M11** | `viz/style.py:77-82` vs `viz/plots.py:130,134,137,216,262,270,342,354,365,398,417,463,478` | README: "7 pt sans-serif". Measured across the exported summary SVG (76 `<text>` elements, 297 size declarations counting `<tspan>` children) the actual sizes are **4.2, 4.55, 4.9, 5.4, 5.8, 6, 6.5, 7, 7.5, 8.5 px**: 116 declarations sit at 7 px and **43 sit below 5 px**. Legend text is hard-coded to `fontsize=5.4` (plots.py:130) and the "provisional" marker to 5.5 (plots.py:478); mathtext superscripts on the log tick labels render at **4.2–4.55 pt**, below every journal's 5 pt floor. Separately, `mathtext.fontset` is unset, so every `$…$` label falls back to **DejaVu Sans** while plain text uses Arial — two typefaces in one figure (23 DejaVu vs 236 Arial font-family declarations in the SVG). |
| **M12** | `viz/style.py:167-171` | 600 dpi TIFF export **does** happen — verified with Pillow: `summary.tiff (4290, 2739) dpi=(600.0, 600.0)`. But it is written **uncompressed RGBA**: 47 MB for the four-panel summary, 32 MB for `panel_1.tiff`. Journals routinely cap uploads below that and reject alpha channels in TIFF. The claim is true; the artefact is unusable. |
| **M13** | `io/tabular.py:212` | `json.dumps(..., default=str)` emits bare `NaN` for any NaN field. Verified: `"compliance_V": NaN` and `"margin": NaN` — **invalid RFC 8259**. Python's non-strict `json.loads` accepts it; `node -e "JSON.parse(...)"` rejects with `SyntaxError: Unexpected token 'N'`. Any non-Python consumer fails on the export. |
| **M14** | `io/tabular.py:170` | `pd.read_csv(path)` with no encoding handling and no error wrapping. A Latin-1 CSV raises `UnicodeDecodeError: 'utf-8' codec can't decode byte 0xe9 in position 145` — a byte offset, **no file name**. An empty file raises `EmptyDataError("No columns to parse from file")` — again no path. In a batch of many files neither error identifies the file. (UTF-8 BOM is fine — pandas' C parser strips it; verified.) |

### LOW

| # | Location | Failure |
|---|----------|---------|
| **L1** | `viz/plots.py:87` | `zip(k_values, greys, strict=False)` against a 3-element `greys` tuple. A caller passing 4+ `k_values` gets the extras **silently dropped** — separatrices requested and never drawn, no error. |
| **L2** | `viz/plots.py:127-128, 219-220, 486` | Log axes are not labelled as log. Decade tick labels (10⁻⁵ …) are present, which is standard practice, so this is a style note rather than a defect. Axis labels *do* all carry units — verified. |
| **L3** | `gui/app.py:192` | `k_value` spinbox has `decimals=2`, so a typed `1.749` silently becomes `1.75` — rounding **up**, the less-conservative direction. Similarly `pulse_width` clamps a typed `0.02` to its 0.1 minimum. The widget does display the clamped value, so it is visible, not hidden. |
| **L4** | `viz/plots.py:512` | `compliance_V=compliance_V or calc.compliance_V` — falsy-zero: an explicit `compliance_V=0.0` falls through to `calc.compliance_V`. Harmless today because both paths are 0, but it is the wrong operator. |
| **L5** | `io/fem.py:238-244` | `compare_with_point_source(field, current_uA)` takes the current as an argument and never checks it against `field.current_uA`. Verified: a field recorded at 100 µA compared against 999999 µA returns `ratio ≈ 1e-4` with no complaint. |

---

## 2. What is correct

Stated explicitly so the negative findings are not read as a blanket verdict.

- **Numeric transcription.** All twelve numbers in §3 reach the PDF with the correct value and a unit attached. No transposition, no unit substitution, no stale cache.
- **Provenance flags DO reach the PDF.** `PROVISIONAL`, `NOT PEER REVIEWED`, `(your measurement, not published literature)`, the user's note, and a standalone `PROVISIONAL: limit not confirmed against a primary source` line all render. Verified with `with_measured_cic(get_material("Pt"), 62.0, …)`. (They are dropped from the *JSON* export — H10.)
- **The bibliography is generated, not hard-coded** (`report.py:382-384` → `references.py::cite().citation()`), and the runtime scan does pick up prose citations that a fixed list would miss — `kuncel_grill2004_full` and `butterwick2007` both appeared from body text. The one gap is the year-less citation in H4.
- **Batch rows fail per-row, as the README claims.** Verified against inner≥outer, missing amplitude, unknown material and an unrecognised extra column: the batch completes, each bad row gets `status="ERROR"` and a typed message in `error`. An errored row can**not** be mistaken for a PASS *by a human reading the status column* — the residual risk is numeric (M4).
- **NaN guards exist where it counts.** An empty `k` cell is rejected with `"Shannon k must be finite, got nan"`; an empty `current_uA` with `"current_uA must be finite and > 0, got nan"`. UTF-8 BOM is handled.
- **`current_sweep` endpoints match the docs.** It takes an arbitrary iterable and assesses exactly the values given — there is no start/stop/step semantics to get wrong, and the README's `current_sweep(electrode, protocol, range(10, 200, 10))` is consistent with that.
- **FEM scale-down error is caught.** Metres read as micrometres trips `min_distance_um` with a pointed message ("is the field centred on the electrode?"). Interpolation outside the convex hull returns NaN rather than extrapolating, as documented.
- **Figure contract, the parts that hold.** Top and right spines are off (verified on the artists). Text is **editable, not outlined**, in both vector formats: 76 `<text>` nodes in the SVG with `svg.fonttype: "none"`, and the PDF carries subsetted TrueType (`GOFYPY+ArialMT`, CID TrueType, embedded) from which `pdftotext` recovers every string. 600 dpi TIFF genuinely happens.
- **Red/green is reserved for pass/fail** — `CATEGORICAL` in `style.py:61-68` contains no red or green, and nothing else in `plots.py` spends them.
- **GUI invalid-input path is correct.** Setting a ring's inner diameter above its outer clears the headline to "Invalid input" in fail-red, sets `_calc = None`, empties the table (0 rows), clears the figure, and puts the exception text in the detail pane. Both export buttons then refuse with "Fix the invalid input first." **No stale result is left on screen.**
- **Exports match the displayed parameters.** `export_pdf` and `export_figure` both build from `self._calc`, the same object that produced the headline; there is no path that exports a different configuration than the one shown. (What the *figure* then draws is C2's problem, not a GUI race.)
- **The embedded plot is genuinely redrawn, never cached** — `figure.clear()` + `add_subplot` on every recompute.
- **Both scripts run clean and are honest.** `provenance_audit.py` exits 0 / 1 under `--strict` as documented and reports 2 known gaps; its "9 peer-reviewed" claim is accurate (checked all nine material CIC references). `verify_transcriptions.py` checks 86/86 values and prints its own limitation: *"it cannot detect a value attached to the wrong material, polarity or condition."*
- **`audit.py` is well built** — digest over inputs *and* constants, timestamp/operator/note deliberately excluded, `differences_from` for diagnosing a mismatch. Its only defect is that nothing in `io/` or `gui/` uses it (H5).

---

## 3. Number traces — `SafetyCalculator` → rendered PDF string

Twelve numbers traced (six were asked for). Case: `RingElectrode(330, 270, "Pt")`,
`StimProtocol(80 µA, 200 µs, 130 Hz, 1 s)`, `compliance_V=10.0`. PDF built with
`build_report`, text recovered with `pdftotext -layout` and NFKC-normalised (the report's
own comment at `io/report.py:246-251` warns that `&ohm;` renders as U+2126 OHM SIGN, not
U+03A9 — that comment is **accurate**; the raw glyph does not compare equal to a Greek
omega, and normalising was required to match it).

| # | Source expression | Computed value | PDF string | Unit on page | Rel. error | Direction |
|---|-------------------|----------------|------------|--------------|-----------|-----------|
| 1 | `e.area_cm2` | 0.0002827433388230814 | `0.0002827` | `cm²` ✓ | 1.5e-04 | down |
| 2 | `p.charge_per_phase_uC` | 0.016 | `0.016` | `µC` ✓ | 0 | exact |
| 3 | `assessment.charge.charge_density_uC_cm2` | 56.58842421045167 | `56.59` | `µC/cm² per phase` ✓ | 2.8e-05 | up |
| 4 | `assessment.shannon.k_metric` | −0.043152416821609085 | `-0.043` | dimensionless, threshold stated ✓ | 3.5e-03 | — |
| 5 | `assessment.shannon.max_current_uA` | 472.78772824642175 | `472.8` | `µA` ✓ | 2.6e-05 | **UP — a limit** |
| 6 | `assessment.charge.max_current_uA` | 141.37166941154072 | `141.4` | `µA` ✓ | 2.0e-04 | **UP — a limit** |
| 7 | `assessment.water_window.peak_potential_V` | −0.22635369684180667 | `-0.226` | `V vs Ag\|AgCl` ✓ | 1.6e-03 | down |
| 8 | `assessment.compliance.access_resistance_ohm` | 7529.232524210429 | `7529` | `Ω` ✓ (+ method + σ) | 3.1e-05 | down |
| 9 | `assessment.compliance.required_V` | 0.8286922987786409 | `0.829` | `V` ✓ (+ split into ohmic/polarisation) | 3.7e-04 | up |
| 10 | `assessment.limiting_current_uA` | 141.37166941154072 | `141.4` | `µA` ✓ | 2.0e-04 | **UP — a limit** |
| 11 | `p.duty_cycle * 100` | 5.2 | `5.20` | `%` ✓ | 0 | exact |
| 12 | `p.rms_current_uA` | 18.24280680158621 | `18.24` | `µA` ✓ | 1.5e-04 | down |

**Verdict on transcription:** every value arrives intact and every one carries a unit.
Rows 5, 6 and 10 are the finding: all three are *maxima*, and all three round **upward**,
which is the only direction that matters (C3). Rows 8 and 9 are exemplary — the access
resistance states its method (`equal-area disc approximation`) and the σ it used, and the
required compliance is decomposed into its ohmic and polarisation parts.

Additional field-level check on the *potential scale*: `_potential_scale` (`report.py:58-67`)
correctly prints `vs Ag|AgCl` for Pt and would print `vs the resting potential` for a
material whose `WaterWindow.scale` says so, rather than hard-coding a reference electrode.

Raw output: `$SCRATCH/io2/traces.txt`; rendered PDFs and their text twins
`$SCRATCH/io2/{base,trace,A,B,C}.{pdf,txt}`.

---

## 4. Reproductions

All run against `./.venv/bin/python` from the
repo root. None writes inside the repo.

**C1 — headline limiting current is 7.1× the highest safe amplitude**
```python
from neurostim import SafetyCalculator
from neurostim.geometry import RingElectrode
from neurostim.protocol import StimProtocol
e = RingElectrode(330, 270, material="Pt")
mk = lambda I: SafetyCalculator(e, StimProtocol(I, 200., 130., 1.0), compliance_V=10.0)
print(mk(80.).assess().limiting_current_uA)            # 141.37166941154072  <- PDF headline
for I in (20, 22, 25, 141.37):
    r = mk(I).assess()
    print(I, r.status.value, [c.name for c in r.checks if c.status.value == "FAIL"])
# 20     CAUTION []
# 22     FAIL    ['Microelectrode charge/phase']
# 25     FAIL    ['Microelectrode charge/phase']
# 141.37 FAIL    ['Current density', 'Microelectrode charge/phase', 'Chronic degradation']
```

**C2 — exported figure panel (b) computed at defaults, not at the user's settings**
```python
import matplotlib; matplotlib.use("Agg"); import numpy as np
from neurostim import SafetyCalculator
from neurostim.geometry import CylindricalBandElectrode
from neurostim.protocol import StimProtocol
from neurostim.viz.plots import safety_summary
e = CylindricalBandElectrode(1270, 1500, material="Pt")
calc = SafetyCalculator(e, StimProtocol(3000., 200., 130., 1.0),
                        k=1.2, tissue_conductivity_S_per_m=0.10, compliance_V=10.0)
a = calc.assess(); fig, axes = safety_summary(calc); axb = axes[0][1]
L = {l.get_label(): np.nanmax(l.get_ydata()) for l in axb.get_lines()}
print("TRUE   shannon %.6g  compliance %.6g  binding %.6g"
      % (a.shannon.max_current_uA, a.compliance.max_current_uA, a.limiting_current_uA))
print("DRAWN  shannon %.6g  compliance %.6g" % (L['Shannon limit'], L['compliance limit']))
print("annotation:", [t.get_text() for t in axb.texts if 'binding' in t.get_text()])
# TRUE   shannon 4869.59  compliance 5480.42  binding 4869.59
# DRAWN  shannon 6878.48  compliance 18836.5
# annotation: ['binding limit 6.88e+03 µA']
```

**C3 — the printed maximum is not attainable**
```python
a = mk(80.).assess(); true_lim = a.charge.max_current_uA      # 141.37166941154072
printed = float(f"{true_lim:.4g}")                            # 141.4  (as it appears in the PDF)
r = mk(printed).assess()
print([(c.status.value, c.summary) for c in r.checks if 'njection' in c.name])
# [('FAIL', '100 uC/cm^2 exceeds the 100 uC/cm^2 limit for Pt; max 141.4 uA')]
```

**H1 — self-refuting summaries**
```python
mk(141.428218).assess()   # -> "100 uC/cm^2 exceeds the 100 uC/cm^2 limit for Pt; max 141.4 uA"
# and on a macroelectrode at k_metric = 1.500043:
#    "k = 1.50 exceeds the 1.50 threshold; max 6878 uA"
```

**H2 — header-only CSV vanishes**
```bash
printf 'shape,outer_diameter_um,inner_diameter_um,material,current_uA,pulse_width_us,frequency_hz,train_duration_s\n' > "$SCRATCH/hdr.csv"
.venv/bin/python -c "
from neurostim.io import read_batch_csv
df = read_batch_csv('$SCRATCH/hdr.csv')
print(len(df), list(df.columns))          # 0 []   -- no status column, no error column, no exception
"
```

**H3 — NaN candidate silently dropped from `min()`**
```python
c = SafetyCalculator(e, StimProtocol(900., 200., 130., 1.0), compliance_V=float("nan"))
a = c.assess()
print([ch.summary for ch in a.checks if 'Compliance' in ch.name])
#   ['needs 9.32 V but only nan V available']            <- FAIL
print(a.compliance.max_current_uA, a.limiting_current_uA)
#   nan 141.37166941154072                               <- the nan never reaches the minimum
print(min([141.0, 212.0, float('nan')]), min([float('nan'), 141.0, 212.0]))   # 141.0  nan
```

**H4 — dangling citation**
```bash
.venv/bin/python -c "
from neurostim import SafetyCalculator; from neurostim.geometry import RingElectrode
from neurostim.protocol import StimProtocol; from neurostim.io.report import build_report
build_report(SafetyCalculator(RingElectrode(330,270,material='Pt'), StimProtocol(80.,200.,130.,1.0)), '$SCRATCH/io2/x.pdf')"
pdftotext -layout "$SCRATCH/io2/x.pdf" - | grep -c Brummer      # 1   (named in the body)
pdftotext -layout "$SCRATCH/io2/x.pdf" - | grep -c brummer      # 0   (absent from the bibliography)
.venv/bin/python -c "from neurostim.references import REFERENCES; print('brummer_turner1977' in REFERENCES)"   # True
```

**H5 — two different inputs, identical rendered input sections**
```python
A = SafetyCalculator(e, p, compliance_V=10.0)
B = SafetyCalculator(e, p, compliance_V=10.0, resting_potential_V=0.35, lead_resistance_ohm=2000.0)
# build both, pdftotext both, diff:
#   only the *results* differ (peak -0.226 V vs +0.124 V; required 0.829 V vs 0.989 V)
#   the Electrode / Stimulation protocol / settings sections are identical
#   no package version appears anywhere in either PDF
```

**H6 — separatrix drawn at a different k than the one that decided the verdict**
```python
import scipy.optimize as so
from neurostim.safety import shannon as sh
e = CylindricalBandElectrode(1270, 1500, material="Pt")
km = lambda I: SafetyCalculator(e, StimProtocol(I,200.,130.,1.0), k=1.5).assess().shannon.k_metric
I = so.brentq(lambda x: km(x) - 1.75, 1, 1e8)                 # 9172.6 uA
s = SafetyCalculator(e, StimProtocol(I,200.,130.,1.0), k=2.0).assess().shannon
print(s.charge_density_uC_cm2, 10**sh.K_SHANNON / s.charge_per_phase_uC, s.passes)
# 30.65   17.24   True      -> point drawn ABOVE the solid k=1.5 line, coloured GREEN
# mirror case: k=1.2, k_metric=1.35 -> BELOW the line, coloured RED
```

**H7 — colour-only pass/fail** (artist scrape)
```python
ax = shannon_safe_operating_area(calc)
[(l.get_label(), l.get_marker(), l.get_markersize(), l.get_markerfacecolor()) for l in ax.get_lines()]
# ('protocol', 'o', 5.0, '#1a7f37')  — marker and size identical on FAIL, only facecolor flips to '#b62324'
[p.get_hatch() for p in material_comparison(e, p).patches]     # [None, None, ... ] on every bar
```

**H8 — GUI aborts on a plot failure**
```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python - <<'PY'
from PyQt6.QtWidgets import QApplication; app = QApplication([])
import neurostim.gui.app as G
from neurostim.gui.app import SafetyWindow
w = SafetyWindow(); print("BEFORE:", w.headline.text(), flush=True)
G.shannon_safe_operating_area = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("plot backend failure"))
try: w.current.setValue(500.0)
except BaseException as ex: print("caught:", ex, flush=True)      # never reached
print("STILL ALIVE", flush=True)                                  # never printed
PY
echo $?     # 134  == SIGABRT
```

**H9 — figure filenames truncated at a dot, silently overwriting**
```python
save_publication(fig_a, f"{SC}/shannon_k1.5", formats=("svg",))   # -> shannon_k1.svg
save_publication(fig_b, f"{SC}/shannon_k1.8", formats=("svg",))   # -> shannon_k1.svg  (clobbers)
os.listdir(SC)    # ['shannon_k1.svg']  — one file, carrying the k=1.8 figure
```

**H10 / M13 — JSON export drops provenance and is not valid JSON**
```python
from neurostim import get_material, with_measured_cic
from neurostim.io import report_to_json
mymat = with_measured_cic(get_material("Pt"), 62.0, pulse_width_us=100, note="EIS batch 2026-03")
txt = report_to_json(SafetyCalculator(e, p, material=mymat))
any(s in txt for s in ("PROVISIONAL","user_measurement","your measurement","EIS batch"))   # False
json.loads(txt)["material"]                                                                # 'Pt'
# and with a NaN anywhere:
'"compliance_V": NaN' in report_to_json(SafetyCalculator(e, p, compliance_V=float('nan')))  # True
#   node -e "JSON.parse(...)"  ->  SyntaxError: Unexpected token 'N'
```

**M5 / M6 / M8 / M9 — FEM**
```python
from neurostim.io.fem import load_field, compare_with_point_source, save_field, FEMField
# potential column off by 1e6:
compare_with_point_source(load_field("f_wrongI.csv", current_uA=100), 100.0).ratio.median()   # 1e+06, no error
# positions off by 1e6 (um data with position_scale_to_um=1e6):
compare_with_point_source(load_field("f_um.csv", current_uA=100, position_scale_to_um=1e6), 100.0).ratio.median()
#   1e+06 across all 400 rows, clean frame, no warning
# both x (metres) and x_um present -> the metre columns silently win:
load_field("amb.csv").bounds_um            # (array([0.,0.,0.]), array([3e-4, 2e-4, 2e-4]))
# one NaN destroys the documented diagnostic:
load_field("f_nan.csv").describe()         # "  potential nan to nan V"
# npz round-trip loses the current:
f = FEMField(pts, V, current_uA=250.0, note="solved at 250 uA")
load_field(save_field(f, "rt.npz")).current_uA      # None      (npz *contains* current_uA)
```

**M10 — worked example contradicts its own stdout**
```bash
.venv/bin/python examples/worked_example.py "$SCRATCH/io2/example_out" > "$SCRATCH/io2/example.log" 2>&1
grep -n "Shannon criterion\|7x headroom\|2.8 V\|Water window:" "$SCRATCH/io2/example.log"
# 19:[NOT_EVALUATED] Shannon criterion: not applicable: ... below the macro/micro boundary
# 31:[         PASS] Water window: peak -0.23 V, 0.37 V headroom
# 93:Note the gap: the tissue-damage criterion is satisfied with 7x headroom while
# 124:interface is driven roughly 2.8 V from rest ... leaves every published water window
```

---

## 5. The rounding question, answered directly

> *Can a FAIL ever be rounded into looking like a PASS — 50.04 shown as "50.0" against a 50 limit?*

**The status badge cannot be laundered. The numbers next to it can, and a limit can be
rounded upward into a value that is not attainable.** Three separate answers, all measured:

**5.1 The badge is safe.** `Status` is computed from the raw floats and rendered as a
string (`check.status.value`), never from a rounded quantity. At 141.428218 µA — 0.04 %
over the limit — the check is `FAIL`, the overall assessment is `FAIL`, and the PDF prints
`FAIL` in `#b62324`. No amount of display rounding changes that. Verified across
0.00 %, 0.04 %, 0.4 % and 4 % exceedance.

**5.2 The *numbers* are laundered, in exactly the shape asked about.** The scenario is
real and reproduces with the package's own default Pt ring:

```
I = 141.428218 µA   ->   true charge density 100.04 µC/cm²,  true limit 100.0 µC/cm²

  PDF "Computed quantities":   Charge density                    100 µC/cm² per phase
                               Charge-injection limit            100 µC/cm² (conservative policy)
  PDF "Safety checks":         Charge injection limit   FAIL   100 uC/cm^2 exceeds the 100 uC/cm^2 limit for Pt
```

Both sides of the word *exceeds* print as `100`. A reader checking the arithmetic — which
is the entire purpose of a methods-ready report — sees equality and a FAIL badge, and has
no way to tell whether the badge or the numbers are wrong. Same defect on the Shannon
check at `.2f`: `k = 1.50 exceeds the 1.50 threshold` for a true k of 1.500043.

**5.3 The genuinely dangerous direction: a limit rounded *up*.** `:.4g` is
round-to-nearest, so roughly half the time a maximum prints **larger than it is**:

```
true charge-injection maximum   141.37166941154072 µA
printed, everywhere in the PDF  "141.4 µA"          (headline, Computed quantities, check summary "max 141.4 uA")

SafetyCalculator(..., StimProtocol(141.4, 200., 130., 1.0)).assess()
  -> Charge injection limit  FAIL
```

Setting the amplitude to the number the report names as the maximum produces a FAIL. Same
class for the Shannon limit (472.78773 → `472.8`). The error is small in relative terms
(2e-4) and unbounded in consequence terms: it is the difference between "inside the limit"
and "outside it". **A displayed limit must floor; a displayed applied value must ceil.**
Neither does.

**5.4 The larger version of the same problem.** C1 dwarfs all of the above: the headline
`limiting current 141.4 µA` is not 0.02 % wrong, it is **7.1× wrong**, because three
failing checks contribute no candidate to `limiting_current_uA` at all. Fixing the
rounding without fixing C1 would leave the more dangerous number in place.

---

## 6. Flag propagation — PROVISIONAL / NOT PEER REVIEWED / user measurement

**Partly reproduced in the PDF, wholly dropped from the JSON, and — the real defect —
not propagated to anything derived from the flagged value.**

### 6.1 What the PDF does carry (verified, `$SCRATCH/io2/C.txt`)

With `with_measured_cic(get_material("Pt"), 62.0, pulse_width_us=100, note="EIS + voltage
transient, batch 2026-03")`, the rendered PDF contains, verbatim:

```
Charge-injection limit   0.062 mC/cm2 [100 us, geometric area] (your measurement, not published
                         literature) -- EIS + voltage transient, batch 2026-03 PROVISIONAL
Limit, as the source states it   EIS + voltage transient, batch 2026-03
...
PROVISIONAL: limit not confirmed against a primary source
```

`MeasuredRange.describe()` (`materials.py:158-189`) appends `NOT PEER REVIEWED` for any
non-peer-reviewed source, `(your measurement, not published literature)` plus the user's
note for `user_measurement`, and `PROVISIONAL` whenever `verified is False`. All of that
reaches the page. That much is correct and worth keeping.

### 6.2 What the PDF drops — **H11, the serious one**

The flag is attached to **one row** and to nothing downstream of it. In the same PDF:

| PDF row | Rendered | Flagged? |
|---------|----------|----------|
| Charge-injection limit (provenance) | `0.062 mC/cm2 … PROVISIONAL` | **yes** |
| Interface model | `capacitance derived from the material's own CIC and window, C_eff = 103 µF/cm²` | **no** |
| Peak electrode potential | `-0.548 V vs Ag\|AgCl` | **no** |
| Water window (check) | `CAUTION — peak -0.55 V, 0.05 V headroom` | **no** |
| Water window (provenance) | `-0.6 to +0.8 V vs Ag\|AgCl (cogan2008)` | **no — and it cites a peer-reviewed paper** |

The interfacial capacitance is **103 µF/cm² here and 250 µF/cm² for literature Pt**,
precisely because it is derived from the user's unverified 62 µC/cm². Every number in the
water-window chain therefore rests on an unpublished bench measurement, and the report's
own *Limitations* paragraph says so structurally ("the water-window check derives the
interfacial capacitance from the material's own charge-injection limit and window") —
while the water-window rows themselves carry a peer-reviewed citation and no caveat. This
independently confirms the finding reported by the other audit: the silence originates in
the water-window result and **the PDF inherits it unchanged**.

Secondary: the *Warnings and caveats* detail for that CAUTION check opens
`Water window (Pt, cathodic phase) -> PASS` (M3), and the material key still prints as
plain `Pt` throughout, so nothing in the electrode section hints the limits are not
Rose & Robblee's.

### 6.3 What the JSON drops entirely — H10

`report_to_json` records `"material": "Pt"` and `cic_limit_uC_cm2: 62.0`. Searching the
whole JSON for `PROVISIONAL`, `user_measurement`, `your measurement`, `EIS batch` or
`verified` returns **nothing**. The machine-readable twin of the report is unable to
distinguish a literature limit from an unpublished measurement, and carries no package
version. Anything built on the JSON path inherits the full silence.

### 6.4 Bibliography suppression

`io/report.py:92` — `if key == "user_measurement": continue` — excludes the key from the
bibliography by design, and `Reference.citation()` (`references.py:57-59`) suppresses the
`[… - not peer reviewed]` suffix for `source_type == "user"`. Both are defensible
individually (a user measurement is not a citation), but together with §6.2 the net effect
is that a reader scanning the References page finds only peer-reviewed sources for a
report whose binding limit came from nobody's publication.

---

## 7. GUI verdict — staleness, and can an exported PDF disagree with the screen?

**Staleness: no, for the ordinary paths. The GUI is better than its reputation here.**
Measured with `QT_QPA_PLATFORM=offscreen`:

- **Invalid input does not leave a stale result on screen.** Driving a ring's inner
  diameter above its outer: headline → `"Invalid input"` in `#b62324`; `_calc` → `None`;
  table → 0 rows; `figure.axes` → 0 (cleared); detail pane → the exception text
  (`ValueError: inner_diameter_um (400.0 um) must be smaller than outer_diameter_um …`).
  Nothing from the previous valid state survives. Restoring a valid value recomputes and
  the headline returns.
- **Exceptions are not swallowed.** `app.py:317-328` catches, then *displays*. The two
  export handlers (`370`, `391`) catch and raise a `QMessageBox.critical` carrying the
  exception type and message. No `except: pass`, no bare `except:`, no fallback default
  substituted for a failed computation anywhere in the GUI.
- **The embedded plot is redrawn, never cached** — `figure.clear()` + `add_subplot(111)` +
  `shannon_safe_operating_area` on every single recompute (expensive, but correct).
- **Recompute is synchronous and fires on every widget signal** (`app.py:206-214`,
  `243`, `150`, `162`), so there is no worker thread and therefore no lag race between a
  changed input and a displayed result. `setKeyboardTracking(False)` means a half-typed
  number is not computed, which is the right choice.

**Can an exported PDF disagree with what is on screen? For the PDF: no. For the figure: yes.**

- `export_pdf` (`app.py:356-373`) builds from `self._calc` — the same object that produced
  the headline, table and detail pane. There is no path by which the PDF describes a
  different configuration than the one displayed, and if `_calc is None` the export refuses
  with *"Fix the invalid input first."* **Verified.**
- `export_figure` (`app.py:375-396`) also builds from `self._calc`, but hands it to
  `safety_summary`, whose **panel (b) silently recomputes at library defaults** (C2). So
  the exported figure disagrees with the screen whenever the user has moved `Shannon k`,
  `CIC policy` or `Tissue sigma` off their defaults — which the GUI invites them to do with
  three dedicated widgets. With k=1.2 and σ=0.10 the exported figure prints
  `binding limit 6.88e+03 µA` while the GUI headline says the limiting current is 4869.59 µA.
  **This is the one place where an export contradicts the screen, and it is a figure
  destined for a manuscript.**

**The one hard GUI failure: a plot exception kills the process.** `app.py:349-352` sits
outside the try/except. Forcing `shannon_safe_operating_area` to raise during a
`valueChanged` gives **exit code 134 (SIGABRT)** — PyQt6 aborts from C++ before any Python
handler runs; even `except BaseException` in the caller's frame is never reached. The
module docstring's promise ("The window never hides a failure … surfaces the exception text
in the results pane rather than silently reverting to a previous valid state") holds for
input errors and fails for render errors. And because the text panes are written at
331-347 and the canvas at 349-352, the update is non-atomic: in the window between them the
panes describe the new protocol while the canvas still holds the old one.

Minor: `k_value` has `decimals=2`, so a typed `1.749` becomes `1.75` — rounding **up**,
the less-conservative direction (L3). `STATUS_COLOURS[assessment.status.value]` at
`app.py:330` is an unguarded dict lookup; a new `Status` member would raise `KeyError`
inside the slot and hit the same SIGABRT path as H8.

---

## 8. Silent-failure inventory

Complete for the audited scope. "Silent" = the program continues and produces an output a
reader would take at face value, with no exception, no visible warning and no flag.

### 8.1 Exception handling — the full census

There are **four** `except` clauses in the entire audited scope. None is bare, none is
`except Exception: pass`, and none discards the error.

| file:line | Clause | Verdict |
|-----------|--------|---------|
| `io/tabular.py:159-163` | `except Exception as exc:` → `{"label":…, "status":"ERROR", "error":f"{type(exc).__name__}: {exc}"}` | **Acceptable but incomplete.** The message is preserved and typed, and `stop_on_error=True` re-raises. The silence is downstream (M4): the row's numeric columns become NaN. |
| `gui/app.py:320-328` | `except Exception as exc:` → headline "Invalid input", detail = exception text, `_calc = None` | **Correct.** Surfaces, does not swallow. |
| `gui/app.py:370-372` | `except Exception as exc:` → `QMessageBox.critical(…, f"{type(exc).__name__}: {exc}")` | **Correct.** |
| `gui/app.py:391-393` | `except Exception as exc:` → `QMessageBox.critical(…)` | **Correct.** |

`grep -n "except" neurostim/io/*.py neurostim/viz/*.py neurostim/gui/*.py neurostim/audit.py
examples/worked_example.py scripts/*.py` returns nothing else. **There is no bare `except:`
and no `except Exception: pass` anywhere in this scope.**

### 8.2 `warnings.warn` — none exists

`grep -rn "warnings.warn\|import warnings" neurostim/ examples/ scripts/` → **zero hits.**
So the specific hazard asked about ("a `warnings.warn` a GUI or PDF reader will never see")
**does not exist in this package** — nothing is warned. The inverse problem is what is
present: several conditions that *should* warn are instead rendered as ordinary output
(M5, M6, M7, M9) or not rendered at all (H11).

### 8.3 Silent numeric / data failures

| file:line | Pattern | What is silently produced |
|-----------|---------|---------------------------|
| `safety/assessment.py:122-131` | `min()` over a list that may contain NaN | A NaN limit is dropped; `limiting_current_uA` reports a bound that ignores a check the assessment itself marked FAIL. Order-dependent (`min([141., nan]) == 141.`, `min([nan, 141.]) is nan`). **H3** |
| `safety/assessment.py:118-131` | Candidate list omits three checks | `limiting_current_uA` = 141.4 µA while the protocol FAILs from 22 µA. **C1** |
| `io/tabular.py:159-163` | Error record has only `label`/`status`/`error` | Every other column → NaN; `df.limiting_current_uA.min()` skips it (pandas `skipna=True` default); `df[df.status != "FAIL"]` returns errored rows as not-failing. **M4** |
| `io/tabular.py:168-171` | `pd.read_csv` with no shape assertion | Header-only file → 0 rows, **0 columns**, no `status`, no `error`, no exception. **H2** |
| `io/tabular.py:154-156` | `clean.get("k", k)` / `clean.get("policy", policy)` / `clean.get("compliance_V", compliance_V)` on a pandas record | Empty cells arrive as **NaN, not None**, so the `.get` default never fires. `k`/`current_uA` are caught downstream by explicit finite checks (good), but `compliance_V=NaN` flows straight through into H3, and `policy` would become the string `"nan"`. |
| `io/tabular.py:212` | `json.dumps(..., default=str)` | Bare `NaN` / `Infinity` tokens → invalid RFC 8259; strict parsers reject the file. **M13** |
| `io/tabular.py:182-217` | Payload has no provenance fields | `PROVISIONAL` / `NOT PEER REVIEWED` / user-measurement / `verified` / reference key all absent. **H10** |
| `io/fem.py:238-272` | `compare_with_point_source` returns a frame and evaluates nothing | A field off by 10⁶ (positions **or** potentials) returns `ratio ≡ 1e6` across every row with no error, no warning, no verdict. The docstring calls it a "sanity check". **M5** |
| `io/fem.py:41-46, 201-215` | `_match_column` returns the first alias hit | A file with both `x` (metres) and `x_um` silently uses the metre columns. No ambiguity error. **M6** |
| `io/fem.py:59-75` | No duplicate-position check in `__post_init__` | Contradictory potentials at one coordinate load cleanly; `griddata` returns an arbitrary blend. **M7** |
| `io/fem.py:143-157` | `describe()` uses raw `.min()`/`.max()` | One NaN → `potential nan to nan V`, destroying the diagnostic the `load_field` docstring points at for catching scale errors. **M8** |
| `io/fem.py:181-197, 217-222` | npz branch ignores the stored `current_uA` | `save_field` → `load_field` round-trip silently returns `current_uA=None` and `note=""`, though the npz **contains** `current_uA`. **M9** |
| `io/fem.py:263-264` | `np.errstate(divide="ignore", invalid="ignore")` + `np.where(analytic != 0, …, nan)` | Legitimate suppression (division by an exactly-zero analytic potential), but the resulting NaNs are never counted or reported to the caller. |
| `io/fem.py:160-176` | `position_scale_to_um` unvalidated | Zero, negative or NaN accepted without comment; only the downstream `min_distance_um` guard catches some of it. |
| `io/report.py:70-103` | Regex citation scan, `surname … year` within 40 chars | A year-less prose citation is silently omitted from the bibliography (`brummer_turner1977`). **H4** |
| `io/report.py:200-413` | No version, no digest, 4 settings unrendered | Two different input sets render identical input sections. `neurostim/audit.py` provides exactly the missing record and is never called. **H5** |
| `io/report.py:313-320, 347-354` | Derived quantities inherit no provenance flag | C_eff, peak potential and water-window headroom rendered unmarked from an unverified CIC, beside a peer-reviewed citation. **H11** |
| `viz/style.py:162-164` | `base.with_suffix("")` | `"shannon_k1.5"` → `shannon_k1.svg`; a second figure named `"shannon_k1.8"` overwrites it. No warning, one file on disk. **H9** |
| `viz/plots.py:87` | `zip(k_values, greys, strict=False)` against a 3-tuple | A 4th+ requested separatrix is silently not drawn. **L1** |
| `viz/plots.py:511-513` | `safety_summary` forwards neither `k`, `policy` nor `tissue_conductivity_S_per_m` | Panel (b) computed at defaults; annotation contradicts the assessment by 41 % in the permissive direction. **C2** |
| `viz/plots.py:512` | `compliance_V or calc.compliance_V` | Falsy-zero: an explicit `0.0` falls through to the calculator's value. **L4** |
| `viz/plots.py:38-42, 87-98` | Separatrix `k_values` default to module constants, never `calc.k` | The line that decided the verdict is absent from the chart; point colour and drawn lines can contradict. **H6** |
| `viz/plots.py:103, 455` | Pass/fail encoded by `markerfacecolor` / bar facecolour only | No shape, size, hatch or text difference — unreadable for a colour-blind reader and in greyscale. **H7** |
| `gui/app.py:330` | `STATUS_COLOURS[assessment.status.value]` unguarded | A new `Status` member → `KeyError` inside a slot → SIGABRT (same path as H8). |
| `gui/app.py:349-352` | Plot call outside the try/except | Exit code 134; and the text/canvas update is non-atomic. **H8** |
| `examples/worked_example.py:66-70, 91-97` | Hard-coded prose narration | Contradicts the same script's stdout in two places. **M10** |

### 8.4 `.get(key, default)` on a safety-relevant quantity

Five call sites, audited individually:

- `io/tabular.py:133` — `clean.get("label", index)`. Label only, not safety-relevant.
- `io/tabular.py:68, 101` — `_SHAPE_ALIASES.get(shape_raw, shape_raw)`. The fallthrough is
  then validated against `_ELECTRODE_TYPES` and raises on an unknown shape. **Safe.**
- `io/tabular.py:154-156` — the three override lookups. **Not a `.get` default problem but
  a NaN problem**: pandas supplies NaN rather than a missing key, so the default is never
  reached. `k` and `current_uA` are rescued by explicit finite checks; `compliance_V` is not.
- `audit.py:99-105` — `mine.get(section)` inside `differences_from`. Diff reporting only.

**No `.get(key, 0)` on a safety quantity exists.** The package does not substitute a
fallback default for a failed computation anywhere in this scope — the failure mode here is
NaN propagation and omitted candidates, not silent zeros.

---

## 9. Priority

1. **C1** — `limiting_current_uA` must consider every check that can express a current
   bound, or must be renamed and stripped of its "the number to programme against"
   framing. It is the most prominent number in both the PDF and the GUI and it is 7× wrong.
2. **C2** — forward `k`, `policy` and `tissue_conductivity_S_per_m` from `safety_summary`
   into `current_limit_sweep`. One line; removes a 41 % permissive error from a figure
   intended for publication.
3. **C3 / H1** — floor displayed limits, ceil displayed applied values, and widen the
   format when the two would collide.
4. **H11 / H10** — propagate the provisional flag to every derived quantity and into the
   JSON; do not print `(cogan2008)` beside a number derived from a user measurement.
5. **H5** — `build_report` should call `neurostim.audit.record()` and print the version,
   the full settings block and the digest. The machinery already exists.
6. **H6 / H7** — draw the separatrix at `calc.k`; add a shape or hatch cue to pass/fail.
7. **H8 / H9 / H2** — move the plot call inside the try/except; stop stripping filename
   suffixes; make a zero-row batch loud.

---

*Audit performed read-only against a clean checkout. No repo file was created, modified or
deleted; `git status` is not applicable (not a git repository), and all artefacts were
written under `$SCRATCH/io2/`. Every claim above was produced by executing code — the
transcripts are in `$SCRATCH/io2/{traces.txt, example.log, gui_boom.log}` and the rendered
PDFs, SVGs and TIFFs alongside them.*
