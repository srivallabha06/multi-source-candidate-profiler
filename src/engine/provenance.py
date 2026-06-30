"""
Provenance tracker.

Convenience layer over ProvenanceStore that provides
a high-level API for the pipeline to record provenance.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.models.provenance import ProvenanceRecord, ProvenanceStore


class ProvenanceTracker:
    """
    High-level provenance tracking API.

    Wraps ProvenanceStore and provides convenience methods
    for the pipeline to record and query provenance.
    """

    def __init__(
        self, store: Optional[ProvenanceStore] = None
    ) -> None:
        self._store = store or ProvenanceStore()

    @property
    def store(self) -> ProvenanceStore:
        return self._store

    def track(
        self,
        candidate_id: str,
        field: str,
        value: Any,
        source: str,
        source_path: str = "",
        method: str = "direct_assertion",
        confidence: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ProvenanceRecord:
        """Record a provenance entry."""
        return self._store.add_field(
            candidate_id=candidate_id,
            field_name=field,
            value=value,
            source=source,
            source_path=source_path,
            method=method,
            confidence=confidence,
            metadata=metadata,
        )

    def get_field_history(
        self, candidate_id: str, field: str
    ) -> List[ProvenanceRecord]:
        """Get all provenance records for a specific field."""
        return self._store.get_provenance(candidate_id, field)

    def get_candidate_history(
        self, candidate_id: str
    ) -> List[ProvenanceRecord]:
        """Get all provenance records for a candidate."""
        return self._store.get_candidate_provenance(candidate_id)

    def explain_field(
        self, candidate_id: str, field: str
    ) -> Dict[str, Any]:
        """
        Explain why a field has its current value.

        Returns a dict with provenance chain details.
        """
        records = self.get_field_history(candidate_id, field)
        if not records:
            return {
                "field": field,
                "candidate_id": candidate_id,
                "explanation": "No provenance records found",
                "records": [],
            }

        return {
            "field": field,
            "candidate_id": candidate_id,
            "current_value": records[-1].value,
            "source_count": len(set(r.source for r in records)),
            "sources": list(set(r.source for r in records)),
            "records": [r.to_dict() for r in records],
        }

    def merge_ids(
        self, old_id: str, new_id: str
    ) -> None:
        """Re-key provenance records during entity resolution."""
        self._store.merge_candidate_ids(old_id, new_id)

    def to_json(self) -> str:
        """Serialize all provenance to JSON."""
        return self._store.to_json()

    def __len__(self) -> int:
        return len(self._store)
