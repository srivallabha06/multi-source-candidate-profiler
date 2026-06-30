"""
GitHub adapter.

Extracts candidate information from GitHub profiles using
the REST API or mock JSON files for offline testing.
Handles rate limiting, private profiles, and API failures gracefully.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.adapters.base import BaseAdapter
from src.models.candidate import RawCandidateRecord

logger = logging.getLogger(__name__)

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    logger.warning("requests library not installed. GitHub API calls disabled.")


class GitHubAdapter(BaseAdapter):
    """
    Adapter for GitHub profiles.

    Handles:
    - GitHub profile URLs (e.g., https://github.com/username)
    - GitHub mock JSON files (for offline testing)
    - GitHub REST API with optional token authentication
    - Rate limiting, private profiles, missing repos, API failures
    """

    API_BASE = "https://api.github.com"

    def __init__(
        self,
        token: Optional[str] = None,
        max_repos: int = 50,
        request_timeout: int = 30,
    ) -> None:
        self._token = token or os.environ.get("GITHUB_TOKEN")
        self._max_repos = max_repos
        self._timeout = request_timeout

    @property
    def source_type(self) -> str:
        return "github"

    def can_handle(self, source_path: str) -> bool:
        # Handle GitHub URLs
        if "github.com/" in source_path.lower():
            return True
        # Handle mock GitHub JSON files
        path = Path(source_path)
        if path.suffix.lower() == ".json" and "github" in path.stem.lower():
            return True
        return False

    def ingest(self, source_path: str) -> List[RawCandidateRecord]:
        # Check if it's a local JSON file (mock data)
        path = Path(source_path)
        if path.exists() and path.suffix.lower() == ".json":
            return self._ingest_from_file(source_path)

        # Otherwise, try API
        if not HAS_REQUESTS:
            logger.error("Cannot fetch GitHub API without requests library")
            return []

        username = self._extract_username(source_path)
        if not username:
            logger.warning("Could not extract GitHub username from: %s", source_path)
            return []

        return self._ingest_from_api(username, source_path)

    def _extract_username(self, url: str) -> Optional[str]:
        """Extract GitHub username from URL."""
        match = re.search(r"github\.com/([^/\?#]+)", url, re.IGNORECASE)
        if match:
            username = match.group(1)
            excluded = {
                "features", "pricing", "about", "explore",
                "marketplace", "topics", "trending", "login", "signup",
            }
            if username.lower() not in excluded:
                return username
        return None

    def _ingest_from_file(self, file_path: str) -> List[RawCandidateRecord]:
        """Ingest from a local mock GitHub JSON file."""
        data = self._safe_read_json(file_path)
        if data is None:
            return []

        try:
            record_data = self._extract_from_mock(data)
            return [self._create_record(record_data, file_path)]
        except Exception as e:
            logger.error("Error extracting GitHub data from '%s': %s", file_path, e)
            return []

    def _ingest_from_api(
        self, username: str, source_url: str
    ) -> List[RawCandidateRecord]:
        """Ingest from GitHub REST API."""
        headers = self._get_headers()

        # Fetch user profile
        profile = self._api_get(f"/users/{username}", headers)
        if profile is None:
            return []

        # Fetch repositories
        repos = self._api_get(
            f"/users/{username}/repos?sort=pushed&per_page={self._max_repos}",
            headers,
        )
        if repos is None:
            repos = []

        # Extract languages from repos
        languages = self._aggregate_languages(repos)
        topics = self._aggregate_topics(repos)

        record_data = {
            "full_name": profile.get("name"),
            "emails": [profile["email"]] if profile.get("email") else [],
            "phones": [],
            "headline": profile.get("bio"),
            "location": self._parse_github_location(profile.get("location")),
            "links": {
                "linkedin": None,
                "github": profile.get("html_url", source_url),
                "portfolio": profile.get("blog") or None,
                "other": [],
            },
            "skills": list(languages.keys()) + list(topics),
            "skills_detail": {
                "languages": languages,
                "topics": list(topics),
            },
            "repos_count": profile.get("public_repos", 0),
            "followers": profile.get("followers", 0),
            "github_username": profile.get("login", username),
        }

        return [self._create_record(record_data, source_url)]

    def _extract_from_mock(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract fields from mock GitHub JSON data."""
        profile = data.get("profile", data)
        repos = data.get("repos", data.get("repositories", []))

        languages = {}
        topics: set = set()

        if isinstance(repos, list):
            for repo in repos:
                if not isinstance(repo, dict):
                    continue
                lang = repo.get("language")
                if lang:
                    languages[lang] = languages.get(lang, 0) + 1
                repo_topics = repo.get("topics", [])
                if isinstance(repo_topics, list):
                    topics.update(str(t) for t in repo_topics if t)

        return {
            "full_name": profile.get("name"),
            "emails": [profile["email"]] if profile.get("email") else [],
            "phones": [],
            "headline": profile.get("bio"),
            "location": self._parse_github_location(profile.get("location")),
            "links": {
                "linkedin": None,
                "github": profile.get("html_url", profile.get("github_url")),
                "portfolio": profile.get("blog") or None,
                "other": [],
            },
            "skills": list(languages.keys()) + list(topics),
            "skills_detail": {
                "languages": languages,
                "topics": list(topics),
            },
            "repos_count": profile.get("public_repos", len(repos)),
            "followers": profile.get("followers", 0),
            "github_username": profile.get("login"),
        }

    def _parse_github_location(self, location: Optional[str]) -> Dict[str, Any]:
        """Parse GitHub location string (e.g., 'Bengaluru, India')."""
        if not location or not isinstance(location, str):
            return {"city": None, "region": None, "country": None}

        parts = [p.strip() for p in location.split(",")]
        return {
            "city": parts[0] if len(parts) >= 1 else None,
            "region": parts[1] if len(parts) >= 3 else None,
            "country": parts[-1] if len(parts) >= 2 else None,
        }

    def _get_headers(self) -> Dict[str, str]:
        """Build API request headers."""
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "CandidateDataTransformer/1.0",
        }
        if self._token:
            headers["Authorization"] = f"token {self._token}"
        return headers

    def _api_get(
        self, endpoint: str, headers: Dict[str, str]
    ) -> Optional[Any]:
        """Make a GET request to the GitHub API with error handling."""
        url = f"{self.API_BASE}{endpoint}"
        try:
            response = requests.get(
                url, headers=headers, timeout=self._timeout
            )

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 403:
                # Rate limited
                reset_time = response.headers.get("X-RateLimit-Reset")
                logger.warning(
                    "GitHub API rate limited. Reset at: %s", reset_time
                )
                return None
            elif response.status_code == 404:
                logger.info("GitHub profile not found: %s", endpoint)
                return None
            else:
                logger.warning(
                    "GitHub API returned %d for %s",
                    response.status_code,
                    endpoint,
                )
                return None

        except requests.Timeout:
            logger.error("GitHub API timeout for: %s", endpoint)
            return None
        except requests.ConnectionError:
            logger.error("GitHub API connection error for: %s", endpoint)
            return None
        except Exception as e:
            logger.error("GitHub API error for '%s': %s", endpoint, e)
            return None

    def _aggregate_languages(
        self, repos: List[Dict[str, Any]]
    ) -> Dict[str, int]:
        """Aggregate languages across all repos."""
        languages: Dict[str, int] = {}
        if not isinstance(repos, list):
            return languages

        for repo in repos:
            if not isinstance(repo, dict):
                continue
            lang = repo.get("language")
            if lang and isinstance(lang, str):
                languages[lang] = languages.get(lang, 0) + 1
        return languages

    def _aggregate_topics(self, repos: List[Dict[str, Any]]) -> set:
        """Aggregate topics across all repos."""
        topics: set = set()
        if not isinstance(repos, list):
            return topics

        for repo in repos:
            if not isinstance(repo, dict):
                continue
            repo_topics = repo.get("topics", [])
            if isinstance(repo_topics, list):
                topics.update(str(t) for t in repo_topics if t)
        return topics
