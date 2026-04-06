"""
Solver dispatcher — v0.2.

.. warning::
    **LEGACY / FROZEN** — This module implements the old ``scenario_type →
    solver`` routing anti-pattern.  It is frozen in P0 and will be deleted in
    a future iteration once ``main.py`` is ported to the new execution pipeline
    (``Scheduler`` + capability-driven rules).

    **Do not add new ``elif`` branches or new solver imports here.**
    New physics logic belongs in ``src/execution/rules/``.

The dispatcher is the entry-point for the *knowledge compiler* layer
(layer 3 in the four-layer architecture).  It inspects the PSDL
``scenario_type`` field and routes the document to the most appropriate
solver backend.

Routing table (v0.2)
--------------------
+-------------------+---------------------------------------------+
| scenario_type     | solver                                      |
+===================+=============================================+
| ``free_fall``     | :func:`analytic.solve_free_fall`            |
+-------------------+---------------------------------------------+
| ``projectile``    | :func:`analytic.solve_projectile`           |
+-------------------+---------------------------------------------+
| ``collision``     | :func:`analytic.solve_collision_1d_elastic` |
+-------------------+---------------------------------------------+
| ``None`` / any    | :func:`engine.simulate_psdl`                |
| other value       | (PyBullet numerical integration)            |
+-------------------+---------------------------------------------+

Design notes
------------
* The dispatcher is intentionally thin: routing logic is a pure
  ``if/elif`` chain with no hidden state.
* Adding a new solver requires only one new ``elif`` branch plus the
  corresponding solver module.
* The analytic solver is always preferred when available because it
  is exact (no integration error) and does not require PyBullet.
* :func:`dispatch_with_validation` extends :func:`dispatch` by also
  running the PSDL validation targets against the solver results and
  returning the ``solver_used`` identifier.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from src.schema.psdl import PSDL

logger = logging.getLogger(__name__)

# Solver identifiers exposed for introspection / testing.
SOLVER_ANALYTIC_FREE_FALL = "analytic_free_fall"
SOLVER_ANALYTIC_PROJECTILE = "analytic_projectile"
SOLVER_ANALYTIC_COLLISION_1D = "analytic_collision_1d_elastic"
SOLVER_PYBULLET = "pybullet"


def select_solver(psdl: PSDL) -> str:
    """
    Return the solver identifier that *dispatch* will use for *psdl*.

    This is a pure function (no side effects) and is exposed separately
    so that tests can verify routing without actually running a simulation.

    Parameters
    ----------
    psdl:
        Validated PSDL document.

    Returns
    -------
    str
        One of the ``SOLVER_*`` constants defined in this module.
    """
    scenario = (psdl.scenario_type or "").lower().strip()

    if scenario == "free_fall":
        return SOLVER_ANALYTIC_FREE_FALL

    if scenario == "projectile":
        return SOLVER_ANALYTIC_PROJECTILE

    if scenario == "collision":
        return SOLVER_ANALYTIC_COLLISION_1D

    # Default: fall back to PyBullet numerical integration
    return SOLVER_PYBULLET


def dispatch(psdl: PSDL) -> List[Dict]:
    """
    Route *psdl* to the appropriate solver and return the final particle states.

    Parameters
    ----------
    psdl:
        Validated PSDL document.

    Returns
    -------
    List[Dict]
        ``[{"position": [x, y, z], "velocity": [vx, vy, vz]}, ...]``

    Raises
    ------
    ValueError
        Propagated from the selected solver on bad input.
    """
    solver_id = select_solver(psdl)
    logger.info(
        "dispatcher: scenario_type=%r → solver=%s",
        psdl.scenario_type,
        solver_id,
    )

    if solver_id == SOLVER_ANALYTIC_FREE_FALL:
        from src.physics.legacy.analytic import solve_free_fall
        return solve_free_fall(psdl)

    if solver_id == SOLVER_ANALYTIC_PROJECTILE:
        from src.physics.legacy.analytic import solve_projectile
        return solve_projectile(psdl)

    if solver_id == SOLVER_ANALYTIC_COLLISION_1D:
        from src.physics.legacy.analytic import solve_collision_1d_elastic
        return solve_collision_1d_elastic(psdl)

    # Default: PyBullet numerical integration
    from src.physics.legacy.engine import simulate_psdl
    return simulate_psdl(psdl)


def dispatch_with_validation(psdl: PSDL) -> Dict[str, Any]:
    """
    Route *psdl* to the appropriate solver and run validation targets.

    This is the preferred entry point when you need both simulation
    results and a structured validation summary in one call.

    Parameters
    ----------
    psdl:
        Validated PSDL document.

    Returns
    -------
    Dict with keys:

    ``states``
        Final particle states (same as :func:`dispatch` return value).
    ``solver_used``
        Identifier of the solver that was selected (one of the
        ``SOLVER_*`` constants defined in this module).
    ``validation_results``
        List of per-target result dicts from
        :func:`~src.validation.runner.run_validation`.

    Raises
    ------
    ValueError
        Propagated from the selected solver on bad input.
    """
    solver_id = select_solver(psdl)
    states = dispatch(psdl)

    from src.validation.runner import run_validation
    validation_results = run_validation(psdl, states)

    return {
        "states": states,
        "solver_used": solver_id,
        "validation_results": validation_results,
    }

