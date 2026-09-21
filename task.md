# neurostim-safety — pre-publication hardening

**Target:** JOSS / SoftwareX submission quality.
**Mandate:** no calculation errors, no silent failures, no unsourced numbers, no doc drift.
**Baseline commit:** bfca95d — 522 tests pass, ruff clean, mypy clean.
**Change policy:** fixes may change reported numbers. Every changed number logged with before/after and its source.

## Phase status

| # | Phase | State |
|---|-------|-------|
| 0 | Git baseline + traceability | DONE (bfca95d) |
| 1 | Parallel read-only audit (6 agents) | RUNNING |
| 2 | Synthesis + fix plan (delegated planner) | PENDING |
| 3 | Adversarial re-plan / criticism | PENDING |
| 4 | Execution, fix by fix, one commit each | PENDING |
| 5 | Independent re-review of every fix | PENDING |
| 6 | Test hardening (negative + property + mutation) | PENDING |
| 7 | Docs, CI, packaging to JOSS bar | PENDING |
| 8 | Final verification + provenance strict pass | PENDING |

## Phase 1 — audit agents

| Agent | Scope | State |
|-------|-------|-------|
| audit-literature | every constant vs its primary-source PDF; units; DOIs; provenance claims | RUNNING |
| audit-safety-math | shannon, charge, water window, compliance, current density, assessment, limiting current | RUNNING |
| audit-models | field, Pennes thermal, strength-duration, VTA; Elwassif 0.8 K gap: BUG or SCOPE | RUNNING |
| audit-geometry | areas, access resistance, arrays, units, interval arithmetic soundness | RUNNING |
| audit-io-gui | report PDF, batch CSV, FEM import, figures, GUI staleness, silent failures | RUNNING |
| audit-tests | tautologies, coverage, missing negative tests, mutation survival, CI | RUNNING |

## Known before audit
- README claims "220 tests"; actual count is 522. Doc drift confirmed.
- Provenance audit reports 2 open gaps: TIROF pulse width unknown, Ta2O5 water window absent.
- README admits an unreconciled thermal gap vs Elwassif 2006 (~0.8 K FEM vs millikelvin here).
- No CONTRIBUTING, no code of conduct, no archived release DOI — all required for JOSS.

## Findings ledger
Populated at the end of Phase 1. See CODE_MISTAKES_LOG.md for the running bug record.
