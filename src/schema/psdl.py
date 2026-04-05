"""
PSDL (Physical Scene Description Language) Pydantic models — v0.1.

PSDL is the *knowledge contract* that separates the natural-language interface
from the deterministic physics execution layer.  Every document must be
self-describing: it carries its own schema version, scenario classification,
explicit assumptions, provenance references, and expected validation targets.

All values use SI units (metres, kilograms, seconds) unless stated otherwise.
Unit symbols are validated against :mod:`src.schema.units`.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator

from src.schema.units import Dimension, validate_unit_for_dimension

# ---------------------------------------------------------------------------
# Source reference
# ---------------------------------------------------------------------------

# Valid roles a source reference can play within a PSDL document.
SOURCE_REF_ROLES = frozenset({
    "primary_template_source",
    "secondary_reference",
    "units_reference",
    "metrology_reference",
    "conceptual_reference",
})


class SourceRef(BaseModel):
    """
    A structured reference to an entry in ``data/sources/registry.yaml``.

    Attributes
    ----------
    source_id:
        The ``id`` key of the source in the registry (e.g.
        ``"openstax_university_physics_v1"``).
    role:
        How this source is used in the current document.  Must be one of:

        * ``primary_template_source`` — the main textbook basis for the template
        * ``secondary_reference`` — supporting or cross-check reference
        * ``units_reference`` — source for SI unit definitions (standards only)
        * ``metrology_reference`` — source for metrology / time-freq terms
        * ``conceptual_reference`` — conceptual explanation only
    """

    source_id: str = Field(description="Registry entry id from data/sources/registry.yaml")
    role: str = Field(description="Role of this source in the document")

    @field_validator("role")
    @classmethod
    def _role_must_be_valid(cls, v: str) -> str:
        if v not in SOURCE_REF_ROLES:
            raise ValueError(
                f"Unknown source role {v!r}. "
                f"Valid roles: {sorted(SOURCE_REF_ROLES)}"
            )
        return v


# ---------------------------------------------------------------------------
# Boundary & World
# ---------------------------------------------------------------------------

class BoundaryType(str, Enum):
    """How particles behave when they reach the edge of the simulation space."""
    elastic = "elastic"       # Reflect velocity component (bounce)
    absorbing = "absorbing"   # Zero out the velocity component (stop at wall)
    periodic = "periodic"     # Wrap-around (reserved for future use)


class SpaceBox(BaseModel):
    """Axis-aligned bounding box that defines the simulation volume."""
    min: List[float] = Field(default=[-10.0, -10.0, -10.0], description="Lower corner (m)")
    max: List[float] = Field(default=[10.0, 10.0, 10.0], description="Upper corner (m)")
    boundary_type: BoundaryType = BoundaryType.elastic


class Observer(BaseModel):
    """Reference frame specification (reserved for multi-frame analysis)."""
    frame: str = "inertial"
    origin: List[float] = Field(default=[0.0, 0.0, 0.0], description="Origin (m)")
    velocity: List[float] = Field(default=[0.0, 0.0, 0.0], description="Frame velocity (m/s)")


class WorldSettings(BaseModel):
    """Global simulation parameters."""
    gravity: List[float] = Field(default=[0.0, 0.0, -9.8], description="Gravity vector (m/s²)")
    dt: float = Field(default=0.01, description="Time step (s)")
    steps: int = Field(default=100, description="Number of simulation steps")
    space: SpaceBox = Field(default_factory=SpaceBox)
    observer: Optional[Observer] = None
    ground_plane: bool = Field(
        default=False,
        description=(
            "Whether a ground plane exists at z=0. "
            "Must be set explicitly — the execution layer never adds a ground "
            "plane unless this flag is True."
        ),
    )
    theorems: List[str] = Field(
        default=["newton_second", "energy_conservation"],
        description="Physical theorems to be honoured by the simulation",
    )

    @field_validator("gravity")
    @classmethod
    def _gravity_has_three_components(cls, v: List[float]) -> List[float]:
        if len(v) != 3:
            raise ValueError("gravity must have exactly 3 components (x, y, z)")
        return v

    def pretty_print(self) -> str:
        """Return a human-readable summary of world settings."""
        return (
            f"WorldSettings(gravity={self.gravity}, dt={self.dt}s, "
            f"steps={self.steps}, boundary={self.space.boundary_type}, "
            f"ground_plane={self.ground_plane})"
        )


# ---------------------------------------------------------------------------
# Physics Objects
# ---------------------------------------------------------------------------

class ParticleObject(BaseModel):
    """A rigid spherical particle (the primary object type)."""
    type: Literal["particle"] = "particle"
    mass: float = Field(default=1.0, description="Mass (kg)")
    radius: float = Field(default=0.1, description="Radius (m)")
    position: List[float] = Field(default=[0.0, 0.0, 0.0], description="Initial position (m)")
    velocity: List[float] = Field(default=[0.0, 0.0, 0.0], description="Initial velocity (m/s)")
    restitution: float = Field(default=0.9, description="Coefficient of restitution [0, 1]")


class CircuitPort(BaseModel):
    """Placeholder for future circuit / electromagnetic element support."""
    type: Literal["circuit_port"] = "circuit_port"
    port_id: str = "port_0"
    voltage: float = Field(default=0.0, description="Port voltage (V)")
    current: float = Field(default=0.0, description="Port current (A)")


class FieldObject(BaseModel):
    """Placeholder for future field-based physics (e.g., electromagnetic fields)."""
    type: Literal["field"] = "field"
    field_type: str = "electric"
    strength: List[float] = Field(default=[0.0, 0.0, 0.0], description="Field vector (N/C or T)")
    region: Optional[SpaceBox] = None


# ---------------------------------------------------------------------------
# Validation target (gold-standard expected results)
# ---------------------------------------------------------------------------

class ValidationTarget(BaseModel):
    """
    A single expected measurement that the execution layer should verify.

    Example::

        ValidationTarget(
            name="final_z",
            expected_value=0.1,
            tolerance_pct=1.0,
            unit="m",
            dimension="length",
        )
    """
    name: str = Field(description="Human-readable name of the target quantity")
    expected_value: float = Field(description="Expected numerical value (SI)")
    tolerance_pct: float = Field(
        default=5.0,
        ge=0.0,
        description="Acceptable relative error, as a percentage of |expected_value|",
    )
    unit: str = Field(default="", description="SI unit symbol (e.g. 'm', 'm/s')")
    dimension: str = Field(default="", description="Physical dimension (e.g. 'length')")

    @field_validator("unit")
    @classmethod
    def _unit_must_be_known(cls, v: str) -> str:
        if v:
            # Will raise UnknownUnitError if the symbol is not in the registry
            from src.schema.units import get_unit_info
            get_unit_info(v)
        return v

    @field_validator("dimension")
    @classmethod
    def _dimension_must_be_known(cls, v: str) -> str:
        if v:
            Dimension(v)  # raises ValueError if unknown
        return v

    def check(self, actual: float) -> bool:
        """Return True if *actual* is within the declared tolerance."""
        if self.expected_value == 0.0:
            return abs(actual) <= self.tolerance_pct / 100.0
        return (
            abs(actual - self.expected_value)
            <= (self.tolerance_pct / 100.0) * abs(self.expected_value)
        )


# ---------------------------------------------------------------------------
# Top-level PSDL document
# ---------------------------------------------------------------------------

PhysicsObject = Union[ParticleObject, CircuitPort, FieldObject]


class PSDL(BaseModel):
    """
    Physical Scene Description Language document — v0.1.

    This is the *knowledge contract*: the LLM produces it, the physics
    engine consumes it.  All physical intent is expressed here; the
    execution layer must not add implicit assumptions.
    """
    schema_version: str = Field(
        default="0.1",
        description="PSDL schema version",
    )
    scenario_type: Optional[str] = Field(
        default=None,
        description=(
            "Scenario classifier used by the dispatcher to select a solver. "
            "Examples: 'free_fall', 'projectile', 'collision'."
        ),
    )
    assumptions: List[str] = Field(
        default_factory=list,
        description=(
            "Explicit modelling assumptions (e.g. 'no air resistance', "
            "'point mass', 'rigid body')."
        ),
    )
    source_refs: List[Union[SourceRef, str]] = Field(
        default_factory=list,
        description=(
            "Provenance references. Prefer structured SourceRef objects "
            "linking to entries in data/sources/registry.yaml. "
            "Plain strings are accepted for backward compatibility."
        ),
    )
    validation_targets: List[ValidationTarget] = Field(
        default_factory=list,
        description="Expected gold-standard results for post-simulation verification.",
    )
    world: WorldSettings = Field(default_factory=WorldSettings)
    objects: List[PhysicsObject] = Field(default_factory=list)
    query: Optional[str] = None

    def pretty_print(self) -> str:
        """Return an indented JSON representation."""
        return self.model_dump_json(indent=2)

    def __str__(self) -> str:
        return self.pretty_print()
