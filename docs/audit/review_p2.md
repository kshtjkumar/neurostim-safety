# Phase 2 Review — `git log aaf3c85..e07114d`

Status: COMPLETE

Repo: .
HEAD: e07114d (master). Main tree not modified by this review; scratch worktrees under the
session scratchpad were created and removed.

## Commits in scope
```
e07114d docs(ledger): record the commit that closed 98
8ca9bd4 fix(safety): let a declared plateau bound the walk down, and declare Shannon's      (98, C2.7)
cf3b843 docs(safety): the interval docstring names all three published bands
206a43b docs(ledger): record the commit that closed 101
8f85f1e test: import the oracles the way pytest puts them on the path, so CI runs green   (101)
9989dc0 docs: log the CI-only import failure and the underated endorsement
6e7db0f docs(ledger): record the commit that closed 100
ca51148 fix(safety): floor the derived charge limits the :g gate could not reach          (100)
2783826 docs(ledger): record the commit that closed 97
33d3f13 fix(safety): declare every ceiling's interval, and raise on a name it does not know (97, C2.6)
788a796 test(safety): pin the refusal contract in both directions, and why zero cannot reach a render
543a3f8 docs(ledger): record the commit that closed 6 and 67
689ddc6 fix(safety): delete the pulse-duty excursion; add and wire the train duty cycle    (C2.5)
14ba7b6 docs(ledger): record the commit that closed 2
5db8415 fix(safety): stop applying biphasic-measured limits to monophasic protocols         (C2.4)
52185e8 docs(ledger): record the commit that closed 99
5276a40 fix(safety): refuse a limit when no amplitude is safe, and name the reason          (99, C2.3a)
82be402 docs: session history through Phase 2 C2.3
de1aaf7 feat(safety): model DC drift out of the water window                               (C2.3)
65e9485 docs: log the gaps in the :g round-trip gate, preserve Phase 1b review            (swept-in C2.3 tests + protocol.py; known)
97c7811 docs: log the Shannon settle raise and the zero-ceiling promise
c4571ca docs(ledger): record the commit that closed 4
0ac7950 fix(safety): evaluate the return phase in current density and compliance           (C2.2)
1518c47 docs(ledger): record the commit that closed 3 and 15
9e87b85 feat(protocol): make charge recovery an independent input                          (C2.1)
```

## Gates at HEAD (executed)
* `pytest -q` (plain, the CI form): **888 passed** in 74 s.
* `ruff check neurostim tests`: clean. `mypy neurostim`: no issues in 53 files.
* `scripts/ledger_check.py`: OK, 102 entries. `regenerate_example_output.py --check`: README
  transcript matches.

## Summary of findings

| # | Sev | Where | One line |
|---|---|---|---|
| F1 | **BLOCKER** | water_window.py:217-219, assessment.py:864-868 | Float residue in a *balanced* asymmetric pulse is treated as DC drift: `ZeroDivisionError` out of `assess()`, spurious Water-window FAIL, non-monotone predicate, a reported limit above an amplitude that FAILs |
| F2 | **BLOCKER** | assessment.py:890-905, 918-929 | Drift clause is non-monotone at ulp scale for any partial recovery; `LimitDidNotSettle` raised out of `assess()` on 576 of 16 200 ordinary protocols |
| F3 | MAJOR | water_window.py:198-236, assessment.py:895-905 | Drift budget ignores the leading-phase excursion riding on the accumulated offset — anti-conservative (2.4 s reported vs 0.42 s by the model's own physics) |
| F4 | MAJOR | FIX_PLAN_v2.md §6 | Unbooked / mis-booked movers: C2.3a, C2.4, C2.2 values, 98's water-window raise→number, C2.3 ceiling last digits |
| F5 | MAJOR | README.md, charge.py, water_window.py docstring, GUI, example_output | §6-booked doc/GUI updates for C2.3–C2.5 not made; example_output not regenerated |
| F6 | MINOR | water_window.py:303-323 | A FAIL Water-window check prints detail "-> PASS … headroom +0.582 V" |
| F7 | MINOR | protocol.py:299-301, assessment.py:1786-1788 | Drift ignores `train_duty_cycle` (conservative inconsistency with `n_pulses`/`average_current_uA`) |
| F8 | MINOR | tests | Two surviving mutants in the drift code; no oracle for partial-recovery drift; no residual-net or partial-recovery protocols in the monotonicity sweeps |
| F9 | MINOR | test_data_model.py:1648-1680 | "Refusal contract" equivalence test restates the implementation |
| F10 | MINOR | protocol.py:303-318 | Charge-balance verdict flips with amplitude for `charge_recovery_ratio` within ~1e-12 of 1 |
| F11 | MINOR | assessment.py:478-513, 574-609 | `limit_bearing_ceiling_uA` not contained in `limiting_current_interval_uA` when the monotonicity cap binds, contrary to its docstring |
| F12 | MINOR | assessment.py:1951-1957 | `report()` / CSV still carry the biphasic CIC current for a monophasic protocol |
| F13 | MINOR | _limits.py:159-207 | Option A turns some non-monotone raises into silent answers (synthetic: 4 030 of 49 824) |
| F14 | MINOR | viz/plots.py:226-249 | The zero ceiling that makes the figure refuse is drawn at y = 0 on a log axis (invisible) |
| F15 | MINOR | water_window.py:363-381; assessment.py:129-134 | Silent fall-throughs: drift clause dropped if any of three optional inputs is `None`; exact-point fallback in `_charge_ceiling_interval` |
| F16 | MINOR | assessment.py:1854-1855, 1262-1272 | Drift-bound limit is not flagged `provisional`, although it rests on a no-leak capacitor that Merrill 2005 §2.4 contradicts for sustained trains |

Counts: **2 BLOCKER, 3 MAJOR, 11 MINOR.**

---

## F1 — BLOCKER — rounding residue of a balanced pulse is treated as DC drift

`neurostim/safety/water_window.py:217-219` gates drift on `self.net_dc_current_uA != 0.0`.
`protocol.net_charge_at_uA` (`protocol.py:295-297`) is `charge_uC(I, W) - charge_uC(I*r_a/r, W*r)`,
a difference of two products whose association differs, so for `r_a = 1.0` and `r != 1` it is
often a few ulps off zero. `Charge balance` uses the relative tolerance
(`is_charge_balanced`, 1e-12 × Q) and says "fully charge-balanced"; `Water window` uses exact
`!= 0.0` and says the interface is drifting. Two checks disagree about the same waveform.

Then `_water_window_seed_uA` (`assessment.py:865-868`) divides by
`abs(protocol.net_dc_current_at_uA(1.0))`, which is exactly 0.0 when the residue happens to
vanish at 1 µA:

```
p = StimProtocol(7, 90, 50, T, return_phase_ratio=0.3); DiscElectrode(500, "Pt")
net -2.168404344971009e-19 balanced True
T=inf : WW FAIL "-1.084e-17 uA of net DC reaches the edge in 3.622e+16 s -- within a continuous train"
        CB PASS "biphasic, fully charge-balanced"; limiting 393.3738671618686
T=3600: RAISE ZeroDivisionError division by zero
T=1.0 : RAISE ZeroDivisionError division by zero
```

With `T = inf` the seed is `window_charge / (0 * inf) = nan` and `min([peak, nan])` silently
returns the peak term (`assessment.py:869`). The predicate is then non-monotone — whether it
FAILs depends on whether the residue rounds to zero at that amplitude:

```
StimProtocol(5, 90, 50, inf, return_phase_ratio=0.3):  net per pulse at I =
1..4 -> 0.0 | 5 -> -5.4e-20 | 6 -> 0.0 | 7 -> -2.2e-19 | 10, 20, 100 -> non-zero | 393 -> 0.0
headline: "Limiting current: 393.3 uA (Current density)", Overall: FAIL (Water window FAILs at 5 uA)
oracles.fail_ceiling_uA(calc, names=LIMIT_BEARING) -> NonMonotonePredicate:
  "Water window FAILs at 1.77828e-12 uA and does not FAIL at 3.16228e-12 uA ..."
```

So the headline names 393.3 µA as the limit while 5 µA and 7 µA FAIL the Water-window
check — the D2/D3 contract (the reported limit is the highest amplitude at which no
limit-bearing check FAILs) is broken, and `floor_to_pass`'s monotone precondition is
violated without detection (it asserts only at the returned point).

Scale (scratch sweep, `residual_sweep.py`: I ∈ 16 values × PW ∈ 10 × r ∈ 13 incl. 1.0 ×
T ∈ {inf, 3600, 1}, `DiscElectrode(500,"Pt")`, all `charge_recovery_ratio = 1.0`):

```
total 6240 | exact zero net 6018 | residual net 222
raise ZeroDivisionError (finite T)            140
WW FAIL with CB PASS (T = inf)                  74
  of which reported limit > a FAILing amplitude 56
WW CAUTION with CB PASS (finite T)               8
```

Identical at `cf3b843` (pre-98), so introduced by C2.3 (`de1aaf7`), not by option A. The
batch path turns the raise into an `ERROR` row; the GUI shows "Invalid input" for valid input
(`gui/app.py:362-370`). `TestSymmetricProtocolsDoNotMove::test_a_balanced_asymmetric_width_protocol_is_still_balanced`
uses `r = 4.0`, which happens to cancel exactly, so the suite cannot see this.

**Fix.** Compute the unrecovered charge in one exact-linear expression,
`charge_uC(I, W) * (1 - r_a)` (return charge is `I·r_a/r · W·r = I·W·r_a` in exact arithmetic),
so it is exactly zero at `r_a = 1` and exactly proportional to `I`; gate `DcDrift.drifts` on
the same tolerance Charge balance uses (`not protocol.is_charge_balanced`), so the two checks
cannot disagree; and never let a `nan` term reach `min()` in the seed (raise if
`dc_per_uA == 0` while `drifts`). Add a residual-net population (`r ∈ {0.3, 0.7, 3}` at many
amplitudes, finite and infinite T) to the suite.

## F2 — BLOCKER — `LimitDidNotSettle` on ordinary partial-recovery protocols

Same root arithmetic as F1, different symptom. For `0 < r_a < 1` the net charge is a
difference of two nearly equal numbers, so its relative rounding noise is ~`eps / (1 - r_a)`
and `net_dc_current_at_uA(I)` is **not monotone in I at float resolution**. The drift clause
of `stays_in_window` therefore flickers across hundreds of consecutive floats, while the
declared `plateau_uA` (`assessment.py:918-929`) covers only the peak clause (ulp of a
potential). The seed lands inside the flicker and the walk down cannot settle:

```
DiscElectrode(500.0,"Pt"), StimProtocol(10.0, 50.0, 130.0, 1.0, charge_recovery_ratio=0.99).assess()
LimitDidNotSettle: Water window: the back-solved limit 4531.143250369907 still fails its own check
after 4 steps down to 4531.143250369903. ... Nor does it pass within 4.35983562251079e-12 below,
4 times the 1.0899589... the caller declared the check can resolve.
```

Diagnosis at the seed of a PEDOT case: `passes` reads F F F F F F **T** F across eight
consecutive floats while `net` alternates between 1.6067927839392915e-11 and …704e-11.

Scale (`lds_rate.py`: 9 materials × 6 diameters × 5 PW × r_a ∈ {0.5, 0.9, 0.95, 0.99, 0.999}
× T ∈ {1, 10, 60, 3600} × I ∈ {10, 80, 500}; nothing edge-clustered, resting potential 0):

```
HEAD (e07114d):  576 of 16 200 raise   (r_a=0.99: 81, r_a=0.999: 495)
cf3b843 (pre-98): 2439 of 16 200 raise (r_a=0.9: 108, 0.95: 954, 0.99: 315, 0.999: 1062)
de1aaf7 (C2.3) and 82be402: the repro above raises identically
```

Option A (98) incidentally reduced the rate because the water window's plateau now also
reaches the walk down, but did not remove it. An edge-clustered water-window sweep
(`ww98.py`, 20 000 configurations mixing r_a, polarity, waveform, T) raised on 107. By the
Phase 1 precedent (a crash on accepted input is a BLOCKER, ledgers 88 and 98), this is one;
it is also the ledger-98 class re-opened in the clause Phase 2 added. The docstring claim at
`assessment.py:850-852` ("Both clauses are individually monotone-decreasing in current … so
floor_to_pass's precondition holds") is false at float resolution.

**Fix.** The F1 fix (net = `charge_uC(I, W) * (1 - r_a)`) makes the drift clause exactly
monotone and makes the seed its exact inverse; that removes both the flicker and the need
for a drift plateau. If the subtraction form is kept, the drift clause must declare its own
resolution (≈ `ulp(charge_uC(I,W)) / ((1-r_a)·W·1e-6)` in µA) and the plateau passed to
`floor_to_pass` must be the max of the two. Pin with a sweep over r_a ∈ {0.9, 0.95, 0.99,
0.999, 1-1e-6} × ordinary geometries asserting zero raises.

## F3 — MAJOR — drift budget ignores the pulse riding on the offset (anti-conservative)

`DcDrift.time_to_exit_s = window_charge / |I_dc|` with `window_charge = headroom(rest→edge)·C·A`
(`water_window.py:174-183, 221-226`), and the peak clause is evaluated separately from rest
(`assessment.py:891-896`). Under the package's own capacitive model the leading phase of pulse
*n* peaks at `rest + offset(n-1) + excursion`, so the interface leaves the window when the
offset reaches `headroom − excursion`, not `headroom`. For monophasic delivery the two agree
(each pulse is all offset), which is why the drift oracle (monophasic only,
`tests/oracles/drift.py`) cannot see it; for partial recovery they do not.

```
DiscElectrode(500,"Pt"), C = 250 uF/cm^2 (package-derived), 200 us, 50 Hz, T = 1 s,
charge_recovery_ratio = 0.99, I = 1227.184630308513 uA (leading excursion 0.50 V of 0.60 V)
package: WW CAUTION "peak -0.50 V, 0.10 V headroom, but +0.1227 uA of net DC reaches the edge
         in 2.4 s -- after the 1 s train";  WW ceiling 1472.6215563702156 uA
hand pulse-by-pulse loop (same C, same edge): leaves the window at the leading phase of
         pulse 22, t = 0.42 s -- inside the 1 s train
```

The verdict should be FAIL and the ceiling is above an amplitude the model says exits. Plan
C2.3's oracle clause ("agree to within one pulse") was only ever exercised on monophasic.

**Fix.** Make the drift clause `offset(t) + excursion(I) ≤ headroom`, i.e.
`t_exit = (headroom − excursion)·C·A / |I_dc|` (still monotone in I, closed-form seed
`(headroom·C·A) / (I_dc/I·T + W/1e6)` per µA), and extend `tests/oracles/drift.py` with a
partial-recovery pulse-by-pulse loop that tracks the leading-phase peak. Over-recovery (drift
toward the opposite edge) needs its own statement of which excursion rides on the offset.

## F4 — MAJOR — §6 does not book every number Phase 2 moved

The plan's preamble promises every number that moves; ledger 95 was rated HIGH in Phase 1b
for five unbooked movers. Checked §6 by searching its text (executed):

* **C2.3a (ledger 99)** — no §6 row. Moves: headline for zero-ceiling protocols
  `Limiting current: 0 uA (Water window)` → refusal (ledger text: 12 240 of 299 520);
  `report()["limiting_mechanism"]` becomes a sentence for those rows (CSV column); JSON gains
  `permits_no_current`. `permits_no_current` occurs 0 times in FIX_PLAN_v2.md.
* **C2.4** — JSON gains `monotonicity_capped` (0 occurrences in the plan);
  `SafetyAssessment.biphasic_ceiling_uA` / `biphasic_mechanism` new; the
  `DiscElectrode(100,"Pt")` monophasic ceiling 19.634954084936204 → 0.4531143250369894 µA
  (in ledger 2, not §6). The §6 row "monophasic `limiting_current_uA` | capped at the biphasic
  value; 0.0 for a continuous train" is wrong: executed, a monophasic protocol always FAILs
  Charge balance, so `limiting_current_uA` is `None` for every one; the cap and the drift
  ceiling move only `limit_bearing_ceiling_uA`.
* **C2.2** — the row is generic; the ledger's concrete movers (band 15285.50941588086 →
  9565.660239570918 µA, Shannon → Current density; `DiscElectrode(500,"SIROF")`
  998.0887516949169 → 461.0459210402362) are not in §6. Both reproduced.
* **C2.7 [98]** — the row says only Shannon moves. Option A also changed water-window
  outcomes: 1 863 of 16 200 configurations in the F2 grid went from `LimitDidNotSettle` to a
  number (2 439 → 576).
* **C2.3 [91]** — §6 books `767.2735903959687`; the package returns `767.2735903959689`
  (executed), which the C2.3 commit message itself states. The test constant and the
  docstrings at `assessment.py:799, 842` carry the seed, not the floored ceiling; the test
  passes only because it compares at `rel=1e-9`.

**Fix.** Add the rows; correct the C2.4 row to name `limit_bearing_ceiling_uA`; book the
floored ceiling digits.

## F5 — MAJOR — booked documentation, GUI and artifact updates not made

* `README.md` and `CHANGELOG.md`: untouched by every Phase 2 commit (`git log aaf3c85..HEAD --
  README.md CHANGELOG.md` lists none). §6 C2.4 says "also update README 'What it computes'
  table, `charge.py` module docstring". The table (`README.md:78-84`) still reads "Water window
  | Interfacial potential excursion vs electrolysis limits" with no drift clause, no monophasic
  NOT_EVALUATED for charge injection, and Known limitations (`README.md:238-240`) says nothing
  about the no-leak drift model.
* `neurostim/safety/charge.py:1-14` module docstring: unchanged; does not say CIC is not
  applied to monophasic delivery (the behaviour lives in `assessment._charge_check`).
* `neurostim/safety/water_window.py:9-45` module docstring ("What that leaves this check
  doing … the effect of anything that shifts the starting potential"): the drift clause is not
  mentioned.
* GUI: C2.1 added a charge-recovery spin box; `train_duty_cycle` (C2.5) has no GUI input,
  while §6's C2.1 [+] row books "GUI form" for both new fields.
* `example_output/` (untracked, regenerated by C0.4's script "once per numeric commit"):
  stale. Regenerated to scratch and compared: `assessment.json` lacks `train_duty_cycle`,
  `permits_no_current`, `monotonicity_capped`; `safety_report.pdf` differs; the other five
  artifacts are byte-identical.

**Fix.** Update the README table and limitations, the two module docstrings and CHANGELOG;
add the GUI field (seeded from `DEFAULT_TRAIN_DUTY_CYCLE`); rerun
`scripts/regenerate_example_output.py`.

## F6 — MINOR — a FAIL check whose detail says PASS

`WaterWindowResult.describe()` (`water_window.py:310`) derives its verdict from the peak alone.
Executed on ledger 2's own case:

```
[         FAIL] Water window: peak -0.02 V is inside the window, but +35.1 uA of net DC reaches the edge in 0.2558 s -- within the 1 s train
    Water window (PtIr, cathodic phase) -> PASS
      headroom      +0.582 V
      DC drift      +35.1 uA net DC ... reaches the window edge in 0.2558 s, before the train ends (1 s)
```

The very text ledger 2 complained about ("PASS with 0.58 V headroom") now sits under the
FAIL, on `describe()` and in the PDF detail. **Fix:** make `describe()` print the combined
verdict (or "peak within window; drift EXCEEDS").

## F7 — MINOR — drift ignores the train duty cycle

`net_dc_current_uA` (`protocol.py:299-301, 320-328`) is not scaled by `train_duty_cycle`, while
`n_pulses`, `average_current_uA` and `rms_current_uA` are, and the drift compares against the
wall-clock `train_duration_s` (`assessment.py:1786-1788`).

```
StimProtocol(3000, 90, 130, 1.0, waveform="monophasic", train_duty_cycle=0.2), band, C=250
n_pulses 26.0, total charge over the train 7.02 uC, window budget 8.977 uC
WW FAIL "... +35.1 uA of net DC reaches the edge in 0.2558 s -- within the 1 s train"
average_current_uA 7.02, net_dc_current_uA 35.1
```

The train delivers less charge than the budget, yet FAILs. Conservative, but a wrong number
and an internal inconsistency one commit after D5 said the field must reach every model that
consumes the train. **Fix:** scale the drift by the duty (or define drift over on-time and
say so), consistently in Charge balance's DC density.

## F8 — MINOR — test gaps in the drift code (executed mutants)

Full suite run against each mutant:

```
water_window.py: drift_anodic = anodic_first (ignore over-recovery sign)   -> 888 passed (SURVIVES)
water_window.py: exits_during_train `<` -> `<=`                             -> 888 passed (SURVIVES)
protocol.py: rms scaled linearly by duty                                    -> killed
protocol.py: n_pulses ignores duty                                          -> killed
compliance.py: required_V_at ignores the return phase                       -> killed
assessment.py: biphasic cap disabled                                        -> killed (2 tests)
```

Also: the only drift oracle is monophasic (F3 lives in the gap); the monotonicity sweeps
(`TestMoreCurrentIsNeverSafer`, the refusal-contract sweep) contain no `return_phase_ratio ≠ 1`
balanced protocol and only `r_a ∈ {0.5, 0.9}` (F1, F2 live in the gap). **Fix:** a boundary
pair for `exits_during_train` (T9-style), an over-recovery case asserting the anodic edge
for cathodic-first, and the F1/F2 populations.

## F9 — MINOR — the "refusal contract" equivalence restates the implementation

`test_none_exactly_when_no_amplitude_is_safe` (`test_data_model.py:1648-1680`) builds its
"independent" right-hand side from `NO_SAFE_AMPLITUDE` imported from the package and from
`assessment.limit_bearing_ceiling_uA` — exactly the two operands of
`no_safe_amplitude_note()` — so it cannot disagree with the code about what the set or the
ceiling is; its docstring says "Not tautological". The genuinely independent half (the
`fail_ceiling` bisection) runs on two configurations. **Fix:** run the oracle over the whole
sweep and write the set literally, as `_limit_bearing_names()` already does in the same file.

## F10 — MINOR — Charge balance flips with amplitude at its tolerance edge

`is_charge_balanced` compares a rounded difference against `1e-12 × Q`; for `r_a` within
~1e-12 of 1 the comparison depends on the rounding at each amplitude. Executed: 13 of 18
(`r_a` ∈ {1±1e-12 variants} × r ∈ {0.3, 1, 3}) flip PASS/CAUTION across
I ∈ {1e-12 … 1e6}. The D3 invariant (non-limit-bearing verdicts amplitude-independent) is
otherwise intact: 0 of 424 configurations across Pt/SIROF/Ta2O5 × r_a ∈ {0, .5, .9, .999, 1,
1.2} × r ∈ {0.3, 1, 3} × waveform × T moved (8 more raised ZeroDivisionError, F1). Only
PASS↔CAUTION, so `unsafe_at_any_amplitude` is unaffected. The F1 fix (exact-linear net)
removes it.

## F11 — MINOR — containment docstring false under the cap

`limit_bearing_ceiling_uA` is documented as "the one `limiting_current_interval_uA` must
contain", but the interval is built from the monophasic protocol's own checks and ignores
`biphasic_ceiling_uA`. Executed: `DiscElectrode(40,"Ta2O5")`, 80 µA/50 µs monophasic →
`limit_bearing_ceiling_uA` 22.116812281272146, interval [80.0, 80.0], `contains` False. Not
rendered (the headline is `None` for every monophasic protocol and the interval is not in the
JSON), so documentation-only today. **Fix:** include the cap in the interval, or narrow the
docstring.

## F12 — MINOR — CSV still applies the biphasic CIC to monophasic delivery

`report()` (`assessment.py:1951-1957`) returns `max_current_cic_uA` and `cic_limit_uC_cm2`
unconditionally. Executed: `DiscElectrode(500,"Pt")`, 80 µA/200 µs monophasic →
`max_current_cic_uA 981.7477042468105`, `cic_limit_uC_cm2 100.0`, beside a Charge-injection
check that is NOT_EVALUATED "no source here validates it for monophasic delivery". These are
0.1.0-compat columns in every batch CSV. **Fix:** `None` (or a documented flag) for monophasic.

## F13 — MINOR — option A (98) and non-monotone predicates

Executed a synthetic adversarial sweep (`sweep98.py`, 200 000 cases, four predicate families,
edge-clustered seeds ±5×allowance and ±8 ulps) comparing `floor_to_pass` at HEAD with the
pre-98 module:

```
plateau = 0: 54 862 cases, 0 differ from pre-98 (value or exception message) -- byte-identical
monotone step / quantised / offset-quantised (149 176 cases): 0 returned points FAIL,
  0 successors pass, 0 differ from an independent integer-bisection boundary
pre-98 raised, HEAD answers exactly (monotone): 8 387
non-monotone "notch" family (49 824): 0 returned points FAIL; 4 030 cases that raised pre-98
  now return a value ABOVE a failing band (the widened walk bisects [value - 4*plateau, failing]
  and lands on whichever transition it finds)
```

Real predicates: Shannon — 100 000 random (k, area 1e-12–10 cm², PW) configurations, 0 raises,
0 values differing from an independent float bisection of `shannon_k(Q,A) <= k`, for both
charge and current. Water window — 20 000 edge-clustered configurations: 0 ceilings failing
their predicate, 0 passing successors, 0 status/ceiling disagreements, 107 raises (F2).

So option A never returns a failing point and does not skip the boundary of a monotone
predicate; it does trade some loud detections of non-monotonicity for silent answers, and
F1/F2 show a shipped predicate that *is* non-monotone. Acceptable once F1/F2 are fixed; worth
a sentence in D2 point 2 that the walk down no longer detects non-monotonicity inside
`PLATEAU_ALLOWANCE × plateau`.

## F14 — MINOR — the binding zero ceiling is invisible in the figure

`current_limit_sweep` draws every finite ceiling; a ceiling of 0.0 is finite, so on the log
axis it is drawn at y = 0. Executed for `DiscElectrode(500,"Pt")`, 80 µA/200 µs/130 Hz,
T = inf, `r_a = 0.9`: y-limits (1.41, 2815.8); lines "Shannon criterion" 1245.9,
"Charge injection limit" 981.7, "Water window" **0.0**, "Current density" 540.2,
"Chronic degradation" 490.9; refusal text present. The reader sees four ceilings of hundreds
of µA and not the one that closed. **Fix:** mark a zero ceiling explicitly (label or arrow at
the axis floor).

## F15 — MINOR — silent fall-throughs in changed code

* `water_window.evaluate` (`water_window.py:363-381`) builds the drift only when
  `net_dc_current_uA`, `area_cm2` and `train_duration_s` are all non-`None`, each defaulting to
  `None`; a direct caller who supplies two of the three gets no drift clause and no warning,
  and a monophasic evaluation through the public module function reports the pre-ledger-2
  PASS. Raise when some but not all are given.
* `_charge_ceiling_interval` (`assessment.py:129-134`) falls back to `Interval.exact` — the
  pattern ledger 97 removed — for a check that has a published band. Unreachable from
  `charge.evaluate` (always sets it); the `# pragma` line sits on its own and does not exclude
  the `return`. Raise instead.
* `min(terms)` in `_water_window_seed_uA` silently discards a `nan` term (F1).

## F16 — MINOR — drift-bound limits are not flagged provisional

`caveats["Water window"]` (`assessment.py:1854-1855`) reads only `window.verified`. When the
drift clause binds, the limit rests on a leak-free capacitor, which the code itself calls a
lower bound (`assessment.py:1233-1236`). Merrill 2005 §2.4 (text extracted from
`papers_stim_calc_ref/merrill_2005_electrical_stimulation.pdf`) describes charge-imbalanced
trains reaching a steady state where "the net imbalance in injected charge is equal to the net
difference in cathodic and anodic unrecoverable charge" (eq. 2.8), and presents imbalance as
sometimes advantageous for reducing anodic corrosion. The continuous-train refusal
("Water window permits no current at all") is therefore a model bound, not a sourced
threshold. **Fix:** set `provisional=True` on Water window whenever `drift.drifts`, and say
"no-leak bound" on the refusal and CAUTION text.

---

## Non-vacuity (executed, scratch worktree; new tests at commit X, package at X^)

| Commit | Test class | Result on pre-fix package |
|---|---|---|
| de1aaf7 (C2.3) | TestDcDriftOutOfTheWaterWindow | 8 failed, 1 passed |
| 0ac7950 (C2.2) | TestTheReturnPhaseIsEvaluated | 6 failed, 1 passed |
| 9e87b85 (C2.1) | TestChargeRecoveryIsAnIndependentInput | 9 failed |
| 5276a40 (99) | TestTheHeadlineRefusesWheneverNoAmplitudeIsSafe | 8 failed |
| 5db8415 (C2.4) | TestMonophasicProtocolsStopInheritingBiphasicLimits | 4 failed, 4 passed (the passing four were not individually identified); cap-disabled mutant at HEAD kills 2 |
| 689ddc6 (C2.5) | TestTheTrainDutyCycleReplacesThePulseDuty | 8 failed, 1 passed |
| 33d3f13 (97) | TestEveryCeilingDeclaresItsInterval | 3 failed, 1 passed |
| ca51148 (100) | TestTheDerivedChargeLimitsFloor | 2 failed |
| 8ca9bd4 (98) | TestTheDeclaredPlateauAlsoBoundsTheWalkDown | 1 failed, 2 passed |
| 8ca9bd4 (98) | TestShannonDeclaresItsPlateau | 3 failed (the three reproduction/sweep tests), 5 passed |

## Verified as claimed (no finding)

* Booked values reproduce: band drift time 0.255757863465323 s, window charge 8.977101007632834
  µC, net DC 35.1 µA; C2.2 required_V 2.593599433515108 V, limit 9565.660239570918 µA (Current
  density); SIROF 461.0459210402362 µA; `DiscElectrode(100,"Pt")` monophasic
  `limit_bearing_ceiling_uA` 0.4531143250369894 with cap 19.634954084936204; envelope
  `inside` True for `StimProtocol(50,400,50,7*3600)` at 0.1 cm².
* Train duty wiring is physically right where it is applied: `n_pulses` and
  `average_current_uA` linear, `rms_current_uA` as √duty; the thermal model reads
  `rms_current_uA` (`models/thermal.py:595`). Two mutants killed.
* Monophasic handling: Charge injection NOT_EVALUATED with `limits_incomplete`; the cap closes
  the Ta2O5 inversions at equality; the twin is built by `copy.copy`, and an unconstructible
  twin leaves no cap. Monophasic drift agrees with the pulse-by-pulse oracle within one pulse.
* Return phase: current density compares each phase against Butterwick at its own width;
  compliance takes the max of the two phase budgets, both linear in the leading amplitude, so
  the closed-form seed stays exact. Symmetric goldens byte-identical.
* D3 invariant: 0 of 424 configurations move a non-limit-bearing verdict between 1e-12 and 1e6
  µA (F10 is the tolerance-edge exception).
* Option A byte-identical at `plateau = 0` over 54 862 cases including messages; Shannon exact
  over 100 000.
* Every render surface reviewed (`describe`, `report`, `report_to_json`, `io/report.py`,
  `gui/app.py:headline_text`, `viz/plots.py`, `sensitivity.py`) routes a refused protocol
  through `no_safe_amplitude_note()` and prints no headline number for it.
* 101: plain `pytest -q` green (888).

## Process note

65e9485 (a docs commit) carries C2.3's tests without its code, so `pytest` is red at that
commit — known and deliberately not rewritten; recorded here only because G12's
"re-run earlier phases' tests unchanged" is not bisectable across it. Per the team lead's
brief this review wrote only this file; `_conversation_history.md` (CLAUDE.md rule 14) was not
updated by the reviewer.

# VERDICT: **NO-GO** for Phase 3

Two BLOCKERs, both in C2.3's drift clause, both on inputs the package accepts, both invisible
to the suite because every drift test uses `r = 1` or `r_a ∈ {0, 0.5, 0.9}`:

1. **F1** — a charge-balanced protocol with `return_phase_ratio ≠ 1` can crash `assess()`
   (`ZeroDivisionError`, 140 of 4 160 finite-train cases in the sweep) or report a limiting
   current above an amplitude that FAILs (56 cases).
2. **F2** — 576 of 16 200 ordinary partial-recovery protocols raise `LimitDidNotSettle`
   (e.g. a 500 µm Pt disc at 10 µA, 50 µs, 130 Hz, 1 s, 99 % recovery).

One change fixes both: compute the unrecovered charge as `charge_uC(I, W) * (1 - r_a)` and
gate drift on `is_charge_balanced`. Land it with the F1/F2 sweeps as tests, decide F3 (the
combined peak-plus-drift budget) before Phase 3 builds on the water-window ceiling, and book
F4/F5. The MINORs can ride with Phase 3.
