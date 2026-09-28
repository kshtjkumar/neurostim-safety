"""Gates on the build harness itself, not on the package.

These tests do not exercise ``neurostim``.  They check that the machinery the later
repair phases depend on exists, computes the metric it claims to compute, and fails
when it should.  A gate that cannot fail is not a gate.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

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


def test_ci_fetches_the_full_history_for_the_ledger_gate() -> None:
    """``actions/checkout@v4`` defaults to ``fetch-depth: 1``.

    The ledger gate asserts that every recorded commit id exists. Under a depth-1
    checkout no historical object is present, so the assertion fails on the first Phase 1
    commit that fills a Commit cell -- on a ledger that is correct.
    """
    lint = _ci_job("lint")
    assert "ledger_check.py" in lint, "this test guards the job that runs the gate"
    executable = [
        line for line in lint.splitlines() if not line.lstrip().startswith("#")
    ]
    assert any("fetch-depth: 0" in line for line in executable), (
        "a commented-out setting is not a setting"
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


def _transplant_ledger_check(root: Path) -> Path:
    """A copy of the gate whose ``REPO_ROOT`` is ``root``, not this repository.

    The script locates the repository from its own path, so the only way to ask it what
    it does where no history is available is to put it somewhere that has none.
    """
    scripts = root / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    transplanted = scripts / "ledger_check.py"
    transplanted.write_text(LEDGER_CHECK.read_text(encoding="utf-8"), encoding="utf-8")
    return transplanted


def _ci_job(name: str) -> str:
    """One job's block from the workflow, sliced by indentation."""
    lines = CI_WORKFLOW.read_text(encoding="utf-8").splitlines()
    start = lines.index(f"  {name}:")
    for offset, line in enumerate(lines[start + 1 :], start + 1):
        if line.strip() and not line.startswith("   ") and not line.startswith("#"):
            return "\n".join(lines[start:offset])
    return "\n".join(lines[start:])


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

    def test_the_hash_check_is_skipped_outside_a_git_checkout(self, tmp_path: Path) -> None:
        """No history is not a fabricated hash. It must say so and pass, not fail.

        A JOSS reviewer running the gate on an unpacked sdist has no ``.git`` at all.
        Reporting every recorded commit as "does not exist" there is a confusing failure
        about a ledger that is correct.
        """
        transplanted = _transplant_ledger_check(tmp_path)
        rows = (
            "| 1 | 2026-09-22 | HIGH | a.py:1 | ok | done | "
            "0000000000000000000000000000000000000000 |\n"
            "| 2 | 2026-09-22 | LOW | b.py:2 | ok | pending | pending |\n"
        )
        ledger, plan = _write_pair(tmp_path, rows)
        result = subprocess.run(
            [sys.executable, str(transplanted), "--ledger", str(ledger), "--plan", str(plan)],
            capture_output=True,
            text=True,
            cwd=tmp_path,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "not a git checkout" in result.stderr
        assert "1 recorded commit id" in result.stderr

    def test_the_hash_check_is_skipped_in_a_shallow_clone(self, tmp_path: Path) -> None:
        """``actions/checkout@v4`` defaults to ``fetch-depth: 1``.

        Under a depth-1 checkout no historical object is present, so every recorded hash
        resolves to "does not exist" and the gate fails the lint job on the first Phase 1
        commit that fills a Commit cell. The workflow now asks for the full history; this
        is what happens anywhere else.
        """
        transplanted = _transplant_ledger_check(tmp_path)
        for command in (
            ["git", "init", "-q", "."],
            ["git", "-c", "user.name=t", "-c", "user.email=t@e", "commit", "-q",
             "--allow-empty", "-m", "x"],
        ):
            subprocess.run(command, cwd=tmp_path, check=True, capture_output=True)
        (tmp_path / ".git" / "shallow").touch()

        rows = (
            "| 1 | 2026-09-22 | HIGH | a.py:1 | ok | done | "
            "0000000000000000000000000000000000000000 |\n"
            "| 2 | 2026-09-22 | LOW | b.py:2 | ok | pending | pending |\n"
        )
        ledger, plan = _write_pair(tmp_path, rows)
        result = subprocess.run(
            [sys.executable, str(transplanted), "--ledger", str(ledger), "--plan", str(plan)],
            capture_output=True,
            text=True,
            cwd=tmp_path,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "shallow" in result.stderr

    def test_a_fabricated_hash_still_fails_where_the_history_is_there(
        self, tmp_path: Path
    ) -> None:
        """The degradation must not have turned the gate off in the place it runs."""
        transplanted = _transplant_ledger_check(tmp_path)
        for command in (
            ["git", "init", "-q", "."],
            ["git", "-c", "user.name=t", "-c", "user.email=t@e", "commit", "-q",
             "--allow-empty", "-m", "x"],
        ):
            subprocess.run(command, cwd=tmp_path, check=True, capture_output=True)

        rows = (
            "| 1 | 2026-09-22 | HIGH | a.py:1 | ok | done | "
            "0000000000000000000000000000000000000000 |\n"
            "| 2 | 2026-09-22 | LOW | b.py:2 | ok | pending | pending |\n"
        )
        ledger, plan = _write_pair(tmp_path, rows)
        result = subprocess.run(
            [sys.executable, str(transplanted), "--ledger", str(ledger), "--plan", str(plan)],
            capture_output=True,
            text=True,
            cwd=tmp_path,
            check=False,
        )
        assert result.returncode == 1, result.stdout + result.stderr
        assert "0000000" in result.stderr

    def test_a_copy_sitting_inside_someone_elses_checkout_is_not_that_checkout(
        self, tmp_path: Path
    ) -> None:
        """``git`` walks upward, so the probe must ask WHICH repository it found.

        An sdist unpacked into a working directory, a vendored copy, a monorepo subtree:
        the gate is then not at a repository root but git answers about the enclosing one,
        and the ledger's ids get resolved against a history that was never going to
        contain them. Every recorded id fails, which is the confusing failure this
        degradation exists to remove.
        """
        outer = tmp_path / "outer"
        (outer / "vendored").mkdir(parents=True)
        for command in (
            ["git", "init", "-q", "."],
            ["git", "-c", "user.name=t", "-c", "user.email=t@e", "commit", "-q",
             "--allow-empty", "-m", "x"],
        ):
            subprocess.run(command, cwd=outer, check=True, capture_output=True)
        transplanted = _transplant_ledger_check(outer / "vendored")

        rows = (
            "| 1 | 2026-09-22 | HIGH | a.py:1 | ok | done | "
            "0000000000000000000000000000000000000000 |\n"
            "| 2 | 2026-09-22 | LOW | b.py:2 | ok | pending | pending |\n"
        )
        ledger, plan = _write_pair(tmp_path, rows)
        result = subprocess.run(
            [sys.executable, str(transplanted), "--ledger", str(ledger), "--plan", str(plan)],
            capture_output=True,
            text=True,
            cwd=outer / "vendored",
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "not itself a git checkout" in result.stderr

    def test_a_shallow_clone_still_checks_the_ids_it_does_have(self, tmp_path: Path) -> None:
        """Skipping the assertion wholesale turns the gate off for present ids too."""
        transplanted = _transplant_ledger_check(tmp_path)
        for command in (
            ["git", "init", "-q", "."],
            ["git", "-c", "user.name=t", "-c", "user.email=t@e", "commit", "-q",
             "--allow-empty", "-m", "x"],
        ):
            subprocess.run(command, cwd=tmp_path, check=True, capture_output=True)
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True,
            check=True,
        ).stdout.strip()
        (tmp_path / ".git" / "shallow").touch()

        rows = (
            f"| 1 | 2026-09-22 | HIGH | a.py:1 | ok | done | {head} |\n"
            "| 2 | 2026-09-22 | LOW | b.py:2 | ok | done | "
            "0000000000000000000000000000000000000000 |\n"
        )
        ledger, plan = _write_pair(tmp_path, rows)
        result = subprocess.run(
            [sys.executable, str(transplanted), "--ledger", str(ledger), "--plan", str(plan)],
            capture_output=True,
            text=True,
            cwd=tmp_path,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        # One of the two could not be resolved, not both: the present id was checked.
        assert "1 of 2 recorded commit id" in result.stderr

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


class TestTheThermalClaimIsTheReproductionNotAValidation:
    """Ledgers 46 and 173, C7.3. CITATION.cff said the Pennes modelling was "validated
    against a published finite element model", and README and the worked example blamed the
    gap to Elwassif on "lead and electrode self-heating". What holds is a reproduction:
    given Elwassif's own drive the model returns 0.83 K against their 0.82 K; their shaft
    is insulated and their source is tissue Joule heating alone."""

    DOCS = ("README.md", "CITATION.cff", "examples/worked_example.py")

    def test_the_documents_state_the_reproduction(self):
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        for name in self.DOCS:
            text = " ".join((root / name).read_text().split())
            # The cause they blamed; "omits electrode and lead self-heating" is a true
            # limitation of this model and stays.
            assert "includes lead and electrode self-heating" not in text, name
            assert "not reconciled" not in text, name
            assert "0.83 K" in text and "0.82 K" in text, name
        citation = (root / "CITATION.cff").read_text()
        assert "validated" not in citation.lower()


class TestTheReadmeMatchesTheDatabase:
    """Ledgers 74, 76 and 78/S-24, C7.4: the README's hand-written claims had drifted from
    the code -- PEDOT's range, a NOT PEER REVIEWED flag no material carries, "four of the
    five", Merrill cited for the water window, a primary-source list missing about eleven
    sources, and a conductivity default it did not name."""

    @staticmethod
    def _readme():
        from pathlib import Path

        return (Path(__file__).resolve().parents[1] / "README.md").read_text()

    def test_74_the_pedot_row_is_the_databases(self):
        from neurostim.materials import get_material

        pedot = get_material("PEDOT").cic
        row = next(line for line in self._readme().splitlines() if line.startswith("| `PEDOT`"))
        assert f"{pedot.low:g}\u2013{pedot.high:g}" in row and "15.0" not in row.split("|")[3]

    def test_76_no_flag_is_claimed_that_does_not_fire(self):
        from neurostim.materials import MATERIALS

        text = " ".join(self._readme().split())
        assert all(m.cic.peer_reviewed for m in MATERIALS.values())  # premise
        assert "flagged `NOT PEER REVIEWED` at every point of use" not in text
        assert "PEDOT's headline limit is not peer reviewed" not in text

    def test_s24_the_remaining_claims(self):
        text = " ".join(self._readme().split())
        assert "four of the five material values" not in text
        water = next(line for line in self._readme().splitlines() if line.startswith("| Water window |"))
        assert "Merrill" not in water
        assert "Primary sources:" not in text and "bibliography()" in text
        assert "0.35 S/m" in text
        assert "an order of magnitude across studies" not in text


PROVENANCE_AUDIT = REPO_ROOT / "scripts" / "provenance_audit.py"


def _load_provenance_audit() -> Any:
    spec = importlib.util.spec_from_file_location("provenance_audit", PROVENANCE_AUDIT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["provenance_audit"] = module
    spec.loader.exec_module(module)
    return module


class TestTheProvenanceGateIsStrict:
    """C7.6, T22 and G4. ``--strict`` failed on six gaps it could never close, so CI ran it
    without the flag and the gate always exited 0. Three were missing DOIs, now added from
    verified Crossref records (user decision D1). The three data gaps have no source and
    stay in a committed baseline that can only shrink."""

    @pytest.mark.parametrize(
        ("key", "doi"),
        [
            ("elwassif2006", "10.1109/IEMBS.2006.259425"),
            ("wang_weiland2012", "10.1109/EMBC.2012.6347150"),
            ("mccreery2008", "10.1016/j.heares.2007.11.014"),
        ],
    )
    def test_the_three_dois_are_the_verified_records(self, key: str, doi: str) -> None:
        from neurostim.references import cite

        assert cite(key).doi == doi

    def test_the_audit_finds_exactly_the_baseline(self) -> None:
        audit = _load_provenance_audit()
        assert sorted(audit.audit()) == sorted(audit.KNOWN_GAPS)
        assert len(audit.KNOWN_GAPS) == 3
        assert audit.main(["--strict"]) == 0

    def test_a_new_gap_fails_strict(self, monkeypatch: pytest.MonkeyPatch) -> None:
        audit = _load_provenance_audit()
        seeded = [*audit.KNOWN_GAPS, "Pt: charge-injection limit not primary-sourced"]
        monkeypatch.setattr(audit, "audit", lambda: seeded)
        assert audit.main(["--strict"]) == 1
        assert audit.main([]) == 0  # the report mode still never fails

    def test_a_closed_gap_must_leave_the_baseline(self, monkeypatch: pytest.MonkeyPatch) -> None:
        audit = _load_provenance_audit()
        monkeypatch.setattr(audit, "audit", lambda: list(audit.KNOWN_GAPS[1:]))
        assert audit.main(["--strict"]) == 1
        monkeypatch.setattr(audit, "audit", lambda: [])  # every gap closed, list not emptied
        assert audit.main(["--strict"]) == 1

    def test_ci_runs_it_strict(self) -> None:
        assert "python scripts/provenance_audit.py --strict" in CI_WORKFLOW.read_text()


VERIFY_TRANSCRIPTIONS = REPO_ROOT / "scripts" / "verify_transcriptions.py"


def _load_verify_transcriptions() -> Any:
    spec = importlib.util.spec_from_file_location("verify_transcriptions", VERIFY_TRANSCRIPTIONS)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["verify_transcriptions"] = module
    spec.loader.exec_module(module)
    return module


class TestTheTranscriptionCheckCanRequireItsPapers:
    """C7.6, user decision D2. The papers are not redistributed, so a checkout without the
    library skipped every claim and ``--strict`` still exited 0: the check could not fail
    where it could not look. ``--require-papers`` makes an absent paper a failure. It is
    the blocking gate in the local release checklist; CI has no library and stays
    informational, and says so."""

    def test_an_empty_library_passes_strict_but_fails_require_papers(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        vt = _load_verify_transcriptions()
        monkeypatch.setattr(vt.shutil, "which", lambda name: "/usr/bin/" + name)
        assert vt.main([str(tmp_path), "--strict"]) == 0  # the hole: all skipped
        assert vt.main([str(tmp_path), "--strict", "--require-papers"]) == 1

    def test_a_missing_directory_or_tool_fails_require_papers(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        vt = _load_verify_transcriptions()
        assert vt.main([str(tmp_path / "absent"), "--require-papers"]) == 1
        monkeypatch.setattr(vt.shutil, "which", lambda name: None)
        assert vt.main([str(tmp_path), "--require-papers"]) == 1

    def test_the_full_library_passes(self) -> None:
        import shutil

        vt = _load_verify_transcriptions()
        if shutil.which("pdftotext") is None or not vt.DEFAULT_PAPERS_DIR.is_dir():
            pytest.skip("paper library or poppler not present")
        assert vt.main(["--strict", "--require-papers"]) == 0

    def test_ci_stays_informational_and_says_so(self) -> None:
        ci = CI_WORKFLOW.read_text()
        assert "python scripts/verify_transcriptions.py\n" in ci
        runs = [
            line
            for line in ci.splitlines()
            if "python scripts/verify_transcriptions.py" in line and not line.strip().startswith("#")
        ]
        assert runs and not any("--require-papers" in line for line in runs)
        assert "informational" in ci


class TestTheCiToolchainIsPinnedAndComplete:
    """C7.6, T21 and T25. The PDF-text tests skipped on every CI interpreter because the
    test job had no poppler. Every run resolved the latest ruff and mypy, so a new release
    could turn CI red with no change in the repository. pytest-cov was not in the dev extra.
    The branch-point floor sat at the audit baseline of 48.0 % against 71.49 % measured."""

    @staticmethod
    def _dev_extra() -> list[str]:
        import re

        text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        line = next(ln for ln in text.splitlines() if ln.startswith("dev = ["))
        return re.findall(r'"([^"]+)"', line)

    def test_ruff_and_mypy_are_pinned_exactly(self) -> None:
        dev = self._dev_extra()
        for tool in ("ruff", "mypy", "pytest", "pytest-cov", "coverage"):
            pins = [d for d in dev if d.split("=")[0].split(">")[0] == tool]
            assert len(pins) == 1 and "==" in pins[0], (tool, dev)

    def test_the_test_job_can_read_pdfs(self) -> None:
        job = _ci_job("test")
        assert "poppler-utils" in job
        assert "brew install poppler" in job

    def test_the_coverage_floor_is_ratcheted(self) -> None:
        import re

        job = _ci_job("coverage")
        match = re.search(
            r"branch_floor\.py --json coverage\.json --min ([0-9.]+) "
            r"--module-min ([0-9.]+) --module-min-points ([0-9]+)",
            job,
        )
        assert match is not None
        # G12: was `floor >= 71.0` (C7.6c). G3 is now met, so the floor is its target or
        # above, overall and per module.
        assert float(match[1]) >= 80.0
        assert float(match[2]) >= 60.0 and int(match[3]) <= 4


def test_ci_type_checks_the_tests() -> None:
    """C7.6, T26: the tests are type-checked with the package."""
    assert "run: mypy neurostim tests\n" in _ci_job("lint")


class TestTheChangelogCarriesARecallNotice:
    """C7.7. Reports made before 0.16.0 print a limiting current up to 7.07x too high, and
    copies of them exist outside the repository where no commit can reach them. The
    CHANGELOG is where a user of an old report will look, so the notice leads 0.16.0."""

    @staticmethod
    def _section() -> str:
        text = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        start = text.index("## 0.16.0")
        return text[start : text.index("\n## ", start + 1)]

    def test_the_notice_leads_the_release(self) -> None:
        section = self._section()
        first_heading = section.index("\n### ")
        assert section[first_heading:].startswith("\n### Recall notice")

    def test_it_names_the_defect_the_factor_and_the_versions(self) -> None:
        notice = self._section().split("\n### ")[1]
        text = " ".join(notice.split())
        assert "7.07" in text and "141.4" in text and "20.00" in text
        assert "0.15.0" in text and "every earlier release" in text
        assert "three" in text and "nine" in text  # the three-check minimum over nine

    def test_it_lists_the_headline_numbers_that_move(self) -> None:
        notice = " ".join(self._section().split("\n### ")[1].split())
        for moved in ("9.11", "on-time", "Compliance", "8.061 mK"):
            assert moved in notice, moved

    def test_it_lists_every_non_conservative_class(self) -> None:
        """Ledger 177 (Phase 7 review S3): the classes where an old report erred unsafe,
        each with the example booked in FIX_PLAN_v2.md §6."""
        notice = " ".join(self._section().split("\n### ")[1].split())
        for example in (
            "1.529e+04", "0.256 s",  # monophasic
            "15285.51", "9565.66",  # asymmetric return
            "refuses a number", "0.42 s", "988.34",  # unbalanced and continuous trains
            "\u00d72/\u03c0", "\u00d7\u03c0/2", "28571",  # access resistance
            "\u00d72.00",  # planar field
            "117.48",  # small-electrode current density
            "NOT_EVALUATED", "never PASS", "fit on discs",  # status vocabulary
        ):
            assert example in notice, example


MUTATION = REPO_ROOT / "scripts" / "mutation.py"


def _load_mutation() -> Any:
    spec = importlib.util.spec_from_file_location("mutation", MUTATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["mutation"] = module
    spec.loader.exec_module(module)
    return module


class TestTheMutationGate:
    """C7.6, G2 and user decision D3. The audit's 42 mutants came from a script that no
    longer exists; 26 are recoverable from its report and are re-anchored by code text. A
    generated set, sampled with a fixed seed, is what a fixed list cannot give."""

    def test_the_26_recoverable_named_mutants_all_fit_the_code(self) -> None:
        mutation = _load_mutation()
        assert len(mutation.NAMED) == 26
        assert len({m.id for m in mutation.NAMED}) == 26
        for m in mutation.NAMED:
            source = (REPO_ROOT / m.path).read_text(encoding="utf-8")
            assert mutation.apply(m, source) != source, m.id

    def test_a_stale_anchor_is_refused(self) -> None:
        mutation = _load_mutation()
        m = mutation.NAMED[0]
        with pytest.raises(ValueError, match="expected once"):
            mutation.apply(m, "nothing here\n")

    def test_the_generated_set_is_fixed_and_large_enough(self) -> None:
        mutation = _load_mutation()
        first, second = mutation.generated_sample(), mutation.generated_sample()
        assert first == second and len(first) == 160
        assert len(mutation.enumerate_sites()) >= 150
        for m in first:
            source = (REPO_ROOT / m.path).read_text(encoding="utf-8")
            assert mutation.apply(m, source) != source, m.id

    @staticmethod
    def _report(mutation: Any, named: str = "killed", killed: int = 160) -> dict[str, Any]:
        return {
            "named": [{"id": m.id, "status": named, "description": ""} for m in mutation.NAMED],
            "generated": [
                {"id": str(i), "status": "killed" if i < killed else "survived"}
                for i in range(160)
            ],
        }

    def test_the_gate_fails_a_surviving_named_mutant(self) -> None:
        mutation = _load_mutation()
        assert mutation.gate(self._report(mutation)) == []
        assert mutation.gate(self._report(mutation, named="survived"))
        assert mutation.gate(self._report(mutation, named="stale"))

    def test_the_gate_fails_a_generated_score_under_its_floor(self) -> None:
        # G12: this pinned 144/160 = 90.0 %, then the 0.86 floor of seed 20260929. The
        # floor is now the measured 0.89 on the Phase 8 official seed 20260930 (ledger
        # 182): 143/160 = 89.4 % passes, 142 fails. Rise only.
        mutation = _load_mutation()
        assert mutation.GENERATED_FLOOR == 0.89
        assert mutation.gate(self._report(mutation, killed=143)) == []
        assert mutation.gate(self._report(mutation, killed=142))
        report = json.loads(mutation.RESULTS.read_text(encoding="utf-8"))
        assert report["generated_score"] >= mutation.GENERATED_FLOOR
        assert report["seed"] == mutation.SEED == 20260930

    def test_the_committed_results_meet_the_gate(self) -> None:
        mutation = _load_mutation()
        report = json.loads(mutation.RESULTS.read_text(encoding="utf-8"))
        assert mutation.gate(report) == []
        assert [o["id"] for o in report["named"]] == [m.id for m in mutation.NAMED]

    def test_every_judgement_still_names_a_site(self) -> None:
        """Ledger 182: judgements are keyed by site, and a stale one must not linger."""
        mutation = _load_mutation()
        sites = mutation.enumerate_sites()
        for entry in mutation.JUDGEMENTS:
            assert any(
                site.path == entry[0] and mutation.judgement(site) == entry[4] for site in sites
            ), entry[:4]

    def test_ci_runs_it_on_demand_and_weekly(self) -> None:
        workflow = (REPO_ROOT / ".github" / "workflows" / "mutation.yml").read_text()
        assert "workflow_dispatch:" in workflow and "schedule:" in workflow
        assert "python scripts/mutation.py --check-anchors" in workflow
        assert "push:" not in workflow and "pull_request:" not in workflow


class TestContributingCarriesTheRulesTheGatesDependOn:
    """C7.5. The ledger gate asserts recorded hashes exist, which a squash-merge or rebase
    breaks; the transcription and mutation gates only block when run by hand."""

    @staticmethod
    def _text() -> str:
        return " ".join((REPO_ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8").split())

    def test_the_merge_policy(self) -> None:
        text = self._text()
        assert "no squash-merge, no rebase onto the default branch" in text
        assert "do not squash" in text and "do not force-push the default branch" in text

    def test_the_release_checklist(self) -> None:
        text = self._text()
        assert "python scripts/verify_transcriptions.py --strict --require-papers" in text
        assert "python scripts/mutation.py" in text and "mutation_results.json" in text

    def test_the_gates_match_ci(self) -> None:
        text = self._text()
        ci = CI_WORKFLOW.read_text(encoding="utf-8")
        for command in (
            "ruff check neurostim tests examples",
            "mypy neurostim tests",
            "python scripts/ledger_check.py",
            "python scripts/regenerate_example_output.py --check",
            "python scripts/provenance_audit.py --strict",
            "python scripts/build_api_docs.py",
        ):
            assert command in text and command in ci, command


class TestTheGuiTestsSkipWithoutQtSystemLibraries:
    """Ledger 175 (Phase 7 review S1). A runner with PyQt6 installed but no libEGL raises
    ``ImportError`` (not ``ModuleNotFoundError``) on ``import PyQt6.QtWidgets``. Under
    pytest 9.1 ``importorskip`` re-raises that by default, so test_gui.py errored at
    collection and failed the whole run. A stub PyQt6 that raises the same error stands in
    for the runner."""

    def test_the_gui_tests_skip_instead_of_erroring(self, tmp_path: Path) -> None:
        stub = tmp_path / "PyQt6"
        stub.mkdir()
        (stub / "__init__.py").write_text(
            'raise ImportError("libEGL.so.1: cannot open shared object file")\n'
        )
        env = {**os.environ, "PYTHONPATH": str(tmp_path), "QT_QPA_PLATFORM": "offscreen"}
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
             "tests/test_gui.py", "tests/test_verdict_core.py", "-k",
             "test_gui or gui_headline or TestLimitsIncompleteAndByKind"],
            cwd=REPO_ROOT, env=env, capture_output=True, text=True, check=False,
        )
        assert result.returncode == 0, result.stdout[-2000:]
        assert "skipped" in result.stdout and "error" not in result.stdout.lower()


def test_the_coverage_job_installs_what_the_test_job_installs() -> None:
    """Ledger 175: the floor is measured over the suite as the test job runs it."""
    import re

    def packages(job: str) -> set[str]:
        text = _ci_job(job)
        start = text.index("sudo apt-get install -y")
        block = text[start : text.index("\n\n", start) if "\n\n" in text[start:] else None]
        return set(re.findall(r"\b(?:poppler-utils|lib[\w.-]+)", block))

    assert "poppler-utils" in packages("coverage")
    assert packages("coverage") == packages("test")


BUILD_API_DOCS = REPO_ROOT / "scripts" / "build_api_docs.py"


def _load_build_api_docs() -> Any:
    spec = importlib.util.spec_from_file_location("build_api_docs", BUILD_API_DOCS)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["build_api_docs"] = module
    spec.loader.exec_module(module)
    return module


class TestTheApiReferenceBuilds:
    """Phase 7 review (7) and the user's request: an API reference generated from the
    docstrings with pdoc, built locally and in CI with every warning an error, not hosted."""

    def test_every_module_gets_a_page(self, tmp_path: Path) -> None:
        pytest.importorskip("pdoc")
        pytest.importorskip("PyQt6.QtWidgets", exc_type=ImportError)  # neurostim.gui
        docs = _load_build_api_docs()
        pages = {p.relative_to(tmp_path).as_posix() for p in docs.build(tmp_path)}
        for name in docs.modules():
            assert name.replace(".", "/") + ".html" in pages, name
        text = (tmp_path / "neurostim" / "models" / "strength_duration.html").read_text()
        assert "fit_lapicque" in text and "not identifiable" in text

    def test_a_warning_fails_the_build(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        pytest.importorskip("pdoc")
        docs = _load_build_api_docs()
        (tmp_path / "noisy_module.py").write_text(
            '"""A module that warns on import."""\nimport warnings\nwarnings.warn("seeded")\n'
        )
        monkeypatch.syspath_prepend(str(tmp_path))
        # pdoc reports the warning, raised as an error, as a failed import of the module.
        with pytest.raises(RuntimeError, match="Error importing noisy_module"):
            docs.build(tmp_path / "out", names=["noisy_module"])

    def test_ci_builds_it_and_the_tool_is_pinned(self) -> None:
        assert "python scripts/build_api_docs.py" in _ci_job("api-docs")
        pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        assert '"pdoc==' in pyproject
        assert "docs/api/" in (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")


class TestTheLicenceIsTheOneTheMetadataDeclares:
    """C7.1 (packaging, CRITICAL). pyproject and CITATION have always said MIT; there was
    no LICENSE file. Holder and year are the user's: Kshitij Kumar, 2026."""

    def test_the_mit_licence_is_present_with_its_holder(self) -> None:
        text = (REPO_ROOT / "LICENSE").read_text(encoding="utf-8")
        assert text.startswith("MIT License\n\nCopyright (c) 2026 Kshitij Kumar\n")
        assert "Permission is hereby granted, free of charge" in text
        assert 'THE SOFTWARE IS PROVIDED "AS IS"' in text
        assert "<year>" not in text and "<copyright holders>" not in text

    def test_the_metadata_agrees(self) -> None:
        assert 'license = { text = "MIT" }' in (REPO_ROOT / "pyproject.toml").read_text()
        assert "\nlicense: MIT\n" in (REPO_ROOT / "CITATION.cff").read_text()


class TestTheCitationHasNoPlaceholders:
    """Ledger 180 (Phase 7 review S6) and G8. CITATION.cff named "neurostim-safety
    contributors" and a https://github.com/example/ repository. The author is the user's:
    Kshitij Kumar, Indian Institute of Technology Kanpur. ORCID, repository URL, DOI and
    release date are intentionally absent -- none exists yet -- rather than invented."""

    @staticmethod
    def _text() -> str:
        return (REPO_ROOT / "CITATION.cff").read_text(encoding="utf-8")

    def test_the_author_is_named_with_the_affiliation(self) -> None:
        text = self._text()
        assert "  - given-names: Kshitij\n    family-names: Kumar\n" in text
        assert "    affiliation: Indian Institute of Technology Kanpur, India\n" in text

    def test_no_placeholder_or_invented_identifier_remains(self) -> None:
        text = self._text()
        for placeholder in ("contributors", "example", "TODO", "XXXX"):
            assert placeholder not in text, placeholder
        keys = {line.split(":")[0] for line in text.splitlines() if line and line[0].isalpha()}
        assert not keys & {"repository-code", "doi", "date-released", "url"}
        assert "orcid" not in text.lower() or "intentionally absent" in text


class TestTheCodeOfConductNamesItsContact:
    """C7.5. The Contributor Covenant 2.1, with its one placeholder filled by the user's
    choice of contact: the project maintainer, Kshitij Kumar, as a named person with no
    address (JOSS and community practice prefer a reachable address; to be added)."""

    def test_the_covenant_is_present_and_complete(self) -> None:
        text = (REPO_ROOT / "CODE_OF_CONDUCT.md").read_text(encoding="utf-8")
        assert text.lstrip().startswith("# Contributor Covenant Code of Conduct")
        assert "version 2.1" in text
        assert "[INSERT" not in text
        assert "the project maintainer, Kshitij Kumar" in text

    def test_contributing_points_to_it(self) -> None:
        assert "CODE_OF_CONDUCT.md" in (REPO_ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")


class TestThePaper:
    """C7.5. The JOSS paper: the author block the user gave, a bibliography of exactly the
    sources cited (each with a DOI, verified before it was written), and the limitations
    the record holds open. ORCID, repository URL and DOI are intentionally absent."""

    @staticmethod
    def _paper() -> str:
        return (REPO_ROOT / "paper.md").read_text(encoding="utf-8")

    @staticmethod
    def _bib_keys() -> set[str]:
        import re

        bib = (REPO_ROOT / "paper.bib").read_text(encoding="utf-8")
        return set(re.findall(r"^@\w+\{([^,]+),", bib, flags=re.M))

    def test_the_front_matter(self) -> None:
        front = self._paper().split("---")[1]
        assert "  - name: Kshitij Kumar\n    affiliation: 1\n    corresponding: true\n" in front
        assert "  - name: Indian Institute of Technology Kanpur, India\n    index: 1\n" in front
        assert "bibliography: paper.bib" in front
        assert "orcid" not in front.lower()

    def test_the_bibliography_is_exactly_what_is_cited(self) -> None:
        import re

        cited = set(re.findall(r"@([A-Za-z][\w]*)", self._paper().split("---", 2)[2]))
        assert cited == self._bib_keys()

    def test_every_entry_has_a_doi(self) -> None:
        import re

        bib = (REPO_ROOT / "paper.bib").read_text(encoding="utf-8")
        entries = re.split(r"\n(?=@)", bib.strip())
        entries = [e for e in entries if e.startswith("@")]
        assert len(entries) == len(self._bib_keys())
        for entry in entries:
            assert re.search(r"doi\s*=\s*\{10\.\d{4,}/", entry), entry.splitlines()[0]

    def test_the_sections_and_length(self) -> None:
        import re

        body = self._paper().split("---", 2)[2]
        for heading in ("# Summary", "# Statement of need", "# Limitations", "# References"):
            assert heading in body, heading
        assert 250 <= len(re.findall(r"\b\w+\b", body)) <= 1000  # JOSS's guidance

    def test_the_limitations_are_the_open_ones(self) -> None:
        text = " ".join(self._paper().split())
        # G12: ledger 174 is closed (cited, Phase 8); ledger 188 is the open gap now.
        for item in ("ledger 182", "ledger 183", "ledger 188", "@weiland2002", "@itis_v42",
                     "@riedy_walter1996", "references 5 and 8", "provisional"):
            assert item in text, item


class TestPulseWidthIsPerPhase:
    """Ledger 187 (Phase 8, found by running the package). ``pulse_width_us`` is the width
    of the leading phase; a user read 200 us as the whole biphasic pulse. Every surface a
    user enters or reads it on says "per phase"."""

    def test_the_protocol_docstring_and_describe(self) -> None:
        from neurostim import StimProtocol

        assert StimProtocol.__doc__ is not None
        assert "per phase" in StimProtocol.__doc__.splitlines()[0]
        assert "40 uA x 200 us per phase @ 130 Hz" in StimProtocol(40, 200, 130, 1).describe()

    def test_the_readme_quick_start(self) -> None:
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        assert "StimProtocol(80, 200, 130, 1)       # µA, µs per phase, Hz, s" in readme

    def test_the_pdf_row_and_the_batch_columns(self) -> None:
        from neurostim.io import report, tabular

        assert '("Pulse width per phase",' in (REPO_ROOT / "neurostim" / "io" / "report.py").read_text()
        assert report is not None
        assert tabular.assess_batch.__doc__ is not None
        assert "``pulse_width_us`` is per phase" in " ".join(tabular.assess_batch.__doc__.split())

    def test_the_gui_label_and_tooltip(self) -> None:
        pytest.importorskip("PyQt6.QtWidgets", exc_type=ImportError)
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6.QtWidgets import QApplication, QLabel

        from neurostim.gui.app import SafetyWindow

        _app = QApplication.instance() or QApplication([])
        window = SafetyWindow()
        labels = [w.text() for w in window.findChildren(QLabel)]
        assert "Pulse width per phase (us)" in labels
        assert "leading phase" in window.pulse_width.toolTip()
