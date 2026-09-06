"""Industry-grade ATS scoring engine.

Models how commercial hiring platforms (Greenhouse, Workable, Lever, iCIMS,
Taleo) actually evaluate resumes:

1. **Recruiter keyword search parity** — recruiters on those platforms search
   candidate pools with *literal* queries ("python", "kubernetes", "CI/CD").
   Our keyword matcher therefore uses whole-phrase matching with separator
   insensitivity (``node.js`` ≡ ``nodejs`` ≡ ``Node JS``) plus a curated
   alias/acronym map (``k8s`` → ``kubernetes``, ``ml`` → ``machine learning``),
   and weights **required** skills roughly double vs **preferred** skills —
   mirroring how ATS relevance ranking treats must-have vs nice-to-have.
2. **Parser friendliness** — real ATS ingest resumes into structured fields
   first. Resumes missing contact data, employment dates, or standard section
   headings lose points (and sometimes get discarded outright) before a human
   ever sees them.
3. **Recruiter-judgement proxies** — quantified achievements and strong action
   verbs approximate the "impact" screen a recruiter applies in the 6-10
   seconds they spend per resume.
4. **Content alignment** — TF-IDF cosine similarity between the JD's
   requirement text and the resume body approximates the "did they actually
   do this job" check, without spending LLM tokens.

The engine is fully deterministic and local (no LLM/embedding calls) so it can
run on every preview/confirm without latency or token cost.

Scoring model (weights sum to 1.0):

====================================  ======  =====================================
Component                             Weight  What it measures
====================================  ======  =====================================
keyword_match                         0.30    required/preferred/general keyword
                                              coverage (recruiter search parity)
skills_coverage                       0.15    JD skills found in the resume's
                                              Skills section (structured match)
semantic_similarity                   0.15    TF-IDF cosine(JD requirements,
                                              resume text)
experience_alignment                  0.10    years-of-experience & seniority
                                              vs the JD's stated requirements
education_match                       0.05    degree tier vs JD education reqs
section_completeness                  0.10    essential sections + contact info
formatting_quality                    0.075   bullets, dates, bullet length,
                                              summary length, word-count sanity
impact_quality                        0.075   quantified achievements & strong
                                              action verbs
====================================  ======  =====================================

The first three legacy sub-scores (``keyword_match``, ``skills_coverage``,
``section_completeness``) keep their names so older clients render
gracefully; the additional components are additive.
"""

import logging
import math
import re
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Weights (must sum to 1.0)
# --------------------------------------------------------------------------
_WEIGHTS = {
    "keyword_match": 0.30,
    "skills_coverage": 0.15,
    "semantic_similarity": 0.15,
    "experience_alignment": 0.10,
    "education_match": 0.05,
    "section_completeness": 0.10,
    "formatting_quality": 0.075,
    "impact_quality": 0.075,
}

# Within keyword_match: required vs preferred vs general keyword weighting
_KEYWORD_SUB_WEIGHTS = {"required": 0.55, "preferred": 0.25, "general": 0.20}

# Curated alias/acronym map — maps surface forms to a canonical skill id.
# Keys and values are compared after canonicalization (see _canonicalize).
_ALIASES: dict[str, list[str]] = {
    "javascript": ["js", "java script", "ecmascript", "es6"],
    "typescript": ["ts"],
    "python": ["py", "python3"],
    "kubernetes": ["k8s"],
    "machine learning": ["ml"],
    "artificial intelligence": ["ai"],
    "amazon web services": ["aws", "amazon aws", "aws cloud"],
    "google cloud": ["gcp", "google cloud platform"],
    "microsoft azure": ["azure", "azure cloud"],
    "nodejs": ["node", "node js", "node js js"],
    "postgresql": ["postgres", "psql"],
    "mongodb": ["mongo"],
    "react": ["reactjs", "react js", "react.js"],
    "react native": ["reactnative"],
    "vuejs": ["vue", "vue js"],
    "angularjs": ["angular", "angular js"],
    "nextjs": ["next js", "next.js"],
    "continuous integration": ["ci"],
    "continuous delivery": ["cd"],
    "cicd": ["ci cd", "ci cd pipeline", "continuous integration and delivery"],
    "rest api": ["rest apis", "restful api", "restful apis", "restful"],
    "graphql": ["graph ql"],
    "elasticsearch": ["elastic search"],
    "microservices": ["micro services", "microservice", "microservice architecture"],
    "infrastructure as code": ["iac"],
    "business intelligence": ["bi"],
    "natural language processing": ["nlp"],
    "large language models": ["llm", "llms", "large language model"],
    "generative ai": ["genai", "gen ai"],
    "power bi": ["powerbi"],
    "structured query language": ["sql"],
    "devops": ["dev ops"],
    "sre": ["site reliability engineering", "site reliability engineer"],
    "user experience": ["ux"],
    "user interface": ["ui"],
    "quality assurance": ["qa"],
    "object oriented": ["oop", "object oriented programming"],
    "ci cd": ["cicd", "ci cd pipeline"],
}

# Reverse map: surface form (canonicalized) -> canonical skill id
_ALIAS_LOOKUP: dict[str, str] = {}
for _canonical_skill, _surfaces in _ALIASES.items():
    _ALIAS_LOOKUP[_canonical_skill] = _canonical_skill
    for _surface in _surfaces:
        _ALIAS_LOOKUP[_surface] = _canonical_skill

# Strong resume action verbs (recruiter "impact" screen)
_ACTION_VERBS = {
    "achieved", "acquired", "adapted", "addressed", "administered", "advised",
    "advocated", "analyzed", "architected", "automated", "accelerated",
    "benchmarked", "boosted", "budgeted", "built", "championed", "coached",
    "consolidated", "converted", "coordinated", "created", "cultivated",
    "debugged", "decreased", "delivered", "deployed", "designed", "developed",
    "devised", "diagnosed", "directed", "documented", "doubled", "drove",
    "eliminated", "enabled", "engineered", "enhanced", "established",
    "evaluated", "exceeded", "executed", "expanded", "facilitated", "forecast",
    "formulated", "founded", "generated", "grew", "guided", "headed",
    "identified", "implemented", "improved", "increased", "influenced",
    "initiated", "instituted", "integrated", "introduced", "launched", "led",
    "leveraged", "maintained", "managed", "mapped", "marketed", "mentored",
    "migrated", "modeled", "modernized", "negotiated", "optimized",
    "orchestrated", "overhauled", "owned", "oversee", "pioneered", "planned",
    "prioritized", "produced", "programmed", "proposed", "prototyped",
    "rearchitected", "rebuilt", "reduced", "refactored", "reengineered",
    "resolved", "restructured", "revamped", "spearheaded", "scaled",
    "secured", "shipped", "simplified", "solved", "standardized",
    "streamlined", "strengthened", "supervised", "surpassed", "tested",
    "tracked", "trained", "transformed", "troubleshot", "unified", "upgraded",
    "validated", "wrote",
}

_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from",
    "has", "have", "in", "is", "it", "its", "of", "on", "or", "our", "that",
    "the", "their", "them", "there", "these", "this", "to", "was", "we",
    "were", "will", "with", "you", "your", "who", "what", "when", "where",
    "which", "while", "about", "across", "after", "all", "also", "any",
    "because", "been", "before", "being", "between", "both", "can", "could",
    "did", "do", "does", "each", "few", "had", "he", "her", "him", "his",
    "how", "if", "into", "just", "me", "more", "most", "my", "no", "not",
    "now", "other", "out", "over", "own", "same", "she", "so", "some", "such",
    "than", "then", "they", "those", "too", "under", "up", "very", "want",
    "well", "would", "years", "year", "etc", "eg", "ie", "including",
    "includes", "include", "using", "use", "used", "ability", "able",
    "strong", "excellent", "good", "great", "various", "via", "per", "plus",
    "preferred", "required", "requirements", "responsibilities", "role",
    "team", "teams", "work", "working", "works", "experience", "experienced",
    "candidate", "candidates", "company", "companies", "job", "join", "looking",
    "seeking", "help", "new", "like", "must", "should", "familiar",
    "knowledge", "understanding", "expertise", "proficient", "proficiency",
}

# Patterns to detect resume section headings
_SECTION_PATTERNS = {
    "summary": ["summary", "objective", "profile", "about"],
    "experience": ["experience", "work history", "employment"],
    "education": ["education", "academic", "degree"],
    "skills": ["skills", "technologies", "competencies", "technical"],
}

# Degree tiers for education matching
_DEGREE_TIERS = {
    "phd": 4, "doctorate": 4, "doctoral": 4, "postdoc": 4,
    "md": 4,
    "master": 3, "masters": 3, "msc": 3, "m sc": 3, "m s": 3, "mba": 3,
    "ma": 3, "meng": 3, "m eng": 3, "graduate degree": 3,
    "bachelor": 2, "bachelors": 2, "bsc": 2, "b sc": 2, "b s": 2,
    "ba": 2, "beng": 2, "b eng": 2, "undergraduate degree": 2, "bs": 2,
    "associate": 1, "diploma": 1, "certificate": 1, "certification": 1,
}

_SENIORITY_RANK = {"junior": 1, "entry": 1, "mid": 2, "intermediate": 2, "mid-level": 2, "senior": 3, "lead": 4, "staff": 4, "principal": 5, "director": 6, "head": 6}

# ---------------------------------------------------------------------------
# Term canonicalization / matching
# ---------------------------------------------------------------------------

# Anything that is not a letter, digit, '+' or '#' acts as a separator.
_SEPARATOR_RE = re.compile(r"[^a-z0-9+#]+")
_WORD_CHAR_CLASS = "a-z0-9+#"


def _canonicalize(term: str) -> str:
    """Lowercase and collapse all separators to single spaces.

    ``Node.JS`` → ``node js``; ``C++`` → ``c++``; ``CI/CD`` → ``ci cd``.
    """
    return _SEPARATOR_RE.sub(" ", term.strip().lower()).strip()


def _term_variants(term: str) -> list[str]:
    """Return all surface forms that should count as a match for ``term``.

    Includes the term itself, its canonical alias family, and a de-pluralized
    form (``microservices`` also matches ``microservice``).
    """
    seen: dict[str, None] = {}  # insertion-ordered set
    base = _canonicalize(term)
    if not base:
        return []

    candidates = [base]
    # Singular/plural tolerance for the final token ("services" -> "service")
    tokens = base.split()
    if tokens:
        last = tokens[-1]
        if last.endswith("s") and len(last) > 3:
            candidates.append(" ".join(tokens[:-1] + [last[:-1]]))
        elif not last.endswith("s"):
            candidates.append(" ".join(tokens[:-1] + [last + "s"]))

    # Expand through the alias map (both directions)
    for candidate in list(candidates):
        canonical = _ALIAS_LOOKUP.get(candidate)
        if not canonical:
            continue
        if canonical not in candidates:
            candidates.append(canonical)
        # Also match every surface form of the same canonical skill
        for surface, target in _ALIAS_LOOKUP.items():
            if target == canonical and surface not in candidates:
                candidates.append(surface)

    for candidate in candidates:
        if candidate:
            seen[candidate] = None
    return list(seen)


def _pattern_for(variant: str) -> re.Pattern:
    """Build a separator-tolerant regex for a canonicalized variant.

    ``node js`` matches ``nodejs``, ``Node.JS``, ``node-js``; boundaries are
    anchored on the word-char class so ``js`` does not match inside ``nodejs``
    and ``go`` does not match inside ``django``.
    """
    tokens = [re.escape(t) for t in variant.split()]
    body = r"[\s._\-]*".join(tokens)
    return re.compile(rf"(?<![{_WORD_CHAR_CLASS}]){body}(?![{_WORD_CHAR_CLASS}])")


def _term_in_text(term: str, normalized_text: str) -> bool:
    """Whole-phrase, separator-insensitive, alias-aware term match."""
    for variant in _term_variants(term):
        if _pattern_for(variant).search(normalized_text):
            return True
    return False


def _extract_all_text(data: dict[str, Any]) -> str:
    """Flatten all string values from a resume dict into a single text block."""
    parts: list[str] = []

    def _walk(obj: Any) -> None:
        if isinstance(obj, str):
            parts.append(obj)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)
        elif isinstance(obj, dict):
            for v in obj.values():
                _walk(v)

    _walk(data)
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Keyword coverage (recruiter search parity)
# ---------------------------------------------------------------------------

def _coverage(items: list[str], text: str) -> tuple[float, list[str], list[str]]:
    """Return (coverage %, matched, missing) for a keyword list vs text."""
    clean = [k for k in items if isinstance(k, str) and k.strip()]
    if not clean:
        return 100.0, [], []  # vacuously covered — do not punish absent data
    matched = [k for k in clean if _term_in_text(k, text)]
    missing = [k for k in clean if k not in matched]
    return (len(matched) / len(clean)) * 100.0, matched, missing


def _compute_keyword_match(
    resume_text_norm: str,
    job_keywords: dict[str, Any],
) -> tuple[float, dict[str, Any]]:
    """Weighted required/preferred/general keyword coverage + detail."""
    required = [s for s in job_keywords.get("required_skills", []) if isinstance(s, str)]
    preferred = [s for s in job_keywords.get("preferred_skills", []) if isinstance(s, str)]
    general = [s for s in job_keywords.get("keywords", []) if isinstance(s, str)]

    if not required and not preferred and not general:
        # No keywords at all — neutral, so this component can't tank the total
        # (the composite falls back to the pipeline's measured match %).
        return 100.0, {
            "required_skills_matched": [],
            "required_skills_missing": [],
            "preferred_skills_matched": [],
            "preferred_skills_missing": [],
            "general_keywords_matched": [],
            "general_keywords_missing": [],
        }

    req_cov, req_matched, req_missing = _coverage(required, resume_text_norm)
    pref_cov, pref_matched, pref_missing = _coverage(preferred, resume_text_norm)
    gen_cov, gen_matched, gen_missing = _coverage(general, resume_text_norm)

    total_weight = sum(
        _KEYWORD_SUB_WEIGHTS[k]
        for k, items in (
            ("required", required),
            ("preferred", preferred),
            ("general", general),
        )
        if items
    ) or 1.0

    score = (
        req_cov * (required and _KEYWORD_SUB_WEIGHTS["required"] or 0)
        + pref_cov * (preferred and _KEYWORD_SUB_WEIGHTS["preferred"] or 0)
        + gen_cov * (general and _KEYWORD_SUB_WEIGHTS["general"] or 0)
    ) / total_weight

    details = {
        "required_skills_matched": req_matched,
        "required_skills_missing": req_missing,
        "preferred_skills_matched": pref_matched,
        "preferred_skills_missing": pref_missing,
        "general_keywords_matched": gen_matched,
        "general_keywords_missing": gen_missing,
    }
    return min(100.0, score), details


def _compute_skills_coverage(
    resume: dict[str, Any],
    job_keywords: dict[str, Any],
) -> float:
    """JD skills overlap with the resume's structured Skills section.

    Falls back to full-text matching when the resume has no skills section,
    so a sparse master resume is not double-punished.
    """
    jd_skills: list[str] = []
    jd_skills.extend(job_keywords.get("required_skills", []))
    jd_skills.extend(job_keywords.get("preferred_skills", []))
    jd_skills = [s for s in jd_skills if isinstance(s, str)]

    if not jd_skills:
        return 0.0

    resume_skills: list[str] = (
        resume.get("additional", {}).get("technicalSkills", []) or []
    )
    if resume_skills:
        skills_blob = _canonicalize(" ".join(str(s) for s in resume_skills))
        matched = sum(1 for s in jd_skills if _term_in_text(s, skills_blob))
        return min(100.0, (matched / len(jd_skills)) * 100)

    resume_text = _canonicalize(_extract_all_text(resume))
    matched = sum(1 for s in jd_skills if _term_in_text(s, resume_text))
    return min(100.0, (matched / len(jd_skills)) * 100)


# ---------------------------------------------------------------------------
# Semantic similarity (TF-IDF cosine, no LLM)
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z]{2,}", text.lower()) if t not in _STOPWORDS]


def _tfidf_vector(text: str, idf: dict[str, float]) -> dict[str, float]:
    tokens = _tokenize(text)
    tf: dict[str, int] = {}
    for tok in tokens:
        tf[tok] = tf.get(tok, 0) + 1
    total = len(tokens) or 1
    return {tok: (count / total) * idf.get(tok, 1.0) for tok, count in tf.items()}


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(v * b.get(k, 0.0) for k, v in a.items())
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _jd_requirement_text(job_keywords: dict[str, Any]) -> str:
    """Reconstruct a JD representation from the extracted keyword dict."""
    parts: list[str] = []
    for key in (
        "required_skills",
        "preferred_skills",
        "keywords",
        "key_responsibilities",
        "experience_requirements",
        "education_requirements",
    ):
        value = job_keywords.get(key, [])
        if isinstance(value, list):
            parts.extend(str(v) for v in value)
        elif isinstance(value, str):
            parts.append(value)
    role = job_keywords.get("role")
    if isinstance(role, str):
        parts.append(role)
    return " ".join(parts)


def _compute_semantic_similarity(resume_text: str, job_keywords: dict[str, Any]) -> float:
    """TF-IDF cosine similarity between JD requirements and resume text.

    Cosines on short text pairs rarely exceed ~0.5, so the raw score is
    rescaled (capped at 0.4 → 100) to a recruiter-intuitive 0-100 range.
    """
    jd_text = _jd_requirement_text(job_keywords)
    if not jd_text or not resume_text:
        return 0.0

    docs = [jd_text, resume_text]
    df: dict[str, int] = {}
    for doc in docs:
        for tok in set(_tokenize(doc)):
            df[tok] = df.get(tok, 0) + 1
    n_docs = len(docs)
    idf = {tok: math.log((n_docs + 1) / (count + 1)) + 1.0 for tok, count in df.items()}

    jd_vec = _tfidf_vector(jd_text, idf)
    resume_vec = _tfidf_vector(resume_text, idf)
    raw = _cosine(jd_vec, resume_vec)
    return min(100.0, (raw / 0.4) * 100.0)


# ---------------------------------------------------------------------------
# Experience & education alignment
# ---------------------------------------------------------------------------

_YEAR_RE = re.compile(r"(19|20)\d{2}")
_NOW_YEAR = datetime.now().year


def _parse_years_field(years: str | None) -> tuple[float, float]:
    """Parse a date range like ``Jan 2020 - Present`` → (start, end) as years.

    Returns (0, 0) when unparseable. ``Present``/``Current`` maps to now.
    """
    if not isinstance(years, str) or not years.strip():
        return 0.0, 0.0
    lowered = years.lower()
    tokens = years.replace("–", "-").replace("—", "-").split("-")
    nums: list[int] = []
    present = ("present" in lowered) or ("current" in lowered) or ("now" in lowered)

    for token in tokens:
        match = _YEAR_RE.search(token)
        if match:
            nums.append(int(match.group(0)))

    if not nums:
        return 0.0, 0.0

    start = float(nums[0])
    end = float(nums[-1]) if len(nums) > 1 else (float(_NOW_YEAR) if present else start)
    if end < start:
        start, end = end, start
    return start, end


def _total_experience_years(resume: dict[str, Any]) -> float:
    """Estimate total years of experience from workExperience date ranges.

    Ranges are merged/summed naively (overlap tolerance is acceptable — this
    is a heuristic alignment score, not payroll math).
    """
    total = 0.0
    for exp in resume.get("workExperience", []) or []:
        if not isinstance(exp, dict):
            continue
        start, end = _parse_years_field(exp.get("years"))
        if end > start:
            total += min(end - start, 15.0)  # cap absurd ranges
        elif start:
            total += 1.0  # single year mentioned — count at least one year
    return min(total, 45.0)


def _compute_experience_alignment(
    resume: dict[str, Any],
    job_keywords: dict[str, Any],
) -> tuple[float, dict[str, Any]]:
    """Years-of-experience + seniority alignment vs the JD requirement."""
    resume_years = _total_experience_years(resume)
    required_years = job_keywords.get("experience_years")
    required_years = required_years if isinstance(required_years, (int, float)) else None

    years_score = 100.0
    if required_years and required_years > 0:
        if resume_years <= 0:
            years_score = 30.0  # no parseable dates — cannot demonstrate
        elif resume_years >= required_years:
            years_score = 100.0
        elif resume_years >= required_years - 1:
            years_score = 85.0  # within one year of the bar
        else:
            ratio = resume_years / float(required_years)
            years_score = max(20.0, ratio * 80.0)

    # Seniority heuristic: compare the JD's level with the resume's top titles
    jd_level = job_keywords.get("seniority_level")
    jd_rank = _SENIORITY_RANK.get(str(jd_level).lower()) if isinstance(jd_level, str) else None
    seniority_score = 80.0  # neutral when the JD doesn't state a level
    if jd_rank:
        title_text = " ".join(
            str(e.get("title", "")) for e in (resume.get("workExperience") or []) if isinstance(e, dict)
        ).lower()
        title_rank = 0
        for keyword, rank in _SENIORITY_RANK.items():
            if keyword in title_text:
                title_rank = max(title_rank, rank)
        if title_rank == 0:
            seniority_score = 70.0  # no signal in titles
        elif title_rank >= jd_rank:
            seniority_score = 100.0
        else:
            seniority_score = max(40.0, 100.0 - (jd_rank - title_rank) * 25.0)

    score = years_score * 0.6 + seniority_score * 0.4
    details = {
        "resume_experience_years": round(resume_years, 1),
        "required_experience_years": required_years,
        "seniority_level": jd_level,
    }
    return min(100.0, score), details


def _compute_education_match(
    resume: dict[str, Any],
    job_keywords: dict[str, Any],
) -> tuple[float, dict[str, Any]]:
    """Match the JD's degree requirement against the resume's degrees."""
    requirements = job_keywords.get("education_requirements", [])
    if isinstance(requirements, str):
        requirements = [requirements]
    requirements = [r for r in (requirements or []) if isinstance(r, str)]

    if not requirements:
        # No education bar stated — neutral score so it can't sink the total.
        return 80.0, {"requirement": None, "matched": None}

    required_tier = 0
    for req in requirements:
        req_norm = _canonicalize(req)
        for degree, tier in _DEGREE_TIERS.items():
            if degree in req_norm:
                required_tier = max(required_tier, tier)

    education = resume.get("education", []) or []
    resume_degrees = _canonicalize(
        " ".join(
            str(e.get("degree", "")) for e in education if isinstance(e, dict)
        )
    )
    resume_tier = 0
    for degree, tier in _DEGREE_TIERS.items():
        if degree in resume_degrees:
            resume_tier = max(resume_tier, tier)

    if required_tier == 0:
        # Requirement stated but no recognizable degree tier (e.g. "degree in
        # CS") — treat any degree as satisfying it.
        score = 100.0 if resume_tier >= 1 else 40.0
    elif resume_tier >= required_tier:
        score = 100.0
    elif resume_tier == 0:
        score = 25.0
    else:
        score = max(35.0, 100.0 - (required_tier - resume_tier) * 40.0)

    details = {
        "requirement": "; ".join(requirements[:2]),
        "resume_highest_tier": resume_tier,
        "required_tier": required_tier,
    }
    return score, details


# ---------------------------------------------------------------------------
# Structure / formatting / impact
# ---------------------------------------------------------------------------

def _compute_section_completeness(resume: dict[str, Any]) -> tuple[float, list[str]]:
    """Essential sections + contact completeness (ATS parseability proxy)."""
    found: list[str] = []
    missing: list[str] = []

    info = resume.get("personalInfo") or {}
    if isinstance(info, dict) and (info.get("email") or info.get("phone")):
        found.append("contact")
    else:
        missing.append("contact")

    checks = {
        "summary": bool(resume.get("summary")),
        "experience": bool(resume.get("workExperience")),
        "education": bool(resume.get("education")),
        "skills": bool((resume.get("additional") or {}).get("technicalSkills")),
        "projects": bool(resume.get("personalProjects")),
    }
    for name, present in checks.items():
        (found if present else missing).append(name)

    # Contact + the four core sections carry the weight; projects is a bonus.
    core_names = {"contact", "summary", "experience", "education", "skills"}
    core_found = sum(1 for f in found if f in core_names)
    bonus = 1 if "projects" in found else 0
    total = len(core_names)
    score = ((core_found + 0.5 * bonus) / total) * 100.0
    return min(100.0, score), missing


def _collect_bullets(resume: dict[str, Any]) -> list[str]:
    """Gather all experience/project description lines."""
    bullets: list[str] = []
    for section in ("workExperience", "personalProjects"):
        for entry in resume.get(section, []) or []:
            if not isinstance(entry, dict):
                continue
            desc = entry.get("description", [])
            if isinstance(desc, list):
                bullets.extend(str(d) for d in desc if str(d).strip())
            elif isinstance(desc, str) and desc.strip():
                bullets.append(desc)
    # Custom item sections also carry achievement bullets
    for section in (resume.get("customSections") or {}).values():
        if not isinstance(section, dict):
            continue
        for item in section.get("items", []) or []:
            if isinstance(item, dict):
                desc = item.get("description", [])
                if isinstance(desc, list):
                    bullets.extend(str(d) for d in desc if str(d).strip())
    return bullets


def _word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9+#.'\-]+", text))


# Matches quantified achievements: percentages, currency, plain numbers and
# suffixed magnitudes ("2M", "500k", "10x"). No trailing word boundary so
# digit+suffix forms count.
_QUANT_RE = re.compile(
    r"\d+\s?%|\d+\s?percent|[$€£¥]\s?\d|\b\d[\d,.]*|\bx\d\b|million|billion"
)


def _compute_impact_quality(resume: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    """Quantified achievements + strong action verbs (recruiter impact screen)."""
    bullets = _collect_bullets(resume)
    if not bullets:
        return 0.0, {"quantified_bullets": 0, "action_verb_bullets": 0, "total_bullets": 0}

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


def _compute_formatting_quality(resume: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    """Parser-friendliness: dates, bullet length, summary & total length."""
    warnings: list[str] = []

    # 1. Dates present on experience entries
    experience = [e for e in (resume.get("workExperience") or []) if isinstance(e, dict)]
    with_dates = sum(
        1 for e in experience if _YEAR_RE.search(str(e.get("years", "")))
    )
    date_score = (with_dates / len(experience) * 100.0) if experience else 70.0
    if experience and with_dates < len(experience):
        warnings.append("some_experience_dates_missing")

    # 2. Bullet length sanity (ideal 8-35 words)
    bullets = _collect_bullets(resume)
    ideal = sum(1 for b in bullets if 8 <= _word_count(b) <= 35)
    len_score = (ideal / len(bullets) * 100.0) if bullets else 70.0
    if bullets and ideal < len(bullets) * 0.5:
        warnings.append("bullet_length_outliers")

    # 3. Summary length (a short punchy summary parses and reads well)
    summary = str(resume.get("summary") or "")
    summary_len = len(summary)
    if 150 <= summary_len <= 900 or (summary_len and resume.get("summary")):
        summary_score = 100.0 if summary_len >= 80 else 60.0
    else:
        summary_score = 50.0
        if not summary:
            warnings.append("summary_missing")

    # 4. Total word count sanity (400-1000 words is the recruiter-friendly band)
    total_words = _word_count(_extract_all_text(resume))
    if 350 <= total_words <= 1100:
        wc_score = 100.0
    elif total_words and total_words < 350:
        wc_score = 60.0
        warnings.append("resume_too_short")
    else:
        wc_score = 55.0
        warnings.append("resume_too_long")

    score = date_score * 0.4 + len_score * 0.25 + summary_score * 0.15 + wc_score * 0.20
    details = {
        "experience_entries_with_dates": with_dates,
        "total_experience_entries": len(experience),
        "total_bullets": len(bullets),
        "well_sized_bullets": ideal,
        "total_words": total_words,
        "formatting_warnings": warnings,
    }
    return min(100.0, score), details


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------

def _generate_recommendations(
    scores: dict[str, float],
    keyword_details: dict[str, Any],
    section_missing: list[str],
    impact_details: dict[str, Any],
    formatting_details: dict[str, Any],
    missing_keywords: list[str],
    injectable_keywords: list[str],
) -> list[str]:
    tips: list[str] = []

    missing_required = keyword_details.get("required_skills_missing", [])
    if missing_required:
        top = ", ".join(missing_required[:6])
        tips.append(
            f"Add these required skills from the job description if you have used them: {top}."
        )
    if injectable_keywords:
        top_injectable = ", ".join(injectable_keywords[:6])
        tips.append(
            f"Skills in your master resume but missing here — safe to add: {top_injectable}."
        )
    elif missing_keywords and not injectable_keywords:
        tips.append(
            "Several job keywords are missing and none are in your master resume — "
            "consider gaining or honestly framing experience with them before applying."
        )

    if scores.get("skills_coverage", 100) < 60:
        tips.append(
            "Expand the Skills section with more of the tools and technologies listed in the job description."
        )
    if scores.get("semantic_similarity", 100) < 55:
        tips.append(
            "Rephrase experience bullets to mirror the job description's language "
            "(same tools, tasks and outcomes) without copying it verbatim."
        )
    if scores.get("experience_alignment", 100) < 60:
        tips.append(
            "Experience length or seniority looks misaligned with the role — "
            "surface your most senior, most relevant roles at the top."
        )
    if "contact" in section_missing:
        tips.append("Add contact details (email and phone) so ATS parsers can reach you.")
    if "summary" in section_missing:
        tips.append("Add a 2-3 line professional summary targeted at this role.")
    if "skills" in section_missing:
        tips.append("Add a dedicated Skills section — ATS keyword searches weight it heavily.")
    if impact_details.get("total_bullets"):
        quantified = impact_details.get("quantified_bullets", 0)
        total = impact_details["total_bullets"]
        if quantified / total < 0.3:
            tips.append(
                "Quantify more achievements with numbers, percentages or dollar impact "
                "(e.g. 'reduced latency by 40%')."
            )
    if "some_experience_dates_missing" in formatting_details.get("formatting_warnings", []):
        tips.append("Add start/end dates (month + year) to every experience entry.")
    if "resume_too_long" in formatting_details.get("formatting_warnings", []):
        tips.append(
            "Trim the resume toward one page: keep the most job-relevant bullets and cut the rest."
        )

    if not tips:
        if scores.get("keyword_match", 0) >= 80 and scores.get("skills_coverage", 0) >= 80:
            tips.append(
                "Strong alignment. Final polish: verify keywords appear in context "
                "(bullets, not just the skills list) and every claim is interview-defensible."
            )
        else:
            tips.append(
                "Your resume is well-aligned with the job description. Review for any niche "
                "certifications or tools to add."
            )
    return tips


def _interpretation(overall: float) -> str:
    if overall >= 85:
        return "excellent"
    if overall >= 70:
        return "strong"
    if overall >= 55:
        return "moderate"
    if overall >= 40:
        return "weak"
    return "poor"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_ats_score(
    refined_resume: dict[str, Any],
    job_keywords: dict[str, Any],
    keyword_match_percentage: float | None = None,
    missing_keywords: list[str] | None = None,
    injectable_keywords: list[str] | None = None,
) -> dict[str, Any]:
    """Compute the industry-style ATS score breakdown.

    Args:
        refined_resume: Fully refined resume data dict (structured JSON).
        job_keywords: Extracted JD keywords (required_skills, preferred_skills, …).
        keyword_match_percentage: Refinement pipeline's measured match %. Kept for
            backward compatibility; the engine now computes a higher-fidelity
            required/preferred-weighted score itself and only falls back to this
            value when the keyword dict is empty.
        missing_keywords: Keywords absent from the tailored resume (non-injectable).
        injectable_keywords: Missing keywords present in the master resume.

    Returns:
        Dict with overall_score, sub_scores (8 components), matched/missing
        keyword detail, recommendations and an interpretation band.
    """
    missing_keywords = missing_keywords or []
    injectable_keywords = injectable_keywords or []

    try:
        resume_text_norm = _canonicalize(_extract_all_text(refined_resume))

        kw_score, kw_details = _compute_keyword_match(resume_text_norm, job_keywords)
        if not job_keywords.get("required_skills") and not job_keywords.get(
            "preferred_skills"
        ) and not job_keywords.get("keywords") and keyword_match_percentage is not None:
            kw_score = min(100.0, max(0.0, float(keyword_match_percentage)))

        sk_score = _compute_skills_coverage(refined_resume, job_keywords)
        sem_score = _compute_semantic_similarity(
            _extract_all_text(refined_resume), job_keywords
        )
        exp_score, exp_details = _compute_experience_alignment(refined_resume, job_keywords)
        edu_score, edu_details = _compute_education_match(refined_resume, job_keywords)
        sec_score, sec_missing = _compute_section_completeness(refined_resume)
        fmt_score, fmt_details = _compute_formatting_quality(refined_resume)
        imp_score, imp_details = _compute_impact_quality(refined_resume)

        scores = {
            "keyword_match": kw_score,
            "skills_coverage": sk_score,
            "semantic_similarity": sem_score,
            "experience_alignment": exp_score,
            "education_match": edu_score,
            "section_completeness": sec_score,
            "formatting_quality": fmt_score,
            "impact_quality": imp_score,
        }

        overall = sum(scores[k] * w for k, w in _WEIGHTS.items())

        # Merge the pipeline's gap analysis with the engine's own (deduped,
        # required-first ordering — recruiters fix required gaps first).
        engine_missing = (
            kw_details.get("required_skills_missing", [])
            + kw_details.get("preferred_skills_missing", [])
            + kw_details.get("general_keywords_missing", [])
        )
        merged_missing: list[str] = []
        for kw in list(missing_keywords) + engine_missing:
            if kw and kw not in merged_missing:
                merged_missing.append(kw)

        return {
            "overall_score": round(min(100.0, max(0.0, overall)), 1),
            "sub_scores": {k: round(min(100.0, v), 1) for k, v in scores.items()},
            "matched_keywords": (
                kw_details.get("required_skills_matched", [])
                + kw_details.get("preferred_skills_matched", [])
            )[:20],
            "missing_keywords": merged_missing[:15],
            "injectable_keywords": injectable_keywords[:10],
            "recommendations": _generate_recommendations(
                scores,
                kw_details,
                sec_missing,
                imp_details,
                fmt_details,
                merged_missing,
                injectable_keywords,
            ),
            "interpretation": _interpretation(overall),
            "details": {
                "keyword_detail": kw_details,
                "experience": exp_details,
                "education": edu_details,
                "sections_missing": sec_missing,
                "impact": imp_details,
                "formatting": fmt_details,
            },
        }
    except Exception:
        logger.exception("ATS score computation failed; returning zeroed breakdown")
        return {
            "overall_score": 0.0,
            "sub_scores": {k: 0.0 for k in _WEIGHTS},
            "matched_keywords": [],
            "missing_keywords": missing_keywords[:15],
            "injectable_keywords": injectable_keywords[:10],
            "recommendations": [
                "Score could not be computed from the resume data — try re-uploading."
            ],
            "interpretation": "unknown",
            "details": {},
        }
