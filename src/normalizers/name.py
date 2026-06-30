"""
Name normalization and similarity scoring.

Rules:
  - Title-case normalization (handles ALL CAPS, lowercase, mixed).
  - Preserves initials as-is (never expands "K" to "Kumar").
  - Strips extra whitespace.
  - Configurable nickname/alias mapping for matching.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Set, Tuple


# Bidirectional nickname mappings.
# Each group contains names that should be treated as equivalent for matching.
DEFAULT_NICKNAME_GROUPS: List[List[str]] = [
    ["robert", "bob", "rob", "bobby", "bert"],
    ["william", "bill", "will", "billy", "willy", "liam"],
    ["richard", "rick", "dick", "rich"],
    ["james", "jim", "jimmy", "jamie"],
    ["john", "jack", "johnny"],
    ["thomas", "tom", "tommy"],
    ["michael", "mike", "mikey"],
    ["joseph", "joe", "joey"],
    ["charles", "charlie", "chuck"],
    ["daniel", "dan", "danny"],
    ["edward", "ed", "eddie", "ted", "teddy"],
    ["alexander", "alex", "alec"],
    ["samuel", "sam", "sammy"],
    ["benjamin", "ben", "benny"],
    ["matthew", "matt"],
    ["nicholas", "nick", "nicky"],
    ["christopher", "chris"],
    ["andrew", "andy", "drew"],
    ["stephen", "steve", "steven"],
    ["elizabeth", "liz", "beth", "lizzy", "eliza"],
    ["jennifer", "jen", "jenny"],
    ["katherine", "kate", "kathy", "kat", "katie", "catherine"],
    ["margaret", "maggie", "meg", "peggy"],
    ["patricia", "pat", "patty", "trish"],
    ["deborah", "deb", "debbie"],
    ["susan", "sue", "suzy"],
    ["rebecca", "becky", "becca"],
    ["jessica", "jess", "jessie"],
    ["victoria", "vicky", "tori"],
    # Transliteration groups
    ["mohammed", "muhammad", "mohamed", "mohammad", "mohamad"],
    ["alexander", "aleksandr", "aleksander"],
    ["sergei", "sergey", "serge"],
    ["dmitri", "dmitry", "dmitriy"],
    ["mikhail", "michael"],
    ["nikolai", "nikolay"],
    ["yusuf", "youssef", "yousuf", "joseph"],
    ["ahmed", "ahmad"],
    ["ali", "aly"],
    ["hassan", "hasan"],
    ["hussein", "husain", "hussain"],
    ["ibrahim", "abraham"],
]


class NameNormalizer:
    """Normalizes and compares candidate names."""

    def __init__(
        self, nickname_groups: Optional[List[List[str]]] = None
    ) -> None:
        self._nickname_groups = nickname_groups or DEFAULT_NICKNAME_GROUPS
        # Build a lookup: lowercase name -> set of equivalent lowercase names
        self._nickname_map: Dict[str, Set[str]] = {}
        for group in self._nickname_groups:
            lower_group = {n.lower() for n in group}
            for name in lower_group:
                if name not in self._nickname_map:
                    self._nickname_map[name] = set()
                self._nickname_map[name].update(lower_group)

    def normalize(self, name: Optional[str]) -> Optional[str]:
        """
        Normalize a name to title case.

        - Strips extra whitespace.
        - Converts to title case.
        - Preserves single-letter initials (does NOT expand them).
        - Returns None for empty/invalid input.

        Examples:
            "rahul sharma"     -> "Rahul Sharma"
            "RAHUL SHARMA"     -> "Rahul Sharma"
            "Rahul K Sharma"   -> "Rahul K Sharma"
            "  rahul   sharma" -> "Rahul Sharma"
        """
        if not name or not isinstance(name, str):
            return None
        # Remove honorifics (mr, mrs, ms, dr, prof, sir, etc.)
        honorifics_pattern = r"\b(mr|mrs|ms|dr|prof|sir|md|phd)\b\.?"
        cleaned = re.sub(honorifics_pattern, "", name.strip(), flags=re.IGNORECASE)
        
        # Remove punctuation (keep spaces, letters, numbers, and periods)
        cleaned = re.sub(r"[^\w\s\.]", "", cleaned)
        
        # Strip and collapse whitespace
        cleaned = re.sub(r"\s+", " ", cleaned.strip())
        if not cleaned:
            return None
        # Title-case each part
        parts = cleaned.split(" ")
        normalized_parts = []
        for part in parts:
            if len(part) == 1:
                # Single letter initial — uppercase it
                normalized_parts.append(part.upper())
            elif len(part) == 2 and part.endswith("."):
                # Initial with period like "K."
                normalized_parts.append(part[0].upper() + ".")
            else:
                # Regular name part — title case
                normalized_parts.append(part.capitalize())
        return " ".join(normalized_parts)

    def tokenize(self, name: Optional[str]) -> List[str]:
        """Split a name into lowercase tokens, stripping periods."""
        if not name:
            return []
        return [
            t.rstrip(".").lower()
            for t in name.strip().split()
            if t.rstrip(".")
        ]

    def get_canonical_tokens(self, tokens: List[str]) -> Set[str]:
        """Expand tokens with all known nickname equivalents."""
        expanded: Set[str] = set()
        for token in tokens:
            expanded.add(token)
            if token in self._nickname_map:
                expanded.update(self._nickname_map[token])
        return expanded

    def similarity(
        self, name1: Optional[str], name2: Optional[str]
    ) -> float:
        """
        Compute similarity between two names.

        Uses token-based Jaccard similarity with nickname expansion.
        Returns a float between 0.0 and 1.0.

        Handles:
          - "Rahul Sharma" vs "Rahul K Sharma" -> high similarity
          - "Bob Smith" vs "Robert Smith" -> high similarity (nickname)
          - "Rahul Sharma" vs "Priya Patel" -> low similarity
        """
        if not name1 or not name2:
            return 0.0

        tokens1 = self.tokenize(name1)
        tokens2 = self.tokenize(name2)

        if not tokens1 or not tokens2:
            return 0.0

        # Expand with nicknames for matching
        expanded1 = self.get_canonical_tokens(tokens1)
        expanded2 = self.get_canonical_tokens(tokens2)

        intersection = expanded1 & expanded2
        union = expanded1 | expanded2

        if not union:
            return 0.0

        jaccard = len(intersection) / len(union)

        # Boost if all original tokens of the shorter name are covered
        shorter = tokens1 if len(tokens1) <= len(tokens2) else tokens2
        longer_expanded = expanded2 if len(tokens1) <= len(tokens2) else expanded1

        covered = sum(
            1
            for t in shorter
            if t in longer_expanded
            or any(
                nick in longer_expanded
                for nick in self._nickname_map.get(t, set())
            )
        )
        coverage = covered / len(shorter) if shorter else 0.0

        # Weighted: 60% Jaccard + 40% coverage of shorter name
        return 0.6 * jaccard + 0.4 * coverage

    def are_compatible(
        self,
        name1: Optional[str],
        name2: Optional[str],
        threshold: float = 0.85,
    ) -> Tuple[bool, float]:
        """
        Check if two names likely belong to the same person.

        Returns (is_compatible, similarity_score).
        """
        score = self.similarity(name1, name2)
        return score >= threshold, score
