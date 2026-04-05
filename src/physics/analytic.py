"""
Analytic (closed-form) physics solvers — v0.2.

These solvers return *exact* results (subject to floating-point precision)
for scenarios where kinematic equations have a closed-form solution.
They are the preferred execution path whenever the dispatcher matches a
known scenario type; PyBullet is reserved for problems that require
numerical integration.

Currently supported
-------------------
* ``free_fall``  — 1-D vertical free fall under constant gravity, no drag.
* ``projectile`` — horizontal throw under constant gravity, no drag.
* ``collision``  — 1-D elastic two-body collision (instantaneous, analytic).

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


# ---------------------------------------------------------------------------
# Projectile solver
# ---------------------------------------------------------------------------

def solve_projectile(psdl: PSDL) -> List[Dict]:
    """
    Exact kinematic solution for a horizontal-throw projectile scenario.

    Assumptions (must be satisfied by the caller / PSDL document):
    - Single particle (only the first :class:`ParticleObject` is processed).
    - No air resistance / drag.
    - Gravity is uniform and acts along the z-axis only.
    - No ground collision within the simulated time span.

    Equations
    ---------
    ::

        x(t)  = x₀ + v₀x · t
        z(t)  = z₀ + v₀z · t + ½ · g_z · t²
        vx(t) = v₀x  (constant)
        vz(t) = v₀z + g_z · t

    where ``t = dt × steps`` and ``g_z`` is the signed z-gravity component
    (negative for downward, e.g. −9.8 m/s²).

    Parameters
    ----------
    psdl:
        Validated PSDL document with ``scenario_type == "projectile"``.

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
            "solve_projectile: PSDL contains no ParticleObject to simulate."
        )

    g_z = psdl.world.gravity[2]  # signed (negative = downward)
    t = psdl.world.dt * psdl.world.steps

    results: List[Dict] = []
    for particle in particles:
        x0, y0, z0 = particle.position
        vx0, vy0, vz0 = particle.velocity

        # Exact kinematics (same equations as free_fall, but horizontal
        # velocity is non-zero for projectile scenarios)
        x_final  = x0  + vx0 * t
        y_final  = y0  + vy0 * t
        z_final  = z0  + vz0 * t + 0.5 * g_z * t ** 2
        vx_final = vx0
        vy_final = vy0
        vz_final = vz0 + g_z * t

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
            "solve_projectile: t=%.4fs  x0=%.4f → x=%.6f  z0=%.4f → z=%.6f"
            "  vx0=%.4f  vz0=%.4f → vz=%.6f",
            t, x0, x_final, z0, z_final, vx0, vz0, vz_final,
        )

    return results


# ---------------------------------------------------------------------------
# Collision solver (1-D elastic, two bodies)
# ---------------------------------------------------------------------------

def solve_collision_1d_elastic(psdl: PSDL) -> List[Dict]:
    """
    Exact analytic solution for a 1-D elastic two-body collision.

    Assumptions (must be satisfied by the caller / PSDL document):
    - Exactly two :class:`ParticleObject` entries (particle 0 = body 1,
      particle 1 = body 2).
    - Collision is along the x-axis; y and z components are unchanged.
    - Elastic: both momentum and kinetic energy are conserved.

    Equations
    ---------
    ::

        v1f = ((m1 − m2) · v1x + 2 · m2 · v2x) / (m1 + m2)
        v2f = ((m2 − m1) · v2x + 2 · m1 · v1x) / (m1 + m2)

    Parameters
    ----------
    psdl:
        Validated PSDL document with ``scenario_type == "collision"``.

    Returns
    -------
    List[Dict]
        Two entries (one per body):
        ``[{"position": [...], "velocity": [v1f, vy1, vz1]},
           {"position": [...], "velocity": [v2f, vy2, vz2]}]``.

    Raises
    ------
    ValueError
        If fewer than two :class:`ParticleObject` entries are found.
    """
    particles = [obj for obj in psdl.objects if isinstance(obj, ParticleObject)]
    if len(particles) < 2:
        raise ValueError(
            "solve_collision_1d_elastic: PSDL requires at least 2 "
            "ParticleObjects (got %d)." % len(particles)
        )

    p1, p2 = particles[0], particles[1]
    m1, m2 = p1.mass, p2.mass
    v1x, v2x = p1.velocity[0], p2.velocity[0]
    total_mass = m1 + m2

    v1f = ((m1 - m2) * v1x + 2.0 * m2 * v2x) / total_mass
    v2f = ((m2 - m1) * v2x + 2.0 * m1 * v1x) / total_mass

    logger.debug(
        "solve_collision_1d_elastic: m1=%.3f v1x=%.3f m2=%.3f v2x=%.3f"
        " → v1f=%.6f v2f=%.6f",
        m1, v1x, m2, v2x, v1f, v2f,
    )

    return [
        {
            "position": list(p1.position),
            "velocity": [
                round(v1f, 6),
                round(p1.velocity[1], 6),
                round(p1.velocity[2], 6),
            ],
        },
        {
            "position": list(p2.position),
            "velocity": [
                round(v2f, 6),
                round(p2.velocity[1], 6),
                round(p2.velocity[2], 6),
            ],
        },
    ]
