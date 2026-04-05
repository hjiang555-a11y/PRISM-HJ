"""
ValidationTarget auto-execution infrastructure — v0.3.

This module provides a standalone runner that evaluates all
:class:`~src.schema.psdl.ValidationTarget` entries in a PSDL document
against the actual simulation results.

Usage::

    from src.validation.runner import run_validation
    results = run_validation(psdl, states)
    for r in results:
        print(r["target"], "PASS" if r["passed"] else "FAIL", r["message"])

Design notes
------------
* The runner is intentionally decoupled from both the dispatcher and the
  physics engine so it can be called from any layer.
* Value extraction uses a *name-based* mapping: target names like
  ``"final_z"`` or ``"final_vz"`` are resolved against the first particle's
  final position/velocity.  This covers v0.1 free-fall scenarios; new names
  can be added to :data:`_EXTRACTORS` as the template library grows.
* Derived metrics (``max_height``, ``range``, ``time_of_flight``) are
  registered in :data:`_PSDL_EXTRACTORS` — they require PSDL initial
  conditions in addition to the final states, so their extractor signature
  is ``(psdl: PSDL, states: List[Dict]) -> Optional[float]``.
* The runner never raises on extraction failure — it sets ``passed=False``
  and records an informative message.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from src.schema.psdl import PSDL, ParticleObject, ValidationTarget
from src.schema.units import validate_unit_for_dimension, Dimension

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Value extractors
# ---------------------------------------------------------------------------
# Each extractor is a callable  (states: List[Dict]) -> Optional[float].
# ``states`` is the list returned by the dispatcher / engine:
#   [{"position": [x, y, z], "velocity": [vx, vy, vz]}, ...]
#
# Naming convention: final_<component> for position/velocity of particle 0.

_Extractor = Callable[[List[Dict]], Optional[float]]


def _make_pos_extractor(axis: int) -> _Extractor:
    def _extract(states: List[Dict]) -> Optional[float]:
        if not states:
            return None
        pos = states[0].get("position")
        if pos is None or len(pos) <= axis:
            return None
        return float(pos[axis])
    return _extract


def _make_vel_extractor(axis: int) -> _Extractor:
    def _extract(states: List[Dict]) -> Optional[float]:
        if not states:
            return None
        vel = states[0].get("velocity")
        if vel is None or len(vel) <= axis:
            return None
        return float(vel[axis])
    return _extract


# Registry of known target names → extractor functions.
# Extend this dict when new scenario types introduce new target names.
_EXTRACTORS: Dict[str, _Extractor] = {
    "final_x":  _make_pos_extractor(0),
    "final_y":  _make_pos_extractor(1),
    "final_z":  _make_pos_extractor(2),
    "final_vx": _make_vel_extractor(0),
    "final_vy": _make_vel_extractor(1),
    "final_vz": _make_vel_extractor(2),
}


# ---------------------------------------------------------------------------
# PSDL-aware derived metric extractors
# ---------------------------------------------------------------------------
# These extractors need both the PSDL document (for initial conditions) and
# the final states from the solver.  Their signature is:
#   (psdl: PSDL, states: List[Dict]) -> Optional[float]
#
# Currently supported derived metrics
# ------------------------------------
# max_height       — peak height (z) reached during the trajectory (m)
# range            — net horizontal displacement x_final − x₀ (m)
# time_of_flight   — total simulated flight time dt × steps (s)

_PSDLExtractor = Callable[["PSDL", List[Dict]], Optional[float]]


def _extract_max_height(psdl: PSDL, states: List[Dict]) -> Optional[float]:
    """
    Analytic peak height for the first particle.

    Formula
    -------
    * If v₀z > 0:  z_max = z₀ + v₀z² / (2 · |g_z|)
    * Otherwise:   z_max = z₀  (object is already falling)

    Applies to both ``free_fall`` and ``projectile`` (horizontal throw has
    v₀z = 0, so max_height equals the initial height).
    """
    particles = [obj for obj in psdl.objects if isinstance(obj, ParticleObject)]
    if not particles:
        return None
    p = particles[0]
    z0 = p.position[2]
    v0z = p.velocity[2]
    g_z = psdl.world.gravity[2]   # negative for downward gravity
    g_mag = abs(g_z)
    if g_mag == 0.0:
        return float(z0)
    if v0z > 0.0:
        return float(z0 + v0z ** 2 / (2.0 * g_mag))
    return float(z0)


def _extract_range(psdl: PSDL, states: List[Dict]) -> Optional[float]:
    """
    Horizontal range: x_final − x₀.

    Returns 0 for pure vertical scenarios (v₀x = 0, e.g. ``free_fall``).
    Requires at least one entry in *states*.
    """
    if not states:
        return None
    particles = [obj for obj in psdl.objects if isinstance(obj, ParticleObject)]
    x0 = float(particles[0].position[0]) if particles else 0.0
    pos = states[0].get("position")
    if pos is None or len(pos) < 1:
        return None
    return float(pos[0]) - x0


def _extract_time_of_flight(psdl: PSDL, states: List[Dict]) -> Optional[float]:
    """
    Total simulated flight time: dt × steps.

    This equals the simulation duration specified in the PSDL world settings.
    """
    return float(psdl.world.dt * psdl.world.steps)


_PSDL_EXTRACTORS: Dict[str, _PSDLExtractor] = {
    "max_height":       _extract_max_height,
    "range":            _extract_range,
    "time_of_flight":   _extract_time_of_flight,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_validation(
    psdl: PSDL,
    states: List[Dict],
) -> List[Dict[str, Any]]:
    """
    Evaluate all :class:`ValidationTarget` entries against *states*.

    Parameters
    ----------
    psdl:
        The PSDL document that produced *states*.  Its
        ``validation_targets`` list is iterated.
    states:
        Final particle states returned by the solver/dispatcher, i.e.
        ``[{"position": [x, y, z], "velocity": [vx, vy, vz]}, ...]``.

    Returns
    -------
    List[Dict]
        One result dict per target, each with keys:

        ``target``
            Name of the :class:`ValidationTarget` (e.g. ``"final_z"``).
        ``passed``
            ``True`` if the observed value is within tolerance.
        ``observed``
            The extracted value (``None`` if extraction failed).
        ``expected``
            The expected value from the PSDL.
        ``unit``
            SI unit symbol from the PSDL target.
        ``tolerance``
            Tolerance percentage from the PSDL target.
        ``message``
            Human-readable pass/fail detail.
    """
    results: List[Dict[str, Any]] = []

    for target in psdl.validation_targets:
        result = _evaluate_target(target, states, psdl)
        results.append(result)
        level = logging.INFO if result["passed"] else logging.WARNING
        logger.log(level, "validation %s: %s", target.name, result["message"])

    _log_summary(results)
    return results


def _evaluate_target(
    target: ValidationTarget,
    states: List[Dict],
    psdl: Optional[PSDL] = None,
) -> Dict[str, Any]:
    """Evaluate a single :class:`ValidationTarget`."""
    observed: Optional[float] = None
    passed = False
    message = ""

    extractor = _EXTRACTORS.get(target.name)
    psdl_extractor = _PSDL_EXTRACTORS.get(target.name)

    if extractor is None and psdl_extractor is None:
        message = (
            f"No extractor registered for target {target.name!r}. "
            "Cannot evaluate."
        )
        return _result(target, passed=False, observed=None, message=message)

    try:
        if psdl_extractor is not None and psdl is not None:
            observed = psdl_extractor(psdl, states)
        elif extractor is not None:
            observed = extractor(states)
        else:
            message = (
                f"Derived metric {target.name!r} requires PSDL context "
                "but none was provided."
            )
            return _result(target, passed=False, observed=None, message=message)
    except (KeyError, TypeError, IndexError, ValueError) as exc:
        message = f"Extraction error for {target.name!r}: {exc}"
        return _result(target, passed=False, observed=None, message=message)

    if observed is None:
        message = (
            f"Could not extract value for {target.name!r} from states "
            f"(states list length: {len(states)})."
        )
        return _result(target, passed=False, observed=None, message=message)

    # Unit/dimension sanity check (non-fatal — warns but does not fail target)
    if target.unit and target.dimension:
        try:
            validate_unit_for_dimension(target.unit, Dimension(target.dimension))
        except (ValueError, KeyError) as exc:
            logger.warning(
                "Unit/dimension check failed for %s: %s", target.name, exc
            )

    passed = target.check(observed)

    if passed:
        message = (
            f"PASS — observed={observed:.6g} {target.unit}, "
            f"expected={target.expected_value:.6g} {target.unit}, "
            f"tol={target.tolerance_pct}%"
        )
    else:
        if target.expected_value != 0.0:
            actual_pct = (
                abs(observed - target.expected_value)
                / abs(target.expected_value)
                * 100.0
            )
            message = (
                f"FAIL — observed={observed:.6g} {target.unit}, "
                f"expected={target.expected_value:.6g} {target.unit}, "
                f"deviation={actual_pct:.2f}% (tolerance={target.tolerance_pct}%)"
            )
        else:
            message = (
                f"FAIL — observed={observed:.6g} {target.unit}, "
                f"expected=0 {target.unit}, "
                f"deviation={abs(observed):.6g} (tolerance={target.tolerance_pct}%)"
            )

    return _result(target, passed=passed, observed=observed, message=message)


def _result(
    target: ValidationTarget,
    *,
    passed: bool,
    observed: Optional[float],
    message: str,
) -> Dict[str, Any]:
    return {
        "target": target.name,
        "passed": passed,
        "observed": observed,
        "expected": target.expected_value,
        "unit": target.unit,
        "tolerance": target.tolerance_pct,
        "message": message,
    }


def _log_summary(results: List[Dict[str, Any]]) -> None:
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    if total == 0:
        logger.info("validation: no targets defined.")
        return
    logger.info(
        "validation summary: %d/%d passed%s",
        passed,
        total,
        "" if passed == total else f" — {total - passed} FAILED",
    )
