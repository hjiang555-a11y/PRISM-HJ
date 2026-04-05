"""
Analytic (closed-form) physics solvers — v0.1.

These solvers return *exact* results (subject to floating-point precision)
for scenarios where kinematic equations have a closed-form solution.
They are the preferred execution path whenever the dispatcher matches a
known scenario type; PyBullet is reserved for problems that require
numerical integration.

Currently supported
-------------------
* ``free_fall`` — 1-D vertical free fall under constant gravity, no drag.

Return format
-------------
All solvers return ``List[Dict]`` with the same schema used by the PyBullet
engine so that the dispatcher can treat both backends uniformly::

    [{"position": [x, y, z], "velocity": [vx, vy, vz]}, ...]
"""

from __future__ import annotations

import logging
from typing import Dict, List

from src.schema.psdl import ParticleObject, PSDL

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Free-fall solver
# ---------------------------------------------------------------------------

def solve_free_fall(psdl: PSDL) -> List[Dict]:
    """
    Exact kinematic solution for vertical free fall under constant gravity.

    Assumptions (must be satisfied by the caller / PSDL document):
    - Single particle (only the first :class:`ParticleObject` is processed).
    - No air resistance / drag.
    - Gravity is uniform and acts along the z-axis only.
    - No ground collision within the simulated time span.

    Equations
    ---------
    ::

        z(t)  = z₀ + v₀z · t − ½ · g · t²
        vz(t) = v₀z − g · t

    where ``t = dt × steps`` and ``g = |gravity[2]|``.

    Parameters
    ----------
    psdl:
        Validated PSDL document with ``scenario_type == "free_fall"``.

    Returns
    -------
    List[Dict]
        One entry per :class:`ParticleObject`:
        ``{"position": [x, y, z], "velocity": [vx, vy, vz]}``.

    Raises
    ------
    ValueError
        If no :class:`ParticleObject` is found in ``psdl.objects``.
    """
    particles = [obj for obj in psdl.objects if isinstance(obj, ParticleObject)]
    if not particles:
        raise ValueError(
            "solve_free_fall: PSDL contains no ParticleObject to simulate."
        )

    g_z = psdl.world.gravity[2]  # negative for downward gravity, e.g. -9.8
    t = psdl.world.dt * psdl.world.steps

    results: List[Dict] = []
    for particle in particles:
        x0, y0, z0 = particle.position
        vx0, vy0, vz0 = particle.velocity

        # Exact kinematics (no numerical integration error)
        z_final  = z0  + vz0 * t + 0.5 * g_z * t ** 2
        vz_final = vz0 + g_z * t

        # Horizontal components are unchanged (no horizontal force)
        x_final  = x0  + vx0 * t
        y_final  = y0  + vy0 * t
        vx_final = vx0
        vy_final = vy0

        state = {
            "position": [
                round(x_final,  6),
                round(y_final,  6),
                round(z_final,  6),
            ],
            "velocity": [
                round(vx_final, 6),
                round(vy_final, 6),
                round(vz_final, 6),
            ],
        }
        results.append(state)
        logger.debug(
            "solve_free_fall: t=%.4fs  z0=%.4f → z=%.6f  vz0=%.4f → vz=%.6f",
            t, z0, z_final, vz0, vz_final,
        )

    return results
