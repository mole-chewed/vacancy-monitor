from __future__ import annotations

from html import unescape
import re
from typing import Any

import requests


JOB_BLOCK_RE = re.compile(r'<li class="[^"]*new-listing-container[^"]*">(.*?)</li>', re.DOTALL)
HREF_RE = re.compile(r'href="(?P<href>/remote-jobs/[^"]+)"')
TITLE_RE = re.compile(r'new-listing__header__title__text">(?P<title>.*?)</span>', re.DOTALL)
COMPANY_RE = re.compile(r'new-listing__company-name">\s*(?P<company>.*?)\s*(?:<img|</p>)', re.DOTALL)
LOCATION_RE = re.compile(r'new-listing__company-headquarters">\s*(?P<location>.*?)\s*<i ', re.DOTALL)
CATEGORY_RE = re.compile(r'new-listing__categories__category[^"]*">\s*(?P<category>.*?)\s*</p>', re.DOTALL)
DATE_RE = re.compile(r'new-listing__header__icons__date">\s*(?P<date>.*?)\s*</p>', re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")


class WeWorkRemotelyApiError(RuntimeError):
    """Raised when We Work Remotely responds with an unusable payload."""


class WeWorkRemotelyClient:
    def __init__(self, base_url: str, user_agent: str, timeout: int = 20) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})

    def fetch_listing_page(self, url: str) -> list[dict[str, Any]]:
        response = self.session.get(url, timeout=self.timeout)
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:  # pragma: no cover - depends on live site behavior
            detail = response.text[:500]
            raise WeWorkRemotelyApiError(
                f"We Work Remotely request failed: {response.status_code} {detail}"
            ) from exc
        return parse_listing_page(response.text, base_url=self.base_url)


def parse_listing_page(html: str, *, base_url: str) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    for block in JOB_BLOCK_RE.findall(html):
        href_match = HREF_RE.search(block)
        title_match = TITLE_RE.search(block)
        company_match = COMPANY_RE.search(block)
        if not href_match or not title_match or not company_match:
            continue
        href = href_match.group("href")
        categories = [_clean_text(match) for match in CATEGORY_RE.findall(block)]
        jobs.append(
            {
                "id": href.rsplit("/", 1)[-1],
                "url": f"{base_url}{href}",
                "title": _clean_text(title_match.group("title")),
                "company": _clean_text(company_match.group("company")),
                "location": _clean_text(LOCATION_RE.search(block).group("location")) if LOCATION_RE.search(block) else "Remote",
                "categories": [item for item in categories if item],
                "listed_at": _clean_text(DATE_RE.search(block).group("date")) if DATE_RE.search(block) else None,
            }
        )
    return jobs


def _clean_text(value: str) -> str:
    no_tags = TAG_RE.sub(" ", unescape(value))
    return WHITESPACE_RE.sub(" ", no_tags).strip()
