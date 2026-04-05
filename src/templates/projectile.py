"""
Projectile scenario template — v0.2.

:func:`build_psdl` constructs a PSDL v0.1 document for a general projectile
scenario: object launched at an arbitrary angle from a height, with no air
resistance and no ground collision within the simulated time span.

Supported launch modes
----------------------
* **Horizontal throw** (default): pass only ``v0x``; ``v0z`` defaults to 0.
* **Angled throw**: pass ``v0x`` and ``v0z`` directly, *or* pass ``v0`` (speed)
  and ``theta`` (launch angle above horizontal, in radians) — the template
  then computes ``v0x = v0 * cos(theta)`` and ``v0z = v0 * sin(theta)``.

The returned document includes:

* ``scenario_type = "projectile"``
* Explicit ``assumptions`` list
* Pre-computed ``validation_targets`` based on the exact kinematic solution
* Appropriate ``source_refs`` (defaults to OpenStax / MIT OCW)

This template is the authoritative source for projectile test fixtures.
"""

from __future__ import annotations

import math
from typing import List, Optional, Union

from src.schema.psdl import (
    BoundaryType,
    ParticleObject,
    PSDL,
    SourceRef,
    SpaceBox,
    ValidationTarget,
    WorldSettings,
)

scenario_type: str = "projectile"

# Default source references: tier_1_authoritative (OpenStax + MIT OCW).
# NIST / ITU are intentionally excluded — they govern unit definitions, not
# mechanics problem templates.
_DEFAULT_SOURCE_REFS: List[SourceRef] = [
    SourceRef(
        source_id="openstax_university_physics_v1",
        role="primary_template_source",
    ),
    SourceRef(
        source_id="mit_ocw_physics",
        role="secondary_reference",
    ),
]


def build_psdl(
    *,
    height: float = 5.0,
    v0x: float = 10.0,
    v0z: float = 0.0,
    v0: Optional[float] = None,
    theta: float = 0.0,
    mass: float = 1.0,
    radius: float = 0.1,
    g: float = 9.8,
    duration: float = 1.0,
    dt: float = 0.01,
    space_half_extent: float = 100.0,
    validation_tolerance_pct: float = 1.0,
    include_derived_metrics: bool = False,
    source_refs: List[Union[SourceRef, str]] | None = None,
) -> PSDL:
    """
    Build a PSDL document for a general projectile scenario.

    Parameters
    ----------
    height:
        Initial height above z=0 (m).  Default: 5.0 m.
    v0x:
        Initial horizontal velocity component (m/s).  Default: 10.0.
        Overridden when ``v0`` and ``theta`` are both provided.
    v0z:
        Initial vertical velocity component (m/s).  Default: 0.0
        (horizontal throw).  Overridden when ``v0`` and ``theta`` are both
        provided.
    v0:
        Initial speed magnitude (m/s).  When provided together with
        ``theta``, ``v0x`` and ``v0z`` are derived as
        ``v0 * cos(theta)`` and ``v0 * sin(theta)`` respectively.
    theta:
        Launch angle above the horizontal plane (radians).  Only used when
        ``v0`` is also provided.  ``theta = 0`` reproduces the horizontal
        throw (backward-compatible default).
    mass:
        Particle mass (kg).  Default: 1.0 kg.
    radius:
        Particle radius (m) — geometrical only, no effect on trajectory.
    g:
        Gravitational acceleration magnitude (m/s²).  Default: 9.8.
    duration:
        Simulation duration (s).  Default: 1.0 s.
    dt:
        Time step (s).  Default: 0.01 s.
    space_half_extent:
        Half-width of the simulation bounding box (m).
    validation_tolerance_pct:
        Tolerance for :class:`ValidationTarget` checks (%).  Default: 1%.
    include_derived_metrics:
        When ``True``, append derived-metric validation targets
        ``max_height``, ``range``, and ``time_of_flight`` to the standard
        kinematic targets.  Default: ``False`` (preserves existing behaviour).
    source_refs:
        Provenance references.  Defaults to OpenStax + MIT OCW (both
        tier_1_authoritative).  NIST / ITU are never included by default.

    Returns
    -------
    PSDL
        Fully populated PSDL v0.1 document with analytic validation targets.
    """
    # Resolve v0x / v0z from (v0, theta) if the caller supplies a speed + angle.
    if v0 is not None:
        v0x = v0 * math.cos(theta)
        v0z = v0 * math.sin(theta)

    steps: int = round(duration / dt)
    t: float = dt * steps
    g_z: float = -g  # signed gravity component (negative = downward)

    # General kinematic solution (works for both horizontal and angled throw):
    #   x(t)  = v0x · t
    #   z(t)  = h + v0z · t + ½ · g_z · t²
    #   vx(t) = v0x  (constant)
    #   vz(t) = v0z + g_z · t
    x_exact: float = v0x * t
    z_exact: float = height + v0z * t + 0.5 * g_z * t ** 2
    vx_exact: float = v0x
    vz_exact: float = v0z + g_z * t

    targets = [
        ValidationTarget(
            name="final_x",
            expected_value=x_exact,
            tolerance_pct=validation_tolerance_pct,
            unit="m",
            dimension="length",
        ),
        ValidationTarget(
            name="final_z",
            expected_value=z_exact,
            tolerance_pct=validation_tolerance_pct,
            unit="m",
            dimension="length",
        ),
        ValidationTarget(
            name="final_vx",
            expected_value=vx_exact,
            tolerance_pct=validation_tolerance_pct,
            unit="m/s",
            dimension="velocity",
        ),
        ValidationTarget(
            name="final_vz",
            expected_value=vz_exact,
            tolerance_pct=validation_tolerance_pct,
            unit="m/s",
            dimension="velocity",
        ),
    ]

    if include_derived_metrics:
        # max_height: analytic peak — z₀ + v₀z² / (2g) when v₀z > 0,
        # else simply the initial height (already at or past peak).
        if v0z > 0.0:
            max_height_exact: float = height + v0z ** 2 / (2.0 * g)
        else:
            max_height_exact = height

        # range: horizontal displacement x_final − x₀  (x₀ = 0)
        range_exact: float = x_exact

        # time_of_flight: total simulation duration
        tof_exact: float = t

        targets += [
            ValidationTarget(
                name="max_height",
                expected_value=max_height_exact,
                tolerance_pct=validation_tolerance_pct,
                unit="m",
                dimension="length",
            ),
            ValidationTarget(
                name="range",
                expected_value=range_exact,
                tolerance_pct=validation_tolerance_pct,
                unit="m",
                dimension="length",
            ),
            ValidationTarget(
                name="time_of_flight",
                expected_value=tof_exact,
                tolerance_pct=validation_tolerance_pct,
                unit="s",
                dimension="time",
            ),
        ]

    # Build the assumptions list; differentiate horizontal vs. angled throw.
    is_angled = v0z != 0.0
    if is_angled:
        # theta is always defined (it's a function parameter with default 0.0).
        # We only include the angle value in the assumption string when the
        # caller explicitly provided a launch speed + angle via v0/theta;
        # direct v0x/v0z usage omits the degree value.
        if v0 is not None:
            theta_str = f" (theta={math.degrees(theta):.4g}° above horizontal)"
        else:
            theta_str = ""
        launch_assumption = (
            f"angled launch: v0x={v0x:.4g} m/s, v0z={v0z:.4g} m/s{theta_str}"
        )
    else:
        launch_assumption = "horizontal initial velocity only (no initial vertical component)"

    assumptions = [
        "no air resistance",
        "point mass",
        "uniform gravitational field",
        launch_assumption,
        "no ground collision within simulation window",
    ]

    # Human-readable query
    if is_angled and v0 is not None:
        query = (
            f"Object launched at {math.degrees(theta):.4g}° above horizontal from "
            f"{height} m with v0={v0} m/s; find position and velocity after {duration} s."
        )
    else:
        query = (
            f"Object launched horizontally from {height} m with "
            f"v0x={v0x} m/s; find position and velocity after {duration} s."
        )

    return PSDL(
        schema_version="0.1",
        scenario_type="projectile",
        assumptions=assumptions,
        source_refs=(
            source_refs if source_refs is not None else list(_DEFAULT_SOURCE_REFS)
        ),
        validation_targets=targets,
        world=WorldSettings(
            gravity=[0.0, 0.0, g_z],
            dt=dt,
            steps=steps,
            ground_plane=False,
            space=SpaceBox(
                min=[-space_half_extent, -space_half_extent, -space_half_extent],
                max=[space_half_extent, space_half_extent, space_half_extent],
                boundary_type=BoundaryType.elastic,
            ),
        ),
        objects=[
            ParticleObject(
                mass=mass,
                radius=radius,
                position=[0.0, 0.0, height],
                velocity=[v0x, 0.0, v0z],
                restitution=0.9,
            )
        ],
        query=query,
    )
