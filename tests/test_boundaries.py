"""Boundaries, guards and small formulas that no test pinned (C7.6, G2).

The generated mutation set (``scripts/mutation.py``) survived at 71.9 % on its first run: 45
of 160 mutants changed nothing any test observed. Most were an input guard's boundary
(``<= 0`` becoming ``< 0``, so zero slips through), a guard's ``or`` becoming ``and``
(so NaN or a negative slips through), or a displayed quantity whose value was never
asserted. Each test here names the mutant it kills and takes its expected value from the
guard's own contract or from a hand calculation, never from the expression under test.

Mutants judged equivalent, and so left alive, are listed in the results file with the
reason; see ``docs/audit/mutation_results.json``.
"""

from __future__ import annotations

import math
from dataclasses import replace

import numpy as np
import pytest

from neurostim import DiscElectrode, SafetyCalculator, StimProtocol
from neurostim.models import strength_duration as sd
from neurostim.models import vta
from neurostim.safety import charge, envelope, shannon
from neurostim.safety import water_window as ww
from neurostim.safety._limits import format_floor_places
from neurostim.uncertainty import Interval

NOT_POSITIVE = [0.0, -1.0, math.nan]


class TestGuardsRefuseZeroNegativeAndNaN:
    """``x <= 0`` guards whose zero, and ``or`` guards whose NaN, were never exercised."""

    @pytest.mark.parametrize("area", [*NOT_POSITIVE, math.inf])
    def test_charge_density_area(self, area: float) -> None:  # charge.py:53
        with pytest.raises(ValueError, match="area_cm2"):
            charge.charge_density_uC_cm2(1.0, area)

    @pytest.mark.parametrize("area", NOT_POSITIVE)
    def test_cic_max_charge_area(self, area: float) -> None:  # charge.py:70
        with pytest.raises(ValueError, match="area_cm2"):
            charge.cic_max_charge_uC("Pt", area)

    @pytest.mark.parametrize("width", NOT_POSITIVE)
    def test_cic_max_current_pulse_width(self, width: float) -> None:  # charge.py:90
        with pytest.raises(ValueError, match="pulse_width_us"):
            charge.cic_max_current_uA("Pt", 0.001, width)

    @pytest.mark.parametrize("area", NOT_POSITIVE)
    def test_shannon_max_charge_area(self, area: float) -> None:  # shannon.py:286
        with pytest.raises(ValueError, match="area_cm2"):
            shannon.shannon_max_charge_uC(area)

    @pytest.mark.parametrize("capacitance", NOT_POSITIVE)
    def test_polarisation_capacitance(self, capacitance: float) -> None:  # water_window.py:192
        with pytest.raises(ValueError, match="capacitance_uF_cm2"):
            ww.polarisation_V(10.0, capacitance)

    def test_a_zero_fit_threshold_is_refused(self) -> None:  # vta.py:188
        with pytest.raises(ValueError, match="thresholds > 0"):
            vta.fit_current_distance(np.array([100.0, 200.0]), np.array([0.0, 40.0]), fit_offset=False)

    def test_zero_distance_is_allowed_and_costs_the_offset(self) -> None:  # vta.py:134
        model = vta.CurrentDistanceModel(k_uA_per_mm2=1300.0, threshold_offset_uA=5.0)
        assert model.threshold_uA(0.0) == 5.0


class TestReportedValuesAreTheirDefinitions:
    """Quantities a result reports, checked against a hand calculation."""

    def test_the_shannon_margin_is_threshold_minus_metric(self) -> None:  # shannon.py:353
        result = shannon.evaluate(0.02, 0.001, 200.0, k=1.5)
        expected = 1.5 - (math.log10(0.02) + math.log10(0.02 / 0.001))
        assert result.margin_db == pytest.approx(expected, rel=1e-12)

    def test_the_lapicque_chronaxie_se_is_ln2_times_taus(self) -> None:  # strength_duration.py:314
        from scipy.optimize import curve_fit

        widths = np.array([50.0, 100.0, 200.0, 400.0, 800.0])
        thresholds = np.array([82.0, 50.0, 34.0, 26.0, 22.0])
        fit = sd.fit_lapicque(widths, thresholds)
        # An independent curve_fit from the converged point: its covariance at the same
        # optimum gives tau's SE directly.
        _, pcov = curve_fit(
            lambda w, r, t: r / (1.0 - np.exp(-w / t)),
            widths,
            thresholds,
            p0=[fit.rheobase_uA, fit.membrane_tau_us],
        )
        assert fit.chronaxie_se_us == pytest.approx(
            math.log(2.0) * math.sqrt(pcov[1, 1]), rel=1e-3
        )

    def test_a_fit_through_the_origin_recovers_k(self) -> None:  # vta.py:204
        r = np.array([100.0, 200.0, 400.0])
        model = vta.fit_current_distance(r, 1300.0 * (r * 1e-3) ** 2, fit_offset=False)
        assert model.k_uA_per_mm2 == pytest.approx(1300.0, rel=1e-12)

    def test_the_maximum_charge_is_the_last_float_that_passes(self) -> None:  # charge.py:350
        result = charge.evaluate("Pt", 0.01, 0.001, 200.0)
        limit = result.cic_limit_uC_cm2
        assert charge.charge_density_uC_cm2(result.max_charge_uC, 0.001) <= limit
        above = math.nextafter(result.max_charge_uC, math.inf)
        assert charge.charge_density_uC_cm2(above, 0.001) > limit

    def test_a_representable_value_floors_to_itself(self) -> None:  # _limits.py:391
        assert format_floor_places(10.0, 3) == "10.000"
        assert format_floor_places(0.5, 2) == "0.50"
        assert format_floor_places(0.83, 2) == "0.82"  # 0.83 is 0.8299999... as a float

    def test_the_margin_of_no_current_is_infinite(self) -> None:  # assessment.py:859
        from neurostim.safety.assessment import _margin_from_ceiling

        assert _margin_from_ceiling(10.0, 0.0) == math.inf
        assert _margin_from_ceiling(10.0, math.nan) == math.inf
        assert _margin_from_ceiling(10.0, 5.0) == 2.0

    def test_utilisation_without_a_positive_compliance_is_infinite(self) -> None:  # compliance.py:529
        result = SafetyCalculator(
            DiscElectrode(500.0, "Pt"), StimProtocol(100.0, 200.0, 50.0, 1.0), compliance_V=10.0
        ).assess().compliance
        assert result.utilisation == pytest.approx(result.required_V / 10.0)
        for available in (None, 0.0, -1.0):
            assert replace(result, available_V=available).utilisation == math.inf

    def test_compliance_defaults_to_the_documented_conductivity(self) -> None:  # compliance.py:679
        from neurostim.safety import compliance

        disc, protocol = DiscElectrode(500.0, "Pt"), StimProtocol(100.0, 200.0, 50.0, 1.0)
        assert compliance.evaluate(disc, protocol).access_resistance_ohm == pytest.approx(
            disc.access_resistance_ohm(0.35), rel=1e-12
        )


class TestReturnPhasePresence:
    """A biphasic pulse that recovers no charge has a return phase of zero current."""

    @pytest.mark.parametrize(
        ("protocol", "present"),
        [
            (StimProtocol(100.0, 200.0, 50.0, 1.0), True),
            (StimProtocol(100.0, 200.0, 50.0, 1.0, charge_recovery_ratio=0.0), False),
            (StimProtocol(100.0, 200.0, 50.0, 1.0, waveform="monophasic"), False),
        ],
    )
    def test_compliance_and_current_density_agree(self, protocol, present) -> None:
        # compliance.py:396 and current_density.py:204
        from neurostim.safety import current_density

        disc = DiscElectrode(500.0, "Pt")
        assessment = SafetyCalculator(disc, protocol, compliance_V=10.0).assess()
        assert assessment.compliance.has_return_phase is present
        density = current_density.evaluate(
            protocol.current_uA,
            disc.area_cm2,
            protocol.pulse_width_us,
            return_phase_current_uA=protocol.return_phase_current_uA,
            return_phase_width_us=protocol.return_phase_width_us,
        )
        assert density.has_return_phase is present


class TestInclusiveEdges:
    """Values exactly on a documented edge sit on the documented side of it."""

    def test_a_pulse_that_exactly_fills_its_period_fits(self) -> None:  # protocol.py:186
        protocol = StimProtocol(100.0, 500.0, 1000.0, 1.0)
        assert protocol.active_duration_us == protocol.period_us == 1000.0

    def test_twice_the_measured_pulse_width_carries_no_warning(self) -> None:  # charge.py:300
        assert charge.PULSE_WIDTH_TOLERANCE == 2.0
        assert charge.evaluate("Pt", 0.01, 0.001, 400.0).condition_warning == ""
        assert charge.evaluate("Pt", 0.01, 0.001, 401.0).condition_warning != ""

    def test_twice_the_fit_pulse_width_is_inside_the_envelope(self) -> None:  # envelope.py:215
        def pulse_width(width: float) -> tuple[str, str]:
            result = envelope.evaluate(StimProtocol(10.0, width, 50.0, 7 * 3600.0), 0.1)
            excursion = next(e for e in result.excursions if e.parameter == "pulse width")
            return excursion.direction, excursion.rationale

        assert pulse_width(800.0) == ("inside", "")
        direction, rationale = pulse_width(801.0)
        assert direction == "unknown" and "extrapolations" in rationale

    def test_touching_intervals_overlap(self) -> None:  # uncertainty.py:121
        assert Interval(0.0, 1.0).overlaps(Interval(1.0, 2.0))
        assert not Interval(0.0, 1.0).overlaps(Interval(1.5, 2.0))


class TestDescribeLines:
    """Lines a description adds only in the case it names."""

    def test_the_return_phase_line_needs_an_unequal_biphasic_return(self) -> None:  # protocol.py:406
        assert "return phase:" not in StimProtocol(100.0, 200.0, 50.0, 1.0).describe()
        assert "return phase:" not in StimProtocol(
            100.0, 200.0, 50.0, 1.0, waveform="monophasic"
        ).describe()
        assert "return phase:" in StimProtocol(
            100.0, 200.0, 50.0, 1.0, return_phase_ratio=2.0
        ).describe()

    def test_the_train_duty_line_needs_a_duty_cycle(self) -> None:  # protocol.py:412
        assert "train duty:" not in StimProtocol(100.0, 200.0, 50.0, 1.0).describe()
        assert "train duty:" in StimProtocol(
            100.0, 200.0, 50.0, 1.0, train_duty_cycle=0.5
        ).describe()

    def test_an_underived_in_vivo_limit_says_so(self) -> None:  # charge.py:212
        text = charge.evaluate("TiN", 0.01, 0.001, 200.0, medium="in_vivo").describe()
        assert "IN VIVO: no in vivo derating is reported for TiN" in text
        assert "IN VIVO" not in charge.evaluate("TiN", 0.01, 0.001, 200.0).describe()


class TestIntervalArithmetic:
    def test_a_number_minus_an_interval(self) -> None:  # uncertainty.py:148
        assert 5.0 - Interval(1.0, 2.0) == Interval(3.0, 4.0)

    def test_an_unbounded_divisor_keeps_the_finite_end_exact(self) -> None:  # uncertainty.py:265
        assert Interval(1.0, 2.0) / Interval(1.0, math.inf) == Interval(0.0, 2.0)


class TestChronaxieRangesAbut:
    def test_the_axon_range_ends_where_the_cell_body_range_begins(self) -> None:  # vta.py:82
        """The docstring's own statement: axons up to the 7 ms at which cell bodies start
        (7-31 ms, Nowak & Bullier 1998 and Ranck 1975 via Tehovnik et al. 2006)."""
        assert vta.AXON_CHRONAXIE_RANGE_MS[1] == vta.CELL_BODY_CHRONAXIE_RANGE_MS[0] == 7.0


class TestALapicqueFitCanNeedMoreThanTwentyEvaluations:
    """Ledger 176 (Phase 7 review S2). ``maxfev = max_iter * 10`` gives curve_fit 2000
    evaluations at the default. The generated mutant ``* -> /`` leaves it 20, and survived
    because no test fitted a design that needs more. This one does: at ``max_iter=2``
    (the same 20) curve_fit gives up. The default must converge to the least-squares
    minimum, checked against an independent ``least_squares`` solve from another start."""

    WIDTHS = np.array([50.0, 100.0, 200.0, 400.0, 800.0, 1600.0])
    THRESHOLDS = np.array([114.739, 66.021, 42.949, 30.284, 16.124, 13.143])

    def test_the_default_converges_to_the_minimum(self) -> None:
        from scipy.optimize import least_squares

        fit = sd.fit_lapicque(self.WIDTHS, self.THRESHOLDS)
        independent = least_squares(
            lambda p: p[0] / (1.0 - np.exp(-self.WIDTHS / p[1])) - self.THRESHOLDS,
            x0=[10.0, 1000.0],
            bounds=([1e-9, 1e-9], [np.inf, np.inf]),
            xtol=1e-14, ftol=1e-14, gtol=1e-14, max_nfev=100_000,
        )
        assert fit.rheobase_uA == pytest.approx(independent.x[0], rel=1e-5)
        assert fit.membrane_tau_us == pytest.approx(independent.x[1], rel=1e-5)

    def test_twenty_evaluations_are_not_enough(self) -> None:
        # The premise. Runs after the convergence test: under the mutant this call gets a
        # fractional maxfev, which the solver does not stop on.
        with pytest.raises(RuntimeError):
            sd.fit_lapicque(self.WIDTHS, self.THRESHOLDS, max_iter=2)


class TestAZeroOffsetIsNotRefusedForItsRounding:
    """Ledger 179 (Phase 7 review S5). Noise-free ``I = k r^2`` data fit an intercept of
    about -1e-14 uA by float least squares, and the negative-offset guard refused them: 64
    of the review's 200 exact designs (72 of this test's 200). The guard now allows an intercept within
    sqrt(eps) of the largest threshold, and a real negative offset is still refused."""

    @staticmethod
    def _exact_designs(count: int = 200) -> list[tuple[np.ndarray, np.ndarray]]:
        rng = np.random.default_rng(179)
        designs = []
        for _ in range(count):
            r = np.sort(rng.uniform(10.0, 3000.0, int(rng.integers(2, 10))))
            k = rng.uniform(100.0, 30000.0)
            designs.append((r, k * (r * 1e-3) ** 2))
        return designs

    def test_exact_zero_offset_designs_fit(self) -> None:
        for r, thresholds in self._exact_designs():
            model = vta.fit_current_distance(r, thresholds)
            assert model.threshold_offset_uA >= 0.0
            assert model.threshold_offset_uA <= 1.5e-8 * thresholds.max()

    def test_a_real_negative_offset_is_still_refused(self) -> None:
        # An offset of -1 uA against thresholds up to 207 uA: 0.5 % of the data scale.
        r = np.array([100.0, 200.0, 400.0])
        with pytest.raises(ValueError, match="negative"):
            vta.fit_current_distance(r, 1300.0 * (r * 1e-3) ** 2 - 1.0)


class TestSecondGeneratedPass:
    """Ledger 181 (Phase 7 review S7). The re-measurement at clean commit 4cacbf2 drew a new
    generated sample, because S4 and S5 moved the site offsets, and 25 of its 160 survived
    (84.4 %). These tests kill the ones that are real, each against a hand value or the
    documented contract. The rest are argued equivalent in scripts/mutation.py."""

    def test_anodic_headroom_is_edge_minus_peak(self) -> None:  # water_window.py:407
        result = ww.evaluate("Pt", 20.0, anodic_first=True, capacitance_uF_cm2=100.0)
        # 20 uC/cm^2 over 100 uF/cm^2 is 0.2 V above rest (0 V).
        assert result.peak_potential_V == pytest.approx(0.2)
        assert result.window is not None
        assert result.headroom_V == pytest.approx(result.window.anodic_V - 0.2)

    def test_a_number_over_an_interval(self) -> None:  # uncertainty.py:165
        assert 6.0 / Interval(2.0, 3.0) == Interval(2.0, 3.0)

    def test_a_zero_value_is_infinitely_far_from_its_reference(self) -> None:  # envelope.py:100
        excursion = envelope.Excursion(
            parameter="pulse width", value=0.0, reference=400.0, units="us", direction="unknown"
        )
        assert excursion.fold == math.inf

    def test_no_requirement_has_no_ceiling(self) -> None:  # compliance.py:543
        result = SafetyCalculator(
            DiscElectrode(500.0, "Pt"), StimProtocol(100.0, 200.0, 50.0, 1.0), compliance_V=10.0
        ).assess().compliance
        assert replace(result, required_V=0.0).max_current_uA == math.inf

    @pytest.mark.parametrize("impedance", [math.nan, -5.0, 0.0])
    def test_a_measured_impedance_must_be_finite_and_positive(self, impedance) -> None:
        from neurostim.safety import compliance  # compliance.py:704

        with pytest.raises(ValueError, match="measured_impedance_ohm"):
            compliance.evaluate(
                DiscElectrode(500.0, "Pt"),
                StimProtocol(100.0, 200.0, 50.0, 1.0),
                measured_impedance_ohm=impedance,
            )

    def test_an_activation_radius_equal_to_the_electrode_is_inside_it(self) -> None:  # vta.py:258
        model = vta.CurrentDistanceModel()
        result = vta.VTAResult(100.0, 50.0, 0.0005, model, electrode_radius_um=50.0)
        assert not result.radius_exceeds_electrode
        assert replace(result, radius_um=50.001).radius_exceeds_electrode

    def test_a_threshold_at_zero_distance_can_be_fit(self) -> None:  # vta.py:194
        r = np.array([0.0, 100.0, 200.0])
        model = vta.fit_current_distance(r, 5.0 + 1300.0 * (r * 1e-3) ** 2)
        assert model.threshold_offset_uA == pytest.approx(5.0)

    def test_half_the_microelectrode_threshold_passes(self) -> None:  # assessment.py:1678
        # 20 uA x 100 us = 2 nC exactly: half of Cogan's 4 nC/phase, the CAUTION edge.
        assessment = SafetyCalculator(
            DiscElectrode(20.0, "Pt"), StimProtocol(20.0, 100.0, 50.0, 1.0)
        ).assess()
        check = next(c for c in assessment.checks if c.name == "Microelectrode charge/phase")
        assert check.status.value == "PASS"

    def test_a_non_drifting_window_prints_no_drift(self) -> None:  # water_window.py:441
        window = SafetyCalculator(
            DiscElectrode(500.0, "Pt"), StimProtocol(100.0, 200.0, 50.0, 1.0)
        ).assess().water_window
        assert window.drift is not None and not window.drift.drifts
        assert window.drift.describe() not in window.describe()

    def test_no_return_current_has_no_return_threshold(self) -> None:  # current_density.py:329
        from neurostim.safety import current_density

        result = current_density.evaluate(
            100.0, 0.00196, 200.0, return_phase_current_uA=0.0, return_phase_width_us=200.0
        )
        assert result.return_threshold is None

    def test_small_limits_print_in_scientific_notation(self) -> None:  # _limits.py:320
        from neurostim.safety._limits import format_limit

        assert format_limit(1.23e-5) == "1.230e-05"  # :.4g switches below 1e-4
        assert format_limit(1.23e-4) == "0.0001230"

    def test_a_value_on_its_bound_needs_no_extra_places(self) -> None:  # _limits.py:375
        from neurostim.safety._limits import format_against

        assert format_against(0.5, "0.50", exceeds=False) == "0.50"

    def test_the_summary_rules_are_72_wide(self) -> None:  # assessment.py:770, 815
        text = SafetyCalculator(
            DiscElectrode(500.0, "Pt"), StimProtocol(100.0, 200.0, 50.0, 1.0)
        ).assess().describe()
        rules = [line for line in text.splitlines() if line and set(line) <= {"=", "-"}]
        assert rules and all(len(line) == 72 for line in rules)

    def test_a_requirement_that_rounds_to_the_available_voltage_still_reads_above_it(
        self,
    ) -> None:  # assessment.py:1895
        # 0.33299 V required against 0.33 V: at two places both print "0.33".
        assessment = SafetyCalculator(
            DiscElectrode(500.0, "Pt"), StimProtocol(102.0, 200.0, 50.0, 1.0), compliance_V=0.33
        ).assess()
        assert f"{assessment.compliance.required_V:.2f}" == "0.33"  # the premise
        check = next(c for c in assessment.checks if c.name == "Compliance voltage")
        assert check.summary.startswith("needs 0.333 V but only 0.330 V available")
