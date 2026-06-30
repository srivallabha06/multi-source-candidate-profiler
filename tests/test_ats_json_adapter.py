"""
Unit tests for the ATSJsonAdapter.
"""

import os
import json
import pytest
import tempfile
from src.adapters.ats_json import ATSJsonAdapter


def test_can_handle():
    adapter = ATSJsonAdapter()
    assert adapter.can_handle("ats_export.json") is True
    assert adapter.can_handle("my_ats_candidates.json") is True
    assert adapter.can_handle("candidate.json") is False  # No "ats"
    assert adapter.can_handle("ats_export.csv") is False   # Not .json


def test_ingest_single_candidate():
    adapter = ATSJsonAdapter()
    candidate_data = {
        "first_name": "John",
        "last_name": "Doe",
        "email": "john.doe@example.com",
        "phone": "+15551234567",
        "headline": "Full Stack Dev",
        "skills": ["Python", "Docker"],
        "location": {"city": "New York", "country": "US"}
    }

    with tempfile.NamedTemporaryFile(suffix="ats_data.json", mode="w", delete=False, encoding="utf-8") as temp:
        json.dump(candidate_data, temp)
        temp_path = temp.name

    try:
        records = adapter.ingest(temp_path)
        assert len(records) == 1
        record = records[0]
        assert record.get("full_name") == "John Doe"
        assert "john.doe@example.com" in record.get("emails")
        assert "+15551234567" in record.get("phones")
        assert record.get("headline") == "Full Stack Dev"
        assert record.get("skills") == ["Python", "Docker"]
        assert record.get("location").get("city") == "New York"
        assert record.source_type == "ats_json"
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_ingest_multiple_candidates():
    adapter = ATSJsonAdapter()
    candidates_list = {
        "candidates": [
            {
                "full_name": "Alice Smith",
                "email": "alice@example.com"
            },
            {
                "full_name": "Bob Jones",
                "email": "bob@example.com"
            }
        ]
    }

    with tempfile.NamedTemporaryFile(suffix="ats_list.json", mode="w", delete=False, encoding="utf-8") as temp:
        json.dump(candidates_list, temp)
        temp_path = temp.name

    try:
        records = adapter.ingest(temp_path)
        assert len(records) == 2
        names = [r.get("full_name") for r in records]
        assert "Alice Smith" in names
        assert "Bob Jones" in names
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
