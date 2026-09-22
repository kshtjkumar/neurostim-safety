"""Phase 1 -- the verdict core.

Everything the package says about *how much current is safe* is settled here: the
status ordering, the flooring of every reported limit, the per-check margin, the
refusal to report a limit at all when no amplitude is safe, and the minimum that
produces the headline.

Expected values in this file come from one of three places, never from the code path
under test:

* ``tests.oracles`` -- an independently written binary search over ``assess().failed``,
  which reads one bit per probe and no package-computed number;
* IEEE float semantics (``math.nextafter``), which is the definition of "floors";
* a literature constant quoted in the test, back-solved by hand in the docstring.
"""

from __future__ import annotations

import pytest

from neurostim import (
    DiscElectrode,
    SafetyCalculator,
    StimProtocol,
)
from neurostim.safety.assessment import Status


def pdf_text(calc: SafetyCalculator, path) -> str:
    """Render the PDF report and return its extracted text, whitespace collapsed.

    ``pdftotext`` rather than a Python PDF reader because that is what the rest of the
    suite uses and what is installed; the point of extracting at all is that the assertion
    lands on what reaches the page, not on the string the renderer assembled.
    """
    import re
    import shutil
    import subprocess

    from neurostim.io import build_report

    if shutil.which("pdftotext") is None:  # pragma: no cover - environment dependent
        pytest.skip("pdftotext (poppler) not available")
    out = build_report(calc, path)
    raw = subprocess.run(
        ["pdftotext", "-layout", str(out), "-"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return re.sub(r"\s+", " ", raw)


class TestStatusRank:
    """NOT_EVALUATED must sit below PASS (ledger 11, fix plan D1).

    Today ``PASS.rank == 0`` and ``NOT_EVALUATED.rank == 1``, so ``_worst`` -- a max over
    ranks -- makes an overall PASS unreachable for any macroelectrode: three of the nine
    checks do not apply above the macro/micro boundary and their NOT_EVALUATED outranks
    every PASS beside them.
    """

    def test_rank_order_is_not_evaluated_pass_caution_fail(self):
        """Four explicit inequalities, written out rather than derived from the mapping.

        Not tautological: each side is a literal member of the enum and the expected
        ordering is stated here, so a mapping that reorders any pair fails this.
        """
        assert Status.NOT_EVALUATED.rank < Status.PASS.rank
        assert Status.PASS.rank < Status.CAUTION.rank
        assert Status.CAUTION.rank < Status.FAIL.rank
        assert Status.NOT_EVALUATED.rank < Status.FAIL.rank

    def test_a_macroelectrode_within_every_applicable_limit_reports_pass(self):
        """T17. A 2 mm SIROF disc at 20 uA / 400 us / 50 Hz passes everything that ran.

        Not tautological: the expected status is named literally (``Status.PASS``) and the
        case is one where three checks are genuinely NOT_EVALUATED -- Microelectrode
        charge/phase and Chronic degradation do not apply, and no compliance voltage was
        supplied -- so it is exactly the configuration today's ordering makes unreachable.
        """
        calc = SafetyCalculator(
            DiscElectrode(2000.0, "SIROF"), StimProtocol(20, 400, 50, 3600)
        )
        assessment = calc.assess()

        assert {c.status for c in assessment.checks} == {
            Status.PASS,
            Status.NOT_EVALUATED,
        }
        assert assessment.status is Status.PASS

    def test_a_check_that_did_not_run_cannot_be_the_overall_verdict(self):
        """The same case, stated as the property rather than the instance.

        Not tautological: it compares the overall status against the worst status among
        the checks that *ran*, computed here from the check list, not from
        ``assessment.status``.
        """
        calc = SafetyCalculator(
            DiscElectrode(2000.0, "SIROF"), StimProtocol(20, 400, 50, 3600)
        )
        assessment = calc.assess()
        ran = [c for c in assessment.checks if c.status is not Status.NOT_EVALUATED]

        assert ran
        assert assessment.status is max(
            (c.status for c in ran), key=lambda s: s.rank
        )


class TestUnevaluatedChecksAreDisclosed:
    """A bare ``PASS`` over a knowingly incomplete check set is less informative than
    today's ``NOT_EVALUATED``. Every headline surface must name what did not run
    (fix plan D1, execution M9).
    """

    @staticmethod
    def _macro_calc() -> SafetyCalculator:
        return SafetyCalculator(
            DiscElectrode(2000.0, "SIROF"), StimProtocol(20, 400, 50, 3600)
        )

    def test_not_evaluated_collects_the_checks_that_did_not_run(self):
        """Not tautological: the expected names are written out, and the count is the
        literal 3, neither read from the assessment."""
        assessment = self._macro_calc().assess()

        assert [c.name for c in assessment.not_evaluated] == [
            "Microelectrode charge/phase",
            "Chronic degradation",
            "Compliance voltage",
        ]

    def test_describe_names_the_checks_that_did_not_run(self):
        """Not tautological: the expected substring is a literal, and the assertion that
        the overall line carries it rules out a disclosure printed somewhere a reader of
        the headline would not see."""
        text = self._macro_calc().describe()
        overall = next(
            line for line in text.splitlines() if line.startswith("Overall:")
        )

        assert "PASS" in overall
        assert "3 checks not evaluated" in overall
        assert "Compliance voltage" in overall

    def test_report_to_json_discloses_the_checks_that_did_not_run(self):
        """Not tautological: the expected list is written out, against a payload key that
        does not exist today.

        Top-level rather than inside ``results``: ``results`` is ``calc.report()``, whose
        keys become columns of ``current_sweep.csv``, and a list does not belong in a CSV
        cell.
        """
        import json

        from neurostim.io import report_to_json

        payload = json.loads(report_to_json(self._macro_calc()))

        assert payload["not_evaluated"] == [
            "Microelectrode charge/phase",
            "Chronic degradation",
            "Compliance voltage",
        ]

    def test_the_pdf_header_discloses_the_checks_that_did_not_run(self, tmp_path):
        """Not tautological: the PDF is rendered and its text extracted with pdftotext, so
        the assertion is on what a reader sees, not on the string the code assembled."""
        text = pdf_text(self._macro_calc(), tmp_path / "report.pdf")

        assert "3 checks not evaluated" in text
        assert "Compliance voltage" in text

    def test_an_assessment_with_every_check_run_says_nothing_about_unevaluated(self):
        """The disclosure must not fire when there is nothing to disclose.

        Not tautological: the fixture is a distinct configuration -- a 250 um Pt disc in
        the macro/micro transition band with a compliance voltage supplied, so all nine
        checks run -- and the assertion is that the parenthetical is absent.
        """
        calc = SafetyCalculator(
            DiscElectrode(250.0, "Pt"),
            StimProtocol(5, 200, 130, 1),
            compliance_V=10.0,
        )
        assessment = calc.assess()

        assert assessment.not_evaluated == ()
        overall = next(
            line
            for line in assessment.describe().splitlines()
            if line.startswith("Overall:")
        )
        assert "not evaluated" not in overall


class TestRestingPotentialIsInsideTheWindow:
    """An electrode already outside its own water window at rest is rejected, not
    assessed (ledger 14, fix plan D2 point 3).

    Two reasons, and the second is why this lands here rather than six commits later.
    The visible one: ``max_charge_density_in_window_uC_cm2("Pt",
    resting_potential_V=5.0)`` returns 1400 uC/cm^2 "allowed" for an interface 4.2 V past
    its anodic limit before any current flows. The structural one: the water-window
    predicate is non-monotone in current for exactly these inputs -- a small cathodic
    pulse pulls the interface back INTO the window while a large one breaches the charge
    limits, so the verdict runs FAIL, PASS, FAIL -- and the next commit introduces
    ``floor_to_pass``, which is only correct for a monotone-decreasing predicate. Phase 0b
    swept 1824 configurations: every non-monotone case was an out-of-window resting
    potential, and across 630 in-window configurations there were none. Rejecting the
    input makes the precondition true rather than merely asserted.
    """

    def test_the_calculator_refuses_a_resting_potential_past_the_anodic_limit(self):
        """Not tautological: 0.9 V and Pt's +0.8 V anodic limit are both literals here,
        the second quoted from the material database's stored window, and the expected
        outcome is a raise rather than any number the package computes."""
        with pytest.raises(ValueError, match=r"resting_potential_V"):
            SafetyCalculator(
                DiscElectrode(100.0, "Pt"),
                StimProtocol(80, 200, 130, 1),
                compliance_V=10.0,
                resting_potential_V=0.9,
            )

    def test_the_message_names_the_window_it_is_outside(self):
        """Not tautological: the three quantities the message must carry are written out
        here -- the offending value, the material, and both window bounds."""
        with pytest.raises(ValueError) as raised:
            SafetyCalculator(
                DiscElectrode(100.0, "Pt"),
                StimProtocol(80, 200, 130, 1),
                resting_potential_V=0.9,
            )
        message = str(raised.value)

        assert "0.9" in message
        assert "Pt" in message
        assert "-0.6" in message and "0.8" in message

    def test_the_calculator_refuses_a_resting_potential_past_the_cathodic_limit(self):
        """The other side. Not tautological: -0.7 V against Pt's stored -0.6 V."""
        with pytest.raises(ValueError, match=r"resting_potential_V"):
            SafetyCalculator(
                DiscElectrode(100.0, "Pt"),
                StimProtocol(80, 200, 130, 1),
                resting_potential_V=-0.7,
            )

    def test_a_resting_potential_on_the_boundary_is_accepted(self):
        """The window is closed: ``WaterWindow.contains`` is inclusive at both ends, and
        the rejection must use the same inclusivity or it contradicts the check it
        protects.

        Not tautological: +0.8 is Pt's stored anodic limit, written out, and the assertion
        is that construction succeeds -- the opposite outcome from the tests above.
        """
        calc = SafetyCalculator(
            DiscElectrode(100.0, "Pt"),
            StimProtocol(80, 200, 130, 1),
            resting_potential_V=0.8,
        )
        assert calc.resting_potential_V == 0.8

    def test_a_material_with_no_window_on_record_accepts_any_resting_potential(self):
        """Ta2O5 has no water window in the database, so there is nothing to be outside
        of and the check itself reports NOT_EVALUATED.

        Not tautological: Ta2O5 is named literally, 5.0 V is a value every windowed
        material would reject, and the expected outcome is construction plus a
        NOT_EVALUATED water-window check.
        """
        calc = SafetyCalculator(
            DiscElectrode(100.0, "Ta2O5"),
            StimProtocol(80, 200, 130, 1),
            resting_potential_V=5.0,
        )
        window = next(
            c for c in calc.assess().checks if c.name == "Water window"
        )
        assert window.status is Status.NOT_EVALUATED

    def test_the_module_function_refuses_what_it_used_to_answer(self):
        """Ledger 14's own reproduction.

        Not tautological: the expected outcome is a raise where the recorded defect is the
        specific number 1400.0, so the test would fail both before the fix and under any
        fix that kept returning a charge density.
        """
        from neurostim.safety import water_window as ww

        with pytest.raises(ValueError, match=r"resting_potential_V"):
            ww.max_charge_density_in_window_uC_cm2("Pt", resting_potential_V=5.0)

    def test_the_evaluate_entry_point_refuses_it_too(self):
        """``evaluate`` is exported and callable directly, so the guard cannot live only
        in the calculator.

        Not tautological: the raise is asserted at a second entry point with its own
        signature, not inferred from the first.
        """
        from neurostim.safety import water_window as ww

        with pytest.raises(ValueError, match=r"resting_potential_V"):
            ww.evaluate("Pt", 10.0, resting_potential_V=0.9)

    def test_an_in_window_resting_potential_still_works(self):
        """The guard must not reject the case it exists to protect.

        Not tautological: +0.3 V is inside Pt's window and the assertion is on the
        assessment running to completion and reporting that potential back.
        """
        calc = SafetyCalculator(
            DiscElectrode(100.0, "Pt"),
            StimProtocol(80, 200, 130, 1),
            resting_potential_V=0.3,
        )
        assert calc.assess().water_window.resting_potential_V == 0.3
