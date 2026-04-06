"""
Projectile scenario template — v0.1.

.. note::
    **LEGACY / FROZEN** — This template exists to support legacy test fixtures
    and the old ``text_to_psdl`` template-first path.  It is not part of the
    new execution pipeline.

    New physics logic should not be added here.  Frozen in P0; slated for
    removal once all dependent test fixtures are ported to the new
    architecture.

:func:`build_psdl` constructs a PSDL v0.1 document for the canonical
horizontal-throw projectile scenario (object launched horizontally from a
height with initial horizontal velocity, no air resistance, no ground
collision within the simulated time span).

The returned document includes:

* ``scenario_type = "projectile"``
* Explicit ``assumptions`` list
* Pre-computed ``validation_targets`` based on the exact kinematic solution
* Appropriate ``source_refs`` (defaults to OpenStax / MIT OCW)

This template is the authoritative source for projectile test fixtures.
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
    Build a PSDL document for a horizontal-throw projectile scenario.

    Parameters
    ----------
    height:
        Initial height above z=0 (m).  Default: 5.0 m.
    v0x:
        Initial horizontal velocity (m/s, positive = forward).  Default: 10.0.
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
    steps: int = round(duration / dt)
    t: float = dt * steps

    # Exact kinematic solution for horizontal throw:
    #   x(t) = v0x · t          (constant horizontal velocity)
    #   z(t) = h − ½ · g · t²  (free fall in vertical direction)
    #   vx(t) = v0x
    #   vz(t) = −g · t
    x_exact: float = v0x * t
    z_exact: float = height - 0.5 * g * t ** 2
    vx_exact: float = v0x
    vz_exact: float = -g * t

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
        # max_height: horizontal throw has v0z = 0 → peak height = initial height
        max_height_exact: float = height

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

    return PSDL(
        schema_version="0.1",
        scenario_type="projectile",
        assumptions=[
            "no air resistance",
            "point mass",
            "uniform gravitational field",
            "horizontal initial velocity only (no initial vertical component)",
            "no ground collision within simulation window",
        ],
        source_refs=(
            source_refs if source_refs is not None else list(_DEFAULT_SOURCE_REFS)
        ),
        validation_targets=targets,
        world=WorldSettings(
            gravity=[0.0, 0.0, -g],
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
                velocity=[v0x, 0.0, 0.0],
                restitution=0.9,
            )
        ],
        query=(
            f"Object launched horizontally from {height} m with "
            f"v0x={v0x} m/s; find position and velocity after {duration} s."
        ),
    )
