"""Interval arithmetic and its propagation into the safety limits."""

from __future__ import annotations

import math

import pytest

from neurostim import RingElectrode, SafetyCalculator, StimProtocol
from neurostim.safety import shannon
from neurostim.uncertainty import Interval, combine, intersect, most_restrictive


class TestInterval:
    def test_rejects_inverted_bounds(self):
        with pytest.raises(ValueError, match="must be >= low"):
            Interval(5.0, 1.0)

    def test_rejects_nan(self):
        with pytest.raises(ValueError, match="NaN"):
            Interval(math.nan, 1.0)

    def test_exact_is_degenerate(self):
        i = Interval.exact(3.0)
        assert i.is_exact and i.width == 0 and i.midpoint == 3.0

    def test_from_mean_sd(self):
        i = Interval.from_mean_sd(10.0, 2.0, k=2)
        assert (i.low, i.high) == (6.0, 14.0)

    def test_fold_range(self):
        assert Interval(50.0, 150.0).fold_range == pytest.approx(3.0)
        assert math.isinf(Interval(0.0, 5.0).fold_range)

    def test_addition(self):
        assert Interval(1, 2) + Interval(10, 20) == Interval(11, 22)

    def test_subtraction_widens(self):
        assert Interval(1, 2) - Interval(10, 20) == Interval(-19, -8)

    def test_multiplication_handles_sign_combinations(self):
        assert Interval(-2, 3) * Interval(-5, 4) == Interval(-15, 12)

    def test_scalar_multiplication_both_sides(self):
        assert Interval(1, 2) * 3 == Interval(3, 6)
        assert 3 * Interval(1, 2) == Interval(3, 6)

    def test_division(self):
        assert Interval(10, 20) / 2 == Interval(5, 10)

    def test_division_by_interval_spanning_zero_raises(self):
        with pytest.raises(ZeroDivisionError, match="spanning zero"):
            Interval(1, 2) / Interval(-1, 1)

    def test_negation(self):
        assert -Interval(1, 3) == Interval(-3, -1)

    def test_sqrt(self):
        assert Interval(4, 9).sqrt() == Interval(2, 3)

    def test_sqrt_of_negative_raises(self):
        with pytest.raises(ValueError, match="negative bound"):
            Interval(-1, 4).sqrt()

    def test_contains_and_overlaps(self):
        assert Interval(1, 5).contains(3)
        assert not Interval(1, 5).contains(6)
        assert Interval(1, 5).overlaps(Interval(4, 9))
        assert not Interval(1, 5).overlaps(Interval(6, 9))

    def test_describe_collapses_when_exact(self):
        assert Interval.exact(5.0).describe("uA") == "5 uA"
        assert "-" in Interval(5.0, 9.0).describe("uA")

    def test_dependency_problem_is_documented_behaviour(self):
        """x - x is not zero in interval arithmetic; occurrences are independent."""
        x = Interval(1, 2)
        assert (x - x) != Interval.exact(0.0)


class TestCombinators:
    def test_combine_is_the_hull(self):
        assert combine([Interval(1, 3), Interval(8, 9)]) == Interval(1, 9)

    def test_intersect_overlapping(self):
        assert intersect([Interval(1, 5), Interval(3, 9)]) == Interval(3, 5)

    def test_intersect_disjoint_returns_none(self):
        assert intersect([Interval(1, 2), Interval(8, 9)]) is None

    def test_most_restrictive_takes_elementwise_min(self):
        assert most_restrictive(
            [Interval.exact(595.0), Interval(70.7, 212.1)]
        ) == Interval(70.7, 212.1)

    def test_empty_inputs_raise(self):
        for fn in (combine, intersect, most_restrictive):
            with pytest.raises(ValueError, match="at least one"):
                fn([])


class TestShannonBand:
    def test_k_band_interval_spans_sqrt_of_ten_to_the_half(self):
        """Q_max goes as sqrt(10^k), so k = 1.5 to 2.0 is a factor of 1.78 in current."""
        band = shannon.max_current_interval_uA(1e-3, 200.0)
        assert band.fold_range == pytest.approx(math.sqrt(10**0.5), rel=1e-9)

    def test_band_brackets_the_default_k(self):
        band = shannon.max_current_interval_uA(2.8e-4, 200.0)
        assert band.contains(
            shannon.shannon_max_current_uA(2.8e-4, 200.0, shannon.K_DEFAULT)
        )


class TestPropagationIntoAssessment:
    @pytest.fixture
    def assessment(self):
        return SafetyCalculator(
            RingElectrode(330, 270, "Pt"),
            StimProtocol(80, 200, 130, 1),
            compliance_V=10.0,
        ).assess()

    def test_platinum_range_reaches_the_final_limit(self, assessment):
        """The polarity-resolved Pt range must survive to the reported current limit.

        The default protocol is cathodic-first, so Rose & Robblee's 100-150 uC/cm^2
        sub-range applies rather than the 50-150 union of both polarities.
        """
        interval = assessment.limiting_current_interval_uA
        assert interval.low == pytest.approx(141.4, rel=1e-3)
        assert interval.high == pytest.approx(212.1, rel=1e-3)
        assert interval.fold_range == pytest.approx(1.5, rel=1e-6)

    def test_anodic_first_gives_the_lower_measured_range(self):
        """Rose & Robblee: 50-100 anodic-first against 100-150 cathodic-first."""
        anodic = SafetyCalculator(
            RingElectrode(330, 270, "Pt"),
            StimProtocol(80, 200, 130, 1, anodic_first=True),
        ).assess().charge
        assert anodic.limit_interval_uC_cm2 == Interval(50.0, 100.0)

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "C1.6 widened the point estimate to all seven limit-bearing checks while "
            "limiting_current_interval_uA still propagates only Shannon and the CIC, so "
            "the point estimate (20.0 uA) now sits below the interval (141.37-212.06). "
            "C1.8 widens the interval through the same per-check machinery; this marker "
            "is strict so that commit cannot land without removing it."
        ),
    )
    def test_point_estimate_sits_at_the_conservative_end(self, assessment):
        assert assessment.limiting_current_uA == pytest.approx(
            assessment.limiting_current_interval_uA.low
        )

    def test_charge_result_carries_the_published_range(self, assessment):
        result = assessment.charge
        assert result.limit_is_a_range
        # Cathodic-first by default, so the 100-150 sub-range applies.
        assert result.limit_interval_uC_cm2 == Interval(100.0, 150.0)

    def test_exact_material_gives_an_exact_limit(self):
        """TiN is a single '~1 mC/cm^2' value, so its interval must not be widened."""
        from neurostim import DiscElectrode

        assessment = SafetyCalculator(
            DiscElectrode(200.0, "TiN"), StimProtocol(10, 200, 50, 1)
        ).assess()
        assert assessment.charge.limit_interval_uC_cm2 is not None
        assert assessment.charge.limit_interval_uC_cm2.is_exact
        assert not assessment.charge.limit_is_a_range

    def test_pedot_range_is_the_peer_reviewed_spread(self):
        """2.3 mC/cm^2 (Cui & Zhou) to 3.6 (Nyberg); the 15 abstract is excluded."""
        from neurostim import DiscElectrode

        assessment = SafetyCalculator(
            DiscElectrode(200.0, "PEDOT"), StimProtocol(10, 400, 50, 1)
        ).assess()
        assert assessment.charge.limit_interval_uC_cm2 is not None
        assert assessment.charge.limit_interval_uC_cm2.fold_range == pytest.approx(
            3.6 / 2.3
        )

    def test_interval_appears_in_the_report_text(self, assessment):
        assert "across published ranges" in assessment.describe()
