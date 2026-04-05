"""
Free-fall scenario template — v0.1.

:func:`build_psdl` constructs a PSDL v0.1 document for the canonical
free-fall scenario (vertical drop from rest or with initial vertical
velocity, no air resistance, no ground collision within the time span).

The returned document includes:

* ``scenario_type = "free_fall"``
* Explicit ``assumptions`` list
* Pre-computed ``validation_targets`` based on the exact kinematic solution
* Appropriate ``source_refs`` (defaults to OpenStax / MIT OCW)

This template is the authoritative source for free-fall test fixtures.
"""

from __future__ import annotations

from typing import List, Union

from src.schema.psdl import (
    BoundaryType,
    ParticleObject,
    PSDL,
    SourceRef,
    SpaceBox,
    ValidationTarget,
    WorldSettings,
)

# Default source references for free-fall templates.
# NIST / ITU are intentionally excluded — they cover unit definitions only,
# not mechanics problem templates.
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
    v0z: float = 0.0,
    mass: float = 1.0,
    radius: float = 0.1,
    g: float = 9.8,
    duration: float = 1.0,
    dt: float = 0.01,
    space_half_extent: float = 50.0,
    validation_tolerance_pct: float = 1.0,
    source_refs: List[Union[SourceRef, str]] | None = None,
) -> PSDL:
    """
    Build a PSDL document for a free-fall scenario.

    Parameters
    ----------
    height:
        Initial height above z=0 (m).  Default: 5.0 m.
    v0z:
        Initial vertical velocity (m/s, positive = upward).  Default: 0.
    mass:
        Particle mass (kg).  Default: 1.0 kg.
    radius:
        Particle radius (m) — geometrical only, does not affect free-fall.
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
    source_refs:
        Provenance references.  Defaults to OpenStax + MIT OCW (both
        tier_1_authoritative).  NIST / ITU are never included by default
        because they cover unit standards only, not mechanics templates.

    Returns
    -------
    PSDL
        Fully populated PSDL v0.1 document with analytic validation targets.
    """
    steps = round(duration / dt)

    # Exact kinematic solution
    t = dt * steps
    z_exact  = height + v0z * t - 0.5 * g * t ** 2
    vz_exact = v0z - g * t

    targets = [
        ValidationTarget(
            name="final_z",
            expected_value=z_exact,
            tolerance_pct=validation_tolerance_pct,
            unit="m",
            dimension="length",
        ),
        ValidationTarget(
            name="final_vz",
            expected_value=vz_exact,
            tolerance_pct=validation_tolerance_pct,
            unit="m/s",
            dimension="velocity",
        ),
    ]

    return PSDL(
        schema_version="0.1",
        scenario_type="free_fall",
        assumptions=[
            "no air resistance",
            "point mass",
            "uniform gravitational field",
            "no ground collision within simulation window",
        ],
        source_refs=source_refs if source_refs is not None else list(_DEFAULT_SOURCE_REFS),
        validation_targets=targets,
        world=WorldSettings(
            gravity=[0.0, 0.0, -g],
            dt=dt,
            steps=steps,
            ground_plane=False,
            space=SpaceBox(
                min=[-space_half_extent, -space_half_extent, -space_half_extent],
                max=[space_half_extent,  space_half_extent,  space_half_extent],
                boundary_type=BoundaryType.elastic,
            ),
        ),
        objects=[
            ParticleObject(
                mass=mass,
                radius=radius,
                position=[0.0, 0.0, height],
                velocity=[0.0, 0.0, v0z],
                restitution=0.9,
            )
        ],
        query=f"Object dropped from {height} m with v0z={v0z} m/s; "
              f"find position and velocity after {duration} s.",
    )
