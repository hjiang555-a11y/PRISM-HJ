"""
Tests for source registry runtime validation (src.sources.*).

Verifies:
* Registry loader correctly reads data/sources/registry.yaml.
* source_exists / get_tier / get_allowed_uses helpers work correctly.
* validate_source_refs enforces all four governance rules.
"""

from __future__ import annotations

import pytest

from src.schema.psdl import PSDL, ParticleObject, SourceRef, WorldSettings
from src.sources.registry import (
    get_allowed_uses,
    get_tier,
    source_exists,
    get_all_sources,
)
from src.sources.validation import SourceValidationError, validate_source_refs


# ---------------------------------------------------------------------------
# Registry loader helpers
# ---------------------------------------------------------------------------

class TestRegistryLoader:
    def test_all_sources_not_empty(self):
        sources = get_all_sources()
        assert len(sources) >= 7

    def test_known_source_exists(self):
        assert source_exists("openstax_university_physics_v1")

    def test_unknown_source_does_not_exist(self):
        assert not source_exists("nonexistent_source_xyz")

    def test_get_tier_tier1(self):
        assert get_tier("openstax_university_physics_v1") == "tier_1_authoritative"

    def test_get_tier_standards_only_nist(self):
        assert get_tier("nist_time_frequency_division") == "standards_only"

    def test_get_tier_standards_only_itu(self):
        assert get_tier("itu_time_frequency_handbook") == "standards_only"

    def test_get_tier_tier2(self):
        assert get_tier("feynman_lectures_online") == "tier_2_high_quality_educational"

    def test_get_allowed_uses_tier1(self):
        uses = get_allowed_uses("openstax_university_physics_v1")
        assert "primary_template_source" in uses
        assert "secondary_reference" in uses

    def test_get_allowed_uses_standards_only_nist(self):
        uses = get_allowed_uses("nist_time_frequency_division")
        assert "units_reference" in uses
        assert "metrology_reference" in uses
        assert "primary_template_source" not in uses

    def test_get_tier_unknown_returns_none(self):
        assert get_tier("does_not_exist") is None

    def test_get_allowed_uses_unknown_returns_empty(self):
        assert get_allowed_uses("does_not_exist") == []


# ---------------------------------------------------------------------------
# Helpers to build minimal PSDL
# ---------------------------------------------------------------------------

def _psdl_with_refs(
    scenario_type: str | None,
    source_refs: list,
) -> PSDL:
    return PSDL(
        scenario_type=scenario_type,
        source_refs=source_refs,
        world=WorldSettings(gravity=[0.0, 0.0, -9.8], dt=0.01, steps=100),
        objects=[
            ParticleObject(
                mass=1.0, radius=0.1,
                position=[0.0, 0.0, 5.0],
                velocity=[0.0, 0.0, 0.0],
            )
        ],
    )


# ---------------------------------------------------------------------------
# Rule 1: source_id must exist in registry
# ---------------------------------------------------------------------------

class TestRuleUnknownSourceId:
    def test_unknown_source_id_raises(self):
        psdl = _psdl_with_refs(
            "free_fall",
            [SourceRef(source_id="nonexistent_book", role="secondary_reference")],
        )
        with pytest.raises(SourceValidationError, match="Unknown source_id"):
            validate_source_refs(psdl)

    def test_known_source_does_not_raise(self):
        psdl = _psdl_with_refs(
            "free_fall",
            [SourceRef(source_id="openstax_university_physics_v1",
                       role="primary_template_source")],
        )
        validate_source_refs(psdl)  # Should not raise


# ---------------------------------------------------------------------------
# Rule 2: role must be in allowed_uses
# ---------------------------------------------------------------------------

class TestRoleAllowedUses:
    def test_role_not_in_allowed_uses_raises(self):
        # conceptual_reference is a valid PSDL role but NOT in nist's allowed_uses
        psdl = _psdl_with_refs(
            None,
            [SourceRef(source_id="nist_time_frequency_division",
                       role="conceptual_reference")],
        )
        with pytest.raises(SourceValidationError, match="does not permit role"):
            validate_source_refs(psdl)

    def test_valid_role_in_allowed_uses_passes(self):
        psdl = _psdl_with_refs(
            None,
            [SourceRef(source_id="nist_time_frequency_division",
                       role="units_reference")],
        )
        validate_source_refs(psdl)  # Should not raise

    def test_tier2_secondary_ref_passes(self):
        """feynman has secondary_reference in its allowed_uses."""
        psdl = _psdl_with_refs(
            None,
            [SourceRef(source_id="feynman_lectures_online",
                       role="secondary_reference")],
        )
        validate_source_refs(psdl)  # Should not raise

    def test_tier2_primary_template_source_raises(self):
        """feynman does NOT have primary_template_source in its allowed_uses."""
        psdl = _psdl_with_refs(
            None,
            [SourceRef(source_id="feynman_lectures_online",
                       role="primary_template_source")],
        )
        with pytest.raises(SourceValidationError, match="does not permit role"):
            validate_source_refs(psdl)


# ---------------------------------------------------------------------------
# Rule 3 & 4: mechanics scenario constraints
# ---------------------------------------------------------------------------

class TestMechanicsConstraints:
    @pytest.mark.parametrize("scenario", ["free_fall", "projectile", "collision"])
    def test_nist_units_reference_in_mechanics_passes(self, scenario):
        """units_reference is not forbidden for mechanics; it's just not the template source."""
        psdl = _psdl_with_refs(
            scenario,
            [
                SourceRef(source_id="openstax_university_physics_v1",
                          role="primary_template_source"),
                SourceRef(source_id="nist_time_frequency_division",
                          role="units_reference"),
            ],
        )
        validate_source_refs(psdl)  # Should not raise

    @pytest.mark.parametrize("scenario", ["free_fall", "projectile", "collision"])
    def test_nist_metrology_reference_in_mechanics_passes(self, scenario):
        """metrology_reference for nist in mechanics is fine (not a template role)."""
        psdl = _psdl_with_refs(
            scenario,
            [
                SourceRef(source_id="openstax_university_physics_v1",
                          role="primary_template_source"),
                SourceRef(source_id="nist_time_frequency_division",
                          role="metrology_reference"),
            ],
        )
        validate_source_refs(psdl)  # Should not raise

    @pytest.mark.parametrize("scenario", ["free_fall", "projectile", "collision"])
    def test_tier1_as_primary_in_mechanics_passes(self, scenario):
        psdl = _psdl_with_refs(
            scenario,
            [SourceRef(source_id="openstax_university_physics_v1",
                       role="primary_template_source")],
        )
        validate_source_refs(psdl)  # Should not raise

    def test_rule3_standards_only_secondary_ref_rejected_via_patched_allowed_uses(
        self, monkeypatch
    ):
        """
        Rule 3 defence-in-depth: standards_only source blocked from
        secondary_reference in mechanics even if allowed_uses were widened.

        We patch validate_source_refs' imported get_allowed_uses so that
        nist_time_frequency_division appears to allow secondary_reference,
        then verify Rule 3 still blocks it.
        """
        import src.sources.validation as val_module
        original_get_allowed_uses = val_module.get_allowed_uses

        def patched_allowed_uses(source_id: str):
            if source_id == "nist_time_frequency_division":
                return ["units_reference", "metrology_reference", "secondary_reference"]
            return original_get_allowed_uses(source_id)

        monkeypatch.setattr(val_module, "get_allowed_uses", patched_allowed_uses)

        psdl = _psdl_with_refs(
            "free_fall",
            [SourceRef(source_id="nist_time_frequency_division",
                       role="secondary_reference")],
        )
        with pytest.raises(SourceValidationError, match="standards_only"):
            validate_source_refs(psdl)

    def test_rule4_tier2_primary_source_rejected_via_patched_allowed_uses(
        self, monkeypatch
    ):
        """
        Rule 4 defence-in-depth: tier_2 source blocked from primary_template_source
        in mechanics even if allowed_uses were widened.
        """
        import src.sources.validation as val_module
        original_get_allowed_uses = val_module.get_allowed_uses

        def patched_allowed_uses(source_id: str):
            if source_id == "feynman_lectures_online":
                return ["secondary_reference", "conceptual_reference",
                        "primary_template_source"]
            return original_get_allowed_uses(source_id)

        monkeypatch.setattr(val_module, "get_allowed_uses", patched_allowed_uses)

        psdl = _psdl_with_refs(
            "projectile",
            [SourceRef(source_id="feynman_lectures_online",
                       role="primary_template_source")],
        )
        with pytest.raises(SourceValidationError, match="tier_1_authoritative"):
            validate_source_refs(psdl)


# ---------------------------------------------------------------------------
# Free-fall and projectile templates pass source validation
# ---------------------------------------------------------------------------

class TestTemplatePSDLsPassValidation:
    def test_free_fall_template_passes(self):
        from src.physics.legacy.templates.free_fall import build_psdl
        psdl = build_psdl()
        validate_source_refs(psdl)  # Should not raise

    def test_projectile_template_passes(self):
        from src.physics.legacy.templates.projectile import build_psdl
        psdl = build_psdl()
        validate_source_refs(psdl)  # Should not raise

    def test_collision_template_passes(self):
        from src.physics.legacy.templates.collision import build_psdl
        psdl = build_psdl()
        validate_source_refs(psdl)  # Should not raise

    def test_bare_string_refs_are_skipped(self):
        """Legacy string refs (from LLM) are not validated — no error."""
        psdl = _psdl_with_refs(
            "free_fall",
            ["some_unregistered_string_ref", "another_string"],
        )
        validate_source_refs(psdl)  # Should not raise

