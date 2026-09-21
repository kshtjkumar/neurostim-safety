"""Activation radius and volume of tissue activated (VTA), by the current-distance rule.

The model
---------
Stoney et al. (1968) established that the current needed to excite a neuron rises with
the square of its distance from the electrode:

.. math::

    I_{th}(r) = I_0 + k\\,r^{2}

Inverting for the radius activated by a given current gives

.. math::

    r(I) = \\sqrt{\\frac{I - I_0}{k}}, \\qquad
    V_{activated} = \\frac{4}{3}\\pi r^{3}

so the activated volume grows as ``(I - I_0)^{3/2}``.

Read this before using it
-------------------------
This is the weakest model in the package and it is included because the alternative --
people estimating activation radius by eye -- is worse. Its limitations are structural,
not fixable by better parameters:

- **``k`` is not a constant.** It is an excitability coefficient for a particular neural
  element. Reported values span 300 to 27 000 uA/mm^2 -- a factor of ninety -- rising as
  axons get smaller and less myelinated. The default here is the 1292 uA/mm^2 mean for
  pyramidal tract neurons (Stoney et al. 1968 via Tehovnik et al. 2006), which is the
  right value only if that is what you are activating.
- **A sphere is the wrong shape.** Real activation follows axon trajectories and
  fibre orientation, not isopotential shells. Activation of passing fibres can extend
  much further along a tract than perpendicular to it.
- **It says nothing about what is activated.** Cell bodies, local axons and passing
  fibres have different thresholds, and their relative order can invert with pulse
  width.

Treat the output as an order-of-magnitude scale, and prefer a coupled finite element
plus cable model whenever the answer matters. :mod:`neurostim.io.fem` exists to bring
such a solution in.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

STONEY_K_uA_PER_MM2 = 1292.0
"""Mean current-distance constant for pyramidal tract neurons.

Stoney et al. (1968), 12 cells in cat motor cortex, antidromically identified, activated
50 % of the time by a single 0.2 ms cathodal pulse. Reported via Tehovnik et al. (2006)
figure 1A, which states the average K and its spread directly.
"""

STONEY_K_SE_RANGE_uA_PER_MM2 = (1037.0, 1547.0)
"""One standard error either side of the Stoney mean, from Tehovnik et al. figure 1A."""

K_RANGE_BY_ELEMENT_uA_PER_MM2 = (300.0, 27000.0)
"""Full reported span of the excitability constant across cortical elements.

300 uA/mm^2 for the largest myelinated cortical neurons up to 27 000 uA/mm^2 for the
smallest unmyelinated ones -- a factor of ninety. K is inversely related to axon
diameter and to whether the axon is myelinated, so the constant encodes *which* element
is being activated, not a property of the tissue. This span, not the mean, is the honest
uncertainty on any activation-radius estimate where the target element is unknown.
"""

MT_BEHAVIOURAL_K_uA_PER_MM2 = 2000.0
"""Behavioural estimate in area MT: 20 uA confined to a 0.2 mm directional column.

Tehovnik et al. (2006) compute this as K = 20 uA / (0.1 mm)^2. An independent method
landing within a factor of two of the Stoney single-cell value.
"""

PYRAMIDAL_CHRONAXIE_RANGE_MS = (0.1, 0.4)
"""Chronaxies of pyramidal tract neurons (Tehovnik et al. 2006 figure 1B)."""

AXON_CHRONAXIE_RANGE_MS = (0.03, 7.0)
"""Axon chronaxies. Cell bodies are far slower at 7-31 ms, so a short pulse
preferentially recruits axons -- which is why microstimulation activates fibres of
passage rather than the somata beneath the electrode."""

CELL_BODY_CHRONAXIE_RANGE_MS = (7.0, 31.0)
"""Cell-body chronaxies (Nowak & Bullier 1998; Ranck 1975, via Tehovnik et al. 2006)."""

TEHOVNIK_K_uA_PER_MM2 = STONEY_K_uA_PER_MM2
"""Deprecated alias. In 0.3.x this held 675 uA/mm^2, taken from a secondary summary;
the primary sources give 1292 uA/mm^2 for the pyramidal tract case. The old value
underestimated threshold roughly twofold and so overestimated activation radius by
about 1.4x."""


@dataclass(frozen=True)
class CurrentDistanceModel:
    """A current-distance relationship ``I_th = I_0 + k r^2``.

    Parameters
    ----------
    k_uA_per_mm2:
        The distance coefficient.
    threshold_offset_uA:
        ``I_0``, the current at zero distance. Often taken as zero.
    verified:
        Whether ``k`` was confirmed against a primary source.
    """

    k_uA_per_mm2: float = STONEY_K_uA_PER_MM2
    threshold_offset_uA: float = 0.0
    verified: bool = True
    source: str = "stoney1968"
    note: str = (
        "pyramidal tract neurons, cat motor cortex, 0.2 ms cathodal, 50 % activation; "
        "mean of 12 cells, SE 1037-1547 uA/mm^2"
    )

    def __post_init__(self) -> None:
        if not math.isfinite(self.k_uA_per_mm2) or self.k_uA_per_mm2 <= 0:
            raise ValueError(
                f"k_uA_per_mm2 must be finite and > 0, got {self.k_uA_per_mm2!r}"
            )
        if not math.isfinite(self.threshold_offset_uA) or self.threshold_offset_uA < 0:
            raise ValueError(
                f"threshold_offset_uA must be finite and >= 0, "
                f"got {self.threshold_offset_uA!r}"
            )

    def threshold_uA(self, distance_um: float | np.ndarray) -> float | np.ndarray:
        """Current required to activate a neuron at the given distance."""
        r_mm = np.asarray(distance_um, dtype=float) * 1e-3
        if np.any(r_mm < 0):
            raise ValueError("distance_um must be >= 0")
        result = self.threshold_offset_uA + self.k_uA_per_mm2 * r_mm**2
        return float(result) if np.isscalar(distance_um) else result

    def activation_radius_um(self, current_uA: float | np.ndarray) -> float | np.ndarray:
        """Radius activated by a given current. Zero below the offset threshold."""
        i = np.asarray(current_uA, dtype=float)
        if np.any(i < 0):
            raise ValueError("current_uA must be >= 0")
        excess = np.maximum(i - self.threshold_offset_uA, 0.0)
        r_mm = np.sqrt(excess / self.k_uA_per_mm2)
        result = r_mm * 1e3
        return float(result) if np.isscalar(current_uA) else result

    def activated_volume_mm3(self, current_uA: float | np.ndarray):
        """Spherical volume enclosed by :meth:`activation_radius_um`, in mm^3."""
        r_mm = np.asarray(self.activation_radius_um(current_uA), dtype=float) * 1e-3
        result = (4.0 / 3.0) * math.pi * r_mm**3
        return float(result) if np.isscalar(current_uA) else result

    def describe(self) -> str:
        """Multi-line summary."""
        lines = [
            f"Current-distance model: I_th = {self.threshold_offset_uA:g} + "
            f"{self.k_uA_per_mm2:g} * r^2  (uA, r in mm)",
            f"  source: {self.source} -- {self.note}",
        ]
        if not self.verified:
            lines.append("  PROVISIONAL: k not confirmed against a primary source")
        return "\n".join(lines)


def fit_current_distance(
    distances_um: np.ndarray,
    thresholds_uA: np.ndarray,
    *,
    fit_offset: bool = True,
) -> CurrentDistanceModel:
    """Fit ``I_th = I_0 + k r^2`` to measured thresholds by linear least squares.

    Linear in ``r^2``, so no iteration is needed. Fitting your own ``k`` on your own
    preparation is strongly preferable to using the literature default.
    """
    r = np.asarray(distances_um, dtype=float)
    i = np.asarray(thresholds_uA, dtype=float)
    if r.shape != i.shape:
        raise ValueError(
            f"distances_um and thresholds_uA must have the same shape, "
            f"got {r.shape} and {i.shape}"
        )
    min_points = 2 if fit_offset else 1
    if r.size < min_points:
        raise ValueError(f"need at least {min_points} points to fit")
    if np.any(r < 0) or np.any(i <= 0):
        raise ValueError("distances must be >= 0 and thresholds > 0")

    r2_mm2 = (r * 1e-3) ** 2
    if fit_offset:
        slope, intercept = np.polyfit(r2_mm2, i, 1)
        offset = max(float(intercept), 0.0)
    else:
        slope = float(np.sum(r2_mm2 * i) / np.sum(r2_mm2**2))
        offset = 0.0
    if slope <= 0:
        raise ValueError(
            "fitted k is non-positive; thresholds do not increase with distance "
            "in these data"
        )

    return CurrentDistanceModel(
        k_uA_per_mm2=float(slope),
        threshold_offset_uA=offset,
        verified=False,
        source="user data",
        note=f"least-squares fit to {r.size} measured thresholds",
    )


@dataclass(frozen=True)
class VTAResult:
    """Activation estimate for one protocol."""

    current_uA: float
    radius_um: float
    volume_mm3: float
    model: CurrentDistanceModel
    electrode_radius_um: float | None = None

    @property
    def radius_exceeds_electrode(self) -> bool:
        """Whether the activated radius is outside the electrode itself.

        When it is not, the estimate is meaningless: the model places the entire
        activated region inside the metal.
        """
        if self.electrode_radius_um is None:
            return True
        return self.radius_um > self.electrode_radius_um

    def describe(self) -> str:
        """Multi-line summary."""
        lines = [
            f"Activation estimate at {self.current_uA:g} uA",
            f"  radius  {self.radius_um:.1f} um",
            f"  volume  {self.volume_mm3:.4g} mm^3",
            self.model.describe(),
        ]
        if not self.radius_exceeds_electrode:
            lines.append(
                f"  WARNING: activation radius is smaller than the electrode radius "
                f"({self.electrode_radius_um:.1f} um); the estimate is not meaningful "
                f"at this current"
            )
        return "\n".join(lines)


def evaluate(
    current_uA: float,
    model: CurrentDistanceModel | None = None,
    *,
    electrode_radius_um: float | None = None,
) -> VTAResult:
    """Estimate activation radius and volume for a stimulation current."""
    m = model if model is not None else CurrentDistanceModel()
    radius = float(m.activation_radius_um(current_uA))
    return VTAResult(
        current_uA=current_uA,
        radius_um=radius,
        volume_mm3=float(m.activated_volume_mm3(current_uA)),
        model=m,
        electrode_radius_um=electrode_radius_um,
    )
