"""
Internal HR system adapter.

Reads HR system JSON exports with flexible field mapping.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.adapters.base import BaseAdapter
from src.models.candidate import RawCandidateRecord

logger = logging.getLogger(__name__)


class HRSystemAdapter(BaseAdapter):
    """
    Adapter for internal HR system JSON exports.

    Handles files with "hr" in the name and ".json" extension.
    Maps internal HR fields to the standard raw record format.
    """

    @property
    def source_type(self) -> str:
        return "hr_system"

    def can_handle(self, source_path: str) -> bool:
        path = Path(source_path)
        if not path.suffix.lower() == ".json":
            return False
        name_lower = path.stem.lower()
        return "hr" in name_lower or "employee" in name_lower or "internal" in name_lower

    def ingest(self, source_path: str) -> List[RawCandidateRecord]:
        data = self._safe_read_json(source_path)
        if data is None:
            return []

        try:
            # Handle both single record and array of records
            if isinstance(data, list):
                records = []
                for item in data:
                    if isinstance(item, dict):
                        record_data = self._extract_fields(item)
                        records.append(
                            self._create_record(record_data, source_path)
                        )
                return records
            elif isinstance(data, dict):
                # Check if there's a nested records array
                employees = data.get(
                    "employees",
                    data.get("records", data.get("candidates", None)),
                )
                if isinstance(employees, list):
                    records = []
                    for item in employees:
                        if isinstance(item, dict):
                            record_data = self._extract_fields(item)
                            records.append(
                                self._create_record(record_data, source_path)
                            )
                    return records
                else:
                    record_data = self._extract_fields(data)
                    return [self._create_record(record_data, source_path)]
            else:
                logger.warning("Unexpected HR data format in: %s", source_path)
                return []

        except Exception as e:
            logger.error("Error extracting HR data from '%s': %s", source_path, e)
            return []

    def _extract_fields(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract and map HR system fields."""
        result: Dict[str, Any] = {}

        # Name
        first = data.get("first_name", data.get("firstName", "")) or ""
        last = data.get("last_name", data.get("lastName", "")) or ""
        full = data.get("full_name", data.get("name", data.get("employee_name")))
        if full:
            result["full_name"] = full
        elif first or last:
            result["full_name"] = f"{first} {last}".strip()
        else:
            result["full_name"] = None

        # Email
        email = data.get("email", data.get("work_email", data.get("corporate_email")))
        result["emails"] = [email] if email else []

        # Phone
        phone = data.get("phone", data.get("mobile", data.get("work_phone")))
        result["phones"] = [phone] if phone else []

        # Employee/HR specific
        result["employee_id"] = data.get("employee_id", data.get("emp_id"))
        result["department"] = data.get("department", data.get("dept"))

        # Title/Position
        result["headline"] = data.get(
            "title", data.get("job_title", data.get("designation"))
        )

        # Location
        result["location"] = {
            "city": data.get("city", data.get("office_city")),
            "region": data.get("state", data.get("region")),
            "country": data.get("country", data.get("country_code")),
        }

        # Links
        result["links"] = {
            "linkedin": data.get("linkedin"),
            "github": data.get("github"),
            "portfolio": None,
            "other": [],
        }

        # Skills
        skills = data.get("skills", data.get("competencies", []))
        if isinstance(skills, str):
            result["skills"] = [s.strip() for s in skills.split(",") if s.strip()]
        elif isinstance(skills, list):
            result["skills"] = [str(s) for s in skills if s]
        else:
            result["skills"] = []

        # Experience
        result["years_experience"] = data.get(
            "years_experience", data.get("tenure_years")
        )
        result["experience"] = []
        result["education"] = []

        return result
