"""
Provenance tracking models.

Every field value in a canonical profile is traced back to its source
through ProvenanceRecord entries stored in a ProvenanceStore.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field as dc_field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class ProvenanceRecord:
    """
    A single provenance entry linking a field value to its source.

    Attributes:
        candidate_id: The canonical candidate this provenance belongs to.
        field: The field path (e.g., "skills", "full_name", "emails[0]").
        value: The actual value recorded.
        source: The source type (e.g., "resume_json", "github").
        source_path: The specific file or URL.
        method: How the value was derived (e.g., "direct_assertion",
                "repo_language_analysis", "keyword_extraction",
                "conflict_resolution").
        confidence: Confidence score for this value (0.0–1.0).
        timestamp: When this record was created (ISO format).
        metadata: Any additional context (e.g., conflict details).
    """
    candidate_id: str = ""
    field: str = ""
    value: Any = None
    source: str = ""
    source_path: str = ""
    method: str = "direct_assertion"
    confidence: float = 0.0
    timestamp: str = dc_field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    metadata: Dict[str, Any] = dc_field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "field": self.field,
            "value": self.value if not isinstance(self.value, (set, frozenset)) else list(self.value),
            "source": self.source,
            "source_path": self.source_path,
            "method": self.method,
            "confidence": self.confidence,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


class ProvenanceStore:
    """
    Append-only store for provenance records.

    Records are keyed by (candidate_id, field) for efficient lookup.
    Thread-safe for single-writer scenarios (typical pipeline usage).
    """

    def __init__(self) -> None:
        # Main storage: list of all records
        self._records: List[ProvenanceRecord] = []
        # Index: (candidate_id, field) -> list of record indices
        self._index: Dict[tuple, List[int]] = {}

    def add(self, record: ProvenanceRecord) -> None:
        """Add a provenance record."""
        idx = len(self._records)
        self._records.append(record)
        key = (record.candidate_id, record.field)
        if key not in self._index:
            self._index[key] = []
        self._index[key].append(idx)

    def add_field(
        self,
        candidate_id: str,
        field_name: str,
        value: Any,
        source: str,
        source_path: str = "",
        method: str = "direct_assertion",
        confidence: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ProvenanceRecord:
        """Convenience method to create and add a provenance record."""
        record = ProvenanceRecord(
            candidate_id=candidate_id,
            field=field_name,
            value=value,
            source=source,
            source_path=source_path,
            method=method,
            confidence=confidence,
            metadata=metadata or {},
        )
        self.add(record)
        return record

    def get_provenance(
        self, candidate_id: str, field_name: str
    ) -> List[ProvenanceRecord]:
        """Get all provenance records for a specific candidate field."""
        key = (candidate_id, field_name)
        indices = self._index.get(key, [])
        return [self._records[i] for i in indices]

    def get_candidate_provenance(
        self, candidate_id: str
    ) -> List[ProvenanceRecord]:
        """Get all provenance records for a candidate."""
        return [r for r in self._records if r.candidate_id == candidate_id]

    def get_all(self) -> List[ProvenanceRecord]:
        """Get all provenance records."""
        return list(self._records)

    def merge_candidate_ids(
        self, old_candidate_id: str, new_candidate_id: str
    ) -> None:
        """Re-key all records from old_candidate_id to new_candidate_id."""
        keys_to_update = [
            k for k in self._index if k[0] == old_candidate_id
        ]
        for old_key in keys_to_update:
            indices = self._index.pop(old_key)
            new_key = (new_candidate_id, old_key[1])
            if new_key not in self._index:
                self._index[new_key] = []
            self._index[new_key].extend(indices)
            for idx in indices:
                self._records[idx].candidate_id = new_candidate_id

    def to_list(self) -> List[Dict[str, Any]]:
        """Serialize all records to a list of dicts."""
        return [r.to_dict() for r in self._records]

    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_list(), indent=indent, default=str)

    def __len__(self) -> int:
        return len(self._records)
