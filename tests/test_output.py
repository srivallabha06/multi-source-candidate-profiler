"""
Unit tests for the output configurator.

Tests cover all output config edge cases:
- Missing fields
- Invalid paths
- Array indexing
- Nested destination creation
- Confidence inclusion
- Missing field handling modes
"""

import os
import sys
import pytest

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.models.candidate import CanonicalProfile, Skill, Location, Links
from src.output.configurator import OutputConfigurator


class TestOutputConfigurator:
    def _make_profile(self):
        """Create a test profile."""
        profile = CanonicalProfile(
            candidate_id="test-123",
            full_name="Rahul Sharma",
            emails=["rahul@gmail.com", "rahul@work.com"],
            phones=["+919876543210"],
            location=Location(city="Bengaluru", region="Karnataka", country="IN"),
            links=Links(
                linkedin="https://linkedin.com/in/rahul-sharma",
                github="https://github.com/rahul-sharma",
                portfolio="https://rahuldev.com",
            ),
            headline="Senior Software Engineer",
            years_experience=5.0,
            skills=[
                Skill(name="Java", confidence=0.95, sources=["resume_json"]),
                Skill(name="Python", confidence=0.85, sources=["resume_json", "github"]),
                Skill(name="AWS", confidence=0.80, sources=["github"]),
            ],
            overall_confidence=0.92,
        )
        return profile

    def test_field_renaming(self):
        """'path' renames the field in output."""
        config = {
            "fields": [
                {"path": "name", "from": "full_name"},
            ],
            "on_missing": "null",
        }
        configurator = OutputConfigurator(config)
        result = configurator.transform(self._make_profile())

        assert result["name"] == "Rahul Sharma"
        assert "full_name" not in result

    def test_array_index(self):
        """emails[0] should extract the first email."""
        config = {
            "fields": [
                {"path": "primary_email", "from": "emails[0]"},
            ],
            "on_missing": "null",
        }
        configurator = OutputConfigurator(config)
        result = configurator.transform(self._make_profile())

        assert result["primary_email"] == "rahul@gmail.com"

    def test_array_wildcard(self):
        """emails[*] should return the full array."""
        config = {
            "fields": [
                {"path": "all_emails", "from": "emails[*]"},
            ],
            "on_missing": "null",
        }
        configurator = OutputConfigurator(config)
        result = configurator.transform(self._make_profile())

        assert result["all_emails"] == ["rahul@gmail.com", "rahul@work.com"]

    def test_nested_source_path(self):
        """location.city should extract nested value."""
        config = {
            "fields": [
                {"path": "city", "from": "location.city"},
            ],
            "on_missing": "null",
        }
        configurator = OutputConfigurator(config)
        result = configurator.transform(self._make_profile())

        assert result["city"] == "Bengaluru"

    def test_nested_destination_path(self):
        """Nested destination should create intermediate dicts."""
        config = {
            "fields": [
                {"path": "contact.email", "from": "emails[0]"},
                {"path": "contact.phone", "from": "phones[0]"},
            ],
            "on_missing": "null",
        }
        configurator = OutputConfigurator(config)
        result = configurator.transform(self._make_profile())

        assert result["contact"]["email"] == "rahul@gmail.com"
        assert result["contact"]["phone"] == "+919876543210"

    def test_wildcard_with_subfield(self):
        """skills[*].name should extract list of skill names."""
        config = {
            "fields": [
                {"path": "skill_names", "from": "skills[*].name"},
            ],
            "on_missing": "null",
        }
        configurator = OutputConfigurator(config)
        result = configurator.transform(self._make_profile())

        assert result["skill_names"] == ["Java", "Python", "AWS"]

    def test_missing_field_null(self):
        """on_missing='null' should set missing fields to None."""
        config = {
            "fields": [
                {"path": "nonexistent", "from": "does_not_exist"},
            ],
            "on_missing": "null",
        }
        configurator = OutputConfigurator(config)
        result = configurator.transform(self._make_profile())

        assert "nonexistent" in result
        assert result["nonexistent"] is None

    def test_missing_field_skip(self):
        """on_missing='skip' should omit missing fields."""
        config = {
            "fields": [
                {"path": "nonexistent", "from": "does_not_exist"},
                {"path": "name", "from": "full_name"},
            ],
            "on_missing": "skip",
        }
        configurator = OutputConfigurator(config)
        result = configurator.transform(self._make_profile())

        assert "nonexistent" not in result
        assert result["name"] == "Rahul Sharma"

    def test_include_confidence(self):
        """include_confidence should add confidence data."""
        config = {
            "fields": [
                {"path": "name", "from": "full_name"},
            ],
            "include_confidence": True,
            "on_missing": "null",
        }
        configurator = OutputConfigurator(config)
        result = configurator.transform(self._make_profile())

        assert "_confidence" in result
        assert "overall" in result["_confidence"]

    def test_no_confidence(self):
        """Without include_confidence, no _confidence key."""
        config = {
            "fields": [
                {"path": "name", "from": "full_name"},
            ],
            "include_confidence": False,
            "on_missing": "null",
        }
        configurator = OutputConfigurator(config)
        result = configurator.transform(self._make_profile())

        assert "_confidence" not in result

    def test_array_index_out_of_bounds(self):
        """Out-of-bounds array index should return None, not crash."""
        config = {
            "fields": [
                {"path": "tenth_email", "from": "emails[10]"},
            ],
            "on_missing": "null",
        }
        configurator = OutputConfigurator(config)
        result = configurator.transform(self._make_profile())

        assert result["tenth_email"] is None

    def test_no_config_returns_full_profile(self):
        """No field config should return the full profile dict."""
        configurator = OutputConfigurator({})
        result = configurator.transform(self._make_profile())

        assert result["full_name"] == "Rahul Sharma"
        assert "emails" in result

    def test_validate_config_valid(self):
        """Valid config should produce no issues."""
        config = {
            "fields": [
                {"path": "name", "from": "full_name"},
            ],
            "on_missing": "null",
        }
        configurator = OutputConfigurator(config)
        issues = configurator.validate_config()
        assert len(issues) == 0

    def test_validate_config_invalid_on_missing(self):
        """Invalid on_missing should produce a warning."""
        config = {
            "fields": [],
            "on_missing": "invalid_value",
        }
        configurator = OutputConfigurator(config)
        issues = configurator.validate_config()
        assert any("on_missing" in issue for issue in issues)

    def test_transform_all(self):
        """transform_all should handle multiple profiles."""
        config = {
            "fields": [
                {"path": "name", "from": "full_name"},
            ],
            "on_missing": "null",
        }
        configurator = OutputConfigurator(config)
        profiles = [self._make_profile(), self._make_profile()]
        results = configurator.transform_all(profiles)

        assert len(results) == 2
        assert all(r["name"] == "Rahul Sharma" for r in results)

    def test_include_provenance(self):
        """Output should include provenance records if include_provenance is true."""
        from src.models.provenance import ProvenanceStore, ProvenanceRecord
        
        config = {
            "fields": [
                {"path": "name", "from": "full_name"},
            ],
            "include_provenance": True,
            "on_missing": "null",
        }
        configurator = OutputConfigurator(config)
        profile = self._make_profile()
        
        store = ProvenanceStore()
        record = ProvenanceRecord(
            candidate_id=profile.candidate_id,
            field="full_name",
            value="Rahul Sharma",
            source="resume_json",
            source_path="resume.json",
            confidence=0.95
        )
        store.add(record)
        
        result = configurator.transform(profile, store)
        assert "_provenance" in result
        assert len(result["_provenance"]) == 1
        assert result["_provenance"][0]["value"] == "Rahul Sharma"
        assert result["_provenance"][0]["source"] == "resume_json"
