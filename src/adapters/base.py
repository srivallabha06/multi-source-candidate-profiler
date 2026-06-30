"""
Base adapter interface and adapter registry.

All source adapters inherit from BaseAdapter and implement
can_handle() and ingest() methods. The AdapterRegistry
auto-detects source types and dispatches to the right adapter.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

from src.models.candidate import RawCandidateRecord

logger = logging.getLogger(__name__)


class BaseAdapter(ABC):
    """
    Abstract base class for all source adapters.

    Each adapter knows how to:
    1. Detect if it can handle a given source (file path or URL).
    2. Ingest the source and produce RawCandidateRecord(s).
    """

    @property
    @abstractmethod
    def source_type(self) -> str:
        """Return the source type identifier (e.g., 'resume_json')."""
        ...

    @abstractmethod
    def can_handle(self, source_path: str) -> bool:
        """
        Check if this adapter can process the given source.

        Args:
            source_path: File path or URL to check.

        Returns:
            True if this adapter should handle this source.
        """
        ...

    @abstractmethod
    def ingest(self, source_path: str) -> List[RawCandidateRecord]:
        """
        Ingest a source and produce raw candidate records.

        Must handle errors gracefully — never crash the pipeline.

        Args:
            source_path: File path or URL to ingest.

        Returns:
            List of RawCandidateRecord objects. May be empty on failure.
        """
        ...

    def _create_record(
        self, data: Dict[str, Any], source_path: str
    ) -> RawCandidateRecord:
        """Helper to create a RawCandidateRecord with standard fields."""
        return RawCandidateRecord(
            source_type=self.source_type,
            source_path=source_path,
            data=data,
            ingested_at=datetime.now(timezone.utc).isoformat(),
        )

    def _safe_read_json(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Safely read and parse a JSON file."""
        import json

        try:
            path = Path(file_path)
            if not path.exists():
                logger.error("File not found: %s", file_path)
                return None

            with open(path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if not content:
                    logger.warning("Empty file: %s", file_path)
                    return None
                return json.loads(content)

        except json.JSONDecodeError as e:
            logger.error("Invalid JSON in '%s': %s", file_path, e)
            return None
        except Exception as e:
            logger.error("Error reading '%s': %s", file_path, e)
            return None


class AdapterRegistry:
    """
    Registry of all available adapters.

    Provides auto-detection: given a source path, it finds the
    right adapter to use. Adapters are tried in registration order.
    """

    def __init__(self) -> None:
        self._adapters: List[BaseAdapter] = []

    def register(self, adapter: BaseAdapter) -> None:
        """Register an adapter."""
        self._adapters.append(adapter)
        logger.debug("Registered adapter: %s", adapter.source_type)

    def register_all(self, adapters: List[BaseAdapter]) -> None:
        """Register multiple adapters."""
        for adapter in adapters:
            self.register(adapter)

    def find_adapter(self, source_path: str) -> Optional[BaseAdapter]:
        """
        Find the first adapter that can handle the given source.

        Returns the adapter or None if no adapter matches.
        """
        for adapter in self._adapters:
            try:
                if adapter.can_handle(source_path):
                    return adapter
            except Exception as e:
                logger.debug(
                    "Adapter %s error checking '%s': %s",
                    adapter.source_type,
                    source_path,
                    e,
                )
        return None

    def ingest(self, source_path: str) -> List[RawCandidateRecord]:
        """
        Auto-detect and ingest a source.

        Returns list of records, or empty list if no adapter matches.
        """
        adapter = self.find_adapter(source_path)
        if not adapter:
            logger.warning("No adapter found for: %s", source_path)
            return []

        logger.info(
            "Ingesting '%s' with adapter '%s'",
            source_path,
            adapter.source_type,
        )
        try:
            return adapter.ingest(source_path)
        except Exception as e:
            logger.error(
                "Adapter '%s' failed on '%s': %s",
                adapter.source_type,
                source_path,
                e,
            )
            return []

    def ingest_all(self, source_paths: List[str]) -> List[RawCandidateRecord]:
        """Ingest multiple sources, collecting all records."""
        all_records: List[RawCandidateRecord] = []
        for path in source_paths:
            records = self.ingest(path)
            all_records.extend(records)
        return all_records

    @property
    def adapter_types(self) -> List[str]:
        """List all registered adapter type names."""
        return [a.source_type for a in self._adapters]
