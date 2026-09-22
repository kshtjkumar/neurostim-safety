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


# --- the generated README transcript -------------------------------------------------


REGENERATE = REPO_ROOT / "scripts" / "regenerate_example_output.py"
README = REPO_ROOT / "README.md"


def _load_regenerate() -> Any:
    spec = importlib.util.spec_from_file_location("regenerate_example_output", REGENERATE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["regenerate_example_output"] = module
    spec.loader.exec_module(module)
    return module


class TestGeneratedReadmeTranscript:
    """The README transcript is output, not prose, so a script owns it.

    At the audit baseline the committed block showed five checks and a limiting current
    of 70.69 uA where the package prints nine checks and 141.4 uA -- stale by a release,
    and the first thing a reviewer checks.
    """

    def test_the_regeneration_script_is_committed(self) -> None:
        assert REGENERATE.is_file()

    def test_the_readme_carries_the_generated_markers(self) -> None:
        text = README.read_text(encoding="utf-8")
        module = _load_regenerate()
        assert module.BEGIN_MARKER in text
        assert module.END_MARKER in text

    def test_the_committed_transcript_is_what_the_package_prints(self) -> None:
        module = _load_regenerate()
        _, existing, _ = module.split_readme(README.read_text(encoding="utf-8"))
        assert existing == module.readme_block(module.quickstart_transcript())

    def test_every_transcript_line_appears_verbatim_in_describe(self) -> None:
        """The elision rule may drop lines; it may never invent or reword one."""
        from neurostim import RingElectrode, SafetyCalculator, StimProtocol

        module = _load_regenerate()
        printed = set(
            SafetyCalculator(
                RingElectrode(330, 270, "Pt"), StimProtocol(80, 200, 130, 1), compliance_V=10.0
            )
            .describe()
            .splitlines()
        )
        for line in module.quickstart_transcript().splitlines():
            assert line in printed, f"transcript line is not in describe(): {line!r}"

    def test_the_transcript_reports_every_check(self) -> None:
        module = _load_regenerate()
        headlines = [
            line for line in module.quickstart_transcript().splitlines() if line.startswith("[")
        ]
        from neurostim import RingElectrode, SafetyCalculator, StimProtocol

        assessment = SafetyCalculator(
            RingElectrode(330, 270, "Pt"), StimProtocol(80, 200, 130, 1), compliance_V=10.0
        ).assess()
        assert len(headlines) == len(assessment.checks)

    def test_check_exits_zero_on_the_committed_readme(self) -> None:
        result = subprocess.run(
            [sys.executable, str(REGENERATE), "--check"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    def test_check_exits_non_zero_when_the_transcript_drifts(self, tmp_path: Path) -> None:
        """The gate must be able to fail, or it gates nothing."""
        module = _load_regenerate()
        original = README.read_text(encoding="utf-8")
        backup = tmp_path / "README.md.bak"
        backup.write_text(original, encoding="utf-8")
        try:
            README.write_text(original.replace("Overall: FAIL", "Overall: PASS"), encoding="utf-8")
            assert "Overall: PASS" in README.read_text(encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(REGENERATE), "--check"],
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
                check=False,
            )
            assert result.returncode == 1, result.stdout + result.stderr
            assert "Overall: PASS" in result.stderr
        finally:
            README.write_text(backup.read_text(encoding="utf-8"), encoding="utf-8")
        assert README.read_text(encoding="utf-8") == original
        assert module.BEGIN_MARKER in original

    def test_the_example_no_longer_writes_a_47_megabyte_tiff(self, tmp_path: Path) -> None:
        """600 dpi uncompressed RGBA. Vector output is the deliverable here."""
        module = _load_regenerate()
        target = tmp_path / "example_output"
        module.regenerate_example_output(target)
        written = sorted(p.name for p in target.iterdir())
        assert not [n for n in written if n.endswith(".tiff")]
        assert max(p.stat().st_size for p in target.iterdir()) < 1_000_000


# --- the mistakes ledger --------------------------------------------------------------


LEDGER_CHECK = REPO_ROOT / "scripts" / "ledger_check.py"
LEDGER = REPO_ROOT / "CODE_MISTAKES_LOG.md"
FIX_PLAN = REPO_ROOT / "docs" / "audit" / "FIX_PLAN_v2.md"


def _load_ledger_check() -> Any:
    spec = importlib.util.spec_from_file_location("ledger_check", LEDGER_CHECK)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["ledger_check"] = module
    spec.loader.exec_module(module)
    return module


_LEDGER_HEADER = (
    "| # | Date | Severity | File:line | Defect | Fix | Commit |\n"
    "|---|------|----------|-----------|--------|-----|--------|\n"
)
_PLAN_SECTION_9 = (
    "## 9. Ledger coverage\n\n"
    "| # | sev | v1 verdict | v2 commit(s) | note |\n"
    "|---|---|---|---|---|\n"
    "| 1 | HIGH | OK | C1.4 | |\n"
    "| 2 | LOW | OK | C2.1 | |\n\n"
    "## 10. Exit criteria\n"
)


def _write_pair(tmp_path: Path, rows: str, section_9: str = _PLAN_SECTION_9) -> tuple[Path, Path]:
    ledger = tmp_path / "CODE_MISTAKES_LOG.md"
    plan = tmp_path / "FIX_PLAN_v2.md"
    ledger.write_text("# log\n\n" + _LEDGER_HEADER + rows, encoding="utf-8")
    plan.write_text(section_9, encoding="utf-8")
    return ledger, plan


def _run_ledger(ledger: Path, plan: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(LEDGER_CHECK), "--ledger", str(ledger), "--plan", str(plan)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )


class TestLedgerGate:
    """The ledger is the record of what was wrong; a row that does not parse is lost.

    Rows 8 and 46 once carried unescaped pipes inside ``min(|cathodic|,|anodic|)``, which
    split them into 11 and 9 fields against the header's 7. Markdown renders the overflow
    as extra columns and every table reader -- including any future script that tries to
    audit this file -- silently misreads the row.
    """

    def test_the_gate_script_is_committed(self) -> None:
        assert LEDGER_CHECK.is_file()

    def test_the_committed_ledger_and_plan_pass(self) -> None:
        result = subprocess.run(
            [sys.executable, str(LEDGER_CHECK)],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    def test_the_committed_ledger_has_uniform_rows(self) -> None:
        module = _load_ledger_check()
        table = module.parse_table(LEDGER.read_text(encoding="utf-8"))
        assert table.header == ["#", "Date", "Severity", "File:line", "Defect", "Fix", "Commit"]
        assert [row.number for row in table.entries] == list(range(1, len(table.entries) + 1))

    def test_an_unescaped_pipe_is_caught(self, tmp_path: Path) -> None:
        """The exact shape of the original defect."""
        rows = (
            "| 1 | 2026-09-22 | HIGH | a.py:1 | ok | pending | pending |\n"
            "| 2 | 2026-09-22 | LOW | b.py:2 | min(|cathodic|,|anodic|) is wrong | pending | pending |\n"
        )
        ledger, plan = _write_pair(tmp_path, rows)
        result = _run_ledger(ledger, plan)
        assert result.returncode == 1, result.stdout + result.stderr
        # Four extra pipes in one cell: 11 fields against the header's 7. (The fix plan
        # quotes 13 and 11 for rows 8 and 46; that count includes the leading and
        # trailing empty tokens of a bare str.split("|"), i.e. 11 and 9 real fields.)
        assert "11 fields against the header's 7" in result.stderr
        assert "unescaped" in result.stderr

    def test_an_entry_missing_from_the_plan_is_caught(self, tmp_path: Path) -> None:
        rows = (
            "| 1 | 2026-09-22 | HIGH | a.py:1 | ok | pending | pending |\n"
            "| 2 | 2026-09-22 | LOW | b.py:2 | ok | pending | pending |\n"
            "| 3 | 2026-09-22 | LOW | c.py:3 | never scheduled | pending | pending |\n"
        )
        ledger, plan = _write_pair(tmp_path, rows)
        result = _run_ledger(ledger, plan)
        assert result.returncode == 1, result.stdout + result.stderr
        assert "3" in result.stderr
        assert "section 9" in result.stderr.lower()

    def test_a_sub_lettered_plan_row_counts_as_coverage(self, tmp_path: Path) -> None:
        """The plan breaks 61, 62, 67, 77 and 78 out into sub-findings."""
        rows = "| 1 | 2026-09-22 | HIGH | a.py:1 | ok | pending | pending |\n"
        section = _PLAN_SECTION_9.replace("| 1 | HIGH | OK | C1.4 | |", "| 1/M3 | HIGH | OK | C1.4 | |")
        ledger, plan = _write_pair(tmp_path, rows, section)
        result = _run_ledger(ledger, plan)
        assert result.returncode == 0, result.stdout + result.stderr

    def test_a_plan_defect_row_needs_no_plan_coverage(self, tmp_path: Path) -> None:
        """Entries 79-83 are defects in the plan itself, disposed of in its section 1b."""
        rows = (
            "| 1 | 2026-09-22 | HIGH | a.py:1 | ok | pending | pending |\n"
            "| 2 | 2026-09-22 | LOW | b.py:2 | ok | pending | pending |\n"
            "| 3 | 2026-09-22 | (plan defect) | FIX_PLAN.md D4 | a plan blocker | pending | pending |\n"
        )
        ledger, plan = _write_pair(tmp_path, rows)
        result = _run_ledger(ledger, plan)
        assert result.returncode == 0, result.stdout + result.stderr

    def test_a_fabricated_commit_hash_is_caught(self, tmp_path: Path) -> None:
        """A row may not claim a fix landed in a commit that does not exist."""
        rows = (
            "| 1 | 2026-09-22 | HIGH | a.py:1 | ok | done | 0000000000000000000000000000000000000000 |\n"
            "| 2 | 2026-09-22 | LOW | b.py:2 | ok | pending | pending |\n"
        )
        ledger, plan = _write_pair(tmp_path, rows)
        result = _run_ledger(ledger, plan)
        assert result.returncode == 1, result.stdout + result.stderr
        assert "0000000" in result.stderr

    def test_a_real_commit_hash_is_accepted(self, tmp_path: Path) -> None:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=REPO_ROOT, check=True
        ).stdout.strip()
        rows = (
            f"| 1 | 2026-09-22 | HIGH | a.py:1 | ok | done | {head} |\n"
            "| 2 | 2026-09-22 | LOW | b.py:2 | ok | pending | pending |\n"
        )
        ledger, plan = _write_pair(tmp_path, rows)
        result = _run_ledger(ledger, plan)
        assert result.returncode == 0, result.stdout + result.stderr

    def test_a_duplicated_entry_number_is_caught(self, tmp_path: Path) -> None:
        rows = (
            "| 1 | 2026-09-22 | HIGH | a.py:1 | ok | pending | pending |\n"
            "| 1 | 2026-09-22 | LOW | b.py:2 | ok | pending | pending |\n"
        )
        ledger, plan = _write_pair(tmp_path, rows)
        result = _run_ledger(ledger, plan)
        assert result.returncode == 1, result.stdout + result.stderr
        assert "duplicate" in result.stderr.lower()

    def test_a_gap_in_the_numbering_is_caught(self, tmp_path: Path) -> None:
        """A gap means an entry was deleted; the ledger says never delete."""
        rows = (
            "| 1 | 2026-09-22 | HIGH | a.py:1 | ok | pending | pending |\n"
            "| 3 | 2026-09-22 | LOW | b.py:2 | ok | pending | pending |\n"
        )
        section = _PLAN_SECTION_9.replace("| 2 | LOW | OK | C2.1 | |", "| 3 | LOW | OK | C2.1 | |")
        ledger, plan = _write_pair(tmp_path, rows, section)
        result = _run_ledger(ledger, plan)
        assert result.returncode == 1, result.stdout + result.stderr
        assert "2" in result.stderr

    def test_a_missing_ledger_is_an_error_not_a_pass(self, tmp_path: Path) -> None:
        result = _run_ledger(tmp_path / "absent.md", tmp_path / "also-absent.md")
        assert result.returncode == 2, result.stdout + result.stderr
