"""Tissue heating from a stimulating electrode, via the Pennes bioheat equation.

The equation
------------
Pennes (1948) models perfused tissue as a conducting solid with a distributed heat sink
proportional to the local temperature rise above arterial blood:

.. math::

    \\rho c \\frac{\\partial T}{\\partial t}
    = \\nabla\\!\\cdot\\!(\\kappa \\nabla T)
      + w_b \\rho_b c_b (T_a - T) + Q_m + Q_{ext}

Writing ``T' = T - T_a`` and ``W = w_b \\rho_b c_b`` (the volumetric perfusion
conductance, W m^-3 K^-1), the steady state with the metabolic term absorbed into the
baseline is ``\\kappa \\nabla^2 T' = W T'``.

Analytic solution used here
---------------------------
For spherical symmetry the radial equation ``(1/r^2) d/dr(r^2 dT'/dr) = T'/L^2`` with
``L = sqrt(kappa / W)`` has the decaying solution ``T' = (A/r) e^{-r/L}``. Requiring
that the total power ``P`` crosses the sphere of radius ``a`` fixes ``A`` and gives

.. math::

    \\Delta T(r) = \\frac{P\\, e^{-(r-a)/L}}{4\\pi \\kappa r \\,(1 + a/L)},
    \\qquad
    \\Delta T(a) = \\frac{P}{4\\pi \\kappa a \\,(1 + a/L)}

As ``L \\to \\infty`` (no perfusion) this reduces to the classical unperfused result
``P / (4\\pi \\kappa a)``, which is the check :func:`pennes_steady_state_sphere` is
tested against.

Heat source
-----------
The source is ohmic dissipation in the tissue spreading resistance,
``P = I_{rms}^2 R_{access}``, using the RMS current of the pulse train. Joule heating
scales with the square of current, so the duty-cycled RMS value -- not the peak pulse
amplitude and not the time-average current -- is the correct quantity.

Validation against a finite element model
-----------------------------------------
Elwassif et al. (2006) solve the same equation by finite elements around a real
Medtronic DBS lead and sweep one parameter at a time. Comparing their Table I against
the analytic solution here (see :mod:`neurostim.data.elwassif2006`):

- peak rise **linear in electrical conductivity** -- matches to 0.7 % over four points
- peak rise **inversely proportional to thermal conductivity** -- matches to 0.9 %
- **perfusion attenuation** ``1/(1 + a/L)`` -- within 7-8 % over three points

The residual on perfusion is expected: they energise two adjacent contacts on a
thermally insulated shaft, which concentrates heat relative to an isolated sphere.

Their headline figure of "up to 0.8 K" is a **worst case**: highest tissue conductivity
in their sweep, lowest thermal conductivity, and *zero* perfusion, driven by a
continuous 1.56 V RMS bipolar setting dissipating about 7.5 mW. A duty-cycled
current-controlled monopolar protocol at 3 mA, 60 us, 130 Hz dissipates roughly 70 uW --
about a hundredth of the power -- and produces a rise of order millikelvin. Both figures
are correct; they describe different protocols. **Compare power, not amplitude.**

Known limits of this model, stated plainly
------------------------------------------
- **Steady state and spherical.** Transient behaviour is available separately via
  :func:`pennes_transient_sphere`, but the geometry is still a sphere.
- **No electrode or lead self-heating.** Resistive dissipation inside the metal and the
  thermal mass of the lead are not modelled. Elwassif et al. found lead geometry to
  matter: their 3387 lead runs about 0.2 K cooler than the 3389 at matched settings
  purely because its contacts are spaced further apart.
- **No encapsulation layer.** Chronic implants develop a sheath with different thermal
  and electrical properties from bulk tissue.
- **Single source.** Multiple energised contacts superpose; this models one.
- **Metabolic heat excluded from the rise.** ``Q_m`` shifts the resting temperature
  relative to arterial blood, not the stimulation-induced increment computed here.
  Elwassif et al. likewise set ``Q_m = 0``.
"""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass, field, replace

import numpy as np

BODY_TEMPERATURE_C = 37.0
"""Arterial blood temperature used as the baseline."""


def perfusion_per_s(
    ml_per_min_per_kg: float, tissue_density_kg_per_m3: float
) -> float:
    """Convert a perfusion rate from ml/min/kg to the volumetric rate ``w_b`` in 1/s.

    The IT'IS database tabulates perfusion as a *mass*-specific volume flow
    (ml of blood per minute per kg of tissue). The Pennes equation needs a *volume*
    -specific rate, so the conversion is

    ``w_b [1/s] = (ml/min/kg) * (1e-6 m^3/ml) / (60 s/min) * rho_tissue [kg/m^3]``

    Getting this conversion wrong by the tissue density is a factor of about 1000 and
    is the most likely error when transcribing perfusion values by hand.
    """
    if ml_per_min_per_kg < 0:
        raise ValueError(
            f"perfusion must be >= 0 ml/min/kg, got {ml_per_min_per_kg!r}"
        )
    if tissue_density_kg_per_m3 <= 0:
        raise ValueError(
            f"tissue density must be > 0, got {tissue_density_kg_per_m3!r}"
        )
    return ml_per_min_per_kg * 1e-6 / 60.0 * tissue_density_kg_per_m3


@dataclass(frozen=True)
class TissueThermalProperties:
    """Thermal and perfusion properties of the surrounding tissue.

    Defaults are IT'IS Database v4.2 grey-matter values. Every one is an aggregate over
    the primary literature with a standard deviation and sample size, recorded in
    :attr:`uncertainty` so that a spread can be propagated rather than a bare mean
    quoted. ``verified_fields`` lists the entries backed by a source in this package's
    bibliography; anything absent from it is reported as PROVISIONAL.
    """

    thermal_conductivity_W_per_mK: float = 0.547
    density_kg_per_m3: float = 1044.5
    specific_heat_J_per_kgK: float = 3695.8
    perfusion_rate_per_s: float = 0.013294
    blood_density_kg_per_m3: float = 1049.75
    blood_specific_heat_J_per_kgK: float = 3617.0
    metabolic_heat_W_per_m3: float = 16230.0
    arterial_temperature_C: float = BODY_TEMPERATURE_C
    verified_fields: tuple[str, ...] = (
        "thermal_conductivity_W_per_mK",
        "density_kg_per_m3",
        "specific_heat_J_per_kgK",
        "perfusion_rate_per_s",
        "blood_density_kg_per_m3",
        "blood_specific_heat_J_per_kgK",
        "metabolic_heat_W_per_m3",
    )
    source: str = "itis2025"
    tissue_name: str = "Brain (Grey Matter)"
    uncertainty: dict[str, tuple[float, int]] = field(
        default_factory=lambda: {
            # field name -> (standard deviation, sample size) from IT'IS v4.2
            "thermal_conductivity_W_per_mK": (0.02546, 2),
            "density_kg_per_m3": (7.778, 9),
            "specific_heat_J_per_kgK": (34.43, 5),
            "perfusion_rate_per_s": (0.001491, 3),
            "blood_density_kg_per_m3": (19.17, 584),
            "blood_specific_heat_J_per_kgK": (301.4, 3),
        }
    )

    def __post_init__(self) -> None:
        positives = {
            "thermal_conductivity_W_per_mK": self.thermal_conductivity_W_per_mK,
            "density_kg_per_m3": self.density_kg_per_m3,
            "specific_heat_J_per_kgK": self.specific_heat_J_per_kgK,
            "blood_density_kg_per_m3": self.blood_density_kg_per_m3,
            "blood_specific_heat_J_per_kgK": self.blood_specific_heat_J_per_kgK,
        }
        for name, value in positives.items():
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and > 0, got {value!r}")
        if not math.isfinite(self.perfusion_rate_per_s) or self.perfusion_rate_per_s < 0:
            raise ValueError(
                f"perfusion_rate_per_s must be finite and >= 0, "
                f"got {self.perfusion_rate_per_s!r}"
            )

    @property
    def perfusion_conductance_W_per_m3K(self) -> float:
        """``W = w_b * rho_b * c_b``, the volumetric perfusion heat-sink coefficient."""
        return (
            self.perfusion_rate_per_s
            * self.blood_density_kg_per_m3
            * self.blood_specific_heat_J_per_kgK
        )

    @property
    def thermal_penetration_depth_m(self) -> float:
        """``L = sqrt(kappa / W)``, the length over which a rise decays e-fold.

        Infinite when perfusion is zero, in which case the temperature field falls off
        as ``1/r`` with no exponential cutoff.
        """
        w = self.perfusion_conductance_W_per_m3K
        if w <= 0:
            return math.inf
        return math.sqrt(self.thermal_conductivity_W_per_mK / w)

    @property
    def thermal_diffusivity_m2_per_s(self) -> float:
        """``alpha = kappa / (rho c)``."""
        return self.thermal_conductivity_W_per_mK / (
            self.density_kg_per_m3 * self.specific_heat_J_per_kgK
        )

    @property
    def fully_verified(self) -> bool:
        """Whether every property came from a primary source."""
        names = {
            "thermal_conductivity_W_per_mK",
            "density_kg_per_m3",
            "specific_heat_J_per_kgK",
            "perfusion_rate_per_s",
            "blood_density_kg_per_m3",
            "blood_specific_heat_J_per_kgK",
        }
        return names.issubset(set(self.verified_fields))

    def describe(self) -> str:
        """Multi-line summary with uncertainty and provenance flags."""
        rows = [
            ("thermal conductivity", "W/m/K", "thermal_conductivity_W_per_mK"),
            ("tissue density", "kg/m^3", "density_kg_per_m3"),
            ("tissue specific heat", "J/kg/K", "specific_heat_J_per_kgK"),
            ("perfusion rate", "1/s", "perfusion_rate_per_s"),
            ("blood density", "kg/m^3", "blood_density_kg_per_m3"),
            ("blood specific heat", "J/kg/K", "blood_specific_heat_J_per_kgK"),
        ]
        lines = [f"Tissue thermal properties: {self.tissue_name} ({self.source})"]
        for label, unit, key in rows:
            value = getattr(self, key)
            spread = self.uncertainty.get(key)
            detail = ""
            if spread is not None:
                sd, n = spread
                detail = f"  (sd {sd:g}, n = {n})"
            flag = "" if key in self.verified_fields else "  PROVISIONAL"
            lines.append(f"  {label:22s} {value:<10g} {unit:<8s}{detail}{flag}")
        depth = self.thermal_penetration_depth_m
        depth_text = "inf (no perfusion)" if math.isinf(depth) else f"{depth * 1e3:.2f} mm"
        lines.append(f"  {'penetration depth L':22s} {depth_text}")
        return "\n".join(lines)


def _itis(
    name: str,
    kappa: float,
    rho: float,
    c: float,
    perfusion_ml_min_kg: float,
    metabolic_W_per_kg: float,
    uncertainty: dict[str, tuple[float, int]],
) -> TissueThermalProperties:
    """Build a preset from IT'IS v4.2 table values, converting perfusion units."""
    return TissueThermalProperties(
        thermal_conductivity_W_per_mK=kappa,
        density_kg_per_m3=rho,
        specific_heat_J_per_kgK=c,
        perfusion_rate_per_s=perfusion_per_s(perfusion_ml_min_kg, rho),
        blood_density_kg_per_m3=1049.75,
        blood_specific_heat_J_per_kgK=3617.0,
        metabolic_heat_W_per_m3=metabolic_W_per_kg * rho,
        tissue_name=name,
        source="itis2025",
        uncertainty=uncertainty,
    )


GREY_MATTER = _itis(
    "Brain (Grey Matter)", 0.547, 1044.5, 3695.8, 763.667, 15.539,
    {
        "thermal_conductivity_W_per_mK": (0.02546, 2),
        "density_kg_per_m3": (7.778, 9),
        "specific_heat_J_per_kgK": (34.43, 5),
        "perfusion_rate_per_s": (perfusion_per_s(85.676, 1044.5), 3),
        "blood_density_kg_per_m3": (19.17, 584),
        "blood_specific_heat_J_per_kgK": (301.4, 3),
    },
)
"""Grey matter, IT'IS Database v4.2."""

WHITE_MATTER = _itis(
    "Brain (White Matter)", 0.481, 1041.0, 3582.8, 212.333, 4.321,
    {
        "thermal_conductivity_W_per_mK": (0.02970, 2),
        "density_kg_per_m3": (1.732, 10),
        "specific_heat_J_per_kgK": (78.30, 5),
        "perfusion_rate_per_s": (perfusion_per_s(23.587, 1041.0), 3),
        "blood_density_kg_per_m3": (19.17, 584),
        "blood_specific_heat_J_per_kgK": (301.4, 3),
    },
)
"""White matter, IT'IS Database v4.2. Perfusion is 3.6x lower than grey matter."""

WHOLE_BRAIN = _itis(
    "Brain (whole)", 0.51325, 1045.5, 3630.0, 558.606, 11.367,
    {
        "thermal_conductivity_W_per_mK": (0.02249, 4),
        "density_kg_per_m3": (6.364, 9),
        "specific_heat_J_per_kgK": (73.54, 2),
        "perfusion_rate_per_s": (perfusion_per_s(98.818, 1045.5), 43),
        "blood_density_kg_per_m3": (19.17, 584),
        "blood_specific_heat_J_per_kgK": (301.4, 3),
    },
)
"""Undifferentiated brain, IT'IS Database v4.2."""

ELWASSIF_BRAIN = replace(
    GREY_MATTER,
    thermal_conductivity_W_per_mK=0.527,
    tissue_name="Brain (homogeneous, Elwassif 2006)",
    source="elwassif2006",
    uncertainty={},
)
"""The homogeneous-brain conductivity used by Elwassif et al. (2006).

Provided so their DBS thermal results can be reproduced. Their paper states only the
thermal conductivity and electrical conductivity, so the remaining properties here are
still the IT'IS grey-matter values.
"""

BRAIN = GREY_MATTER
"""Package default. Grey matter from IT'IS v4.2, fully sourced with uncertainty."""


def voltage_driven_power_W(v_rms: float, resistance_ohm: float) -> float:
    """Power dissipated by a voltage-controlled stimulator: ``P = V_rms^2 / R``.

    Clinical DBS is usually specified as a voltage, and its thermal load follows from
    the RMS voltage and the interelectrode resistance -- not from a current amplitude.
    Mixing the two is what makes published temperature rises look irreconcilable: a
    continuous 1.56 V RMS bipolar setting dissipates milliwatts, a duty-cycled 3 mA
    monopolar pulse train microwatts.
    """
    if resistance_ohm <= 0 or not math.isfinite(resistance_ohm):
        raise ValueError(f"resistance_ohm must be finite and > 0, got {resistance_ohm!r}")
    if not math.isfinite(v_rms):
        raise ValueError(f"v_rms must be finite, got {v_rms!r}")
    return v_rms**2 / resistance_ohm


def ohmic_power_W(rms_current_uA: float, resistance_ohm: float) -> float:
    """Time-averaged power dissipated in the tissue spreading resistance.

    For a *current*-controlled stimulator. Use :func:`voltage_driven_power_W` when the
    stimulator is voltage-controlled.
    """
    if resistance_ohm < 0 or not math.isfinite(resistance_ohm):
        raise ValueError(f"resistance_ohm must be finite and >= 0, got {resistance_ohm!r}")
    return (rms_current_uA * 1e-6) ** 2 * resistance_ohm


def pennes_steady_state_sphere(
    power_W: float,
    source_radius_um: float,
    distance_um: float | np.ndarray | None = None,
    tissue: TissueThermalProperties = BRAIN,
) -> float | np.ndarray:
    """Steady-state temperature rise around a spherical heat source, in kelvin.

    Parameters
    ----------
    distance_um:
        Radial distance. Defaults to the source surface, giving the peak rise.
        Distances inside the source radius are rejected -- the solution is only valid
        in the tissue outside it.
    """
    if power_W < 0 or not math.isfinite(power_W):
        raise ValueError(f"power_W must be finite and >= 0, got {power_W!r}")
    if not math.isfinite(source_radius_um) or source_radius_um <= 0:
        raise ValueError(
            f"source_radius_um must be finite and > 0, got {source_radius_um!r}"
        )

    a = source_radius_um * 1e-6
    kappa = tissue.thermal_conductivity_W_per_mK
    L = tissue.thermal_penetration_depth_m

    r = a if distance_um is None else np.asarray(distance_um, dtype=float) * 1e-6
    if np.any(np.asarray(r) < a * (1 - 1e-12)):
        raise ValueError(
            f"distance_um must be >= source_radius_um ({source_radius_um:g} um); "
            f"the solution describes tissue outside the source only"
        )

    surface_factor = 1.0 if math.isinf(L) else 1.0 + a / L
    decay = 1.0 if math.isinf(L) else np.exp(-(np.asarray(r) - a) / L)
    result = power_W * decay / (4.0 * math.pi * kappa * np.asarray(r) * surface_factor)

    if distance_um is None or np.isscalar(distance_um):
        return float(result)
    return np.asarray(result)


def peak_temperature_rise_K(
    power_W: float,
    source_radius_um: float,
    tissue: TissueThermalProperties = BRAIN,
) -> float:
    """Steady-state rise at the source surface, which is where it is largest."""
    return float(pennes_steady_state_sphere(power_W, source_radius_um, None, tissue))


def pennes_transient_sphere(
    power_W: float,
    source_radius_um: float,
    times_s: np.ndarray,
    tissue: TissueThermalProperties = BRAIN,
    *,
    cells_per_radius: int = 20,
    domain_extent_factor: float | None = None,
    max_cells: int = 20000,
) -> np.ndarray:
    """Surface temperature rise over time, by implicit finite differences.

    Solves the spherically symmetric Pennes equation on ``[a, a + extent]`` and returns
    the rise at the source surface sampled at ``times_s``.

    Two choices make this accurate where a naive discretisation is not:

    - **Substitution** ``u = r T'``. This turns the spherical operator
      ``T'' + (2/r)T'`` into a plain second derivative ``u''``, removing the ``1/r``
      geometric term. Discretising ``T`` directly needs a grid far finer than the
      source radius to resolve the near-field ``1/r`` behaviour at the inner boundary;
      in ``u`` it is smooth.
    - **Backward Euler with a tridiagonal solve**. Unconditionally stable, so the time
      step is set by accuracy rather than by the explicit diffusion limit.

    The inner boundary imposes the constant heat flux ``P / (4 pi a^2)`` through a
    second-order ghost node; the outer boundary is clamped to the arterial baseline at
    ``domain_extent_factor`` penetration depths, far enough not to influence the surface.

    Domain size and the unperfused case
    -----------------------------------
    With perfusion the temperature field decays exponentially over ``L``, so a domain of
    a few ``L`` is effectively infinite and the result matches
    :func:`pennes_steady_state_sphere` to rounding.

    Without perfusion there is no such length scale: the field decays only as ``1/r``,
    and clamping the outer boundary at radius ``R`` depresses the surface temperature by
    exactly the factor ``(1 - a/R)``. ``domain_extent_factor`` therefore defaults to 12
    penetration depths when perfused and to 400 source radii when not, the latter
    keeping the truncation error near 0.25 %. Increasing it helps only while the grid
    fits in ``max_cells``: past that the cells coarsen, the added domain goes unresolved,
    and the error saturates near 0.075 % -- a :class:`ThermalResolutionWarning` says so,
    and ``max_cells`` can be raised (ledger 36). Or compare against the analytic
    solution, which assumes an unbounded medium.

    The time step is set by the physics, not by the other times requested: a sample at
    ``t`` is the same whatever else is asked for (ledger 35).
    """
    from scipy.linalg import solve_banded

    times = np.asarray(times_s, dtype=float)
    if times.ndim != 1 or times.size == 0:
        raise ValueError("times_s must be a non-empty 1-D array")
    if np.any(times < 0):
        raise ValueError("times_s must be >= 0")
    if cells_per_radius < 4:
        raise ValueError(f"cells_per_radius must be >= 4, got {cells_per_radius}")
    if power_W < 0 or not math.isfinite(power_W):
        raise ValueError(f"power_W must be finite and >= 0, got {power_W!r}")
    if not math.isfinite(source_radius_um) or source_radius_um <= 0:
        raise ValueError(
            f"source_radius_um must be finite and > 0, got {source_radius_um!r}"
        )

    a = source_radius_um * 1e-6
    kappa = tissue.thermal_conductivity_W_per_mK
    alpha = tissue.thermal_diffusivity_m2_per_s
    W = tissue.perfusion_conductance_W_per_m3K
    rho_c = tissue.density_kg_per_m3 * tissue.specific_heat_J_per_kgK
    beta = W / rho_c

    L = tissue.thermal_penetration_depth_m
    if domain_extent_factor is None:
        domain_extent_factor = 400.0 if math.isinf(L) else 12.0
    elif domain_extent_factor <= 0 or not math.isfinite(domain_extent_factor):
        raise ValueError(
            f"domain_extent_factor must be finite and > 0, got {domain_extent_factor!r}"
        )
    extent = domain_extent_factor * (a if math.isinf(L) else L)

    dr = a / cells_per_radius
    n = round(extent / dr) + 1
    if n > max_cells:
        # Loudly: the clamp used to be silent, and it is why a larger
        # domain_extent_factor stops helping (ledgers 36, 42).
        warnings.warn(
            f"the grid needs {n} cells for {cells_per_radius} per radius over "
            f"{extent * 1e3:.3g} mm but max_cells is {max_cells}; using {max_cells} "
            f"({extent / (max_cells - 1) / a:.3g} radii per cell's worth, "
            f"{a / (extent / (max_cells - 1)):.3g} cells per radius). Raise max_cells "
            f"for the resolution asked for",
            ThermalResolutionWarning,
            stacklevel=2,
        )
        n = max_cells
        dr = extent / (n - 1)
    r = a + dr * np.arange(n)

    flux_in = power_W / (4.0 * math.pi * a**2)  # W/m^2 into the tissue at r = a
    # Ghost-node form of -kappa dT/dr = flux_in expressed in u = r*T:
    #   du/dr|_a = u(a)/a - a*flux_in/kappa
    ghost_source = a * flux_in / kappa

    # Backward Euler on du/dt = alpha u'' - beta u, tridiagonal in banded storage.
    #
    # The step grows with time, dt = STEP_FRACTION * (t + t0), on a grid set by the
    # physics alone: t0 is a hundredth of the diffusion time a^2/alpha. It used to be the
    # largest requested time over a fixed step count, so an early sample depended on the
    # others requested with it -- t = 1e-3 s read -0.1 % alone and -15.0 % inside
    # logspace(-3, 3.5, 60) (ledger 35). A requested time is reached by shortening the
    # step that would pass it.
    t0 = 0.01 * a**2 / alpha

    def step_once(u: np.ndarray, step: float) -> np.ndarray:
        lam = alpha * step / dr**2
        ab = np.zeros((3, n))
        ab[0, 1:] = -lam
        ab[1, :] = 1.0 + 2.0 * lam + beta * step
        ab[2, :-1] = -lam
        # i = 0: eliminate the ghost node u_{-1} = u_1 - 2*dr*(u_0/a - ghost_source).
        ab[1, 0] += 2.0 * lam * dr / a
        ab[0, 1] = -2.0 * lam
        # i = n-1: clamped to baseline.
        ab[1, -1] = 1.0
        ab[2, -2] = 0.0
        rhs = u.copy()
        rhs[0] += 2.0 * lam * dr * ghost_source
        rhs[-1] = 0.0
        return solve_banded((1, 1), ab, rhs)

    u = np.zeros(n)
    out = np.zeros_like(times)
    t = 0.0
    for index in np.argsort(times):
        target = float(times[index])
        while t < target - 1e-12 * max(target, 1.0):
            step = min(STEP_FRACTION * (t + t0), target - t)
            u = step_once(u, step)
            t += step
        out[index] = float(u[0] / r[0]) if target > 0 else 0.0

    return out


STEP_FRACTION = 0.01
"""Backward-Euler step as a fraction of ``t + t0`` in :func:`pennes_transient_sphere`."""


class ThermalResolutionWarning(UserWarning):
    """The transient grid was clamped to ``max_cells`` (ledgers 36, 42)."""


@dataclass(frozen=True)
class ThermalResult:
    """Outcome of the thermal estimate for one protocol."""

    power_W: float
    rms_current_uA: float
    resistance_ohm: float
    source_radius_um: float
    peak_rise_K: float
    penetration_depth_mm: float
    tissue: TissueThermalProperties
    limit_K: float = 2.0

    @property
    def passes(self) -> bool:
        """Whether the estimated rise stays under :attr:`limit_K`."""
        return self.peak_rise_K <= self.limit_K

    @property
    def satisfies_iso_surface_limit(self) -> bool:
        """Whether the rise satisfies ISO 14708-3 clause 17.1(a) at a 37 C baseline."""
        from ..data import iso14708_3

        return iso14708_3.rise_is_acceptable(self.peak_rise_K)

    def cem43_minutes_allowed(self, tissue: str = "brain") -> float:
        """Minutes at this temperature before the tissue's CEM43 threshold is reached.

        Infinite below 39 C, where clause 17.1(a) is satisfied outright.
        """
        from ..data import iso14708_3

        return iso14708_3.allowed_minutes(
            iso14708_3.BASELINE_BODY_TEMPERATURE_C + self.peak_rise_K, tissue
        )

    def describe(self) -> str:
        """Multi-line summary."""
        depth = (
            "inf"
            if math.isinf(self.penetration_depth_mm)
            else f"{self.penetration_depth_mm:.2f} mm"
        )
        verdict = "PASS" if self.passes else "EXCEEDS"
        lines = [
            f"Thermal (Pennes steady state, spherical) -> {verdict}",
            f"  RMS current     {self.rms_current_uA:.4g} uA into "
            f"{self.resistance_ohm:.0f} ohm",
            f"  dissipated      {self.power_W * 1e6:.4g} uW",
            f"  peak rise       {self.peak_rise_K * 1e3:.4g} mK "
            f"(limit {self.limit_K:g} K, ISO 14708-3 clause 17.1a)",
            f"  penetration L   {depth}",
        ]
        if not self.tissue.fully_verified:
            lines.append(
                "  CAUTION: perfusion and heat-capacity values are conventional "
                "textbook figures, not primary-sourced"
            )
        lines.append(
            "  spreading-resistance heating only: no electrode/lead self-heating, "
            "no encapsulation"
        )
        lines.append(
            "  scalings validated against Elwassif et al. (2006) FEM: linear in sigma "
            "(0.7 %),\n  inverse in kappa (0.9 %), perfusion attenuation within 7-8 %"
        )
        return "\n".join(lines)


def evaluate(
    rms_current_uA: float,
    access_resistance_ohm: float,
    source_radius_um: float,
    tissue: TissueThermalProperties = BRAIN,
    *,
    limit_K: float = 2.0,
) -> ThermalResult:
    """Estimate steady-state tissue heating for a protocol.

    ``limit_K`` defaults to 2 K, which is what ISO 14708-3:2017 clause 17.1(a) implies
    at a 37 C baseline: no outer surface of the implant above 39 C. The standard offers
    a CEM43 thermal-dose alternative for excursions above 39 C -- see
    :mod:`neurostim.data.iso14708_3` and :meth:`ThermalResult.cem43_minutes_allowed`.

    Earlier releases used 1 K here, which was a reporting convention with no standard
    behind it.
    """
    power = ohmic_power_W(rms_current_uA, access_resistance_ohm)
    rise = peak_temperature_rise_K(power, source_radius_um, tissue)
    depth = tissue.thermal_penetration_depth_m
    return ThermalResult(
        power_W=power,
        rms_current_uA=rms_current_uA,
        resistance_ohm=access_resistance_ohm,
        source_radius_um=source_radius_um,
        peak_rise_K=rise,
        penetration_depth_mm=math.inf if math.isinf(depth) else depth * 1e3,
        tissue=tissue,
        limit_K=limit_K,
    )
