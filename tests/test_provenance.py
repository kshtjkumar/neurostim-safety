"""Phase 4 -- provenance: every constant says where it came from, and whether it is confirmed.

The package's claim is traceable provenance. These tests pin the places where a constant's
origin or its verified flag was lost on the way to a result or a report.
"""

from __future__ import annotations

import math
from dataclasses import replace

import pytest

from neurostim import DiscElectrode, SafetyCalculator, StimProtocol, get_material
from neurostim.materials import MATERIALS, ChronicThreshold, MeasuredRange, with_measured_cic


class TestAMeasuredRangeRefusesBoundsThatAreNotNumbers:
    """Ledger 24. ``if self.high < self.low`` is False for NaN, so a NaN bound constructed,
    and ``with_measured_cic(Pt, 100, high=nan).cic_uC_cm2("optimistic")`` returned nan;
    ``high=inf`` returned inf; ``MeasuredRange(-5, 1).value("conservative")`` returned -5."""

    @pytest.mark.parametrize(
        ("low", "high"),
        [(1.0, math.nan), (math.nan, 1.0), (1.0, math.inf), (-5.0, 1.0), (0.0, 1.0)],
    )
    def test_a_bound_that_is_not_a_positive_finite_number_raises(self, low, high):
        with pytest.raises(ValueError, match="MeasuredRange"):
            MeasuredRange(low=low, high=high, units="uC/cm2", reference="user_measurement")

    @pytest.mark.parametrize("high", [math.nan, math.inf, -1.0])
    def test_with_measured_cic_checks_its_high_end_too(self, high):
        with pytest.raises(ValueError):
            with_measured_cic(get_material("Pt"), 100.0, high)

    @pytest.mark.parametrize(
        ("low", "high"), [(1.0, math.nan), (math.nan, 1.0), (1.0, math.inf), (-1.0, 1.0)]
    )
    def test_a_chronic_threshold_refuses_them_too(self, low, high):
        with pytest.raises(ValueError, match="ChronicThreshold"):
            ChronicThreshold(low, high, mechanism="x", reference="rose_robblee1990")

    def test_every_shipped_material_still_constructs(self):
        """The premise: no shipped range is non-finite or non-positive."""
        assert len(MATERIALS) == 9


class TestAChronicThresholdCarriesItsOwnVerifiedFlag:
    """Ledger 30. ``Material.verified`` rolled up the CIC and the water window but not the
    chronic threshold, which had no ``verified`` field at all. The flag now exists, rolls
    into ``Material.verified``, and reaches ``describe()``, the JSON and the PDF's
    provenance rows."""

    @staticmethod
    def _pt_with_unverified_threshold():
        pt = get_material("Pt")
        assert pt.verified and pt.chronic_threshold is not None  # the premise
        return replace(
            pt, chronic_threshold=replace(pt.chronic_threshold, verified=False)
        )

    def test_it_rolls_into_the_material(self):
        assert self._pt_with_unverified_threshold().verified is False

    def test_every_shipped_threshold_is_verified(self):
        for material in MATERIALS.values():
            if material.chronic_threshold is not None:
                assert material.chronic_threshold.verified is True, material.key
            assert material.verified is True, material.key

    def test_describe_says_provisional(self):
        threshold = self._pt_with_unverified_threshold().chronic_threshold
        assert "PROVISIONAL" in threshold.describe()
        assert "PROVISIONAL" not in get_material("Pt").chronic_threshold.describe()

    def test_the_json_carries_each_constants_reference_and_flag(self):
        import json

        from neurostim.io.tabular import report_to_json

        protocol = StimProtocol(80.0, 200.0, 130.0, 1.0)
        payload = json.loads(
            report_to_json(
                SafetyCalculator(
                    DiscElectrode(100.0, "Pt"), protocol,
                    material=self._pt_with_unverified_threshold(),
                )
            )
        )
        provenance = payload["provenance"]
        assert provenance["material_verified"] is False
        assert provenance["chronic_threshold"] == {
            "reference": "rose_robblee1990", "verified": False,
        }
        assert provenance["cic"]["verified"] is True
        clean = json.loads(
            report_to_json(SafetyCalculator(DiscElectrode(100.0, "Pt"), protocol))
        )["provenance"]
        assert clean["material_verified"] is True
        assert clean["chronic_threshold"]["verified"] is True

    def test_the_pdf_provenance_rows_include_the_threshold(self):
        from neurostim.io.report import _provenance_rows

        protocol = StimProtocol(80.0, 200.0, 130.0, 1.0)
        calc = SafetyCalculator(
            DiscElectrode(100.0, "Pt"), protocol, material=self._pt_with_unverified_threshold()
        )
        rows = dict(_provenance_rows(calc, calc.assess()))
        assert "rose_robblee1990" in rows["Chronic degradation threshold"]
        assert "PROVISIONAL" in rows["Chronic degradation threshold"]
        clean = SafetyCalculator(DiscElectrode(100.0, "Pt"), protocol)
        clean_rows = dict(_provenance_rows(clean, clean.assess()))
        assert "PROVISIONAL" not in clean_rows["Chronic degradation threshold"]
        titanium = SafetyCalculator(DiscElectrode(100.0, "TiN"), protocol)
        assert "no chronic threshold on record" in dict(
            _provenance_rows(titanium, titanium.assess())
        )["Chronic degradation threshold"]
