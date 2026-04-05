"""
Tests for the minimal ExplorationConfig / ExplorationParameter schema.

Covers:
1. Default / None semantics — WorldSettings.exploration_config defaults to None.
2. Valid minimal configs pass validation.
3. Invalid configs raise ValidationError:
   - range with wrong length
   - range[0] > range[1]
   - sampling == "grid" with step <= 0
   - empty parameter name
4. Backward compatibility — PSDL construction without exploration_config is unaffected.
5. JSON roundtrip — exploration_config survives model_dump / pretty_print.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from src.schema.exploration import ExplorationConfig, ExplorationParameter
from src.schema.psdl import PSDL, WorldSettings


# ---------------------------------------------------------------------------
# 1. Default / None semantics
# ---------------------------------------------------------------------------

class TestExplorationConfigDefaults:
    def test_world_settings_default_none(self):
        ws = WorldSettings()
        assert ws.exploration_config is None

    def test_psdl_world_default_none(self):
        psdl = PSDL()
        assert psdl.world.exploration_config is None

    def test_exploration_config_empty_parameters(self):
        cfg = ExplorationConfig()
        assert cfg.parameters == []
        assert cfg.combine_method is None
        assert cfg.interestingness is None

    def test_exploration_parameter_defaults(self):
        p = ExplorationParameter(name="mass")
        assert p.type == "float"
        assert p.range is None
        assert p.sampling is None
        assert p.step is None


# ---------------------------------------------------------------------------
# 2. Valid minimal configs
# ---------------------------------------------------------------------------

class TestValidExplorationConfigs:
    def test_single_float_parameter(self):
        cfg = ExplorationConfig(
            parameters=[ExplorationParameter(name="mass", type="float", range=[0.1, 10.0])],
        )
        assert len(cfg.parameters) == 1
        assert cfg.parameters[0].name == "mass"

    def test_int_parameter_with_grid_step(self):
        cfg = ExplorationConfig(
            parameters=[
                ExplorationParameter(
                    name="steps", type="int", range=[10, 100], sampling="grid", step=10
                )
            ],
        )
        assert cfg.parameters[0].step == 10

    def test_bool_parameter_no_range(self):
        cfg = ExplorationConfig(
            parameters=[ExplorationParameter(name="ground_plane", type="bool")],
        )
        assert cfg.parameters[0].range is None

    def test_multiple_parameters(self):
        cfg = ExplorationConfig(
            parameters=[
                ExplorationParameter(name="mass", type="float", range=[0.5, 5.0]),
                ExplorationParameter(name="velocity", type="float", range=[1.0, 20.0]),
            ],
            combine_method="cartesian",
        )
        assert len(cfg.parameters) == 2
        assert cfg.combine_method == "cartesian"

    def test_with_interestingness_placeholder(self):
        cfg = ExplorationConfig(
            parameters=[ExplorationParameter(name="mass", type="float")],
            interestingness={"metric": "extremum"},
        )
        assert cfg.interestingness == {"metric": "extremum"}

    def test_range_equal_endpoints_valid(self):
        """range[0] == range[1] is a degenerate but valid point."""
        p = ExplorationParameter(name="mass", type="float", range=[5.0, 5.0])
        assert p.range == [5.0, 5.0]

    def test_grid_sampling_without_step_is_valid(self):
        """step is optional even when sampling='grid'."""
        p = ExplorationParameter(name="mass", type="float", range=[1.0, 10.0], sampling="grid")
        assert p.step is None

    def test_world_settings_with_valid_config(self):
        cfg = ExplorationConfig(
            parameters=[ExplorationParameter(name="mass", type="float", range=[0.1, 5.0])],
        )
        ws = WorldSettings(exploration_config=cfg)
        assert ws.exploration_config is not None

    def test_dict_coercion_valid(self):
        """Pydantic coerces a matching dict into ExplorationConfig."""
        ws = WorldSettings(
            exploration_config={
                "parameters": [{"name": "mass", "type": "float", "range": [0.1, 10.0]}],
                "combine_method": "cartesian",
            }
        )
        assert ws.exploration_config is not None
        assert ws.exploration_config.parameters[0].name == "mass"


# ---------------------------------------------------------------------------
# 3. Invalid configs raise ValidationError
# ---------------------------------------------------------------------------

class TestInvalidExplorationConfigs:
    def test_range_length_not_2_raises(self):
        with pytest.raises(ValidationError, match="exactly 2 elements"):
            ExplorationParameter(name="mass", type="float", range=[0.1, 5.0, 10.0])

    def test_range_single_element_raises(self):
        with pytest.raises(ValidationError, match="exactly 2 elements"):
            ExplorationParameter(name="mass", type="float", range=[5.0])

    def test_range_min_greater_than_max_raises(self):
        with pytest.raises(ValidationError, match="range\\[0\\] must be <= range\\[1\\]"):
            ExplorationParameter(name="mass", type="float", range=[10.0, 1.0])

    def test_grid_step_zero_raises(self):
        with pytest.raises(ValidationError, match="step must be > 0"):
            ExplorationParameter(
                name="mass", type="float", range=[0.0, 10.0], sampling="grid", step=0
            )

    def test_grid_step_negative_raises(self):
        with pytest.raises(ValidationError, match="step must be > 0"):
            ExplorationParameter(
                name="mass", type="float", range=[0.0, 10.0], sampling="grid", step=-1.0
            )

    def test_empty_name_raises(self):
        with pytest.raises(ValidationError, match="name must not be empty"):
            ExplorationParameter(name="  ")

    def test_whitespace_only_name_raises(self):
        with pytest.raises(ValidationError, match="name must not be empty"):
            ExplorationParameter(name="\t\n")


# ---------------------------------------------------------------------------
# 4. Backward compatibility — normal PSDL construction unaffected
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    def test_psdl_without_exploration_config(self):
        psdl = PSDL(
            scenario_type="free_fall",
            world=WorldSettings(gravity=[0.0, 0.0, -9.8]),
        )
        assert psdl.world.exploration_config is None

    def test_world_settings_without_exploration_config(self):
        ws = WorldSettings(dt=0.005, steps=200)
        assert ws.exploration_config is None

    def test_existing_psdl_fields_unchanged(self):
        psdl = PSDL(
            scenario_type="projectile",
            assumptions=["no air resistance"],
        )
        assert psdl.scenario_type == "projectile"
        assert psdl.world.exploration_config is None


# ---------------------------------------------------------------------------
# 5. JSON roundtrip
# ---------------------------------------------------------------------------

class TestJsonRoundtrip:
    def test_exploration_config_null_present_in_json(self):
        psdl = PSDL()
        data = json.loads(psdl.pretty_print())
        assert "exploration_config" in data["world"]
        assert data["world"]["exploration_config"] is None

    def test_exploration_config_serialised_in_json(self):
        cfg = ExplorationConfig(
            parameters=[ExplorationParameter(name="mass", type="float", range=[0.5, 5.0])],
        )
        psdl = PSDL(world=WorldSettings(exploration_config=cfg))
        data = json.loads(psdl.pretty_print())
        ec = data["world"]["exploration_config"]
        assert ec is not None
        assert ec["parameters"][0]["name"] == "mass"
        assert ec["parameters"][0]["range"] == [0.5, 5.0]

    def test_exploration_config_roundtrip(self):
        cfg = ExplorationConfig(
            parameters=[
                ExplorationParameter(name="velocity", type="float", range=[1.0, 10.0], sampling="random")
            ],
            combine_method="independent",
        )
        ws = WorldSettings(exploration_config=cfg)
        dumped = ws.model_dump()
        ws2 = WorldSettings(**dumped)
        assert ws2.exploration_config is not None
        assert ws2.exploration_config.parameters[0].sampling == "random"
        assert ws2.exploration_config.combine_method == "independent"
