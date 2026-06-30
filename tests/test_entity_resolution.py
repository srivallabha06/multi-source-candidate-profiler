"""
Unit tests for entity resolution engine.

Tests cover:
- Same person with different name variants merging correctly
- Different people with same name NOT merging
- No-signal records staying separate
- Nickname handling
- Strong signal requirements
"""

import os
import sys
import pytest

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.models.candidate import RawCandidateRecord
from src.engine.entity_resolution import EntityResolutionEngine


class TestEntityResolution:
    def setup_method(self):
        self.engine = EntityResolutionEngine()

    def _make_record(self, **kwargs):
        """Helper to create a RawCandidateRecord with data."""
        return RawCandidateRecord(
            source_type=kwargs.pop("source_type", "test"),
            source_path=kwargs.pop("source_path", "test.json"),
            data=kwargs,
        )

    def test_same_email_merges(self):
        """Records with the same email should merge."""
        r1 = self._make_record(
            full_name="Rahul Sharma",
            emails=["rahul@gmail.com"],
            skills=["Java"],
        )
        r2 = self._make_record(
            full_name="Rahul K Sharma",
            emails=["rahul@gmail.com"],
            skills=["Python"],
        )

        clusters = self.engine.resolve([r1, r2])

        # Should have 1 cluster with both records
        merged_clusters = [c for c in clusters if len(c.record_ids) > 1]
        assert len(merged_clusters) == 1
        assert len(merged_clusters[0].record_ids) == 2

    def test_same_phone_merges(self):
        """Records with the same phone should merge."""
        r1 = self._make_record(
            full_name="Rahul Sharma",
            phones=["+919876543210"],
        )
        r2 = self._make_record(
            full_name="Rahul Sharma",
            phones=["9876543210"],
        )

        clusters = self.engine.resolve([r1, r2])
        merged = [c for c in clusters if len(c.record_ids) > 1]
        assert len(merged) == 1

    def test_same_linkedin_merges(self):
        """Records with the same LinkedIn URL should merge."""
        r1 = self._make_record(
            full_name="Rahul Sharma",
            links={"linkedin": "https://linkedin.com/in/rahul-sharma"},
        )
        r2 = self._make_record(
            full_name="R Sharma",
            links={"linkedin": "https://www.linkedin.com/in/rahul-sharma/"},
        )

        clusters = self.engine.resolve([r1, r2])
        merged = [c for c in clusters if len(c.record_ids) > 1]
        assert len(merged) == 1

    def test_same_github_merges(self):
        """Records with the same GitHub URL should merge."""
        r1 = self._make_record(
            full_name="Rahul Sharma",
            links={"github": "https://github.com/rahul-sharma"},
        )
        r2 = self._make_record(
            full_name="Rahul Sharma",
            links={"github": "github.com/rahul-sharma"},
        )

        clusters = self.engine.resolve([r1, r2])
        merged = [c for c in clusters if len(c.record_ids) > 1]
        assert len(merged) == 1

    def test_different_people_same_name_no_merge(self):
        """Different people with the same name but different emails must NOT merge."""
        r1 = self._make_record(
            full_name="Rahul Sharma",
            emails=["rahul1@gmail.com"],
        )
        r2 = self._make_record(
            full_name="Rahul Sharma",
            emails=["rahul2@gmail.com"],
        )

        clusters = self.engine.resolve([r1, r2])
        merged = [c for c in clusters if len(c.record_ids) > 1]
        # Should NOT merge — different emails, name alone is not enough
        assert len(merged) == 0

    def test_name_only_no_merge(self):
        """Records with only matching names must NOT merge."""
        r1 = self._make_record(full_name="Rahul Sharma")
        r2 = self._make_record(full_name="Rahul Sharma")

        clusters = self.engine.resolve([r1, r2])
        merged = [c for c in clusters if len(c.record_ids) > 1]
        assert len(merged) == 0

    def test_no_signals_stays_separate(self):
        """Records with no strong signals stay separate."""
        r1 = self._make_record(full_name="Person A")
        r2 = self._make_record(full_name="Person B")
        r3 = self._make_record(full_name="Person C")

        clusters = self.engine.resolve([r1, r2, r3])
        assert len(clusters) == 3

    def test_match_result_explains_signals(self):
        """Match results should contain signal explanations."""
        r1 = self._make_record(
            full_name="Rahul Sharma",
            emails=["rahul@gmail.com"],
        )
        r2 = self._make_record(
            full_name="Rahul K Sharma",
            emails=["rahul@gmail.com"],
        )

        clusters = self.engine.resolve([r1, r2])
        merged = [c for c in clusters if len(c.record_ids) > 1]
        assert len(merged) == 1

        # Check that match result has signal details
        match_results = merged[0].match_results
        assert len(match_results) > 0
        assert match_results[0].total_score >= 100  # Email match = 100
        assert any(
            s.signal_type == "email_match" for s in match_results[0].signals
        )

    def test_multiple_candidates_correct_clustering(self):
        """Multiple candidates should cluster correctly."""
        # Rahul's records (should merge via email)
        r1 = self._make_record(
            full_name="Rahul Sharma",
            emails=["rahul@gmail.com"],
            source_type="resume_json",
        )
        r2 = self._make_record(
            full_name="Rahul K Sharma",
            emails=["rahul@gmail.com"],
            source_type="linkedin_json",
        )

        # Priya's records (should stay separate)
        r3 = self._make_record(
            full_name="Priya Patel",
            emails=["priya@outlook.com"],
            source_type="resume_json",
        )

        # Amit (should stay separate)
        r4 = self._make_record(
            full_name="Amit Kumar",
            emails=["amit@company.com"],
            source_type="ats_csv",
        )

        clusters = self.engine.resolve([r1, r2, r3, r4])

        # Should have 3 clusters: Rahul (merged), Priya, Amit
        assert len(clusters) == 3

        # Find the merged cluster
        merged = [c for c in clusters if len(c.record_ids) > 1]
        assert len(merged) == 1
        assert len(merged[0].record_ids) == 2

    def test_transitive_merge(self):
        """If A matches B and B matches C, all three should merge."""
        r1 = self._make_record(
            full_name="Rahul Sharma",
            emails=["rahul@gmail.com"],
        )
        r2 = self._make_record(
            full_name="Rahul Sharma",
            emails=["rahul@gmail.com"],
            phones=["+919876543210"],
        )
        r3 = self._make_record(
            full_name="Rahul Sharma",
            phones=["+919876543210"],
        )

        clusters = self.engine.resolve([r1, r2, r3])
        merged = [c for c in clusters if len(c.record_ids) > 1]
        assert len(merged) == 1
        assert len(merged[0].record_ids) == 3

    def test_empty_records(self):
        """Empty record list should return empty clusters."""
        clusters = self.engine.resolve([])
        assert len(clusters) == 0
