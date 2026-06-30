"""
Pipeline orchestrator.

Orchestrates the full candidate data transformation pipeline:
Ingest → Normalize → Resolve → Merge → Score → Output

Features:
- Error isolation per-record (one bad record doesn't crash pipeline)
- Logging at each stage
- Returns profiles + provenance + report data
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.models.candidate import CanonicalProfile, RawCandidateRecord
from src.models.provenance import ProvenanceStore
from src.adapters.base import AdapterRegistry
from src.adapters.resume_json import ResumeJsonAdapter
from src.adapters.linkedin_json import LinkedInJsonAdapter
from src.adapters.github_adapter import GitHubAdapter
from src.adapters.ats_csv import ATSCsvAdapter
from src.adapters.pdf_adapter import PDFAdapter
from src.adapters.portfolio_web import PortfolioWebAdapter
from src.adapters.hr_system import HRSystemAdapter
from src.adapters.ats_json import ATSJsonAdapter
from src.normalizers.skill import SkillNormalizer
from src.engine.entity_resolution import EntityResolutionEngine, CandidateCluster
from src.engine.profile_merger import ProfileMerger
from src.engine.confidence import ConfidenceEngine
from src.output.configurator import OutputConfigurator
from src.output.report import ExplainabilityReport

logger = logging.getLogger(__name__)


class Pipeline:
    """
    Main pipeline orchestrator.

    Usage:
        pipeline = Pipeline(config)
        result = pipeline.run(input_paths, output_config)
    """

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        config_path: Optional[str] = None,
    ) -> None:
        # Load config
        if config:
            self._config = config
        elif config_path:
            self._config = self._load_json(config_path) or {}
        else:
            self._config = {}

        # Initialize components
        self._registry = self._build_registry()
        self._skill_normalizer = self._build_skill_normalizer()
        self._entity_resolver = EntityResolutionEngine(self._config)
        self._provenance_store = ProvenanceStore()
        self._confidence_engine = ConfidenceEngine(self._config)

    def _build_registry(self) -> AdapterRegistry:
        """Build and configure the adapter registry."""
        registry = AdapterRegistry()
        pipeline_config = self._config.get("pipeline", {})

        # Get skill keywords for PDF/web adapters
        skill_keywords = self._get_skill_keywords()

        # Register adapters in priority order
        # (more specific adapters first for correct can_handle dispatch)
        registry.register_all([
            LinkedInJsonAdapter(),
            GitHubAdapter(
                token=pipeline_config.get("github_token") or os.environ.get(
                    pipeline_config.get("github_token_env", "GITHUB_TOKEN"), ""
                ),
                max_repos=pipeline_config.get("max_github_repos", 50),
                request_timeout=pipeline_config.get("request_timeout_seconds", 30),
            ),
            HRSystemAdapter(),
            ResumeJsonAdapter(),
            ATSCsvAdapter(),
            ATSJsonAdapter(),
            PDFAdapter(skill_keywords=skill_keywords),
            PortfolioWebAdapter(
                request_timeout=pipeline_config.get("request_timeout_seconds", 30),
                skill_keywords=skill_keywords,
            ),
        ])

        return registry

    def _build_skill_normalizer(self) -> SkillNormalizer:
        """Build skill normalizer with taxonomy."""
        # Try to find taxonomy file
        taxonomy_paths = [
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "skill_taxonomy.json"),
            "config/skill_taxonomy.json",
            os.path.join(os.getcwd(), "config", "skill_taxonomy.json"),
        ]
        for path in taxonomy_paths:
            if os.path.exists(path):
                return SkillNormalizer(taxonomy_path=path)

        logger.warning("Skill taxonomy not found, using empty taxonomy")
        return SkillNormalizer()

    def _get_skill_keywords(self) -> List[str]:
        """Get skill keywords from taxonomy for PDF/web extraction."""
        normalizer = self._build_skill_normalizer()
        return normalizer.get_canonical_skills()

    def run(
        self,
        input_paths: List[str],
        output_config: Optional[Dict[str, Any]] = None,
        output_config_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Run the full pipeline.

        Args:
            input_paths: List of file paths or directories to ingest.
            output_config: Output schema configuration dict.
            output_config_path: Path to output config JSON file.

        Returns:
            Dict with keys: "profiles", "report", "output"
        """
        logger.info("=" * 60)
        logger.info("PIPELINE START")
        logger.info("=" * 60)

        # Load output config if path provided
        if output_config_path and not output_config:
            output_config = self._load_json(output_config_path)

        # Phase 1: Discover sources
        source_files = self._discover_sources(input_paths)
        logger.info("Phase 1: Discovered %d source files", len(source_files))

        # Phase 2: Ingest
        records = self._ingest(source_files)
        logger.info("Phase 2: Ingested %d records", len(records))

        if not records:
            logger.warning("No records ingested. Pipeline complete.")
            return {
                "profiles": [],
                "report": {"summary": {"total_profiles": 0}},
                "output": [],
            }

        # Phase 3: Entity resolution
        clusters = self._resolve_entities(records)
        logger.info("Phase 3: Resolved into %d clusters", len(clusters))

        # Phase 4: Merge profiles
        record_map = {r.record_id: r for r in records}
        profiles = self._merge_profiles(clusters, record_map)
        logger.info("Phase 4: Merged into %d profiles", len(profiles))

        # Phase 5: Compute confidence scores
        self._compute_confidence(profiles)
        logger.info("Phase 5: Confidence scores computed")

        # Phase 6: Generate output
        output = self._generate_output(profiles, output_config)
        logger.info("Phase 6: Output generated")

        # Phase 7: Generate report
        report = self._generate_report(profiles, clusters)
        logger.info("Phase 7: Report generated")

        logger.info("=" * 60)
        logger.info("PIPELINE COMPLETE: %d profiles", len(profiles))
        logger.info("=" * 60)

        return {
            "profiles": [p.to_dict() for p in profiles],
            "report": report,
            "output": output,
            "provenance": self._provenance_store.to_list(),
        }

    def _discover_sources(self, input_paths: List[str]) -> List[str]:
        """Discover all source files from input paths."""
        files: List[str] = []

        for path_str in input_paths:
            # Pass web URLs directly through to the adapters
            is_url = (
                path_str.lower().startswith(("http://", "https://"))
                or "github.com/" in path_str.lower()
                or "linkedin.com/" in path_str.lower()
            )
            if is_url:
                files.append(path_str)
                continue

            path = Path(path_str)
            if path.is_file():
                files.append(str(path.resolve()))
            elif path.is_dir():
                # Recursively find all files
                for child in sorted(path.rglob("*")):
                    if child.is_file() and not child.name.startswith("."):
                        files.append(str(child.resolve()))
            else:
                logger.warning("Path not found: %s", path_str)

        return files

    def _ingest(
        self, source_files: List[str]
    ) -> List[RawCandidateRecord]:
        """Ingest all source files using the adapter registry."""
        all_records: List[RawCandidateRecord] = []

        for file_path in source_files:
            try:
                records = self._registry.ingest(file_path)
                all_records.extend(records)
                logger.debug(
                    "Ingested %d records from '%s'",
                    len(records),
                    file_path,
                )
            except Exception as e:
                logger.error(
                    "Fatal error ingesting '%s': %s", file_path, e
                )
                # Continue — one bad file doesn't stop the pipeline

        return all_records

    def _resolve_entities(
        self, records: List[RawCandidateRecord]
    ) -> List[CandidateCluster]:
        """Run entity resolution."""
        return self._entity_resolver.resolve(records)

    def _merge_profiles(
        self,
        clusters: List[CandidateCluster],
        record_map: Dict[str, RawCandidateRecord],
    ) -> List[CanonicalProfile]:
        """Merge clusters into canonical profiles."""
        merger = ProfileMerger(
            config=self._config,
            provenance_store=self._provenance_store,
            skill_normalizer=self._skill_normalizer,
        )
        return merger.merge_clusters(clusters, record_map)

    def _compute_confidence(
        self, profiles: List[CanonicalProfile]
    ) -> None:
        """Compute confidence scores for all profiles."""
        for profile in profiles:
            try:
                self._confidence_engine.compute_profile_confidence(
                    profile, self._provenance_store
                )
            except Exception as e:
                logger.error(
                    "Error computing confidence for %s: %s",
                    profile.candidate_id,
                    e,
                )

    def _generate_output(
        self,
        profiles: List[CanonicalProfile],
        output_config: Optional[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Generate configured output."""
        configurator = OutputConfigurator(output_config)

        # Validate config
        issues = configurator.validate_config()
        return configurator.transform_all(profiles, self._provenance_store)

    def _generate_report(
        self,
        profiles: List[CanonicalProfile],
        clusters: List[CandidateCluster],
    ) -> Dict[str, Any]:
        """Generate explainability report."""
        reporter = ExplainabilityReport(self._confidence_engine)
        return reporter.generate(profiles, clusters, self._provenance_store)

    def get_report_text(
        self,
        profiles: List[CanonicalProfile],
        clusters: List[CandidateCluster],
    ) -> str:
        """Generate human-readable report text."""
        reporter = ExplainabilityReport(self._confidence_engine)
        return reporter.to_text(profiles, clusters, self._provenance_store)

    @staticmethod
    def _load_json(path: str) -> Optional[Dict[str, Any]]:
        """Safely load a JSON file."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            logger.error("File not found: %s", path)
            return None
        except json.JSONDecodeError as e:
            logger.error("Invalid JSON in '%s': %s", path, e)
            return None
        except Exception as e:
            logger.error("Error reading '%s': %s", path, e)
            return None
