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
    rheobase_se_uA: float | None = None
    """Standard error of the rheobase; ``None`` with no residual degrees of freedom."""
    chronaxie_se_us: float | None = None
    """Standard error of the chronaxie (delta method for Weiss, ``ln 2 * se(tau)`` for
    Lapicque); ``None`` with no residual degrees of freedom (ledger 37)."""
    chronaxie_ci95_us: tuple[float, float] | None = None
    """95 % confidence interval, estimate +/- t(0.975, n - 2) x SE. At 5 % threshold noise,
    widths 50-800 us and a true chronaxie of 200 us it covers 94 % of 4000 synthetic
    replicates, whose estimates scatter with sd 27 us."""

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
        """Multi-line summary, with the uncertainty the fit supports."""
        if self.chronaxie_ci95_us is None or self.rheobase_se_uA is None:
            spread = [
                f"  uncertainty not estimable from {self.n_points} points "
                f"(no residual degrees of freedom)"
            ]
        else:
            low, high = self.chronaxie_ci95_us
            spread = [
                f"  rheobase SE {self.rheobase_se_uA:.3g} uA",
                f"  chronaxie SE {self.chronaxie_se_us:.3g} us, 95 % CI "
                f"{low:.4g}-{high:.4g} us",
            ]
        return "\n".join(
            [
                f"{self.model.capitalize()} fit to {self.n_points} points",
                f"  rheobase   {self.rheobase_uA:.4g} uA",
                f"  chronaxie  {self.chronaxie_us:.4g} us",
                f"  tau_m      {self.membrane_tau_us:.4g} us",
                f"  residual   {self.rss:.4g}",
                *spread,
            ]
        )


def _interval(
    estimate: float, se: float | None, dof: int
) -> tuple[float, float] | None:
    """``estimate +/- t(0.975, dof) se``, or ``None`` without a finite SE."""
    if se is None or not math.isfinite(se) or dof < 1:
        return None
    from scipy.stats import t as student_t

    half = float(student_t.ppf(0.975, dof)) * se
    return estimate - half, estimate + half


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
    # One width gives the charge-duration line no slope to fit: polyfit returned numbers
    # behind a RankWarning (ledger 38).
    if np.unique(w).size < 2:
        raise ValueError(
            f"need at least 2 distinct pulse widths to fit a strength-duration curve, "
            f"got {np.unique(w).size}"
        )

    charge = i * w  # proportional to threshold charge; units cancel in the ratio
    slope, intercept = np.polyfit(w, charge, 1)
    if slope <= 0:
        raise ValueError(
            "fitted rheobase is non-positive; the data do not follow a Weiss "
            "strength-duration relationship"
        )
    # A non-positive intercept is a non-positive chronaxie, which no nerve has; the fit
    # used to return it (-60 us for a design generated at -60 us) with tau = nan
    # (ledger 33).
    if intercept <= 0:
        raise ValueError(
            f"fitted chronaxie is non-positive ({intercept / slope:.4g} us); the data do "
            f"not follow a Weiss strength-duration relationship"
        )
    rheobase = float(slope)
    chronaxie = float(intercept / slope)
    residual = float(np.sum((charge - (slope * w + intercept)) ** 2))

    # Ordinary least-squares covariance, s^2 (X^T X)^-1 with n - 2 degrees of freedom,
    # and the chronaxie's by the delta method on intercept / slope (ledger 37).
    dof = int(w.size) - 2
    rheobase_se = chronaxie_se = None
    if dof >= 1:
        design = np.column_stack([w, np.ones_like(w)])
        cov = residual / dof * np.linalg.inv(design.T @ design)
        var_s, var_b, cov_sb = cov[0, 0], cov[1, 1], cov[0, 1]
        rheobase_se = float(math.sqrt(var_s))
        var_c = (
            var_b / slope**2
            + intercept**2 * var_s / slope**4
            - 2.0 * intercept * cov_sb / slope**3
        )
        chronaxie_se = float(math.sqrt(max(var_c, 0.0)))

    return StrengthDurationFit(
        model="weiss",
        rheobase_uA=rheobase,
        chronaxie_us=chronaxie,
        membrane_tau_us=tau_from_chronaxie_us(chronaxie),
        rss=residual,
        n_points=int(w.size),
        rheobase_se_uA=rheobase_se,
        chronaxie_se_us=chronaxie_se,
        chronaxie_ci95_us=_interval(chronaxie, chronaxie_se, dof),
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

    params, pcov = curve_fit(
        model,
        w,
        i,
        p0=[seed.rheobase_uA, seed.membrane_tau_us],
        bounds=([1e-12, 1e-12], [np.inf, np.inf]),
        maxfev=max_iter * 10,
    )
    rheobase, tau = (float(p) for p in params)
    residual = float(np.sum((i - model(w, rheobase, tau)) ** 2))
    # curve_fit's covariance, which used to be discarded (ledger 37): scaled by the
    # residual variance, so infinite when there are no degrees of freedom left.
    dof = int(w.size) - 2
    diag = np.diag(pcov)
    finite = dof >= 1 and bool(np.all(np.isfinite(diag)))
    rheobase_se = float(math.sqrt(diag[0])) if finite else None
    chronaxie_se = float(math.log(2.0) * math.sqrt(diag[1])) if finite else None
    chronaxie = chronaxie_from_tau_us(tau)

    return StrengthDurationFit(
        model="lapicque",
        rheobase_uA=rheobase,
        chronaxie_us=chronaxie,
        membrane_tau_us=tau,
        rss=residual,
        n_points=int(w.size),
        rheobase_se_uA=rheobase_se,
        chronaxie_se_us=chronaxie_se,
        chronaxie_ci95_us=_interval(chronaxie, chronaxie_se, dof),
    )


def _check_positive(name: str, value: float) -> None:
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and > 0, got {value!r}")
