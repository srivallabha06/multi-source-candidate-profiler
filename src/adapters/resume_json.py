"""
Resume JSON adapter.

Parses resume JSON files with flexible field mapping.
Handles missing/extra fields gracefully.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.adapters.base import BaseAdapter
from src.models.candidate import RawCandidateRecord

logger = logging.getLogger(__name__)


class ResumeJsonAdapter(BaseAdapter):
    """
    Adapter for resume JSON files.

    Expected to handle files with names containing "resume" and
    extension ".json". Flexible field mapping handles various
    resume JSON schemas.
    """

    @property
    def source_type(self) -> str:
        return "resume_json"

    def can_handle(self, source_path: str) -> bool:
        path = Path(source_path)
        if not path.suffix.lower() == ".json":
            return False
        name_lower = path.stem.lower()
        return "resume" in name_lower or "cv" in name_lower

    def ingest(self, source_path: str) -> List[RawCandidateRecord]:
        data = self._safe_read_json(source_path)
        if data is None:
            return []

        try:
            record_data = self._extract_fields(data)
            record = self._create_record(record_data, source_path)
            return [record]
        except Exception as e:
            logger.error("Error extracting resume data from '%s': %s", source_path, e)
            return []

    def _extract_fields(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract candidate fields from resume JSON with flexible mapping."""
        result: Dict[str, Any] = {}

        # Name — try multiple possible keys
        result["full_name"] = self._find_value(
            data,
            ["full_name", "name", "fullName", "candidate_name", "candidateName"],
        )

        # Email
        emails = self._find_list(
            data,
            ["emails", "email", "email_addresses", "emailAddresses"],
        )
        result["emails"] = emails

        # Phone
        phones = self._find_list(
            data,
            ["phones", "phone", "phone_numbers", "phoneNumbers", "mobile"],
        )
        result["phones"] = phones

        # Location
        location = self._extract_location(data)
        result["location"] = location

        # Links
        result["links"] = self._extract_links(data)

        # Headline/Summary
        result["headline"] = self._find_value(
            data,
            ["headline", "summary", "title", "objective", "professional_summary"],
        )

        # Years of experience
        yoe = self._find_value(
            data,
            ["years_experience", "yearsExperience", "experience_years",
             "total_experience", "totalExperience", "years_of_experience"],
        )
        if yoe is not None:
            try:
                result["years_experience"] = float(yoe)
            except (ValueError, TypeError):
                result["years_experience"] = None
        else:
            result["years_experience"] = None

        # Skills
        skills_raw = self._find_list(
            data,
            ["skills", "skill_list", "skillList", "technical_skills",
             "technicalSkills", "core_skills"],
        )
        result["skills"] = skills_raw

        # Experience
        result["experience"] = self._find_value(
            data,
            ["experience", "work_experience", "workExperience",
             "employment", "positions", "work_history"],
        ) or []

        # Education
        result["education"] = self._find_value(
            data,
            ["education", "educations", "academic", "qualifications"],
        ) or []

        return result

    def _find_value(
        self, data: Dict[str, Any], keys: List[str]
    ) -> Optional[Any]:
        """Find the first matching key in the data dict."""
        for key in keys:
            if key in data and data[key] is not None:
                return data[key]
        return None

    def _find_list(
        self, data: Dict[str, Any], keys: List[str]
    ) -> List[str]:
        """Find a value and ensure it's a list."""
        value = self._find_value(data, keys)
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            return [str(v) for v in value if v]
        return [str(value)]

    def _extract_location(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract location from various possible structures."""
        # Try nested location object
        loc = self._find_value(
            data, ["location", "address", "geo", "geography"]
        )
        if isinstance(loc, dict):
            return {
                "city": loc.get("city"),
                "region": loc.get("region") or loc.get("state") or loc.get("province"),
                "country": loc.get("country") or loc.get("country_code"),
            }

        # Try flat fields
        return {
            "city": self._find_value(data, ["city"]),
            "region": self._find_value(data, ["region", "state", "province"]),
            "country": self._find_value(
                data, ["country", "country_code", "countryCode"]
            ),
        }

    def _extract_links(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract profile links."""
        links_obj = self._find_value(data, ["links", "profiles", "urls", "social"])

        if isinstance(links_obj, dict):
            return {
                "linkedin": links_obj.get("linkedin"),
                "github": links_obj.get("github"),
                "portfolio": links_obj.get("portfolio") or links_obj.get("website"),
                "other": links_obj.get("other", []),
            }

        # Try flat fields
        return {
            "linkedin": self._find_value(
                data, ["linkedin", "linkedin_url", "linkedinUrl"]
            ),
            "github": self._find_value(
                data, ["github", "github_url", "githubUrl"]
            ),
            "portfolio": self._find_value(
                data, ["portfolio", "website", "portfolio_url"]
            ),
            "other": [],
        }
