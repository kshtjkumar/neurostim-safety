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
    """Parameters recovered from measured threshold data.

    How far to trust the interval depends on the form (ledger 170). **Weiss**: the
    least-squares interval is calibrated -- 94 % coverage at 5 % threshold noise over
    widths 50-800 us, and 0.94-0.98 across every noise level and design the Phase 6
    review tried. **Lapicque**: the interval comes from ``curve_fit``'s local covariance
    and can under-cover on weakly informative designs -- 0.82 at 20 % noise with widths
    only 50-200 us, 0.85 with widths only 400-3200 us, 0.90 at 10 % noise on 50-200 us --
    and on such designs up to 29 % of noisy replicates are refused outright, so coverage
    is conditional on the fit being accepted. Spread the widths across the chronaxie.

    **Lapicque interval (ledger 183).** Reported as ``c * exp(+/- t se / c)``, positive
    and asymmetric. It is withheld, with :attr:`uncertainty_note` saying so, when the
    linear interval ``c +/- t se`` lies wholly below the shortest width tested: the
    chronaxie is then an extrapolation below the design. A design spanning less than
    :data:`NARROW_SPAN` (8x) carries :attr:`coverage_caveat`. An interval with no finite
    upper end, or wider than :data:`VACUOUS_RATIO`, is withheld the same way: it does not
    bound the chronaxie (ledger 193). The fit is weighted by threshold
    (relative error, ledger 191). Coverage of the intervals reported, from
    ``scripts/lapicque_coverage.py`` (600 seeded replicates per cell, rheobase 20 uA, true
    chronaxie 50 / 100 / 200 / 500 us, 2-20 % noise; the range over those 16 cells, cells
    with fewer than 20 intervals left out; withheld intervals are not in the coverage;
    ``docs/audit/lapicque_coverage.txt`` is seed 191, and seed 192 is
    ``docs/audit/lapicque_coverage_seed192.txt``):

    ============  ================  ================  =============  ==============
    widths (us)   seed 191          seed 192          rule A         vacuous
    ============  ================  ================  =============  ==============
    50-800        0.943-0.981       0.943-0.985       0-6 %          0-15 %
    20-3200       0.928-0.962       0.918-0.963       0-1 %          0-1 %
    50-200 (*)    0.725-0.988       0.730-0.986       0-6 %          0-64 %
    400-3200      0.687-1.000       0.699-1.000       0-100 %        0-18 %
    2000-8000 (*) 0.211-1.000       0.145-1.000       32-100 %       0-25 %
    ============  ================  ================  =============  ==============

    The last two columns are the fits withheld, as a share of those accepted, by rule A and
    as vacuous. Designs of span >= 8 cover 0.69-1.00 over this grid.

    (*) span below 8x: the caveat is set. 400-3200 us spans exactly 8x and has no caveat,
    yet covers only about 0.69 at a 50 us chronaxie and 20 % noise, where every width is
    at least 8x the chronaxie: spread the widths across it.
    """

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
    uncertainty_note: str = ""
    """Why no SE or interval is given, when the reason is the design rather than the
    number of points (ledger 178)."""
    coverage_caveat: str = ""
    """Set when a Lapicque interval is reported on a design whose widths span less than
    :data:`NARROW_SPAN` fold, where its measured coverage can be far below nominal
    (ledgers 183, 192). Empty for Weiss and for wider designs."""

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
                f"  uncertainty not estimable: {self.uncertainty_note}"
                if self.uncertainty_note
                else f"  uncertainty not estimable from {self.n_points} points "
                f"(no residual degrees of freedom)"
            ]
        else:
            low, high = self.chronaxie_ci95_us
            spread = [
                f"  rheobase SE {self.rheobase_se_uA:.3g} uA",
                f"  chronaxie SE {self.chronaxie_se_us:.3g} us, 95 % CI "
                f"{low:.4g}-{high:.4g} us",
            ]
            if self.coverage_caveat:
                spread.append(f"  {self.coverage_caveat}")
            if self.model == "lapicque":
                spread.append(
                    "  (local-covariance interval: can under-cover on narrow or long-only "
                    "width designs)"
                )
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


NARROW_SPAN = 8.0
"""Width span (w_max / w_min) below which a Lapicque interval carries a coverage caveat.

From the validation grid (scripts/lapicque_coverage.py, output committed at
docs/audit/lapicque_coverage.txt, ledgers 183, 191, 192): over chronaxies 50-500 us and
2-20 % noise, on seeds 191 and 192, the span-4 designs (50-200 us, and 2-8 ms after rule
A) cover from below 0.25 to 1.00, so the caveat quotes no floor. Designs of span >= 8
cover 0.69-1.00 (seed 191); below 0.90 only on 400-3200 us at a 50-100 us chronaxie and
20 % noise, where every width is at least 4x the chronaxie. The span rule is kept (user
decision b, ledger 191). At seed 183 and a 200 us chronaxie alone, unweighted, this read
0.79-1.00 and >= 0.935. No per-fit statistic did better: a residual-noise flag misses the
under-covering fits, whose residual came out small by chance, and se/c > 0.3 flags the
fits that cover."""


VACUOUS_RATIO = 1000.0
"""An interval whose upper end is infinite, or more than this many times its lower end,
does not bound the chronaxie: it is withheld with an :attr:`~StrengthDurationFit.uncertainty_note`,
and the validation grid counts it apart from the coverage (ledger 193)."""


def _log_interval(
    estimate: float, se: float | None, dof: int
) -> tuple[float, float] | None:
    """``estimate * exp(+/- t(0.975, dof) se / estimate)``, or ``None`` without a finite SE."""
    if se is None or not math.isfinite(se) or dof < 1 or estimate <= 0:
        return None
    from scipy.stats import t as student_t

    half = float(student_t.ppf(0.975, dof)) * se / estimate
    if half > 700.0:
        # exp would overflow: the data put no finite upper end on the chronaxie, and the
        # interval says so rather than disappearing.
        return estimate * math.exp(-half), math.inf
    return estimate * math.exp(-half), estimate * math.exp(half)


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
    """Fit the Lapicque form by Levenberg-Marquardt, seeded from the Weiss fit.

    The interval is ``curve_fit``'s local covariance; it can under-cover on weakly
    informative designs (0.82 and 0.85 in the cases :class:`StrengthDurationFit` lists).
    """
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
        # Relative weighting: threshold noise is proportional to the threshold, so the
        # short widths, whose thresholds are largest and which pin a short chronaxie,
        # were over-weighted in absolute terms and the covariance assumed the wrong error
        # model. Unweighted, 20-3200 us covered 0.835 at a 50 us chronaxie (ledger 191).
        sigma=i,
    )
    rheobase, tau = (float(p) for p in params)
    residual = float(np.sum((i - model(w, rheobase, tau)) ** 2))
    # curve_fit's covariance, which used to be discarded (ledger 37): scaled by the
    # residual variance, so infinite when there are no degrees of freedom left.
    dof = int(w.size) - 2
    diag = np.diag(pcov)
    note = _unidentifiable_note(w, rheobase, tau)
    finite = dof >= 1 and bool(np.all(np.isfinite(diag))) and not note
    rheobase_se = float(math.sqrt(diag[0])) if finite else None
    chronaxie_se = float(math.log(2.0) * math.sqrt(diag[1])) if finite else None
    chronaxie = chronaxie_from_tau_us(tau)
    # Rule A is judged on the linear interval, as it was validated (ledger 183).
    interval = _interval(chronaxie, chronaxie_se, dof)
    # An interval wholly below the shortest width places the chronaxie below every pulse
    # the design tested: an extrapolation, and on the long-only designs the Phase 7b
    # review measured, one that covered 0.71-0.86 (ledger 183). Withheld, with the reason.
    if interval is not None and float(w.min()) > interval[1]:
        note = (
            f"the chronaxie's whole 95 % interval ({interval[0]:.4g}-{interval[1]:.4g} us) "
            f"lies below the shortest width tested ({float(w.min()):.4g} us), so it is an "
            f"extrapolation below the design. Include widths near the chronaxie"
        )
        rheobase_se = chronaxie_se = None
        interval = None
    caveat = ""
    if interval is not None:
        # The reported interval is log-scale, c exp(+/- t se / c): positive and
        # asymmetric, as a chronaxie is, and better calibrated than c +/- t se at the
        # 10-20 % noise the Phase 7b review measured (ledger 183, user decision L).
        interval = _log_interval(chronaxie, chronaxie_se, dof)
        # An interval with no finite upper end, or one wider than VACUOUS_RATIO, printed
        # as "95 % CI 0-inf us": it does not bound the chronaxie. Withheld, with the
        # reason, as rule A is (ledger 193, user decision a).
        if interval is not None and (
            not math.isfinite(interval[1])
            or interval[0] <= 0
            or interval[1] > VACUOUS_RATIO * interval[0]
        ):
            note = (
                f"the chronaxie's 95 % interval ({interval[0]:.4g}-{interval[1]:.4g} us) "
                f"spans more than {VACUOUS_RATIO:g}x, so it does not bound the chronaxie. "
                f"Include widths near the chronaxie"
            )
            rheobase_se = chronaxie_se = None
            interval = None
    if interval is not None:
        span = float(w.max() / w.min())
        if span < NARROW_SPAN:
            caveat = (
                f"narrow design (width span {span:.3g}x < {NARROW_SPAN:g}x): measured "
                f"coverage of this interval can be far below nominal"
            )

    return StrengthDurationFit(
        model="lapicque",
        rheobase_uA=rheobase,
        chronaxie_us=chronaxie,
        membrane_tau_us=tau,
        rss=residual,
        n_points=int(w.size),
        rheobase_se_uA=rheobase_se,
        chronaxie_se_us=chronaxie_se,
        chronaxie_ci95_us=interval,
        uncertainty_note=note,
        coverage_caveat=caveat,
    )


IDENTIFIABILITY_RCOND = math.sqrt(np.finfo(float).eps)
"""Smallest ratio of the relative-sensitivity Jacobian's singular values at which the
Lapicque covariance is taken as estimable: the usual numerical-rank cut for least
squares, below which the pseudo-inverse ``curve_fit`` returns reports zero variance for
a direction the data cannot see (ledger 178)."""


def _unidentifiable_note(w: np.ndarray, rheobase: float, tau: float) -> str:
    """A reason the Lapicque covariance cannot be trusted at this design, or ``""``.

    With every width far above the chronaxie, ``I = R / (1 - exp(-W/tau))`` is flat at
    the rheobase and does not depend on ``tau``: its column of the Jacobian underflows
    to zero, and ``curve_fit``'s covariance then reports an SE of 0 for exactly the
    parameter the data say nothing about. The Phase 6/7 review measured widths 2-8 ms at
    5 % noise: 124 of 246 accepted fits with a near-zero SE, CI coverage 0.41.
    """
    x = w / tau
    decay = np.exp(-x)
    denominator = -np.expm1(-x)
    # Relative sensitivities d ln I / d ln R and d ln I / d ln tau, one row per width.
    jac = np.column_stack([np.ones_like(w), -x * decay / denominator])
    s = np.linalg.svd(jac, compute_uv=False)
    if s[-1] > IDENTIFIABILITY_RCOND * s[0]:
        return ""
    return (
        f"the chronaxie is not identifiable from this design: every width "
        f"({float(w.min()):.4g} us and up) is far above the fitted chronaxie "
        f"({chronaxie_from_tau_us(tau):.3g} us), so the thresholds do not depend on it. "
        f"Include widths near the chronaxie"
    )


def _check_positive(name: str, value: float) -> None:
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and > 0, got {value!r}")
