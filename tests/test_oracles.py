"""Pins for ``tests/oracles`` -- the expected values every later phase will assert against.

An oracle that drifts is worse than no oracle: it makes a wrong answer look confirmed. So
each one is pinned here to a constant computed by hand, from the physics or from a
published number, never from the package.

These tests say nothing about whether the package is right. Several of them record that it
is currently wrong -- the ceiling is 20.0 uA where the package reports 141.4, and the field
model is low by exactly a factor of two. That is the point: the oracles are built and
verified before the repairs that will be judged against them, so the expected values cannot
be quietly reshaped to agree with whatever the fix happens to produce.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest
from oracles import disc_field, drift, fail_ceiling, fd_band

# --- the worked example the plan is built around ------------------------------------
#
# RingElectrode(330, 270, "Pt") at 80 uA, 200 us, 130 Hz, compliance 10 V. The package
# reports a limiting current of 141.37166941154072 uA while two checks FAIL at 80 uA.

RING_OUTER_UM = 330.0
RING_INNER_UM = 270.0
PULSE_WIDTH_US = 200.0


@pytest.fixture
def worked_example():
    from neurostim import RingElectrode, SafetyCalculator, StimProtocol

    return SafetyCalculator(
        RingElectrode(RING_OUTER_UM, RING_INNER_UM, "Pt"),
        StimProtocol(80.0, PULSE_WIDTH_US, 130.0, 1.0),
        compliance_V=10.0,
    )


class TestFailCeiling:
    """Oracle (a): binary search over ``assess().failed``."""

    def test_the_ceiling_on_the_worked_example_is_twenty_microamps(self, worked_example) -> None:
        """Pinned to Cogan 2016's microelectrode threshold, not to the search.

        4 nC per phase over a 200 us pulse is 4e-9 C / 200e-6 s = 2e-5 A = 20 uA. The
        binding check is a published charge-per-phase threshold divided by a pulse width;
        the arithmetic is one line and does not involve the package.
        """
        from neurostim.data import cogan2016

        threshold_nC = cogan2016.MICROELECTRODE_DAMAGE_THRESHOLD_NC_PER_PHASE
        expected_uA = (threshold_nC * 1e-9) / (PULSE_WIDTH_US * 1e-6) * 1e6
        assert threshold_nC == 4.0
        assert expected_uA == 20.0

        ceiling = fail_ceiling.fail_ceiling_uA(worked_example)
        assert ceiling == 20.0

    def test_the_ceiling_really_is_the_boundary(self, worked_example) -> None:
        """Passes at the ceiling and fails one ulp above it.

        A finiteness assertion would admit -21.095 uA, which is what the naive
        headroom/excursion reading of the water-window margin returns on this very case.
        """
        ceiling = fail_ceiling.fail_ceiling_uA(worked_example)
        assert ceiling > 0.0
        assert fail_ceiling.brackets_the_ceiling(worked_example, ceiling)

    def test_the_package_headline_is_seven_times_the_ceiling(self, worked_example) -> None:
        """Records today's defect, so the oracle is demonstrably not restating the code."""
        assessment = worked_example.assess()
        ceiling = fail_ceiling.fail_ceiling_uA(worked_example)
        assert assessment.limiting_current_uA == pytest.approx(141.37166941154072)
        assert assessment.limiting_current_uA / ceiling == pytest.approx(7.0686, rel=1e-4)
        assert {check.name for check in assessment.failed} == {
            "Microelectrode charge/phase",
            "Chronic degradation",
        }

    def test_the_oracle_reads_only_the_failed_tuple(self) -> None:
        """Structural, not behavioural: the module must not name what it is used to check."""
        text = Path(fail_ceiling.__file__ or "").read_text(encoding="utf-8")
        body = text.split('"""', 2)[-1]  # skip the module docstring, which discusses them
        for forbidden in ("limiting_current_uA", "limiting_mechanism", ".margin"):
            assert forbidden not in body, f"the oracle reads {forbidden}, which it must not"

    def test_a_non_monotone_predicate_is_reported_not_bisected(self) -> None:
        """The shape the module's docstring promises to report, and used to answer 0.0 on.

        ``resting_potential_V = 0.9 V`` is already outside Pt's +0.8 V window at rest, so a
        small cathodic pulse pulls the interface back INTO the window while a large one
        breaches the charge limits. ``assess().failed`` is therefore non-empty at 1e-12 uA,
        empty across roughly [9.83, 19.61] uA, and non-empty again above -- FAIL, PASS,
        FAIL. The true ceiling is 19.6 uA and the oracle used to return 0.0, which is also
        what it returns for a protocol that is unsafe at every amplitude.
        """
        from neurostim import DiscElectrode, SafetyCalculator, StimProtocol

        calc = SafetyCalculator(
            DiscElectrode(100.0, "Pt"),
            StimProtocol(80.0, PULSE_WIDTH_US, 130.0, 1.0),
            compliance_V=10.0,
            resting_potential_V=0.9,
        )
        # The band is real, and it does not reach the bottom of the bracket.
        assert fail_ceiling.no_check_fails(calc, 15.0)
        assert not fail_ceiling.no_check_fails(calc, 1e-12)

        with pytest.raises(fail_ceiling.NonMonotonePredicate, match="Water window"):
            fail_ceiling.fail_ceiling_uA(calc)

    def test_zero_means_no_amplitude_in_the_bracket_passes(self) -> None:
        """0.0 is the right answer for an amplitude-independent failure -- and only that.

        Ledger 84: Charge balance FAILs at every amplitude on a monophasic protocol,
        being a property of the waveform. 0.0 must therefore stay reachable, but it must
        mean "no probe anywhere in the bracket passes", not "the lower bracket failed".
        """
        from neurostim import CylindricalBandElectrode, SafetyCalculator, StimProtocol

        calc = SafetyCalculator(
            CylindricalBandElectrode(1270.0, 1500.0, "PtIr"),
            StimProtocol(3000.0, 90.0, 130.0, 1.0, waveform="monophasic"),
            compliance_V=10.0,
        )
        assert {check.name for check in calc.assess().failed} == {"Charge balance"}
        assert fail_ceiling.fail_ceiling_uA(calc) == 0.0
        # And the answer is distinguishable from a ceiling at the call site.
        assert not fail_ceiling.brackets_the_ceiling(calc, 0.0)

    def test_a_non_positive_ceiling_never_brackets(self, worked_example) -> None:
        """``brackets_the_ceiling`` must report, not raise. -21.095 is the naive margin."""
        for value in (0.0, -21.095, -math.inf, math.inf, math.nan):
            assert not fail_ceiling.brackets_the_ceiling(worked_example, value)

    def test_the_answer_is_checked_before_it_is_returned(
        self, worked_example, monkeypatch
    ) -> None:
        """The docstring's guarantee, made testable rather than asserted in prose."""
        monkeypatch.setattr(
            fail_ceiling, "brackets_the_ceiling", lambda *args, **kwargs: False
        )
        with pytest.raises(fail_ceiling.NonMonotonePredicate):
            fail_ceiling.fail_ceiling_uA(worked_example)

    def test_a_protocol_that_never_fails_reports_no_ceiling(self) -> None:
        """``inf`` is an honest answer; the bracket's upper end presented as one is not."""
        from neurostim import DiscElectrode, SafetyCalculator, StimProtocol

        calc = SafetyCalculator(
            DiscElectrode(2000.0, "SIROF"), StimProtocol(1.0, 100.0, 10.0, 1.0)
        )
        ceiling = fail_ceiling.fail_ceiling_uA(calc, upper_uA=10.0)
        assert ceiling == math.inf


class TestDiscSurfacePotential:
    """Oracle (b): the exact half-space disc solution."""

    # A 500 um disc in grey matter at 100 uA. R = 1/(4*0.35*250e-6) = 2857.142857 ohm.
    RADIUS_M = 250e-6
    CURRENT_A = 100e-6
    SIGMA = 0.35

    def test_the_access_resistance_is_newmans(self) -> None:
        resistance = disc_field.newman_disc_resistance_ohm(self.SIGMA, self.RADIUS_M)
        assert resistance == pytest.approx(1.0 / (4.0 * 0.35 * 250e-6))
        assert resistance == pytest.approx(2857.142857142857)

    def test_the_rim_potential_is_exactly_current_times_resistance(self) -> None:
        """``arcsin(1) = pi/2`` cancels the ``2/pi``, so this is bit-exact, not approximate."""
        resistance = disc_field.newman_disc_resistance_ohm(self.SIGMA, self.RADIUS_M)
        rim = disc_field.disc_surface_potential_V(
            self.CURRENT_A, resistance, self.RADIUS_M, self.RADIUS_M
        )
        assert rim == self.CURRENT_A * resistance
        assert rim * 1e3 == pytest.approx(285.714286, abs=5e-7)

    def test_at_a_hundred_radii_only_the_half_space_factor_agrees(self) -> None:
        """The measurement that tells the two space conventions apart.

        Far from the disc the exact solution tends to the point source, so the ratio is
        the geometry factor and nothing else. 0.5 is a factor of two; 0.999983 is the
        genuine near-field residual of a disc at a hundred radii.
        """
        resistance = disc_field.newman_disc_resistance_ohm(self.SIGMA, self.RADIUS_M)
        distance = 100.0 * self.RADIUS_M
        exact = disc_field.disc_surface_potential_V(
            self.CURRENT_A, resistance, self.RADIUS_M, distance
        )

        full_space = disc_field.point_source_potential_V(
            self.CURRENT_A, self.SIGMA, distance, geometry_factor=disc_field.FULL_SPACE_FACTOR
        )
        half_space = disc_field.point_source_potential_V(
            self.CURRENT_A, self.SIGMA, distance, geometry_factor=disc_field.HALF_SPACE_FACTOR
        )

        assert full_space / exact == pytest.approx(0.499992, abs=5e-7)
        assert half_space / exact == pytest.approx(0.999983, abs=5e-7)

    def test_todays_field_model_is_the_full_space_one(self) -> None:
        """Records the defect the oracle exists to pin: ratio exactly 0.5000."""
        from neurostim import DiscElectrode
        from neurostim.models import field

        electrode = DiscElectrode(2.0 * self.RADIUS_M * 1e6, "Pt")
        distance_um = 100.0 * self.RADIUS_M * 1e6
        resistance = disc_field.newman_disc_resistance_ohm(self.SIGMA, self.RADIUS_M)
        exact = disc_field.disc_surface_potential_V(
            self.CURRENT_A, resistance, self.RADIUS_M, 100.0 * self.RADIUS_M
        )

        today_V = field.potential_V(
            self.CURRENT_A * 1e6, distance_um, self.SIGMA, electrode=electrode
        )
        assert today_V / exact == pytest.approx(0.5, abs=1e-4)

    def test_inside_the_disc_is_a_domain_error(self) -> None:
        with pytest.raises(ValueError, match="must be >= radius_m"):
            disc_field.disc_surface_potential_V(1e-4, 1000.0, 250e-6, 100e-6)


class TestDriftTime:
    """Oracle (c): pulse-by-pulse DC accumulation."""

    # The audit's case: CylindricalBandElectrode(1270, 1500, 'PtIr') driven monophasically
    # at 3000 uA, 90 us, 130 Hz. Area = pi * d * h = pi * 0.127 cm * 0.15 cm.
    CURRENT_UA = 3000.0
    PULSE_WIDTH_US = 90.0
    FREQUENCY_HZ = 130.0
    AREA_CM2 = math.pi * 0.127 * 0.15
    CAPACITANCE_UF_CM2 = 250.0
    WINDOW_V = 0.6

    def _kwargs(self) -> dict[str, float]:
        return {
            "current_uA": self.CURRENT_UA,
            "pulse_width_us": self.PULSE_WIDTH_US,
            "frequency_hz": self.FREQUENCY_HZ,
            "area_cm2": self.AREA_CM2,
            "capacitance_uF_cm2": self.CAPACITANCE_UF_CM2,
            "window_V": self.WINDOW_V,
        }

    def test_the_net_dc_current_is_the_duty_cycle_times_the_amplitude(self) -> None:
        # 90 us at 130 Hz is a duty of 0.0117; 3000 uA * 0.0117 = 35.1 uA.
        duty = 90e-6 * 130.0
        assert duty == pytest.approx(0.0117)
        assert drift.net_dc_current_uA(3000.0, 90.0, 130.0) == pytest.approx(35.1)

    def test_the_geometry_matches_the_audits_area(self) -> None:
        assert abs(self.AREA_CM2 - 0.05985) < 5e-6

    def test_the_closed_form_is_a_quarter_of_a_second(self) -> None:
        """35.1 uA over 0.05985 cm^2 is 586.5 uA/cm^2; at 250 uF/cm^2 that is 2.346 V/s."""
        dc_density = 35.1 / self.AREA_CM2
        assert dc_density == pytest.approx(586.5, abs=0.1)
        volts_per_second = (dc_density * 1e-6) / (self.CAPACITANCE_UF_CM2 * 1e-6)
        assert volts_per_second == pytest.approx(2.346, abs=5e-4)
        assert self.WINDOW_V / volts_per_second == pytest.approx(0.2558, abs=5e-5)

        assert drift.drift_time_s_closed_form(**self._kwargs()) == pytest.approx(0.2558, abs=5e-5)

    def test_the_pulse_loop_agrees_with_the_closed_form_to_within_one_pulse(self) -> None:
        """The strongest statement available: a pulse train cannot resolve time finer."""
        stepped = drift.drift_time_s(**self._kwargs())
        continuous = drift.drift_time_s_closed_form(**self._kwargs())
        one_pulse = 1.0 / self.FREQUENCY_HZ

        assert stepped == pytest.approx(34.0 / 130.0)  # the 34th pulse crosses 0.6 V
        assert 0.0 < stepped - continuous < one_pulse

    def test_the_loop_never_evaluates_the_closed_form(self) -> None:
        text = Path(drift.__file__ or "").read_text(encoding="utf-8")
        body = text.split("def drift_time_s(", 1)[1].split("def drift_time_s_closed_form", 1)[0]
        assert "closed_form" not in body

    def test_an_unreachable_window_reports_infinity(self) -> None:
        assert drift.drift_time_s(**{**self._kwargs(), "max_pulses": 3}) == math.inf

    def test_the_package_currently_reports_a_pass_here(self) -> None:
        """Records the defect: a PASS with headroom, against a quarter-second to failure."""
        from neurostim import CylindricalBandElectrode, SafetyCalculator, StimProtocol

        calc = SafetyCalculator(
            CylindricalBandElectrode(1270.0, 1500.0, "PtIr"),
            StimProtocol(3000.0, 90.0, 130.0, 1.0, waveform="monophasic"),
            compliance_V=10.0,
        )
        water_window = next(c for c in calc.assess().checks if c.name == "Water window")
        assert water_window.status.value == "PASS"
        assert drift.drift_time_s(**self._kwargs()) < 1.0


class TestFdBandReference:
    """Oracle (d): the converged Laplace solve for a band on an insulating shaft."""

    def test_the_clinical_contact_is_three_hundred_and_thirty_five_ohms(self) -> None:
        assert fd_band.FD_BAND_REFERENCE[fd_band.CLINICAL_DBS_ASPECT] == 335.1

    def test_the_equal_area_sphere_is_within_two_percent_at_the_clinical_aspect(self) -> None:
        """329.5 ohm, computed here from the geometry rather than quoted."""
        diameter_cm = fd_band.SHAFT_DIAMETER_UM * 1e-4
        height_cm = fd_band.CLINICAL_DBS_ASPECT * diameter_cm
        area_cm2 = math.pi * diameter_cm * height_cm
        radius_m = math.sqrt((area_cm2 * 1e-4) / (4.0 * math.pi))
        sphere_ohm = 1.0 / (4.0 * math.pi * fd_band.CONDUCTIVITY_S_PER_M * radius_m)

        assert sphere_ohm == pytest.approx(329.5, abs=0.05)
        reference = fd_band.FD_BAND_REFERENCE[fd_band.CLINICAL_DBS_ASPECT]
        assert (sphere_ohm - reference) / reference == pytest.approx(-0.017, abs=5e-4)

    def test_the_equal_area_disc_the_package_uses_is_high_by_half(self) -> None:
        diameter_cm = fd_band.SHAFT_DIAMETER_UM * 1e-4
        height_cm = fd_band.CLINICAL_DBS_ASPECT * diameter_cm
        area_cm2 = math.pi * diameter_cm * height_cm
        radius_m = math.sqrt((area_cm2 * 1e-4) / math.pi)
        disc_ohm = 1.0 / (4.0 * fd_band.CONDUCTIVITY_S_PER_M * radius_m)

        assert disc_ohm == pytest.approx(517.5, abs=0.05)
        reference = fd_band.FD_BAND_REFERENCE[fd_band.CLINICAL_DBS_ASPECT]
        assert disc_ohm / reference == pytest.approx(1.545, abs=5e-3)

    def test_resistance_falls_monotonically_with_band_height(self) -> None:
        values = [fd_band.FD_BAND_REFERENCE[a] for a in sorted(fd_band.FD_BAND_REFERENCE)]
        assert values == sorted(values, reverse=True)

    def test_the_rejected_log_form_is_negative_at_small_aspect(self) -> None:
        """``ln(2L/r)/(2 pi sigma L)`` below aspect 0.25, written out here."""
        shaft_radius_m = fd_band.SHAFT_DIAMETER_UM * 1e-6 / 2.0
        height_m = 0.2 * fd_band.SHAFT_DIAMETER_UM * 1e-6
        log_form = math.log(2.0 * height_m / shaft_radius_m) / (
            2.0 * math.pi * fd_band.CONDUCTIVITY_S_PER_M * height_m
        )
        assert log_form < 0.0
        assert log_form == pytest.approx(-399.5, abs=0.5)
        assert fd_band.FD_BAND_REFERENCE[0.200] == 739.9

    def test_the_generator_reproduces_the_table(self) -> None:
        """A frozen table nothing can re-derive is a magic number.

        Coarse settings so this costs a second or so; the committed table is from a
        500x500 grid at 2000x the shaft radius, and the clinical value moves by 0.45 %
        across every refinement tried.
        """
        import importlib.util
        import sys
        from pathlib import Path

        generator_path = Path(__file__).resolve().parents[1] / "scripts" / "fd_band_reference.py"
        spec = importlib.util.spec_from_file_location("fd_band_reference", generator_path)
        assert spec is not None and spec.loader is not None
        generator = importlib.util.module_from_spec(spec)
        sys.modules["fd_band_reference"] = generator
        spec.loader.exec_module(generator)

        resolved = generator.solve_band_resistance_ohm(
            generator.SHAFT_DIAMETER_M / 2.0,
            fd_band.CLINICAL_DBS_ASPECT * generator.SHAFT_DIAMETER_M,
            nr=200,
            nz=200,
            domain_factor=500.0,
        )
        assert resolved == pytest.approx(
            fd_band.FD_BAND_REFERENCE[fd_band.CLINICAL_DBS_ASPECT], rel=0.02
        )
