"""Strength-duration and charge-duration relationships.

Two classical forms are provided. Both describe the same empirical fact -- threshold
current falls with increasing pulse width toward an asymptote, the rheobase -- and both
are fits, not derivations from membrane biophysics.

Lapicque (1907), quoted as equation (4.2) in Merrill et al. (2005):

.. math::

    I_{th}(W) = \\frac{I_{rh}}{1 - e^{-W/\\tau_m}}

Weiss (1901), the linear charge-duration form:

.. math::

    Q_{th}(W) = I_{rh}(W + t_c), \\qquad
    I_{th}(W) = I_{rh}\\left(1 + \\frac{t_c}{W}\\right)

Chronaxie ``t_c`` is defined as the pulse width at which threshold is twice rheobase.
For the Weiss form that is exact by construction. For the Lapicque form it follows from
setting ``I_th = 2 I_rh``, giving ``t_c = tau_m ln 2``.

The two forms are not interchangeable
-------------------------------------
Fitted to the same rheobase and chronaxie they agree **exactly at chronaxie** -- both are
constrained to pass through ``2 I_rh`` there -- and diverge on either side:

============  ==================
Pulse width   Weiss / Lapicque
============  ==================
0.33 x t_c    0.83
1.0 x t_c     1.00
6.7 x t_c     1.14
============  ==================

Weiss predicts a *lower* threshold for short pulses and a *higher* one for long pulses.
Neither is derived from membrane biophysics, so there is no principled basis for
preferring one: fit whichever describes your own data better, and do not mix a rheobase
fitted under one with a chronaxie fitted under the other. :func:`fit_weiss` is exact and
non-iterative, which makes it the better choice when you have few points.

Merrill et al. note explicitly that the quantitative parameters -- rheobase above all --
depend on the distance between the electrode and the target population and are
determined empirically. Neither form predicts a threshold for a new preparation; they
interpolate one you have measured. There are no default rheobase or chronaxie values in
this module for that reason.

The charge-duration curve rising at long pulse widths is the practically important
consequence: minimising injected charge favours short pulses, which is why the
charge-per-phase safety limits and the efficacy optimum point in the same direction.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


def lapicque_threshold_uA(
    pulse_width_us: float | np.ndarray,
    rheobase_uA: float,
    membrane_tau_us: float,
) -> float | np.ndarray:
    """Threshold current from the Lapicque exponential form."""
    _check_positive("rheobase_uA", rheobase_uA)
    _check_positive("membrane_tau_us", membrane_tau_us)
    w = np.asarray(pulse_width_us, dtype=float)
    if np.any(w <= 0):
        raise ValueError("pulse_width_us must be > 0")
    result = rheobase_uA / (1.0 - np.exp(-w / membrane_tau_us))
    return float(result) if np.isscalar(pulse_width_us) else result


def weiss_threshold_uA(
    pulse_width_us: float | np.ndarray,
    rheobase_uA: float,
    chronaxie_us: float,
) -> float | np.ndarray:
    """Threshold current from the Weiss linear charge-duration form."""
    _check_positive("rheobase_uA", rheobase_uA)
    _check_positive("chronaxie_us", chronaxie_us)
    w = np.asarray(pulse_width_us, dtype=float)
    if np.any(w <= 0):
        raise ValueError("pulse_width_us must be > 0")
    result = rheobase_uA * (1.0 + chronaxie_us / w)
    return float(result) if np.isscalar(pulse_width_us) else result


def weiss_threshold_charge_uC(
    pulse_width_us: float | np.ndarray,
    rheobase_uA: float,
    chronaxie_us: float,
) -> float | np.ndarray:
    """Threshold charge from the Weiss form: ``Q = I_rh (W + t_c)``."""
    _check_positive("rheobase_uA", rheobase_uA)
    _check_positive("chronaxie_us", chronaxie_us)
    w = np.asarray(pulse_width_us, dtype=float)
    if np.any(w <= 0):
        raise ValueError("pulse_width_us must be > 0")
    result = rheobase_uA * (w + chronaxie_us) * 1e-6
    return float(result) if np.isscalar(pulse_width_us) else result


def chronaxie_from_tau_us(membrane_tau_us: float) -> float:
    """Chronaxie implied by a Lapicque membrane time constant: ``t_c = tau ln 2``."""
    _check_positive("membrane_tau_us", membrane_tau_us)
    return membrane_tau_us * math.log(2.0)


def tau_from_chronaxie_us(chronaxie_us: float) -> float:
    """Inverse of :func:`chronaxie_from_tau_us`."""
    _check_positive("chronaxie_us", chronaxie_us)
    return chronaxie_us / math.log(2.0)


@dataclass(frozen=True)
class StrengthDurationFit:
    """Parameters recovered from measured threshold data."""

    model: str
    rheobase_uA: float
    chronaxie_us: float
    membrane_tau_us: float
    rss: float
    n_points: int

    def threshold_uA(self, pulse_width_us: float | np.ndarray):
        """Evaluate the fitted curve."""
        if self.model == "weiss":
            return weiss_threshold_uA(
                pulse_width_us, self.rheobase_uA, self.chronaxie_us
            )
        return lapicque_threshold_uA(
            pulse_width_us, self.rheobase_uA, self.membrane_tau_us
        )

    def describe(self) -> str:
        """Multi-line summary."""
        return "\n".join(
            [
                f"{self.model.capitalize()} fit to {self.n_points} points",
                f"  rheobase   {self.rheobase_uA:.4g} uA",
                f"  chronaxie  {self.chronaxie_us:.4g} us",
                f"  tau_m      {self.membrane_tau_us:.4g} us",
                f"  residual   {self.rss:.4g}",
            ]
        )


def fit_weiss(
    pulse_widths_us: np.ndarray, thresholds_uA: np.ndarray
) -> StrengthDurationFit:
    """Fit the Weiss form by linear least squares on the charge-duration line.

    ``Q(W) = I_rh W + I_rh t_c`` is linear in ``W``, so the fit is exact and
    non-iterative: the slope is the rheobase and the intercept over the slope is the
    chronaxie. This is why Weiss is the form to fit when you have few points.
    """
    w = np.asarray(pulse_widths_us, dtype=float)
    i = np.asarray(thresholds_uA, dtype=float)
    if w.shape != i.shape:
        raise ValueError(
            f"pulse_widths_us and thresholds_uA must have the same shape, "
            f"got {w.shape} and {i.shape}"
        )
    if w.size < 2:
        raise ValueError("need at least 2 points to fit a strength-duration curve")
    if np.any(w <= 0) or np.any(i <= 0):
        raise ValueError("pulse widths and thresholds must all be > 0")

    charge = i * w  # proportional to threshold charge; units cancel in the ratio
    slope, intercept = np.polyfit(w, charge, 1)
    if slope <= 0:
        raise ValueError(
            "fitted rheobase is non-positive; the data do not follow a Weiss "
            "strength-duration relationship"
        )
    rheobase = float(slope)
    chronaxie = float(intercept / slope)
    residual = float(np.sum((charge - (slope * w + intercept)) ** 2))

    return StrengthDurationFit(
        model="weiss",
        rheobase_uA=rheobase,
        chronaxie_us=chronaxie,
        membrane_tau_us=tau_from_chronaxie_us(chronaxie) if chronaxie > 0 else math.nan,
        rss=residual,
        n_points=int(w.size),
    )


def fit_lapicque(
    pulse_widths_us: np.ndarray,
    thresholds_uA: np.ndarray,
    *,
    max_iter: int = 200,
) -> StrengthDurationFit:
    """Fit the Lapicque form by Levenberg-Marquardt, seeded from the Weiss fit."""
    from scipy.optimize import curve_fit

    w = np.asarray(pulse_widths_us, dtype=float)
    i = np.asarray(thresholds_uA, dtype=float)
    seed = fit_weiss(w, i)

    def model(width, rheobase, tau):
        return rheobase / (1.0 - np.exp(-width / tau))

    params, _ = curve_fit(
        model,
        w,
        i,
        p0=[seed.rheobase_uA, seed.membrane_tau_us],
        bounds=([1e-12, 1e-12], [np.inf, np.inf]),
        maxfev=max_iter * 10,
    )
    rheobase, tau = (float(p) for p in params)
    residual = float(np.sum((i - model(w, rheobase, tau)) ** 2))

    return StrengthDurationFit(
        model="lapicque",
        rheobase_uA=rheobase,
        chronaxie_us=chronaxie_from_tau_us(tau),
        membrane_tau_us=tau,
        rss=residual,
        n_points=int(w.size),
    )


def _check_positive(name: str, value: float) -> None:
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and > 0, got {value!r}")
