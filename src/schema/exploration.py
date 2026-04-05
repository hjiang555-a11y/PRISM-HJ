"""
Minimal structured schema for exploration_config — src/schema/exploration.py

This module defines the contract layer for parameter-space exploration.
It intentionally performs only structural validation; no exploration algorithm
is implemented here.  Real exploration logic belongs in src/explorer/ and will
be added in future iterations.

Design constraints:
- Does NOT affect the deterministic simulation path.
- Does NOT implement grid search, random sampling, Bayesian optimisation,
  interestingness metrics, or any other exploration algorithm.
- Intended to replace the bare ``Optional[dict]`` on WorldSettings.exploration_config
  with a lightweight, verifiable schema so that mis-configured exploration setups
  are caught at load time rather than silently ignored at runtime.
"""

from __future__ import annotations

from typing import List, Optional, Union

from pydantic import BaseModel, Field, field_validator, model_validator


class ExplorationParameter(BaseModel):
    """
    A single parameter dimension in the exploration space.

    Attributes
    ----------
    name:
        Identifier for the parameter (e.g. ``"mass"``, ``"initial_velocity"``).
        Must be a non-empty string.
    type:
        Data type of the parameter.  Recommended values: ``"float"``,
        ``"int"``, ``"bool"``.
    range:
        Closed interval ``[min, max]`` for numeric parameters.  Must have
        exactly 2 elements and satisfy ``range[0] <= range[1]``.
        May be omitted for ``bool`` parameters.
    sampling:
        Suggested sampling strategy.  Recommended values: ``"grid"``,
        ``"random"``, ``"bayesian"``.  Not validated against an enum to
        keep the schema forwards-compatible.
    step:
        Step size for grid sampling.  When ``sampling == "grid"`` and a
        numeric ``step`` is provided it must be strictly positive.
    """

    name: str = Field(description="Parameter identifier (non-empty)")
    type: str = Field(default="float", description="Data type: 'float', 'int', or 'bool'")
    range: Optional[List[Union[float, int]]] = Field(
        default=None,
        description="Closed interval [min, max] for numeric parameters",
    )
    sampling: Optional[str] = Field(
        default=None,
        description="Sampling strategy: 'grid', 'random', or 'bayesian'",
    )
    step: Optional[Union[float, int]] = Field(
        default=None,
        description="Step size for grid sampling (must be > 0 when provided with sampling='grid')",
    )

    @field_validator("name")
    @classmethod
    def _name_must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("ExplorationParameter.name must not be empty")
        return v

    @model_validator(mode="after")
    def _validate_range_and_step(self) -> "ExplorationParameter":
        if self.range is not None:
            if len(self.range) != 2:
                raise ValueError(
                    "ExplorationParameter.range must have exactly 2 elements [min, max]; "
                    f"got {len(self.range)}"
                )
            if self.range[0] > self.range[1]:
                raise ValueError(
                    "ExplorationParameter.range[0] must be <= range[1]; "
                    f"got [{self.range[0]}, {self.range[1]}]"
                )
        if self.sampling == "grid" and self.step is not None:
            if self.step <= 0:
                raise ValueError(
                    "ExplorationParameter.step must be > 0 when sampling='grid'; "
                    f"got step={self.step}"
                )
        return self


class ExplorationConfig(BaseModel):
    """
    Minimal structured configuration for parameter-space exploration.

    This is the *contract layer* only: it validates that the configuration
    is well-formed but does not execute any exploration algorithm.

    Attributes
    ----------
    parameters:
        List of parameter dimensions to explore.  May be empty (default).
    combine_method:
        How multiple parameters are combined (e.g. ``"cartesian"``,
        ``"independent"``).  Currently unconstrained; reserved for future
        use.
    interestingness:
        Lightweight placeholder for future interestingness-metric
        configuration.  Kept as an unstructured dict for now to avoid
        premature schema lock-in.
    """

    parameters: List[ExplorationParameter] = Field(
        default_factory=list,
        description="Parameter dimensions to explore",
    )
    combine_method: Optional[str] = Field(
        default=None,
        description="How multiple parameters are combined (reserved)",
    )
    interestingness: Optional[dict] = Field(
        default=None,
        description="Interestingness-metric configuration (reserved, unstructured)",
    )
