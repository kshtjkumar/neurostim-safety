# Phase 3b Review — `git log 278932b..26d833c`

Status: COMPLETE

Repo: .
HEAD: 26d833c. The main tree was not modified. A scratch worktree was created under the session
scratchpad and removed. The independent solvers are the ones used in review_p3
(`fv_band.py`, `fv_tip.py`, `fv_pair.py`) plus sweep scripts, all in the scratchpad.

## Commits in scope
```
26d833c docs(ledger)            b355890 C3.11 counter charge injection (133)
b09595a docs(ledger)            f072907 C3.8  bare flat microwire tip -> Newman disc (129)
2867ffe docs(ledger)            982b65b C3.10 counter spacing guard; drift-CAUTION header (130, 132)
c73c1ae docs(ledger)            248a6f5 C3.9  per-phase polarity C_eff (131)
a9f2432 docs(ledger)            f2b6a0a C3.7  converged FD band table (127)
bc48e20 / c37c2f6 logs H1-H8 as 127-134, H8 fix
```

## Gates at HEAD (executed)
`pytest -q`: 1029 passed, as confirmed on the main thread. I re-ran the full suite five times
under mutants in the worktree (below).

## Summary

| # | Sev | Where | One line |
|---|---|---|---|
| J1 | MAJOR | safety/compliance.py:176-214, 400-417 (C3.9) | The per-phase polarity change is physically wrong for any pulse whose return phase does not overshoot rest. Under the package's own capacitor model, the return phase carries the interface **back** through the leading polarity's region to rest; it never reaches the opposite polarity. Giving that traversal the opposite polarity's `C_eff` inflates Pt/PtIr requirements (worked example 0.8287 → 1.0550 V, ceiling 965.38 → 758.26 µA). It is conservative against truth, but a calculation error on the default example. **My H5 prompted this, and H5 was framed inside a return-phase model that already double-counts. I retract H5's recommendation** |
| J2 | MINOR | safety/assessment.py `limiting_current_interval_uA`, `_counter_charge_ceiling_interval` | The interval fails to contain its point estimate by 1–2 ulps: the floored ceiling against an unfloored interval end. **55 of 3 000** active Charge-injection-bound protocols (pre-existing: identical at 39331bf), and **47 of 600** counter configurations, most of them bound by the new counter check |
| J3 | MINOR | safety/assessment.py `caveats` dict | `caveats.get(check.name, False)`: a typo in the counter check's caveat key survives the full suite (1029 pass), silently making its limit non-provisional. It is the ledger-97 fall-through pattern, still present for provisional |
| J4 | MINOR | tests/oracles/fd_microwire.py docstring | It cites "the Phase 3 reviewer's independent solve gives 0.1755" at ℓ = 0. That was my unconverged value. Refined, my solve gives 0.17817, 0.17547, 0.17415, 0.17359, which extrapolates to **~0.1731**, agreeing with the table's 0.1726–0.1729. The table is fine; the citation should be updated. Note also that the generator imports `_clustered` from `fd_band_reference`, so it is independent of `neurostim` but not of the band solver |
| J5 | MINOR | safety/compliance.py `_reach_um` | Half the largest dimension understates a rectangle's reach (half its diagonal is larger). This is small and only affects rectangles near the guard |

Counts: **0 BLOCKER, 1 MAJOR, 4 MINOR.**

---

## J1 — MAJOR — C3.9's return-phase polarity is not the physics

**What the model says.** For a cathodic-first, charge-balanced pulse:
* The leading phase drives the interface from rest to −ΔV along the cathodic branch, with the
  cathodic `C_eff`. The stimulator supplies `I·R + ΔV`.
* The anodic return phase then carries it from −ΔV back to rest, removing charge stored on
  that same cathodic branch. The stimulator supplies `−I_ret·R` against a capacitor that
  starts at −ΔV and ends at 0. Its magnitude runs from `I_ret·R − ΔV` to `I_ret·R`, and never
  exceeds `I_ret·R`.

Only over-recovery (`r_a > 1`) carries the interface past rest into the anodic branch, and
only by the excess `(r_a − 1)·Q`.

**What the code does.** The return-phase budget has been `I_ret·R + ΔV_ret` (its own full
excursion from rest) since C2.2. That was already conservative. For a symmetric pulse it
equals the leading term, so it never changed the answer. C3.9 now computes `ΔV_ret` at the
opposite polarity's `C_eff`. For Pt/PtIr (125 against 250 µF/cm²) this doubles the fictitious
term, so the return phase binds every symmetric Pt/PtIr pulse.

Executed on the worked example (330/270 µm Pt ring, 80 µA/200 µs/130 Hz, 10 V):

```
required_compliance_V 0.8286922987786409 -> 1.0550459956204477 V   (+27 %)
compliance ceiling    965.3764143567779  -> 758.2607804027908  uA  (-21 %)
Pt disc 100 um        1.957730451487647  -> 2.7726037601181512 V
```

Under the capacitor model the package itself uses, the correct symmetric-pulse requirement is
the leading one: `I·R + ΔV_lead = 0.8287 V`. That is the pre-C3.9 value.

**Direction.**
* Against the truth above, every C3.9 value is still at or above the correct requirement.
  The "24 down" moves (AIROF, PEDOT, cathodic-first, where the anodic `C_eff` is larger) only
  shrink an overestimate. So no number is anti-conservative.
* The defect is an unsourced mechanism that inflates the default README transcript's
  Compliance line (0.83 → 1.06 V) and the instrument-kind limit.
* The counter's return-phase term (C3.9's other half) has the same flaw. The counter's
  leading-phase term at the opposite polarity (C3.5) is correct: that is the counter's real
  excursion.

**H5 retracted.** My Phase 3 H5 asked for exactly this per-phase polarity. I reasoned inside
the return-phase model without questioning that the model adds a return excursion from rest
at all. The builder implemented what I asked for. The error is mine.

**Fix.** Give the return phase `I_ret·R + ΔV_excess`, where
`ΔV_excess = max(0, (r_a − 1))·Q / (C_opposite·A)` for the active electrode, and likewise for
the counter. That gives exact `I_ret·R` for balanced and under-recovered pulses, and the
opposite polarity's `C_eff` applies only to the part beyond rest. Then:
* restore the symmetric-pulse numbers (the worked example returns to 0.8287 V / 965.38 µA);
* re-book §6 C3.9;
* re-pin the goldens;
* keep `max_current_uA` inverting `required_V_at`.

If the user prefers to keep the current conservative form, document it as a deliberate
overestimate with its size (+27 % on the worked example), not as the physics.

## J2 — MINOR — interval containment fails by ulps (pre-existing; widened by C3.11)

`limiting_current_interval_uA` takes the check intervals from unfloored arithmetic
(`limit·A/W`, and for the counter `× 1/scale`). The point estimate is `floor_to_pass`'s
boundary, which may sit one or two ulps above.

```
contain.py, 3 000 random single-electrode protocols (9 materials, 3 policies, 2 media):
  HEAD:    55 not contained, all bound by Charge injection limit
  39331bf: 55 not contained (identical, so pre-existing since Phase 1)
600 random counter configurations: 62 not contained, 47 of them bound by Counter charge injection
  e.g. SIROF/SIROF optimistic in vivo: point 8.675795347284206, interval [1.735..., 8.675795347284204]
```

C1.8/C1.11's containment tests pass only on their fixed grids. **Fix:** floor the interval
ends through the same predicate (or widen by the settle distance), and add a random-sweep
containment test that includes counters.

## J3 — MINOR — the provisional flag still falls through silently

Mutant: rename the caveats-dict key to `"Counter charge injectoin"`. The full suite gives
**1029 passed**. The ceilings-dict typo, a typo in the emitted check name, the unmirrored CIC,
and the dropped over-recovery scale are each killed by exactly one test. **Fix:** make
`caveats` a lookup that raises, like `CEILING_INTERVALS`, or assert its keys equal
`LIMIT_BEARING`.

## J4, J5 — see the table.

---

## Verification of the lead's items

**C3.7 (H1): CLOSED.**
* The regenerated table against my independent FV (executed): 653.4/653.7, 520.4/520.6,
  473.7/473.9, 353.8/353.9, 327.6/327.8, 252.3/252.5, 171.8/171.9, 96.7/96.7. Every entry
  agrees to 0.08 % or better.
* A search for "within 2 %", "335.1" and "−1.7 %" across the README, CHANGELOG, package, tests,
  scripts and plan finds only annotated historical mentions (plan §1/§2 notes, the oracle's
  "the first table was wrong" section, test docstrings naming the replaced value), plus
  base.py's "(ledger 127 corrected an earlier, unconverged 'within 2 %')". No live claim remains.

**C3.8 (H3): CLOSED.**
* `MicrowireElectrode(50,0,"flat")` gives 28571.428571428572 Ω (Newman); at 5 V `required_V`
  is 0.6931509400295378 and `max_current_uA` 72.13436080440043. Both are booked exactly.
* Independence: see J4. My converged solve (~0.1731) and the table (0.1726) agree, so
  choosing the upper bound 0.25 is sound.

**C3.9 (H5):** see J1. The booked digits are exact:
* 1.0550459956204477 V and 758.2607804027908 µA;
* 2.7726037601181512 V (Pt disc 100 µm) and 1.4306086118430048 V (SIROF disc 500 µm);
* the 3389 bipolar pair is unchanged at 1.3488137938726137 V, correctly, because the two
  interfaces swap polarities between phases.

**C3.10 (H4, H6): CLOSED.**
* The guard now uses `max(substitute radius, half largest dimension)`, which is 750 µm for a
  3389 band, so the 1390–1499 µm inputs are refused.
* The drift-CAUTION header reads "-> CAUTION (…)". The J5 caveat applies to rectangles.

**C3.11 (H7): sound. The focus questions:**
1. **Conditional emission against D3 and the refusal contract.**
   * The counter check is limit-bearing, not in `NO_SAFE_AMPLITUDE`, and can only refuse
     through a zero ceiling, which the iff-contract already covers.
   * `CEILING_INTERVALS` declares it (the keys-equal-`LIMIT_BEARING` test holds).
   * The oracle's `COUNTER_ONLY_CHECKS` excuses its absence only when the calculator has no
     counter.
   * Typo mutants: the emitted name, the ceilings key, the mirrored polarity and the scale
     are all **killed**. The caveats key is not (J3).
2. **Renders.** Executed on `DiscElectrode(200,"Pt")` with a `DiscElectrode(50,"Pt")` counter.
   The check appears in describe, the JSON `checks[]`, PDF text and the GUI headline
   ("limiting current 4.908 uA (Counter charge injection)").
   * Batch and GUI cannot supply a counter (ledger 126), and the check is emitted only with a
     counter, so no limit-bearing check is silently dropped there. Those surfaces simply
     cannot ask the question.
   * The JSON `settings` block still omits the counter (126, unchanged).
   * Monophasic plus counter gives NOT_EVALUATED, named in the INCOMPLETE note.
3. **Mirrored CIC.** The active check keys the stored CIC by the waveform's leading polarity,
   applied to the leading charge. At the counter the leading polarity is the opposite
   (`not protocol.anodic_first`), and the charge is the larger phase
   (`max(1, r_a)·Q`, the return being larger only on over-recovery). Policy, medium and
   derating are identical. That is consistent with how the active check keys CIC. The FAIL
   summary's "max" is rewritten to the leading-amplitude ceiling, which reproduces:
   4.908738521234051 µA = Pt anodic 50 µC/cm² × counter area / 200 µs.
4. **§6 movers.** All executed values match to the last digit:
   * 78.53981633974482 µA (Chronic degradation) → 4.908738521234051 µA (Counter charge
     injection);
   * the 3389 bipolar headline stays 15285.50941588086 µA (Shannon);
   * the C3.7, C3.8 and C3.9 numbers above.
5. **Docs.** The README table and limitations, the compliance docstring and the CHANGELOG
   describe the code, including the counter's unassessed water window and chronic threshold.
   J1 is a physics defect that the docs faithfully describe.
6. **Regression grids (executed at HEAD):**
   * residual sweep: 6 240/6 240 exact zero net;
   * lds_rate: 0 of 16 200 raise; the repros are ok;
   * ww98: 20 000 configurations, 0 raises or disagreements;
   * disc oracle round-trip: 1 000 configurations, 843 agree and 157 are both zero;
   * mixed geometries with counters (oracle now including the counter check): **1 200 of
     1 200 agree**.

## Process note
Per the brief, this review wrote only this file. The reviewer did not update
`_conversation_history.md` (CLAUDE.md rule 14).

# VERDICT: **GO** for Phase 4, with one condition

Every Phase 3 finding is closed or correctly scheduled:
* the FD table now agrees with an independent solve to 0.08 %;
* the counter check is limit-bearing, mirrored correctly, rendered everywhere it can be, and
  guarded against typos except for `provisional`;
* no grid regresses.

**Condition:** resolve J1 before release. Either restrict the return-phase polarisation to
the overshoot beyond rest (restoring the worked example's 0.8287 V / 965.38 µA), or record the
current form as a deliberate, sized overestimate. It is conservative, so it need not block
Phase 4 work, but it is a wrong mechanism in the default output. J2 and J3 are cheap and
should ride with the next commit that touches the interval or the caveats.
