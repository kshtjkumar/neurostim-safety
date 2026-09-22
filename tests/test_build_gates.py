"""Gates on the build harness itself, not on the package.

These tests do not exercise ``neurostim``.  They check that the machinery the later
repair phases depend on exists, computes the metric it claims to compute, and fails
when it should.  A gate that cannot fail is not a gate.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
BRANCH_FLOOR = REPO_ROOT / "scripts" / "branch_floor.py"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"


def _load_branch_floor() -> Any:
    spec = importlib.util.spec_from_file_location("branch_floor", BRANCH_FLOOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolves annotations through sys.modules, so the module must be
    # registered before it is executed.
    sys.modules["branch_floor"] = module
    spec.loader.exec_module(module)
    return module


def _report(files: dict[str, tuple[list[list[int]], list[list[int]]]]) -> dict[str, Any]:
    """A minimal ``coverage json`` report carrying only the arc lists we aggregate."""
    return {
        "meta": {"format": 3, "version": "7.16.1", "branch_coverage": True},
        "files": {
            name: {"executed_branches": executed, "missing_branches": missing}
            for name, (executed, missing) in files.items()
        },
        "totals": {},
    }


def _run(report: dict[str, Any], tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    path = tmp_path / "coverage.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(BRANCH_FLOOR), "--json", str(path), *args],
        capture_output=True,
        text=True,
        check=False,
    )


# --- the metric ---------------------------------------------------------------------


def test_the_gate_script_is_committed() -> None:
    assert BRANCH_FLOOR.is_file(), "scripts/branch_floor.py must be in the repository"


def test_a_point_counts_as_covered_only_when_no_arc_from_it_is_missing() -> None:
    module = _load_branch_floor()
    report = _report(
        {
            "pkg/both.py": ([[10, 11], [10, 12]], []),
            "pkg/half.py": ([[20, 21]], [[20, 22]]),
        }
    )
    modules = module.aggregate(report)
    by_name = {m.name: m for m in modules}
    assert (by_name["pkg/both.py"].covered, by_name["pkg/both.py"].points) == (1, 1)
    assert (by_name["pkg/half.py"].covered, by_name["pkg/half.py"].points) == (0, 1)
    assert module.totals(modules) == (1, 2)


def test_a_half_covered_point_earns_no_credit_where_the_arc_metric_gives_half() -> None:
    """The whole reason for this script: arcs give half credit, points give none."""
    module = _load_branch_floor()
    report = _report({"pkg/half.py": ([[20, 21]], [[20, 22]])})
    covered, points = module.totals(module.aggregate(report))
    assert (covered, points) == (0, 1)
    assert module.percent(covered, points) == 0.0
    # The same data under coverage.py's headline rule is 1 arc of 2 = 50 %.
    assert module.percent(1, 2) == 50.0


def test_one_line_with_three_exits_is_still_one_point() -> None:
    module = _load_branch_floor()
    report = _report({"pkg/match.py": ([[5, 6], [5, 7]], [[5, 8]])})
    covered, points = module.totals(module.aggregate(report))
    assert (covered, points) == (0, 1)


def test_files_without_branches_do_not_dilute_the_denominator() -> None:
    module = _load_branch_floor()
    report = _report({"pkg/flat.py": ([], []), "pkg/one.py": ([[3, 4], [3, 5]], [])})
    covered, points = module.totals(module.aggregate(report))
    assert (covered, points) == (1, 1)


# --- the gate -----------------------------------------------------------------------


def test_the_gate_fails_below_the_floor(tmp_path: Path) -> None:
    report = _report(
        {
            "pkg/a.py": ([[10, 11], [10, 12]], []),
            "pkg/b.py": ([[20, 21]], [[20, 22]]),
            "pkg/c.py": ([[30, 31]], [[30, 32]]),
            "pkg/d.py": ([[40, 41]], [[40, 42]]),
        }
    )  # 1 of 4 points = 25.00 %
    result = _run(report, tmp_path, "--min", "48.0")
    assert result.returncode != 0, result.stdout + result.stderr
    assert "25.00" in result.stdout + result.stderr
    assert "48.0" in result.stdout + result.stderr


def test_the_gate_passes_at_or_above_the_floor(tmp_path: Path) -> None:
    report = _report(
        {
            "pkg/a.py": ([[10, 11], [10, 12]], []),
            "pkg/b.py": ([[20, 21]], [[20, 22]]),
        }
    )  # 1 of 2 points = 50.00 %
    result = _run(report, tmp_path, "--min", "48.0")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "50.00" in result.stdout


def test_the_per_module_floor_fails_one_bad_module(tmp_path: Path) -> None:
    report = _report(
        {
            "pkg/good.py": ([[1, 2], [1, 3], [4, 5], [4, 6], [7, 8], [7, 9], [10, 11], [10, 12]], []),
            "pkg/bad.py": ([[20, 21]], [[20, 22], [23, 24], [25, 26], [27, 28]]),
        }
    )
    result = _run(report, tmp_path, "--min", "0.0", "--module-min", "60.0", "--module-min-points", "4")
    assert result.returncode != 0, result.stdout + result.stderr
    assert "pkg/bad.py" in result.stdout + result.stderr
    assert "pkg/good.py" not in (result.stdout + result.stderr).split("below the per-module")[-1]


def test_the_per_module_floor_skips_modules_with_too_few_points(tmp_path: Path) -> None:
    report = _report({"pkg/tiny.py": ([], [[20, 21], [22, 23]])})
    result = _run(report, tmp_path, "--min", "0.0", "--module-min", "60.0", "--module-min-points", "4")
    assert result.returncode == 0, result.stdout + result.stderr


def test_a_missing_report_is_an_error_and_never_a_silent_pass(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(BRANCH_FLOOR), "--json", str(tmp_path / "absent.json"), "--min", "0.0"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2, result.stdout + result.stderr
    assert "absent.json" in result.stderr


def test_a_report_without_branch_coverage_is_an_error(tmp_path: Path) -> None:
    report = _report({"pkg/a.py": ([], [])})
    report["meta"]["branch_coverage"] = False
    result = _run(report, tmp_path, "--min", "0.0")
    assert result.returncode == 2, result.stdout + result.stderr
    assert "branch coverage" in result.stderr.lower()


def test_the_recorded_baseline_matches_the_measured_one() -> None:
    """48.30 % is the measured baseline; the CI floor must not be set above it silently."""
    module = _load_branch_floor()
    assert module.BASELINE_POINT_PERCENT == 48.30


# --- CI ------------------------------------------------------------------------------


def test_ci_tests_python_314() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    assert '"3.14"' in workflow, "the interpreter this package is developed on is untested in CI"


def test_ci_runs_the_branch_point_gate() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    assert "branch_floor.py" in workflow
    assert "coverage json" in workflow
    executable = [
        line for line in workflow.splitlines() if not line.lstrip().startswith("#")
    ]
    assert not any("--cov-fail-under" in line for line in executable), (
        "the blended line+branch total is not the gate"
    )
