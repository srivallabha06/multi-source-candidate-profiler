"""
Portfolio website adapter.

Fetches HTML from portfolio/personal websites,
extracts text, and uses regex pipelines to find
contact info, skills, and links.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from src.adapters.base import BaseAdapter
from src.models.candidate import RawCandidateRecord

logger = logging.getLogger(__name__)

try:
    import requests as req_lib
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

# Reuse patterns from PDF adapter
EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)
PHONE_PATTERN = re.compile(
    r"(?:\+?\d{1,3}[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}"
    r"|\+?\d{10,13}"
)


class PortfolioWebAdapter(BaseAdapter):
    """
    Adapter for portfolio/personal websites.

    Fetches HTML via requests, strips tags, extracts contact
    info and skills via regex. Handles network failures gracefully.
    """

    def __init__(
        self,
        request_timeout: int = 30,
        skill_keywords: Optional[List[str]] = None,
    ) -> None:
        self._timeout = request_timeout
        self._skill_keywords = skill_keywords or []

    @property
    def source_type(self) -> str:
        return "portfolio_web"

    def can_handle(self, source_path: str) -> bool:
        lower = source_path.lower().strip()
        # Handle URLs that aren't GitHub or LinkedIn
        if any(
            lower.startswith(prefix)
            for prefix in ["http://", "https://", "www."]
        ):
            if "github.com" not in lower and "linkedin.com" not in lower:
                return True
        return False

    def ingest(self, source_path: str) -> List[RawCandidateRecord]:
        if not HAS_REQUESTS:
            logger.error("Cannot fetch web pages without requests library")
            return []

        html = self._fetch_html(source_path)
        if not html:
            return []

        try:
            text = self._strip_html(html)
            record_data = self._extract_from_text(text, source_path)
            return [self._create_record(record_data, source_path)]
        except Exception as e:
            logger.error(
                "Error extracting from portfolio '%s': %s", source_path, e
            )
            return []

    def _fetch_html(self, url: str) -> Optional[str]:
        """Fetch HTML content from a URL."""
        if not url.startswith("http"):
            url = "https://" + url

        try:
            response = req_lib.get(
                url,
                timeout=self._timeout,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (compatible; CandidateTransformer/1.0)"
                    )
                },
            )
            response.raise_for_status()
            return response.text
        except req_lib.Timeout:
            logger.error("Timeout fetching: %s", url)
        except req_lib.ConnectionError:
            logger.error("Connection error fetching: %s", url)
        except req_lib.HTTPError as e:
            logger.error("HTTP error fetching '%s': %s", url, e)
        except Exception as e:
            logger.error("Error fetching '%s': %s", url, e)
        return None

    def _strip_html(self, html: str) -> str:
        """Strip HTML tags and extract visible text."""
        # Remove script and style elements
        cleaned = re.sub(
            r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE
        )
        # Remove HTML tags
        cleaned = re.sub(r"<[^>]+>", " ", cleaned)
        # Decode HTML entities
        cleaned = re.sub(r"&[a-zA-Z]+;", " ", cleaned)
        cleaned = re.sub(r"&#\d+;", " ", cleaned)
        # Collapse whitespace
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    def _extract_from_text(
        self, text: str, source_url: str
    ) -> Dict[str, Any]:
        """Extract candidate data from portfolio page text."""
        result: Dict[str, Any] = {}

        result["full_name"] = None  # Hard to extract reliably from websites
        result["emails"] = list(set(EMAIL_PATTERN.findall(text)))
        result["phones"] = list(set(PHONE_PATTERN.findall(text)))

        # Links
        linkedin_match = re.search(
            r"linkedin\.com/in/([A-Za-z0-9_-]+)", text, re.IGNORECASE
        )
        github_match = re.search(
            r"github\.com/([A-Za-z0-9_-]+)", text, re.IGNORECASE
        )

        result["links"] = {
            "linkedin": (
                f"https://linkedin.com/in/{linkedin_match.group(1)}"
                if linkedin_match
                else None
            ),
            "github": (
                f"https://github.com/{github_match.group(1)}"
                if github_match
                else None
            ),
            "portfolio": source_url,
            "other": [],
        }

        # Skills
        result["skills"] = self._extract_skills(text)
        result["location"] = {"city": None, "region": None, "country": None}
        result["headline"] = None
        result["years_experience"] = None
        result["experience"] = []
        result["education"] = []

        return result

    def _extract_skills(self, text: str) -> List[str]:
        """Extract skills by keyword matching."""
        if not self._skill_keywords:
            return []
        text_lower = text.lower()
        found = []
        for skill in self._skill_keywords:
            pattern = r"\b" + re.escape(skill.lower()) + r"\b"
            if re.search(pattern, text_lower):
                found.append(skill)
        return found
