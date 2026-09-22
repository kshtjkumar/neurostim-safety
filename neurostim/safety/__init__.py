"""Electrochemical and tissue-damage safety checks.

Each submodule answers one question and can be used on its own:

- :mod:`~neurostim.safety.shannon` -- tissue damage, via the Shannon k criterion
- :mod:`~neurostim.safety.charge` -- electrode charge-injection capacity
- :mod:`~neurostim.safety.water_window` -- electrode potential excursion
- :mod:`~neurostim.safety.compliance` -- stimulator voltage headroom
- :mod:`~neurostim.safety.assessment` -- all of the above, aggregated

``StimProtocol`` is re-exported here because the 0.1.0 prototype defined it in
``neurostim.safety``; it now lives in :mod:`neurostim.protocol`.
"""

from ..protocol import StimProtocol
from . import charge, compliance, shannon, water_window
from .assessment import (
    CAUTION_MARGIN,
    CHECK_KINDS,
    LIMIT_BEARING,
    Check,
    CheckKind,
    SafetyAssessment,
    SafetyCalculator,
    Status,
)
from .charge import ChargeResult, charge_density_uC_cm2, cic_max_charge_uC, cic_max_current_uA
from .compliance import ComplianceResult
from .shannon import (
    K_CONSERVATIVE,
    K_DEFAULT,
    K_MODERATE,
    K_PERMISSIVE,
    ShannonResult,
    shannon_k,
    shannon_max_charge_uC,
    shannon_max_current_uA,
)
from .water_window import (
    DOUBLE_LAYER_CAPACITANCE_uF_cm2,
    WaterWindowResult,
    max_charge_density_in_window_uC_cm2,
    polarisation_V,
    validate_resting_potential_V,
)

__all__ = [
    "CAUTION_MARGIN",
    "CHECK_KINDS",
    "K_CONSERVATIVE",
    "K_DEFAULT",
    "K_MODERATE",
    "K_PERMISSIVE",
    "LIMIT_BEARING",
    "ChargeResult",
    "Check",
    "CheckKind",
    "ComplianceResult",
    "DOUBLE_LAYER_CAPACITANCE_uF_cm2",
    "SafetyAssessment",
    "SafetyCalculator",
    "ShannonResult",
    "Status",
    "StimProtocol",
    "WaterWindowResult",
    "charge",
    "charge_density_uC_cm2",
    "cic_max_charge_uC",
    "cic_max_current_uA",
    "compliance",
    "max_charge_density_in_window_uC_cm2",
    "polarisation_V",
    "shannon",
    "shannon_k",
    "shannon_max_charge_uC",
    "shannon_max_current_uA",
    "validate_resting_potential_V",
    "water_window",
]
