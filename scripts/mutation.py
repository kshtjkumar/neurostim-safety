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
seed. At least 90 % of it must be killed; not 100 %, because a generated set contains
equivalent mutants that no test can kill. Every survivor is listed in the results.

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

SEED = 20260927
GENERATED_COUNT = 160
GENERATED_FLOOR = 0.90

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


# Generated mutants that survive because no test *can* kill them, each with the argument.
# They still count as survivors in the score; the note is so a reader can check the claim.
# A mutant id carries its source offset, so an edit to the file drops its note.
JUDGED_EQUIVALENT: dict[str, str] = {
    "G:neurostim/models/field.py:131:5704":
        "0-d array arithmetic returns an np.float64, which is a float, so both branches "
        "return a float",
    "G:neurostim/models/strength_duration.py:359:14649":
        "differs only when the singular-value ratio equals sqrt(eps) exactly",
    "G:neurostim/safety/assessment.py:1262:59708":
        "NOT proven equivalent: differs only where the average current density equals "
        "the threshold exactly, one float, which moves the settled ceiling by an ulp; no "
        "test pins the current-density ceiling to the ulp",
    "G:neurostim/safety/assessment.py:1271:59990":
        "NOT proven equivalent: the return phase's version of the one-ulp boundary above",
    "G:neurostim/safety/assessment.py:2314:106534":
        "counter_result is None exactly when counter_electrode is None (both are set "
        "together in assess), so the two conditions always agree",
    "G:neurostim/safety/charge.py:301:13042":
        "differs only at a pulse width equal to the measured one, where the fold is 1 and "
        "no warning (and so no direction) is printed",
    "G:neurostim/safety/compliance.py:396:19416":
        "the width comparison: a return phase of zero width always carries zero current, "
        "so the current comparison already decides",
    "G:neurostim/safety/compliance.py:500:24635":
        "at equality both branches give cap / active_slope, the same seed",
    "G:neurostim/safety/current_density.py:329:15115":
        "the width comparison, as for compliance.py:396",
    "G:neurostim/safety/shannon.py:273:11346":
        "NOT proven equivalent: the plateau is consulted only when floor_to_pass has "
        "walked past its 4-step budget, which no Shannon back-solve reaches in the suite",
    "G:neurostim/safety/shannon.py:329:13790":
        "NOT proven equivalent: the same plateau, for the current back-solve",
}


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


_OWN_RESULTS_TEST = (
    "tests/test_build_gates.py::TestTheMutationGate::test_the_committed_results_meet_the_gate"
)
"""Deselected inside the workspace: it checks this script's own output, which the run is
producing, so it cannot be part of the suite the mutants are measured against."""


def _pytest(work: Path, targets: list[str], timeout: float) -> tuple[int | None, float]:
    start = time.monotonic()
    try:
        done = subprocess.run(
            [sys.executable, "-m", "pytest", "-x", "-q", "--tb=no", "-p", "no:cacheprovider",
             "--deselect", _OWN_RESULTS_TEST, *targets],
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
             "judged": JUDGED_EQUIVALENT.get(o["id"], "not judged")}
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
