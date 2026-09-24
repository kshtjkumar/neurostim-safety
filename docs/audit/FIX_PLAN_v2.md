# FIX_PLAN v2 — sequenced repair of neurostim-safety before submission

Supersedes `docs/audit/FIX_PLAN.md` (v1), which failed two adversarial reviews:
`critique_physics.md` (5 BLOCKER, 7 MAJOR, 6 MINOR) and `critique_blast.md` (8 BLOCKER,
13 MAJOR, 7 MINOR, plus a 94-row coverage mapping). Ledger entries 79–83 are v1's own
defects.

Original baseline: `7a0515b` (docs-only commits above `bfca95d`), **522 passed in 22.78 s**,
ruff and mypy clean, source byte-untouched at the time this plan was written.

**Phase 0 is landed** (`3c66e24..7e40799`, plus `5405023` recording four new defects), and
**Phase 0b** hardened the oracles (`fe6544b..689c9f2`, 9 commits, **650 passed 1 skipped**,
package byte-untouched — `git diff 8c57f9a HEAD -- neurostim/` is empty). After Phase 0:
**627 tests pass**, ruff and mypy clean, behaviour unchanged —
`limiting_current_uA` is still exactly `141.37166941154072` on the worked example.
`tests/oracles/` exists and is verified: `fail_ceiling_uA` returns exactly 20.0 on the
worked example, `disc_surface_potential_V` gives `V(a) == I·R` bit-equal and
`V(100a)/exact == 0.499992`, `FD_BAND_REFERENCE` gives 335.1 Ω at clinical DBS aspect
(unconverged; 327.6 Ω after C3.7, ledger 127).
Executing Phase 0 surfaced four further defects, now ledger entries **84–87**; §1d records
how each is folded in. Phase 0b closed five oracle MAJORs plus two the builder found
reviewing its own work: over 1824 configurations, silently-wrong `0.0` answers went from 90
to 0, and a non-monotone bracket now raises `NonMonotonePredicate` naming the check and both
amplitudes. §1e records the four consequences for Phase 1.

Evidence: `CODE_MISTAKES_LOG.md` (**82 package defects** + 5 plan defects) and
`docs/audit/*.md` (six audits, two critiques).

Target: JOSS/SoftwareX. Mandate unchanged: no calculation errors, no silent failures, no
unsourced numbers, no doc drift. Fixes may change reported numbers.

**This plan sequences the 82 package defects into 8 phases and 61 commits**, of which 6 are
landed. v1 claimed 41 and enumerated 50; v2's count is stated and enumerated below (§5.9).

Every number in this document was produced by running
`./.venv/bin/python`. Verification scripts are
in `$SCRATCH/v2_inv.py`, `v2_kg.py`, `v2_checks.py`, `v2_surfaces.py`, `v2_s2.py`,
`v2_therm.py`, `v2_mono.py`, `v2_pinmatrix.py`, `v2a_check.py`; the FD Laplace solve was
re-run from the physics reviewer's `p2_fd.py` and reproduced to the digit.

---

## 1. What changed from v1, and why

### 1a. Kept unchanged — endorsed by the physics review, do not relitigate

D1's rank change · D4's **space assignment** (half_space for flush planar + hemisphere,
full_space for immersed) · D2's 4-ulp bound (unbroken over ~43 000 cases in three paths,
worst observed 2) · D3's core claim (an independent binary search returns exactly 20.0 µA
on the worked example) · D5's *diagnosis* · D6's bijective parameterisation · all five
§5 refusals including Shannon-on-non-disc. The seven-phase structure, the tests-first rule,
and most of v1's sequencing survive; v2 adds a Phase 0 commit and reorders three edges.

### 1b. The 13 blockers — disposition

| # | v1 | v2 decision | §  |
|---|---|---|---|
| P1 | `V(r=a) == I·R_access` as the pin for D4 | **Replaced by two pins that jointly admit exactly one fix**: the exact half-space disc oracle `V(r) = (2/π)·I·R·arcsin(a/r)` evaluated at `r = 100a` (cross-module, external closed form), and the surface identity at the **physical** radius for sphere and hemisphere (exact today; a per-geometry guard against double-correction). Verified: the four (factor × R) combinations give 0.499992 / 0.785385 / 1.570770 / **0.999983** — only (2π, Newman) passes. | §2 D4, §5.3 |
| P2 | `ln(2L/r)/(2πσL)` override for band and microwire | **Rejected. Equal-area sphere `1/(4πσa)` for both**, flagged inexact, accuracy stated. Re-ran the FD solve: 335.1 Ω at clinical DBS aspect vs sphere 329.5 (−1.7 %), eq-disc 517.5 (+54.5 %), v1's form 470.7 (+40.5 %). **Corrected at C3.7 (ledger 127):** that solve was unconverged; converged, 327.6 Ω, so sphere +0.6 %, eq-disc +58 %, v1's form +43.7 %. v1's form is also **negative** below aspect ≈0.25 (−399.5 Ω at 0.2), returns 496.3681 Ω for aspect 0.5 *and* 1.0, and steps 38.6 % at its own switch. | §2 D4, §5.3 |
| P3 | `TestKuncelGrill2004` as R2's second pin | **Withdrawn as a pin; the test is rewritten to what it can honestly assert.** Today's 2 % is a coincidence of two errors. At Kuncel & Grill's own stated σ = 0.2 S/m the equal-area sphere gives 578.8 Ω against an FD-true 586.4 Ω (1.3 %; 573.3 Ω, +1.0 %, after C3.7's converged table, ledger 127) and against their *assumed* 500 Ω (+15.8 %); their own numbers back-solve to 508.8 Ω. The replacement pins are P1's two. | §5.3, §7 R2 |
| P4 | T4 `mono < bi`; charge-injection and water-window → NOT_EVALUATED | **Monophasic FAILs with a computable drift time.** Charge injection stays NOT_EVALUATED (no source transfers a biphasic CIC); the water window is *evaluated* by DC drift, which yields a **lower** limit. Verified: v1's design produces 110 inversions over 1134 cases; v2's produces **6**, all Ta2O5, the one material with no window on record — closed by a monotonicity cap (`mono ≤ bi` by construction) plus `limits_incomplete`. | §2 D5, §5.2 |
| P5 | Re-reference the pulse-duty excursion to 0.04 | **Deleted.** Verified `duty_fold ≡ pw_fold × f_fold` (100 µs/200 Hz: duty_fold 1.000 against a product of 16.00; 600 µs/75 Hz: 2.250 both). Reachability of `EnvelopeResult.inside` is restored by the deletion, not by the re-reference: verified `inside` becomes True for the fit protocol with the duty excursion removed. The **train** duty excursion replaces it and is wired into the thermal path. | §2 D5, §5.2 |
| B1 | `limiting_current_interval_uA` fixed by no commit | **New commit C1.8** widens the interval through the same per-check machinery, scheduled *before* T16. Verified 18/18 failures today. | §5.1 |
| B2 | `viz.current_limit_sweep` keeps the three-check minimum | **C5.1 rebuilds `binding` from `assess().limiting_current_uA`.** Verified the artist annotates `binding limit 141 µA` beside a headline that becomes 20.00. | §5.5 |
| B3 | T2 asserts whole-assessment cleanliness at C1.3 | **Split.** T2a (charge + Shannon round-trip, the float half) lands at C1.3; T2b (`not at_limit.failed`) lands at C1.6. The v1 dependency row is inverted and corrected. | §5.1, §4 |
| B4 | T1, T2's second line, T19 are tautologies | **New Phase 0 commit C0.6** adds `tests/oracles/` — an independently written binary-search FAIL ceiling, the arcsin disc oracle, a pulse-by-pulse drift integrator, and the FD band reference. Every later assertion is against an oracle, never against the code path under test. | §5.0, §5.1, §5.6 |
| B5 | Finiteness-only margin test admits −21.1 µA | **`margin` is defined as the FAIL ceiling ratio**, asserted equal to the oracle's binary search to `rel=1e-9`; T1 becomes `== approx(20.0)` **and** `> 0`. Verified the naive `headroom/excursion` reading gives −21.095 / 13.266 / −50.548 µA where truth is 58.905 / 93.266 / 29.452. | §2 D3, §5.1 |
| B6 | Exit criteria 2, 3, 5, 6 broken | **All four restated; 12 criteria, each individually achievable.** T18 scheduled into C3.5; mutation restated as 42/42 named + ≥90 % of a ≥150-mutant generated set; coverage gated on branch **points** by a committed script, not `--cov-fail-under`; criterion 6 restated so no material's `verified` flag may move. | §10 |
| B7 | §3 omits ten moving surfaces; thermal moves twice | **§6 rebuilt with 31 rows**, including all ten, and the thermal rise is booked **once**, in C6.3, at the post-C3.1 value. Verified: today 5.3961 mK → **8.0612 mK**; v1's 24.060 mK was the unperfused analytic value at the *old* access resistance, wrong on both counts. | §6 |
| B8 | "41 commits", 50 enumerated | **61 commits, enumerated and counted** (59 as first written, +1 for C1.5 at the Phase-0 amendment, +1 for C1.2 at the Phase-0b amendment). | §5.9 |

### 1c. MAJOR and MINOR findings adopted

Physics M1(a) `Check.kind` separates tissue / electrode-chronic / electrode-acute /
instrument limits · M1(b) `margin` is margin-to-FAIL, stated · M1(c) handled by `kind`, not
by a train-duration gate (no source supports a cut-off) · M2 `floor_to_pass` gets a checked
contract (declared monotone-decreasing, asserted at the returned point; exhaustion raises;
`resting_potential_V` validated against the window at construction) · M3 renamed
`charge_recovery_ratio`, and the imbalance FAIL cliff is replaced by the same DC-drift
criterion the monophasic fix uses · M4 counter-electrode default becomes CAUTION and the
mutual term is modelled · M5 `environment` is an instance field, set explicitly on the five
disc-substituted presets · M6 folded into P4 · M7 `train_duty_cycle` wired into
`average_current_uA`, `rms_current_uA` and `n_pulses` · m1 the D1→D3 edge is soft · m2 the
D2→D3 reason restated · m3 C1.7's value change booked in §6 · m4 the C3.1 consumers are
`io/fem.py` and `viz/plots.py`, and `compare_with_point_source` gets the electrode threaded
through · m5, m6 editorial.

Execution M2 C1.9 raises at construction and catches per row · M4 `cic_max_current_uA`
floored explicitly · M5 GUI, figure annotation and `Interval.describe` routed through
`format_limit` · M6 ledger rows 8 and 46 repaired in C0.5; C4.2 split out of C4.3 · M7 the
five listed-only entries get commits (28/29 → C3.4, 30 → C4.1 with its own assertion,
38 → C6.2, 41 → C6.5) · M8 §6 row added · M9 C1.1 lands the renderer edits in the same
commit · M11 C1.3/C1.4 trigger artifact regeneration · M12 C3.2's signature change named ·
M13 C0.4's script emits the README transcript and runs on every numeric commit · m2 the
baseline is named · m3, m4, m5, m6, m7 corrected.

**Rejected:** nothing from either review was rejected outright. Three thresholds were
changed rather than adopted verbatim — see §10.

### 1d. Amended after Phase 0 execution (ledger 84–87)

Executing Phase 0 found four things this plan had wrong or had not seen. All four are
folded in below; nothing else in the plan changed.

| # | finding | v2 amendment | §  |
|---|---|---|---|
| **84** | D3's two definitions disagree. D3(i) said "the highest amplitude at which no check FAILs"; D3(ii) takes the minimum over the seven `LIMIT_BEARING` checks. They differ whenever a **non**-limit-bearing check FAILs at every amplitude — which Charge balance does for a monophasic protocol, being a property of the waveform rather than the amplitude. Verified: monophasic `CylindricalBandElectrode(1270,1500,"PtIr")` at 90 µs/130 Hz reports `failed = ['Charge balance']`, `limiting_current_uA = 15285.509415880857` and `describe()` prints `Limiting current: 1.529e+04 uA`, against an oracle ceiling of **0.0**. So C1.6's pin was unsatisfiable as written. | **`LIMIT_BEARING` stays seven** — imbalance is a categorical waveform property, not a ceiling. D3(i) is restated precisely, and the real defect is fixed rather than defined away: `SafetyAssessment` gains **`unsafe_at_any_amplitude`** and every render surface prints that no amplitude is safe, naming the check, instead of a number. **New commit C1.5**, placed before C1.6. | §2 D3, §5.1 |
| **85** | `io/report.py:217` printed `datetime.now(timezone.utc)` into the PDF's own visible byline, so every report was non-reproducible on its face independently of file metadata. | **Fixed in Phase 0, C0.3.** Recorded in §9. | §9 |
| **86** | The README quick-start transcript was hand-written and showed 5 checks where `assess()` emits 9, plus a k/charge-density pair no default configuration produces. Same class as 74 and 76, and absent from both the ledger and audit_literature S-24. | **Fixed in Phase 0, C0.4** — generated between markers from one script and gated in CI. Recorded in §9. | §9 |
| **87** | `viz/style.py` writes TIFF uncompressed: 47 MB for one four-panel 600 dpi figure. `pil_kwargs={"compression": "tiff_lzw"}` cuts it roughly tenfold at no quality cost. Ledger 61/M12 records the size but not the setting. | Deferred out of Phase 0 because it changes the bytes of a package output. **Assigned to C5.9**, which already owns the TIFF. | §5.5, §9 |

Two further amendments follow from executing C0.6:

- **The per-check ceiling oracle does not exist and is folded into C1.4, not C0.6.** C1.4's
  assertion named `oracles.fail_ceiling_for(check)`; C0.6 shipped `fail_ceiling_uA` (whole
  assessment) and deliberately did not add a per-check form, because the set it applies to
  is `LIMIT_BEARING`, which C1.4 itself defines. Signature, semantics and non-tautology
  argument are now in C1.4's row.
- **The ceiling oracles must be guarded against construction-time validation**, in the
  commit that introduces it. Both oracles rebuild a `SafetyCalculator` up to ~60 times per
  bisection across a `1e-12` to `1e6` µA bracket. Nothing in C1.9 validates `current_uA`
  today, so no breakage is expected — but if validation ever reaches amplitude, the upper
  bracket raises and the oracle crashes instead of returning a ceiling. The guard lands in
  **C1.9**, so it is not discovered by it.

### 1e. Amended after Phase 0b (oracle hardening)

Phase 0b made the oracles safe to assert against. Four consequences for Phase 1, and two
standing decisions.

| # | finding | v2 amendment |
|---|---|---|
| **i** | **Load-bearing.** C1.6's T1 asserts `a.limiting_current_uA == approx(fail_ceiling_uA(calc))`. After ledger 84 the package quantity is the minimum over `LIMIT_BEARING`, so the call must be `fail_ceiling_uA(calc, names=LIMIT_BEARING)` — the `names` parameter Phase 0b added. The worked-example ring hides the error (both forms give 20.0); the monophasic companion test in the same row is where they diverge, verified **0.0** against **15285.50941588086**. | C1.6's row restated. |
| **ii** | The `resting_potential_V` window check was scheduled in C1.9, six commits after the floor helper whose monotonicity precondition it is. | Split out into **new commit C1.2**, placed immediately before the floor commit. C1.9 keeps the non-finite class and the batch row errors. |
| **iii** | C1.4's `check_fail_ceiling_uA` was specified as a second bisection. It is now one line: `fail_ceiling_uA(calculator, names={check_name})`. A second bisection would give the per-check form its own probe ladder and its own `NonMonotonePredicate` handling, defeating the single-invariant-in-one-place property Phase 0b bought. Verified: all five pinned constants reproduce through the wrapper bit-exactly. | C1.4's row restated as a thin wrapper plus `brackets_the_check_ceiling`. |
| **iv** | C1.5 asserted `fail_ceiling_uA(calc) == 0.0`. The **witness** is strictly stronger: `amplitude_independent_failures(calc) == ("Charge balance",)` establishes the same thing across all 73 ladder probes rather than two sampled points, and it **names** the check — which is what `unsafe_at_any_amplitude` has to render. | C1.5's row uses the witness for both halves. |

**Decision — an out-of-window resting potential is rejected, not bisected around.** Evidence:
of 1824 swept configurations every non-monotone case is an out-of-window resting potential
and the check that un-fails is always Water window; across 630 in-window configurations
there were **0**. So rejection makes D2's monotonicity precondition *true*, not merely
asserted. C1.2 also re-points
`test_a_non_monotone_predicate_is_reported_not_bisected` and
`test_a_band_narrower_than_one_probe_step_is_reported` at a **stub calculator** returning a
scripted FAIL/PASS/FAIL sequence, because both are built on the `0.9` / `0.95` V fixtures
this commit makes unconstructible. That is not bookkeeping: C2.3 moves the DC-drift verdict
onto Water window, which can legitimately reintroduce amplitude dependence there, so the
guard must not become dead code in the interval.

**Decision — the ledger records the hash as made, and history is not rewritten.** The merge
policy is **no squash-merge and no rebase onto the default branch**, already written into
`CODE_MISTAKES_LOG.md`'s header and repeated in CONTRIBUTING at C7.5. No per-merge hash
rewriting is needed; §9 says so.

---

## 2. Seven conventions settled up front

**D1 — `NOT_EVALUATED` sits *below* `PASS`. Unchanged from v1.**
`Status.rank` becomes `NOT_EVALUATED: 0, PASS: 1, CAUTION: 2, FAIL: 3`. `SafetyAssessment`
gains a `not_evaluated` tuple and `describe()` prints
`Overall: PASS (2 checks not evaluated: ...)`. **v2 change:** that disclosure lands in
`report_to_json`, the PDF header and the GUI headline **in the same commit**, not in
Phase 5 — otherwise ~30 commits ship a bare `PASS` that is strictly less informative than
today's `NOT_EVALUATED` (execution M9). Closes 11, unblocks 67(c).

**D2 — a reported limit always floors; the forward inequality stays exact. Unchanged in
principle; the contract is completed.**
`neurostim/safety/_limits.py` gains `floor_to_pass(value, passes)` and
`format_limit(value, sig=4)`. **v2 additions (physics M2):**

1. Every predicate handed to `floor_to_pass` must be **declared monotone-decreasing in
   current**, asserted at the returned point (`passes(v)` and not
   `passes(nextafter(v, +inf))`).
2. **The settle budget is directional, and both halves raise a named error rather than
   returning an unsettled value.** *Downward*, `STEP_BUDGET = 4` floats of the seed,
   carrying the check, the value and the step count: the walk down corrects a one-ulp
   disagreement between a back-solve and its forward comparison, and a fifth step means
   they are not inverses (ledger 9). **Amended at C2.7 (ledger 98):** the walk down may
   *also* go as far as `PLATEAU_ALLOWANCE × plateau` below the seed when the caller
   declares a plateau, then bisects onto the boundary. A run the predicate cannot resolve
   can straddle the boundary from above as well as below: Shannon's seed lands five floats
   over it once `log10(Q/A)` enters the `[4, 8)` binade. With `plateau = 0` the walk down,
   and its message, are exactly the four-float budget above. **What it gives up (ledger 115):** inside
   `PLATEAU_ALLOWANCE × plateau` the widened walk no longer *detects* a non-monotone
   predicate. It bisects onto whichever transition it finds, and never returns a failing
   point. Monotonicity is therefore a precondition the check's own arithmetic must
   guarantee, not something `floor_to_pass` checks. That is why ledger 104's flickering
   drift clause was fixed at its source (C2.8) rather than by a wider plateau. *Upward*, a **distance**
   `max(CLIMB_TOLERANCE × value, PLATEAU_ALLOWANCE × plateau)` bracketed exponentially
   in ulps and then bisected, carrying the check, the value, the point reached and the
   budget: the walk up crosses a plateau of the check's own making, whose length says
   nothing about the back-solve, so a step count is the wrong unit there (C1.10). v1's
   single 4-step budget described only the first half.
3. **`plateau` is declared by the caller, in the value's own units, and defaults to 0.0**
   — the smallest change in the limit the predicate can resolve. A relative bound alone
   is not sufficient and no constant makes it sufficient: where a predicate adds the
   amplitude's effect to a *constant* (the water window adds an excursion to
   `resting_potential_V` and compares the sum against a window edge), one ulp of that sum
   is a run of amplitudes the check cannot tell apart, its width in current is fixed by
   the constant rather than by the limit, and so its width *relative to the limit* grows
   as `1/limit` without bound. Measured at `CLIMB_TOLERANCE = 1e-9` with no plateau
   declared: **4487 of 70 831 edge-clustered configurations raised `LimitDidNotSettle` on
   inputs C1.2 accepts**, every one of them Water window —
   `resting_potential_V = -0.59999999` on a 100 µm Pt disc, 1e-8 V inside the window,
   among them (ledger 88). `_water_window_ceiling_uA` converts `ulp` of the largest
   potential in its own arithmetic back through `C·A/PW` and declares that.
4. `resting_potential_V` is validated against the material's window **at construction**, in
   **C1.2 — the commit immediately before the floor helper**, not six commits later.
   Without it the water-window predicate is two-sided and non-monotone (False–True–False),
   and "largest float ≤ value that passes" is not the safe answer. Phase 0b measured the
   scope: over 1824 swept configurations every non-monotone case is an out-of-window
   resting potential and the check that un-fails is always Water window; across 630
   in-window configurations there were none. Rejecting the input is therefore sufficient to
   make the monotonicity precondition true rather than merely asserted.
5. `charge.cic_max_current_uA` — a *second*, separate back-solve behind
   `SafetyCalculator.max_current_cic_uA`, hence behind every CSV row and the figure — is
   floored explicitly and asserted equal to `a.charge.max_current_uA` (execution M4).
6. Render sites: `io/report.py`, `assessment.py`, `charge.py` **plus** `gui/app.py:332`
   (`:.4g`), `viz/plots.py:211` (`:.3g`, verified output `binding limit 141 µA`) and
   `uncertainty.Interval.describe` (execution M5).

Closes 9, 49, 88.

**D3 — the limiting current is the minimum over every check that produces a limit.**
Core claim unchanged and independently confirmed: the worked example reports
141.37166941154072 µA while `Microelectrode charge/phase` and `Chronic degradation` both
FAIL; the binary search returns exactly 20.0 µA (ratio 7.0686). Only 4 of 9 checks expose a
finite margin today, so every limit-bearing check must first be given one.

**v2 decisions the reviews forced:**

- **`margin` is the ratio of the FAIL ceiling to the applied current**, not the CAUTION
  ceiling and not `headroom/excursion`. Verified the difference matters: for
  `DiscElectrode(100,"Pt")` at 200 µs the chronic FAIL ceiling is 19.635 µA and the CAUTION
  ceiling 7.854 µA; on the worked-example ring, 70.686 vs 28.274. And the naive
  headroom reading of the water-window margin is **negative** at `resting_potential_V = 0`
  (−21.095 µA against a true 58.905 µA), which a finiteness test and a one-sided `<= 20.0`
  both admit (execution B4).
- **`LIMIT_BEARING` is defined**: Shannon (when evaluated), Charge injection, Current
  density, Microelectrode charge/phase, Compliance, Chronic degradation, Water window —
  seven. Validated envelope and Charge balance impose no current ceiling and stay `inf`.
  **Amended at C3.11 (ledger 133, user decision): eight.** *Counter charge injection* joins,
  emitted only when a `counter_electrode` is supplied. Since C3.5 the counter's area and
  material are inputs, and its charge density moves with amplitude. A counter check left
  outside `LIMIT_BEARING` would be an amplitude-dependent verdict there, breaking the
  invariant that licenses `unsafe_at_any_amplitude`, so it must bear a ceiling.
- **`Check` gains `kind`** (`tissue` / `electrode-chronic` / `electrode-acute` /
  `instrument`) **and `provisional: bool`**. The scalar headline stays a single minimum over
  all seven — programming above the compliance limit means the protocol is not delivered as
  specified, which invalidates every other margin — but `limiting_current_by_kind` is
  reported alongside, and the docstring stops saying "the number to programme against"
  (physics M1a, M1c, m6). `provisional` travels with the margin so a caveated limit is
  visible when it binds (physics m6).
- **`limits_incomplete: bool`** is True whenever a limit-bearing check is NOT_EVALUATED for
  the protocol as given, and is rendered by `describe()`, `report_to_json`, the PDF and the
  GUI. A limit over a knowingly-incomplete candidate set is ledger 1 in a new place
  (physics B4.2).
- **"Limiting current" means the highest amplitude at which no LIMIT-BEARING check FAILs**
  (ledger 84). The qualifier is load-bearing and v2 originally omitted it: the unqualified
  form disagrees with the minimum over `LIMIT_BEARING` whenever a **non**-limit-bearing
  check FAILs, and a non-limit-bearing check's verdict is amplitude-independent by
  construction — that is what "bears no limit" means. Verified over three configurations at
  `1e-12` and `1e6` µA: **no** non-limit-bearing check changes status between the two
  brackets, while five to six limit-bearing ones do.
  `CAUTION_MARGIN = 2.0` is a downgrade factor, not a limit.
- **The limiting current is therefore not the same as "safe", and the package must say so
  rather than rely on the reader.** `SafetyAssessment` gains

  ```python
  unsafe_at_any_amplitude: tuple[Check, ...]
      = tuple(c for c in checks if c.status is Status.FAIL and c.name not in LIMIT_BEARING)
  ```

  Emptiness is the boolean; the tuple exists so every surface can **name** the check. When
  it is non-empty, `describe()`, the PDF, `report_to_json`, the GUI headline and the figure
  annotation must print that **no amplitude is safe and which check makes it so**, in place
  of a number — not beside one. Verified today: the monophasic band prints
  `Limiting current: 1.529e+04 uA (Shannon tissue-damage criterion)` while
  `failed == ['Charge balance']` and the oracle ceiling is 0.0.

  **This is a separate field from `limits_incomplete`, not a reuse of it**, because the two
  carry opposite instructions to the reader. `limits_incomplete` says *the number may be too
  high — a candidate was missing*; `unsafe_at_any_amplitude` says *there is no number*. A
  single flag would force one rendering for both, and the correct rendering differs. A
  monophasic protocol sets both, and `unsafe_at_any_amplitude` takes precedence.

  `limiting_current_uA` keeps its value (the minimum over `LIMIT_BEARING`) — it is still
  what `limiting_current_by_kind` decomposes and what C1.6's round-trip pins — but it is no
  longer *presented* bare when the tuple is non-empty.

Closes 1, 66, 84; needs D2 first (see §4 for the corrected reason).

**D4 — one space convention per geometry, declared on the electrode.**
`Electrode` gains `environment: Literal["half_space", "full_space"]`. **v2 change (physics
M5): an instance field with a class-appropriate default, not a class property**, because
five shipped presets model immersed, non-planar electrodes as equal-area discs
(`mccreery_microelectrode`, `mccreery2010_chronic`, `beebe_iridium_wire`, `weiland_tin`, and
`rose_robblee_typeA` which genuinely is planar). They are tagged explicitly in the same
commit that flips their `access_resistance_is_exact` to False (ledger 21).

Flush planar (Disc, Ring, Rectangular) and Hemispherical → `half_space`; immersed
volumetric (CylindricalBand, Microwire, Sphere) → `full_space`. Both
`models/field._geometry_factor` (2π vs 4π) and `geometry/base.access_resistance_ohm` read
that one property.

**v2 change (physics B2): no cylinder override.** Band and microwire use the equal-area
sphere `1/(4πσa_sphere)`, `access_resistance_is_exact = False`, with the measured accuracy
in the docstring. Re-run FD Laplace solve (converged to 0.1 %, σ = 0.35 S/m, d = 1270 µm):

> **Corrected at C3.7 (ledger 127).** The table below was *not* converged: its radial cells
> were a fixed fraction of the shaft radius, so the band edge was under-resolved. The
> regenerated solve (first cell tied to the band height, box- and Richardson-extrapolated,
> checked against Newman's disc to 0.009 % and against an independent FV solve to 0.3 %)
> gives FV = 653.4, 520.4, 473.7, 353.8, **327.6**, 252.3, 96.7 Ω for the rows below. So the
> sphere is +22.5, **+10.2, +6.9**, +1.2, **+0.6**, +0.3 and +17.1 %: high at every aspect,
> not "within 2 %". The conclusion stands (sphere, not `ln(2L/r)`), but not for accuracy
> everywhere: at aspect 0.5 the log form is +4.8 % against the sphere's +6.9 %. It is
> rejected for being negative below 0.25, non-monotone, discontinuous, 21.5 % *low* at
> 0.39, and 36–48 % high from aspect 1 up. The original table is kept for the record:

| aspect h/d | FD true | eq-sphere | eq-disc (today) | v1's `ln(2L/r)` |
|---|---|---|---|---|
| 0.200 | 739.9 | 800.6 (+8.2 %) | 1257.6 | **−399.5** |
| 0.390 | 559.8 | 573.3 (+2.4 %) | 900.6 | 408.3 |
| 0.500 | 502.2 | 506.4 (+0.8 %) | 795.4 | 496.4 |
| 1.000 | 363.7 | 358.1 (−1.5 %) | 562.4 | 496.4 |
| 1.181 | 335.1 | 329.5 (−1.7 %) | 517.5 | 470.7 (+40.5 %) |
| 2.000 | 255.0 | 253.2 (−0.7 %) | 397.7 | 372.3 |
| 10.00 | 96.3 | 113.2 (+17.5 %) | 177.9 | 132.1 |

v1's form is negative below aspect ≈0.25, returns **496.3681 Ω for both aspect 0.5 and
1.0**, peaks at aspect 0.679, and jumps 38.6 % at its own `L/r = 2` switch. Ledger 20
supersedes ledger 16 and v2 follows it. Ledger 16 stays open as a documented limitation.

**v2 change (physics B1): the pin is not `V(r=a) == I·R_access`.** That identity is false
for disc/ring/rectangle by a **legitimate** π/2 (the point source is the disc's asymptote,
not its surface field; verified `V_exact(a) = 285.714286 mV = I·R` exactly while the 2π
point source gives 181.891 mV, ratio 2/π). Enforcing 1.0000 would force
`1/(4σa) → 1/(2πσa)`, a 57 % error manufactured by a test. The two pins that replace it are
in §5.3 C3.1, with the verified matrix showing they admit exactly one fix.

Closes 17, 20, 21; 16 documented.

**D5 — the pulse-duty excursion is deleted; the train duty cycle is a new, wired field.**
v1's diagnosis is right and is kept: McCreery 2010's duty is a train on/off schedule, so
comparing a pulse duty against it is a category error, and `EnvelopeResult.inside` is
unreachable today (verified: the *fit protocol itself*, 400 µs at 50 Hz, reports
duty fold 25.0 and `inside = False`).

v1's repair is wrong (physics B5). `duty = 2·PW·f·1e-6` for a symmetric biphasic pulse, so
`duty_fold ≡ pw_fold · f_fold` **exactly**. Verified: 100 µs at 200 Hz (4× outside on both
real axes) gives duty_fold 1.000; 600 µs at 75 Hz (inside on both) gives 2.250 and would
fabricate a Shannon CAUTION. v2:

- **Delete the pulse-duty excursion.** Verified this alone restores reachability:
  `inside` becomes True for `StimProtocol(50, 400, 50, 7*3600)` at area 0.1 cm². The
  module docstring states why — at fixed waveform symmetry it is the product of two
  excursions already reported with their own sourced directions, and no source in this
  bibliography gives it an independent basis.
- **Add `StimProtocol.train_duty_cycle: float = 1.0`** (continuous), feed it to
  `mccreery2010.duty_cycle_note`, and add a *train* duty excursion against McCreery 2010's
  continuous protocol — the comparison that source actually supports. At the default the
  fold is 1.0, so `inside` stays reachable.
- **Wire it into the models that claim to consume it** (physics M7): `average_current_uA`
  × train_duty, `rms_current_uA` × √train_duty, `n_pulses` × train_duty. `StimProtocol`'s
  own docstring already says duty cycle "governs average power dissipation, which is what
  the thermal model integrates"; a field only the citation string reads is a new silent
  failure one commit after C2.1's note warns against exactly that. Default 1.0 leaves every
  existing number byte-identical.

Also eliminates execution M3's percent-vs-fraction unit trap, since no numeric duty
reference remains.

Closes 6 and both its symptoms; 67(a).

**D6 — charge imbalance is expressible, and the FAIL is sourced.**
The parameterisation is bijective, not redundant, and survives. **v2 change (physics M3):
the field is `charge_recovery_ratio: float = 1.0`**, not `return_phase_amplitude_ratio`.
Under v1's own formula the return charge is `I·W·r_a`, so `r_a` is the fraction of charge
recovered; "amplitude ratio" reads as amplitude-to-amplitude and is only that when
`return_phase_ratio == 1`. A user setting `return_phase_ratio=0.25,
return_phase_amplitude_ratio=0.9` intending "return at 90 % amplitude" would get `3.6·I`.
The new name is what every downstream consumer actually reads.

**v2 change: the revived FAIL branch gets a sourced criterion — and it lives on the Water
window check, not on Charge balance.** A binary FAIL at `abs(net) > tol` turns a float
tolerance into a safety threshold: at 80 µA/200 µs/130 Hz a 0.1 % imbalance is 2.1 nA of net
DC, below anything this bibliography treats as damaging. The sourced criterion is C2.3's
DC-drift model — but **where** it is reported matters, and ledger 84 settles it:

- **Charge balance** states the imbalance categorically and carries **no** ceiling: FAIL for
  monophasic, CAUTION for a non-zero biphasic imbalance, with the net DC current and DC
  current density reported. It is not in `LIMIT_BEARING`, and its verdict must stay
  amplitude-independent, because that invariant is what makes
  `unsafe_at_any_amplitude` correct (D3).
- **Water window** absorbs the drift consequence and *is* limit-bearing, so the amplitude
  dependence lives where a ceiling can express it.

v2 originally put the drift verdict on Charge balance. That would have made a
non-limit-bearing check's status depend on amplitude and broken D3's new invariant one phase
after it was introduced. One mechanism, two consumers, but only one of them carries a limit.

`is_charge_balanced` switches to a tolerance relative to `charge_per_phase_uC` (closes 15).
Closes 3, unblocks 4.

**D7 — the counter electrode is an explicit input, and the default is visible.**
`SafetyCalculator` gains `counter_electrode: Electrode | None = None` and, when supplied,
`counter_separation_um: float` (required). **v2 change (physics M4):** `None` keeps today's
arithmetic — v1 is right to refuse silent doubling — but the compliance check returns
**CAUTION**, not PASS, with "monopolar single-interface budget assumed; supply
`counter_electrode` for a two-terminal estimate". Under-estimating `required_V` is the
anti-conservative direction and `compliance.py`'s own docstring says the stimulator drops
out of regulation silently; everywhere else this package downgrades for exactly this
(unverified CIC → CAUTION, non-disc Shannon → CAUTION).

**And the two-terminal ohmic term is not `2 × R`.** First-order superposition for two
compact electrodes of equivalent radius `a` at separation `d` gives
`R = (1/(2πσ))·(1/a − 1/d)`. For two adjacent Medtronic-3389 contacts that is 431.7 Ω
against 659.0 Ω for the naive series sum — the mutual term removes 34.5 %. Polarisation
terms *do* double (interfaces do not couple through the medium). The test is
`1.0 < ratio <= 2.0 + tol` with an exact `→ 2.0` assertion at large separation, never
"exactly double".

Closes 5.

---

## 3. Coverage verdict — the two measurements are both right, of different units

The contradiction is resolved, not adjudicated. Measured this session from the two existing
harnesses in the scratchpad (nothing installed; `coverage` and `pytest-cov` are absent from
`.venv` and stay absent):

| measurement | unit | result |
|---|---|---|
| test audit, `sys.monitoring` harness, PEP-649 phantoms excluded | **bytecode conditional-jump sites with both sides exercised** | **338 / 724 = 46.69 %** |
| execution review, `coverage.py` 7.16.1 default report | **source-level branch *arcs* taken** | **548 / 766 = 71.54 %** |
| `coverage.py`'s own data, re-aggregated to branch **points** | **source-level branch points with both exits exercised** | **185 / 383 = 48.30 %** |

Method: I read `coverage.py`'s per-file `executed_branches` / `missing_branches` arc lists,
grouped them by source line, and counted a point covered only when it had no missing arc —
the same rule the audit harness applies to jump sites. The result, **48.30 %**, is within
1.6 points of the audit's 46.69 %.

**Verdict: neither number is wrong and neither refutes the other.** The audit measured
decision points fully exercised; `coverage.py`'s headline measures arcs taken, which counts
a branch half-covered as half-credit. The denominators differ (724 vs 383) because the audit
counts bytecode jumps — `and`/`or` short-circuits, comprehension and loop exits — while
`coverage.py` counts AST branch statements; that difference cancels in the ratio.

The execution review's per-module refutations do not survive the same recasting:

| module | audit (jump points) | coverage.py points | coverage.py arcs |
|---|---|---|---|
| `safety/current_density.py` | 1 / 11 | **1 / 6** | 7 / 12 (58.3 %) |
| `safety/assessment.py` | 47 / 67 | **26 / 30** | 56 / 60 (93.3 %) |
| `units.py` | 0 / 2 | **0 / 1** | 0 / 2 |
| `models/vta.py` | 2 / 20 | **0 / 12** | 12 / 24 |
| `sensitivity.py` | 8 / 12 | **0 / 2** | 1 / 4 |

`current_density.py` has exactly **one** fully-exercised decision under both point metrics;
"58.3 %" is the arc figure and does not contradict the audit's finding. `assessment.py`'s
"93.3 %" is likewise arcs.

**What gates.** Branch **points**, computed by a committed `scripts/branch_floor.py` that
reads `coverage json` and re-aggregates arcs to points exactly as above. Not
`--cov-fail-under`, which the execution review correctly showed gates the blended
line+branch total (88.15 % on day one against a 46.7 floor — 41 points of slack, and it can
never ratchet). Baseline **48.30 %**; exit floor **80 %**, with a **60 % per-module floor**
for every module with ≥ 4 branch points. An 80 % point floor implies ≥ 87 % arcs, so the
execution review's proposed 85 % arc floor is subsumed rather than rejected.

Where the 198 uncovered points live (top 12, coverage.py points):
`models/thermal.py` 10/28 · `io/fem.py` 2/17 · `materials.py` 15/29 · `viz/plots.py` 6/20 ·
`models/vta.py` 0/12 · `models/field.py` 3/14 · `safety/compliance.py` 5/13 ·
`models/strength_duration.py` 1/9 · `safety/charge.py` 11/18 · `safety/water_window.py`
6/13 · `geometry/arrays.py` 3/9 · `safety/current_density.py` 1/6. Every one of these is
touched by a commit in §5.

---

## 4. Fix order and dependency graph

```
Phase 0  harness + oracles ───────────────────────────────────┐
             │                                                │
Phase 1  verdict core   D1 → margins → D2 → D3 → interval     │  (numbers move)
             │                                                │
Phase 2  data model     D6 → return-phase assessment          │  (numbers move)
             │          drift model → monophasic              │
             │          D5 → envelope repair                  │
             │                                                │
Phase 3  space/geometry D4 → current distribution → D7        │  (numbers move)
             │                                                │
Phase 4  provenance     materials → propagation → io → lit    │  (numbers move)
             │                                                │
Phase 5  io / viz / gui (consumes everything above)           │
             │                                                │
Phase 6  models (C6.3 depends on C3.1; rest parallelisable)   │
             │                                                │
Phase 7  release / docs / CI ─────────────────────────────────┘
```

| edge | reason | changed from v1? |
|---|---|---|
| C0.6 → every later test | The oracles must exist before the first assertion that needs one, or the tests get written against the code path they test. | **new** |
| C0.3 → C0.4 | Determinism must be pinned before content is pinned. Verified: 5 of 8 artifacts differ between two identical runs (SVG `<dc:date>`, PDF `/CreationDate`, matplotlib's random `svg.hashsalt` — identical file lengths, only element ids differ). | **new** |
| margins → D3 | Chronic degradation and water window carry no `margin` today, so the minimum cannot see them. Verified: `assessment.json` records `null` for 5 of 9. | unchanged |
| **T2b → D3, not D2 → D3** | v1 has this backwards. Verified T2's stated parametrisation: 52/54 fail as *whole assessments* today, of which only 12 are the float bug (all ≤ 2 ulp) — the other 40 are structural and are cleared by C1.6, not by flooring. What C1.3 genuinely owes C1.6 is the **helper**: `floor_to_pass` cannot be applied to the four new limits until D3 defines their forward predicates, so the helper lands at C1.3 and its *application* to the new limits lands inside C1.6 (physics m2). | **corrected** |
| D1 → D3 is **soft** | v1 calls it hard, claiming the rank change supplies the ran/did-not-run predicate. It does not — `c.status is not Status.NOT_EVALUATED` is available today at any rank order. C1.6 is not blocked if C1.1 proves contentious (physics m1). | **corrected** |
| **C1.2 → C1.3** | D2 point 1 asserts that every predicate handed to `floor_to_pass` is monotone-decreasing. The water-window predicate is not, for out-of-window resting potentials — and only for those (1824 configurations swept, 0 non-monotone among 630 in-window). The rejection must land before the helper that assumes it. | **new (amendment)** |
| **C1.4 → C1.5 → C1.6** | `unsafe_at_any_amplitude` is defined by `LIMIT_BEARING` membership, which C1.4 introduces; and C1.6's pin `limiting_current_uA == fail_ceiling_uA(calc)` is unsatisfiable until C1.5 has made the exclusion explicit (ledger 84, verified 15285.5 vs an oracle 0.0). | **new (amendment)** |
| C2.3 → C2.4 and C2.1 | One DC-drift model serves both the monophasic water window and the unbalanced-biphasic criterion — but the drift **verdict** is reported on Water window (limit-bearing), never on Charge balance, so C1.5's invariant survives Phase 2. | **new** |
| **C1.5 → C2.3, C5.1** | C2.3 must keep the drift verdict off Charge balance, so C1.5's invariant — a non-limit-bearing check's verdict is amplitude-independent — survives Phase 2; and C5.1's figure must honour the flag rather than annotate a binding limit. **Corrected at C2.1:** this edge also claimed C2.1 inherits C1.5's rendering contract, because an unbalanced biphasic protocol would fail amplitude-independently. D6's v2 change makes that unreachable — a partial recovery is a CAUTION here and a ceiling on Water window — so C2.1 is no longer a dependant of C1.5. | **new (amendment)** |
| D6 → 4 | Return-phase current density and compliance cannot be evaluated until imbalance and independent amplitude exist. | unchanged |
| D5 ⇔ D6 | Both are `StimProtocol` fields; both ripple into `io/tabular.py`, `io/report.py`, `report_to_json` and the GUI form. Pay the ripple once. | unchanged |
| D4 → D7 | The two-interface budget sums two access resistances; both must already be computed under one convention. | unchanged |
| **C3.1 → C6.3** | `dT ∝ R_access²`. Verified: C3.1 moves the DBS band 517.5 → 329.5 Ω, which moves C6.3's headline by (329.5/517.5)² = 0.4054. Phase 6 is *not* fully parallel; C6.3 is a dependent. | **corrected** |
| **C3.1 → C5.10, C3.1 → C7.3** | `io/fem.compare_with_point_source` calls `potential_V` with no `electrode=`, so after D4 it silently stays full-space while every planar assessment becomes half-space — inside the utility C7.3's FEM-validation claim rests on (physics m4). | **new** |
| 19 → 60, 59 | One root cause, three surfaces. Fix the propagation, then the two renderers. | unchanged |
| Phase 4 → C7.4 | README's PEDOT row (74) and the two inert-flag claims (76) can only be written truthfully after the materials and propagation fixes land. **But the transcript regenerates on every numeric commit**, not once at C7.4 (execution M13). | **corrected** |

---

## 5. Commits, tests-first

Each commit lands the failing test(s) **first** in the same commit, then the fix, then the
doc/artifact updates. `pytest -q` must be red on the test alone and green after.
"Why not tautological" names what the expected value is derived from — it is never the code
path under test.

**Fixture rule, earned from a surviving mutant in Phase 0b.** Any round-trip or forwarding
test must use values that differ from every default the code could silently fall back to.
A forwarding defect in `rebuild_at` survived a signature guard, a frozen-set test and a
human review, and died only to mutation testing — because the fixture sat on the argument's
own default, so dropping the argument changed nothing observable. Where a parameter has a
default, the fixture must not use it.

### 5.0 Phase 0 — harness and oracles (6 commits, no behaviour change) — **LANDED** `3c66e24..7e40799`

| # | subject | closes | test that must fail first | why it cannot pass tautologically |
|---|---|---|---|---|
| C0.1 | `build: gate branch-POINT coverage with a committed script; add Python 3.14 to CI` | 68 (partial), T23, T24 | `scripts/branch_floor.py --min 48.0` exits non-zero when fed a synthetic report below the floor; CI job absent today | The floor is computed from `coverage json` arcs re-aggregated to points by a script under review; the metric and the denominator are both in the repo, not in a flag. Baseline 48.30 %. |
| C0.2 | `test: add tests/test_units.py and drop the grep subprocess` | 65, 69 (§8.1), T10, T20 | T10 — four unit-conversion mutants survive today; `units.py` has no importing test and 0 of 1 branch points covered | Expected values are SI identities written longhand (`1 µA × 1 µs = 1e-12 C = 1e-6 µC`; `1 mm² = 0.01 cm²`), not round-trips through the converters. |
| C0.3 | `build: make every generated artifact byte-reproducible` | 85, prerequisite for C0.4 | new: run `examples/worked_example.py` twice into clean directories and diff — 5 of 8 differ today (verified) | The assertion is a diff of two runs of unchanged code; nothing in it is computed by the code under test. Fix: `SOURCE_DATE_EPOCH`, `metadata={"Date": None, "Creator": None}` on every `savefig`, fixed `rcParams["svg.hashsalt"]`, `reportlab.rl_config.invariant = 1`. **Execution found a fifth cause the plan had not seen (ledger 85): `io/report.py:217` printed `datetime.now(timezone.utc)` into the PDF's own visible byline.** |
| C0.4 | `build: generate example_output and the README transcript from one script` | 86, 61/M12 (partial), enables 74, 76, 78/S-24 | new: `scripts/regenerate_example_output.py` output must equal what is committed, and must include the README quick-start block | Byte comparison against committed files. Load-bearing: the 47 MB uncompressed RGBA TIFF leaves the repo here, and every later numeric commit reruns one script instead of hand-editing eight surfaces. **Execution confirmed ledger 86: the hand-written transcript showed 5 checks against 9 emitted.** |
| C0.5 | `build: repair and gate the mistakes ledger` | 69 (gate), execution M6 | new: `scripts/ledger_check.py` — rows 8 and 46 parse to 13 and 11 fields against the table's 9, because of unescaped `\|` in `min(\|cathodic\|,\|anodic\|)` | A parser over the markdown source; expected field count is the header's. Also asserts every entry number appears in §9 with a commit id present in `git log`. |
| C0.6 | `test: add tests/oracles/ — independent expected-value generators` | prerequisite for B4's repairs | new: each oracle pinned to a hand-computed constant — the suite fails to import today | **This is the structural answer to "tests that pass for the wrong reason".** Four oracles: (a) `fail_ceiling(calc)` — binary search for the highest amplitude at which no check FAILs, written from `assess().failed` only, verified to return exactly **20.0** on the worked example; (b) `disc_surface_potential(I, R, a, r) = (2/π)·I·R·arcsin(a/r)` — the exact half-space disc solution, verified `V(a) = 285.714286 mV = I·R` exactly; (c) `drift_time_s` — pulse-by-pulse accumulation loop, verified to reproduce the closed form to within one pulse at **0.2558 s**; (d) `FD_BAND_REFERENCE` — the converged FD Laplace table above, generator committed at `scripts/fd_band_reference.py`. **As landed the names are `fail_ceiling_uA`, `disc_surface_potential_V`, `drift_time_s` / `drift_time_s_closed_form`, `FD_BAND_REFERENCE`, plus `rebuild_at`, `no_check_fails` and `brackets_the_ceiling`. The per-check ceiling this plan called `fail_ceiling_for` is deliberately NOT here — it is keyed to `LIMIT_BEARING`, which C1.4 defines, so it lands in C1.4.** |

### 5.1 Phase 1 — the verdict core (11 commits)

| # | subject | closes | test that must fail first | why it cannot pass tautologically |
|---|---|---|---|---|
| C1.1 | `fix(safety): rank NOT_EVALUATED below PASS and surface unevaluated checks everywhere` | 11, 67(c), 61/M1 (headline half) | **T17** — `SafetyCalculator(DiscElectrode(2000.,"SIROF"), StimProtocol(20,400,50,3600)).assess().status is Status.PASS`; returns NOT_EVALUATED today for every macroelectrode | The expected status is named literally; the rank order is asserted as four explicit inequalities. Scope includes `report_to_json`, the PDF header and the GUI headline in this commit (execution M9). |
| C1.2 | `fix(safety): reject a resting potential outside the material's own water window` | 14 (part), 84 (oracle consequence) | new: `SafetyCalculator(DiscElectrode(100.,"Pt"), ..., resting_potential_V=0.9)` must raise `ValueError` naming the window — 0.9 V is already past Pt's +0.8 V anodic limit at rest. Same commit: `tests/test_oracles.py::test_a_non_monotone_predicate_is_reported_not_bisected` and `::test_a_band_narrower_than_one_probe_step_is_reported` are re-pointed at a **stub calculator** returning a scripted FAIL/PASS/FAIL sequence | **Split out of C1.9 and moved six commits earlier** because D2 point 1 requires every predicate handed to `floor_to_pass` to be monotone-decreasing and asserts it at the returned point — and the water-window predicate is non-monotone for exactly the inputs C1.9 would have rejected six commits later. Fixing the input class before the helper that assumes it is the ordering that makes the assertion meaningful rather than aspirational. Evidence: over 1824 swept configurations **every** non-monotone case is an out-of-window resting potential and the check that un-fails is always Water window; across 630 in-window configurations there were **0**. **The stub re-point is not bookkeeping.** Both guard tests are built on `resting_potential_V = 0.9` / `0.95`, which this commit makes unconstructible, so they would silently stop exercising `NonMonotonePredicate`. A stub keeps the guard live — and it must stay live, because C2.3 moves the DC-drift verdict onto Water window, which can legitimately reintroduce amplitude dependence there. Non-tautology: the stub's FAIL/PASS/FAIL script is written in the test, so the expected `NonMonotonePredicate` is a property of the script, not of any package verdict. |
| C1.3 | `fix(safety): floor every reported limit, at every render site` | 9, 49 | **T2a** — `at_limit.charge.passes and at_limit.shannon.passes` over 9 materials × 3 policies × 2 polarities; 12/54 fail today with `100.00000000000001 > 100.0` | The oracle is IEEE, not the code: `passes(limit)` true and `passes(nextafter(limit, +inf))` false. Plus a property test over random `(area, pulse_width, k)`. Scope adds `cic_max_current_uA`, the GUI, the figure annotation and `Interval.describe` (execution M4, M5). |
| C1.4 | `fix(safety): give every limit-bearing check a margin, a kind and a provisional flag` | 1 (prerequisite), 30 (partial) | new: for each of the seven `LIMIT_BEARING` checks, `c.margin * p.current_uA == approx(oracles.check_fail_ceiling_uA(calc, c.name), rel=1e-9)` | **The per-check oracle lands here, not in C0.6** (amendment 2): it is keyed to `LIMIT_BEARING`, which this commit defines, so it cannot be specified earlier. **It is a one-line wrapper, not a second bisection** — Phase 0b gave `fail_ceiling_uA` a `names` parameter, so `check_fail_ceiling_uA(calculator, check_name, **kw) = fail_ceiling_uA(calculator, names={check_name}, **kw)`, plus `brackets_the_check_ceiling` wrapping `brackets_the_ceiling` the same way. A re-implementation would give the per-check form its own probe ladder and its own `NonMonotonePredicate` handling, defeating the single-invariant-in-one-place property that Phase 0b bought. Semantics carry over unchanged: `0.0` if the check FAILs at the lower bracket, `inf` if it never FAILs — so a NOT_EVALUATED check yields `inf`, matching `margin = inf`. Verified: all five pinned constants reproduce through the wrapper bit-exactly. **Non-tautology:** it reads exactly one bit per probe — one named check's `status is Status.FAIL` — and never reads `margin`, `max_current_uA`, `limiting_current_uA`, `kind` or `LIMIT_BEARING`. Landing in the same commit as `margin` does not make it circular: the value comes from bisection over the package's verdict, the same relationship `fail_ceiling_uA` already has to `limiting_current_uA`. `tests/test_oracles.py` pins it to hand constants on `DiscElectrode(100,"Pt")` at 80 µA/200 µs — Chronic degradation **19.634954084936204** (= 50/203.7 × 80), Water window **58.90486225480862**, Microelectrode charge/phase **20.0**, Charge injection **39.26990816987241**, Current density **86.42793360039114** (all verified). A finiteness assertion is explicitly **not** sufficient: the naive water-window margin is −21.095 µA and finite. |
| C1.5 | `fix(safety): refuse to report a limiting current for a protocol unsafe at any amplitude` | 84 | new: monophasic `CylindricalBandElectrode(1270,1500,"PtIr")` at 90 µs/130 Hz — **no** render surface may present a bare limiting current, and each must name `Charge balance`. Verified today: `describe()` prints `Limiting current: 1.529e+04 uA (Shannon tissue-damage criterion)` with `failed == ['Charge balance']` and an oracle ceiling of `0.0`. Second assertion, pinning the definition: for every check **not** in `LIMIT_BEARING`, its status at 1e-12 µA equals its status at 1e6 µA | The expected value is an **absence** — a rendered string that contains no amplitude — checked against the oracle's **witness**, `amplitude_independent_failures(calc) == ("Charge balance",)`, not against a bare `fail_ceiling_uA(calc) == 0.0`. The witness is the stronger statement in both directions: it establishes amplitude-independence across all 73 ladder probes rather than two sampled points, and it **names the check** — which is precisely what `unsafe_at_any_amplitude` has to render, so the test asserts the thing the feature promises. Use it for the second assertion too, in place of the two-bracket comparison. Verified: `amplitude_independent_failures` returns `('Charge balance',)` for the monophasic band and `()` for the worked-example ring. Scope: `describe()`, `report_to_json`, the PDF header, the GUI headline — the figure annotation follows at C5.1, which is where `viz` stops computing its own minimum. |
| C1.6 | `fix(safety): the limiting current is the minimum over every limit-bearing check` | 1, 66 | **T1** (rewritten) — `assert not a.unsafe_at_any_amplitude` as an explicit, visible precondition, then `a.limiting_current_uA == approx(oracles.fail_ceiling_uA(calc, names=LIMIT_BEARING), rel=1e-9)`, `> 0`, and `== approx(20.0)` on the worked example; plus **T2b** (`not at_limit.failed`), moved here from C1.3; plus a companion test that a monophasic protocol presents **no** bare limiting current on any surface | The oracle is the binary search; the 20.0 is independently pinned to `cogan2016.MICROELECTRODE_DAMAGE_THRESHOLD_NC_PER_PHASE / 200 µs`. **`names=LIMIT_BEARING` is load-bearing and was missing** (amendment 1e): after ledger 84 the package quantity is the minimum over the seven, so the unrestricted oracle is a different number. The worked-example ring hides the error — both forms return 20.0 — and the monophasic companion test in this same row is where they diverge: verified **0.0** unrestricted against **15285.50941588086** restricted, matching the package's 15285.509415880857. **The precondition is asserted rather than assumed** (amendment 1d): without it T1 is unsatisfiable for any protocol with an amplitude-independent failure — verified 15285.509415880857 against an oracle 0.0 — and silently narrowing the parametrisation would hide exactly the case C1.5 exists to fix. v1's `min(c.margin * I ...)` form is the implementation restated and is dropped. |
| C1.7 | `fix(safety): limiting_mechanism must name a check that ran` | 1 (§9b.1) | **T3** — `DiscElectrode(40.,"PEDOT")` at 200 µs reports **99.6724 µA "(Shannon tissue-damage criterion)"** while that check is NOT_EVALUATED (verified) | The expected mechanism is derived from the check statuses, which C1.7 does not compute; the failing case is pinned to Cogan 2016's macro/micro boundary. This is a **value** change, not just a label — §6 has a row (physics m3). |
| C1.8 | `fix(safety): widen the limiting-current interval to the same candidate set as the point estimate` | 1 (interval surface) | **T16**, pulled forward from v1's C1.8 — `a.limiting_current_interval_uA.contains(a.limiting_current_uA)`; **18 of 18** cases fail after C1.6 (verified: ring interval 141.37–212.06 against a point estimate of 20.0) | Containment is a property of two independently computed objects; the interval is built from published ranges (Shannon 1.5–2.0, the full material range) and per-check margins, not from the point estimate. |
| C1.9 | `fix(safety): reject non-finite settings at construction, and record row errors` | 13, 14 (remainder), 52 | new: `SafetyCalculator(..., compliance_V=float("nan"))` must raise `ValueError`; a batch row that raises must appear with `status="ERROR"` and the message. **The `resting_potential_V` window check moved to C1.2**; what stays here is the non-finite class | The raise is asserted by type and message, and the row contract is asserted on the frame. **Resolves execution M2:** v1's C1.6 required a raise while C5.5 required a recorded row four phases later — both land here. **Also lands the oracle guard** (amendment 3): both ceiling oracles rebuild a `SafetyCalculator` up to ~60 times per bisection over a `1e-12`–`1e6` µA bracket, so `tests/oracles/fail_ceiling.no_check_fails` must catch `ValueError` and return `False` — an amplitude the package refuses to construct is not an amplitude at which nothing fails. Nothing here validates `current_uA` today, so no oracle breaks; the guard lands with the validation so that a later extension to amplitude is caught by a test rather than by a crashed bisection. Pinned by a case whose settings reject a high amplitude: the oracle must return the largest constructible amplitude, not raise. |
| C1.10 | `test: pin a FAIL and both boundary sides for every safety check` | 63, 64, 67(a,b) | **T8** (six reachable FAIL states, listed in `audit_tests.md` §10) + **T9** (`<=` vs `<` at the line) | Each threshold is pinned to its stored source sentence (Shannon k = 1.5; Pt CIC 50–150 µC/cm²; Pt window −0.6/+0.8 V; Pt dissolution 20–50 µC/cm²), and the boundary is approached from both sides by `nextafter`. Kills S3, C2, P3, A5, A3, A4. |
| C1.11 | `test: pin monotonicity, interval containment and dimensional consistency` | 69 | **T15**, **T11**; T16 already landed at C1.8 | T11's expected values are dimensional identities (`Q/A × A == Q`; `(4/3)πr³` written out) — kills M4 and M5, which the existing ratio-only test cannot see. T15 asserts an ordering, not a value. |

### 5.2 Phase 2 — data model (5 commits)

| # | subject | closes | test that must fail first | why it cannot pass tautologically |
|---|---|---|---|---|
| C2.1 | `feat(protocol): make charge recovery an independent input` | 3, 15 | **T12** — `charge_recovery_ratio=0.9` gives `net_charge_per_pulse_uC ≈ 0.1 × charge_per_phase_uC`; today `net_charge ≡ 0` for every ratio | The expected 10 % residual is arithmetic on the inputs, not a call into the protocol's charge properties. Must include the consumer wiring — `io/tabular.py` (`asdict(calc.p)` and the batch aliases), `io/report.py`, `gui/app.py` — in this commit. **Corrected against D6 at execution (C2.1):** this row originally said an unbalanced biphasic protocol inherits C1.5's contract because its Charge balance FAILs. Under D6's v2 change it does not — Charge balance is CAUTION for a partial recovery and FAILs only for a waveform that recovers *nothing* (monophasic, or `charge_recovery_ratio == 0`). "No amplitude is safe" would be a false claim for a partially recovered pulse: the mechanism is DC drift, whose time to the window edge rises without bound as amplitude falls, so the ceiling belongs on Water window (C2.3), which bears one. T12 therefore asserts the CAUTION, the reported net DC and its density, and that `limiting_current_uA` stays a number. |
| C2.2 | `fix(safety): evaluate the return phase in current density and compliance` | 4 | **T13** — `return_phase_ratio=0.25` must give a worse current-density margin than symmetric; identical today (0.3183 A/cm² both) | The expected 4× is computed from `return_phase_current_uA`, a quantity the package already exposes and never reads. Plus a golden assertion that every **symmetric** protocol is byte-identical across this commit. |
| C2.3 | `feat(safety): model DC drift out of the water window` | prerequisite for 2 and 3's criterion, 84 (invariant) | new: for `StimProtocol(3000,90,130,1, waveform="monophasic")` on a 0.05985 cm² Pt band, the reported drift time is **0.2558 s** (verified: 0.6 V × 250 µF/cm² × 0.05985 cm² / 35.1 µA) | The oracle is C0.6's landed `drift_time_s` — a pulse-by-pulse accumulation loop, independent of `drift_time_s_closed_form`; they must agree to within one pulse. **The drift verdict is reported on the Water window check, never on Charge balance** (D6, ledger 84): Charge balance is not limit-bearing and its status must stay amplitude-independent, so a second assertion re-runs C1.5's bracket test (status at 1e-12 µA equals status at 1e6 µA for every non-limit-bearing check) on an unbalanced biphasic protocol. |
| C2.4 | `fix(safety): stop applying biphasic-measured limits to monophasic protocols` | 2 | **T4** (rewritten, four assertions) — see below | See below. |
| C2.5 | `fix(safety): delete the pulse-duty excursion; add and wire the train duty cycle` | 6, 67(a) | **T14** (rewritten) — `envelope.evaluate(StimProtocol(50,400,50,7*3600), 0.1).inside` is True (verified unreachable today, duty fold 25.0), **and** the excursion list contains no pulse-duty entry, **and** `StimProtocol(50,600,75,3600)` produces no concerning excursion | The deletion is pinned by the absence assertion — a re-referenced excursion would pass the first clause and fail the second. The 600 µs/75 Hz clause pins the fabrication case v1 would have created (verified duty_fold 2.25 with both real axes inside). Wiring is pinned by `rms_current_uA(train_duty=0.5) == approx(rms_current_uA(1.0)/√2)`. |

**C2.4 in full.** v1's C2.4 is unsatisfiable *and* a regression: removing candidates from a
minimum can only raise it, and v1's design produces **110 cases out of 1134** where the
monophasic limit is strictly higher than the biphasic one (reproduced this session; e.g.
`DiscElectrode(150,"SS316LVM")` at 200 µs, 17.67 → 20.00 µA). v2:

1. **Charge injection → NOT_EVALUATED** with "every stored CIC was measured biphasic
   (Merrill 2005); no source here validates it for monophasic delivery". Unchanged from v1
   and endorsed by the physics review.
2. **Water window → evaluated by DC drift** (C2.3), not NOT_EVALUATED. Ledger 2's finding
   is that the answer is affirmatively wrong in the unsafe direction, and the correct
   conservative answer is computable from quantities the package already holds. FAIL when
   `t_exit < train_duration_s`; CAUTION with the time reported otherwise; never PASS. Its
   current ceiling enters the candidate set — **0.0 for a continuous train**, which is the
   honest answer under a capacitive-interface model and is consistent with the charge-balance
   FAIL that a monophasic protocol carries regardless.
3. **A monotonicity cap**: `limiting_current_uA` for a monophasic protocol is additionally
   capped at what the same electrode and protocol would report biphasic. A strictly worse
   waveform can never earn a higher limit.
4. **`limits_incomplete = True`**, rendered everywhere.

Verified: v2's design reduces the 110 inversions to **6**, all on Ta2O5 — the one shipped
material with no water window on record, so no drift ceiling exists for it. The cap closes
those 6 by construction.

**T4's four assertions, none tautological:**
(a) on the 110 cases v1 would have inverted, `mono.limiting_current_uA < bi.limiting_current_uA`
**strictly**, with the expected value from C0.6's drift oracle — the cap alone would only give
`≤`, so this clause fails if the drift model is not wired in;
(b) `mono.status is Status.FAIL`;
(c) `"Charge injection limit" in mono.not_evaluated` and `mono.limits_incomplete is True`
for Ta2O5;
(d) the ledger-2 case reports a drift time of 0.2558 s ± 1 %, against the integrator.

### 5.3 Phase 3 — space convention, distribution, counter electrode (6 commits)

| # | subject | closes | test that must fail first | why it cannot pass tautologically |
|---|---|---|---|---|
| C3.1 | `fix(geometry): settle one half-space/full-space convention per geometry` | 16 (documented), 17, 20, 21 | **T5** (rewritten, two pins) — see below | See below. |
| C3.2 | `fix(safety): report the current distribution of the actual geometry` | 18 | new: a sphere and a flush hemisphere must report a **uniform** primary distribution, not the disc's `0.5/√(1−(r/a)²)` | The expected distribution is the analytic primary distribution for each geometry, written in the test. **Names the API change v1 hid** (execution M12): `current_density.evaluate` has no electrode parameter and needs one threaded from `assessment.py`. No margin or limit moves — the Butterwick comparison uses the average, not the peak. |
| C3.3 | `fix(geometry): correct the direction of the equal-area substitution error` | 10 | new: pin against the exact elliptic-disc solution `R = K(e)/(2πσa)` — thin annulus w/b = 0.01: 50 634 Ω equal-area disc vs 11 682 Ω exact ring — asserting the substitution **over**estimates | The oracle is a closed-form elliptic integral written in the test, validated to 0.34 % against the exact disc in the geometry audit. A docstring direction is not testable; the inequality is. |
| C3.4 | `fix(geometry): reject NaN pitch, coincident sites and contradictory tip parameters` | 28, 29 | new: `linear_array(disc,3,nan)` must raise; two sites at identical coordinates must raise; `MicrowireElectrode(50,0,"flat",999999.)` must raise | Separated from C3.3 (execution M7): C3.3's subject and oracle are the substitution *direction* and cannot fail for a NaN pitch. |
| C3.5 | `feat(safety): model the counter electrode and the lead resistance in the voltage budget` | 5, 69 (T18) | new: `counter_electrode=None` byte-identical to today but the check is **CAUTION**; with a counter electrode, `1.0 < ratio <= 2.0 + tol`, and `→ 2.0` at large separation; **T18** — `lead_resistance_ohm=2000` must add `I·R` to `required_V` and lower `max_current_uA` | The two-terminal expected value is `(1/(2πσ))·(1/a − 1/d)` written in the test (431.7 Ω for two 3389 contacts at 2 mm, against 659.0 Ω naive). T18's expected value is Ohm's law on the inputs. **T18 was scheduled in no v1 commit, leaving mutant P1 alive** (execution B6); `lead_resistance_ohm` is non-zero nowhere in the 522-test suite today. |
| C3.6 | `docs(safety): state Shannon's diameter-not-area finding where it applies` | 12 | new: a non-disc geometry must not return an unqualified PASS from the Shannon check, **and** its `Check.provisional` must be True so a caveated limit is visible when it binds | The status expectation is a literal; the `provisional` clause closes physics m6 — v1 changed the confidence but left an uncaveated Shannon limit free to bind the headline for a band or ring. The limit's *value* does not change (§6 says so). |

**C3.1's two pins (replacing the false T5).** Verified matrix — ratio of the model to the
oracle, disc radius 500 µm, σ = 0.35, r = 100a:

| geometry factor | `access_resistance_ohm` | Pin A ratio |
|---|---|---|
| 4π (today) | Newman `1/(4σa)` | 0.499992 |
| 4π | `1/(2πσa)` (the regression v1's T5 would force) | 0.785385 |
| **2π** | **Newman `1/(4σa)`** | **0.999983** ✓ |
| 2π | `1/(2πσa)` | 1.570770 |

**Pin A — asymptotic identity against the exact half-space disc solution.** For Disc, Ring
and Rectangular, `potential_V(I, 100a, σ, electrode=el)` must equal
`(2/π)·I·R_access·arcsin(a/100a)` to `rel=1e-4` (and to `rel=1e-2` at `r = 10a`). This is
cross-module, and the oracle is an analytic formula that appears nowhere in the package.
Only one of the four combinations passes, so it cannot be made green by manufacturing the
57 % error v1's T5 would have forced.

**Pin B — surface identity at the *physical* radius, sphere and hemisphere.** Verified
exact today (`1.000000000000` both). Under a uniform factor it breaks in opposite
directions: at 4π the hemisphere reads 2.000000, at 2π the sphere reads 0.500000. So Pin B
forces the assignment to be **per geometry** — precisely the double-correction failure mode
R2 named and v1 then committed. v1 evaluated this at `equivalent_radius_um`, the equal-area
*disc* radius, which is why it read 2.000 and 1.414.

**Pin C — band and microwire against the FD Laplace table** (C0.6 oracle):
`|R_eq-sphere / R_FD − 1| < 0.05` for aspect 0.39–2.0 and `< 0.20` to aspect 10.

Scope also includes: `environment` as an instance field with the five presets tagged
(physics M5); `access_resistance_is_exact = False` on those presets (ledger 21); and
threading the electrode through `io/fem.compare_with_point_source`, which today calls
`potential_V` with no `electrode=` and would otherwise become a new 2× inconsistency inside
the utility C7.3's validation claim rests on (physics m4).

**`TestKuncelGrill2004` is rewritten in this commit, not cited as a guard** (physics B3).
It never calls `potential_V` and cannot detect the double-correction. Verified: today's 2 %
agreement is a coincidence of two errors — at Kuncel & Grill's own stated σ = 0.2 S/m the
equal-area sphere gives 578.8 Ω against an FD-true 586.4 Ω (1.3 %; 573.3 Ω, +1.0 %, after C3.7's converged table, ledger 127) and against their
*conservatively assumed* 500 Ω (+15.8 %); their published 0.0993 A/cm² back-solves to
508.8 Ω, an assumed clinical impedance, not a FEM spreading resistance. The test asserts
that, and its docstring stops attributing 0.0993 A/cm² to their finite element model.

### 5.4 Phase 4 — provenance (9 commits)

| # | subject | closes | test that must fail first | why it cannot pass tautologically |
|---|---|---|---|---|
| C4.1 | `fix(materials): stop a user CIC inheriting another source's citations` | 24, 25, 30 | new: `with_measured_cic(Pt, 100).chronic_threshold` must not report Rose & Robblee's platinum-dissolution reference as its own; `MeasuredRange(low=1, high=nan)` must raise; **`ChronicThreshold` gains `verified` and it must roll into `Material.verified`, the JSON and the PDF provenance rows** | The expected reference key is the *absence* of `rose_robblee1990` on a user material — asserted against `references.py`, not against the material. Entry 30's data-model change is named explicitly (execution M7). |
| C4.2 | `fix(safety): use the correct half-window and a single polarity convention` | 7, 8 | new: AIROF at its own CIC (1000 µC/cm²) must land **on** the window edge, not return +0.4286 V headroom; `anodic_first` and `anodic_first_for_capacitance` must not be independently settable | **Split out of v1's C4.2** (execution M6): v1 folded 7 and 8 into the provenance commit on a *location* argument, and neither of its named tests touches the half-window denominator or the polarity disagreement. Entry 8 is anti-conservative — the narrower half-window sits in the denominator of `C = limit/available_V`, so it enlarges C and understates the excursion. |
| C4.3 | `fix(safety): propagate PROVISIONAL to every quantity derived from an unverified limit` | 19, 60, **128** | **T7** — asserted on **every** check in the assessment, not a named three; today the water window returns a clean PASS with the excursion reduced 4× | The oracle is the provenance graph: every check whose value depends on `effective_capacitance_uF_cm2` must carry the flag. Asserted by dependency, not by enumeration. **Scope extended by ledger 128 (Phase 3 review H2):** a provisional binding check must mark the limiting current itself -- on `describe()`, the PDF header, the GUI headline and the figure annotation -- not only the JSON `checks[]` row. That covers the monotonicity cap's binder too. |
| C4.4 | `fix(io): carry provenance and the audit record into the JSON and the PDF` | 54, 59 | new: two reports differing only in `resting_potential_V` (0.0 vs 0.35) must not render identical settings sections; `report_to_json` must carry `verified`, the reference key and the package version | The oracle is a byte diff of two reports plus a schema assertion. Verified: `assessment.json`'s `settings` block holds only `shannon_k`, `cic_policy`, `tissue_conductivity_S_per_m`, `compliance_V` — 4 of 11. `neurostim/audit.py` already builds the full record and `build_report` never calls it. Must also carry `counter_electrode` from C3.5. |
| C4.5 | `fix(literature): use Leung's pulse-width-matched Pt in-vivo derating` | 71 | new: pin 3.2×–8.7× against Leung et al.'s own sentence; today 2–14× from a mismatched-pulse-width division | The expected bounds are quoted from the source text, on the existing `test_literature.py` pattern. |
| C4.6 | `fix(literature): attribute the 316LVM 20 uC/cm2 figure to its real source` | 72, 73 | new: pin the quoted sentence; the figure is a tissue-damage number from a cited chapter, not Riedy & Walter's corrosion result, and it drives `recommended_policy` | Quoted source text. |
| C4.7 | `fix(literature): repair seven condition and derivation defects` | 77 (S-6, S-7, S-8, S-10, S-11, S-12, S-13) | one assertion per item, each quoting its source sentence | Quoted source text. **Note:** entry 77's header says "Eight" but lists seven — S-9 belongs to entry 76 (execution m4). Reconciled here. |
| C4.8 | `fix(references): resolve elwassif2006 to the paper the values were read from` | 45, 75, 78/S-19, 78/S-20 | new: the DOI, volume and pages in `references.py` must match the conference proceedings `data/elwassif2006.py` transcribes | The expected metadata is read from the PDF in `papers_stim_calc_ref/`. Also records ledger 45's discrepancy (`10 × √(185 × 210e-6) = 1.971 V`, not the paper's 1.56 V, which implies 131.5 µs) in the data module rather than "correcting" the source. |
| C4.9 | `fix(literature): eleven lower-severity corrections` | 78 (S-14…S-18, S-21…S-23, S-25) | per item; S-14's zero-width `separating_k_range()` (both bounds 1.69897) is the one that changes a computed value | Each pinned to its source sentence; S-14 pinned to the k values the package actually uses. |

### 5.5 Phase 5 — io, viz, gui (11 commits)

| # | subject | closes | test that must fail first | why it cannot pass tautologically |
|---|---|---|---|---|
| C5.1 | `fix(viz): forward the calculator's settings AND its candidate set to every panel` | 48 | new, **two** assertions: at `k=1.2, σ=0.10` panel (b)'s annotated binding limit must equal the assessment's (6880 vs 4869.59 µA today); **and** `annotation_value == assessment.limiting_current_uA` for a microelectrode case | **Execution B3:** v1 fixed only the settings forwarding. `viz/plots.py:184-205` computes `binding = min(shannon, cic, compliance)` from the 0.1.0-compat properties, independently of `limiting_current_uA`. Verified the artist annotates `binding limit 141 µA` against a headline that becomes 20.00. The oracle is the assessment object, which the figure does not currently consult. **Third assertion (C1.5 edge):** when `unsafe_at_any_amplitude` is non-empty the figure must draw no binding-limit line and annotate the naming text instead — this is the surface C1.5 could not reach, because `viz` computes its own minimum until this commit. |
| C5.2 | `fix(viz): draw the separatrix that decided the verdict` | 55 | new: scrape the artists — a line at `calc.k` must exist | Artist scraping; the expected value is the calculator setting. |
| C5.3 | `fix(viz): carry pass/fail in marker shape as well as colour` | 56 | new: pass and fail artists must differ in a non-colour property | Artist scraping. |
| C5.4 | `fix(viz): stop save_publication truncating names at a decimal point` | 58 | new: `save_publication(fig,"shannon_k1.5")` and `"shannon_k1.8"` must not collide | Filesystem state. |
| C5.5 | `fix(io): distinguish an empty batch from a clean batch` | 51, 61/M4, 61/M14 | new: a header-only CSV must raise or return a frame **with** `status`/`error` columns; an errored row must not be all-NaN; `df.min()` must not silently report the one good row; a read error must name the file | Frame schema assertions. The row-error contract itself landed at C1.9. |
| C5.6 | `fix(io): print an applied value and its limit at distinguishable precision` | 50 | new: no rendered sentence may read `X exceeds the X limit` | A regex over rendered output; the expected relation is inequality of the two rendered strings. |
| C5.7 | `fix(io): resolve every citation the report text names` | 53 | new: every author-year in the rendered body must appear in the bibliography; `brummer_turner1977` dangles today | Set difference between two independently produced sets. |
| C5.8 | `fix(gui): surface every exception and update text and canvas atomically` | 57, 62/L3 | new: a raising plot call must leave the process alive and put the traceback in the results pane; today exit code 134 (SIGABRT) | Process exit code and pane contents. |
| C5.9 | `fix(io): emit RFC 8259 JSON and a compressed TIFF` | 61/M12, 61/M13, **87** | new: `json.loads` under a strict parser on output forced to contain a NaN; TIFF ≤ journal cap, no alpha channel, **and `pil_kwargs={"compression": "tiff_lzw"}` asserted on the written file's tags** | A third-party-grade parser and file metadata, not the emitter. Ledger 87 (deferred out of Phase 0 because it changes the bytes of a package output): the TIFF is written uncompressed at 47 MB and LZW cuts it roughly tenfold at no quality cost. |
| C5.10 | `fix(io): repair the FEM import path` | 61/M5, M6, M7, M8, M9 | new, five assertions: `compare_with_point_source` must reject a 10⁶ potential error **and take the electrode** (C3.1 edge); `_match_column` must raise on ambiguous aliases; duplicate positions must raise; a single NaN must not collapse `describe()` to "nan to nan V"; `save_field`/`load_field` must round-trip `current_uA` and `note` | M5 and M9 lose data and are separated from the bundle. Round-trip asserted against the input values. |
| C5.11 | `fix(io,viz): nine further io/viz defects` | 61/M1, M2, M3, M10, M11; 62/L1, L2, L4, L5 | one assertion each | M1's headline half already landed at C1.1; what remains here is the per-row caveat rendering. |

### 5.6 Phase 6 — physical models (6 commits; C6.3 depends on C3.1)

| # | subject | closes | test that must fail first | why it cannot pass tautologically |
|---|---|---|---|---|
| C6.1 | `fix(models): reject unphysical strength-duration fits and report their uncertainty` | 33, 37 | **T6** — `fit_weiss` on a negative-chronaxie design must raise; today returns `chronaxie_us=-60`, `tau=nan`, `rss=5.4e-22`. Plus: `curve_fit`'s covariance must reach the caller as an SE/CI | The design is generated from a known `t_c = −60 µs`, so the expected rejection is a property of the input. The CI is checked against a 4000-replicate synthetic recovery (sd 27 µs, 95 % CI [153, 258] at true 200 µs). |
| C6.2 | `fix(models): reject a rank-deficient strength-duration design` | 38 | new: `fit_weiss([100,100,100],[40,41,39])` must raise rather than return `rheobase 20, chronaxie 100` behind a bare numpy RankWarning | **Split out of C6.1** (execution M7): the negative-chronaxie test takes a different path and cannot fail for a rank-deficient design. |
| C6.3 | `fix(models): derive the thermal source radius from the electrode's own access resistance` | 32, 34 | new: `a_eff_um = 1e6/(4πσ·R_access)` — the electro-thermal analogy — and the printed rise must match Elwassif's reproduction, **not** any internal value | **T19 as v1 wrote it is a tautology** (execution M1): "matches `peak_temperature_rise_K` for the SAME geometry" holds for the equal-area disc radius, the equal-area sphere radius and the geometry-exact radius alike. The pin is Elwassif's own 0.8200 K, which the analytic solution reproduces to 1.2 % (0.8298 K) — the only external anchor the model has, and preserved by construction since `a_eff` reduces to `a` for a sphere. Verified: `a_eff` for the equal-area sphere equals the equal-area sphere radius exactly (690.11 µm), against today's 1380.22 µm — exactly 2×. |
| C6.4 | `fix(models): make the transient step independent of the other requested times` | 35, 36, 42 | new: `t=1e-3` alone and `t=1e-3` inside `logspace(-3,3.5,60)` must agree to < 1 %; −15.0 % today. Make `max_cells` a parameter and warn loudly when it clamps | The oracle is the same time evaluated two ways; neither is the expected value of the other, and the agreement threshold is independent of both. |
| C6.5 | `fix(models): surface the current-distance spread and stop clamping a fitted offset` | 39, 40, 41 | new: `evaluate(100).describe()` must carry the 300–27 000 µA/mm² k range (854× in volume); `sensitivity.analyse()` must cover thermal and VTA parameters or stop claiming "every limit"; a negative fitted offset must not be silently clamped to 0.0 | The k range is quoted from the docstring's own cited source. **Entry 41 moved here from v1's C6.1** — it lives in `models/vta.py` (execution M7). |
| C6.6 | `fix(units,uncertainty): guard non-finite inputs and round intervals outward` | 23, 26, 27, 31, 43, 44 | **T10** extensions; `Interval(0.1,0.1)*3` must contain 0.3; `Interval(-1,1).square()` must be `[0,1]` | Containment of an exact decimal by a float interval is an IEEE property. Implement outward rounding as a one-ulp `math.nextafter` pad in `_binary` and add `square()`/`__pow__`; do **not** attempt general dependency tracking (§8). |

### 5.7 Phase 7 — release, documentation, CI (7 commits)

| # | subject | closes | test that must fail first |
|---|---|---|---|
| C7.1 | `chore: add the MIT LICENSE the metadata has always declared` | packaging (CRITICAL) | file presence; needs the real copyright holder and year from the user |
| C7.2 | `chore: single-source the version from package metadata` | 47 | new: `neurostim.__version__`, `pyproject.toml`, `CITATION.cff` and the installed distribution must agree; today 0.15.0 vs 0.13.0 |
| C7.3 | `docs: correct the FEM validation claim and its stated cause` | 46 | new: assert the reproduction figure appears and the "lead and electrode self-heating" cause does not |
| C7.4 | `docs: refresh the README from the generated transcript` | 74, 76, 78/S-24 | new: the README quick-start block must equal C0.4's generated block byte for byte |
| C7.5 | `docs: add paper.md, paper.bib, CONTRIBUTING and CODE_OF_CONDUCT` | packaging (JOSS) | paper builds. **CONTRIBUTING must carry the merge policy the ledger gate depends on: no squash-merge and no rebase onto the default branch**, because the ledger's Commit column records the hash as made |
| C7.6 | `ci: gate on provenance, transcription, coverage, mutation, determinism and the ledger` | 68, T21, T22, T25, T26 | each gate must go red on a seeded violation before it is wired in |
| C7.7 | `docs: CHANGELOG for 0.16.0 with a recall notice for earlier reports` | doc drift | presence of the recall notice naming the defect, the 7.07× figure and the affected version range |

C7.3 is precise because ledger 46 settles what is true: the analytic solution reproduces
Elwassif's 0.8200 K to **1.2 %** (0.8298 K) on that paper's own parameters. Therefore
(a) CITATION.cff's "validated against a published finite element model" is an overclaim *as
written* and becomes "reproduces the published steady-state temperature rise of Elwassif et
al. (2006) to 1.2 % when given that paper's own parameters"; (b) README's "that gap is not
reconciled" is **stale**, not false, and is replaced by the reconciliation — the gap is the
protocol power difference (72.66 µW vs 5.639 mW, 78×) and nothing else; (c) the stated
**cause is wrong** in both README and `examples/worked_example.py`, which blame Elwassif's
"lead and electrode self-heating"; their shaft is thermally insulated and their source is
`σ|∇V|²` in tissue only.

C7.4 is now a byte comparison rather than a hand edit, because C0.4 generates the block.
Verified stale today at README `:40`, `:135`, `:136`, `:140`: `Limiting current: 70.69 uA`
(which is not a current at all — it is the Pt chronic FAIL ceiling for that geometry),
`across published ranges: 70.69-212.1 uA`, a transcript showing 5 checks where `assess()`
emits 9, a threshold of 1.70 where the default is 1.50, and a 50 µC/cm² Pt limit where the
code uses 100.

### 5.8 Phases at a glance

| phase | commits | ids |
|---|---|---|
| 0 harness and oracles | 6 | C0.1–C0.6 |
| 1 verdict core | 11 | C1.1–C1.11 |
| 2 data model | 5 | C2.1–C2.5 |
| 3 space, distribution, counter electrode | 6 | C3.1–C3.6 |
| 4 provenance | 9 | C4.1–C4.9 |
| 5 io, viz, gui | 11 | C5.1–C5.11 |
| 6 physical models | 6 | C6.1–C6.6 |
| 7 release, docs, CI | 7 | C7.1–C7.7 |

### 5.9 Commit count

**61**, of which **6 are landed** (Phase 0; Phase 0b added 9 follow-up commits that land no
new plan item).
6 + 11 + 5 + 6 + 9 + 11 + 6 + 7 = 61, enumerated above.

v1 said 41 and enumerated 50. v2 as first written was 59 — it added C0.3, C0.5, C0.6, C1.8
(the interval widening), C2.3, C3.4, C4.2, C5.10, C6.2 (nine new) and merged none. The
amendment after Phase 0 added **C1.5** (ledger 84); the amendment after Phase 0b adds
**C1.2** (the resting-potential window rejection, split out of C1.9 and moved six commits
earlier). Phase 1 renumbered twice: what this plan first called C1.4–C1.9 is now C1.6–C1.11.
No commit was merged or removed.

---

## 6. Blast radius — every number that moves

Thirty-six rows. The ten surfaces v1 omitted are marked **[+]**; the two v1 booked wrongly
are marked **[!]**; the three added after Phase 0 are marked **[84]**.

| fix | quantity | before → after | also update in the same commit |
|---|---|---|---|
| C1.2 | `SafetyCalculator(..., resting_potential_V=...)` outside the material's window | silently accepted → `ValueError`. Previously-constructible calculators stop constructing, and `max_charge_density_in_window_uC_cm2('Pt', resting_potential_V=5.0)` stops returning 1400 µC/cm² "allowed" | `water_window.py` docstrings, README settings table, GUI field validation; two oracle guard tests re-pointed at a stub |
| C1.3 | any back-solved limit at its own boundary | `100.00000000000001` → `100.0`; 12/54 combinations stop failing their own check | — |
| C1.10 **[88]** | `limiting_current_uA` for a resting potential within ~1e-7 V of a window edge | `LimitDidNotSettle` raised out of `assess()` → a number again (`DiscElectrode(100,"Pt")`, 200 µs, `resting_potential_V = -0.59999999`, `C = 103 µF/cm²`: raise → 4.0448e-07 µA). Measured 4487 of 70 831 edge-clustered configurations raising before, 0 of 40 000 after. No committed number moves — these configurations produced no output at all | `_limits.py` and `_water_window_ceiling_uA` docstrings, D2 point 3 |
| C1.3 | rendered limits, text and PDF | `141.4 µA` → `141.3 µA`; `472.8` → `472.7` | README transcript, PDF/JSON goldens |
| C1.3 **[+]** | GUI headline string (`gui/app.py:332`, `:.4g`) | `141.4 uA` → `141.3 uA`, then `20.00` after C1.6 | GUI snapshot test |
| C1.3 **[+]** | figure annotation (`viz/plots.py:211`, `:.3g`) | verified `binding limit 141 µA` → `141.3`, then `20.00` after C5.1 | `figure_summary.{svg,pdf}` |
| C1.3 **[+]** | `Interval.describe()` low bound | `141.4-212.1 uA` → `141.3-212.0 uA` | README `:136`, `:140` |
| C1.3 **[89]** | `sensitivity.describe()` baseline and every row (`sensitivity.py:60-61`, `:167`, `:.4g`) | `DiscElectrode(60,"Pt")` at 100 µs: `14.14 uA` → `14.13 uA`; 100 of 243 swept configurations printed a limit strictly larger than the limit | `Sensitivity.describe` docstring |
| C1.3 **[89]** | `examples/worked_example.py` §2, §4 and §5 amplitudes (`:.4g`, `:8.1f`, `:.1f`) | `Shannon allows: 472.8` → `472.7`; `Electrode allows: 141.4` → `141.3`; `max current with measured limit: 87.7` → `87.65`; `Binding limit: 20` → `20.00`; the `max uA` and `CIC limit` columns go through `format_limit` | `example_output/` is regenerated by this example, and is untracked; the README transcript comes from `describe()` and does not move |
| C1.3 **[96]** | `cic_limit_uC_cm2`, rendered on four surfaces (`safety/charge.py:152`, `safety/assessment.py` both Charge-injection branches, `io/report.py`) | `:.4g` → `format_limit`. Pt/PtIr at `medium="in_vivo"`, `policy="conservative"`: limit `7.142857142857143`, was printing `7.143`, now `7.142`. Round-number limits gain the sig-digit form: the worked example's `100 uC/cm^2` → `100.0 uC/cm^2` | README transcript (**regenerated**), PDF golden, check-summary goldens |
| C1.3 **[96]** | the published charge-injection **range** (`safety/charge.py` `published range` line) | hand-rolled `{lo:.4g}-{hi:.4g}` → `Interval.describe('uC/cm^2', floor=True)`, matching the µA interval beside it: `7.143-10.71` → `7.142-10.71` | `charge.describe()` golden |
| C1.3 **[96]** | `threshold_A_per_cm2` (`safety/assessment.py` both Current-density branches, `data/butterwick2007.py`) | `:.4g` → `format_limit`. A power law in pulse width and electrode size, so round only by accident: **32 of 56 swept (diameter, pulse width) pairs overstated**. On the worked example itself `0.3057` → `0.3056` for a threshold of `0.3056762856382303` | README transcript (**regenerated**), `assessment.json`, PDF |
| C1.5 **[89]** | `sensitivity.analyse()` / `.describe()` for a protocol with an amplitude-independent failure | nine bare amplitudes headed `baseline: 1.529e+04 uA (Shannon criterion)` → `analyse` raises `sensitivity.UnsafeAtAnyAmplitude` and `describe` prints `none -- no amplitude is safe: Charge balance FAILs at every amplitude` in place of the ranking | `sensitivity` module docstring; the sixth render surface after `describe()`, JSON, PDF, GUI and the figure |
| C1.3 **[+]** | `report()["max_current_cic_uA"]`, `["max_current_shannon_uA"]`, `["max_charge_shannon_uC"]` | raw floats move by ≤ 2 ulp | all three are columns in `example_output/current_sweep.csv` — **regenerate** (v1 said "no user-visible digit changes"; under C0.4's byte regime a one-ulp change *is* a byte change) |
| C1.4 **[+]** | `assessment.json` `checks[].margin` | `null` → float for Water window and Chronic degradation (verified 5 of 9 are `null` today) | `example_output/assessment.json` schema, JSON consumer docs |
| C1.4 | `Check` schema | gains `kind`, `provisional` | JSON, PDF check table, GUI table |
| C1.5 **[84]** | headline for any protocol with an amplitude-independent failure | a bare number → an explicit "no amplitude is safe (Charge balance FAILs)". Verified: the monophasic band prints `Limiting current: 1.529e+04 uA (Shannon tissue-damage criterion)` today against an oracle ceiling of 0.0 | `describe()` golden, `report_to_json` schema, PDF header, GUI headline; the figure follows at C5.1 |
| C1.5 **[84]** | `SafetyAssessment` schema | gains `unsafe_at_any_amplitude` | `assessment.json` schema, JSON consumer docs |
| C1.5 **[92]** | `SafetyAssessment.limiting_current_uA` **type** | `float` → `float \| None`, `None` exactly when `unsafe_at_any_amplitude`; the raw minimum over `LIMIT_BEARING` keeps its definition under the new name `limit_bearing_ceiling_uA`. **API change** — a consumer that does not handle the `None` stops typechecking (`mypy neurostim` is a CI gate). No *value* moves: `report()["limiting_current_uA"]` was already `None` for these protocols | `describe()`, `io/report.py`, `gui/app.py`, `viz/plots.py`, `sensitivity.py`, `examples/worked_example.py`; the interval / by-kind / oracle round-trip tests re-pointed at `limit_bearing_ceiling_uA` |
| C1.6 | worked-example limiting current | **141.37 → 20.00 µA (7.0686×)**; mechanism `Pt charge-injection limit` → `Microelectrode charge/phase`. Independently confirmed by binary search: first FAIL at 20.000000000000004 | `assessment.json`, `current_sweep.csv` (`limiting_current_uA` and `limiting_mechanism` on every row), `figure_summary.*`, README transcript, CHANGELOG, `limiting_current_uA` docstring |
| C1.6 | `limits_incomplete`, `limiting_current_by_kind` | new fields | `describe()`, JSON, PDF, GUI |
| C1.7 **[+]** | `limiting_mechanism` **value** where the named check did not run | verified `DiscElectrode(40,"PEDOT")` at 200 µs: **99.6724 µA "(Shannon tissue-damage criterion)"** while Shannon is NOT_EVALUATED → the real binding mechanism | `current_sweep.csv` `limiting_mechanism` column |
| C1.6 **[95]** | `limiting_mechanism` **vocabulary**, on every row including rows where no number moved | the strings are now `Check.name` lookups, not phrases composed in `assessment.py`: `'SS316LVM charge-injection limit'` → `'Charge injection limit'` (the material name is gone), `'Shannon tissue-damage criterion'` → `'Shannon criterion'`, `'stimulator compliance voltage'` → `'Compliance voltage'`. **Breaking for a documented column**: a downstream filter on `"charge-injection"` now matches nothing, with no number to notice | `current_sweep.csv` and every batch CSV, JSON consumer docs, CHANGELOG |
| C1.5 **[95]** | `report()["limiting_mechanism"]` for an unsafe protocol | a check name → a **sentence**: `'no amplitude is safe: Charge balance FAILs at every amplitude'`. The `limiting_current_uA → None` half was booked; the companion column turning into prose in the same CSV was not | `current_sweep.csv`, batch CSVs, JSON consumer docs |
| C1.4 **[95]** | `checks[].ceiling_uA` in `assessment.json` | new field (`io/tabular.py:225`). The C1.4 row above books the `Check` schema gaining `kind` and `provisional` and stops there | `assessment.json` schema, JSON consumer docs |
| C1.1 **[95]** | `report()["status"]` for every macroelectrode | `'NOT_EVALUATED'` → `'PASS'`/`'CAUTION'`/`'FAIL'` as the checks warrant (verified `DiscElectrode(2000,"SIROF")` → `'CAUTION'`). The C1.1 row above books the `Status.rank` docstring, the README table and the JSON/PDF/GUI headline — not this dict key, which is the `status` column of `current_sweep.csv` and of every batch CSV, and the column `assess_batch` writes `"ERROR"` into after C1.9 | `current_sweep.csv`, batch CSVs, README status table |
| C1.6 **[95]** | `limiting_current_uA` **beyond the worked example** | the C1.6 row above names only the worked example while the preamble promises every number that moves. Verified at HEAD: `DiscElectrode(60,"TiN")` 282.74 → **20.0**; `DiscElectrode(40,"PEDOT")` 99.67 → **20.0**; `DiscElectrode(800,"Ta2O5")` 1993.45 → **1382.8469376062583** with the mechanism moving Shannon → Current density; `DiscElectrode(100,"Pt")` 39.27 → **19.634954084936204** | `current_sweep.csv`, batch CSVs, any downstream numbers |
| C1.8 **[+]** | `limiting_current_interval_uA` and its `describe()` line | verified `[141.37166941154072, 212.05750411731108]` → an interval that contains 20.00; `contains()` False in 18/18 cases today | README `:136` and `:140`, `describe()` golden |
| C1.1 | overall status of every macroelectrode | `NOT_EVALUATED` → `PASS`/`CAUTION`/`FAIL` as the checks warrant | `Status.rank` docstring, README status table, **JSON/PDF/GUI headline in the same commit** |
| C2.1 **[+]** | `asdict(calc.p)` in `assessment.json` | gains `charge_recovery_ratio` and `train_duty_cycle` (verified the protocol block has 8 keys today) | `assessment.json`, batch CSV aliases, GUI form |
| ~~C2.1 **[84]**~~ | ~~headline for an unbalanced **biphasic** protocol~~ | **DOES NOT FIRE.** Booked on the pre-D6 design in which Charge balance FAILed for any imbalance. Under D6 a partially recovered biphasic pulse is a CAUTION there and keeps a numeric `limiting_current_uA`; the suppression fires only for a waveform that recovers nothing, which is monophasic and was already covered by the C1.5 rows. Verified at C2.1: `charge_recovery_ratio=0.999` on `DiscElectrode(500,"Pt")` leaves `unsafe_at_any_amplitude` empty. | — |
| C2.2 | `required_V`, `J_avg` for `return_phase_ratio ≠ 1` | 0.524 V → ~2.6 V; 0.0167 → 0.0836 A/cm² peak at r = 0.2 | compliance + current-density docstrings |
| C2.2 **[+]** | `limiting_current_uA` / `limiting_mechanism` for **asymmetric** protocols | the current-density margin is in the candidate set after C1.6, so the headline moves for every `return_phase_ratio ≠ 1` | plus an assertion that symmetric protocols are byte-identical across this commit |
| C2.2 **[106]** | concrete movers of the row above, executed | `CylindricalBandElectrode(1270,1500,"PtIr")`, 1000 µA/90 µs/130 Hz, r = 0.2, `capacitance_uF_cm2 = 250` (ledger 4's fixture; relabelled from `compliance_V = 250` at ledger 121, and the value is the same under either setting or neither): `limiting_current_uA` **15285.50941588086 → 9565.660239570918 µA**, mechanism Shannon criterion → **Current density**; `DiscElectrode(500,"SIROF")`, 500 µA/50 µs/130 Hz, r = 0.25: **998.0887516949169 → 461.0459210402362 µA** (Current density) | `current_sweep.csv` unaffected (symmetric protocols) |
| C2.4 | monophasic charge-injection limit | a number → NOT_EVALUATED, `limits_incomplete = True` | README "What it computes" table, `charge.py` module docstring |
| C2.3 **[91]** | monophasic water-window **ceiling** (`_water_window_ceiling_uA`) | `99745.56675147594` µA (pulse-peak inverse) → **`767.2735903959689` µA** as reported (`Q_window / (PW·f·T)` = `767.2735903959687` is the seed, which `floor_to_pass` settles two ulps up; corrected at C2.10, ledger 106(e), and now asserted to the bit), a factor of `f·T = 130`. **`_water_window_seed_uA` must gain the drift term in the same commit as the clause**: the peak-only seed is 8.7e17 ulps above the new boundary against a 4-float budget, so `floor_to_pass` raises on every monophasic protocol otherwise. Pinned by `TestTheWaterWindowSeedInvertsItsOwnPredicate` | `_water_window_seed_uA` docstring (carries the expression), `assessment.json`, `current_sweep.csv` |
| C2.4 | monophasic water-window verdict | PASS with 0.58 V headroom → **FAIL, drift time 0.256 s** (verified 0.2558 s) | water_window docstring, PDF |
| C2.4 | monophasic ~~`limiting_current_uA`~~ **`limit_bearing_ceiling_uA`** | **Corrected at C2.10 (ledger 106(b)):** every monophasic protocol FAILs Charge balance, so `limiting_current_uA` is `None` for all of them and prints the refusal. The cap and the drift ceiling move only `limit_bearing_ceiling_uA`: capped at the biphasic value, **0.0 for a continuous train**. Executed: `DiscElectrode(100,"Pt")`, 80 µA/200 µs/130 Hz/1 s monophasic → `limit_bearing_ceiling_uA` **19.634954084936204 → 0.4531143250369894 µA** (the biphasic twin's 19.634954084936204, Chronic degradation, is the cap and does not bind), `limiting_current_uA` `None` | JSON, PDF, GUI |
| C2.4 **[106]** | `SafetyAssessment` and `report_to_json` schema | gains `biphasic_ceiling_uA` and `biphasic_mechanism` (attributes) and a `monotonicity_capped` JSON key | `assessment.json` schema, JSON consumer docs |
| C2.3a **[99, 106]** | headline for a protocol whose limit-bearing ceiling is 0.0 while nothing is amplitude-independently FAILing (resting potential on the window edge; any continuous train with unrecovered charge) | `Limiting current: 0 uA (Water window)` → the refusal `no amplitude is safe: Water window permits no current at all`; `limiting_current_uA` `0.0` → `None` (`limit_bearing_ceiling_uA` keeps 0.0). Executed: `DiscElectrode(100,"Pt")`, 80 µA/200 µs/130 Hz/1 s, `resting_potential_V = -0.6`. Ledger 99 measured 12 240 of 299 520 swept water-window configurations with a zero ceiling | `describe()`, PDF header, GUI headline, figure annotation, `sensitivity` |
| C2.3a **[99, 106]** | `report()["limiting_mechanism"]` for those rows | a check name (`'Water window'`) → a **sentence** (`'no amplitude is safe: Water window permits no current at all'`); the CSV column carries prose for these rows, as C1.5 already made it for amplitude-independent failures | `current_sweep.csv`, batch CSVs, JSON consumer docs |
| C2.3a **[99, 106]** | `report_to_json` schema | gains `permits_no_current` (list of check names) beside `unsafe_at_any_amplitude` | `assessment.json` schema, JSON consumer docs |
| C2.5 | envelope excursion list | the pulse-duty entry is removed; a train-duty entry appears | `EnvelopeResult.describe()` golden. `report()["duty_cycle"]` is **unchanged** (0.052) — v1 would have moved it; v2 does not |
| C2.7 **[100]** | `charge.evaluate` policy warning (`safety/charge.py`, both numbers), on `ChargeResult.describe()`, the PDF and every surface that prints it | `:g` → `format_limit`. The only warning reachable from the shipped database is SS316LVM's, whose numbers are round, so the visible change is the four-significant-digit form: `applies 30 uC/cm^2 … end at 20 uC/cm^2` → `applies 30.00 … 20.00` (nominal), `applies 40` → `applies 40.00` (optimistic). Latent overstatement removed: a derated or midpoint limit printed high, e.g. Pt in vivo nominal `100/14 = 7.142857142857143` as `7.14286` → `7.142`, optimistic `10.714285714285714` as `10.7143` → `10.71` | PDF golden (`tests/test_gui.py` policy-warning assertion updated to `20.00`); not in the README transcript or `example_output/` (default policy is conservative) |
| C2.7 **[98]** | Shannon limits (`shannon_max_charge_uC`, `shannon_max_current_uA`, hence `assess()`) for a non-round `k` on a small electrode | `LimitDidNotSettle` raised out of `assess()` → a number (`DiscElectrode(5.586476331363039,"Pt")`, 10 µA/200 µs, `k = 1.642880206146527`; also the package's own `K_MODERATE = 1.7` at 2.845538350306074e-07 cm²). Edge-clustered sweep: 2535 of 165 300 raising before, 0 after. **Water window moved too (ledger 106(d))**: the water window also declares a plateau, so option A widened its walk down and turned many of ledger 104's partial-recovery raises into numbers. The review measured 2 439 → 576 raises over its 16 200-configuration grid; the same grid shape re-run here at `cf3b843` and `e07114d` gives 2 607 → 606. Each is the boundary of a predicate that is monotone at the returned point, and C2.8 then removed the remaining raises at their source. **No returned value moves**: over 60 810 further scratch configurations (random `k` 1.0–2.5 and area 1e-12–10 cm², plus `assess()` over 9 materials × 5 diameters × 3 pulse widths × 3 resting potentials × 2 polarities), every configuration that returned a number before returns the identical float; the 811 that raised now return | `_limits.py` and `shannon.py` docstrings, D2 point 2 |
| C2.8 **[103, 104]** | unrecovered charge for any biphasic protocol with `charge_recovery_ratio != 1` (`net_charge_per_pulse_uC`, `net_dc_current_uA`, the water-window drift ceiling and every `limit_bearing_ceiling_uA` it binds) | a difference of two products → `charge_uC(I, W) * (1 - r_a)`, the same value in exact arithmetic. Last-digit moves only: over 9 504 swept configurations (9 materials × 4 diameters × 2 PW × r_a {0, .5, .9, .99, .999, 1, 1.2} × r {1, .3, 3} × T {1, 3600, inf} × I {10, 500} × waveform), 1 836 `limit_bearing_ceiling_uA` values move by at most 1.12e-13 relative (e.g. AIROF 40 µm, 50 µs, r_a 0.9, 1 s: 19.332877868244893 → 19.332877868244886), 4 474 `net_dc_current_uA` values by at most 1.32e-13, and **0 statuses change**. Monophasic and `r_a ∈ {0, 1}` are byte-identical. Raises out of `assess()` → numbers: 124 `LimitDidNotSettle` of those 9 504 before, 0 after. The reviewer's balanced-asymmetric population (`r ≠ 1`, `r_a = 1`) goes from `ZeroDivisionError`, a spurious Water window FAIL and a 393.37 µA headline above FAILing amplitudes to drift-free, with a headline that matches the independent bisection | `current_sweep.csv` is unaffected (all its rows have `r_a = 1`); `protocol.py` and `_water_window_seed_uA` docstrings |
| C2.9 **[105]** | water-window drift clause, and therefore its ceiling, for every biphasic protocol that under-recovers (`0 < r_a < 1`) | budget `Q_window` → `Q_window − r_a·Q` (the recovered part of each pulse rides on the offset). Drift times and ceilings only **fall**, the conservative direction. Review case (`DiscElectrode(500,"Pt")`, C = 250, 200 µs, 50 Hz, 1 s, r_a 0.99, 1227.184630308513 µA): Water window CAUTION "reaches the edge in 2.4 s" → **FAIL "0.42 s"**; ceiling **1472.6215563702156 → 988.3366150135672 µA**. Over 9 504 swept configurations (as for C2.8): 4 608 change, all with r_a ∈ {0.5, 0.9, 0.99, 0.999}; 2 090 `limit_bearing_ceiling_uA` / `limiting_current_uA` values fall by a factor of 0.8734–0.999998, none rise; 9 Water window verdicts CAUTION → FAIL (no overall status moves: each was already FAIL); **monophasic, balanced and over-recovering (r_a 1.2) protocols are byte-identical**, so ledger 2's 0.2558 s and 767.2735903959689 µA do not move. Example: Pt 500 µm, 50 µs, r_a 0.5, 1 s: 90.62286500739789 → 89.93108741192157 µA. `test_the_ceiling_converges_to_the_monophasic_one_as_recovery_vanishes` asserted 2× at r_a = 0.5; the model now gives `2·fT/(fT+1)` = 260/131 at fT = 130, and the assertion says so | `water_window.py` `DcDrift` docstring, `_water_window_seed_uA` docstring; not in `example_output/` (every example protocol is balanced) |
| C3.0 **[108]** | `WaterWindowResult.describe()` header and headroom label, for a protocol that drifts (on `describe()` and in the PDF check detail) | header `-> PASS` → `-> EXCEEDS (peak within window; drift reaches the edge within the train)` when drift exits, or `-> PASS (peak within window; drift reaches the edge after the train)` when it does not; `headroom` → `peak headroom`. Executed on ledger 2's case (band, 3000 µA/90 µs/130 Hz monophasic, C = 250). **Protocols that do not drift are byte-identical**, so the README transcript does not move | PDF detail golden, if any |
| C3.1 | planar `potential_V` | **2.00× larger** (22.7364 → 45.4728 mV at the audit's reference point) | `field.py` docstrings, README "Field — exact for a sphere" |
| C3.1 **[+]** | `io/fem.compare_with_point_source` | the same 2× **when the electrode is passed**: it gains an `electrode=` keyword threaded to `potential_V`. `None` keeps the full-space point source, documented, so an existing call does not move silently in either direction | `io/fem.py`, and C7.3's validation claim depends on it |
| C3.1 **[+]** | `viz/plots.py:309-334` field panel | the same 2× | `figure_summary.*` |
| C3.1 | DBS band access resistance | **517.5 → 329.5 Ω (−36.3 %)** (equal-area sphere, not v1's 470.7); aspect 0.39: 900.6 → 573.3 Ω | compliance numbers in `example_output`, `access_resistance_ohm` column in `current_sweep.csv` |
| C3.1 | `access_resistance_is_exact` on ~~five~~ **four** presets | `True` → `False`. **Corrected at C3.1:** `rose_robblee_typeA` is a real flush disc ("a smooth disk, 1.1 mm diam, cut from Pt foil and mounted in a silicone rubber support", rose1990) and stays exact, as physics M5 itself says. Tags, each from its paper: `mccreery_microelectrode` is penetrating ("inserted approximately 1.5 mm deep into the parietal cortex", mccreery1990), so full-space; `mccreery2010_chronic` is full-space and inexact, but its paper is not in the library, so the tag is unverified (ledger 124); `beebe_iridium_wire` is a stub through a silicone septum (beebe1988), so half-space and inexact; `weiland_tin` is half-space and inexact because its paper is not in the library. The two full-space presets' resistances move with the substitute: **15 698.587 → 9 994.031 Ω** and **28 288.543 → 18 009.046 Ω** (both ×2/π). `describe()` names the stand-in | `describe()` output, PDF electrode section |
| C3.1 **[+]** | every `CylindricalBandElectrode` and `MicrowireElectrode` access resistance, and therefore its required compliance voltage and compliance ceiling | half-space equal-area disc → full-space equal-area sphere, exactly ×2/π = 0.6366 for every instance (`dbs_kuncel` 519.566 → 330.766 Ω). Worked example §6, `CylindricalBandElectrode(1270,1500)` at 3000 µA/60 µs/130 Hz with 10 V compliance: `limiting_mechanism` **Compliance voltage → Shannon criterion**. The band's symmetric `required_V` at 1000 µA/90 µs, C = 250: **0.5235321306516268 → 0.3354767487193873 V**; with r = 0.2 **2.593599433515108 → 1.6533225238539098 V** | `example_output/` (untracked), the C2.2 test goldens (re-measured, stated in the test) |
| C3.1 **[+]** | worked-example thermal rise (`examples/worked_example.py` §7) | **5.396 → 3.435 mK** (dissipated 72.66 → 46.26 µW), because the power is `I_rms² · R_access` and `R_access` fell. The C6.3 row below said this number moves once, at C6.3. It moves twice, and the C6.3 row's *before* is now 3.435 mK | `examples/worked_example.py` output (untracked) |
| C3.1 **[+]** | PDF access-resistance label (`io/report.py`) | `equal-area disc approximation` → the electrode's own substitute: `equal-area sphere approximation` for a band or microwire, `equal-area disc for <stand-in> approximation` for a tagged preset | PDF |
| C3.1 **[+]** | `Electrode` API | gains `environment` (instance field, class default) and `equivalent_sphere_radius_um`, and `DiscElectrode` gains `stands_in_for`. Positional construction is unchanged (the new fields follow `material`) | README, CHANGELOG |
| C3.2 **[18]** | Current density check **detail** for every non-disc geometry (`describe()`, the PDF check detail) | the disc's `centre 0.50x average` / `outer 25 % ... diverges at the rim` → `uniform primary distribution: J = I/A everywhere ...` for sphere and hemisphere, and `current crowds at this geometry's edges ...; the disc's centre and area-fraction figures do not apply` for ring, rectangle, band, microwire and any stand-in disc. **No margin, ceiling or status moves**, pinned bit for bit: the Butterwick comparison uses the average. The README transcript does not move, because it prints summaries | PDF detail golden, if any |
| C3.2 **[18]** | `current_density` API | `evaluate(..., electrode=)`; `CurrentDensityResult.distribution`; `centre_ratio` and `fraction_above_average` become `float \| None`; `ratio_at_area_fraction` raises unless the distribution is the disc's. `electrode=None` reproduces the old disc answer | — |
| C3.3 **[10]** | ring and rectangle access-resistance **docstrings** and the README limitation | direction corrected: the equal-area disc *over*estimates, as an upper bound. **No number moves** | — |
| C3.4 **[28, 29]** | arrays with a non-finite pitch, coincident or non-finite site positions; a microwire with `cone_height_um` on a flat or hemispherical tip | silently constructed → `ValueError`. `linear_array(disc, 3, nan).min_pitch_um()` was `nan`; two coincident sites gave `0.0`; `MicrowireElectrode(50, 0, "flat", 999999.)` had the flat wire's area. No constructible input's number moves | CHANGELOG |
| C3.5 | bipolar required compliance | ~~1.571 V → 431.7/659.0 × 3.142 = 2.06 V~~ **Corrected at C3.5, re-measured after C3.1 moved the band's resistance:** 3389 contact, 3000 µA/90 µs/130 Hz, derived C: monopolar **1.0064302461581618 V** (unchanged by C3.5); with `counter_electrode` = the same contact at 2 mm, **1.3488137938726137 V** (×1.340). Ohmic **431.5586831502678 Ω** against 658.92 naive. Active polarisation 0.018 V; the counter's is **0.036 V**, because the counter carries the anodic phase and PtIr's anodic C_eff is 125 against 250 µF/cm² (ledger 8, C4.2). Far apart, identical interfaces give exactly 2× (pinned on TiN, whose two polarities agree). Unchanged when no counter is supplied | README compliance formula row |
| C3.5 | monopolar compliance **status** | `PASS` → `CAUTION` with the stated assumption: `"...(8 % used); monopolar single-interface budget assumed -- supply counter_electrode for a two-terminal estimate"`. `FAIL` and `NOT_EVALUATED` are unchanged. **The README quick-start transcript is regenerated in this commit** (its Compliance line changes). No number moves | JSON, PDF, GUI, README transcript |
| C3.5 | `SafetyCalculator` and `compliance.evaluate` API | gain `counter_electrode` and `counter_separation_um`, validated at construction; `ComplianceResult` gains the counter's resistance, the mutual term, its area, capacitance and polarisation, and `counter_modelled`. Reaches the compliance detail, the PDF row (breakdown now adds the counter polarisation, or states the monopolar assumption) and `sensitivity`. Not yet the batch CSV, the GUI, or the `report_to_json`/`audit` settings record (ledger 126: C4.4, C5.5, C5.8) | C4.4 |
| C3.6 **[12]** | Shannon check **status** and `provisional` for every non-disc geometry (ring, rectangle, band, microwire, sphere, hemisphere, stand-in disc) | an unqualified `PASS` → `CAUTION` ("fit on discs, not this geometry"), with Shannon's diameter sentence in the detail; `provisional` `False` → `True` whatever the status. **The limit's value does not move** (asserted). Over 168 swept configurations (7 geometries × 4 sizes × 3 amplitudes × 2 widths) 42 Shannon checks change, 39 of them PASS → CAUTION and the other 3 already CAUTION (only `provisional` moves), and **no overall verdict and no limit moves**, because the monopolar compliance CAUTION (C3.5) already held each at CAUTION. A real disc is unchanged | JSON `checks[].provisional`, PDF |
| C3.7 **[127]** | the FD band reference (`tests/oracles/fd_band`) and every documented sphere accuracy | table regenerated converged: clinical **335.1 → 327.6 Ω**, aspect 0.2 739.9 → 653.4, 0.39 559.8 → 520.4, 0.5 502.2 → 473.7, 1.0 363.7 → 353.8, 2.0 255.0 → 252.3, 4.0 172.1 → 171.8, 10 96.3 → 96.7. Documented sphere accuracy "within 2 % (−1.7 % clinical)" → **high at every aspect: +0.6 % clinical, +0.3 to +1.2 % aspect 1–2, +7 to +10 % at 0.39–0.5, +17 to +23 % at the extremes**. **No package number moves**: the package computes the sphere; only the oracle and the prose change | base.py, volumetric.py, compliance.py docstrings, README, CHANGELOG, ledger 16/20 notes, D4 and §8 notes |
| ~~C3.9 **[131]**~~ **REVERSED at C3.12 (ledger 135)** | `required_V`, `compliance.max_current_uA` and every compliance-bound limit, for any material whose C_eff differs by polarity (Pt, PtIr, AIROF, PEDOT, SIROF, TIROF) | the return phase polarises the active electrode at the opposite polarity's C_eff and the counter at the leading one's (was: leading polarity for both, both phases). **Both directions.** Over 144 swept configurations (all 9 materials × 2 polarities × r {1, 0.25} × counter/none × 2 disc sizes, 50 µA/200 µs, 5 V) 72 `required_V` move, every one on the six materials whose C_eff differs by polarity (TiN, SS316LVM and Ta2O5 are unchanged): 48 up and 24 down, by a factor of 0.8686 to 1.4162; 24 `limit_bearing_ceiling_uA` move; **no status moves**. Worked example (330/270 Pt ring, 80 µA/200 µs/130 Hz, 10 V): `required_compliance_V` **0.8286922987786409 → 1.0550459956204477 V**, compliance ceiling **965.3764143567779 → 758.2607804027908 µA** (oracle-pinned), `limiting_current_by_kind['instrument']` likewise. Goldens: Pt disc 100 µm 1.957730451487647 → 2.7726037601181512 V; SIROF disc 500 µm 1.4300993160251108 → 1.4306086118430048 V | **README transcript regenerated** (by-kind line and Compliance line), `current_sweep.csv`/JSON (untracked) |
| C3.10 **[130, 132]** | counter-electrode inputs closer than the two half-extents; the drift-CAUTION water-window detail header | a 3389 band pair at 1390–1500 µm centre spacing: a resistance (e.g. 334.1 Ω at 1400 µm) → `ValueError` (the guard is now max(equal-area substitute radius, half the largest dimension)); `-> PASS (peak within window; drift reaches the edge after the train)` → `-> CAUTION (...)`. No number of a valid input moves | CHANGELOG |
| C3.8 **[129]** | access resistance of `MicrowireElectrode(d, 0, "flat")` (no exposed shaft), and its required compliance and compliance ceiling | full-space equal-area sphere `1/(2πσa)` → Newman half-space disc `1/(4σa)`, exactly ×π/2 = 1.5708. `MicrowireElectrode(50, 0, "flat")`: **18189.136353359467 → 28571.428571428572 Ω**; at 10 µA/100 µs/130 Hz, 5 V: `required_V` **0.5893280178488467 → 0.6931509400295378 V**, compliance `max_current_uA` **84.84239419416879 → 72.13436080440043 µA**. Every other microwire, and hemispherical or conical tips with no shaft, unchanged. The README transcript does not move | README Known limitations, CHANGELOG; the solver and table are committed (`scripts/fd_microwire_reference.py`, `tests/oracles/fd_microwire.py`) |
| C3.11 **[133]** | assessments **with** a `counter_electrode`: a new limit-bearing check, *Counter charge injection*, and every limit it now binds | a 10th check appears (NOT_EVALUATED for monophasic), in `checks[]`, describe, JSON, PDF and GUI tables. It can bind the headline: over 160 swept configurations (5 materials × 2 active sizes × 4 counter sizes × 2 polarities × 2 amplitudes, 200 µs, 10 V, 50 mm spacing) **36 `limit_bearing_ceiling_uA` values fall, none rise, the mechanism becomes *Counter charge injection* in all 36, and 17 verdicts go CAUTION → FAIL**. Example: `DiscElectrode(200,"Pt")` with a `DiscElectrode(50,"Pt")` counter, cathodic-first, **78.53981633974482 µA (Chronic degradation) → 4.908738521234051 µA (Counter charge injection)**, i.e. Pt's anodic-first 50 µC/cm² over the counter's area. C3.5's booked 3389 bipolar headline is unchanged (15285.50941588086 µA, Shannon). `LIMIT_BEARING` goes from 7 to 8 (D3 amended). **Assessments without a counter are byte-identical**: the check is not emitted, and the README transcript does not move | D3, README table and limitations, compliance docstring, CHANGELOG, the oracle's `LIMIT_BEARING` and `COUNTER_ONLY_CHECKS` |
| C3.12 **[135]** | the return-phase term of `required_V` (active and counter), and every compliance ceiling and limit it bound; **reverses C3.9's row** | return phase `I_ret·R + ΔV(full return charge, opposite-polarity C)` (C3.9), before that `I_ret·R + ΔV(full return charge, leading C)` (C2.2) → **`I_ret·R + ΔV(overshoot (r_a−1)·Q, opposite-polarity C)`**, exactly `I_ret·R` when r_a ≤ 1. **Worked example restored exactly**: `required_compliance_V` 1.0550459956204477 → **0.8286922987786409 V**, compliance ceiling 758.2607804027908 → **965.3764143567779 µA** (oracle-pinned); README transcript regenerated and **byte-identical to the pre-C3.9 transcript**. Goldens restored: Pt disc 100 µm 2.7726037601181512 → 1.957730451487647 V, SIROF disc 1.4306086118430048 → 1.4300993160251108 V. Band r = 0.2 (C2.2's own case, C = 250): **1.6533225238539098 → 1.647307218918153 V**. Over 432 swept configurations (9 materials × 2 polarities × r {1, 0.25} × r_a {0.8, 1, 1.3} × counter/none × 2 sizes): **against C3.9, 314 fall, 0 rise, ×0.548–0.9996; against pre-C3.9, 288 fall, 0 rise, ×0.560–0.9997**, all where the return phase bound (r < 1, or r_a = 1.3), 90 limits move, no status moves; **every symmetric balanced (r = 1, r_a = 1) configuration has every number, status and limit identical to pre-C3.9**, but not its text (corrected at C3.22, ledger 145): the compliance detail's diagnostic `return phase` line now prints `I_ret·R`, e.g. Pt 500 µm disc, 80 µA/200 µs/130 Hz: `return phase  0.261 V (80 uA x 200 us)` → `return phase  0.229 V (80 uA x 200 us)`. Measured at 9d1d503 against a9f2432 over 144 balanced no-counter configurations (9 materials × disc 100/500 µm, ring, 3389 band × polarity × compliance none/10 V): 0 numbers, statuses or limits differ; 134 describe() outputs differ in that line; 8 of them also differ in C3.15's interval line, and nothing else differs. The review measured 1 800 of 4 608 against a9f2432, only in that line | compliance docstring, CHANGELOG (the C3.9 entry replaced), README transcript |
| C3.16 **[139]** | the counter-separation guard's reach (`compliance._reach_um`) | the enclosing sphere replaces half the largest dimension for rectangles (half the diagonal), bands and exposed microwires (`sqrt(r^2 + (L/2)^2)`, L = exposed length plus the tip cap). Presets: dbs_3389 and dbs_3387 750.0 → 982.7130812195388 µm, dbs_kuncel 750.0 → 979.4896630388705 µm; the other 7 presets unchanged. A 3389 pair at 1500–1965.4261624390776 µm now raises `ValueError` (at 1800 µm it returned total 406.29599377060197 Ω, mutual 252.6268937966593 Ω); the 2 and 3 mm clinical spacings are still accepted. No number of an accepted input moves | CHANGELOG |
| C3.17 **[140]** | `required_V`, `max_current_uA` and the Compliance voltage ceiling of every **unbalanced** protocol (Charge balance's own test); the train's DC offset `(N − 1)·\|1 − r_a\|·Q`, `N = ceil(n_pulses)` with `train_duty_cycle`, on the leading phase (under-recovery, monophasic) or the return overshoot (over-recovery), capped at the active electrode's water-window headroom from `resting_potential_V`, uncapped on the counter and for Ta2O5 | Sweep of 3240 configurations (5 materials × disc 100/500 µm and 3389 band × monophasic/1.0/0.95/0.8/1.3 recovery × ratio 1/0.25 × polarity × counter × train 0.05 s/1 s/continuous × duty 1/0.2, 100 µA/200 µs/130 Hz, 10 V): balanced **720/720 byte-identical**; unbalanced 2049 of 2520 `required_V` rise (×1.000061–×116.99, 504 to inf), none fall; Compliance status 388 PASS → FAIL, 86 CAUTION → FAIL; `limiting_current_uA` moves in 372 (228 down, 144 number → None, the latter all continuous with a counter or Ta2O5). Examples, Pt 500 µm disc, r_a = 0.95: 1 s train 0.3264579511458109 → 0.5892545931791486 V, max 3063.1816333165516 → 2879.390735317558 µA; continuous 0.3264579511458109 → 0.9264579511458109 V; continuous with a 900 µm Pt counter 0.5057912365478305 → inf V, max 1977.1002890941431 → 0.0 µA; Ta2O5 500 µm continuous 0.7950101036083507 → inf V, limit 540.1745850024447 µA → None (Compliance voltage). r_a = 1.3, 1 s: 0.39587477068748655 → 1.1958747706874866 V. Worked example and README transcript unchanged | README compliance row and limitations; CHANGELOG |
| C3.18 **[141]** | the Water window drift clause's window budget, and through it the Water window verdict, ceiling and limiting current, for **over-recovering** waveforms with a **derived** capacitance (a measured `capacitance_uF_cm2` is unchanged): `C_eff` of the drift's own polarity instead of the leading one | Sweep of 16 848 configurations (9 materials × disc 100/500 µm and 3389 band × monophasic/1.0/0.95/0.8/1.05/1.3/1.5 recovery × ratio 1/0.25 × polarity × 20/300 µA × 0.05 s/1 s/continuous × rest 0/−0.2 V × derived/measured C; 200 µs, 130 Hz): 2592 change, every one over-recovery with a derived C; TiN, SS316LVM and Ta2O5 unchanged. `time_to_exit_s` scales by the branch ratio (×0.5, ×2, ×0.75, ×1.333, ×0.635, ×1.575, ×0.667, ×1.5). Water-window ceiling 732 down, 708 up, ×0.5–×2.0; status CAUTION → FAIL 34, FAIL → CAUTION 56; `limiting_current_uA` 254 down, 298 up. Examples, Pt 500 µm disc, 300 µA/200 µs/130 Hz/1 s, r_a 1.3: cathodic-first ceiling 50.34603611522104 → 25.17301805761052 µA, t_exit 0.16782012038407015 → 0.08391006019203508 s; anodic-first 18.87976354320789 → 37.75952708641578 µA. Pt 100 µm, 20 µA, 0.05 s, r_a 1.5, cathodic-first: CAUTION → FAIL (t_exit 0.060415243338265257 → 0.030207621669132628 s); r_a 1.3 anodic-first: FAIL → CAUTION (0.03775952708641577 → 0.07551905417283154 s). The capped compliance offset now implies a Water window FAIL in every case (0 exceptions, was 34) | README DC-drift limitation; CHANGELOG |
| C3.15 **[136]** | the ends of `ChargeResult.max_current_interval_uA` and the Counter charge injection interval (now `SafetyAssessment.counter_charge_interval_uA`), each floored through the point's own predicate | Sweep of 3600 random configurations (3000 active, 600 with a counter; 9 materials, 3 policies, saline/in vivo, both polarities, recovery 1.0/1.2/1.5): 3602 interval ends move, by at most 3 ulps; 252 aggregate `limiting_current_interval_uA` move; no ceiling, `limit_bearing_ceiling_uA` or `limiting_current_uA` moves. A per-check ceiling outside its own interval: 1029 → 0. Text mover, booked at C3.22 (ledger 145): where the published range is a single value (SS316LVM), the interval was 1–2 ulps wide and printed as a range, `across published ranges: 7.853-7.853 uA (Shannon k 1.5-2.0, full material range, chronic threshold band)`. It is now exact: `across published ranges: 7.853 uA (unchanged: Charge injection limit has no published range; ...)`. The same for the 500 µm disc, 196.3-196.3 → 196.3 uA. Pinned: `DiscElectrode(50, "Pt")` at 50 µs, conservative, saline, point 39.26990816987241 against a closed-form low end of 39.26990816987242, now 39.26990816987241 | CHANGELOG |
| C3.19 **[142]** | the water-window plateau (`_water_window_search`), which now includes `\|edge − rest\|` for both edges | Only inputs that raised `LimitDidNotSettle` change: the reviewer's `DiscElectrode(570.7046435217787, "TiN")`, 10 µA/200 µs/20 Hz anodic-first at −0.2 V, and 6 of 40 000 far-side configurations (all TiN) now return a ceiling on their own predicate's boundary. Previously returned floats: 0 of 5 000 uniform-rest, 0 of 39 994 far-side and 0 of 16 848 C3.18-sweep ceilings, statuses and limits change | CHANGELOG |
| C3.20 **[143]** | every render of an unbounded compliance requirement, and the JSON/CSV schema | Render sweep of 1 152 configurations (4 materials × 4 recoveries × 3 trains × 3 compliance settings × counter × 2 rests × disc/band) against 7537e8f: every finite case's describe(), PDF row and summaries are byte-identical; the JSON of every finite, non-continuous case is identical apart from the new `null_reasons` ({}) and `results.required_compliance_note` ("") keys. Continuous trains change text only: "(inf s)" → "during continuous stimulation" (216 lines), "after inf unbalanced pulses" → "over a continuous unbalanced train", "inf V" → "unbounded" or the refusal sentence, the headroom line dropped when unbounded (120), "drop out of regulation above 0 uA" → "no amplitude of this protocol is within the compliance voltage" (148, all at 0 uA). JSON: `protocol.train_duration_s` `Infinity` → `null` for every continuous train (pre-existing), `results.required_compliance_V` `Infinity` → `null`; `report()['required_compliance_V']` inf → None. No number, status or limit moves | README report()/JSON paragraph; CHANGELOG |
| C3.21 **[144]** | documentation only: the compliance docstring and README's "upper bound" for the train offset | Documented, not modelled: a correction would add a second kink to the compliance back-solve, in a regime that never bears a limit. Stated bound: `min(N·e/(C_opp·A), H_opp)` with `e = max(0, Q − Q_edge)`. Measured against the clamped whole-train oracle: 42 of 1 500 over-recovery configurations below it, by up to 6.7 %, 0 outside the bound, all Water window FAIL. No number moves | README limitations; compliance module docstring |
| C4.0a **[146, 147]** | `protocol_from_dict` (null duration), new `protocol_from_report`; the `assess_batch` / `current_sweep` frames' `limiting_current_uA` and `required_compliance_V` columns (float64 with NaN → object with None) | A continuous report's protocol round-trips (`TypeError` → equal `StimProtocol`). A bare `null` duration with no reason: `TypeError` → named `ValueError`. Frames: over 300 random batch rows, 12 `required_compliance_V` NaN → None and 197 `limiting_current_uA` rows now None in every batch composition. `to_csv` output byte-identical. No number moves | README report()/JSON paragraph; CHANGELOG |
| C4.3 | water-window headroom under an unverified CIC | clean PASS → CAUTION/PROVISIONAL; `C_eff = 103 µF/cm²` gains its provenance | PDF provenance section, JSON, README `:15` and `:205-206` |
| C4.5 | Pt in-vivo derating range | 2–14× → 3.2–8.7× | `data/cogan2016.py` docstring, any derated limit |
| C6.3 **[!]** | worked-example thermal rise | **5.3961 → 8.0612 mK (×1.494)**, booked **once**, here, at the post-C3.1 access resistance. **Corrected at C3.1:** C3.1 moves it too (5.396 → 3.435 mK, row above), so the *before* at this commit is 3.435 mK. v1's 24.060 mK is the *unperfused* analytic value at the *old* 517.5 Ω and is wrong twice. Cross-check: the FD-true 335.1 Ω gives 8.3639 mK, 3.6 % away | `examples/worked_example.py` narration, `data/elwassif2006.py` (7.5 mW → 5.639 mW, 325 → 431.6 Ω in four docstrings — these are Elwassif's own quantities and are independent of C3.1), README thermal claim |
| C5.9 **[84]** | `example_output/figure_summary.tiff` | 47 001 446 bytes uncompressed → roughly a tenth, LZW, no alpha (ledger 87) | the TIFF left the repo at C0.4, so this changes only what `save_publication` writes for users |
| C4.9 | `separating_k_range()` | zero-width `[1.69897, 1.69897]` → a band that contains the k values the package uses | `shannon.py` docstring |

**Artifacts regenerated by C0.4's script, once per numeric commit:**
`example_output/assessment.json`, `current_sweep.csv`, `figure_summary.{svg,pdf}`,
`figure_strength_duration.{svg,pdf}`, `safety_report.pdf`, **and the README quick-start
block**. The 47 MB TIFF leaves the repo at C0.4. Numeric commits are C1.1, C1.3, C1.4,
C1.5, C1.6, C1.7, C1.8, C2.1, C2.2, C2.4, C2.5, C3.1, C3.5, C4.3, C4.5, C4.9, C5.1, C5.9,
C6.3.

**Loose exports outside the repo.** Five PDFs in `~/Downloads/` carry the pre-fix headline:
`neurostim_report_1.pdf`, `_2.pdf`, `_4.pdf`, `_A.pdf`, `_B.pdf`. They cannot be
repaired by a commit. Two actions: (a) C7.7's CHANGELOG carries an explicit recall notice
naming the defect, the 7.07× figure and the affected version range; (b) C4.4 stamps the
package version and the `audit.py` SHA-256 digest onto every future PDF, which is the
structural fix. The five existing files should be deleted or regenerated by the user; this
plan does not touch files outside the repo.

---

## 7. Risk register

**R1 — C1.3 + C1.6, the limit floor and the widened minimum. Highest risk.**
It changes the most prominent number in every output by 7.07×, and the floor operates at
the last ulp where an off-by-one reintroduces the exact defect being fixed, in the opposite
direction.
*Proof:* C0.6's independently written binary search — **not** `min(c.margin × I)`, which is
the implementation restated (execution M1). T2a over 9 × 3 × 2 with both boundary
directions; `floor_to_pass(v)` passes and `nextafter(v, +inf)` does not; a property test
over random `(area, pulse_width, k)`; and the cross-surface gate (§10 G9) so the figure,
the GUI, the CSV and the PDF cannot drift apart.

**R2 — C3.1, the half-space/full-space convention. Second highest.**
The same 2× appears in `_geometry_factor`, in `access_resistance_ohm`, and implicitly in the
thermal source term, and the legitimate disc-vs-sphere factor is π/2. The failure mode is
double-correcting.
*Proof:* Pin A (the exact disc oracle) verified to admit exactly one of four (factor × R)
combinations; Pin B (sphere and hemisphere surface identity at the physical radius) verified
to break in opposite directions under a uniform factor; Pin C (the FD band table). v1's
named second pin, `TestKuncelGrill2004`, is withdrawn — it never calls `potential_V` and
goes red under D4 either way.

**R3 — C2.1, the return-phase data model. Third highest.**
Widest blast radius of any single commit: `protocol.py`, `safety/current_density.py`,
`safety/compliance.py`, `safety/assessment.py`, `io/tabular.py`, `io/report.py`,
`gui/app.py` — **7 modules** and **79** `StimProtocol(` call sites in `tests/` (measured;
v1 said ~150). The failure mode is a silent default change.
*Proof:* a golden capture of `calc.report()` for a spread of existing protocols before the
commit, asserted byte-identical after; T12 and T13; `rms_current_uA` and
`average_current_uA` re-derived by hand for one asymmetric case.

**R4 — C2.4 interacting with C1.1 and D3.** v1's version of this was a live regression
(110 inversions). v2's is a monotonicity cap plus a drift model, so the failure mode is now
*under*-reach: a drift model that is wired into the report but not into the candidate set.
*Proof:* T4(a) asserts **strict** inequality on the 110 previously-inverting cases, which
the cap alone cannot satisfy.

**R5 — C4.3, provenance propagation.** Risk is under-reach: the flag must follow the derived
quantity through `effective_capacitance_uF_cm2` → `polarisation_V` → water window →
compliance → PDF → JSON, and stopping one hop short is precisely defect 60.
*Proof:* T7 asserted on *every* check, plus an assertion that the JSON and the PDF carry the
same provenance set.

**R6 — C6.3, the thermal radius.** Three candidate radii differ by 2× and π, and C3.1 moves
the access resistance underneath it.
*Proof:* the electro-thermal analogy makes the radius a derived quantity rather than a
choice (`a_eff = 1/(4πσR)`), the Elwassif 0.8200 K anchor is preserved by construction for a
sphere, and the FD cross-check agrees to 3.6 %.

**R7 — C0.4's byte-comparison regime, new in v2.** Every numeric commit must regenerate
eight artifacts plus the README block, and a missed regeneration reddens CI on an unrelated
commit. Mitigated by C0.3 landing determinism first (verified 5 of 8 artifacts are
non-deterministic today) and by the regeneration being one script invocation.

---

## 8. What not to fix — document as a limitation instead

All five of v1's refusals are retained; the physics review endorsed each and found nothing
in this section above MINOR. One is amended and one is added.

**Ledger 12 — Shannon on non-disc geometries. Do not add a perimeter correction.**
Shannon p.425 gives a mechanism ("the limit of safe stimulation is linearly related to
electrode **diameter**… probably due to the charge 'building up' at the edges"), not a
functional form, and this bibliography contains none for a ring, band, rectangle or
microwire. C3.6 attaches a geometry caveat and returns CAUTION. **v2 amendment (physics
m6):** it also sets `Check.provisional`, so a caveated Shannon limit is visible when it
binds the headline. The limit's value does not change.

**Ledger 16 — no closed form for a band on an insulating shaft. New in v2.** Against the
converged FV solve (C3.7, ledger 127) the equal-area sphere is high at every aspect: +0.3 to
+1.2 % from aspect 1 to 2 (clinical +0.6 %), +7 to +10 % at 0.39–0.5, and +17 to +23 % at
aspects 10 and 0.2. (It was written here as "within 2 % over 0.39–2.0" from an unconverged
table.) No compact exact solution exists. v1's `ln(2L/r)` form is rejected for its
negativity, non-monotonicity and anti-conservative error at 0.39, not for accuracy at every
aspect. Document the accuracy, keep the entry open.

**Ledger 22 — no array-level safety API. Do not build one.**
No source here quantifies current sharing between simultaneously-driven sites. Fix: state
the caution in `ArrayElectrode.describe()` and in the docstrings of `total_area_cm2` and
`mean_area_cm2` ("this is a geometric sum; dividing total charge by it is not a safety
calculation"), and correct the module docstring to say the caution is *stated*, not
*modelled*.

**Ledger 45 — Elwassif's own arithmetic is unreproducible.** Do not "correct" the source.
Record the discrepancy in `data/elwassif2006.py` (C4.8).

**Ledger 23 — the interval dependency problem.** Implement `square()`/`__pow__` correctly
and stop. General dependency tracking is an affine-arithmetic rewrite; the hazard is latent
(the Shannon `k = log10(Q²/A)` interval path cannot be run at all today). Document that
`x*x` is not `x.square()`.

**Ledger 36 — thermal domain truncation saturating at 0.075 %.** Do not raise `max_cells` by
default. Make it a parameter, warn loudly when it clamps, and replace the docstring's
"increase `domain_extent_factor` if you need better" — which is false — with the measured
saturation figures (400a 0.249 %, 1000a 0.101 %, 2000a 0.075 %, 5000a 0.075 %, 20000a
0.075 %, ideal 0.005 %).

**Not fixed and now explicitly declared: the chronic check binds acute protocols.**
The physics review is right that a platinum-dissolution threshold setting the binding
amplitude for a one-second train is odd. But no source here gives a train-duration cut-off,
so gating it would be an unsourced number. `Check.kind = "electrode-chronic"` plus
`limiting_current_by_kind` makes it visible instead; the user decides.

---

## 9. Ledger coverage — all 82 entries, sub-findings broken out

Reuses the execution review's appendix mapping, remapped to v2 commit ids. Verdict key:
**OK** = commit named and its test can fail before / pass after · **DOC** = deliberate
non-fix, disclosed in §8 · **N/A** = no action needed. Every v1 verdict of TEST-WEAK,
BLOCKED, PARTIAL or LISTED-ONLY has been repaired; the repair is named in the note.

| # | sev | v1 verdict | v2 commit(s) | note |
|---|---|---|---|---|
| 1 | CRIT | TEST-WEAK | C1.4, C1.5, C1.6, C1.7, C1.8 | tautology replaced by the C0.6 binary search; interval, `report()` floats and the figure now have commits |
| 2 | HIGH | BLOCKED | C2.3, C2.4 | T4 rewritten as four assertions; drift model supplies a *lower* limit |
| 3 | HIGH | OK | C2.1, C2.3 | field renamed; FAIL criterion sourced |
| 4 | HIGH | OK | C2.2 | §6 now books the limiting-current move |
| 5 | HIGH | OK | C3.5 | **FIXED** `978c1da`; default CAUTION; mutual term modelled |
| 6 | HIGH | TEST-WEAK | C2.5 | excursion deleted, so the percent/fraction trap is gone |
| 7 | MED | LISTED-ONLY | C4.2 | split out, with a polarity test. **Owns the counter-2× re-check (moved here from row 8 by ledger 134):** C3.5's counter uses the opposite boolean polarity's C_eff (Pt/PtIr 250 against 125 µF/cm², from CIC 150/100 × half-window 0.6/0.8 V). If C4.2 changes these branches, re-check D7's 2× for Pt/PtIr and update `TestTheCounterElectrodeEntersTheVoltageBudget` |
| 8 | MED | LISTED-ONLY | C4.2 | split out, with the half-window test; ledger row repaired at C0.5. C3.5's counter-electrode 2× relation for Pt/PtIr (pinned on TiN only) comes from the polarity-specific CIC (1.5×) *and* half-window (1.33×). Ledger 8's own fix, the `anodic_first=None` `min()` branch, does not reach the counter path. **Re-check it only if C4.2 also changes `effective_capacitance_uF_cm2`'s boolean branches (ledger 7)**, and update `TestTheCounterElectrodeEntersTheVoltageBudget` if so (corrected by ledger 134) |
| 9 | HIGH | OK | C1.3 | T2 split into T2a (here) and T2b (C1.6) |
| 10 | MED | OK | C3.3 | **FIXED** `c327cee`; elliptic-disc pin |
| 11 | MED | OK | C1.1 | T17 verified reachable |
| 12 | MED | DOC | C3.6 | **FIXED** `114604a`; value unchanged; `provisional` flag added |
| 13 | LOW | OK | C1.9 | |
| 14 | LOW | OK | C1.2, C1.9 | split: the window check lands at C1.2 (D2's monotonicity precondition), the non-finite class at C1.9 |
| 15 | LOW | OK | C2.1 | |
| 16 | LOW | BLOCKED | — (DOC, §8) | cylinder override rejected; documented limitation |
| 17 | HIGH | BLOCKED | C3.1 | **FIXED** `a010103`; Pin A + Pin B replace the false invariant |
| 18 | HIGH | OK | C3.2 | **FIXED** `0c3e79a`; signature change named |
| 19 | HIGH | OK | C4.3 | |
| 20 | MED | BLOCKED | C3.1 | **FIXED** `a010103`; equal-area sphere |
| 21 | MED | OK | C3.1 | **FIXED** `a010103` |
| 22 | MED | DOC | — | §8 |
| 23 | MED | DOC | C6.6 | `square()`/`__pow__` only |
| 24 | MED | OK | C4.1 | |
| 25 | MED | OK | C4.1 | |
| 26 | LOW | OK | C6.6 | |
| 27 | LOW | OK | C6.6 | |
| 28 | LOW | LISTED-ONLY | C3.4 | **FIXED** `d5136df`; own commit |
| 29 | LOW | LISTED-ONLY | C3.4 | **FIXED** `d5136df`; own commit |
| 30 | LOW | LISTED-ONLY | C4.1 | `verified` field + provenance rollup named |
| 31 | LOW | OK | C6.6 | |
| 32 | HIGH | TEST-WEAK | C6.3 | pinned to Elwassif 0.8200 K, not to itself; booked once |
| 33 | HIGH | OK | C6.1 | |
| 34 | MED | OK | C6.3 | |
| 35 | MED | OK | C6.4 | |
| 36 | MED | DOC | C6.4 | measured saturation figures |
| 37 | MED | OK | C6.1 | |
| 38 | MED | LISTED-ONLY | C6.2 | own commit |
| 39 | MED | OK | C6.5 | |
| 40 | MED | OK | C6.5 | |
| 41 | MED | LISTED-ONLY | C6.5 | moved to the VTA commit |
| 42 | LOW | OK | C6.4 | |
| 43 | LOW | OK | C6.6 | |
| 44 | LOW | OK | C6.6 | |
| 45 | LOW | DOC | C4.8 | discrepancy recorded |
| 46 | HIGH | OK | C7.3 | ledger row repaired at C0.5 |
| 47 | HIGH | OK | C7.2 | |
| 48 | CRIT | PARTIAL | C5.1 | candidate set rebuilt from the assessment |
| 49 | CRIT | PARTIAL | C1.3 | GUI, figure and `Interval.describe` added to scope |
| 50 | HIGH | OK | C5.6 | |
| 51 | HIGH | OK | C5.5 | row-error contract landed at C1.9 |
| 52 | HIGH | OK | C1.9 | |
| 53 | HIGH | OK | C5.7 | |
| 54 | HIGH | OK | C4.4 | also carries `counter_electrode` |
| 55 | HIGH | OK | C5.2 | |
| 56 | HIGH | OK | C5.3 | |
| 57 | HIGH | OK | C5.8 | |
| 58 | HIGH | OK | C5.4 | |
| 59 | HIGH | OK | C4.4 | |
| 60 | HIGH | OK | C4.3 | |
| 61/M1 | MED | OK | C1.1 + C5.11 | headline caveat pulled forward ~30 commits |
| 61/M2 | MED | OK | C5.11 | |
| 61/M3 | MED | OK | C5.11 | |
| 61/M4 | MED | OK | C5.5 | |
| 61/M5 | MED | OK | C5.10 | unbundled; also C3.1's electrode threading |
| 61/M6 | MED | OK | C5.10 | |
| 61/M7 | MED | OK | C5.10 | |
| 61/M8 | MED | OK | C5.10 | |
| 61/M9 | MED | OK | C5.10 | unbundled |
| 61/M10 | MED | OK | C5.11 | |
| 61/M11 | MED | OK | C5.11 | |
| 61/M12 | MED | OK | C0.4, C5.9 | TIFF 47 001 446 bytes |
| 61/M13 | MED | OK | C5.9 | test must force a NaN |
| 61/M14 | MED | OK | C5.5 | mapping label corrected from v1's `62/L-M14` |
| 62/L1 | LOW | OK | C5.11 | |
| 62/L2 | LOW | OK | C5.11 | |
| 62/L3 | LOW | OK | C5.8 | |
| 62/L4 | LOW | OK | C5.11 | |
| 62/L5 | LOW | OK | C5.11 | |
| 63 | HIGH | PARTIAL | C0.1, C0.2, C1.10 | coverage sub-claims reconciled in §3; mutation gate in §10 |
| 64 | HIGH | OK | C1.10 | |
| 65 | HIGH | OK | C0.2 | |
| 66 | HIGH | TEST-WEAK | C1.6 | binary-search oracle |
| 67(a) | HIGH | OK | C1.10, C2.5 | assigned once in §9, as in v1's §2 |
| 67(b) | HIGH | OK | C2.1 | **re-assigned from C1.10** (Phase 1 review F9). The unbalanced-biphasic Charge-balance FAIL branch cannot be reached until imbalance is expressible, which is C2.1; C1.10 could not close it and correctly did not. The row was unsatisfiable as written and must not be used as a Phase-2 exit criterion against C1.10 |
| 67(c) | HIGH | OK | C1.1 | |
| 68 | MED | PARTIAL | C0.1, C7.6 | branch floor now implementable (§3) |
| 69 | MED | PARTIAL | C0.2, C0.5, C1.11, C3.5 | **FIXED** `978c1da` (T18 landed at C3.5); ledger gate at C0.5 |
| 70 | — | N/A | — | vindication |
| 71 | HIGH | OK | C4.5 | |
| 72 | HIGH | OK | C4.6 | |
| 73 | HIGH | OK | C4.6 | |
| 74 | HIGH | OK | C0.4, C7.4 | transcript regenerates from C0.4 on every numeric commit |
| 75 | HIGH | OK | C4.8 | |
| 76 | HIGH | OK | C7.4 | exit criterion 6 restated so it no longer conflicts |
| 77/S-6 | MED | OK | C4.7 | Butterwick exponent −0.48 vs the re-fit −0.4429 |
| 77/S-7 | MED | OK | C4.7 | AIROF derating evidence string |
| 77/S-8 | MED | OK | C4.7 | SIROF 2–4 vs Kane's 2–3 |
| 77/S-10 | MED | OK | C4.7 | `audit.py` digest omits nine condition fields |
| 77/S-11 | MED | OK | C4.7 | two Ta2O5 designs measured by different methods |
| 77/S-12 | MED | OK | C4.7 | McCreery 2010's four defining conditions; damage radius |
| 77/S-13 | MED | OK | C4.7 | Butterwick d⁻² measured on single pulses |
| 78/S-14 | LOW | OK | C4.9 | zero-width `separating_k_range()` — changes a computed value |
| 78/S-15 | LOW | OK | C4.9 | |
| 78/S-16 | LOW | OK | C4.9 | κ range excludes Elwassif's 0.45 |
| 78/S-17 | LOW | OK | C4.9 | |
| 78/S-18 | LOW | OK | C4.9 | |
| 78/S-19 | LOW | OK | C4.8 | leung2014 is 2015 |
| 78/S-20 | LOW | OK | C4.8 | itis2025 is v4.2, 2024 |
| 78/S-21 | LOW | OK | C4.9 | |
| 78/S-22 | LOW | OK | C4.9 | |
| 78/S-23 | LOW | OK | C4.9 | |
| 78/S-24 | LOW | OK | C7.4 | six stale README claims |
| 78/S-25 | LOW | OK | C4.9 | |
| 84 | HIGH | — (found in Phase 0) | C1.5 | D3(i) restated; `unsafe_at_any_amplitude` + the rendering contract. Interacts with C2.1, C2.3 and C5.1, each of which carries an assertion |
| 85 | MED | — (found in Phase 0) | C0.3 | **FIXED** — `datetime.now` removed from the PDF byline |
| 86 | HIGH | — (found in Phase 0) | C0.4 | **FIXED** — transcript generated between markers from one script, gated in CI |
| 87 | LOW | — (found in Phase 0) | C5.9 | deferred out of Phase 0 because it changes package output bytes |
| 88 | HIGH | — (found in the Phase 1 review) | C1.10 | **FIXED** — `_climb_to_boundary`'s relative bound is joined by a caller-declared absolute `plateau` (D2 point 3); `assess()` stopped raising on the 6.3 % of edge-clustered valid inputs that used to crash |
| 89 | CRIT | — (found in the Phase 1 review) | C1.3, C1.5 | **FIXED** — `sensitivity.py` and `examples/worked_example.py` were byte-untouched by Phase 1 and are render surfaces for both conventions; §6 had no row for either file |
| 90 | MED | — (found in the Phase 1 review) | C1.9 | **FIXED** — the `UNCONSTRUCTIBLE` guard was one-sided; a *lower* amplitude bound crashed the bisection where an upper bound was handled. No package number moves: the defect is in `tests/oracles/fail_ceiling.py` |
| 91 | HIGH | — (found in the Phase 1 review) | C2.3 | seed refactored into `_water_window_seed_uA` with the required drift term written out and a tripwire test in Phase 1b; **the term itself must land inside C2.3**, beside the clause it inverts |
| 92 | MAJOR | — (found in the Phase 1 review) | C1.5 | **FIXED** — the headline refuses in its own type; `limit_bearing_ceiling_uA` carries the raw quantity. Landed in Phase 1b, before C2.1 widens the disagreeing population |
| 93 | MED | — (found in the Phase 1 review) | C1.3, C1.10 | **FIXED** — `STEP_BUDGET` and `CLIMB_TOLERANCE` are straddled by behavioural pairs written as literals, so a test cannot move with the constant it pins |
| 94 | MED | — (found in the Phase 1 review) | C1.6, C1.8 | **FIXED** — the by-kind test asserts hand-written per-kind ceilings instead of rebuilding them from the ceilings under test; the interval-containment docstring states what a structural guarantee can and cannot catch |
| 95 | HIGH | — (found in the Phase 1 review) | C1.1, C1.4, C1.5, C1.6 | **FIXED (booking only)** — five movers added to §6; no code change, the moves already happened in Phase 1 |
| 96 | HIGH | — (found in Phase 1b) | C1.3 | **FIXED** — D2's floor is about maxima, not about microamps; seven sites routed through `format_limit` and the `:g` constants gated by a round-trip test |
| 97 | HIGH | — (found in Phase 1b review) | **C2.6** (`33d3f13`) | **FIXED** — `CEILING_INTERVALS` beside `CHECK_KINDS`, keys asserted equal to `LIMIT_BEARING`, lookup raises. `_ceiling_interval_uA` dispatches on check-name string literals and falls through to `Interval.exact`, silently narrowing a published band to a point (7.853–19.63 µA → 19.63 µA). Move the interval provider beside the kind in `CHECK_KINDS`, or onto `Check` where it is built, so a stale name raises the way `Check.kind` already does. Scheduled after Phase 2's data-model commits because it touches the same dispatch |
| 98 | HIGH | — (found in Phase 1b review) | **C2.7** | **FIXED** — option A, chosen by the user: the declared plateau bounds the walk down as well as the climb (D2 point 2 amended), and Shannon declares one at both call sites. The Phase 1b mechanism alone could not close it, because the raise is on the walk down, which the plateau did not reach. Originally: `shannon_k` is a sum of two logs, so its resolution is set by the larger addend; above 1e4 µC/cm² the seed overshoots `STEP_BUDGET` and `assess()` raises on accepted `k`. Declare Shannon's plateau with the Phase 1b mechanism. MUST land before Phase 2's exit gate — it is a crash on accepted input, orthogonal to Phase 2's files |
| 99 | HIGH | — (found in Phase 1b review) | **C2.3a** (`5276a40`) | `limiting_current_uA` returns 0.0 for a zero limit-bearing ceiling while documenting that it returns None whenever no amplitude is safe. Decided: None for a no-amplitude-is-safe FAIL **or** a ceiling ≤ 0.0, each with a reason naming the check. **Landed at C2.3a, not C2.1**: the row was written when C2.1 was the commit widening the refusal, and C2.3 has since opened a second door to the same defect — a continuous train with any unrecovered charge drives the drift ceiling to exactly 0.0 while Charge balance is only CAUTION, so `unsafe_at_any_amplitude` is empty and the surface printed `Limiting current: 0 uA (Water window)`. Carries the `NO_SAFE_AMPLITUDE` named set in the same commit, since both answer the question of what makes the headline refuse |
| 100 | MEDIUM | — (found in Phase 1b review) | **C2.7** | **FIXED** — the policy warning floors through `format_limit` and is walked for every material × policy × polarity × medium; the stored-constant gate walks the stored ends and polarity sub-ranges and reads `limit_K` from the thermal module. `nominal` is a midpoint rather than a stored constant and is gated at its one render site instead. The `:g` round-trip gate walks two of three `Policy` values and cannot reach a derated quotient, so ledger 96's "structurally safe" claim is untrue of `charge.py:257`. Extend the gate to every policy and polarity, cover derived values, and replace the tautological `renders_exactly(2.0)` literal. Lands with 98 before Phase 2's exit gate |
| 101 | MED | — (found executing C2.6) | **C2.6b** (`8f85f1e`) | **FIXED** — landed before 98 so every gate after it is plain `pytest -q`. Originally: CI's `pytest -q` fails 8 tests on `from tests import …` in `tests/test_data_model.py`; green only under `python -m pytest`. Must land before Phase 2's exit gate: the failing tests are the ones that close 2, 3 and 99 |
| 102 | LOW | — (found in Phase 1b review, recorded at C2.7) | **unscheduled** — reported to the team lead | policy warning compares a derated `limit` with an underated `endorsed` under `medium="in_vivo"`; unreachable in the shipped database |
| 103 | CRIT | — (found in Phase 2 review, F1) | **C2.8** | **FIXED** `f4f08b8`; exact-linear unrecovered charge; drift gated on `is_charge_balanced`; the seed refuses a zero DC. MUST land before Phase 3 |
| 104 | CRIT | — (found in Phase 2 review, F2) | **C2.8** | **FIXED** `f4f08b8`; removed by the same exact-linear net, which makes the drift clause exactly monotone; sweep over r_a in {0.9,...,1-1e-6} |
| 105 | HIGH | — (found in Phase 2 review, F3) | **C2.9** | **FIXED** `1fc2cbc`; drift budget carries the excursion riding on the offset; the drift oracle is extended to partial recovery |
| 106 | HIGH | — (found in Phase 2 review, F4) | **C2.10** | **FIXED** `4dbca6e`; booking only: the missing section 6 rows, and the C2.4 row corrected |
| 107 | HIGH | — (found in Phase 2 review, F5) | **C2.11** | **FIXED** `3bd56f0`; README, CHANGELOG, module docstrings, GUI train_duty_cycle field, example_output regenerated |
| 108 | MED | — (found in Phase 2 review, F6) | **C3.0** (own commit immediately before C3.1; moved from C5.11 at ledger 123) | **FIXED** `5dc9eb1`; render text: describe() must print the combined peak-and-drift verdict |
| 109 | MED | — (found in Phase 2 review, F7) | **C4.2** (user decision after the Phase 3d review) | the drift runs over the wall-clock train while n_pulses, the mean and RMS currents and, since C3.17, the compliance train offset scale with train_duty_cycle; conservative today. Settled at C4.2 |
| 110 | MED | — (found in Phase 2 review, F8) | C2.8, C2.9 | **FIXED** `1fc2cbc`; residual-net and partial-recovery populations at C2.8; partial-recovery oracle, `exits_during_train` boundary pair and over-recovery edge at C2.9 |
| 111 | LOW | — (found in Phase 2 review, F9) | **unscheduled** | test-only. Run the oracle over the whole sweep with the set written literally; first Phase 3 commit |
| 112 | LOW | — (found in Phase 2 review, F10) | C2.8 | **FIXED** `f4f08b8`; removed by the exact-linear net: the balance test becomes amplitude-independent |
| 113 | LOW | — (found in Phase 2 review, F11) | **P2b docs commit** (docstring narrowed; ledger 123) | **FIXED** `96ccae5`; documentation-only today (not rendered); fix with the next change to the interval, or narrow the docstring |
| 114 | LOW | — (found in Phase 2 review, F12) | C5.5 | batch CSV columns |
| 115 | LOW | — (found in Phase 2 review, F13) | C2.8 | **FIXED** `f4f08b8`; one sentence in D2 point 2 |
| 116 | LOW | — (found in Phase 2 review, F14) | C5.11 | viz |
| 117 | LOW | — (found in Phase 2 review, F15; extended by Phase 2b review G1 = ledger 119) | C2.8, C4.2 | the nan term closes at C2.8; water_window.evaluate's argument contract at C4.2, which already reworks its polarity arguments; the charge-interval fallback at C4.2 — nan term **FIXED** at `f4f08b8` |
| 118 | LOW | — (found in Phase 2 review, F16) | C4.3 | provisional propagation: set provisional on Water window whenever drift binds, and say 'no-leak bound' |
| 119 | LOW | — (found in Phase 2b review, G1) | C4.2 (folded into 117) | the public `water_window.evaluate` keeps both old behaviours: no balance gate, and `recovered_charge_uC` defaults to 0.0. C4.2 makes the drift inputs one object, or makes the riding charge required with the DC, and applies the balance tolerance inside the function |
| 120 | LOW | — (found in Phase 2b review, G2) | C5.5 | `report()["net_dc_current_uA"]` (a batch column) carries the raw 1.04e-12 residue for a pulse both checks call balanced; report 0.0 when balanced or document it as the raw residue |
| 121 | LOW | — (found in Phase 2b review, G3) | **P2b docs commit** | **FIXED** `96ccae5`; mislabelled fixture in the section 6 C2.2 [106] row; relabelled |
| 122 | LOW | — (found in Phase 2b review, G4) | **P2b docs commit** | **FIXED** `96ccae5`; the README water-window limitation described a pure double-layer capacitance; rewritten to the CIC-derived `C_eff` |
| 123 | LOW | — (found in Phase 2b review, G5) | **P2b docs commit** | **FIXED** `96ccae5`; scheduling: 108 moved to its own commit before C3.1; 113 closed by narrowing the docstring |
| 124 | LOW | — (found at C3.1) | C4.8 | obtain Weiland 2002 and McCreery 2010 for papers_stim_calc_ref/ and verify the two presets' geometry and tags against them; C4.8 already verifies citations against the PDFs in the library |
| 125 | LOW | — (found at C3.2) | C5.11 | condition charge.describe()'s perimeter-peak note on the geometry, using `current_density.primary_distribution` |
| 126 | LOW | — (found at C3.5) | C4.4, C5.5, C5.8 | the JSON and audit settings record carry the counter at C4.4 (already in its scope); batch CSV columns at C5.5; a GUI input at C5.8 |
| 127 | HIGH | — (found in Phase 3 review, H1) | **C3.7** | **FIXED** `f2b6a0a`; regenerate the FD band table with radial resolution tied to band height, show convergence, cross-check against an independent solve, restate the sphere's accuracy everywhere. MUST land before Phase 4 closes (review condition) |
| 128 | HIGH | — (found in Phase 3 review, H2) | **C4.3** | render a provisional marker beside the limiting current whenever the binding check (or the cap's binder) is provisional, on describe, PDF, GUI and figure. Written into C4.3's scope (section 5.4) |
| 129 | MED | — (found in Phase 3 review, H3) | **C3.8** | **FIXED** `f072907`; flat-tip microwire with no shaft: correct R, or refuse/flag (a modelling choice, proposed before implementing) |
| 130 | LOW | — (found in Phase 3 review, H4) | **C3.10** | **FIXED** `982b65b`; separation guard on the largest half-dimension for elongated geometries |
| 131 | MED | — (found in Phase 3 review, H5) | **C3.9** | **FIXED** `248a6f5`, then **RETRACTED by the reviewer (ledger 135)** and corrected at C3.12; each phase uses its own polarity's C_eff for the counter and for the active electrode's return-phase term |
| 132 | LOW | — (found in Phase 3 review, H6) | **C3.10** | **FIXED** `982b65b`; the drift-CAUTION water-window header reads '-> CAUTION (...)' |
| 133 | MED | — (found in Phase 3 review, H7) | **C3.11** | **FIXED** `b355890`; counter electrode not assessed: a design choice proposed to the user first; the out-of-scope statement lands in the README and compliance docstring regardless |
| 134 | LOW | — (found in Phase 3 review addendum, H8) | **P3b docs commit** | ledger 8's note reworded: the 2x comes from the polarity-specific CIC and half-window together, and the re-check moves to ledger 7's boolean branches |
| 135 | HIGH | — (found in Phase 3b review, J1) | **C3.12** | **FIXED** `6c5f34d`; the return phase polarises only by the overshoot beyond rest, (r_a - 1)*Q at the opposite polarity's C_eff; exactly I_ret*R otherwise; for the active electrode and the counter. Restores the symmetric-pulse numbers; pulse-by-pulse oracle. Review condition before release |
| 136 | LOW | — (found in Phase 3b review, J2) | **C3.15** | **FIXED** `ca356f8`; floor the interval ends through the same predicate as the point estimate; random-sweep containment test including counters |
| 137 | LOW | — (found in Phase 3b review, J3) | **C3.13** | **FIXED** `3595c05`; the caveats lookup raises on an unknown key, as CEILING_INTERVALS does |
| 138 | LOW | — (found in Phase 3b review, J4) | **C3.14** | **FIXED** `5372f77`; correct the 0.1755 citation to the reviewer's converged ~0.1731; state the generator's dependency on the band solver's node helper |
| 139 | LOW | — (found in Phase 3b review, J5) | **C3.16** | **FIXED** `bd8297b`; the separation guard uses a rectangle's half-diagonal; check other geometries for the same reach error |
| 140 | MED | — (found at C3.12) | **C3.17** | **FIXED** `b0ab74f`; the train's accumulated DC offset in the compliance budget, per the user's decisions: leading phase for under-recovery, return overshoot for over-recovery; active capped at the water-window headroom, counter and window-less materials uncapped; N = ceil(duty-scaled n_pulses) |
| 141 | MED | — (found at C3.17) | **C3.18** | **FIXED** `758ac66`; the drift clause budgets an over-recovery drift, which heads for the opposite edge, at the opposite polarity's C_eff instead of the leading one |
| 142 | HIGH | — (found in Phase 3c review, K1) | **C3.19** | **FIXED** `ebdf596`; include the distance the interface travels, \|edge − rest\|, in the max that sets the water-window plateau; far-side-rest sweep with zero raises and no previously returned float changed |
| 143 | HIGH | — (found in Phase 3c review, K2) | **C3.20** | **FIXED** `362752e`; render an infinite requirement as a refusal sentence naming why on every surface; report_to_json strictly valid (null plus a reason field), schema change documented |
| 144 | LOW | — (found in Phase 3c review, K3) | **C3.21** | **DOCUMENTED** `2d87352` (bound stated, not modelled); compute the over-recovery overshoot from the clamped state if cheap and model-sourced, otherwise document the exception and its bound |
| 145 | LOW | — (found in Phase 3c review, K4) | **C3.22** | **FIXED** `25cc8da`; correct the C3.12 row: numbers, statuses and limits identical; the detail's 'return phase' line moves, with before/after text |
| 146 | LOW | — (found in Phase 3d review, L1) | **C4.0a** (first Phase 4 commit) | protocol_from_dict and every JSON/CSV reader map a null train_duration_s back to math.inf; report_to_json → load → protocol round-trip test for continuous and finite trains |
| 147 | LOW | — (found in Phase 3d review, L2) | **C4.0a** | keep None for an unbounded row in the batch frame (object dtype), or document it; decided and justified in the commit |
| 148 | LOW | — (found in Phase 3d review, L3) | **C4.0b** | correct the documented maximum deficit to the verified figure, citing the configuration |
| 149 | LOW | — (found at C4.0a) | **C4.4** | the audit record's JSON strict, with the protocol's null duration explained as report_to_json does, and old records' digests still reproducible |

**Merge policy.** The Commit column of `CODE_MISTAKES_LOG.md` records each hash **as made**,
and the repository's policy — written into that file's header, and repeated in CONTRIBUTING
at C7.5 — is **no squash-merge and no rebase onto the default branch**. So no per-merge hash
rewriting is needed, and `scripts/ledger_check.py` can resolve every recorded id in `git log`
for the life of the project.

**Coverage:** 82 entries, 118 rows with 61 (14), 62 (5), 67 (3), 77 (7) and 78 (12) broken
out. Two entries take no code action: 22 (documented, §8) and 70 (vindication). Entry 16 is
a documented limitation with a stated accuracy, not an unfixed defect. Entries 85 and 86 are
already fixed (Phase 0); 84 and 87 are scheduled at C1.5 and C5.9.

---

## 10. Exit criteria

Twelve criteria. Each is individually achievable from the state this plan leaves, and each
names the artifact that proves it. v1's criteria 2, 3, 5 and 6 were unsatisfiable,
unimplementable, unachievable and fabrication-inviting respectively; all four are restated.

| # | criterion | why it is achievable | measured today |
|---|---|---|---|
| G1 | `pytest -q` green, and all 26 tests of `audit_tests.md` §10 present and passing — with T1, T2, T4, T5, T14, T16 and T19 in their **v2** forms, **T1 carrying its `not a.unsafe_at_any_amplitude` precondition explicitly** | v1's versions of T1, T2, T4, T5, T14, T16 and T19 were unsatisfiable or tautological; the v2 forms are specified in §5 with their oracles | 522 pass |
| G2 | **Mutation: all 42 named mutants killed (100 %), plus ≥ 90 % of a generated set of ≥ 150 mutants** over `neurostim/safety/`, `units.py`, `protocol.py`, `uncertainty.py`, `models/field.py`, `models/vta.py`, `models/strength_duration.py`. Script and results committed. | v1 asked for "≥ 95 % over safety + units" while 4 of its 13 named survivors live outside that scope, and measured "from 69 %" over a *different* 42-mutant population. A named set should be 100 % — "95 % of 42" leaves one survivor with no rule for which. The generated set is what a fixed list cannot give: it cannot be satisfied by writing one test per named mutant. 90 %, not 95 %, because equivalent mutants in a generated set should not block a release. | 42 mutants, 13 survivors, **69.0 %**. `units.py` contributes 1 mutant, already killed — which is why the scope is widened rather than narrowed |
| G3 | **Branch-POINT coverage ≥ 80 % overall, and ≥ 60 % for every module with ≥ 4 branch points**, measured by `scripts/branch_floor.py` from `coverage json`, ratcheted per phase in CI | §3. `--cov-fail-under` gates the blended line+branch total and cannot ratchet. An 80 % point floor implies ≥ 87 % arcs, so the execution review's 85 % arc floor is subsumed | **48.30 %** points (185/383); 71.54 % arcs (548/766) |
| G4 | `python scripts/provenance_audit.py --strict` exits 0 **in CI** | already written; only the `--strict` flag and the CI wiring are missing | never run with `--strict` |
| G5 | **Determinism: `regenerate_example_output.py` run twice is byte-identical, asserted before the committed-vs-regenerated comparison** | v1 asked only for the second comparison, which fails on unchanged code. C0.3 lands the four fixes (`SOURCE_DATE_EPOCH`, `savefig` metadata, `svg.hashsalt`, `rl_config.invariant`) first | 5 of 8 artifacts differ between two identical runs |
| G6 | **Every provenance flag the README describes is exercised by a test using `with_measured_cic`, the README says so explicitly, and a test asserts all nine shipped materials remain `verified=True`** | v1's "fires on at least one shipped material" is false by construction — all nine are verified, which *is* ledger 76 — and its only satisfaction is flipping a flag, i.e. fabricating provenance in a provenance package. The third clause makes that flip a test failure | all nine `verified=True`, `cic.verified=True` |
| G7 | `neurostim.__version__`, `pyproject.toml`, `CITATION.cff` and the installed distribution agree, asserted by a test | C7.2 single-sources it | 0.15.0 vs 0.13.0 |
| G8 | LICENSE present; `paper.md` builds; `CITATION.cff` free of placeholders | C7.1, C7.5 | LICENSE absent |
| G9 | **Cross-surface consistency**: the limiting current is identical in `describe()`, `report()`, `report_to_json`, the PDF text, the GUI headline and the figure annotation, for one microelectrode and one macroelectrode case — **and, for a third case with `unsafe_at_any_amplitude` non-empty, every one of those surfaces presents the same absence of a number and names the same check** (ledger 84) | adopted from the execution review. This is the single gate that makes B1/B3/M4/M5 unrepeatable | figure 141 µA vs a headline that becomes 20.00 |
| G10 | **Round-trip**: over the 9 × 3 × 2 grid **restricted to protocols with no amplitude-independent failure, with the restriction asserted rather than assumed**, `limiting_current_uA` equals C0.6's independent binary search to `rel=1e-9`, `nextafter(limit, +inf)` FAILs, and `limit > 0`; plus, on the excluded protocols, `fail_ceiling_uA == 0.0` and no surface presents a number | adopted. The `> 0` clause is what a one-sided `<= 20.0` admits (−21.095 µA) | 18/18 interval containments fail; 52/54 whole-assessment round-trips fail |
| G11 | **Ledger gate**: every row of `CODE_MISTAKES_LOG.md` parses to exactly 9 fields, and every entry number appears in §9 with a commit id present in `git log` | adopted. Rows 8 and 46 parse to 13 and 11 fields today | 2 corrupt rows |
| G12 | **No regression on earlier phases**: each phase re-runs the previous phases' new tests unchanged; a later phase that must edit an earlier phase's assertion says so in the commit message | adopted | — |

**What can still be false when all twelve are met.** Ledger 16 (no exact band form) and
ledger 22 (no array safety API) remain open as documented limitations; the chronic check can
still bind an acute protocol, visibly; the compliance two-interface model (ledger 5) is
first-order superposition, not a solved two-body problem, and this bibliography contains no
published compliance-voltage measurement to pin it against — which is the one gap the test
list cannot close from inside the repo. Each is stated in §8 or in the module docstring.

---

## 11. Process note

`<user CLAUDE.md>` rule 14 requires appending a summary to
`_conversation_history.md` after every response. The task brief for this revision restricted
writes to `docs/audit/FIX_PLAN_v2.md` only. That conflict is flagged rather than resolved
silently: `_conversation_history.md` has **not** been updated by the author of this plan.
The same restriction applies to `CODE_MISTAKES_LOG.md`, whose corrupt rows 8 and 46 are
therefore scheduled for repair in commit C0.5 rather than fixed here.
