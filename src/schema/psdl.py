"""
PSDL (Physical Scene Description Language) Pydantic models.

All values use SI units (metres, kilograms, seconds).
"""

from __future__ import annotations

from enum import Enum
from typing import List, Literal, Optional, Union

from pydantic import BaseModel, Field


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
    theorems: List[str] = Field(
        default=["newton_second", "energy_conservation"],
        description="Physical theorems to be honoured by the simulation",
    )

    def pretty_print(self) -> str:
        """Return a human-readable summary of world settings."""
        return (
            f"WorldSettings(gravity={self.gravity}, dt={self.dt}s, "
            f"steps={self.steps}, boundary={self.space.boundary_type})"
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
# Top-level PSDL document
# ---------------------------------------------------------------------------

PhysicsObject = Union[ParticleObject, CircuitPort, FieldObject]


class PSDL(BaseModel):
    """
    Physical Scene Description Language document.

    This is the root model that the LLM produces and the physics engine consumes.
    """
    world: WorldSettings = Field(default_factory=WorldSettings)
    objects: List[PhysicsObject] = Field(default_factory=list)
    query: Optional[str] = None

    def pretty_print(self) -> str:
        """Return an indented JSON representation."""
        return self.model_dump_json(indent=2)

    def __str__(self) -> str:
        return self.pretty_print()
