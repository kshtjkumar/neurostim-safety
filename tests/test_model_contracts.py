"""Contracts and closed forms of the modules the branch-point floor found untested (G3).

Each test either checks a value against an analytic solution or a published number, or
checks that a documented input contract holds: the guard's own message says what is
refused, so an input that should be refused must raise with it. Before this file these
modules sat below 60 % of branch points fully exercised: the refusal side of their guards
had never run, and several reported quantities (a fitted curve's predictions, the FEM
field's gradient, a measured transient's coarse-trace fallback) had never been checked.
"""

from __future__ import annotations

import math
from dataclasses import replace
from typing import Any

import numpy as np
import pytest

from neurostim import DiscElectrode, transient
from neurostim.data import asanuma1976, gabriel1996, iso14708_3, ta2o5_capacitor
from neurostim.geometry import linear_array
from neurostim.io import fem
from neurostim.models import field, thermal, vta
from neurostim.models import strength_duration as sd

# --- data modules -------------------------------------------------------------------


class TestAsanuma1976:
    def test_the_printed_rheobases_and_the_corrected_one(self) -> None:
        # Figure 4 prints 20 uA for the first fibre; the module corrects the suspected typo.
        assert asanuma1976.rheobase_fibres_ua(as_printed=True) == (20.0, 2.5, 1.0)
        assert asanuma1976.rheobase_fibres_ua() == (2.0, 2.5, 1.0)

    def test_an_unknown_structure_names_the_known_ones(self) -> None:
        with pytest.raises(KeyError, match="cortical cell bodies"):
            asanuma1976.chronaxie_for("cerebellar granule cells")
        assert asanuma1976.chronaxie_for("  Cortical Cell Bodies ").median_ms == 0.14

    def test_the_threshold_ratio_is_two_at_chronaxie(self) -> None:
        assert asanuma1976.threshold_ratio_at(140.0, 140.0) == 2.0
        assert asanuma1976.threshold_ratio_at(70.0, 140.0) == 3.0
        for bad in ((0.0, 140.0), (140.0, 0.0), (-1.0, 140.0)):
            with pytest.raises(ValueError, match="must both be > 0"):
                asanuma1976.threshold_ratio_at(*bad)


class TestGabriel1996:
    def test_the_effective_frequency_is_one_over_twice_the_width(self) -> None:
        assert gabriel1996.effective_frequency_hz(100.0) == pytest.approx(5000.0)
        with pytest.raises(ValueError, match="pulse_width_us"):
            gabriel1996.effective_frequency_hz(0.0)

    def test_a_non_positive_frequency_is_refused(self) -> None:
        tissue = gabriel1996.get("grey matter")
        for frequency in (0.0, -10.0):
            with pytest.raises(ValueError, match="frequency_hz"):
                tissue.complex_permittivity(frequency)


class TestIso14708Cem43:
    def test_one_minute_at_43_is_one_equivalent_minute(self) -> None:
        # CEM43 = sum t R^(43 - T): at 43 C the factor is 1 by definition.
        assert iso14708_3.cem43_steady(43.0, 1.0) == 1.0
        assert iso14708_3.cem43_steady(44.0, 1.0) == pytest.approx(2.0)  # R = 0.5 above 43
        assert iso14708_3.cem43_steady(42.0, 1.0) == pytest.approx(0.25)  # R = 0.25 below

    def test_below_39_contributes_nothing(self) -> None:
        assert iso14708_3.cem43([37.0, 38.9], [600.0, 600.0]) == 0.0

    def test_malformed_histories_are_refused(self) -> None:
        with pytest.raises(ValueError, match="same length"):
            iso14708_3.cem43([40.0, 41.0], [1.0])
        with pytest.raises(ValueError, match="durations must be >= 0"):
            iso14708_3.cem43([40.0], [-1.0])
        with pytest.raises(ValueError, match="must be finite"):
            iso14708_3.cem43([math.nan], [1.0])


class TestTa2O5Capacitor:
    @staticmethod
    def _design(forming_voltage_V: float | None) -> ta2o5_capacitor.CapacitorElectrode:
        return ta2o5_capacitor.CapacitorElectrode(
            label="test design",
            dielectric="Ta2O5",
            preparation="test",
            charge_storage_uC_mm2=1.0,
            reference="rose1985",
            forming_voltage_V=forming_voltage_V,
        )

    def test_the_safe_voltage_is_eighty_percent_of_forming(self) -> None:
        assert self._design(10.0).safe_operating_voltage_V == pytest.approx(8.0)
        assert self._design(None).safe_operating_voltage_V is None

    def test_the_smooth_capacitance_scales_inversely_with_forming_voltage(self) -> None:
        # 22 nF/mm^2 measured at 5 V; thickness grows with V_f, so C halves at 10 V.
        assert ta2o5_capacitor.smooth_capacitance_nF_mm2(5.0) == pytest.approx(22.0)
        assert ta2o5_capacitor.smooth_capacitance_nF_mm2(10.0) == pytest.approx(11.0)

    def test_the_rose_barium_titanate_case(self) -> None:
        # Rose et al. eq. (1): 10 nm, k = 7000, 1e-4 mm^2, pulsed to 4 V -> about 2.4 nC.
        c = ta2o5_capacitor.parallel_plate_capacitance_F(7000.0, 1e-4 * 1e-6, 10e-9)
        assert c * 4.0 * 1e9 == pytest.approx(2.48, abs=0.01)

    @pytest.mark.parametrize("value", [0.0, -5.0])
    def test_non_positive_inputs_are_refused(self, value: float) -> None:
        with pytest.raises(ValueError, match="forming_voltage_V"):
            ta2o5_capacitor.safe_operating_voltage_V(value)
        with pytest.raises(ValueError, match="forming_voltage_V"):
            ta2o5_capacitor.smooth_capacitance_nF_mm2(value)
        with pytest.raises(ValueError, match="measured_capacitance_uF_mm2"):
            ta2o5_capacitor.roughness_factor(value, 10.0)
        with pytest.raises(ValueError, match="must all be > 0"):
            ta2o5_capacitor.parallel_plate_capacitance_F(7000.0, 1e-10, value)


# --- models -------------------------------------------------------------------------


class TestFieldContracts:
    def test_a_distance_at_or_inside_the_source_is_refused(self) -> None:
        for bad in (0.0, -1.0):
            with pytest.raises(ValueError, match="distance_um must be > 0"):
                field.field_V_per_m(100.0, bad)
            with pytest.raises(ValueError, match="distance_um must be > 0"):
                field.current_density_A_per_m2(100.0, bad)

    def test_a_radial_profile_needs_an_increasing_range_of_two_points(self) -> None:
        with pytest.raises(ValueError, match="must exceed"):
            field.radial_profile(100.0, 500.0, 500.0)
        with pytest.raises(ValueError, match="n_points"):
            field.radial_profile(100.0, 100.0, 500.0, n_points=1)

    def test_a_linear_profile_is_evenly_spaced_and_follows_one_over_r(self) -> None:
        profile = field.radial_profile(100.0, 100.0, 500.0, n_points=5, log_spaced=False)
        assert np.allclose(profile.distance_um, [100.0, 200.0, 300.0, 400.0, 500.0])
        expected = 100e-6 / (4.0 * math.pi * 0.35 * profile.distance_um * 1e-6)
        assert np.allclose(profile.potential_V, expected, rtol=1e-12)

    def test_equal_and_opposite_sites_cancel_midway(self) -> None:
        array = linear_array(DiscElectrode(100.0, "Pt"), 2, 1000.0)
        a, b = (np.asarray(site.position_um(), dtype=float) for site in array.sites)
        midway = ((a + b) / 2.0)[None, :] + np.array([[300.0, 0.0, 0.0]])
        v = field.array_potential_V(array, [100.0, -100.0], midway)
        assert v[0] == pytest.approx(0.0, abs=1e-15)

    def test_array_inputs_are_checked(self) -> None:
        array = linear_array(DiscElectrode(100.0, "Pt"), 2, 1000.0)
        with pytest.raises(ValueError, match="shape"):
            field.array_potential_V(array, [100.0, -100.0], np.zeros((2, 2)))
        site = np.asarray(array.sites[0].position_um(), dtype=float)[None, :]
        with pytest.raises(ValueError, match="coincides"):
            field.array_potential_V(array, [100.0, -100.0], site)


class TestStrengthDurationContracts:
    def test_a_fit_predicts_the_curve_it_was_fit_to(self) -> None:
        widths = np.array([50.0, 100.0, 200.0, 400.0, 800.0])
        weiss = np.asarray(sd.weiss_threshold_uA(widths, 20.0, 150.0))
        assert np.allclose(sd.fit_weiss(widths, weiss).threshold_uA(widths), weiss, rtol=1e-9)
        lapicque = sd.lapicque_threshold_uA(widths, 20.0, 200.0)
        fit = sd.fit_lapicque(widths, np.asarray(lapicque))
        assert np.allclose(fit.threshold_uA(widths), lapicque, rtol=1e-6)

    def test_malformed_designs_are_refused(self) -> None:
        with pytest.raises(ValueError, match="same shape"):
            sd.fit_weiss(np.array([100.0, 200.0]), np.array([40.0]))
        with pytest.raises(ValueError, match="must all be > 0"):
            sd.fit_weiss(np.array([100.0, 200.0]), np.array([40.0, 0.0]))
        # Thresholds that fall with width: a negative rheobase, which no nerve has.
        with pytest.raises(ValueError, match="rheobase is non-positive"):
            sd.fit_weiss(np.array([100.0, 200.0, 400.0]), np.array([80.0, 20.0, 5.0]))

    def test_non_positive_parameters_and_widths_are_refused(self) -> None:
        with pytest.raises(ValueError, match="pulse_width_us"):
            sd.lapicque_threshold_uA(0.0, 20.0, 200.0)
        with pytest.raises(ValueError, match="pulse_width_us"):
            sd.weiss_threshold_charge_uC(0.0, 20.0, 150.0)
        with pytest.raises(ValueError, match="rheobase_uA"):
            sd.lapicque_threshold_uA(100.0, math.nan, 200.0)


class TestCurrentDistanceContracts:
    def test_the_constants_are_checked(self) -> None:
        with pytest.raises(ValueError, match="k_uA_per_mm2"):
            vta.CurrentDistanceModel(k_uA_per_mm2=0.0)
        with pytest.raises(ValueError, match="threshold_offset_uA"):
            vta.CurrentDistanceModel(threshold_offset_uA=-1.0)

    def test_negative_distances_and_currents_are_refused(self) -> None:
        model = vta.CurrentDistanceModel()
        with pytest.raises(ValueError, match="distance_um"):
            model.threshold_uA(-1.0)
        with pytest.raises(ValueError, match="current_uA"):
            model.activation_radius_um(-1.0)

    def test_a_fitted_model_is_provisional_and_recovers_its_data(self) -> None:
        r = np.array([100.0, 200.0, 300.0])
        thresholds = 5.0 + 1300.0 * (r * 1e-3) ** 2
        model = vta.fit_current_distance(r, thresholds)
        assert model.k_uA_per_mm2 == pytest.approx(1300.0, rel=1e-9)
        assert model.threshold_offset_uA == pytest.approx(5.0, rel=1e-9)
        assert "PROVISIONAL" in model.describe()
        assert "PROVISIONAL" not in vta.CurrentDistanceModel().describe()

    def test_malformed_fits_are_refused(self) -> None:
        with pytest.raises(ValueError, match="same shape"):
            vta.fit_current_distance(np.array([100.0, 200.0]), np.array([10.0]))
        with pytest.raises(ValueError, match="at least 2 points"):
            vta.fit_current_distance(np.array([100.0]), np.array([10.0]))
        # Thresholds that fall with distance.
        with pytest.raises(ValueError, match="non-positive"):
            vta.fit_current_distance(
                np.array([100.0, 200.0, 300.0]), np.array([60.0, 40.0, 20.0])
            )


# --- thermal ------------------------------------------------------------------------


class TestThermalContracts:
    def test_the_itis_perfusion_conversion(self) -> None:
        # IT'IS v4.2 grey matter: 763.7 ml/min/kg at 1044.5 kg/m^3 -> 0.01329 1/s.
        assert thermal.perfusion_per_s(763.7, 1044.5) == pytest.approx(0.013294, rel=1e-3)
        with pytest.raises(ValueError, match="perfusion must be >= 0"):
            thermal.perfusion_per_s(-1.0, 1044.5)
        with pytest.raises(ValueError, match="tissue density must be > 0"):
            thermal.perfusion_per_s(763.7, 0.0)

    def test_tissue_properties_are_checked(self) -> None:
        with pytest.raises(ValueError, match="thermal_conductivity_W_per_mK"):
            thermal.TissueThermalProperties(thermal_conductivity_W_per_mK=0.0)
        with pytest.raises(ValueError, match="perfusion_rate_per_s"):
            thermal.TissueThermalProperties(perfusion_rate_per_s=-0.01)

    def test_a_tissue_without_a_spread_prints_none(self) -> None:
        text = thermal.ELWASSIF_BRAIN.describe()
        assert "(sd" not in text and "0.527" in text
        assert "(sd 0.02546, n = 2)" in thermal.BRAIN.describe()

    def test_elwassifs_drive_dissipates_5_6_milliwatts(self) -> None:
        # 1.56 V RMS across the two-sphere resistance of 431.6 ohm (C6.3 reproduction).
        assert thermal.voltage_driven_power_W(1.56, 431.6) == pytest.approx(5.639e-3, rel=1e-3)
        with pytest.raises(ValueError, match="v_rms"):
            thermal.voltage_driven_power_W(math.nan, 431.6)

    def test_the_steady_solution_refuses_what_it_cannot_solve(self) -> None:
        with pytest.raises(ValueError, match="power_W"):
            thermal.pennes_steady_state_sphere(-1e-3, 500.0)
        with pytest.raises(ValueError, match="source_radius_um"):
            thermal.pennes_steady_state_sphere(1e-3, 0.0)

    def test_the_transient_refuses_what_it_cannot_solve(self) -> None:
        good = np.array([1.0])
        cases: list[tuple[dict[str, Any], str]] = [
            (dict(times_s=np.array([])), "non-empty"),
            (dict(times_s=np.array([-1.0])), ">= 0"),
            (dict(times_s=good, cells_per_radius=3), "cells_per_radius"),
            (dict(times_s=good, power_W=math.inf), "power_W"),
            (dict(times_s=good, source_radius_um=0.0), "source_radius_um"),
            (dict(times_s=good, domain_extent_factor=0.0), "domain_extent_factor"),
        ]
        for overrides, message in cases:
            kwargs: dict[str, Any] = {"power_W": 1e-3, "source_radius_um": 500.0, **overrides}
            with pytest.raises(ValueError, match=message):
                thermal.pennes_transient_sphere(**kwargs)

    def test_an_explicit_domain_reaches_the_steady_state(self) -> None:
        steady = thermal.pennes_steady_state_sphere(1e-3, 500.0)
        late = thermal.pennes_transient_sphere(
            1e-3, 500.0, np.array([3600.0]), domain_extent_factor=12.0
        )
        assert late[0] == pytest.approx(steady, rel=1e-3)

    def test_an_unsourced_tissue_is_flagged(self) -> None:
        unsourced = replace(thermal.BRAIN, verified_fields=())
        text = thermal.evaluate(100.0, 1000.0, 500.0, unsourced).describe()
        assert "CAUTION: perfusion and heat-capacity values" in text
        assert "CAUTION" not in thermal.evaluate(100.0, 1000.0, 500.0).describe()


# --- measured transients ------------------------------------------------------------


def _capacitor_trace(
    step_us: float, *, r_ohm: float = 1000.0, c_uF_cm2: float = 100.0
) -> tuple[np.ndarray, np.ndarray]:
    """An ideal series RC interface under a 100 uA, 200 us step on 0.01 cm^2."""
    t = np.arange(-50.0, 250.0 + step_us, step_us)
    i_A, area = 100e-6, 0.01
    during = (t >= 0.0) & (t <= 200.0)
    v = np.where(during, i_A * r_ohm + i_A * t * 1e-6 / (c_uF_cm2 * 1e-6 * area), 0.0)
    return t, v


class TestMeasuredTransientContracts:
    def test_a_coarse_trace_falls_back_and_says_so(self) -> None:
        t, v = _capacitor_trace(20.0)
        keep = t != 0.0  # drop the sample at onset, so the 0-4 us window holds none
        t, v = t[keep], v[keep]
        result = transient.analyse(t, v, current_uA=100.0, pulse_width_us=200.0, area_cm2=0.01)
        assert result.samples_in_access_estimate == 1
        assert "CAUTION: access voltage estimated from only 1 sample(s)" in result.describe()

    def test_a_resolved_trace_recovers_r_and_c(self) -> None:
        t, v = _capacitor_trace(0.5)
        result = transient.analyse(t, v, current_uA=100.0, pulse_width_us=200.0, area_cm2=0.01)
        assert result.access_estimate_is_well_resolved
        assert result.access_resistance_ohm == pytest.approx(1000.0, rel=0.02)
        assert result.effective_capacitance_uF_cm2 == pytest.approx(100.0, rel=0.03)
        assert "CAUTION" not in result.describe()

    def test_a_purely_resistive_trace_has_no_capacitance_and_no_limit(self) -> None:
        t, v = _capacitor_trace(0.5, c_uF_cm2=math.inf)
        result = transient.analyse(t, v, current_uA=100.0, pulse_width_us=200.0, area_cm2=0.01)
        assert result.max_polarisation_V == 0.0
        assert result.effective_capacitance_uF_cm2 == math.inf
        with pytest.raises(ValueError, match="no polarisation"):
            transient.charge_injection_limit_uC_cm2(result, -0.6)

    def test_malformed_traces_are_refused(self) -> None:
        with pytest.raises(ValueError, match="at least 4 samples"):
            transient.analyse(np.arange(3.0), np.zeros(3), current_uA=1.0,
                              pulse_width_us=1.0, area_cm2=1.0)
        t, v = _capacitor_trace(0.5)
        with pytest.raises(ValueError, match="no samples fall inside the pulse"):
            transient.analyse(t, v, current_uA=100.0, pulse_width_us=200.0, area_cm2=0.01,
                              pulse_start_us=10_000.0)


# --- FEM import ---------------------------------------------------------------------


def _point_source_field(current_uA: float = 100.0) -> fem.FEMField:
    """A full-space point source, sampled on a 3-D grid that avoids the origin."""
    axis = np.linspace(-2000.0, 2000.0, 21)
    pts = np.array([(x, y, z) for x in axis for y in axis for z in axis])
    pts = pts[np.linalg.norm(pts, axis=1) > 150.0]
    r_m = np.linalg.norm(pts, axis=1) * 1e-6
    v = current_uA * 1e-6 / (4.0 * math.pi * 0.35 * r_m)
    return fem.FEMField(points_um=pts, potential_V=v, source="analytic", current_uA=current_uA)


class TestFemContracts:
    def test_the_gradient_is_the_point_source_field(self) -> None:
        f = _point_source_field()
        query = np.array([[1000.0, 0.0, 0.0]])
        expected = 100e-6 / (4.0 * math.pi * 0.35 * (1e-3) ** 2)
        got = f.gradient_magnitude_V_per_m(query, step_um=200.0)[0]
        assert got == pytest.approx(expected, rel=0.1)  # linear interpolation on a 200 um grid

    def test_the_description_carries_the_current_and_the_note(self) -> None:
        scaled = _point_source_field().scale_to_current(200.0)
        text = scaled.describe()
        assert "solved at 200 uA" in text and "rescaled from 100 uA by 2" in text

    def test_malformed_fields_are_refused(self) -> None:
        with pytest.raises(ValueError, match=r"shape \(n, 3\)"):
            fem.FEMField(points_um=np.zeros((4, 2)), potential_V=np.zeros(4))
        with pytest.raises(ValueError, match="one value per point"):
            fem.FEMField(points_um=np.eye(4, 3), potential_V=np.zeros(3))
        with pytest.raises(ValueError, match="at least 4 points"):
            fem.FEMField(points_um=np.eye(3), potential_V=np.zeros(3))
        f = _point_source_field()
        with pytest.raises(ValueError, match="query_points_um"):
            f.interpolate_V(np.zeros((2, 2)))
        with pytest.raises(ValueError, match="finite"):
            f.scale_to_current(math.nan)

    def test_npz_round_trips_in_both_layouts(self, tmp_path) -> None:
        f = _point_source_field()
        back = fem.load_field(fem.save_field(f, tmp_path / "f.npz"))
        assert back.current_uA == 100.0 and np.array_equal(back.potential_V, f.potential_V)
        xyzv = tmp_path / "xyzv.npz"
        np.savez(xyzv, X=f.points_um[:, 0], Y=f.points_um[:, 1], Z=f.points_um[:, 2],
                 V=f.potential_V)
        loaded = fem.load_field(xyzv, current_uA=100.0)
        assert np.array_equal(loaded.points_um, f.points_um) and loaded.current_uA == 100.0
        bad = tmp_path / "bad.npz"
        np.savez(bad, a=np.zeros(4))
        with pytest.raises(ValueError, match="must contain either"):
            fem.load_field(bad)

    def test_missing_files_and_columns_are_refused(self, tmp_path) -> None:
        with pytest.raises(FileNotFoundError):
            fem.load_field(tmp_path / "absent.csv")
        csv = tmp_path / "f.csv"
        csv.write_text("x,y,z\n0,0,1\n0,1,0\n1,0,0\n1,1,1\n")
        with pytest.raises(ValueError, match="potential"):
            fem.load_field(csv)

    def test_a_field_with_nothing_far_enough_is_refused(self) -> None:
        f = _point_source_field()
        with pytest.raises(ValueError, match="no imported points lie"):
            fem.compare_with_point_source(f, 100.0, min_distance_um=1e6)
