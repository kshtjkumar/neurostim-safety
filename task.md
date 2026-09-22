# neurostim-safety — pre-publication hardening

**Target:** JOSS / SoftwareX submission quality.
**Mandate:** no calculation errors, no silent failures, no unsourced numbers, no doc drift.
**Baseline commit:** bfca95d — 522 tests pass, ruff clean, mypy clean.
**Change policy:** fixes may change reported numbers. Every changed number logged with before/after and its source.

## Phase status

| # | Phase | State |
|---|-------|-------|
| 0 | Git baseline + traceability | DONE (bfca95d) |
| 1 | Parallel read-only audit (6 agents) | DONE - 78 findings |
| 2 | Synthesis + fix plan (delegated planner) | DONE - docs/audit/FIX_PLAN.md, 41 commits, 7 conventions |
| 3 | Adversarial re-plan / criticism | DONE - 13 blockers found, FIX_PLAN_v2.md |
| 4 | Execution, fix by fix, one commit each | Phase 0 DONE (6 commits, 522->627 tests); Phase 1 blocked on plan amendment |
| 5 | Independent re-review of every fix | Phase 0 review RUNNING |
| 6 | Test hardening (negative + property + mutation) | PENDING |
| 7 | Docs, CI, packaging to JOSS bar | PENDING |
| 8 | Final verification + provenance strict pass | PENDING |

## Phase 1 — audit agents

| Agent | Scope | State |
|-------|-------|-------|
| audit-literature | every constant vs its primary-source PDF; units; DOIs; provenance claims | DONE |
| audit-safety-math | shannon, charge, water window, compliance, current density, assessment, limiting current | DONE |
| audit-models | field, Pennes thermal, strength-duration, VTA; Elwassif 0.8 K gap: BUG or SCOPE | DONE |
| audit-geometry | areas, access resistance, arrays, units, interval arithmetic soundness | DONE |
| audit-io-gui | report PDF, batch CSV, FEM import, figures, GUI staleness, silent failures | DONE |
| audit-tests | tautologies, coverage, missing negative tests, mutation survival, CI | DONE |

## Known before audit
- README claims "220 tests"; actual count is 522. Doc drift confirmed.
- Provenance audit reports 2 open gaps: TIROF pulse width unknown, Ta2O5 water window absent.
- README admits an unreconciled thermal gap vs Elwassif 2006 (~0.8 K FEM vs millikelvin here).
- No CONTRIBUTING, no code of conduct, no archived release DOI — all required for JOSS.

## Findings ledger
78 entries in CODE_MISTAKES_LOG.md. Full reports with executed reproductions in docs/audit/.

| Severity | Count |
|----------|-------|
| CRITICAL | 3 |
| HIGH | 26 |
| MEDIUM | 28 |
| LOW | 21 |

Verified CORRECT and not to be touched: all 12 geometry area formulas (machine precision);
the Shannon identity and per-phase convention; the disc primary current distribution;
input validation across the safety core; zero try/except in neurostim/safety/;
~300 literature constants with ZERO unit errors; Pennes reproducing Elwassif's FEM to 1.2%.
