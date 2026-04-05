"""
Tests for the exploration reserve (src/explorer) and related CLI/schema extensions.

Covers:
1. explore() placeholder outputs the reservation message and returns a structured result.
2. main() --explore path calls explore() and does NOT enter the deterministic pipeline.
3. WorldSettings / PSDL carry the exploration_config field (default None).
4. Without --explore the existing deterministic pipeline is unaffected.
"""

from __future__ import annotations

import json

from src.explorer import explore
from src.explorer.placeholder import (
    EXPLORER_RESERVED_MESSAGE,
    explore as explore_direct,
)
from src.schema.psdl import PSDL, WorldSettings


# ---------------------------------------------------------------------------
# 1. explore() placeholder
# ---------------------------------------------------------------------------

class TestExplorePlaceholder:
    def test_prints_reservation_message(self, capsys):
        explore(base_psdl=None, exploration_config=None)
        out = capsys.readouterr().out
        assert EXPLORER_RESERVED_MESSAGE in out

    def test_returns_structured_reserved_result(self):
        result = explore(base_psdl=None, exploration_config=None)
        assert isinstance(result, dict)
        assert result["mode"] == "explore"
        assert result["status"] == "reserved"
        assert EXPLORER_RESERVED_MESSAGE in result["message"]
        assert result["results"] == []
        assert result["base_psdl"] is None
        assert result["exploration_config"] is None
        assert "parameter_space_search" in result["metadata"]["future_capabilities"]

    def test_echoes_lightweight_inputs(self):
        config = {"strategy": "grid"}
        result = explore(base_psdl=None, exploration_config=config)
        assert result["exploration_config"] == config

    def test_direct_import_same_as_package_import(self):
        """from src.explorer import explore must resolve to placeholder.explore."""
        r1 = explore(None, None)
        r2 = explore_direct(None, None)
        assert r1 == r2
        assert r1["mode"] == "explore"


# ---------------------------------------------------------------------------
# 2. main() --explore path
# ---------------------------------------------------------------------------

class TestMainExplorePath:
    def test_explore_flag_exits_zero(self):
        """--explore --question returns exit code 0."""
        from main import main
        rc = main(["--explore", "--question", "任何问题"])
        assert rc == 0

    def test_explore_flag_prints_message(self, capsys):
        """--explore prints the reservation message."""
        from main import main
        main(["--explore", "--question", "任何问题"])
        out = capsys.readouterr().out
        assert EXPLORER_RESERVED_MESSAGE in out
        assert "Structured explorer result:" in out
        json_blob = out.split("Structured explorer result:\n", maxsplit=1)[1].strip()
        parsed = json.loads(json_blob)
        assert parsed["mode"] == "explore"
        assert parsed["status"] == "reserved"
        assert parsed["results"] == []

    def test_explore_does_not_enter_dispatch(self, monkeypatch):
        """When --explore is set, dispatch_with_validation must NOT be called."""
        calls = []

        def fake_dispatch(psdl):
            calls.append(psdl)
            return {"states": [], "solver_used": "none", "validation_results": []}

        import src.physics.dispatcher as disp
        monkeypatch.setattr(disp, "dispatch_with_validation", fake_dispatch)

        from main import main
        main(["--explore", "--question", "任何问题"])
        assert calls == [], "dispatch_with_validation should not be called with --explore"

    def test_explore_does_not_enter_text_to_psdl(self, monkeypatch):
        """When --explore is set, text_to_psdl must NOT be called."""
        calls = []

        def fake_translate(q):
            calls.append(q)
            return PSDL()

        import src.llm.translator as trans
        monkeypatch.setattr(trans, "text_to_psdl", fake_translate)
        # Also patch the name used in main module's namespace
        import main as main_mod
        monkeypatch.setattr(main_mod, "text_to_psdl", fake_translate)

        from main import main
        main(["--explore", "--question", "任何问题"])
        assert calls == [], "text_to_psdl should not be called with --explore"

    def test_explore_flag_clean_exit(self, capsys):
        from main import main

        rc = main(["--explore", "--question", "任何问题"])
        out = capsys.readouterr().out

        assert rc == 0
        assert EXPLORER_RESERVED_MESSAGE in out


# ---------------------------------------------------------------------------
# 3. WorldSettings / PSDL exploration_config field
# ---------------------------------------------------------------------------

class TestExplorationConfigField:
    def test_world_settings_default_none(self):
        ws = WorldSettings()
        assert ws.exploration_config is None

    def test_psdl_world_default_none(self):
        psdl = PSDL()
        assert psdl.world.exploration_config is None

    def test_world_settings_accepts_dict(self):
        ws = WorldSettings(exploration_config={"strategy": "grid", "param": "mass"})
        assert ws.exploration_config == {"strategy": "grid", "param": "mass"}

    def test_psdl_with_exploration_config(self):
        psdl = PSDL(world=WorldSettings(exploration_config={"strategy": "bayesian"}))
        assert psdl.world.exploration_config == {"strategy": "bayesian"}

    def test_exploration_config_in_json_output(self):
        psdl = PSDL(world=WorldSettings(exploration_config={"x": 1}))
        json_str = psdl.pretty_print()
        assert "exploration_config" in json_str

    def test_exploration_config_null_in_json(self):
        psdl = PSDL()
        json_str = psdl.pretty_print()
        assert "exploration_config" in json_str  # field is present even when null

    def test_pretty_print_hints_when_set(self):
        ws = WorldSettings(exploration_config={"x": 1})
        assert "exploration_config=<set>" in ws.pretty_print()

    def test_pretty_print_no_hint_when_none(self):
        ws = WorldSettings()
        assert "exploration_config" not in ws.pretty_print()

    def test_backward_compat_psdl_without_field(self):
        """Existing PSDL construction without exploration_config must still work."""
        psdl = PSDL(
            scenario_type="free_fall",
            world=WorldSettings(gravity=[0.0, 0.0, -9.8]),
        )
        assert psdl.world.exploration_config is None


# ---------------------------------------------------------------------------
# 4. Without --explore the existing pipeline is unaffected
# ---------------------------------------------------------------------------

class TestNoExplorePathUnchanged:
    def test_free_fall_dispatch_still_works(self):
        """The deterministic free-fall pipeline is completely unaffected."""
        from src.templates.free_fall import build_psdl
        from src.physics.dispatcher import dispatch_with_validation

        psdl = build_psdl(height=5.0, duration=1.0)
        result = dispatch_with_validation(psdl)
        assert result["solver_used"] != ""
        assert "states" in result

    def test_explore_false_by_default(self):
        """build_parser() must default --explore to False."""
        from main import build_parser
        args = build_parser().parse_args(["--question", "test"])
        assert args.explore is False
