"""
Tests for the reference source registry (data/sources/registry.yaml)
and source governance policy constraints.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REGISTRY_PATH = Path(__file__).parent.parent / "data" / "sources" / "registry.yaml"

# IDs that must be present
REQUIRED_IDS = {
    "openstax_university_physics_v1",
    "openstax_college_physics_2e",
    "mit_ocw_physics",
    "feynman_lectures_online",
    "motion_mountain",
    "nist_time_frequency_division",
    "itu_time_frequency_handbook",
}

# Required top-level fields for every entry
REQUIRED_FIELDS = {"id", "title", "organization", "url", "tier", "subject_areas",
                   "allowed_uses", "status", "notes"}

# Standards-only sources that must NOT allow mechanics template uses
STANDARDS_ONLY_IDS = {"nist_time_frequency_division", "itu_time_frequency_handbook"}

# Uses that are forbidden for standards-only sources
FORBIDDEN_MECHANICS_USES = {"primary_template_source", "secondary_reference",
                             "validation_case_basis", "conceptual_reference"}

# Mechanics template source IDs that must belong to tier_1_authoritative
TIER1_MECHANICS_IDS = {
    "openstax_university_physics_v1",
    "openstax_college_physics_2e",
    "mit_ocw_physics",
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def registry() -> dict:
    """Load and return the parsed registry YAML."""
    assert REGISTRY_PATH.exists(), f"Registry file not found: {REGISTRY_PATH}"
    data = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    assert isinstance(data, dict), "Registry YAML must be a mapping at top level"
    assert "sources" in data, "Registry must have a 'sources' key"
    return data


@pytest.fixture(scope="module")
def sources_by_id(registry) -> dict:
    """Return a mapping of id → source entry dict."""
    return {entry["id"]: entry for entry in registry["sources"]}


# ---------------------------------------------------------------------------
# Structure tests
# ---------------------------------------------------------------------------

class TestRegistryCanLoad:
    def test_file_exists(self):
        assert REGISTRY_PATH.exists()

    def test_yaml_parses(self, registry):
        assert "sources" in registry

    def test_sources_is_list(self, registry):
        assert isinstance(registry["sources"], list)

    def test_sources_not_empty(self, registry):
        assert len(registry["sources"]) > 0


class TestRegistryRequiredEntries:
    def test_all_required_ids_present(self, sources_by_id):
        for sid in REQUIRED_IDS:
            assert sid in sources_by_id, f"Missing required source id: {sid!r}"

    def test_every_entry_has_required_fields(self, registry):
        for entry in registry["sources"]:
            for field in REQUIRED_FIELDS:
                assert field in entry, (
                    f"Source {entry.get('id', '?')!r} missing required field {field!r}"
                )

    def test_allowed_uses_is_list(self, registry):
        for entry in registry["sources"]:
            assert isinstance(entry["allowed_uses"], list), (
                f"allowed_uses must be a list in source {entry['id']!r}"
            )

    def test_subject_areas_is_list(self, registry):
        for entry in registry["sources"]:
            assert isinstance(entry["subject_areas"], list), (
                f"subject_areas must be a list in source {entry['id']!r}"
            )

    def test_status_is_valid(self, registry):
        valid_statuses = {"active", "pending", "deprecated"}
        for entry in registry["sources"]:
            assert entry["status"] in valid_statuses, (
                f"Source {entry['id']!r} has invalid status {entry['status']!r}"
            )


# ---------------------------------------------------------------------------
# Tier and policy tests
# ---------------------------------------------------------------------------

class TestSourceTiers:
    def test_tier1_sources_have_correct_tier(self, sources_by_id):
        for sid in TIER1_MECHANICS_IDS:
            entry = sources_by_id[sid]
            assert entry["tier"] == "tier_1_authoritative", (
                f"{sid!r} should be tier_1_authoritative, got {entry['tier']!r}"
            )

    def test_feynman_is_tier2(self, sources_by_id):
        entry = sources_by_id["feynman_lectures_online"]
        assert entry["tier"] == "tier_2_high_quality_educational"

    def test_motion_mountain_is_tier2(self, sources_by_id):
        entry = sources_by_id["motion_mountain"]
        assert entry["tier"] == "tier_2_high_quality_educational"

    def test_nist_is_standards_only(self, sources_by_id):
        assert sources_by_id["nist_time_frequency_division"]["tier"] == "standards_only"

    def test_itu_is_standards_only(self, sources_by_id):
        assert sources_by_id["itu_time_frequency_handbook"]["tier"] == "standards_only"


class TestStandardsOnlyPolicyConstraints:
    """NIST and ITU must not allow mechanics template uses."""

    @pytest.mark.parametrize("source_id", sorted(STANDARDS_ONLY_IDS))
    def test_standards_only_has_no_forbidden_uses(self, sources_by_id, source_id):
        entry = sources_by_id[source_id]
        actual_uses = set(entry["allowed_uses"])
        forbidden_present = actual_uses & FORBIDDEN_MECHANICS_USES
        assert not forbidden_present, (
            f"Standards-only source {source_id!r} must not allow mechanics uses, "
            f"but found: {forbidden_present}"
        )

    @pytest.mark.parametrize("source_id", sorted(STANDARDS_ONLY_IDS))
    def test_standards_only_allows_metrology_uses(self, sources_by_id, source_id):
        entry = sources_by_id[source_id]
        actual_uses = set(entry["allowed_uses"])
        assert actual_uses & {"units_reference", "metrology_reference"}, (
            f"Standards-only source {source_id!r} should allow at least one metrology use"
        )


class TestTier1AllowsTemplatePrimaryUse:
    @pytest.mark.parametrize("source_id", sorted(TIER1_MECHANICS_IDS))
    def test_tier1_allows_primary_template_source(self, sources_by_id, source_id):
        entry = sources_by_id[source_id]
        assert "primary_template_source" in entry["allowed_uses"], (
            f"Tier-1 source {source_id!r} must allow primary_template_source"
        )


# ---------------------------------------------------------------------------
# Free-fall template source policy tests
# ---------------------------------------------------------------------------

class TestFreeFallTemplateSourcePolicy:
    """Verify that the free_fall template does not reference standards-only sources."""

    def test_free_fall_default_source_refs_are_tier1(self, sources_by_id):
        from src.physics.legacy.templates.free_fall import _DEFAULT_SOURCE_REFS, build_psdl

        # Check default refs
        for ref in _DEFAULT_SOURCE_REFS:
            sid = ref.source_id
            assert sid in sources_by_id, f"Default source ref {sid!r} not in registry"
            tier = sources_by_id[sid]["tier"]
            assert tier in ("tier_1_authoritative", "tier_2_high_quality_educational"), (
                f"Default free_fall source {sid!r} should not be standards_only, got {tier!r}"
            )

    def test_free_fall_default_does_not_reference_nist(self):
        from src.physics.legacy.templates.free_fall import _DEFAULT_SOURCE_REFS

        ids = {r.source_id for r in _DEFAULT_SOURCE_REFS}
        assert "nist_time_frequency_division" not in ids, (
            "NIST must not be a default source ref for free_fall template"
        )

    def test_free_fall_default_does_not_reference_itu(self):
        from src.physics.legacy.templates.free_fall import _DEFAULT_SOURCE_REFS

        ids = {r.source_id for r in _DEFAULT_SOURCE_REFS}
        assert "itu_time_frequency_handbook" not in ids, (
            "ITU must not be a default source ref for free_fall template"
        )

    def test_free_fall_template_primary_source_role(self):
        from src.physics.legacy.templates.free_fall import _DEFAULT_SOURCE_REFS

        roles = {r.role for r in _DEFAULT_SOURCE_REFS}
        assert "primary_template_source" in roles, (
            "free_fall template defaults must include at least one primary_template_source"
        )

    def test_build_psdl_source_refs_are_source_ref_objects(self):
        from src.schema.psdl import SourceRef
        from src.physics.legacy.templates.free_fall import build_psdl

        psdl = build_psdl()
        # Default source_refs should contain SourceRef objects
        assert len(psdl.source_refs) > 0
        for ref in psdl.source_refs:
            assert isinstance(ref, SourceRef), (
                f"Expected SourceRef, got {type(ref).__name__}"
            )
