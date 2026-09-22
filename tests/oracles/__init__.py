"""Independently written expected values.

The characteristic failure of this test suite is not that tests are missing. It is that
tests pass for the wrong reason. The audit found fifteen tautologies, of which two were
sitting directly on top of shipped defects and asserting them:

* ``test_required_voltage_is_ohmic_plus_polarisation`` asserts
  ``required_V == ohmic_drop_V + polarisation_V`` against a line that literally constructs
  ``required_V = ohmic + polar``. It is ``a == a``, and it is the test that should have
  caught "compliance models one interface, not two".
* ``test_limiting_mechanism_matches_limiting_current`` asserts the limiting current equals
  ``min(shannon, charge, compliance)`` against a line computing exactly that minimum over
  exactly those three. It restates the bug it should have caught: that four further
  computed limits are excluded from the candidate set.

A test can only fail for the right reason if its expected value comes from somewhere the
code under test cannot reach. That is what this package is for.

The rule
--------
**An oracle may never be computed by calling the function it will be used to check.**

Each module here derives its answer from the physics, from a published constant, or from a
numerical method that shares no code with the package:

``fail_ceiling``
    Binary search over amplitude, reading nothing but ``assess().failed`` -- the set of
    checks in a FAIL state. It never reads ``limiting_current_uA``, ``margin``, or any
    other quantity it is used to check. The monotonicity bisection needs is sampled across
    the whole bracket before the search runs, so a predicate that breaks it raises
    ``NonMonotonePredicate`` instead of returning the edge of one passing band -- the
    invariant is held per check, which catches a passing band narrower than one probe
    step. ``names``
    restricts the predicate to a set of checks -- ``LIMIT_BEARING`` for the quantity
    ledger 84's D3(i) names -- and that set is written out here rather than imported from
    the package that also defines it.
``disc_field``
    The exact half-space disc solution ``V(r) = (2/pi) I R arcsin(a/r)``, a closed form
    from the literature, evaluated with the standard library alone. ``disc_potential_V``
    takes the conductivity and derives R itself, so a pin cannot be handed the resistance
    it is meant to be checking.
``drift``
    A pulse-by-pulse accumulation loop, which reproduces the closed form to within the
    duration of one pulse without ever evaluating it.
``fd_band``
    A converged finite-difference Laplace solve, from a generator committed at
    ``scripts/fd_band_reference.py`` that imports no part of ``neurostim``.

``tests/test_oracles.py`` pins every one of them to a constant computed by hand, so an
oracle that silently starts agreeing with the code is itself caught.
"""

from .disc_field import disc_potential_V, disc_surface_potential_V
from .drift import drift_time_s, drift_time_s_closed_form
from .fail_ceiling import (
    LIMIT_BEARING,
    NonMonotonePredicate,
    amplitude_independent_failures,
    brackets_the_ceiling,
    fail_ceiling_uA,
    no_check_fails,
)
from .fd_band import CLINICAL_DBS_ASPECT, FD_BAND_REFERENCE

__all__ = [
    "CLINICAL_DBS_ASPECT",
    "FD_BAND_REFERENCE",
    "LIMIT_BEARING",
    "NonMonotonePredicate",
    "amplitude_independent_failures",
    "brackets_the_ceiling",
    "disc_potential_V",
    "disc_surface_potential_V",
    "drift_time_s",
    "drift_time_s_closed_form",
    "fail_ceiling_uA",
    "no_check_fails",
]
