"""Extract electrode parameters from a measured voltage transient.

This is the measurement that replaces the literature. Every charge-injection limit in
this package was obtained this way by its original authors, and Rose & Robblee say so
plainly: "the only certain way to determine a particular electrode's reversible charge
injection limit is by measurement of its potential excursions."

The method
----------
Drive a constant-current pulse and record the electrode potential against a reference.
The trace has two parts that must be separated:

- an **access voltage** ``V_a``, the ohmic ``iR`` drop through the electrolyte. It
  appears and disappears instantaneously with the current step, and is *not* part of the
  electrode potential.
- a **polarisation**, the interfacial excursion that accumulates during the pulse. This
  is what must stay inside the water window.

Subtracting ``V_a`` from the peak gives the true maximum polarisation, which is what
Rose & Robblee plot and what defines the charge-injection limit. Failing to subtract it
overestimates the excursion, and the size of the error grows with electrolyte resistance
-- Cogan notes that naive compensation for access resistance "may create hazards".

What this gives you
-------------------
Three numbers the package otherwise has to assume:

- **access resistance**, replacing the geometric estimate and the tissue-conductivity
  choice that dominates the sensitivity analysis;
- **interfacial capacitance**, replacing the value derived from a published CIC;
- **your own charge-injection limit**, via :func:`charge_injection_limit_uC_cm2`,
  replacing the literature value entirely.

Conventions and limits
----------------------
Sign convention follows the recorded trace: a cathodic-first pulse produces a negative
excursion. Both are handled by magnitude.

The access voltage is estimated from the step immediately after current onset. That
requires the sampling interval to resolve it -- Rose & Robblee used 0.9 us resolution on
a 0.2 ms pulse. Too coarse a trace will fold part of the polarisation into ``V_a`` and
understate the excursion, so :class:`TransientResult` reports the number of samples the
estimate rested on.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class TransientResult:
    """Electrode parameters extracted from one measured pulse."""

    current_uA: float
    pulse_width_us: float
    area_cm2: float
    access_voltage_V: float
    peak_potential_V: float
    max_polarisation_V: float
    resting_potential_V: float
    samples_in_access_estimate: int
    sample_interval_us: float

    @property
    def access_resistance_ohm(self) -> float:
        """``V_a / I`` -- the measured ohmic path, replacing the geometric estimate."""
        return abs(self.access_voltage_V) / (abs(self.current_uA) * 1e-6)

    @property
    def charge_density_uC_cm2(self) -> float:
        """Charge density delivered by this pulse."""
        return (
            abs(self.current_uA) * self.pulse_width_us * 1e-6 / self.area_cm2
        )

    @property
    def effective_capacitance_uF_cm2(self) -> float:
        """``(Q/A) / dV`` -- the interfacial capacitance this electrode actually shows.

        Compare against the value :mod:`neurostim.safety.water_window` derives from the
        published limit. A large disagreement means the literature electrode is not
        yours.
        """
        if self.max_polarisation_V <= 0:
            return math.inf
        return self.charge_density_uC_cm2 / self.max_polarisation_V

    @property
    def access_estimate_is_well_resolved(self) -> bool:
        """Whether enough samples supported the access-voltage step estimate.

        Fewer than three samples inside the first 2 % of the pulse means the trace is
        too coarse to separate the ohmic step from the polarisation cleanly.
        """
        return self.samples_in_access_estimate >= 3

    def describe(self) -> str:
        """Multi-line summary."""
        lines = [
            "Measured voltage transient",
            f"  pulse           {self.current_uA:g} uA x {self.pulse_width_us:g} us "
            f"on {self.area_cm2:.4g} cm^2",
            f"  charge density  {self.charge_density_uC_cm2:.4g} uC/cm^2",
            f"  access voltage  {self.access_voltage_V:+.4f} V "
            f"-> R_access {self.access_resistance_ohm:.0f} ohm",
            f"  peak potential  {self.peak_potential_V:+.4f} V",
            f"  polarisation    {self.max_polarisation_V:.4f} V "
            f"(peak minus access, from a resting {self.resting_potential_V:+.4f} V)",
            f"  C_eff           {self.effective_capacitance_uF_cm2:.1f} uF/cm^2",
        ]
        if not self.access_estimate_is_well_resolved:
            lines.append(
                f"  CAUTION: access voltage estimated from only "
                f"{self.samples_in_access_estimate} sample(s) at "
                f"{self.sample_interval_us:g} us resolution. Part of the polarisation "
                f"may be folded into it, which understates the excursion."
            )
        return "\n".join(lines)


def analyse(
    time_us: np.ndarray,
    voltage_V: np.ndarray,
    *,
    current_uA: float,
    pulse_width_us: float,
    area_cm2: float,
    pulse_start_us: float = 0.0,
    access_window_fraction: float = 0.02,
) -> TransientResult:
    """Separate access voltage from polarisation in a measured transient.

    Parameters
    ----------
    time_us, voltage_V:
        The recorded trace. ``voltage_V`` is the electrode potential against the
        reference, not the compliance voltage across the whole circuit.
    pulse_start_us:
        When the current step begins, in the trace's own time base.
    access_window_fraction:
        Fraction of the pulse width over which the ohmic step is taken to be complete.
        The default of 2 % follows the usual practice of reading ``V_a`` immediately
        after onset, before appreciable interfacial charging.
    """
    t = np.asarray(time_us, dtype=float)
    v = np.asarray(voltage_V, dtype=float)
    if t.shape != v.shape:
        raise ValueError(
            f"time_us and voltage_V must have the same shape, got {t.shape} and {v.shape}"
        )
    if t.size < 4:
        raise ValueError(f"need at least 4 samples, got {t.size}")
    if pulse_width_us <= 0:
        raise ValueError(f"pulse_width_us must be > 0, got {pulse_width_us!r}")
    if area_cm2 <= 0:
        raise ValueError(f"area_cm2 must be > 0, got {area_cm2!r}")
    if not 0 < access_window_fraction < 1:
        raise ValueError(
            f"access_window_fraction must be in (0, 1), got {access_window_fraction!r}"
        )

    pre = t < pulse_start_us
    resting = float(np.mean(v[pre])) if np.any(pre) else 0.0

    during = (t >= pulse_start_us) & (t <= pulse_start_us + pulse_width_us)
    if not np.any(during):
        raise ValueError(
            "no samples fall inside the pulse; check pulse_start_us and the time base"
        )

    access_end = pulse_start_us + access_window_fraction * pulse_width_us
    access_mask = (t >= pulse_start_us) & (t <= access_end)
    n_access = int(np.count_nonzero(access_mask))
    if n_access == 0:
        # Trace too coarse to resolve the window; fall back to the first in-pulse sample.
        first = int(np.argmax(during))
        access_voltage = float(v[first] - resting)
        n_access = 1
    else:
        access_voltage = float(np.mean(v[access_mask]) - resting)

    # Peak is the largest excursion from rest in the direction the pulse drives.
    excursions = v[during] - resting
    peak_index = int(np.argmax(np.abs(excursions)))
    peak_excursion = float(excursions[peak_index])
    peak_potential = float(v[during][peak_index])

    polarisation = abs(peak_excursion) - abs(access_voltage)
    interval = float(np.median(np.diff(t))) if t.size > 1 else math.nan

    return TransientResult(
        current_uA=current_uA,
        pulse_width_us=pulse_width_us,
        area_cm2=area_cm2,
        access_voltage_V=access_voltage,
        peak_potential_V=peak_potential,
        max_polarisation_V=max(polarisation, 0.0),
        resting_potential_V=resting,
        samples_in_access_estimate=n_access,
        sample_interval_us=interval,
    )


def charge_injection_limit_uC_cm2(
    result: TransientResult, water_window_limit_V: float
) -> float:
    """Extrapolate this electrode's charge-injection limit from one measured pulse.

    Scales the measured charge density by the ratio of available potential to the
    polarisation actually produced, which assumes the interface stays linear between the
    two. That assumption is good for a capacitive electrode and optimistic for a strongly
    faradaic one, where the response flattens as reactions saturate.

    Measure at several charge densities and check the polarisation really is
    proportional before relying on a single-pulse extrapolation.
    """
    if result.max_polarisation_V <= 0:
        raise ValueError(
            "no polarisation was resolved in this transient; cannot extrapolate a limit"
        )
    available = abs(water_window_limit_V - result.resting_potential_V)
    return result.charge_density_uC_cm2 * available / result.max_polarisation_V
