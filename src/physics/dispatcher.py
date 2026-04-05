"""
Solver dispatcher — v0.1.

The dispatcher is the entry-point for the *knowledge compiler* layer
(layer 3 in the four-layer architecture).  It inspects the PSDL
``scenario_type`` field and routes the document to the most appropriate
solver backend.

Routing table (v0.1)
--------------------
+----------------+-------------------------------------+
| scenario_type  | solver                              |
+================+=====================================+
| ``free_fall``  | :func:`analytic.solve_free_fall`    |
+----------------+-------------------------------------+
| ``None`` / any | :func:`engine.simulate_psdl`        |
| other value    | (PyBullet numerical integration)    |
+----------------+-------------------------------------+

Design notes
------------
* The dispatcher is intentionally thin: routing logic is a pure
  ``if/elif`` chain with no hidden state.
* Adding a new solver requires only one new ``elif`` branch plus the
  corresponding solver module.
* The analytic solver is always preferred when available because it
  is exact (no integration error) and does not require PyBullet.
"""

from __future__ import annotations

import logging
from typing import Dict, List

from src.schema.psdl import PSDL

logger = logging.getLogger(__name__)

# Solver identifiers exposed for introspection / testing.
SOLVER_ANALYTIC_FREE_FALL = "analytic_free_fall"
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
        from src.physics.analytic import solve_free_fall
        return solve_free_fall(psdl)

    # Default: PyBullet numerical integration
    from src.physics.engine import simulate_psdl
    return simulate_psdl(psdl)
