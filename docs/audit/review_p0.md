# Phase 0 review — `7a0515b..7e40799`

Scope: the six commits `3c66e24, 3cc5c53, f1a704b, f5d8225, 1ef63f8, 7e40799`.
Evidence produced this session with `./.venv/bin/python`
(matplotlib 3.10.8, reportlab 5.0.0, CPython 3.14.7). Scratch work under
`$SCRATCH/{old,new}` (pristine `git archive` exports of the two endpoints — the repo was
not modified).

**Verdict: GO — sound, with 5 MAJORs to land before Phase 1's first oracle-backed assertion. No BLOCKER.**

---

## 1. Behaviour is unchanged — VERIFIED, no finding

Method: `$SCRATCH/sweep.py`, run under `PYTHONPATH=old` and `PYTHONPATH=new` with the same
interpreter, dumping every float as `float.hex()` so a 1-ulp move cannot hide behind repr.

Surface swept:

| surface | cases |
|---|---|
| `SafetyCalculator.assess()` — status, `limiting_current_uA`, `limiting_mechanism`, `limiting_current_interval_uA`, and per-check `status`/`summary`/`detail`/`margin`/`describe()` | 432 (9 materials x 8 geometries x 6 protocols incl. monophasic), 3888 checks |
| `SafetyCalculator.describe()` full text | 432 |
| `neurostim.io.report_to_json` | 432 |
| `neurostim.io.current_sweep` rows | 120 (24 electrodes x 5 amplitudes) |
| `geometry` surface (`area_cm2`, `access_resistance_ohm`, `..._is_exact`, radius) | 72 |
| `models.field.potential_V` at 3 distances | 42 |
| `electrodes` presets | 10 |
| `sensitivity.analyse`, `transient.analyse` | 1 each, all fields |

Result: **9 111 200 bytes of output, byte-for-byte identical** (`md5 25afcdad...` on the
earlier 9 MB cut; `cmp -s` clean on the final one). Overall statuses in the corpus:
218 CAUTION / 202 FAIL / 12 NOT_EVALUATED, so the sweep is not degenerate — it exercises
every verdict branch, both waveforms, and every shipped material.

The only source edits in the diff are `viz/style.py` (savefig metadata + `svg.hashsalt`),
`io/report.py` (byline stamp source + per-document `invariant`), and the new `_repro.py`.
None of them touches a computed value. Confirmed by the sweep above and by reading the
diff: no arithmetic line is changed anywhere in `neurostim/`.

(Sections 2-7 follow.)

---

## 2. `tests/oracles/` — the load-bearing claim, attacked

### 2a. Independence: holds structurally

`disc_field.py`, `drift.py`, `fd_band.py` import nothing but `math` / nothing at all; no
`neurostim` at module or function level. `tests/oracles/__init__.py` imports only those
four modules, so importing the package does not import `neurostim`.

`fail_ceiling.py` imports `neurostim.SafetyCalculator` **inside** `rebuild_at`, and reads
exactly one property of it: `assess().failed`. I confirm the confinement is real — it reads
VERDICTS, never NUMBERS. That dependency is **acceptable and necessary**: "the highest
amplitude at which nothing fails" is a property *of the package's verdict function*, and
the only alternative would be to reimplement nine checks, which would be a second package,
not an oracle. The structural test `test_the_oracle_reads_only_the_failed_tuple`
(`tests/test_oracles.py:85-92`) greps the module body for `limiting_current_uA`,
`limiting_mechanism`, `.margin` and is a reasonable, if narrow, guard.

`scripts/fd_band_reference.py` imports only numpy/scipy — verified. And
`test_the_generator_reproduces_the_table` actually re-runs the solve (coarse grid,
`rel=0.02`) rather than trusting the frozen number, so the table is not a magic constant.

### 2b. Are the expected values pinned to hand constants? Mostly yes

| oracle | pinned to | can it drift with the code? |
|---|---|---|
| `fail_ceiling` | `cogan2016.MICROELECTRODE_DAMAGE_THRESHOLD_NC_PER_PHASE` = 4 nC, divided by 200 us by hand = 20.0 uA, and `assert threshold_nC == 4.0` | No. Both the constant and the arithmetic are asserted. |
| `disc_field` | `R = 1/(4 sigma a)` computed in the test, ratios 0.499992 / 0.999983 `abs=5e-7` | No — **but see 2d(iii)**. |
| `drift` | 0.2558 s, re-derived in the test from 586.5 uA/cm^2 and 2.346 V/s | No. |
| `fd_band` | frozen table + a live re-solve of the clinical aspect | Partly — only 1 of 8 rows is re-derived. |

**`drift_time_s` — verified this session (was outstanding).** Independent hand derivation,
no oracle code: `n_exact = V_w C_total / (I W) = 0.6 x (250e-6 x pi x 0.127 x 0.15) /
(3000e-6 x 90e-6) = 33.2485`.

* closed form `= n_exact / f = 0.2557578634653229 s` — **bit-equal** to
  `drift_time_s_closed_form`, and within `4.21e-5` of the plan's stated `0.2558`
  (the test allows `abs=5e-5`, so it passes with ~16 % of its tolerance left).
* pulse loop `= ceil(n_exact)/f = 34/130 = 0.26153846153846155 s` — **bit-equal** to
  `drift_time_s`. The loop is a genuine accumulation; the two routes are independent.

### 2c. MAJOR findings against the oracles

**[MAJOR-1] `fail_ceiling_uA` returns a wrong answer, silently, on a non-monotone
predicate — and the self-check that is documented to catch it crashes instead.**
`tests/oracles/fail_ceiling.py:66-97`.

The docstring at `fail_ceiling.py:78-80` states: *"The predicate is assumed monotone...
That assumption is asserted at the answer by `brackets_the_ceiling`, so a check that breaks
it is reported rather than silently bisected through."* Neither half is implemented.

1. `fail_ceiling_uA` never calls `brackets_the_ceiling`. Nothing is asserted unless a
   caller remembers to, and only one of the six tests does.
2. On the path where non-monotonicity actually lands — the `return 0.0` at
   `fail_ceiling.py:84` — `brackets_the_ceiling` does not return `False`; it **raises**,
   because it guards `math.isfinite` but not `> 0`, and `StimProtocol` rejects a zero
   amplitude.

Concrete failure case (reproduced):

```python
calc = SafetyCalculator(DiscElectrode(100.0, "Pt"), StimProtocol(80, 200, 130, 1),
                        compliance_V=10.0, resting_potential_V=0.9)   # 0.9 V > Pt's +0.8 V
fail_ceiling_uA(calc)            # -> 0.0
# truth: assess().failed is empty on [9.83, 19.61] uA; the ceiling is 19.61 uA.
#        at 1e-9 uA the only failing check is 'Water window'.
brackets_the_ceiling(calc, 0.0)  # -> ValueError: current_uA must be finite and > 0
```

This is exactly the False-True-False water-window shape the plan itself predicts
(§2 D2 point 3). I swept 6 804 configurations (7 geometries x 6 protocols x 9 resting
potentials x 3 compliances x 6 materials): **88 are non-monotone**, 1.3 %. A second sweep
of 17 496 configurations found no `True->False->True` shape, so the oracle does not
currently return a *plausible wrong finite number* — every observed failure returns `0.0`.

Why it still matters for Phase 1: `0.0` is **overloaded**. Under the ledger-84 convention
`0.0` is the correct answer for an amplitude-independent failure (Charge balance on
monophasic — confirmed, the oracle returns `0.0` there and that is right). It is also the
answer when the passing band merely does not include 1e-12. The two are indistinguishable
at the call site, so a Phase 1 test cannot tell "no usable amplitude" from "the oracle gave
up". Fix is ~6 lines: call `brackets_the_ceiling` from `fail_ceiling_uA` before returning;
make `brackets_the_ceiling` return `False` for `ceiling_uA <= 0`; and on the `0.0` path
probe a few decades before concluding.

**[MAJOR-2] The oracle has no way to express the restated D3(i), so Phase 1 cannot assert
against it on any monophasic protocol.** `tests/oracles/fail_ceiling.py:58-63`.

`no_check_fails` reads `assess().failed` — *every* check. Ledger 84 restates D3(i) as *"the
highest amplitude at which no **LIMIT-BEARING** check fails"*, and LIMIT_BEARING excludes
Charge balance and Validated envelope. The oracle therefore computes a **different
quantity** from the one Phase 1 will be asserting, with no parameter to restrict the
predicate, and `fail_ceiling.py:8-9` still claims *"This is the definition of 'limiting
current' the fix plan settles on"* — which after ledger 84 is no longer true.

Reproduced: `CylindricalBandElectrode(1270, 1500, "PtIr")`, 3000 uA / 90 us / 130 Hz,
monophasic — `assess().failed == ('Charge balance',)`, oracle `0.0`, package `15285.5`.
The oracle's `0.0` is *correct for the predicate it implements* and is honest, not a quiet
fallback. But it is not D3(i), and D5/P4 (the monophasic work) is exactly where Phase 1
needs an oracle. Fix: a `names` / `limit_bearing_only` parameter on `no_check_fails`, plus
a docstring correction.

**[MAJOR-3] `rebuild_at`'s stated protection against constructor drift does not exist.**
`tests/oracles/fail_ceiling.py:33-41`.

The docstring claims *"naming them means a new field that changes the verdict shows up here
as a missing argument rather than as a wrong answer."* That is true only for a new
**required** parameter. A new **optional** one — which is what Phase 1 will add — is
silently defaulted, and the oracle then answers about a different calculator than the one
it was handed. Verified today all 12 `SafetyCalculator` parameters are carried; nothing
asserts that they continue to be. Fix: assert
`set(inspect.signature(SafetyCalculator.__init__).parameters) == FROZEN_SET` in
`tests/test_oracles.py`, so the next added keyword fails loudly.

**[MAJOR-4] `disc_surface_potential_V` takes the access resistance as an *input*, so the
r = 100a pin is identically blind to an error in R that the field model shares.**
`tests/oracles/disc_field.py:43-56`, claim at `disc_field.py:12`.

The module's headline claim is *"**It pins the resistance and the field together.** ... Any
change that moves the access resistance without moving the field, or the reverse, breaks
it."* The signature does not support that for a general caller. Demonstrated:

```
R fed to the oracle    ratio pkg/exact at r=100a   (test asserts 0.999983)
correct (Newman)       0.999983
wrong by 2/pi          0.999983
wrong by 1/2           0.999983
```

`tests/test_oracles.py` is **correct** — it computes R from `newman_disc_resistance_ohm`.
The trap is for C3.1: a Phase 3 test written as
`disc_surface_potential_V(I, electrode.access_resistance_ohm, a, 100*a)` passes with a 57 %
wrong R, which is precisely the "two errors that cancel" mode D4 exists to break. Fix: have
the oracle take `conductivity_S_per_m` and compute R itself via
`newman_disc_resistance_ohm`, or add a structural test like `fail_ceiling`'s.

### 2d. MINOR findings against the oracles

* **[MINOR]** "within one pulse" should be "within one **period**" — the bound is `1/f`
  (7.69 ms), not the pulse width (90 us), an 85x difference. The assertion itself is right
  (`one_pulse = 1.0 / self.FREQUENCY_HZ`), only the prose is wrong, in four places:
  `tests/oracles/drift.py:17`, `tests/oracles/__init__.py:35`, the test name
  `test_the_pulse_loop_agrees_with_the_closed_form_to_within_one_pulse`, and
  `docs/audit/FIX_PLAN_v2.md` §5.0 C0.6.
* **[MINOR]** `drift_time_s(max_pulses=100_000_000)` (`drift.py:49`) is a pure-Python loop. Measured
  0.438 s per 2e6 iterations, so a call that does not reach the window costs **~22 s**
  before returning `inf`. Cheap guard: compute the expected pulse count first and return
  `inf` without looping when it exceeds `max_pulses`.
* **[MINOR]** `FD_BAND_REFERENCE` carries 8 aspects; the docstring table above it (and the
  plan's §2 D4 table) lists 7 — `4.000 -> 172.1` appears in the data and nowhere in the
  prose. Only `1.181` is re-derived by `test_the_generator_reproduces_the_table`; the other
  seven rows are unverified constants.
* **[MINOR]** `FD_BAND_REFERENCE` is keyed by float, so a computed aspect
  (1500/1270 = 1.1811023...) will `KeyError` rather than match `1.181`.

---

## 3. `scripts/branch_floor.py` — the metric is right; the gate has one hole

**It computes branch POINTS, and the baseline reproduces to the digit.** I installed
coverage 7.16.1 into the scratchpad (never into the repo venv) and ran the suite against
both exported trees:

| tree | tests | branch points | arcs | blended |
|---|---|---|---|---|
| `7a0515b` | 522 passed | **185 / 383 = 48.30 %** | 548 / 766 = **71.54 %** | **88.15 %** |
| `7e40799` | 627 (626 passed, 1 env-only failure) | 188 / 385 = 48.83 % | — | 89 % |

Every number in the script's docstring — 185/383, 48.30 %, 548/766, 71.54 %, 88.15 % — is
exact. The aggregation rule (`points = {arc[0] for arc in executed} | {arc[0] for arc in
missing}`; covered iff no arc from that line is in `missing_branches`) is branch-point
coverage as described, and `tests/test_build_gates.py:63-99` pins the half-credit case, the
three-exit case and the branchless-file case directly.

**[MINOR] An empty-but-readable report passes at 100 %.** `scripts/branch_floor.py:70-73`.
`percent()` returns `100.0` for a zero denominator, and `aggregate()` drops every file with
no branch points, so:

```
$ echo '{"meta":{"branch_coverage":true},"files":{}}' > empty.json
$ python scripts/branch_floor.py --json empty.json --min 48.0
branch points fully exercised: 0 / 0 = 100.00 %
OK                                                     # exit 0
```

Same for `{"meta":{"branch_coverage":true}}` and for a report whose only file has no arcs.
The docstring says *"A report that cannot be read is an error, never a pass"* — a report
that *is* readable and empty is a pass. **Mitigated, not closed:** through the committed CI
path this is unreachable, because `coverage json` on an empty dataset prints
`No data to report.` and exits 1, failing the step before `branch_floor.py` runs (verified).
One-line fix: `if points == 0: fail`.

**Not fooled by:** unexecuted modules. `neurostim/gui/__main__.py` has zero covered lines
and still lands in the denominator (coverage reports all its branch arcs as missing), so a
run that fails to import a module cannot shrink the denominator. The 11 files
`aggregate()` does drop are genuinely branchless (`__init__.py` files and pure data
modules) — correct.

**[MINOR]** CI lints `neurostim tests examples` and not `scripts/`, so the three new
scripts are unlinted in CI. They are clean under `ruff check scripts` today.

---

## 4. Byte-reproducibility (C0.3) — all three departures endorsed, verified empirically

**(a) Not passing `metadata={"Date": None}`, and asserting the epoch reaches the output
instead — ENDORSE, and it is better than the plan.** Verified: with
`SOURCE_DATE_EPOCH=1234567890` the PDF carries
`/CreationDate (D:20090213233130+00'00')` and the SVG carries
`<dc:date>2009-02-13T23:31:30+00:00` — the pinned instant, present, not deleted. Suppressing
the date would have made `test_every_artifact_is_byte_identical_across_two_runs` passable by
a future regression that simply stopped writing timestamps;
`test_the_pinned_date_reaches_every_artifact_that_carries_one`
(`tests/test_reproducibility.py:85`) closes that. What *is* suppressed is only
`Creator`/`Producer` (`neurostim/_repro.py:31-42`) — verified absent: no `Matplotlib` and no
`3.10.8` string in the PDF or SVG — which is the right call, since a matplotlib upgrade
would otherwise rewrite every artifact with no number moving.

**(b) Per-document `invariant`, only when the date is pinned — ENDORSE. The result is
reproducible AND truthful.** Verified both ways:

```
unpinned: two builds 1.2 s apart -> bytes differ
          /CreationDate D:20260922223900+05'00'  and  ...223901+05'00'   (real clock)
          visible byline: "Generated 2026-09-22 17:09 UTC"               (real clock)
pinned:   two builds 1.2 s apart -> bytes identical
          /CreationDate D:20090213233130+00'00'                          (the pinned epoch)
```

reportlab 5.0.0's invariant mode honours `SOURCE_DATE_EPOCH` rather than stamping a fixed
fictional date, so the pinned document is not lying either — it says the build date it was
built for. A global `rl_config.invariant = 1` would have put a false creation date on every
real report; the per-document flag does not.

**(c) The `datetime.now()` in the PDF's visible byline (ledger 85) — a real defect, and the
fix is correct.** `neurostim/io/report.py:217` (was `datetime.now(timezone.utc)` at the same line pre-Phase-0) printed the wall clock into the document
body, so even a fully invariant PDF differed between two runs that straddled a minute
boundary — an intermittent failure roughly once in a few hundred runs, i.e. a flake rather
than a gate. Routing it through `_repro.build_time()` keeps the wall clock when unpinned
(verified above) and `test_the_visible_byline_follows_the_pinned_date` pins the pinned case
through `pdftotext`.

Also checked: `save_publication`'s TIFF path still works now that `metadata` is passed
(`_repro.VECTOR_METADATA.get("tiff")` is `None`, which `savefig` accepts) — 3 formats
written, 1.3 MB TIFF at dpi=100.

**[MINOR]** `invariant=1 if _repro.is_pinned() else 0` (`neurostim/io/report.py:416`)
passes an explicit `0`, which **overrides** a caller's global `reportlab.rl_config.invariant
= 1`; the previous `None` deferred to it. `else None` would preserve that opt-in.

**[MINOR]** `_repro.source_date_epoch()` validates only that the value parses as `int`.
A negative or absurd epoch reaches `datetime.fromtimestamp`, which raises an unnamed
`OverflowError`/`OSError` rather than the named error the module is careful about elsewhere.

**[MINOR]** `test_the_visible_byline_follows_the_pinned_date`
(`tests/test_reproducibility.py:118-123`) sets and `del`s `os.environ` directly instead of
using `monkeypatch` like its three siblings, so it deletes a pre-existing
`SOURCE_DATE_EPOCH` for the remainder of the session.

---

## 5. `ledger_check.py` and `regenerate_example_output.py` — can either pass while doing nothing?

### `ledger_check.py` — no, it catches the real historical defect

Run against the genuinely broken pre-baseline ledger (`7a0515b~1`):

```
FAIL: line 20: 11 fields against the header's 7 -- an unescaped '|' ... : '8'
FAIL: line 58: 9 fields against the header's 7 -- an unescaped '|' ... : '46'
```

and `OK: 83 entries, 7 fields each` on the tree at `7e40799`.

**The 7-vs-9 / 11,9-vs-13,11 discrepancy between the script and the plan is not an error.**
`tests/test_build_gates.py:391-393` reconciles it explicitly: the plan counts with a bare
`str.split("|")`, which includes the leading and trailing empty tokens. I verified both:
naive split gives header 7+2 = 9, row 8 = 11+2 = 13, row 46 = 9+2 = 11. Both statements are
correct under their own convention and the builder documented it. No finding.

**[MINOR] The commit subject overstates what the commit did.** `1ef63f8 build: repair and
gate the mistakes ledger` **gates**; it repairs nothing, because rows 8 and 46 were already
repaired in the baseline itself (`7a0515b docs: record execution critique and repair ledger
table parsing`). Consequently plan §5.0 C0.5's "test that must fail first" does not fail at
this phase's own baseline. The gate is nonetheless genuine — verified against the real
broken input above — so this is a record-accuracy point, not a dead gate.

**[MINOR]** A ledger with a header and zero data rows passes: `OK: 0 entries`. No minimum
is asserted anywhere. `parse_table`'s docstring says "the first markdown table", but it
actually concatenates every `|`-prefixed line in the file into one table; harmless today
(the ledger has one table) and it would fail loudly rather than quietly if a second were
added.

### `regenerate_example_output.py` — the README half is a real gate; there is no committed-artifact half

`--check` genuinely runs the package: it builds `calc.describe()` and byte-compares the
regenerated block against the committed one. It is proven able to fail
(`test_check_exits_non_zero_when_the_transcript_drifts`), and the transcript is pinned from
two independent directions — every line must appear verbatim in `describe()`
(`test_every_transcript_line_appears_verbatim_in_describe`) and the headline count must
equal `len(assessment.checks)` (`test_the_transcript_reports_every_check`). It cannot pass
while doing nothing.

**On `example_output/` being untracked — ENDORSE, with one correction to the record.** It
was **already** ignored at `7a0515b` and has **never** been tracked in this repository
(`git log --all -- example_output` is empty). Phase 0 added only the explanatory comment.
So this is not a departure from the plan so much as the plan's C0.4 having been written
against a false premise ("output must equal what is committed"). The consequence should be
stated plainly: **no committed artifact is byte-compared; the only byte-compared committed
surface is the README block.** That is acceptable, and arguably stronger, because
`tests/test_reproducibility.py` runs the worked example twice into clean directories and
diffs all seven artifacts — which catches non-determinism whether or not anyone remembered
to regenerate, something a diff against a committed blob cannot do.

**[MINOR]** The module docstring claims *"`--check` fails when either has drifted"*
(`scripts/regenerate_example_output.py:12`). It checks only the README; `main()` returns 0
immediately after the README check when `--check` is set, and never touches
`example_output/`. Correct the sentence.

**[MINOR]** `test_check_exits_non_zero_when_the_transcript_drifts`
(`tests/test_build_gates.py:272`) **writes to the repository's tracked `README.md`** and
restores it in a `finally`. A hard crash in that window leaves a tracked file containing a
false `Overall: PASS`, and two workers under `pytest-xdist` would race. The cause is that
the script hardcodes `README = REPO_ROOT / "README.md"` with no override; a `--readme PATH`
argument would let the test work on a copy.

---

## 6. `tests/test_units.py` — the mutant claim is true, verified by mutation

I copied each exported tree to a scratch directory, applied one mutation, and ran the whole
suite. The repository was never touched.

| mutant | mutation | `7a0515b` (522 tests) | `7e40799` (627 tests) | killed by |
|---|---|---|---|---|
| **C4** | drop `* 1e-6` on `pulse_width_us` in `neurostim/safety/charge.py:72` | **522 passed — survives** | **fails** | `test_cic_max_current_is_a_charge_divided_by_a_time_in_seconds` |
| **M4** | `(4.0/3.0)` -> `4.0` in `neurostim/models/vta.py:152` | **522 passed — survives** | **fails** | `test_activated_volume_is_four_thirds_pi_r_cubed_in_cubic_millimetres` |
| **M5** | `* 1e-3` -> `* 1e-6` in `neurostim/models/vta.py:151` | **522 passed — survives** | **fails** | same test |
| **M10** | drop `* 1e-6` in `neurostim/models/strength_duration.py:103` | **522 passed — survives** | **fails** | `test_weiss_threshold_charge_is_microamps_times_microseconds` |

(The only other failure in the `7e40799` runs is
`TestLedgerGate::test_a_real_commit_hash_is_accepted`, an artifact of my exports having no
`.git`; see the MINOR below.)

**No ratio round-trip is used as an expected value.** Read line by line: every expected
value is an SI chain written longhand or an absolute magnitude. The one line that goes
through a package converter — `result == approx(units.charge_uC(rheobase_uA,
pulse_width_us + chronaxie_us))` at the end of the M10 test — is a cross-check, not the
pin: the preceding `assert result == pytest.approx(0.004)` is what kills the mutant, and
`units.charge_uC` is itself pinned absolutely in `TestChargeFromCurrentAndTime`. Not a
finding.

`test_cic_max_current_...` draws the material limit from `get_material("Pt").cic_uC_cm2()`
rather than a literal, which is deliberate and stated in its docstring ("the identity is
dimensional, so it holds whatever the material's stored limit turns out to be after the
provenance phase"). Correct choice — it keeps the unit test from becoming a data test that
Phase 4 would have to rewrite.

Also verified: the grep subprocess in `tests/test_gui.py` is genuinely replaced by an
`rglob` anchored to `Path(__file__).parents[1]`, with `assert package.is_dir()` and
`assert sources` so the scan cannot report "all clean" by matching nothing — the exact
failure mode the old `grep -rho ... neurostim` had when run from any other directory.

---

## 7. Ordinary review of the rest

**[MAJOR-5] The ledger gate will break CI at the first Phase 1 commit, because every
`actions/checkout@v4` in the workflow is a shallow (`fetch-depth: 1`) clone.**
`.github/workflows/ci.yml:34, 67, 106, 139` against `scripts/ledger_check.py:138-146`.

`commit_exists()` runs `git cat-file -e <sha>^{commit}`. Under a depth-1 checkout no
historical object is present, so any recorded hash resolves to "does not exist" and the
`lint` job fails with `entry N records commit <sha>, which does not exist in this
repository`. It passes today only because every `Commit` cell reads `pending` and
`_HASH` does not match it. The plan requires those cells to be filled from C1.1 onward, so
this breaks on the first Phase 1 commit. Fix: `with: fetch-depth: 0` on the `lint` job's
checkout (or `git cat-file` guarded by a "is this a full clone" probe that *skips* rather
than fails).

**[MINOR]** `tests/test_build_gates.py:439-447`
(`test_a_real_commit_hash_is_accepted`) calls `git rev-parse HEAD` with `check=True`, so
outside a git checkout it raises `CalledProcessError` instead of skipping. A JOSS reviewer
running `pytest` on an unpacked sdist or zip gets a hard error rather than a skip. This is
the one failure I saw in every clean run above. `pytest.skip` when the call fails.

**Other diff items, all fine:**

* `examples/worked_example.py:165-169` — dropping the 47 MB TIFF is a change to the
  artifact set, not to any computed value, and is asserted by
  `test_the_example_no_longer_writes_a_47_megabyte_tiff`. The `formats=("svg","pdf")`
  argument is explicit at the call site rather than a change to `save_publication`'s
  default, which is the right place for it.
* `neurostim/viz/style.py:174-180` — `mpl.rc_context` scopes the hashsalt to the call
  instead of mutating global rcParams. Correct.
* `README.md` — the transcript change is the *correction of a stale block*, not a behaviour
  change: the old block (5 checks, 70.69 uA) never matched the code at `7a0515b`. Confirmed
  by §1: assessments are byte-identical across the range.
* `pyproject.toml` + CI matrix gain 3.14, which is the interpreter this is actually
  developed on (3.14.7). Good.
* `ruff check` and `mypy neurostim` are clean on the tree at `7e40799` (run this session).

---

## 8. Findings, ranked

### BLOCKER
None. Nothing in this diff prevents Phase 1 from starting.

### MAJOR — fix before Phase 1 wires any assertion to an oracle
1. `tests/oracles/fail_ceiling.py:66-97` — non-monotone predicates are bisected through
   silently; `brackets_the_ceiling` raises instead of reporting on the `0.0` path; the
   documented guarantee is not implemented. 88 of 6 804 swept configurations trigger it.
2. `tests/oracles/fail_ceiling.py:58-63` — no `LIMIT_BEARING` hook, so the oracle computes
   a different quantity from the restated D3(i); the module still claims otherwise.
3. `tests/oracles/fail_ceiling.py:33-41` — `rebuild_at`'s "a new field shows up as a
   missing argument" is false for a new *optional* parameter, which is what Phase 1 adds.
4. `tests/oracles/disc_field.py:43` (claim at `:12`) — R is an input, so the r = 100a pin is blind to a
   shared error in R; demonstrated to return 0.999983 for R wrong by 2/pi and by 1/2.
5. `.github/workflows/ci.yml:67` + `scripts/ledger_check.py:138` — shallow checkout makes
   `commit_exists` fail on every recorded hash; breaks CI at the first Phase 1 commit.

### MINOR
6. `scripts/branch_floor.py:70-72` — empty report passes at 100 % (unreachable via committed CI).
7. "within one pulse" should be "within one period" (`drift.py:17`, `oracles/__init__.py:35`,
   the test name, plan §5.0 C0.6).
8. `drift.py:49` — `max_pulses=1e8` costs ~22 s before returning `inf`.
9. `fd_band.py` — aspect 4.000 in the data and not in the table; 7 of 8 rows never re-derived.
10. `fd_band.py` — float dict keys; a computed 1500/1270 will not match `1.181`.
11. `neurostim/io/report.py:416` — explicit `invariant=0` overrides a caller's global setting.
12. `neurostim/_repro.py:45-55` — negative/absurd epochs raise an unnamed error.
13. `tests/test_reproducibility.py:118` — raw `os.environ` mutation instead of `monkeypatch`.
14. `scripts/regenerate_example_output.py:12` — `--check` does not check `example_output/`.
15. `tests/test_build_gates.py:272` — the drift test rewrites the tracked `README.md`.
16. `scripts/ledger_check.py` — a zero-row ledger passes; `parse_table` is not "the first table".
17. `1ef63f8`'s subject says "repair and gate"; the repair landed at the baseline.
18. `tests/test_build_gates.py:439` — hard error, not skip, outside a git checkout.
19. CI `ruff check` omits `scripts/`.

---

## 9. Verdict

**Phase 0 is sound. GO for Phase 1**, conditional on the five MAJORs landing first —
four of them are in `tests/oracles/` and together are well under an hour of work, and the
fifth is one line of YAML.

What I actually confirmed, rather than accepted:

* Behaviour is unchanged over 432 assessments / 3 888 checks / 120 sweep rows / 72 geometry
  surfaces — 9.1 MB of hex-precision output, byte-identical between the endpoints.
* The branch-point baseline is real: 185/383 = 48.30 % reproduced exactly, along with
  548/766 = 71.54 % and 88.15 %.
* All four named mutants survive the 522-test suite and die in the 627-test suite.
* `drift_time_s` is bit-equal to an independent hand derivation on both routes and matches
  the plan's 0.2558 s.
* Reproducibility is achieved by pinning the date, not by deleting it, and an unpinned
  report still states the minute it was really made.
* The ledger gate catches the real historical defect when fed the real broken file.

The phase does what it set out to do. Its weakness is not in the measurements — those are
unusually well sourced — but in three docstrings in `tests/oracles/` that claim guarantees
the code does not yet provide. In a phase whose entire purpose is that the next seven
phases can trust what they assert against, a false guarantee is the one defect that
propagates, so fix those before the first oracle-backed assertion is written.
