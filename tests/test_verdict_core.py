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


class TestFloorToPass:
    """The helper itself: ``_limits.floor_to_pass`` and ``_limits.format_limit``
    (fix plan D2, ledger 9 and 49).

    A reported limit is a promise: programme this and the check passes. Two things broke
    it. The back-solve recomputed the limit through a different float association than the
    forward comparison, so the answer could land one ulp on the wrong side (ledger 9); and
    every render site formatted with round-to-nearest, which rounds a maximum UP
    (ledger 49). Both are fixed by the same contract -- return, and print, the largest
    value that still passes.
    """

    def test_it_steps_down_to_the_largest_passing_value(self):
        """Not tautological: the predicate is written here as a comparison against a
        literal, so the expected answer is the largest float at or below that literal --
        an IEEE fact, not a package one."""
        import math

        from neurostim.safety import _limits

        limit = 100.0
        overshoot = math.nextafter(limit, math.inf)

        settled = _limits.floor_to_pass(
            overshoot, lambda v: v <= limit, name="synthetic"
        )
        assert settled == limit

    def test_it_steps_up_when_the_back_solve_undershot(self):
        """Flooring is "the largest value that passes", which is not always downward.

        Measured on the real back-solves: of 108 (material, policy, polarity) x
        (charge, Shannon) limits, 12 sit one ulp above their own boundary and 4 sit one
        ulp below it. A one-directional helper would leave the second group reporting a
        limit that is not the limit.

        Not tautological: the expected answer is again the literal boundary, reached from
        the other side.
        """
        import math

        from neurostim.safety import _limits

        limit = 100.0
        undershoot = math.nextafter(limit, -math.inf)

        settled = _limits.floor_to_pass(
            undershoot, lambda v: v <= limit, name="synthetic"
        )
        assert settled == limit

    def test_the_returned_value_is_asserted_to_be_the_boundary(self):
        """D2 point 1: ``passes(v)`` and not ``passes(nextafter(v, +inf))``.

        Not tautological: the assertion is made here, independently, on whatever the
        helper returned.
        """
        import math

        from neurostim.safety import _limits

        settled = _limits.floor_to_pass(
            1.0000000000000002, lambda v: v <= 1.0, name="synthetic"
        )
        assert settled <= 1.0
        assert not (math.nextafter(settled, math.inf) <= 1.0)

    def test_exhausting_the_step_budget_raises_and_names_the_check(self):
        """Returning the failing value would be a silent failure; leaving the budget
        unstated is how a future non-linear check degrades quietly (D2 point 2).

        Not tautological: the predicate written here never passes, so no value the helper
        could return would be correct, and the expected outcome is the raise.
        """
        from neurostim.safety import _limits

        with pytest.raises(_limits.LimitDidNotSettle) as raised:
            _limits.floor_to_pass(50.0, lambda v: False, name="Chronic degradation")
        message = str(raised.value)

        assert "Chronic degradation" in message
        assert "50" in message
        assert "4" in message  # the step budget

    def test_a_non_finite_or_non_positive_value_is_returned_unchanged(self):
        """``inf`` means "no ceiling" and ``0.0`` means "nothing is permitted"; neither is
        a float to be walked, and neither has a successor that means anything.

        Not tautological: three literal inputs, three literal expected outputs.
        """
        import math

        from neurostim.safety import _limits

        never = lambda v: False  # noqa: E731 - the point is that it is never consulted
        assert _limits.floor_to_pass(math.inf, never, name="x") == math.inf
        assert _limits.floor_to_pass(0.0, never, name="x") == 0.0
        assert math.isnan(_limits.floor_to_pass(math.nan, never, name="x"))


class TestFormatLimit:
    """A limit must never be printed larger than it is (ledger 49)."""

    def test_the_worked_example_headline_floors(self):
        """Not tautological: 141.37166941154072 and the expected "141.3" are both written
        out, and 141.4 -- what ``:.4g`` prints -- is asserted absent."""
        from neurostim.safety._limits import format_limit

        assert format_limit(141.37166941154072) == "141.3"

    def test_the_shannon_limit_floors(self):
        """Ledger 49's second recorded case. Not tautological: both literals are quoted
        from the ledger entry."""
        from neurostim.safety._limits import format_limit

        assert format_limit(472.78772824642175) == "472.7"

    def test_the_printed_number_never_exceeds_the_value_it_floors(self):
        """The property, over a decade-spanning grid rather than one case.

        Not tautological: the comparison is between the float the string parses back to
        and the input float -- arithmetic on the test's own values, with the package only
        supplying the formatter.
        """
        from neurostim.safety._limits import format_limit

        values = [
            base * 10.0**exponent
            for exponent in range(-6, 7)
            for base in (1.0, 1.0000001, 1.4999, 1.5, 1.9999, 3.14159265, 9.99999)
        ]
        for value in values:
            printed = format_limit(value)
            assert float(printed) <= value, f"{printed} exceeds {value!r}"

    def test_four_significant_digits_are_kept(self):
        """Flooring must not become truncation to the integer.

        Not tautological: the expected strings are written out for values whose fourth
        significant digit is where the information is.
        """
        from neurostim.safety._limits import format_limit

        assert format_limit(0.0012345678) == "0.001234"
        assert format_limit(15285.509415880857) == "1.528e+04"
        # Trailing zeros are kept: four significant digits is the promise, and "20" would
        # claim only two. This is the form the fix plan's blast radius records.
        assert format_limit(20.0) == "20.00"
        assert format_limit(212.05750411731108) == "212.0"

    def test_it_does_not_invent_a_number_for_infinity(self):
        """Not tautological: the expected output is the same token ``:.4g`` produces, so
        no surface starts printing a finite ceiling where there is none."""
        import math

        from neurostim.safety._limits import format_limit

        assert format_limit(math.inf) == "inf"


class TestEveryBackSolvedLimitPassesItsOwnCheck:
    """T2a. Re-assess at the package's own reported limit and the check must pass.

    Measured before the fix: over 9 materials x 3 policies x 2 polarities, 12 of the 54
    charge-injection limits and 0 of the 54 Shannon limits FAIL their own forward check,
    surfacing as "100 uC/cm^2 exceeds the 100 uC/cm^2 limit" (ledger 9). A further 4
    charge limits sit one ulp *below* their boundary.
    """

    @staticmethod
    def _cases():
        from dataclasses import replace

        from neurostim.materials import MATERIALS

        electrode = DiscElectrode(100.0, "Pt")
        base = StimProtocol(80.0, 200.0, 130.0, 1.0)
        for material in MATERIALS:
            for policy in ("conservative", "nominal", "optimistic"):
                for anodic_first in (False, True):
                    protocol = replace(base, anodic_first=anodic_first)
                    yield material, policy, protocol, electrode

    @staticmethod
    def _at(electrode, protocol, current_uA, material, policy):
        from dataclasses import replace

        return SafetyCalculator(
            electrode,
            replace(protocol, current_uA=current_uA),
            material=material,
            policy=policy,
        ).assess()

    def test_the_charge_injection_limit_is_the_boundary(self):
        """Not tautological: the oracle is IEEE, not the package -- the limit must pass
        and its successor float must fail. A one-sided ``<=`` would admit a limit that is
        merely somewhere below the boundary."""
        import math

        for material, policy, protocol, electrode in self._cases():
            limit = SafetyCalculator(
                electrode, protocol, material=material, policy=policy
            ).assess().charge.max_current_uA
            if not math.isfinite(limit) or limit <= 0:
                continue
            at = self._at(electrode, protocol, limit, material, policy)
            above = self._at(
                electrode, protocol, math.nextafter(limit, math.inf), material, policy
            )
            assert at.charge.passes, (material, policy, protocol.anodic_first, limit)
            assert not above.charge.passes, (material, policy, limit)

    def test_the_shannon_limit_is_the_boundary(self):
        """Same oracle, second back-solve."""
        import math

        for material, policy, protocol, electrode in self._cases():
            limit = SafetyCalculator(
                electrode, protocol, material=material, policy=policy
            ).assess().shannon.max_current_uA
            if not math.isfinite(limit) or limit <= 0:
                continue
            at = self._at(electrode, protocol, limit, material, policy)
            above = self._at(
                electrode, protocol, math.nextafter(limit, math.inf), material, policy
            )
            assert at.shannon.passes, (material, policy, limit)
            assert not above.shannon.passes, (material, policy, limit)

    def test_the_compliance_limit_is_the_boundary(self):
        """The third back-solve, and the one C1.6 is about to add to the candidate set.

        Measured before the fix: over 36 (electrode, compliance, pulse width)
        combinations, 6 reported limits FAIL their own compliance check and 14 more sit
        below their boundary.
        """
        import math
        from dataclasses import replace

        from neurostim import CylindricalBandElectrode, RingElectrode

        electrodes = (
            DiscElectrode(100.0, "Pt"),
            RingElectrode(330.0, 270.0, "Pt"),
            CylindricalBandElectrode(1270.0, 1500.0, "PtIr"),
            DiscElectrode(2000.0, "SIROF"),
        )
        for electrode in electrodes:
            for compliance_V in (1.0, 5.0, 10.0):
                for pulse_width_us in (50.0, 200.0, 400.0):
                    protocol = StimProtocol(80.0, pulse_width_us, 130.0, 1.0)
                    limit = SafetyCalculator(
                        electrode, protocol, compliance_V=compliance_V
                    ).assess().compliance.max_current_uA
                    if not math.isfinite(limit) or limit <= 0:
                        continue

                    def at(current, electrode=electrode, protocol=protocol,
                           compliance_V=compliance_V):
                        return SafetyCalculator(
                            electrode,
                            replace(protocol, current_uA=current),
                            compliance_V=compliance_V,
                        ).assess().compliance

                    assert at(limit).passes, (electrode, compliance_V, limit)
                    assert not at(math.nextafter(limit, math.inf)).passes, (
                        electrode,
                        compliance_V,
                        limit,
                    )

    def test_the_second_charge_back_solve_agrees_with_the_first(self):
        """``SafetyCalculator.max_current_cic_uA`` is a separate back-solve behind every
        CSV row and the amplitude-limits figure, and it was not floored (execution M4).

        Not tautological: two independently computed attributes are compared to each
        other, and both are separately asserted to be the boundary above.
        """
        for material, policy, protocol, electrode in self._cases():
            calc = SafetyCalculator(
                electrode, protocol, material=material, policy=policy
            )
            assert calc.max_current_cic_uA == calc.assess().charge.max_current_uA, (
                material,
                policy,
            )


class TestEveryRenderSiteFloors:
    """Ledger 49: a limit rounded to nearest is a limit rounded UP, on five surfaces."""

    @staticmethod
    def _worked_example() -> SafetyCalculator:
        from neurostim import RingElectrode

        return SafetyCalculator(
            RingElectrode(330.0, 270.0, "Pt"),
            StimProtocol(80, 200, 130, 1),
            compliance_V=10.0,
        )

    def test_describe_floors_the_headline(self):
        """Not tautological: "141.4" is what ``:.4g`` prints today and is asserted absent;
        "141.3" is the floored value, computed by hand from 141.37166941154072."""
        line = next(
            row
            for row in self._worked_example().describe().splitlines()
            if row.startswith("Limiting current:")
        )
        assert "141.3" in line
        assert "141.4" not in line

    def test_describe_floors_both_ends_of_the_published_range(self):
        """Not tautological: 141.37166941154072 and 212.05750411731108 floor by hand to
        141.3 and 212.0; ``:.4g`` prints 141.4 and 212.1."""
        line = next(
            row
            for row in self._worked_example().describe().splitlines()
            if "across published ranges" in row
        )
        assert "141.3-212.0" in line

    def test_the_pdf_floors_every_limit_it_prints(self):
        """Not tautological: the three ledger-49 sites are asserted on extracted PDF text
        against hand-floored values."""
        text = pdf_text(self._worked_example(), __import__("pathlib").Path("/tmp") / "x")
        assert "141.3" in text
        assert "472.7" in text
        assert "141.4" not in text
        assert "472.8" not in text

    def test_the_figure_annotation_floors(self):
        """``viz/plots.py`` prints the binding limit at ``:.3g``.

        Not tautological: the expected string is the hand-floored 3-significant-digit
        form of the same number, and the round-to-nearest form is asserted absent.
        """
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        from neurostim import RingElectrode
        from neurostim.viz.plots import current_limit_sweep

        figure, axes = plt.subplots()
        try:
            current_limit_sweep(
                RingElectrode(330.0, 270.0, "Pt"),
                StimProtocol(80, 200, 130, 1),
                compliance_V=10.0,
                ax=axes,
            )
            texts = [text.get_text() for text in axes.texts]
        finally:
            plt.close(figure)

        binding = [text for text in texts if "binding limit" in text]
        assert binding, texts
        assert "141.3" in binding[0]


class TestEveryLimitBearingCheckHasAMargin:
    """C1.4. Four of nine checks expose a margin today, so a minimum over them cannot see
    the other three (fix plan D3, ledger 1).

    ``margin`` is defined as **the ratio of the FAIL ceiling to the applied current** --
    not the CAUTION ceiling, and not ``headroom / excursion``. The difference is not
    cosmetic: the naive headroom reading of the water-window margin is **negative** at
    ``resting_potential_V = 0`` (-21.095 uA against a true 58.905), which a finiteness
    test and a one-sided ``<= 20.0`` both admit.
    """

    @staticmethod
    def _cases():
        from neurostim import CylindricalBandElectrode, RingElectrode

        yield SafetyCalculator(
            RingElectrode(330.0, 270.0, "Pt"),
            StimProtocol(80, 200, 130, 1),
            compliance_V=10.0,
        )
        yield SafetyCalculator(
            DiscElectrode(100.0, "Pt"),
            StimProtocol(80.0, 200.0, 130.0, 1.0),
            compliance_V=10.0,
        )
        yield SafetyCalculator(
            CylindricalBandElectrode(1270.0, 1500.0, "PtIr"),
            StimProtocol(3000.0, 90.0, 130.0, 1.0),
            compliance_V=10.0,
        )
        yield SafetyCalculator(
            DiscElectrode(2000.0, "SIROF"),
            StimProtocol(20, 400, 50, 3600),
            compliance_V=20.0,
        )

    def test_every_limit_bearing_margin_is_its_own_fail_ceiling(self):
        """The pin. ``margin * current`` must equal the independent per-check bisection.

        Not tautological: the expected value comes from ``tests/oracles``, which reads one
        bit per probe -- whether that named check is in ``assess().failed`` -- and never
        reads a margin, a maximum or a limiting current.
        """
        from oracles.fail_ceiling import check_fail_ceiling_uA

        from neurostim.safety import LIMIT_BEARING

        for calc in self._cases():
            assessment = calc.assess()
            named = {c.name for c in assessment.checks}
            assert named >= LIMIT_BEARING, LIMIT_BEARING - named
            for check in assessment.checks:
                if check.name not in LIMIT_BEARING:
                    continue
                expected = check_fail_ceiling_uA(calc, check.name)
                assert check.margin * calc.p.current_uA == pytest.approx(
                    expected, rel=1e-9
                ), (calc.e, check.name)

    def test_the_water_window_margin_is_positive_where_the_naive_reading_is_negative(
        self,
    ):
        """Execution B4's case, stated as a value rather than as finiteness.

        Not tautological: 58.90486225480862 uA is derived in the oracle pins from Pt's own
        150 uC/cm^2 over its own 0.6 V cathodic limit, and -21.095 is asserted absent.
        """
        calc = SafetyCalculator(
            DiscElectrode(100.0, "Pt"),
            StimProtocol(80.0, 200.0, 130.0, 1.0),
            compliance_V=10.0,
        )
        water = next(c for c in calc.assess().checks if c.name == "Water window")

        assert water.margin > 0.0
        assert water.margin * 80.0 == pytest.approx(58.90486225480862, rel=1e-12)

    def test_the_two_checks_that_had_no_margin_now_have_one(self):
        """§6: ``assessment.json`` records ``null`` for 5 of 9 margins today.

        Not tautological: the two names are written out and the assertion is finiteness
        *plus* the ceiling identity above, which finiteness alone would not give.
        """
        calc = SafetyCalculator(
            DiscElectrode(100.0, "Pt"),
            StimProtocol(80.0, 200.0, 130.0, 1.0),
            compliance_V=10.0,
        )
        checks = {c.name: c for c in calc.assess().checks}
        import math

        assert math.isfinite(checks["Water window"].margin)
        assert math.isfinite(checks["Chronic degradation"].margin)

    def test_a_check_that_did_not_run_has_an_infinite_margin(self):
        """NOT_EVALUATED must not contribute a ceiling to the minimum C1.6 takes.

        Not tautological: the oracle answers ``inf`` for a check that never FAILs across
        the whole bracket, and that is what is compared against.
        """
        import math

        from oracles.fail_ceiling import check_fail_ceiling_uA

        calc = SafetyCalculator(
            DiscElectrode(100.0, "Pt"),
            StimProtocol(80.0, 200.0, 130.0, 1.0),
            compliance_V=10.0,
        )
        shannon = next(c for c in calc.assess().checks if c.name == "Shannon criterion")

        assert shannon.status is Status.NOT_EVALUATED
        assert shannon.margin == math.inf
        assert check_fail_ceiling_uA(calc, "Shannon criterion") == math.inf

    def test_the_checks_that_bear_no_limit_keep_an_infinite_margin(self):
        """Validated envelope and Charge balance impose no ceiling on amplitude.

        Not tautological: both names are written out, and the second half asserts the
        *reason* -- their verdict does not move with amplitude -- against the oracle's
        witness rather than against their margin.
        """
        import math

        from oracles.fail_ceiling import LIMIT_BEARING as ORACLE_LIMIT_BEARING

        from neurostim.safety import LIMIT_BEARING

        calc = SafetyCalculator(
            DiscElectrode(100.0, "Pt"),
            StimProtocol(80.0, 200.0, 130.0, 1.0),
            compliance_V=10.0,
        )
        checks = {c.name: c for c in calc.assess().checks}

        assert set(checks) - LIMIT_BEARING == {"Validated envelope", "Charge balance"}
        assert checks["Validated envelope"].margin == math.inf
        assert checks["Charge balance"].margin == math.inf
        assert set(ORACLE_LIMIT_BEARING) == LIMIT_BEARING


class TestCheckKindAndProvisional:
    """``kind`` separates the four things a limit can be about; ``provisional`` says the
    limit is caveated (physics M1a, M1c, m6)."""

    @staticmethod
    def _calc() -> SafetyCalculator:
        return SafetyCalculator(
            DiscElectrode(100.0, "Pt"),
            StimProtocol(80.0, 200.0, 130.0, 1.0),
            compliance_V=10.0,
        )

    def test_every_check_declares_one_of_the_four_kinds(self):
        """Not tautological: the four labels are written out here, and the mapping from
        each check name to its kind is written out in the next test."""
        kinds = {c.kind for c in self._calc().assess().checks}
        assert kinds <= {"tissue", "electrode-chronic", "electrode-acute", "instrument"}

    def test_the_kind_of_each_check_is_the_one_its_source_measures(self):
        """Not tautological: the expected mapping is stated here from what each check's
        cited source is about -- Shannon and Butterwick measured tissue injury, the CIC
        and water window are single-pulse interface properties, dissolution is chronic,
        and compliance is a property of the stimulator, not of the patient."""
        kinds = {c.name: c.kind for c in self._calc().assess().checks}

        assert kinds == {
            "Shannon criterion": "tissue",
            "Charge injection limit": "electrode-acute",
            "Water window": "electrode-acute",
            "Validated envelope": "tissue",
            "Current density": "tissue",
            "Microelectrode charge/phase": "tissue",
            "Chronic degradation": "electrode-chronic",
            "Charge balance": "electrode-chronic",
            "Compliance voltage": "instrument",
        }

    def test_the_current_density_limit_is_always_provisional(self):
        """Its own docstring says why: the threshold is chick membrane and retina, so the
        margin is against a preparation that is not the one being stimulated.

        Not tautological: the expected value is ``True`` and the reason is the check's own
        stated one, not a recomputation of anything.
        """
        density = next(
            c for c in self._calc().assess().checks if c.name == "Current density"
        )
        assert density.provisional is True

    def test_a_caveated_charge_injection_limit_is_provisional(self):
        """Three distinct caveats, three fixtures, each chosen from the database itself.

        * TIROF's stored CIC carries **no pulse width**, so its applicability at any
          pulse width is unknown.
        * Pt's was measured at 200 us, so 2000 us is ten times away from it.
        * SS316LVM's source endorses the conservative end, so the optimistic policy
          applies a number that source argues against.

        Not tautological: each premise is asserted here against the material database
        before the ``provisional`` flag is checked, so the test fails if the fixture stops
        being the case it claims to be.
        """
        from neurostim.materials import get_material

        assert get_material("TIROF").cic.pulse_width_us is None
        assert get_material("Pt").cic.pulse_width_us == 200.0
        assert get_material("SS316LVM").cic.recommended_policy == "conservative"

        fixtures = (
            ("TIROF", 200.0, "conservative"),
            ("Pt", 2000.0, "conservative"),
            ("SS316LVM", 100.0, "optimistic"),
        )
        for material, pulse_width_us, policy in fixtures:
            calc = SafetyCalculator(
                DiscElectrode(100.0, material),
                StimProtocol(1.0, pulse_width_us, 130.0, 1.0),
                policy=policy,  # type: ignore[arg-type]
            )
            charge = next(
                c for c in calc.assess().checks if c.name == "Charge injection limit"
            )
            assert charge.provisional is True, (material, pulse_width_us, policy)

    def test_a_verified_limit_at_its_measured_conditions_is_not_provisional(self):
        """The flag must discriminate, not decorate.

        Not tautological: Pt's CIC is verified and measured at 200 us, which is the pulse
        width used, so the expected value is ``False`` -- the opposite of the test above.
        """
        charge = next(
            c
            for c in self._calc().assess().checks
            if c.name == "Charge injection limit"
        )
        assert charge.provisional is False

    def test_kind_and_provisional_reach_the_json(self):
        """Not tautological: the keys and one expected value are written out, against a
        payload that carries neither today."""
        import json

        from neurostim.io import report_to_json

        payload = json.loads(report_to_json(self._calc()))
        rows = {row["name"]: row for row in payload["checks"]}

        assert rows["Compliance voltage"]["kind"] == "instrument"
        assert rows["Current density"]["provisional"] is True
        assert rows["Water window"]["margin"] is not None
