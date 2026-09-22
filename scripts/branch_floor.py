#!/usr/bin/env python3
"""Gate branch coverage on fully-exercised branch *points*, not on arcs taken.

Why this script exists
----------------------
``coverage.py``'s headline branch figure counts **arcs**: for a two-way branch it
awards half credit when only one exit has ever been taken.  A test suite that enters
every ``if`` and never once takes the ``else`` therefore scores 50 %, which is the
failure mode this package's audit actually found.  What a reviewer means by "branch
coverage" is the stricter quantity: the fraction of decision **points** at which every
exit has been exercised.  This script reads ``coverage json`` output and re-aggregates
its per-file arc lists to points, counting a point covered only when it has no missing
arc.

The two measurements are both correct and they are of different units.  Measured on
this repository at the audit baseline (coverage.py 7.16.1, the full suite)::

    branch arcs taken   548 / 766 = 71.54 %
    branch points       185 / 383 = 48.30 %

``--cov-fail-under`` is deliberately not used: it gates the blended line+branch total,
which stood at 88.15 % against a real branch-point figure of 48.30 %, and it can never
ratchet the number this project cares about.

Usage
-----
::

    coverage run -m pytest -q
    coverage json -o coverage.json
    python scripts/branch_floor.py --json coverage.json --min 48.0

Exit status: ``0`` when every floor is met, ``1`` when a floor is breached, ``2`` when
the report is missing or is not a branch-coverage report.  A report that cannot be read
is an error, never a pass.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn

BASELINE_POINT_PERCENT = 48.30
"""Branch points with both exits exercised, measured on the audit baseline.

185 / 383, from ``coverage.py`` 7.16.1 over the full suite at commit ``7a0515b``.
The exit floor for this repair is 80 %, raised in phase 7; this constant records where
the ratchet started so that a floor set above the measured value cannot pass unnoticed.
"""


@dataclass(frozen=True)
class ModuleCoverage:
    """Branch-point coverage for one source file."""

    name: str
    covered: int
    points: int

    @property
    def percent(self) -> float:
        return percent(self.covered, self.points)


def percent(covered: int, points: int) -> float:
    """Percentage covered, with an empty denominator reported as fully covered."""
    if points == 0:
        return 100.0
    return 100.0 * covered / points


def aggregate(report: dict[str, Any]) -> list[ModuleCoverage]:
    """Re-aggregate a ``coverage json`` report's branch arcs to branch points.

    An arc is ``[source_line, destination_line]``.  The *point* is the source line: one
    line with three exits is one point, not three.  A point is covered only when none of
    its arcs appears in ``missing_branches`` -- exactly the rule a bytecode jump-site
    harness applies, and the reason this number is not ``coverage.py``'s headline.
    """
    modules: list[ModuleCoverage] = []
    for name, data in sorted(report.get("files", {}).items()):
        executed = data.get("executed_branches") or []
        missing = data.get("missing_branches") or []
        points = {arc[0] for arc in executed} | {arc[0] for arc in missing}
        if not points:
            continue
        uncovered = {arc[0] for arc in missing}
        modules.append(ModuleCoverage(name, len(points - uncovered), len(points)))
    return modules


def totals(modules: list[ModuleCoverage]) -> tuple[int, int]:
    """Summed (covered, points) over every module that has at least one branch point."""
    return sum(m.covered for m in modules), sum(m.points for m in modules)


def load(path: Path) -> dict[str, Any]:
    """Read a ``coverage json`` report, refusing anything that is not one."""
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        _abort(
            f"error: coverage report not found: {path}",
            "run: coverage run -m pytest -q && coverage json -o coverage.json",
        )
    except json.JSONDecodeError as exc:
        _abort(f"error: {path} is not valid JSON: {exc}")
    if not report.get("meta", {}).get("branch_coverage"):
        _abort(
            f"error: {path} was not produced with branch coverage enabled;",
            "run coverage with --branch",
        )
    return report


def _abort(*lines: str) -> NoReturn:
    """Exit 2 -- an unreadable report is an error, never a silent pass."""
    for line in lines:
        print(line, file=sys.stderr)
    raise SystemExit(2)


def render(modules: list[ModuleCoverage]) -> str:
    """A per-module table, worst first, for the CI log."""
    width = max((len(m.name) for m in modules), default=10)
    lines = [f"{'module':{width}s}  points  covered  percent"]
    for module in sorted(modules, key=lambda m: (m.percent, -m.points, m.name)):
        lines.append(
            f"{module.name:{width}s}  {module.points:6d}  {module.covered:7d}  "
            f"{module.percent:6.2f}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json", type=Path, default=Path("coverage.json"),
                        help="coverage json report to read (default: coverage.json)")
    parser.add_argument("--min", type=float, default=BASELINE_POINT_PERCENT,
                        help=f"total branch-point floor, percent (default: {BASELINE_POINT_PERCENT})")
    parser.add_argument("--module-min", type=float, default=None,
                        help="per-module branch-point floor, percent (default: not enforced)")
    parser.add_argument("--module-min-points", type=int, default=4,
                        help="smallest module the per-module floor applies to (default: 4 points)")
    args = parser.parse_args(argv)

    modules = aggregate(load(args.json))
    covered, points = totals(modules)
    overall = percent(covered, points)

    print(render(modules))
    print(f"\nbranch points fully exercised: {covered} / {points} = {overall:.2f} %")
    print(f"total floor: {args.min:.2f} %")

    failures: list[str] = []
    if overall < args.min:
        failures.append(f"total {overall:.2f} % is below the floor of {args.min:.2f} %")
    if args.module_min is not None:
        below = [
            m for m in modules
            if m.points >= args.module_min_points and m.percent < args.module_min
        ]
        if below:
            failures.append(
                f"{len(below)} module(s) below the per-module floor of {args.module_min:.2f} %: "
                + ", ".join(f"{m.name} ({m.percent:.2f} %)" for m in below)
            )

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
