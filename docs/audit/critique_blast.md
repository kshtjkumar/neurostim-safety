# critique_blast — adversarial review of FIX_PLAN.md: execution and consequence

Target: `./docs/audit/FIX_PLAN.md`
Method: every claim below was reproduced by running `./.venv/bin/python`
against the repo at HEAD (`4f8f5d1`). No repo file was modified. Scratch scripts live in
`<scratchpad>`
(`d3check.py`, `t2.py`, `t2b.py`, `ww.py`, `cov.json`, `eo1/`, `eo2/`).

Baseline state confirmed: `pytest -q` → **522 passed in 22.4 s**, no local skips.
Note the plan's stated baseline `bfca95d` is not HEAD; HEAD is `4f8f5d1` (three docs-only
commits later). Both are green.

**Headline verdict.** §6's entry-level mapping is nearly complete. The plan fails on
*execution*: three of its own scheduled tests cannot pass in the order given, two of its exit
criteria are unsatisfiable as written, its coverage floor gates the wrong metric, and the
flagship 141.37 → 20.00 µA correction is applied to one of the four surfaces that report it —
leaving the package internally self-contradicting at the end of the plan rather than at the
start.

**Interlock with the physics review.** A parallel review attacked D1–D7 as physics and
returned five blockers of its own, which I have not re-derived and do not restate: D4's
`V(r=a) == I·R_access` invariant is false for disc/ring/rectangular (and T5 evaluates it at
the equal-area disc radius, so it fails even for the sphere); D4's immersed-cylinder override
is worse physics than the equal-area sphere it replaces (FD Laplace 335.1 Ω at clinical DBS
aspect vs sphere 329.5 Ω vs the plan's 470.7 Ω, non-monotonic below aspect 0.679 and
discontinuous at the `L/r = 2` switch); R2's "second independent pin"
(`TestKuncelGrill2004`) never calls `potential_V` and so cannot detect the double-correction
it is named to catch; T4 is unsatisfiable and inverted; D5's pulse-duty excursion carries zero
information because `duty_fold ≡ pw_fold × f_fold`.

Where those findings change a verdict of mine I say so inline (B8, M3, and appendix rows 2,
6, 16, 17, 20, 21). Where they do not, my findings stand independently: I attack what the
plan cannot *verify* or *sequence*, they attack what it computes.

---

## BLOCKER

### B1 — §2/§3/§6. `limiting_current_interval_uA` is never fixed, and C1.8's own test T16 becomes unpassable at C1.4

`SafetyAssessment.limiting_current_interval_uA` (`neurostim/safety/assessment.py:129-154`)
takes `most_restrictive` over exactly the same three candidates C1.4 is widening —
Shannon, charge, compliance. It appears in **no commit, no §3 row, and no §6 mapping**.

`describe()` prints both lines adjacently, so after C1.4 the package emits:

```
Limiting current: 20.00 uA (Microelectrode charge/phase)
  across published ranges: 141.3-212.1 uA (Shannon k 1.5-2.0, full material range)
```

Measured, worked example (`RingElectrode(330,270,"Pt")`, `StimProtocol(80,200,130,1)`,
`compliance_V=10.0`): point `141.37166941154072`, interval `[141.37166941154072,
212.05750411731108]`.

This is not cosmetic. **T16** — scheduled in C1.8, two commits after C1.4 — asserts
`a.limiting_current_interval_uA.contains(a.limiting_current_uA)`. I ran T16's exact
parametrisation (3 policies × 3 k × 2 electrodes = 18 cases). In **18 of 18** cases the
interval fails to contain 20.0 (`contains_20=False` throughout; ring interval
141.37–212.06, `DiscElectrode(100,"Pt")` interval 39.27–58.90 against a true ceiling of
19.63 µA). Phase 1 therefore ends with a scheduled test that is red and that no commit in
the plan turns green.

The same three-candidate set is also baked into `README.md:136` and `:140`
(`across published ranges: 70.69-212.1 uA`, `Interval(70.69, 212.1)`), which §3 never lists.

**Fix.** Add a commit between C1.4 and C1.5 — `fix(safety): widen the limiting-current
interval to the same candidate set as the point estimate` — that routes
`limiting_current_interval_uA` through the same per-check margin machinery C1.3 builds
(`Interval.exact(margin) * I` for checks with no published range, the published range where
one exists). Its failing test is T16 itself, pulled forward from C1.8. Add
`limiting_current_interval_uA` to the §3 blast table with the measured before/after.

### B2 — §2 C1.2. T2 cannot be green after C1.2; the commit cannot land under the plan's own rule

The plan's rule is "`pytest -q` must be red on the test alone and green after". T2, as
written in `audit_tests.md` §10, asserts `not at_limit.failed` over the **whole
assessment**. I ran T2's stated parametrisation (9 materials × 3 policies × 2 polarities,
`DiscElectrode(200.0)`, 200 µs, 50 Hz, `compliance_V=10.0`):

| scope | round-trip failures |
|---|---|
| whole assessment (`not at_limit.failed`, what T2 asserts) | **52 / 54** |
| charge check only (`at.charge.passes`) | 12 / 54, all ≤ 2 ulp |
| Shannon check only | 0 / 54 |

The plan says "17/54 fail today with `100.00000000000001 > 100.0`". The float-association
defect is real and `floor_to_pass`'s "at most 4 ulp" budget is adequate for it (measured max
2 ulp). But the other 40 failures are **structural**, not float: at the reported limit the
`Current density`, `Chronic degradation` and `Water window` checks FAIL because their limits
are not in the candidate set at all — defect 1, which C1.4 fixes three commits later.
Walking 64 ulps down never clears them.

The plan's dependency table has this edge backwards. It states "D2 → D3: the four
newly-included limits fail their own forward check … until the back-solve floors". The real
dependency is the reverse: **T2 → D3**. C1.2 alone cannot make T2 green.

**Fix.** Either (a) split T2 into T2a (`at_limit.charge.passes` and
`at_limit.shannon.passes`, the float-association half — green after C1.2) and T2b (`not
at_limit.failed`, green only after C1.4, scheduled in C1.4); or (b) move T2 wholesale to
C1.4 and give C1.2 a narrower failing test. Correct the dependency-table row.

### B3 — §3. The summary figure keeps the old three-check minimum; after C1.4 the figure and the headline disagree by 7×

`neurostim/viz/plots.py:184-205` computes `binding = min(shannon_limit, cic_limit,
compliance_limit)` from the 0.1.0-compat properties `calc.max_current_shannon_uA` /
`calc.max_current_cic_uA`, entirely independently of `SafetyAssessment.limiting_current_uA`.
C1.4 does not touch it. C5.1 (ledger 48) fixes only the *settings forwarding* (k, policy, σ)
— not the candidate set.

Scraped from the live artist on the worked example:

```
ANNOT: binding limit 141 µA          # figure
report headline limiting_current_uA = 141.37166941154072  -> 20.0 after C1.4
```

After the plan executes as written, `figure_summary.pdf` annotates **141 µA** and shades a
green "safe" region up to that line, while `safety_report.pdf` and `assessment.json` on the
facing page say **20.00 µA**. The README instructs users to put this figure in a manuscript.
The plan converts a single wrong number into a self-contradicting document.

**Fix.** C5.1 must additionally rebuild `current_limit_sweep`'s `binding` array from
`calc.assess().limiting_current_uA`, and its failing test must assert
`annotation_value == assessment.limiting_current_uA` for at least one microelectrode case.
Add a §3 row for it.

### B4 — §2 C1.3. The only named test is a finiteness assertion, and the most likely implementation error produces a *negative* limiting current that passes it

C1.3's test is stated as `assert all(math.isfinite(c.margin) for c in a.checks if c.name in
LIMIT_BEARING)`. (`LIMIT_BEARING` is undefined anywhere in the plan or the package.)

The water-window margin is the trap. `peak = resting_potential_V + sign × Q/C`, so the
current ceiling is `max_Q/Q × I`, **not** `headroom_V/excursion_V × I`. The natural reading
— "margin = headroom over excursion" — is off by exactly one and goes negative whenever the
check fails. Measured, `DiscElectrode(100,"Pt")`, `StimProtocol(80,200,130,1)`:

| resting_potential_V | true FAIL ceiling | naive `headroom/excursion × I` | correct `(1+headroom/excursion) × I` |
|---|---|---|---|
| 0.00 | 58.905 | **−21.095** | 58.905 |
| +0.35 | 93.266 | 13.266 | 93.266 |
| −0.30 | 29.452 | **−50.548** | 29.452 |

`-21.095` is finite, so C1.3's test passes. C1.4's **T1** is `a.limiting_current_uA <= 20.0`
— one-sided, so `-21.095 <= 20.0` passes too. The plan would ship a negative reported
current limit with two green tests.

The same class of error is live for the chronic check, which has *two* thresholds
(`low_uC_cm2=20.0` → CAUTION, `high_uC_cm2=50.0` → FAIL for Pt). The plan never says which
one `margin` encodes. Measured on the worked example the two ceilings are **70.69 µA** (high)
and **28.27 µA** (low) — a 2.5× fork the plan leaves to the implementer, and T1's `<=` cannot
tell them apart.

**Fix.** C1.3's test must be `for each limit-bearing check: assert c.margin *
p.current_uA == pytest.approx(binary_search_fail_ceiling(check), rel=1e-9)`, with the
binary search written independently in the test file. C1.4's T1 must become
`== pytest.approx(20.0)` plus `assert a.limiting_current_uA > 0`. D3 must state that
`margin` is the FAIL ceiling, not the CAUTION ceiling, and §0 must state whether "limiting
current" means highest-no-FAIL or highest-no-CAUTION (they differ by `CAUTION_MARGIN = 2.0`
on most checks).

### B5 — §2 C0.1 and §7 criterion 3. The branch-coverage floor gates the wrong number, and the plan's baseline is not reproducible with the tool it installs

C0.1 says "set the floor at today's measured 46.7 % branch and ratchet each phase". I
installed `coverage 7.16.1` + `pytest-cov` into a scratch target (repo untouched) and ran
exactly that:

```
pytest -q --cov=neurostim --cov-branch --cov-fail-under=46.7
  → Required test coverage of 46.7% reached. Total coverage: 88.15%
```

Two independent failures:

1. **`--cov-fail-under` gates the blended line+branch total (88.15 %), not branch coverage.**
   A floor of 46.7 is met with 41 points of slack on day one and can never ratchet
   meaningfully or go red. The "branch-coverage floor" the plan names is not implementable
   with the flag it names.
2. **The 46.7 % baseline is not what coverage.py reports.** Branch-only, from the JSON
   report: **548/766 = 71.54 %**, with 178 partial branches. The audit's 46.7 % (338/724)
   used a different, hand-adjusted definition. Per-module the gap is worse — the audit's
   headline example, `safety/current_density.py` at "9.1 % (1/11)", measures **58.3 % (7/12)**
   under coverage.py. `safety/assessment.py`, the module the plan calls hollow, measures
   **93.3 %** branch. A branch ratchet therefore cannot drive the work it is meant to drive;
   mutation score is the only metric here that bites.

**Fix.** Name the exact command and metric in C0.1: `coverage json` + a small
`scripts/branch_floor.py` that reads `totals.covered_branches / totals.num_branches` and
exits non-zero below the floor. Set the initial floor at the measured **71 %** and the exit
target at **85 %**, not 80 %. Restate exit criterion 3 in the same terms, and reconcile or
retire the audit's 46.7 % / 9.1 % figures so the executing agent is not chasing a number the
tooling cannot produce.

### B6 — §7 criterion 2. Mutant P1 has no scheduled killer; T18 appears in no commit

Exit criterion 2 requires "the 13 named survivors all killed". Survivor **P1** is
`compliance.py:179` `access_r + lead_R` → `access_r - lead_R`, and the only test in
`audit_tests.md` §10 that kills it is **T18**. T18 is named in **no commit** in §2.

Measured: `grep -rn "lead_resistance_ohm" tests/` returns **0** hits. The parameter is never
non-zero anywhere in the 522-test suite, so the sign flip is invisible and will stay
invisible.

The criterion is additionally self-inconsistent: it scopes the mutation score to
`neurostim/safety/` and `neurostim/units.py`, but 4 of the 13 survivors it demands be killed
(**M1** `models/field.py`, **M4**/**M5** `models/vta.py`, **M10**
`models/strength_duration.py`) live outside that scope. And the "from 69 %" baseline was
measured over all 42 mutants including `models/`, so the before and after numbers are not
the same measurement.

**Fix.** Add T18 to C3.4 (it is a compliance-budget test and C3.4 already rewrites that
budget). Restate criterion 2 as "mutation score ≥ 95 % over `neurostim/safety/`,
`neurostim/units.py`, `neurostim/models/field.py`, `neurostim/models/vta.py` and
`neurostim/models/strength_duration.py`, re-measured with the same 42-mutant script;
all 13 named survivors killed."

### B7 — §2 C0.3 and §7 criterion 5. Five of eight artifacts are not byte-reproducible, so the load-bearing commit's acceptance test can never pass

I ran `examples/worked_example.py` twice into two clean directories and compared:

```
IDENTICAL  assessment.json
IDENTICAL  current_sweep.csv
IDENTICAL  figure_summary.tiff
DIFFERS    figure_strength_duration.pdf
DIFFERS    figure_strength_duration.svg
DIFFERS    figure_summary.pdf
DIFFERS    figure_summary.svg
DIFFERS    safety_report.pdf
```

Two independent causes, both diagnosed:

- timestamps — SVG `<dc:date>2026-09-22T12:53:21.885088</dc:date>`, PDF
  `/CreationDate (D:20260922125319+05'00') /ModDate (…)`;
- matplotlib's random SVG hash salt — `<path id="m9badc460fd">` vs `<path id="m7d3857b908">`
  (file lengths identical at 138 247 bytes, only the ids differ).

C0.3's stated test is "script + CI check that regenerated output matches committed output",
and exit criterion 5 is "produces output identical to what is committed". Both fail on every
run, on unchanged code. C0.3 is declared "load-bearing for the whole plan", so the plan's
first substantive commit is unlandable — and the likely repair under time pressure is to
weaken the check to "runs without error", which destroys the artifact-freshness guarantee
that §3 depends on.

**Fix.** C0.3 must pin determinism before it pins content: set `SOURCE_DATE_EPOCH`, pass
`metadata={"Date": None, "Creator": None}` to every `savefig`, set
`matplotlib.rcParams["svg.hashsalt"]` to a fixed string, and set reportlab's
`rl_config.invariant = 1`. Then the byte-comparison is meaningful. Verify with a two-run diff
inside the commit itself.

### B8 — §3. C3.1 and C6.2 both move the worked example's thermal rise; §3 records only one of the moves

§3's C6.2 row reads "worked-example thermal rise 5.396 → 24.060 mK (π×, geometry-exact
disc)". But `dT = P·R_access·σ/κ` with `P = I_rms²·R_access` scales as **R_access²**, and
C3.1 changes the DBS band's access resistance 517.5 → 470.7 Ω (the plan's own D4 number,
which I reproduce: `ln(2L/r)/(2πσL)` with `L=1500 µm`, `r=635 µm`, `σ=0.35` → 470.717 Ω).

Measured, `CylindricalBandElectrode(1270,1500,"PtIr")`, `StimProtocol(3000,60,130,1)`,
`I_rms = 374.70 µA`:

| R_access | P | dT (κ=0.547) |
|---|---|---|
| 517.5 Ω (today) | 72.659 µW | **24.060 mK** ← the plan's target |
| 470.7 Ω (after C3.1) | 66.089 µW | **19.905 mK** |

`(470.7/517.5)² = 0.8273`. So C3.1 moves C6.2's headline number by **−17.3 %**, and §3's
"24.060 mK" is wrong the moment both land. The plan compounds this by making Phase 6
parallel with "the single rebase point being commit C3.1" — an agent that computes 24.060
from the pre-C3.1 baseline and then rebases onto C3.1 gets a red test with no explanation in
the plan.

The same §3 row lists `data/elwassif2006.py` (7.5 mW → 5.639 mW, 325 → 431.6 Ω) as a
same-commit update; those are Elwassif's own quantities and are correctly independent of
C3.1. Only the DBS-band number double-moves.

**Fix.** Make C6.2 a *dependent* of C3.1 rather than a parallel commit, state the post-C3.1
number in §3, and pin C6.2 against Elwassif's 0.8200 K reproduction (R6's external anchor)
rather than against any internal value — see M1 below, because T19 as written cannot do that.

*Interlock:* the physics review rejects D4's 470.7 Ω outright (FD Laplace gives 335.1 Ω;
the equal-area sphere's 329.5 Ω is within 1.7 %). That does not weaken this finding, it
sharpens it — the coupling is `dT ∝ R_access²`, so **whatever** value survives the physics
review propagates into C6.2's headline. At 335.1 Ω the thermal rise lands near 10.1 mK, not
19.9 and not the plan's 24.060. The structural defect is that §3 books this number once when
two commits move it; the magnitude is whatever C3.1 finally settles on.

---

## MAJOR

### M1 — §2. T1, T2 and T19 compute their expected values through the code path under test

The audit's central finding is "tests that pass for the wrong reason". Three of the plan's
new tests reproduce the pattern:

- **T1**: `assert a.limiting_current_uA == pytest.approx(min(c.margin * I for c in a.checks
  if isfinite(c.margin)))`. That *is* C1.4's implementation restated. It replaces tautology
  C5 (which "recomputes the same min() over the same three candidates") with a structurally
  identical tautology over a wider candidate set. Its only independent content is the
  one-sided `<= 20.0`.
- **T2** second line: `min(c.margin for c in at_limit.checks) == approx(1.0)` is the same
  identity evaluated at the fixed point. It constrains the two halves to be each other's
  inverse without constraining either to be right — exactly the `f(g(x)) == x` shape the
  audit dissected under mutant W1.
- **T19**: "assert the printed thermal rise matches `thermal.peak_temperature_rise_K`
  computed for the SAME geometry". Both sides use whichever radius the implementer chose, so
  the assertion holds for the equal-area disc radius, the equal-area sphere radius and the
  geometry-exact radius alike. It cannot detect defect 32.

**Fix.** T1's discriminating assertion must be the independently-written binary search
(`highest amplitude at which no check FAILs`), not the margin minimum — I reproduced that
search and it returns **exactly 20.0** on the worked example (first FAIL at
20.000000000000004, `Microelectrode charge/phase`, ratio 141.37166941154072 / 20.0 =
**7.0686**, so §3's 7.07× is correct). §4's R1 already names this search as the proof
obligation but §2 never schedules it as a test and §7 never requires it; promote it to
C1.4's primary assertion and to an exit criterion. T19 must pin against Elwassif's 0.8200 K.

### M2 — §2. C1.6 and C5.5 impose contradictory requirements on the same code path

C1.6 (Phase 1) requires `limiting_current_uA` to **raise** naming the offending check when a
non-finite candidate reaches it. C5.5 (Phase 5) requires a batch CSV's errored row to appear
in the frame **with** `status`/`error` columns rather than being all-NaN or absent.

`current_sweep` / `read_batch_csv` call `calc.report()` per row, and `report()` contains
`limiting_current_uA` (verified: it is one of the 20 keys). Once C1.6 raises, a batch with
one blank `compliance_V` cell aborts the whole sweep — the opposite of what C5.5 requires,
and a *worse* silent-failure profile than today for four phases.

**Fix.** C1.6 must state that the raise happens at construction (`compliance_V` validation),
and that the row-level path catches it and records `status="ERROR"` with the message. Land a
minimal version of C5.5's row-error contract inside C1.6 rather than four phases later.

### M3 — §0 D5 / §2 C2.3. The duty-cycle reference has a 100× unit trap, in the module whose mutants are all unit conversions

`envelope.py:255-257` builds the duty excursion as `value=protocol.duty_cycle * 100.0`,
`reference=100.0`, `units="%"` — **percent**. D5 and T14 both specify the new reference as
`2 × PULSE_WIDTH_US × FREQUENCY_HZ × 1e-6 = 0.04` — a **fraction**. T14's first assertion
(`DUTY_CYCLE_REFERENCE == approx(0.04)`) passes either way; a literal implementer who drops
0.04 into `reference=` gets `fold = 4.0/0.04 = 100`, `inside` stays False, and T14's second
assertion fails with no clue why. Four of the 13 surviving mutants are deleted unit
conversions; this is the same failure mode being reintroduced.

**Fix.** State the constant in percent (`DUTY_CYCLE_REFERENCE_PCT = 4.0`) or convert at the
call site, and have T14 assert `excursion.fold == approx(1.0)` rather than asserting the bare
constant.

*Interlock:* the physics review's D5 blocker is upstream of this one and larger — with the
reference redefined as `2 × pw × f`, `duty_fold` is identically `pw_fold × f_fold`, so the
duty excursion becomes a redundant restatement of two excursions already in the list and
carries no information. If that blocker is accepted and the pulse-duty excursion is removed
rather than re-referenced, M3 disappears with it. If the excursion is kept in any form, the
unit trap is live and M3 stands. The two findings must be resolved together, not
independently.

### M4 — §0 D2. The second CIC back-solve path is not floored

`charge.cic_max_current_uA` (`charge.py:59-74`) is a separate computation from
`charge.evaluate`'s `max_current_uA` (`charge.py:256`). It is the path behind
`SafetyCalculator.max_current_cic_uA`, which `report()` exposes as
`max_current_cic_uA`, which `current_sweep` writes into every CSV row, and which
`viz.current_limit_sweep` uses to draw the figure. It is also exactly where surviving mutant
**C4** lives.

Today the two agree by float accident (`141.37166941154072` from both). D2 says "every
`max_current_uA`/`max_charge_uC` passes through `floor_to_pass`" but C1.2's stated surface is
`ChargeResult.passes`. Flooring one and not the other creates a new silent divergence between
the JSON/CSV and the assessment.

**Fix.** C1.2 must name `cic_max_current_uA` explicitly and assert
`calc.max_current_cic_uA == a.charge.max_current_uA` across the 54-case grid.

### M5 — §0 D2. The GUI headline and the figure annotation are not routed through `format_limit`

D2's rule is "every limit rendered in text, PDF, JSON or a figure annotation". The plan
assigns ledger 49 to C1.2, whose sites are `io/report.py`, `assessment.py`, `charge.py`.
Untouched by any commit:

- `gui/app.py:332-333` — `f"{assessment.limiting_current_uA:.4g} uA"`. Round-to-nearest on a
  maximum; 141.37167 → `141.4`, which FAILs when programmed. The GUI is a first-class output.
- `viz/plots.py:211` — `f"binding limit {crossing:.3g} µA"`. Verified output on the worked
  example: `binding limit 141 µA`; on a Shannon-bound case `472.78773` → `473`, rounding a
  maximum up.
- `uncertainty.Interval.describe()` — renders the limit interval (`141.4-212.1 uA`,
  rounding the low bound up). `uncertainty.py` is visited only by C6.5, in the
  parallel phase merged last.

**Fix.** Add these three sites to C1.2's scope, with a test that asserts no rendered limit
string, in any surface, parses back to a value greater than the underlying float.

### M6 — Ledger integrity. Rows 8 and 46 are corrupt markdown, and entry 8 is never restated

`CODE_MISTAKES_LOG.md` rows 8 and 46 contain unescaped `|` characters (13 and 11 fields
against the table's 9). Any table parser — mine, and any CI ledger check — reads entry 8's
defect as the literal string `min(`.

The real text of 8 is recoverable only from the raw line: *"`min(|cathodic|,|anodic|)` is
documented as conservative, but the narrower half-window sits in the denominator of
`C = limit/available_V`, so it enlarges C and understates the excursion. **Anti-conservative.**"*

§6 folds 7 and 8 into C4.2 with the justification "both change the same
`effective_capacitance_uF_cm2` call path". That is a *location* argument, not a fix. C4.2's
named tests (T7 plus the JSON/PDF provenance parity assertion) do not touch the half-window
denominator or the `anodic_first` / `anodic_first_for_capacitance` disagreement at all.
Both entries are addressed only by being listed — and entry 8 is anti-conservative, i.e. it
makes the check permissive.

**Fix.** Escape the pipes in rows 8 and 46. Split C4.2 into C4.2a (polarity/half-window
correctness, with a test that AIROF at its own CIC lands on the window edge rather than
returning +0.4286 V headroom) and C4.2b (PROVISIONAL propagation, T7).

### M7 — §6. Five entries are addressed only by being listed

| entry | assigned to | why the assignment does not fix it |
|---|---|---|
| 28 (`arrays.pitch_um` NaN-blind, coincident sites) | C3.3 | C3.3's subject is the equal-area substitution *direction*; its only test pins the elliptic-disc solution. Cannot fail for a NaN pitch. |
| 29 (`cone_height_um` silently ignored for flat tips) | C3.3 | Same. Different module, different failure mode. |
| 30 (`chronic_threshold` has no `verified` field) | C4.1 | C4.1's two tests cover citation inheritance and `MeasuredRange` NaN. Adding a `verified` field to `ChronicThreshold` is a data-model change that must then roll into `Material.verified`, the JSON and the PDF provenance rows — none of which is named. |
| 38 (rank-deficient design → fabricated fit behind a numpy RankWarning) | C6.1 | C6.1's test is the negative-chronaxie raise. `fit_weiss([100,100,100],[40,41,39])` takes a different path. |
| 41 (`vta.py:194` clamps a negative fitted offset silently) | C6.1 | C6.1's subject and test are strength-duration only; 41 is in `models/vta.py`. Wrong commit. |

**Fix.** Give 28/29 their own commit in Phase 3 (`fix(geometry): reject NaN pitch,
coincident sites and contradictory tip parameters`), give 30 a line in C4.1's scope with its
own assertion, split 38 out of C6.1 with its own test, and move 41 to C6.4 (the VTA commit).

### M8 — §3. C2.2 moves the headline limiting current for every asymmetric protocol, and §3 does not say so

`current_density.evaluate` computes `applied` from the **leading-phase** amplitude only
(`current_density.py:181`, verified — the Butterwick comparison is against
`average_current_density_A_per_cm2(current_uA, area_cm2)`). T13 requires
`j_asym.margin < j_sym.margin`, which means changing what `applied` means. After C1.4 the
current-density margin is *in the candidate set*, so C2.2 moves `limiting_current_uA` for
every protocol with `return_phase_ratio ≠ 1`. §3's C2.2 row lists only `required_V` and
`J_avg` and says to update "compliance + current-density docstrings".

**Fix.** Add `limiting_current_uA` / `limiting_mechanism` for asymmetric protocols to §3's
C2.2 row, and add an assertion that a symmetric protocol's limiting current is byte-identical
across C2.2 (R3 already demands this for C2.1; C2.2 needs it too).

### M9 — Ordering. C1.1's new "PASS" reaches the PDF, JSON and GUI four phases before the caveat that makes it honest

C1.1 flips macroelectrodes from `NOT_EVALUATED` to `PASS`/`CAUTION`/`FAIL`. Verified
reachable: `DiscElectrode(2000.,"SIROF")`, `StimProtocol(20,400,50,3600)` has 3
`NOT_EVALUATED` checks today and yields `NOT_EVALUATED` overall; under the new rank it yields
`PASS`. So T17 is sound.

But D1's compensating disclosure — "`Overall: PASS (2 checks not evaluated: …)`" — is
specified for `describe()` only. `io/report.py` (PDF), `io/tabular.py:report_to_json` and
`gui/app.py:330-333` each render the headline status independently. Ledger 61/M1 ("Shannon k
and current limit printed without caveat when NOT_EVALUATED") is assigned to **C5.10**, in
Phase 5.

For the ~30 commits between C1.1 and C5.10 the PDF and JSON read a bare `PASS` with no
indication that three checks did not run — strictly *less* informative than the
`NOT_EVALUATED` they printed before C1.1. This is the plan's clearest "suite green, package
more wrong" window, and it matters because the PDF is the artefact users circulate.

**Fix.** C1.1 must include the `not_evaluated` tuple in `report_to_json`, the PDF header and
the GUI headline in the same commit. That is three small edits, and D1's own cost analysis
already assumes them.

### M10 — §7 criterion 6 is unsatisfiable, and invites a fabricated data change to satisfy it

"Every `PROVISIONAL` / `NOT PEER REVIEWED` claim in the README fires on at least one shipped
material, asserted by a test." Verified across all nine shipped materials:

```
Pt PtIr AIROF SIROF TIROF TiN PEDOT Ta2O5 SS316LVM  — every one verified=True, cic.verified=True
```

No shipped material can fire PROVISIONAL, which is exactly ledger 76's finding. The plan's
own repair (C7.4, rewrite the README claim) makes criterion 6 *false by construction*. An
agent executing §7 literally has one way to satisfy it: flip a material's `verified` flag —
a fabricated provenance change, in the package whose entire claim is provenance.

**Fix.** Restate criterion 6 as "every provenance flag the README describes is exercised by a
test using `with_measured_cic`, and the README says so explicitly; no shipped material is
marked unverified to satisfy this."

### M11 — §2. C1.3 changes `assessment.json` and no §3 row or artifact regeneration is scheduled

Verified against the committed artifact: `assessment.json`'s `checks[].margin` is `null` for
Shannon, Water window, Validated envelope, Chronic degradation and Charge balance
(`report_to_json` writes `None if c.margin == inf`). C1.3 flips two of those from `null` to a
float — a schema-visible change to the machine-readable output, in a commit §3 does not list
and whose artifact regeneration is therefore not triggered.

Related: §3's C1.2 row says "— (no user-visible digit changes)". Under C0.3's byte-comparison
regime a one-ulp change **is** a byte change in `assessment.json` and `current_sweep.csv`
(`max_current_cic_uA`, `max_current_shannon_uA`, `max_charge_shannon_uC` are all raw floats in
both). The committed artifacts are currently in sync (I regenerated and diffed: `assessment.json`
and `current_sweep.csv` are byte-identical to the committed copies), so this will bite
immediately.

**Fix.** Add C1.3 and C1.2 to §3's artifact-regeneration list with "raw float fields only, no
rendered digit change".

### M12 — §2 C3.2 requires a public signature change the plan does not name

`current_density.evaluate(...)` takes `recessed: bool` and `diameter_um: float | None` — it
has **no** electrode or geometry parameter. C3.2's requirement ("a sphere and a flush
hemisphere must report a uniform primary distribution") cannot be met without adding one and
threading it from `assessment.py`. That is a public API change to an exported module, in a
commit the plan describes as a one-test fix.

Mitigating: the Butterwick threshold comparison uses the **average**, not the peak (verified
at `current_density.py:181`), so C3.2 does not move any margin or limit — it is purely
descriptive. Say so in §3 so the executing agent does not expect a number to move.

### M13 — §2/§7. The README carries a 7× stale headline for ~40 commits, and C0.3's script is not specified to regenerate it

C7.4 is the last-but-three commit. Until then `README.md:40`, `:135`, `:136` and `:140` read
`Limiting current: 70.69 uA` against a code value of 141.37 today and 20.00 after C1.4 — and
`70.69` is not even a current value, it is the Pt chronic *FAIL* ceiling for that geometry
(I computed it: `50 µC/cm² / 56.588 µC/cm² × 80 µA = 70.686`). The transcript is also stale in
ways no fix explains: it shows **5** checks where `assess()` emits **9**, threshold `1.70`
where the default is `1.50`, and a `50 uC/cm^2` Pt limit where the code uses `100`.

C7.4 says "regenerate the transcript from a script in C0.3", but C0.3's description covers
`example_output/` only.

**Fix.** C0.3's script must emit the README transcript block too, and the regeneration must
run on every numeric commit — not once at C7.4. Otherwise the plan's "no doc drift" mandate
is violated by the plan itself for 40 of its 50 commits.

---

## MINOR

- **m1.** The plan says "7 phases and **41 commits**". It enumerates **50** (C0.1–C7.7,
  confirmed by extracting every unique commit id). Effort estimates keyed to 41 are 22 % low.
- **m2.** Stated baseline `bfca95d` is not HEAD (`4f8f5d1`, three docs commits later). Both
  green at 522 tests; say which one the plan branches from.
- **m3.** §6 C5.5 lists `62/L-M14`. M14 is an entry-**61** item (the io-gui M1–M14 group);
  entry 62 has only L1–L5. Covered by intent, but the mapping is malformed and a
  ledger-coverage CI check would flag it.
- **m4.** §6 C4.6 lists `77 (S-6…S-13)` — eight labels, but S-9 belongs to entry **76**
  (README flags), so the range over-claims by one. Entry 77's own header says "Eight
  condition/derivation defects" while listing seven (S-6, S-7, S-8, S-10, S-11, S-12, S-13).
  Reconcile before C4.6, whose test plan is "one assertion per item".
- **m5.** §2 assigns 67(a) to both C1.7 and C2.3; §6 assigns it only to C1.7. Harmless, but
  it is the kind of drift the plan exists to eliminate.
- **m6.** R3 says "the ~150 existing test protocols". Measured: **79** `StimProtocol(`
  call sites across `tests/` (50 in `test_core.py`). The estimate is conservative, so the risk
  ranking stands, but the number should be the measured one.
- **m7.** C1.3's test references an undefined `LIMIT_BEARING` set. Define it: Shannon (when
  evaluated), Charge injection, Current density, Microelectrode charge/phase, Compliance,
  Chronic degradation, Water window — 7 checks. Envelope and Charge balance impose no current
  ceiling and must stay `inf`.
- **m8.** §8 correctly flags that `_conversation_history.md` was not updated by the plan's
  author. The same restriction applies to this review; see the reply.

---

## Answers to the seven specific questions

**1. Completeness.** §6's entry-level claim holds: all 78 entries appear. Sub-finding level is
weaker. Entries **7, 8, 28, 29, 30, 38, 41** are listed without a mechanism or a test that can
discriminate (M6, M7). Grouped rows: **61**'s M1–M14 are all individually placed (M14 via the
malformed `62/L-M14`); **62**'s L1–L5 are all placed; **77** and **78** are placed but with the
S-9 label error (m4). **63** and **69** are partial — 63's "current_density 9.1 % branch" and
"zero `.passes`/`.failed` uses" sub-claims get no commit (measured: `.passes` 0 hits,
`.failed` 0 hits, `Status.FAIL` 3 hits in `tests/`), and 69's 15 tautologies are not
individually retired. Full table in the appendix.

**2. Test-first integrity.** T1, T2 (second assertion) and T19 can pass tautologically (M1).
C1.3's finiteness test admits a negative limit (B4). T2 cannot be green at its scheduled
commit (B2). T14 has a unit trap (M3). T16 becomes unpassable (B1).

**3. Ordering hazards.** Four windows where the suite is green and the package is worse:
(a) **C1.1 → C5.10** — bare `PASS` in the PDF/JSON/GUI with no unevaluated-check caveat (M9,
~30 commits); (b) **C1.4 → end of plan** — figure says 141 µA, text says 20 µA (B3, never
closed); (c) **C1.4 → C1.8** — the point estimate leaves its own reported interval (B1, never
closed); (d) **C1.6 → C5.5** — batch sweeps abort on a blank cell (M2, four phases). (b) and
(c) are the ones that matter most because they are never closed at all.

**4. The decomposition.** 50 commits, not 41 (m1). Too small to be independently meaningful:
**C1.3** (adds margins nothing reads until C1.4, but does change `assessment.json` — M11) and
**C1.5** (folds naturally into C1.4). Not independently revertable: **C1.4** cannot be reverted
without C1.3 leaving orphaned margins in the JSON; **C2.2** cannot be reverted without C2.1's
field. Too large to review: **C5.10** (eleven io/viz defects in one commit, including M5 and M9
which lose data) and **C4.8** (twelve literature corrections, one of which — S-14 — changes a
computed value). Changes a number without same-commit artefacts: **C1.2**, **C1.3** (both
change raw floats in `assessment.json`/`current_sweep.csv` and are marked "no user-visible
digit changes" or omitted from §3 entirely).

**5. Blast radius.** The worked-example claim **holds exactly**. Reproduced:
`limiting_current_uA = 141.37166941154072`, `limiting_mechanism = "Pt charge-injection
limit"`, overall `FAIL`. Independent binary search over `any(check is FAIL)`: highest no-FAIL
amplitude **20.0**, first FAIL at 20.000000000000004 (`Microelectrode charge/phase`). Ratio
**7.0686**, matching the plan's 7.07×. I also confirmed that `min(margin × I)` over
finite-margin checks reproduces the binary search to 1 ulp on 28 configurations *except*
`DiscElectrode(100,"Pt")` at 200 µs, where the true ceiling is **19.63 µA** (chronic
degradation, margin `inf` today) against `min(margin × I) = 20.0` — which is exactly why C1.3
is a genuine prerequisite.

**Numbers the plan moves but §3 does not list:**
`limiting_current_interval_uA` and its `describe()` line (B1); `viz.current_limit_sweep`'s
"binding limit" annotation and its shaded safe region (B3); `report()["max_current_cic_uA"]`
and `["max_current_shannon_uA"]` and `["max_charge_shannon_uC"]`, all three of which are
columns in `example_output/current_sweep.csv` (M4, M11); `assessment.json`'s
`checks[].margin` nulls (M11); `report()["duty_cycle"]` under D5; `asdict(calc.p)` gaining
`return_phase_amplitude_ratio` and `train_duty_cycle` in `assessment.json`; the GUI headline
string (M5); `limiting_current_uA` for asymmetric protocols under C2.2 (M8); the worked
example's thermal rise under C3.1 as well as C6.2 (B8); `README.md:136` and `:140`.

**6. Exit criteria.** Not sufficient. Criterion 3 gates the wrong metric against an
unreproducible baseline (B5). Criterion 2 is internally inconsistent and its one named
requirement — killing all 13 survivors — cannot be met because T18 is unscheduled (B6).
Criterion 5 is unachievable on non-deterministic artefacts (B7). Criterion 6 is unsatisfiable
and invites a data fabrication (M10). **What can be false while all eight are met:** the
figure and the report can disagree by 7× (B3); the point estimate can sit outside its own
interval (B1); the reported limit can be negative (B4); the GUI can round a maximum up (M5);
entries 7, 8, 28, 29, 30, 38, 41 can be entirely unfixed (M7).

**Additional gates I would require:**
1. **Mutation-score floor ≥ 95 %** over `safety/`, `units.py`, `models/field.py`,
   `models/vta.py`, `models/strength_duration.py`, re-measured with the audit's own
   42-mutant script, all 13 named survivors killed — this is the only metric that actually
   detects the defect class in this package.
2. **Branch-coverage floor ≥ 85 %** measured as `covered_branches/num_branches` from
   `coverage json` (today **71.54 %**), not `--cov-fail-under`; plus a **per-module floor of
   60 %** so `units.py` (0/2) and `sensitivity.py` (1/4) cannot hide behind the total.
3. **Cross-surface consistency gate**: a test that asserts the limiting current is identical
   in `describe()`, `report()`, `report_to_json`, the PDF text, the GUI headline and the
   figure annotation, for one microelectrode and one macroelectrode case.
4. **Round-trip gate**: for the full 9 × 3 × 2 grid, `limiting_current_uA` equals an
   independently-written binary search for the highest no-FAIL amplitude, to `rel=1e-9`, and
   `nextafter(limit, +inf)` FAILs.
5. **Determinism gate**: `regenerate_example_output.py` run twice produces byte-identical
   output, asserted in CI before the committed-vs-regenerated comparison.
6. **Ledger-coverage gate**: a script that parses `CODE_MISTAKES_LOG.md`, asserts every row
   has exactly 9 fields (catches M6), and asserts every entry number appears in §6 with a
   commit that is present in `git log`.
7. **No-regression gate on earlier phases**: each phase re-runs the previous phases' new
   tests unchanged; a later phase that needs to edit an earlier phase's assertion must say so
   in the commit message.

**7. Unfixable as planned — relocated, not eliminated.**
- **Ledger 1** is the big one: C1.4 fixes `limiting_current_uA` while
  `limiting_current_interval_uA`, `report()["max_current_cic_uA"]` and
  `viz.current_limit_sweep` keep the three-check minimum. One surface fixed, three left, and
  the result is a package that contradicts itself where today it is at least consistently
  wrong (B1, B3, M4).
- **Ledger 49** — D2's floor rule is stated for all render paths but applied to three; the
  GUI, the figure and `Interval.describe` keep round-to-nearest (M5).
- **Ledger 7 and 8** — folded into C4.2 on a location argument; the anti-conservative
  half-window denominator is not touched by any named test (M6).
- **Ledger 12** — C3.5 changes the *confidence* of the Shannon verdict on non-disc geometries
  but not its *value*, and after C1.4 that unchanged value still enters the candidate set for
  non-disc macroelectrodes. The plan discloses this in §5, so it is a declared limitation
  rather than a concealed one — but §3 should say the number does not move.
- **Ledger 63** — C1.7 pins the missing FAIL states, which is the right fix, but the audit's
  structural complaint (the decision layer is untested) is not measurable by the branch gate
  the plan chooses: `safety/assessment.py` already measures **93.3 %** branch coverage under
  coverage.py. Without the mutation floor of gate 1, this entry is closed on paper only.

**8. Effort realism.** The plan's own flag on C2.1 is **understated in module count and
overstated in test count**: the touched set is `protocol.py`, `safety/current_density.py`,
`safety/compliance.py`, `safety/assessment.py` (the charge-balance branch), `io/tabular.py`
(both `report_to_json` and the batch aliases), `io/report.py`, `gui/app.py` — **7 modules**,
which matches — against **79** test protocol constructions, not ~150 (m6). Other understated
commits: **C3.2** hides a public signature change (M12); **C1.1** hides three renderer edits
if M9 is fixed as it should be; **C4.2** hides the entry-7/8 polarity work it claims to
absorb (M6); **C0.3** hides a determinism programme (B7); **C1.3** hides the per-check
ceiling derivations for chronic and water window, each of which needs its own decision about
which threshold the margin encodes (B4); **C5.10** bundles eleven defects including two that
lose data.

---

## Appendix — 78-entry coverage mapping

Verdict key: **OK** = commit named and its test can fail before / pass after ·
**TEST-WEAK** = commit named, test cannot discriminate the defect · **PARTIAL** = some
sub-findings unaddressed · **LISTED-ONLY** = named in §6 with no mechanism or test ·
**DOCUMENTED** = deliberate non-fix, disclosed in §5 · **N/A** = no action needed.

| # | sev | commit(s) | verdict | note |
|---|---|---|---|---|
| 1 | CRIT | C1.3, C1.4, C1.5 | **TEST-WEAK** | T1 one-sided + tautological (M1); defect survives in interval, `report()`, viz (B1, B3, M4) |
| 2 | HIGH | C2.4 | **BLOCKED** | physics review: T4 (`mono.limiting < bi.limiting`) is unsatisfiable — C2.4 *removes* candidates from a minimum, which can only raise it. My own reading agrees the commit's stated design (checks → `NOT_EVALUATED`) is logically incompatible with its stated test; one of the two must change before C2.4 can land |
| 3 | HIGH | C2.1 | OK | T12 discriminates |
| 4 | HIGH | C2.2 | OK | fix sound; §3 misses the limiting-current move (M8) |
| 5 | HIGH | C3.4 | OK | byte-identical-when-None assertion is the right guard |
| 6 | HIGH | C2.3 | **TEST-WEAK** | T14 fraction-vs-percent trap (M3) |
| 7 | MED | C4.2 | **LISTED-ONLY** | no named test touches `anodic_first` / `anodic_first_for_capacitance` |
| 8 | MED | C4.2 | **LISTED-ONLY** | ledger row corrupt; anti-conservative half-window denominator untested (M6) |
| 9 | HIGH | C1.2 | OK | fix sound; T2 mis-scheduled (B2). Measured 12/54 genuine, ≤2 ulp |
| 10 | MED | C3.3 | OK | elliptic-disc pin is a real external anchor |
| 11 | MED | C1.1 | OK | T17 verified reachable: `DiscElectrode(2000,"SIROF")` → PASS under new rank |
| 12 | MED | C3.5 | DOCUMENTED | value unchanged; §3 should say so |
| 13 | LOW | C1.6 | OK | |
| 14 | LOW | C1.6 | OK | |
| 15 | LOW | C2.1 | OK | |
| 16 | LOW | C3.1 | **BLOCKED** | I reproduced the plan's arithmetic (470.717 Ω); the physics review rejects the formula itself (FD Laplace 335.1 Ω, sphere 329.5 Ω, non-monotonic below aspect 0.679, discontinuous at the L/r=2 switch). Commit needs a new override before it can land |
| 17 | HIGH | C3.1 | **BLOCKED** | physics review: T5's invariant V(r=a)==I·R_access is false for disc/ring/rect and is evaluated at the equal-area disc radius, so it fails even for the sphere. The 2× field defect is real; the named test cannot pin it |
| 18 | HIGH | C3.2 | OK | signature change understated (M12); no number moves |
| 19 | HIGH | C4.2 | OK | T7 discriminates |
| 20 | MED | C3.1 | **BLOCKED** | same commit, same rejected override (see 16) |
| 21 | MED | C3.1 | OK | flag flip stated explicitly; independent of the override dispute |
| 22 | MED | — | DOCUMENTED | §5, correctly |
| 23 | MED | C6.5 | DOCUMENTED | `square()`/`__pow__` only, stated |
| 24 | MED | C4.1 | OK | |
| 25 | MED | C4.1 | OK | |
| 26 | LOW | C6.5 | OK | one-ulp `nextafter` pad |
| 27 | LOW | C6.5 | OK | T10 extensions |
| 28 | LOW | C3.3 | **LISTED-ONLY** | commit subject and test are about the substitution direction (M7) |
| 29 | LOW | C3.3 | **LISTED-ONLY** | same (M7) |
| 30 | LOW | C4.1 | **LISTED-ONLY** | needs a new `verified` field + provenance rollup; unnamed (M7) |
| 31 | LOW | C6.5 | OK | |
| 32 | HIGH | C6.2 | **TEST-WEAK** | T19 is self-consistency (M1); number double-moved by C3.1 (B8) |
| 33 | HIGH | C6.1 | OK | T6 discriminates |
| 34 | MED | C6.2 | OK | |
| 35 | MED | C6.3 | OK | |
| 36 | MED | C6.3 | DOCUMENTED | §5, with measured saturation figures |
| 37 | MED | C6.1 | OK | |
| 38 | MED | C6.1 | **LISTED-ONLY** | rank-deficient path has no test (M7) |
| 39 | MED | C6.4 | OK | |
| 40 | MED | C6.4 | OK | |
| 41 | MED | C6.1 | **LISTED-ONLY** | wrong module — 41 is `models/vta.py`, C6.1 is strength-duration (M7) |
| 42 | LOW | C6.3 | OK | |
| 43 | LOW | C6.5 | OK | |
| 44 | LOW | C6.5 | OK | |
| 45 | LOW | C4.7 | DOCUMENTED | §5, correctly |
| 46 | HIGH | C7.3 | OK | ledger row corrupt but content restated in C7.3 |
| 47 | HIGH | C7.2 | OK | |
| 48 | CRIT | C5.1 | **PARTIAL** | settings forwarded, candidate set not → new figure/text contradiction (B3) |
| 49 | CRIT | C1.2 | **PARTIAL** | GUI, figure annotation and `Interval.describe` not routed (M5) |
| 50 | HIGH | C5.6 | OK | |
| 51 | HIGH | C5.5 | OK | conflicts with C1.6 ordering (M2) |
| 52 | HIGH | C1.6 | OK | conflicts with C5.5 ordering (M2) |
| 53 | HIGH | C5.7 | OK | |
| 54 | HIGH | C4.3 | OK | should also add `counter_electrode` from C3.4 |
| 55 | HIGH | C5.2 | OK | |
| 56 | HIGH | C5.3 | OK | |
| 57 | HIGH | C5.8 | OK | |
| 58 | HIGH | C5.4 | OK | |
| 59 | HIGH | C4.3 | OK | |
| 60 | HIGH | C4.2 | OK | R5's "assert on every check" is the right guard |
| 61/M1 | MED | C5.10 | OK | but arrives ~30 commits after C1.1 makes it acute (M9) |
| 61/M2 | MED | C5.10 | OK | |
| 61/M3 | MED | C5.10 | OK | |
| 61/M4 | MED | C5.5 | OK | |
| 61/M5 | MED | C5.10 | OK | data-loss defect bundled into an 11-item commit |
| 61/M6 | MED | C5.10 | OK | |
| 61/M7 | MED | C5.10 | OK | |
| 61/M8 | MED | C5.10 | OK | |
| 61/M9 | MED | C5.10 | OK | data-loss defect bundled into an 11-item commit |
| 61/M10 | MED | C5.10 | OK | |
| 61/M11 | MED | C5.10 | OK | |
| 61/M12 | MED | C0.3, C5.9 | OK | TIFF confirmed 47 001 446 bytes |
| 61/M13 | MED | C5.9 | OK | committed JSON is RFC-clean today; the test must force a NaN |
| 61/M14 | MED | C5.5 | OK | mapped via the malformed `62/L-M14` (m3) |
| 62/L1 | LOW | C5.10 | OK | |
| 62/L2 | LOW | C5.10 | OK | |
| 62/L3 | LOW | C5.8 | OK | |
| 62/L4 | LOW | C5.10 | OK | |
| 62/L5 | LOW | C5.10 | OK | |
| 63 | HIGH | C1.7, C0.1, C0.2 | **PARTIAL** | FAIL-pinning covered; coverage/mutation sub-claims not reproducible with the named tooling (B5) |
| 64 | HIGH | C1.7 | OK | T9 is the right shape |
| 65 | HIGH | C0.2 | OK | T10 kills C4 |
| 66 | HIGH | C1.4 | **TEST-WEAK** | T1 is a tautology over the widened set (M1) |
| 67(a) | HIGH | C1.7 / C2.3 | OK | assigned twice in §2, once in §6 (m5) |
| 67(b) | HIGH | C1.7 | OK | |
| 67(c) | HIGH | C1.1 | OK | |
| 68 | MED | C0.1, C7.6 | **PARTIAL** | branch floor not implementable as written (B5); lockfile/mypy via T25/T26 are scheduled |
| 69 | MED | C0.2, C1.8 | **PARTIAL** | T18 unscheduled ⇒ mutant P1 survives (B6); 15 tautologies not individually retired |
| 70 | — | — | N/A | vindication |
| 71 | HIGH | C4.4 | OK | |
| 72 | HIGH | C4.5 | OK | |
| 73 | HIGH | C4.5 | OK | |
| 74 | HIGH | C7.4 | OK | but scheduled 40 commits late (M13) |
| 75 | HIGH | C4.7 | OK | |
| 76 | HIGH | C7.4 | OK | conflicts with exit criterion 6 (M10) |
| 77 | MED | C4.6 | OK | S-9 label error; "eight" vs seven listed (m4) |
| 78 | LOW | C4.8, C7.4 | OK | S-14…S-23, S-25 to C4.8; S-24 to C7.4 — all 12 placed |

**Totals:** 56 OK · 4 TEST-WEAK · 4 BLOCKED-BY-PHYSICS-REVIEW · 4 PARTIAL · 5 LISTED-ONLY ·
5 DOCUMENTED · 1 N/A (counting 61 and 62 by sub-finding, 78 entries by ledger row).

**Reading of the total.** 56 of 78 entries have a commit and a test that can actually
discriminate the defect. The 22 that do not are concentrated, not scattered: 13 of them sit
in four commits (C1.3/C1.4 on the limiting current, C3.1 on the space convention, C4.2 on
provenance propagation, C6.1 on the model fits). Repairing those four commits' test plans and
adding the one missing commit (the interval widening, B1) moves the plan from "mostly
verifiable" to "verifiable", which is the difference that matters for a submission whose
claim is that it has no unverified numbers.
