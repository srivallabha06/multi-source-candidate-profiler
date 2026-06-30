"""
Phone number normalization to E.164 format.

Uses the `phonenumbers` library (Google's libphonenumber port).
Configurable default region for numbers without country prefix.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import phonenumbers
    from phonenumbers import PhoneNumberFormat, NumberParseException

    HAS_PHONENUMBERS = True
except ImportError:
    HAS_PHONENUMBERS = False
    logger.warning(
        "phonenumbers library not installed. Phone normalization will use "
        "basic regex fallback. Install with: pip install phonenumbers"
    )


class PhoneNormalizer:
    """
    Normalizes phone numbers to E.164 format.

    Examples:
        "9876543210"       -> "+919876543210" (with default_region="IN")
        "+91 9876543210"   -> "+919876543210"
        "91-9876543210"    -> "+919876543210"
        "(555) 123-4567"   -> "+15551234567" (with default_region="US")
        "invalid"          -> None
    """

    def __init__(self, default_region: str = "IN") -> None:
        self.default_region = default_region

    def normalize(self, phone: Optional[str]) -> Optional[str]:
        """
        Normalize a phone number to E.164 format.

        Returns the E.164 string (e.g., "+919876543210") or None if
        the number is invalid or cannot be parsed.
        """
        if not phone or not isinstance(phone, str):
            return None

        cleaned = phone.strip()
        if not cleaned:
            return None

        if HAS_PHONENUMBERS:
            return self._normalize_with_library(cleaned)
        else:
            return self._normalize_with_regex(cleaned)

    def _normalize_with_library(self, phone: str) -> Optional[str]:
        """Use phonenumbers library for proper E.164 normalization."""
        try:
            # If it starts with '+', parse without default region
            if phone.startswith("+"):
                parsed = phonenumbers.parse(phone, None)
            else:
                # Try with default region
                parsed = phonenumbers.parse(phone, self.default_region)

            if phonenumbers.is_valid_number(parsed):
                return phonenumbers.format_number(
                    parsed, PhoneNumberFormat.E164
                )

            # Even if not strictly valid, if it's possible, format it
            if phonenumbers.is_possible_number(parsed):
                return phonenumbers.format_number(
                    parsed, PhoneNumberFormat.E164
                )

            logger.debug("Invalid phone number: %s", phone)
            return None

        except NumberParseException as e:
            logger.debug("Failed to parse phone '%s': %s", phone, e)
            return None
        except Exception as e:
            logger.debug("Unexpected error parsing phone '%s': %s", phone, e)
            return None

    def _normalize_with_regex(self, phone: str) -> Optional[str]:
        """
        Basic regex fallback when phonenumbers is not installed.

        Strips non-digit characters and prepends country code.
        This is NOT as accurate as the phonenumbers library.
        """
        # Remove all non-digit characters except leading +
        digits = re.sub(r"[^\d]", "", phone)

        if not digits or len(digits) < 7:
            return None

        # If the original started with +, keep the digits as-is
        if phone.lstrip().startswith("+"):
            return f"+{digits}"

        # Check for common country code prefixes
        if self.default_region == "IN" and len(digits) == 10:
            return f"+91{digits}"
        elif self.default_region == "US" and len(digits) == 10:
            return f"+1{digits}"
        elif digits.startswith("91") and len(digits) == 12:
            return f"+{digits}"
        elif digits.startswith("1") and len(digits) == 11:
            return f"+{digits}"
        else:
            # Can't determine country code reliably
            return f"+{digits}" if len(digits) >= 10 else None
