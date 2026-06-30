"""
Entity resolution engine.

Determines which raw records belong to the same candidate
using index-based blocking and weighted signal matching.

Key design decisions:
- NEVER merge on name alone.
- Uses strong signals (email, phone, LinkedIn, GitHub) for blocking.
- Weighted scoring produces explainable match decisions.
- Configurable merge threshold.
- O(n) average via indexing (avoids O(n²)).
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from src.models.candidate import RawCandidateRecord
from src.normalizers.name import NameNormalizer
from src.normalizers.phone import PhoneNormalizer
from src.normalizers.url import URLNormalizer

logger = logging.getLogger(__name__)


@dataclass
class MatchSignal:
    """A single signal contributing to a match decision."""
    signal_type: str  # e.g., "email_match", "name_similarity"
    weight: float  # contribution to total score
    is_strong: bool  # whether this is a strong identity signal
    details: str = ""  # human-readable explanation

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signal_type": self.signal_type,
            "weight": self.weight,
            "is_strong": self.is_strong,
            "details": self.details,
        }


@dataclass
class MatchResult:
    """The result of comparing two records."""
    record_a_id: str
    record_b_id: str
    total_score: float
    signals: List[MatchSignal] = field(default_factory=list)
    is_match: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "record_a_id": self.record_a_id,
            "record_b_id": self.record_b_id,
            "total_score": self.total_score,
            "signals": [s.to_dict() for s in self.signals],
            "is_match": self.is_match,
        }


@dataclass
class CandidateCluster:
    """A group of records believed to belong to the same candidate."""
    cluster_id: str
    record_ids: List[str] = field(default_factory=list)
    match_results: List[MatchResult] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cluster_id": self.cluster_id,
            "record_ids": self.record_ids,
            "match_results": [m.to_dict() for m in self.match_results],
        }


class EntityResolutionEngine:
    """
    Resolves which raw records belong to the same candidate.

    Algorithm:
    1. Build indexes on strong signals (email, phone, LinkedIn, GitHub).
    2. Generate candidate pairs from index collisions.
    3. Score each pair using weighted signals.
    4. Apply merge threshold and strong-signal requirement.
    5. Build clusters using union-find.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self._config = config or {}
        er_config = self._config.get("entity_resolution", {})

        self._merge_threshold = er_config.get("merge_threshold", 80)
        self._require_strong = er_config.get(
            "require_strong_signal_for_merge", True
        )
        self._weights = er_config.get("weights", {
            "email_match": 100,
            "phone_match": 80,
            "linkedin_match": 100,
            "github_match": 100,
            "name_similarity": 30,
            "location_match": 10,
            "company_overlap": 20,
            "education_overlap": 15,
            "skill_overlap": 10,
        })
        self._name_threshold = er_config.get("name_similarity_threshold", 0.85)
        self._skill_overlap_threshold = er_config.get(
            "skill_overlap_threshold", 0.50
        )

        self._name_normalizer = NameNormalizer()
        self._phone_normalizer = PhoneNormalizer(
            default_region=self._config.get("pipeline", {}).get(
                "default_phone_region", "IN"
            )
        )
        self._url_normalizer = URLNormalizer()

    def resolve(
        self, records: List[RawCandidateRecord]
    ) -> List[CandidateCluster]:
        """
        Resolve identity across all records.

        Returns a list of CandidateCluster objects, each containing
        record IDs that belong to the same candidate.
        """
        if not records:
            return []

        logger.info("Starting entity resolution for %d records", len(records))

        # Step 1: Build indexes
        indexes = self._build_indexes(records)
        record_map = {r.record_id: r for r in records}

        # Step 2: Generate candidate pairs from index collisions
        candidate_pairs = self._generate_pairs(indexes, records)
        logger.info("Generated %d candidate pairs", len(candidate_pairs))

        # Step 3: Score each pair
        match_results: List[MatchResult] = []
        for id_a, id_b in candidate_pairs:
            result = self._score_pair(record_map[id_a], record_map[id_b])
            if result.is_match:
                match_results.append(result)

        logger.info("Found %d matches", len(match_results))

        # Step 4: Build clusters using union-find
        clusters = self._build_clusters(records, match_results)
        logger.info("Resolved into %d clusters", len(clusters))

        return clusters

    def _build_indexes(
        self, records: List[RawCandidateRecord]
    ) -> Dict[str, Dict[str, List[str]]]:
        """
        Build blocking indexes for efficient pair generation.

        Returns:
            {index_name: {key: [record_ids]}}
        """
        indexes: Dict[str, Dict[str, List[str]]] = {
            "email": defaultdict(list),
            "phone": defaultdict(list),
            "linkedin": defaultdict(list),
            "github": defaultdict(list),
        }

        for record in records:
            data = record.data
            rid = record.record_id

            # Email index
            emails = data.get("emails", [])
            if isinstance(emails, str):
                emails = [emails]
            for email in emails:
                if email and isinstance(email, str):
                    key = email.strip().lower()
                    if key:
                        indexes["email"][key].append(rid)

            # Phone index (normalize first)
            phones = data.get("phones", [])
            if isinstance(phones, str):
                phones = [phones]
            for phone in phones:
                if phone and isinstance(phone, str):
                    normalized = self._phone_normalizer.normalize(phone)
                    if normalized:
                        indexes["phone"][normalized].append(rid)

            # LinkedIn index
            links = data.get("links", {})
            if isinstance(links, dict):
                linkedin = links.get("linkedin")
                if linkedin:
                    username = self._url_normalizer.extract_linkedin_username(
                        linkedin
                    )
                    if username:
                        indexes["linkedin"][username.lower()].append(rid)

                # GitHub index
                github = links.get("github")
                if github:
                    username = self._url_normalizer.extract_github_username(
                        github
                    )
                    if username:
                        indexes["github"][username.lower()].append(rid)

        return indexes

    def _generate_pairs(
        self,
        indexes: Dict[str, Dict[str, List[str]]],
        records: List[RawCandidateRecord],
    ) -> Set[Tuple[str, str]]:
        """
        Generate candidate pairs from index collisions.

        Produces pairs where at least one strong signal matches.
        Uses set to avoid duplicates.
        """
        pairs: Set[Tuple[str, str]] = set()

        for index_name, index in indexes.items():
            for key, record_ids in index.items():
                if len(record_ids) < 2:
                    continue
                # Generate all pairs within this bucket
                for i in range(len(record_ids)):
                    for j in range(i + 1, len(record_ids)):
                        pair = tuple(sorted([record_ids[i], record_ids[j]]))
                        pairs.add(pair)

        return pairs

    def _score_pair(
        self,
        record_a: RawCandidateRecord,
        record_b: RawCandidateRecord,
    ) -> MatchResult:
        """
        Score a candidate pair using weighted signals.

        Returns a MatchResult with detailed signal breakdown.
        """
        signals: List[MatchSignal] = []
        data_a = record_a.data
        data_b = record_b.data

        # --- Strong Signals ---

        # Email match
        emails_a = set(
            e.strip().lower()
            for e in (data_a.get("emails") or [])
            if isinstance(e, str) and e.strip()
        )
        emails_b = set(
            e.strip().lower()
            for e in (data_b.get("emails") or [])
            if isinstance(e, str) and e.strip()
        )
        common_emails = emails_a & emails_b
        if common_emails:
            signals.append(MatchSignal(
                signal_type="email_match",
                weight=self._weights.get("email_match", 100),
                is_strong=True,
                details=f"Matching emails: {', '.join(common_emails)}",
            ))

        # Phone match
        phones_a = set()
        for p in data_a.get("phones") or []:
            norm = self._phone_normalizer.normalize(p)
            if norm:
                phones_a.add(norm)
        phones_b = set()
        for p in data_b.get("phones") or []:
            norm = self._phone_normalizer.normalize(p)
            if norm:
                phones_b.add(norm)
        common_phones = phones_a & phones_b
        if common_phones:
            signals.append(MatchSignal(
                signal_type="phone_match",
                weight=self._weights.get("phone_match", 80),
                is_strong=True,
                details=f"Matching phones: {', '.join(common_phones)}",
            ))

        # LinkedIn match
        li_a = self._get_linkedin_username(data_a)
        li_b = self._get_linkedin_username(data_b)
        if li_a and li_b and li_a == li_b:
            signals.append(MatchSignal(
                signal_type="linkedin_match",
                weight=self._weights.get("linkedin_match", 100),
                is_strong=True,
                details=f"Matching LinkedIn: {li_a}",
            ))

        # GitHub match
        gh_a = self._get_github_username(data_a)
        gh_b = self._get_github_username(data_b)
        if gh_a and gh_b and gh_a == gh_b:
            signals.append(MatchSignal(
                signal_type="github_match",
                weight=self._weights.get("github_match", 100),
                is_strong=True,
                details=f"Matching GitHub: {gh_a}",
            ))

        # --- Weak Signals ---

        # Name similarity
        name_a = data_a.get("full_name")
        name_b = data_b.get("full_name")
        if name_a and name_b:
            is_compatible, similarity = self._name_normalizer.are_compatible(
                name_a, name_b, self._name_threshold
            )
            if is_compatible:
                signals.append(MatchSignal(
                    signal_type="name_similarity",
                    weight=self._weights.get("name_similarity", 30),
                    is_strong=False,
                    details=f"Name similarity: {similarity:.2f} "
                            f"('{name_a}' vs '{name_b}')",
                ))

        # Location match
        loc_a = data_a.get("location", {})
        loc_b = data_b.get("location", {})
        if isinstance(loc_a, dict) and isinstance(loc_b, dict):
            city_a = (loc_a.get("city") or "").strip().lower()
            city_b = (loc_b.get("city") or "").strip().lower()
            if city_a and city_b and city_a == city_b:
                signals.append(MatchSignal(
                    signal_type="location_match",
                    weight=self._weights.get("location_match", 10),
                    is_strong=False,
                    details=f"Matching city: {city_a}",
                ))

        # Company overlap
        companies_a = self._extract_companies(data_a)
        companies_b = self._extract_companies(data_b)
        common_companies = companies_a & companies_b
        if common_companies:
            signals.append(MatchSignal(
                signal_type="company_overlap",
                weight=self._weights.get("company_overlap", 20),
                is_strong=False,
                details=f"Common companies: {', '.join(common_companies)}",
            ))

        # Education overlap
        edu_a = self._extract_institutions(data_a)
        edu_b = self._extract_institutions(data_b)
        common_edu = edu_a & edu_b
        if common_edu:
            signals.append(MatchSignal(
                signal_type="education_overlap",
                weight=self._weights.get("education_overlap", 15),
                is_strong=False,
                details=f"Common institutions: {', '.join(common_edu)}",
            ))

        # Skill overlap
        skills_a = set(
            s.lower() for s in (data_a.get("skills") or []) if isinstance(s, str)
        )
        skills_b = set(
            s.lower() for s in (data_b.get("skills") or []) if isinstance(s, str)
        )
        if skills_a and skills_b:
            overlap = len(skills_a & skills_b)
            min_skills = min(len(skills_a), len(skills_b))
            if min_skills > 0:
                overlap_ratio = overlap / min_skills
                if overlap_ratio >= self._skill_overlap_threshold:
                    signals.append(MatchSignal(
                        signal_type="skill_overlap",
                        weight=self._weights.get("skill_overlap", 10),
                        is_strong=False,
                        details=f"Skill overlap: {overlap_ratio:.1%} "
                                f"({overlap}/{min_skills})",
                    ))

        # Calculate total score
        total_score = sum(s.weight for s in signals)
        has_strong = any(s.is_strong for s in signals)

        # Determine if it's a match
        is_match = total_score >= self._merge_threshold
        if self._require_strong and not has_strong:
            is_match = False  # Never merge without a strong signal

        result = MatchResult(
            record_a_id=record_a.record_id,
            record_b_id=record_b.record_id,
            total_score=total_score,
            signals=signals,
            is_match=is_match,
        )

        if is_match:
            logger.debug(
                "Match found: %s <-> %s (score=%.1f, signals=%d)",
                record_a.record_id[:8],
                record_b.record_id[:8],
                total_score,
                len(signals),
            )

        return result

    def _build_clusters(
        self,
        records: List[RawCandidateRecord],
        matches: List[MatchResult],
    ) -> List[CandidateCluster]:
        """Build clusters using union-find from match results."""
        # Union-Find
        parent: Dict[str, str] = {r.record_id: r.record_id for r in records}

        def find(x: str) -> str:
            while parent[x] != x:
                parent[x] = parent[parent[x]]  # Path compression
                x = parent[x]
            return x

        def union(a: str, b: str) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        # Union matched records
        match_map: Dict[str, List[MatchResult]] = defaultdict(list)
        for match in matches:
            union(match.record_a_id, match.record_b_id)
            match_map[match.record_a_id].append(match)
            match_map[match.record_b_id].append(match)

        # Build clusters
        clusters_dict: Dict[str, List[str]] = defaultdict(list)
        for record in records:
            root = find(record.record_id)
            clusters_dict[root].append(record.record_id)

        # Create CandidateCluster objects
        clusters = []
        for cluster_id, record_ids in clusters_dict.items():
            # Collect match results for this cluster
            cluster_matches = []
            seen_match_pairs: set = set()
            for rid in record_ids:
                for m in match_map.get(rid, []):
                    pair_key = tuple(sorted([m.record_a_id, m.record_b_id]))
                    if pair_key not in seen_match_pairs:
                        seen_match_pairs.add(pair_key)
                        cluster_matches.append(m)

            clusters.append(CandidateCluster(
                cluster_id=cluster_id,
                record_ids=record_ids,
                match_results=cluster_matches,
            ))

        return clusters

    # --- Helper methods ---

    def _get_linkedin_username(self, data: Dict[str, Any]) -> Optional[str]:
        links = data.get("links", {})
        if isinstance(links, dict):
            linkedin = links.get("linkedin")
            if linkedin:
                username = self._url_normalizer.extract_linkedin_username(linkedin)
                return username.lower() if username else None
        return None

    def _get_github_username(self, data: Dict[str, Any]) -> Optional[str]:
        links = data.get("links", {})
        if isinstance(links, dict):
            github = links.get("github")
            if github:
                username = self._url_normalizer.extract_github_username(github)
                return username.lower() if username else None
        # Also check github_username field (from GitHub adapter)
        gh_user = data.get("github_username")
        return gh_user.lower() if gh_user and isinstance(gh_user, str) else None

    def _extract_companies(self, data: Dict[str, Any]) -> Set[str]:
        companies: Set[str] = set()
        for exp in data.get("experience", []):
            if isinstance(exp, dict):
                company = exp.get("company")
                if company and isinstance(company, str):
                    companies.add(company.strip().lower())
        return companies

    def _extract_institutions(self, data: Dict[str, Any]) -> Set[str]:
        institutions: Set[str] = set()
        for edu in data.get("education", []):
            if isinstance(edu, dict):
                inst = edu.get("institution") or edu.get("school")
                if inst and isinstance(inst, str):
                    institutions.add(inst.strip().lower())
        return institutions
