"""
Conflict resolution for scalar fields.

When multiple sources disagree on a value, this module applies
deterministic rules to pick the winning value.

Rules (in order):
1. Trust hierarchy (configurable source ranking).
2. Most recent source (if same rank).
3. Highest confidence source.

Every decision is logged — no silent overwrites.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

DEFAULT_TRUST_HIERARCHY = [
    "resume_json",
    "linkedin_json",
    "github",
    "ats_csv",
    "ats_json",
    "hr_system",
    "portfolio_web",
    "pdf",
]


class ConflictResolver:
    """
    Resolves conflicts when multiple sources provide different
    values for the same scalar field.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self._config = config or {}
        cr_config = self._config.get("conflict_resolution", {})
        self._trust_hierarchy = cr_config.get(
            "trust_hierarchy", DEFAULT_TRUST_HIERARCHY
        )
        # Build rank lookup: lower rank = higher trust
        self._trust_rank: Dict[str, int] = {
            source: idx for idx, source in enumerate(self._trust_hierarchy)
        }

    def resolve_scalar(
        self,
        field_name: str,
        candidates: List[Tuple[Any, str, str]],
    ) -> Tuple[Any, str, str]:
        """
        Resolve a scalar field conflict.

        Args:
            field_name: Name of the field being resolved.
            candidates: List of (value, source_type, source_path) tuples.

        Returns:
            (chosen_value, chosen_source_type, chosen_source_path)
        """
        if not candidates:
            return None, "", ""

        if len(candidates) == 1:
            return candidates[0]

        # Log the conflict
        logger.info(
            "Conflict on field '%s': %d sources disagree",
            field_name,
            len(candidates),
        )
        for val, src, path in candidates:
            logger.debug("  %s (%s): %s", src, path, repr(val))

        # Sort by trust rank (lower = higher trust)
        sorted_candidates = sorted(
            candidates,
            key=lambda c: self._get_rank(c[1]),
        )

        chosen = sorted_candidates[0]

        logger.info(
            "Conflict resolution for '%s': chose '%s' from source '%s' "
            "(trust rank: %d). Rejected: %s",
            field_name,
            repr(chosen[0]),
            chosen[1],
            self._get_rank(chosen[1]),
            ", ".join(
                f"'{repr(c[0])}' from '{c[1]}'"
                for c in sorted_candidates[1:]
            ),
        )

        return chosen

    def _get_rank(self, source_type: str) -> int:
        """Get trust rank for a source type. Unknown sources get lowest rank."""
        return self._trust_rank.get(source_type, len(self._trust_hierarchy))

    def get_resolution_explanation(
        self,
        field_name: str,
        candidates: List[Tuple[Any, str, str]],
    ) -> Dict[str, Any]:
        """
        Generate an explanation of the conflict resolution decision.

        Returns a dict with full details for the explainability report.
        """
        if len(candidates) <= 1:
            return {
                "field": field_name,
                "conflict": False,
                "chosen_value": candidates[0][0] if candidates else None,
                "chosen_source": candidates[0][1] if candidates else None,
            }

        sorted_candidates = sorted(
            candidates,
            key=lambda c: self._get_rank(c[1]),
        )

        return {
            "field": field_name,
            "conflict": True,
            "chosen_value": sorted_candidates[0][0],
            "chosen_source": sorted_candidates[0][1],
            "chosen_reason": (
                f"Source '{sorted_candidates[0][1]}' has highest trust rank "
                f"({self._get_rank(sorted_candidates[0][1])})"
            ),
            "rejected": [
                {
                    "value": c[0],
                    "source": c[1],
                    "trust_rank": self._get_rank(c[1]),
                }
                for c in sorted_candidates[1:]
            ],
        }
