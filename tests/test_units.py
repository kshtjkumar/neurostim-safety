"""Unit conversions, pinned to SI written longhand.

``neurostim/units.py`` had no importing test and 0 of its 1 branch points exercised, and
four mutations that *delete* a unit conversion survived the whole suite (ledger 65): the
us->s factor in ``charge.cic_max_current_uA``, the um->mm factor and the 4/3 in
``vta.activated_volume_mm3``, and the uA*us->uC factor in
``strength_duration.weiss_threshold_charge_uC``.  Every one survived because the only test
that reached it asserted a *ratio* or a *sign*, in which the constant cancels exactly.

So no expected value in this file is a round-trip through the converter it checks.  Each
is the SI chain written out --- ``1 mm = 0.1 cm``, so ``1 mm^2 = 0.1^2 cm^2`` --- or an
absolute magnitude derived from the inputs by hand.  A ratio assertion appears nowhere in
this file by design.
"""

from __future__ import annotations

import math

import pytest

from neurostim import units
from neurostim.materials import get_material
from neurostim.models import strength_duration as sd
from neurostim.models import vta
from neurostim.safety import charge as charge_mod


class TestChargeFromCurrentAndTime:
    """``Q = I * W``, with the prefix arithmetic spelled out every time."""

    def test_one_microamp_for_one_microsecond_is_one_picocoulomb(self) -> None:
        # 1e-6 A * 1e-6 s = 1e-12 C.  1e-12 C expressed in uC is 1e-12 * 1e6 = 1e-6 uC.
        assert units.charge_uC(1.0, 1.0) == pytest.approx(1e-12 * 1e6)

    def test_the_worked_example_charge_in_coulombs_first(self) -> None:
        # 80 uA for 200 us: 80e-6 A * 200e-6 s = 1.6e-8 C = 0.016 uC.
        coulombs = (80.0 * 1e-6) * (200.0 * 1e-6)
        assert coulombs == pytest.approx(1.6e-8)
        assert units.charge_uC(80.0, 200.0) == pytest.approx(coulombs * 1e6)
        assert units.charge_uC(80.0, 200.0) == pytest.approx(0.016)

    def test_inverting_the_charge_recovers_the_current_in_amperes(self) -> None:
        # 0.016 uC = 1.6e-8 C delivered over 200e-6 s is 8e-5 A = 80 uA.
        amperes = (0.016 * 1e-6) / (200.0 * 1e-6)
        assert amperes == pytest.approx(8e-5)
        assert units.current_uA_from_charge(0.016, 200.0) == pytest.approx(amperes * 1e6)

    def test_a_non_positive_window_is_a_domain_error(self) -> None:
        """The one branch point in units.py, previously never taken."""
        with pytest.raises(ValueError, match="pulse_width_us must be > 0"):
            units.current_uA_from_charge(0.016, 0.0)
        with pytest.raises(ValueError, match="pulse_width_us must be > 0"):
            units.current_uA_from_charge(0.016, -200.0)


class TestScaleTables:
    """Each table entry against the prefix it names, not against its neighbours."""

    @pytest.mark.parametrize(
        ("value", "unit", "expected"),
        [(1.0, "C", 1e6), (1.0, "mC", 1e3), (1.0, "uC", 1.0), (1.0, "nC", 1e-3), (1.0, "pC", 1e-6)],
    )
    def test_charge(self, value: float, unit: str, expected: float) -> None:
        assert units.to_uC(value, unit) == pytest.approx(expected)

    @pytest.mark.parametrize(
        ("value", "unit", "expected"),
        [(1.0, "A", 1e6), (1.0, "mA", 1e3), (1.0, "uA", 1.0), (1.0, "nA", 1e-3)],
    )
    def test_current(self, value: float, unit: str, expected: float) -> None:
        assert units.to_uA(value, unit) == pytest.approx(expected)

    @pytest.mark.parametrize(
        ("value", "unit", "expected"),
        [(1.0, "s", 1e6), (1.0, "ms", 1e3), (1.0, "us", 1.0), (1.0, "ns", 1e-3)],
    )
    def test_time(self, value: float, unit: str, expected: float) -> None:
        assert units.to_us(value, unit) == pytest.approx(expected)

    @pytest.mark.parametrize(
        ("value", "unit", "expected"),
        [(1.0, "m", 1e6), (1.0, "cm", 1e4), (1.0, "mm", 1e3), (1.0, "um", 1.0), (1.0, "nm", 1e-3)],
    )
    def test_length(self, value: float, unit: str, expected: float) -> None:
        assert units.to_um(value, unit) == pytest.approx(expected)

    def test_areas_are_the_square_of_the_length_prefix(self) -> None:
        """The place a scale table is most often wrong: 1 mm = 0.1 cm, so 1 mm^2 = 0.01 cm^2."""
        assert units.to_cm2(1.0, "m2") == pytest.approx(100.0**2)
        assert units.to_cm2(1.0, "mm2") == pytest.approx(0.1**2)
        assert units.to_cm2(1.0, "um2") == pytest.approx(1e-4**2)
        assert units.to_cm2(1.0, "nm2") == pytest.approx(1e-7**2)
        assert units.to_cm2(1.0, "cm2") == 1.0

    def test_charge_density_carries_both_prefixes(self) -> None:
        # 1 uC/mm^2 spread over 1 cm^2 = 100 mm^2 is 100 uC per cm^2.
        assert units.to_uC_cm2(1.0, "uC/mm2") == pytest.approx(1.0 / 0.1**2)
        assert units.to_uC_cm2(1.0, "mC/mm2") == pytest.approx(1e3 / 0.1**2)
        assert units.to_uC_cm2(1.0, "C/cm2") == pytest.approx(1e6)
        assert units.to_uC_cm2(1.0, "mC/cm2") == pytest.approx(1e3)
        assert units.to_uC_cm2(1.0, "nC/cm2") == pytest.approx(1e-3)

    @pytest.mark.parametrize(
        ("func", "kind", "bad"),
        [
            (units.to_uC, "charge", "kC"),
            (units.to_uA, "current", "kA"),
            (units.to_us, "time", "min"),
            (units.to_um, "length", "inch"),
            (units.to_cm2, "area", "km2"),
            (units.to_uC_cm2, "charge density", "C/m2"),
        ],
    )
    def test_an_unknown_unit_is_a_named_error(self, func, kind: str, bad: str) -> None:
        with pytest.raises(ValueError, match=f"Unknown {kind} unit"):
            func(1.0, bad)


class TestConvenienceConversions:
    def test_square_micrometres_to_square_centimetres(self) -> None:
        # 1 cm = 1e4 um, so 1 cm^2 = 1e8 um^2.
        assert units.um2_to_cm2(1e4**2) == pytest.approx(1.0)
        assert units.um2_to_cm2(1.0) == pytest.approx(1.0 / 1e4**2)

    def test_square_centimetres_to_square_metres(self) -> None:
        # 1 m = 100 cm, so 1 m^2 = 1e4 cm^2.
        assert units.cm2_to_m2(100.0**2) == pytest.approx(1.0)

    def test_micrometres_to_metres(self) -> None:
        assert units.um_to_m(1e6) == pytest.approx(1.0)

    def test_millicoulomb_and_microcoulomb_densities(self) -> None:
        assert units.mC_cm2_to_uC_cm2(1.0) == pytest.approx(1e3)
        assert units.uC_cm2_to_mC_cm2(1.0) == pytest.approx(1e-3)

    def test_the_kelvin_offset_is_the_defined_one(self) -> None:
        assert units.KELVIN_OFFSET == 273.15
        assert units.celsius_to_kelvin(0.0) == pytest.approx(273.15)
        assert units.celsius_to_kelvin(37.0) == pytest.approx(310.15)
        assert units.kelvin_to_celsius(310.15) == pytest.approx(37.0)


class TestUnitConversionsElsewhereInThePackage:
    """The four mutation survivors of ledger 65, each pinned by magnitude.

    Every one of these lives outside ``units.py`` but is a unit conversion, and every one
    survived because its only test asserted a ratio or a sign.
    """

    def test_cic_max_current_is_a_charge_divided_by_a_time_in_seconds(self) -> None:
        """Mutant C4: dropping the us->s factor in ``charge.cic_max_current_uA``.

        A 10^6 error.  The identity below is dimensional, so it holds whatever the
        material's stored limit turns out to be after the provenance phase.
        """
        area_cm2 = 1e-3
        pulse_width_us = 200.0
        limit_uC_cm2 = get_material("Pt").cic_uC_cm2("conservative")

        # SI chain: Q[C] = limit[uC/cm^2] * 1e-6 * area[cm^2];  I[A] = Q[C] / W[s].
        charge_C = limit_uC_cm2 * 1e-6 * area_cm2
        expected_uA = (charge_C / (pulse_width_us * 1e-6)) * 1e6

        assert charge_mod.cic_max_current_uA("Pt", area_cm2, pulse_width_us) == pytest.approx(
            expected_uA
        )
        # And the magnitude is of the order a microelectrode actually runs at, not 1e-4.
        assert 1.0 < expected_uA < 1e4

    def test_activation_radius_is_reported_in_micrometres(self) -> None:
        """``r_mm = sqrt(excess / k)``, then mm -> um."""
        model = vta.CurrentDistanceModel(k_uA_per_mm2=1.0, threshold_offset_uA=0.0, verified=False)
        # 4 uA at 1 uA/mm^2 gives r^2 = 4 mm^2, r = 2 mm = 2000 um.
        assert model.activation_radius_um(4.0) == pytest.approx(2.0 * 1e3)

    def test_activated_volume_is_four_thirds_pi_r_cubed_in_cubic_millimetres(self) -> None:
        """Mutants M4 (4/3 -> 4) and M5 (um->mm 1e-3 -> 1e-6), both in one line.

        The only existing volume test asserts a ratio of two volumes, in which both
        constants cancel exactly.
        """
        model = vta.CurrentDistanceModel(k_uA_per_mm2=1.0, threshold_offset_uA=0.0, verified=False)
        radius_mm = 2.0  # from the test above: 4 uA at k = 1 uA/mm^2
        expected_mm3 = (4.0 / 3.0) * math.pi * radius_mm**3

        assert expected_mm3 == pytest.approx(33.510321638291124)
        assert model.activated_volume_mm3(4.0) == pytest.approx(expected_mm3)
        # Dropping the 4/3 trebles it; mistaking um->mm for um->m kills it by 1e9.
        assert model.activated_volume_mm3(4.0) != pytest.approx(4.0 * math.pi * radius_mm**3)

    def test_weiss_threshold_charge_is_microamps_times_microseconds(self) -> None:
        """Mutant M10: dropping the uA*us -> uC factor in ``weiss_threshold_charge_uC``.

        Its only test asserts ``np.diff(...) > 0`` --- a sign, not a magnitude.
        """
        rheobase_uA = 20.0
        chronaxie_us = 100.0
        pulse_width_us = 100.0

        # Q = I_rh * (W + t_c) = 20e-6 A * 200e-6 s = 4e-9 C = 0.004 uC.
        coulombs = (rheobase_uA * 1e-6) * ((pulse_width_us + chronaxie_us) * 1e-6)
        assert coulombs == pytest.approx(4e-9)

        result = sd.weiss_threshold_charge_uC(pulse_width_us, rheobase_uA, chronaxie_us)
        assert result == pytest.approx(coulombs * 1e6)
        assert result == pytest.approx(0.004)
        # Independently, through the package's own charge converter at the same inputs.
        assert result == pytest.approx(units.charge_uC(rheobase_uA, pulse_width_us + chronaxie_us))
