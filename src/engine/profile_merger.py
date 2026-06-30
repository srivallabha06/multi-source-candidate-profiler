"""
Profile merger.

Merges multiple RawCandidateRecords within a cluster into
a single CanonicalProfile. Handles union for lists, conflict
resolution for scalars, and provenance tracking for everything.
"""

from __future__ import annotations

import logging
import hashlib
import uuid
from typing import Any, Dict, List, Optional, Set

from src.models.candidate import (
    CanonicalProfile,
    Education,
    Experience,
    Links,
    Location,
    RawCandidateRecord,
    Skill,
)
from src.models.provenance import ProvenanceStore
from src.engine.conflict_resolver import ConflictResolver
from src.engine.entity_resolution import CandidateCluster
from src.normalizers.name import NameNormalizer
from src.normalizers.phone import PhoneNormalizer
from src.normalizers.country import CountryNormalizer
from src.normalizers.skill import SkillNormalizer
from src.normalizers.date import DateNormalizer
from src.normalizers.url import URLNormalizer

logger = logging.getLogger(__name__)


class ProfileMerger:
    """
    Merges records within each cluster into a CanonicalProfile.

    Strategies:
    - Lists (emails, phones, skills): union with dedup.
    - Scalars (name, headline, years_experience): conflict resolution.
    - Nested lists (experience, education): union by key similarity.
    - All values get provenance records.
    """

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        provenance_store: Optional[ProvenanceStore] = None,
        skill_normalizer: Optional[SkillNormalizer] = None,
    ) -> None:
        self._config = config or {}
        self._provenance = provenance_store if provenance_store is not None else ProvenanceStore()
        self._conflict_resolver = ConflictResolver(config)
        self._name_normalizer = NameNormalizer()
        self._phone_normalizer = PhoneNormalizer(
            default_region=self._config.get("pipeline", {}).get(
                "default_phone_region", "IN"
            )
        )
        self._country_normalizer = CountryNormalizer()
        self._skill_normalizer = skill_normalizer or SkillNormalizer()
        self._date_normalizer = DateNormalizer()
        self._url_normalizer = URLNormalizer()

    @property
    def provenance_store(self) -> ProvenanceStore:
        return self._provenance

    def merge_clusters(
        self,
        clusters: List[CandidateCluster],
        record_map: Dict[str, RawCandidateRecord],
    ) -> List[CanonicalProfile]:
        """Merge all clusters into canonical profiles."""
        profiles = []
        for cluster in clusters:
            records = [
                record_map[rid]
                for rid in cluster.record_ids
                if rid in record_map
            ]
            if records:
                profile = self._merge_records(records, cluster)
                profiles.append(profile)
        return profiles

    def _generate_stable_id(self, records: List[RawCandidateRecord]) -> str:
        """Generate a deterministic stable candidate ID based on unique identifiers."""
        identifiers = set()
        names = set()

        for r in records:
            data = r.data
            if not data:
                continue

            # Emails
            for email in data.get("emails", []):
                if email and isinstance(email, str):
                    cleaned = email.strip().lower()
                    if cleaned:
                        identifiers.add(f"email:{cleaned}")

            # Phones
            for phone in data.get("phones", []):
                if phone and isinstance(phone, str):
                    cleaned = "".join(filter(str.isdigit, phone))
                    if cleaned:
                        identifiers.add(f"phone:{cleaned}")

            # Links
            links = data.get("links", {})
            if isinstance(links, dict):
                for k in ["linkedin", "github"]:
                    val = links.get(k)
                    if val and isinstance(val, str):
                        cleaned = val.strip().lower()
                        if cleaned:
                            identifiers.add(f"{k}:{cleaned}")

            # Names (fallback)
            name = data.get("full_name")
            if name and isinstance(name, str):
                cleaned = name.strip().lower()
                if cleaned:
                    names.add(cleaned)

        if identifiers:
            sorted_ids = sorted(list(identifiers))
            seed = "|".join(sorted_ids)
        elif names:
            seed = "name:" + "|".join(sorted(list(names)))
        else:
            return str(uuid.uuid4())

        return str(uuid.uuid5(uuid.NAMESPACE_DNS, seed))

    def _merge_records(
        self,
        records: List[RawCandidateRecord],
        cluster: CandidateCluster,
    ) -> CanonicalProfile:
        """Merge a list of records into a single CanonicalProfile."""
        profile = CanonicalProfile()
        profile.candidate_id = self._generate_stable_id(records)
        profile.merged_from = [r.record_id for r in records]

        cid = profile.candidate_id

        # --- Name ---
        names = []
        for r in records:
            name = r.data.get("full_name")
            if name:
                normalized = self._name_normalizer.normalize(name)
                if normalized:
                    names.append((normalized, r.source_type, r.source_path))
        if names:
            chosen_name, source, source_path = self._conflict_resolver.resolve_scalar(
                "full_name", names
            )
            profile.full_name = chosen_name
            self._provenance.add_field(
                cid, "full_name", chosen_name, source, source_path,
                method="conflict_resolution" if len(names) > 1 else "direct_assertion",
                confidence=0.95,
            )

        # --- Emails ---
        seen_emails: Set[str] = set()
        for r in records:
            for email in r.data.get("emails", []):
                if isinstance(email, str) and email.strip():
                    email_lower = email.strip().lower()
                    if email_lower not in seen_emails:
                        seen_emails.add(email_lower)
                        profile.emails.append(email_lower)
                        self._provenance.add_field(
                            cid, "emails", email_lower, r.source_type,
                            r.source_path, confidence=0.95,
                        )

        # --- Phones ---
        seen_phones: Set[str] = set()
        for r in records:
            for phone in r.data.get("phones", []):
                if isinstance(phone, str) and phone.strip():
                    normalized = self._phone_normalizer.normalize(phone)
                    if normalized and normalized not in seen_phones:
                        seen_phones.add(normalized)
                        profile.phones.append(normalized)
                        self._provenance.add_field(
                            cid, "phones", normalized, r.source_type,
                            r.source_path, confidence=0.90,
                        )

        # --- Location ---
        locations = []
        for r in records:
            loc = r.data.get("location")
            if isinstance(loc, dict):
                city = loc.get("city")
                region = loc.get("region")
                country = loc.get("country")
                if city or region or country:
                    # Normalize country
                    norm_country = self._country_normalizer.normalize(country) if country else None
                    locations.append((
                        Location(
                            city=city.strip().title() if city else None,
                            region=region.strip().title() if region else None,
                            country=norm_country,
                        ),
                        r.source_type,
                        r.source_path,
                    ))
        if locations:
            chosen_loc, source, source_path = self._conflict_resolver.resolve_scalar(
                "location",
                [(loc.to_dict(), src, sp) for loc, src, sp in locations],
            )
            if isinstance(chosen_loc, dict):
                profile.location = Location.from_dict(chosen_loc)
            else:
                profile.location = locations[0][0]
            self._provenance.add_field(
                cid, "location", profile.location.to_dict() if profile.location else None,
                source, source_path, confidence=0.85,
            )

        # --- Links ---
        linkedin = None
        github = None
        portfolio = None
        other_links: List[str] = []

        for r in records:
            links = r.data.get("links", {})
            if not isinstance(links, dict):
                continue

            li = links.get("linkedin")
            if li and not linkedin:
                linkedin = self._url_normalizer.normalize(li)
                if linkedin:
                    self._provenance.add_field(
                        cid, "links.linkedin", linkedin, r.source_type,
                        r.source_path, confidence=0.95,
                    )

            gh = links.get("github")
            if gh and not github:
                github = self._url_normalizer.normalize(gh)
                if github:
                    self._provenance.add_field(
                        cid, "links.github", github, r.source_type,
                        r.source_path, confidence=0.95,
                    )

            pf = links.get("portfolio")
            if pf and not portfolio:
                portfolio = self._url_normalizer.normalize(pf)
                if portfolio:
                    self._provenance.add_field(
                        cid, "links.portfolio", portfolio, r.source_type,
                        r.source_path, confidence=0.85,
                    )

            for other in links.get("other", []):
                norm_other = self._url_normalizer.normalize(other)
                if norm_other and norm_other not in other_links:
                    other_links.append(norm_other)

        profile.links = Links(
            linkedin=linkedin,
            github=github,
            portfolio=portfolio,
            other=other_links,
        )

        # --- Headline ---
        headlines = []
        for r in records:
            headline = r.data.get("headline")
            if headline and isinstance(headline, str) and headline.strip():
                headlines.append((headline.strip(), r.source_type, r.source_path))
        if headlines:
            chosen, source, source_path = self._conflict_resolver.resolve_scalar(
                "headline", headlines
            )
            profile.headline = chosen
            self._provenance.add_field(
                cid, "headline", chosen, source, source_path,
                confidence=0.85,
            )

        # --- Years Experience ---
        yoe_values = []
        for r in records:
            yoe = r.data.get("years_experience")
            if yoe is not None:
                try:
                    yoe_values.append((float(yoe), r.source_type, r.source_path))
                except (ValueError, TypeError):
                    pass
        if yoe_values:
            chosen, source, source_path = self._conflict_resolver.resolve_scalar(
                "years_experience", yoe_values
            )
            profile.years_experience = chosen
            self._provenance.add_field(
                cid, "years_experience", chosen, source, source_path,
                method="conflict_resolution" if len(yoe_values) > 1 else "direct_assertion",
                confidence=0.80,
            )

        # --- Skills ---
        skill_map: Dict[str, Skill] = {}  # canonical_name -> Skill
        for r in records:
            source_confidence = self._get_source_confidence(r.source_type)
            skills_raw = r.data.get("skills", [])
            if not isinstance(skills_raw, list):
                continue
            for skill_name in skills_raw:
                if not isinstance(skill_name, str) or not skill_name.strip():
                    continue
                canonical = self._skill_normalizer.normalize(skill_name)
                if not canonical:
                    continue
                canonical_lower = canonical.lower()
                if canonical_lower in skill_map:
                    existing = skill_map[canonical_lower]
                    if r.source_type not in existing.sources:
                        existing.sources.append(r.source_type)
                    existing.confidence = max(
                        existing.confidence, source_confidence
                    )
                else:
                    skill_map[canonical_lower] = Skill(
                        name=canonical,
                        confidence=source_confidence,
                        sources=[r.source_type],
                    )
                self._provenance.add_field(
                    cid, f"skills.{canonical}", canonical,
                    r.source_type, r.source_path,
                    method=self._get_skill_method(r.source_type),
                    confidence=source_confidence,
                )

        profile.skills = sorted(
            skill_map.values(), key=lambda s: s.confidence, reverse=True
        )

        # --- Experience ---
        experience_entries: List[Experience] = []
        seen_exp_keys: Set[str] = set()
        for r in records:
            for exp_data in r.data.get("experience", []):
                if not isinstance(exp_data, dict):
                    continue
                exp = Experience(
                    company=exp_data.get("company"),
                    title=exp_data.get("title"),
                    start_date=self._date_normalizer.normalize(
                        exp_data.get("start_date")
                    ),
                    end_date=self._date_normalizer.normalize(
                        exp_data.get("end_date")
                    ),
                    description=exp_data.get("description"),
                    source=r.source_type,
                )
                # Dedup by (company, title) key
                exp_key = f"{(exp.company or '').lower()}|{(exp.title or '').lower()}"
                if exp_key not in seen_exp_keys:
                    seen_exp_keys.add(exp_key)
                    experience_entries.append(exp)
                    self._provenance.add_field(
                        cid, f"experience.{exp.company or 'unknown'}",
                        exp.to_dict(), r.source_type, r.source_path,
                        confidence=0.85,
                    )
        profile.experience = experience_entries

        # --- Education ---
        education_entries: List[Education] = []
        seen_edu_keys: Set[str] = set()
        for r in records:
            for edu_data in r.data.get("education", []):
                if not isinstance(edu_data, dict):
                    continue
                edu = Education(
                    institution=edu_data.get("institution") or edu_data.get("school"),
                    degree=edu_data.get("degree"),
                    field_of_study=edu_data.get("field_of_study") or edu_data.get("major"),
                    start_date=self._date_normalizer.normalize(
                        edu_data.get("start_date")
                    ),
                    end_date=self._date_normalizer.normalize(
                        edu_data.get("end_date")
                    ),
                    source=r.source_type,
                )
                edu_key = f"{(edu.institution or '').lower()}|{(edu.degree or '').lower()}"
                if edu_key not in seen_edu_keys:
                    seen_edu_keys.add(edu_key)
                    education_entries.append(edu)
                    self._provenance.add_field(
                        cid, f"education.{edu.institution or 'unknown'}",
                        edu.to_dict(), r.source_type, r.source_path,
                        confidence=0.90,
                    )
        profile.education = education_entries

        return profile

    def _get_source_confidence(self, source_type: str) -> float:
        """Get base confidence score for a source type."""
        confidence_map = self._config.get("confidence", {}).get(
            "source_base_scores", {}
        )
        return confidence_map.get(source_type, 0.50)

    def _get_skill_method(self, source_type: str) -> str:
        """Determine the method used to extract a skill based on source type."""
        method_map = {
            "resume_json": "direct_assertion",
            "linkedin_json": "direct_assertion",
            "github": "repo_language_analysis",
            "pdf": "keyword_extraction",
            "portfolio_web": "keyword_extraction",
            "ats_csv": "direct_assertion",
            "ats_json": "direct_assertion",
            "hr_system": "direct_assertion",
        }
        return method_map.get(source_type, "inferred")
