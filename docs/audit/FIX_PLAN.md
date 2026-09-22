# FIX_PLAN — sequenced repair of neurostim-safety before submission

Baseline: `bfca95d` (clean, 522 tests pass, ruff clean, mypy clean).
Evidence: `CODE_MISTAKES_LOG.md` (78 entries) + `docs/audit/*.md` (six reports).
Target: JOSS/SoftwareX. Mandate: no calculation errors, no silent failures, no unsourced
numbers, no doc drift. Fixes may change reported numbers.

This plan sequences the 78 ledger entries into 7 phases and 41 commits. It does not
restate the findings; it says what order to repair them in, which test must fail first,
what number moves, and what must land in the same commit.

---

## 0. Six conventions settled up front

Several ledger entries are two surfaces of one undecided question. Decide each once, here,
and apply it everywhere rather than patching each site. Every later phase assumes these.

**D1 — `NOT_EVALUATED` sits *below* `PASS` in the severity order.**
`Status.rank` becomes `NOT_EVALUATED: 0, PASS: 1, CAUTION: 2, FAIL: 3`. `_worst` is then
"the worst status among checks that actually ran, or `NOT_EVALUATED` if none did", which
is the semantics the docstring already claims. The alternative — filtering
structurally-inapplicable checks out of the aggregate — needs a per-check "is this
applicable" predicate that does not exist and would have to be maintained by hand. The
rank change is three lines and is directly assertable (T17). Cost: an unevaluated check
becomes invisible in the headline, so `SafetyAssessment` gains a `not_evaluated` tuple and
`describe()` prints `Overall: PASS (2 checks not evaluated: Shannon criterion, ...)`.
Closes 11, unblocks 67(c).

**D2 — a reported limit always floors; the forward inequality stays exact.**
Ledger 9 (back-solve is not an exact inverse) and 49 (display rounds a maximum up) are one
rule violated twice. Add `neurostim/safety/_limits.py`:

```python
def floor_to_pass(value: float, passes: Callable[[float], bool]) -> float:
    """Largest float <= value that satisfies the forward check. At most 4 ulp steps."""
def format_limit(value: float, sig: int = 4) -> str:
    """Decimal-floor formatting: 141.37167 -> '141.3', never '141.4'."""
```

Every `max_current_uA` / `max_charge_uC` passes through `floor_to_pass` against the same
predicate the check uses; every limit rendered in text, PDF, JSON or a figure annotation
passes through `format_limit`. Do **not** loosen `ChargeResult.passes` with a tolerance —
that makes the inequality unverifiable and hides the next float bug. Closes 9, 49; makes
the newly-added limits of D3 survive their own forward check.

**D3 — the limiting current is the minimum over every check that produces a limit.**
Not over three hand-picked ones. Mechanism detail the ledger summary does not carry:
`_chronic_check` and `_water_window_check` currently never populate `Check.margin`, so the
obvious `min(c.margin * I for c in checks)` implementation silently misses them. Verified
on the worked example: only 4 of 9 checks expose a finite margin. So D3 requires first
giving every limit-bearing check a margin. Closes 1, 66; needs D2 first.

**D4 — one space convention per geometry, declared on the electrode.**
`Electrode` gains `environment: Literal["half_space", "full_space"]`. Flush planar
(Disc, Ring, Rectangular) and Hemispherical are `half_space`; immersed volumetric
(CylindricalBand, Microwire, Sphere) are `full_space`. Both `models/field._geometry_factor`
(2π vs 4π) and `geometry/base.access_resistance_ohm` (equal-area disc `1/(4σa)` vs
equal-area sphere `1/(4πσa)`) read that one property. `CylindricalBandElectrode` and the
`MicrowireElectrode` shaft override with the immersed-cylinder form `ln(2L/r)/(2πσL)`
where `L/r ≥ 2`, falling back to the equal-area sphere below that with a stated note.
Rationale for preferring the cylinder form on the band over the equal-area sphere: it is
the geometry's own solution rather than a second substitution, and for a clinical DBS band
it gives 470.7 Ω against 329.5 Ω for the sphere — the direction that is both physically
right and closer to measured DBS impedance. Closes 17, 20, 16; the invariant
`V(r=a) == I·R_access` (T5) is what proves both halves consistent.

**D5 — the McCreery duty cycles are two different quantities and both must exist.**
`envelope.py` currently compares the protocol's *intra-period current-flowing fraction*
against a 100 % reference taken from McCreery 2010's *train on/off schedule*. Split:
- The envelope excursion compares pulse duty against the **fit protocol's own** pulse
  duty, `2 × PULSE_WIDTH_US × FREQUENCY_HZ × 1e-6 = 0.04`, derived from
  `envelope.PULSE_WIDTH_US` and `FREQUENCY_HZ` which the package already stores — no new
  constant. This makes `EnvelopeResult.inside` reachable (T14).
- `mccreery2010.duty_cycle_note` is fed a **new** `StimProtocol.train_duty_cycle`
  (default 1.0 = continuous), which is what that source's 50 %/100 % contrast measured.

Closes 6 and its two symptoms (the unreachable inside-PASS branch, the 50 %-duty sentence
printed for a continuous protocol). The `train_duty_cycle` field is a data-model change,
so it is sequenced with D6, not separately.

**D6 — charge imbalance is expressible.**
`StimProtocol` gains `return_phase_amplitude_ratio: float = 1.0`, independent of
`return_phase_ratio` (which stays a width multiplier). Return current becomes
`current_uA × return_phase_amplitude_ratio / return_phase_ratio`; symmetric protocols are
byte-identical. `is_charge_balanced` switches to a tolerance relative to
`charge_per_phase_uC` (closes 15). Closes 3, revives the dead FAIL branch at
`assessment.py:567`, and unblocks 4.

**D7 — the counter electrode is an explicit input, not an assumption.**
`SafetyCalculator` gains `counter_electrode: Electrode | None = None`. `None` keeps
today's single-interface budget but the result states the assumption ("remote/large
counter; monopolar"). When supplied, the budget carries two access resistances, two
polarisation terms and the equilibrium-potential difference. This gives bipolar users the
~2× they are owed without silently doubling every existing monopolar number. Closes 5.

---

## 1. Fix order and dependency graph

```
Phase 0  harness ─────────────────────────────────────────────┐
             │                                                │
Phase 1  verdict core   D1 → margins → D2 → D3 → finiteness   │  (numbers move)
             │                                                │
Phase 2  data model     D6 → return-phase assessment          │  (numbers move)
             │          D5 → envelope repair                  │
             │          monophasic (needs D1)                 │
             │                                                │
Phase 3  space/geometry D4 → current distribution → D7        │  (numbers move)
             │                                                │
Phase 4  provenance     materials → propagation → io → lit    │  (numbers move)
             │                                                │
Phase 5  io / viz / gui (consumes everything above)           │
             │                                                │
Phase 6  models (independent of 1-5; may run in parallel)     │
             │                                                │
Phase 7  release / docs / CI ─────────────────────────────────┘
```

Hard edges, with the reason:

| edge | reason |
|---|---|
| D1 → D3 | `limiting_current_uA` must skip checks that did not run; that decision is the rank change. |
| D2 → D3 | The four newly-included limits fail their own forward check in 17/54 material×policy×polarity combinations until the back-solve floors (ledger 9, 66). Landing D3 first ships a known-broken invariant. |
| margins → D3 | Chronic degradation and water window carry no `margin` today, so the minimum cannot see them. |
| D3 → Phase 5 | Every figure annotation, PDF headline and JSON field that reports a limit reads the corrected value; fixing the plumbing first means fixing it twice. |
| D6 → 4 | Return-phase current density and compliance cannot be evaluated until imbalance and independent amplitude exist. |
| D5 ⇔ D6 | Both are `StimProtocol` fields; both ripple into `io/tabular.py`, `io/report.py`, `report_to_json` and the GUI form. Pay the ripple once. |
| D4 → 5 (counter electrode) | The two-interface budget sums two access resistances; both must already be computed under one convention. |
| 19 → 60, 59 | One root cause (an unverified CIC reaching `effective_capacitance_uF_cm2`), three surfaces (assessment, PDF, JSON). Fix the propagation, then the two renderers. |
| Phase 4 → Phase 7 docs | README's PEDOT row (74) and the two inert-flag claims (76) can only be written truthfully after the materials and propagation fixes land. |
| Phase 0 → everything | Without `pytest-cov --cov-branch` and `tests/test_units.py` the suite cannot observe most of these fixes landing. |

Phase 6 (models) touches no module Phases 1–5 touch except `models/thermal.py`'s consumption
of `access_resistance_ohm`; it can be worked in parallel and merged last, with the single
rebase point being commit C3.1.

---

## 2. Commits, tests-first

Each commit lands: the failing test(s) **first** in the same commit, then the fix, then the
doc/artifact updates listed. `pytest -q` must be red on the test alone and green after.

### Phase 0 — harness (no behaviour change)

| # | subject | closes | test first |
|---|---|---|---|
| C0.1 | `build: add pytest-cov, a branch-coverage floor and Python 3.14 to CI` | 68 (partial), T23–T26 | n/a — set the floor at today's measured 46.7 % branch and ratchet each phase |
| C0.2 | `test: add tests/test_units.py and drop the grep subprocess` | 65, 69 (§8.1), T10, T20 | T10 fails today: four unit-conversion mutants survive; `units.py` has no importing test |
| C0.3 | `build: generate example_output instead of committing it` | 61/M12 (partial) | script + CI check that regenerated output matches committed output |

**C0.3 is load-bearing for the whole plan.** `example_output/` currently holds a 47 MB
uncompressed RGBA TIFF that journals reject anyway (ledger 61/M12). Add
`scripts/regenerate_example_output.py`, commit the small artifacts only, and stop
committing the TIFF. Every later numeric commit then reruns one script instead of
hand-editing seven files, which is what makes "documentation as an atomic unit" affordable.

### Phase 1 — the verdict core (the headline number)

| # | subject | closes | test that must fail first |
|---|---|---|---|
| C1.1 | `fix(safety): rank NOT_EVALUATED below PASS and surface unevaluated checks` | 11, 67(c) | **T17** — `SafetyCalculator(DiscElectrode(2000.,"SIROF"), StimProtocol(20,400,50,3600)).assess().status is Status.PASS`; returns `NOT_EVALUATED` today for every macroelectrode |
| C1.2 | `fix(safety): floor every reported limit so it passes its own forward check` | 9, 49 | **T2** — parametrised over 9 materials × 3 policies × 2 polarities; 17/54 fail today with `100.00000000000001 > 100.0` |
| C1.3 | `fix(safety): give every limit-bearing check a margin` | prerequisite for 1 | new: `assert all(math.isfinite(c.margin) for c in a.checks if c.name in LIMIT_BEARING)` — 5 of 9 are `inf` today |
| C1.4 | `fix(safety): the limiting current is the minimum over every check` | 1, 66 | **T1** — `a.limiting_current_uA <= 20.0` (4 nC/phase ÷ 200 µs), pinned to `cogan2016.MICROELECTRODE_DAMAGE_THRESHOLD_NC_PER_PHASE` |
| C1.5 | `fix(safety): limiting_mechanism must name a check that ran` | 1 (§9b.1) | **T3** |
| C1.6 | `fix(safety): reject non-finite settings rather than dropping them from min()` | 52, 13, 14 | new: `SafetyCalculator(..., compliance_V=float("nan"))` must raise `ValueError`, and `limiting_current_uA` must raise naming the offending check if a non-finite candidate reaches it |
| C1.7 | `test: pin a FAIL and both boundary sides for every safety check` | 63, 64, 67(a,b) | **T8** (six reachable FAIL states, listed in audit_tests §10) + **T9** (`<=` vs `<` at the line). Kills mutants S3, C2, P3, A5 |
| C1.8 | `test: pin monotonicity, interval containment and dimensional consistency` | 69 | **T15**, **T16**, **T11**. Kills M4, M5 |

C1.6 note: NaN must be stopped at the boundary (`compliance_V` validation, and the batch
CSV reader's blank cells — see C5.5) so that `min()` never sees one. The assertion inside
`limiting_current_uA` is a backstop, not the fix; a silently-dropped NaN and a silently
raised one are both silent failures.

### Phase 2 — data model

| # | subject | closes | test that must fail first |
|---|---|---|---|
| C2.1 | `feat(protocol): make return-phase amplitude an independent input` | 3, 15 | **T12** — `return_phase_amplitude_ratio=0.9` gives `net_charge_per_pulse_uC ≈ 0.1 × charge_per_phase_uC` and the Charge-balance check FAILs; today `net_charge ≡ 0` for every ratio |
| C2.2 | `fix(safety): evaluate the return phase in current density and compliance` | 4 | **T13** — asymmetric `return_phase_ratio=0.25` must give a worse current-density margin than symmetric; identical today (0.3183 A/cm² both) |
| C2.3 | `feat(protocol): separate the train duty cycle from the pulse duty cycle` | 6, 67(a) | **T14** — `envelope.evaluate(StimProtocol(50,400,50,7*3600), 0.1).inside` is True; unreachable today over a 300 000-protocol sweep |
| C2.4 | `fix(safety): stop applying biphasic-measured limits to monophasic protocols` | 2 | **T4** — `mono.limiting_current_uA < bi.limiting_current_uA`; identical today (981.748 µA both) |

C2.1 must include the consumer wiring — `io/tabular.py` (`asdict(calc.p)` and the batch
column aliases), `io/report.py` (the Protocol section), `gui/app.py` (the form) — in the
same commit. A dataclass field that no serialiser writes is a new silent failure.

C2.4 decision, stated because the audit leaves it open: for a monophasic protocol the
charge-injection and water-window checks return **`NOT_EVALUATED`** with an explicit
"every stored CIC was measured biphasic (Merrill 2005); no source here validates it for
monophasic delivery", and their limits leave the `limiting_current_uA` candidate set. A
derating factor would be an unsourced number; keeping the biphasic limit is
anti-conservative and is the defect. Overall status stays `FAIL` from the charge-balance
check regardless, so the D1 rank change cannot let a monophasic protocol read better — but
T4 must assert exactly that, because D1 and C2.4 interact.

### Phase 3 — space convention, distribution, counter electrode

| # | subject | closes | test that must fail first |
|---|---|---|---|
| C3.1 | `fix(geometry): settle one half-space/full-space convention per geometry` | 17, 20, 16, 21 | **T5** — `potential_V(100, el.equivalent_radius_um, 0.35, electrode=el) ≈ 100e-6 × el.access_resistance_ohm(0.35)` for Disc, Ring, Rectangular; fails by exactly 2× today. Extend to band/microwire/sphere. Kills M1 |
| C3.2 | `fix(safety): report the current distribution of the actual geometry` | 18 | new: a sphere and a flush hemisphere must report a **uniform** primary distribution, not the disc's `0.5/sqrt(1-(r/a)²)` |
| C3.3 | `fix(geometry): correct the direction of the equal-area substitution error` | 10, 29, 28 | new: docstring assertion is not testable — pin instead against the exact elliptic-disc solution `R = K(e)/(2πσa)` (thin annulus w/b=0.01: 50 634 Ω disc vs 11 682 Ω ring), asserting the substitution **over**estimates |
| C3.4 | `feat(safety): model the counter electrode in the voltage budget` | 5 | new: a supplied identical counter electrode must exactly double the ohmic + polarisation budget; and `counter_electrode=None` must be byte-identical to today |
| C3.5 | `docs(safety): state Shannon's diameter-not-area finding where it applies` | 12 | new: a non-disc geometry must not return an unqualified `PASS` from the Shannon check (see §5, *what not to fix*) |

C3.1 also flips `access_resistance_is_exact` to `False` on the three presets that model a
non-disc physical electrode as an equal-area disc (21) — the flag is what `describe()` and
the PDF render as "(exact)".

### Phase 4 — provenance

| # | subject | closes | test that must fail first |
|---|---|---|---|
| C4.1 | `fix(materials): stop a user CIC inheriting another source's citations` | 25, 30, 24 | new: `with_measured_cic(Pt, 100).chronic_threshold` must not report Rose & Robblee's platinum-dissolution reference as its own; `MeasuredRange(low=1, high=nan)` must raise |
| C4.2 | `fix(safety): propagate PROVISIONAL to every quantity derived from an unverified limit` | 19, 60 | **T7** — Charge injection, Water window and Compliance must each be non-`PASS` or carry `PROVISIONAL` when the CIC is unverified; today the water window returns a clean `PASS` with the excursion reduced 4× |
| C4.3 | `fix(io): carry provenance and the audit record into the JSON and the PDF` | 59, 54 | new: two reports differing only in `resting_potential_V` (0.0 vs 0.35) must not render identical settings sections; `report_to_json` must carry `verified`, the reference key and the package version. `neurostim/audit.py` already builds exactly this record and `build_report` never calls it |
| C4.4 | `fix(literature): use Leung's pulse-width-matched Pt in-vivo derating` | 71 | pin 3.2×–8.7× against Leung et al.'s own sentence; today 2–14× from a mismatched-pulse-width division |
| C4.5 | `fix(literature): attribute the 316LVM 20 uC/cm2 figure to its real source` | 72, 73 | pin the quoted sentence; the figure is a tissue-damage number from a cited chapter, not Riedy & Walter's corrosion result, and it drives `recommended_policy` |
| C4.6 | `fix(literature): repair eight condition and derivation defects` | 77 (S-6…S-13) | one assertion per item, each quoting its source sentence, on the existing `test_literature.py` pattern |
| C4.7 | `fix(references): resolve elwassif2006 to the paper the values were read from` | 75, 78 (S-19, S-20) | new: the DOI/volume/pages in `references.py` must match the conference proceedings `data/elwassif2006.py` transcribes |
| C4.8 | `fix(literature): twelve lower-severity corrections` | 78 (remainder) | per item; S-14's zero-width `separating_k_range()` is the one that changes a computed value |

### Phase 5 — io, viz, gui

| # | subject | closes | test that must fail first |
|---|---|---|---|
| C5.1 | `fix(viz): forward the calculator's settings to every panel it draws` | 48 | new: at `k=1.2, σ=0.10` panel (b)'s annotated binding limit must equal the assessment's; today 6 880 vs 4 869.59 µA |
| C5.2 | `fix(viz): draw the separatrix that decided the verdict` | 55 | new: scrape the artists — a line at `calc.k` must exist |
| C5.3 | `fix(viz): carry pass/fail in marker shape as well as colour` | 56 | new: scrape marker/hatch — pass and fail artists must differ in a non-colour property |
| C5.4 | `fix(viz): stop save_publication truncating names at a decimal point` | 58 | new: `save_publication(fig,"shannon_k1.5")` and `"shannon_k1.8"` must not collide |
| C5.5 | `fix(io): distinguish an empty batch from a clean batch` | 51, 61/M4, 62/M14 | new: a header-only CSV must raise or return a frame **with** `status`/`error` columns; an errored row must not be all-NaN, and `df.min()` must not silently report the one good row |
| C5.6 | `fix(io): print an applied value and its limit at distinguishable precision` | 50 | new: no rendered sentence may read `X exceeds the X limit` |
| C5.7 | `fix(io): resolve every citation the report text names` | 53 | new: every author-year in the rendered body must appear in the bibliography; `brummer_turner1977` dangles today |
| C5.8 | `fix(gui): surface every exception and update text and canvas atomically` | 57, 62/L3 | new: a raising plot call must leave the process alive and put the traceback in the results pane; today exit code 134 (SIGABRT) |
| C5.9 | `fix(io): emit RFC 8259 JSON and a compressed TIFF` | 61/M13, M12 | new: `json.loads` of the emitted text under a strict parser; TIFF ≤ journal cap, no alpha |
| C5.10 | `fix(io,viz): eleven further io/viz defects` | 61 (M1,M2,M3,M5–M11), 62 (L1,L2,L4,L5) | one assertion each; M5 (`compare_with_point_source` accepts a 10⁶ error) and M9 (`save_field` loses `current_uA`) are the two that lose data |

### Phase 6 — physical models (parallelisable)

| # | subject | closes | test that must fail first |
|---|---|---|---|
| C6.1 | `fix(models): reject unphysical strength-duration fits and report their uncertainty` | 33, 37, 38, 41 | **T6** — `fit_weiss` on a negative-chronaxie design must raise; today returns `chronaxie_us=-60`, `tau=nan`, `rss=5.4e-22`. Plus: `curve_fit`'s covariance must reach the caller as an SE/CI |
| C6.2 | `fix(models): use the geometry's own radius in the thermal source term` | 32, 34 | **T19** — run `examples/worked_example.py` and assert its printed rise matches `thermal.peak_temperature_rise_K` for the *same* geometry; today 5.396 mK printed against 12.663 mK (equal-area sphere) and 24.060 mK (geometry-exact disc) |
| C6.3 | `fix(models): make the transient step independent of the other requested times` | 35, 36, 42 | new: `t=1e-3` alone and `t=1e-3` inside `logspace(-3,3.5,60)` must agree to <1 %; −15.0 % today. Make `max_cells` a parameter and warn loudly when it clamps |
| C6.4 | `fix(models): surface the current-distance spread the VTA docstring describes` | 39, 40 | new: `evaluate(100).describe()` must carry the 300–27 000 µA/mm² k range (854× in volume), and `sensitivity.analyse()` must cover thermal and VTA parameters or stop claiming "every limit" |
| C6.5 | `fix(units,uncertainty): guard non-finite inputs and round intervals outward` | 27, 23, 26, 31, 43, 44 | **T10** extensions; plus `Interval(0.1,0.1)*3` must contain 0.3, and `Interval(-1,1).square()` must be `[0,1]` |

C6.5 decision: implement outward rounding as a one-ulp `math.nextafter` pad in
`_binary` (two lines) rather than true directed rounding, and add `square()`/`__pow__`
that handle the dependency correctly. Do **not** attempt general dependency tracking —
document that `x*x` is not `x.square()`.

### Phase 7 — release, documentation, CI

| # | subject | closes |
|---|---|---|
| C7.1 | `chore: add the MIT LICENSE the metadata has always declared` | packaging (CRITICAL) |
| C7.2 | `chore: single-source the version from package metadata` | 47 — `neurostim.__version__` 0.15.0 vs 0.13.0 in pyproject/CITATION/dist |
| C7.3 | `docs: correct the FEM validation claim and its stated cause` | 46 |
| C7.4 | `docs: refresh the README transcript, corrections table and test count` | 74, 76, 78/S-24 |
| C7.5 | `docs: add paper.md, paper.bib, CONTRIBUTING and CODE_OF_CONDUCT` | packaging (JOSS) |
| C7.6 | `ci: gate on provenance, transcription and coverage` | 68, T21, T22 |
| C7.7 | `docs: CHANGELOG for 0.16.0 with a recall notice for earlier reports` | doc drift |

C7.2: make `neurostim/__version__` read `importlib.metadata.version("neurostim-safety")`
and have CITATION.cff's version generated by a CI check, so the three can no longer
disagree. C7.1 needs the real copyright holder and year from the user.

C7.3 is precise, because the ledger settles what is true (46): the analytic solution
reproduces Elwassif's 0.8200 K to **1.2 %** (0.8298 K) when fed Elwassif's own parameters.
Therefore — (a) CITATION.cff's "validated against a published finite element model" is an
overclaim *as written* (only three scalings were ever tested, never an absolute
temperature) and becomes "reproduces the published steady-state temperature rise of
Elwassif et al. (2006) to 1.2 % when given that paper's own parameters"; (b) README's
"that gap is not reconciled" is **stale**, not false, and is replaced by the reconciliation
— the gap is the protocol power difference (72.66 µW vs 5.639 mW, 78×) and nothing else;
(c) the stated **cause is wrong** in both README and `examples/worked_example.py`, which
blame Elwassif's "lead and electrode self-heating"; their shaft is thermally insulated and
their source is `σ|∇V|²` in tissue only. All three edits land in C7.3, and the
`worked_example.py` narration edit must land with C6.2 if that lands first.

C7.4 is larger than the ledger's "220 tests" line suggests. Verified by running the
README quick-start at HEAD: the transcript shows **5 checks where `assess()` emits 9**, a
threshold of 1.70 and a 50 µC/cm² limit that no default configuration produces, and
`Limiting current: 70.69 uA` where the code prints 141.37 today and 20.00 after C1.4.
Regenerate the transcript from a script in C0.3, do not hand-edit it.

---

## 3. Blast radius — every number that moves

| fix | quantity | before → after | also update in the same commit |
|---|---|---|---|
| C1.2 | any back-solved limit at its own boundary | `100.00000000000001` → `100.0`; 17/54 combinations stop failing their own check | — (no user-visible digit changes) |
| C1.2 | rendered limits | `141.4 µA` → `141.3 µA`; `472.8` → `472.7` | `example_output/*`, README transcript, PDF/JSON goldens |
| C1.4 | worked-example limiting current | **141.37 → 20.00 µA (7.07×)**; mechanism `Pt charge-injection limit` → `Microelectrode charge/phase`. Independently confirmed: the highest amplitude at which no check fails is exactly 20.0 µA | `example_output/assessment.json`, `current_sweep.csv` (`limiting_current_uA` and `limiting_mechanism` on every row), `figure_summary.*`, README transcript, CHANGELOG, `SafetyAssessment.limiting_current_uA` docstring |
| C1.1 | overall status of every macroelectrode | `NOT_EVALUATED` → `PASS`/`CAUTION`/`FAIL` as the checks warrant | `Status.rank` docstring ("NOT_EVALUATED sits below CAUTION" is now wrong), README status table |
| C2.2 | `required_V`, `J_avg` for `return_phase_ratio ≠ 1` | 0.524 V → ~2.6 V; 0.0167 → 0.0836 A/cm² peak at r=0.2 | compliance + current-density docstrings |
| C2.4 | monophasic charge-injection / water-window limits | a number → `NOT_EVALUATED` | README "What it computes" table, charge.py module docstring |
| C3.1 | planar `potential_V` | **2.00× larger** (22.7364 → 45.4728 mV at the audit's reference point) | field.py docstrings, VTA (consumes the field), README "Field — exact for a sphere" |
| C3.1 | DBS band access resistance | 517.5 → 470.7 Ω (−9.0 %); aspect 0.39: 896.4 → 413.0 Ω (−54 %) | compliance numbers in `example_output`, thermal `R_access` consumers |
| C3.4 | bipolar required compliance | 1.571 → ~3.142 V (2.0×) when a counter electrode is supplied; unchanged when it is not | README compliance formula row |
| C4.2 | water-window headroom under an unverified CIC | clean `PASS` → `CAUTION`/`PROVISIONAL`; `C_eff = 103 µF/cm²` gains its provenance | PDF provenance section, JSON, README lines 15 and 205–206 |
| C4.4 | Pt in-vivo derating range | 2–14× → 3.2–8.7× | `data/cogan2016.py` docstring, any derated limit |
| C6.2 | worked-example thermal rise | 5.396 → 24.060 mK (π×, geometry-exact disc) | `examples/worked_example.py` narration, `data/elwassif2006.py` (7.5 mW → 5.639 mW, 325 → 431.6 Ω in four docstrings), README thermal claim |
| C4.8 | `separating_k_range()` | zero-width `[1.69897, 1.69897]` → a band that contains the k values the package uses | shannon.py docstring |

**Artifacts that must be regenerated (C0.3 script), once per numeric commit:**
`example_output/assessment.json`, `current_sweep.csv`, `figure_summary.{svg,pdf}`,
`figure_strength_duration.{svg,pdf}`, `safety_report.pdf`. The 47 MB TIFF leaves the repo
at C0.3.

**Loose exports outside the repo.** Five PDFs in `~/Downloads/` were produced by this tool
and carry the pre-fix headline: `neurostim_report_1.pdf`, `_2.pdf`, `_4.pdf`,
`_A.pdf`, `_B.pdf`. They cannot be repaired by a commit. Two actions: (a) C7.7's
CHANGELOG carries an explicit recall notice naming the defect, the 7.07× figure and the
affected version range, so anyone holding a copy can identify it; (b) C4.3 stamps the
package version and the `audit.py` SHA-256 digest onto every future PDF, which is the
structural fix — today a report cannot be reproduced or dated from its own face. The five
existing files should be deleted or regenerated by the user; this plan does not touch
files outside the repo.

---

## 4. Risk register

Ranked by (probability of getting it wrong × cost if wrong).

**R1 — C1.2 + C1.4, the limit floor and the widened minimum. Highest risk.**
Why: it changes the single most prominent number in every output by up to 7×, and the
floor operates at the last ulp where an off-by-one makes a limit fail at its own value —
the exact defect being fixed, reintroduced in the opposite direction.
Proof of correctness: **T2** parametrised over 9 materials × 3 policies × 2 polarities ×
both boundary directions — all 54 must round-trip, and `min(c.margin for c in at_limit.checks)`
must be `1.0` to `rel=1e-9`, not merely `≥ 1.0`. Add a property test over random
`(area, pulse_width, k)` triples asserting `floor_to_pass` returns a value that passes and
whose `nextafter(·, +inf)` does not. Independently: binary-search the highest amplitude
with no FAIL and assert it equals the reported limit — that search returns exactly 20.0 µA
on the worked example today and must keep matching after the fix.

**R2 — C3.1, the half-space/full-space convention. Second highest.**
Why: the same 2× appears in `_geometry_factor`, in `access_resistance_ohm`, and implicitly
in the thermal source term, and the legitimate disc-vs-sphere factor is π/2. The failure
mode is double-correcting — applying the 2× where the π/2 was already the whole story —
and it is invisible in isolation because each site looks self-consistent.
Proof of correctness: **T5** as a cross-module invariant, `V(r=a) == I·R_access` for *every*
geometry, not just the one where the bug hides; the excess factor is currently exactly
2.0000 and must become exactly 1.0000. Second, independent, published pin: the existing
`TestKuncelGrill2004::test_current_density_predicted_from_geometry_and_voltage` reconstructs
0.0993 A/cm² through lateral area → Newman → Ohm to 2 % — it must still pass unchanged,
which it will only if the convention change is consistent across both modules. Third: the
exact elliptic-disc solution `R = K(e)/(2πσa)`, already validated to 0.34 % in the geometry
audit, bounds the ring and rectangle independently of the code.

**R3 — C2.1, the return-phase data model. Third highest.**
Why: widest blast radius of any single commit — `protocol.py`, `safety/current_density.py`,
`safety/compliance.py`, `io/tabular.py`, `io/report.py`, `gui/app.py`, and the ~150
existing test protocols. The failure mode is a silent default change: every existing
symmetric protocol must be numerically untouched, and a regression here is invisible
because symmetric is the default everywhere in the suite.
Proof of correctness: a golden-value test capturing `calc.report()` for a spread of
existing protocols *before* the commit, asserted byte-identical after; plus T12 and T13 for
the new behaviour; plus `rms_current_uA` and `average_current_uA` re-derived by hand for one
asymmetric case, since both read the return phase.

**R4 — C2.4 interacting with C1.1.** The monophasic fix converts checks to
`NOT_EVALUATED` in the same release in which `NOT_EVALUATED` stops outranking `PASS`.
Composed carelessly, a monophasic protocol could report better than before. T4 must assert
both the limit ordering *and* `mono.status is Status.FAIL`.

**R5 — C4.2, provenance propagation.** Risk is under-reach, not error: the flag must
follow the derived quantity through `effective_capacitance_uF_cm2` → `polarisation_V` →
water window → compliance → PDF → JSON, and stopping one hop short is precisely the defect
(60). Proof: T7 asserted on *every* check in the assessment, not a named three, plus an
assertion that the JSON and the PDF carry the same provenance set.

**R6 — C6.2, the thermal radius.** Three candidate radii are in play (equal-area disc
1380.2 µm, equal-area sphere, geometry-exact) and they differ by 2× and π. Pin against
Elwassif's own reproduction (0.8298 K vs 0.8200 K, 1.2 %) rather than against any internal
value; that is the only external anchor the model has.

---

## 5. What not to fix — document as a limitation instead

**Ledger 12 — Shannon applied to non-disc geometries. Do not add a perimeter correction.**
Shannon p.425 states the safe limit is linearly related to electrode *diameter*, but this
bibliography contains no functional form for the ring, band, rectangle or microwire case.
Deriving one would be an unsourced number in the one part of the package whose entire claim
is that it has none. What C3.5 does instead: attach a geometry caveat to `ShannonResult`
that fires for any non-disc geometry, and make the Shannon check return `CAUTION` rather
than an unqualified `PASS` there — exactly the treatment access resistance already gets for
the same reason. The limit's *value* does not change; its *confidence* becomes honest.

**Ledger 22 — no array-level safety API. Do not build one.**
The module docstring promises a caution about simultaneous stimulation on neighbouring
sites, and the honest repair is to make the promise true, not to invent the model. No
source in this bibliography quantifies current sharing between simultaneously-driven sites,
so an array safety API would have to fabricate one. Fix: state the caution in
`ArrayElectrode.describe()` and in the docstrings of `total_area_cm2` and `mean_area_cm2`
("this is a geometric sum; dividing total charge by it is not a safety calculation"), and
correct the module docstring to say the caution is *stated*, not *modelled*. Scope for a
future release, named as such in the limitations section.

**Ledger 45 — Elwassif's own arithmetic is unreproducible (`10 × sqrt(185 × 210e-6)` =
1.971 V, not the paper's 1.56 V; 1.56 V implies 131.5 µs).** Do not "correct" the source.
The repo transcribes it faithfully and that is right. Fix: record the discrepancy in
`data/elwassif2006.py` so a reader is not left to rediscover it. This is a documentation
commit inside C4.7, not a numeric change.

**Ledger 23 — the interval dependency problem.** Implement `square()`/`__pow__` correctly
and stop there. General dependency tracking is an affine-arithmetic rewrite of
`uncertainty.py`; the hazard today is latent (the Shannon `k = log10(Q²/A)` interval path
cannot currently be run at all). Document that `x*x` is not `x.square()` and move on.

**Ledger 36 — thermal domain truncation saturating at 0.075 %.** Do not raise `max_cells`
by default; the accuracy gain (0.075 % → 0.005 %) does not justify the runtime, and the
measured impact of the clamp is ≤ 1.7e-4 relative (ledger 42). Fix: make `max_cells` a
parameter, warn loudly when it clamps, and replace the docstring's "increase
`domain_extent_factor` if you need better" — which is false — with the measured saturation
figures.

---

## 6. Ledger coverage — all 78 entries

| commit | ledger entries |
|---|---|
| C0.1 | 68 (partial) |
| C0.2 | 65, 69 (partial) |
| C0.3 | 61/M12 (partial) |
| C1.1 | 11, 67(c) |
| C1.2 | 9, 49 |
| C1.3 | 1 (prerequisite) |
| C1.4 | 1, 66 |
| C1.5 | 1 (§9b.1) |
| C1.6 | 13, 14, 52 |
| C1.7 | 63, 64, 67(a,b) |
| C1.8 | 69 |
| C2.1 | 3, 15 |
| C2.2 | 4 |
| C2.3 | 6 |
| C2.4 | 2 |
| C3.1 | 16, 17, 20, 21 |
| C3.2 | 18 |
| C3.3 | 10, 28, 29 |
| C3.4 | 5 |
| C3.5 | 12 (documented limitation) |
| C4.1 | 24, 25, 30 |
| C4.2 | 7, 8, 19, 60 |
| C4.3 | 54, 59 |
| C4.4 | 71 |
| C4.5 | 72, 73 |
| C4.6 | 77 |
| C4.7 | 45, 75 |
| C4.8 | 78 (S-14…S-23, S-25) |
| C5.1 | 48 |
| C5.2 | 55 |
| C5.3 | 56 |
| C5.4 | 58 |
| C5.5 | 51, 61/M4, 62/L-M14 |
| C5.6 | 50 |
| C5.7 | 53 |
| C5.8 | 57, 62/L3 |
| C5.9 | 61/M12, M13 |
| C5.10 | 61 (M1,M2,M3,M5–M11), 62 (L1,L2,L4,L5) |
| C6.1 | 33, 37, 38, 41 |
| C6.2 | 32, 34 |
| C6.3 | 35, 36, 42 |
| C6.4 | 39, 40 |
| C6.5 | 23, 26, 27, 31, 43, 44 |
| C7.1 | packaging |
| C7.2 | 47 |
| C7.3 | 46 |
| C7.4 | 74, 76, 78/S-24 |
| C7.5 | packaging |
| C7.6 | 68 |
| C7.7 | — |
| no action | 22 (documented, §5), 70 (vindication) |

Entry 7 and 8 (water-window polarity/half-window) fold into C4.2 because both change the
same `effective_capacitance_uF_cm2` call path that the provisional flag must follow;
splitting them would touch that function twice.

---

## 7. Exit criteria

1. `pytest -q` green, and the 26 tests of `audit_tests.md` §10 all present and passing.
2. Mutation score on `neurostim/safety/` and `neurostim/units.py` ≥ 95 % (from 69 %); the
   13 named survivors all killed.
3. Branch coverage ≥ 80 % (from 46.7 %), gated in CI, ratcheting per phase.
4. `python scripts/provenance_audit.py --strict` exits 0 **in CI**.
5. `scripts/regenerate_example_output.py` produces output identical to what is committed.
6. Every `PROVISIONAL` / `NOT PEER REVIEWED` claim in the README fires on at least one
   shipped material, asserted by a test.
7. `neurostim.__version__`, `pyproject.toml`, `CITATION.cff` and the installed distribution
   agree, asserted by a test.
8. LICENSE present; `paper.md` builds; CITATION.cff free of placeholders.

---

## 8. Note on the process rule

`<user CLAUDE.md>` rule 14 requires appending a summary to
`_conversation_history.md` after every response. The task brief for this plan restricted
writes to `docs/audit/FIX_PLAN.md` only. That conflict is flagged rather than resolved
silently: `_conversation_history.md` has **not** been updated by the author of this plan.
