"""
Country normalization to ISO-3166 Alpha-2 codes.

Uses `pycountry` with fuzzy search plus a custom alias map
for common variants not covered by the library.
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

try:
    import pycountry

    HAS_PYCOUNTRY = True
except ImportError:
    HAS_PYCOUNTRY = False
    logger.warning(
        "pycountry library not installed. Country normalization will use "
        "basic alias lookup only. Install with: pip install pycountry"
    )


# Custom alias map for common variants not always handled by pycountry
COUNTRY_ALIASES: Dict[str, str] = {
    # India variants
    "india": "IN",
    "ind": "IN",
    "republic of india": "IN",
    "bharat": "IN",
    # USA variants
    "usa": "US",
    "us": "US",
    "united states": "US",
    "united states of america": "US",
    "america": "US",
    # UK variants
    "uk": "GB",
    "united kingdom": "GB",
    "great britain": "GB",
    "britain": "GB",
    "england": "GB",
    # China variants
    "china": "CN",
    "chn": "CN",
    "peoples republic of china": "CN",
    "prc": "CN",
    # Germany variants
    "germany": "DE",
    "deu": "DE",
    "deutschland": "DE",
    # France
    "france": "FR",
    "fra": "FR",
    # Japan
    "japan": "JP",
    "jpn": "JP",
    # Canada
    "canada": "CA",
    "can": "CA",
    # Australia
    "australia": "AU",
    "aus": "AU",
    # Brazil
    "brazil": "BR",
    "bra": "BR",
    "brasil": "BR",
    # Russia
    "russia": "RU",
    "rus": "RU",
    "russian federation": "RU",
    # South Korea
    "south korea": "KR",
    "korea": "KR",
    "kor": "KR",
    "republic of korea": "KR",
    # Singapore
    "singapore": "SG",
    "sgp": "SG",
    # UAE
    "uae": "AE",
    "united arab emirates": "AE",
    # Israel
    "israel": "IL",
    "isr": "IL",
    # Netherlands
    "netherlands": "NL",
    "nld": "NL",
    "holland": "NL",
    # Sweden
    "sweden": "SE",
    "swe": "SE",
    # Switzerland
    "switzerland": "CH",
    "che": "CH",
    # Ireland
    "ireland": "IE",
    "irl": "IE",
    # New Zealand
    "new zealand": "NZ",
    "nzl": "NZ",
    # South Africa
    "south africa": "ZA",
    "zaf": "ZA",
}


class CountryNormalizer:
    """
    Normalizes country names/codes to ISO-3166 Alpha-2 codes.

    Examples:
        "India"              -> "IN"
        "IND"                -> "IN"
        "Republic of India"  -> "IN"
        "IN"                 -> "IN"
        "United States"      -> "US"
        "xyznotacountry"     -> None
    """

    def __init__(
        self, extra_aliases: Optional[Dict[str, str]] = None
    ) -> None:
        self._aliases = dict(COUNTRY_ALIASES)
        if extra_aliases:
            for k, v in extra_aliases.items():
                self._aliases[k.lower().strip()] = v.upper().strip()

    def normalize(self, country: Optional[str]) -> Optional[str]:
        """
        Normalize a country name or code to ISO-3166 Alpha-2.

        Returns the 2-letter code (e.g., "IN") or None.
        """
        if not country or not isinstance(country, str):
            return None

        cleaned = country.strip()
        if not cleaned:
            return None

        # 1. If it's already a 2-letter code, validate it
        if len(cleaned) == 2:
            upper = cleaned.upper()
            if self._is_valid_alpha2(upper):
                return upper

        # 2. Check custom alias map
        lower = cleaned.lower()
        if lower in self._aliases:
            return self._aliases[lower]

        # 3. Try pycountry exact lookups
        if HAS_PYCOUNTRY:
            result = self._lookup_pycountry(cleaned)
            if result:
                return result

        # 4. Try pycountry fuzzy search
        if HAS_PYCOUNTRY:
            result = self._fuzzy_search_pycountry(cleaned)
            if result:
                return result

        logger.debug("Could not normalize country: %s", country)
        return None

    def _is_valid_alpha2(self, code: str) -> bool:
        """Check if a 2-letter code is a valid ISO-3166 Alpha-2 code."""
        if HAS_PYCOUNTRY:
            try:
                result = pycountry.countries.get(alpha_2=code)
                return result is not None
            except Exception:
                pass
        # Fallback: check if it's in our alias map values
        return code in set(self._aliases.values())

    def _lookup_pycountry(self, value: str) -> Optional[str]:
        """Try exact lookups via pycountry."""
        try:
            # Try alpha_2
            if len(value) == 2:
                result = pycountry.countries.get(alpha_2=value.upper())
                if result:
                    return result.alpha_2

            # Try alpha_3
            if len(value) == 3:
                result = pycountry.countries.get(alpha_3=value.upper())
                if result:
                    return result.alpha_2

            # Try name
            result = pycountry.countries.get(name=value)
            if result:
                return result.alpha_2

            # Try official_name
            result = pycountry.countries.get(official_name=value)
            if result:
                return result.alpha_2

        except Exception as e:
            logger.debug("pycountry lookup error for '%s': %s", value, e)

        return None

    def _fuzzy_search_pycountry(self, value: str) -> Optional[str]:
        """Use pycountry's fuzzy search as a last resort."""
        try:
            results = pycountry.countries.search_fuzzy(value)
            if results:
                return results[0].alpha_2
        except LookupError:
            pass
        except Exception as e:
            logger.debug("pycountry fuzzy search error for '%s': %s", value, e)
        return None
