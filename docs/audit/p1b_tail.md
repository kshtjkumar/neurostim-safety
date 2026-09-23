# Phase 1b — the truncated remainder

Continues from "Yes — with one condition already carried by the code and a test."
Repo at `aaf3c85`, 814 tests, five gates clean. Every number below was produced by
`.venv/bin/python` at that commit.

---

## 1. The rest of the Phase 2 verdict

B1 (ledger 88), B2 (89), F3 (90), M2 (92), M3 (95), M4 (93), M5 (94) and the
non-amplitude render class (96) are closed, each with red-before/green-after and all five
gates clean. The review's NO-GO rested on B1, B2, B3's seed and M2; three of those four are
closed outright and the fourth is carried as an enforced obligation rather than a fix.

**Phase 2 may proceed, subject to one condition. For the builder's brief, verbatim:**

> **C2.3 must add the DC-drift term to `_water_window_seed_uA` in the same commit that adds
> the DC-drift clause to the water-window predicate. They are one change. Landing the clause
> without the seed term makes `floor_to_pass` raise `LimitDidNotSettle` on every monophasic
> protocol; landing the seed term without the clause makes it raise on every monophasic
> protocol in the other direction (measured: 160 of 160 swept configurations, 0 of 160
> biphasic). `TestTheWaterWindowSeedInvertsItsOwnPredicate` fails if they are separated, in
> either direction. Do not satisfy it by widening `CLIMB_TOLERANCE`, `STEP_BUDGET` or
> `PLATEAU_ALLOWANCE`: all three are straddled by behavioural tests that fail if the
> constant moves (`TestBothSettleBudgetsAreBinding`).**

That is the whole condition. Nothing else in Phase 1b blocks Phase 2, and no other Phase 1b
result depends on Phase 2 landing in any particular order.

---

## 2. What the Phase 2 builder must do about the water-window seed

### Which commit

**C2.3**, and only C2.3. Not a follow-up, not C2.4. The clause and its closed-form inverse
are a single edit to `neurostim/safety/assessment.py`:

* the clause goes into `stays_in_window`, inside `_water_window_search`;
* the inverse goes into `_water_window_seed_uA`, as a **second entry in the list** the `min`
  already takes. The list exists for exactly this and today has one member.

Both functions are adjacent in the file and both are returned through `_WindowSearch`, which
is what makes the coupling assertable.

### What the failing test says if they are separated

Adding C2.3's clause alone in a scratch tree produces, on the plan's own case:

```
E   Failed: the water-window seed no longer inverts the predicate it seeds, for
    ('PtIr', 1270.0, 3000.0, 90.0, 'monophasic'): Water window: the back-solved limit
    6749.062117423617 still fails its own check after 4 steps down to 6749.062117423613.
    A one-ulp disagreement between the back-solve and the forward comparison is what this
    walk is for; this is a larger disagreement, so the two are not inverses of each other
    and no value in between can be reported as the limit.. A clause added to the forward
    check needs its closed-form inverse in _water_window_seed_uA, in the same commit.
```

Test: `tests/test_verdict_core.py::TestTheWaterWindowSeedInvertsItsOwnPredicate::test_the_seed_inverts_the_predicate_it_seeds`.
Two companions fail alongside it:
`::test_the_seed_is_a_minimum_over_the_clauses_the_check_actually_has` (the seed is no
longer the peak-excursion inverse — this one is *expected* to need updating, and is where
the builder records the new seed), and
`::test_the_monophasic_water_window_ceiling_is_the_pulse_peak_inverse_today` (the tripwire
on the value, which C2.3 moves deliberately).

### The closed-form inverse, with its verified constants

```python
(window_headroom_V * capacitance_uF_cm2 * area_cm2)
    / (net_charge_fraction * pulse_width_s * frequency_hz * train_duration_s)
```

* `window_headroom_V` — distance from `resting_potential_V` to the window edge **in the
  drift direction**: `window.anodic_V - resting` when `anodic_first`, else
  `resting - window.cathodic_V`. Same expression
  `max_charge_density_in_window_uC_cm2` already uses for `available_V`.
* `net_charge_fraction` — per-pulse unrecovered fraction: `1.0` monophasic;
  `1 - charge_recovery_ratio` once C2.1 lands; `0.0` for a perfectly balanced biphasic
  pulse, which must map to a drift ceiling of `inf` (no drift bound), **not** to a division
  by zero. Guard it before dividing.
* `pulse_width_s` is `pulse_width_us * 1e-6`.

Verified against the plan's own numbers on
`CylindricalBandElectrode(1270, 1500, "PtIr")`, 3000 µA / 90 µs / 130 Hz monophasic,
`capacitance_uF_cm2=250`, `area_cm2 = 0.05984734005088556`:

```
Q_window   = 0.6 V x 250 uF/cm^2 x 0.05984734005088556 cm^2 = 8.977101007632834 uC
t_exit     = 8.977101007632834 / 35.1 uA                     = 0.2557578634653229 s   (plan: 0.2558 s)
drift      = 8.977101007632834 / (90e-6 x 130 x 1)           = 767.2735903959687 uA
peak seed  (today's, unchanged)                              = 99745.56675147593 uA
ratio                                                        = 130.0  ( = f x T )
```

Monotonicity survives the addition: both branches are individually monotone-decreasing in
current, so their conjunction is, and `floor_to_pass`'s precondition holds. The plateau
declaration already in `_water_window_search` does not change — it is a property of the
potential comparison, which the drift clause also performs.

---

## 3. What I now believe is wrong in §5.2 (C2.1–C2.5)

Five items. The first two are consequences of M2, which the plan predates.

### (a) C2.4 point 3 — the monotonicity cap names the wrong attribute. **Blocking.**

> "*`limiting_current_uA` for a monophasic protocol is additionally capped at what the same
> electrode and protocol would report biphasic.*"

Since `15a943c`, `limiting_current_uA` is `None` for **every** monophasic protocol —
verified 12 of 12 across four diameters × three pulse widths — because Charge balance FAILs
at every amplitude and is not limit-bearing. Capping it is capping `None`.

The cap must be applied to **`limit_bearing_ceiling_uA`**, which is a float for every
protocol and is the quantity the cap is actually about. Rewrite the point as: *the
limit-bearing ceiling for a monophasic protocol is additionally capped at the ceiling the
same electrode and protocol report biphasic.*

### (b) C2.4 test T4 assertion (a) is a `TypeError` as written. **Blocking.**

> "*(a) on the 110 cases v1 would have inverted, `mono.limiting_current_uA <
> bi.limiting_current_uA` strictly…*"

At HEAD that comparison is:

```
TypeError: '<' not supported between instances of 'NoneType' and 'float'
```

Both sides must read `limit_bearing_ceiling_uA`. T4(c) is unaffected
(`not_evaluated` / `limits_incomplete` are both still defined).

### (c) C2.4 point 2 — "0.0 for a continuous train" breaks two things the plan does not name.

The drift ceiling goes to `0.0` as `train_duration_s → inf`, which the plan intends. Two
consequences, both verified:

1. **`format_limit(0.0)` returns `'0'`, not `'0.000'`** — its own docstring promises "a
   limit of exactly 20 prints 20.00" (`format_limit(20.0) == '20.00'`, checked). So the one
   value C2.4 is designed to produce is the one value the renderer does not render to its
   stated precision. Decide in C2.4 whether a limit of zero renders as `0.000` or as a word.
2. **`test_each_check_passes_at_its_ceiling_and_fails_one_float_above` breaks on it.** Its
   guard is `if not math.isfinite(ceiling): pytest.skip(...)` — `0.0` is finite, so it
   proceeds to `replace(protocol, current_uA=0.0)` and hits
   `ValueError: current_uA must be finite and > 0, got 0.0`. The same applies to any Phase 2
   round-trip that reassesses at the reported limit. `oracles.brackets_the_ceiling` is
   already safe (it returns `False` for non-positive, by design). Extend the guard to
   `ceiling <= 0.0` **and** add a separate assertion for what a zero ceiling means, or the
   skip silently swallows C2.4's headline case.

### (d) C2.5 — a FAIL on `Validated envelope` would silently refuse the headline. **Design trap.**

`unsafe_at_any_amplitude` is *every* FAILing check outside `LIMIT_BEARING`, and there are
two such checks: `Charge balance` and `Validated envelope`. Measured over 72 configurations
(3 diameters × 3 pulse widths × 4 frequencies × 2 train durations), `Validated envelope`
returns **CAUTION 60, PASS 12, FAIL 0** — it has no FAIL state today, which is the only
reason the coupling is invisible.

C2.5 rewrites that check. If it ever returns `Status.FAIL` — "outside the fitted
conditions" is a plausible thing to want to fail — then `limiting_current_uA` becomes `None`
and every surface prints "no amplitude is safe" for a protocol whose only sin is sitting
outside McCreery's fit envelope. That is a wrong and alarming answer, and nothing in the
code or the plan currently prevents it.

C2.5 must either state that `Validated envelope` never FAILs (and pin it), or the
`unsafe_at_any_amplitude` predicate must narrow from "not limit-bearing" to an explicit
set/flag of checks whose failure genuinely means no amplitude is safe.

### (e) C2.1 — `sensitivity.analyse` now **raises** for the protocols C2.1 creates.

Since `d712995`/`15a943c`, `sensitivity.analyse` raises `sensitivity.UnsafeAtAnyAmplitude`
and `sensitivity.describe` prints a refusal whenever the protocol is unsafe at any
amplitude. C2.1 makes unbalanced *biphasic* protocols join that population. Any Phase 2
test, example or notebook that calls `sensitivity` on an unbalanced protocol must catch it;
it is not a silent empty list. Worth one line in C2.1's row.

Minor, not wrong but stale: C2.2's "*every symmetric protocol is byte-identical across this
commit*" golden baseline moved at `5381185` — the README transcript's Charge-injection and
Current-density lines. Re-baseline before asserting byte-identity.

---

## 4. Review findings not closed, excluding ledger 96

| finding | status |
|---|---|
| **F4 / M1** — `limits_incomplete` True by construction in 95.8 % of configurations, and on the worked example claims the limit may be lower because of a criterion the package says is inapplicable | **Open, withdrawn from my scope by you.** Untouched. Still gates any commit that renders the flag somewhere new. |
| **F6 / B3** — the C2.3 seed | **Partial (ledger 91).** Enforcement + documentation landed; the drift term itself is C2.3's, per §2 above. |
| **F8** — C1.7 subsumption (no defect) | **Confirmed, two caveats left open.** (i) the "every limit-bearing candidate is `inf`" escape is unguarded — `min(..., key=...)` would return the first check in emission order and print `Limiting current: inf uA (Shannon criterion)`. Unreachable today only because `_current_density_ceiling_uA` is always finite; **C2.4 opens it** if Current density ever becomes NOT_EVALUATED for monophasic the way Charge injection does. One line closes it. (ii) ties resolve to emission order — see F14. |
| **F11** — `ComplianceResult` gained three *required* fields positionally before a defaulted one; publicly exported; no §6 row | **Open.** Not touched. A direct constructor caller breaks. |
| **F12** — `Interval.describe(unit, fmt, floor=True)` silently ignores `fmt` | **Open.** I added a *new* caller of `floor=True` (`charge.py`'s published-range line, ledger 96) that passes only `unit`, so nothing depends on it yet — but the surface is now wider. |
| **F13** — the `incomplete` note is suppressed on three of four surfaces when a refusal is present | **Open, and I touched the code.** M2 changed those three conditions from `if incomplete and not refusal` to `if incomplete and limit_uA is not None` — same behaviour, now keyed on the value. The F13 concern is unchanged: after C2.4 the monophasic case is exactly where the incomplete message is the substantive one. Re-check when C2.4 lands. |
| **F14** — `limiting_mechanism` resolves ties by emission order without saying so (`DiscElectrode(150,"SS316LVM")`: Charge injection and Chronic degradation both at `17.67145867644259`) | **Open.** Deterministic, undocumented, and the reader is not told two checks bind. |

Closed for the record: F1 (89), F2 (88), F3 (90), F5/M3 (95), F7/M2 (92), F9/M4+M5 (93, 94),
F10 (in `89a54b4`), §9's unsatisfiable 67(b) row (re-assigned to C2.1 in `7ec2006`).

---

## 5. The weakest remaining part of the verdict core

**`SafetyAssessment._ceiling_interval_uA` (`neurostim/safety/assessment.py:452-467`) — a
three-way dispatch on check-name string literals whose fallback silently narrows the answer.**

```python
if check.name == "Shannon criterion":        ... published k band
if check.name == "Charge injection limit":   ... published CIC band
if check.name == "Chronic degradation":      ... published threshold band
return Interval.exact(check.ceiling_uA)      # <- everything else, and every typo
```

Three reasons this is where I would look first if I were reviewing someone else:

1. **The failure is silent and anti-conservative.** A name that stops matching falls through
   to `Interval.exact`, which reports a *point* where the literature supports a *band*.
   Demonstrated on `DiscElectrode(100,"Pt")` at 80 µA / 200 µs, with one name drifted:

   ```
   interval today      : 7.853-19.63 uA
   if the name drifted : 19.63 uA
   ```

   The interval collapses by 2.5×, the low end disappears, and nothing raises, warns or
   fails. That is precisely the "precision the literature does not supply" that C1.8 exists
   to prevent, reachable by a rename.

2. **The rename has already happened once, wholesale.** Ledger 95 records C1.6 replacing the
   entire `limiting_mechanism` vocabulary — `'Pt charge-injection limit'` →
   `'Charge injection limit'`, `'Shannon tissue-damage criterion'` → `'Shannon criterion'`.
   These three literals survived only because someone updated them by hand in the same
   commit. This is not a hypothetical class of change; it is a change this repo makes.

3. **The neighbouring dispatch on the same strings is guarded, and this one is not.**
   `Check.kind` looks up `CHECK_KINDS[self.name]` and raises a named `KeyError` — *"no kind
   declared for check …; add it to CHECK_KINDS"*. `LIMIT_BEARING` is cross-asserted against
   the oracle's independently written copy by the test suite. `_ceiling_interval_uA` has
   neither. The same information is spelled out in four places (`LIMIT_BEARING`,
   `CHECK_KINDS`, this dispatch, and each builder's `name=` argument) with one source of
   truth and three copies, and exactly one of the copies degrades quietly.

**The fix is small:** move the interval provider beside the kind in `CHECK_KINDS` (or onto
`Check` itself as a `ceiling_interval` callable set where the check is built), so a check
either declares its published band or declares that it has none, and a name that no longer
exists raises the way `Check.kind` already does. Until then, a test asserting that exactly
three limit-bearing checks return a non-exact interval, named, would at least make the
narrowing loud.

**Runner-up, for completeness:** `floor_to_pass`'s downward walk is still a pure 4-float
step count while the upward walk is now a distance. I could not construct a case that
exhausts it — 0 of 199 937 edge-clustered water-window seeds needed even one downward step,
because the seed's construction round-trips through the same capacitance and lands at or
below the boundary — so I did not add an untested exponential descent. But C2.3 pushes this
ceiling down by 130×, and the asymmetry is the kind of thing that is fine until it is not.
The `plateau` argument is already threaded; the down walk is where it would go.
