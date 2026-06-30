"""
LinkedIn JSON adapter.

Parses LinkedIn profile export JSON files.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.adapters.base import BaseAdapter
from src.models.candidate import RawCandidateRecord

logger = logging.getLogger(__name__)


class LinkedInJsonAdapter(BaseAdapter):
    """
    Adapter for LinkedIn profile JSON exports.

    Handles files with "linkedin" in the name and ".json" extension.
    """

    @property
    def source_type(self) -> str:
        return "linkedin_json"

    def can_handle(self, source_path: str) -> bool:
        # Handle LinkedIn URLs
        if "linkedin.com/in/" in source_path.lower() or "linkedin.com/profile/" in source_path.lower():
            return True
        path = Path(source_path)
        if not path.suffix.lower() == ".json":
            return False
        return "linkedin" in path.stem.lower()

    def ingest(self, source_path: str) -> List[RawCandidateRecord]:
        is_url = (
            source_path.lower().startswith(("http://", "https://"))
            or "linkedin.com/" in source_path.lower()
        )
        if is_url:
            return self._ingest_from_api(source_path)

        data = self._safe_read_json(source_path)
        if data is None:
            return []

        try:
            record_data = self._extract_fields(data)
            record = self._create_record(record_data, source_path)
            return [record]
        except Exception as e:
            logger.error(
                "Error extracting LinkedIn data from '%s': %s",
                source_path, e
            )
            return []

    def _ingest_from_api(self, url: str) -> List[RawCandidateRecord]:
        import os
        token = os.environ.get("APIFY_TOKEN")
        if not token:
            logger.error("APIFY_TOKEN environment variable not set. Cannot parse LinkedIn URL.")
            return []

        actor = os.environ.get("APIFY_ACTOR", "harvestapi/linkedin-profile-scraper")
        actor_id = actor.replace("/", "~")
        api_url = f"https://api.apify.com/v2/acts/{actor_id}/run-sync-get-dataset-items?token={token}"
        
        payload = {
            "urls": [url],
            "linkedinUrls": [url],
            "profileUrls": [url]
        }
        
        try:
            import requests
            logger.info("Calling Apify LinkedIn profile scraper for: %s", url)
            response = requests.post(api_url, json=payload, timeout=60)
            if response.status_code not in (200, 201):
                logger.error("Apify API call failed with status %d: %s", response.status_code, response.text)
                return []
            
            items = response.json()
            if not isinstance(items, list) or not items:
                logger.warning("Apify returned empty or invalid dataset: %s", items)
                return []
            
            profile_data = items[0]
            # Discard error or status codes indicating failure (e.g. 404 Profile not found)
            if "status" in profile_data and profile_data.get("status") not in (200, 201):
                logger.error("Apify scraper returned failed status %s: %s", profile_data.get("status"), profile_data.get("error"))
                return []
            if "error" in profile_data:
                logger.error("Apify scraper returned error: %s", profile_data.get("error"))
                return []

            if "profile" in profile_data and isinstance(profile_data["profile"], dict):
                profile_data = profile_data["profile"]

            record_data = self._extract_fields(profile_data)
            record = self._create_record(record_data, url)
            return [record]
        except Exception as e:
            logger.error("Exception calling Apify for LinkedIn URL '%s': %s", url, e)
            return []

    def _extract_fields(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract candidate fields from LinkedIn JSON."""
        result: Dict[str, Any] = {}

        # Name
        first = data.get("firstName", data.get("first_name", "")) or ""
        last = data.get("lastName", data.get("last_name", "")) or ""
        full = data.get("full_name", data.get("fullName", ""))
        if full:
            result["full_name"] = full
        elif first or last:
            result["full_name"] = f"{first} {last}".strip()
        else:
            result["full_name"] = None

        # Email
        emails = []
        email = data.get("emailAddress", data.get("email"))
        if email:
            emails = [email] if isinstance(email, str) else list(email)
        result["emails"] = emails

        # Phone
        phones = []
        phone = data.get("phone", data.get("phoneNumbers"))
        if phone:
            phones = [phone] if isinstance(phone, str) else list(phone)
        result["phones"] = phones

        # Headline
        result["headline"] = data.get("headline", data.get("title"))

        # Location
        loc_str = data.get("location", data.get("locationName"))
        result["location"] = self._parse_location_string(loc_str, data)

        # LinkedIn URL
        profile_url = data.get(
            "publicProfileUrl",
            data.get("profile_url", data.get("linkedin_url")),
        )
        result["links"] = {
            "linkedin": profile_url,
            "github": data.get("github", data.get("github_url")),
            "portfolio": data.get("website", data.get("portfolio")),
            "other": [],
        }

        # Skills
        skills_raw = data.get("skills", [])
        if isinstance(skills_raw, list):
            result["skills"] = [
                s.get("name", s) if isinstance(s, dict) else str(s)
                for s in skills_raw
                if s
            ]
        else:
            result["skills"] = []

        # Experience
        positions = data.get("positions", data.get("experience", []))
        result["experience"] = self._extract_experience(positions)

        # Education
        edu = data.get("educations", data.get("education", []))
        result["education"] = self._extract_education(edu)

        # Years of experience
        result["years_experience"] = data.get(
            "years_experience", data.get("yearsExperience")
        )

        return result

    def _parse_location_string(
        self, loc_str: Optional[Any], data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Parse a location string like 'Bengaluru, Karnataka, India'."""
        if isinstance(loc_str, dict):
            return {
                "city": loc_str.get("city"),
                "region": loc_str.get("region") or loc_str.get("state"),
                "country": loc_str.get("country") or loc_str.get("countryCode"),
            }

        if isinstance(loc_str, str) and loc_str.strip():
            parts = [p.strip() for p in loc_str.split(",")]
            return {
                "city": parts[0] if len(parts) >= 1 else None,
                "region": parts[1] if len(parts) >= 2 else None,
                "country": parts[-1] if len(parts) >= 3 else None,
            }

        return {
            "city": data.get("city"),
            "region": data.get("region", data.get("state")),
            "country": data.get("country", data.get("countryCode")),
        }

    def _extract_experience(self, positions: Any) -> List[Dict[str, Any]]:
        """Extract experience entries from LinkedIn positions."""
        if not isinstance(positions, list):
            return []

        result = []
        for pos in positions:
            if not isinstance(pos, dict):
                continue
            entry = {
                "company": pos.get("companyName", pos.get("company")),
                "title": pos.get("title", pos.get("position")),
                "start_date": self._extract_date(pos.get("startDate", pos.get("start_date"))),
                "end_date": self._extract_date(pos.get("endDate", pos.get("end_date"))),
                "description": pos.get("description", pos.get("summary")),
                "location": None,
            }
            loc = pos.get("location", pos.get("locationName"))
            if loc:
                entry["location"] = {"city": loc if isinstance(loc, str) else None}
            result.append(entry)
        return result

    def _extract_education(self, educations: Any) -> List[Dict[str, Any]]:
        """Extract education entries."""
        if not isinstance(educations, list):
            return []

        result = []
        for edu in educations:
            if not isinstance(edu, dict):
                continue
            result.append({
                "institution": edu.get("schoolName", edu.get("institution", edu.get("school"))),
                "degree": edu.get("degree", edu.get("degreeName")),
                "field_of_study": edu.get("fieldOfStudy", edu.get("field_of_study", edu.get("major"))),
                "start_date": self._extract_date(edu.get("startDate", edu.get("start_date"))),
                "end_date": self._extract_date(edu.get("endDate", edu.get("end_date"))),
            })
        return result

    def _extract_date(self, date_val: Any) -> Optional[str]:
        """Extract a date from various formats."""
        if date_val is None:
            return None
        if isinstance(date_val, str):
            return date_val
        if isinstance(date_val, dict):
            year = date_val.get("year")
            month = date_val.get("month")
            if year and month:
                return f"{year}-{int(month):02d}"
            elif year:
                return str(year)
        return str(date_val)
