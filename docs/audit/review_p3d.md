# Phase 3d Review — `git log 98f483b..c89fdf4`

Status: COMPLETE

Repo: .
HEAD: c89fdf4. The main tree was not modified. A scratch worktree at 98f483b was created
under the session scratchpad and removed. New scratch tools:

* `k1.py`: a far-side resting-potential sweep with before/after capture of every ceiling.
* `leak.py`: an inf/nan token scan of describe, GUI headline, `report()`, strict-parsed JSON,
  `sensitivity.describe`, PDF text, figure text and batch frames.
* `train_sim3.py`: the Phase 3c whole-train stepping plus the K3 bound.

## Commits in scope
889347b docs · ebdf596 K1 (ledger 142) · 362752e K2 (143) · 2d87352 K3 documented (144) ·
25cc8da K4 (145) · ledger commits 7537e8f, 148b34b, 9d1d503, c89fdf4.

## Summary

| # | Sev | Where | One line |
|---|---|---|---|
| L1 | MINOR | io/tabular.py `report_to_json` / `protocol_from_dict` | The new `protocol.train_duration_s: null` (continuous trains) no longer round-trips through the package's own reader. `protocol_from_dict(json["protocol"])` drops the `null` and raises `TypeError: missing 1 required positional argument: 'train_duration_s'`. Before, Python's `json` read `Infinity` back as `inf` and it worked. The strict-JSON change is right, but the reader should map `null` (with its `null_reasons` entry) to `math.inf`, or raise a named `ValueError` |
| L2 | MINOR | io/tabular.py `assess_batch` | In memory, the batch DataFrame holds `NaN` in `required_compliance_V` for an unbounded row, because pandas coerces `None` in a float column. On disk the CSV cell is empty and `required_compliance_note` carries the sentence, so nothing leaks to a file. A consumer testing `is None` on the frame will not see it |
| L3 | MINOR | compliance.py docstring / ledger 144 | The measured deficit is stated as "up to 6.7 %". My independent whole-train stepping finds up to **17 %** (Pt, r_a 1.1, N = 4). That case is still inside the stated bound and still a peak-clause FAIL above the limit, so only the quoted maximum is low |

Counts: **0 BLOCKER, 0 MAJOR, 3 MINOR.**

---

## Verification

**K1 (ledger 142): CLOSED.** I ran my own far-side generator: 7 materials with windows ×
rest {−0.8, −0.59, −0.5, −0.35, −0.2, +0.2, +0.5, +0.7} × 1 500 random (size, PW,
amplitude, polarity), which is 96 000 configurations.

```
98f483b: 18 LimitDidNotSettle (all TiN, rest +-0.2 far side)   HEAD: 0
previously-returned configurations whose ceilings changed (every check, repr-compared): 0 of 86 982
```

The original repro now assesses. The unbalanced sweep seed that hit K1 before now gives
1 500/1 500 oracle agreement.

**K2 (ledger 143): CLOSED on every render surface.** `leak.py` over 1 200 random
configurations (seeds 3 and 9):
* The mix: 9 materials; disc and 3389 band; monophasic and r_a 0–1.3; trains 0.01 s–∞;
  duty 0.5 and 1; compliance None/2/10 V; 40 % with a counter.
* Scanned on all 1 200: describe, GUI headline, the string fields of `report()`,
  `report_to_json` (parsed with `parse_constant` rejecting `Infinity`/`NaN`) and
  `sensitivity.describe`. The PDF text and summary-figure text were scanned on the first 120.
* Result: **0 `inf`/`nan`/`Infinity`/`NaN` tokens, 0 JSON strict-parse failures, 0 raises**
  (`allow_nan=False` never fired). No `report()` float field is non-finite.

Batch: see L2. The new keys are documented: `required_compliance_note` and `null_reasons`
in the README (line 66) and the CHANGELOG. The schema change is judged in L1.

**K3 (ledger 144): the bound is sound.** Whole-train stepping, clamped at the edge with
branch C_eff, covered 7 500 (seeds 11–13) + 7 200 (six seeds, r_a up to 2.0) configurations.
It found 33 cases where the budget is below the stepped maximum. In **every one**:
* the deficit is at or below `min(N·e/(C_opp·A), H_opp)`, with
  `e = max(0, Q − H_lead·C_lead·A)`;
* the Water window peak clause fails (`water_window.passes` is False);
* the configured amplitude is above the limiting current, or the headline is refused.

So "never bears a limit" holds. The largest deficit is ×1.17, not the documented 6.7 % (L3).

**K4 (ledger 145).** The §6 wording change was reviewed. The builder's newly booked J2 text
mover (SS316LVM "7.853-7.853 uA" → "7.853 uA") is consistent with J2 flooring both ends onto
the same float. It was not independently re-derived here.

**Regressions (executed at HEAD):**
* unbalanced sweep: 1 500/1 500 oracle agreement, 332 capped, all Water window FAIL, 0
  raises, 0 NaN, refusal iff holds;
* residual sweep: 6 240/6 240;
* lds_rate: 0 of 16 200;
* ww98: 20 000 configurations, clean;
* mixed geometries with counters: 1 200/1 200;
* containment: 0 of 3 000 outside.

## Process note
Per the brief, this review wrote only this file. The reviewer did not update
`_conversation_history.md` (CLAUDE.md rule 14).

# VERDICT: **GO** for Phase 4

Both Phase 3c conditions are met. K1 is fixed at its source: 18 → 0 over 96 000, with no
other float moving. K2 emits strict JSON and no render surface prints a bare infinity. K3's
documented bound holds against an independent whole-train simulation. The three MINORs are
cheap and can ride with the first Phase 4 commit that touches `io/tabular.py`. L1 is the one
that could bite a user who reloads a saved assessment.
