"""Tests that pin the package to its primary sources.

These are the tests that matter most. Everything else checks that the code does what
the code intends; these check that what the code intends matches what the papers say.
If a value in the materials database drifts from its published source, one of these
fails with the citation in the message.
"""

from __future__ import annotations

import math

import pytest

from neurostim import get_material
from neurostim.geometry import CylindricalBandElectrode, DiscElectrode
from neurostim.models import thermal as thermal_mod
from neurostim.models.thermal import BRAIN
from neurostim.safety import shannon
from neurostim.safety.water_window import DOUBLE_LAYER_CAPACITANCE_uF_cm2, polarisation_V


class TestCogan2008Table2:
    """Cogan (2008) Table 2, 'Charge-injection limits of electrode materials in the CNS'.

    Transcribed row by row. Units in the table are mC/cm^2.
    """

    @pytest.mark.parametrize(
        ("key", "low_mC_cm2", "high_mC_cm2"),
        [
            ("Pt", 0.05, 0.15),
            ("PtIr", 0.05, 0.15),
            # AIROF now carries Beebe & Rose primary values (1.0 CF, 2.1 AF,
            # 3.5 biased) rather than Cogan's rounded 1-5 row.
            ("AIROF", 1.0, 3.5),
            ("SIROF", 1.0, 5.0),
            ("TIROF", 1.0, 1.0),
            ("TiN", 1.0, 1.0),
            # Cogan's Ta2O5 row is "~0.5" with no conditions. The package uses the two
            # microelectrode designs Rose et al. measured *under pulsing* at 0.1 ms:
            # 88-140 uC/cm^2 etched, 150 uC/cm^2 sintered. Their best-reported
            # 260 uC/cm^2 is excluded on purpose -- it equals the DC capacitance times
            # 0.8 V_f, so it is a slow-charge figure, and pore resistance costs a pulsed
            # electrode up to 80 % of that.
            ("Ta2O5", 0.088, 0.15),
            # Cogan's PEDOT row is a single 15 mC/cm^2 value from a meeting abstract,
            # 4-6x above every peer-reviewed measurement. The package uses the
            # peer-reviewed consensus instead: Cui & Zhou 2.3, Luo 2.5, Nyberg 3.6.
            ("PEDOT", 2.3, 3.6),
        ],
    )
    def test_charge_injection_limits(self, key, low_mC_cm2, high_mC_cm2):
        material = get_material(key)
        assert material.cic.units == "mC/cm2"
        assert material.cic.low == pytest.approx(low_mC_cm2)
        assert material.cic.high == pytest.approx(high_mC_cm2)

    def test_cogan_headline_pedot_value_is_rejected_as_unreplicated(self):
        """15 mC/cm^2 is 4-6x above every peer-reviewed PEDOT measurement."""
        pedot = get_material("PEDOT")
        assert pedot.cic.high == pytest.approx(3.6)
        assert "unreplicated" in pedot.note
        assert 15.0 / pedot.cic.high > 4.0

    @pytest.mark.parametrize(
        ("key", "pulse_width_us"),
        [
            ("Pt", 200.0),
            ("PtIr", 200.0),
            ("AIROF", 200.0),
            ("SIROF", 400.0),
            ("TiN", 500.0),
            ("PEDOT", 400.0),
            # Both read from the primary papers rather than from a review summary.
            ("Ta2O5", 100.0),
        ],
    )
    def test_measurement_pulse_widths(self, key, pulse_width_us):
        """Charge-injection limits are pulse-width specific; the value must be recorded."""
        assert get_material(key).cic.pulse_width_us == pytest.approx(pulse_width_us)

    @pytest.mark.parametrize("key", ["TIROF", "SS316LVM"])
    def test_materials_without_a_stated_pulse_width(self, key):
        """TIROF's source is a conference proceedings not held here; do not invent one.

        Ta2O5 and SS316LVM left this list when their primary papers were read. SS316LVM
        is back (G12, C4.6, ledger 73): Riedy & Walter measured neither of its figures,
        and the 100 us was their corrosion test's, not a charge-injection measurement's.
        Closing a gap means moving a key out of it, never inventing a value to fill it.
        """
        assert get_material(key).cic.pulse_width_us is None

    def test_pedot_now_rests_on_peer_reviewed_work(self):
        """0.5.x cited a meeting abstract; Cui & Zhou 2007 replaces it."""
        pedot = get_material("PEDOT")
        assert pedot.cic.peer_reviewed
        assert pedot.cic.reference == "cui_zhou2007"
        assert "NOT PEER REVIEWED" not in pedot.cic.describe()

    @pytest.mark.parametrize(
        "key", ["Pt", "PtIr", "AIROF", "SIROF", "TIROF", "TiN", "Ta2O5", "SS316LVM"]
    )
    def test_every_other_material_is_peer_reviewed(self, key):
        assert get_material(key).cic.peer_reviewed

    @pytest.mark.parametrize(
        ("key", "cathodic_V", "anodic_V"),
        [
            ("Pt", -0.6, 0.8),
            ("PtIr", -0.6, 0.8),
            ("AIROF", -0.6, 0.8),
            ("SIROF", -0.6, 0.8),
            ("TIROF", -0.6, 0.8),
            ("TiN", -0.9, 0.9),
            ("PEDOT", -0.9, 0.6),
        ],
    )
    def test_water_windows(self, key, cathodic_V, anodic_V):
        window = get_material(key).water_window
        assert window is not None
        assert window.cathodic_V == pytest.approx(cathodic_V)
        assert window.anodic_V == pytest.approx(anodic_V)

    def test_tantalum_has_no_published_window(self):
        """Cogan's Ta2O5 row leaves the potential-limits column blank."""
        assert get_material("Ta2O5").water_window is None

    def test_pedot_is_comparable_to_iridium_oxide_not_far_above_it(self):
        """Cui & Zhou describe PEDOT as 'comparable to IrOx'. With the abstract value
        removed it no longer tops the table."""
        pedot = get_material("PEDOT").cic.high
        sirof = get_material("SIROF").cic.high
        assert 0.5 < pedot / sirof < 2.0


class TestMerrill2005:
    """Merrill, Bikson & Jefferys (2005)."""

    def test_shannon_equation_5_1_identity(self):
        """Eq. (5.1): log(Q/A) = k - log(Q), i.e. k = log(Q) + log(Q/A)."""
        for charge_uC, area_cm2 in [(0.016, 2.8e-4), (1.0, 1e-2), (0.5, 6e-3)]:
            k = shannon.shannon_k(charge_uC, area_cm2)
            assert math.log10(charge_uC / area_cm2) == pytest.approx(
                k - math.log10(charge_uC)
            )

    def test_k_band_is_1_5_to_2_0(self):
        """Merrill quote 2.0 > k > 1.5 as the family of lines Shannon drew.

        This is NOT a statement that k = 2.0 is safe -- see TestShannon1992.
        """
        assert shannon.K_BOUNDS == (1.5, 2.0)
        assert shannon.k_is_supported(1.5)
        assert shannon.k_is_supported(2.0)
        assert not shannon.k_is_supported(1.2)
        assert not shannon.k_is_supported(2.5)

    def test_figure_8_lowest_curve_is_available(self):
        """Merrill Fig. 8 draws k = 1.7, 1.85 and 2.0. The lowest is exposed as
        K_MODERATE, but it is not the package default -- Shannon's own 1.5 is."""
        assert shannon.K_MODERATE == 1.7
        assert shannon.K_DEFAULT == shannon.K_SHANNON == 1.5

    def test_footnote_2_double_layer_capacitance(self):
        """'A 1 V excursion across 20 uF/cm^2 yields 20 uC/cm^2 stored charge'."""
        assert DOUBLE_LAYER_CAPACITANCE_uF_cm2 == pytest.approx(20.0)
        assert polarisation_V(20.0, 20.0) == pytest.approx(1.0)

    def test_rose_robblee_platinum_range_is_the_source_of_cogan_pt_row(self):
        """50-150 uC/cm^2 geometric at 200 us, matching Cogan's 0.05-0.15 mC/cm^2."""
        pt = get_material("Pt")
        assert pt.cic.pulse_width_us == pytest.approx(200.0)
        assert pt.cic.area_basis == "geometric"
        assert pt.cic_uC_cm2("conservative") == pytest.approx(50.0)
        assert pt.cic_uC_cm2("optimistic") == pytest.approx(150.0)


class TestStainlessSteel:
    """Riedy & Walter (1996), corroborated by Merrill (2005) Table 2."""

    def test_316lvm_limits(self):
        """40 uC/cm^2 reported safe; 20 uC/cm^2 available non-faradaically."""
        ss = get_material("SS316LVM")
        assert ss.cic_uC_cm2("conservative") == pytest.approx(20.0)
        assert ss.cic_uC_cm2("optimistic") == pytest.approx(40.0)

    def test_legacy_ss_alias_resolves(self):
        """The 0.1.0 prototype's 'SS' must still resolve, to 316LVM."""
        assert get_material("SS").key == "SS316LVM"

    def test_polarisation_limit_is_not_labelled_a_water_window(self):
        """1.2 V is a reversible-injection limit, not a potential window vs a reference.

        It is stored in a WaterWindow so the polarisation check can run, which makes
        the ``scale`` field load-bearing: rendering it as "vs Ag|AgCl" would misstate
        what Riedy & Walter measured.
        """
        window = get_material("SS316LVM").water_window
        assert window is not None
        assert window.cathodic_V == pytest.approx(-1.2)
        assert window.anodic_V == pytest.approx(1.2)
        assert "Ag|AgCl" not in window.describe()
        assert "polarisation from rest" in window.describe()

    def test_nonfaradaic_limit_is_consistent_with_double_layer_capacitance(self):
        """20 uC/cm^2 over 1.2 V should land near the 20 uF/cm^2 double-layer value.

        Riedy & Walter say 20 uC/cm^2 is what is "available for nonfaradic charge
        transfer and double layer charge injection". If that is true, the implied
        capacitance must be a double-layer capacitance -- an independent check that
        the two constants were read correctly.
        """
        from neurostim.safety.water_window import DOUBLE_LAYER_CAPACITANCE_uF_cm2

        implied = 20.0 / 1.2
        assert implied == pytest.approx(DOUBLE_LAYER_CAPACITANCE_uF_cm2, rel=0.2)


class TestNewman1966:
    """Disc access resistance R = 1/(4 * kappa * a)."""

    @pytest.mark.parametrize("diameter_um", [50.0, 200.0, 1000.0])
    @pytest.mark.parametrize("sigma", [0.2, 0.35, 1.0])
    def test_disc_access_resistance(self, diameter_um, sigma):
        disc = DiscElectrode(diameter_um)
        expected = 1.0 / (4.0 * sigma * (diameter_um / 2.0) * 1e-6)
        assert disc.access_resistance_ohm(sigma) == pytest.approx(expected)
        assert disc.access_resistance_is_exact


class TestCogan2008Table1:
    """Clinical DBS electrodes 'have large areas (0.06 cm2)' -- Table 1 footnote b."""

    def test_dbs_contact_area(self):
        """A 1.27 mm x 1.5 mm band contact gives 0.0599 cm^2."""
        contact = CylindricalBandElectrode(1270.0, 1500.0, "PtIr")
        assert contact.area_cm2 == pytest.approx(0.06, abs=0.001)


class TestElwassif2006:
    """Tissue property values quoted from the DBS bioheat model."""

    def test_elwassif_thermal_conductivity_preset(self):
        from neurostim.models.thermal import ELWASSIF_BRAIN

        assert ELWASSIF_BRAIN.thermal_conductivity_W_per_mK == pytest.approx(0.527)

    def test_conductivity_default_matches_paper(self):
        from neurostim.models.field import BRAIN_CONDUCTIVITY_S_PER_M

        assert pytest.approx(0.35) == BRAIN_CONDUCTIVITY_S_PER_M


class TestITISDatabase:
    """IT'IS Database v4.2, materialparameterdatabasecurrent20250821.xls."""

    @pytest.mark.parametrize(
        ("field_name", "expected"),
        [
            ("thermal_conductivity_W_per_mK", 0.547),
            ("density_kg_per_m3", 1044.5),
            ("specific_heat_J_per_kgK", 3695.8),
            ("blood_density_kg_per_m3", 1049.75),
            ("blood_specific_heat_J_per_kgK", 3617.0),
        ],
    )
    def test_grey_matter_values(self, field_name, expected):
        from neurostim.models.thermal import GREY_MATTER

        assert getattr(GREY_MATTER, field_name) == pytest.approx(expected)

    def test_perfusion_unit_conversion(self):
        """763.667 ml/min/kg at 1044.5 kg/m^3 is 0.013294 1/s."""
        from neurostim.models.thermal import perfusion_per_s

        assert perfusion_per_s(763.667, 1044.5) == pytest.approx(0.013294, rel=1e-4)

    def test_perfusion_conversion_is_density_scaled(self):
        """The tissue density factor is what makes this a volumetric rate."""
        from neurostim.models.thermal import perfusion_per_s

        assert perfusion_per_s(600.0, 2000.0) == pytest.approx(
            2 * perfusion_per_s(600.0, 1000.0)
        )

    def test_white_matter_is_less_perfused_than_grey(self):
        """IT'IS gives 212 vs 764 ml/min/kg, so white matter has a longer thermal reach."""
        from neurostim.models.thermal import GREY_MATTER, WHITE_MATTER

        assert WHITE_MATTER.perfusion_rate_per_s < GREY_MATTER.perfusion_rate_per_s
        assert (
            WHITE_MATTER.thermal_penetration_depth_m
            > GREY_MATTER.thermal_penetration_depth_m
        )

    def test_all_defaults_are_now_sourced(self):
        """The thermal block used to be mostly unsourced textbook values."""
        assert BRAIN.fully_verified
        assert BRAIN.source == "itis2025"
        assert "PROVISIONAL" not in BRAIN.describe()

    def test_uncertainty_is_recorded(self):
        """Every default carries a standard deviation and sample size."""
        for name in (
            "thermal_conductivity_W_per_mK",
            "density_kg_per_m3",
            "specific_heat_J_per_kgK",
            "perfusion_rate_per_s",
        ):
            sd, n = BRAIN.uncertainty[name]
            assert sd > 0 and n >= 1

    def test_conductivity_constants(self):
        from neurostim.models import field as f

        assert pytest.approx(0.419) == f.GREY_MATTER_CONDUCTIVITY_S_PER_M
        assert pytest.approx(0.348) == f.WHITE_MATTER_CONDUCTIVITY_S_PER_M
        assert pytest.approx(0.662) == f.BLOOD_CONDUCTIVITY_S_PER_M


class TestProvenanceIsAlwaysPresent:
    """Every material constant must resolve to a real bibliography entry."""

    def test_every_material_cites_a_known_reference(self):
        from neurostim import list_materials
        from neurostim.references import cite

        for material in list_materials():
            assert cite(material.cic.reference) is not None
            if material.water_window is not None:
                assert cite(material.water_window.reference) is not None

    def test_every_material_describes_its_conditions(self):
        from neurostim import list_materials

        for material in list_materials():
            text = material.cic.describe()
            assert material.cic.reference in text
            assert material.cic.units in text

    def test_unknown_reference_key_raises(self):
        from neurostim.references import cite

        with pytest.raises(KeyError, match="Unknown reference key"):
            cite("not_a_real_paper_2099")

    def test_user_measurement_is_never_attributed_to_a_paper(self):
        """A locally measured limit must not display the material's original citation."""
        from neurostim import with_measured_cic

        pt = get_material("Pt")
        assert pt.cic.reference == "rose_robblee1990"

        measured = with_measured_cic(pt, 62.0, pulse_width_us=200, note="my batch")
        assert measured.cic.reference == "user_measurement"
        assert not measured.cic.verified

        text = measured.cic.describe()
        assert "rose_robblee1990" not in text
        assert "not published literature" in text
        assert "my batch" in text
        assert "PROVISIONAL" in text

    def test_user_measurement_rejects_non_positive_values(self):
        from neurostim import with_measured_cic

        with pytest.raises(ValueError, match="must be finite and > 0"):
            with_measured_cic(get_material("Pt"), 0.0)


class TestShannon1992Primary:
    """Read from the primary text, not from Merrill's restatement of it."""

    def test_shannon_recommends_1_5(self):
        """'k = 1.5 is a conservative limit and has been used in all calculations.'"""
        assert shannon.K_SHANNON == 1.5
        assert shannon.K_DEFAULT == 1.5

    def test_k_2_is_labelled_as_damage_not_as_a_limit(self):
        """'When k = 2, the straight line falls in an area where damage was observed.'"""
        assert shannon.K_DAMAGE_OBSERVED == 2.0
        warning = shannon.k_warning(2.0)
        assert "damage was observed" in warning
        assert "not a safety limit" in warning

    def test_k_above_shannons_value_warns_with_the_charge_factor(self):
        """Permitted charge scales as 10^(k/2), so 1.7 allows 1.26x of 1.5."""
        warning = shannon.k_warning(1.7)
        assert "1.26x" in warning

    def test_shannons_own_value_produces_no_warning(self):
        assert shannon.k_warning(1.5) == ""
        assert shannon.k_is_conservative(1.5)
        assert not shannon.k_is_conservative(1.7)

    def test_fit_conditions_are_recorded(self):
        """400 us/phase, 50 Hz, 7 h, cat parietal cortex."""
        assert shannon.FIT_PULSE_WIDTH_US == 400.0
        assert shannon.FIT_FREQUENCY_HZ == 50.0
        assert shannon.FIT_DURATION_H == 7.0
        assert "cat" in shannon.FIT_PREPARATION

    def test_conditions_warning_fires_away_from_the_fit(self):
        """Shannon: extrapolation to other rates or pulse widths is not established."""
        assert shannon.conditions_warning(400.0, 50.0) == ""
        assert "130 Hz" in shannon.conditions_warning(400.0, 130.0)
        assert "60 us" in shannon.conditions_warning(60.0, 50.0)


class TestMcCreery1990Dataset:
    """Table I, transcribed from the primary paper."""

    def test_dataset_size(self):
        from neurostim.data import mccreery1990 as m

        assert len(m.TABLE_I) == 12
        assert m.CONTROL_SITES == 23
        assert m.TOTAL_SITES_EXAMINED == 64

    def test_conditions_match_shannons_stated_fit_conditions(self):
        from neurostim.data import mccreery1990 as m

        assert m.PULSE_WIDTH_US == shannon.FIT_PULSE_WIDTH_US
        assert m.FREQUENCY_HZ == shannon.FIT_FREQUENCY_HZ
        assert m.DURATION_H == shannon.FIT_DURATION_H

    def test_microelectrodes_at_extreme_density_showed_no_damage(self):
        """800 and 1600 uC/cm^2 with no damage; this is the synergy argument."""
        from neurostim.data import mccreery1990 as m

        extreme = [p for p in m.TABLE_I if p.charge_density_uC_cm2 >= 800]
        assert len(extreme) == 2
        assert all(p.outcome == "none" for p in extreme)

    def test_lowest_damaging_charge_density(self):
        """No damage below 12 uC/cm^2 anywhere in the study."""
        from neurostim.data import mccreery1990 as m

        harmful = [p for p in m.TABLE_I if p.outcome in ("damage", "partial")]
        assert min(p.charge_density_uC_cm2 for p in harmful) == pytest.approx(12.0)

    def test_area_charge_density_and_charge_are_self_consistent(self):
        """Q/A must equal the tabulated charge density for every row."""
        from neurostim.data import mccreery1990 as m

        for p in m.TABLE_I:
            assert p.charge_per_phase_uC / p.area_cm2 == pytest.approx(
                p.charge_density_uC_cm2, rel=0.05
            )

    def test_data_pin_the_boundary_near_k_1_7(self):
        """The highest safe surface point sits at k = 1.699, so Shannon's recommended 1.5
        is deliberately below the observed boundary.

        G12 (C4.9a, ledger 78 S-14): the band's upper end is now the lowest all-damage
        point, 2.107, not a partial point at 1.699; the lower end is unchanged.
        """
        from neurostim.data import mccreery1990 as m

        safe, hurt = m.separating_k_range()
        assert safe == pytest.approx(1.699, abs=0.01)
        assert hurt == pytest.approx(2.107, abs=0.01)
        assert safe > shannon.K_SHANNON

    def test_local_charge_density_falls_with_depth(self):
        """McCreery eq. (1): QD_x = QD_s (1 - x/sqrt(R^2 + x^2))."""
        from neurostim.data import mccreery1990 as m

        assert m.local_charge_density_uC_cm2(800.0, 0.0, 45.0) == pytest.approx(800.0)
        assert m.local_charge_density_uC_cm2(800.0, 60.0, 45.0) == pytest.approx(160.0)
        deeper = m.local_charge_density_uC_cm2(800.0, 200.0, 45.0)
        assert deeper < m.local_charge_density_uC_cm2(800.0, 60.0, 45.0)

    def test_local_charge_density_validates_inputs(self):
        from neurostim.data import mccreery1990 as m

        with pytest.raises(ValueError, match="electrode_radius_um"):
            m.local_charge_density_uC_cm2(800.0, 10.0, 0.0)
        with pytest.raises(ValueError, match="distance_um"):
            m.local_charge_density_uC_cm2(800.0, -1.0, 45.0)


class TestElwassif2006Validation:
    """Table I of the FEM paper, used to check this package's analytic scalings."""

    @staticmethod
    def _contact_radius_m() -> float:
        import math

        from neurostim.data import elwassif2006 as e

        area = (
            math.pi
            * e.LEAD_3389_CONTACT_DIAMETER_UM
            * 1e-6
            * e.LEAD_3389_CONTACT_HEIGHT_UM
            * 1e-6
        )
        return math.sqrt(area / math.pi)

    def test_table_has_twelve_rows(self):
        from neurostim.data import elwassif2006 as e

        assert len(e.TABLE_I) == 12

    def test_peak_rise_matches_the_abstract(self):
        from neurostim.data import elwassif2006 as e

        assert max(p.rise_K_3389 for p in e.TABLE_I) == pytest.approx(e.PEAK_RISE_K)

    def test_rise_is_linear_in_electrical_conductivity(self):
        """A voltage-driven source dissipates P proportional to sigma, so dT is too."""
        from neurostim.data import elwassif2006 as e

        ratios = [p.rise_K_3389 / p.sigma_S_per_m for p in e.conductivity_block()]
        assert max(ratios) / min(ratios) < 1.02  # 0.7 % spread in the source data

    def test_rise_is_inverse_in_thermal_conductivity(self):
        """dT = P / (4 pi kappa a), so dT * kappa is constant."""
        from neurostim.data import elwassif2006 as e

        products = [
            p.rise_K_3389 * p.thermal_conductivity_W_per_mK
            for p in e.thermal_conductivity_block()
        ]
        assert max(products) / min(products) < 1.02

    def test_perfusion_attenuation_matches_the_analytic_form(self):
        """Analytic 1/(1 + a/L) reproduces their FEM perfusion sweep within 10 %."""
        from neurostim.data import elwassif2006 as e

        a = self._contact_radius_m()
        block = e.perfusion_block()
        unperfused = block[0]
        assert unperfused.perfusion_per_s == 0.0

        for point in block[1:]:
            tissue = thermal_mod.TissueThermalProperties(
                thermal_conductivity_W_per_mK=point.thermal_conductivity_W_per_mK,
                perfusion_rate_per_s=point.perfusion_per_s,
                blood_density_kg_per_m3=e.BLOOD_DENSITY_KG_PER_M3,
                blood_specific_heat_J_per_kgK=e.BLOOD_SPECIFIC_HEAT_J_PER_KGK,
                verified_fields=(),
                uncertainty={},
            )
            predicted = 1.0 / (1.0 + a / tissue.thermal_penetration_depth_m)
            reported = point.rise_K_3389 / unperfused.rise_K_3389
            assert predicted == pytest.approx(reported, rel=0.10)

    def test_implied_power_is_a_sensible_bipolar_impedance(self):
        """0.82 K needs about 7.5 mW, i.e. roughly 325 ohm at their 1.56 V RMS."""
        from neurostim.data import elwassif2006 as e

        power = e.implied_power_W()
        assert power == pytest.approx(7.5e-3, rel=0.05)
        assert 200.0 < e.V_RMS**2 / power < 500.0

    def test_the_apparent_gap_is_a_protocol_difference_not_a_physics_one(self):
        """Their mW-scale continuous bipolar drive vs a uW-scale duty-cycled pulse train.

        Matching the power reproduces their temperature rise; matching the amplitude
        does not, because the two protocols differ in power by about a hundredfold.
        """
        from neurostim import CylindricalBandElectrode, StimProtocol
        from neurostim.data import elwassif2006 as e

        contact = CylindricalBandElectrode(
            e.LEAD_3389_CONTACT_DIAMETER_UM, e.LEAD_3389_CONTACT_HEIGHT_UM, "PtIr"
        )
        unperfused = thermal_mod.TissueThermalProperties(
            thermal_conductivity_W_per_mK=0.527,
            perfusion_rate_per_s=0.0,
            verified_fields=(),
            uncertainty={},
        )

        # Feed the analytic model their power and it lands on their number.
        at_their_power = thermal_mod.peak_temperature_rise_K(
            e.implied_power_W(), contact.equivalent_radius_um, unperfused
        )
        assert at_their_power == pytest.approx(e.PEAK_RISE_K, rel=0.02)

        # A duty-cycled current-controlled protocol is two orders of magnitude cooler.
        pulsed = StimProtocol(3000, 60, 130, 1)
        pulsed_power = thermal_mod.ohmic_power_W(
            pulsed.rms_current_uA, contact.access_resistance_ohm(0.35)
        )
        assert pulsed_power < e.implied_power_W() / 50

    def test_voltage_driven_power_helper(self):
        from neurostim.data import elwassif2006 as e

        assert thermal_mod.voltage_driven_power_W(e.V_RMS, 325.0) == pytest.approx(
            e.V_RMS**2 / 325.0
        )
        with pytest.raises(ValueError, match="resistance_ohm"):
            thermal_mod.voltage_driven_power_W(1.56, 0.0)

    def test_their_stated_tissue_values_are_recorded(self):
        from neurostim.data import elwassif2006 as e

        assert e.TISSUE_DENSITY_KG_PER_M3 == 1040.0
        assert e.TISSUE_SPECIFIC_HEAT_J_PER_KGK == 3650.0
        assert e.BLOOD_DENSITY_KG_PER_M3 == 1057.0
        assert e.BLOOD_SPECIFIC_HEAT_J_PER_KGK == 3600.0
        assert e.METABOLIC_HEAT_ASSUMED_ZERO


class TestRoseRobblee1990Primary:
    """Read from the primary text rather than through Cogan's restatement."""

    def test_it_is_paper_viii(self):
        """The title page reads 'Electrical Stimulation with Pt Electrodes. VIII.'"""
        from neurostim.references import cite

        assert "VIII" in cite("rose_robblee1990").title

    def test_charge_injection_range(self):
        """AF 50-100, CF 100-150 uC/cm^2 geometric, at 0.2 ms and 50 pps."""
        pt = get_material("Pt")
        assert pt.cic_uC_cm2("conservative") == pytest.approx(50.0)
        assert pt.cic_uC_cm2("optimistic") == pytest.approx(150.0)
        assert pt.cic.pulse_width_us == pytest.approx(200.0)
        assert pt.cic.area_basis == "geometric"

    def test_electrolyte_ph_is_7_3_not_7_0(self):
        assert "7.3" in get_material("Pt").cic.medium

    def test_reference_electrode_discrepancy_is_recorded(self):
        """Their limits are vs SCE; Cogan restates them vs Ag|AgCl."""
        note = get_material("Pt").cic.note
        assert "SCE" in note
        assert "Ag|AgCl" in note

    def test_pulse_width_and_bias_dependence_are_recorded(self):
        """1 ms raises the limit to 250; a +0.9 V bias raises it to 600 uC/cm^2."""
        note = get_material("Pt").cic.note
        assert "250" in note
        assert "600" in note

    @pytest.mark.parametrize("key", ["Pt", "PtIr"])
    def test_dissolution_threshold_is_below_the_injection_limit(self, key):
        """'Pt dissolution occurs even at charge densities of 20-50 uC/cm^2 geom.'"""
        material = get_material(key)
        assert material.chronic_threshold is not None
        assert material.chronic_threshold.low_uC_cm2 == pytest.approx(20.0)
        assert material.chronic_threshold.high_uC_cm2 == pytest.approx(50.0)
        assert material.chronic_threshold.low_uC_cm2 < material.cic_uC_cm2("conservative")

    def test_chronic_check_fires_inside_the_injection_limit(self):
        """A protocol can pass the CIC check and still be eroding the electrode."""
        from neurostim import DiscElectrode, SafetyCalculator, StimProtocol
        from neurostim.safety.assessment import Status

        # 22 uC/cm^2: comfortably under the 50 uC/cm^2 CIC (2.3x margin, so it
        # reports PASS rather than a thin-margin CAUTION), but inside the 20-50
        # dissolution band.
        area = DiscElectrode(1000.0, "Pt").area_cm2
        current = 22.0 * area / 200e-6
        calc = SafetyCalculator(
            DiscElectrode(1000.0, "Pt"), StimProtocol(current, 200, 50, 1)
        )
        checks = {c.name: c for c in calc.assess().checks}
        assert checks["Charge injection limit"].status is Status.PASS
        assert checks["Chronic degradation"].status is Status.CAUTION


class TestCogan2016:
    """The FDA-co-authored re-evaluation of stimulation damage thresholds."""

    def test_microelectrode_threshold_is_charge_per_phase(self):
        from neurostim.data import cogan2016 as c

        assert pytest.approx(4.0) == c.MICROELECTRODE_DAMAGE_THRESHOLD_NC_PER_PHASE

    def test_macro_micro_boundary(self):
        from neurostim.data import cogan2016 as c

        assert c.MACRO_MICRO_BOUNDARY_AREA_CM2 == (3e-4, 7e-4)
        assert c.is_microelectrode(1e-5)
        assert not c.is_microelectrode(0.06)
        assert c.in_regime_transition(5e-4)

    def test_dbs_approved_limit_and_actual_clinical_use(self):
        """The 30 uC/cm^2 approval limit is ~4x what DBS actually uses clinically."""
        from neurostim.data import cogan2016 as c

        assert c.DBS_APPROVED_CHARGE_DENSITY_UC_CM2 == 30.0
        assert c.DBS_TYPICAL_CLINICAL_CHARGE_DENSITY_UC_CM2 == 8.0

    def test_in_vivo_derating_is_recorded_for_the_main_materials(self):
        """Saline CIC overstates in vivo capacity by up to 10x for Pt and AIROF."""
        from neurostim.data import cogan2016 as c

        assert c.derating_for("Pt").worst == pytest.approx(8.7)  # G12, C4.5: Leung's matched
        assert c.derating_for("AIROF").worst == pytest.approx(10.0)
        assert c.derating_for("SIROF").worst == pytest.approx(4.0)
        assert c.derating_for("TiN") is None

    def test_porous_platinum_derates_worst(self):
        from neurostim.data import cogan2016 as c

        assert c.POROUS_PLATINUM_DERATING.worst == pytest.approx(8.0)

    def test_their_k_1_25_worked_example_reproduces(self):
        """60 uC/cm^2 on 0.005 cm^2 gives k = 1.255, matching their stated 'k ~ 1.25'.

        This is the check that confirms their k formula is the standard one, which in
        turn is why their separate '1.4' for the 12 uC/cm^2 point looks like a slip.
        """
        charge_uC = 60.0 * 0.005
        assert shannon.shannon_k(charge_uC, 0.005) == pytest.approx(1.25, abs=0.01)

    def test_the_mccreery_point_they_call_k_1_4_is_actually_1_86(self):
        """Documented discrepancy; the tabulated values give 1.86, not 1.4."""
        assert shannon.shannon_k(6.0, 0.5) == pytest.approx(1.857, abs=0.01)


class TestStoneyTehovnikCurrentDistance:
    """Current-distance constant, read from Tehovnik et al. (2006) figure 1A."""

    def test_pyramidal_tract_mean(self):
        from neurostim.models import vta

        assert vta.STONEY_K_uA_PER_MM2 == pytest.approx(1292.0)
        assert vta.STONEY_K_SE_RANGE_uA_PER_MM2 == (1037.0, 1547.0)

    def test_element_span_is_ninetyfold(self):
        """300 uA/mm^2 (large myelinated) to 27000 (small unmyelinated)."""
        from neurostim.models import vta

        low, high = vta.K_RANGE_BY_ELEMENT_uA_PER_MM2
        assert (low, high) == (300.0, 27000.0)
        assert high / low == pytest.approx(90.0)

    def test_mt_behavioural_estimate_reproduces(self):
        """K = 20 uA / (0.1 mm)^2 = 2000 uA/mm^2."""
        from neurostim.models import vta

        assert pytest.approx(vta.MT_BEHAVIOURAL_K_uA_PER_MM2) == 20.0 / (0.1**2)

    def test_radius_formula_matches_the_review(self):
        """Tehovnik state the spread as (I/K)^(1/2); 1292 uA at K=1292 gives 1 mm."""
        from neurostim.models import vta

        model = vta.CurrentDistanceModel()
        assert model.activation_radius_um(1292.0) == pytest.approx(1000.0)
        assert model.threshold_uA(1000.0) == pytest.approx(1292.0)

    def test_old_default_was_non_conservative(self):
        """675 uA/mm^2 overestimated activation radius by about 1.4x."""
        from neurostim.models import vta

        old = vta.CurrentDistanceModel(k_uA_per_mm2=675.0).activation_radius_um(80.0)
        new = vta.CurrentDistanceModel().activation_radius_um(80.0)
        assert old / new == pytest.approx((1292.0 / 675.0) ** 0.5, rel=1e-6)

    def test_axons_have_shorter_chronaxies_than_cell_bodies(self):
        """Which is why short pulses recruit fibres of passage, not somata."""
        from neurostim.models import vta

        assert vta.AXON_CHRONAXIE_RANGE_MS[0] < vta.CELL_BODY_CHRONAXIE_RANGE_MS[0]


class TestISO14708_3:
    """The regulatory heat criterion, clause 17.1 and Table 101."""

    def test_surface_limit_and_implied_rise(self):
        from neurostim.data import iso14708_3 as iso

        assert iso.MAX_OUTER_SURFACE_C == 39.0
        assert pytest.approx(2.0) == iso.MAX_RISE_K

    def test_table_101_thresholds(self):
        from neurostim.data import iso14708_3 as iso

        assert iso.threshold_for("brain") == 2.0
        assert iso.threshold_for("muscle") == 40.0
        assert iso.threshold_for("peripheral nerve") == 40.0
        assert iso.threshold_for("skin") == 21.0
        assert iso.threshold_for("bone") == 16.0

    def test_brain_is_the_most_restrictive_tissue(self):
        from neurostim.data import iso14708_3 as iso

        assert iso.threshold_for("brain") == min(iso.CEM43_THRESHOLDS.values())

    def test_cem43_quadruples_per_degree_below_43(self):
        """R = 0.25 below 43 C, so each degree costs a factor of four in time."""
        from neurostim.data import iso14708_3 as iso

        assert iso.allowed_minutes(40.0) / iso.allowed_minutes(41.0) == pytest.approx(4.0)

    def test_below_39_c_the_formula_does_not_apply(self):
        from neurostim.data import iso14708_3 as iso

        assert math.isinf(iso.allowed_minutes(38.9))
        assert iso.cem43_steady(38.0, 10_000.0) == 0.0

    def test_brain_at_43_c_reaches_threshold_in_two_minutes(self):
        from neurostim.data import iso14708_3 as iso

        assert iso.allowed_minutes(43.0, "brain") == pytest.approx(2.0)

    def test_unknown_tissue_raises(self):
        from neurostim.data import iso14708_3 as iso

        with pytest.raises(KeyError, match="No CEM43 threshold"):
            iso.threshold_for("liver")

    def test_thermal_default_limit_now_comes_from_the_standard(self):
        from neurostim.data import iso14708_3 as iso

        result = thermal_mod.evaluate(100.0, 1000.0, 500.0)
        assert result.limit_K == pytest.approx(iso.MAX_RISE_K)
        assert result.satisfies_iso_surface_limit


class TestBeebeRose1988Primary:
    """Activated iridium oxide, read from the primary abstract and methods."""

    def test_cathodic_and_biased_limits(self):
        """1.0 mC/cm^2 cathodic-first; 3.5 mC/cm^2 biased to +0.8 V vs SCE."""
        airof = get_material("AIROF")
        assert airof.cic.low == pytest.approx(1.0)
        assert airof.cic.high == pytest.approx(3.5)

    def test_conditions(self):
        airof = get_material("AIROF")
        assert airof.cic.pulse_width_us == pytest.approx(200.0)
        assert "7.3" in airof.cic.medium
        assert "bicarbonate" in airof.cic.medium
        assert airof.cic.area_basis == "geometric"

    def test_measured_on_a_microelectrode_sized_area(self):
        """3.7-4.5e-4 cm^2, right at the macro/micro boundary."""
        from neurostim.data import cogan2016

        airof = get_material("AIROF")
        assert airof.cic.measured_area_cm2 == pytest.approx(4.1e-4, rel=0.1)
        assert cogan2016.in_regime_transition(airof.cic.measured_area_cm2)

    def test_reference_electrode_caveat_is_recorded_on_the_window(self):
        """Both primary sources used SCE; Cogan restates the window vs Ag|AgCl."""
        note = get_material("AIROF").water_window.note
        assert "SCE" in note
        assert "45 mV" in note


class TestKuncelGrill2004:
    """The DBS parameter review, read from the primary text."""

    def test_thirty_uC_cm2_is_described_as_liberal_not_conservative(self):
        from neurostim.references import cite

        note = cite("kuncel_grill2004_full").note
        assert "liberal" in note

    def test_fraction_of_contact_above_average_current_density(self):
        from neurostim.data import current_distribution as cd

        assert pytest.approx(0.256) == cd.DBS_FRACTION_ABOVE_AVERAGE
        assert pytest.approx(0.0993) == cd.DBS_AVERAGE_CURRENT_DENSITY_A_PER_CM2

    def test_averaging_caveat_applies_unless_recessed(self):
        from neurostim.data import current_distribution as cd

        assert cd.averaged_density_understates_local_peak(recessed=False)
        assert not cd.averaged_density_understates_local_peak(recessed=True)

    def test_caveat_is_surfaced_in_the_charge_check(self):
        from neurostim import DiscElectrode, SafetyCalculator, StimProtocol

        calc = SafetyCalculator(DiscElectrode(500.0, "Pt"), StimProtocol(10, 200, 50, 1))
        detail = next(
            c for c in calc.assess().checks if c.name == "Charge injection limit"
        ).detail
        assert "geometric-average" in detail
        assert "25.6" in detail

    def test_derivation_of_the_limit_is_reproducible(self):
        """'the largest charge for a contact area of 0.06 cm^2 that did not result in a
        charge density in the damaging region' -- 30 uC/cm^2 on 0.06 cm^2 is 1.8 uC/ph,
        which sits at k = 1.73, matching the k ~ 1.75 Cogan attributes to them."""
        charge_uC = 30.0 * 0.06
        assert shannon.shannon_k(charge_uC, 0.06) == pytest.approx(1.75, abs=0.03)


class TestHudak2017:
    """Why charge-storage capacity overestimates injectable charge."""

    def test_reference_records_the_mechanisms(self):
        from neurostim.references import cite

        note = cite("hudak2017").note
        assert "overestimates" in note
        assert "oxygen reduction" in note
        assert "protein" in note

    def test_package_uses_injection_limits_not_storage_capacities(self):
        """Pt is stored at the 50-150 uC/cm^2 injection limit, not Brummer's 300-350
        uC/cm^2 charge-storage capacity, which is exactly the distinction Hudak
        explains."""
        pt = get_material("Pt")
        assert pt.cic_uC_cm2("optimistic") == pytest.approx(150.0)
        assert "Brummer" in pt.cic.note


class TestGabriel1996:
    """What the dielectric survey does and does not supply."""

    def test_recorded_as_a_survey_without_tabulated_values(self):
        from neurostim.references import cite

        note = cite("gabriel1996").note
        assert "graphical" in note
        assert "Part III" in note

    def test_conductivity_default_is_still_the_dbs_convention(self):
        """Gabriel I supplies no number to replace 0.35 S/m; IT'IS remains the source
        for the alternative value."""
        from neurostim.models import field as f

        assert pytest.approx(0.35) == f.BRAIN_CONDUCTIVITY_S_PER_M
        assert pytest.approx(0.419) == f.GREY_MATTER_CONDUCTIVITY_S_PER_M


class TestButterwick2007:
    """Current-density damage thresholds, read from the primary text."""

    def test_retina_anchor_points(self):
        from neurostim.data import butterwick2007 as b

        assert pytest.approx(0.061) == b.RETINA_THRESHOLD_AT_6MS_A_PER_CM2
        assert pytest.approx(1.3) == b.RETINA_THRESHOLD_AT_6US_A_PER_CM2

    def test_anchor_points_reproduce_from_the_fitted_power_law(self):
        from neurostim.data import butterwick2007 as b

        assert b.threshold_A_per_cm2(6000.0) == pytest.approx(0.061, rel=1e-6)
        assert b.threshold_A_per_cm2(6.0) == pytest.approx(1.3, rel=1e-6)

    def test_fitted_exponent_is_close_to_the_quoted_minus_half(self):
        """They quote t^-0.5 as characteristic of electroporation; their own two
        anchor points fit -0.44."""
        from neurostim.data import butterwick2007 as b

        assert pytest.approx(-0.44, abs=0.01) == b.FITTED_DURATION_EXPONENT
        assert abs(b.FITTED_DURATION_EXPONENT - b.QUOTED_DURATION_EXPONENT) < 0.1

    def test_shorter_pulses_tolerate_higher_current_density(self):
        from neurostim.data import butterwick2007 as b

        assert b.threshold_A_per_cm2(60.0) > b.threshold_A_per_cm2(600.0)

    def test_small_electrodes_scale_as_inverse_square_of_diameter(self):
        """Below 200 um the threshold total current is constant, so J_th goes as d^-2."""
        from neurostim.data import butterwick2007 as b

        at_100 = b.threshold_A_per_cm2(200.0, diameter_um=100.0)
        at_50 = b.threshold_A_per_cm2(200.0, diameter_um=50.0)
        assert at_50 / at_100 == pytest.approx(4.0)

    def test_large_electrodes_are_size_independent(self):
        from neurostim.data import butterwick2007 as b

        assert b.threshold_A_per_cm2(200.0, 400.0) == pytest.approx(
            b.threshold_A_per_cm2(200.0, 1000.0)
        )

    def test_size_regimes(self):
        from neurostim.data import butterwick2007 as b

        assert "d^-2" in b.size_regime(100.0)
        assert b.size_regime(500.0) == "size-independent"
        assert "transition" in b.size_regime(250.0)

    def test_single_pulse_tolerates_more_than_a_train(self):
        """Threshold falls about sevenfold from 1 pulse to saturation on retina."""
        from neurostim.data import butterwick2007 as b

        single = b.threshold_A_per_cm2(200.0, n_pulses=1)
        saturated = b.threshold_A_per_cm2(200.0, n_pulses=b.PULSE_COUNT_SATURATION)
        assert single / saturated == pytest.approx(
            b.REPEATED_EXPOSURE_FACTOR_RETINA, rel=1e-6
        )

    def test_check_now_evaluates_instead_of_deferring(self):
        from neurostim import DiscElectrode, SafetyCalculator, StimProtocol
        from neurostim.safety.assessment import Status

        check = next(
            c
            for c in SafetyCalculator(
                DiscElectrode(500.0, "Pt"), StimProtocol(10, 200, 50, 1)
            ).assess().checks
            if c.name == "Current density"
        )
        assert check.status is not Status.NOT_EVALUATED
        assert "electroporation threshold" in check.summary

    def test_exceeding_the_threshold_fails(self):
        from neurostim import DiscElectrode, SafetyCalculator, StimProtocol
        from neurostim.safety.assessment import Status

        # 1 mA into a 100 um disc is ~12.7 A/cm^2, far above threshold at 1 ms.
        check = next(
            c
            for c in SafetyCalculator(
                DiscElectrode(100.0, "SIROF"), StimProtocol(1000, 1000, 50, 1)
            ).assess().checks
            if c.name == "Current density"
        )
        assert check.status is Status.FAIL


class TestMcCreery1995Frequency:
    """The measured frequency dependence."""

    def test_table_values(self):
        from neurostim.data import mccreery1995 as m

        at50 = m.point_at(50.0)
        at100 = m.point_at(100.0)
        at20 = m.point_at(20.0)
        assert at50.slope_percent_ead_per_alpha_unit == pytest.approx(0.37)
        assert at100.slope_percent_ead_per_alpha_unit == pytest.approx(1.1)
        assert at50.threshold_alpha_units == pytest.approx(1.1)
        assert at100.threshold_alpha_units == pytest.approx(0.8)
        assert at20.threshold_alpha_units is None

    def test_doubling_frequency_triples_the_damage_slope(self):
        from neurostim.data import mccreery1995 as m

        assert pytest.approx(2.97, abs=0.02) == m.SLOPE_RATIO_50_TO_100

    def test_threshold_falls_to_073_at_100_hz(self):
        from neurostim.data import mccreery1995 as m

        assert pytest.approx(0.727, abs=0.01) == m.THRESHOLD_RATIO_50_TO_100

    def test_twenty_hz_shows_no_amplitude_correlation(self):
        from neurostim.data import mccreery1995 as m

        assert not m.point_at(20.0).amplitude_correlates
        assert m.point_at(50.0).amplitude_correlates

    def test_no_interpolation_between_measured_points(self):
        """Only three frequencies were measured; the module does not invent others."""
        from neurostim.data import mccreery1995 as m

        assert m.point_at(75.0) is None

    def test_risk_text_refuses_to_supply_a_charge_derating(self):
        """Amplitude is in recruitment units, so no charge-based factor follows."""
        from neurostim.data import mccreery1995 as m

        text = m.describe_frequency_risk(130.0)
        assert "no charge-based derating follows" in text
        assert "not measured" in text

    def test_low_frequency_message(self):
        from neurostim.data import mccreery1995 as m

        assert "no correlation" in m.describe_frequency_risk(20.0)

    def test_envelope_cites_the_measured_numbers(self):
        from neurostim import CylindricalBandElectrode, SafetyCalculator, StimProtocol

        detail = next(
            c
            for c in SafetyCalculator(
                CylindricalBandElectrode(1270, 1500, "PtIr"),
                StimProtocol(3000, 60, 130, 3600),
            ).assess().checks
            if c.name == "Validated envelope"
        ).detail
        assert "0.37 -> 1.1" in detail
        assert "0.73x" in detail


class TestGabriel1996PartIII:
    """Four-Cole-Cole parametric model, Table 1."""

    def test_grey_matter_parameters(self):
        from neurostim.data import gabriel1996 as g

        gm = g.GREY_MATTER
        assert gm.eps_inf == 4.0
        assert gm.sigma_i_S_per_m == pytest.approx(0.0200)
        assert len(gm.dispersions) == 4
        assert gm.dispersions[0] == (45.0, 7.96e-12, 0.10)
        assert gm.dispersions[3] == (4.5e7, 5.305e-3, 0.00)

    def test_blood_low_frequency_conductivity_is_its_ionic_term(self):
        """Blood has no low-frequency dispersions in Table 1, so sigma -> sigma_i."""
        from neurostim.data import gabriel1996 as g

        assert g.BLOOD.conductivity_S_per_m(100.0) == pytest.approx(0.700, rel=1e-3)

    def test_conductivity_rises_with_frequency(self):
        from neurostim.data import gabriel1996 as g

        values = [g.GREY_MATTER.conductivity_S_per_m(f) for f in (100, 1e3, 1e4, 1e6)]
        assert values == sorted(values)

    def test_permittivity_falls_with_frequency(self):
        from neurostim.data import gabriel1996 as g

        values = [g.GREY_MATTER.relative_permittivity(f) for f in (100, 1e3, 1e4, 1e6)]
        assert values == sorted(values, reverse=True)

    def test_grey_matter_exceeds_white_matter(self):
        from neurostim.data import gabriel1996 as g

        assert g.GREY_MATTER.conductivity_S_per_m(2500.0) > (
            g.WHITE_MATTER.conductivity_S_per_m(2500.0)
        )

    def test_effective_frequency_convention(self):
        from neurostim.data import gabriel1996 as g

        assert g.effective_frequency_hz(200.0) == pytest.approx(2500.0)

    def test_pulse_relevant_conductivity_is_far_below_the_dbs_convention(self):
        """The finding that matters: ~0.10 S/m vs the 0.35 S/m default."""
        from neurostim.data import gabriel1996 as g
        from neurostim.models.field import BRAIN_CONDUCTIVITY_S_PER_M

        sigma = g.conductivity_for_pulse(200.0)
        assert sigma == pytest.approx(0.104, abs=0.005)
        assert BRAIN_CONDUCTIVITY_S_PER_M / sigma == pytest.approx(3.4, abs=0.15)

    def test_compliance_check_warns_about_the_discrepancy(self):
        from neurostim import RingElectrode, SafetyCalculator, StimProtocol

        detail = next(
            c
            for c in SafetyCalculator(
                RingElectrode(330, 270, "Pt"), StimProtocol(80, 200, 130, 1),
                compliance_V=10.0,
            ).assess().checks
            if c.name == "Compliance voltage"
        ).detail
        assert "Gabriel" in detail
        assert "3.4x" in detail

    def test_measured_impedance_suppresses_the_warning(self):
        """If you measured it, the modelled conductivity spread is irrelevant."""
        from neurostim import RingElectrode, SafetyCalculator, StimProtocol

        detail = next(
            c
            for c in SafetyCalculator(
                RingElectrode(330, 270, "Pt"), StimProtocol(80, 200, 130, 1),
                compliance_V=10.0, measured_impedance_ohm=8000.0,
            ).assess().checks
            if c.name == "Compliance voltage"
        ).detail
        assert "Gabriel" not in detail

    def test_unknown_tissue_raises(self):
        from neurostim.data import gabriel1996 as g

        with pytest.raises(KeyError, match="No Cole-Cole parameters"):
            g.get("liver")


class TestMcCreery2010:
    """Primary source for the microelectrode charge-per-phase figure."""

    def test_threshold_is_bracketed_not_located(self):
        """2 nC/phase safe, 4 nC/phase damaging. The usual '4 nC/ph threshold' is the
        lowest damaging level, not the highest safe one."""
        from neurostim.data import mccreery2010 as m

        assert m.NO_DAMAGE_NC_PER_PHASE == 2.0
        assert m.DAMAGE_NC_PER_PHASE == 4.0

    def test_cogan_quotes_the_damaging_level(self):
        from neurostim.data import cogan2016, mccreery2010

        assert cogan2016.MICROELECTRODE_DAMAGE_THRESHOLD_NC_PER_PHASE == (
            mccreery2010.DAMAGE_NC_PER_PHASE
        )

    def test_halving_duty_cycle_shrank_the_damage_radius(self):
        from neurostim.data import mccreery2010 as m

        assert m.DAMAGE_RADIUS_CONTINUOUS_UM == 150.0
        assert m.DAMAGE_RADIUS_HALF_DUTY_UM == 60.0
        assert pytest.approx(2.5) == m.DUTY_CYCLE_RADIUS_RATIO

    def test_no_interpolation_between_the_two_tested_duty_cycles(self):
        from neurostim.data import mccreery2010 as m

        assert "not measured" in m.duty_cycle_note(0.75)

    def test_unpulsed_controls_were_also_damaged(self):
        """Chronic microelectrode loss is not solely a stimulation effect."""
        from neurostim.data import mccreery2010 as m

        assert m.UNPULSED_CONTROLS_ALSO_DAMAGED


class TestPEDOTPeerReviewedConsensus:
    """Three peer-reviewed measurements against one conference abstract."""

    def test_cui_zhou_and_luo_bracket_the_low_end(self):
        pedot = get_material("PEDOT")
        assert pedot.cic.low == pytest.approx(2.3)
        assert pedot.cic.high == pytest.approx(3.6)

    def test_abstract_value_is_four_to_six_fold_above_all_of_them(self):
        assert 15.0 / 3.6 > 4.0
        assert 15.0 / 2.3 > 6.0

    def test_pedot_no_longer_a_provenance_gap(self):
        from neurostim import list_materials

        assert all(m.cic.peer_reviewed for m in list_materials())


class TestInVivoDeratingSources:
    """Per-material derating now traced to its own measurement."""

    def test_platinum_from_leung(self):
        from neurostim.data import cogan2016 as c

        d = c.derating_for("Pt")
        assert "Leung" in d.evidence
        # G12 (C4.5, ledger 71): Leung's own matched-pulse-width factors, p. 852.
        assert d.factor_low == pytest.approx(3.2)
        assert d.factor_high == pytest.approx(8.7)

    def test_airof_from_hu(self):
        from neurostim.data import cogan2016 as c

        assert "Hu" in c.derating_for("AIROF").evidence

    def test_sirof_from_kane(self):
        from neurostim.data import cogan2016 as c

        assert "Kane" in c.derating_for("SIROF").evidence

    def test_derated_platinum_overlaps_leungs_measured_in_vivo_range(self):
        """Cross-check: derating the saline limit should land on what Leung actually
        measured in vivo, 3.84-16.6 uC/cm^2.

        The conservative point estimate comes out at 3.57, marginally below their
        lowest measurement -- the derating is applied to Cogan's 50 uC/cm^2 saline
        floor rather than Leung's own 34, so it errs slightly safe. The interval is
        the meaningful comparison and it overlaps their range well.
        """
        from neurostim import DiscElectrode, SafetyCalculator, StimProtocol
        from neurostim.uncertainty import Interval

        result = SafetyCalculator(
            DiscElectrode(500.0, "Pt"),
            StimProtocol(10, 200, 50, 1, anodic_first=True),
            medium="in_vivo",
        ).assess().charge
        leung = Interval(3.84, 16.6)
        assert result.limit_interval_uC_cm2.overlaps(leung)
        assert result.cic_limit_uC_cm2 <= leung.high


class TestPolarityResolvedLimits:
    """Rose & Robblee and Beebe & Rose both resolved polarity; use it."""

    def test_platinum_sub_ranges(self):
        pt = get_material("Pt")
        assert pt.cic.bounds(anodic_first=True) == (0.05, 0.10)
        assert pt.cic.bounds(anodic_first=False) == (0.10, 0.15)
        assert pt.cic.bounds(anodic_first=None) == (0.05, 0.15)

    def test_airof_sub_ranges(self):
        """Beebe & Rose: 2.1 mC/cm^2 anodic-first, 1.0 cathodic-first."""
        airof = get_material("AIROF")
        assert airof.cic.bounds(anodic_first=True) == (2.1, 2.1)
        assert airof.cic.bounds(anodic_first=False) == (1.0, 1.0)

    def test_polarity_changes_the_limit_twofold_for_platinum(self):
        from neurostim import DiscElectrode, SafetyCalculator, StimProtocol

        limits = {}
        for anodic in (True, False):
            limits[anodic] = SafetyCalculator(
                DiscElectrode(500.0, "Pt"),
                StimProtocol(10, 200, 50, 1, anodic_first=anodic),
            ).assess().charge.cic_limit_uC_cm2
        assert limits[False] / limits[True] == pytest.approx(2.0)

    def test_material_without_sub_ranges_is_unaffected(self):
        tin = get_material("TiN")
        assert tin.cic.bounds(True) == tin.cic.bounds(False) == tin.cic.bounds(None)

    def test_polarity_is_reported(self):
        from neurostim import DiscElectrode, SafetyCalculator, StimProtocol

        detail = SafetyCalculator(
            DiscElectrode(500.0, "Pt"),
            StimProtocol(10, 200, 50, 1, anodic_first=True),
        ).assess().charge.describe()
        assert "anodic-first" in detail


class TestDormantFieldsNowUsed:
    """Two pieces of information the package collected but never read."""

    def test_interphase_gap_reaches_the_report(self):
        from neurostim import DiscElectrode, SafetyCalculator, StimProtocol
        from neurostim.safety.assessment import Status

        check = next(
            c
            for c in SafetyCalculator(
                DiscElectrode(500.0, "Pt"),
                StimProtocol(10, 200, 50, 1, interphase_gap_us=100.0),
            ).assess().checks
            if c.name == "Charge balance"
        )
        assert check.status is Status.PASS
        assert "100 us interphase gap" in check.summary
        assert "efficiency" in check.detail

    def test_zero_gap_explains_the_tradeoff_too(self):
        from neurostim import DiscElectrode, SafetyCalculator, StimProtocol

        detail = next(
            c
            for c in SafetyCalculator(
                DiscElectrode(500.0, "Pt"), StimProtocol(10, 200, 50, 1)
            ).assess().checks
            if c.name == "Charge balance"
        ).detail
        assert "No interphase gap" in detail

    def test_temperature_gain_is_recorded(self):
        """Cogan: AIROF 1.67 -> 2.0 mC/cm^2 from 20 C to 37 C."""
        from neurostim.materials import AIROF_TEMPERATURE_GAIN

        assert pytest.approx(2.0 / 1.67) == AIROF_TEMPERATURE_GAIN
        assert AIROF_TEMPERATURE_GAIN > 1.19

    def test_sub_body_temperature_measurements_are_flagged(self):
        from neurostim.materials import MeasuredRange

        cold = MeasuredRange(1.0, 1.0, "mC/cm2", "cogan2008", temperature_C=20.0)
        warm = MeasuredRange(1.0, 1.0, "mC/cm2", "cogan2008", temperature_C=37.0)
        unknown = MeasuredRange(1.0, 1.0, "mC/cm2", "cogan2008")
        assert cold.measured_below_body_temperature
        assert not warm.measured_below_body_temperature
        assert not unknown.measured_below_body_temperature
        assert "below body temperature" in cold.describe()


class TestLeungsPulseWidthMatchedDerating:
    """Ledger 71 (literature audit S-1), C4.5. The platinum in-vivo derating was 2-14x, from
    the best in-vitro value over the worst in-vivo one across MISMATCHED pulse widths --
    the division Leung et al. pre-empt with their own, matched ones. Pinned against their
    sentence, quoted from the PDF with its page."""

    PDF = "papers_stim_calc_ref/In_Vivo_and_In_Vitro_Comparison_of_the_Charge_Injection_Capacity_of_Platinum_Macroelectrodes.pdf"

    def test_the_factors_are_the_sentences(self):
        from neurostim.data import cogan2016 as c

        quote = c.LEUNG_MATCHED_PULSE_WIDTH_QUOTE
        assert "8.7 times less (200" in quote and "3.2 times less (3200" in quote
        for key in ("Pt", "PtIr"):
            d = c.derating_for(key)
            assert (d.factor_low, d.factor_high) == (3.2, 8.7), key
        assert "p. 852" in c.derating_for("Pt").evidence

    def test_the_quote_is_on_page_852_of_the_pdf(self):
        import shutil
        import subprocess
        from pathlib import Path

        from neurostim.data import cogan2016 as c

        if shutil.which("pdftotext") is None:
            pytest.skip("pdftotext (poppler) not available")
        pdf = Path(__file__).resolve().parents[1] / self.PDF
        if not pdf.exists():
            pytest.skip("paper library not present")
        # PDF page 4 is journal page 852 (the article runs 849-857).
        text = subprocess.run(
            ["pdftotext", "-f", "4", "-l", "4", str(pdf), "-"],
            capture_output=True, text=True, check=True,
        ).stdout
        normalised = " ".join(text.split())
        assert "852" in normalised.split()[:3]
        assert " ".join(c.LEUNG_MATCHED_PULSE_WIDTH_QUOTE.split()) in normalised


class TestTheStainlessSteelFiguresCarryTheirOwnSources:
    """Ledgers 72, 73 and 151 (literature audit S-2, S-3), C4.6. The 316LVM record said 20
    uC/cm^2 was Riedy & Walter's own year-long conclusion. Their text attributes it to a
    cited tissue-damage report, their ref. [8]; 40 uC/cm^2 "has been reported"; and neither
    was measured under the conditions the record attached to them, which are those of
    their corrosion test. The 1.2 V reversible limit is theirs by citation too ([5]).
    Quoted from the PDF in the library with pages (its OCR prints the micro sign as "p").
    """

    PDF = "papers_stim_calc_ref/10.495287.pdf"

    def _page(self, number):
        import shutil
        import subprocess
        from pathlib import Path

        if shutil.which("pdftotext") is None:
            pytest.skip("pdftotext (poppler) not available")
        pdf = Path(__file__).resolve().parents[1] / self.PDF
        if not pdf.exists():
            pytest.skip("paper library not present")
        # The article runs 660-663; PDF page n is journal page 659 + n.
        text = subprocess.run(
            ["pdftotext", "-f", str(number - 659), "-l", str(number - 659), str(pdf), "-"],
            capture_output=True, text=True, check=True,
        ).stdout
        return "".join(text.split())

    @pytest.mark.parametrize(
        ("name", "page"),
        [("REPORTED_40_QUOTE", 660), ("OWN_RESULT_QUOTE", 662),
         ("REVERSIBLE_LIMIT_QUOTE", 662), ("TISSUE_20_QUOTE", 663)],
    )
    def test_each_stored_quote_is_on_its_page(self, name, page):
        from neurostim.data import riedy_walter1996 as rw

        assert "".join(getattr(rw, name).split()) in self._page(page)

    def test_the_20_is_attributed_to_the_cited_tissue_report(self):
        from neurostim.data import riedy_walter1996 as rw

        assert "[8]" in rw.TISSUE_20_QUOTE and "Based on this report" in rw.TISSUE_20_QUOTE
        cic = get_material("SS316LVM").cic
        for text in (cic.recommendation_note, cic.note):
            assert "[8]" in text and "p. 663" in text, text
            assert "their own year-long experiment" not in text.lower(), text

    def test_no_measurement_conditions_are_attached_to_figures_nobody_measured(self):
        """The 100 us / 60 pps / interstitial-fluid / 0.016 cm^2 conditions were those of
        the corrosion test run at 20 uC/cm^2; they now sit in the note, labelled so."""
        cic = get_material("SS316LVM").cic
        assert cic.pulse_width_us is None
        assert cic.measured_area_cm2 is None
        assert cic.waveform == "" and cic.medium == ""
        assert "corrosion test" in cic.note and "100 us" in cic.note

    def test_the_reversible_limit_is_theirs_by_citation(self):
        from neurostim.data import riedy_walter1996 as rw

        assert "[ 5 ]" in rw.REVERSIBLE_LIMIT_QUOTE or "[5]" in rw.REVERSIBLE_LIMIT_QUOTE
        note = get_material("SS316LVM").water_window.note
        assert "ref. [5]" in note and "p. 662" in note


def _pdf_page_text(relative, page):
    """Whitespace-free text of one PDF page, or skip when poppler or the library is absent."""
    import shutil
    import subprocess
    from pathlib import Path

    if shutil.which("pdftotext") is None:
        pytest.skip("pdftotext (poppler) not available")
    pdf = Path(__file__).resolve().parents[1] / relative
    if not pdf.exists():
        pytest.skip("paper library not present")
    text = subprocess.run(
        ["pdftotext", "-f", str(page), "-l", str(page), str(pdf), "-"],
        capture_output=True, text=True, check=True,
    ).stdout
    return "".join(text.split())


class TestLedger77ConditionsAndDerivations:
    """Ledger 77 (literature audit S-6 to S-13), C4.7a: the items whose sources settle them
    -- S-7, S-11 and S-12. One assertion per item, each against its source sentence."""

    def test_s7_the_airof_derating_quotes_the_right_hu_sentence(self):
        """Hu et al. (p. 888): "the in vivo value is about 10% of the in vitro ones for both
        electrodes". Their 3-4 mC/cm^2 sentence (p. 886) compares AIROF with PLATINUM,
        citing another paper; the evidence string welded the two."""
        from neurostim.data import cogan2016 as c
        from neurostim.references import cite

        quote = c.HU_IN_VIVO_QUOTE
        assert "".join(quote.split()) in _pdf_page_text(
            "papers_stim_calc_ref/In_Vitro_and_In_Vivo_Charge_Capacity_of_AIROF_Microelectrodes.pdf", 3
        )
        d = c.derating_for("AIROF")
        assert (d.factor_low, d.factor_high) == (10.0, 10.0)  # the number survives
        for text in (d.evidence, cite("hu2006").note):
            assert "same films" not in text, text
            assert "1.69" in text and "1.18" in text, text

    def test_s11_neither_best_reported_capacitor_design_has_a_pulse_width(self):
        """Rose et al. 1985: the 2.6 and 6.3 uC/mm^2 are Table III's "Highest charge density"
        (p. 191); its "200 us constant current pulse" belongs to a theoretical last column.
        The etched-Ti 6.3 was measured on an AC capacitance bridge (Table I, "1570 (AC)",
        footnote d, p. 187, read from the page image)."""
        from neurostim.data import ta2o5_capacitor as ta

        assert "200~sconstantcurrentpulse" in _pdf_page_text(
            "papers_stim_calc_ref/0165-0270%2885%2990001-9.pdf", 11
        )
        for label, basis in (("etched Ta, best reported", "slow-charge"),
                             ("etched Ti, best reported", "capacitance bridge")):
            design = next(d for d in ta.DESIGNS if label in d.label)
            assert design.pulse_width_us is None, label
            assert basis in design.note, label
            assert "Table III" in design.note, label

    def test_s12_mccreery_2010_carries_its_defining_conditions(self):
        """Author manuscript p. 3: "cathodic pulses 200 us in duration ... biased to + 0.6
        volts ... in order to increase their charge capacity"; p. 2: "2,000 +/- 150 um2"."""
        from neurostim.data import mccreery2010 as m

        page3 = _pdf_page_text("papers_stim_calc_ref/nihms209066.pdf", 3)
        assert "".join(m.CONDITIONS_QUOTE.split()) in page3
        assert m.PULSE_WIDTH_US == 200.0
        assert m.INTERPULSE_BIAS_V == 0.6
        assert m.ELECTRODE_AREA_UM2 == (2000.0, 150.0)
        assert m.POLARITY == "cathodic"
        for duty in (1.0, 0.5):
            note = m.duty_cycle_note(duty)
            assert "200 us" in note and "+0.6 V" in note, note

    def test_s12_the_60_um_radius_is_not_the_whole_loss_at_half_duty(self):
        """p. 1: the insertion injury "was responsible for most of the neuronal loss within
        150 um of the electrodes pulsed with the 50% duty cycle"."""
        from neurostim.data import mccreery2010 as m

        assert "".join(m.INSERTION_LOSS_QUOTE.split()) in _pdf_page_text(
            "papers_stim_calc_ref/nihms209066.pdf", 1
        )
        note = m.duty_cycle_note(0.5)
        assert "insertion" in note and "150 um" in note, note


class TestTheElwassifCitationIsThePaperTheValuesCameFrom:
    """Ledgers 75, 45, 78/S-19 and 124, C4.8. Metadata read from the PDFs in the library."""

    PDF = "papers_stim_calc_ref/elwassif2006.pdf"

    def test_75_the_reference_is_the_conference_paper(self):
        """The module reads Table I from the Proc. 28th IEEE EMBS paper (pp. 3580-3583, the
        PDF's own page footers); references.py cited the J Neural Eng article, with that
        article's DOI, volume, pages and PMID. The conference PDF prints no DOI, so none is
        invented."""
        from neurostim.references import cite

        ref = cite("elwassif2006")
        assert ref.source_type == "conference"
        assert "28th" in ref.venue and "EMBS" in ref.venue
        assert ref.pages == "3580-3583"
        assert ref.doi == "" and ref.pmid == ""
        first, last = _pdf_page_text(self.PDF, 1), _pdf_page_text(self.PDF, 4)
        assert "3580" in first and "3583" in last
        assert "10.1088" not in first + last

    def test_45_the_papers_rms_does_not_follow_from_its_setting(self):
        """p. 3581: 10 V, 185 pps, 210 us "using a constant Vrms of 1.56 Volt". The RMS of that
        setting is 10 * sqrt(185 * 210e-6) = 1.971 V; 1.56 V implies 131.5 us. Transcribed
        faithfully, and the discrepancy recorded rather than "corrected"."""
        import math

        from neurostim.data import elwassif2006 as e

        assert "".join(e.RMS_QUOTE.split()) in _pdf_page_text(self.PDF, 2)
        assert e.V_RMS == 1.56  # the paper's number, unchanged
        assert pytest.approx(10.0 * math.sqrt(185 * 210e-6)) == e.RMS_OF_STATED_SETTING_V
        assert pytest.approx(1.971, abs=5e-4) == e.RMS_OF_STATED_SETTING_V
        assert pytest.approx(131.5, abs=0.05) == e.IMPLIED_PULSE_WIDTH_US

    def test_s19_leung_is_dated_by_its_issue(self):
        from neurostim.references import cite

        assert cite("leung2014").year == 2015
        assert "MARCH2015" in _pdf_page_text(
            "papers_stim_calc_ref/In_Vivo_and_In_Vitro_Comparison_of_the_Charge_Injection_Capacity_of_Platinum_Macroelectrodes.pdf",
            1,
        )

    def test_124_the_mccreery_preset_is_checked_against_its_paper(self):
        """McCreery 2010 is in the library (nihms209066.pdf); ledger 124 said it was not.
        Author manuscript p. 2: the insulation "was laser-ablated from their tips, to yield a
        geometric surface area of 2,000 +/- 150 um2"; the 50.5 um disc is 2003 um^2."""
        import math

        from neurostim.electrodes import get_preset

        preset = get_preset("mccreery2010_chronic")
        assert "not in the package's library" not in preset.note
        assert "p. 2" in preset.note and "2,000" in preset.note
        assert math.isclose(preset.electrode.area_um2, 2000.0, rel_tol=0.075)
        assert "laser-ablatedfromtheirtips" in _pdf_page_text(
            "papers_stim_calc_ref/nihms209066.pdf", 2
        )
        weiland = get_preset("weiland_tin")
        assert "not in the package's library" in weiland.note  # still true, and said


class TestLedger78LowerSeverityCorrections:
    """Ledger 78 (literature audit S-14 to S-18), C4.9a. One assertion per item."""

    ROSE = "papers_stim_calc_ref/0165-0270%2885%2990001-9.pdf"

    def test_s14_the_separating_band_is_not_zero_width(self):
        """The highest no-damage point and a partial-damage point share k = 1.699, so
        "the highest safe and lowest damaging" gave (1.699, 1.699). A separatrix must lie
        at or above every no-damage point and below every all-damage point; the partial
        points are the transition inside that band. Pinned to the k the package uses."""
        from neurostim.data import mccreery1990 as m
        from neurostim.safety import shannon

        low, high = m.separating_k_range()
        assert low == pytest.approx(1.69897, abs=1e-5)
        assert high == pytest.approx(2.10721, abs=1e-5)
        partial = [p.shannon_k for p in m.TABLE_I if p.outcome == "partial"]
        assert all(low <= k <= high for k in partial)
        assert low < shannon.K_MODERATE < high and low < shannon.K_DAMAGE_OBSERVED < high
        assert low > shannon.K_SHANNON  # Shannon's 1.5 sits below the observed transition

    def test_s15_the_target_densities_belong_to_the_introductions_electrode(self):
        """Rose et al. p. 182: 10,000 uC/cm^2 and 50 A/cm^2 on "0.5 x 10-6 cm2 as used by
        Schmidt and McIntosh"; on the module's 1e-4 mm^2 (1e-6 cm^2) the same 5 nC in
        0.2 ms is 5,000 uC/cm^2 and 25 A/cm^2."""
        from neurostim.data import ta2o5_capacitor as ta

        assert "10,000" in _pdf_page_text(self.ROSE, 2)
        doc = ta.__doc__
        assert "5,000 uC/cm^2" in doc and "25 A/cm^2" in doc
        assert "0.5e-6 cm^2" in doc

    def test_s16_the_thermal_conductivity_range_is_the_papers_sweep(self):
        """Elwassif Table I (p. 3582) sweeps 0.45, 0.50, 0.55 and 0.60 W/m/K; 0.45 gives the
        hottest result in that block."""
        from neurostim.data import elwassif2006 as e

        swept = sorted({
            p.thermal_conductivity_W_per_mK for p in e.TABLE_I
            if p.sigma_S_per_m == 0.30 and p.perfusion_per_s == 0.0
            and p.thermal_conductivity_W_per_mK != 0.527
        })
        assert e.THERMAL_CONDUCTIVITY_RANGE_W_PER_MK == (min(swept), max(swept)) == (0.45, 0.6)

    def test_s17_the_peak_rise_docstring_names_its_own_row(self):
        import inspect

        from neurostim.data import elwassif2006 as e

        source = inspect.getsource(e)
        doc = source.split("PEAK_RISE_K = ", 1)[1].split('"""', 2)[1]
        assert "lowest thermal conductivity in the sweep" not in doc
        assert "0.527" in doc and "0.45" in doc

    def test_s18_tio2_storage_is_as_the_source_states(self):
        """Rose et al. p. 186: "a factor of as much as 4 relative to Ta based electrodes";
        their Table III gives 2.6 against 6.3 uC/mm^2 (2.4x) and 0.07 against 0.10 nA/nF."""
        from neurostim.data import ta2o5_capacitor as ta

        assert "factorofasmuchas4" in _pdf_page_text(self.ROSE, 6)
        design = next(d for d in ta.DESIGNS if "etched Ti, best reported" in d.label)
        assert "5-10x" not in design.note
        assert "as much as 4" in design.note and "2.4x" in design.note


class TestRiedyAndWaltersCitedSourcesAreNamedAsCited:
    """Ledger 152, the C4.6 follow-up. Their ref. [8] (the 20 uC/cm^2) is Robblee & Rose
    1990 and ref. [5] (the 1.2 V limit) is Lan, Daroux & Mortimer, by position in the
    reference list on p. 663. Neither is in the library, so both are named as cited by
    Riedy & Walter, never as verified primaries."""

    def test_both_are_named_and_marked_as_via_citation(self):
        from neurostim.data import riedy_walter1996 as rw

        material = get_material("SS316LVM")
        assert "Robblee & Rose 1990" in material.cic.recommendation_note
        assert "cited via Riedy & Walter" in material.cic.recommendation_note
        assert "Lan, Daroux & Mortimer" in material.water_window.note
        assert "cited via Riedy & Walter" in material.water_window.note
        assert "not verified primaries" in " ".join(rw.__doc__.split())

    def test_the_list_positions_are_on_page_663(self):
        page = _pdf_page_text("papers_stim_calc_ref/10.495287.pdf", 4)
        assert "Pittingcorrosionofhighstrength" in page
        assert "Electrochemicalguidelinesforselectionof" in page


class TestLedger77ExponentAndDerating:
    """Ledger 77, C4.7b, per the user's decisions: S-6 (b) and S-8 (b)."""

    BUTTERWICK = "papers_stim_calc_ref/Tissue_Damage_by_Pulsed_Electrical_Stimulation.pdf"

    def test_s6_the_published_exponent_is_recorded_and_used(self):
        """Butterwick p. 2264 (read from the page image; the exponents are typeset as
        glyphs the text layer drops): "the power fit slopes are t^-0.52 and t^-0.48 in the
        chronic regime". Their abstract (p. 2261) gives the two anchors, "0.061 A/cm2 at
        6 ms to 1.3 A/cm2 at 6 us"."""
        from neurostim.data import butterwick2007 as b

        assert b.PUBLISHED_EXPONENT_RETINA_SUSTAINED == -0.48
        abstract = _pdf_page_text(self.BUTTERWICK, 1)
        assert "0.061A/cm2at6ms" in abstract

    def test_s6_the_default_is_the_published_line_capped_by_the_anchors(self):
        """Our construction, not the paper's: the -0.48 line anchored at 6 ms, taken as the
        minimum with the two-anchor line, so neither published anchor is exceeded."""
        from neurostim.data import butterwick2007 as b

        def line(n, pw):
            return b.RETINA_THRESHOLD_AT_6MS_A_PER_CM2 * (pw / b.ANCHOR_LONG_US) ** n

        for pw in (6.0, 60.0, 200.0, 1000.0, 6000.0, 20000.0):
            expected = min(line(-0.48, pw), line(b.FITTED_DURATION_EXPONENT, pw))
            assert b.threshold_A_per_cm2(pw) == pytest.approx(expected, rel=1e-12), pw
        assert b.threshold_A_per_cm2(6.0) == pytest.approx(1.3, rel=1e-12)
        assert b.threshold_A_per_cm2(6000.0) == pytest.approx(0.061, rel=1e-12)
        assert b.threshold_A_per_cm2(20000.0) < line(b.FITTED_DURATION_EXPONENT, 20000.0)
        # An explicit exponent is still a plain power law.
        assert b.threshold_A_per_cm2(60.0, exponent=-0.5) == pytest.approx(line(-0.5, 60.0))

    def test_s8_the_sirof_derating_cites_both_of_its_sources(self):
        """Kane et al. (author manuscript p. 7): "reduced by a factor of 2-3"; Cogan 2016
        (author manuscript p. 8): "a factor of four lower with SIROF microelectrodes". The
        range stays 2-4, with the 4 attributed to the review."""
        from neurostim.data import cogan2016 as c

        d = c.derating_for("SIROF")
        assert (d.factor_low, d.factor_high) == (2.0, 4.0)
        assert "factor of 2-3" in d.evidence and "Kane" in d.evidence
        assert "Cogan et al. 2016" in d.evidence and "factor of four" in d.evidence
        # The PDF prints an en dash.
        assert "factorof2\u20133" in _pdf_page_text("papers_stim_calc_ref/nihms-1619003.pdf", 7)
        assert "afactoroffourlowerwithSIROF" in _pdf_page_text(
            "papers_stim_calc_ref/nihms854736.pdf", 8
        )


class TestLedger78DerivedValuesAndSecondaryChains:
    """Ledger 78 (literature audit S-22, S-23, S-25), C4.9b."""

    def test_s22_two_derived_values_are_labelled_as_derived(self):
        """AIROF's measured_area_cm2 = 4.1e-4 is the midpoint of Beebe & Rose's "3.7 to
        4.5 x 10-4 cm2" (p. 494); the Schaldach wire's forming_voltage_V = 2.5 is back-solved
        from the quoted "breakdown voltage of 2 V" (Rose et al. p. 184) over 0.8."""
        from neurostim.data import ta2o5_capacitor as ta

        assert "3.7to4.5x10-4cm2" in _pdf_page_text("papers_stim_calc_ref/beebe1988.pdf", 1)
        airof = get_material("AIROF").cic
        assert airof.measured_area_cm2 == pytest.approx(4.1e-4)
        assert "midpoint" in airof.note and "3.7-4.5e-4" in airof.note
        schaldach = next(d for d in ta.DESIGNS if "Schaldach" in d.label)
        assert "back-solved" in schaldach.note and "2 V" in schaldach.note

    def test_s23_the_contact_diameter_is_not_attributed_to_elwassif(self):
        """The conference paper states "1.5 mm electrodes and 0.5 mm spacing" (p. 3581) but
        no contact diameter; the 1.27 mm is the manufacturer's figure."""
        import inspect

        from neurostim.data import elwassif2006 as e

        assert "1.5mmelectrodesand0.5mmspacing" in _pdf_page_text(
            "papers_stim_calc_ref/elwassif2006.pdf", 2
        )
        source = inspect.getsource(e)
        doc = source.split("LEAD_3389_CONTACT_DIAMETER_UM = ", 1)[1].split('"""', 2)[1]
        assert "not stated in the paper" in doc.lower() and "manufacturer" in doc

    @pytest.mark.parametrize(
        ("key", "via"),
        [("wang_weiland2012", "cogan2016"), ("mccreery2008", "cogan2016"),
         ("robblee_rose1990_chapter", "riedy_walter1996"),
         ("lan_daroux_mortimer", "riedy_walter1996")],
    )
    def test_s25_each_secondary_source_is_recorded_as_cited_via(self, key, via):
        """Four sources the package's figures rest on through another paper. Each has an
        entry whose metadata is taken from the citing paper's reference list, marked as not
        in the library and cited via that paper."""
        from neurostim.references import cite

        ref = cite(key)
        assert f"cited via {via}" in ref.note
        assert "not in the library" in ref.note.lower()

    def test_s25_the_citing_lists_carry_them(self):
        cogan = _pdf_page_text("papers_stim_calc_ref/nihms854736.pdf", 20)
        assert "Reductionofcurrentdensityatdiskelectrodeperiphery" in cogan
        assert "Cochlearnucleusauditoryprostheses" in _pdf_page_text(
            "papers_stim_calc_ref/nihms854736.pdf", 18
        )


class TestLedger77SmallElectrodeAnchor:
    """Ledger 77, S-13, C4.7c, per the user's decision (b'): the d^-2 model stays and no
    number moves; the paper's own small-electrode measurements are recorded beside it.

    Butterwick p. 2264, Fig. 5 caption: "In the regime of constant current, electrodes
    smaller than 200 um, the threshold value of total current for damage is 139 uA on
    retina and 55 uA on CAM"; the text: "only one pulse of duration 60 us on CAM and 600 us
    on the retina"; and, read from the page image (the exponents are glyphs the text layer
    drops), "the slopes are also t^-0.48 for the large pipette and t^-0.29 for the small
    one"."""

    BUTTERWICK = "papers_stim_calc_ref/Tissue_Damage_by_Pulsed_Electrical_Stimulation.pdf"

    def test_the_anchor_and_slope_are_recorded_from_page_2264(self):
        from neurostim.data import butterwick2007 as b

        page = _pdf_page_text(self.BUTTERWICK, 4)
        # The text layer renders the micro sign as the control character U+0016.
        assert "thresholdvalueoftotalcurrentfordamageis139\x16Aonretinaand55\x16AonCAM" in page
        assert "onlyonepulseofduration60sonCAMand600sontheretina" in page
        assert b.SMALL_ELECTRODE_THRESHOLD_CURRENT_UA == {"retina": 139.0, "cam": 55.0}
        assert b.SMALL_ELECTRODE_PULSE_WIDTH_US == {"retina": 600.0, "cam": 60.0}
        assert b.SMALL_ELECTRODE_DURATION_EXPONENT_RETINA == -0.29
        assert "t^-0.29" in b.SMALL_ELECTRODE_QUOTE and "139 uA" in b.SMALL_ELECTRODE_QUOTE

    def test_the_measured_density_is_the_total_current_over_the_disc(self):
        from neurostim.data import butterwick2007 as b

        assert b.measured_small_electrode_A_per_cm2(199.0) == pytest.approx(
            139e-6 / (math.pi * (199e-4 / 2) ** 2), rel=1e-12
        )
        assert b.measured_small_electrode_A_per_cm2(100.0, "cam") == pytest.approx(
            55e-6 / (math.pi * (100e-4 / 2) ** 2), rel=1e-12
        )
        with pytest.raises(ValueError, match="200"):
            b.measured_small_electrode_A_per_cm2(200.0)

    def test_the_model_sits_below_every_measured_point_checked(self):
        """At the saturated default, at the anchor's own pulse width: 2.62x below on retina
        and 1.12x below on CAM, the same at every diameter since both scale as d^-2. The
        model is unchanged: 0.169 A/cm^2 at 600 us and 200 um."""
        from neurostim.data import butterwick2007 as b

        assert b.threshold_A_per_cm2(600.0, 200.0) == pytest.approx(0.16912, rel=1e-4)
        assert b.measured_small_electrode_A_per_cm2(199.999) == pytest.approx(0.4425, rel=1e-3)
        for tissue, low, high in (("retina", 2.61, 2.63), ("cam", 1.11, 1.13)):
            pw = b.SMALL_ELECTRODE_PULSE_WIDTH_US[tissue]
            for d in (20.0, 50.0, 100.0, 115.0, 150.0, 199.0):
                ratio = b.measured_small_electrode_A_per_cm2(d, tissue) / (
                    b.threshold_A_per_cm2(pw, d, tissue=tissue)
                )
                assert low < ratio < high, (tissue, d, ratio)

    def test_the_docstring_states_the_comparison_and_the_cam_inconsistency(self):
        from neurostim.data import butterwick2007 as b

        doc = b.__doc__
        assert "139 uA" in doc and "55 uA" in doc and "t^-0.29" in doc
        assert "0.169 A/cm^2" in doc and "0.44 A/cm^2" in doc
        # The retina line at 60 us, 139 x 10^0.29 = 271 uA, over three is about 90 uA,
        # against the 55 uA measured on CAM.
        assert "90 uA" in doc
        cam_predicted_uA = 139.0 * 10**0.29 / 3.0
        assert 90.3 < cam_predicted_uA < 90.5
        # G12, changed at C4.7d (ledger 154): the docstring used to say the single-pulse
        # relief was applied on top of d^-2 below 200 um without having been measured
        # there; it is no longer applied there, so the comparison holds at every count.
        assert "saturated" in doc and "never below 200 um" in doc and "ledger 154" in doc

    def test_a_small_electrode_renders_the_anchor_and_is_provisional(self):
        from neurostim import SafetyCalculator, StimProtocol

        assessment = SafetyCalculator(
            DiscElectrode(100.0, "Pt"), StimProtocol(5, 200, 130, 1)
        ).assess()
        check = next(c for c in assessment.checks if c.name == "Current density")
        assert check.provisional
        assert "provisional below 200 um" in check.detail
        assert "139 uA" in check.detail and "55 uA" in check.detail
        # A 1 mm disc is outside the regime and gets no such line.
        big = SafetyCalculator(
            DiscElectrode(1000.0, "Pt"), StimProtocol(5, 200, 130, 1)
        ).assess()
        detail = next(c for c in big.checks if c.name == "Current density").detail
        assert "provisional below 200 um" not in detail

    def test_below_saturation_the_line_says_why_no_relief_is_applied(self):
        """G12, changed at C4.7d (ledger 154): the line used to say the relief applied on
        top of d^-2 was not measured; by the user's decision it is no longer applied below
        200 um, and the line says that instead."""
        from neurostim.data import butterwick2007 as b

        few = b.compare(0.1, 600.0, 100.0, n_pulses=5).describe()
        many = b.compare(0.1, 600.0, 100.0).describe()
        assert "single-pulse relief not applied below 200 um" in few
        assert "never measured there" in few
        assert "relief not applied" not in many
        assert "relief not applied" not in b.compare(0.1, 600.0, 250.0, n_pulses=5).describe()


class TestLedger154NoSinglePulseReliefOnSmallElectrodes:
    """Ledger 154, C4.7d, per the user's decision: below 200 um the threshold is the
    saturated (n >= 50) one whatever n_pulses is, because Butterwick measured the pulse-count
    dependence only on the 1 mm pipette (p. 2263, Fig. 3 caption: "A pipette of 1 mm in
    diameter was used in these measurements"). At and above 200 um nothing changes."""

    BUTTERWICK = "papers_stim_calc_ref/Tissue_Damage_by_Pulsed_Electrical_Stimulation.pdf"

    def test_the_pulse_count_data_are_from_the_1mm_pipette(self):
        page = _pdf_page_text(self.BUTTERWICK, 3)
        assert "Apipetteof1mmindiameterwasusedinthesemeasurements" in page

    def test_one_pulse_on_a_100um_retina_disc_is_at_or_below_the_measured_anchor(self):
        from neurostim.data import butterwick2007 as b

        single = b.threshold_A_per_cm2(600.0, 100.0, n_pulses=1)
        assert single <= b.measured_small_electrode_A_per_cm2(100.0)
        assert single == b.threshold_A_per_cm2(600.0, 100.0)

    def test_below_200um_n_pulses_does_not_move_the_threshold(self):
        from neurostim.data import butterwick2007 as b

        for tissue in ("retina", "cam"):
            for d in (20.0, 100.0, 199.9):
                saturated = b.threshold_A_per_cm2(200.0, d, tissue=tissue)
                for n in (1, 2, 10, 49, 50, 500):
                    assert b.threshold_A_per_cm2(
                        200.0, d, n_pulses=n, tissue=tissue
                    ) == saturated, (tissue, d, n)

    def test_at_and_above_200um_the_relief_is_unchanged(self):
        from neurostim.data import butterwick2007 as b

        for d in (None, 200.0, 250.0, 1000.0):
            saturated = b.threshold_A_per_cm2(600.0, d)
            assert b.threshold_A_per_cm2(600.0, d, n_pulses=1) == pytest.approx(
                7.0 * saturated, rel=1e-12
            ), d
            assert b.threshold_A_per_cm2(
                60.0, d, n_pulses=1, tissue="cam"
            ) == pytest.approx(14.0 * b.threshold_A_per_cm2(60.0, d, tissue="cam"), rel=1e-12)

    def test_the_assessment_tightens_a_short_train_on_a_small_disc(self):
        """A 100 um Pt disc, 5 uA, 200 us, 2 pulses: the Current density ceiling is the
        saturated one, not 7^(1 - ln2/ln50) = 5.5x above it."""
        from neurostim import SafetyCalculator, StimProtocol
        from neurostim.data import butterwick2007 as b

        electrode = DiscElectrode(100.0, "Pt")
        short = SafetyCalculator(electrode, StimProtocol(5, 200, 2, 1)).assess()
        check = next(c for c in short.checks if c.name == "Current density")
        expected = b.threshold_A_per_cm2(200.0, 2.0 * electrode.equivalent_radius_um)
        assert check.ceiling_uA <= expected * electrode.area_cm2 * 1e6
        assert "single-pulse relief not applied below 200 um" in check.detail


class TestLedger78SourceRadius:
    """Ledger 78, S-23, the radius half, per the user's decision (a): keep 1.3803 mm and
    document where it comes from."""

    ELWASSIF = "papers_stim_calc_ref/elwassif2006.pdf"

    def test_the_paper_states_no_radius_or_diameter(self):
        for page in (1, 2, 3, 4):
            text = _pdf_page_text(self.ELWASSIF, page).lower()
            assert "radius" not in text and "diameter" not in text, page

    def test_the_default_is_one_contacts_equal_area_disc_radius(self):
        """pi a^2 = pi x 1.27 mm x 1.5 mm gives a = 1.38022 mm; the same a solves
        4 pi a^2 = 4 x that area, so it is also the equal-area sphere of four contacts."""
        import inspect

        from neurostim.data import elwassif2006 as e

        contact = CylindricalBandElectrode(
            e.LEAD_3389_CONTACT_DIAMETER_UM, e.LEAD_3389_CONTACT_HEIGHT_UM, "PtIr"
        )
        default = inspect.signature(e.implied_power_W).parameters["source_radius_m"].default
        assert default == e.SOURCE_RADIUS_M
        assert abs(e.SOURCE_RADIUS_M - contact.equivalent_radius_um * 1e-6) < 1e-7
        four_sphere = math.sqrt(4 * contact.area_um2 / (4 * math.pi)) * 1e-6
        assert abs(e.SOURCE_RADIUS_M - four_sphere) < 1e-7

    def test_the_docstring_names_the_derivation_and_the_two_contact_alternative(self):
        """Their protocol energises two contacts; their equal-area sphere is 0.976 mm,
        which would give 5.30 mW and 459 ohm at 1.56 V RMS instead of 7.50 mW and 325."""
        from neurostim.data import elwassif2006 as e

        doc = " ".join(e.implied_power_W.__doc__.split())
        assert "equal-area disc" in doc and "not stated in the paper" in doc
        assert "four contacts" in doc and "0.976 mm" in doc and "459 ohm" in doc
        two = e.implied_power_W(source_radius_m=0.9759610647971567e-3)
        assert two == pytest.approx(5.30e-3, rel=1e-3)
        assert e.V_RMS**2 / two == pytest.approx(459.2, rel=1e-3)


class TestLedger153CurrentDensityPassIsProvisional:
    """Ledger 153, per the user's decision: text only, no verdict change. The check can
    PASS, and is provisional at every size; its docstring and the caveat comment said it
    never returns a bare PASS."""

    def test_a_pass_is_possible_and_always_provisional(self):
        from neurostim import SafetyCalculator, StimProtocol
        from neurostim.safety.assessment import Status

        assessment = SafetyCalculator(
            DiscElectrode(100.0, "Pt"), StimProtocol(5, 200, 130, 1)
        ).assess()
        check = next(c for c in assessment.checks if c.name == "Current density")
        assert check.status is Status.PASS and check.provisional

    def test_the_text_no_longer_claims_no_bare_pass(self):
        import inspect

        from neurostim.safety import assessment

        doc = " ".join(assessment._current_density_check.__doc__.split())
        assert "never returns a bare PASS" not in doc
        assert "can PASS" in doc and "provisional at every size" in doc
        source = inspect.getsource(assessment.SafetyCalculator.assess)
        assert "never returns a bare PASS" not in source


class TestLedger159SmallPipetteDiameter:
    """Ledger 159 (Phase 4 review M5), C4b.4. Butterwick p. 2264 gives the small pipette
    two sizes: "two different diameters—0.115 and 1.0 mm" in the text, and "pipettes of
    0.12 (●) and 1.0 mm (○)" in the Fig. 6 caption. No number is affected."""

    BUTTERWICK = "papers_stim_calc_ref/Tissue_Damage_by_Pulsed_Electrical_Stimulation.pdf"

    def test_both_sizes_are_on_the_page_and_the_module_names_both(self):
        from neurostim.data import butterwick2007 as b

        page = _pdf_page_text(self.BUTTERWICK, 4)
        assert "twodifferentdiameters—0.115and1.0mm" in page
        assert "measuredwithpipettesof0.12(" in page
        doc = " ".join(b.__doc__.split())
        assert "0.115 mm" in doc and "0.12 mm" in doc and "Fig. 6 caption" in doc
