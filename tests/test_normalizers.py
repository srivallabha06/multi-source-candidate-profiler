"""
Unit tests for all normalizers.

Tests cover all the normalization edge cases from the spec:
names, phones, countries, skills, dates, and URLs.
"""

import os
import sys
import pytest

# Ensure project root is on path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.normalizers.name import NameNormalizer
from src.normalizers.phone import PhoneNormalizer
from src.normalizers.country import CountryNormalizer
from src.normalizers.skill import SkillNormalizer
from src.normalizers.date import DateNormalizer
from src.normalizers.url import URLNormalizer


# ==================== Name Normalizer Tests ====================

class TestNameNormalizer:
    def setup_method(self):
        self.normalizer = NameNormalizer()

    def test_lowercase_to_title_case(self):
        assert self.normalizer.normalize("rahul sharma") == "Rahul Sharma"

    def test_uppercase_to_title_case(self):
        assert self.normalizer.normalize("RAHUL SHARMA") == "Rahul Sharma"

    def test_mixed_case(self):
        assert self.normalizer.normalize("Rahul Sharma") == "Rahul Sharma"

    def test_preserves_initial(self):
        """Initials must NOT be expanded."""
        assert self.normalizer.normalize("Rahul K Sharma") == "Rahul K Sharma"

    def test_initial_with_period(self):
        assert self.normalizer.normalize("Rahul K. Sharma") == "Rahul K. Sharma"

    def test_strips_extra_whitespace(self):
        assert self.normalizer.normalize("  rahul   sharma  ") == "Rahul Sharma"

    def test_none_input(self):
        assert self.normalizer.normalize(None) is None

    def test_empty_string(self):
        assert self.normalizer.normalize("") is None

    def test_whitespace_only(self):
        assert self.normalizer.normalize("   ") is None

    def test_single_name(self):
        assert self.normalizer.normalize("rahul") == "Rahul"

    def test_removes_honorifics(self):
        assert self.normalizer.normalize("Mr. Rahul Sharma") == "Rahul Sharma"
        assert self.normalizer.normalize("Dr. Priya Patel") == "Priya Patel"
        assert self.normalizer.normalize("Prof. John Doe, PhD") == "John Doe"

    def test_removes_punctuation(self):
        assert self.normalizer.normalize("Rahul - Sharma") == "Rahul Sharma"
        assert self.normalizer.normalize("Dahagam, Srivallabha") == "Dahagam Srivallabha"

    def test_similarity_same_name(self):
        score = self.normalizer.similarity("Rahul Sharma", "Rahul Sharma")
        assert score == 1.0

    def test_similarity_case_insensitive(self):
        score = self.normalizer.similarity("rahul sharma", "RAHUL SHARMA")
        assert score == 1.0

    def test_similarity_with_middle_name(self):
        score = self.normalizer.similarity("Rahul Sharma", "Rahul K Sharma")
        assert score > 0.7  # High similarity despite extra initial

    def test_similarity_nickname(self):
        """Bob should match Robert via nickname mapping."""
        score = self.normalizer.similarity("Bob Smith", "Robert Smith")
        assert score > 0.7

    def test_similarity_transliteration(self):
        """Mohammed should match Muhammad."""
        score = self.normalizer.similarity("Mohammed Ali", "Muhammad Ali")
        assert score > 0.7

    def test_similarity_different_people(self):
        score = self.normalizer.similarity("Rahul Sharma", "Priya Patel")
        assert score < 0.5

    def test_are_compatible_same(self):
        is_compat, score = self.normalizer.are_compatible(
            "Rahul Sharma", "Rahul Sharma"
        )
        assert is_compat is True

    def test_are_compatible_different(self):
        is_compat, score = self.normalizer.are_compatible(
            "Rahul Sharma", "Priya Patel"
        )
        assert is_compat is False


# ==================== Phone Normalizer Tests ====================

class TestPhoneNormalizer:
    def setup_method(self):
        self.normalizer = PhoneNormalizer(default_region="IN")

    def test_bare_number(self):
        """9876543210 -> +919876543210"""
        result = self.normalizer.normalize("9876543210")
        assert result == "+919876543210"

    def test_with_plus_country_code(self):
        """+91 9876543210 -> +919876543210"""
        result = self.normalizer.normalize("+91 9876543210")
        assert result == "+919876543210"

    def test_with_dashes(self):
        """91-9876543210 -> +919876543210"""
        result = self.normalizer.normalize("91-9876543210")
        assert result == "+919876543210"

    def test_none_input(self):
        assert self.normalizer.normalize(None) is None

    def test_empty_string(self):
        assert self.normalizer.normalize("") is None

    def test_invalid_input(self):
        result = self.normalizer.normalize("not-a-phone")
        assert result is None

    def test_us_phone(self):
        normalizer = PhoneNormalizer(default_region="US")
        result = normalizer.normalize("(555) 123-4567")
        assert result is not None
        assert result.startswith("+1")


# ==================== Country Normalizer Tests ====================

class TestCountryNormalizer:
    def setup_method(self):
        self.normalizer = CountryNormalizer()

    def test_full_name(self):
        assert self.normalizer.normalize("India") == "IN"

    def test_alpha3(self):
        assert self.normalizer.normalize("IND") == "IN"

    def test_official_name(self):
        assert self.normalizer.normalize("Republic of India") == "IN"

    def test_alpha2(self):
        assert self.normalizer.normalize("IN") == "IN"

    def test_usa(self):
        assert self.normalizer.normalize("USA") == "US"

    def test_united_states(self):
        assert self.normalizer.normalize("United States") == "US"

    def test_uk(self):
        assert self.normalizer.normalize("UK") == "GB"

    def test_none_input(self):
        assert self.normalizer.normalize(None) is None

    def test_empty_string(self):
        assert self.normalizer.normalize("") is None

    def test_unknown_country(self):
        assert self.normalizer.normalize("xyznotacountry") is None


# ==================== Skill Normalizer Tests ====================

class TestSkillNormalizer:
    def setup_method(self):
        taxonomy_path = os.path.join(
            project_root, "config", "skill_taxonomy.json"
        )
        self.normalizer = SkillNormalizer(taxonomy_path=taxonomy_path)

    def test_java_uppercase(self):
        assert self.normalizer.normalize("JAVA") == "Java"

    def test_core_java(self):
        assert self.normalizer.normalize("Core Java") == "Java"

    def test_java_se(self):
        assert self.normalizer.normalize("Java SE") == "Java"

    def test_aws_alias(self):
        assert self.normalizer.normalize("Amazon Web Services") == "AWS"

    def test_aws_cloud(self):
        assert self.normalizer.normalize("AWS Cloud") == "AWS"

    def test_unknown_skill(self):
        """Unknown skills should be returned as-is."""
        result = self.normalizer.normalize("UnknownSkillXYZ")
        assert result == "UnknownSkillXYZ"

    def test_none_input(self):
        assert self.normalizer.normalize(None) is None

    def test_empty_string(self):
        assert self.normalizer.normalize("") is None

    def test_normalize_list_dedup(self):
        """Normalizing a list should deduplicate."""
        result = self.normalizer.normalize_list(
            ["Java", "JAVA", "Core Java", "Python"]
        )
        assert "Java" in result
        assert "Python" in result
        # All Java variants should collapse to one
        java_count = sum(1 for s in result if s.lower() == "java")
        assert java_count == 1

    def test_kubernetes_alias(self):
        assert self.normalizer.normalize("K8s") == "Kubernetes"


# ==================== Date Normalizer Tests ====================

class TestDateNormalizer:
    def setup_method(self):
        self.normalizer = DateNormalizer()

    def test_month_name_year(self):
        assert self.normalizer.normalize("Jan 2023") == "2023-01"

    def test_full_month_name(self):
        assert self.normalizer.normalize("January 2023") == "2023-01"

    def test_slash_format(self):
        assert self.normalizer.normalize("01/2023") == "2023-01"

    def test_already_normalized(self):
        assert self.normalizer.normalize("2023-01") == "2023-01"

    def test_year_only(self):
        assert self.normalizer.normalize("2023") == "2023"

    def test_present(self):
        assert self.normalizer.normalize("present") == "present"

    def test_current(self):
        assert self.normalizer.normalize("current") == "present"

    def test_none_input(self):
        assert self.normalizer.normalize(None) is None

    def test_empty_string(self):
        assert self.normalizer.normalize("") is None

    def test_invalid_input(self):
        assert self.normalizer.normalize("not-a-date") is None

    def test_full_date_extracts_month(self):
        result = self.normalizer.normalize("2023-01-15")
        assert result == "2023-01"

    def test_march_2022(self):
        assert self.normalizer.normalize("March 2022") == "2022-03"

    def test_dash_format(self):
        assert self.normalizer.normalize("06-2018") == "2018-06"


# ==================== URL Normalizer Tests ====================

class TestURLNormalizer:
    def setup_method(self):
        self.normalizer = URLNormalizer()

    def test_linkedin_trailing_slash(self):
        result = self.normalizer.normalize(
            "https://www.linkedin.com/in/rahul-sharma/"
        )
        assert result == "https://linkedin.com/in/rahul-sharma"

    def test_github_trailing_slash(self):
        result = self.normalizer.normalize(
            "http://github.com/rahul-sharma/"
        )
        assert result == "https://github.com/rahul-sharma"

    def test_github_no_scheme(self):
        result = self.normalizer.normalize("github.com/rahul-sharma")
        assert result == "https://github.com/rahul-sharma"

    def test_portfolio_strips_query(self):
        result = self.normalizer.normalize(
            "https://rahuldev.com/portfolio?ref=google"
        )
        assert "ref=google" not in result

    def test_none_input(self):
        assert self.normalizer.normalize(None) is None

    def test_empty_string(self):
        assert self.normalizer.normalize("") is None

    def test_extract_linkedin_username(self):
        result = self.normalizer.extract_linkedin_username(
            "https://linkedin.com/in/rahul-sharma"
        )
        assert result == "rahul-sharma"

    def test_extract_github_username(self):
        result = self.normalizer.extract_github_username(
            "https://github.com/rahul-sharma"
        )
        assert result == "rahul-sharma"

    def test_classify_linkedin(self):
        category, url = self.normalizer.classify_url(
            "https://linkedin.com/in/test"
        )
        assert category == "linkedin"

    def test_classify_github(self):
        category, url = self.normalizer.classify_url(
            "https://github.com/test"
        )
        assert category == "github"
