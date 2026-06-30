"""
Canonical data models for the candidate profile system.

All models use dataclasses with optional fields and sensible defaults.
Every field is nullable to handle missing data gracefully.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Location:
    """Normalized geographic location."""
    city: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None  # ISO-3166 Alpha-2

    def to_dict(self) -> Dict[str, Any]:
        return {"city": self.city, "region": self.region, "country": self.country}

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> Optional["Location"]:
        if not data:
            return None
        return cls(
            city=data.get("city"),
            region=data.get("region"),
            country=data.get("country"),
        )


@dataclass
class Links:
    """Normalized profile links."""
    linkedin: Optional[str] = None
    github: Optional[str] = None
    portfolio: Optional[str] = None
    other: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "linkedin": self.linkedin,
            "github": self.github,
            "portfolio": self.portfolio,
            "other": list(self.other),
        }

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> Optional["Links"]:
        if not data:
            return None
        return cls(
            linkedin=data.get("linkedin"),
            github=data.get("github"),
            portfolio=data.get("portfolio"),
            other=data.get("other", []),
        )


@dataclass
class Skill:
    """A normalized skill with confidence and source tracking."""
    name: str = ""
    confidence: float = 0.0
    sources: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "confidence": self.confidence,
            "sources": list(self.sources),
        }

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> Optional["Skill"]:
        if not data:
            return None
        return cls(
            name=data.get("name", ""),
            confidence=data.get("confidence", 0.0),
            sources=data.get("sources", []),
        )


@dataclass
class Experience:
    """A work experience entry."""
    company: Optional[str] = None
    title: Optional[str] = None
    start_date: Optional[str] = None  # YYYY-MM
    end_date: Optional[str] = None  # YYYY-MM or "present"
    description: Optional[str] = None
    location: Optional[Location] = None
    source: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "company": self.company,
            "title": self.title,
            "start": self.start_date,
            "end": self.end_date,
            "summary": self.description,
        }

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> Optional["Experience"]:
        if not data:
            return None
        return cls(
            company=data.get("company"),
            title=data.get("title"),
            start_date=data.get("start") or data.get("start_date"),
            end_date=data.get("end") or data.get("end_date"),
            description=data.get("summary") or data.get("description"),
            location=Location.from_dict(data.get("location")),
            source=data.get("source"),
        )


@dataclass
class Education:
    """An education entry."""
    institution: Optional[str] = None
    degree: Optional[str] = None
    field_of_study: Optional[str] = None
    start_date: Optional[str] = None  # YYYY-MM
    end_date: Optional[str] = None  # YYYY-MM
    source: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "institution": self.institution,
            "degree": self.degree,
            "field": self.field_of_study,
            "end_year": self.end_date,
        }

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> Optional["Education"]:
        if not data:
            return None
        return cls(
            institution=data.get("institution"),
            degree=data.get("degree"),
            field_of_study=data.get("field") or data.get("field_of_study"),
            end_date=data.get("end_year") or data.get("end_date"),
            source=data.get("source"),
        )


@dataclass
class CanonicalProfile:
    """
    The canonical candidate profile — internal source of truth.

    Every field is optional to handle partial data. The profile
    accumulates information from multiple sources and tracks
    provenance for every value.
    """
    candidate_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    full_name: Optional[str] = None
    emails: List[str] = field(default_factory=list)
    phones: List[str] = field(default_factory=list)
    location: Optional[Location] = None
    links: Optional[Links] = None
    headline: Optional[str] = None
    years_experience: Optional[float] = None
    skills: List[Skill] = field(default_factory=list)
    experience: List[Experience] = field(default_factory=list)
    education: List[Education] = field(default_factory=list)
    overall_confidence: float = 0.0
    # Source record IDs that were merged into this profile
    merged_from: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "full_name": self.full_name,
            "emails": list(self.emails),
            "phones": list(self.phones),
            "location": self.location.to_dict() if self.location else None,
            "links": self.links.to_dict() if self.links else None,
            "headline": self.headline,
            "years_experience": self.years_experience,
            "skills": [s.to_dict() for s in self.skills],
            "experience": [e.to_dict() for e in self.experience],
            "education": [e.to_dict() for e in self.education],
            "overall_confidence": self.overall_confidence,
            "merged_from": list(self.merged_from),
        }

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> Optional["CanonicalProfile"]:
        if not data:
            return None
        profile = cls(
            candidate_id=data.get("candidate_id", str(uuid.uuid4())),
            full_name=data.get("full_name"),
            emails=data.get("emails", []),
            phones=data.get("phones", []),
            headline=data.get("headline"),
            years_experience=data.get("years_experience"),
            overall_confidence=data.get("overall_confidence", 0.0),
            merged_from=data.get("merged_from", []),
        )
        profile.location = Location.from_dict(data.get("location"))
        profile.links = Links.from_dict(data.get("links"))
        profile.skills = [
            Skill.from_dict(s) for s in data.get("skills", []) if s
        ]
        profile.experience = [
            Experience.from_dict(e) for e in data.get("experience", []) if e
        ]
        profile.education = [
            Education.from_dict(e) for e in data.get("education", []) if e
        ]
        return profile


@dataclass
class RawCandidateRecord:
    """
    A raw, un-normalized record from a single source.

    This is the output of an adapter before normalization.
    The `data` dict contains source-specific fields.
    """
    record_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source_type: str = ""  # e.g., "resume_json", "linkedin_json", "github"
    source_path: str = ""  # file path or URL
    data: Dict[str, Any] = field(default_factory=dict)
    ingested_at: Optional[str] = None  # ISO timestamp

    def get(self, key: str, default: Any = None) -> Any:
        """Convenience accessor for nested data."""
        return self.data.get(key, default)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "record_id": self.record_id,
            "source_type": self.source_type,
            "source_path": self.source_path,
            "data": self.data,
            "ingested_at": self.ingested_at,
        }
