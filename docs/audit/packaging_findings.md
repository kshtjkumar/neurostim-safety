# Packaging / JOSS findings (main thread, independent of audit swarm)

| Sev | Item | Evidence | Fix |
|-----|------|----------|-----|
| CRITICAL | No LICENSE file exists | `ls LICENSE*` -> no matches; pyproject `license={text="MIT"}`, CITATION.cff `license: MIT`, README "MIT." | Add MIT LICENSE with copyright holder + year |
| HIGH | CITATION.cff overclaims validation | CITATION abstract: "Pennes bioheat modelling validated against a published finite element model"; README Known limitations: Elwassif gap "not reconciled" | Reconcile wording once audit-models returns BUG-or-SCOPE verdict |
| HIGH | CITATION.cff placeholders | author "neurostim-safety contributors"; repository-code github.com/example/neurostim-safety; no ORCID; no DOI | Real author, real repo, ORCID, Zenodo DOI |
| HIGH | Provenance gate is non-blocking in CI | .github/workflows/ci.yml literature job runs `python scripts/provenance_audit.py` without --strict; verify_transcriptions labelled informational | Run --strict; make transcription check blocking where papers available |
| MEDIUM | Python 3.14 untested | local venv 3.14.7; CI matrix 3.10-3.13; classifiers stop at 3.13 | Add 3.14 to matrix + classifiers, or declare upper bound |
| MEDIUM | No coverage measurement or gate in CI | no --cov in ci.yml; pytest-cov not in dev extra | Add coverage with branch mode + floor |
| MEDIUM | JOSS required files missing | no paper.md, paper.bib, CONTRIBUTING.md, CODE_OF_CONDUCT.md, docs/ | Author all |
| MEDIUM | README test count stale | README "220 tests"; actual 522 | Fix, and make the count generated not hand-written |
| LOW | No dependency lock for reproducibility | only floor pins (numpy>=1.24 etc.) | Add constraints file for the JOSS-archived release |
