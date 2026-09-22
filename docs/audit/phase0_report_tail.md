# Phase 0 report — remainder

Continues from the truncation point in C0.3's third departure. C0.1, C0.2 and the first two
C0.3 departures are not repeated.

---

## 1. C0.3, third departure, completed — `io/report.py:217`

**The sentence that was cut.** `io/report.py:217` read the wall clock directly:

```python
stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
byline = f"Generated {stamp}" + (f" &middot; {author}" if author else "")
```

That string is rendered into the PDF's own body, not into its metadata, so it is *not*
covered by `SOURCE_DATE_EPOCH`, by reportlab's `invariant` mode, or by anything else the
fix plan's C0.3 row lists. It is quantised to the minute, which is why the defect hides:
two back-to-back runs of the worked example complete in about 8 s and land in the same
minute on almost every attempt, so `safety_report.pdf` compares byte-identical and the
gate reports success. It would have failed only when a run straddled a minute boundary —
roughly once in a few hundred runs, and on a machine slower than this one, much more often.

**Why that matters beyond one file.** The whole point of C0.3 is to make C0.4's byte
comparison meaningful. A gate that passes 99 % of the time for a reason unrelated to the
property it claims to test is worse than no gate: it produces a green CI history that
licenses trusting the artifacts, and then fails at random on someone else's machine, where
it will read as flakiness to be retried rather than as the real non-determinism it is. It
is the same failure mode as the tautologies in §1 of `tests/oracles/__init__.py`, in a
build gate rather than in a unit test.

**What I did.** Added `neurostim/_repro.py` with `source_date_epoch()`, `build_time()` and
`is_pinned()`, and routed the byline through it:

```python
stamp = _repro.build_time().strftime("%Y-%m-%d %H:%M UTC")
```

`build_time()` returns `datetime.fromtimestamp(SOURCE_DATE_EPOCH, tz=utc)` when the
variable is set and `datetime.now(timezone.utc)` when it is not, so an ordinary report a
user generates still carries the time it was really generated. A malformed value raises
`ValueError` rather than falling back to the wall clock — a silent fallback there would
make a build *look* reproducible while not being so, which is the defect one level up.
The now-unused `datetime`/`timezone` import was removed.

`SimpleDocTemplate` is passed `invariant=1` only when the date is pinned, so the PDF's
`/CreationDate`, `/ModDate` and document id are pinned by us rather than by whatever
reportlab's default happens to be in a future version.

**Pinned by test, not left to luck.** `tests/test_reproducibility.py::
test_the_visible_byline_follows_the_pinned_date` builds a report under
`SOURCE_DATE_EPOCH=1234567890`, runs `pdftotext -layout`, and asserts the body contains
`Generated 2009-02-13 23:31 UTC`. The pinned instant is 2009, so no wall clock can produce
it by accident, and the assertion also blocks the lazy repair of deleting the byline.

**Ledger status — this is a new defect.** I searched `CODE_MISTAKES_LOG.md` for
`timestamp`, `CreationDate`, `datetime.now`, `hashsalt`, `determinis`: **zero hits for
each**. Entry 54 covers `io/report.py:200-413` but is about the PDF omitting a package
version, a digest, and 4 of 11 `SafetyCalculator` settings — a different claim. Entry 61
(io-gui M1–M14) mentions the TIFF but as a size complaint, not a determinism one. Nothing
in the ledger names artifact reproducibility.

### Proposed ledger entry A

| field | value |
|---|---|
| severity | **MEDIUM** |
| file:line | `io/report.py:217`; `viz/style.py` `save_publication`; `examples/worked_example.py` |
| defect | Generated artifacts are not reproducible: 5 of 8 outputs of `examples/worked_example.py` differ between two back-to-back runs of unchanged code, at identical file lengths. Three independent causes — SVG `<dc:date>` plus element ids salted from a per-process `uuid4` (`rcParams["svg.hashsalt"]` defaults to `None`); matplotlib and reportlab `/CreationDate`; and `report.py:217` printing `datetime.now()` into the PDF's *visible* byline, which no environment variable covers and which is quantised to the minute, so byte-identity across two fast runs is luck rather than a property. Separately, both matplotlib backends stamp `Matplotlib v3.10.8` into every SVG and PDF, so a dependency upgrade rewrites every committed artifact with no number moving. Committed output that changes on its own cannot distinguish a real numeric change from clock noise. |
| fix | `neurostim/_repro.py` (SOURCE_DATE_EPOCH contract, raising on a malformed value); fixed `svg.hashsalt` in an `rc_context` around `savefig`; `Creator`/`Producer` suppressed on vector `savefig`; byline routed through `_repro.build_time()`; reportlab `invariant=1` only when the date is pinned. |
| commit | `f1a704b` |

Severity rationale: no safety number is wrong, so not HIGH. But it defeats the byte
comparison every later numeric commit depends on, and it produced a gate that passed for
the wrong reason — which is the class of defect this repair exists to eliminate. MEDIUM,
not LOW.

---

## 2. C0.4 — `build: generate example_output and the README transcript from one script`

**Commit `f5d8225` · 592 tests** (584 → 592)

### Failing first

```
FAILED tests/test_build_gates.py::TestGeneratedReadmeTranscript::test_the_readme_carries_the_generated_markers
FAILED tests/test_build_gates.py::TestGeneratedReadmeTranscript::test_the_committed_transcript_is_what_the_package_prints
FAILED tests/test_build_gates.py::TestGeneratedReadmeTranscript::test_check_exits_zero_on_the_committed_readme
FAILED tests/test_build_gates.py::TestGeneratedReadmeTranscript::test_check_exits_non_zero_when_the_transcript_drifts
FAILED tests/test_build_gates.py::TestGeneratedReadmeTranscript::test_the_example_no_longer_writes_a_47_megabyte_tiff
5 failed, 17 passed in 10.61s
```

with, for the TIFF row:

```
        written = sorted(p.name for p in target.iterdir())
>       assert not [n for n in written if n.endswith(".tiff")]
E       AssertionError: assert not ['figure_summary.tiff']
----------------------------- Captured stdout call -----------------------------
wrote 8 artifacts to .../example_output:
  assessment.json
  current_sweep.csv
  figure_strength_duration.pdf
  figure_strength_duration.svg
  figure_summary.pdf
  figure_summary.svg
  figure_summary.tiff
  safety_report.pdf
```

### Passing after

```
592 passed in 44.80s
ruff: All checks passed!
mypy: Success: no issues found in 52 source files
$ python scripts/regenerate_example_output.py --check
OK: the README transcript matches the package's own output
```

### What was actually wrong

The committed README quick-start block:

```
Overall: FAIL
Limiting current: 70.69 uA (Pt charge-injection limit)

[         PASS] Shannon criterion: k = -0.04 at threshold 1.70, 7.44x headroom
[         FAIL] Charge injection limit: 56.59 uC/cm^2 exceeds the 50 uC/cm^2 limit for Pt
[         FAIL] Water window: peak -2.83 V leaves the window by 2.23 V
[         PASS] Charge balance: biphasic, fully charge-balanced
[         PASS] Compliance voltage: 3.43 V of 10.00 V (34 % used)
```

What the package prints for those exact inputs:

```
Overall: FAIL
Limiting current: 141.4 uA (Pt charge-injection limit)
  across published ranges: 141.4-212.1 uA (Shannon k 1.5-2.0, full material range)

[NOT_EVALUATED] Shannon criterion: not applicable: 0.000283 cm^2 is below the macro/micro boundary (k would read -0.04)
[      CAUTION] Charge injection limit: 56.59 uC/cm^2 of 100 uC/cm^2 (57 % used)
[         PASS] Water window: peak -0.23 V, 0.37 V headroom
[      CAUTION] Validated envelope: frequency 2.6x outside the fit conditions in a direction that reduces margin
[      CAUTION] Current density: 0.2829 A/cm^2 of the 0.3057 A/cm^2 electroporation threshold (92.6 % used, chick-tissue derived)
[         FAIL] Microelectrode charge/phase: 16 nC/phase exceeds the 4 nC/phase microelectrode damage threshold
[         FAIL] Chronic degradation: 56.59 uC/cm^2 exceeds the 50 uC/cm^2 platinum dissolution threshold
[         PASS] Charge balance: biphasic, fully charge-balanced
[         PASS] Compliance voltage: 0.83 V of 10.00 V (8 % used)
```

Five checks against nine; a limiting current understated by 2.00×; Shannon shown as a PASS
where it is `NOT_EVALUATED`; charge injection shown as FAIL where it is CAUTION; water
window shown as leaving the window by 2.23 V where it has 0.37 V of headroom; and the two
checks that actually FAIL — `Microelectrode charge/phase` and `Chronic degradation` — not
present at all. This is the first output any reviewer reads.

### How it is generated

`scripts/regenerate_example_output.py` owns both derived surfaces. The transcript is
`calc.describe()` with per-check detail elided by one mechanical rule — drop the lines the
renderer indents four spaces — so every retained line is verbatim package output. Three
assertions keep the elision honest:

- every transcript line must appear verbatim in `describe()` (it may drop lines, never
  invent or reword one);
- the number of `[...]` headlines must equal `len(assessment.checks)`, so a check cannot
  silently vanish from the block;
- `--check` must exit 1 on drift, demonstrated by perturbing `Overall: FAIL` → `PASS` in a
  test that restores the file in a `finally` and then asserts it is byte-identical again.

`--check` runs in the CI lint job. Later numeric commits rerun one script instead of
hand-editing eight surfaces.

### `.gitignore` and `example_output/` — the choice, and why

`.gitignore` already listed `example_output/`, and `git ls-files example_output` returns
nothing: the directory has **never** been tracked. The plan's C0.4 row says "output must
equal what is committed", which only has content if something is committed, so the
ambiguity had to be resolved rather than inherited.

**I kept `example_output/` untracked, and made the README transcript the tracked,
byte-compared surface.** Reasons, in order of weight:

1. Every one of the 53 remaining numeric commits rewrites every byte of all seven
   artifacts. Tracking them would add roughly 336 KB of binary churn per commit — on the
   order of 15–20 MB of history — for output that `python scripts/regenerate_example_output.py`
   reproduces exactly on demand, now that C0.3 has made it deterministic.
2. The surfaces that actually drift, and that the ledger names (74, 76, 78/S-24), are
   README claims, not figure bytes. Gating the README gates the defect class that exists.
3. A binary diff in review conveys nothing. A transcript diff shows a reviewer exactly
   which number moved, which is what §6's blast-radius accounting needs.

The decision is written into `.gitignore` as a comment rather than left implicit, so the
next person does not read the exclusion as an oversight:

```
# example_output/ is generated, not authored: `python scripts/regenerate_example_output.py`
# rebuilds it byte-for-byte from the package. Deliberately untracked -- every numeric
# commit in the repair rewrites all of it, and a few hundred kilobytes of binary churn per
# commit buys nothing that regenerating on demand does not. The tracked, byte-compared
# surface is the generated transcript block in README.md, which the same script owns and
# `--check` gates in CI.
example_output/
```

If you would rather have the artifacts in git, the change is one line in `.gitignore` plus
one test; say so and I will do it in Phase 7 rather than now, when the bytes are still
going to move 53 more times.

### Where the 47 MB TIFF went

It was never in git, so "leaves the repo" could only mean the working tree. It was 47 MB of
uncompressed 600 dpi RGBA for a single four-panel figure, and it was also about half the
runtime of every example run.

`examples/worked_example.py` now asks for `formats=("svg", "pdf")` on the summary figure —
exactly what it already did for the strength-duration figure two calls later, so this makes
the example internally consistent rather than introducing a new convention:

```python
    # SVG and PDF only. The 600 dpi TIFF `save_publication` also offers is 47 MB of
    # uncompressed RGBA for this figure, and the vector formats are the deliverable.
    for path in save_publication(
        fig, output_dir / "figure_summary", formats=("svg", "pdf"), close=True
    ):
```

`save_publication`'s own default is **untouched** — `("svg", "pdf", "tiff")` — so this is a
change to an example, not to package behaviour, which Phase 0 forbids. Result:

```
example_output/  336K   (was 47 MB)
```

A test asserts no `.tiff` is written and that the largest artifact is under 1 MB, so the
regression is gated rather than merely fixed.

**Left for a later phase, deliberately:** `save_publication` writes TIFFs with no
compression. Passing `pil_kwargs={"compression": "tiff_lzw"}` would cut any TIFF a *user*
asks for by roughly an order of magnitude at no quality cost. That changes the bytes of a
package output, so it does not belong in Phase 0. It is not in the ledger either — see
§4 below.

### Also in this commit

README's Tests section read `pytest -q  # 220 tests` against a real 592. Replaced with
`# the full suite`, so it cannot go stale again. This is **not** one of S-24's six stale
README claims (I checked all six in `audit_literature.md`: the "four of the five material
values" count, the Cogan Table 2 attribution, the Merrill water-window citation, the "gap is
not reconciled" sentence, the omitted primary-sources list, and the 0.35 vs 0.419 S/m
conductivity). See §4.

---

## 3. C0.5 — `build: repair and gate the mistakes ledger`

**Commit `1ef63f8` · 604 tests** (592 → 604)

### Failing first

```
FAILED tests/test_build_gates.py::TestLedgerGate::test_the_gate_script_is_committed
FAILED tests/test_build_gates.py::TestLedgerGate::test_the_committed_ledger_and_plan_pass
FAILED tests/test_build_gates.py::TestLedgerGate::test_the_committed_ledger_has_uniform_rows
FAILED tests/test_build_gates.py::TestLedgerGate::test_an_unescaped_pipe_is_caught
FAILED tests/test_build_gates.py::TestLedgerGate::test_an_entry_missing_from_the_plan_is_caught
FAILED tests/test_build_gates.py::TestLedgerGate::test_a_sub_lettered_plan_row_counts_as_coverage
FAILED tests/test_build_gates.py::TestLedgerGate::test_a_plan_defect_row_needs_no_plan_coverage
FAILED tests/test_build_gates.py::TestLedgerGate::test_a_fabricated_commit_hash_is_caught
FAILED tests/test_build_gates.py::TestLedgerGate::test_a_real_commit_hash_is_accepted
FAILED tests/test_build_gates.py::TestLedgerGate::test_a_duplicated_entry_number_is_caught
FAILED tests/test_build_gates.py::TestLedgerGate::test_a_gap_in_the_numbering_is_caught
11 failed, 1 passed, 22 deselected in 1.94s
```

The stronger evidence is that the finished gate fires on the **pre-repair ledger**, taken
straight out of git at `ef02355`, and names exactly the two rows the plan says were broken:

```
$ git show ef02355:CODE_MISTAKES_LOG.md > /tmp/ledger_before.md
$ python scripts/ledger_check.py --ledger /tmp/ledger_before.md
FAIL: line 20: 11 fields against the header's 7 -- an unescaped '|' in the cell text splits the row (write it as '\|'): '8'
FAIL: line 58:  9 fields against the header's 7 -- an unescaped '|' in the cell text splits the row (write it as '\|'): '46'
```

### Passing after

```
604 passed in 47.10s
ruff: All checks passed!
mypy: Success: no issues found in 52 source files
$ python scripts/ledger_check.py
OK: 83 entries, 7 fields each, every package defect scheduled in the plan
```

### Two things the plan gets slightly differently

**Field counts.** §5.0 says rows 8 and 46 "parse to 13 and 11 fields against the table's 9".
The header has **7** columns (`# | Date | Severity | File:line | Defect | Fix | Commit`) and
the broken rows have **11** and **9**. The plan's figures are the same rows counted with a
bare `line.split("|")`, which yields two extra empty tokens from the leading and trailing
pipes: 7+2=9, 11+2=13, 9+2=11. Same rows, same defect, different tokenisation — not an error
in the plan, but the gate reports the real column counts, and my test asserts
`"11 fields against the header's 7"` with a comment recording the reconciliation so nobody
re-derives it later.

**How they were repaired.** The plan says "repaired"; the mechanism was *rewording*, not
escaping — `git diff ef02355 7a0515b` shows `min(|cathodic|,|anodic|)` became
`min(abs cathodic, abs anodic)`. There is not a single `\|` in the file. Both are valid
repairs and the parser handles either (`\|` is treated as an escaped pipe and does not
split a cell), but it is worth knowing that the escaping convention is not actually in use
in this file yet.

### The §9 assertion, and the exemption it needs

The brief says "asserting every entry number appears in FIX_PLAN_v2.md section 9". Taken
literally that assertion **fails today**: §9 enumerates 1–78 across 114 rows, and the ledger
has 83 entries. Missing: 79, 80, 81, 82, 83.

That is not an omission. The plan's own preamble says "Ledger entries 79–83 are v1's own
defects" and "This plan sequences the 78 **package** defects"; §9's coverage line says
"78 entries, 114 rows". Those five are defects in FIX_PLAN v1, disposed of in §1b's blocker
table, and by construction have no row in a table that maps package defects to package
commits.

Rather than hardcode `{79, 80, 81, 82, 83}` — which would need editing every time a plan
defect is found — the gate derives the exemption from the ledger's own data: those five
rows carry `(plan defect)` in the Severity column, where every other row carries
CRITICAL/HIGH/MEDIUM/LOW. So the rule is:

> every entry whose severity is not `(plan defect)` must appear in §9, as a plain number or
> under a sub-finding label (`61/M3`, `67(a)`, `78/S-24`)

Two tests pin both halves: `test_a_sub_lettered_plan_row_counts_as_coverage` and
`test_a_plan_defect_row_needs_no_plan_coverage`. If you would rather §9 carry explicit rows
for 79–83, that is a plan edit and the gate will then require them with no code change.

### The other three assertions

- **Uniform field count** — the recurrence guard for the original defect.
- **Unique and contiguous numbering from 1** — a gap means a row was deleted, which the
  ledger's own header forbids ("Append new entries; never delete"). Currently 1–83, no gaps,
  no duplicates.
- **Recorded commit ids exist** — any cell matching `[0-9a-f]{7,40}` is checked with
  `git cat-file -e <sha>^{commit}`. Vacuous today (every row says `pending`), and it is the
  assertion that matters most from C1.1 onward: it makes it impossible for the ledger to
  claim a fix landed in a commit that was never made. Tested both ways — 40 zeros fails,
  the real `HEAD` passes.

### `FIX_PLAN_v2.md` is now tracked

It was untracked at the start of the phase. The §9 assertion reads it, so without it in git
the CI job has no input and would exit 2. I committed it as part of C0.5 and said so in the
commit message. Flagging in case another agent intended to own that file — if so, the
commit can be reworded but the file has to be tracked for the gate to run.

---

## 4. C0.6 — `test: add tests/oracles/ — independent expected-value generators`

**Commit `7e40799` · 627 tests** (604 → 627)

### Failing first

```
tests/test_oracles.py:20: in <module>
    from oracles import disc_field, drift, fail_ceiling, fd_band
E   ModuleNotFoundError: No module named 'oracles'
=========================== short test summary info ============================
ERROR tests/test_oracles.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.23s
```

(Captured by moving `tests/oracles` aside and re-running, so the pre-commit state is on the
record rather than merely asserted.)

### Passing after

```
$ pytest -q tests/test_oracles.py
23 passed in 0.90s

$ pytest -q
627 passed in 47.80s
ruff: All checks passed!
mypy: Success: no issues found in 52 source files
```

### (a) `fail_ceiling` — binary search over `assess().failed`

Returns **exactly `20.0`** on the worked example, asserted with `==`, not `approx`. The
constant is pinned independently:

```python
threshold_nC = cogan2016.MICROELECTRODE_DAMAGE_THRESHOLD_NC_PER_PHASE   # 4.0
expected_uA = (threshold_nC * 1e-9) / (PULSE_WIDTH_US * 1e-6) * 1e6     # 20.0 exactly
```

4 nC per phase over a 200 µs pulse is 4e-9 C / 200e-6 s = 2e-5 A. The bisection narrows
until the bracket is one ulp wide, so it lands on the exact boundary float rather than near
it, and `brackets_the_ceiling` asserts the answer passes while `nextafter(answer, inf)`
fails — because a finiteness assertion would admit the naive `headroom/excursion` reading
of the water-window margin, which is −21.095 µA on this very case.

Three things make it non-tautological, and each is tested:

- it reads only whether `assess().failed` is empty;
- a structural test reads the module's own source (docstring stripped) and asserts it never
  names `limiting_current_uA`, `limiting_mechanism` or `.margin`;
- it currently **disagrees** with the package by 7.0686×, which no restatement of the code
  could do.

`rebuild_at` names all twelve `SafetyCalculator` construction arguments explicitly rather
than copying, so a field added in a later phase surfaces as a missing-argument error rather
than as a silently wrong verdict.

Case correction, for the record: the brief said "DiscElectrode 330/270 um Pt ring". The
plan's case, and the worked example's, is `RingElectrode(330, 270, "Pt")` at
`StimProtocol(80, 200, 130, 1)`, `compliance_V=10.0`. Confirmed: limiting current
141.37166941154072 µA, failures `{Microelectrode charge/phase, Chronic degradation}`.

One implementation constraint worth recording: **the bisection cannot start at zero.**
`StimProtocol.__post_init__` raises `ValueError: current_uA must be finite and > 0, got 0.0`.
The bracket starts at 1e-12 µA and a protocol that already FAILs there returns `0.0`.

### (b) `disc_surface_potential_V` — the exact half-space disc

`V(r) = (2/π)·I·R·arcsin(a/r)`. At 250 µm radius, 100 µA, σ = 0.35, R = 2857.142857 Ω:

| quantity | value | assertion |
|---|---|---|
| `V(a)` | 0.28571428571428575 V | `== I*R` **bit-equal**, and `285.714286 mV` to 5e-7 |
| `V_today(100a)/V_exact` | 0.499992 | `abs=5e-7` |
| `V_2π(100a)/V_exact` | 0.999983 | `abs=5e-7` |

Reproduces your main-thread verification to the digit. A separate test drives the package's
own `field.potential_V` and records the ratio as 0.5 — so the oracle demonstrably measures
the defect rather than agreeing with it. The docstring states why the rim is *not* pinned to
the point source: the legitimate disc-vs-sphere ratio there is exactly π/2, and demanding
1.0000 would force `1/(4σa) → 1/(2πσa)`, a 57 % error manufactured by a test.

### (c) `drift_time_s` — pulse-by-pulse accumulation

Audit case: `CylindricalBandElectrode(1270, 1500, 'PtIr')`, 3000 µA / 90 µs / 130 Hz
monophasic, area π·0.127·0.15 = 0.0598473 cm², 250 µF/cm², 0.6 V window.

```
duty 90e-6 * 130            = 0.0117
net DC 3000 * 0.0117        = 35.1 uA
J_dc 35.1 / 0.0598473       = 586.5 uA/cm^2
dV/dt 586.5e-6 / 250e-6     = 2.346 V/s
closed form 0.6 / 2.346     = 0.25576 s      -> asserted 0.2558 (abs=5e-5)
pulse loop                  = 34 pulses / 130 Hz = 0.26154 s
difference                  = 0.00577 s  <  one pulse 0.00769 s
```

A test reads the loop's own source between its `def` and the next one and asserts the string
`closed_form` does not appear in it, so the "independent route" claim is enforced rather
than promised. Another records that the package currently returns a water-window **PASS**
for this protocol while the interface leaves the window in under a quarter of a second.

### (d) `FD_BAND_REFERENCE` — converged Laplace solve

I wrote `scripts/fd_band_reference.py` from the physics — axisymmetric finite volume on a
geometric (r, z) grid, band at V = 1, insulating shaft above and below, symmetry at the
midplane, far-field Dirichlet, current taken as the flux across the first radial face. It
imports nothing from `neurostim`. Output at σ = 0.35 S/m, d = 1270 µm, 500×500, domain 2000×:

```
aspect h/d   h (um)   FD (ohm)  eq-sphere    eq-disc
     0.200      254      739.9      800.6     1257.6
     0.390      495      559.8      573.3      900.6
     0.500      635      502.2      506.4      795.4
     1.000     1270      363.7      358.1      562.4
     1.181     1500      335.1      329.5      517.5
     2.000     2540      255.0      253.2      397.7
     4.000     5080      172.1      179.0      281.2
    10.000    12700       96.3      113.2      177.9
```

**Every row of the plan's §2 D4 table, to the digit, including both comparison columns.**
Clinical contact 335.1 Ω; equal-area sphere 329.5 Ω (−1.67 %); equal-area disc 517.5 Ω
(+54.5 %). The rejected `ln(2L/r)/(2πσL)` form is asserted negative at aspect 0.2
(−399.5 Ω) directly from the formula written out in the test.

**One honest amendment to the plan.** §2 D4 describes the solve as "converged to 0.1 %". My
refinement study does not support that figure:

```
clinical contact, 1500 um band on a 1270 um shaft
      grid   domain    R (ohm)
  300x300       300     334.70
  300x300      2000     336.76
  500x500      1000     334.56
  500x500      2000     335.06
  700x700      2000     334.04
  700x700      3000     334.26
```

Spread 334.0–336.8, i.e. **335 ± 1.5 Ω, about ±0.45 %**. I recorded ±0.45 % in the oracle's
docstring rather than repeating 0.1 %. Nothing the table is used for changes: the smallest
comparison it settles is the equal-area sphere at −1.7 %, and the ones that matter are
+54 % and +40 %. But a reviewer who re-runs the solve should find the stated tolerance true,
so the number is the measured one.

A coarse re-solve (200×200, domain 500×, ~1.4 s) runs inside the test suite at `rel=0.02`,
so the frozen table is falsifiable rather than a magic number.

---

## 5. Other departures from the plan

Beyond the two C0.3 departures already delivered (not suppressing the date, and scoping
reportlab's `invariant`) and the C0.4 `.gitignore` choice above:

1. **`scripts/branch_floor.py` gates on the total only; the per-module floor ships disabled.**
   §3 specifies "exit floor 80 %, with a 60 % per-module floor for every module with ≥ 4
   branch points". At the 48.30 % baseline, enabling the per-module floor would fail
   immediately (`vta.py` 0/12, `fem.py` 2/17, `current_density.py` 1/6). `--module-min` and
   `--module-min-points` are implemented and tested both ways; CI passes neither. Phase 7
   turns them on by editing one CI line, with no code change.

2. **Python 3.14 added to the trove classifiers as well as the CI matrix.** The plan's C0.1
   subject says "add Python 3.14 to CI". Audit T24 says "add `"3.14"` to the matrix **and the
   classifier list**", and a classifier list that stops at 3.13 while CI tests 3.14 is exactly
   the doc drift the mandate forbids. One line in `pyproject.toml`.

3. **C0.2 closes ledger 65 across four modules, not only `units.py`.** The plan's C0.2 row
   describes `tests/test_units.py`; §9 assigns ledger 65 wholly to C0.2, and 65 is about four
   surviving mutants of which only the SI identities live in `units.py`. The file therefore
   also pins `charge.cic_max_current_uA` (C4), `vta.activated_volume_mm3` (M4, M5) and
   `strength_duration.weiss_threshold_charge_uC` (M10) by magnitude. Tests only.

4. **No append to `_conversation_history.md`.** It is tracked, several agents are running in
   parallel, and touching it would leave the tree dirty going into Phase 1. Flagged rather
   than silently skipped; your call.

---

## 6. Other defects found that neither the plan nor the ledger names

Beyond entry A in §1.

### Proposed ledger entry B — README quick-start transcript

| field | value |
|---|---|
| severity | **HIGH** |
| file:line | `README.md:38-47` (transcript), `README.md:182` (test count) |
| defect | The quick-start transcript, presented as the output of `print(calc.describe())`, was stale by a release: 5 checks against the package's 9; `Limiting current: 70.69 uA` against 141.4 (2.00× understated); Shannon shown PASS where it is `NOT_EVALUATED`; charge injection shown FAIL where it is CAUTION; water window shown "leaves the window by 2.23 V" where it has 0.37 V headroom; and the two checks that actually FAIL — `Microelectrode charge/phase` and `Chronic degradation` — absent entirely. It is the package's headline output and the first thing a reviewer checks. Separately `README:182` claimed "# 220 tests" against 592. |
| fix | Block regenerated by `scripts/regenerate_example_output.py` between HTML markers, every line asserted verbatim against `describe()`, headline count asserted equal to `len(assessment.checks)`, `--check` gated in CI. Test count literal removed. |
| commit | `f5d8225` |

Not covered by 74 (PEDOT row), 76 (the two inert provenance flags), or 78/S-24 — I read all
six of S-24's claims in `audit_literature.md` and the transcript is not among them.
Severity HIGH by the ledger's own rule: it is doc drift on a user-facing safety number, the
same class as 74 and 76.

### Not a defect, but not recorded anywhere either

- **`save_publication` writes uncompressed TIFF.** 47 MB for one four-panel figure at 600 dpi.
  `pil_kwargs={"compression": "tiff_lzw"}` would cut it roughly tenfold at no quality cost.
  It changes the bytes of a package output, so it is out of scope for Phase 0. Worth a LOW
  entry if you want it fixed; ledger 61's io-gui M-series mentions the file size but not the
  compression setting.
- **`dataclasses` on Python 3.14 requires the module to be in `sys.modules` before
  `exec_module`.** Loading a `scripts/*.py` file by spec without registering it first raises
  `AttributeError: 'NoneType' object has no attribute '__dict__'` from `dataclasses.py:814`
  the moment the module defines a dataclass. This bit the test loader, not the package, and
  is fixed in `tests/test_build_gates.py`. Recording it because the same pattern will recur
  in any later commit that loads a script by path.

---

## 7. Phase 1 — what I now believe is wrong, having touched the code

### 7.1 BLOCKER — C1.4's pin is false whenever `Charge balance` FAILs

§5.1 C1.4 specifies:

> **T1** (rewritten) — `a.limiting_current_uA == approx(oracles.fail_ceiling(calc), rel=1e-9)`

and §2 D3 specifies two things that are not equivalent:

> (i) "**Limiting current** means the highest amplitude at which no check FAILs"
> (ii) "`LIMIT_BEARING` is defined: Shannon, Charge injection, Current density,
> Microelectrode charge/phase, Compliance, Chronic degradation, Water window — seven.
> Validated envelope and **Charge balance** impose no current ceiling and stay `inf`."

(i) is `fail_ceiling(calc)`. (ii) makes the headline `min` over seven checks. They coincide
only if every FAIL-capable check is limit-bearing. **`Charge balance` can FAIL and is not
limit-bearing**, and `audit_tests.md` T8 lists it among the six reachable FAIL states.

Measured just now, on today's code, using the C0.6 oracle:

```python
mono = SafetyCalculator(CylindricalBandElectrode(1270., 1500., "PtIr"),
                        StimProtocol(3000., 90., 130., 1., waveform="monophasic"),
                        compliance_V=10.0)

monophasic failed checks:     ['Charge balance']
monophasic limiting_current_uA: 15285.509415880857
monophasic fail_ceiling oracle: 0.0
```

`Charge balance` FAILs at *every* amplitude for a monophasic protocol, because it is a
property of the waveform, not of the amplitude. So `fail_ceiling` correctly returns 0.0
while `min` over the seven limit-bearing checks returns 15285.5 µA. `15285.5 ==
approx(0.0, rel=1e-9)` is false, and no amount of repair in Phase 1 makes it true.

Today this only bites monophasic protocols, which are a small corner. **C2.1 and C2.3 make it
general**: once `charge_recovery_ratio` makes imbalance expressible, the revived FAIL branch
reaches ordinary biphasic protocols too, and any test parametrised over recovery ratios will
hit it.

Three ways out, in my order of preference:

1. **Add `Charge balance` to `LIMIT_BEARING`** with a margin derived from the C2.3 drift
   model — which the plan already builds, and which does give imbalance an amplitude
   dependence (drift time falls as current rises). D6 says "One mechanism, two consumers";
   this makes it three, consistently. `Validated envelope` genuinely imposes no ceiling and
   stays out, so the equivalence becomes exact rather than approximate.
2. Restate D3 (i) as "the highest amplitude at which no *limit-bearing* check FAILs" and
   scope T1 to protocols with no non-limit-bearing failure, asserting the exclusion
   explicitly so it is visible rather than implicit.
3. Have `limiting_current_uA` return 0.0 (or raise) whenever any check FAILs at every
   amplitude. Most conservative and most disruptive; it changes the headline for every
   monophasic protocol.

I did not choose. Option 1 changes D3's LIMIT_BEARING list, which is a §2 convention and
therefore yours.

### 7.2 MAJOR — C1.3 calls an oracle API that C0.6 does not define

§5.1 C1.3's test is:

```
for each of the seven LIMIT_BEARING checks,
  c.margin * p.current_uA == approx(oracles.fail_ceiling_for(check), rel=1e-9)
```

C0.6's row specifies only `fail_ceiling(calc)` — the whole-assessment ceiling — and that is
what I built. `fail_ceiling_for(check)` is a **per-check** ceiling: the highest amplitude at
which *that named check* is not in a FAIL state, with the other eight ignored. It does not
exist.

This is a gap, not an error: the shape is a one-function addition to
`tests/oracles/fail_ceiling.py`, reusing `rebuild_at` and bisecting on

```python
lambda I: next(c for c in rebuild_at(calc, I).assess().checks
               if c.name == name).status is not Status.FAIL
```

I did not add it in Phase 0 because the plan's C0.6 row does not list it and because its
correctness argument depends on D3's `kind` and `provisional` fields, which land in C1.3
itself. Flagging so C1.3 does not start by discovering a missing import. Say the word and I
will add it as a C0.7, or fold it into C1.3.

Related, and worth deciding at the same time: `c.margin * p.current_uA` is only the FAIL
ceiling if `margin` is defined against FAIL rather than CAUTION. D3 says it is. Today's
values are consistent with that on the worked example — `Microelectrode charge/phase` has
`margin = 0.25` and `0.25 × 80 = 20.0`, exactly the oracle's answer — so the definition is
already right for at least one check and C1.3 is extending it to the other six.

### 7.3 MINOR — C1.7's construction-time validation will constrain the oracles

C1.7 adds validation at construction: non-finite settings raise, and
`resting_potential_V` is validated against the material's window. Both oracles that rebuild
a calculator at a probe amplitude (`fail_ceiling`, and `fail_ceiling_for` when it exists)
call `SafetyCalculator(...)` up to ~60 times per search across a 1e-12 … 1e6 µA bracket.

Nothing in C1.7 as described validates `current_uA`, so I expect no breakage — but if the
validation grows to cover amplitude (say, a maximum), the bisection's upper bracket will
start raising rather than returning a FAIL, and `fail_ceiling` will crash instead of
returning `inf`. A one-line guard in the oracle handles it; it needs to be added *with*
C1.7, not discovered by it.

### 7.4 Checks on Phase 1 that came out clean

- **C1.1's T17** — `SafetyCalculator(DiscElectrode(2000., "SIROF"), StimProtocol(20,400,50,3600)).assess().status is Status.PASS`. Consistent with what I saw: `Status.NOT_EVALUATED` is returned for macroelectrodes today and the rank order is the cause.
- **C1.2's T2a** — the float-boundary claim is testable exactly as written; `math.nextafter` behaves as the plan assumes on this interpreter, and C0.6 already uses that pattern successfully in `brackets_the_ceiling`.
- **C1.5's T3** — `DiscElectrode(40., "PEDOT")` reporting a Shannon-attributed limit while Shannon is `NOT_EVALUATED` is the same defect shape I saw on the worked example, where the mechanism string reads "Pt charge-injection limit" while two other checks are the ones actually failing. Plausible as stated.
- **C1.6's T16** — the worked example's interval is `141.4–212.1 µA` against a point estimate that C1.4 moves to 20.0, so containment fails after C1.4 exactly as the plan predicts. Confirmed by reading the transcript this phase generated.
