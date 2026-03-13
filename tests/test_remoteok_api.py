from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from hh_monitor.adapters.remoteok_adapter import RemoteOkAdapter
from hh_monitor.models import SearchQuery, WorkFormat
from hh_monitor.sources.remoteok_api import RemoteOkApiError, RemoteOkClient


class FakeResponse:
    def __init__(self, payload, status_code: int = 200, text: str = "") -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = text

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(f"status {self.status_code}")

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.headers = {}

    def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        if not self.responses:
            raise AssertionError("No fake responses left")
        return self.responses.pop(0)


class RemoteOkClientTestCase(unittest.TestCase):
    def test_search_jobs_filters_using_boolean_like_groups(self) -> None:
        session = FakeSession(
            [
                FakeResponse(
                    [
                        {"legal": "Remote OK API"},
                        {
                            "id": 101,
                            "slug": "senior-ruby",
                            "position": "Senior Ruby on Rails Developer",
                            "company": "Ruby Co",
                            "location": "Worldwide",
                            "description": "Build backend APIs with Rails and PostgreSQL.",
                            "tags": ["Ruby", "Ruby on Rails", "PostgreSQL", "API"],
                            "url": "https://remoteok.com/remote-jobs/101",
                        },
                        {
                            "id": 202,
                            "slug": "frontend-react",
                            "position": "Frontend React Engineer",
                            "company": "Frontend Co",
                            "location": "Worldwide",
                            "description": "React, TypeScript, CSS",
                            "tags": ["React", "Frontend"],
                            "url": "https://remoteok.com/remote-jobs/202",
                        },
                    ]
                )
            ]
        )
        client = RemoteOkClient(base_url="https://remoteok.com", user_agent="test-agent")
        client.session = session

        jobs = client.search_jobs('((Ruby OR "Ruby on Rails" OR Rails OR RoR) AND (backend OR API OR PostgreSQL OR Sidekiq))')

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["id"], 101)
        self.assertEqual(session.calls[0]["url"], "https://remoteok.com/api")

    def test_get_job_raises_when_missing(self) -> None:
        session = FakeSession([FakeResponse([{"id": 101, "slug": "senior-ruby", "url": "https://remoteok.com/101"}])])
        client = RemoteOkClient(base_url="https://remoteok.com", user_agent="test-agent")
        client.session = session

        with self.assertRaises(RemoteOkApiError):
            client.get_job("remoteok:404")


class RemoteOkAdapterTestCase(unittest.TestCase):
    def test_adapter_normalizes_remoteok_jobs(self) -> None:
        class FakeClient:
            def search_jobs(self, query_text: str):
                self.last_query = query_text
                return [
                    {
                        "id": 101,
                        "slug": "senior-ruby",
                        "position": "Senior Ruby on Rails Developer",
                        "company": "Ruby Co",
                        "location": "Worldwide",
                        "description": "Build backend APIs with Rails and PostgreSQL.",
                        "tags": ["Ruby", "Ruby on Rails", "PostgreSQL", "API"],
                        "url": "https://remoteok.com/remote-jobs/101",
                        "salary_min": 80000,
                        "salary_max": 120000,
                        "date": "2026-03-10T10:00:00+00:00",
                    }
                ]

            def get_job(self, external_id: str):
                return {}

        adapter = RemoteOkAdapter(FakeClient())
        vacancies = adapter.search(
            SearchQuery(source="remoteok", name="remoteok_ruby_primary", text="Ruby Rails backend", fetch_all=True)
        )

        self.assertEqual(len(vacancies), 1)
        self.assertEqual(vacancies[0].external_id, "remoteok:101")
        self.assertEqual(vacancies[0].source, "remoteok_api:remoteok_ruby_primary")
        self.assertEqual(vacancies[0].work_format, WorkFormat.REMOTE)
        self.assertEqual(vacancies[0].salary_from, 80000)
        self.assertEqual(vacancies[0].salary_to, 120000)


if __name__ == "__main__":
    unittest.main()
