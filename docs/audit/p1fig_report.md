# C5.1 pulled forward — final report

Repo: .
Base: 505aea6 (the main thread added 149f229 `docs: session history through Phase 1`
— `_conversation_history.md` only — between my read and my first commit; my commits sit
on top of it and I did not touch that file).

## Commits

| hash | subject |
|---|---|
| fa01e26 | `fix(viz): forward the calculator's settings AND its candidate set to every panel` |
| 36d3d6b | `docs(ledger): record the commit that closed 48` |

Gates after **each** commit: pytest **780 passed** (770 + 10 new); ruff clean;
mypy clean (53 files); `scripts/ledger_check.py` OK (87 entries).
`scripts/regenerate_example_output.py --check` OK — no committed number moved
(`example_output/` is gitignored; the tracked artifact is the README transcript, which
renders `describe()`, untouched here). Working tree clean.

## What was verified broken first (main-thread repro, re-run here)

| case | assessment | figure (before) |
|---|---|---|
| ring 330/270 Pt, 80 uA/200 us/130 Hz, 10 V | 20.0 uA (Microelectrode charge/phase) | `binding limit 141.3 uA` |
| band 1270/1500 Pt, 3000 uA/200 us, k=1.2, sigma=0.10, 10 V | 4869.590378911605 uA (Shannon) | `binding limit 6878 uA`; drawn Shannon 6878.479237146387 = the k=1.5 value, drawn compliance 18836.5 vs true 5480.42 |
| monophasic band 1270/1500 PtIr, 3000 uA/90 us | refuses: "no amplitude is safe: Charge balance FAILs at every amplitude" | `binding limit 1.528e+04 uA` |

## What landed

1. **Candidate set.** `current_limit_sweep` no longer computes
   `min(shannon, cic, compliance)`. It runs `assess()` once and draws every
   `LIMIT_BEARING` check that ran, at its own `ceiling_uA`, labelled with the check's
   name; the red rule and the annotation come from `limiting_current_uA` and
   `limiting_mechanism`. Ceilings are constant in the requested amplitude (verified to
   the last bit over 25 amplitudes x 4 configurations), so the 120-iteration rebuild loop
   is gone.
2. **Settings.** `safety_summary` forwards every construction setting to panel (b) and
   `tissue_conductivity_S_per_m` to panel (d) (which drew the field at the library 0.35
   S/m regardless — same defect class, same function, so it landed here).
   `viz.plots._calculator_settings` reads the `SafetyCalculator.__init__` signature
   rather than a list, and raises if a setting is not stored under its own name.
3. **Refusal (ledger 84).** When `unsafe_at_any_amplitude` is non-empty the rule, the
   shaded pass region and the number are replaced by the sentence naming the check. The
   per-check ceiling curves stay — each is that check's own honest limit and carries its
   name.

## Tests

`tests/test_figure_surface.py`, 10 tests, **all 10 red before the fix**
(`scratchpad/red_c51.txt`), all green after (`scratchpad/green_c51.txt`).

- expected values from `tests/oracles/fail_ceiling` (binary search over `assess().failed`)
  and hand arithmetic quoted in each test: 4 nC/phase / 200 us = 20 uA;
  `sqrt(A*10**1.2)/200us` = 4869.590378911605 uA.
- fixtures off-default (`k=1.2`, `sigma=0.10`) — a `k=1.5` fixture passes even unfixed.
- forwarding pinned **independently** of the minimum: one test asserts each drawn
  per-check curve equals that check's own ceiling and that 6878.479237146387 appears
  nowhere.
- the refusal is asserted in both directions in one test (one rule on the worked example,
  zero on the monophasic band), so a panel that stopped drawing rules fails.
- every test carries a one-line "not tautological because" in its docstring.

**One existing test changed**: `TestEveryRenderSiteFloors::test_the_figure_annotation_floors`
in `tests/test_verdict_core.py` (part of the diff under concurrent review). It asserted
`"141.3"`, which this commit makes 20.00 — where flooring and rounding agree, so the site
would assert nothing. Repointed to `DiscElectrode(100,"Pt")` at 100 us, which binds at
39.26990816987241 uA (12.5*pi): `:.4g` gives "39.27" (above the ceiling — the ledger 49
defect), `format_limit` gives "39.26". Both are asserted.

## Ledger

Row **48** (CRITICAL): Fix column written in fa01e26 with `see C5.1`; Commit column
backfilled to `fa01e26` in 36d3d6b — the repo's established convention (e704d8a wrote
`see C1.5`, 2d63aa2 backfilled it). No other row's Commit column touched. Row 84 is
already closed at e704d8a and its Fix text ("The figure annotation follows at C5.1") is
now true; I left the row alone rather than editing a closed entry.

## Plan section 9 mapping — rows now done

- **`| 48 | CRIT | PARTIAL | C5.1 | candidate set rebuilt from the assessment |`** → done, fa01e26.
- **§1b blocker B2** (`viz.current_limit_sweep` keeps the three-check minimum) → resolved.
- **§5.5 row C5.1** → landed, out of order, as the first commit after the Phase 1 tail.
- **§6 blast radius, row `C1.3 [+]`** (`figure annotation (viz/plots.py:211, :.3g)` →
  "141.3, then 20.00 after C5.1") → the second half has now happened.
- **§5.1 row C1.5**, scope note "the figure annotation follows at C5.1" → satisfied.
- Not closed, and not claimed: everything else in §5.5 (C5.2–C5.11) is untouched.

## Deliberately not done

The figure does **not** render `limits_incomplete`. Fix plan D3 lists that flag's surfaces
as `describe()`, `report_to_json`, the PDF and the GUI; the figure is not among them, and
the note does not fit an 89 mm panel at 6 pt. On the worked example the flag is True
(Shannon is NOT_EVALUATED), so a reader of panel (b) alone is not told the candidate set
was short one check. If that should change, it wants its own commit and its own layout
decision.

## Artifacts in scratchpad
`red_c51.txt`, `green_c51.txt`, `full2.txt`, `summary_ring.png`, `sweep_mono.png`
(rendered panels, eyeballed for legibility — the legend gained a white background because
seven flat lines span the full width and an unframed legend sat illegibly on top of four
of them).
