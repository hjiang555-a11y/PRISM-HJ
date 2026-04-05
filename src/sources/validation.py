"""
Source reference runtime validation (v0.2).

Validates that :class:`~src.schema.psdl.SourceRef` entries in a PSDL document
comply with the source tier governance rules defined in
``data/sources/registry.yaml``.

Rules enforced
--------------
1. ``source_id`` must exist in the registry.
2. The assigned ``role`` must be listed in the source's ``allowed_uses``.
3. Sources with tier ``standards_only`` (e.g. NIST, ITU) cannot carry
   ``primary_template_source``, ``secondary_reference``, or
   ``conceptual_reference`` roles for mechanics scenarios.
4. For mechanics scenarios (``free_fall``, ``projectile``, ``collision``),
   the ``primary_template_source`` role requires ``tier_1_authoritative``.

Bare string source refs (legacy / LLM-generated) are skipped — only
structured :class:`~src.schema.psdl.SourceRef` objects are validated.
"""

from __future__ import annotations

import logging
from typing import List

from src.schema.psdl import PSDL, SourceRef
from src.sources.registry import (
    MECHANICS_SCENARIO_TYPES,
    get_allowed_uses,
    get_tier,
    source_exists,
)

logger = logging.getLogger(__name__)

# Roles that are forbidden for standards_only sources in any mechanics context.
_STANDARDS_ONLY_FORBIDDEN_ROLES: frozenset[str] = frozenset(
    {"primary_template_source", "secondary_reference", "conceptual_reference"}
)

# Roles that require tier_1_authoritative when used in mechanics scenarios.
_MECHANICS_TIER1_REQUIRED_ROLES: frozenset[str] = frozenset(
    {"primary_template_source"}
)


class SourceValidationError(ValueError):
    """Raised when source_refs fail governance validation."""


def validate_source_refs(psdl: PSDL) -> None:
    """
    Validate all :class:`~src.schema.psdl.SourceRef` entries in *psdl*.

    Parameters
    ----------
    psdl:
        A validated PSDL document whose ``source_refs`` list is to be checked.

    Raises
    ------
    SourceValidationError
        On any governance violation (unknown source, tier mismatch, forbidden
        role).
    """
    scenario: str = (psdl.scenario_type or "").lower().strip()
    is_mechanics: bool = scenario in MECHANICS_SCENARIO_TYPES

    for ref in psdl.source_refs:
        # Bare string refs (legacy / LLM-generated) are not validated.
        if not isinstance(ref, SourceRef):
            continue

        sid: str = ref.source_id
        role: str = ref.role

        # Rule 1: source_id must exist in registry.
        if not source_exists(sid):
            raise SourceValidationError(
                f"Unknown source_id {sid!r}: not found in "
                "data/sources/registry.yaml. "
                "Add the source to the registry before referencing it in PSDL "
                "documents."
            )

        tier: str | None = get_tier(sid)
        allowed_uses: List[str] = get_allowed_uses(sid)

        # Rule 2: role must appear in allowed_uses.
        if role not in allowed_uses:
            raise SourceValidationError(
                f"Source {sid!r} (tier={tier!r}) does not permit role "
                f"{role!r}. Allowed roles for this source: {allowed_uses}."
            )

        # Rule 3: standards_only sources banned from mechanics content roles.
        if tier == "standards_only" and is_mechanics:
            if role in _STANDARDS_ONLY_FORBIDDEN_ROLES:
                raise SourceValidationError(
                    f"Source {sid!r} has tier 'standards_only' and cannot be "
                    f"used as {role!r} for mechanics scenario {scenario!r}. "
                    "NIST/ITU sources are restricted to units/metrology "
                    "references only — they must not appear as template or "
                    "content sources for free_fall, projectile, or collision."
                )

        # Rule 4: primary_template_source for mechanics → tier_1_authoritative.
        if is_mechanics and role in _MECHANICS_TIER1_REQUIRED_ROLES:
            if tier != "tier_1_authoritative":
                raise SourceValidationError(
                    f"Mechanics scenario {scenario!r} requires a "
                    "'tier_1_authoritative' source for role {role!r}, but "
                    f"{sid!r} has tier {tier!r}. Use an OpenStax or MIT OCW "
                    "source as the primary template source."
                )

    logger.debug(
        "validate_source_refs: %d structured refs validated (scenario=%r).",
        sum(1 for r in psdl.source_refs if isinstance(r, SourceRef)),
        scenario,
    )
