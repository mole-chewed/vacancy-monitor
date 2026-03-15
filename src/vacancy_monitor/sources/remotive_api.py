from __future__ import annotations

import logging
import re
from typing import Any

import requests

LOGGER = logging.getLogger(__name__)
GROUP_RE = re.compile(r"\(([^()]+)\)")
OR_SPLIT_RE = re.compile(r"\s+OR\s+", re.IGNORECASE)
STOP_WORDS = {"and", "or", "not"}


class RemotiveApiError(RuntimeError):
    """Raised when the Remotive API responds with an unusable payload."""


class RemotiveClient:
    def __init__(self, base_url: str, user_agent: str, timeout: int = 20) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent, "Accept": "application/json"})
        self._cached_jobs: list[dict[str, Any]] | None = None

    def search_jobs(self, query_text: str) -> list[dict[str, Any]]:
        jobs = self.list_jobs()
        groups = _extract_query_groups(query_text)
        if not groups:
            return jobs
        return [job for job in jobs if _matches_query(job, groups)]

    def list_jobs(self) -> list[dict[str, Any]]:
        if self._cached_jobs is not None:
            return list(self._cached_jobs)
        response = self.session.get(f"{self.base_url}/api/remote-jobs", timeout=self.timeout)
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:  # pragma: no cover - depends on live API behavior
            detail = response.text[:500]
            raise RemotiveApiError(f"Remotive API request failed: {response.status_code} {detail}") from exc
        payload = response.json()
        if not isinstance(payload, dict):
            raise RemotiveApiError("Remotive API returned a non-object JSON payload")
        jobs = payload.get("jobs")
        if not isinstance(jobs, list):
            raise RemotiveApiError("Remotive API response is missing jobs list")
        self._cached_jobs = [item for item in jobs if isinstance(item, dict) and item.get("id")]
        LOGGER.info("Fetched %s jobs from Remotive", len(self._cached_jobs))
        return list(self._cached_jobs)

    def get_job(self, external_id: str) -> dict[str, Any]:
        target = external_id.removeprefix("remotive:")
        for job in self.list_jobs():
            if str(job.get("id")) == target:
                return job
        raise RemotiveApiError(f"Remotive job {external_id} was not found in the current API payload")


def _normalize(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def _extract_query_groups(query_text: str) -> list[list[str]]:
    raw_groups = GROUP_RE.findall(query_text)
    groups = raw_groups or [query_text]
    extracted: list[list[str]] = []
    for group in groups:
        terms = []
        for raw_term in OR_SPLIT_RE.split(group):
            normalized = _normalize(raw_term.strip().strip('"').strip("'").replace("(", "").replace(")", ""))
            if not normalized or normalized in STOP_WORDS:
                continue
            terms.append(normalized)
        if terms:
            extracted.append(terms)
    return extracted


def _matches_query(job: dict[str, Any], groups: list[list[str]]) -> bool:
    tags = job.get("tags") or []
    text_parts = [
        str(job.get("title") or ""),
        str(job.get("description") or ""),
        str(job.get("candidate_required_location") or ""),
        str(job.get("company_name") or ""),
        " ".join(str(tag) for tag in tags if tag),
    ]
    haystack = _normalize(" ".join(text_parts))
    return all(any(term in haystack for term in group) for group in groups)
