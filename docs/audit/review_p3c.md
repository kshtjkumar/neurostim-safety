# Phase 3c Review — `git log 26d833c..98f483b`

Status: COMPLETE

Repo: .
HEAD: 98f483b. The main tree was not modified. A scratch worktree (26d833c, a9f2432,
39331bf, aaf3c85) was created under the session scratchpad and removed. The new independent
tools are all in the scratchpad and none uses the package's compliance or drift code:

* `train_sim.py`: whole-train stepping of both interfaces through every phase, with
  branch-dependent C_eff, clamping at the window edge (electrolysis) and duty-scaled N.
* `unbal_rt.py`: an unbalanced-train sweep covering raises, NaN, the refusal contract, capped
  ⇒ FAIL, the oracle round-trip and containment.
* `iv_ends.py`: interval-end exactness.
* a branch-C drift stepper.

## Commits in scope
6c5f34d C3.12 (J1) · 3595c05 J3 · 5372f77 J4 · bd8297b J5 · b0ab74f C3.17 (140) ·
758ac66 C3.18 (141) · ca356f8 C3.15 (J2) · plus the docs and ledger commits 2165bc8, 8dd1910,
f822d1b, bc371aa, f27b3ec, 6363001, afb0f03, 7924bce, 98f483b.

## Summary

| # | Sev | Where | One line |
|---|---|---|---|
| K1 | MAJOR (pre-existing) | assessment.py `_water_window_search` plateau | `LimitDidNotSettle` out of `assess()` on accepted input: TiN, resting potential 0.2 V on the far side of the leading edge. **18 of 60 000** swept. The declared plateau uses `ulp(max(|rest|, |edges|))`, but the excursion itself is 1.1 V, which is in a larger binade than 0.9 V. The seed lands 5 floats, 5.76 plateaus, above the boundary, beyond `PLATEAU_ALLOWANCE = 4`. Present at 39331bf; this is the fragility review_p1b flagged as MINOR, now realised |
| K2 | MAJOR | compliance → io/tabular, describe, PDF, batch | An infinite `required_V` (continuous unbalanced train with a counter, or on Ta2O5) is rendered as a bare `inf`: "needs inf V", "requires inf V", "train offset inf V ... after inf unbalanced pulses". The batch `required_compliance_V` column is `inf`. **`report_to_json` emits `Infinity`, which is not valid JSON**: a strict parser (`parse_constant` rejecting it, or any RFC 8259 consumer) fails. The headline itself refuses correctly |
| K3 | MINOR | compliance.py docstring and README ("upper bound") | The train-offset budget is not an upper bound in one regime. With over-recovery, when the leading phase already exceeds the window (electrolysis dumps part of Q), the next return phase overshoots further than `(r_a − 1)Q`. Whole-train stepping: **13 of 7 500** configurations have the package below the stepped maximum, by up to 17 %. All 13 are Water window FAIL, with the configured amplitude above the limit, so **no reported limiting current is affected**. Only the Compliance check's own number and the "instrument" by-kind figure are low in that regime |
| K4 | MINOR | FIX_PLAN §6 C3.12 row | "Every symmetric balanced configuration is byte-identical to pre-C3.9" holds for every number, status and limit. It does not hold for the text: the compliance detail's diagnostic `return phase X V` line moves (e.g. 0.337 → 0.286 V) because it now prints `I_ret·R`. Executed over 4 608 configurations against a9f2432: 1 800 of the r = 1 balanced ones differ, and only in that line |

Counts: **0 BLOCKER, 2 MAJOR, 2 MINOR.**

---

## K1 — MAJOR (pre-existing) — a peak-clause settle failure the plateau under-declares

```
SafetyCalculator(DiscElectrode(570.7046435217787,"TiN"), StimProtocol(10,200,20,1,anodic_first=True),
                 resting_potential_V=-0.2).assess()
-> LimitDidNotSettle: Water window: the back-solved limit 15632.659691332417 still fails its own
   check after 4 steps down ...
seed 15632.659691332417, plateau 1.5777944295860763e-12, boundary 5 floats (5.76 plateaus) below
identical at 26d833c and 39331bf; independent of amplitude, frequency, duty and return ratio;
570.0 / 571.0 um do not raise
sweep, 9 materials x rest {+-0.2, +-0.35, +-0.5} x random size/PW/polarity: 18 of 60 000 raise,
   all TiN with 0.2 V on the far side
```

TiN's window is ±0.9 V. From −0.2 V, an anodic-first pulse must travel 1.1 V, and the sum
`rest + excursion` rounds in the [1, 2) binade (ulp 2.2e-16). The plateau is declared from
`ulp(0.9)` (1.1e-16), which is exactly the "declared plateau can be 2× smaller than the true
resolution when the resting potential sits on the far side" that review_p1b recorded as MINOR.
It is a crash on accepted input, so it is the ledger-88/98 class, though rare and pre-existing.

**Fix:** include the excursion at the boundary, `|edge − rest|`, in the `max(...)` that sets
`plateau_uA`. Add a far-side-rest sweep (TiN included) asserting zero raises.

## K2 — MAJOR — infinite requirement leaks as `inf` / `Infinity`

Executed on `DiscElectrode(500,"Ta2O5")`, 80 µA/200 µs/130 Hz, continuous, r_a 0.9:

```
compliance_V=10:  CV FAIL "needs inf V but only 10.00 V available"; headline "no amplitude is safe:
                  Compliance voltage permits no current at all" (correct); report required inf;
                  JSON contains Infinity -> strict parse fails; PDF "inf V (0.229 V ohmic + 0.407 V
                  polarisation; train DC offset inf V ..."; batch required_compliance_V = inf
no compliance_V:  CV NOT_EVALUATED "requires inf V"; the limit stays numeric (540.17 uA, limits_incomplete)
```

The refusal contract holds (see below), and the text is truthful. But the brief's requirement
is that no surface prints "inf", and invalid JSON breaks every machine consumer of
`report_to_json`.

**Fix:** render an unbounded requirement as a sentence ("no finite voltage: the counter's
offset is uncapped over a continuous train"). Serialise it as `null` plus a reason key (as
`ceiling_uA` already does), or pass `allow_nan=False` after mapping.

## K3 — MINOR — the offset budget's "upper bound" has an electrolysis exception

`train_sim.py` steps both interfaces through all N pulses. It uses branch-dependent C_eff,
clamps the active electrode at the window edge (the excess charge goes to electrolysis),
leaves the counter unclamped, and uses N = ceil(duty-scaled n_pulses). Three seeds:

```
7 500 configurations: equal 6 714, package above 773 (up to x2.87, conservative), package BELOW 13
the 13: all r_a > 1 (1.01-1.6), N = 1-130, with and without counter; every one Water window FAIL
        and limit < configured current
```

A leading phase that crosses the edge loses charge to electrolysis, so the following
over-recovering return overshoots by more than `(r_a − 1)Q`. Clamping happens only when the
peak clause already FAILs, so no limiting current can sit in that regime. **Fix:** document the
exception, or compute the overshoot from the clamped state.

## K4 — see the table.

---

## Verification of the lead's focus items

**(1) Physics of 140/141 against the capacitor model.**
* **Under-recovery (140).** The last pulse's leading phase peaks at `offset(N−1) + Q` on the
  leading branch; the code adds `(N−1)(1−r_a)Q/C_lead` to the leading term. **Over-recovery.**
  The return phase ends at `−offset(N)`; the code adds `(N−1)(r_a−1)Q/C_opp` plus the overshoot.
  Both are exact against the stepping in the no-clamp regime: 6 714 of 7 500 are equal to
  1e-9.
* **The counter** mirrors the offset on its own branches, uncapped.
* **Duty.** Compliance uses the pulses actually delivered, `ceil(T f d)`, which is physically
  right for a leak-free capacitor. The drift clause's `f·T` over-counts, so it is conservative.
  Nothing anti-conservative follows from the ledger-109 inconsistency. The only
  anti-conservative cells are K3's, and they are inside a Water window FAIL.
* **141.** A branch-C drift stepper was compared with the package's `time_to_exit_s` over
  2 803 configurations (6 materials, both polarities, r_a 0.3–1.6, random rest). The maximum
  disagreement was **0.99995 pulse**. The drift direction's C_eff is right, over-recovery
  included.

**(2) "Capped offset ⇒ WW FAIL", both drift directions.**
* Analytic argument. Under-recovery: a cap means `(N−1)(1−r_a)Q ≥ Qw`, so the drift
  `n_exit = (Qw − r_aQ)/((1−r_a)Q) ≤ N−1 < f·T`. Over-recovery, with the same opposite-branch C
  (141): `n_exit = Qw_opp/((r_a−1)Q) ≤ N−1`. Both give t_exit < T.
* Executed: `unbal_rt.py` over 3 000 unbalanced configurations. It includes monophasic,
  r_a 0–1.6, return ratios 0.5/1/2, duty 0.1–1, trains 0.01 s–∞, rest 0/−0.2/+0.3, 40 %
  with counters, and compliance None/2/10 V. **651 capped, 651 Water window FAIL, 0
  exceptions.**

**(3) Refusal iff-contract with the new inf/None cases.** In the same 3 000:
* `limiting_current_uA is None` ⇔ (Charge balance FAIL or `limit_bearing_ceiling_uA ≤ 0`)
  in every case.
* No NaN appears in any ceiling or margin, and no returned limit is non-finite or ≤ 0.
* The own-check ceiling agrees with the bisection oracle in 2 999 of 2 999 (the other one
  raised: K1).
* Renders: the headline refuses on describe, JSON, PDF, GUI and batch. The bare `inf` is in
  the requirement lines (K2).

**(4) J2 soundness.** Interval ends were compared at 26d833c and HEAD over 2 000
configurations. They move by −2 to +2 ulps, and **each of the 4 000 ends is exactly the float
boundary of its sourced CIC bound**: the density at the end is at or below the bound, and one
float up exceeds it. So no band is narrowed below its sourced range. Containment: `contain.py`
over 3 000 gives **0 not contained** (55 at 26d833c), and 0 in the unbalanced sweep.

**(5) Worked example and README.**
* The worked example gives 0.8286922987786409 V and 965.3764143567779 µA, exactly.
* The README transcript block is **identical to a9f2432's** (pre-C3.9), compared directly.
* Balanced protocols against pre-C3.9 are unchanged in every number, status and limit. The
  only textual change is K4.
* J5 reach: `_reach_um` gives dbs_3389 and dbs_3387 982.7130812195388 µm and dbs_kuncel
  979.4896630388705 µm.

**(6) §6 digits.** All executed, all exact:
* **C3.12:** 0.8286922987786409 / 965.3764143567779; 1.957730451487647; 1.4300993160251108;
  band r 0.2, 1.647307218918153.
* **C3.17**, Pt 500 µm, r_a 0.95:
  * 1 s: 0.5892545931791486 V, max 2879.390735317558 µA;
  * continuous: 0.9264579511458109 V;
  * with a 900 µm Pt counter: inf V, max 0.0 µA, headline None;
  * Ta2O5 continuous: inf V, limit None;
  * r_a 1.3, 1 s: 1.1958747706874866 V.
* **C3.18:** 25.17301805761052 µA with t 0.08391006019203508 s; 37.75952708641578 µA; Pt
  100 µm r_a 1.5 FAIL at 0.030207621669132628 s; r_a 1.3 anodic-first CAUTION at
  0.07551905417283154 s.
* **C3.15:** 39.26990816987241 on both point and low end.

**Docs** match the code, except the "upper bound" wording (K3) and "byte-identical" (K4).

**J3.** The caveat keys now raise, closing my Phase 3b mutant. The mutant was not re-run
here; the builder states it and the 3595c05 tests exist.

**(7) Regression grids (executed at HEAD):**
* residual sweep: 6 240/6 240 exact zero net;
* lds_rate: 0 of 16 200 raise; the two repros are ok;
* ww98: 20 000 configurations, 0 raises or disagreements;
* disc oracle round-trip: 1 000 configurations, 843 agree and 157 are both zero;
* mixed geometries with counters: **1 200 of 1 200 agree**;
* unbalanced trains: 3 000 configurations, 1 raise (K1, pre-existing) and 0 NaN.

## Process note
Per the brief, this review wrote only this file. The reviewer did not update
`_conversation_history.md` (CLAUDE.md rule 14).

# VERDICT: **GO** for Phase 4, with two conditions

The Phase 3c physics is right:
* the return phase and the train offset match an independent whole-train stepping exactly
  outside the electrolysis regime;
* the drift branch C is within one pulse over 2 803 configurations;
* capped ⇒ FAIL holds in 651 of 651;
* J2's ends are exact boundaries;
* the worked example and README are restored byte for byte.

**Conditions, before Phase 4 closes:**
1. Fix K1. The fix is one term in the plateau, and the defect is a crash on accepted input,
   even though it is rare and pre-existing.
2. Fix K2's JSON: `Infinity` must not be emitted. The text renders should say "no finite
   voltage" rather than "inf V".

K3 and K4 are doc-level and can be scheduled.
