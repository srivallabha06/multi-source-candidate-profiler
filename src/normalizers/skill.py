"""
Skill canonicalization using a configurable taxonomy.

Loads a taxonomy JSON mapping canonical skill names to their aliases.
Performs case-insensitive matching. Returns canonical name or original.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class SkillNormalizer:
    """
    Normalizes skill names using a configurable taxonomy.

    Taxonomy format (skill_taxonomy.json):
    {
      "skills": [
        {
          "canonical": "Java",
          "aliases": ["JAVA", "Core Java", "Java SE", "java8"]
        }
      ]
    }

    Examples:
        "JAVA"       -> "Java"
        "Core Java"  -> "Java"
        "Java SE"    -> "Java"
        "AWS Cloud"  -> "AWS"
        "unknown_skill" -> "unknown_skill" (returned as-is, title-cased)
    """

    def __init__(self, taxonomy_path: Optional[str] = None) -> None:
        # Lowercase alias -> canonical name
        self._alias_map: Dict[str, str] = {}
        # Set of canonical names (lowercase) for quick lookup
        self._canonical_set: set = set()

        if taxonomy_path:
            self._load_taxonomy(taxonomy_path)

    def _load_taxonomy(self, path: str) -> None:
        """Load skill taxonomy from a JSON file."""
        try:
            taxonomy_file = Path(path)
            if not taxonomy_file.exists():
                logger.warning("Skill taxonomy file not found: %s", path)
                return

            with open(taxonomy_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            skills = data.get("skills", [])
            for entry in skills:
                canonical = entry.get("canonical", "").strip()
                if not canonical:
                    continue

                canonical_lower = canonical.lower()
                self._canonical_set.add(canonical_lower)
                # Map the canonical name to itself
                self._alias_map[canonical_lower] = canonical

                aliases = entry.get("aliases", [])
                for alias in aliases:
                    alias_clean = alias.strip().lower()
                    if alias_clean:
                        self._alias_map[alias_clean] = canonical

            logger.info(
                "Loaded skill taxonomy: %d canonical skills, %d total aliases",
                len(self._canonical_set),
                len(self._alias_map),
            )

        except json.JSONDecodeError as e:
            logger.error("Invalid JSON in skill taxonomy '%s': %s", path, e)
        except Exception as e:
            logger.error("Failed to load skill taxonomy '%s': %s", path, e)

    def normalize(self, skill: Optional[str]) -> Optional[str]:
        """
        Normalize a skill name to its canonical form.

        Returns the canonical name if found in taxonomy,
        otherwise returns the original skill name in title case.
        Returns None for empty/invalid input.
        """
        if not skill or not isinstance(skill, str):
            return None

        cleaned = skill.strip()
        if not cleaned:
            return None

        lower = cleaned.lower()

        # Check alias map
        if lower in self._alias_map:
            return self._alias_map[lower]

        # Not in taxonomy — return as-is with reasonable casing
        return cleaned

    def normalize_list(self, skills: Optional[List[str]]) -> List[str]:
        """Normalize a list of skills, removing duplicates after normalization."""
        if not skills:
            return []

        seen: set = set()
        result: List[str] = []
        for skill in skills:
            normalized = self.normalize(skill)
            if normalized and normalized.lower() not in seen:
                seen.add(normalized.lower())
                result.append(normalized)
        return result

    def is_known_skill(self, skill: Optional[str]) -> bool:
        """Check if a skill is in the taxonomy."""
        if not skill:
            return False
        return skill.strip().lower() in self._alias_map

    def get_canonical_skills(self) -> List[str]:
        """Return all canonical skill names."""
        return sorted(
            {self._alias_map[k] for k in self._canonical_set if k in self._alias_map}
        )
