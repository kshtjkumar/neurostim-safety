"""Geometry, protocol and safety-check behaviour, including input validation."""

from __future__ import annotations

import math

import pytest

from neurostim import (
    CylindricalBandElectrode,
    DiscElectrode,
    HemisphericalElectrode,
    MicrowireElectrode,
    RectangularElectrode,
    RingElectrode,
    SafetyCalculator,
    SphericalElectrode,
    StimProtocol,
)
from neurostim.geometry import grid_array, linear_array
from neurostim.safety import shannon
from neurostim.safety.assessment import Status


class TestGeometryAreas:
    def test_disc_area(self):
        assert DiscElectrode(200.0).area_um2 == pytest.approx(math.pi * 100.0**2)

    def test_ring_area(self):
        ring = RingElectrode(330.0, 270.0)
        assert ring.area_um2 == pytest.approx(math.pi * (165.0**2 - 135.0**2))

    def test_ring_reduces_to_disc_when_inner_is_zero(self):
        assert RingElectrode(200.0, 0.0).area_um2 == pytest.approx(
            DiscElectrode(200.0).area_um2
        )

    def test_rectangle_area(self):
        assert RectangularElectrode(200.0, 500.0).area_um2 == pytest.approx(1e5)

    def test_band_area_is_lateral_only(self):
        """A band is a sleeve: no end caps."""
        band = CylindricalBandElectrode(100.0, 200.0)
        assert band.area_um2 == pytest.approx(math.pi * 100.0 * 200.0)

    def test_sphere_and_hemisphere(self):
        sphere = SphericalElectrode(200.0)
        hemi = HemisphericalElectrode(200.0)
        assert sphere.area_um2 == pytest.approx(4 * math.pi * 100.0**2)
        assert hemi.area_um2 == pytest.approx(sphere.area_um2 / 2)

    @pytest.mark.parametrize(
        ("tip", "expected_factor"),
        [("flat", 1.0), ("hemispherical", 2.0)],
    )
    def test_microwire_tip_shapes(self, tip, expected_factor):
        wire = MicrowireElectrode(50.0, 0.0, tip)
        assert wire.area_um2 == pytest.approx(expected_factor * math.pi * 25.0**2)

    def test_microwire_conical_tip(self):
        wire = MicrowireElectrode(50.0, 0.0, "conical", cone_height_um=100.0)
        slant = math.sqrt(25.0**2 + 100.0**2)
        assert wire.area_um2 == pytest.approx(math.pi * 25.0 * slant)

    def test_microwire_shaft_plus_tip(self):
        wire = MicrowireElectrode(50.0, 100.0, "flat")
        assert wire.area_um2 == pytest.approx(
            math.pi * 50.0 * 100.0 + math.pi * 25.0**2
        )

    def test_equivalent_radius_recovers_disc_radius(self):
        assert DiscElectrode(200.0).equivalent_radius_um == pytest.approx(100.0)


class TestGeometryValidation:
    def test_ring_rejects_inner_at_least_outer(self):
        with pytest.raises(ValueError, match="must be smaller than"):
            RingElectrode(270.0, 330.0)
        with pytest.raises(ValueError, match="must be smaller than"):
            RingElectrode(300.0, 300.0)

    @pytest.mark.parametrize("bad", [0.0, -1.0, math.nan, math.inf])
    def test_disc_rejects_non_positive_and_non_finite(self, bad):
        with pytest.raises(ValueError):
            DiscElectrode(bad)

    def test_ring_rejects_negative_inner(self):
        with pytest.raises(ValueError, match=">= 0"):
            RingElectrode(330.0, -5.0)

    def test_conical_tip_requires_height(self):
        with pytest.raises(ValueError, match="cone_height_um is required"):
            MicrowireElectrode(50.0, 0.0, "conical")

    def test_unknown_tip_shape(self):
        with pytest.raises(ValueError, match="tip_shape must be"):
            MicrowireElectrode(50.0, 0.0, "pointy")  # type: ignore[arg-type]

    @pytest.mark.parametrize("sigma", [0.0, -1.0, math.nan])
    def test_access_resistance_rejects_bad_conductivity(self, sigma):
        with pytest.raises(ValueError, match="conductivity"):
            DiscElectrode(100.0).access_resistance_ohm(sigma)


class TestAccessResistance:
    def test_sphere_exact_form(self):
        sphere = SphericalElectrode(200.0)
        assert sphere.access_resistance_ohm(0.35) == pytest.approx(
            1.0 / (4 * math.pi * 0.35 * 100e-6)
        )
        assert sphere.access_resistance_is_exact

    def test_hemisphere_is_twice_the_sphere(self):
        sphere = SphericalElectrode(200.0)
        hemi = HemisphericalElectrode(200.0)
        assert hemi.access_resistance_ohm(0.35) == pytest.approx(
            2 * sphere.access_resistance_ohm(0.35)
        )

    def test_resistance_scales_inversely_with_conductivity(self):
        disc = DiscElectrode(100.0)
        assert disc.access_resistance_ohm(0.7) == pytest.approx(
            disc.access_resistance_ohm(0.35) / 2
        )

    def test_approximate_geometries_are_flagged(self):
        assert not RingElectrode(330.0, 270.0).access_resistance_is_exact
        assert not CylindricalBandElectrode(1270.0, 1500.0).access_resistance_is_exact


class TestArrays:
    def test_linear_array_pitch_and_area(self):
        array = linear_array(DiscElectrode(100.0), 4, 500.0)
        assert len(array) == 4
        assert array.min_pitch_um() == pytest.approx(500.0)
        assert array.total_area_cm2 == pytest.approx(4 * DiscElectrode(100.0).area_cm2)
        assert array.is_homogeneous

    def test_grid_array_size(self):
        array = grid_array(DiscElectrode(50.0), 3, 4, 400.0)
        assert len(array) == 12
        assert array.min_pitch_um() == pytest.approx(400.0)

    def test_single_site_pitch_is_infinite(self):
        assert math.isinf(linear_array(DiscElectrode(50.0), 1, 100.0).min_pitch_um())

    def test_empty_array_rejected(self):
        from neurostim.geometry import ElectrodeArray

        with pytest.raises(ValueError, match="at least one site"):
            ElectrodeArray(sites=())


class TestProtocol:
    def test_charge_per_phase(self):
        assert StimProtocol(80, 200, 130, 1).charge_per_phase_uC == pytest.approx(0.016)

    def test_biphasic_symmetric_is_charge_balanced(self):
        p = StimProtocol(80, 200, 130, 1)
        assert p.is_charge_balanced
        assert p.net_dc_current_uA == pytest.approx(0.0)

    def test_monophasic_is_not_charge_balanced(self):
        p = StimProtocol(80, 200, 130, 1, waveform="monophasic")
        assert not p.is_charge_balanced
        assert p.net_charge_per_pulse_uC == pytest.approx(0.016)
        assert p.net_dc_current_uA == pytest.approx(0.016 * 130)

    def test_asymmetric_return_phase_stays_balanced(self):
        p = StimProtocol(80, 200, 130, 1, return_phase_ratio=4.0)
        assert p.return_phase_current_uA == pytest.approx(20.0)
        assert p.return_phase_width_us == pytest.approx(800.0)
        assert p.is_charge_balanced

    def test_duty_cycle(self):
        p = StimProtocol(80, 200, 130, 1)
        assert p.duty_cycle == pytest.approx(2 * 200e-6 * 130)

    def test_rms_current_of_symmetric_biphasic(self):
        p = StimProtocol(100, 200, 100, 1)
        expected = math.sqrt((100.0**2 * 200 + 100.0**2 * 200) / (1e6 / 100))
        assert p.rms_current_uA == pytest.approx(expected)

    def test_n_pulses(self):
        assert StimProtocol(80, 200, 130, 2).n_pulses == pytest.approx(260)

    def test_continuous_train(self):
        p = StimProtocol(80, 200, 130, math.inf)
        assert math.isinf(p.n_pulses)
        assert math.isinf(p.total_charge_per_train_uC)

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"current_uA": 0},
            {"current_uA": -5},
            {"pulse_width_us": 0},
            {"frequency_hz": 0},
            {"train_duration_s": 0},
            {"interphase_gap_us": -1},
            {"return_phase_ratio": 0},
            {"waveform": "triphasic"},
        ],
    )
    def test_invalid_protocols_rejected(self, kwargs):
        base = {
            "current_uA": 80,
            "pulse_width_us": 200,
            "frequency_hz": 130,
            "train_duration_s": 1,
        }
        with pytest.raises(ValueError):
            StimProtocol(**{**base, **kwargs})

    def test_pulse_must_fit_in_its_period(self):
        """A 200 us biphasic pulse cannot repeat at 10 kHz."""
        with pytest.raises(ValueError, match="does not fit in its period"):
            StimProtocol(80, 200, 10000, 1)


class TestShannon:
    def test_max_charge_round_trip(self):
        area = 2.8e-4
        for k in (1.5, 1.7, 2.0):
            q_max = shannon.shannon_max_charge_uC(area, k)
            assert shannon.shannon_k(q_max, area) == pytest.approx(k)

    def test_max_charge_formula(self):
        assert shannon.shannon_max_charge_uC(1e-2, 1.7) == pytest.approx(
            math.sqrt(1e-2 * 10**1.7)
        )

    def test_smaller_electrodes_permit_higher_charge_density(self):
        small = shannon.shannon_max_charge_density_uC_cm2(1e-5)
        large = shannon.shannon_max_charge_density_uC_cm2(1e-2)
        assert small > large

    def test_current_limit_scales_inversely_with_pulse_width(self):
        a = shannon.shannon_max_current_uA(1e-3, 100.0)
        b = shannon.shannon_max_current_uA(1e-3, 200.0)
        assert a == pytest.approx(2 * b)

    @pytest.mark.parametrize("charge", [0.0, -1.0])
    def test_zero_or_negative_charge_raises_not_domain_error(self, charge):
        with pytest.raises(ValueError, match="must be finite and > 0"):
            shannon.shannon_k(charge, 1e-3)

    def test_zero_area_raises(self):
        with pytest.raises(ValueError, match="area_cm2"):
            shannon.shannon_k(0.01, 0.0)


class TestAssessment:
    def test_all_checks_present(self):
        calc = SafetyCalculator(RingElectrode(330, 270, "Pt"), StimProtocol(80, 200, 130, 1))
        names = {c.name for c in calc.assess().checks}
        assert names == {
            "Shannon criterion",
            "Validated envelope",
            "Charge injection limit",
            "Current density",
            "Water window",
            "Microelectrode charge/phase",
            "Chronic degradation",
            "Charge balance",
            "Compliance voltage",
        }

    def test_shannon_defers_to_the_microelectrode_criterion_below_the_boundary(self):
        """Cogan 2016: Shannon does not apply below ~3e-4 cm^2, so it must not report
        headroom there and contradict the charge-per-phase check."""
        calc = SafetyCalculator(
            RingElectrode(330, 270, "Pt"), StimProtocol(80, 200, 130, 1)
        )
        checks = {c.name: c for c in calc.assess().checks}
        assert checks["Shannon criterion"].status is Status.NOT_EVALUATED
        assert checks["Microelectrode charge/phase"].status is Status.FAIL

    def test_macroelectrode_uses_shannon_and_not_the_microelectrode_criterion(self):
        calc = SafetyCalculator(
            CylindricalBandElectrode(1270, 1500, "PtIr"), StimProtocol(3000, 60, 130, 1)
        )
        checks = {c.name: c for c in calc.assess().checks}
        assert checks["Microelectrode charge/phase"].status is Status.NOT_EVALUATED
        assert checks["Shannon criterion"].status is not Status.NOT_EVALUATED

    def test_overall_status_is_worst_check(self):
        calc = SafetyCalculator(
            RingElectrode(330, 270, "Pt"), StimProtocol(80, 200, 130, 1)
        )
        assessment = calc.assess()
        worst = max(c.status.rank for c in assessment.checks)
        assert assessment.status.rank == worst

    def test_monophasic_fails_charge_balance(self):
        calc = SafetyCalculator(
            DiscElectrode(500.0, "SIROF"),
            StimProtocol(10, 100, 50, 1, waveform="monophasic"),
        )
        balance = next(
            c for c in calc.assess().checks if c.name == "Charge balance"
        )
        assert balance.status is Status.FAIL

    def test_limiting_mechanism_matches_limiting_current(self):
        calc = SafetyCalculator(
            RingElectrode(330, 270, "Pt"),
            StimProtocol(80, 200, 130, 1),
            compliance_V=10.0,
        )
        assessment = calc.assess()
        assert assessment.limiting_current_uA == pytest.approx(
            min(
                assessment.shannon.max_current_uA,
                assessment.charge.max_current_uA,
                assessment.compliance.max_current_uA,
            )
        )

    def test_compliance_not_evaluated_without_a_voltage(self):
        calc = SafetyCalculator(DiscElectrode(500.0, "SIROF"), StimProtocol(5, 100, 50, 1))
        check = next(c for c in calc.assess().checks if c.name == "Compliance voltage")
        assert check.status is Status.NOT_EVALUATED

    def test_water_window_not_evaluated_for_material_without_one(self):
        """Ta2O5 has no window because a capacitor electrode does not have one.

        Its ceiling is dielectric breakdown at 80 % of the anodisation forming voltage,
        which is a property of the individual electrode rather than of the material, so
        there is nothing to store. The check must report NOT_EVALUATED rather than
        passing by default. SS316LVM stood here until Riedy & Walter's 1.2 V reversible
        injection limit was read out of the primary text.
        """
        calc = SafetyCalculator(
            DiscElectrode(500.0, "Ta2O5"), StimProtocol(1, 100, 50, 1)
        )
        check = next(c for c in calc.assess().checks if c.name == "Water window")
        assert check.status is Status.NOT_EVALUATED

    def test_pulse_width_mismatch_raises_caution(self):
        """Pt's limit is measured at 200 us; a 20 us protocol must be flagged."""
        calc = SafetyCalculator(
            DiscElectrode(2000.0, "Pt"), StimProtocol(1, 20, 50, 1)
        )
        check = next(
            c for c in calc.assess().checks if c.name == "Charge injection limit"
        )
        assert check.status is Status.CAUTION
        assert "pulse-width dependent" in check.detail

    def test_policy_changes_the_limit(self):
        electrode = DiscElectrode(500.0, "Pt")
        protocol = StimProtocol(10, 200, 50, 1)
        conservative = SafetyCalculator(electrode, protocol, policy="conservative")
        optimistic = SafetyCalculator(electrode, protocol, policy="optimistic")
        # Cathodic-first default -> 100-150 uC/cm^2, a 1.5x span rather than the 3x
        # of the polarity-agnostic union.
        assert optimistic.max_current_cic_uA == pytest.approx(
            1.5 * conservative.max_current_cic_uA
        )

    def test_anodic_first_flips_the_potential_excursion(self):
        electrode = DiscElectrode(500.0, "Pt")
        cathodic = SafetyCalculator(electrode, StimProtocol(5, 100, 50, 1)).assess()
        anodic = SafetyCalculator(
            electrode, StimProtocol(5, 100, 50, 1, anodic_first=True)
        ).assess()
        assert cathodic.water_window.peak_potential_V < 0
        assert anodic.water_window.peak_potential_V > 0


class TestBackwardCompatibility:
    """The 0.1.0 prototype's public surface must keep working."""

    def test_original_import_and_call_pattern(self):
        from neurostim import RingElectrode, SafetyCalculator, StimProtocol

        e = RingElectrode(330, 270, "SS")
        p = StimProtocol(80, 200, 130, 1)
        report = SafetyCalculator(e, p).report()
        for key in (
            "area_cm2",
            "charge_uC",
            "charge_density_uC_cm2",
            "shannon_metric",
            "max_current_shannon_uA",
            "max_current_cic_uA",
        ):
            assert key in report

    def test_original_numeric_results_unchanged(self):
        """Values that did not depend on a corrected literature constant must match."""
        calc = SafetyCalculator(RingElectrode(330, 270, "SS"), StimProtocol(80, 200, 130, 1))
        report = calc.report()
        assert report["area_cm2"] == pytest.approx(2.827433388e-4)
        assert report["charge_uC"] == pytest.approx(0.016)
        assert report["charge_density_uC_cm2"] == pytest.approx(56.588424, rel=1e-6)
        assert report["shannon_metric"] == pytest.approx(-0.043152417, rel=1e-6)

    def test_shannon_current_limit_changed_with_the_default_k(self):
        """max_current_shannon_uA moved when the default k was corrected to 1.5.

        The prototype used k = 1.7, which came from Merrill's figure and had no safety
        justification. Shannon (1992) recommends 1.5 and uses it throughout his own
        paper, so the limit is now 1.26x lower. This is a deliberate, sourced change.
        """
        calc = SafetyCalculator(RingElectrode(330, 270, "SS"), StimProtocol(80, 200, 130, 1))
        assert calc.k == shannon.K_SHANNON == 1.5
        assert calc.max_current_shannon_uA == pytest.approx(472.7877282, rel=1e-6)
        at_old_default = SafetyCalculator(
            RingElectrode(330, 270, "SS"), StimProtocol(80, 200, 130, 1), k=1.7
        )
        assert at_old_default.max_current_shannon_uA == pytest.approx(595.2044855, rel=1e-6)

    def test_stimprotocol_still_importable_from_safety(self):
        from neurostim.safety import StimProtocol as FromSafety

        assert FromSafety is StimProtocol

    def test_default_k_is_shannons_own_value_not_the_prototypes(self):
        """Deliberate break with 0.1.0: 1.7 -> 1.5, per Shannon (1992)."""
        calc = SafetyCalculator(DiscElectrode(100.0), StimProtocol(10, 100, 50, 1))
        assert calc.k == 1.5


class TestValidatedEnvelope:
    """Refusing an unqualified PASS outside the conditions the fit was derived at."""

    def test_matched_protocol_supports_an_unqualified_pass(self):
        """Pulse width, frequency, duration and area all match the fit conditions.

        Duty cycle is necessarily far below McCreery's continuous stimulation for any
        realistic pulse train, but in the safer direction, so it does not block a pass.
        """
        from neurostim.safety import envelope

        result = envelope.evaluate(StimProtocol(50, 400, 50, 7 * 3600), area_cm2=0.1)
        assert result.supports_unqualified_pass
        assert not result.concerning
        duty = next(e for e in result.excursions if e.parameter == "duty cycle")
        assert duty.direction == "conservative"

    def test_duty_cycle_cites_the_measured_contrast(self):
        """McCreery 2010: 50 % duty shrank the damage radius from >=150 um to ~60 um."""
        from neurostim.safety import envelope

        result = envelope.evaluate(StimProtocol(50, 400, 50, 3600))
        duty = next(e for e in result.excursions if e.parameter == "duty cycle")
        assert "60" in duty.rationale and "150" in duty.rationale

    def test_higher_frequency_reduces_margin(self):
        from neurostim.safety import envelope

        result = envelope.evaluate(StimProtocol(50, 400, 130, 3600))
        freq = next(e for e in result.excursions if e.parameter == "frequency")
        assert freq.direction == "non_conservative"
        assert freq.fold == pytest.approx(2.6)
        assert not result.supports_unqualified_pass

    def test_lower_frequency_is_the_safe_direction(self):
        from neurostim.safety import envelope

        result = envelope.evaluate(StimProtocol(50, 400, 10, 3600))
        freq = next(e for e in result.excursions if e.parameter == "frequency")
        assert freq.direction == "conservative"
        assert not freq.concerning
        assert result.supports_unqualified_pass

    def test_pulse_width_departure_is_unknown_in_both_directions(self):
        from neurostim.safety import envelope

        for width in (60.0, 2000.0):
            result = envelope.evaluate(StimProtocol(50, width, 50, 3600))
            pw = next(e for e in result.excursions if e.parameter == "pulse width")
            assert pw.direction == "unknown"
            assert pw.concerning

    def test_continuous_stimulation_is_unbounded(self):
        from neurostim.safety import envelope

        result = envelope.evaluate(StimProtocol(50, 400, 50, math.inf))
        duration = next(e for e in result.excursions if e.parameter == "duration")
        assert math.isinf(duration.fold)
        assert duration.direction == "non_conservative"
        assert "continuous" in duration.describe()

    def test_area_outside_the_fitted_range_blocks_a_clean_pass(self):
        from neurostim.safety import envelope

        result = envelope.evaluate(StimProtocol(50, 400, 50, 3600), area_cm2=1e-5)
        assert not result.area_in_range
        assert not result.supports_unqualified_pass

    def test_shannon_cannot_report_clean_pass_outside_the_envelope(self):
        """Clinical DBS rates: the criterion is being asked a question its data
        cannot answer, so a bare PASS would overstate the evidence."""
        calc = SafetyCalculator(
            CylindricalBandElectrode(1270, 1500, "PtIr"),
            StimProtocol(500, 60, 130, math.inf),
        )
        checks = {c.name: c for c in calc.assess().checks}
        assert checks["Shannon criterion"].status is Status.CAUTION
        assert "outside validated envelope" in checks["Shannon criterion"].summary
        assert checks["Validated envelope"].status is Status.CAUTION

    def test_matched_protocol_gives_a_clean_shannon_pass(self):
        calc = SafetyCalculator(
            DiscElectrode(2000.0, "SIROF"), StimProtocol(20, 400, 50, 3600)
        )
        checks = {c.name: c for c in calc.assess().checks}
        assert checks["Validated envelope"].status is Status.PASS
        assert checks["Shannon criterion"].status is Status.PASS


class TestCurrentDensity:
    """The quantity that governs electroporation, previously not computed at all."""

    def test_average_density(self):
        from neurostim.safety import current_density as jd

        assert jd.average_current_density_A_per_cm2(1000.0, 0.01) == pytest.approx(0.1)

    def test_disc_centre_runs_at_half_the_average(self):
        from neurostim.safety import current_density as jd

        assert jd.disc_ratio_at_radius(0.0) == pytest.approx(0.5)

    def test_density_diverges_at_the_rim(self):
        from neurostim.safety import current_density as jd

        assert jd.disc_ratio_at_radius(0.99) > 3.0
        with pytest.raises(ValueError, match="diverges at the rim"):
            jd.disc_ratio_at_radius(1.0)

    def test_outer_quarter_of_a_disc_exceeds_its_own_average(self):
        """Analytic: J/J_avg > 1 requires r/a > sqrt(3)/2, so 1 - 3/4 = 25 % of area."""
        from neurostim.safety import current_density as jd

        assert jd.disc_ratio_at_area_fraction(0.25) == pytest.approx(1.0)
        assert pytest.approx(0.25) == jd.DISC_FRACTION_ABOVE_AVERAGE

    def test_analytic_result_agrees_with_kuncel_grill_fem(self):
        """25 % analytic for a disc vs 25.6 % from their finite element band model --
        different geometry, different method, close agreement."""
        from neurostim.data import current_distribution as cd
        from neurostim.safety import current_density as jd

        assert pytest.approx(
            cd.DBS_FRACTION_ABOVE_AVERAGE, abs=0.01
        ) == jd.DISC_FRACTION_ABOVE_AVERAGE

    def test_now_compared_against_the_butterwick_threshold(self):
        """0.5.0 reported the value with no threshold; Butterwick 2007 supplies one."""
        calc = SafetyCalculator(DiscElectrode(500.0, "Pt"), StimProtocol(10, 200, 50, 1))
        check = next(
            c for c in calc.assess().checks if c.name == "Current density"
        )
        assert check.status is not Status.NOT_EVALUATED
        assert "electroporation threshold" in check.summary
        assert "Butterwick" in check.detail
        assert "extrapolation across preparation" in check.detail


class TestInVivoDerating:
    """Cogan 2016 reports in vivo capacity up to 10x below the saline value."""

    def test_saline_is_the_default(self):
        calc = SafetyCalculator(DiscElectrode(500.0, "Pt"), StimProtocol(10, 200, 50, 1))
        assert calc.assess().charge.derating_applied == pytest.approx(1.0)

    def test_platinum_derating_from_leung(self):
        electrode = DiscElectrode(500.0, "Pt")
        protocol = StimProtocol(10, 200, 50, 1)
        saline = SafetyCalculator(electrode, protocol).assess().charge
        in_vivo = SafetyCalculator(
            electrode, protocol, medium="in_vivo"
        ).assess().charge
        # Leung et al. 2014 measured 34-54 uC/cm^2 in vitro against 3.84-16.6 in vivo.
        assert in_vivo.derating_applied == pytest.approx(14.0)
        assert in_vivo.cic_limit_uC_cm2 == pytest.approx(saline.cic_limit_uC_cm2 / 14)
        # The derated limit should land inside Leung's measured in vivo range.
        assert 3.5 <= in_vivo.cic_limit_uC_cm2 <= 17.0

    def test_sirof_derates_fourfold(self):
        result = SafetyCalculator(
            DiscElectrode(500.0, "SIROF"), StimProtocol(10, 200, 50, 1), medium="in_vivo"
        ).assess().charge
        assert result.derating_applied == pytest.approx(4.0)

    def test_material_without_reported_derating_is_flagged_not_silently_passed(self):
        result = SafetyCalculator(
            DiscElectrode(500.0, "TiN"), StimProtocol(10, 200, 50, 1), medium="in_vivo"
        ).assess().charge
        assert result.derating_applied == pytest.approx(1.0)
        assert "no in vivo derating is reported" in result.derating_note

    def test_interval_is_derated_too(self):
        result = SafetyCalculator(
            DiscElectrode(500.0, "Pt"), StimProtocol(10, 200, 50, 1), medium="in_vivo"
        ).assess().charge
        assert result.limit_interval_uC_cm2.high == pytest.approx(150.0 / 14.0)

    def test_invalid_medium_rejected(self):
        with pytest.raises(ValueError, match="medium must be"):
            SafetyCalculator(
                DiscElectrode(500.0, "Pt"), StimProtocol(10, 200, 50, 1), medium="brain"
            ).assess()


class TestElectrodePresets:
    """Presets reproduce the electrodes their sources describe."""

    def test_every_preset_cites_a_known_reference(self):
        from neurostim import list_presets
        from neurostim.references import cite

        for preset in list_presets():
            assert cite(preset.reference) is not None

    @pytest.mark.parametrize(
        ("key", "stated_area_cm2"),
        [
            ("dbs_3389", 0.06),
            ("mccreery_surface_smallest", 0.01),
            ("mccreery_surface_largest", 0.5),
            ("mccreery_microelectrode", 6.5e-5),
            ("mccreery2010_chronic", 2e-5),
            ("rose_robblee_typeA", 9.5e-3),
            ("beebe_iridium_wire", 4.1e-4),
            ("weiland_tin", 4e-5),
        ],
    )
    def test_preset_area_matches_its_source(self, key, stated_area_cm2):
        from neurostim import get_preset

        assert get_preset(key).electrode.area_cm2 == pytest.approx(
            stated_area_cm2, rel=0.02
        )

    def test_preset_drives_an_assessment(self):
        from neurostim import electrode

        assessment = SafetyCalculator(
            electrode("dbs_3389"), StimProtocol(3000, 60, 130, 1), compliance_V=10.0
        ).assess()
        assert assessment.limiting_current_uA > 0

    def test_unknown_preset_raises(self):
        from neurostim import get_preset

        with pytest.raises(KeyError, match="Unknown electrode preset"):
            get_preset("utah_array")


class TestAuditRecord:
    """Reproducibility records."""

    @pytest.fixture
    def calc(self):
        from neurostim import electrode

        return SafetyCalculator(
            electrode("dbs_3389"), StimProtocol(3000, 60, 130, 1), compliance_V=10.0
        )

    def test_digest_is_self_consistent(self, calc):
        from neurostim import audit

        assert audit.record(calc).digest_matches

    def test_same_configuration_gives_the_same_digest(self, calc):
        from neurostim import audit

        assert audit.record(calc).digest == audit.record(calc).digest

    def test_digest_ignores_operator_and_note(self, calc):
        """The same calculation by different people must reproduce."""
        from neurostim import audit

        a = audit.record(calc, operator="alice", note="run 1")
        b = audit.record(calc, operator="bob", note="run 2")
        assert a.digest == b.digest

    def test_changing_a_setting_breaks_reproduction_and_says_why(self, calc):
        from neurostim import audit, electrode

        original = audit.record(calc)
        changed = SafetyCalculator(
            electrode("dbs_3389"),
            StimProtocol(3000, 60, 130, 1),
            compliance_V=10.0,
            k=1.7,
        )
        ok, diffs = audit.reproduces(original, changed)
        assert not ok
        assert any("shannon_k" in d for d in diffs)

    def test_digest_covers_constants_not_just_inputs(self, calc):
        """A corrected constant must invalidate an old record, which is the point."""
        from neurostim import audit

        record = audit.record(calc)
        assert "cic_low" in record.constants
        assert "cic_reference" in record.constants

    def test_round_trips_through_json(self, calc):
        from neurostim import audit

        original = audit.record(calc, operator="kk")
        restored = audit.load(original.to_json())
        assert restored.digest == original.digest
        assert restored.digest_matches
        assert restored.operator == "kk"


class TestSensitivity:
    """Ranking the inputs by how much each moves the answer."""

    def test_ranked_by_influence(self):
        from neurostim import electrode, sensitivity

        calc = SafetyCalculator(
            electrode("dbs_3389"), StimProtocol(3000, 60, 130, 1), compliance_V=10.0
        )
        rows = sensitivity.analyse(calc)
        folds = [r.fold for r in rows]
        assert folds == sorted(folds, reverse=True)

    def test_irrelevant_inputs_report_no_influence(self):
        """When compliance voltage binds, the damage criteria cannot move the answer."""
        from neurostim import electrode, sensitivity

        calc = SafetyCalculator(
            electrode("dbs_3389"), StimProtocol(3000, 60, 130, 1), compliance_V=10.0
        )
        by_name = {r.parameter: r for r in sensitivity.analyse(calc)}
        assert by_name["Shannon k"].fold == pytest.approx(1.0)
        assert not by_name["Shannon k"].dominates

    def test_charge_limited_case_makes_the_material_matter(self):
        """Flip the binding constraint and the CIC policy should start to dominate."""
        from neurostim import sensitivity

        calc = SafetyCalculator(
            DiscElectrode(500.0, "Pt"), StimProtocol(500, 200, 50, 1)
        )
        by_name = {r.parameter: r for r in sensitivity.analyse(calc)}
        assert by_name["CIC policy"].fold > 1.0

    def test_report_names_the_dominant_inputs(self):
        from neurostim import electrode, sensitivity

        calc = SafetyCalculator(
            electrode("dbs_3389"), StimProtocol(3000, 60, 130, 1), compliance_V=10.0
        )
        text = sensitivity.describe(calc)
        assert "Dominant:" in text
        assert "not error bars" in text


class TestVoltageTransient:
    """Extracting electrode parameters from a measured pulse."""

    @staticmethod
    def _synthetic(current_uA=500.0, pulse_us=200.0, area_cm2=9.5e-3,
                   resistance_ohm=800.0, capacitance_uF_cm2=250.0, n=2601,
                   resting_V=0.0):
        """Ohmic step plus a linear capacitive ramp, the shape Rose & Robblee show."""
        import numpy as np

        t = np.linspace(-20.0, pulse_us + 40.0, n)
        access = -(current_uA * 1e-6) * resistance_ohm
        density = current_uA * pulse_us * 1e-6 / area_cm2
        ramp = (density / capacitance_uF_cm2) * np.clip(t, 0.0, pulse_us) / pulse_us
        v = np.where(t < 0.0, resting_V, resting_V + access - ramp)
        return t, v

    def test_recovers_access_resistance(self):
        from neurostim import transient

        t, v = self._synthetic(resistance_ohm=800.0)
        result = transient.analyse(
            t, v, current_uA=500.0, pulse_width_us=200.0, area_cm2=9.5e-3
        )
        assert result.access_resistance_ohm == pytest.approx(800.0, rel=0.01)

    def test_recovers_interfacial_capacitance(self):
        from neurostim import transient

        t, v = self._synthetic(capacitance_uF_cm2=250.0)
        result = transient.analyse(
            t, v, current_uA=500.0, pulse_width_us=200.0, area_cm2=9.5e-3
        )
        assert result.effective_capacitance_uF_cm2 == pytest.approx(250.0, rel=0.02)

    def test_separates_polarisation_from_the_ohmic_step(self):
        """The whole point: the peak is not the excursion."""
        from neurostim import transient

        t, v = self._synthetic()
        result = transient.analyse(
            t, v, current_uA=500.0, pulse_width_us=200.0, area_cm2=9.5e-3
        )
        assert abs(result.peak_potential_V) > result.max_polarisation_V
        assert result.max_polarisation_V == pytest.approx(
            abs(result.peak_potential_V) - abs(result.access_voltage_V), rel=1e-6
        )

    def test_extrapolated_limit_agrees_with_the_literature(self):
        """A synthetic electrode built with the capacitance the package derives for Pt
        should yield the charge-injection limit the package stores for Pt."""
        from neurostim import get_material, transient
        from neurostim.safety import water_window as ww

        material = get_material("Pt")
        c_eff = ww.effective_capacitance_uF_cm2(material, anodic_first=False)
        t, v = self._synthetic(capacitance_uF_cm2=c_eff)
        result = transient.analyse(
            t, v, current_uA=500.0, pulse_width_us=200.0, area_cm2=9.5e-3
        )
        limit = transient.charge_injection_limit_uC_cm2(
            result, material.water_window.cathodic_V
        )
        assert limit == pytest.approx(
            material.cic_uC_cm2("optimistic", anodic_first=False), rel=0.05
        )

    def test_respects_a_non_zero_resting_potential(self):
        from neurostim import transient

        t, v = self._synthetic(resting_V=0.3)
        result = transient.analyse(
            t, v, current_uA=500.0, pulse_width_us=200.0, area_cm2=9.5e-3
        )
        assert result.resting_potential_V == pytest.approx(0.3, abs=1e-6)
        assert result.access_resistance_ohm == pytest.approx(800.0, rel=0.01)

    def test_flags_an_under_resolved_trace(self):
        """Too few samples in the step means polarisation is folded into V_a."""
        from neurostim import transient

        t, v = self._synthetic(n=25)
        result = transient.analyse(
            t, v, current_uA=500.0, pulse_width_us=200.0, area_cm2=9.5e-3
        )
        assert not result.access_estimate_is_well_resolved
        assert "CAUTION" in result.describe()

    def test_well_resolved_trace_is_not_flagged(self):
        from neurostim import transient

        t, v = self._synthetic()
        result = transient.analyse(
            t, v, current_uA=500.0, pulse_width_us=200.0, area_cm2=9.5e-3
        )
        assert result.access_estimate_is_well_resolved

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"pulse_width_us": 0.0},
            {"area_cm2": 0.0},
            {"access_window_fraction": 0.0},
            {"access_window_fraction": 1.0},
        ],
    )
    def test_invalid_inputs_rejected(self, kwargs):
        from neurostim import transient

        t, v = self._synthetic()
        base = {
            "current_uA": 500.0,
            "pulse_width_us": 200.0,
            "area_cm2": 9.5e-3,
        }
        with pytest.raises(ValueError):
            transient.analyse(t, v, **{**base, **kwargs})

    def test_mismatched_arrays_rejected(self):
        import numpy as np

        from neurostim import transient

        with pytest.raises(ValueError, match="same shape"):
            transient.analyse(
                np.arange(10.0), np.arange(5.0),
                current_uA=500.0, pulse_width_us=200.0, area_cm2=9.5e-3,
            )
