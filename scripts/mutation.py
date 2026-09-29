#!/usr/bin/env python3
"""Mutation gate: does the test suite notice when the arithmetic is wrong?

Why this script exists
----------------------
The test audit (``docs/audit/audit_tests.md`` §5) ran 42 hand-written mutants against the
suite and 13 survived: every inclusive safety boundary, four dropped unit conversions and
two constants nothing ever varied. Coverage said those lines ran. Only mutation showed that
no test would have failed if they were wrong.

That audit's script lived in a scratch directory that no longer exists, and its report
names only 26 of the 42: the 13 survivors with their mutation, and 13 kills named by a
phrase. Those 26 are re-anchored here as ``NAMED`` and must all be killed. A fixed list can
be satisfied one test per mutant, so there is also a **generated** set: operator and
constant mutations enumerated from the AST of the gated modules and sampled with a fixed
seed. The target is 90 % killed, not 100 %, because a generated set contains
equivalent mutants that no test can kill. Every survivor is listed in the results.

The gate is the measured floor, not the target (ledger 182). The pre-registered official
seed, 20260930, scored 137/160 = 85.6 % at 31a8db4, so ``GENERATED_FLOOR`` is 0.85. The
run first reported 143/160 and the floor was raised to 0.89 on it, but 6 of those kills
were the harness's own tests failing (ledger 190, ``HARNESS_TESTS``); the record is a
full re-run of the same sample on the same code with those tests deselected, and carries
a ``corrections`` field. The floor rises only with a measured score. A score is only a measurement of the suite on a seed that no test was written
against: after tests are written from a sample's survivors, pre-register a new seed in a
commit message before running it.

Anchors, not line numbers
-------------------------
Each named mutant is a verbatim snippet that must occur exactly once in its file, and its
replacement. Line numbers went stale within a phase of the audit; a snippet either still
says what the mutant is about or fails loudly as ``stale``, which the gate counts as a
failure.

How a mutant is run
-------------------
Never in this checkout. Each worker copies the tracked files to a temporary directory and
runs pytest there with ``PYTHONPATH`` pointing at the copy (checked before the run: an
import that resolved to the installed package instead would let every mutant survive).
The copy carries its own copy of ``.git`` so the ledger tests see the real history. Bytecode
is not written, so a mutant and its restoration cannot share a stale ``.pyc``.

A mutant first meets the test files that mention its module, with ``-x``; if they all
pass it meets the whole suite. Any failing test kills it. A run past ``--timeout`` counts
as killed and is marked so.

Usage
-----
::

    python scripts/mutation.py                       # full run, writes the results JSON
    python scripts/mutation.py --list                # print the mutants, run nothing
    python scripts/mutation.py --check-anchors       # every named anchor occurs once
    python scripts/mutation.py --gate RESULTS.json   # exit 1 unless the gate is met

A full run takes about an hour on eight cores. CI runs it on demand and weekly
(``.github/workflows/mutation.yml``), not on every push.
"""

from __future__ import annotations

import argparse
import ast
import datetime as _dt
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RESULTS = REPO_ROOT / "docs" / "audit" / "mutation_results.json"

SEED = 20260930
"""The official seed, pre-registered in 31a8db4 and never tuned against (Phase 8).
20260927, 20260928 and 20260929 were measured first, and tests were then written against
some of their survivors (ledgers 181, 182)."""
GENERATED_COUNT = 160
GENERATED_FLOOR = 0.85
"""The measured floor: 137/160 = 85.6 % on the official seed 20260930 at 31a8db4, from a
full re-run with the harness's own tests deselected. It was set to 0.89 on a first count
of 143/160 that credited 6 kills to those tests (ledger 190), then to 0.86 on a
reconstruction that re-ran only 4 of them; this is the measurement, not a lowering of
one. The target is 0.90 (G2); the gap is ledger 182 and the real survivors are
ledger 188. Seed 20260930 is now used: tests have been written against its survivors, so
the next measurement needs a new seed pre-registered in a commit message."""

SCOPE = (
    "neurostim/safety/*.py",
    "neurostim/units.py",
    "neurostim/protocol.py",
    "neurostim/uncertainty.py",
    "neurostim/models/field.py",
    "neurostim/models/vta.py",
    "neurostim/models/strength_duration.py",
)
"""The modules G2 names. The named set also reaches ``models/thermal.py`` and
``safety/water_window.py`` because the audit's mutants did."""


@dataclass(frozen=True)
class Mutant:
    id: str
    path: str
    anchor: str
    replacement: str
    description: str


def _m(id: str, path: str, anchor: str, replacement: str, description: str) -> Mutant:
    return Mutant(id, path, anchor, replacement, description)


NAMED: tuple[Mutant, ...] = (
    # --- the audit's 13 survivors ---------------------------------------------------
    _m("S3", "neurostim/safety/shannon.py",
       "return self.k_metric <= self.k_threshold",
       "return self.k_metric < self.k_threshold",
       "ShannonResult.passes: the inclusive boundary <= becomes <"),
    _m("C2", "neurostim/safety/charge.py",
       "return self.charge_density_uC_cm2 <= self.cic_limit_uC_cm2",
       "return self.charge_density_uC_cm2 < self.cic_limit_uC_cm2",
       "ChargeResult.passes: the inclusive boundary <= becomes <"),
    _m("C4", "neurostim/safety/charge.py",
       "cic_max_charge_uC(mat, area_cm2, policy, anodic_first) / (pulse_width_us * 1e-6),",
       "cic_max_charge_uC(mat, area_cm2, policy, anodic_first) / (pulse_width_us),",
       "cic_max_current_uA: the us->s conversion is dropped"),
    _m("P1", "neurostim/safety/compliance.py",
       "total_r = access_r + counter_r - mutual_r + lead_resistance_ohm",
       "total_r = access_r + counter_r - mutual_r - lead_resistance_ohm",
       "compliance.evaluate: the lead resistance is subtracted"),
    _m("P3", "neurostim/safety/compliance.py",
       "return self.required_V <= self.available_V",
       "return self.required_V < self.available_V",
       "ComplianceResult.passes: the inclusive boundary <= becomes <"),
    _m("A2", "neurostim/safety/assessment.py",
       "CAUTION_MARGIN = 2.0",
       "CAUTION_MARGIN = 1.0",
       "the CAUTION margin is halved"),
    _m("A3", "neurostim/safety/assessment.py",
       "status = Status.CAUTION if result.headroom_V < 0.1 else Status.PASS",
       "status = Status.CAUTION if result.headroom_V < 0.0 else Status.PASS",
       "water-window CAUTION gate: 0.1 V headroom becomes 0.0"),
    _m("A4", "neurostim/safety/assessment.py",
       "status = Status.CAUTION if result.utilisation > 0.8 else Status.PASS",
       "status = Status.CAUTION if result.utilisation > 2.0 else Status.PASS",
       "compliance CAUTION gate: 0.8 utilisation becomes unreachable 2.0"),
    _m("A5", "neurostim/safety/assessment.py",
       "if charge_density_uC_cm2 > threshold.high_uC_cm2:",
       "if charge_density_uC_cm2 >= threshold.high_uC_cm2:",
       "chronic FAIL: > the high threshold becomes >="),
    _m("M1", "neurostim/models/field.py",
       "result = i_A / (_geometry_factor(electrode) * r_m**2)",
       "result = i_A / (_geometry_factor(electrode) * r_m**3)",
       "field.current_density_A_per_m2: 1/r^2 becomes 1/r^3"),
    _m("M4", "neurostim/models/vta.py",
       "result = (4.0 / 3.0) * math.pi * r_mm**3",
       "result = 4.0 * math.pi * r_mm**3",
       "CurrentDistanceModel.activated_volume_mm3: the 4/3 becomes 4"),
    _m("M5", "neurostim/models/vta.py",
       "r_mm = np.asarray(self.activation_radius_um(current_uA), dtype=float) * 1e-3",
       "r_mm = np.asarray(self.activation_radius_um(current_uA), dtype=float) * 1e-6",
       "CurrentDistanceModel.activated_volume_mm3: um->mm 1e-3 becomes 1e-6"),
    _m("M10", "neurostim/models/strength_duration.py",
       "result = rheobase_uA * (w + chronaxie_us) * 1e-6",
       "result = rheobase_uA * (w + chronaxie_us)",
       "weiss_threshold_charge_uC: the 1e-6 is dropped"),
    # --- the audit's 13 named kills ---------------------------------------------------
    _m("S1", "neurostim/safety/shannon.py",
       "seed = math.sqrt(area_cm2 * 10.0**k)",
       "seed = math.sqrt(area_cm2 * 10.0 ** (2.0 * k))",
       "shannon_max_charge_uC: the exponent 10**k becomes 10**(2k)"),
    _m("S2", "neurostim/safety/shannon.py",
       "return math.log10(charge_per_phase_uC) + math.log10(charge_density)",
       "return math.log10(charge_per_phase_uC) - math.log10(charge_density)",
       "shannon_k: log Q + log D becomes log Q - log D"),
    _m("C1", "neurostim/safety/charge.py",
       'scale = 1e3 if mat.cic.units == "mC/cm2" else 1.0',
       'scale = 1e-3 if mat.cic.units == "mC/cm2" else 1.0',
       "charge.evaluate: the mC/cm^2 -> uC/cm^2 factor is inverted"),
    _m("C3", "neurostim/safety/charge.py",
       "limit = limit / derating",
       "limit = limit * derating",
       "charge.evaluate: the in-vivo derating relaxes instead of tightening"),
    _m("J1", "neurostim/safety/current_density.py",
       "return (current_uA * 1e-6) / area_cm2",
       "return (current_uA * 1e-3) / area_cm2",
       "average_current_density_A_per_cm2: uA->A 1e-6 becomes 1e-3"),
    _m("J2", "neurostim/safety/current_density.py",
       "return 0.5 / math.sqrt(1.0 - fraction_of_radius**2)",
       "return 1.0 / math.sqrt(1.0 - fraction_of_radius**2)",
       "the disc's primary-distribution rim ratio doubles"),
    _m("W1", "neurostim/safety/water_window.py",
       "return limit / available_V",
       "return limit * available_V",
       "effective_capacitance_uF_cm2: limit / V becomes limit * V"),
    _m("W3", "neurostim/safety/water_window.py",
       "sign = 1.0 if anodic_first else -1.0",
       "sign = -1.0 if anodic_first else 1.0",
       "water_window.evaluate: the excursion's sign is reversed"),
    _m("M3", "neurostim/models/field.py",
       "return 2.0 * math.pi",
       "return 1.0 * math.pi",
       "field._geometry_factor: the half-space 2*pi becomes pi"),
    _m("M6", "neurostim/models/thermal.py",
       "result = power_W * decay / (4.0 * math.pi * kappa * np.asarray(r) * surface_factor)",
       "result = power_W * decay / (2.0 * math.pi * kappa * np.asarray(r) * surface_factor)",
       "the Pennes sphere solution's 4*pi*kappa*a becomes 2*pi*kappa*a"),
    _m("M7", "neurostim/models/thermal.py",
       "return (rms_current_uA * 1e-6) ** 2 * resistance_ohm",
       "return (rms_current_uA * 1e-6) * resistance_ohm",
       "joule_power_from_current: I^2 R becomes I R"),
    _m("M8", "neurostim/models/thermal.py",
       "return ml_per_min_per_kg * 1e-6 / 60.0 * tissue_density_kg_per_m3",
       "return ml_per_min_per_kg * 1e-6 * tissue_density_kg_per_m3",
       "perfusion unit conversion: the /60 (per minute -> per second) is dropped"),
    _m("M9", "neurostim/models/strength_duration.py",
       "return membrane_tau_us * math.log(2.0)",
       "return membrane_tau_us / math.log(2.0)",
       "chronaxie from tau: tau * ln 2 becomes tau / ln 2"),
)


# Generated mutants that survive because no test *can* kill them, each with the argument,
# or marked NOT proven where the argument falls short. They still count as survivors in
# the score; the note is so a reader can check the claim.
#
# Keyed by site, not by offset (ledger 182): (path, a fragment of the source line that
# contains the mutated token, the old token, the new one). The token's place in the
# fragment must be the mutant's column, so two comparisons on one line are told apart,
# and an unrelated edit elsewhere in the file does not orphan the note.
JUDGEMENTS: tuple[tuple[str, str, str, str, str], ...] = (
    ("neurostim/models/field.py", "np.isscalar(distance_um) or result.ndim", "or", "and",
     "0-d array arithmetic returns an np.float64, which is a float, so both branches "
     "return a float"),
    ("neurostim/models/strength_duration.py", "s[-1] > IDENTIFIABILITY_RCOND", ">", ">=",
     "differs only when the singular-value ratio equals sqrt(eps) exactly"),
    ("neurostim/models/strength_duration.py", "IDENTIFIABILITY_RCOND * s[0]", "*", "/",
     "NOT proven equivalent: s[0] of the relative-sensitivity Jacobian is of order 1-2, "
     "so dividing instead of multiplying moves the cut by that factor only"),
    ("neurostim/models/strength_duration.py", "max_iter: int = 200", "200", "400",
     "the default iteration cap: accepted fits converge far below 2000 evaluations, so "
     "4000 changes nothing"),
    ("neurostim/models/strength_duration.py", "if slope <= 0", "<=", "<",
     "NOT proven equivalent: differs only for a fitted slope of exactly 0.0; np.polyfit "
     "on 1/W thresholds returns about 4e-15, not 0.0"),
    ("neurostim/models/strength_duration.py", "bounds=([1e-12, 1e-12]", "1e-12", "2e-12",
     "NOT proven equivalent: the curve_fit lower bound binds only for fits that collapse "
     "to zero, which the accepted-fit guards and the identifiability notes refuse or flag"),
    ("neurostim/safety/assessment.py", "area_cm2) >= threshold", ">=", ">",
     "NOT proven equivalent: differs only where the average current density equals the "
     "threshold exactly, one float, which moves the settled ceiling by an ulp"),
    ("neurostim/safety/assessment.py", "< return_comparison.threshold_A_per_cm2", "<", "<=",
     "NOT proven equivalent: the return phase's version of the one-ulp boundary above"),
    ("neurostim/safety/assessment.py", "counter_result is None or self.counter_electrode",
     "or", "and",
     "counter_result is None exactly when counter_electrode is None (both are set "
     "together in assess), so the two conditions always agree"),
    ("neurostim/safety/assessment.py", "Status.FAIL: 3", "3", "6",
     "Status.rank is used only to order statuses (max in _worst), and 6 keeps FAIL "
     "highest"),
    ("neurostim/safety/assessment.py", "scale, area_cm2\n        )\n        <= limit", "<=", "<",
     "NOT proven equivalent: the counter ceiling's predicate at exact equality, a "
     "one-float boundary no test reaches"),
    ("neurostim/safety/charge.py", "pulse_width_us > measured_pw", ">", ">=",
     "differs only at a pulse width equal to the measured one, where the fold is 1 and "
     "no warning (and so no direction) is printed"),
    ("neurostim/safety/charge.py", 'self.medium == "in_vivo" and self.derating_note', "and",
     "or", "in vivo the derating note is always set, and in saline it is always empty, so "
     "the two conditions agree"),
    ("neurostim/safety/compliance.py", "self.return_phase_width_us > 0.0", ">", ">=",
     "the width comparison: a return phase of zero width always carries zero current, so "
     "the current comparison already decides"),
    ("neurostim/safety/compliance.py", "available_V <= (linear * cap", "<=", "<",
     "at equality both branches give cap / active_slope, the same seed"),
    ("neurostim/safety/compliance.py", "return_factor > 0.0 and", ">", ">=",
     "with return_factor 0 the return phase draws no current and "
     "return_required_voltage_V gives 0.0, as the skipped branch does"),
    ("neurostim/safety/compliance.py", "if overshoot > 0.0", ">", ">=",
     "a zero overshoot adds polarisation_V(0) = 0 V on both electrodes"),
    ("neurostim/safety/compliance.py", "if fold > 1.5", ">", ">=",
     "NOT proven equivalent: differs only at a conductivity exactly 1.5x Gabriel's, which "
     "no default reaches"),
    ("neurostim/safety/current_density.py", "and return_phase_width_us > 0.0", ">", ">=",
     "the width comparison, as for compliance.py"),
    ("neurostim/safety/_limits.py", "for places in range(decimals, 18)", "18", "36",
     "the loop returns once the text reads on the right side of the bound, which a "
     "double does within 17 decimals; places 18 and up never run"),
    ("neurostim/safety/_limits.py", "if reach <= 0.0 or", "<=", "<",
     "with reach 0, low = value, and value fails its own check on this path, so both "
     "conditions raise"),
    ("neurostim/safety/shannon.py", "math.ulp(larger) * charge_per_phase_uC", "*", "/",
     "NOT proven equivalent: the plateau is consulted only when floor_to_pass has walked "
     "past its 4-step budget, which no Shannon back-solve reaches in the suite"),
    ("neurostim/safety/shannon.py", "math.log(10.0) / 2.0", "10.0", "20.0",
     "NOT proven equivalent: the same plateau"),
    ("neurostim/safety/shannon.py", "math.log(10.0) / 2.0", "/", "*",
     "NOT proven equivalent: the same plateau"),
    ("neurostim/safety/shannon.py", "math.log(10.0) / 2.0", "2.0", "4.0",
     "NOT proven equivalent: the same plateau (seed 20260930 full re-run, ledger 190)"),
    ("neurostim/safety/shannon.py", "charge_per_phase_uC / area_cm2)),", "/", "*",
     "NOT proven equivalent: the same plateau (its larger-log term)"),
    ("neurostim/safety/shannon.py", "_metric_plateau_uC(max_charge, area_cm2) / (", "/", "*",
     "NOT proven equivalent: the same plateau, for the current back-solve"),
    ("neurostim/safety/water_window.py", "<= CHARGE_BALANCE_REL_TOLERANCE", "<=", "<",
     "NOT proven equivalent: the balance tolerance at exact equality; recovered/leading "
     "lands exactly on 1 +/- CHARGE_BALANCE_REL_TOLERANCE for no protocol the suite "
     "builds"),
    ("neurostim/uncertainty.py", "return cls(mean - k * sd, mean + k * sd)", "+", "-",
     "the non-finite-mean branch: mean +/- k*sd is the same infinity or NaN either way"),
    ("neurostim/uncertainty.py", "return cls(mean - k * sd, mean + k * sd)", "-", "+",
     "the non-finite-mean branch again: sd and k are checked finite above, so k*sd is "
     "finite and mean -/+ k*sd is the same infinity or NaN (seed 20260930 full re-run, "
     "ledger 190)"),
    # Survivors of seed 20260930 (Phase 8, the results of record).
    ("neurostim/models/strength_duration.py",
     "self.chronaxie_ci95_us is None or self.rheobase_se_uA", "or", "and",
     "every path that withholds the interval also withholds the rheobase SE, so the two "
     "are None together"),
    ("neurostim/safety/compliance.py", "and protocol.return_phase_width_us > 0.0", ">", ">=",
     "the width comparison: a zero-width return phase draws no current"),
    ("neurostim/safety/water_window.py", "if available_V <= 0:  # pragma", "<=", "<",
     "unreachable, as its pragma says: every material's window straddles zero"),
    ("neurostim/safety/water_window.py", "net_dc_current_uA >= 0.0 else", ">=", ">",
     "at exactly zero net DC nothing drifts, so which branch the offset is timed on is "
     "never read"),
    ("neurostim/safety/_limits.py", "PLATEAU_ALLOWANCE = 4", "4", "8",
     "NOT proven equivalent: the allowance is read only on the descend-across-plateau "
     "path, which no suite back-solve reaches"),
    ("neurostim/safety/assessment.py", "        <= limit_uC_cm2,\n", "<=", "<",
     "NOT proven equivalent: a one-float boundary of the chronic ceiling's predicate"),
    ("neurostim/safety/compliance.py", "self.utilisation > CAUTION_UTILISATION", ">", ">=",
     "NOT proven equivalent: differs only at exactly 80 % utilisation"),
    ("neurostim/models/vta.py", "PYRAMIDAL_CHRONAXIE_RANGE_MS = (0.1, 0.4)", "0.1", "0.2",
     "REAL gap (ledger 188): the constant is not pinned against Tehovnik et al. 2006 Fig. 1B"),
    ("neurostim/safety/assessment.py", "if drift.train_duty_cycle == 1.0", "==", "!=",
     "REAL gap (ledger 188): the drift summary's train wording is not tested"),
    ("neurostim/safety/assessment.py", "margin=threshold / charge_nC", "/", "*",
     "REAL gap (ledger 188): the microelectrode check's margin value is not tested"),
    ("neurostim/safety/assessment.py", "margin=result.max_current_uA / result.current_uA",
     "/", "*", "REAL gap (ledger 188): the compliance check's margin value is not tested"),
    ("neurostim/safety/current_density.py",
     "self.average_A_per_cm2 / DBS_CLINICAL_REFERENCE_A_PER_CM2", "/", "*",
     "REAL gap (ledger 188): the 'for scale' ratio to the DBS reference is not tested"),
    ("neurostim/safety/envelope.py", "hours = protocol.train_duration_s / 3600.0", "3600.0",
     "7200.0", "REAL gap (ledger 188): the envelope's duration in hours is not tested"),
    ("neurostim/safety/envelope.py", "protocol.train_duty_cycle < 0.95", "<", "<=",
     "REAL gap (ledger 188): the train-duty edge at 0.95 is not tested"),
    ("neurostim/uncertainty.py", "if self.low < 0:\n            raise ValueError(f\"sqrt",
     "<", "<=", "REAL gap (ledger 188): sqrt of an interval starting at 0 is not tested"),
    ("neurostim/units.py", '"nm2": 1e-14', "1e-14", "2e-14",
     "REAL gap (ledger 188): the nm^2 area conversion is not tested"),
)


def judgement(mutant: Mutant, root: Path = REPO_ROOT) -> str:
    """The recorded argument for a generated mutant's survival, or ``"not judged"``."""
    if not mutant.anchor.startswith("@"):
        return "not judged"
    offset, old = mutant.anchor[1:].split(":", 1)
    at = int(offset)
    source = (root / mutant.path).read_text(encoding="utf-8")
    for path, fragment, token, replacement, note in JUDGEMENTS:
        if path != mutant.path or token != old or replacement != mutant.replacement:
            continue
        fragment = fragment.replace("\\n", "\n")
        start = source.find(fragment)
        while start != -1:
            if start + fragment.find(token) == at:
                return note
            start = source.find(fragment, start + 1)
    return "not judged"


# --- generated mutants ------------------------------------------------------------------

_COMPARE_SWAP = {ast.Lt: ("<", "<="), ast.LtE: ("<=", "<"), ast.Gt: (">", ">="),
                 ast.GtE: (">=", ">"), ast.Eq: ("==", "!="), ast.NotEq: ("!=", "==")}
_BINOP_SWAP = {ast.Add: ("+", "-"), ast.Sub: ("-", "+"), ast.Mult: ("*", "/"),
               ast.Div: ("/", "*")}
_BOOL_SWAP = {ast.And: ("and", "or"), ast.Or: ("or", "and")}
_OP_PATTERN = {
    "<": r"(?<![<>=!])<(?![<=])", "<=": r"<=", ">": r"(?<![<>=!-])>(?![>=])", ">=": r">=",
    "==": r"==", "!=": r"!=", "+": r"(?<![+=])\+(?!=)", "-": r"(?<![-=])-(?![=>])",
    "*": r"(?<!\*)\*(?![*=])", "/": r"(?<!/)/(?![/=])", "and": r"\band\b", "or": r"\bor\b",
}


def scope_files(root: Path = REPO_ROOT) -> list[str]:
    files: set[str] = set()
    for pattern in SCOPE:
        files.update(str(p.relative_to(root)) for p in root.glob(pattern))
    return sorted(files)


def _offset(lines: list[str], lineno: int, col: int) -> int:
    """Character offset of an AST position. ``col`` counts UTF-8 bytes, not characters."""
    line = lines[lineno - 1]
    return sum(len(text) for text in lines[: lineno - 1]) + len(
        line.encode("utf-8")[:col].decode("utf-8")
    )


def _docstring_nodes(tree: ast.AST) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list):
            for stmt in body:
                if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
                    ids.add(id(stmt.value))
    return ids


def _in_fstring(tree: ast.AST) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            ids.update(id(n) for n in ast.walk(node))
    return ids


def _is_str(node: ast.AST) -> bool:
    return isinstance(node, ast.JoinedStr) or (
        isinstance(node, ast.Constant) and isinstance(node.value, str)
    )


def _gap_mutation(
    path: str, source: str, lines: list[str], left: ast.expr, right: ast.expr,
    old: str, new: str, kind: str,
) -> Mutant | None:
    start = _offset(lines, left.end_lineno or left.lineno, left.end_col_offset or 0)
    end = _offset(lines, right.lineno, right.col_offset)
    gap = source[start:end]
    if "#" in gap:
        return None
    found = list(re.finditer(_OP_PATTERN[old], gap))
    if len(found) != 1:
        return None
    at = start + found[0].start()
    line = source.count("\n", 0, at) + 1
    return Mutant(
        f"G:{path}:{line}:{at}", path, f"@{at}:{old}", new,
        f"{kind} {old} -> {new} at line {line}",
    )


def enumerate_sites(root: Path = REPO_ROOT) -> list[Mutant]:
    """Every generated mutant over the scope, in a fixed order. Offsets, not text."""
    sites: list[Mutant] = []
    for path in scope_files(root):
        source = (root / path).read_text(encoding="utf-8")
        lines = source.splitlines(keepends=True)
        tree = ast.parse(source)
        skip = _docstring_nodes(tree) | _in_fstring(tree)
        for node in ast.walk(tree):
            if id(node) in skip:
                continue
            mutant: Mutant | None = None
            if isinstance(node, ast.Compare) and len(node.ops) == 1:
                swap = _COMPARE_SWAP.get(type(node.ops[0]))
                if swap:
                    mutant = _gap_mutation(path, source, lines, node.left,
                                           node.comparators[0], *swap, "compare")
            elif isinstance(node, ast.BinOp) and type(node.op) in _BINOP_SWAP:
                if not (_is_str(node.left) or _is_str(node.right)):
                    mutant = _gap_mutation(path, source, lines, node.left, node.right,
                                           *_BINOP_SWAP[type(node.op)], "arithmetic")
            elif isinstance(node, ast.BoolOp) and len(node.values) == 2:
                mutant = _gap_mutation(path, source, lines, node.values[0], node.values[1],
                                       *_BOOL_SWAP[type(node.op)], "boolean")
            elif (
                isinstance(node, ast.Constant)
                and isinstance(node.value, (int, float))
                and not isinstance(node.value, bool)
                and node.value not in (0, 1)
                and node.end_lineno == node.lineno
            ):
                at = _offset(lines, node.lineno, node.col_offset)
                old = source[at:_offset(lines, node.lineno, node.end_col_offset or 0)]
                mutant = Mutant(
                    f"G:{path}:{node.lineno}:{at}", path, f"@{at}:{old}",
                    repr(node.value * 2), f"constant {old} -> {node.value * 2!r} at line "
                    f"{node.lineno}",
                )
            if mutant is not None:
                sites.append(mutant)
    sites.sort(key=lambda m: (m.path, int(m.anchor[1:].split(":")[0])))
    return sites


def generated_sample(count: int = GENERATED_COUNT, seed: int = SEED,
                     root: Path = REPO_ROOT) -> list[Mutant]:
    sites = enumerate_sites(root)
    return sorted(random.Random(seed).sample(sites, count),
                  key=lambda m: (m.path, int(m.anchor[1:].split(":")[0])))


def apply(mutant: Mutant, source: str) -> str:
    """The mutated source. Raises ValueError if the mutant no longer fits the source."""
    if mutant.anchor.startswith("@"):
        offset, old = mutant.anchor[1:].split(":", 1)
        at = int(offset)
        if source[at : at + len(old)] != old:
            raise ValueError(f"{mutant.id}: expected {old!r} at offset {at}")
        mutated = source[:at] + mutant.replacement + source[at + len(old) :]
    else:
        if source.count(mutant.anchor) != 1:
            raise ValueError(
                f"{mutant.id}: anchor occurs {source.count(mutant.anchor)} times in "
                f"{mutant.path}, expected once"
            )
        mutated = source.replace(mutant.anchor, mutant.replacement)
    compile(mutated, mutant.path, "exec")
    return mutated


# --- running ----------------------------------------------------------------------------


@dataclass
class Outcome:
    id: str
    path: str
    description: str
    status: str  # killed | survived | stale | timeout
    stage: str = ""
    exit_code: int | None = None
    seconds: float = 0.0


def _tracked_files() -> list[str]:
    """Tracked files plus untracked ones git does not ignore: the working tree as a commit
    of it would record it."""
    out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                         cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    return [line for line in out.stdout.splitlines() if line and (REPO_ROOT / line).is_file()]


def _uncommitted_paths() -> list[str]:
    """Paths the workspace copies that differ from HEAD, so a report says what it measured."""
    out = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"],
                         cwd=REPO_ROOT, capture_output=True, text=True, check=False)
    return sorted(line[3:] for line in out.stdout.splitlines() if line)


def _make_workspace(files: list[str]) -> Path:
    work = Path(tempfile.mkdtemp(prefix="neurostim-mutation-"))
    for name in files:
        target = work / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO_ROOT / name, target)
    # A copy of the history, not GIT_DIR: the ledger tests also run the gate from a
    # directory that must NOT be a checkout, and GIT_DIR would reach that one too.
    shutil.copytree(REPO_ROOT / ".git", work / ".git", symlinks=True)
    papers = REPO_ROOT / "papers_stim_calc_ref"
    if papers.is_dir():
        (work / "papers_stim_calc_ref").symlink_to(papers)
    return work


def _env(work: Path) -> dict[str, str]:
    env = dict(os.environ)
    env.update(
        PYTHONPATH=str(work), PYTHONDONTWRITEBYTECODE="1", QT_QPA_PLATFORM="offscreen",
        MPLBACKEND="Agg",
    )
    return env


def _check_isolation(work: Path) -> None:
    out = subprocess.run(
        [sys.executable, "-c", "import neurostim; print(neurostim.__file__)"],
        cwd=work, env=_env(work), capture_output=True, text=True, check=True,
    )
    resolved = Path(out.stdout.strip()).resolve()
    if work.resolve() not in resolved.parents:
        raise SystemExit(
            f"neurostim imports from {resolved}, not from the workspace {work}: every "
            f"mutant would survive. Refusing to run."
        )


def _related_tests(work: Path, path: str) -> list[str]:
    stem = Path(path).stem
    return sorted(
        str(p.relative_to(work)) for p in (work / "tests").glob("test_*.py")
        if stem in p.read_text(encoding="utf-8")
    )


HARNESS_TESTS = ("tests/test_build_gates.py::TestTheMutationGate",)
"""Deselected inside the workspace: the tests of this harness itself.

They read this script's own metadata and output: the results file the run is producing,
the named anchors, and the site-keyed judgements. A mutant at a judged site or a named
anchor changes the source text they look up, so they fail, and the run counted that as a
kill. That is the harness observing its own bookkeeping, not a test of the arithmetic: 6
of seed 20260930's 143 kills at 31a8db4 were this and nothing else (ledger 190)."""


def _pytest(work: Path, targets: list[str], timeout: float) -> tuple[int | None, float]:
    start = time.monotonic()
    try:
        done = subprocess.run(
            [sys.executable, "-m", "pytest", "-x", "-q", "--tb=no", "-p", "no:cacheprovider",
             *(arg for test in HARNESS_TESTS for arg in ("--deselect", test)), *targets],
            cwd=work, env=_env(work), capture_output=True, timeout=timeout, check=False,
        )
        return done.returncode, time.monotonic() - start
    except subprocess.TimeoutExpired:
        return None, time.monotonic() - start


def run_one(mutant: Mutant, work: Path, timeout: float) -> Outcome:
    target = work / mutant.path
    original = target.read_text(encoding="utf-8")
    outcome = Outcome(mutant.id, mutant.path, mutant.description, "survived")
    try:
        mutated = apply(mutant, original)
    except (ValueError, SyntaxError) as exc:
        outcome.status, outcome.stage = "stale", str(exc)
        return outcome
    target.write_text(mutated, encoding="utf-8")
    try:
        total = 0.0
        for stage, targets in (("related", _related_tests(work, mutant.path)),
                               ("full", ["tests"])):
            if not targets:
                continue
            code, seconds = _pytest(work, targets, timeout)
            total += seconds
            if code is None:
                outcome.status, outcome.stage = "timeout", stage
                break
            if code not in (0, 5):
                outcome.status, outcome.stage, outcome.exit_code = "killed", stage, code
                break
        outcome.seconds = round(total, 1)
    finally:
        target.write_text(original, encoding="utf-8")
        if target.read_text(encoding="utf-8") != original:
            raise SystemExit(f"could not restore {target}")
    return outcome


def run(mutants: list[Mutant], workers: int, timeout: float) -> list[Outcome]:
    files = _tracked_files()
    spaces = [_make_workspace(files) for _ in range(workers)]
    try:
        _check_isolation(spaces[0])
        code, seconds = _pytest(spaces[0], ["tests"], timeout)
        if code != 0:
            raise SystemExit(f"the unmutated suite does not pass in the workspace ({code})")
        print(f"baseline: suite passes in {seconds:.0f} s", flush=True)
        free = list(spaces)
        results: dict[str, Outcome] = {}

        def work(mutant: Mutant) -> Outcome:
            space = free.pop()
            try:
                return run_one(mutant, space, timeout)
            finally:
                free.append(space)

        with ThreadPoolExecutor(max_workers=workers) as pool:
            for index, outcome in enumerate(pool.map(work, mutants), 1):
                results[outcome.id] = outcome
                print(f"[{index}/{len(mutants)}] {outcome.status:8} {outcome.id} "
                      f"({outcome.seconds:.0f} s)", flush=True)
        return [results[m.id] for m in mutants]
    finally:
        for space in spaces:
            shutil.rmtree(space, ignore_errors=True)


# --- the gate ---------------------------------------------------------------------------


def gate(report: dict) -> list[str]:
    """Reasons the report fails the gate; empty when it passes."""
    reasons: list[str] = []
    named = report["named"]
    ids = {m.id for m in NAMED}
    if {o["id"] for o in named} != ids:
        reasons.append("the report's named set is not NAMED")
    for o in named:
        if o["status"] not in ("killed", "timeout"):
            reasons.append(f"named mutant {o['id']} {o['status']}: {o['description']}")
    generated = report["generated"]
    if len(generated) < 150:
        reasons.append(f"only {len(generated)} generated mutants, need >= 150")
    killed = sum(o["status"] in ("killed", "timeout") for o in generated)
    stale = [o["id"] for o in generated if o["status"] == "stale"]
    if stale:
        reasons.append(f"{len(stale)} generated mutants are stale")
    score = killed / len(generated) if generated else 0.0
    if score < GENERATED_FLOOR:
        reasons.append(f"generated score {score:.1%} is below {GENERATED_FLOOR:.0%}")
    return reasons


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--list", action="store_true", help="print the mutants and exit")
    parser.add_argument("--check-anchors", action="store_true",
                        help="exit 1 unless every named anchor occurs exactly once")
    parser.add_argument("--gate", type=Path, metavar="RESULTS",
                        help="check a results file against the gate and exit")
    parser.add_argument("--named-only", action="store_true")
    parser.add_argument(
        "--seed", type=int, default=SEED,
        help=(
            "seed for the generated sample. After tests have been written against one "
            "sample's survivors, re-running that seed measures a set the tests were tuned "
            "to; pre-register a fresh seed to measure the suite (ledger 181)"
        ),
    )
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) // 2))
    parser.add_argument("--timeout", type=float, default=900.0,
                        help="seconds per pytest run before the mutant counts as killed")
    parser.add_argument("--output", type=Path, default=RESULTS)
    args = parser.parse_args(argv)

    generated = [] if args.named_only else generated_sample(seed=args.seed)
    if args.list:
        for m in (*NAMED, *generated):
            print(f"{m.id:40} {m.path:40} {m.description}")
        print(f"{len(NAMED)} named, {len(generated)} generated "
              f"(from {len(enumerate_sites())} sites, seed {args.seed})")
        return 0
    if args.check_anchors:
        bad = []
        for m in NAMED:
            try:
                apply(m, (REPO_ROOT / m.path).read_text(encoding="utf-8"))
            except (ValueError, SyntaxError) as exc:
                bad.append(str(exc))
        print("\n".join(bad) or f"all {len(NAMED)} named anchors occur exactly once")
        return 1 if bad else 0
    if args.gate:
        reasons = gate(json.loads(args.gate.read_text(encoding="utf-8")))
        print("\n".join(reasons) or "mutation gate met")
        return 1 if reasons else 0

    # What the workspaces copy is the tree as it stands now, so record it now: a file
    # edited during the hour-long run is not part of what was measured (ledger 181).
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT,
                          capture_output=True, text=True, check=False).stdout.strip()
    dirty = _uncommitted_paths()
    outcomes = run([*NAMED, *generated], args.workers, args.timeout)
    named_out = [asdict(o) for o in outcomes[: len(NAMED)]]
    generated_out = [asdict(o) for o in outcomes[len(NAMED) :]]
    killed = sum(o["status"] in ("killed", "timeout") for o in generated_out)
    by_id = {m.id: m for m in generated}
    report = {
        "head": head,
        "uncommitted_paths": dirty,
        "measured": (
            f"the working tree: {head} plus the uncommitted paths listed"
            if dirty else f"commit {head} exactly"
        ),
        "date": _dt.date.today().isoformat(),
        "seed": args.seed,
        "sites": len(enumerate_sites()),
        "named_killed": sum(o["status"] in ("killed", "timeout") for o in named_out),
        "named_total": len(named_out),
        "generated_killed": killed,
        "generated_total": len(generated_out),
        "generated_score": round(killed / len(generated_out), 4) if generated_out else None,
        "generated_survivors": [
            {"id": o["id"], "description": o["description"],
             "judged": judgement(by_id[o["id"]])}
            for o in generated_out if o["status"] == "survived"
        ],
        "named": named_out,
        "generated": generated_out,
    }
    args.output.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    reasons = gate(report) if generated_out else [
        f"named mutant {o['id']} {o['status']}" for o in named_out
        if o["status"] not in ("killed", "timeout")
    ]
    print("\n".join(reasons) or "mutation gate met")
    return 1 if reasons else 0


if __name__ == "__main__":
    sys.exit(main())
