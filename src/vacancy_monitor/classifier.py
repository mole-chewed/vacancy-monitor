from __future__ import annotations

import re

from vacancy_monitor import keywords
from vacancy_monitor.models import TrackAssessment, Vacancy, VacancyTrack

BOUNDARY_TERMS = {
    "ai",
    "ml",
    "ui",
    "ux",
    "api",
    "rag",
    "llm",
    "ror",
    "aws",
    "ruby",
    "rails",
    "redis",
    "react",
    "docker",
    "fastapi",
    "graphql",
    "postgresql",
    "postgres",
}


def _term_present(text: str, term: str) -> bool:
    if term in BOUNDARY_TERMS or (term.isascii() and term.isalpha() and len(term) <= 6):
        pattern = re.compile(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])")
        return pattern.search(text) is not None
    return term in text


def _matched_terms(text: str, terms: list[str]) -> list[str]:
    found: list[str] = []
    for term in terms:
        if _term_present(text, term) and term not in found:
            found.append(term)
    return found


def _weighted_hits(vacancy: Vacancy, terms: list[str]) -> tuple[int, list[str]]:
    title_text = vacancy.title.lower()
    body_text = vacancy.normalized_text
    skills_text = " ".join(skill.lower() for skill in vacancy.key_skills)

    matched = []
    score = 0
    for term in terms:
        hit = False
        if _term_present(title_text, term):
            score += 3
            hit = True
        if _term_present(skills_text, term):
            score += 2
            hit = True
        elif _term_present(body_text, term):
            score += 1
            hit = True
        if hit and term not in matched:
            matched.append(term)
    return score, matched


def classify_vacancy(vacancy: Vacancy) -> TrackAssessment:
    hard_exclude_title_terms = _matched_terms(vacancy.title.lower(), keywords.HARD_EXCLUDE_TITLE_KEYWORDS)
    hard_exclude_body_terms = _matched_terms(vacancy.normalized_text, keywords.HARD_EXCLUDE_BODY_KEYWORDS)
    ai_signal, ai_terms = _weighted_hits(vacancy, keywords.AI_TITLE_KEYWORDS + keywords.AI_GENERAL_KEYWORDS)
    ruby_signal, ruby_terms = _weighted_hits(vacancy, keywords.RUBY_KEYWORDS)
    backend_signal, backend_terms = _weighted_hits(vacancy, keywords.BACKEND_KEYWORDS)
    product_signal, product_terms = _weighted_hits(vacancy, keywords.PRODUCT_KEYWORDS)
    architect_signal, architect_terms = _weighted_hits(vacancy, keywords.ARCHITECT_KEYWORDS)
    org_leadership_signal, org_leadership_terms = _weighted_hits(vacancy, keywords.ORG_LEADERSHIP_KEYWORDS)
    frontend_signal, frontend_terms = _weighted_hits(vacancy, keywords.FRONTEND_KEYWORDS)
    legacy_stack_signal, legacy_stack_terms = _weighted_hits(vacancy, keywords.LEGACY_STACK_KEYWORDS)
    research_signal, research_terms = _weighted_hits(vacancy, keywords.RESEARCH_KEYWORDS)
    data_science_signal, data_science_terms = _weighted_hits(vacancy, keywords.DATA_SCIENCE_KEYWORDS)
    qa_signal, qa_terms = _weighted_hits(vacancy, keywords.QA_KEYWORDS)
    education_signal, education_terms = _weighted_hits(vacancy, keywords.EDUCATION_KEYWORDS)
    evangelist_signal, evangelist_terms = _weighted_hits(vacancy, keywords.EVANGELIST_KEYWORDS)
    python_strict_signal, python_terms = _weighted_hits(vacancy, keywords.PYTHON_STRICT_KEYWORDS)
    automation_signal, automation_terms = _weighted_hits(vacancy, keywords.AUTOMATION_KEYWORDS)
    automation_only_signal, automation_only_terms = _weighted_hits(vacancy, keywords.AUTOMATION_ONLY_KEYWORDS)

    strong_ai_title = bool(_matched_terms(vacancy.title.lower(), keywords.AI_TITLE_KEYWORDS))
    strong_ruby_title = bool(_matched_terms(vacancy.title.lower(), keywords.RUBY_KEYWORDS))
    product_title = bool(_matched_terms(vacancy.title.lower(), keywords.PRODUCT_KEYWORDS))
    architect_title = bool(_matched_terms(vacancy.title.lower(), keywords.ARCHITECT_KEYWORDS))
    org_leadership_title = bool(_matched_terms(vacancy.title.lower(), keywords.ORG_LEADERSHIP_KEYWORDS))
    frontend_title = bool(_matched_terms(vacancy.title.lower(), keywords.FRONTEND_KEYWORDS))
    research_title = bool(_matched_terms(vacancy.title.lower(), keywords.RESEARCH_KEYWORDS))
    legacy_stack_title = bool(_matched_terms(vacancy.title.lower(), keywords.LEGACY_STACK_KEYWORDS))
    data_science_title = bool(_matched_terms(vacancy.title.lower(), keywords.DATA_SCIENCE_KEYWORDS))
    qa_title = bool(_matched_terms(vacancy.title.lower(), keywords.QA_KEYWORDS))
    education_title = bool(_matched_terms(vacancy.title.lower(), keywords.EDUCATION_KEYWORDS))
    evangelist_title = bool(_matched_terms(vacancy.title.lower(), keywords.EVANGELIST_KEYWORDS))
    python_title = bool(_matched_terms(vacancy.title.lower(), keywords.PYTHON_TITLE_KEYWORDS))

    red_flags: list[str] = []
    if product_signal >= 3 or product_title:
        red_flags.append("product-heavy")
    if architect_signal >= 3 or architect_title:
        red_flags.append("architect-heavy")
    if org_leadership_signal >= 3 or org_leadership_title:
        red_flags.append("org-leadership-heavy")
    if frontend_signal >= 4 or frontend_title:
        red_flags.append("frontend-heavy")
    if legacy_stack_signal >= 3 or legacy_stack_title:
        red_flags.append("legacy-stack-heavy")
    if research_signal >= 5 or research_title:
        red_flags.append("ml-research-heavy")
    if data_science_signal >= 3 or data_science_title:
        red_flags.append("data-science-heavy")
    if qa_signal >= 3 or qa_title:
        red_flags.append("qa-heavy")
    if education_signal >= 2 or education_title:
        red_flags.append("education-heavy")
    if evangelist_signal >= 1 or evangelist_title:
        red_flags.append("evangelist-heavy")
    if python_strict_signal >= 4:
        red_flags.append("strong-python-background-required")
    if "n8n" in vacancy.normalized_text:
        red_flags.append("n8n-production-heavy")
    if hard_exclude_title_terms or hard_exclude_body_terms:
        red_flags.append("hard-excluded-ml-research")

    automation_only = automation_only_signal >= 3 and backend_signal < 5 and ruby_signal < 4
    if automation_only:
        red_flags.append("automation-only")

    if hard_exclude_title_terms or hard_exclude_body_terms:
        track = VacancyTrack.OTHER
    elif architect_title:
        track = VacancyTrack.OTHER
    elif python_title and ruby_signal < 4:
        track = VacancyTrack.OTHER
    elif frontend_title and ruby_signal < 5:
        track = VacancyTrack.OTHER
    elif automation_only:
        track = VacancyTrack.OTHER
    elif (product_title and backend_signal < 5) or (research_title and backend_signal < 5):
        track = VacancyTrack.OTHER
    elif org_leadership_title and ai_signal < 8 and ruby_signal < 5:
        track = VacancyTrack.OTHER
    elif legacy_stack_title and ai_signal < 8 and ruby_signal < 5:
        track = VacancyTrack.OTHER
    elif (data_science_title and backend_signal < 5) or qa_title or education_title or evangelist_title:
        track = VacancyTrack.OTHER
    elif (product_signal >= ai_signal and product_signal >= 3) or (research_signal >= ai_signal and research_signal >= 5):
        track = VacancyTrack.OTHER
    elif org_leadership_signal >= ai_signal and org_leadership_signal >= 3 and backend_signal < 6:
        track = VacancyTrack.OTHER
    elif legacy_stack_signal >= 3 and ai_signal < 8 and backend_signal < 7:
        track = VacancyTrack.OTHER
    elif data_science_signal >= ai_signal and data_science_signal >= 4 and backend_signal < 5:
        track = VacancyTrack.OTHER
    elif ruby_signal >= 5 and ai_signal >= 8 and backend_signal >= 4:
        track = VacancyTrack.MIXED
    elif strong_ai_title and product_signal < 5 and research_signal < 5:
        track = VacancyTrack.AI
    elif ai_signal >= 8 or (ai_signal >= 5 and backend_signal >= 3 and product_signal < 6 and research_signal < 6):
        track = VacancyTrack.AI
    elif strong_ruby_title or ruby_signal >= 5 or (ruby_signal >= 4 and backend_signal >= 2):
        track = VacancyTrack.RUBY
    else:
        track = VacancyTrack.OTHER

    return TrackAssessment(
        track=track,
        ai_signal=ai_signal,
        ruby_signal=ruby_signal,
        backend_signal=backend_signal,
        product_signal=product_signal,
        org_leadership_signal=org_leadership_signal,
        frontend_signal=frontend_signal,
        legacy_stack_signal=legacy_stack_signal,
        research_signal=research_signal,
        data_science_signal=data_science_signal,
        qa_signal=qa_signal,
        education_signal=education_signal,
        evangelist_signal=evangelist_signal,
        python_strict_signal=python_strict_signal,
        automation_signal=automation_signal,
        matched_keywords={
            "ai": ai_terms,
            "ruby": ruby_terms,
            "backend": backend_terms,
            "product": product_terms,
            "architect": architect_terms,
            "org_leadership": org_leadership_terms,
            "frontend": frontend_terms,
            "legacy_stack": legacy_stack_terms,
            "research": research_terms,
            "data_science": data_science_terms,
            "qa": qa_terms,
            "education": education_terms,
            "evangelist": evangelist_terms,
            "python": python_terms,
            "automation": automation_terms,
            "hard_exclude": hard_exclude_title_terms + [term for term in hard_exclude_body_terms if term not in hard_exclude_title_terms],
            "automation_only": automation_only_terms,
        },
        red_flags=red_flags,
    )
