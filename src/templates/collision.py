"""
Collision scenario template — v0.1.

:func:`build_psdl` constructs a PSDL v0.1 document for a 1-D two-particle
collision (elastic or perfectly inelastic).

The returned document includes:

* ``scenario_type = "collision"``
* Explicit ``assumptions`` list (elastic / inelastic)
* Pre-computed ``validation_targets`` based on exact momentum conservation
* Appropriate ``source_refs`` (defaults to OpenStax / MIT OCW)
* Two :class:`ParticleObject` entries representing the two colliding bodies

This template is the authoritative source for collision test fixtures.

Analytic formulae
-----------------
Elastic (momentum + kinetic energy conserved)::

    v1f = ((m1 − m2) · v1x + 2 · m2 · v2x) / (m1 + m2)
    v2f = ((m2 − m1) · v2x + 2 · m1 · v1x) / (m1 + m2)

Perfectly inelastic (objects stick together; momentum conserved only)::

    vf  = (m1 · v1x + m2 · v2x) / (m1 + m2)
"""

from __future__ import annotations

from typing import List, Literal, Union

from src.schema.psdl import (
    BoundaryType,
    ParticleObject,
    PSDL,
    SourceRef,
    SpaceBox,
    ValidationTarget,
    WorldSettings,
)

scenario_type: str = "collision"

# Default source references: tier_1_authoritative only.
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
    m1: float = 1.0,
    m2: float = 1.0,
    v1x: float = 2.0,
    v2x: float = 0.0,
    radius: float = 0.1,
    collision_type: Literal["elastic", "inelastic"] = "elastic",
    dt: float = 0.01,
    space_half_extent: float = 50.0,
    validation_tolerance_pct: float = 1.0,
    source_refs: List[Union[SourceRef, str]] | None = None,
) -> PSDL:
    """
    Build a PSDL document for a 1-D two-particle collision.

    Parameters
    ----------
    m1, m2:
        Masses of the two particles (kg).  Both default to 1.0 kg.
    v1x, v2x:
        Initial x-velocities (m/s, positive = right).  Default: v1x=2 m/s,
        v2x=0 m/s (particle 2 at rest).
    radius:
        Particle radius (m).  Default: 0.1 m.
    collision_type:
        ``"elastic"`` — conserves both momentum and kinetic energy.
        ``"inelastic"`` — perfectly inelastic; objects move together after.
    dt:
        Time step (s).  Default: 0.01 s.
    space_half_extent:
        Half-width of the simulation bounding box (m).
    validation_tolerance_pct:
        Tolerance for :class:`ValidationTarget` checks (%).  Default: 1%.
    source_refs:
        Provenance references.  Defaults to OpenStax + MIT OCW.

    Returns
    -------
    PSDL
        Fully populated PSDL v0.1 document with analytic collision results.
    """
    total_mass = m1 + m2

    if collision_type == "elastic":
        v1f: float = ((m1 - m2) * v1x + 2.0 * m2 * v2x) / total_mass
        v2f: float = ((m2 - m1) * v2x + 2.0 * m1 * v1x) / total_mass
        assumptions = [
            "1-dimensional collision",
            "elastic collision (momentum and kinetic energy conserved)",
            "point masses",
            "no external forces during collision",
            "no gravity (horizontal 1-D setup)",
        ]
        restitution = 1.0
    else:
        # Perfectly inelastic: both objects move together at vf
        vf: float = (m1 * v1x + m2 * v2x) / total_mass
        v1f = vf
        v2f = vf
        assumptions = [
            "1-dimensional collision",
            "perfectly inelastic collision (objects coalesce after impact)",
            "momentum conserved",
            "kinetic energy not conserved",
            "point masses",
            "no external forces during collision",
            "no gravity (horizontal 1-D setup)",
        ]
        restitution = 0.0

    targets = [
        ValidationTarget(
            name="final_vx",
            expected_value=v1f,
            tolerance_pct=validation_tolerance_pct,
            unit="m/s",
            dimension="velocity",
        ),
    ]

    return PSDL(
        schema_version="0.1",
        scenario_type="collision",
        assumptions=assumptions,
        source_refs=(
            source_refs if source_refs is not None else list(_DEFAULT_SOURCE_REFS)
        ),
        validation_targets=targets,
        world=WorldSettings(
            gravity=[0.0, 0.0, 0.0],  # 1-D collision; gravity ignored
            dt=dt,
            steps=1,  # Analytic result; no time integration needed
            ground_plane=False,
            space=SpaceBox(
                min=[-space_half_extent, -space_half_extent, -space_half_extent],
                max=[space_half_extent, space_half_extent, space_half_extent],
                boundary_type=BoundaryType.elastic,
            ),
        ),
        objects=[
            ParticleObject(
                mass=m1,
                radius=radius,
                position=[-1.0, 0.0, 0.0],
                velocity=[v1x, 0.0, 0.0],
                restitution=restitution,
            ),
            ParticleObject(
                mass=m2,
                radius=radius,
                position=[1.0, 0.0, 0.0],
                velocity=[v2x, 0.0, 0.0],
                restitution=restitution,
            ),
        ],
        query=(
            f"{collision_type.capitalize()} collision: "
            f"m1={m1} kg at v1x={v1x} m/s, "
            f"m2={m2} kg at v2x={v2x} m/s. "
            "Find final velocities."
        ),
    )


def compute_final_velocities(
    m1: float,
    m2: float,
    v1x: float,
    v2x: float,
    collision_type: Literal["elastic", "inelastic"] = "elastic",
) -> tuple[float, float]:
    """
    Compute final velocities for a 1-D collision without building a PSDL.

    Useful as a standalone reference calculator.

    Returns
    -------
    tuple[float, float]
        ``(v1_final, v2_final)`` in m/s.
    """
    total = m1 + m2
    if collision_type == "elastic":
        return (
            ((m1 - m2) * v1x + 2.0 * m2 * v2x) / total,
            ((m2 - m1) * v2x + 2.0 * m1 * v1x) / total,
        )
    # Perfectly inelastic
    vf = (m1 * v1x + m2 * v2x) / total
    return vf, vf
