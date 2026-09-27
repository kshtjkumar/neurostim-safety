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
        thresholds = np.asarray(sd.weiss_threshold_uA(widths, 20.0, 150.0))
        fit = sd.fit_weiss(widths, thresholds)
        assert fit.rheobase_uA == pytest.approx(20.0)
        assert fit.chronaxie_us == pytest.approx(150.0)

    def test_lapicque_fit_recovers_its_own_parameters(self):
        widths = np.array([50.0, 100.0, 200.0, 400.0, 800.0])
        thresholds = np.asarray(sd.lapicque_threshold_uA(widths, 20.0, 200.0))
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


class TestTheBatchColumnsSayWhatTheChecksSay:
    """Ledgers 114, 157, 120 and 126 (CSV part), C5.5b. max_current_cic_uA ignored medium
    (981.7477042468105 against the in-vivo check ceiling for a 500 um Pt disc) and was a
    number beside a Charge injection check NOT_EVALUATED for a monophasic pulse;
    net_dc_current_uA carried a 1.04e-12 residue for a pulse Charge balance calls balanced;
    and the batch could not take a counter electrode."""

    BASE = {"shape": "disc", "diameter_um": 500.0, "material": "Pt", "current_uA": 50,
            "pulse_width_us": 200, "frequency_hz": 130, "train_duration_s": 1}

    @staticmethod
    def _cic_check(assessment):
        return next(c for c in assessment.checks if c.name == "Charge injection limit")

    def test_the_cic_column_honours_the_medium(self):
        e, p = DiscElectrode(500.0, "Pt"), StimProtocol(50, 200, 130, 1)
        in_vivo = SafetyCalculator(e, p, medium="in_vivo")
        ceiling = self._cic_check(in_vivo.assess()).ceiling_uA
        assert ceiling == pytest.approx(107.71174812307864, rel=1e-12)
        assert in_vivo.report()["max_current_cic_uA"] == ceiling
        assert in_vivo.max_current_cic_uA == ceiling
        saline = SafetyCalculator(e, p)
        assert saline.report()["max_current_cic_uA"] == pytest.approx(981.7477042468105, rel=1e-12)
        assert saline.report()["max_current_cic_uA"] == self._cic_check(saline.assess()).ceiling_uA

    def test_a_not_evaluated_check_gives_no_number(self):
        import json

        from neurostim.io.tabular import report_to_json

        mono = SafetyCalculator(
            DiscElectrode(500.0, "Pt"), StimProtocol(50, 200, 130, 1, waveform="monophasic")
        )
        assert self._cic_check(mono.assess()).status.value == "NOT_EVALUATED"
        report = mono.report()
        assert report["max_current_cic_uA"] is None and report["cic_limit_uC_cm2"] is None
        body = json.loads(report_to_json(mono))
        assert "results.max_current_cic_uA" in body["null_reasons"]
        assert "results.cic_limit_uC_cm2" in body["null_reasons"]

    def test_a_balanced_pulse_reports_no_dc(self):
        balanced = StimProtocol(50, 200, 130, 1, charge_recovery_ratio=1 - 5e-13)
        assert balanced.is_charge_balanced and balanced.net_dc_current_uA != 0.0  # premise
        calc = SafetyCalculator(DiscElectrode(500.0, "Pt"), balanced)
        assert calc.report()["net_dc_current_uA"] == 0.0
        partial = StimProtocol(50, 200, 130, 1, charge_recovery_ratio=0.9)
        assert SafetyCalculator(DiscElectrode(500.0, "Pt"), partial).report()[
            "net_dc_current_uA"
        ] == partial.net_dc_current_uA

    def test_the_batch_takes_a_counter_electrode(self):
        from neurostim.io.tabular import assess_batch

        row = {**self.BASE, "counter_shape": "disc", "counter_diameter_um": 2000.0,
               "counter_material": "Pt", "counter_separation_um": 3000.0}
        frame = assess_batch([row])
        assert frame.loc[0, "status"] != "ERROR", frame.loc[0, "error"]
        expected = SafetyCalculator(
            DiscElectrode(500.0, "Pt"), StimProtocol(50, 200, 130, 1),
            counter_electrode=DiscElectrode(2000.0, "Pt"), counter_separation_um=3000.0,
        ).report()
        monopolar = SafetyCalculator(DiscElectrode(500.0, "Pt"), StimProtocol(50, 200, 130, 1)).report()
        assert expected["required_compliance_V"] != monopolar["required_compliance_V"]  # premise
        assert frame.loc[0, "required_compliance_V"] == expected["required_compliance_V"]

    def test_a_counter_without_its_separation_is_a_row_error(self):
        from neurostim.io.tabular import assess_batch

        row = {**self.BASE, "counter_shape": "disc", "counter_diameter_um": 2000.0,
               "counter_material": "Pt"}
        with pytest.warns(UserWarning, match="rows failed to build"):
            frame = assess_batch([row])
        assert frame.loc[0, "status"] == "ERROR"
        assert "counter_separation_um" in frame.loc[0, "error"]


class TestTheJsonIsRfc8259:
    """Ledger 61/M13, pinned at C5.9. json.dumps(default=str) emitted bare NaN; strict JSON
    landed with ledger 143 (allow_nan=False). A NaN forced into the report must raise, never
    reach the output, and ordinary output must parse under a strict parser."""

    @staticmethod
    def _strict_loads(text):
        import json

        def refuse(token):
            raise ValueError(f"non-RFC 8259 constant {token}")

        return json.loads(text, parse_constant=refuse)

    def test_ordinary_output_parses_strictly(self):
        from neurostim.io.tabular import report_to_json

        calc = SafetyCalculator(RingElectrode(330, 270, "Pt"), StimProtocol(80, 200, 130, 1))
        assert self._strict_loads(report_to_json(calc))["results"]

    def test_a_forced_nan_raises_rather_than_emitting(self, monkeypatch):
        from neurostim.io.tabular import report_to_json

        calc = SafetyCalculator(RingElectrode(330, 270, "Pt"), StimProtocol(80, 200, 130, 1))
        real = SafetyCalculator.report
        monkeypatch.setattr(SafetyCalculator, "report", lambda self: {**real(self), "shannon_metric": math.nan})
        with pytest.raises(ValueError, match="JSON compliant"):
            report_to_json(calc)


class TestTheFemImportPathCatchesItsOwnMistakes:
    """Ledgers 61/M5-M9 (io-gui), C5.10. compare_with_point_source evaluated nothing -- a
    potential column off by 1e6 came back as a clean frame with ratio 1e6; _match_column
    took the first alias with no ambiguity check; duplicate positions loaded silently; one
    NaN turned describe() into "nan to nan V"; and save_field/load_field dropped
    current_uA and note."""

    @staticmethod
    def _point_source_field(scale=1.0, current_uA=100.0):
        from neurostim.io.fem import FEMField
        from neurostim.models.field import potential_V

        rng = np.random.default_rng(3)
        direction = rng.normal(size=(60, 3))
        direction /= np.linalg.norm(direction, axis=1, keepdims=True)
        r = np.geomspace(50.0, 5000.0, 60)
        points = direction * r[:, None]
        v = np.asarray(potential_V(current_uA, r, 0.35)) * scale
        return FEMField(points, v, current_uA=current_uA)

    def test_m5_a_million_fold_potential_is_rejected(self):
        from neurostim.io.fem import compare_with_point_source

        good = compare_with_point_source(self._point_source_field(), 100.0)
        assert np.allclose(good["ratio"], 1.0)
        with pytest.raises(ValueError, match="unit"):
            compare_with_point_source(self._point_source_field(scale=1e6), 100.0)
        # The check can be waived when a large far-field deviation is the point.
        waived = compare_with_point_source(
            self._point_source_field(scale=1e6), 100.0, check_scale=False
        )
        assert np.allclose(waived["ratio"], 1e6)

    def test_m6_an_ambiguous_column_raises(self, tmp_path):
        import pandas as pd

        from neurostim.io import load_field

        csv = tmp_path / "both.csv"
        pd.DataFrame(
            {"x": [0, 1e-4, 0, 1e-4, 2e-4], "y": [0, 0, 1e-4, 1e-4, 2e-4],
             "z": [0, 0, 0, 1e-4, 2e-4], "x_um": [0, 100, 0, 100, 200],
             "y_um": [0, 0, 100, 100, 200], "z_um": [0, 0, 0, 100, 200],
             "V": [1.0, 0.5, 0.5, 0.3, 0.2]}
        ).to_csv(csv, index=False)
        with pytest.raises(ValueError, match="ambiguous"):
            load_field(csv)

    def test_m7_duplicate_positions_raise(self):
        from neurostim.io.fem import FEMField

        points = np.random.default_rng(4).uniform(-100, 100, size=(10, 3))
        with pytest.raises(ValueError, match="duplicate"):
            FEMField(np.vstack([points, points]), np.arange(20.0))

    def test_m8_one_nan_does_not_collapse_describe(self):
        from neurostim.io.fem import FEMField

        points = np.random.default_rng(5).uniform(-100, 100, size=(10, 3))
        v = np.linspace(0.1, 1.0, 10)
        v[3] = np.nan
        text = FEMField(points, v).describe()
        assert "nan to nan" not in text
        assert "0.1 to 1 V" in text and "1 non-finite" in text
        points[2, 0] = np.nan
        lo, hi = FEMField(points, np.linspace(0.1, 1.0, 10)).bounds_um
        assert np.all(np.isfinite(lo)) and np.all(np.isfinite(hi))

    def test_m9_current_and_note_round_trip(self, tmp_path):
        from neurostim.io.fem import FEMField, load_field, save_field

        points = np.random.default_rng(6).uniform(-500, 500, size=(20, 3))
        original = FEMField(points, np.ones(20), current_uA=250.0, note="COMSOL run 7")
        path = save_field(original, tmp_path / "field.npz")
        reloaded = load_field(path)
        assert reloaded.current_uA == 250.0 and reloaded.note == "COMSOL run 7"
        assert load_field(path, current_uA=250.0).current_uA == 250.0
        with pytest.raises(ValueError, match="250"):
            load_field(path, current_uA=100.0)
        unrecorded = save_field(FEMField(points, np.ones(20)), tmp_path / "none.npz")
        assert load_field(unrecorded).current_uA is None


class TestTheExampleAndTheFemComparisonAgreeWithThemselves:
    """C5.11c: ledgers 61/M10 and 62/L5."""

    def test_m10_the_narration_agrees_with_the_assessment_above_it(self, tmp_path, capsys):
        """The worked example printed "the tissue-damage criterion is satisfied with 7x
        headroom" eleven lines after "[NOT_EVALUATED] Shannon criterion", and "the interface
        is driven roughly 2.8 V from rest ... which leaves every published water window"
        beside "[PASS] Water window: peak -0.23 V"."""
        import importlib.util
        from pathlib import Path

        spec = importlib.util.spec_from_file_location(
            "worked_example", Path(__file__).resolve().parents[1] / "examples" / "worked_example.py"
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert module.main(tmp_path) == 0
        out = " ".join(capsys.readouterr().out.split())
        assert "[NOT_EVALUATED] Shannon criterion" in out and "[ PASS] Water window" in out
        assert "satisfied with 7x headroom" not in out
        assert "leaves every published water window" not in out
        assert "cannot deliver the charge reversibly" not in out
        assert "The Shannon criterion does not apply at this size" in out
        assert (
            "every material here with a higher limit than Pt (SIROF, PEDOT) is bound at "
            "20.00 uA by Microelectrode charge/phase, as Pt is" in out
        )

    def test_l5_a_comparison_at_another_current_is_refused(self):
        from neurostim.io.fem import FEMField, compare_with_point_source
        from neurostim.models.field import potential_V

        rng = np.random.default_rng(7)
        direction = rng.normal(size=(40, 3))
        direction /= np.linalg.norm(direction, axis=1, keepdims=True)
        r = np.geomspace(50.0, 5000.0, 40)
        field = FEMField(direction * r[:, None], np.asarray(potential_V(100.0, r, 0.35)),
                         current_uA=100.0)
        with pytest.raises(ValueError, match="100"):
            compare_with_point_source(field, 999999.0)
        assert len(compare_with_point_source(field, 100.0)) == 40


class TestTheFemScaleCheckToleratesAGroundedBoundary:
    """Ledger 165 (Phase 5 review P3), C5b.3. The scale check took the median over the
    farther half of the points by count, which a regular grid puts near the outer
    boundary; a correctly scaled solution with a grounded boundary, V = I/(4 pi sigma)
    (1/r - 1/R) on a 41^3 grid, read 0.0931 and raised."""

    @staticmethod
    def _grid(potential, position_scale=1.0):
        from neurostim.io.fem import FEMField

        radius = 20000.0
        axis = np.linspace(-radius, radius, 41)
        x, y, z = np.meshgrid(axis, axis, axis, indexing="ij")
        points = np.column_stack([x.ravel(), y.ravel(), z.ravel()])
        r = np.linalg.norm(points, axis=1)
        keep = (r > 50.0) & (r < radius)
        points, r = points[keep], r[keep]
        k = 100e-6 / (4 * math.pi * 0.35)
        return FEMField(points * position_scale, potential(k, r * 1e-6, radius * 1e-6),
                        current_uA=100.0)

    def test_a_grounded_boundary_passes(self):
        from neurostim.io.fem import compare_with_point_source

        grounded = self._grid(lambda k, r, big: k * (1 / r - 1 / big))
        free = self._grid(lambda k, r, big: k / r)
        assert len(compare_with_point_source(grounded, 100.0, 0.35)) > 0
        assert len(compare_with_point_source(free, 100.0, 0.35)) > 0

    def test_unit_mistakes_still_raise(self):
        from neurostim.io.fem import compare_with_point_source

        with pytest.raises(ValueError, match="unit"):
            compare_with_point_source(self._grid(lambda k, r, big: k / r * 1e3), 100.0, 0.35)
        with pytest.raises(ValueError, match="unit"):
            compare_with_point_source(
                self._grid(lambda k, r, big: k / r, position_scale=1e-3), 100.0, 0.35
            )


class TestFailedRowsPersistInTheCsv:
    """Ledger 167 (Phase 5 review P5), C5b.5. frame.attrs["rows_failed"] does not survive
    write_csv or most pandas operations; the persistent signal is the status and error
    columns, which write_csv must keep, and which it now also counts and warns about."""

    ROWS = [
        {"shape": "disc", "diameter_um": 200.0, "material": "Pt", "current_uA": 50,
         "pulse_width_us": 200, "frequency_hz": 130, "train_duration_s": 1},
        {"shape": "disc", "diameter_um": -1.0, "material": "Pt", "current_uA": 50,
         "pulse_width_us": 200, "frequency_hz": 130, "train_duration_s": 1},
    ]

    def test_status_and_error_survive_the_round_trip(self, tmp_path):
        import pandas as pd

        from neurostim.io.tabular import BatchRowsFailedWarning, assess_batch, write_csv

        with pytest.warns(BatchRowsFailedWarning):
            frame = assess_batch(self.ROWS)
        path = tmp_path / "out.csv"
        with pytest.warns(BatchRowsFailedWarning, match=r"1 of 2 rows.*status"):
            write_csv(frame, path)
        back = pd.read_csv(path)
        assert back.loc[1, "status"] == "ERROR"
        assert "diameter_um" in back.loc[1, "error"]
        assert path.read_text().splitlines()[0].startswith("label,")  # no comment header

    def test_a_clean_frame_writes_silently(self, tmp_path):
        import warnings

        from neurostim.io.tabular import assess_batch, write_csv

        frame = assess_batch(self.ROWS[:1])
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            write_csv(frame, tmp_path / "clean.csv")


class TestAStrengthDurationFitIsPhysicalAndSaysHowSure:
    """Ledgers 33 and 37, C6.1. fit_weiss returned a negative chronaxie (with tau = nan and
    a residual near 1e-22) rather than refusing, and curve_fit's covariance, like the
    Weiss fit's, never reached the caller: at 5 % noise and a true chronaxie of 200 us the
    fitted value scatters with sd 27 us, and nothing said so."""

    def test_t6_a_negative_chronaxie_design_is_refused(self):
        widths = np.array([100.0, 200.0, 400.0])
        # Generated from a known t_c = -60 us, so the rejection is a property of the input.
        thresholds = 20.0 * (1.0 - 60.0 / widths)
        with pytest.raises(ValueError, match=r"fitted chronaxie is non-positive \(-60"):
            sd.fit_weiss(widths, thresholds)
        with pytest.raises(ValueError, match=r"fitted chronaxie is non-positive \(-50"):
            sd.fit_weiss(widths, np.array([10.0, 15.0, 17.5]))

    def test_the_interval_is_calibrated(self):
        """Against a synthetic recovery, not the fit's own formula: 2000 replicates at 5 %
        multiplicative threshold noise, true chronaxie 200 us."""
        rng = np.random.default_rng(37)
        widths = np.array([50.0, 100.0, 200.0, 400.0, 800.0])
        truth = 20.0 * (1.0 + 200.0 / widths)
        covered, estimates = 0, []
        for _ in range(2000):
            fit = sd.fit_weiss(widths, truth * (1.0 + 0.05 * rng.standard_normal(widths.size)))
            assert fit.chronaxie_ci95_us is not None
            low, high = fit.chronaxie_ci95_us
            covered += low <= 200.0 <= high
            estimates.append(fit.chronaxie_us)
        assert 0.92 <= covered / 2000 <= 0.97, covered / 2000
        assert 22.0 < float(np.std(estimates)) < 32.0

    def test_se_reaches_the_caller_and_describe(self):
        widths = np.array([50.0, 100.0, 200.0, 400.0, 800.0])
        thresholds = np.array([82.0, 50.0, 34.0, 26.0, 22.0])
        for fit in (sd.fit_weiss(widths, thresholds), sd.fit_lapicque(widths, thresholds)):
            assert fit.rheobase_se_uA is not None and fit.chronaxie_se_us is not None
            assert fit.rheobase_se_uA > 0 and fit.chronaxie_se_us > 0
            assert fit.chronaxie_ci95_us is not None
            low, high = fit.chronaxie_ci95_us
            assert low < fit.chronaxie_us < high
            assert "95 % CI" in fit.describe()

    def test_two_points_have_no_estimable_uncertainty(self):
        fit = sd.fit_weiss(np.array([100.0, 400.0]), np.array([40.0, 25.0]))
        assert fit.chronaxie_se_us is None and fit.chronaxie_ci95_us is None
        assert "not estimable" in fit.describe()


class TestARankDeficientDesignIsRefused:
    """Ledger 38, C6.2. With every pulse width equal the charge-duration line has no slope
    to fit: fit_weiss([100, 100, 100], [40, 41, 39]) returned rheobase 20 and chronaxie
    100 behind a bare numpy RankWarning."""

    def test_equal_widths_raise(self):
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("error")
            with pytest.raises(ValueError, match="distinct pulse widths"):
                sd.fit_weiss(np.array([100.0, 100.0, 100.0]), np.array([40.0, 41.0, 39.0]))
            with pytest.raises(ValueError, match="distinct pulse widths"):
                sd.fit_lapicque(np.array([100.0, 100.0, 100.0]), np.array([40.0, 41.0, 39.0]))


class TestTheTransientDependsOnlyOnTheTimeAsked:
    """Ledgers 35, 36 and 42, C6.4. The time step was the largest requested time over a
    fixed step count, so an early sample depended on the others requested with it:
    t = 1e-3 s alone read -0.1 % against the analytic solution, and -15.0 % inside
    logspace(-3, 3.5, 60). max_cells clamped the grid silently."""

    def test_one_time_alone_and_among_others_agree(self):
        # G12 (C7.0b, ledger 171): 1 ms at 500 um is tau ~ 6e-4, below the resolved tau,
        # so both calls now warn; the test is about order independence, not accuracy.
        with pytest.warns(thermal.ThermalResolutionWarning):
            alone = thermal.pennes_transient_sphere(1e-3, 500.0, np.array([1e-3]))[0]
        with pytest.warns(thermal.ThermalResolutionWarning):
            among = thermal.pennes_transient_sphere(1e-3, 500.0, np.logspace(-3, 3.5, 60))[0]
        assert abs(among / alone - 1.0) < 0.01, (alone, among)

    def test_the_long_time_limit_is_the_steady_state(self):
        rise = thermal.pennes_transient_sphere(1e-3, 500.0, np.array([1e4]))[0]
        steady = thermal.peak_temperature_rise_K(1e-3, 500.0)
        assert abs(rise / steady - 1.0) < 0.005, (rise, steady)

    def test_a_clamped_grid_warns(self):
        """a = 10 um in perfused brain asks for 79006 cells; max_cells is 20000."""
        with pytest.warns(thermal.ThermalResolutionWarning, match="max_cells"):
            thermal.pennes_transient_sphere(1e-3, 10.0, np.array([1.0]))


class TestTheActivationEstimateCarriesItsSpread:
    """Ledgers 39, 40 and 41, C6.5. evaluate(100).describe() printed a bare "radius 278.2
    um, volume 0.0902 mm^3" though k spans 300-27000 uA/mm^2 across cortical elements,
    854x in volume at 100 uA; sensitivity claimed to cover "every limit" without the
    thermal or VTA inputs; and a negative fitted offset was clamped to 0 silently."""

    def test_39_the_k_range_reaches_the_result_and_describe(self):
        result = vta.evaluate(100.0)
        low, high = result.radius_range_um
        assert low == pytest.approx(60.858061, rel=1e-6) and high == pytest.approx(577.35027, rel=1e-6)
        vlow, vhigh = result.volume_range_mm3
        assert vhigh / vlow == pytest.approx(90.0**1.5, rel=1e-9)
        assert 850 < vhigh / vlow < 860
        text = " ".join(result.describe().split())
        assert "300-27000 uA/mm^2" in text and "60.9-577.4 um" in text and "854x" in text

    def test_40_sensitivity_says_what_it_does_not_cover(self):
        import neurostim.sensitivity as sens

        doc = " ".join(sens.__doc__.split())
        assert "Every limit this package reports" not in doc
        assert "thermal" in doc and "activation" in doc and "not varied here" in doc

    def test_41_a_negative_offset_is_refused_not_clamped(self):
        r = np.array([100.0, 200.0, 300.0, 400.0])
        i = -5.0 + 1292.0 * (r * 1e-3) ** 2  # a true offset below zero
        with pytest.raises(ValueError, match="fit_offset=False"):
            vta.fit_current_distance(r, i)
        fitted = vta.fit_current_distance(r, i, fit_offset=False)
        assert fitted.threshold_offset_uA == 0.0


class TestTheLapicqueIntervalSaysWhereItUnderCovers:
    """Ledger 170 (Phase 6 review R1), C7.0a. The Lapicque CI comes from curve_fit's local
    covariance and under-covers on weakly informative designs (0.82 at 20 % noise with
    widths 50-200 us, 0.85 with 400-3200 us only, 0.90 at 10 %), while the docstring
    quoted Weiss's 94 % for the result generally."""

    def test_the_docstring_scopes_the_figures(self):
        doc = " ".join(f"{sd.StrengthDurationFit.__doc__} {sd.fit_lapicque.__doc__}".split())
        assert "Weiss" in doc and "94 %" in doc
        assert "Lapicque" in doc and "0.82" in doc and "0.85" in doc and "under-cover" in doc

    def test_a_lapicque_fit_says_so_in_describe(self):
        widths = np.array([50.0, 100.0, 200.0, 400.0, 800.0])
        thresholds = np.array([82.0, 50.0, 34.0, 26.0, 22.0])
        assert "under-cover" in sd.fit_lapicque(widths, thresholds).describe()
        assert "under-cover" not in sd.fit_weiss(widths, thresholds).describe()


class TestAnUnresolvedEarlyTimeWarns:
    """Ledger 171 (Phase 6 review R2), C7.0b. Early samples read low, limited by the grid:
    against the analytic unperfused solution, -67 % at tau = alpha t / a^2 = 1e-4 and -20 %
    at 1e-3 with 20 cells per radius; -1.4 % at 1e-2. Non-conservative. The solver now
    warns below the resolved tau and says how to resolve it."""

    @staticmethod
    def _unperfused():
        return thermal.TissueThermalProperties(
            thermal_conductivity_W_per_mK=0.527, perfusion_rate_per_s=0.0,
            verified_fields=(), uncertainty={},
        )

    def _time(self, tau):
        return tau * (500e-6) ** 2 / self._unperfused().thermal_diffusivity_m2_per_s

    def test_below_the_resolved_tau_it_warns(self):
        with pytest.warns(thermal.ThermalResolutionWarning, match="cells_per_radius"):
            thermal.pennes_transient_sphere(1e-3, 500.0, np.array([self._time(1e-3)]), self._unperfused())

    def test_resolved_times_are_silent(self):
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("error")
            thermal.pennes_transient_sphere(1e-3, 500.0, np.array([self._time(0.02)]), self._unperfused())
            thermal.pennes_transient_sphere(
                1e-3, 500.0, np.array([self._time(5e-3)]), self._unperfused(), cells_per_radius=40
            )

    def test_the_resolved_limit_is_accurate(self):
        """At the threshold for 20 cells per radius the error is under 1.5 %."""
        import math

        from scipy.special import erfcx

        tau = thermal.resolved_tau(20)
        t = self._time(tau)
        exact = 1e-3 / (4 * math.pi * 0.527 * 500e-6) * (1 - erfcx(math.sqrt(tau)))
        num = thermal.pennes_transient_sphere(1e-3, 500.0, np.array([t]), self._unperfused())[0]
        assert abs(num / exact - 1) < 0.015


class TestTheCurrentDensityIsTheCurrentOverTheShell:
    """C7.6 (G2, mutant M1). ``current_density_A_per_m2`` was never asserted numerically,
    so its 1/r^2 could become 1/r^3 unnoticed (audit_tests.md §5). The oracle is the shell
    area: 100 uA through a full sphere of radius 1 mm, and through a hemisphere for a
    source in a half-space."""

    def test_full_space(self) -> None:
        expected = 100e-6 / (4.0 * math.pi * 1e-3**2)
        assert field_mod.current_density_A_per_m2(100.0, 1000.0) == pytest.approx(
            expected, rel=1e-12
        )
        assert field_mod.current_density_A_per_m2(100.0, 2000.0) == pytest.approx(
            expected / 4.0, rel=1e-12
        )

    def test_half_space_and_ohms_law(self) -> None:
        from neurostim import DiscElectrode

        disc = DiscElectrode(100.0, "Pt")
        j = field_mod.current_density_A_per_m2(100.0, 1000.0, electrode=disc)
        assert j == pytest.approx(100e-6 / (2.0 * math.pi * 1e-3**2), rel=1e-12)
        e = field_mod.field_V_per_m(100.0, 1000.0, 0.35, electrode=disc)
        assert j == pytest.approx(0.35 * e, rel=1e-12)  # J = sigma E


class TestFieldAndFitBoundaries:
    """C7.6 (G2, generated mutants). Each input guard below had no test on its boundary, so
    ``<=`` could become ``<`` or ``or`` become ``and`` unnoticed. The expected behaviour is
    the guard's own message: the value is refused."""

    @pytest.mark.parametrize("sigma", [0.0, -0.35, math.nan, math.inf])
    def test_the_field_refuses_a_conductivity_that_is_not_finite_and_positive(self, sigma):
        with pytest.raises(ValueError, match="sigma_S_per_m"):
            field_mod.field_V_per_m(100.0, 1000.0, sigma)
        with pytest.raises(ValueError, match="sigma_S_per_m"):
            field_mod.potential_V(100.0, 1000.0, sigma)

    def test_a_zero_dimensional_array_distance_returns_a_float(self):
        assert isinstance(field_mod.field_V_per_m(100.0, np.array(1000.0)), float)
        assert isinstance(field_mod.potential_V(100.0, np.array(1000.0)), float)
        assert isinstance(field_mod.current_density_A_per_m2(100.0, np.array(1000.0)), float)

    def test_a_zero_target_potential_is_refused(self):
        with pytest.raises(ValueError, match="target_V"):
            field_mod.distance_for_potential_um(100.0, 0.0)

    def test_a_zero_minimum_distance_is_refused(self):
        with pytest.raises(ValueError, match="min_distance_um"):
            field_mod.radial_profile(100.0, 0.0, 1000.0)

    def test_a_zero_pulse_width_is_refused(self):
        with pytest.raises(ValueError, match="pulse_width_us"):
            sd.weiss_threshold_uA(0.0, 20.0, 150.0)
        with pytest.raises(ValueError, match="pulse_width_us"):
            sd.weiss_threshold_uA(np.array([100.0, 0.0]), 20.0, 150.0)

    def test_the_weiss_chronaxie_se_is_the_delta_method(self):
        """The oracle is a numerical Jacobian of intercept/slope against numpy's own OLS
        covariance (``np.polyfit(..., cov="unscaled")`` scaled by s^2), not the module's
        closed form."""
        widths = np.array([50.0, 100.0, 200.0, 400.0, 800.0])
        # Noisy on purpose: 82, 50, 34, 26, 22 is an exact Weiss curve (rheobase 18,
        # chronaxie 177.8 us) whose SE is float noise of order 1e-13.
        thresholds = np.array([82.5, 49.0, 34.6, 25.7, 22.3])
        fit = sd.fit_weiss(widths, thresholds)
        assert fit.chronaxie_se_us is not None and fit.chronaxie_se_us > 1.0
        charge = thresholds * widths
        (s, b), unscaled = np.polyfit(widths, charge, 1, cov="unscaled")
        rss = float(np.sum((charge - (s * widths + b)) ** 2))
        cov = unscaled * rss / (widths.size - 2)
        eps = 1e-6
        grad = np.array(
            [
                ((b / (s + eps * s)) - (b / (s - eps * s))) / (2 * eps * s),
                (((b + eps * b) / s) - ((b - eps * b) / s)) / (2 * eps * b),
            ]
        )
        assert fit.chronaxie_se_us == pytest.approx(math.sqrt(grad @ cov @ grad), rel=1e-6)
        assert fit.rss == pytest.approx(rss, rel=1e-12)

    def test_the_lapicque_rss_is_the_sum_of_squared_residuals(self):
        widths = np.array([50.0, 100.0, 200.0, 400.0, 800.0])
        thresholds = np.array([82.0, 50.0, 34.0, 26.0, 22.0])
        fit = sd.fit_lapicque(widths, thresholds)
        model = fit.rheobase_uA / (1.0 - np.exp(-widths / fit.membrane_tau_us))
        assert fit.rss == pytest.approx(float(np.sum((thresholds - model) ** 2)), rel=1e-12)


class TestAnUnidentifiableChronaxieReportsNoUncertainty:
    """Ledger 178 (Phase 7 review S4). With every width far above the chronaxie the
    Lapicque thresholds do not depend on tau, and ``curve_fit`` reported an SE of 0.0 and
    a zero-width CI for exactly that parameter. The review's two designs."""

    def test_constant_thresholds_at_long_widths(self):
        fit = sd.fit_lapicque(np.array([1e5, 2e5, 3e5]), np.array([20.0, 20.0, 20.0]))
        assert fit.chronaxie_se_us is None and fit.chronaxie_ci95_us is None
        assert "not identifiable" in fit.describe()

    def test_long_only_widths_at_five_percent_noise(self):
        widths = np.array([2000.0, 4000.0, 6000.0, 8000.0])
        tau = 200.0 / math.log(2.0)
        rng = np.random.default_rng(1)
        reported = covered = 0
        for _ in range(300):
            noisy = 20.0 / (1.0 - np.exp(-widths / tau)) * (1 + 0.05 * rng.standard_normal(4))
            try:
                fit = sd.fit_lapicque(widths, noisy)
            except (ValueError, RuntimeError):
                continue
            if fit.chronaxie_ci95_us is None:
                assert "not identifiable" in fit.uncertainty_note
                continue
            assert fit.chronaxie_se_us is not None and fit.chronaxie_se_us > 0.0
            reported += 1
            low, high = fit.chronaxie_ci95_us
            covered += low <= 200.0 <= high
        # Measured: 82 intervals reported of 153 accepted fits, 71 cover (0.866). Before,
        # 153 were reported and 71 of them covered (0.46): the rest were zero-width.
        assert reported > 50 and covered / reported > 0.8

    def test_an_informative_design_keeps_its_interval(self):
        widths = np.array([50.0, 100.0, 200.0, 400.0, 800.0])
        fit = sd.fit_lapicque(widths, np.array([82.5, 49.0, 34.6, 25.7, 22.3]))
        assert fit.chronaxie_ci95_us is not None and fit.uncertainty_note == ""
