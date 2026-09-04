"""Unit tests for the industry-grade ATS scoring engine."""

import pytest

from app.services.ats import (
    _canonicalize,
    _compute_education_match,
    _compute_experience_alignment,
    _compute_impact_quality,
    _compute_keyword_match,
    _compute_semantic_similarity,
    _compute_skills_coverage,
    _interpretation,
    _term_in_text,
    _total_experience_years,
    compute_ats_score,
)


@pytest.fixture
def resume():
    return {
        "personalInfo": {
            "name": "Jane Doe",
            "title": "Senior Software Engineer",
            "email": "jane@example.com",
            "phone": "+1 555 0100",
            "location": "Berlin",
        },
        "summary": "Senior engineer with 6 years building scalable Python services on Kubernetes.",
        "workExperience": [
            {
                "id": 1,
                "title": "Senior Backend Engineer",
                "company": "Acme",
                "years": "Jan 2021 - Present",
                "description": [
                    "Led migration of 12 microservices to Kubernetes, cutting deploy time by 70%.",
                    "Built data pipelines in Python processing 2M events/day.",
                ],
            },
            {
                "id": 2,
                "title": "Software Engineer",
                "company": "Beta",
                "years": "Jul 2019 - Dec 2020",
                "description": [
                    "Developed REST APIs with Node.js and PostgreSQL serving 500k users.",
                ],
            },
        ],
        "education": [
            {"id": 1, "institution": "TU Berlin", "degree": "MSc Computer Science"}
        ],
        "personalProjects": [],
        "additional": {
            "technicalSkills": ["Python", "Kubernetes", "PostgreSQL", "Node.js", "AWS"]
        },
    }


@pytest.fixture
def job_keywords():
    return {
        "required_skills": ["Python", "Kubernetes", "AWS", "CI/CD"],
        "preferred_skills": ["GraphQL"],
        "keywords": ["microservices", "docker"],
        "key_responsibilities": ["Build scalable microservices"],
        "experience_requirements": ["5+ years"],
        "education_requirements": ["Bachelor's in CS"],
        "experience_years": 5,
        "seniority_level": "senior",
        "role": "Senior Backend Engineer",
    }


# ---------------------------------------------------------------------------
# Term canonicalization / matching
# ---------------------------------------------------------------------------


class TestTermMatching:
    def test_canonicalize_collapses_separators(self):
        assert _canonicalize("Node.JS") == "node js"
        assert _canonicalize("CI/CD") == "ci cd"
        assert _canonicalize("C++") == "c++"

    def test_separator_insensitive_match(self):
        text = _canonicalize("built with NodeJS and node.js")
        assert _term_in_text("node.js", text)
        assert _term_in_text("nodejs", text)

    def test_alias_expansion(self):
        text = _canonicalize("deployed on K8s daily; strong JS skills")
        assert _term_in_text("kubernetes", text)
        assert _term_in_text("javascript", text)

    def test_postgres_matches_postgresql(self):
        assert _term_in_text("postgresql", _canonicalize("ran Postgres clusters"))

    def test_no_false_positive_inside_words(self):
        text = _canonicalize("django developer using mongoexport")
        assert not _term_in_text("go", text)
        assert not _term_in_text("c", _canonicalize("wrote C++ code"))

    def test_plural_tolerance(self):
        assert _term_in_text("microservices", _canonicalize("microservice architecture"))
        assert _term_in_text("microservice", _canonicalize("microservices everywhere"))

    def test_cicd_matches_ci_cd(self):
        assert _term_in_text("CI/CD", _canonicalize("set up CI CD pipelines"))
        assert _term_in_text("ci cd", _canonicalize("configured CI/CD tooling"))


# ---------------------------------------------------------------------------
# Component scores
# ---------------------------------------------------------------------------


class TestKeywordMatch:
    def test_weighted_required_preferred(self, job_keywords):
        text = _canonicalize(
            "Python and Kubernetes and AWS and CI/CD and GraphQL and microservices and docker"
        )
        score, details = _compute_keyword_match(text, job_keywords)
        assert score == 100.0
        assert details["required_skills_missing"] == []
        assert details["preferred_skills_missing"] == []

    def test_partial_coverage_below_half(self, job_keywords):
        text = _canonicalize("only python here")
        score, _ = _compute_keyword_match(text, job_keywords)
        # 1/4 required, 0/1 preferred, 0/2 general -> well below 50
        assert score < 50.0

    def test_required_weighs_more_than_preferred(self):
        jd = {
            "required_skills": ["alpha"],
            "preferred_skills": ["beta", "gamma"],
            "keywords": [],
        }
        text = _canonicalize("alpha only")
        score, _ = _compute_keyword_match(text, jd)
        # required fully covered, preferred 0
        # weight = 0.55 / (0.55 + 0.25) = 0.6875
        assert score == pytest.approx(68.75, abs=0.1)

    def test_empty_keyword_dict_is_neutral(self):
        score, details = _compute_keyword_match("anything", {})
        assert score == 100.0
        assert details["required_skills_matched"] == []


class TestSkillsCoverage:
    def test_skills_section_matching(self, resume, job_keywords):
        score = _compute_skills_coverage(resume, job_keywords)
        # JD skills = required (Python, Kubernetes, AWS, CI/CD) + preferred (GraphQL)
        # = 5; resume skills list contains Python, Kubernetes, AWS -> 3/5
        assert score == pytest.approx(3 / 5 * 100, abs=0.1)

    def test_falls_back_to_text(self, job_keywords):
        resume = {"additional": {}, "summary": "python kubernetes aws postgresql nodejs"}
        score = _compute_skills_coverage(resume, job_keywords)
        # CI/CD and GraphQL absent from the text too -> 3/5
        assert score == pytest.approx(3 / 5 * 100, abs=0.1)


class TestSemanticSimilarity:
    def test_identical_texts_score_high(self, job_keywords):
        jd_text = "python kubernetes microservices scalable pipelines"
        kw = {"required_skills": ["python"], "keywords": ["kubernetes", "microservices"]}
        score = _compute_semantic_similarity(jd_text, kw)
        assert score > 60.0

    def test_unrelated_texts_score_low(self):
        kw = {"required_skills": ["fortran", "cobol"], "keywords": ["mainframe"]}
        score = _compute_semantic_similarity(
            "baking sourdough bread and pastries daily", kw
        )
        assert score < 25.0


class TestExperienceAlignment:
    def test_years_parsed_from_ranges(self, resume):
        # Jan 2021 - now + Jul 2019 - Dec 2020
        years = _total_experience_years(resume)
        assert 5.0 <= years <= 8.0

    def test_meets_requirement(self, resume, job_keywords):
        score, details = _compute_experience_alignment(resume, job_keywords)
        assert score >= 90.0
        assert details["required_experience_years"] == 5

    def test_no_dates_is_penalized(self, job_keywords):
        resume = {
            "workExperience": [
                {"id": 1, "title": "Engineer", "years": "", "description": []}
            ]
        }
        score, _ = _compute_experience_alignment(resume, job_keywords)
        assert score < 70.0

    def test_seniority_alignment(self, job_keywords):
        resume = {
            "workExperience": [
                {"id": 1, "title": "Principal Engineer", "years": "2015 - Present"}
            ]
        }
        score, _ = _compute_experience_alignment(resume, job_keywords)
        assert score >= 85.0


class TestEducationMatch:
    def test_higher_degree_satisfies_bachelors(self, resume, job_keywords):
        score, details = _compute_education_match(resume, job_keywords)
        assert score == 100.0
        assert details["resume_highest_tier"] == 3

    def test_no_education_penalized(self, job_keywords):
        score, _ = _compute_education_match({"education": []}, job_keywords)
        assert score <= 35.0

    def test_no_requirement_is_neutral(self):
        score, _ = _compute_education_match({"education": []}, {})
        assert score == 80.0


class TestImpactQuality:
    def test_quantified_action_bullets_score_well(self, resume):
        score, details = _compute_impact_quality(resume)
        assert score >= 50.0
        assert details["quantified_bullets"] >= 2

    def test_weak_bullets_score_poorly(self):
        resume = {
            "workExperience": [
                {
                    "id": 1,
                    "title": "Dev",
                    "years": "2020 - 2021",
                    "description": ["was responsible for things", "helped out"],
                }
            ]
        }
        score, _ = _compute_impact_quality(resume)
        assert score < 20.0


# ---------------------------------------------------------------------------
# Composite score
# ---------------------------------------------------------------------------


class TestComputeAtsScore:
    def test_full_breakdown_shape(self, resume, job_keywords):
        result = compute_ats_score(resume, job_keywords, 80.0, ["GraphQL"], [])
        assert 0.0 <= result["overall_score"] <= 100.0
        expected_subscores = {
            "keyword_match",
            "skills_coverage",
            "semantic_similarity",
            "experience_alignment",
            "education_match",
            "section_completeness",
            "formatting_quality",
            "impact_quality",
        }
        assert set(result["sub_scores"]) == expected_subscores
        assert "interpretation" in result
        assert "details" in result
        assert "matched_keywords" in result
        assert "GraphQL" in result["missing_keywords"]

    def test_tailored_resume_scores_higher_than_generic(self, job_keywords):
        generic = {
            "personalInfo": {"name": "X", "email": "x@x.com"},
            "summary": "hard working person",
            "workExperience": [
                {"id": 1, "title": "Worker", "years": "2018 - 2020", "description": ["did stuff"]}
            ],
        }
        tailored = {
            "personalInfo": {"name": "X", "email": "x@x.com", "phone": "1"},
            "summary": "Senior engineer: Python, Kubernetes, AWS microservices at scale",
            "workExperience": [
                {
                    "id": 1,
                    "title": "Senior Backend Engineer",
                    "years": "2018 - Present",
                    "description": [
                        "Built 10 microservices on Kubernetes with Python and AWS, cut costs 40%",
                        "Automated CI/CD pipelines accelerating releases 5x",
                    ],
                }
            ],
            "education": [{"id": 1, "institution": "MIT", "degree": "BSc CS"}],
            "additional": {"technicalSkills": ["Python", "Kubernetes", "AWS", "Docker"]},
        }
        weak = compute_ats_score(generic, job_keywords)
        strong = compute_ats_score(tailored, job_keywords)
        assert strong["overall_score"] > weak["overall_score"] + 15

    def test_empty_resume_does_not_crash(self, job_keywords):
        result = compute_ats_score({}, job_keywords)
        assert result["overall_score"] >= 0.0
        assert result["interpretation"] in {"poor", "weak"}

    def test_empty_job_keywords_does_not_crash(self, resume):
        result = compute_ats_score(resume, {}, None, [], [])
        assert result["overall_score"] >= 0.0

    def test_recommendations_mention_missing_required(self, resume, job_keywords):
        result = compute_ats_score(resume, job_keywords, 50.0, ["GraphQL"], [])
        joined = " ".join(result["recommendations"])
        # GraphQL is preferred-missing, CI/CD required-missing
        assert "GraphQL" in joined or "CI/CD" in joined

    def test_interpretation_bands(self):
        assert _interpretation(90) == "excellent"
        assert _interpretation(75) == "strong"
        assert _interpretation(60) == "moderate"
        assert _interpretation(45) == "weak"
        assert _interpretation(10) == "poor"
