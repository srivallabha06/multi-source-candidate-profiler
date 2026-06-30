"""
PDF adapter for resume/CV PDFs.

Uses pdfplumber for text extraction and regex-based pipelines
for extracting contact info, skills, and other candidate facts.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.adapters.base import BaseAdapter
from src.models.candidate import RawCandidateRecord

logger = logging.getLogger(__name__)

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False
    logger.warning("pdfplumber not installed. PDF ingestion disabled.")


# Regex patterns for extraction
EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)
PHONE_PATTERN = re.compile(
    r"(?:\+?\d{1,3}[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}"
    r"|\+?\d{10,13}"
)
LINKEDIN_PATTERN = re.compile(
    r"(?:https?://)?(?:www\.)?linkedin\.com/in/[A-Za-z0-9_-]+/?",
    re.IGNORECASE,
)
GITHUB_PATTERN = re.compile(
    r"(?:https?://)?(?:www\.)?github\.com/[A-Za-z0-9_-]+/?",
    re.IGNORECASE,
)
URL_PATTERN = re.compile(
    r"https?://[^\s<>\"]+|www\.[^\s<>\"]+",
    re.IGNORECASE,
)


class PDFAdapter(BaseAdapter):
    """
    Adapter for PDF resumes/CVs.

    Extraction pipeline:
    1. Extract text from PDF (pdfplumber)
    2. Regex extraction for emails, phones, URLs
    3. Skill keyword matching against taxonomy
    4. Name heuristic (first non-empty line)
    """

    def __init__(self, skill_keywords: Optional[List[str]] = None) -> None:
        self._skill_keywords = skill_keywords or []

    @property
    def source_type(self) -> str:
        return "pdf"

    def can_handle(self, source_path: str) -> bool:
        return Path(source_path).suffix.lower() == ".pdf"

    def ingest(self, source_path: str) -> List[RawCandidateRecord]:
        if not HAS_PDFPLUMBER:
            logger.error("Cannot process PDF without pdfplumber library")
            return []

        text = self._extract_text(source_path)
        if not text:
            logger.warning("No text extracted from PDF: %s", source_path)
            return []

        try:
            record_data = self._extract_from_text(text)
            return [self._create_record(record_data, source_path)]
        except Exception as e:
            logger.error("Error extracting from PDF '%s': %s", source_path, e)
            return []

    def _extract_text(self, file_path: str) -> Optional[str]:
        """Extract all text from a PDF file."""
        try:
            path = Path(file_path)
            if not path.exists():
                logger.error("PDF file not found: %s", file_path)
                return None

            with pdfplumber.open(str(path)) as pdf:
                pages_text = []
                for page in pdf.pages:
                    try:
                        text = page.extract_text()
                        if text:
                            pages_text.append(text)
                    except Exception as e:
                        logger.warning("Error extracting page: %s", e)
                        continue

                return "\n".join(pages_text) if pages_text else None

        except Exception as e:
            logger.error("Error opening PDF '%s': %s", file_path, e)
            return None

    def _extract_from_text(self, text: str) -> Dict[str, Any]:
        """Extract candidate data from raw text."""
        result: Dict[str, Any] = {}

        # Name — heuristic: first non-empty line that looks like a name
        result["full_name"] = self._extract_name(text)

        # Emails
        result["emails"] = list(set(EMAIL_PATTERN.findall(text)))

        # Phones
        phones_raw = PHONE_PATTERN.findall(text)
        result["phones"] = list(set(phones_raw))

        # Links
        linkedin_urls = LINKEDIN_PATTERN.findall(text)
        github_urls = GITHUB_PATTERN.findall(text)
        all_other_urls = [
            u.strip("/ ") for u in URL_PATTERN.findall(text)
            if "linkedin.com" not in u.lower()
            and "github.com" not in u.lower()
        ]

        # Extract platform URLs that don't start with http/https/www
        extra_platforms = re.findall(
            r"\b(?:leetcode\.com|hackerrank\.com|geeksforgeeks\.com|geeksforgeeks\.org)\b/[^\s<>\"]+",
            text,
            re.IGNORECASE
        )
        for u in extra_platforms:
            cleaned_u = u.strip("/ ")
            if not cleaned_u.startswith("http"):
                cleaned_u = "https://" + cleaned_u
            if cleaned_u not in all_other_urls:
                all_other_urls.append(cleaned_u)


        portfolio_candidates = []
        platform_urls = []
        non_portfolio_domains = [
            "leetcode.com", "hackerrank.com", "codechef.com",
            "geeksforgeeks", "hackerearth.com", "medium.com",
            "twitter.com", "x.com", "facebook.com", "instagram.com"
        ]

        for u in all_other_urls:
            is_platform = any(domain in u.lower() for domain in non_portfolio_domains)
            if is_platform:
                platform_urls.append(u)
            else:
                portfolio_candidates.append(u)

        result["links"] = {
            "linkedin": linkedin_urls[0] if linkedin_urls else None,
            "github": github_urls[0] if github_urls else None,
            "portfolio": portfolio_candidates[0] if portfolio_candidates else None,
            "other": (portfolio_candidates[1:] if len(portfolio_candidates) > 1 else []) + platform_urls,
        }

        # Skills — match against known keywords
        result["skills"] = self._extract_skills(text)

        # Location, headline, experience, education — minimal extraction
        result["location"] = {"city": None, "region": None, "country": None}
        result["headline"] = None
        result["years_experience"] = self._extract_years_experience(text)
        result["experience"] = []
        result["education"] = self._extract_education(text)

        return result

    def _extract_name(self, text: str) -> Optional[str]:
        """
        Heuristic name extraction from resume text.

        Strategy: The name is usually the first non-empty line
        that contains 2-4 words of alphabetic characters.
        """
        lines = text.split("\n")
        for line in lines[:10]:  # Check first 10 lines
            cleaned = line.strip()
            if not cleaned:
                continue
            # Skip lines that look like headers/sections
            if any(
                kw in cleaned.lower()
                for kw in [
                    "resume", "curriculum", "cv", "objective",
                    "summary", "experience", "education", "skills",
                    "phone", "email", "address", "contact",
                ]
            ):
                continue

            # Strip emails, phone numbers, and URLs
            cleaned = EMAIL_PATTERN.sub("", cleaned)
            cleaned = PHONE_PATTERN.sub("", cleaned)
            cleaned = URL_PATTERN.sub("", cleaned)

            # Split concatenated TitleCase/camelCase words (e.g., 'KalluriNikhil' -> 'Kalluri Nikhil')
            cleaned = re.sub(r"([a-z])([A-Z])", r"\1 \2", cleaned)

            # Clean extra whitespaces
            cleaned = re.sub(r"\s+", " ", cleaned).strip()
            if not cleaned:
                continue

            # Name heuristic: 2-4 words, mostly alphabetic
            words = cleaned.split()
            if 2 <= len(words) <= 4:
                alpha_words = sum(
                    1 for w in words if w.replace(".", "").isalpha()
                )
                if alpha_words >= 2:
                    return cleaned.title()
        return None

    def _extract_skills(self, text: str) -> List[str]:
        """Extract skills by keyword matching."""
        if not self._skill_keywords:
            return []

        text_lower = text.lower()
        found = []
        for skill in self._skill_keywords:
            # Match whole word (case-insensitive)
            pattern = r"\b" + re.escape(skill.lower()) + r"\b"
            if re.search(pattern, text_lower):
                found.append(skill)
        return found

    def _extract_years_experience(self, text: str) -> Optional[float]:
        """Try to extract years of experience from text."""
        patterns = [
            r"(\d+)\+?\s*(?:years?|yrs?)[\s.]*(?:of\s+)?(?:experience|exp)",
            r"(?:experience|exp)[\s:]*(\d+)\+?\s*(?:years?|yrs?)",
            r"(\d+)\+?\s*(?:years?|yrs?)[\s.]*(?:in\s+(?:the\s+)?(?:industry|field|software))",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    return float(match.group(1))
                except ValueError:
                    continue
        return None

    def _extract_education(self, text: str) -> List[Dict[str, Any]]:
        """Extract education entries from resume text."""
        education_entries = []

        # Find education section header (case-insensitive)
        pattern = re.compile(
            r"\b(?:education|academic|academics|qualifications|scholastic)\b",
            re.IGNORECASE
        )

        lines = text.split("\n")
        edu_start_idx = -1
        for i, line in enumerate(lines):
            if pattern.search(line) and len(line.strip()) < 30:
                edu_start_idx = i
                break

        if edu_start_idx == -1:
            return []

        # Find where education section ends (next section header)
        next_section_pattern = re.compile(
            r"\b(?:projects|experience|work|employment|positions|achievements|skills|profiles|languages|certifications)\b",
            re.IGNORECASE
        )

        edu_lines = []
        for i in range(edu_start_idx + 1, len(lines)):
            line = lines[i].strip()
            if not line:
                continue
            if next_section_pattern.search(line) and len(line) < 30:
                break
            edu_lines.append(line)

        # Group lines: support multi-line structures (e.g. institution on line 1, degree on line 2)
        grouped_lines = []
        current_entry_parts = []
        
        common_degrees = [
            "b.tech", "btech", "m.tech", "mtech", "intermediate", "ssc", "b.s.", "bs", "m.s.", "ms", "b.e.", "be", 
            "bachelor", "master", "ph.d", "phd", "diploma", "high school", "secondary school", "secondary", "xstandard", 
            "x standard", "10th", "12th", "cbse", "icse", "tsbie"
        ]

        for line in edu_lines:
            # Check if this line looks like a column header rather than real data
            header_keywords = ["degree", "specialization", "institute", "year", "cpi", "gpa", "marks", "grade", "percentage", "board"]
            matched_count = sum(1 for w in header_keywords if w in line.lower())
            if matched_count >= 3:
                continue

            # Check if this line looks like a continuation or a new entry
            has_year = bool(re.search(r"\b\d{4}\b", line))
            has_degree = any(deg in line.lower() for deg in common_degrees)
            has_inst = any(kw in line.lower() for kw in ["college", "university", "school", "institute", "academy", "polytechnic", "sri chaitanya", "srichaitanya", "iare", "iaer"])

            if current_entry_parts:
                # If we have a year and the existing part also has a year, it's a new entry
                already_has_year = any(re.search(r"\b\d{4}\b", p) for p in current_entry_parts)
                # If we have a degree and the existing part also has a degree, it's a new entry
                already_has_degree = any(any(deg in p.lower() for deg in common_degrees) for p in current_entry_parts)

                if (has_year and already_has_year) or (has_degree and already_has_degree) or (has_inst and (already_has_year or already_has_degree)):
                    grouped_lines.append(" ".join(current_entry_parts))
                    current_entry_parts = [line]
                else:
                    current_entry_parts.append(line)
            else:
                current_entry_parts.append(line)

        if current_entry_parts:
            grouped_lines.append(" ".join(current_entry_parts))

        # Sort by length descending to match longest degrees first
        common_degrees = sorted(common_degrees, key=len, reverse=True)

        # Parse each grouped entry line
        for line in grouped_lines:
            # Pre-split common concatenations (e.g., 'B.TechinComputerScience' -> 'B.Tech in ComputerScience')
            line = re.sub(r"\]([A-Za-z])", r"] \1", line)
            line = re.sub(r"([A-Za-z]+)college", r"\1 college", line, flags=re.IGNORECASE)
            line = re.sub(r"([A-Za-z]+)school", r"\1 school", line, flags=re.IGNORECASE)
            line = re.sub(r"([A-Za-z]+)in([A-Z])", r"\1 in \2", line)
            line = re.sub(r"([A-Za-z]+)and([A-Z])", r"\1 and \2", line)
            line = re.sub(r"([A-Za-z]+)of([A-Z])", r"\1 of \2", line)

            # Spacing helper for CamelCase / concatenated words
            line_spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", line)
            line_spaced = re.sub(r"([A-Z])([A-Z][a-z])", r"\1 \2", line_spaced)
            # Standardize dashes/hyphens (replace Unicode dashes/replacement chars with '-')
            line_spaced = re.sub(r"[\u2013\u2014\ufffd]+", "-", line_spaced)
            line_spaced = line_spaced.replace("&", " & ").replace(",", ", ")
            line_spaced = re.sub(r"\s+", " ", line_spaced).strip()

            # Date Range or Single Year extraction supporting optional month prefixes
            month_pattern = r"(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+|\d{1,2}/)?"
            year_range_pattern = r"\b(" + month_pattern + r"\d{4})\s*-\s*(" + month_pattern + r"(?:[Pp]resent|\d{4}))\b"
            single_date_pattern = r"\b(" + month_pattern + r"\d{4})\b"

            year_range_match = re.search(year_range_pattern, line_spaced, re.IGNORECASE)
            single_year_match = re.search(single_date_pattern, line_spaced, re.IGNORECASE)

            start_date = None
            end_date = None

            if year_range_match:
                start_date = year_range_match.group(1).strip()
                end_date = year_range_match.group(2).strip().capitalize()
                line_spaced = line_spaced.replace(year_range_match.group(0), "")
            elif single_year_match:
                end_date = single_year_match.group(1).strip()
                line_spaced = line_spaced.replace(single_year_match.group(0), "")

            # Remove grade/GPA/percentage patterns
            # E.g. "GPA: 9.00 / 10.0", "CGPA: 10/10", "Aggregate: 98.9 / 100%", "98.9%", "10/10", "/ 10.0", "/ 100%"
            grade_pattern = r"\b(?:gpa|cgpa|cpi|aggregate|marks|percentage|score|grade)\b[\s:]*(?:\d{1,3}(?:\.\d{1,2})?\s*/?\s*\d{1,3}(?:\.\d{1,2})?%?|\d{1,3}(?:\.\d{1,2})?%?)?"
            line_spaced = re.sub(grade_pattern, "", line_spaced, flags=re.IGNORECASE)

            # Clean standalone ratio metrics (like "10/10", "/ 10.0", "/ 100%") or remaining percentages
            line_spaced = re.sub(r"\b\d{1,3}\s*/\s*\d{1,3}\b", "", line_spaced)
            line_spaced = re.sub(r"/\s*\d{1,3}(?:\.\d{1,2})?%?", "", line_spaced)
            line_spaced = re.sub(r"\b\d{1,3}(?:\.\d{1,2})?%", "", line_spaced)
            line_spaced = re.sub(r"\b\w*(?:percent|cgpa|gpa|cpi|marks|grade|score|current)\w*\b[\s:]*", "", line_spaced, flags=re.IGNORECASE)

            # Cleanup connectors
            line_cleaned = re.sub(r"\s*-\s*", " ", line_spaced)
            line_cleaned = re.sub(r"\s+", " ", line_cleaned).strip()

            degree = None
            field_of_study = None
            institution = None

            # Search for the degree in the line
            matched_degree_keyword = None
            for deg in common_degrees:
                pattern = r"\b" + re.escape(deg) + r"\b"
                match = re.search(pattern, line_cleaned, re.IGNORECASE)
                if match:
                    matched_degree_keyword = match.group(0)
                    break

            if matched_degree_keyword:
                # Map to canonical degree names
                lower_keyword = matched_degree_keyword.lower()
                if "b.tech" in lower_keyword or "btech" in lower_keyword:
                    degree = "B.Tech"
                elif "m.tech" in lower_keyword or "mtech" in lower_keyword:
                    degree = "M.Tech"
                elif "intermediate" in lower_keyword:
                    degree = "Intermediate"
                elif "ssc" in lower_keyword:
                    degree = "SSC"
                elif "secondary school" in lower_keyword or "secondary" in lower_keyword or "xstandard" in lower_keyword or "x standard" in lower_keyword or "10th" in lower_keyword:
                    degree = "SSC (10th Standard)"
                else:
                    degree = matched_degree_keyword.title()

                # Split at the degree match
                parts = re.split(re.escape(matched_degree_keyword), line_cleaned, flags=re.IGNORECASE)
                institution = parts[0].strip().rstrip(", - &")
                field_of_study = parts[1].strip() if len(parts) > 1 else None

            else:
                # Fallback to splitting by inst keywords or in half
                words = line_cleaned.split()
                if words:
                    degree = words[0]
                    remaining = " ".join(words[1:])
                    inst_keywords = ["griet", "college", "university", "institute", "school", "sri chaitanya", "srichaitanya", "iit", "nit", "bits", "iiit"]
                    inst_idx = -1
                    for kw in inst_keywords:
                        idx = remaining.lower().find(kw)
                        if idx != -1:
                            if inst_idx == -1 or idx < inst_idx:
                                inst_idx = idx

                    if inst_idx != -1:
                        field_of_study = remaining[:inst_idx].strip().rstrip(", - &")
                        institution = remaining[inst_idx:].strip()
                    else:
                        if len(words) >= 3:
                            mid = len(words) // 2
                            field_of_study = " ".join(words[1:mid])
                            institution = " ".join(words[mid:])
                        else:
                            institution = remaining if remaining else None

            # Clean field of study leading "in" or similar connectors
            if field_of_study:
                field_of_study = re.sub(r"^(?:in\s+)+", "", field_of_study, flags=re.IGNORECASE).strip()
                field_of_study = field_of_study.strip("() ").rstrip(".")
                if field_of_study == "-" or not field_of_study:
                    field_of_study = None

            education_entries.append({
                "institution": institution,
                "degree": degree,
                "field_of_study": field_of_study,
                "start_date": start_date,
                "end_date": end_date
            })

        return education_entries
