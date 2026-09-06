"""Standalone ATS scoring engine (no job description required).

Unlike :mod:`app.services.ats` — which scores a resume *against* a job
description — this engine evaluates a resume **in isolation**, the way
commercial ATS parsers (Taleo, iCIMS, Greenhouse ingest) sanity-check a
document before it ever reaches a recruiter:

1. **Parse-ability of contact data** — ATS field-mapping looks for name,
   email, phone, location and professional links; missing fields mean the
   candidate is unreachable in recruiter searches.
2. **Section recognizability** — standard headings (Summary, Experience,
   Education, Skills…) let the parser route content into the right fields.
3. **Formatting hygiene** — date ranges, bullet structure and length sanity;
   multi-column/table artifacts are flagged because they scramble linear
   text extraction.
4. **Impact signals** — quantified achievements and strong action verbs,
   reusing the same recruiter-judgement proxies as the JD-aware engine.
5. **Keyword optimization** — a resume for a real role names concrete tools
   and skills; we measure how many *known* skills appear (alias-aware) and
   penalize keyword stuffing.
6. **Readability** — filler phrases ("responsible for"), first-person
   pronouns, ALL-CAPS abuse and over-long lines all hurt both ATS tokenization
   and the 6-second recruiter skim.

The engine is fully deterministic and local (no LLM calls), so a standalone
check is instant, free and privacy-friendly. It operates directly on the
markdown text extracted from the uploaded PDF — no LLM parsing step needed,
which is what makes the feature truly standalone.

Scoring model (weights sum to 1.0):

====================================  ======  =====================================
Component                             Weight  What it measures
====================================  ======  =====================================
contact_info                          0.20    email / phone / links / location
section_completeness                  0.20    standard headings present
formatting_quality                    0.20    dates, bullets, length, artifacts
impact_quality                        0.20    quantified bullets + action verbs
keyword_optimization                  0.10    concrete skills, no stuffing
readability_structure                 0.10    fillers, pronouns, caps, lines
====================================  ======  =====================================
"""

import logging
import re
from typing import Any

from app.services.ats import (
    _ACTION_VERBS,
    _QUANT_RE,
    _canonicalize,
    _interpretation,
    _term_in_text,
    _word_count,
)

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Weights (must sum to 1.0)
# --------------------------------------------------------------------------
_WEIGHTS = {
    "contact_info": 0.20,
    "section_completeness": 0.20,
    "formatting_quality": 0.20,
    "impact_quality": 0.20,
    "keyword_optimization": 0.10,
    "readability_structure": 0.10,
}

# Known canonical skills probed for the keyword component (alias-aware via
# _term_in_text, so "k8s" counts for "kubernetes" etc.).
_KNOWN_SKILLS: tuple[str, ...] = (
    "python", "javascript", "typescript", "java", "c++", "c#", "go", "rust",
    "sql", "postgresql", "mongodb", "redis", "react", "angular", "vuejs",
    "nodejs", "nextjs", "graphql", "rest api", "microservices", "docker",
    "kubernetes", "terraform", "aws", "google cloud", "microsoft azure",
    "devops", "cicd", "machine learning", "deep learning", "nlp",
    "large language models", "data analysis", "pandas", "spark", "hadoop",
    "tableau", "power bi", "excel", "git", "jenkins", "linux", "bash",
    "html", "css", "figma", "ui", "ux", "agile", "scrum", "jira",
    "selenium", "cypress", "kafka", "elasticsearch", "rabbitmq",
    "flutter", "swift", "kotlin", "android", "ios",
)

# Section heading detection: heading keyword -> canonical section name.
# Matches markdown headings (``## Experience``), ALL-CAPS standalone lines and
# plain Title-Case heading lines (``Professional Summary``) — the latter are
# what PDF text extraction usually produces.
_SECTION_KEYWORDS: dict[str, tuple[str, ...]] = {
    "summary": (
        "summary", "professional summary", "summary of qualifications",
        "objective", "career objective", "profile", "professional profile",
        "about me", "overview", "personal statement",
    ),
    "experience": (
        "experience", "work experience", "professional experience",
        "relevant experience", "industry experience", "employment",
        "employment history", "work history", "career history",
    ),
    "education": (
        "education", "academic background", "academics", "qualifications",
        "education and training", "academic qualifications",
    ),
    "skills": (
        "skills", "technical skills", "key skills", "relevant skills",
        "skills summary", "technologies", "tech stack", "toolkit",
        "competencies", "core competencies", "technical expertise",
        "skills & tools", "skills and tools",
    ),
    "projects": (
        "projects", "personal projects", "side projects", "selected projects",
        "key projects", "academic projects", "portfolio",
    ),
    "certifications": (
        "certifications", "certificates", "licenses", "licenses & certifications",
        "certifications and licenses", "courses", "training",
        "professional development",
    ),
    "achievements": (
        "achievements", "awards", "honors", "honors & awards",
        "accomplishments", "key achievements",
    ),
    "languages": ("languages", "spoken languages", "language skills"),
}

# Flat phrase set (canonicalized) used to recognize plain heading lines.
_ALL_HEADING_PHRASES: frozenset[str] = frozenset(
    _canonicalize(phrase)
    for phrases in _SECTION_KEYWORDS.values()
    for phrase in phrases
)

# Core sections an ATS expects; the rest are bonuses.
_CORE_SECTIONS = ("summary", "experience", "education", "skills")
_BONUS_SECTIONS = ("projects", "certifications", "achievements", "languages")

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(
    r"(?:\+?\d{1,3}[\s.-]?)?(?:\(\d{2,4}\)[\s.-]?)?\d{3}[\s.-]?\d{3,4}(?:[\s.-]?\d{2,4})?"
)
_LINK_RE = re.compile(
    r"(linkedin\.com|github\.com|gitlab\.com|behance\.net|dribbble\.com|"
    r"medium\.com|stackoverflow\.com|[a-z0-9-]+\.(?:com|dev|io|me|net|org))/[^\s]*",
    re.IGNORECASE,
)
# City, ST / City, Country style location in the header region (anchored to
# the start of a line, but tolerant of trailing pipes/URLs after it).
_LOCATION_RE = re.compile(
    r"^\s*[A-Z][A-Za-z .'-]{1,30},\s*(?:[A-Z]{2}\b|[A-Z][A-Za-z .'-]{1,30})",
)
# Date ranges: "Jan 2020 - Present", "03/2019 - 07/2021", "2019 - 2022",
# "Jan 2020 – Present" (en dash) etc.
_DATE_RANGE_RE = re.compile(
    r"(?:(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s*\d{4}"
    r"|\d{1,2}/\d{4}|\d{4})"
    r"\s*(?:-|–|—|to)\s*"
    r"(?:(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s*\d{4}"
    r"|\d{1,2}/\d{4}|\d{4}|present|current|now|date)",
    re.IGNORECASE,
)
_BULLET_MARKERS = ("•", "◦", "‣", "·", "▪")
_FILLER_PHRASES = (
    "responsible for",
    "duties included",
    "in charge of",
    "worked on",
    "helped with",
    "assisted with",
    "tasked with",
    "various tasks",
)
_FIRST_PERSON_RE = re.compile(r"\b(?:I|I'm|I've|my|me|myself)\b")
_ALL_CAPS_WORD_RE = re.compile(r"\b[A-Z]{4,}\b")
_MARKDOWN_TABLE_RE = re.compile(r"^\s*\|.*\|\s*$", re.MULTILINE)
_MARKDOWN_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$", re.MULTILINE)


# --------------------------------------------------------------------------
# Text helpers
# --------------------------------------------------------------------------

def _strip_code_fences(text: str) -> str:
    """Remove markdown code blocks (extraction artifacts) before analysis."""
    return re.sub(r"```.*?```", " ", text, flags=re.DOTALL)


def _iter_heading_lines(text: str) -> list[str]:
    """Return normalized heading-candidate strings.

    Three sources: markdown headings (``## Experience``), ALL-CAPS standalone
    lines (``WORK EXPERIENCE``) and plain short lines that match a known
    section heading phrase (``Professional Summary``) — PDF extraction
    typically loses all styling, so plain lines are the common case.
    """
    headings: list[str] = []
    for match in _MARKDOWN_HEADING_RE.finditer(text):
        headings.append(_canonicalize(match.group(2)))
    for line in text.splitlines():
        stripped = line.strip().rstrip(":").strip()
        if not stripped or len(stripped) > 48 or stripped.startswith("#"):
            continue
        canonical = _canonicalize(stripped)
        if not canonical:
            continue
        letters = [c for c in stripped if c.isalpha()]
        is_caps = bool(letters) and all(c.isupper() for c in letters) and len(letters) >= 3
        if is_caps:
            headings.append(canonical)
        elif any(
            canonical == phrase or canonical.startswith(phrase + " ")
            for phrase in _ALL_HEADING_PHRASES
        ):
            headings.append(canonical)
    return headings


def _detect_sections(text: str) -> tuple[set[str], list[str]]:
    """Detect canonical sections present in the document.

    Returns (found_sections, all_detected_names) — the second list keeps
    bonus sections found for the details payload.
    """
    headings = _iter_heading_lines(text)
    found: set[str] = set()
    for canonical_name, keywords in _SECTION_KEYWORDS.items():
        for heading in headings:
            padded = f" {heading} "
            if any(
                heading == _canonicalize(keyword)               # exact ("skills")
                or padded.startswith(f" {_canonicalize(keyword)}")  # prefix ("skills & tools")
                or f" {_canonicalize(keyword)} " in padded      # whole-word ("professional summary")
                or heading.startswith(f"{_canonicalize(keyword)} ")  # "work experience"
                for keyword in keywords
            ):
                found.add(canonical_name)
                break
    return found, sorted(found)


def _collect_bullets(text: str) -> list[str]:
    """Collect bullet-style lines (markdown list markers or bullet glyphs)."""
    bullets: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(("-", "*", "+")) and len(stripped) > 2:
            bullets.append(stripped.lstrip("-*+ ").strip())
        elif any(stripped.startswith(marker) for marker in _BULLET_MARKERS):
            bullets.append(stripped.lstrip("".join(_BULLET_MARKERS)).strip())
    return [b for b in bullets if _word_count(b) >= 3]


def _extract_all_text(text: str) -> str:
    """Flatten markdown to plain text (headings/list markers removed)."""
    plain = _MARKDOWN_HEADING_RE.sub(r" \1", _strip_code_fences(text))
    plain = re.sub(r"^[ \t]*[-*+•◦‣·▪][ \t]+", " ", plain, flags=re.MULTILINE)
    plain = re.sub(r"[|*_`>#]+", " ", plain)
    return plain


# --------------------------------------------------------------------------
# Component scorers
# --------------------------------------------------------------------------

def _compute_contact_info(text: str) -> tuple[float, dict[str, Any]]:
    """Contact field completeness (ATS field-mapping proxy).

    Weights inside the component: email 40, phone 30, professional link 15,
    location 15. The first line of the document almost always carries the
    candidate name; if it has no email/phone/URL we assume it is the name.
    """
    # Only look at the header region (top of the document) for links/location,
    # but scan the whole document for email/phone (footer signatures count).
    header = "\n".join(text.splitlines()[:20])

    email_found = bool(_EMAIL_RE.search(text))
    phone_found = bool(re.search(r"(?:\+?\d[\d\s().-]{7,}\d)", header))
    link_found = bool(_LINK_RE.search(header))
    # City, ST / City, Country style location: matched anywhere in a header
    # line (contact headers often join everything with pipes or bullets).
    location_found = any(
        _LOCATION_RE.search(line.strip()) for line in header.splitlines()
    )

    # Name heuristic: first non-empty line exists and is not an email/phone/URL.
    first_line = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    name_found = bool(first_line) and not any(
        pattern.search(first_line) for pattern in (_EMAIL_RE, _PHONE_RE, _LINK_RE)
    )

    score = (
        (40.0 if email_found else 0.0)
        + (30.0 if phone_found else 0.0)
        + (15.0 if link_found else 0.0)
        + (15.0 if location_found else 0.0)
    )
    details = {
        "email": email_found,
        "phone": phone_found,
        "professional_link": link_found,
        "location": location_found,
        "name_line": name_found,
    }
    return score, details


def _compute_section_completeness(text: str) -> tuple[float, dict[str, Any]]:
    """Standard heading presence — the ATS routing layer."""
    found, detected = _detect_sections(text)

    core_found = sum(1 for name in _CORE_SECTIONS if name in found)
    bonus_found = sum(1 for name in _BONUS_SECTIONS if name in found)

    # The four core sections carry the weight; each bonus adds a little.
    score = min(100.0, (core_found / len(_CORE_SECTIONS)) * 85.0 + bonus_found * 7.5)
    missing = [name for name in _CORE_SECTIONS if name not in found]
    return score, {"found": detected, "missing": missing}


def _compute_formatting_quality(text: str) -> tuple[float, dict[str, Any]]:
    """Parser-friendliness: dates, bullets, length, linear-text artifacts."""
    warnings: list[str] = []
    plain = _extract_all_text(text)
    total_words = _word_count(plain)
    bullets = _collect_bullets(text)

    # 1. Date ranges on experience entries (want at least 2 for a career).
    date_ranges = _DATE_RANGE_RE.findall(text)
    n_dates = len(date_ranges)
    if n_dates == 0:
        date_score = 20.0
        warnings.append("no_date_ranges_found")
    elif n_dates == 1:
        date_score = 60.0
    elif n_dates <= 4:
        date_score = 100.0
    else:
        date_score = 100.0

    # 2. Bullet usage: achievements should be bulleted (>= 5 bullets is healthy).
    n_bullets = len(bullets)
    if n_bullets == 0:
        bullet_score = 40.0
        warnings.append("no_bullet_structure")
    elif n_bullets < 5:
        bullet_score = 65.0
    else:
        bullet_score = 100.0

    # 3. Bullet length sanity (ideal 6-40 words).
    if bullets:
        well_sized = sum(1 for b in bullets if 6 <= _word_count(b) <= 40)
        length_score = (well_sized / len(bullets)) * 100.0
        if length_score < 50:
            warnings.append("bullet_length_outliers")
    else:
        length_score = 60.0

    # 4. Total word count sanity (350-1100 = recruiter-friendly band).
    if 350 <= total_words <= 1100:
        wc_score = 100.0
    elif 200 <= total_words < 350:
        wc_score = 65.0
        warnings.append("resume_too_short")
    elif 1100 < total_words <= 1600:
        wc_score = 60.0
        warnings.append("resume_too_long")
    elif total_words < 200:
        wc_score = 35.0
        warnings.append("resume_too_short")
    else:
        wc_score = 40.0
        warnings.append("resume_too_long")

    # 5. Linear-text artifacts: markdown tables / heavy pipe usage scramble
    #    extraction (multi-column layouts).
    artifacts = len(_MARKDOWN_TABLE_RE.findall(text))
    artifact_score = max(0.0, 100.0 - artifacts * 25.0)
    if artifacts:
        warnings.append("table_like_structure_detected")

    score = (
        date_score * 0.30
        + bullet_score * 0.20
        + length_score * 0.15
        + wc_score * 0.20
        + artifact_score * 0.15
    )
    details = {
        "total_words": total_words,
        "bullet_lines": n_bullets,
        "well_sized_bullets": sum(1 for b in bullets if 6 <= _word_count(b) <= 40),
        "date_ranges_found": n_dates,
        "table_artifacts": artifacts,
        "formatting_warnings": warnings,
    }
    return min(100.0, score), details


def _compute_impact_quality(text: str) -> tuple[float, dict[str, Any]]:
    """Quantified achievements + strong action verbs (recruiter impact screen).

    Mirrors the JD-aware engine's formula but operates on bullet lines parsed
    straight from the markdown, so it works without LLM structuring.
    """
    bullets = _collect_bullets(text)
    if not bullets:
        plain_lines = [
            line.strip() for line in _extract_all_text(text).splitlines() if line.strip()
        ]
        bullets = [line for line in plain_lines if _word_count(line) >= 5]

    if not bullets:
        return 0.0, {
            "quantified_bullets": 0,
            "action_verb_bullets": 0,
            "total_bullets": 0,
        }

    quantified = 0
    action_verbs = 0
    for bullet in bullets:
        words = bullet.split()
        first = _canonicalize(words[0]) if words else ""
        if first in _ACTION_VERBS:
            action_verbs += 1
        if _QUANT_RE.search(bullet):
            quantified += 1

    n = len(bullets)
    # Quantified achievements count double: they are the #1 recruiter signal.
    score = (quantified / n) * 60.0 + (action_verbs / n) * 40.0
    details = {
        "quantified_bullets": quantified,
        "action_verb_bullets": action_verbs,
        "total_bullets": n,
    }
    return min(100.0, score), details


def _compute_keyword_optimization(text: str) -> tuple[float, dict[str, Any]]:
    """Concrete-skills coverage + keyword stuffing guard.

    A resume aimed at real roles names concrete tools/skills. We measure how
    many *known* skills appear (alias-aware) and penalize single-term stuffing
    (ATS spam filters and recruiters both punish it).
    """
    plain = _canonicalize(_extract_all_text(text))

    found_skills: list[str] = []
    for skill in _KNOWN_SKILLS:
        if _term_in_text(skill, plain):
            found_skills.append(skill)

    n_found = len(found_skills)
    if n_found >= 10:
        coverage_score = 100.0
    elif n_found >= 6:
        coverage_score = 80.0
    elif n_found >= 3:
        coverage_score = 60.0
    elif n_found >= 1:
        coverage_score = 40.0
    else:
        coverage_score = 20.0

    # Stuffing guard: any single word repeated far beyond sanity.
    words = [w for w in re.findall(r"[a-z][a-z+#.-]{2,}", plain)]
    stuffing = False
    max_repeats = 0
    worst_word = ""
    counts: dict[str, int] = {}
    total_words = len(words) or 1
    for word in words:
        counts[word] = counts.get(word, 0) + 1
    for word, count in counts.items():
        if count > max_repeats and count >= 12 and count / total_words > 0.02:
            max_repeats = count
            worst_word = word
            stuffing = True

    stuffing_penalty = 30.0 if stuffing else 0.0
    score = max(0.0, coverage_score - stuffing_penalty)
    details = {
        "known_skills_found": found_skills[:25],
        "distinct_known_skills": n_found,
        "keyword_stuffing": stuffing,
        "most_repeated_word": worst_word or None,
        "most_repeated_count": max_repeats if stuffing else 0,
    }
    return score, details


def _compute_readability_structure(text: str) -> tuple[float, dict[str, Any]]:
    """Language hygiene: fillers, first person, caps abuse, long lines."""
    plain = _extract_all_text(text).lower()

    filler_count = sum(plain.count(phrase) for phrase in _FILLER_PHRASES)
    first_person = len(_FIRST_PERSON_RE.findall(text))
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    long_lines = sum(1 for line in lines if len(line) > 220)

    heading_texts = {h for h in _iter_heading_lines(text)}
    caps_words = 0
    for line in lines:
        canonical = _canonicalize(line)
        if canonical in heading_texts:
            continue
        caps_words += len(_ALL_CAPS_WORD_RE.findall(line))

    warnings: list[str] = []
    score = 100.0

    if filler_count > 0:
        score -= min(30.0, filler_count * 10.0)
        warnings.append("filler_phrases_used")
    if first_person > 3:
        score -= min(25.0, (first_person - 3) * 5.0)
        warnings.append("first_person_pronouns")
    if caps_words > 8:
        score -= min(20.0, (caps_words - 8) * 2.0)
        warnings.append("excessive_all_caps")
    if long_lines > 2:
        score -= min(25.0, long_lines * 5.0)
        warnings.append("very_long_lines")

    details = {
        "filler_phrases": filler_count,
        "first_person_pronouns": first_person,
        "all_caps_words": caps_words,
        "long_lines": long_lines,
        "readability_warnings": warnings,
    }
    return max(0.0, score), details


# --------------------------------------------------------------------------
# Recommendations
# --------------------------------------------------------------------------

def _generate_recommendations(
    scores: dict[str, float],
    contact: dict[str, Any],
    sections: dict[str, Any],
    formatting: dict[str, Any],
    impact: dict[str, Any],
    keywords: dict[str, Any],
    readability: dict[str, Any],
) -> list[str]:
    tips: list[str] = []

    if not contact.get("email"):
        tips.append("Add a professional email address — ATS parsers map it to the primary contact field.")
    if not contact.get("phone"):
        tips.append("Include a phone number in the header so recruiters can reach you.")
    if not contact.get("professional_link"):
        tips.append("Add a LinkedIn (or GitHub/portfolio) URL to strengthen your professional profile.")
    if not contact.get("location"):
        tips.append("Add your city and state/country — location filters are common in recruiter searches.")

    for missing in sections.get("missing", []):
        if missing == "summary":
            tips.append("Add a 2-3 line professional Summary at the top — recruiters read it first.")
        elif missing == "experience":
            tips.append("Add a clearly headed Experience section with roles, companies and dates.")
        elif missing == "education":
            tips.append("Add an Education section — ATS forms almost always include a degree field.")
        elif missing == "skills":
            tips.append("Add a dedicated Skills section — ATS keyword searches weight it heavily.")

    formatting_warnings = formatting.get("formatting_warnings", [])
    if "no_date_ranges_found" in formatting_warnings:
        tips.append("Add start/end dates (month + year) to every experience entry.")
    if "no_bullet_structure" in formatting_warnings:
        tips.append(
            "Format achievements as bullet points — walls of text parse poorly and read worse."
        )
    if "resume_too_short" in formatting_warnings:
        tips.append(
            "The resume looks thin — expand experience bullets with scope, tools and outcomes."
        )
    if "resume_too_long" in formatting_warnings:
        tips.append(
            "Trim the resume toward one page: keep the most relevant bullets and cut the rest."
        )
    if "table_like_structure_detected" in formatting_warnings:
        tips.append(
            "Remove table/column layouts — linear single-column text extracts cleanly through ATS parsers."
        )
    if "bullet_length_outliers" in formatting_warnings:
        tips.append(
            "Rewrite bullets to one or two lines each (roughly 8-35 words) for scannability."
        )

    impact_total = impact.get("total_bullets", 0)
    if impact_total:
        quantified_ratio = impact.get("quantified_bullets", 0) / impact_total
        if quantified_ratio < 0.3:
            tips.append(
                "Quantify more achievements with numbers, percentages or dollar impact "
                "(e.g. 'reduced latency by 40%')."
            )
        verb_ratio = impact.get("action_verb_bullets", 0) / impact_total
        if verb_ratio < 0.4:
            tips.append(
                "Start bullets with strong action verbs (led, built, reduced, launched…) "
                "instead of nouns or passive phrasing."
            )

    if keywords.get("distinct_known_skills", 0) < 3:
        tips.append(
            "Name concrete tools and technologies (Python, SQL, Figma, AWS…) so keyword "
            "searches can find you."
        )
    if keywords.get("keyword_stuffing"):
        tips.append(
            "Reduce keyword repetition — the same term appears far too often and reads as spam."
        )

    readability_warnings = readability.get("readability_warnings", [])
    if "filler_phrases_used" in readability_warnings:
        tips.append(
            "Replace filler phrases like 'responsible for' with direct achievement statements."
        )
    if "first_person_pronouns" in readability_warnings:
        tips.append("Drop first-person pronouns (I, my, me) — resumes conventionally omit them.")
    if "very_long_lines" in readability_warnings:
        tips.append("Break very long lines into shorter bullets; long lines often signal dense paragraphs.")

    if not tips:
        tips.append(
            "Strong parseability. Final polish: mirror the vocabulary of your target role's "
            "job descriptions and verify every claim is interview-defensible."
        )
    return tips


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

def compute_standalone_ats_score(markdown_text: str) -> dict[str, Any]:
    """Compute the standalone (resume-only) ATS score breakdown.

    Args:
        markdown_text: Markdown extracted from the uploaded resume PDF/DOCX.

    Returns:
        Dict with ``overall_score``, ``sub_scores`` (6 components),
        ``recommendations``, ``interpretation`` and ``details``. Mirrors the
        top-level shape of ``compute_ats_score`` so downstream consumers can
        treat both engines uniformly.
    """
    try:
        text = markdown_text or ""
        if not text.strip():
            raise ValueError("Empty resume text")

        contact_score, contact_details = _compute_contact_info(text)
        section_score, section_details = _compute_section_completeness(text)
        formatting_score, formatting_details = _compute_formatting_quality(text)
        impact_score, impact_details = _compute_impact_quality(text)
        keyword_score, keyword_details = _compute_keyword_optimization(text)
        readability_score, readability_details = _compute_readability_structure(text)

        scores = {
            "contact_info": contact_score,
            "section_completeness": section_score,
            "formatting_quality": formatting_score,
            "impact_quality": impact_score,
            "keyword_optimization": keyword_score,
            "readability_structure": readability_score,
        }

        overall = sum(scores[k] * w for k, w in _WEIGHTS.items())

        return {
            "overall_score": round(min(100.0, max(0.0, overall)), 1),
            "sub_scores": {k: round(min(100.0, v), 1) for k, v in scores.items()},
            "recommendations": _generate_recommendations(
                scores,
                contact_details,
                section_details,
                formatting_details,
                impact_details,
                keyword_details,
                readability_details,
            ),
            "interpretation": _interpretation(overall),
            "details": {
                "contact": contact_details,
                "sections": section_details,
                "formatting": formatting_details,
                "impact": impact_details,
                "keywords": {
                    "distinct_known_skills": keyword_details["distinct_known_skills"],
                    "known_skills_found": keyword_details["known_skills_found"],
                    "keyword_stuffing": keyword_details["keyword_stuffing"],
                },
                "readability": readability_details,
            },
        }
    except Exception:
        logger.exception("Standalone ATS scoring failed; returning zeroed breakdown")
        return {
            "overall_score": 0.0,
            "sub_scores": {k: 0.0 for k in _WEIGHTS},
            "recommendations": [
                "Score could not be computed from the resume text — try re-uploading the file."
            ],
            "interpretation": "unknown",
            "details": {},
        }
