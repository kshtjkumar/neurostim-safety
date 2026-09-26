# Changelog

## 0.16.0 — unreleased: the limiting current was 7.07x too high

Phases 1-4 of the audit fixes. The version is a minor bump because, before 1.0, a minor
bump is where incompatible changes go, and these are incompatible:
- published numbers move (the limiting current, the in-vivo derating, the drift budget);
- `report()` and the JSON write `None` where they wrote infinity;
- the JSON is strict;
- audit records gain a payload version.

1.0.0 would promise a stable interface, and Phases 5-7 still change it.
`pyproject.toml` and `CITATION.cff` had stayed at 0.13.0 while `__version__` said
0.15.0. All three now say 0.16.0.

### The Shannon panel draws the line its verdict was decided against

The safe-operating-area panel drew separatrices at the reference values 1.5, 1.7 and 2.0
only, and coloured the operating point by the calculator's own `k`. At `k = 2.0` a point
above the solid 1.5 line was green; at `k = 1.2` a point below it was red. The
calculator's `k` is now drawn solid and labelled "this assessment", and added when it is
not one of the reference values. With no calculator the panel is unchanged.

### Pass and fail read in greyscale

Pass and fail were told apart by colour alone, and the green and red in use have nearly
the same luminance. Now:
- the operating point is a circle when it passes and an X when it fails;
- McCreery's "some damage" points are triangles, beside the circles and squares;
- a material bar that fails is hatched.

### `save_publication` keeps a decimal in the file name

`save_publication(fig, "shannon_k1.5")` and `"shannon_k1.8"` both wrote
`shannon_k1.svg`, so the second silently destroyed the first. Only an image extension is
replaced now: the first writes `shannon_k1.5.svg`, and `fig.svg` still writes `fig.svg`
and `fig.pdf`.

### An empty or partly failed batch says so

- `read_batch_csv` on a header-only file returned an empty frame with no columns, which
  looked the same as a clean batch. It now raises and names the file.
- `assess_batch([])` returns an empty frame that still has every column.
- A row that failed to build was NaN everywhere, so `frame.limiting_current_uA.min()`
  quietly reported the minimum of the rows that ran. A failed row is now `None` in every
  result column. The batch emits `BatchRowsFailedWarning` naming how many rows failed,
  and lists their labels in `frame.attrs["rows_failed"]`.
- A Latin-1 or empty file raised pandas' own error, which gave a byte offset and no path.
  It now raises `ValueError` naming the file.
- `frame.attrs["rows_failed"]` does not survive `write_csv`. The CSV's `status` (`ERROR`)
  and `error` columns are the lasting record, and `write_csv` warns again when a table
  holds failed rows. No comment header is added, because it would break default CSV
  readers.

### The batch columns say what the checks say

- `max_current_cic_uA` ignored `medium`, so every in-vivo row carried the saline figure.
  A 500 µm Pt disc read 981.75 µA beside a Charge injection ceiling of 107.71. The column
  and the `SafetyCalculator.max_current_cic_uA` property are now the check's own
  back-solve, derated in vivo.
- `max_current_cic_uA` and `cic_limit_uC_cm2` are now `None` where the Charge injection
  check did not run (a monophasic pulse). Before, they printed a limit nothing applied.
  The JSON explains each `null`.
- `net_dc_current_uA` is 0.0 for a pulse that Charge balance calls balanced. Before, it
  carried a rounding residue of about 1e-12 µA.
- A batch row can take a counter electrode: the electrode columns prefixed `counter_`,
  plus `counter_separation_um`.

### An exceedance reads as one

A FAIL used to print the applied value and its bound at the same precision. That
produced sentences such as:
- "100 uC/cm^2 exceeds the 100.0 uC/cm^2 limit";
- "k = 1.50 exceeds the 1.50 threshold";
- "4 nC/phase exceeds the 4 nC/phase";
- "needs 0.83 V but only 0.83 V available".

The applied value keeps round-to-nearest. It now gains digits only until it reads above
the printed bound (`_limits.format_exceeding`). The available compliance voltage is a
bound, so it now floors at three significant figures like the other limits: "10.00 V
available" reads "10.0 V available". It floors in the PASS and CAUTION summaries and the
detail too ("0.83 V of 14.5 V", not "of 14.52 V" for 14.5171 V). The PDF's charge density
and Shannon k rows follow the same rule.

### Every citation the PDF names is in its bibliography

The bibliography was built from the assessment's own text and matched a source only by
key, or by surname within 40 characters of its year. "Brummer & Turner's 300-350
uC/cm^2" in the Pt note therefore had no entry. The scan now also covers everything the
report renders. A first author named without a year cites that source when no other
source shares the first author. A surname right after "&" is a second author, so "Rose &
Robblee (1990)" does not also cite Robblee & Rose's 1990 chapter. Pt reports gain
Brummer & Turner 1977; no entry is lost.

### The window survives a failing plot, and takes a counter electrode

- The plot was drawn outside the error handling, so an exception from it aborted the
  whole application (SIGABRT). By then the headline, table and text already described
  the new protocol while the canvas still showed the old one. Everything is now computed
  and drawn first, and the widgets change only when all of it succeeds. Otherwise every
  view shows one failure state, with the traceback in the results pane.
- The k box has three decimals, so a typed 1.749 is no longer rounded up to 1.75, the
  less conservative direction. The pulse-width box accepts 0.001 µs; a typed 0.02 used
  to become 0.1.
- A "Counter electrode" group makes the assessment two-terminal, as the library can. The
  counter has the same geometry as the active electrode, with its own size, material and
  separation. An early version used a disc, which the library refuses beside a
  full-space electrode, so the DBS band, the microwire and the sphere showed "Invalid
  input".

### The TIFF is one a journal accepts

`save_publication` wrote its 600 dpi TIFF as uncompressed RGBA, 47 MB for the four-panel
summary. That is above journal upload caps, and journals reject an alpha channel in a
TIFF. It is now LZW-compressed RGB, 0.93 MB for the same figure, with the same pixels.
A test also pins that the JSON export never emits `NaN`: a NaN raises instead.

### The FEM import catches its own mistakes

- `compare_with_point_source` is now a check as well as a table. A potential column off
  by 10⁶ used to return a clean frame with every ratio at 10⁶. It now raises when the
  far-field median ratio is off by more than a decade, naming the likely unit mistake.
  `check_scale=False` waives the check. The median is taken over a band of distances,
  from a thirtieth to a third of the largest. A median over the farther half of the
  points by count sat on a regular grid's outer boundary, which raised on a correct
  solution with a grounded boundary.
- A file carrying two columns for one quantity (`x` and `x_um`) raises instead of
  silently taking the first.
- Duplicate positions raise.
- One NaN no longer turns `describe()` into "potential nan to nan V". The range ignores
  non-finite values and says how many there are, and `bounds_um` does the same.
- `save_field` records the note, and `load_field` reads the saved `current_uA` and note
  back. A `current_uA` passed at load that disagrees with the saved one raises.

### Each row of the report says what it rests on

- When the Shannon check does not run, as on a microelectrode, the PDF's Shannon k and
  Shannon current limit rows now say "not applied". Before, they printed a live-looking
  limit.
- The charge-injection provenance row is in µC/cm², the unit of the limit beside it. It
  names the polarity sub-range applied, for example "cathodic-first 100-150 uC/cm2
  applied, of 50-150 uC/cm2". It used to print "0.05-0.15 mC/cm2".
- A CAUTION charge-injection detail opens "-> CAUTION", not "-> PASS".
- On a sphere or hemisphere the charge-injection note says the primary distribution is
  uniform, instead of the perimeter-peak note that applies to discs and bands.
- In vivo, a policy warning now derates the endorsed end as it does the limit. Before,
  the endorsed end read as the more permissive of the two. No shipped material reaches
  this.

### The figures meet their own style contract

- No text in the exported figures is smaller than 5 pt. Before, 42 declarations sat
  between 4.2 and 4.9 pt, all mathtext superscripts:
  - unit labels are plain text ("µC/cm²", "V/m");
  - the two field-profile labels read "V falls as 1/r" and "E falls as 1/r²";
  - tick labels are 7.2 pt, so the log-axis powers of ten render at 5.04 pt.
- mathtext uses the body typeface, so a figure is set in one font rather than Arial and
  DejaVu Sans.
- `shannon_safe_operating_area` draws every requested `k`. It used to drop a fourth and
  later value silently.
- A zero ceiling is no longer drawn at y = 0 on the log axis, where it could not be seen.
  The refusal sentence names it.

### The worked example says what its own output shows

The example printed two fixed paragraphs that contradicted the assessment above them:
- that the tissue criterion was "satisfied with 7x headroom", while the Shannon check was
  NOT_EVALUATED;
- that the interface "leaves every published water window", while Water window passed
  at −0.23 V.

Both paragraphs are now read off the assessment. `compare_with_point_source` refuses a
current other than the one the field was solved at; rescale the field first.

### The operating-point label clears the legend

The Shannon panel's "k = …" label sat up and to the right of the point. For a point high
in the panel, that put it on the upper-right legend: a 1000 µm Pt disc at 8000 µA printed
"k = 3.31" across the legend entries. A point in the upper half of the axes now has its
label below and to the left, on a white backing so it stays legible where it crosses a
separatrix.

### Shannon's k prints as given

The Shannon threshold was printed with two decimals, which rounds a three-decimal k up.
The GUI's k box has taken three decimals since this release, and the API always did.
At k = 1.749 a FAIL read "k = 1.7490173716055608 exceeds the 1.75 threshold". The
threshold now prints exactly as given (1.749 prints "1.749", 1.5 still prints "1.50").
The computed k gains places only until it reads above the threshold in a FAIL, and at or
below it in a PASS. This covers the check summary, its detail, the PDF row, the figure
legend and the k warning. At two-decimal k values away from the boundary the text is
unchanged.

### No figure text sits on a line, a bar or another label

- The legends of the Shannon and amplitude-limit panels sit below their axes. Inside,
  they covered ceiling lines and data points, and on a refusal they clipped the sentence
  that replaces the limit. The summary figure is 125 mm tall rather than 115, so the four
  plotting areas keep their size.
- The binding-limit note sits below its line, in the empty safe region. Above the line,
  it crossed the cluster of ceilings on a DBS contact.
- The applied charge density in the material panel is a legend entry. It used to be
  written across the bottom bar.
- "V falls as 1/r" sits below its line. It used to sit on the line.
- On a microelectrode the Shannon panel reads "k = 1.50 (this k, not applied)" and says
  "Shannon not applied (microelectrode)".
- The operating-point label takes the first of four positions (up-right, down-left,
  up-left, down-right) that covers no McCreery point and stays out of the caption corner.
  On the DBS panel it used to cover the no-damage point at 1 µC. The not-applied note
  and the McCreery caption are one text block, so they cannot overlap.

### A strength-duration fit refuses the unphysical and says how sure it is

- `fit_weiss` raises on a non-positive fitted chronaxie. It used to return one, for
  example −60 µs with τ = nan, and fail only when the curve was later evaluated.
- Both fits report standard errors for rheobase and chronaxie and a 95 % confidence
  interval for the chronaxie. Weiss uses the least-squares covariance and the delta
  method; Lapicque uses `curve_fit`'s covariance, which was computed and discarded.
- At 5 % threshold noise the Weiss interval covers about 94 % of synthetic replicates.
  The Lapicque interval, from `curve_fit`'s local covariance, can under-cover on designs
  whose widths do not span the chronaxie: 0.82–0.90 at 10–20 % noise. Its `describe()`
  says so.
- A two-point fit says its uncertainty is not estimable.
- The fitted values themselves are unchanged.
- A design with every pulse width equal raises. It used to return a rheobase and a
  chronaxie behind a numpy RankWarning.

### The thermal transient depends only on the time asked

`pennes_transient_sphere` took its time step from the latest requested time, so an early
sample changed with the other times requested alongside it. At t = 1 ms the error was
−0.1 % alone and −15.0 % inside a 60-point sweep. The step now grows with time on a grid
set by the diffusion time alone, so a sample reads the same whatever else is asked for.
The earliest point of the thermal figure's default grid (0.1 s) rises by 15 % to its
converged value. A grid clamped to `max_cells` now raises `ThermalResolutionWarning`
instead of silently coarsening; that clamp is why a larger `domain_extent_factor` stopped
helping.

### Tissue heating uses the electrode's own thermal radius, and Elwassif is reproduced, not inverted

- **The heating estimate read half the rise.** It fed the equal-area *disc* radius,
  √(A/π), into a *sphere* solution. The radius is now the electrode's electro-thermal
  one, `thermal.source_radius_um(electrode, σ)` = 1/(4πσR_access). For a 3389 contact
  that is 690.11 µm, not 1380.22 µm, and the worked example's DBS rise at 3 mA, 60 µs,
  130 Hz goes from **3.435 to 8.061 mK**. The old figure was not conservative.
- **Elwassif's absolute number is reproduced from their drive.** 1.56 V RMS across two
  contacts, taken as spheres of the contact's area 2.0 mm apart, is 431.6 Ω and 5.639 mW.
  With the power split equally and each contact heated by itself and its partner, the
  rise is **0.8298 K against their 0.8200 K** (`elwassif2006.two_sphere_peak_rise_K`).
  The two-sphere model and the equal split are this package's choice, not the paper's.
  The previous "validation" fed back the power that 0.82 K implies at the disc radius,
  and returned 0.82 K by construction.
- `elwassif2006.implied_power_W()` now returns that 5.639 mW, and its signature is the
  drive's (voltage, σ, radius, separation). It used to invert the rise at 1.3803 mm and
  returned 7.5 mW, "roughly 325 Ω": both 2× off, compensating.
  `SOURCE_RADIUS_M` is 690.11 µm. **This reverses S-23 decision (a)**, which kept
  1.3803 mm, on the new evidence of the compensating errors.
- The README and the worked example no longer call the gap to Elwassif "not
  reconciled", or attribute it to lead self-heating. It is the protocol's power. The
  perfusion-scaling agreement is now 2.7–7.7 % (was 7.1–7.8 % at the disc radius).

### The activation estimate carries its spread

- `vta.evaluate(...)` reports the activated radius and volume across the full span of
  the current-distance constant, 300–27 000 µA/mm² over cortical elements
  (`radius_range_um`, `volume_range_mm3`), and `describe()` prints them. At 100 µA
  that is 60.9–577.4 µm, a factor of 854 in volume, where the output used to show only
  the single-k point.
- `fit_current_distance` refuses a negative fitted offset. It used to clamp the offset
  to 0 while keeping the slope fitted with it. Pass `fit_offset=False` to force I₀ = 0.
- The sensitivity module no longer claims to cover every limit. It says the thermal and
  activation estimates are not varied there, and where their spreads are reported.

### Intervals round outward, and the small converters refuse nonsense

- Interval arithmetic widens a result by one ulp at each end when floating point had to
  round it, so an interval contains every possible result. Before, `Interval(0.1, 0.1) *
  3` excluded 0.3. Exact results stay exact.
- `Interval.square()` and `** n` know a square is non-negative: `[-1, 1]` squared is
  `[0, 1]`, where `x * x` gave `[-1, 1]`.
- `Interval.from_mean_sd` refuses an infinite sd, and a negative `k` with its own message.
- The unit converters refuse NaN and infinity. `charge_uC` refuses a negative pulse
  width, and the temperature converters refuse anything below
  absolute zero.
- `field.distance_for_potential_um` checks σ > 0, as its siblings do, and
  `thermal.ohmic_power_W` refuses R = 0, as `voltage_driven_power_W` does.
- No package output moves: the package builds its intervals directly and does no
  arithmetic on them.

### The flat report says when its limit is provisional

The PROVISIONAL marker reached `describe()`, the GUI, the PDF and the JSON checks list,
but not `report()` or the batch and sweep CSVs. Those are where a machine reads
`limiting_current_uA`. `report()` now carries two new keys, and so every CSV row does
too:
- `limit_is_provisional`: `None` when there is no limit, and `None` in a row that failed
  to build;
- `limits_incomplete`.

### An audit record certifies the answer, not only the inputs

`audit.reproduces` said a record reproduced when the answer had moved. Take a record of a
500 µm Pt disc in vivo made before the in-vivo derating changed: its limiting current was
70.12 µA and is now 112.84 µA, yet it came back `(True, [])`. The digest covered the
inputs and the material record, not the results or the model's other constants.

- **Payload version 3**, which `record()` now writes, adds the answer to the digest: the
  limiting current and mechanism, the status, the provisional, incomplete and unsafe
  flags, and every check's status, ceiling and provisional flag.
- Version 3 also adds a SHA-256 per module over the constants of every module the
  assessment reads (`audit.MODEL_CONSTANT_MODULES`, `audit.model_constants()`).
- `reproduces` compares the stored results with fresh ones at every payload version.
  That record now fails with `results.limiting_current_uA: 70.12483601762932 ->
  112.84456370652995`.
- Differences now read recorded → now, walked to the leaf.
- A package-version difference alone is not a failure. It is listed beside a real one.
- Records of versions 1 and 2 still load and verify.
- **Payload version 4**, which `record()` now writes, adds the limiting-current interval
  over the published ranges and the limit per check kind. The digest hashes constants,
  not function bodies, so before this a code change in a band provider could move the
  interval while a version 3 record still reproduced.
- A version 3 record keeps its shape and still reproduces.
- Version 1 and 2 records store only `report()`, so they cannot see a change confined to
  one check. The `reproduces` docstring now says so.

### The limiting current was 7.07x too high, and is corrected

**Anyone who used a reported limiting current from an earlier version should recompute
it.** The headline was a minimum over three checks — Shannon, charge injection and
compliance — while the assessment ran nine. Four checks computed a ceiling that could not
reach it: the microelectrode charge-per-phase threshold, chronic dissolution, current
density and the water window. On the package's own worked example — a 330/270 µm Pt ring
at 80 µA, 200 µs, 130 Hz, 10 V compliance — it reported **141.4 µA** while Microelectrode
charge/phase (ceiling 20.0 µA) and Chronic degradation (70.69 µA) were both in a FAIL
state at 80 µA. The correct figure is **20.00 µA**, confirmed independently by binary
search over the assessment's own verdicts and by Cogan et al. (2016)'s 4 nC/phase over a
200 µs pulse.

It reports 20.00 µA now, and names the check that binds — `Microelectrode charge/phase`,
a check name, where it used to compose a phrase that could name a check that never ran.

Three things qualify the number, each its own field because each says something
different:

- `unsafe_at_any_amplitude` — a check outside the limit-bearing set is FAILing, so *no*
  amplitude is safe and no number is printed at all. A monophasic protocol is the case on
  record; the package used to print 15.3 mA for one.
- `limits_incomplete` — a limit-bearing check did not run, so the true limit may be lower
  than the one reported.
- `limiting_current_by_kind` — which of tissue, electrode-acute, electrode-chronic or
  instrument binds, since a user can change one and not the others.

Every reported limit also **floors** now instead of rounding to nearest. `141.37167 µA`
printed as "141.4 µA", and programming 141.4 µA FAILed the check whose maximum it claimed
to be.

### The summary figure draws the verdict it sits beside

The figure and the report go into the same manuscript, and they disagreed. `safety_summary`
took the electrode, the protocol and the compliance voltage into panel (b) and nothing
else, so all of its curves were recomputed at the library defaults — `k = 1.5`,
`conservative`, σ = 0.35 S/m — while the suptitle above them carried the user's verdict. At
`k = 1.2`, σ = 0.10 the panel annotated a binding limit of **6878 µA** against the
assessment's **4869.59**, with the drawn Shannon limit 1.41× and the drawn compliance limit
3.44× the true ones, both permissive. Panel (d) drew the field at 0.35 S/m whatever
conductivity the verdict used.

And the panel computed its own `min(Shannon, charge injection, compliance)` — the
three-check minimum this release replaced — so on the worked example it annotated
**141.3 µA** beside a headline of **20.00**.

Both are fixed. Every panel is drawn at the calculator's own settings, read off the
constructor so a setting added later cannot be dropped from the figure. Panel (b) draws
every limit-bearing check that ran at its own ceiling, labelled with the check's name, and
takes its binding amplitude and mechanism from the assessment. When no amplitude is safe,
the red rule, the shaded region and the number are replaced by the sentence naming the
check — the figure was the fifth render surface, and the only one the refusal could not
reach while `viz` computed its own minimum.

### The counter electrode's charge injection is checked

With a `counter_electrode` supplied, a new limit-bearing check, **Counter charge
injection**, compares the counter's charge density against its own material's
charge-injection capacity. It uses the larger of the two phases, the mirrored waveform's
polarity (a cathodic-first protocol is anodic-first at the counter), and the same policy,
medium and derating as the active electrode. A small counter can now bind the limiting
current, which it could exceed silently before. In a 160-configuration sweep with
counters, 36 limits fell to the counter's ceiling: for example a 50 µm Pt counter beside a
200 µm Pt disc goes from 78.54 µA to 4.909 µA. Seventeen verdicts went CAUTION → FAIL.
Without a counter nothing changes, and the check does not appear. The counter's water
window and chronic threshold are not assessed.

### A bare flat microwire tip is no longer understated

`MicrowireElectrode(d, 0, "flat")`, a wire exposed only at its cut end, took the
full-space equal-area sphere, 0.159/(σa). A converged solve of a disc on the end of an
insulating rod gives about 0.173/(σa), so the sphere was 8 % low: an under-estimate of the
required compliance voltage. That case now takes Newman's half-space disc, 0.25/(σa), an
upper bound. A 50 µm wire goes from 18 189 Ω to 28 571 Ω (×π/2). The solver and its table
are committed (`scripts/fd_microwire_reference.py`), and the sphere's error for other
exposures is documented.

### Five small guards

- A counter electrode closer than the two electrodes' reaches is refused. Each reach is the
  radius of a sphere enclosing the electrode, not its equal-area sphere: half the diagonal
  for a rectangle, and the rim, `sqrt(r^2 + (L/2)^2)`, for a band or an exposed microwire
  with its tip cap. Two 3389 bands are refused below a 1965 µm centre spacing instead of
  returning a resistance; the clinical 2 mm spacing is accepted.
- A Water window check that CAUTIONs on a drift reaching the edge after the train now says
  "CAUTION" in its detail header, not "PASS".
- Whether a limit is provisional is looked up by check name, and a missing or misspelt name
  now raises instead of silently reading "not provisional".
- The charge-injection interval, on the active electrode and on the counter, always
  contains its own point estimate. Its ends were an unrounded closed form, while the point
  is settled onto the exact float boundary of its own check, and the two could differ by
  1–3 ulps. No limit moves.
- A resting potential on the far side of the leading edge no longer crashes the
  water-window back-solve. For TiN at ±0.2 V, the interface travels 1.1 V to the edge.
  The check's declared resolution missed that distance, and about 1 configuration in
  7000 raised `LimitDidNotSettle` from `assess()`. No returned value changes.

### The return phase polarises only past rest

The compliance budget treated the return phase as a full excursion of its own, starting
from rest. Under the package's capacitor model that is not what happens. A return phase
that recovers no more than the leading charge only discharges the interface back along
the leading polarity's branch, and needs no more than `I_ret R` from the stimulator. Only
charge recovered beyond rest, `(r_a − 1)·Q`, polarises, at the opposite polarity's
capacitance. That now holds on both electrodes. It is checked against a pulse-by-pulse
integration of the same circuit.

A balanced symmetric pulse is unchanged: the worked example stays at 0.83 V and
965.3 µA. The requirement falls wherever the return phase used to bind: short return
phases (`return_phase_ratio < 1`) and over-recovery. It fell in 288 of 432 swept
configurations, by up to 44 %, and never rose. The clinical band at
`return_phase_ratio = 0.2` goes from 1.653 V to 1.647 V.

(An intermediate change in this release gave the return phase the opposite polarity's
capacitance throughout, which raised the worked example to 1.06 V. It was a wrong
mechanism and is reversed here.)

### An unbalanced train's DC offset is in the voltage budget

The compliance budget took every pulse from rest. A waveform that recovers less than it
injects, or more, leaves the difference on the interface, and the Water window check's
drift clause already follows that offset over the train. The last pulse of a train of `N`
starts `N − 1` residues from rest, and the stimulator must drive through that too. The
budget now includes it:

- under-recovery and monophasic delivery, on the leading phase;
- over-recovery, on the return phase's overshoot;
- on the counter as well, from its own area and material.

`N` counts the pulses `train_duty_cycle` delivers. On the active electrode the offset is
capped at the water-window headroom from the resting potential; beyond that the interface
is at the edge and the Water window check fails the waveform in its own right. The counter
(whose window is not assessed) and a material with no window (Ta₂O₅) are not capped, so a
continuous unbalanced train with either permits no current. The assessment then refuses and
names Compliance voltage.

A charge-balanced waveform is unchanged, bit for bit (720 of 720 swept configurations).
Of 2520 unbalanced ones, 2049 needed more voltage, 504 of them an infinite one, and none
less. For a 500 µm Pt disc at 100 µA, 200 µs, 130 Hz and 95 % recovery:

- a 1 s train goes from 0.326 V to 0.589 V;
- a continuous one goes to 0.926 V, the 0.6 V cap reached;
- with a counter, a continuous train goes to an infinite requirement (it was 0.506 V).

### An over-recovering drift is timed on the branch it charges

A waveform whose return phase recovers more than the leading phase injected drifts
toward the edge opposite the leading phase, so its offset is stored on that polarity's
branch. The drift clause used the leading polarity's capacitance for the window budget
in both directions. For most materials the two differ. A cathodic-first Pt pulse drifting
anodic was given 250 µF/cm² where the anodic branch holds 125, so it was allowed twice
the time to the edge, which is too permissive. An anodic-first Pt pulse was held to half
the time, which is too strict. Both are corrected, and a measured capacitance is still
one value.

Only over-recovering waveforms with a derived capacitance move, 2592 of 16 848 swept, and
only for materials whose two branches differ. Water-window ceilings move by exactly ×0.5
to ×2 (732 down, 708 up). Water-window verdicts go CAUTION → FAIL in 34 cases and
FAIL → CAUTION in 56. For a 500 µm Pt disc at 300 µA, 200 µs, 130 Hz, 1 s and 130 %
recovery:

- cathodic-first: the ceiling goes from 50.35 µA to 25.17 µA;
- anodic-first: it goes from 18.88 µA to 37.76 µA.

The compliance budget's cap on an unbalanced train's offset now always coincides with a
Water window FAIL, in both drift directions.

### An unbounded requirement is refused in words, and the JSON is strict

A continuous unbalanced train with a counter electrode, or on a material with no water
window, needs an unbounded compliance voltage. Every surface used to print it as `inf`:
"needs inf V", "headroom -inf V (inf % used)", "train offset inf V ... after inf
unbalanced pulses", an `inf` cell in the batch CSV. `report_to_json` wrote `Infinity`,
which is not JSON, and it did so for every continuous train, through
`protocol.train_duration_s`.

Now:

- The requirement reads "no finite voltage: a continuous unbalanced train leaves an
  unbounded DC offset, and ..." with the reason: the counter's water window is not
  assessed, or the material has none.
- `report()` gives `required_compliance_V = None` and a new `required_compliance_note`
  column.
- The JSON is strict. It writes `null` for the two unbounded fields and gains a
  `null_reasons` object mapping each one's path to its reason.
- The drift detail says "during continuous stimulation" instead of "(inf s)".

Finite requirements render exactly as before, and apart from the two new keys the JSON is
unchanged.

A saved report reads back: `protocol_from_report(payload)` restores a continuous train's
`null` duration to `math.inf`. `protocol_from_dict` refuses a bare `null` duration by name.
The batch and sweep frames hold `None`, not `NaN`, in `limiting_current_uA` and
`required_compliance_V`, in every row. The CSV files are byte-identical.

### Provenance: bounds that are numbers, and a flag for every constant

- A charge-injection range, a polarity sub-range or a chronic threshold must have positive
  finite bounds. A NaN bound used to construct, and every policy that read it returned
  nan. So did an infinite or non-positive bound. `with_measured_cic` now checks its high
  end as it already checked its low end.
- `ChronicThreshold` has a `verified` flag. It rolls into `Material.verified` beside the CIC
  and the water window, and `describe()` marks an unconfirmed threshold PROVISIONAL. Every
  shipped threshold is verified, so no shipped verdict moves.
- The JSON report gains a `provenance` object: each applied constant's reference key and
  verified flag, and the material's roll-up.
- The PDF's provenance section gains a "Chronic degradation threshold" row. The threshold
  used to be applied without one.
- `with_measured_cic` no longer presents the base material's other constants as yours.
  The water window and chronic threshold stay in force, marked `inherited_from` the base
  material. Every render reads "published for Platinum (rose_robblee1990), not measured
  on this electrode", and the material note says which constants are inherited. The
  `water_window=` and `chronic_threshold=` keywords take your own value, cited as
  `user_measurement`, or `None` to drop it, which is recorded in the incomplete-limits
  note.
- A material with its own water window no longer crashes the water-window back-solve.
  The seed was read from the shipped material with the same key, so
  `replace(Pt, water_window=...)` raised `LimitDidNotSettle`.

### One polarity convention for the water window, and a strict argument contract

These changes affect direct callers of `water_window.evaluate` and
`effective_capacitance_uF_cm2`. `SafetyCalculator.assess` already passed consistent
arguments, so none of its numbers move.

- The capacitance follows the pulse's own polarity by default.
  `anodic_first_for_capacitance` that disagrees with `anodic_first` raises. AIROF at its
  own charge-injection limit now lands on the window edge; the default call used to report
  0.43 V of headroom and PASS.
- With the polarity unknown (`anodic_first=None`), the capacitance is the smaller of the two
  polarities' values, which is the conservative choice. The narrower half-window used to be
  taken, which enlarged C. For Pt it is now 125 µF/cm², against 250 before.
- The drift inputs (`net_dc_current_uA`, `area_cm2`, `train_duration_s`,
  `recovered_charge_uC`) come together or not at all; a partial set raises. A waveform that
  Charge balance calls balanced has no drift, as in `assess()`.
- A charge result with no current interval now raises rather than collapsing its band to
  a point.

### Butterwick's own exponent, SIROF's two sources, and a digest that covers the conditions

- The electroporation threshold's duration dependence uses Butterwick's published fit,
  t^-0.48 for retina under sustained pulsing, anchored at 6 ms. It is capped by the line
  through their two published anchors, so it never exceeds 0.061 A/cm² at 6 ms or 1.3 at
  6 µs; the cap is this package's construction, not theirs. Below 6 ms nothing changes.
  Above it the threshold falls slightly (×0.981 at 10 ms).
- SIROF's in-vivo derating (2-4×) names both of its sources: Kane et al.'s "factor of
  2-3" and Cogan 2016's "factor of four".
- The audit digest covers the measurement conditions: the verified flag, area basis,
  waveform, bias, medium, temperature, measured area, polarity sub-ranges and recommended
  policy. The payload is versioned, so a record made before this release still verifies
  and reproduces the way it was made. New records' digests differ from old ones for the
  same inputs.

### Small electrodes: what Butterwick measured, beside what the package models

Below 200 µm the current-density threshold is unchanged: the large-electrode density
extended as d⁻². Butterwick et al. also measured this regime directly, 139 µA on retina
at 600 µs and 55 µA on CAM at 60 µs, with a t^-0.29 slope for the small pipette (p. 2264).
Those figures are now recorded in `butterwick2007`, with
`measured_small_electrode_A_per_cm2()` to compare against. The model sits below every
point checked: at 600 µs and 200 µm it gives 0.169 A/cm², against the 0.44 A/cm² the
measured current makes over a 200 µm disc (2.62× below on retina, 1.12× on CAM). The
measured line is not adopted, because the CAM and retina anchors disagree under the
package's CAM rule (about 90 µA predicted, 55 µA measured). The comparison holds at the
saturated pulse count. Below it, the single-pulse relief is applied on top of d⁻², which
was not measured on small electrodes. The Current density check was already provisional
at every size. Its detail now says so for this regime. Butterwick gives the small pipette as 0.115 mm in
the text and 0.12 mm in the Fig. 6 caption. The module now notes both sizes, and no
number depends on which is right.

**Short trains on small electrodes get no single-pulse relief.** Below 200 µm the
threshold is now the saturated (50-pulse) one whatever the pulse count. Butterwick
measured the pulse-count dependence only with a 1 mm pipette (p. 2263, Fig. 3). Applying
it on top of d⁻² put one pulse on a 100 µm retina disc at 2.7× the density the paper
measured on small electrodes. This tightens the threshold for trains of fewer than 50
pulses below 200 µm, by up to 7× on retina and 14× on CAM (n = 1). On the three
microelectrode presets (`mccreery_microelectrode`, `mccreery2010_chronic`, `weiland_tin`),
the Current density ceiling at one pulse falls from 822.4 µA to 117.5 µA. None of their
limiting currents move, because Microelectrode charge/phase binds first. At and above
200 µm nothing changes.

The Current density check can PASS, and always could. It is provisional at every size,
so any limit it sets carries the PROVISIONAL note. The 0.6.0 entry below, and the
check's own docstring, said it "never returns a bare PASS". The docstring and the
caveat comment are corrected, and no verdict changes.

### Five smaller corrections to the data modules

- `mccreery1990.separating_k_range()` returns (1.699, 2.107), from the highest no-damage
  point to the lowest all-damage point, with the partial-damage points inside. It returned
  (1.699, 1.699), a band of zero width.
- The Ta2O5 module's target densities, 10,000 µC/cm² and 50 A/cm², belong to the
  0.5 × 10⁻⁶ cm² electrode the paper quotes them for. On the module's 10⁻⁴ mm² electrode
  they are 5,000 µC/cm² and 25 A/cm².
- `elwassif2006.THERMAL_CONDUCTIVITY_RANGE_W_PER_MK` is the paper's full sweep, 0.45-0.6.
  It had dropped 0.45, the hottest case. The 0.82 K peak's docstring now names its two
  rows correctly.
- The TiO2 capacitor note quotes the source's "a factor of as much as 4" and its table
  (2.4× storage), not "5-10x".

### Derived values say they are derived, and second-hand citations say so

- The AIROF record's measured area, 4.1 × 10⁻⁴ cm², is the midpoint of the 3.7-4.5 × 10⁻⁴
  cm² that Hu et al. state (p. 494), and its note now says so.
- The Ta2O5 module's Schaldach figures are back-solved from the densities the paper gives,
  and the note says that rather than presenting them as read from it.
- The DBS lead's contact diameter is not stated in Elwassif et al. It is the
  manufacturer's figure, and the docstring names it as such.
- Elwassif et al. state no source radius either. `SOURCE_RADIUS_M` is now one contact's
  equal-area sphere, 690.11 µm. The 1.3803 mm equal-area disc radius was first kept and
  documented. That decision (S-23 (a)) is reversed below: the disc radius put the implied
  power and impedance 2× off in compensating directions.
- Four sources the package cites but does not hold are now in `references.py` as
  entries of their own, each with a note naming the paper it was cited through: Wang &
  Weiland 2012 and McCreery 2008 (via Cogan 2016), and Robblee & Rose 1990 and Lan,
  Daroux & Mortimer (via Riedy & Walter). A new `chapter` source type covers the book
  chapter.

### Citations that point at the paper the values came from

- `elwassif2006` cited the J Neural Eng article, with its DOI and PMID, but its Table I
  values are read from the conference paper (Proc. 28th IEEE EMBS, pp. 3580-3583). The
  reference is now the conference paper. That PDF prints no DOI, so none is given; the
  journal article is named in the note.
- The same paper states "a constant Vrms of 1.56 Volt" for 10 V, 185 pps and 210 µs. The
  RMS of that setting is 1.971 V; 1.56 V implies 131.5 µs. The paper's number is kept,
  because its temperatures were computed at it, and the discrepancy is recorded beside it.
- `leung2014` is dated 2015, its issue (IEEE TBME 62(3), March 2015). The key is
  unchanged.
- The `mccreery2010_chronic` preset is checked against its paper, which is in the
  library: 2,000 ± 150 µm² exposed at the tip of a penetrating shaft. Weiland 2002 is
  still not in the library, and the `weiland_tin` preset says so.

### Three more conditions restored to their numbers

- AIROF's in-vivo derating (10×) now cites Hu et al.'s own sentence, "the in vivo value
  is about 10% of the in vitro ones" (p. 888). The evidence had welded it to their
  separate comparison of AIROF with platinum.
- Rose et al.'s two best-reported capacitor electrodes no longer carry a 200 µs pulse
  width. That figure belongs to a theoretical column of their Table III. The etched-Ti
  value was measured on an AC capacitance bridge (Table I).
- McCreery et al. 2010's 4 nC/phase now carries its defining conditions (cathodic 200 µs
  pulses, +0.6 V interpulse bias applied to raise charge capacity, 2000 ± 150 µm²
  activated iridium). The 60 µm radius at 50 % duty is described as the
  stimulation-induced loss: the insertion injury accounted for most of the loss within
  150 µm.

No number moves.

### 316LVM's figures are attributed to where they came from

The stainless-steel record called 20 µC/cm² Riedy & Walter's own year-long conclusion. It
is not. Their paper (IEEE TBME 43(6), 1996) adopts it "Based on this report", a cited
tissue-damage figure (their ref. [8], p. 663). The 40 µC/cm² "has been reported"
(p. 660). Their own work is a corrosion test at 20 µC/cm², which is consistent with the
lower figure (p. 662). The record now says so, with the sentences stored verbatim.

The record also carried the corrosion test's conditions (100 µs, 60 pps, interstitial
fluid, 0.016 cm²) as if they were the conditions of a charge-injection measurement that
nobody made. They now sit in the note, labelled as the corrosion test's. The limit
therefore has no stated pulse width, and the Charge injection check says so: in a sweep,
80 SS316LVM checks went PASS → CAUTION with the "no stated pulse width" caveat. No limit
moved. The 1.2 V reversible limit is theirs by citation too (ref. [5], p. 662).

### Platinum's in-vivo derating is Leung's own, 3.2-8.7x

With `medium="in_vivo"`, platinum and platinum-iridium CICs were divided by up to 14.
That figure came from the best in-vitro value over the worst in-vivo value, taken at
different pulse widths. That is the comparison Leung et al. avoid; they publish their own
factors at matched pulse widths (IEEE TBME 62(3), p. 852): "between 8.7 times less
(200 μs pulsewidth) and 3.2 times less (3200-μs pulsewidth)". The range is now 3.2-8.7x.

In-vivo Pt and PtIr charge-injection limits rise by 14/8.7 = 1.609x (in a 864-configuration
sweep: 216 limits up, 14 verdicts FAIL → CAUTION). Saline limits and the other materials
are unchanged.

**Then corrected to 9.11×, at every pulse width.** The quoted "8.7 (200 μs)" is not
Leung's largest factor. It is the 100 μs pair: Fig. 4 (p. 853) gives about 5.7× at
200 μs. Their largest matched reduction is 35 µC/cm² in vitro (abstract, p. 849) over
3.84 acute in vivo (p. 852) at 100 µs, which is 9.11×. That factor now applies at every
pulse width, so every in-vivo Pt and PtIr charge-injection limit tightens by
8.7/9.11 = 0.9545 (−4.5 %) relative to the 8.7× above. On a 500 µm Pt disc at 50 µA and
200 µs the limiting current goes from 112.84 to 107.71 µA. No preset's status changes.
Net of both corrections, the release moves in-vivo Pt limits from ÷14 to ÷9.11, a
×1.536 relaxation.

Below 100 µs Leung measured nothing, and they report that the reduction grows at short
pulse widths. A limit derated there is now provisional
(`ChargeResult.derating_provisional`), and so is the Charge injection or Counter
charge injection check.

A per-width curve was considered and declined. It relaxes in-vivo limits 1.5-2.7× above
100 µs on single-site data. It also misses cortex: Leung's one cortical point, 7.84× at
400 µs, sits well above the suprachoroidal 4.7×. The digitised Fig. 4, with its method
and calibration, is recorded in `cogan2016` (`LEUNG_FIG4_DIGITISED_UC_CM2`,
`PT_IN_VIVO_DERATING_DOC`).

### Reports carry every setting, their own version, and their provenance

- The PDF gains "Settings" (all 11 calculator settings, the counter electrode included)
  and "Reproducibility" (package version and the audit digest). It showed 4 settings and
  no version, so two reports that differed only in the resting potential rendered the
  same settings beside different peak potentials.
- The JSON report gains `package_version`. `settings` now holds every setting, with
  `counter_electrode` and `counter_separation_um` null without a counter. Each
  `provenance` entry gains `peer_reviewed` and `note`: for a user measurement, your own
  note and `peer_reviewed: false`.
- A user measurement no longer claims peer review. Its reference entry defaulted to the
  journal source type.
- The audit record's JSON is strict: a continuous train's duration is `null`, explained in
  `null_reasons`, and `audit.load` restores it. A record written before, with
  `Infinity`, still loads. Digests are computed exactly as before, and a record made
  without a counter has the same settings, so stored digests still reproduce. A record
  with a counter now carries it.

### A provisional limit says so wherever it is shown

- A limit set by a check flagged provisional is marked on `describe()`, the PDF header,
  the GUI headline and the summary figure: "PROVISIONAL: the binding check (Shannon
  criterion) rests on a constant or model flagged as unconfirmed". It used to be marked
  only in the JSON check list. When the monotonicity cap binds, the biphasic
  counterpart's binding check decides. In a 3 072-configuration sweep, 894 of the 1 536
  headlines with a limit are now marked; none were before.
- An unverified charge-injection limit (a `with_measured_cic` value) sets the interfacial
  capacitance. Everything derived from it now says PROVISIONAL: the Water window and
  Compliance voltage checks, the water-window detail's interface line, the compliance
  polarisation, and the PDF's peak potential, required compliance, interface model and
  water-window provenance rows. This is asserted by dependency: every check whose ceiling
  moves when only the unverified number moves is flagged.
- A Water window limit set by the drift clause is provisional, and says "the limit is a
  no-leak bound": the capacitor model has no leakage. (2 016 shipped configurations
  gain the flag; no number moves.)
- A caller-supplied `capacitance_uF_cm2` is labelled "capacitance supplied by the
  caller". It was labelled "derived from the material's own CIC".
- An unverified chronic threshold makes the Chronic degradation check provisional.

### The DC drift runs over the train's on-time

The water-window drift clause timed the offset against the train's wall-clock duration,
while the pulse count, the mean and RMS currents and the compliance offset all scaled with
`train_duty_cycle`. Under the package's leak-free capacitor the offset grows only while
pulses are delivered, so the clause now asks whether the edge is reached within
`train_duration_s × train_duty_cycle`. The ceiling is back-solved over the same time, and
the detail says "(on-time)". A real interface also relaxes during the off-time, so on-time
is still conservative.

- This relaxes every duty-cycled unbalanced train, by up to 1/duty. In a sweep of 27 648
  configurations, 10 557 water-window ceilings rose (×1.04 to ×10), 1 139 Water window
  verdicts went FAIL → CAUTION, and 4 233 limiting currents rose. Nothing at full duty
  moved.
- The review's own case, a 3389 band at 3000 µA, 90 µs, 130 Hz, monophasic, 1 s at
  20 % duty, delivers 7.02 µC against an 8.977 µC budget. It reached the edge at 0.2558 s
  of a 0.2 s on-time, so it goes from FAIL to CAUTION.
- The same protocol at full duty (ledger 2) is unchanged: FAIL at 0.2558 s.

### Shannon says it was fit on discs

Shannon (1992): "the limit of safe stimulation is linearly related to electrode diameter,
not electrode area", because charge builds up at the edges. The criterion is written in
area, so a ring and a disc of equal area got the same limit despite about three times the
perimeter, with no caveat. For every non-disc geometry the Shannon check is now at best
CAUTION ("fit on discs, not this geometry"), its detail quotes that sentence, and its limit
is marked `provisional`. This includes a preset disc that stands in for another shape.
The limit's value is unchanged. Over a 168-configuration sweep no overall verdict moved,
because the monopolar compliance CAUTION already held them there.

### The voltage budget includes the return path

`SafetyCalculator` takes `counter_electrode` and `counter_separation_um`, which must be
given together. With them, the required compliance voltage has both interfaces and both
spreading resistances, less the mutual term of two sources sharing the medium. So two 3389
contacts 2 mm apart need 1.349 V at 3000 µA/90 µs, not the single-contact 1.006 V and
not twice it. Far apart, two identical interfaces need exactly twice one.

**Without a counter electrode the Compliance voltage check is now CAUTION, never PASS.**
The number is unchanged, but the check says it assumes a monopolar single-interface
budget, which under-estimates a real two-terminal pair. The README quick-start line
changes accordingly.

A counter with `measured_impedance_ohm` is refused, because the measurement may already
include the return path. So are a counter whose environment differs from the active
electrode's and a separation that lets the two overlap.

Where the counter electrode reaches so far: `SafetyCalculator`, `compliance.evaluate`,
the Compliance check and its detail, the PDF's "Required compliance" row (whose breakdown
now includes the counter's polarisation or states the single-interface assumption), and
`sensitivity`. **Not yet:** the batch CSV (`assess_batch` has no counter columns), the GUI
form, and the settings recorded by `report_to_json` and `audit`. Those surfaces assess
every protocol monopolar, and say so through the CAUTION above.

### Geometry inputs that meant nothing are refused

- `linear_array` and `grid_array` refuse a non-finite pitch. `pitch_um <= 0` let NaN
  through, giving an array whose minimum pitch was NaN.
- `ElectrodeArray` refuses two sites at the same point, which gave a pitch of 0.0 and a
  field that diverges between them. `ArraySite` refuses a non-finite position.
- `MicrowireElectrode` refuses `cone_height_um` unless the tip is conical. Before, it was
  ignored and the area was the plain wire's.

### The equal-area substitution errs high, not low, for rings and strips

The ring and rectangle docstrings stated the direction of their access-resistance
approximation backwards. The equal-area disc *over*estimates both: it is the most
resistive plane shape of its area, so the substitution is an upper bound and is
conservative for the compliance budget. Against the exact elliptic disc it is 1.34× high
at aspect 10, and against the thin-ring asymptote 4.3× for a ring 1 % as wide as it is
across. No number changes; a reader adding margin in the stated direction would have
double-counted it.

### The current-density detail describes the electrode's own distribution

The Current density check printed a disc's primary distribution for every electrode:
centre at 0.50× average, the outer 25 % above it, and the density diverging at the rim.
A sphere or a hemisphere flush in its plane has a uniform distribution, with no edge at
all. A ring, rectangle, band or microwire crowds at its own edges, but not with the disc's
figures. The detail now says which, and gives the disc's figures only for a real disc.
No margin, limit or verdict moves, because the threshold comparison uses the average
density.

`current_density.evaluate` takes the `electrode`. `CurrentDensityResult` gains
`distribution`, and its `centre_ratio` and `fraction_above_average` are `None` where no
figure is known. `ratio_at_area_fraction` raises for anything but a disc.

### One half-space/full-space convention per geometry

The field model and the access resistance disagreed about which space an electrode injects
into, and the band and microwire used a formula for the wrong one.

- **Planar potentials double.** Disc, ring and rectangle sit flush in an insulating plane.
  Their access resistance was already Newman's half-space disc, but the field model gave
  them a full-space point source. So their far field was exactly half the true value:
  22.74 mV where the exact disc solution gives 45.47 mV (500 µm radius, 100 µA,
  0.35 S/m, 1 mm). Every `potential_V`, `field_V_per_m` and field panel for these
  geometries is now twice what it was. `io.fem.compare_with_point_source` takes the
  `electrode`, so an imported planar field is compared against the right source.
- **Immersed access resistance falls by 36 %.** The clinical band and the microwire took
  Newman's half-space disc, although they have tissue on every side. They now take the
  equal-area sphere. A converged finite-volume solve puts it high at every aspect: +0.6 %
  for the 3389 contact, +0.3 to +1.2 % from aspect 1 to 2, and up to +10 % for short
  bands. The 3389 contact goes from 517.5 Ω to **329.5 Ω** (converged 327.6 Ω).
  The required compliance voltage falls with it. On the worked example's DBS contact the
  binding limit moves from compliance to Shannon, and the thermal estimate falls from
  5.396 to **3.435 mK** (72.66 → 46.26 µW).
- **`Electrode.environment`** (`"half_space"` / `"full_space"`) is a per-instance field
  with a class default, and it sets both the field factor and the equal-area substitute.
  `DiscElectrode` gains `stands_in_for`, for presets that use a disc of the right area to
  represent another shape. Four presets are re-tagged from their papers and no longer
  print "(exact)": the two penetrating McCreery microelectrodes (full-space; resistance
  15 699 → 9 994 Ω and 28 289 → 18 009 Ω), the Beebe iridium wire stub, and the Weiland
  TiN electrode, whose paper is not in the library to check.

### Charge imbalance, return phases and DC drift

A return phase that does not recover what the leading phase injected could not be entered
at all, and neither could anything that follows from it. That is the commonest real DC
fault. Now:

- **`StimProtocol.charge_recovery_ratio`** (default 1.0) is the fraction of the injected
  charge the return phase recovers. **`train_duty_cycle`** (default 1.0) is the train's
  on/off schedule. It scales the pulse count, the mean current and the RMS current, and
  replaces the intra-pulse duty in the validated-envelope comparison, which made McCreery's
  own fit protocol read as 25x outside its own envelope. Both are in the JSON protocol
  block, the batch columns and the GUI form. At their defaults every earlier number is
  unchanged.
- **The return phase is evaluated.** Current density compares each phase against its own
  threshold, and compliance budgets the larger of the two phase voltages. For
  `return_phase_ratio = 0.2` on a clinical band the required compliance goes from 0.52 V to
  2.59 V, and the limit moves from Shannon (15.3 mA) to current density (9.57 mA).
- **Water window models DC drift.** Unrecovered charge accumulates on the interface
  capacitance. The check FAILs when the edge is reached before the train ends, and
  CAUTIONs with the time when it is reached afterwards. The recovered part of each pulse
  rides on the accumulated offset, so it is spent from the same budget. A monophasic
  3000 µA train on a clinical band used to PASS with 0.58 V of headroom; it now FAILs at
  0.256 s.
- **Monophasic delivery gets no charge-injection limit**, because none was measured on such
  a waveform, and its limit-bearing ceiling is capped at the biphasic answer. Charge
  balance FAILs for any waveform that recovers nothing, so the headline refuses a number.
- **The headline also refuses when a limit closes to zero**, for example a resting
  potential on the window edge, or a continuous train with any unrecovered charge. It
  prints `no amplitude is safe: Water window permits no current at all` instead of
  `0 uA`. The JSON gains `permits_no_current` and `monotonicity_capped`.

**Consumers of `current_sweep.csv` and batch output:** `limiting_mechanism` holds a
sentence, not a check name, for every row whose headline refuses.

Two arithmetic defects in the first version of the drift clause are fixed in the same
release. A balanced pulse with `return_phase_ratio != 1` could crash `assess()` or report a
limit above an amplitude that FAILed. A partial recovery near 99 % could raise
`LimitDidNotSettle`. The unrecovered charge is now computed as one product, not a
difference of two.

## 0.15.0 — a permissive setting could improve the verdict

Reading a generated report surfaced a defect no test was watching for. On 316LVM,
switching the charge-injection policy from `conservative` to `optimistic` turned the
check from CAUTION to **PASS** — by applying 40 µC/cm², the exact figure Riedy & Walter's
paper was written to argue down. Selecting the weaker evidence made the verdict better,
and nothing said so.

The caveat was not missing from the package. It was 576 characters of text sitting in the
material's `note`, and `MeasuredRange.describe()` only ever emitted `note` for user
measurements — so it reached no report, no check detail, and no screen. Stored provenance
that never renders is not provenance.

Two changes:

- **`MeasuredRange.recommended_policy`** records which end of a range the primary source
  itself endorses, with a `recommendation_note` saying why. Most sources report a range
  without arguing for an end and stay `None`; 316LVM is currently the only material where
  one takes a position. Selecting a more permissive policy than the source endorses now
  emits a `POLICY:` warning and forces CAUTION — a limit the cited work disputes cannot
  return an unqualified PASS, for the same reason a protocol outside the Shannon envelope
  cannot.
- **Reports now print the material's own caveats** in the provenance section, both the
  limit note and the material note.

### Ta2O5 high end corrected

Found while auditing the same path. 0.14.0 stored 0.088–0.26 mC/cm² at 100 µs, but
260 µC/cm² is Rose et al.'s Table III best-reported value, which equals the DC
capacitance times 0.8·V_f — a **slow-charge** figure. Pore resistance costs a pulsed
electrode up to 80 % of that, which is why their measured 0.1 ms values are 88–140.
Capping a 100 µs limit with a DC number overstates pulsed capacity. The range is now
**0.088–0.15 mC/cm²**, spanning the two designs measured under pulsing: etched Ta at
88–140 and the sintered electrode Schmidt et al. implanted at 150.

### Verification

522 tests (up from 513). ruff and mypy clean, 86/86 transcriptions verified.

## 0.14.0 — four primary papers read, three provenance gaps closed

Four papers previously cited-but-unread were obtained and read in full. Every number
below came out of the primary text, not out of a review's summary table, and each one
either closed a gap or corrected a value the reviews had rounded.

### Ta2O5 — the limit was never a material constant

Cogan (2008) Table 2 gives Ta2O5 `~0.5 mC/cm²` with no pulse width and no potential
limits. Reading Rose, Kelliher & Robblee (1985) shows why no such constant exists: a
capacitor electrode's charge storage is `Q/A = C × 0.8 V_f`, set by the roughness factor
and the anodisation forming voltage chosen when the electrode was built. The eight
published designs in `neurostim.data.ta2o5_capacitor` span **80-fold**.

`~0.5 mC/cm²` is above *every Ta2O5 microelectrode* in that paper — the highest is
0.26 mC/cm², and that is a slow-charge figure. It sits just below Guyton & Hambrecht's
sintered porous **surface disc** at 0.7 mC/cm², which is also where Merrill's otherwise
unexplained 700 µC/cm² comes from. Quoting either for a microelectrode overstates the
limit by two- to threefold. The material now carries **0.088–0.26 mC/cm² at 100 µs**.

The paper's own arithmetic is now reproduced as a test, and one step in it is easy to get
wrong: the etched-Ta roughness factor of "12 to 30" only comes out if the smooth baseline
is thickness-corrected from a 5 V to a 10 V film first. Uncorrected it gives 6 to 15.

Two operating constraints with no faradaic analogue are now recorded: the film must be
pulsed cathodically **from a standing anodic bias** (Schmidt et al. held +4.2 V), and it
draws a continuous DC leakage current that must stay in the 1–10 nA band.

Schmidt et al. (1982) also decompose a measured pulse into **three** elements — access
resistance, lumped *pore* resistance, and lumped capacitance. `neurostim.transient`
models two. On a porous electrode the pore term is absorbed into the polarisation, so the
module now documents that it overstates polarisation, and therefore understates the
charge-injection limit, on sintered or etched electrodes.

### 316LVM stainless steel — pulse width, window and polarity

Riedy & Walter (1996) supplies all three. Their protocol was **100 µs at 60 pps**,
capacitor-coupled, in a bath mimicking interstitial fluid, run for **365 days**.

- The conservative 20 µC/cm² end is now the *authors' recommendation*, not merely the low
  end of a range: they argue the standing 40 µC/cm² figure down because it rests on a
  one-hour study, and only half of it is available non-faradaically.
- A **1.2 V** reversible charge-injection limit is now on record. It is stored in a
  `WaterWindow` so the polarisation check can run, which made `WaterWindow.scale`
  necessary — rendering a polarisation magnitude as "vs Ag|AgCl" would misstate it.
  Independent check: 20 µC/cm² over 1.2 V implies 17 µF/cm², within a whisker of the
  20 µF/cm² double-layer value, which is exactly what "available for double-layer
  injection" should mean.
- **Anodic-first is the safer polarity here.** After a year, SEM found pitting on the
  *cathodically* pulsed electrode and none at all on the anodic one. This reverses the
  prior literature claim and is the opposite of platinum.
- Albumin at 0.4 and 4.0 g/L had no effect on corrosion or on the transients.

### Strength–duration — the first measured chronaxies

`neurostim.models.strength_duration` still ships no defaults, because chronaxie depends
on the preparation. What it lacked was anything to *check a fit against*. Asanuma, Arnold
& Zarzecki (1976) measured 11 curves with the shock artifact cancelled:

| structure | chronaxie | median | n |
|---|---|---|---|
| cortical cell bodies | 0.12–0.2 ms | 0.14 ms | 4 |
| cortical axons | 0.06–0.13 ms | 0.085 ms | 7 |

Mann-Whitney p < 0.012; one neuron measured at both sites gave 0.13 ms at the soma and
0.10 ms at its fibre. `plausible_cortical_chronaxie()` flags a fit outside 60–200 µs.

Two findings that bound what any stimulation claim can assert, independent of charge:
axon collaterals run **1.0 mm** laterally and fire at **0.4 µA**, so ICMS cannot be
assumed to be activating the neuron under the electrode; and trains at **80 µA / 0.2 ms**
(16 nC/phase) depressed descending volleys in 5 of 7 trials, with a second depression
starting 3–5 min later and lasting 30 min. That is orders of magnitude below anything the
Shannon criterion or the charge-injection limits can see — a real ceiling this package's
checks do not cover, now recorded so it is not silently absent.

Figure 4's fibre rheobases are printed as "20, 2.5 and 1.0 µa". Twenty is almost
certainly a slip for 2.0. Stored as printed and flagged, with the corrected reading behind
`rheobase_fibres_ua()`.

### Still open

- **TIROF** pulse width and water window. The source is Robblee et al. (1986), *MRS
  Symposium Proceedings* 55:303–310, a conference proceedings not obtained. The Inorganics
  2022 iridium-oxide review was read in full and does not address neural stimulation.
- Strength–duration remains **model-checked, not data-reproduced**: Asanuma et al. publish
  chronaxies and a figure, not a table of threshold-versus-width points. The measured
  curves also rise more steeply below ~0.15 ms than either classical form predicts, which
  is now documented rather than smoothed over.

### GUI — first tests, and a bug they immediately found

The desktop app had **no tests at all**. That is worse than it sounds: the window is a
*second* place where defaults are declared, so a literal typed into a spin box can
disagree with the library constant it mirrors and nothing else in the suite notices.

One had. The Shannon **k** box opened at **1.7** while `SafetyCalculator` defaults to
**1.5** — the drift dates from when the default moved to Shannon's own recommended value.
A higher k permits more charge, so the GUI was the *more permissive* of the two: the same
electrode and protocol got a different answer depending on how they were entered.

Impact is confined to protocols where Shannon is the binding constraint, which means
larger electrodes. On a 1 mm platinum disc the GUI reported a limiting current of
3137 µA against the API's 2492 µA — **26 % high**. Below about 500 µm the
charge-injection limit binds first and the two agreed.

The box now reads `shannon.K_SHANNON` rather than a literal, so it cannot drift again,
and `TestDefaultsMatchTheLibrary` asserts the GUI and the API return the same assessment
for a freshly opened window — deliberately calling the API with *no* k, policy or
conductivity, so the test only passes while all three widgets still open on the library
defaults.

**51 new headless tests** (`QT_QPA_PLATFORM=offscreen`, no display needed, safe in CI),
driving the real widgets and the real `recompute` with nothing mocked: every material,
every geometry, invalid-input recovery, both export paths, dialog cancellation, and that
each input is actually wired to recompute. Two lock in this release's material changes —
Ta2O5 must report its water-window check as NOT_EVALUATED rather than PASS, and SS316LVM
must now evaluate it.

### PDF report — six defects found by reading real output

A generated report surfaced problems no unit test was watching for. All the arithmetic
checked out — ring area, access resistance, Shannon k, every limit and the compliance
split verify by hand — but the document itself was wrong in ways that matter for
something meant to be attached to a methods section.

- **HTML entities printed literally.** `314 &micro;m`, `0.0004079 cm&sup2;`, `6268 &ohm;`
  throughout the electrode and protocol tables. Only ReportLab `Paragraph` decodes
  entities; `_kv_table` was putting raw strings into table cells.
- **Provenance rows truncated.** Same root cause: a raw-string cell clips at the column
  edge instead of wrapping. The charge-injection row ended mid-word at
  `on 0.016 cm^2, geo`, losing the area basis — in the one section whose entire purpose
  is to state measurement conditions.
- **Peak electrode potential hardcoded "vs Ag|AgCl".** For 316LVM that is a
  misstatement: its limits are a polarisation magnitude relative to rest, measured
  against SCE. The report said one thing here and the correct thing two inches below in
  the provenance table, because that row goes through `WaterWindow.describe()` and
  honours `scale`. Now both do.
- **Dangling citations.** Butterwick's electroporation threshold and Kuncel & Grill's
  current-distribution result were discussed in the warnings text with no bibliography
  entry, because the reference list was a hand-maintained tuple that had gone stale. It
  is now derived by scanning the assembled text, matching both bare keys and prose
  citations via each reference's own first-author surname near its year — so a new
  source is picked up automatically.
- **A duplicate reference.** `kuncel_grill2004` and `kuncel_grill2004_full` were the same
  paper — identical authors, title, venue, volume, pages, DOI and PMID — and would have
  printed twice. The short key was dead; removed.
- **Limitations contradicted the body.** The boilerplate claimed the water-window check
  "models the interface as a pure double-layer capacitance". It has not since 0.10.0:
  `C_eff` is derived from the material's own CIC and window, which the report's own
  provenance section states. Rewritten to describe what the check actually does and what
  that leaves it able to test.

Also corrected: the Shannon summary rendered `k = -0.80 at threshold 3.00 ... (k above
Shannon's 1.5)`. Two different quantities under one symbol, and the note flatly
contradicted the number beside it whenever the metric was negative — which is common. It
now reads "threshold k above Shannon's 1.5".

One non-defect, documented rather than fixed: the ohm reaches the page as U+2126 OHM SIGN
rather than U+03A9 GREEK CAPITAL OMEGA, because the built-in Type 1 Helvetica has no
omega and ReportLab substitutes a glyph that maps back to U+2126 whichever entity is
used. They are canonically equivalent under NFKC and visually identical, but do not
compare equal — worth knowing before grepping extracted report text.

### Verification

513 tests (up from 441). **86/86** transcribed values machine-verified against source
PDFs, none skipped. 46 references. ruff and mypy clean.

Five tests that pinned the *old* gaps — "no pulse width on record", "no window on record"
— were rewritten to assert the new sourced values. Closing a gap means moving a key out of
that list, never inventing a value to fill it.

## 0.13.0 — measurement ingestion, and full transcription coverage

### Voltage-transient analysis

`neurostim.transient` extracts electrode parameters from a measured pulse, which is the
measurement that replaces the literature. Rose & Robblee put it plainly: "the only
certain way to determine a particular electrode's reversible charge injection limit is by
measurement of its potential excursions."

It separates the **access voltage** (the instantaneous ohmic `iR` step, not part of the
electrode potential) from the **polarisation** (the interfacial excursion that must stay
inside the water window). Failing to separate them overestimates the excursion, and Cogan
warns that naive compensation "may create hazards".

Validated against a synthetic trace with known parameters:

| | true | recovered |
|---|---|---|
| access resistance | 800 Ω | **800.8 Ω** |
| interfacial capacitance | 250 µF/cm² | **252.5 µF/cm²** |
| extrapolated CIC | — | **152 µC/cm²** vs literature Pt 100–150 |

It gives you three numbers the package otherwise assumes: your access resistance
(replacing the conductivity choice that *dominates* the sensitivity analysis), your
interfacial capacitance, and your own charge-injection limit. It also flags a trace too
coarse to resolve the ohmic step, since that silently understates the excursion.

### Transcription coverage now complete

Cogan 2008 and Merrill 2005 were read from web downloads and were never in the papers
folder, so the verifier had been skipping their claims. Restored from cache:
**52 of 52 values verified, zero skipped.** The two most load-bearing papers in the
package are now machine-checked like the rest.

### Ta2O5 gap documented rather than closed

Merrill 2005 does not supply the missing pulse width either. Its Table 2 gives two
geometric charge storage capacities from separate sources, 700 and 200 µC/cm², which
bracket Cogan's 500 — a threefold spread with no conditions attached to any of the three.
Recorded as such.

441 tests.

## 0.12.0 — usability and reproducibility

### Electrode presets, each one from a cited paper

`neurostim.electrodes` holds ten geometries, every one reproducing an electrode a paper
in the bibliography describes. No commercial part numbers were invented. Each preset's
area is tested against the area its source states.

That makes the library smaller than a vendor catalogue and more useful than one: these
are the geometries the damage and charge-injection data were actually measured on.

```python
from neurostim import electrode, get_preset
calc = SafetyCalculator(electrode("dbs_3389"), protocol)
print(get_preset("mccreery_surface_largest").describe())
```

### Audit records

`neurostim.audit` captures package version, full inputs, **and the constants in force**,
with a SHA-256 digest over all of it. The digest deliberately covers constants as well as
inputs: this package corrected four of its own during development, and a digest over
inputs alone would silently claim reproducibility across a change that altered the
answer. `reproduces()` says whether a fresh run matches and, if not, exactly which value
moved.

Operator and note are excluded from the digest, so the same calculation by different
people on different days still reproduces.

### Sensitivity analysis

`neurostim.sensitivity` varies each defensible choice over its range and ranks them by
how far the binding limit moves. For a DBS contact driven at 3 mA:

| Input | Moves the answer |
|---|---|
| tissue conductivity | **3.67×** |
| medium (saline vs in vivo) | **2.69×** |
| Shannon k | 1.00× |
| CIC policy | 1.00× |

The damage criteria are irrelevant there — compliance voltage binds. Which is exactly
the kind of thing worth knowing before arguing about k.

### Fixed

`get_preset` lowercased the query but not the registry, making any mixed-case key
unreachable. Found by the preset area tests.

### Also

`CITATION.cff`. Wang et al. (2014) and McIntyre & Grill (2001) added, giving three
sourced mitigations for edge concentration: recessing the geometry, a thin conducting
surface film, and shaping the pulse leading edge — the last being the only one available
after an electrode is built.

45 references, 429 tests.

## 0.11.0 — the last three unvalidated modules audited

Applied the audit that found the 0.10.0 water-window bug to strength-duration, VTA and
compliance. No second contradiction, but three findings.

### New external evidence: two independent measurements agree

Stoney et al. (1968) measured a current-distance constant by **single-cell recording** in
cat motor cortex. McCreery et al. (2010) measured a **damage radius** by chronic
histology in cat sensorimotor cortex, 42 years later.

At 4 nC/phase and 100 µs, Stoney's constant puts the activation radius at **176 µm**;
McCreery observed neuron loss to **at least 150 µm**. Agreement within ~20 %, from
unrelated experiments and methods — and consistent with the mass-action damage mechanism
McCreery proposes, in which damage follows the activated volume.

The activation radius also sits comfortably in the far field (124 µm at 20 µA against
Cogan's ~50 µm point-source threshold), so the assumption behind the current-distance
rule holds where it is being applied.

### Tehovnik's worked example reproduces

"K = 20 µA/(0.1 mm)² = 2,000 µA/mm²" and "an element with a constant of 1,292 µA/mm²
would require 1,292 µA to be activated 1 mm away" — both reproduce exactly.

### Weiss and Lapicque are not interchangeable

Fitted to the same rheobase and chronaxie they agree **exactly at chronaxie** — both are
constrained to pass through 2·I_rh there — and diverge either side by up to **17 %**:

| Pulse width | Weiss / Lapicque |
|---|---|
| 0.33 × t_c | 0.83 |
| 1.0 × t_c | 1.00 |
| 6.7 × t_c | 1.14 |

The package offered them side by side without saying so. Now documented, with the
warning not to mix a rheobase fitted under one with a chronaxie fitted under the other.

### Compliance verified consistent

The polarisation term and the water-window excursion share one interfacial capacitance;
injecting the CIC now lands exactly on the window edge in both. Enforced per material.

408 tests.

## 0.10.0 — an internal contradiction, found by asking whether verification was robust

Auditing which modules had external validation exposed one that did not, and it was
wrong: the water-window check contradicted a measurement held elsewhere in this package.

### The contradiction

Rose & Robblee **measured** platinum staying inside the water window up to
100–150 µC/cm². The package's own model said it exits at **12 µC/cm²** — a tenfold
disagreement between two numbers sitting in the same codebase. The model fired a false
alarm on nearly every realistic protocol.

The cause was physical, not a bug. The interface was modelled as a bare 20 µF/cm²
double layer, but platinum and iridium oxide are pseudocapacitive — most injected charge
goes into reversible surface reactions. Merrill quotes Pt pseudocapacitance at
210 µC/cm² of real area, an order of magnitude above double-layer storage.

### The fix

`C_eff` is now derived from each material's **own** measured charge-injection limit and
window, so injecting exactly the CIC brings the electrode exactly to the window edge —
which is what the CIC means. Consistent by construction, and now enforced by tests for
every material and both polarities.

The half-window is matched to the swing direction: an anodic-first pulse is bounded by
the anodic limit, cathodic-first by the cathodic one. Windows are asymmetric, so this
matters — Pt gives 125 µF/cm² anodic-first and 250 cathodic-first.

| | before | after |
|---|---|---|
| Pt effective capacitance | 20 µF/cm² | **125–250** |
| Window reached at | 12 µC/cm² | **100–150** (= the measurement) |
| Required compliance, 330/270 ring @ 80 µA | 3.43 V | **0.83 V** |

That old 2.83 V polarisation term **exceeded the entire 1.4 V window** — impossible for
an electrode operating inside its measured limit. The compliance check shares the same
capacitance and was over-estimating required voltage by ~4×.

### What the check now does

It is no longer a second, worse test of charge density — the charge-injection check
already covers that from the same measurement. What it adds is the effect of anything
shifting the starting potential: a non-zero resting potential, or the interpulse bias
several materials need to reach their quoted limit. Those are not captured anywhere else.

396 tests.

## 0.9.0 — external validation suite

`tests/test_published_cases.py` feeds published inputs to the package and checks it
returns numbers those papers also publish but that the package never stores. This is the
external-validation gap that earlier releases had to concede.

The strongest new case: **Kuncel & Grill state a 1.26 × 1.5 mm DBS contact at 3 V gives
0.0993 A/cm².** They publish neither the current nor the resistance. Starting from
geometry alone the package predicts **0.0972 A/cm² — 2 % agreement** — through three
independent steps (lateral-surface area → Newman access resistance → Ohm's law) that
never touch their figure. It also independently supports the 0.35 S/m default, since that
is the conductivity which reproduces their result.

24 published cases, agreements as achieved:

| Source | Reproduced | Agreement |
|---|---|---|
| Kuncel & Grill 2004 | current density from geometry + 3 V | **2 %** |
| Kuncel & Grill 2004 | 30 µC/cm² limit ← Shannon at k ≈ 1.75 | exact |
| Cogan 2008 | DBS contact area 0.06 cm² | 0.3 % |
| Cogan 2016 | their k ≈ 1.25 worked example | exact |
| Elwassif 2006 | ΔT ∝ σ, ΔT ∝ 1/κ | 0.7 %, 0.9 % |
| Elwassif 2006 | perfusion attenuation 1/(1+a/L) | 8 % |
| Elwassif 2006 | 0.82 K peak from implied power | 2 % |
| McCreery 1990 | Table I self-consistency, stated thresholds, eq. (1) | exact |
| Merrill 2005 | footnote 2 arithmetic, eq. (5.1) identity | exact |
| Newman 1966 | R = 1/(4κa), and V(a) ≡ I·R by two derivations | machine precision |
| Butterwick 2007 | both retina anchors; their mK thermal estimate | exact |
| Gabriel 1996 | blood σ → σᵢ; grey matter ≈ 0.1 S/m at 1 kHz | exact |

Every tolerance is the agreement actually achieved, not a target chosen to pass. Added to
CI as its own step.

383 tests.

## 0.8.0 — polarity, and transcription verified mechanically

### Pulse polarity now selects the range that was actually measured

Rose & Robblee resolved platinum into **50–100 µC/cm² anodic-first** and
**100–150 cathodic-first**. The package stored the 50–150 union and ignored
`anodic_first`, despite carrying the flag and already using it for the water-window
excursion. That was wrong in both directions:

| Polarity | was | now | error |
|---|---|---|---|
| anodic-first | 50–150 | **50–100** | optimistic end was 1.5× too permissive |
| cathodic-first | 50–150 | **100–150** | conservative end was 2× too strict |

Beebe & Rose likewise resolved AIROF into 2.1 anodic-first and 1.0 cathodic-first; both
are now used. Materials whose sources did not resolve polarity are unaffected.

### Transcription is now machine-verified

`scripts/verify_transcriptions.py` searches each cited PDF for every constant the package
stores. **50 of 50 values confirmed present in their source paper.**

Two initially failed and both turned out to be OCR artefacts, not errors: the 1995
McCreery scan renders `0.37` as `0-37` and `0.87` as `0,87`. The checker now accepts
decimal-separator variants generically, which matters because the oldest scans are both
the least reliable to OCR and the most load-bearing.

It cannot catch a value attached to the wrong material or condition — that needs a
reader — but it closes the typo failure mode permanently, and it runs in CI.

### Two collected-but-unused fields put to work

- **`interphase_gap_us`** now reaches the charge-balance report, explaining the
  efficiency-versus-recovery trade-off in both directions.
- **`temperature_C`** now flags measurements taken below body temperature.
  `AIROF_TEMPERATURE_GAIN` records Cogan's 1.67 → 2.0 mC/cm² rise from 20 °C to 37 °C, so
  a room-temperature literature value can be recognised as conservative. Not applied
  automatically: it was measured on one film at one pulse width.

359 tests.

## 0.7.0 — all 26 papers integrated, zero non-peer-reviewed constants

### PEDOT corrected, and the last unreviewed source removed

Three peer-reviewed measurements cluster tightly and none is near Cogan's headline value:

| Source | Value | Peer reviewed |
|---|---|---|
| Cui & Zhou 2007 | 2.3 mC/cm² | yes |
| Luo et al. 2011 | 2.5 ± 0.1 (n=4) | yes |
| Nyberg et al. 2007 | 3.6 | yes |
| Cogan 2008 Table 2 | **15** | **conference abstract** |

PEDOT moves from **3.6–15 → 2.3–3.6 mC/cm²**. The abstract value is 4–6× above every
replicated measurement and is documented as unreplicated rather than used. PEDOT is
"comparable to iridium oxide", not far above it.

**Every material constant in the package is now peer-reviewed.**

### In-vivo derating traced to its own measurement

Replaces the blanket factors quoted in Cogan's review:

| Material | Factor | Source |
|---|---|---|
| Pt, PtIr | 2–14× | Leung 2014: in vitro 34–54 µC/cm² vs 3.84–16.6 in vivo |
| AIROF | 10× | Hu 2006: in vitro 3–4 mC/cm², ~10× above in vivo |
| SIROF | 2–4× | Kane 2013, chronic cat cortex |
| porous Pt | 8× | Terasawa 2013, ~45 days rabbit sclera |

Cross-check: derating the saline limit lands on what Leung actually measured in vivo.

### Duty cycle is now evidenced (McCreery et al. 2010)

The primary source for the "4 nC/phase threshold" is richer than the number:

- **2 nC/phase** (100 µC/cm²) — no detectable change
- **4 nC/phase** (200 µC/cm²), 100 % duty — neuron loss to radius **≥150 µm**
- same stimulus at **50 % duty** — loss radius **~60 µm**

So 4 nC/ph is the *lowest damaging* level, not the highest safe one; both are now kept.
And halving duty cycle shrank the damage radius **2.5×** at identical charge — the
clearest quantification of what omitting duty cycle costs. The envelope check now carries
a duty-cycle axis citing this contrast, with no interpolation between the two tested
values.

The authors also found loss around **unpulsed** control electrodes, so chronic
microelectrode damage is not bounded by any stimulation-safety calculation.

### Also added

Rubinstein 1987 (Green's function solution for recessed discs, error <7 %) recorded as
the mitigation for the edge concentration the package computes.

41 references, 349 tests.

## 0.6.0 — three flagged checks become quantified

Three papers arrived that turn warnings into numbers.

### Current density now has a threshold (Butterwick et al. 2007)

The check added in 0.5.0 computed a value with nothing to compare it against. It now
compares against a measured electroporation threshold:

- falls as **t^−0.5** with pulse width (their fitted exponent on the two retina anchor
  points is −0.44; both are recorded)
- **independent of electrode size above 300 µm**; rises as **d^−2 below 200 µm**, because
  the threshold *total current* is constant there
- **saturates after ~50 pulses**, having fallen ~7× (retina) from a single pulse

Anchors: 0.061 A/cm² at 6 ms, 1.3 A/cm² at 6 µs. The check never returns a bare PASS —
the threshold is chick membrane and retina, so applying it to cortex is an extrapolation
across preparation and is labelled as such.

### Frequency dependence is now sourced (McCreery et al. 1995)

| Frequency | Damage slope (% EAD per α unit) | Threshold (× full α recruitment) | R |
|---|---|---|---|
| 20 Hz | 0.003 | none resolvable | 0.07 |
| 50 Hz | 0.37 | 1.1 | 0.87 |
| 100 Hz | 1.1 | 0.8 | 0.85 |

Doubling 50→100 Hz **tripled the damage slope** and dropped the threshold to **0.73×**. At
20 Hz damage did not correlate with amplitude at all.

**Deliberately not converted into a derating factor.** The authors normalise amplitude to
α-component recruitment and state that correlation with damage "is poor when the stimulus
is expressed simply as charge per phase or as current". The envelope check now quotes the
measured numbers instead of a vague warning.

### Tissue conductivity: a 3.4× discrepancy surfaced (Gabriel et al. 1996 Part III)

Implemented the four-Cole-Cole model from Table 1. Evaluated at the effective frequency
of a 200 µs pulse it gives grey matter **0.104 S/m** — against the 0.35 S/m DBS convention
and IT'IS's 0.419 S/m.

Access resistance scales as 1/σ, so **the default may understate required compliance
voltage by ~3.4×**. The compliance check now says so explicitly, and the warning
disappears when a measured impedance is supplied. The default stays at 0.35 S/m for
comparability with published DBS work; all three values are exposed and the spread is
documented rather than resolved by preference.

336 tests. 35 references.

## 0.5.0 — the three gaps the literature says matter most

### Validated envelope: the criterion may no longer overstate its own evidence

The Shannon fit rests on one experiment — 400 µs, 50 Hz, 7 h, cat cortex, 0.01–0.5 cm²
platinum discs. Clinical DBS runs 130–185 Hz continuously for years. The package used to
report a comfortable PASS there.

`neurostim.safety.envelope` now quantifies every departure and, crucially, labels its
**direction**, because excursions are not symmetric:

| Parameter | Direction | Basis |
|---|---|---|
| frequency **above** 50 Hz | **reduces margin** | frequency-dependent damage threshold; lower rates consistently reduced damage and SIDNE |
| frequency below 50 Hz | safer | same |
| duration beyond 7 h | **reduces margin** | total pulse count is a reported damage factor |
| pulse width, either way | **unknown** | Shannon lists it among the extrapolations he cannot support |

Outside the envelope in a non-conservative or unknown direction, the Shannon check can no
longer return an unqualified PASS. **No derating factor is invented** — none in this
bibliography supports one.

### Current density: a governing quantity that was not computed at all

Charge density was computed everywhere; current density nowhere. It is the quantity that
governs electroporation, and Butterwick et al. found its damage threshold varies with
both pulse width and frequency.

`neurostim.safety.current_density` reports it, plus the peak factor from the primary
current distribution on a disc, `J(r)/J_avg = 1/(2√(1−(r/a)²))`:

- the **centre** runs at **half** the average;
- density **diverges at the rim**;
- the outer **25 %** of the area exceeds the average — derived analytically, and within
  half a percent of the **25.6 %** Kuncel & Grill obtained by finite element modelling of
  a cylindrical contact. Different geometry, different method, independent agreement.

No threshold is applied, because none is sourced here.

### In-vivo derating is now a switch, not a docstring

`SafetyCalculator(..., medium="in_vivo")` divides the saline limit by the reported
reduction — **10× for Pt and AIROF**, 4× for SIROF (Cogan et al. 2016). Materials with no
reported derating say so rather than silently passing. Intervals derate too.

For a clinical DBS contact this moves the binding limit from 17.6 mA to 5.0 mA and
charge-injection utilisation from 6 % to 60 %.

308 tests.

## 0.4.0 — twelve primary sources read end to end

Every paper in `papers_stim_calc_ref/` was read in full and reconciled against the code.
Four constants changed, two of them in the non-conservative direction.

### Corrections

| What | Was | Now | Source |
|---|---|---|---|
| Shannon `k` default | 1.7 | **1.5** | Shannon 1992: "k = 1.5 is a conservative limit and has been used in all calculations in this report" |
| `k = 2.0` label | "least protective defensible choice" | **`K_DAMAGE_OBSERVED`** | Shannon: "the straight line falls in an area where damage was observed" |
| Current-distance `k` | 675 µA/mm² (web summary) | **1292 µA/mm²** | Stoney 1968 via Tehovnik 2006 fig. 1A |
| AIROF limit | 1–5 mC/cm² | **1.0–3.5 mC/cm²** | Beebe & Rose 1988 primary values |
| Thermal limit | 1 K (invented) | **2 K** | ISO 14708-3:2017 clause 17.1(a) |

The old current-distance constant underestimated threshold ~2× and so **overestimated
activation radius ~1.4×**.

### Retracted claim

0.3.0 stated the thermal model "does not reconcile" with Elwassif et al. That was wrong.
The comparison was between their **continuous 1.56 V RMS bipolar** drive (~7.5 mW) and a
**duty-cycled 3 mA monopolar** train (~70 µW) — a 100× power difference, not a physics
error. Their Table I now serves as a validation set: linear in σ (0.7 %), inverse in κ
(0.9 %), perfusion attenuation `1/(1+a/L)` within 7–8 %.

### New criteria

- **Microelectrode regime** (Cogan et al. 2016). Below ~3×10⁻⁴ cm² the Shannon
  codependence does not hold; the governing quantity is charge per phase with a ~4 nC/ph
  threshold. The Shannon check now returns `NOT_EVALUATED` there rather than reporting
  headroom that contradicts it.
- **Chronic degradation.** Pt dissolves at 20–50 µC/cm², *below* its 50 µC/cm² injection
  limit (Rose & Robblee 1990).
- **ISO 14708-3 CEM43 thermal dose.** Brain threshold is 2, twenty times stricter than
  muscle or peripheral nerve.

### Datasets transcribed

`neurostim/data/` now holds McCreery 1990 Table I (12 conditions, plotted under the
Shannon line), Elwassif 2006 Table I, Cogan 2016 regime boundaries and in-vivo derating,
ISO 14708-3 Table 101, and Kuncel & Grill's current-distribution figures.

### Caveats now surfaced

- **In vivo CIC is up to 10× below saline** for Pt and AIROF, 4× for SIROF, 8× for porous
  Pt (Cogan 2016). Recorded, not auto-applied.
- **Water-window reference electrode.** Both primary sources measured vs **SCE**; Cogan
  restates vs Ag|AgCl. SCE sits ~45 mV positive of saturated Ag|AgCl.
- **Charge density is a geometric average.** 25.6 % of a DBS contact operates above it
  (Kuncel & Grill 2004), who call the 30 µC/cm² limit *liberal*, not conservative.
- **CSC ≠ CIC.** Hudak et al. 2017 explain mechanistically why cyclic-voltammetry storage
  capacity overestimates injectable charge.

### Arithmetic checks on the sources

- McCreery's data pin the observed boundary at **k = 1.699** — Shannon's 1.5 is
  deliberately below it, and it is why Merrill drew 1.7.
- Cogan 2016 calls McCreery's 12 µC/cm² / 6 µC-per-phase point "k ≈ 1.4"; it computes to
  **1.86**. Their other worked example (60 µC/cm², 0.005 cm² → "k ~ 1.25") reproduces
  exactly, confirming the standard formula.
- Rose & Robblee is paper **VIII** (publisher metadata); Cogan's reference list prints VII.

32 references, 25 with DOIs. 288 tests.

## 0.3.0 — provenance hardening

Closes the gaps that could be closed without new papers. No new features; this release
is about making the existing numbers defensible.

### Every charge-injection limit re-sourced to its own primary paper

The materials database previously cited `cogan2008` for everything, because that is the
review the values were read from. Each row now cites the study Cogan cites, with its
measurement conditions:

| Material | Now cites | Pulse width | Notes added |
|---|---|---|---|
| Pt, PtIr | Rose & Robblee 1990 | 200 µs | pH 7, geometric area; Brummer & Turner's 300–350 µC/cm² explicitly excluded as measured at >0.6 ms |
| AIROF | Beebe & Rose 1988 | 200 µs | bicarbonate buffered saline; Qinj rises ~20 % from 20 °C to 37 °C |
| SIROF | Cogan et al. 2004 | 400 µs | strongly area dependent: 5 mC/cm² at 2000 µm² vs 750 µC/cm² at 0.05 cm² |
| TiN | Weiland et al. 2002 | 500 µs | 0.9 mC/cm² in vitro on 4000 µm² |
| PEDOT | Cogan et al. 2007 | 400 µs | **meeting abstract, not peer reviewed** |
| TIROF | Robblee et al. 1986 | none stated | |
| Ta2O5 | Rose et al. 1985 | none stated | |

- **PEDOT changed from 15 to a 3.6–15 mC/cm² range.** Cogan's headline 15 mC/cm² comes
  from a conference abstract. The low end is now Nyberg et al.'s peer-reviewed
  3.6 mC/cm², so the conservative default no longer rests on unreviewed work.
- `Reference` gained `source_type`/`peer_reviewed`; non-peer-reviewed sources are
  labelled `NOT PEER REVIEWED` wherever they surface.
- `MeasuredRange` gained `temperature_C` and `measured_area_cm2`, because Cogan states
  explicitly that both change the answer.
- **Rose & Robblee bibliography corrected**: it is paper VIII at 37:1118–1120
  (publisher metadata). Cogan's reference list 71 prints "VII" at 37:1119–20, which
  appears to be an error there. Documented in the reference note.

### Tissue properties replaced with sourced values

The thermal block was mostly unsourced textbook figures. All of it now comes from the
**IT'IS Database v4.2**, with standard deviation and sample size recorded per value.

| | before | after |
|---|---|---|
| perfusion | 0.0085 1/s (provisional) | **0.01329 1/s** (763.7 ml/min/kg, n=3) |
| thermal conductivity | 0.527 W/m/K | **0.547** W/m/K (n=2) |
| specific heat | 3650 J/kg/K (provisional) | **3695.8** (n=5) |
| density | 1040 kg/m³ (provisional) | **1044.5** (n=9) |
| penetration depth L | 4.04 mm | **3.29 mm** |

`BRAIN.fully_verified` is now `True`. Added `GREY_MATTER`, `WHITE_MATTER`,
`WHOLE_BRAIN` and `ELWASSIF_BRAIN` presets, plus `perfusion_per_s()` for the
ml/min/kg → 1/s conversion (the density factor in it is a ~1000× trap).

Added `GREY_MATTER_CONDUCTIVITY_S_PER_M` = 0.419 (n=214) and white-matter and blood
equivalents. The default stays 0.35 S/m — it is the DBS-modelling convention and
changing it would silently move every published comparison — but it is now documented
as the weaker-supported of the two.

### Uncertainty propagation

New `neurostim.uncertainty.Interval`. Published ranges now survive to the final answer
instead of collapsing at the `policy` setting:

```
Limiting current: 70.69 uA (Pt charge-injection limit)
  across published ranges: 70.69-212.1 uA (Shannon k 1.5-2.0, full material range)
```

`shannon.max_current_interval_uA()` propagates the whole k = 1.5–2.0 band (a factor of
1.78 in current), and `SafetyAssessment.limiting_current_interval_uA` reduces every
constraint to whichever binds at each end. Documented as interval arithmetic, not
uncertainty quantification — it ignores correlation and assumes inputs can conspire.

### Bibliography

26 → 27 references; 21 now carry DOIs, all resolved via Crossref rather than recalled.
The six without are genuinely pre-DOI (Lapicque 1907, Weiss 1901, Pennes 1948,
Robblee 1986) or a meeting abstract. Pennes deliberately carries **no** DOI: the one
Crossref returns belongs to the 1998 reprint, not the 1948 original, and attaching it
would misattribute the record.

### Tooling

- ruff + mypy configured and **both clean** across 32 source files
- GitHub Actions CI: tests on Python 3.10–3.13 (Linux) and 3.12 (macOS), lint/type job,
  and a separate **literature provenance** job — a drift between a constant and its
  publication is a different class of failure from a bug and is reported as such
- `scripts/provenance_audit.py` lists the 8 remaining documented gaps; `--strict` fails
  on them
- 220 tests (was 161)

## 0.2.0

Rebuilt from the 0.1.0 prototype. The public surface of 0.1.0 still works:
`RingElectrode(330, 270, "SS")`, `StimProtocol(80, 200, 130, 1)`,
`SafetyCalculator(e, p).report()`, and all six original report keys.

### Literature corrections

Every material constant was traced to a primary source. Four of five changed:

| Material | 0.1.0 | 0.2.0 | Source |
|---|---|---|---|
| `SS` | 0.05 mC/cm² | 0.02–0.04 | Riedy & Walter 1996 (40 µC/cm² safe, 20 non-faradaic) |
| `Pt` | 0.10 | 0.05–0.15 | Cogan 2008 Table 2, from Rose & Robblee 1990 at 200 µs |
| `PtIr` | 0.15 | 0.05–0.15 | Cogan gives one row for "Pt and PtIr alloys" |
| `PEDOT` | 5.0 | 15.0 | Cogan 2008 Table 2 |
| `SIROF` | 2.0 | 1.0–5.0 | Cogan 2008 Table 2 |

Consequence for the 0.1.0 README example: `max_current_cic_uA` moves from 70.7 µA to
28.3 µA for stainless steel. Materials added: AIROF, TIROF, TiN, Ta2O5.

### Added

- **Provenance** — every constant carries its reference, measurement conditions
  (pulse width, waveform, bias, electrolyte, geometric vs real area) and a `verified`
  flag. Unconfirmed values surface as `PROVISIONAL`.
- **Geometries** — disc, ring, rectangle, cylindrical band, microwire (flat,
  hemispherical, conical tip), sphere, hemisphere; linear and grid arrays. Exact
  access resistance for disc (Newman 1966), sphere and hemisphere; equal-area disc
  substitution elsewhere, flagged as such.
- **Protocol** — waveform, interphase gap, leading polarity, asymmetric return phase,
  duty cycle, RMS current, net DC offset, charge-balance detection.
- **Checks** — water window, charge balance and stimulator compliance voltage join the
  Shannon and charge-injection checks. Aggregate `SafetyAssessment` reports a status per
  check and identifies the binding constraint.
- **Models** — point-source field, Pennes bioheat (analytic steady state plus an
  implicit transient solver), Lapicque/Weiss strength–duration with fitting, and a
  current–distance activation estimate.
- **I/O** — batch CSV assessment, current sweeps, JSON export, scattered-point FEM field
  import, and methods-ready PDF reports with bibliography.
- **Figures** — publication style (7 pt, editable vector text, 600 dpi SVG/PDF/TIFF) and
  six figure functions, each documenting the claim it defends.
- **GUI** — PyQt6 desktop app with live recomputation, launched via `neurostim-gui`.
- **Tests** — 161 tests. `tests/test_literature.py` pins every constant to its source.

### Fixed

- `shannon_metric` raised a bare `math` domain error at zero or negative charge; it now
  raises `ValueError` explaining why the metric is undefined there.
- `RingElectrode` accepted `inner >= outer`, silently producing zero or negative area.
- `frequency_hz` and `train_duration_s` were stored but never used; they now drive duty
  cycle, RMS current, net DC and the thermal model.
- A pulse that cannot fit inside its own repetition period is now rejected.

### Packaging

`setup.py` replaced by `pyproject.toml`. Optional extras: `gui`, `report`, `all`, `dev`.
Console script `neurostim-gui`.
