"""
PyBullet physics engine wrapper for PRISM-HJ.

.. note::
    **LEGACY COMPATIBILITY SHIM** — This module wraps PyBullet for general
    numerical integration and serves as the fallback solver for scenario types
    not handled by the analytic solvers.  It has no equivalent in the new
    execution core yet.

    Frozen in P0.  Will be superseded once ``Scheduler`` provides a general
    numerical fallback path.  Do not extend this module with new scenario logic.

Runs in DIRECT (headless) mode – no GUI, fully deterministic.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
import pybullet as p
import pybullet_data

from src.schema.psdl import BoundaryType, ParticleObject, PSDL, SpaceBox

logger = logging.getLogger(__name__)


class PhysicsSimulator:
    """
    Thin wrapper around PyBullet providing PSDL-aware methods.

    Usage::

        sim = PhysicsSimulator(gravity=[0, 0, -9.8], dt=0.01)
        sim.add_plane()
        body_id = sim.add_particle(particle_obj)
        sim.step(steps=100, space=space_box)
        states = sim.get_particle_states()
        sim.close()
    """

    def __init__(
        self,
        gravity: List[float] = None,
        dt: float = 0.01,
    ) -> None:
        """Connect to PyBullet (DIRECT mode) and configure basic settings."""
        if gravity is None:
            gravity = [0.0, 0.0, -9.8]
        self._client = p.connect(p.DIRECT)
        p.setAdditionalSearchPath(pybullet_data.getDataPath(), physicsClientId=self._client)
        p.setGravity(*gravity, physicsClientId=self._client)
        p.setTimeStep(dt, physicsClientId=self._client)
        self._dt = dt
        self._particle_ids: List[int] = []
        logger.debug("PhysicsSimulator initialised (gravity=%s, dt=%s)", gravity, dt)

    # ------------------------------------------------------------------
    # Scene construction
    # ------------------------------------------------------------------

    def add_plane(self, position: Tuple[float, float, float] = (0.0, 0.0, -0.5)) -> int:
        """
        Load the standard ground plane.

        Parameters
        ----------
        position:
            Where to place the plane centre. Default is slightly below the
            world origin so free-falling objects don't clip through at t=0.

        Returns
        -------
        int
            PyBullet body ID of the plane.
        """
        plane_id = p.loadURDF(
            "plane.urdf",
            basePosition=position,
            physicsClientId=self._client,
        )
        logger.debug("Ground plane added at %s (id=%d)", position, plane_id)
        return plane_id

    def add_particle(self, obj: ParticleObject) -> int:
        """
        Create a spherical rigid body from a :class:`ParticleObject`.

        Parameters
        ----------
        obj:
            Pydantic model describing the particle.

        Returns
        -------
        int
            PyBullet body ID.
        """
        collision_shape = p.createCollisionShape(
            p.GEOM_SPHERE,
            radius=obj.radius,
            physicsClientId=self._client,
        )
        visual_shape = p.createVisualShape(
            p.GEOM_SPHERE,
            radius=obj.radius,
            rgbaColor=[0.2, 0.6, 1.0, 1.0],
            physicsClientId=self._client,
        )
        body_id = p.createMultiBody(
            baseMass=obj.mass,
            baseCollisionShapeIndex=collision_shape,
            baseVisualShapeIndex=visual_shape,
            basePosition=obj.position,
            baseOrientation=p.getQuaternionFromEuler([0, 0, 0]),
            physicsClientId=self._client,
        )
        # Set initial velocity
        p.resetBaseVelocity(
            body_id,
            linearVelocity=obj.velocity,
            angularVelocity=[0, 0, 0],
            physicsClientId=self._client,
        )
        # Configure restitution (bounciness) and disable artificial damping so
        # that free-fall and other ideal scenarios match the analytical solution.
        p.changeDynamics(
            body_id,
            -1,
            restitution=obj.restitution,
            linearDamping=0.0,
            angularDamping=0.0,
            physicsClientId=self._client,
        )
        self._particle_ids.append(body_id)
        logger.debug(
            "Particle added: id=%d mass=%.3f pos=%s vel=%s",
            body_id, obj.mass, obj.position, obj.velocity,
        )
        return body_id

    # ------------------------------------------------------------------
    # Shape helpers (reserved for future polygon / cylinder support)
    # ------------------------------------------------------------------

    def add_box(
        self,
        half_extents: List[float],
        mass: float,
        position: List[float],
        velocity: Optional[List[float]] = None,
        restitution: float = 0.9,
    ) -> int:
        """Reserved: create a box-shaped rigid body."""
        collision_shape = p.createCollisionShape(
            p.GEOM_BOX,
            halfExtents=half_extents,
            physicsClientId=self._client,
        )
        body_id = p.createMultiBody(
            baseMass=mass,
            baseCollisionShapeIndex=collision_shape,
            basePosition=position,
            physicsClientId=self._client,
        )
        if velocity:
            p.resetBaseVelocity(body_id, linearVelocity=velocity, physicsClientId=self._client)
        p.changeDynamics(body_id, -1, restitution=restitution, physicsClientId=self._client)
        self._particle_ids.append(body_id)
        return body_id

    def add_cylinder(
        self,
        radius: float,
        height: float,
        mass: float,
        position: List[float],
        velocity: Optional[List[float]] = None,
        restitution: float = 0.9,
    ) -> int:
        """Reserved: create a cylindrical rigid body."""
        collision_shape = p.createCollisionShape(
            p.GEOM_CYLINDER,
            radius=radius,
            height=height,
            physicsClientId=self._client,
        )
        body_id = p.createMultiBody(
            baseMass=mass,
            baseCollisionShapeIndex=collision_shape,
            basePosition=position,
            physicsClientId=self._client,
        )
        if velocity:
            p.resetBaseVelocity(body_id, linearVelocity=velocity, physicsClientId=self._client)
        p.changeDynamics(body_id, -1, restitution=restitution, physicsClientId=self._client)
        self._particle_ids.append(body_id)
        return body_id

    # ------------------------------------------------------------------
    # Boundary enforcement
    # ------------------------------------------------------------------

    def apply_boundary(self, space: SpaceBox) -> None:
        """
        Enforce spatial boundaries on all tracked particles.

        For each axis (x, y, z):
          - **elastic**: reflect the velocity component and clamp position.
          - **absorbing**: zero the velocity component and clamp position.
          - **periodic**: wrap position to the opposite side (reserved).
        """
        low = np.array(space.min)
        high = np.array(space.max)

        for body_id in self._particle_ids:
            pos, orn = p.getBasePositionAndOrientation(body_id, physicsClientId=self._client)
            vel, ang = p.getBaseVelocity(body_id, physicsClientId=self._client)

            pos = np.array(pos)
            vel = np.array(vel)
            modified = False

            for axis in range(3):
                if pos[axis] < low[axis]:
                    pos[axis] = low[axis]
                    modified = True
                    if space.boundary_type == BoundaryType.elastic:
                        vel[axis] = abs(vel[axis])
                    elif space.boundary_type == BoundaryType.absorbing:
                        vel[axis] = 0.0
                    # periodic: wrap (reserved)
                    elif space.boundary_type == BoundaryType.periodic:
                        pos[axis] = high[axis]

                elif pos[axis] > high[axis]:
                    pos[axis] = high[axis]
                    modified = True
                    if space.boundary_type == BoundaryType.elastic:
                        vel[axis] = -abs(vel[axis])
                    elif space.boundary_type == BoundaryType.absorbing:
                        vel[axis] = 0.0
                    elif space.boundary_type == BoundaryType.periodic:
                        pos[axis] = low[axis]

            if modified:
                p.resetBasePositionAndOrientation(
                    body_id, pos.tolist(), orn, physicsClientId=self._client
                )
                p.resetBaseVelocity(
                    body_id,
                    linearVelocity=vel.tolist(),
                    angularVelocity=list(ang),
                    physicsClientId=self._client,
                )

    # ------------------------------------------------------------------
    # Simulation loop
    # ------------------------------------------------------------------

    def step(self, steps: int, space: SpaceBox) -> None:
        """
        Advance the simulation by *steps* time steps.

        After each :func:`p.stepSimulation` call the boundary conditions are
        applied so that no particle ever escapes the simulation volume.
        """
        for _ in range(steps):
            p.stepSimulation(physicsClientId=self._client)
            self.apply_boundary(space)

    # ------------------------------------------------------------------
    # State retrieval
    # ------------------------------------------------------------------

    def get_particle_states(self) -> List[Dict]:
        """
        Return a list of state dicts for every tracked particle.

        Each dict has keys ``position`` and ``velocity``, both as
        ``List[float]`` rounded to 6 decimal places.
        """
        states = []
        for body_id in self._particle_ids:
            pos, _ = p.getBasePositionAndOrientation(body_id, physicsClientId=self._client)
            vel, _ = p.getBaseVelocity(body_id, physicsClientId=self._client)
            states.append(
                {
                    "position": [round(v, 6) for v in pos],
                    "velocity": [round(v, 6) for v in vel],
                }
            )
        return states

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Disconnect from the PyBullet physics server."""
        p.disconnect(physicsClientId=self._client)
        logger.debug("PhysicsSimulator disconnected.")


# ---------------------------------------------------------------------------
# Convenience top-level function
# ---------------------------------------------------------------------------

def simulate_psdl(psdl: PSDL) -> List[Dict]:
    """
    End-to-end simulation from a :class:`PSDL` document.

    Steps
    -----
    1. Create a :class:`PhysicsSimulator` with the world's gravity and dt.
    2. Add a ground plane **only** if ``psdl.world.ground_plane`` is ``True``.
    3. Add all :class:`ParticleObject` instances in ``psdl.objects``.
    4. Run ``psdl.world.steps`` simulation steps.
    5. Retrieve and return final particle states.
    6. Close the simulator.

    Ground-plane policy
    -------------------
    The execution layer **never** adds a ground plane implicitly.  Callers
    that need a floor must set ``psdl.world.ground_plane = True`` in the PSDL
    document.  This makes the physical assumption explicit and auditable at
    the contract layer.

    Parameters
    ----------
    psdl:
        Validated PSDL document.

    Returns
    -------
    List[Dict]
        Final ``{"position": [...], "velocity": [...]}`` for each particle.
    """
    sim = PhysicsSimulator(
        gravity=psdl.world.gravity,
        dt=psdl.world.dt,
    )
    try:
        if psdl.world.ground_plane:
            sim.add_plane()

        for obj in psdl.objects:
            if isinstance(obj, ParticleObject):
                sim.add_particle(obj)
            # CircuitPort and FieldObject are not simulated in PyBullet (yet)

        sim.step(steps=psdl.world.steps, space=psdl.world.space)
        return sim.get_particle_states()
    finally:
        sim.close()
