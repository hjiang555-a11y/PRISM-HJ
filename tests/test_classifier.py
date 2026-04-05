"""
Tests for the rule-based scenario classifier
(src/llm/translator.classify_scenario).
"""

from __future__ import annotations

import pytest

from src.llm.translator import classify_scenario


# ---------------------------------------------------------------------------
# free_fall
# ---------------------------------------------------------------------------

class TestClassifyFreeFall:
    @pytest.mark.parametrize("query", [
        "一个2kg的球自由落体，1秒后位置？",
        "物体自由下落，求末速度",
        "从5米高处落下，忽略空气阻力",
        "从高度10m处释放，求落地时间",
        "A ball is dropped from a height of 10 m",
        "an object falls from rest from height 5 m",
        "a stone is dropped from the top of a building",
        "free fall from 20 meters",
        "object released from height h",
        "vertical drop from 15 m",
    ])
    def test_free_fall_detected(self, query):
        result = classify_scenario(query)
        assert result == "free_fall", (
            f"Expected 'free_fall' for query {query!r}, got {result!r}"
        )


# ---------------------------------------------------------------------------
# projectile
# ---------------------------------------------------------------------------

class TestClassifyProjectile:
    @pytest.mark.parametrize("query", [
        "以初速度10m/s水平抛出，2秒后位置？",
        "水平抛出一个小球，求落地点",
        "平抛运动，初速度5m/s",
        "斜抛运动，45度角抛出",
        "a ball is thrown horizontally at 20 m/s",
        "projectile motion from a cliff",
        "launched at an angle of 30 degrees",
        "initial horizontal velocity of 15 m/s",
    ])
    def test_projectile_detected(self, query):
        result = classify_scenario(query)
        assert result == "projectile", (
            f"Expected 'projectile' for query {query!r}, got {result!r}"
        )


# ---------------------------------------------------------------------------
# collision
# ---------------------------------------------------------------------------

class TestClassifyCollision:
    @pytest.mark.parametrize("query", [
        "两球碰撞，碰后速度各是多少？",
        "弹性碰撞，求末速度",
        "非弹性碰撞问题",
        "两个小球发生碰后各自速度",
        "two balls collide elastically",
        "elastic collision between two objects",
        "inelastic collision, final velocity?",
        "a ball strikes another ball at rest",
        "the impact between two carts",
    ])
    def test_collision_detected(self, query):
        result = classify_scenario(query)
        assert result == "collision", (
            f"Expected 'collision' for query {query!r}, got {result!r}"
        )


# ---------------------------------------------------------------------------
# Unknown / None
# ---------------------------------------------------------------------------

class TestClassifyUnknown:
    @pytest.mark.parametrize("query", [
        "calculate the electric potential",
        "什么是量子纠缠",
        "find the period of a pendulum",
        "a circuit with resistance 10 ohms",
        "热力学第二定律",
    ])
    def test_unknown_returns_none(self, query):
        result = classify_scenario(query)
        assert result is None, (
            f"Expected None for query {query!r}, got {result!r}"
        )


# ---------------------------------------------------------------------------
# Return type contract
# ---------------------------------------------------------------------------

class TestClassifyReturnType:
    def test_returns_string_or_none(self):
        for q in ["自由落体", "水平抛出", "碰撞", "random text"]:
            result = classify_scenario(q)
            assert result is None or isinstance(result, str)

    def test_empty_string_returns_none(self):
        assert classify_scenario("") is None

    def test_whitespace_returns_none(self):
        assert classify_scenario("   ") is None


# ---------------------------------------------------------------------------
# Integration with text_to_psdl path (smoke test — no LLM required)
# ---------------------------------------------------------------------------

class TestClassifierIntegration:
    """Verify the classifier output is compatible with scenario_type values used by dispatcher."""

    @pytest.mark.parametrize("query,expected", [
        ("自由落体运动", "free_fall"),
        ("水平抛体", "projectile"),
        ("两球碰撞", "collision"),
        ("unknown scenario xyz", None),
    ])
    def test_output_is_valid_scenario_type(self, query, expected):
        result = classify_scenario(query)
        assert result == expected, (
            f"classify_scenario({query!r}) returned {result!r}, expected {expected!r}"
        )
