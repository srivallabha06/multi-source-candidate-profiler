"""
ATS CSV adapter.

Reads Applicant Tracking System CSV exports with configurable
column mapping. Each row produces one RawCandidateRecord.
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.adapters.base import BaseAdapter
from src.models.candidate import RawCandidateRecord

logger = logging.getLogger(__name__)

# Default column name mappings (case-insensitive)
DEFAULT_COLUMN_MAP = {
    "full_name": ["name", "full_name", "fullname", "candidate_name", "candidate"],
    "email": ["email", "email_address", "emailaddress", "e-mail"],
    "phone": ["phone", "phone_number", "phonenumber", "mobile", "telephone", "contact"],
    "skills": ["skills", "skill_list", "technical_skills", "core_skills"],
    "company": ["company", "current_company", "employer", "organization"],
    "title": ["title", "job_title", "position", "role", "designation"],
    "location": ["location", "city", "address"],
    "country": ["country", "country_code"],
    "linkedin": ["linkedin", "linkedin_url", "linkedin_profile"],
    "github": ["github", "github_url", "github_profile"],
    "experience_years": ["experience", "years_experience", "experience_years", "yoe", "total_experience"],
    "education": ["education", "degree", "qualification"],
    "institution": ["institution", "school", "university", "college"],
}


class ATSCsvAdapter(BaseAdapter):
    """
    Adapter for ATS CSV exports.

    Auto-detects column mappings via header matching.
    Handles encoding issues, empty rows, and malformed data.
    """

    def __init__(
        self, column_map: Optional[Dict[str, List[str]]] = None
    ) -> None:
        self._column_map = column_map or DEFAULT_COLUMN_MAP

    @property
    def source_type(self) -> str:
        return "ats_csv"

    def can_handle(self, source_path: str) -> bool:
        path = Path(source_path)
        return path.suffix.lower() == ".csv"

    def ingest(self, source_path: str) -> List[RawCandidateRecord]:
        try:
            path = Path(source_path)
            if not path.exists():
                logger.error("CSV file not found: %s", source_path)
                return []

            records = []

            # Try different encodings
            for encoding in ["utf-8", "utf-8-sig", "latin-1", "cp1252"]:
                try:
                    with open(
                        path, "r", encoding=encoding, newline=""
                    ) as f:
                        reader = csv.DictReader(f)
                        if not reader.fieldnames:
                            logger.warning("No headers in CSV: %s", source_path)
                            return []

                        # Build column index from headers
                        col_index = self._build_column_index(
                            reader.fieldnames
                        )

                        for row_num, row in enumerate(reader, start=2):
                            try:
                                record_data = self._extract_row(
                                    row, col_index
                                )
                                if record_data and self._has_useful_data(record_data):
                                    records.append(
                                        self._create_record(
                                            record_data, source_path
                                        )
                                    )
                            except Exception as e:
                                logger.warning(
                                    "Error in row %d of '%s': %s",
                                    row_num, source_path, e,
                                )
                                continue

                    break  # Success with this encoding

                except UnicodeDecodeError:
                    continue
                except Exception as e:
                    logger.error(
                        "Error reading CSV '%s' with %s: %s",
                        source_path, encoding, e,
                    )
                    continue

            logger.info(
                "Ingested %d records from CSV: %s", len(records), source_path
            )
            return records

        except Exception as e:
            logger.error("Fatal error reading CSV '%s': %s", source_path, e)
            return []

    def _build_column_index(
        self, fieldnames: List[str]
    ) -> Dict[str, str]:
        """
        Map canonical field names to actual CSV column names.

        Returns {canonical_field: actual_column_name}
        """
        index: Dict[str, str] = {}
        for canonical_field, aliases in self._column_map.items():
            for col in fieldnames:
                if col.strip().lower().replace(" ", "_") in [
                    a.lower() for a in aliases
                ]:
                    index[canonical_field] = col
                    break
        return index

    def _extract_row(
        self, row: Dict[str, str], col_index: Dict[str, str]
    ) -> Dict[str, Any]:
        """Extract candidate data from a CSV row."""

        def get_val(field: str) -> Optional[str]:
            col = col_index.get(field)
            if col and col in row:
                val = row[col].strip()
                return val if val else None
            return None

        result: Dict[str, Any] = {}

        result["full_name"] = get_val("full_name")

        # Email — might be comma-separated
        email_str = get_val("email")
        if email_str:
            result["emails"] = [
                e.strip() for e in email_str.split(",") if e.strip()
            ]
        else:
            result["emails"] = []

        # Phone
        phone = get_val("phone")
        result["phones"] = [phone] if phone else []

        # Skills — might be comma or semicolon separated
        skills_str = get_val("skills")
        if skills_str:
            # Split on comma, semicolon, or pipe
            result["skills"] = [
                s.strip()
                for s in skills_str.replace(";", ",").replace("|", ",").split(",")
                if s.strip()
            ]
        else:
            result["skills"] = []

        # Location
        result["location"] = {
            "city": get_val("location"),
            "region": None,
            "country": get_val("country"),
        }

        # Links
        result["links"] = {
            "linkedin": get_val("linkedin"),
            "github": get_val("github"),
            "portfolio": None,
            "other": [],
        }

        # Experience
        result["headline"] = get_val("title")

        yoe = get_val("experience_years")
        if yoe:
            try:
                result["years_experience"] = float(yoe)
            except ValueError:
                result["years_experience"] = None
        else:
            result["years_experience"] = None

        # Build experience entry from current role
        company = get_val("company")
        title = get_val("title")
        if company or title:
            result["experience"] = [{
                "company": company,
                "title": title,
                "start_date": None,
                "end_date": None,
                "description": None,
            }]
        else:
            result["experience"] = []

        # Education
        degree = get_val("education")
        institution = get_val("institution")
        if degree or institution:
            result["education"] = [{
                "institution": institution,
                "degree": degree,
                "field_of_study": None,
                "start_date": None,
                "end_date": None,
            }]
        else:
            result["education"] = []

        return result

    def _has_useful_data(self, data: Dict[str, Any]) -> bool:
        """Check if a record has at least some useful data."""
        return bool(
            data.get("full_name")
            or data.get("emails")
            or data.get("phones")
        )
