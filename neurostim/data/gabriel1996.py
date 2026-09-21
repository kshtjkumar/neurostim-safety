"""Gabriel et al. (1996) four-Cole-Cole model of tissue dielectric properties.

Part III, *Parametric models for the dielectric spectrum of tissues*, Phys Med Biol
41:2271-93. Table 1 parameters, transcribed for the tissues relevant here.

The model
---------
Complex permittivity as a sum of four Cole-Cole dispersions plus an ionic term:

.. math::

    \\hat{\\varepsilon}(\\omega) = \\varepsilon_\\infty
        + \\sum_{n=1}^{4} \\frac{\\Delta\\varepsilon_n}{1 + (j\\omega\\tau_n)^{1-\\alpha_n}}
        + \\frac{\\sigma_i}{j\\omega\\varepsilon_0}

Total conductivity follows as ``sigma(omega) = sigma_i + omega * eps_0 * eps''``.

Why this matters, and the surprise in it
----------------------------------------
This package defaults to 0.35 S/m, the deep-brain-stimulation modelling convention, and
offers the IT'IS grey-matter figure of 0.419 S/m as the better-sourced alternative.
Evaluating Gabriel's model at frequencies relevant to a stimulation pulse gives a value
**well below both**.

That is not a contradiction to resolve by picking a favourite. The three numbers measure
different things: Gabriel's is a low-frequency dielectric-spectroscopy result on excised
tissue, IT'IS aggregates low-frequency measurements across many studies and methods, and
0.35 S/m is a value chosen in DBS finite element work partly because it reproduces
clinical impedances, which include the encapsulation sheath around a chronic implant.
A chronically implanted electrode does not sit in the tissue Gabriel measured.

The package therefore keeps 0.35 S/m as the default for comparability with published DBS
work, exposes all three, and documents the spread rather than hiding it. Access
resistance scales as ``1/sigma``, so the choice moves compliance voltage proportionally.

Effective frequency of a pulse
------------------------------
A rectangular pulse of width ``W`` has most of its energy below roughly ``1/(2W)``.
:func:`effective_frequency_hz` uses that convention so a pulse width can be turned into a
frequency at which to evaluate the model. It is a convention, not a result.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

EPS_0 = 8.8541878128e-12
"""Permittivity of free space, F/m."""


@dataclass(frozen=True)
class ColeColeTissue:
    """Four-Cole-Cole parameters for one tissue, from Gabriel et al. (1996) Table 1."""

    name: str
    eps_inf: float
    sigma_i_S_per_m: float
    # (delta_eps, tau_seconds, alpha) for each of the four dispersions
    dispersions: tuple[tuple[float, float, float], ...] = field(default_factory=tuple)

    def complex_permittivity(self, frequency_hz: float) -> complex:
        """Relative complex permittivity at a frequency."""
        if frequency_hz <= 0:
            raise ValueError(f"frequency_hz must be > 0, got {frequency_hz!r}")
        omega = 2.0 * math.pi * frequency_hz
        total = complex(self.eps_inf, 0.0)
        for delta_eps, tau, alpha in self.dispersions:
            if delta_eps == 0.0:
                continue
            total += delta_eps / (1.0 + (1j * omega * tau) ** (1.0 - alpha))
        total += self.sigma_i_S_per_m / (1j * omega * EPS_0)
        return total

    def conductivity_S_per_m(self, frequency_hz: float) -> float:
        """Total conductivity at a frequency, ``sigma = omega eps_0 eps''``."""
        omega = 2.0 * math.pi * frequency_hz
        eps = self.complex_permittivity(frequency_hz)
        # eps'' is carried as the negative imaginary part in this convention.
        return -eps.imag * omega * EPS_0

    def relative_permittivity(self, frequency_hz: float) -> float:
        """Real part of the relative permittivity at a frequency."""
        return self.complex_permittivity(frequency_hz).real


GREY_MATTER = ColeColeTissue(
    name="Brain (grey matter)",
    eps_inf=4.0,
    sigma_i_S_per_m=0.0200,
    dispersions=(
        (45.0, 7.96e-12, 0.10),
        (400.0, 15.92e-9, 0.15),
        (2.0e5, 106.10e-6, 0.22),
        (4.5e7, 5.305e-3, 0.00),
    ),
)

WHITE_MATTER = ColeColeTissue(
    name="Brain (white matter)",
    eps_inf=4.0,
    sigma_i_S_per_m=0.0200,
    dispersions=(
        (32.0, 7.96e-12, 0.10),
        (100.0, 7.96e-9, 0.10),
        (4.0e4, 53.05e-6, 0.30),
        (3.5e7, 7.958e-3, 0.02),
    ),
)

BLOOD = ColeColeTissue(
    name="Blood",
    eps_inf=4.0,
    sigma_i_S_per_m=0.7000,
    dispersions=(
        (56.0, 8.38e-12, 0.10),
        (5200.0, 132.63e-9, 0.10),
        (0.0, 0.0, 0.0),
        (0.0, 0.0, 0.0),
    ),
)

MUSCLE = ColeColeTissue(
    name="Muscle",
    eps_inf=4.0,
    sigma_i_S_per_m=0.2000,
    dispersions=(
        (50.0, 7.23e-12, 0.10),
        (7000.0, 353.68e-9, 0.10),
        (1.2e6, 318.31e-6, 0.10),
        (2.5e7, 2.274e-3, 0.00),
    ),
)

TISSUES: dict[str, ColeColeTissue] = {
    "grey matter": GREY_MATTER,
    "white matter": WHITE_MATTER,
    "blood": BLOOD,
    "muscle": MUSCLE,
}

REFERENCE = "gabriel1996_iii"


def effective_frequency_hz(pulse_width_us: float) -> float:
    """Frequency below which most of a rectangular pulse's energy lies, ``1/(2W)``.

    A convention for choosing where to evaluate the dispersion model, not a result.
    """
    if pulse_width_us <= 0:
        raise ValueError(f"pulse_width_us must be > 0, got {pulse_width_us!r}")
    return 1.0 / (2.0 * pulse_width_us * 1e-6)


def get(tissue: str = "grey matter") -> ColeColeTissue:
    """Look up a tissue by name."""
    key = tissue.strip().lower()
    try:
        return TISSUES[key]
    except KeyError:
        raise KeyError(
            f"No Cole-Cole parameters for {tissue!r}. Available: {sorted(TISSUES)}"
        ) from None


def conductivity_for_pulse(
    pulse_width_us: float, tissue: str = "grey matter"
) -> float:
    """Conductivity at the effective frequency of a pulse of the given width."""
    return get(tissue).conductivity_S_per_m(effective_frequency_hz(pulse_width_us))
