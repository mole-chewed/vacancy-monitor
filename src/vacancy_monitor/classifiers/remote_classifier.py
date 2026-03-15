from __future__ import annotations

import re
from html import unescape

from vacancy_monitor.keywords import HYBRID_KEYWORDS, ONSITE_KEYWORDS, REMOTE_KEYWORDS
from vacancy_monitor.models import WorkFormat

WHITESPACE_RE = re.compile(r"\s+")
HTML_TAG_RE = re.compile(r"<[^>]+>")


def _normalize_for_match(value: str | None) -> str:
    if not value:
        return ""
    no_html = HTML_TAG_RE.sub(" ", unescape(value))
    return WHITESPACE_RE.sub(" ", no_html).strip().lower()


def classify_remote_type(*values: str) -> WorkFormat:
    text = " ".join(_normalize_for_match(value) for value in values if value)
    if any(keyword in text for keyword in REMOTE_KEYWORDS):
        return WorkFormat.REMOTE
    if any(keyword in text for keyword in HYBRID_KEYWORDS):
        return WorkFormat.HYBRID
    if any(keyword in text for keyword in ONSITE_KEYWORDS):
        return WorkFormat.ONSITE
    return WorkFormat.UNKNOWN
