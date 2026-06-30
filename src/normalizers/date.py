"""
Date normalization to YYYY-MM or YYYY format.

Handles various input formats using regex parsing.
No external dependencies required.
"""

from __future__ import annotations

import re
from typing import Optional

# Month name/abbreviation to number mapping
MONTH_MAP = {
    "jan": "01", "january": "01",
    "feb": "02", "february": "02",
    "mar": "03", "march": "03",
    "apr": "04", "april": "04",
    "may": "05",
    "jun": "06", "june": "06",
    "jul": "07", "july": "07",
    "aug": "08", "august": "08",
    "sep": "09", "sept": "09", "september": "09",
    "oct": "10", "october": "10",
    "nov": "11", "november": "11",
    "dec": "12", "december": "12",
}

# Patterns ordered by specificity (most specific first)
DATE_PATTERNS = [
    # "January 2023" or "Jan 2023"
    re.compile(
        r"^(?P<month>[A-Za-z]+)\s+(?P<year>\d{4})$"
    ),
    # "2023-01" (already normalized)
    re.compile(
        r"^(?P<year>\d{4})-(?P<month>\d{1,2})$"
    ),
    # "01/2023" or "1/2023"
    re.compile(
        r"^(?P<month>\d{1,2})/(?P<year>\d{4})$"
    ),
    # "01-2023"
    re.compile(
        r"^(?P<month>\d{1,2})-(?P<year>\d{4})$"
    ),
    # "2023/01"
    re.compile(
        r"^(?P<year>\d{4})/(?P<month>\d{1,2})$"
    ),
    # "2023-01-15" (full date — extract year-month)
    re.compile(
        r"^(?P<year>\d{4})-(?P<month>\d{1,2})-\d{1,2}$"
    ),
    # "01/15/2023" (US date — extract month and year)
    re.compile(
        r"^(?P<month>\d{1,2})/\d{1,2}/(?P<year>\d{4})$"
    ),
    # "15/01/2023" (EU date — day/month/year)
    # Ambiguous with US format, so we only use this if month > 12
    re.compile(
        r"^(?P<day>\d{1,2})/(?P<month>\d{1,2})/(?P<year>\d{4})$"
    ),
    # "2023" (year only)
    re.compile(
        r"^(?P<year>\d{4})$"
    ),
    # "Jan-2023" or "January-2023"
    re.compile(
        r"^(?P<month>[A-Za-z]+)-(?P<year>\d{4})$"
    ),
    # "2023 Jan" or "2023 January"
    re.compile(
        r"^(?P<year>\d{4})\s+(?P<month>[A-Za-z]+)$"
    ),
]


class DateNormalizer:
    """
    Normalizes dates to YYYY-MM or YYYY format.

    Examples:
        "Jan 2023"      -> "2023-01"
        "01/2023"       -> "2023-01"
        "January 2023"  -> "2023-01"
        "2023-01"       -> "2023-01"
        "2023"          -> "2023"
        "present"       -> "present"
        "current"       -> "present"
        ""              -> None
        "invalid"       -> None
    """

    # Values that represent "current/ongoing"
    PRESENT_ALIASES = {"present", "current", "now", "ongoing", "till date", "to date"}

    def normalize(self, date_str: Optional[str]) -> Optional[str]:
        """
        Normalize a date string to YYYY-MM or YYYY format.

        Returns normalized date string, "present" for ongoing dates,
        or None for invalid/empty input.
        """
        if not date_str or not isinstance(date_str, str):
            return None

        cleaned = date_str.strip()
        if not cleaned:
            return None

        # Check for "present" aliases
        if cleaned.lower() in self.PRESENT_ALIASES:
            return "present"

        # Try each pattern
        for pattern in DATE_PATTERNS:
            match = pattern.match(cleaned)
            if match:
                groups = match.groupdict()
                year = groups.get("year")
                month_raw = groups.get("month")

                if not year:
                    continue

                # Validate year
                try:
                    year_int = int(year)
                    if year_int < 1900 or year_int > 2100:
                        continue
                except ValueError:
                    continue

                if not month_raw:
                    return year

                # Resolve month
                month_num = self._resolve_month(month_raw)
                if month_num:
                    return f"{year}-{month_num}"
                elif not month_raw.isdigit():
                    # Month name didn't resolve
                    continue
                else:
                    return year

        return None

    def _resolve_month(self, month_raw: str) -> Optional[str]:
        """Resolve a month value (name or number) to a 2-digit string."""
        # Try as a name/abbreviation
        lower = month_raw.lower().strip(".")
        if lower in MONTH_MAP:
            return MONTH_MAP[lower]

        # Try as a number
        try:
            month_int = int(month_raw)
            if 1 <= month_int <= 12:
                return f"{month_int:02d}"
        except ValueError:
            pass

        return None
