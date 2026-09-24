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
            "reference": "rose_robblee1990", "verified": False, "inherited_from": None,
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


class TestAUserMeasurementInheritsOnlyWhatItSays:
    """Ledger 25, by user decision option (c). ``with_measured_cic`` replaced only the CIC,
    so the base material's water window, chronic threshold and note survived and were
    presented as the user material's own: "[PASS] Chronic degradation: ... below the 20
    uC/cm^2 platinum dissolution threshold (platinum dissolution, rose_robblee1990)".

    Dropping them would satisfy the letter of the plan's first test ("absence of
    rose_robblee1990") but remove the platinum dissolution limit, the less conservative
    direction. So they are kept by default, labelled as inherited, and never presented as
    the user material's own. Keyword arguments replace or drop each one, and a drop is
    recorded where the limit goes missing.
    """

    PROTOCOL = StimProtocol(80.0, 200.0, 130.0, 1.0)
    LABEL = "not measured on this electrode"

    def _assess(self, material):
        return SafetyCalculator(DiscElectrode(100.0, "Pt"), self.PROTOCOL, material=material).assess()

    def test_by_default_the_published_limits_stay_in_force_labelled_inherited(self):
        user = with_measured_cic(get_material("Pt"), 100.0)
        assert user.chronic_threshold.reference == "rose_robblee1990"
        assert user.chronic_threshold.inherited_from == "Platinum"
        assert user.water_window.inherited_from == "Platinum"
        assert user.chronic_threshold.verified is True  # the label carries the caveat
        assert (
            "published for Platinum (rose_robblee1990), not measured on this electrode"
            in user.chronic_threshold.describe()
        )
        assert (
            "published for Platinum (cogan2008), not measured on this electrode"
            in user.water_window.describe()
        )
        assert user.note.startswith("User-measured charge-injection limit on Platinum")

        chronic = next(
            c for c in self._assess(user).checks if c.name == "Chronic degradation"
        )
        assert chronic.status.value != "NOT_EVALUATED"  # the Pt dissolution limit applies
        assert self.LABEL in chronic.summary

    def test_a_published_reference_is_never_presented_as_the_users_own(self):
        """Every line of every render that names an inherited reference carries the label."""
        import json

        from neurostim.io.report import _provenance_rows
        from neurostim.io.tabular import report_to_json

        user = with_measured_cic(get_material("Pt"), 100.0)
        calc = SafetyCalculator(DiscElectrode(100.0, "Pt"), self.PROTOCOL, material=user)
        assessment = calc.assess()
        texts = assessment.describe().splitlines()
        texts += [f"{k}: {v}" for k, v in _provenance_rows(calc, assessment)]
        texts += [c.summary for c in assessment.checks]
        named = [line for line in texts if "rose_robblee1990" in line or "cogan2008" in line]
        assert named, "the premise: the inherited references are rendered"
        assert all(self.LABEL in line for line in named), [
            line for line in named if self.LABEL not in line
        ]
        provenance = json.loads(report_to_json(calc))["provenance"]
        assert provenance["chronic_threshold"]["inherited_from"] == "Platinum"
        assert provenance["water_window"]["inherited_from"] == "Platinum"
        assert provenance["cic"]["inherited_from"] is None

    def test_a_replaced_constant_is_the_users_and_cites_the_user(self):
        user = with_measured_cic(
            get_material("Pt"), 100.0, chronic_threshold=(10.0, 30.0),
            water_window=(-0.5, 0.7),
        )
        assert user.chronic_threshold.reference == "user_measurement"
        assert user.chronic_threshold.verified is False
        assert user.chronic_threshold.inherited_from == ""
        assert (user.chronic_threshold.low_uC_cm2, user.chronic_threshold.high_uC_cm2) == (10.0, 30.0)
        assert user.water_window.reference == "user_measurement"
        assert (user.water_window.cathodic_V, user.water_window.anodic_V) == (-0.5, 0.7)
        assert "rose_robblee1990" not in user.chronic_threshold.describe()
        chronic = next(
            c for c in self._assess(user).checks if c.name == "Chronic degradation"
        )
        # 80 uA x 200 us on a 100 um disc is 203.7 uC/cm^2, past the user's 30.
        assert chronic.status.value == "FAIL"
        assert "30 uC/cm^2" in chronic.summary

    @pytest.mark.parametrize(
        ("keyword", "check", "phrase"),
        [
            ("chronic_threshold", "Chronic degradation", "chronic threshold"),
            ("water_window", "Water window", "water window"),
        ],
    )
    def test_a_dropped_constant_is_recorded_where_the_limit_goes_missing(
        self, keyword, check, phrase
    ):
        user = with_measured_cic(get_material("Pt"), 100.0, **{keyword: None})
        assert getattr(user, keyword) is None
        assessment = self._assess(user)
        result = next(c for c in assessment.checks if c.name == check)
        assert result.status.value == "NOT_EVALUATED"
        assert f"{phrase} was dropped" in result.summary
        assert assessment.limits_incomplete is True
        assert check in assessment.limits_incomplete_note()
        assert f"{phrase} was dropped" in assessment.limits_incomplete_note()

    def test_no_shipped_constant_is_marked_inherited(self):
        for material in MATERIALS.values():
            assert material.dropped == ()
            for constant in (material.water_window, material.chronic_threshold):
                if constant is not None:
                    assert constant.inherited_from == "", material.key


class TestTheWindowSeedReadsTheWindowItIsGiven:
    """Ledger 150, found at C4.1b. The water-window seed looked the material up by key
    (``max_charge_density_in_window_uC_cm2(result.material_key, ...)``), so a Material
    instance with its own window -- ``replace(Pt, water_window=...)``, or since C4.1b
    ``with_measured_cic(..., water_window=(c, a))`` -- was seeded from the shipped window,
    far from its own boundary, and ``assess()`` raised ``LimitDidNotSettle``."""

    @pytest.mark.parametrize("window", [(-0.5, 0.7), (-0.3, 0.9), (-0.9, 0.2)])
    @pytest.mark.parametrize("anodic_first", [False, True])
    def test_a_material_with_its_own_window_assesses_on_its_boundary(self, window, anodic_first):
        from neurostim.materials import WaterWindow
        from neurostim.safety import assessment as assessment_mod

        material = replace(
            get_material("Pt"), water_window=WaterWindow(*window, reference="cogan2008")
        )
        calc = SafetyCalculator(
            DiscElectrode(100.0, "Pt"),
            StimProtocol(80.0, 200.0, 130.0, 1.0, anodic_first=anodic_first),
            material=material,
        )
        assessment = calc.assess()
        ceiling = next(c for c in assessment.checks if c.name == "Water window").ceiling_uA
        search = assessment_mod._water_window_search(
            assessment.water_window, calc.p, calc.e.area_cm2
        )
        assert search.passes(ceiling)
        assert not search.passes(math.nextafter(ceiling, math.inf))
