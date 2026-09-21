"""Physical models built on top of the safety calculation.

Unlike :mod:`neurostim.safety`, whose limits come from published empirical criteria,
these modules are analytic approximations. Each carries its validity range in its own
docstring, and the two weakest -- :mod:`~neurostim.models.thermal` and
:mod:`~neurostim.models.vta` -- say so explicitly at the top.
"""

from . import field, strength_duration, thermal, vta
from .field import (
    BLOOD_CONDUCTIVITY_S_PER_M,
    BRAIN_CONDUCTIVITY_S_PER_M,
    GREY_MATTER_CONDUCTIVITY_S_PER_M,
    WHITE_MATTER_CONDUCTIVITY_S_PER_M,
    FieldProfile,
    array_potential_V,
    field_V_per_m,
    potential_V,
    radial_profile,
)
from .strength_duration import (
    StrengthDurationFit,
    chronaxie_from_tau_us,
    fit_lapicque,
    fit_weiss,
    lapicque_threshold_uA,
    weiss_threshold_charge_uC,
    weiss_threshold_uA,
)
from .thermal import (
    BRAIN,
    ELWASSIF_BRAIN,
    GREY_MATTER,
    WHITE_MATTER,
    WHOLE_BRAIN,
    ThermalResult,
    TissueThermalProperties,
    peak_temperature_rise_K,
    pennes_steady_state_sphere,
    pennes_transient_sphere,
    perfusion_per_s,
    voltage_driven_power_W,
)
from .vta import CurrentDistanceModel, VTAResult, fit_current_distance

__all__ = [
    "BLOOD_CONDUCTIVITY_S_PER_M",
    "BRAIN",
    "BRAIN_CONDUCTIVITY_S_PER_M",
    "ELWASSIF_BRAIN",
    "GREY_MATTER",
    "GREY_MATTER_CONDUCTIVITY_S_PER_M",
    "WHITE_MATTER",
    "WHITE_MATTER_CONDUCTIVITY_S_PER_M",
    "WHOLE_BRAIN",
    "CurrentDistanceModel",
    "FieldProfile",
    "StrengthDurationFit",
    "ThermalResult",
    "TissueThermalProperties",
    "VTAResult",
    "array_potential_V",
    "chronaxie_from_tau_us",
    "field",
    "field_V_per_m",
    "fit_current_distance",
    "fit_lapicque",
    "fit_weiss",
    "lapicque_threshold_uA",
    "peak_temperature_rise_K",
    "pennes_steady_state_sphere",
    "pennes_transient_sphere",
    "perfusion_per_s",
    "potential_V",
    "radial_profile",
    "strength_duration",
    "thermal",
    "voltage_driven_power_W",
    "vta",
    "weiss_threshold_charge_uC",
    "weiss_threshold_uA",
]
