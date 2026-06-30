"""
ATS JSON system adapter.

Reads ATS system JSON exports mapping candidate lists to raw records.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List

from src.adapters.base import BaseAdapter
from src.models.candidate import RawCandidateRecord

logger = logging.getLogger(__name__)


class ATSJsonAdapter(BaseAdapter):
    """
    Adapter for ATS JSON exports.

    Handles files with "ats" in the name and ".json" extension.
    Maps candidate records to standard raw candidate structure.
    """

    @property
    def source_type(self) -> str:
        return "ats_json"

    def can_handle(self, source_path: str) -> bool:
        path = Path(source_path)
        if not path.suffix.lower() == ".json":
            return False
        name_lower = path.stem.lower()
        return "ats" in name_lower

    def ingest(self, source_path: str) -> List[RawCandidateRecord]:
        data = self._safe_read_json(source_path)
        if data is None:
            return []

        records = []
        try:
            # Handle both single dictionary and list of dictionaries
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                items = data.get(
                    "candidates",
                    data.get("records", data.get("results", [data])),
                )
                if not isinstance(items, list):
                    items = [data]
            else:
                items = []

            for item in items:
                if isinstance(item, dict):
                    record_data = self._extract_fields(item)
                    records.append(
                        self._create_record(record_data, source_path)
                    )
            return records
        except Exception as e:
            logger.error("Error extracting ATS JSON data from '%s': %s", source_path, e)
            return []

    def _extract_fields(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract standard raw candidate fields from the raw ATS JSON dict."""
        result: Dict[str, Any] = {}

        # Name
        first = data.get("first_name", data.get("firstName", "")) or ""
        last = data.get("last_name", data.get("lastName", "")) or ""
        full = data.get("full_name", data.get("fullName", ""))
        if full:
            result["full_name"] = full
        elif first or last:
            result["full_name"] = f"{first} {last}".strip()
        else:
            result["full_name"] = None

        # Email
        emails = []
        email = data.get("email", data.get("email_address", data.get("emailAddress")))
        if email:
            emails = [email] if isinstance(email, str) else list(email)
        elif "emails" in data and isinstance(data["emails"], list):
            emails = data["emails"]
        result["emails"] = emails

        # Phone
        phones = []
        phone = data.get("phone", data.get("phone_number", data.get("phoneNumber")))
        if phone:
            phones = [phone] if isinstance(phone, str) else list(phone)
        elif "phones" in data and isinstance(data["phones"], list):
            phones = data["phones"]
        result["phones"] = phones

        # Headline
        result["headline"] = data.get("headline", data.get("role", data.get("title")))

        # Location
        result["location"] = data.get("location", {})

        # Links (linkedin, github, portfolio)
        links_data = data.get("links", {})
        social = data.get("socialProfiles", data.get("social_profiles", {}))
        result["links"] = {
            "linkedin": links_data.get("linkedin", data.get("linkedin", social.get("linkedin"))),
            "github": links_data.get("github", data.get("github", social.get("github"))),
            "portfolio": links_data.get("portfolio", data.get("portfolio", social.get("portfolio"))),
            "other": links_data.get("other", []),
        }

        # Skills
        result["skills"] = data.get("skills", [])

        # Experience
        raw_experience = data.get("experience", [])
        experience_list = []
        for exp in raw_experience:
            if isinstance(exp, dict):
                end_val = exp.get("endDate", exp.get("end_date"))
                if exp.get("current") or exp.get("is_current"):
                    end_val = "present"
                experience_list.append({
                    "company": exp.get("company"),
                    "title": exp.get("title"),
                    "start_date": exp.get("startDate", exp.get("start_date")),
                    "end_date": end_val,
                    "description": exp.get("description", exp.get("summary")),
                })
        result["experience"] = experience_list

        # Education
        raw_education = data.get("education", [])
        education_list = []
        for edu in raw_education:
            if isinstance(edu, dict):
                end_val = edu.get("graduationYear", edu.get("graduation_year", edu.get("end_date")))
                education_list.append({
                    "institution": edu.get("institution", edu.get("school")),
                    "degree": edu.get("degree"),
                    "field_of_study": edu.get("field_of_study", edu.get("field", edu.get("major"))),
                    "end_date": str(end_val) if end_val is not None else None,
                })
        result["education"] = education_list

        return result
