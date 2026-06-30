"""
URL normalization for LinkedIn, GitHub, portfolio, and general URLs.

Strips trailing slashes, unnecessary prefixes, query parameters,
and normalizes to a consistent format.
"""

from __future__ import annotations

import re
from typing import Optional, Tuple
from urllib.parse import urlparse, urlunparse


class URLNormalizer:
    """
    Normalizes URLs, with special handling for LinkedIn and GitHub.

    Examples:
        "https://www.linkedin.com/in/rahul-sharma/"
            -> "https://linkedin.com/in/rahul-sharma"

        "http://github.com/rahul-sharma/"
            -> "https://github.com/rahul-sharma"

        "github.com/rahul-sharma"
            -> "https://github.com/rahul-sharma"

        "https://rahuldev.com/portfolio?ref=google"
            -> "https://rahuldev.com/portfolio"
    """

    def normalize(self, url: Optional[str]) -> Optional[str]:
        """
        Normalize a URL to a consistent format.

        Returns normalized URL string or None for invalid/empty input.
        """
        if not url or not isinstance(url, str):
            return None

        cleaned = url.strip()
        if not cleaned:
            return None

        # Add scheme if missing
        if not re.match(r"^https?://", cleaned, re.IGNORECASE):
            cleaned = "https://" + cleaned

        try:
            parsed = urlparse(cleaned)
        except Exception:
            return None

        if not parsed.netloc:
            return None

        # Lowercase the domain, strip www.
        domain = parsed.netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]

        # Remove trailing slashes from path
        path = parsed.path.rstrip("/")

        # For LinkedIn and GitHub, strip query params and fragments
        if "linkedin.com" in domain or "github.com" in domain:
            normalized = urlunparse((
                "https",  # Always use HTTPS
                domain,
                path,
                "",  # params
                "",  # no query
                "",  # no fragment
            ))
        else:
            # For other URLs, keep as-is but clean up
            normalized = urlunparse((
                "https",
                domain,
                path,
                "",
                "",  # strip query for cleanliness
                "",
            ))

        return normalized if normalized != "https://" else None

    def extract_linkedin_username(self, url: Optional[str]) -> Optional[str]:
        """
        Extract LinkedIn username from a URL.

        "https://linkedin.com/in/rahul-sharma" -> "rahul-sharma"
        """
        normalized = self.normalize(url)
        if not normalized:
            return None

        match = re.search(
            r"linkedin\.com/in/([^/\?#]+)", normalized, re.IGNORECASE
        )
        return match.group(1) if match else None

    def extract_github_username(self, url: Optional[str]) -> Optional[str]:
        """
        Extract GitHub username from a URL.

        "https://github.com/rahul-sharma" -> "rahul-sharma"
        "https://github.com/rahul-sharma/repo" -> "rahul-sharma"
        """
        normalized = self.normalize(url)
        if not normalized:
            return None

        match = re.search(
            r"github\.com/([^/\?#]+)", normalized, re.IGNORECASE
        )
        if match:
            username = match.group(1)
            # Exclude GitHub pages that aren't usernames
            excluded = {
                "features", "pricing", "about", "explore",
                "marketplace", "topics", "trending", "collections",
                "events", "sponsors", "settings", "notifications",
                "login", "signup", "join", "enterprise", "team",
                "organizations", "orgs",
            }
            if username.lower() not in excluded:
                return username
        return None

    def classify_url(
        self, url: Optional[str]
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Classify a URL into a category and normalize it.

        Returns (category, normalized_url) where category is one of:
        "linkedin", "github", "portfolio", "other", or None.
        """
        normalized = self.normalize(url)
        if not normalized:
            return None, None

        lower = normalized.lower()

        if "linkedin.com/in/" in lower:
            return "linkedin", normalized
        elif "github.com/" in lower:
            return "github", normalized
        elif any(
            kw in lower
            for kw in ["portfolio", "personal", "blog", "dev.", ".dev"]
        ):
            return "portfolio", normalized
        else:
            return "other", normalized
