# Code mistakes log — neurostim-safety

Running record of every defect found and what was done about it.
Read this before writing code in this repo. Append new entries; never delete.

Severity: CRITICAL (wrong number reaches a user-facing safety verdict) /
HIGH (wrong provenance, silent failure, unsound uncertainty) /
MEDIUM (doc drift, weak test) / LOW (cosmetic).

| # | Date | Severity | File:line | Defect | Fix | Commit |
|---|------|----------|-----------|--------|-----|--------|
| — | 2026-09-22 | — | — | Audit opened at baseline bfca95d | — | — |
| 1 | 2026-09-22 | CRITICAL | safety/assessment.py:119-131,158-167 | Limiting current = min(Shannon, charge-injection, compliance) only. Microelectrode 4 nC/phase, chronic degradation, Butterwick current-density and water-window limits are computed but excluded from the candidate set. ~12.5x overstatement of max safe current. | pending | pending |
| 2 | 2026-09-22 | HIGH | safety/assessment.py:733-791 | Monophasic protocols receive biphasic-measured limits unchanged. 3000 uA/90 us/130 Hz monophasic reports water-window PASS with 0.58 V headroom; real DC drift exits the window in 0.256 s. | pending | pending |
| 3 | 2026-09-22 | HIGH | protocol.py:117-121,160-171 | Return-phase current is derived as current_uA/return_phase_ratio, so an unbalanced biphasic pulse cannot be expressed. 150 (I,W,r) combinations produce zero imbalance. The charge-balance FAIL branch (assessment.py:567) and net_dc_current_uA are dead code for every biphasic protocol. | pending | pending |
| 4 | 2026-09-22 | HIGH | safety/current_density.py:181; safety/compliance.py:180-196 | Only the leading-phase current is evaluated. With return_phase_ratio=0.2 the true return phase is 5000 uA, yet verdicts are bit-identical to symmetric: required_V 0.524 V (true ~2.6 V), J_avg 0.0167 A/cm2 (true peak 0.0836). | pending | pending |
| 5 | 2026-09-22 | HIGH | safety/compliance.py:10-21,179-197 | Voltage budget models one interface and one spreading resistance. A two-terminal pair has two of each plus the equilibrium-potential difference. Bipolar DBS 3000 uA: reports 1.571 V vs true ~3.142 V, 2.0x under-report. No mention of counter/return electrode anywhere in the module. | pending | pending |
| 6 | 2026-09-22 | HIGH | safety/envelope.py:251-260 | McCreery 2010 duty cycle is the train on/off schedule; code passes the intra-period current-flowing fraction. McCreery's own fit protocol (400 us, 50 Hz, 7 h) yields duty_cycle 0.04, fold 25x, inside=False, so the "within fitted conditions" branch (assessment.py:351-357) is unreachable for every pulsed protocol, and duty_cycle_note prints a 50%-duty statement for a continuous protocol. | pending | pending |
| 7 | 2026-09-22 | MEDIUM | safety/water_window.py:172-192 | anodic_first defaults False but anodic_first_for_capacitance defaults None, so sign and capacitance can disagree. AIROF at its own CIC (1000 uC/cm2) returns +0.4286 V headroom PASS instead of landing on the edge; excursion understated 3.50x. Packaged assess() passes both and is safe; direct callers of the exported module are not. | pending | pending |
| 8 | 2026-09-22 | MEDIUM | safety/water_window.py:79-87 | min(|cathodic|,|anodic|) is documented as conservative, but the narrower half-window sits in the denominator of C = limit/available_V, so it enlarges C and understates the excursion. Anti-conservative. | pending | pending |
