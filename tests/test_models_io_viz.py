"""Physical models, import/export, and figure generation.

The model tests check each analytic solution against an independent limit: the Pennes
steady state against its classical unperfused form and against a finite-difference
solve, the point-source field against the electrode's own access resistance, and both
fitting routines against data they generated themselves.
"""

from __future__ import annotations

import math

import matplotlib
import numpy as np
import pytest

matplotlib.use("Agg")

from neurostim import (
    DiscElectrode,
    RingElectrode,
    SafetyCalculator,
    SphericalElectrode,
    StimProtocol,
)
from neurostim.models import field as field_mod
from neurostim.models import strength_duration as sd
from neurostim.models import thermal, vta


class TestField:
    def test_sphere_surface_potential_equals_current_times_access_resistance(self):
        """The point-source solution and the access resistance must agree exactly."""
        sphere = SphericalElectrode(500.0)
        current_uA, sigma = 100.0, 0.35
        assert field_mod.potential_V(current_uA, sphere.radius_um, sigma) == pytest.approx(
            current_uA * 1e-6 * sphere.access_resistance_ohm(sigma)
        )

    def test_potential_falls_as_inverse_distance(self):
        v1 = field_mod.potential_V(100.0, 100.0)
        v2 = field_mod.potential_V(100.0, 200.0)
        assert v1 / v2 == pytest.approx(2.0)

    def test_field_falls_as_inverse_square(self):
        e1 = field_mod.field_V_per_m(100.0, 100.0)
        e2 = field_mod.field_V_per_m(100.0, 200.0)
        assert e1 / e2 == pytest.approx(4.0)

    def test_hemisphere_doubles_the_potential(self):
        from neurostim import HemisphericalElectrode

        full = field_mod.potential_V(100.0, 500.0)
        half = field_mod.potential_V(
            100.0, 500.0, electrode=HemisphericalElectrode(200.0)
        )
        assert half == pytest.approx(2 * full)

    def test_zero_distance_raises_rather_than_returning_inf(self):
        with pytest.raises(ValueError, match="diverges"):
            field_mod.potential_V(100.0, 0.0)

    def test_invert_potential_round_trip(self):
        r = field_mod.distance_for_potential_um(100.0, 0.05)
        assert field_mod.potential_V(100.0, r) == pytest.approx(0.05)

    def test_array_superposition_matches_manual_sum(self):
        from neurostim.geometry import linear_array

        array = linear_array(DiscElectrode(100.0), 3, 500.0)
        points = np.array([[0.0, 0.0, 2000.0]])
        total = field_mod.array_potential_V(array, [10.0, 20.0, 30.0], points)
        manual = sum(
            field_mod.potential_V(
                current,
                math.dist((0, 0, 2000), site.position_um()),
                electrode=site.electrode,
            )
            for current, site in zip([10.0, 20.0, 30.0], array.sites, strict=True)
        )
        assert total[0] == pytest.approx(manual)

    def test_array_current_count_must_match(self):
        from neurostim.geometry import linear_array

        array = linear_array(DiscElectrode(100.0), 3, 500.0)
        with pytest.raises(ValueError, match="one entry per site"):
            field_mod.array_potential_V(array, [1.0], np.array([[0.0, 0.0, 100.0]]))


class TestThermal:
    def test_unperfused_reduces_to_classical_solution(self):
        """With no perfusion the result must be exactly P / (4 pi kappa a)."""
        tissue = thermal.TissueThermalProperties(perfusion_rate_per_s=0.0)
        power, radius_um = 1e-3, 500.0
        expected = power / (
            4 * math.pi * tissue.thermal_conductivity_W_per_mK * radius_um * 1e-6
        )
        assert thermal.peak_temperature_rise_K(power, radius_um, tissue) == pytest.approx(
            expected
        )

    def test_perfusion_reduces_the_temperature_rise(self):
        unperfused = thermal.TissueThermalProperties(perfusion_rate_per_s=0.0)
        assert thermal.peak_temperature_rise_K(1e-3, 500.0, thermal.BRAIN) < (
            thermal.peak_temperature_rise_K(1e-3, 500.0, unperfused)
        )

    def test_penetration_depth_formula(self):
        expected = math.sqrt(
            thermal.BRAIN.thermal_conductivity_W_per_mK
            / thermal.BRAIN.perfusion_conductance_W_per_m3K
        )
        assert thermal.BRAIN.thermal_penetration_depth_m == pytest.approx(expected)

    def test_penetration_depth_is_infinite_without_perfusion(self):
        tissue = thermal.TissueThermalProperties(perfusion_rate_per_s=0.0)
        assert math.isinf(tissue.thermal_penetration_depth_m)

    def test_transient_converges_to_analytic_steady_state(self):
        """The independent finite-difference solve must reproduce the closed form."""
        analytic = thermal.peak_temperature_rise_K(1e-3, 500.0, thermal.BRAIN)
        numeric = thermal.pennes_transient_sphere(
            1e-3, 500.0, np.array([20000.0]), thermal.BRAIN
        )[0]
        assert numeric == pytest.approx(analytic, rel=1e-3)

    def test_transient_is_grid_independent(self):
        values = [
            thermal.pennes_transient_sphere(
                1e-3, 500.0, np.array([20000.0]), thermal.BRAIN, cells_per_radius=n
            )[0]
            for n in (10, 20, 40)
        ]
        assert values[0] == pytest.approx(values[-1], rel=1e-3)

    def test_transient_starts_at_zero_and_rises_monotonically(self):
        times = np.array([0.0, 1.0, 10.0, 100.0, 1000.0])
        rise = thermal.pennes_transient_sphere(1e-3, 500.0, times, thermal.BRAIN)
        assert rise[0] == 0.0
        assert np.all(np.diff(rise) > 0)

    def test_temperature_decays_with_distance(self):
        r = np.array([500.0, 1000.0, 5000.0])
        rise = thermal.pennes_steady_state_sphere(1e-3, 500.0, r, thermal.BRAIN)
        assert np.all(np.diff(rise) < 0)

    def test_inside_source_radius_raises(self):
        with pytest.raises(ValueError, match="outside the source"):
            thermal.pennes_steady_state_sphere(1e-3, 500.0, 100.0, thermal.BRAIN)

    def test_ohmic_power_scales_with_current_squared(self):
        assert thermal.ohmic_power_W(200.0, 1000.0) == pytest.approx(
            4 * thermal.ohmic_power_W(100.0, 1000.0)
        )

    def test_evaluate_uses_rms_current(self):
        protocol = StimProtocol(100, 200, 100, 1)
        result = thermal.evaluate(protocol.rms_current_uA, 1000.0, 500.0)
        assert result.power_W == pytest.approx(
            (protocol.rms_current_uA * 1e-6) ** 2 * 1000.0
        )


class TestStrengthDuration:
    def test_weiss_fit_recovers_its_own_parameters(self):
        widths = np.array([50.0, 100.0, 200.0, 400.0, 800.0])
        thresholds = sd.weiss_threshold_uA(widths, 20.0, 150.0)
        fit = sd.fit_weiss(widths, thresholds)
        assert fit.rheobase_uA == pytest.approx(20.0)
        assert fit.chronaxie_us == pytest.approx(150.0)

    def test_lapicque_fit_recovers_its_own_parameters(self):
        widths = np.array([50.0, 100.0, 200.0, 400.0, 800.0])
        thresholds = sd.lapicque_threshold_uA(widths, 20.0, 200.0)
        fit = sd.fit_lapicque(widths, thresholds)
        assert fit.rheobase_uA == pytest.approx(20.0, rel=1e-4)
        assert fit.membrane_tau_us == pytest.approx(200.0, rel=1e-4)

    def test_chronaxie_is_pulse_width_at_twice_rheobase(self):
        """True by construction for the Weiss form."""
        assert sd.weiss_threshold_uA(150.0, 20.0, 150.0) == pytest.approx(40.0)

    def test_chronaxie_tau_relationship(self):
        assert sd.chronaxie_from_tau_us(200.0) == pytest.approx(200.0 * math.log(2))
        assert sd.tau_from_chronaxie_us(sd.chronaxie_from_tau_us(200.0)) == pytest.approx(
            200.0
        )

    def test_threshold_falls_with_pulse_width(self):
        widths = np.array([50.0, 100.0, 400.0])
        assert np.all(np.diff(sd.weiss_threshold_uA(widths, 20.0, 150.0)) < 0)

    def test_threshold_charge_rises_with_pulse_width(self):
        """The practical argument for short pulses."""
        widths = np.array([50.0, 100.0, 400.0])
        assert np.all(np.diff(sd.weiss_threshold_charge_uC(widths, 20.0, 150.0)) > 0)

    def test_lapicque_approaches_rheobase_asymptotically(self):
        assert sd.lapicque_threshold_uA(1e6, 20.0, 200.0) == pytest.approx(20.0)

    def test_fit_needs_two_points(self):
        with pytest.raises(ValueError, match="at least 2 points"):
            sd.fit_weiss(np.array([100.0]), np.array([30.0]))


class TestVTA:
    def test_radius_threshold_round_trip(self):
        model = vta.CurrentDistanceModel(k_uA_per_mm2=675.0)
        radii = np.array([100.0, 300.0, 1000.0])
        assert np.allclose(model.activation_radius_um(model.threshold_uA(radii)), radii)

    def test_threshold_scales_with_distance_squared(self):
        model = vta.CurrentDistanceModel(k_uA_per_mm2=675.0)
        assert model.threshold_uA(200.0) == pytest.approx(4 * model.threshold_uA(100.0))

    def test_volume_scales_as_current_to_the_three_halves(self):
        model = vta.CurrentDistanceModel(k_uA_per_mm2=675.0)
        assert model.activated_volume_mm3(400.0) / model.activated_volume_mm3(100.0) == (
            pytest.approx(4**1.5)
        )

    def test_below_offset_gives_zero_radius(self):
        model = vta.CurrentDistanceModel(k_uA_per_mm2=675.0, threshold_offset_uA=50.0)
        assert model.activation_radius_um(20.0) == pytest.approx(0.0)

    def test_default_model_is_now_primary_sourced(self):
        """0.3.x used 675 uA/mm^2 from a secondary summary; the primary value is 1292."""
        model = vta.CurrentDistanceModel()
        assert model.verified
        assert model.k_uA_per_mm2 == pytest.approx(vta.STONEY_K_uA_PER_MM2)
        assert "PROVISIONAL" not in model.describe()

    def test_fit_recovers_its_own_parameters(self):
        truth = vta.CurrentDistanceModel(k_uA_per_mm2=500.0, threshold_offset_uA=10.0)
        radii = np.array([100.0, 200.0, 400.0, 800.0])
        fit = vta.fit_current_distance(radii, np.asarray(truth.threshold_uA(radii)))
        assert fit.k_uA_per_mm2 == pytest.approx(500.0)
        assert fit.threshold_offset_uA == pytest.approx(10.0)

    def test_warns_when_activation_is_inside_the_electrode(self):
        result = vta.evaluate(1.0, electrode_radius_um=500.0)
        assert not result.radius_exceeds_electrode
        assert "not meaningful" in result.describe()


class TestIO:
    def test_batch_returns_one_row_per_input(self):
        from neurostim.io import assess_batch

        rows = [
            {
                "shape": "ring",
                "outer_diameter_um": 330,
                "inner_diameter_um": 270,
                "material": "Pt",
                "current_uA": current,
                "pulse_width_us": 200,
                "frequency_hz": 130,
                "train_duration_s": 1,
            }
            for current in (10, 50, 200)
        ]
        frame = assess_batch(rows)
        assert len(frame) == 3
        assert frame["error"].eq("").all()

    def test_batch_records_errors_without_aborting(self):
        from neurostim.io import assess_batch

        rows = [
            {
                "shape": "disc",
                "diameter_um": 200,
                "current_uA": 10,
                "pulse_width_us": 100,
                "frequency_hz": 50,
                "train_duration_s": 1,
            },
            {"shape": "not_a_shape", "current_uA": 10, "pulse_width_us": 100,
             "frequency_hz": 50, "train_duration_s": 1},
        ]
        # G12 (C5.5a, ledger 61/M4): a batch with a failed row now warns.
        with pytest.warns(UserWarning, match="rows failed to build"):
            frame = assess_batch(rows)
        assert len(frame) == 2
        assert frame.loc[1, "status"] == "ERROR"
        assert "Unknown electrode shape" in frame.loc[1, "error"]

    def test_unknown_column_is_rejected(self):
        from neurostim.io import assess_batch

        # G12 (C5.5a, ledger 61/M4): a batch with a failed row now warns.
        with pytest.warns(UserWarning, match="rows failed to build"):
            frame = assess_batch(
                [{"shape": "disc", "diameter_um": 100, "current_uA": 10,
                  "pulse_width_us": 100, "frequency_hz": 50, "train_duration_s": 1,
                  "typo_field": 3}]
            )
        assert frame.loc[0, "status"] == "ERROR"
        assert "unrecognised column" in frame.loc[0, "error"]

    def test_electrode_dict_round_trip(self):
        from neurostim.io import electrode_from_dict, electrode_to_dict

        original = RingElectrode(330.0, 270.0, "Pt")
        assert electrode_from_dict(electrode_to_dict(original)) == original

    def test_json_report_contains_checks_and_disclaimer(self):
        import json

        from neurostim.io import report_to_json

        calc = SafetyCalculator(RingElectrode(330, 270, "Pt"), StimProtocol(80, 200, 130, 1))
        payload = json.loads(report_to_json(calc))
        assert len(payload["checks"]) == 9
        assert "not validated" in payload["disclaimer"].lower()

    def test_current_sweep_shape(self):
        from neurostim.io import current_sweep

        frame = current_sweep(
            DiscElectrode(200.0, "Pt"), StimProtocol(10, 100, 50, 1), [5, 10, 20]
        )
        assert list(frame["current_uA"]) == [5.0, 10.0, 20.0]

    def test_pdf_report_is_written(self, tmp_path):
        from neurostim.io import build_report

        calc = SafetyCalculator(
            RingElectrode(330, 270, "Pt"), StimProtocol(80, 200, 130, 1), compliance_V=10.0
        )
        out = build_report(calc, tmp_path / "report.pdf")
        assert out.exists() and out.stat().st_size > 2000

    def test_fem_round_trip(self, tmp_path):
        from neurostim.io import FEMField, load_field, save_field

        points = np.random.default_rng(0).uniform(-500, 500, size=(50, 3))
        values = np.linalg.norm(points, axis=1) * 1e-4
        original = FEMField(points, values, current_uA=100.0)
        path = save_field(original, tmp_path / "field.npz")
        reloaded = load_field(path, current_uA=100.0)
        assert np.allclose(reloaded.points_um, original.points_um)
        assert np.allclose(reloaded.potential_V, original.potential_V)

    def test_fem_csv_import(self, tmp_path):
        import pandas as pd

        from neurostim.io import load_field

        csv = tmp_path / "field.csv"
        pd.DataFrame(
            {"x": [0, 1, 0, 1, 2], "y": [0, 0, 1, 1, 2], "z": [0, 0, 0, 1, 2],
             "V": [1.0, 0.5, 0.5, 0.3, 0.2]}
        ).to_csv(csv, index=False)
        field = load_field(csv)
        assert field.n_points == 5

    def test_fem_rescaling_is_linear(self):
        from neurostim.io import FEMField

        points = np.random.default_rng(1).uniform(-100, 100, size=(20, 3))
        field = FEMField(points, np.ones(20), current_uA=100.0)
        assert np.allclose(field.scale_to_current(200.0).potential_V, 2.0)

    def test_fem_rescaling_without_recorded_current_raises(self):
        from neurostim.io import FEMField

        points = np.random.default_rng(2).uniform(-100, 100, size=(20, 3))
        with pytest.raises(ValueError, match="no current_uA on record"):
            FEMField(points, np.ones(20)).scale_to_current(200.0)


class TestViz:
    @pytest.fixture
    def calc(self):
        return SafetyCalculator(
            RingElectrode(330, 270, "Pt"), StimProtocol(80, 200, 130, 1), compliance_V=10.0
        )

    def test_shannon_plot_renders(self, calc):
        from neurostim.viz import shannon_safe_operating_area

        ax = shannon_safe_operating_area(calc)
        assert ax.get_xscale() == "log" and ax.get_yscale() == "log"

    def test_summary_figure_has_four_panels(self, calc):
        from neurostim.viz import safety_summary

        fig, _axes = safety_summary(calc)
        assert len(fig.axes) >= 4

    def test_save_publication_writes_all_formats(self, calc, tmp_path):
        from neurostim.viz import safety_summary, save_publication

        fig, _ = safety_summary(calc)
        written = save_publication(fig, tmp_path / "fig", formats=("svg", "pdf"), close=True)
        assert {p.suffix for p in written} == {".svg", ".pdf"}
        assert all(p.exists() and p.stat().st_size > 0 for p in written)

    def test_svg_text_stays_editable(self, calc, tmp_path):
        """svg.fonttype='none' keeps text as text, not paths, for a typesetter."""
        from neurostim.viz import save_publication, shannon_safe_operating_area
        from neurostim.viz.style import subplots

        fig, ax = subplots()
        shannon_safe_operating_area(calc, ax=ax)
        path = save_publication(fig, tmp_path / "fig", formats=("svg",), close=True)[0]
        assert "<text" in path.read_text(encoding="utf-8")

    def test_strength_duration_and_thermal_render(self):
        from neurostim.viz import strength_duration, thermal_profile

        assert len(strength_duration(20.0, 150.0)) == 2
        assert len(thermal_profile(1e-3, 500.0)) == 2

    def test_material_comparison_renders(self, calc):
        from neurostim.viz import material_comparison

        ax = material_comparison(calc.e, calc.p)
        assert ax.get_xscale() == "log"


class TestAnEmptyBatchIsNotACleanBatch:
    """Ledger 51 (io-gui H2) and 61/M4, 61/M14, C5.5a. A header-only CSV returned a 0 x 0
    frame, indistinguishable from a clean one; errored rows were NaN everywhere and
    ``df.limiting_current_uA.min()`` silently reported the one good row as the batch
    minimum; a Latin-1 or empty file raised an error naming a byte offset, not the file."""

    HEADER = "shape,diameter_um,material,current_uA,pulse_width_us,frequency_hz,train_duration_s\n"
    GOOD = "disc,200,Pt,50,200,130,1\n"

    def test_a_header_only_csv_raises_naming_the_file(self, tmp_path):
        from neurostim.io.tabular import read_batch_csv

        path = tmp_path / "spec.csv"
        path.write_text(self.HEADER)
        with pytest.raises(ValueError, match=r"spec\.csv"):
            read_batch_csv(path)

    def test_an_empty_row_list_keeps_the_schema(self):
        from neurostim.io.tabular import assess_batch

        frame = assess_batch([])
        assert len(frame) == 0
        assert {"label", "status", "error", "limiting_current_uA"} <= set(frame.columns)

    def test_an_errored_row_is_none_not_nan_and_the_batch_warns(self, tmp_path):
        from neurostim.io.tabular import BatchRowsFailedWarning, read_batch_csv

        path = tmp_path / "mixed.csv"
        path.write_text(self.HEADER + self.GOOD + "disc,-1,Pt,50,200,130,1\n")
        with pytest.warns(BatchRowsFailedWarning, match="1 of 2 rows"):
            frame = read_batch_csv(path)
        bad = frame[frame.status == "ERROR"].iloc[0]
        good_columns = frame[frame.status != "ERROR"].iloc[0].dropna().index
        result_columns = [c for c in good_columns if c not in ("label", "status", "error")]
        assert result_columns
        assert all(bad[c] is None for c in result_columns), {c: bad[c] for c in result_columns}
        assert frame.attrs["rows_failed"] == [1]

    def test_a_clean_batch_does_not_warn(self, tmp_path):
        import warnings

        from neurostim.io.tabular import read_batch_csv

        path = tmp_path / "clean.csv"
        path.write_text(self.HEADER + self.GOOD)
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            frame = read_batch_csv(path)
        assert frame.attrs["rows_failed"] == []

    @pytest.mark.parametrize(
        "content", [b"", HEADER.rstrip().encode() + b",label\ndisc,200,Pt,50,200,130,1,caf\xe9\n"]
    )
    def test_a_read_error_names_the_file(self, tmp_path, content):
        from neurostim.io.tabular import read_batch_csv

        path = tmp_path / "bad_input.csv"
        path.write_bytes(content)
        with pytest.raises(ValueError, match=r"bad_input\.csv"):
            read_batch_csv(path)
