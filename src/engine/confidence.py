"""
Confidence engine.

Computes deterministic confidence scores for:
- Individual fields
- Candidate identity matches
- Overall profile completeness

All calculations are deterministic and documented.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from src.models.candidate import CanonicalProfile
from src.models.provenance import ProvenanceStore

logger = logging.getLogger(__name__)


# Default source base confidence scores
DEFAULT_SOURCE_SCORES = {
    "resume_json": 0.95,
    "linkedin_json": 0.85,
    "github_repo_language": 0.80,
    "github": 0.80,
    "github_readme_keyword": 0.60,
    "pdf_keyword": 0.50,
    "pdf": 0.50,
    "portfolio_keyword": 0.50,
    "portfolio_web": 0.50,
    "ats_csv": 0.70,
    "ats_json": 0.70,
    "hr_system": 0.90,
    "inferred": 0.40,
}

# Weights for each profile field in overall confidence
FIELD_WEIGHTS = {
    "full_name": 15,
    "emails": 15,
    "phones": 10,
    "location": 5,
    "links": 5,
    "headline": 5,
    "years_experience": 5,
    "skills": 15,
    "experience": 15,
    "education": 10,
}


class ConfidenceEngine:
    """
    Computes confidence scores for profiles and fields.

    Confidence Formula:
    - Field confidence = max(source_confidence for provenance records)
    - Overall confidence = weighted_avg(field_confidences) * coverage_factor
    - Coverage factor = fields_with_data / total_fields

    All calculations are deterministic.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self._config = config or {}
        self._source_scores = self._config.get("confidence", {}).get(
            "source_base_scores", DEFAULT_SOURCE_SCORES
        )

    def compute_profile_confidence(
        self,
        profile: CanonicalProfile,
        provenance_store: ProvenanceStore,
    ) -> float:
        """
        Compute overall confidence for a profile.

        Returns a float between 0.0 and 1.0.
        """
        field_confidences = self.compute_field_confidences(
            profile, provenance_store
        )

        # Weighted average
        total_weight = 0.0
        weighted_sum = 0.0

        for field_name, weight in FIELD_WEIGHTS.items():
            conf = field_confidences.get(field_name, 0.0)
            weighted_sum += conf * weight
            total_weight += weight

        if total_weight == 0:
            return 0.0

        base_confidence = weighted_sum / total_weight

        # Coverage factor: boost for profiles with more data
        coverage = self._compute_coverage(profile)

        # Multi-source bonus: profiles confirmed by multiple sources
        source_count = len(set(
            r.source for r in provenance_store.get_candidate_provenance(
                profile.candidate_id
            )
        ))
        source_bonus = min(source_count * 0.05, 0.15)  # Up to 15% bonus

        overall = min(base_confidence * coverage + source_bonus, 1.0)

        profile.overall_confidence = round(overall, 4)
        return overall

    def compute_field_confidences(
        self,
        profile: CanonicalProfile,
        provenance_store: ProvenanceStore,
    ) -> Dict[str, float]:
        """
        Compute confidence for each field in the profile.

        Returns {field_name: confidence_score}.
        """
        cid = profile.candidate_id
        confidences: Dict[str, float] = {}

        for field_name in FIELD_WEIGHTS:
            provenance_records = provenance_store.get_provenance(
                cid, field_name
            )

            # Also check sub-fields (e.g., "skills.Java", "links.linkedin")
            if not provenance_records:
                all_prov = provenance_store.get_candidate_provenance(cid)
                provenance_records = [
                    r for r in all_prov
                    if r.field.startswith(f"{field_name}.")
                    or r.field == field_name
                ]

            if not provenance_records:
                # No data for this field
                confidences[field_name] = 0.0
                continue

            # Field confidence = max confidence across all provenance records
            max_conf = max(r.confidence for r in provenance_records)

            # Bonus for multi-source confirmation
            sources = set(r.source for r in provenance_records)
            if len(sources) > 1:
                max_conf = min(max_conf + 0.05 * (len(sources) - 1), 1.0)

            confidences[field_name] = round(max_conf, 4)

        return confidences

    def _compute_coverage(self, profile: CanonicalProfile) -> float:
        """
        Compute field coverage ratio.

        Returns the fraction of fields that have data.
        """
        total_fields = len(FIELD_WEIGHTS)
        filled = 0

        if profile.full_name:
            filled += 1
        if profile.emails:
            filled += 1
        if profile.phones:
            filled += 1
        if profile.location and (
            profile.location.city
            or profile.location.country
        ):
            filled += 1
        if profile.links and (
            profile.links.linkedin
            or profile.links.github
        ):
            filled += 1
        if profile.headline:
            filled += 1
        if profile.years_experience is not None:
            filled += 1
        if profile.skills:
            filled += 1
        if profile.experience:
            filled += 1
        if profile.education:
            filled += 1

        return filled / total_fields if total_fields > 0 else 0.0

    def get_source_confidence(self, source_type: str) -> float:
        """Get the base confidence for a source type."""
        return self._source_scores.get(source_type, 0.40)

    def compute_match_confidence(
        self, total_score: float, max_possible_score: float
    ) -> float:
        """
        Compute confidence for an entity match.

        Returns total_score / max_possible_score, capped at 1.0.
        """
        if max_possible_score <= 0:
            return 0.0
        return min(round(total_score / max_possible_score, 4), 1.0)

    def get_confidence_breakdown(
        self,
        profile: CanonicalProfile,
        provenance_store: ProvenanceStore,
    ) -> Dict[str, Any]:
        """
        Generate a detailed confidence breakdown for a profile.

        Used in explainability reports.
        """
        field_confidences = self.compute_field_confidences(
            profile, provenance_store
        )
        coverage = self._compute_coverage(profile)

        # Source contributions
        all_prov = provenance_store.get_candidate_provenance(
            profile.candidate_id
        )
        source_contrib: Dict[str, int] = {}
        for r in all_prov:
            source_contrib[r.source] = source_contrib.get(r.source, 0) + 1

        return {
            "candidate_id": profile.candidate_id,
            "overall_confidence": profile.overall_confidence,
            "field_confidences": field_confidences,
            "coverage": round(coverage, 4),
            "source_contributions": source_contrib,
            "total_provenance_records": len(all_prov),
            "formula": (
                "overall = weighted_avg(field_confidences) * coverage + "
                "multi_source_bonus (max 0.15)"
            ),
        }
