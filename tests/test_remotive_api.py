from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from hh_monitor.adapters.remotive_adapter import RemotiveAdapter
from hh_monitor.models import SearchQuery, WorkFormat
from hh_monitor.sources.remotive_api import RemotiveApiError, RemotiveClient


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


class RemotiveClientTestCase(unittest.TestCase):
    def test_search_jobs_filters_using_boolean_like_groups(self) -> None:
        session = FakeSession(
            [
                FakeResponse(
                    {
                        "jobs": [
                            {
                                "id": 101,
                                "title": "Senior Ruby on Rails Engineer",
                                "company_name": "Ruby Co",
                                "candidate_required_location": "Worldwide",
                                "description": "Build backend APIs with Rails and PostgreSQL.",
                                "tags": ["Ruby", "Ruby on Rails", "PostgreSQL", "API"],
                                "url": "https://remotive.com/remote-jobs/software-dev/senior-ruby-on-rails-engineer-101",
                            },
                            {
                                "id": 202,
                                "title": "Frontend React Engineer",
                                "company_name": "Frontend Co",
                                "candidate_required_location": "USA",
                                "description": "React, TypeScript, CSS",
                                "tags": ["React", "Frontend"],
                                "url": "https://remotive.com/remote-jobs/software-dev/frontend-react-engineer-202",
                            },
                        ]
                    }
                )
            ]
        )
        client = RemotiveClient(base_url="https://remotive.com", user_agent="test-agent")
        client.session = session

        jobs = client.search_jobs('((Ruby OR "Ruby on Rails" OR Rails OR RoR) AND (backend OR API OR PostgreSQL OR Sidekiq))')

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["id"], 101)
        self.assertEqual(session.calls[0]["url"], "https://remotive.com/api/remote-jobs")

    def test_get_job_raises_when_missing(self) -> None:
        session = FakeSession([FakeResponse({"jobs": [{"id": 101, "url": "https://remotive.com/101"}]})])
        client = RemotiveClient(base_url="https://remotive.com", user_agent="test-agent")
        client.session = session

        with self.assertRaises(RemotiveApiError):
            client.get_job("remotive:404")


class RemotiveAdapterTestCase(unittest.TestCase):
    def test_adapter_normalizes_remotive_jobs(self) -> None:
        class FakeClient:
            def search_jobs(self, query_text: str):
                self.last_query = query_text
                return [
                    {
                        "id": 101,
                        "title": "Senior Ruby on Rails Engineer",
                        "company_name": "Ruby Co",
                        "candidate_required_location": "Worldwide",
                        "description": "Build backend APIs with Rails and PostgreSQL.",
                        "tags": ["Ruby", "Ruby on Rails", "PostgreSQL", "API"],
                        "url": "https://remotive.com/remote-jobs/software-dev/senior-ruby-on-rails-engineer-101",
                        "publication_date": "2026-03-10T10:00:00",
                        "job_type": "full_time",
                    }
                ]

            def get_job(self, external_id: str):
                return {}

        adapter = RemotiveAdapter(FakeClient())
        vacancies = adapter.search(
            SearchQuery(source="remotive", name="remotive_ruby_primary", text="Ruby Rails backend", fetch_all=True)
        )

        self.assertEqual(len(vacancies), 1)
        self.assertEqual(vacancies[0].external_id, "remotive:101")
        self.assertEqual(vacancies[0].source, "remotive_api:remotive_ruby_primary")
        self.assertEqual(vacancies[0].work_format, WorkFormat.REMOTE)
        self.assertEqual(vacancies[0].employment_type, "full_time")


if __name__ == "__main__":
    unittest.main()
