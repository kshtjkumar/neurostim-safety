"""neurostim -- electrode safety and stimulation modelling for neural interfaces.

Quick start
-----------
>>> from neurostim import RingElectrode, StimProtocol, SafetyCalculator
>>> electrode = RingElectrode(330, 270, "SS")
>>> protocol = StimProtocol(80, 200, 130, 1)
>>> calc = SafetyCalculator(electrode, protocol)
>>> print(calc.describe())          # doctest: +SKIP

What this package is
--------------------
A transparent implementation of the standard electrode safety criteria, with every
literature-derived constant carrying its primary source and its measurement conditions
(see :mod:`neurostim.references` and :mod:`neurostim.materials`).

What it is not
--------------
It is **not validated for clinical or regulatory use**. The tissue-damage criterion is
an empirical separatrix through animal histology; the thermal and activation models are
analytic approximations with narrow validity ranges, documented per module. Values that
could not be confirmed against a primary source are flagged ``PROVISIONAL`` wherever
they surface.
"""

from . import audit, sensitivity, transient
from .electrodes import ElectrodePreset, electrode, get_preset, list_presets
from .geometry import (
    ArraySite,
    CylindricalBandElectrode,
    DiscElectrode,
    Electrode,
    ElectrodeArray,
    HemisphericalElectrode,
    MicrowireElectrode,
    RectangularElectrode,
    RingElectrode,
    SphericalElectrode,
    grid_array,
    linear_array,
)
from .materials import (
    MATERIALS,
    Material,
    MeasuredRange,
    WaterWindow,
    get_material,
    list_materials,
    with_measured_cic,
)
from .protocol import StimProtocol
from .references import REFERENCES, Reference, bibliography, cite
from .safety import SafetyAssessment, SafetyCalculator, Status
from .uncertainty import Interval

__version__ = "0.16.0"

__all__ = [
    "MATERIALS",
    "REFERENCES",
    "ArraySite",
    "CylindricalBandElectrode",
    "DiscElectrode",
    "Electrode",
    "ElectrodeArray",
    "ElectrodePreset",
    "HemisphericalElectrode",
    "Interval",
    "Material",
    "MeasuredRange",
    "MicrowireElectrode",
    "RectangularElectrode",
    "Reference",
    "RingElectrode",
    "SafetyAssessment",
    "SafetyCalculator",
    "SphericalElectrode",
    "Status",
    "StimProtocol",
    "WaterWindow",
    "__version__",
    "audit",
    "bibliography",
    "cite",
    "electrode",
    "get_material",
    "get_preset",
    "grid_array",
    "linear_array",
    "list_materials",
    "list_presets",
    "sensitivity",
    "transient",
    "with_measured_cic",
]
