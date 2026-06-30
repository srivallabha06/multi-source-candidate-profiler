"""
Integration tests for the full pipeline.

Tests the complete flow: Ingest → Resolve → Merge → Score → Output
using sample data files.
"""

import json
import os
import sys
import pytest

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.pipeline import Pipeline


class TestPipeline:
    @pytest.fixture
    def sample_data_dir(self):
        return os.path.join(project_root, "sample_data")

    @pytest.fixture
    def pipeline_config(self):
        config_path = os.path.join(project_root, "config", "default_config.json")
        with open(config_path, "r") as f:
            return json.load(f)

    @pytest.fixture
    def output_config(self):
        config_path = os.path.join(project_root, "config", "output_config.json")
        with open(config_path, "r") as f:
            return json.load(f)

    def test_full_pipeline_runs(self, sample_data_dir, pipeline_config, output_config):
        """Pipeline should run without errors on sample data."""
        pipeline = Pipeline(config=pipeline_config)
        result = pipeline.run(
            input_paths=[sample_data_dir],
            output_config=output_config,
        )

        assert "profiles" in result
        assert "report" in result
        assert "output" in result
        assert len(result["profiles"]) > 0

    def test_rahul_records_merge(self, sample_data_dir, pipeline_config):
        """Rahul's resume, LinkedIn, GitHub, and ATS records should merge."""
        pipeline = Pipeline(config=pipeline_config)
        result = pipeline.run(input_paths=[sample_data_dir])

        profiles = result["profiles"]

        # Find Rahul's profile
        rahul_profiles = [
            p for p in profiles
            if p.get("full_name") and "rahul" in p["full_name"].lower()
        ]

        # Should be exactly 1 merged Rahul profile
        assert len(rahul_profiles) == 1

        rahul = rahul_profiles[0]

        # Should have been merged from multiple sources
        assert len(rahul.get("merged_from", [])) > 1

        # Should have the email
        assert "rahul.sharma@gmail.com" in rahul.get("emails", [])

        # Should have skills from multiple sources
        skill_names = [s["name"] for s in rahul.get("skills", [])]
        assert len(skill_names) > 0

    def test_priya_stays_separate(self, sample_data_dir, pipeline_config):
        """Priya should not merge with Rahul."""
        pipeline = Pipeline(config=pipeline_config)
        result = pipeline.run(input_paths=[sample_data_dir])

        profiles = result["profiles"]

        priya_profiles = [
            p for p in profiles
            if p.get("full_name") and "priya" in p["full_name"].lower()
        ]

        # Priya should exist as a separate profile
        assert len(priya_profiles) >= 1

        # Priya should have her own email
        for priya in priya_profiles:
            emails = priya.get("emails", [])
            # Priya's email should not include Rahul's
            assert "rahul.sharma@gmail.com" not in emails

    def test_confidence_scores_present(self, sample_data_dir, pipeline_config):
        """All profiles should have confidence scores."""
        pipeline = Pipeline(config=pipeline_config)
        result = pipeline.run(input_paths=[sample_data_dir])

        for profile in result["profiles"]:
            assert "overall_confidence" in profile
            assert isinstance(profile["overall_confidence"], (int, float))
            assert 0.0 <= profile["overall_confidence"] <= 1.0

    def test_provenance_present(self, sample_data_dir, pipeline_config):
        """Pipeline should generate provenance records."""
        pipeline = Pipeline(config=pipeline_config)
        result = pipeline.run(input_paths=[sample_data_dir])

        assert "provenance" in result
        assert len(result["provenance"]) > 0

        # Check provenance record structure
        record = result["provenance"][0]
        assert "field" in record
        assert "source" in record
        assert "confidence" in record

    def test_report_generated(self, sample_data_dir, pipeline_config):
        """Pipeline should generate an explainability report."""
        pipeline = Pipeline(config=pipeline_config)
        result = pipeline.run(input_paths=[sample_data_dir])

        report = result["report"]
        assert "summary" in report
        assert "candidates" in report
        assert report["summary"]["total_profiles"] > 0

    def test_output_matches_config(self, sample_data_dir, pipeline_config, output_config):
        """Output should match the configured schema."""
        pipeline = Pipeline(config=pipeline_config)
        result = pipeline.run(
            input_paths=[sample_data_dir],
            output_config=output_config,
        )

        output = result["output"]
        assert len(output) > 0

        # Check that configured fields exist in output
        for item in output:
            assert "full_name" in item
            assert "candidate_id" in item

    def test_phone_normalization(self, sample_data_dir, pipeline_config):
        """Phones should be normalized to E.164."""
        pipeline = Pipeline(config=pipeline_config)
        result = pipeline.run(input_paths=[sample_data_dir])

        for profile in result["profiles"]:
            for phone in profile.get("phones", []):
                assert phone.startswith("+"), f"Phone not E.164: {phone}"

    def test_country_normalization(self, sample_data_dir, pipeline_config):
        """Countries should be normalized to ISO-3166 Alpha-2."""
        pipeline = Pipeline(config=pipeline_config)
        result = pipeline.run(input_paths=[sample_data_dir])

        for profile in result["profiles"]:
            location = profile.get("location")
            if location and location.get("country"):
                country = location["country"]
                assert len(country) == 2, f"Country not ISO-3166: {country}"

    def test_empty_input_does_not_crash(self, pipeline_config):
        """Empty input should produce empty output without crashing."""
        pipeline = Pipeline(config=pipeline_config)
        # Create a temp empty directory
        import tempfile
        with tempfile.TemporaryDirectory() as tmp_dir:
            result = pipeline.run(input_paths=[tmp_dir])
            assert result["profiles"] == []

    def test_malformed_input_handled_gracefully(self, pipeline_config):
        """Malformed input should not crash the pipeline."""
        pipeline = Pipeline(config=pipeline_config)
        import tempfile

        # Create a malformed JSON file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix="_resume.json", delete=False, prefix="malformed"
        ) as f:
            f.write("{invalid json content!!!}")
            temp_path = f.name

        try:
            result = pipeline.run(input_paths=[temp_path])
            # Should return empty but not crash
            assert "profiles" in result
        finally:
            os.unlink(temp_path)
