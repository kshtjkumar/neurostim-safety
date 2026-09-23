# Phase 1 review — `f068a8d..505aea6` (10 commits, C1.1–C1.11 minus C1.7)

Reviewer: code-reviewer subagent. Repo `.`.
All numbers below produced by `.venv/bin/python` at HEAD (505aea6). IN PROGRESS.

---

## F1 (BLOCKER) — `sensitivity.py` is an unrepaired render surface: it prints a bare limit for an unsafe protocol AND rounds limits up

`neurostim/sensitivity.py` is byte-untouched by Phase 1 (`git diff f068a8d..505aea6 --stat` does not
list it), yet it is a top-level public export (`neurostim/__init__.py:26,92`) that renders the
limiting current. It violates **both** C1.3 (D2: floor at every render site) and C1.5 (ledger 84:
no bare amplitude when `unsafe_at_any_amplitude`).

**(a) C1.5 violation — `neurostim/sensitivity.py:167-168` + `:95` + `:59-61`.** Verified at HEAD:

```
>>> mono = SafetyCalculator(CylindricalBandElectrode(1270.,1500.,"PtIr"),
...                         StimProtocol(3000.,90.,130.,1., waveform="monophasic"))
>>> mono.report()["limiting_current_uA"]      -> None
>>> mono.assess().describe()                  -> "Limiting current: none -- no amplitude is safe: ..."
>>> sensitivity.describe(mono)
Sensitivity of the binding current limit to each defensible choice
  baseline: 1.529e+04 uA (Shannon criterion)
  medium                      3.22x   in_vivo -> 4750 uA, saline -> 1.529e+04 uA
  Shannon k                   1.53x   1.5 -> 1.529e+04 uA, 2 -> 2.345e+04 uA
  ...
```

Nine bare amplitudes, plus the mechanism string `(Shannon criterion)`, for the exact protocol
C1.5 exists to refuse. `_limit()` at `:95` returns the raw attribute and `Sensitivity.describe()`
at `:59-61` renders it with no access to the assessment, so the flag cannot be consulted at the
point of rendering — the refusal has to be hoisted into `analyse()`/`describe()`.

**(b) C1.3 violation — `:159-161` and `:167` use `:.4g`.** Ledger 49 is "`:.4g` prints
141.37166941154072 as 141.4, and 141.4 µA FAILs the check whose maximum it claims to be".
Swept 9 diameters × 9 materials × 3 pulse widths (243 configurations): **100 print a limit strictly
larger than the limit**. Concrete: `DiscElectrode(60,"Pt")` at 100 µs, limit
`14.137166941154069` → sensitivity prints `14.14`; `format_limit` gives `14.13`.
`examples/worked_example.py:57` (`:.4g`) and `:89` (`:8.1f`) are the same defect on the same
values — `:8.1f` is worse, it can overstate in the third significant digit.

This is the same shape as the known `viz` annotation, but it is **not** the same defect and is
**not** assigned to C5.1: §6's C1.3 rows book `gui/app.py:332`, `viz/plots.py:211` and
`Interval.describe` and stop there. `sensitivity.py` and `examples/worked_example.py` are not in
§6 at all.

---

## F2 (BLOCKER) — the `LimitDidNotSettle` regression is **moved, not fixed**: `assess()` still raises on validly-constructed inputs

The lead verified "0 of 108 valid configurations raise". I swept wider. Two sweeps:

* deterministic, 316 800 configurations (9 materials × 11 diameters × 8 pulse widths × 5 currents
  × 8 resting potentials × 5 capacitances × 2 polarities): **0 raises**. Matches the builder's claim.
* randomised, 120 000 draws clustered against the *window edges* (the region `_climb_to_boundary`
  exists for), 70 831 constructed: **4 487 raise `LimitDidNotSettle` (6.3 %)**. Every one is
  `Water window`.

**Minimal reproduction** (`neurostim/safety/assessment.py:570-604` → `_limits.py:_climb_to_boundary:173`):

```python
SafetyCalculator(DiscElectrode(100., "Pt"),
                 StimProtocol(80., 200., 130., 1., anodic_first=False),
                 resting_potential_V=-0.59999999,   # inside Pt's [-0.6, +0.8]: C1.2 ACCEPTS it
                 capacitance_uF_cm2=103.0).assess()
# LimitDidNotSettle: Water window: the back-solved limit 4.044800516914701e-07 still passes
# its own check more than 1e-09 of its own size above it ...
```

At `f068a8d` the same call returns `limiting_current_uA = 39.26990816987242`. **Phase 1 turned a
number into a crash on an input the package itself declares valid.** Threshold measured by
walking the resting potential in: raises from `-0.59999999` inward (~1e-8 V of headroom);
`-0.5999999` still returns `4.0448e-06`; exactly `-0.6` returns `0.0`.

**Why `CLIMB_TOLERANCE` cannot work as specified.** The plateau's width in *current* is set by
one ulp of the sum `resting_potential_V + excursion` — an absolute quantity ≈ `ulp(0.6 V)`
converted back through `C·A/PW`. It does not scale with the seed. So its width *relative to the
seed* goes as 1/seed, and a relative bound is guaranteed to fail once the seed is small enough.
Measured on the case above:

```
seed                 4.044800516914701e-07
true boundary        4.0448005393678537e-07
relative gap         5.551e-09          (budget: CLIMB_TOLERANCE = 1e-9)
plateau width        42 412 806 ulps
```

`_limits.py:173-181` asserts "A plateau in the check's own arithmetic is a few floats wide;
this is a back-solve that does not invert its forward comparison". That is false here on both
counts: it is 4.2e7 floats wide and the back-solve is correct. **The error message misdiagnoses
its own cause**, which is how the next person loses a day.

**Does the split budget silently return an unsettled limit?** No — I could not break that half.
`floor_to_pass` returns only after `passes(settled)` and `not passes(nextafter(settled, +inf))`
on every path (`_limits.py:120-124`, and `_climb_to_boundary`'s bisection terminates only when
`high == nextafter(low)` with `passes(low)` and `not passes(high)` both established). The
failure mode is loud, not silent. That is the one good thing here.

**D2 is no longer accurately described.** §2 D2 point 2 says "Exhausting the **4-step budget**
raises a named error carrying the check, the value and **the step count**." The code now has two
budgets with different units, and the upward error carries no step count. `docs/audit/FIX_PLAN_v2.md`
was not touched by this phase, so the settled convention and the code disagree — against the
stated "no doc drift" mandate.

**Fix direction.** The bound must come from the predicate's own arithmetic, not from the seed.
The climb is crossing a plateau whose width is `ulp(resting + excursion)` in *potential*; convert
that to current (`× capacitance_uF_cm2 × area_cm2 / pulse_width_s`) and bound the climb by a small
multiple of it, or give `floor_to_pass` an explicit `absolute_plateau_uA` supplied by the caller
that knows the units. A blanket loosening of `CLIMB_TOLERANCE` is not equivalent: it would have
to be ~1e-3 to cover a 1e-8 V headroom and would then stop catching a genuinely wrong back-solve.

---

## F3 (MINOR) — the C1.9 oracle guard is one-sided; a *lower* amplitude bound crashes the bisection

`tests/oracles/fail_ceiling.py:227-232` returns `UNCONSTRUCTIBLE` for a refused amplitude, and
`tests/test_verdict_core.py:1616` pins it — but only through `rejects_above_uA`
(`tests/test_oracles.py:133`). `UNCONSTRUCTIBLE` enters the per-check suffix invariant as if it
were a check name, so a rejection at the *bottom* of the ladder is a prefix, not a suffix, and
`_assert_each_check_fails_upwards` raises. Demonstrated with a scripted calculator that refuses
`current_uA < 1.0`:

```
NonMonotonePredicate: <amplitude refused at construction> FAILs at 1e-12 uA and does not
FAIL at 1.77828 uA ...
```

which is exactly the crashed bisection the guard was scheduled to prevent. Latent today
(nothing validates `current_uA`), and the *likelier* future validation is a floor, not a ceiling —
the bracket already starts at `1e-12` µA specifically to dodge `StimProtocol`'s zero rejection.
Fix: treat `UNCONSTRUCTIBLE` as bracket-narrowing rather than as a failing check, or exempt it
from the suffix invariant and raise the lower bracket to the smallest constructible amplitude.

---

## F4 (MAJOR) — `limits_incomplete` is True by construction for 95.8 % of configurations, and on the flagship example it makes a claim the package elsewhere refutes

`neurostim/safety/assessment.py:333-362`. Swept 9 materials × 8 diameters × 3 pulse widths
(216 configurations): **207 True, 9 False (95.8 % True)**.

The reason is structural, not incidental. `Shannon criterion` and `Microelectrode charge/phase`
**partition** the size axis (`cogan2016.is_microelectrode` is `area < 3e-4`;
`in_regime_transition` is `3e-4 <= area <= 7e-4`):

| area | Shannon | Microelectrode | `limits_incomplete` |
|---|---|---|---|
| `< 3e-4 cm²` | NOT_EVALUATED | evaluated | **True, always** |
| `3e-4 … 7e-4` | evaluated | CAUTION | can be False |
| `> 7e-4 cm²` | evaluated | NOT_EVALUATED | **True, always** |

So the flag — and the `INCOMPLETE: ... so the true limit may be lower` banner it drives in
`describe()`, `report_to_json`, the PDF and the GUI — is on for every electrode outside a narrow
transition band, whatever the protocol. The suite's own evidence: the only way
`test_limits_incomplete_is_clear_when_every_limit_bearing_check_ran`
(`tests/test_verdict_core.py:1326-1342`) can get a `False` is to reach for
`DiscElectrode(250.0, "Pt")` — area 4.909e-4 cm², inside the band.

Worse than dilution, it is **wrong on the worked example**. `describe()` at HEAD prints:

```
Limiting current: 20.00 uA (Microelectrode charge/phase)
  INCOMPLETE: 1 limit-bearing check did not run (Shannon criterion), so the true limit may be lower
```

Shannon is NOT_EVALUATED here *because Cogan 2016 says it does not apply to a microelectrode* —
`_shannon_check` (`assessment.py:703-706`) says in its own comment that "reporting Shannon
headroom here would contradict the microelectrode check and give false reassurance". The banner
then tells the reader the true limit may be lower **because of that same criterion**. That is an
unsourced claim printed on the headline of the package's flagship example, which is the class of
defect this repair exists to remove.

D3's intent is the opposite: "a limit over a **knowingly-incomplete** candidate set". A check
that correctly does not apply is not a missing candidate. The distinction the code needs is
*did not run because inapplicable* vs *did not run because no source covers this protocol*
(C2.4's monophasic charge injection is the second kind, and is the case the flag was designed
for). Concretely: exclude the Shannon/Microelectrode regime pair — exactly one of them abstains
by construction — or give `Check` a reason for NOT_EVALUATED and count only the evidential one.

Not in §6 either: §6's C1.6 row books `limits_incomplete` as a "new field" with no note that it
fires on essentially every assessment.

---

## F5 (MAJOR) — numbers that moved and are not in §6

Diffed `report()`, `report_to_json()` and `describe()` across ten configurations between
`f068a8d` and `505aea6` (`scratchpad/cmp.py`). Beyond the rows §6 already books:

**(a) `limiting_mechanism` changed vocabulary on *every* row, including rows where no number
moved.** §6 books only C1.6's `Pt charge-injection limit → Microelectrode charge/phase` and
C1.7's value change "where the named check did not run". But the strings themselves were replaced
wholesale (`assessment.py:434-446` now returns a `Check.name`):

| configuration | limit | mechanism |
|---|---|---|
| `DiscElectrode(150,"SS316LVM")` 80 µA/200 µs | 17.671… → **unchanged** | `'SS316LVM charge-injection limit'` → `'Charge injection limit'` |
| `CylindricalBand(1270,1500,"PtIr")` biphasic | 15285.5 → 15285.5 (1 ulp) | `'Shannon tissue-damage criterion'` → `'Shannon criterion'` |

The material name is gone from the charge-injection string. `current_sweep.csv`'s
`limiting_mechanism` column and every batch CSV are now a different vocabulary in every row;
a downstream filter on `"charge-injection"` silently matches nothing, with no number to notice.
This is a breaking change to a documented column and it is unbooked.

**(b) `report()["limiting_mechanism"]` now holds a sentence, not a check name**, for unsafe
protocols: `'no amplitude is safe: Charge balance FAILs at every amplitude'`
(`assessment.py:1428`). The builder booked the `limiting_current_uA → None` half; the companion
column turning into prose in the same CSV is the other half and is not booked.

**(c) `checks[].ceiling_uA` is a new JSON field** (`io/tabular.py:225`). §6's C1.4 row books the
`Check` schema as gaining "`kind`, `provisional`" and stops there.

**(d) `report()["status"]` moves `'NOT_EVALUATED' → 'PASS'`** for every macroelectrode
(verified `DiscElectrode(2000,"SIROF")`). §6's C1.1 row books "overall status of every
macroelectrode" against `Status.rank` docstring / README table / JSON-PDF-GUI headline — not
against `report()["status"]`, which is the `status` column of `current_sweep.csv` and of every
batch CSV, and is also the column `assess_batch` writes `"ERROR"` into after C1.9.

**(e) `limiting_current_uA` moves far beyond the worked example**, and §6's C1.6 row names only
the worked example while §6's preamble promises "every number that moves". Verified:
`DiscElectrode(60,"TiN")` 282.74 → **40.0** (7.07×); `DiscElectrode(40,"PEDOT")` 99.67 → **20.0**;
`DiscElectrode(800,"Ta2O5")` 1993.45 → **1382.85** with the mechanism moving
Shannon → Current density; `DiscElectrode(100,"Pt")` 39.27 → **19.63**.

Not a finding, for the record: `example_output/` is deliberately untracked (`.gitignore:29-34`)
and the tracked surface is the README transcript, which is current —
`scripts/regenerate_example_output.py --check` exits 0 at HEAD.

---

## F6 (BLOCKER for Phase 2, confirmed) — C2.3 will make `_water_window_ceiling_uA`'s seed wrong by a factor of `f·T`, and `floor_to_pass` will raise on every monophasic protocol

The builder's warning is correct and I can put a number on it.
`assessment.py:570-604` seeds `floor_to_pass` by inverting the **pulse-peak** window expression
only: `seed_density × area / pulse_width_s`. C2.3 adds a DC-drift clause to the same check
(FAIL when `t_exit < train_duration_s`), so the predicate gains a second, much tighter branch
the seed knows nothing about. On the plan's own C2.3 case
(`CylindricalBandElectrode(1270,1500,"PtIr")`, `StimProtocol(3000, 90, 130, 1, monophasic)`,
`capacitance_uF_cm2=250`, area 0.05984734 cm²):

```
pulse-peak seed (today's)                99745.56675147594 uA
drift ceiling  Q_window / (PW·f·T)         767.2735903959685 uA
ratio                                      130.0   ( = f × T )
gap in ulps                                8.7e17          (floor_to_pass budget: 4)
```

`floor_to_pass` walks down 4 floats, `passes` is still False, and it raises `LimitDidNotSettle`
— for every monophasic protocol, i.e. exactly the population C2.4 is about. And the message it
raises ("the two are not inverses of each other") will be true but misdiagnosed, as in F2.

**What the seed must become.** The minimum of the two closed forms, because the predicate becomes
their conjunction:

```
seed = min(
    seed_density * area_cm2 / pulse_width_s,                                  # peak excursion
    (window_headroom_V * capacitance_uF_cm2 * area_cm2)                       # DC drift
        / (net_charge_fraction * pulse_width_s * frequency_hz * train_duration_s),
)
```

with `window_headroom_V` the distance from `resting_potential_V` to the window edge in the drift
direction (0.6 V in the plan's case) and `net_charge_fraction` the per-pulse unrecovered fraction
(1.0 monophasic; `1 - charge_recovery_ratio` after C2.1). Verified against the plan's own
constants: `0.6 × 250e-6 × 0.05984734 × 1e6 = 8.9771 µC`, `/35.1 µA = 0.25576 s` (plan: 0.2558 s),
and the ceiling `8.9771 / (90e-6 × 130 × 1) = 767.27 µA`.

The monotonicity precondition survives: both branches are individually monotone-decreasing in
current, so their conjunction is too. Three consequences to carry into C2.3:

1. **`train_duration_s → inf` (continuous train) drives the seed to 0.0.** `floor_to_pass`
   returns non-positive values unchanged (`_limits.py:103-104`), so the ceiling is `0.0` — the
   plan's intended answer. But `StimProtocol` rejects `current_uA = 0.0`
   (`ValueError: current_uA must be finite and > 0`), so **every round-trip that reassesses at the
   reported limit becomes unconstructible**: T2b's shape
   (`tests/test_verdict_core.py:1215`, guarded today by `assert limit > 0`),
   `oracles.brackets_the_ceiling`, and C2.4's own assertions. Decide now what "reassess at 0.0"
   means before writing those tests.
2. **`format_limit(0.0)` returns `'0'`**, not `'0.000'` — the sig-digit promise in its own
   docstring ("a limit of exactly 20 prints 20.00") does not hold at the one value C2.4 is
   designed to produce.
3. **F2 must be fixed first.** C2.3 pushes the water-window ceiling *down*, and F2 shows
   `_climb_to_boundary` blows up precisely when that ceiling is small. Landing C2.3 on top of F2
   compounds two raises in the same function.

---

## F7 (MAJOR) — attack area 1: the `limiting_current_uA` split. Judgement and recommendation

### Every consumer of `assess().limiting_current_uA` in the package, at `36d3d6b`

| # | site | consults `unsafe_at_any_amplitude`? |
|---|---|---|
| 1 | `neurostim/safety/assessment.py:501` (`describe()`) | **yes** — `:496` branches on `unsafe_at_any_amplitude_note()` |
| 2 | `neurostim/safety/assessment.py:1425-1427` (`report()`) | **yes** — returns `None` |
| 3 | `neurostim/io/report.py:238` (PDF headline) | **yes** — `:232` |
| 4 | `neurostim/gui/app.py:137` (`headline_text`) | **yes** — `:131` |
| 5 | `neurostim/viz/plots.py:269,276` (figure annotation) | **yes**, since `fa01e26` — `:252` |
| 6 | `neurostim/io/tabular.py` (`report_to_json`, `assess_batch`, `current_sweep`) | **yes, transitively** — all go through `calc.report()` |
| 7 | **`neurostim/sensitivity.py:95`** (`_limit`) | **NO** |
| 8 | **`neurostim/sensitivity.py:167-168`** (`describe`) | **NO** |
| 9 | **`examples/worked_example.py:57,89`** | **NO** |

Internal consumers inside `SafetyAssessment` — `limiting_current_by_kind`, `limiting_current_interval_uA`,
`limiting_mechanism`, `_by_kind_line` — do not consult it and **should not**: they are the
decomposition and the uncertainty band *of* the raw quantity, and `describe()` already suppresses
all three together in the refusal branch.

So six of nine consult; the three that do not are F1. With the viz fix landed, `sensitivity.py`
is now the **only package module** that prints a bare amplitude for a protocol every other surface
refuses — which makes it more exposed, not less: a reader who sees the PDF refuse and the
sensitivity report print `1.529e+04 uA` will trust the number, because it came with a mechanism
name and a ranked table.

### Is the attribute's value defensible?

**As a quantity, yes. Under that name, no.** 15285.50941588086 is exactly the minimum over
`LIMIT_BEARING`, which is what amended D3 defines; it is what `limiting_current_by_kind`
decomposes, what C1.8's interval must contain, and what C1.6's round-trip pins. Deleting it would
break three things that are correct. But "limiting current" in a safety package is read as *the
highest amplitude you may use*, and for this protocol there is no such amplitude. The name asserts
something the value does not support, and the only thing standing between a consumer and that
misreading is remembering to check a second attribute — which three of nine consumers did not.

That is precisely the ledger 19/59/60 shape: the qualifying information exists, one row away from
where it is needed, and nothing structural carries it across. Phase 1 fixed the *rendering* sites
one at a time by hand; each new consumer restarts the same race. Phase 2's C2.1 widens the refusal
to unbalanced **biphasic** protocols (§6's own C2.1 [84] row), which multiplies the number of rows
where the two answers disagree — so the population of "consumers who must remember" grows before
anyone re-audits them.

### Recommendation: **rename the raw quantity and make `limiting_current_uA` refuse**

Not "keep as-is", and not "raise".

```python
@property
def limit_bearing_ceiling_uA(self) -> float:      # today's limiting_current_uA, verbatim
    return min(c.ceiling_uA for c in self._limit_bearing)

@property
def limiting_current_uA(self) -> float | None:    # None when unsafe_at_any_amplitude
    return None if self.unsafe_at_any_amplitude else self.limit_bearing_ceiling_uA
```

Three reasons this and not the alternatives:

1. **It is enforced rather than remembered.** `float` → `float | None` is a type change, and mypy
   is already clean and CI-gated (§10). `sensitivity.py:95` and `:167` and
   `examples/worked_example.py:57` **cannot typecheck** without handling the `None`. That is the
   mechanism that makes "one row short" structurally impossible, which a convention cannot be.
2. **Raising is worse.** It would take `limiting_current_by_kind`, `limiting_current_interval_uA`
   and `limiting_mechanism` with it, and those are exactly what a user needs to *diagnose* a
   protocol that is unsafe as a waveform. `None` refuses the headline while leaving the
   decomposition reachable.
3. **`report()` collapses to one line** (`assessment.limiting_current_uA`, no conditional), and
   the four render surfaces stop each carrying their own copy of the branch. One rule, one place.

Keep `limit_bearing_ceiling_uA` public and documented — it is a real quantity with a real
definition, and the interval/by-kind/round-trip tests should pin *it*, not the refusing form.

**Do it now, in Phase 1's tail, not after Phase 2.** Two call sites and one test rename today;
after C2.1 the disagreeing population is every unbalanced protocol, and the audit is larger.

---

## F8 (no defect) — attack area 3: C1.7 is genuinely subsumed, and I can say why by construction

The builder's argument holds, and I could not break it. Searched 4 680 configurations
(9 materials × 13 diameters spanning both sides of both regime boundaries × 5 pulse widths
× 4 amplitudes from 1 nA to 10 mA × biphasic/monophasic) for four distinct failure shapes:

```
mechanism names a NOT_EVALUATED check : 0
limiting_current_uA is inf            : 0
any nan ceiling                       : 0
mechanism's ceiling != limiting_current_uA : 0
```

The structural reason is at `assessment.py:1365-1376`, not in `limiting_mechanism` itself. The
ceiling is attached centrally, after every builder has returned, by a single expression that reads
`math.inf if check.status is Status.NOT_EVALUATED else ceilings.get(...)`. So "NOT_EVALUATED ⇒
`inf`" is a property of one line, and `limiting_mechanism`'s
`min(self._limit_bearing, key=lambda c: c.ceiling_uA)` cannot select it unless *every* candidate is
`inf`. That is C1.7 discharged by construction, and the T3 red-at-`e704d8a`/green-at-`2d63aa2`
evidence is consistent with it. **No commit for C1.7 was the right call.**

Two caveats to carry, neither a defect today:

* **The "every candidate is `inf`" escape is unguarded.** If it ever happened,
  `min(..., key=...)` silently returns the *first* limit-bearing check in emission order —
  `Shannon criterion` — and `describe()` would print `Limiting current: inf uA (Shannon criterion)`
  for a check that did not run. It is unreachable today only because `_current_density_ceiling_uA`
  is finite whenever `jd_mod.evaluate` supplies a threshold, which it always does
  (`assessment.py:891` is marked `pragma: no cover`). Phase 2 touches this: if C2.4 ever makes
  Current density NOT_EVALUATED for monophasic the way it does Charge injection, the escape opens.
  One line (`if math.isinf(...): return "no limit-bearing check imposes a ceiling"`) closes it.
* **Ties resolve to emission order.** `DiscElectrode(150,"SS316LVM")` has Charge injection and
  Chronic degradation at exactly 17.67145867644259; the mechanism reported is whichever the
  builder emits first. Deterministic, but arbitrary, and the reader is not told two checks bind.

---

## F9 — attack area 4: test quality across the ~120 new tests

Method: read every new test class; then a mutation battery (7 mutants, each a fresh
`git archive 505aea6` tree in the scratchpad, run against
`tests/test_verdict_core.py tests/test_oracles.py tests/test_core.py`, 284 tests).

### FAIL-side coverage — genuinely delivered

| | `f068a8d` | `505aea6` |
|---|---|---|
| `Status.FAIL` assertions across `tests/` | **3** (test_core 2, test_literature 1) | **18** (test_verdict_core **15**, test_core 2, test_literature 1) |
| checks with a pinned FAIL | 3 of 9 | **8 of 9** |

Pinned FAILs: Shannon `:1698`, Charge injection `:1713`, Water window `:1736`, Compliance
`:1747`, Chronic degradation `:1765`, Microelectrode charge/phase `:1780`, Charge balance `:1796`,
Current density `:1814`. Only `Validated envelope` has none, and it has no FAIL state.
Each pins the published constant and the applied quantity against it *before* asserting the
status, so the fixture cannot drift off the far side of the number it is meant to cross. This is
the real thing.

**Both sides of each boundary: yes, for all seven limit-bearing checks.**
`test_each_check_passes_at_its_ceiling_and_fails_one_float_above` `:1845` is parametrised over the
seven and asserts `not FAIL` at the ceiling and `FAIL` at `math.nextafter(ceiling, +inf)`. It
carries a `pytest.skip` for a non-finite ceiling — I checked, **nothing skips**
(`160 passed`, 0 skipped on `test_verdict_core.py + test_oracles.py`). Plus
`test_the_shannon_line_is_inclusive` `:1817` and the water-window plateau case `:1886`.

One gap, and it is the plan's fault not the builder's: §9 assigns ledger **67(b)** (the
unbalanced-biphasic FAIL branch) to **C1.10 alone**. That branch cannot be reached until imbalance
is expressible at **C2.1**, and the test says so in its own docstring (`:1786-1788`). C1.10 could
not close 67(b) and did not; 67 is correctly left `pending`. **§9's row is unsatisfiable as
written and should be re-assigned to C2.1** before it is used as a Phase-2 exit criterion.

### Tests that can pass for the wrong reason — three, one of them demonstrated

**(a) `test_exhausting_the_step_budget_raises_and_names_the_check`
(`tests/test_verdict_core.py:390-405`) — DEMONSTRATED SURVIVOR.**

```python
assert "4" in message   # the step budget
```

A substring test on a number. Mutant `STEP_BUDGET = 4 → 40`: **284 passed, mutant survived** —
"40 steps" contains "4". It cannot distinguish 4 from 40, 14, 42 or 400. Fix:
`assert f"after {_limits.STEP_BUDGET} steps" in message` *and* a second case proving the budget
binds (a predicate that passes at exactly `STEP_BUDGET` floats down and fails at `STEP_BUDGET+1`).

**(b) `test_the_headline_is_the_minimum_of_the_per_kind_limits`
(`tests/test_verdict_core.py:1335-1350`) — tautological, and labelled otherwise.**
It builds `expected` by looping over `check.ceiling_uA` — the same values
`limiting_current_by_kind` and `limiting_current_uA` are computed from — then asserts equality.
If every ceiling were wrong by 2× it still passes. This is v1's `min(c.margin * I ...)` form,
which the plan's C1.6 row explicitly **dropped** as "the implementation restated", reappearing in
the by-kind commit. It is not worthless (it killed the `min → max` mutant), but its docstring's
"recomputed here from the checks' own ceilings" is the claim, not the refutation. Give it one
hand-written expected value — `test_the_per_kind_limits_disagree_where_it_matters` `:1352`
already has the four constants; assert against those instead.

**(c) `test_the_interval_contains_the_point_estimate` (`tests/test_verdict_core.py:1441-1457`) —
structurally guaranteed, not measured.** `most_restrictive` is `(min lows, min highs)`
(`neurostim/uncertainty.py:206-217`), and `_ceiling_interval_uA` returns an interval bracketing
each check's own ceiling. Then for `j = argmin(highs)`: `min(highs) = high_j ≥ low_j ≥ min(lows)`,
and `point = min(ceilings) ≤ min(highs)` since `ceiling_i ≤ high_i`. So containment is a theorem
about the two constructions, not a relation between two independent computations. It is still a
valid regression guard for the *old* defect (different candidate sets), so keep it — but the
docstring's "computed by different code from different inputs" overstates what it can catch.

### Constants that no test pins — mutation results

| mutant | outcome |
|---|---|
| `CLIMB_TOLERANCE` 1e-9 → 1e-3 | **SURVIVED** (284 passed) |
| `STEP_BUDGET` 4 → 40 | **SURVIVED** (284 passed) |
| `limiting_current_by_kind` `min` → `max` | killed, 4 tests |
| `limits_incomplete` → always `False` | killed, 2 tests |
| NOT_EVALUATED contributes its own ceiling | killed, 2 tests (incl. the per-check oracle) |
| chronic ceiling reads the band's low end | killed, 5 tests |
| `format_limit` `ROUND_FLOOR` → `ROUND_HALF_EVEN` | survived, but **equivalent mutant** — see below |

`CLIMB_TOLERANCE` is the more serious of the two survivors: it is the constant F2 shows is wrong,
and loosening it 10⁶× is **not behaviour-neutral** — the F2 case goes from
`LimitDidNotSettle` to returning `4.0448005393678537e-07`, and nothing in 770 tests notices.
Whichever way F2 is fixed, the fix needs a test that fails if the bound moves.

`STEP_BUDGET` is survivor (a) above.

**`format_limit`'s rounding mode is an equivalent mutant, and the reason is a dead branch.**
Over 400 000 random values `ROUND_FLOOR` and `ROUND_HALF_EVEN` produce **byte-identical output**
and neither ever overstates, because `_limits.py:210-214` corrects any round-up afterwards. And
under the shipped `ROUND_FLOOR` that correction is **provably unreachable**: `Decimal(value)` is
exact, `quantize(ROUND_FLOOR)` gives a decimal `D ≤ value`, and the nearest float to `D` cannot
exceed `value` because `value` is itself a representable float `≥ D`. Measured: **0 firings in
303 904 values.** So `format_limit` ships a dead branch whose docstring describes a case that
cannot arise, blessed by a passing suite — ledger 67's own shape ("a passing test that blesses
dead code is worse than no test"), reintroduced at C1.3. Delete the branch, or keep it and say in
one line that it is unreachable under `ROUND_FLOOR` and exists to make the rounding mode
non-load-bearing.

### Fixture rule — clean

I checked every new fixture against `SafetyCalculator.__init__`'s defaults
(`assessment.py:1153-1168`: `k=1.5`, `policy="conservative"`, `medium="saline"`,
`tissue_conductivity_S_per_m=0.35`, `lead_resistance_ohm=0.0`, `compliance_V=None`,
`resting_potential_V=0.0`, `capacitance_uF_cm2=None`). No new test rests on a value the code
could fall back to: `compliance_V=10.0`/`20.0`/`5.0`/`1.0` against a `None` default;
`resting_potential_V=-0.55`/`-0.5`/`0.9` against `0.0`; `k` and `policy` are each swept across
three values including but not only the default. `tests/test_oracles.py:123-128` goes further —
`ScriptedCalculator` asserts every carried setting on arrival against `SCRIPTED_SETTINGS`, so a
silently-dropped forward fails instead of scripting the same answer anyway. That is the right
pattern and it should be the model for the rest of the suite.

### Construction-time validation (C1.9) — thorough

Probed every settable field for `nan`/`inf`/zero/negative: `current_uA`, `pulse_width_us`,
`frequency_hz`, `train_duration_s`, `k`, `resting_potential_V`, `tissue_conductivity_S_per_m`,
`lead_resistance_ohm`, `compliance_V`, `measured_impedance_ohm`, `capacitance_uF_cm2`, `medium`,
`policy`, `diameter_um`. **All rejected with a named message**; `train_duration_s = inf` is
accepted, correctly (continuous train). `validate_resting_potential_V` checks finiteness *before*
the `window is None` early return, so `nan` is rejected on Ta2O5 too. Ledger 13 and 52 are
genuinely closed.

---

## F4 addendum — direct answer on rendering `limits_incomplete` on the figure

**Do not render `limits_incomplete` on the figure as it is currently defined. Redefine it first —
it is a ~10-line change and it belongs *before* the figure commit, not after.**

The decision to put the disclosure on the figure is right. The flag you would be rendering is not.
Two separate things are tangled in it:

* **the fact** — "Shannon criterion did not run" — true, useful, and already rendered everywhere by
  `not_evaluated_note()` (`Overall: FAIL (1 check not evaluated: Shannon criterion)`);
* **the inference** — `limits_incomplete_note()`'s "**so the true limit may be lower**" — which is
  false for the inapplicability cases, i.e. 95.8 % of them, and on the worked example contradicts
  `_shannon_check`'s own reasoning three lines away in the same module.

Rendering the current flag on `viz/plots.py` copies the false inference to a **fifth** surface, on
a figure that goes in the paper, for essentially every configuration. That is worse than not
disclosing at all, because a caveat that is always on is a caveat nobody reads — and this one is
also wrong.

Two ways to proceed; either is fine, the first is better:

1. **Split the flag, then render (recommended).** `limits_incomplete` counts only limit-bearing
   checks that abstained *for want of evidence*. The Shannon/Microelectrode pair partitions the
   size axis — exactly one of them abstains for every electrode outside `3e-4…7e-4 cm²`, by
   construction — so an abstention from that pair is never a missing candidate. The cleanest form
   is a reason on the check (`NOT_EVALUATED because inapplicable` vs `because unsourced`), which
   C2.4 needs anyway: its monophasic Charge-injection abstention is the *evidential* kind and is
   the case the flag was designed for. After the split, `limits_incomplete` is False on the worked
   example and True where it means something, and rendering it on the figure is straightforwardly
   right.
2. **If you want the figure commit to land now**, render `assessment.not_evaluated_note()` in terse
   form — the fact, not the inference — and leave `limits_incomplete` off the figure until it is
   split. This is strictly safe; the cost is that the figure and the PDF then disclose the same
   situation in two different vocabularies until the split lands.

What you must not do is render `limits_incomplete_note()` verbatim. F4's finding is not "the flag
is noisy"; it is "the sentence it renders makes a claim about the limit that the package's own
sourcing refutes", and that is a submission-blocking sentence to put on a figure.

---

## Remaining findings (MINOR)

**F10.** `docs/audit/FIX_PLAN_v2.md` §2 D2 is now stale. It states one "**4-step budget**" whose
exhaustion "raises a named error carrying the check, the value and **the step count**". The code
has two budgets in two units (`STEP_BUDGET` floats down, `CLIMB_TOLERANCE` relative up) and the
upward error carries no step count. The plan was not touched by this phase. Against a stated
"no doc drift" mandate, the settled convention and the code must not disagree — and D2 is
load-bearing for Phase 2's review.

**F11.** `ComplianceResult` (`neurostim/safety/compliance.py:70-83`) gained three **required**
fields — `pulse_width_us`, `area_cm2`, `capacitance_uF_cm2` — positionally before the defaulted
`conductivity_note`. It is publicly exported (`neurostim/safety/__init__.py:28,58`), so any
caller constructing one directly breaks. No §6 row.

**F12.** `Interval.describe(unit, fmt, floor=True)` silently ignores `fmt`
(`neurostim/uncertainty.py:164-172` → `format_limit(value)` always at 4 significant digits). No
caller passes both today; it will bite the first one that does.

**F13.** The `incomplete` note is suppressed on three of four surfaces when a refusal is present
(`assessment.py:508` else-branch, `io/report.py:246`, `gui/app.py:146` — all `if incomplete and
not refusal`), while `report_to_json` keeps the raw boolean. Correct today. After C2.4 the
monophasic case is exactly where the incomplete message is the *substantive* one (Charge injection
abstains for want of a monophasic CIC), so re-check this suppression when C2.4 lands.

**F14.** `limiting_mechanism` resolves ties by emission order without saying so —
`DiscElectrode(150,"SS316LVM")` has Charge injection and Chronic degradation both at exactly
`17.67145867644259` and only the first is named. Deterministic; a reader changing the named
mechanism would find the limit unmoved.

---

# Verdict

Re-confirmed at the **current** repo HEAD `36d3d6b` (after the viz fix), not only at `505aea6`:
F2's minimal reproduction still raises `LimitDidNotSettle`; `sensitivity.describe()` still prints
`baseline: 1.529e+04 uA (Shannon criterion)` where `report()` returns `None`.

**Effect of the viz fix (`fa01e26`, `36d3d6b`) on my findings:** it closes the figure hole and
makes F1 *narrower and sharper* — `neurostim/sensitivity.py` is now the only package module that
prints a bare amplitude for a protocol every other surface refuses. Nothing else changes. No
finding below is about viz.

## Ranked

**BLOCKER — Phase 2 must not proceed until these are closed**

| | finding | where | one-line failure case |
|---|---|---|---|
| **B1** | `LimitDidNotSettle` regression **moved, not fixed** — `assess()` raises on 6.3 % of edge-clustered valid constructions; baseline returned a number | `_limits.py:173-181` via `assessment.py:570-604` | `DiscElectrode(100,"Pt")`, cathodic-first, `resting_potential_V=-0.59999999` → raise; at `f068a8d` → `39.26990816987242` |
| **B2** | `sensitivity.py` is an unrepaired render surface: bare limit for an unsafe protocol, and `:.4g` rounds 100 of 243 limits **up** | `sensitivity.py:95,159-161,167-168`; `examples/worked_example.py:57,89` | `sensitivity.describe(monophasic_band)` prints nine amplitudes; `DiscElectrode(60,"Pt")` 100 µs prints `14.14` for a limit of `14.137166941154069` |
| **B3** | C2.3 will break `_water_window_ceiling_uA`'s seed by a factor `f·T`, raising on every monophasic protocol — **fix the seed in the same commit** | `assessment.py:570-604` | plan's own case: seed 99745.57 µA vs drift ceiling 767.27 µA, 8.7e17 ulps, budget 4 |

B1 and B3 are the same function and the same helper. They should be fixed together, and B1 first —
C2.3 pushes the water-window ceiling down into exactly the range where B1 bites.

**MAJOR**

| | finding | where |
|---|---|---|
| M1 | `limits_incomplete` True by construction in 95.8 % of configurations, and on the worked example asserts the limit may be lower because of a criterion the package says is inapplicable. **Do not render it on the figure until it is split.** | `assessment.py:333-362`, `:349-362` |
| M2 | `limiting_current_uA` means two things under one name; 3 of 9 consumers do not consult the flag. Rename the raw quantity to `limit_bearing_ceiling_uA` and make the attribute return `float \| None` so mypy enforces it. Do it before C2.1 widens the disagreeing population. | `assessment.py:306-331` |
| M3 | Unbooked movers: `limiting_mechanism`'s whole vocabulary (breaking, on rows where no number moved), the same key turning into prose, `checks[].ceiling_uA` as a new JSON field, `report()["status"]`, and `limiting_current_uA` on far more than the worked example | §6 |
| M4 | `CLIMB_TOLERANCE` and `STEP_BUDGET` are unpinned — both mutants survived 284 tests, and loosening `CLIMB_TOLERANCE` is **not** behaviour-neutral | `_limits.py:57,74`; `test_verdict_core.py:390` |
| M5 | Three tests pass for the wrong reason, one demonstrated (`assert "4" in message` survives `STEP_BUDGET = 40`) | `test_verdict_core.py:390,1335,1441` |

**MINOR** — F3 (one-sided oracle guard), F10 (D2 stale in the plan), F11 (`ComplianceResult`
constructor break), F12 (`Interval.describe` ignores `fmt` under `floor`), F13 (incomplete note
suppressed where C2.4 will need it), F14 (tie-breaking unstated), plus §9's unsatisfiable
assignment of ledger 67(b) to C1.10.

## What Phase 1 got right, and it is most of it

The headline is genuinely fixed and genuinely verified: 141.37 → 20.00 µA against an independently
written binary search that never reads a margin, a maximum or a limiting current. The oracle's
`LIMIT_BEARING` is written out rather than imported, and the two sets are cross-asserted — that is
the structural answer to "tests that pass for the wrong reason" and it works. FAIL-side coverage
went 3 → 18 assertions and 3 → 8 checks with a pinned failure, each pinned to its published
constant *before* the status. Both sides of all seven limit-bearing boundaries are pinned, with no
skips. C1.9's validation is exhaustive — I could not find a settable field that accepts `nan`.
C1.7's subsumption argument is correct and I could not break it over 4 680 configurations. Five of
seven mutants died, several to more than one test. The refusal machinery is one renderer shared by
four surfaces rather than four copies.

## Go / no-go

**NO-GO for Phase 2 as scheduled. Land a short Phase 1b first — B1, B2, B3's seed, and M2 —
then go.**

The reasoning is not that Phase 1 is bad work; it is that three of its defects are in the exact
code Phase 2's first commits touch. C2.3 rewrites the water-window predicate that B1 crashes on and
B3 mis-seeds; C2.1 widens the refusal that B2 ignores and multiplies M2's exposed consumers. Doing
Phase 2 first means fixing all four anyway, in a tree where the blast radius is larger and the
cause is harder to see — B1's own error message misdiagnoses itself, and after C2.3 it will look
like a C2.3 bug.

Phase 1b is small and every item is specified above:

1. **B1** — bound `_climb_to_boundary` by the predicate's own plateau width, not by a fraction of
   the seed, with a test that fails if the bound moves (closes M4's `CLIMB_TOLERANCE` half too).
2. **B2** — route `sensitivity.py` and `examples/worked_example.py` through
   `unsafe_at_any_amplitude_note()` and `format_limit`.
3. **M2** — rename to `limit_bearing_ceiling_uA`; `limiting_current_uA -> float | None`. This makes
   B2 a compile error rather than a review finding, which is the point.
4. **M3** — book the five unbooked movers in §6, and fix §9's 67(b) row.
5. **M5(a)** — `assert f"after {STEP_BUDGET} steps" in message`.

**M1 gates the figure commit specifically.** Split `limits_incomplete` before rendering it
anywhere new; if that must wait, render `not_evaluated_note()` on the figure instead and leave
`limits_incomplete` off it.

**B3** is a Phase-2 commit, not Phase 1b — but it must land *inside* C2.3 with the corrected seed,
never as a follow-up.

Everything else on the MINOR list can ride along with Phase 2 or Phase 7.

*Review complete.*
