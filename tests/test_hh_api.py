from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from hh_monitor.models import SearchQuery
from hh_monitor.sources.hh_api import HeadHunterApiError, HeadHunterClient


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


class HeadHunterClientTestCase(unittest.TestCase):
    def test_search_vacancies_by_query_builds_expected_requests(self) -> None:
        session = FakeSession(
            [
                FakeResponse(
                    {
                        "items": [
                            {
                                "id": "101",
                                "name": "AI Backend Engineer",
                                "alternate_url": "https://hh.example/101",
                                "employer": {"name": "AI Team"},
                                "salary": {"from": 400000, "to": 500000, "currency": "RUR"},
                                "area": {"name": "Remote"},
                                "schedule": {"name": "Remote"},
                                "employment": {"name": "Full-time"},
                                "experience": {"name": "3-6 years"},
                                "description": "LLM integrations and RAG pipelines.",
                                "key_skills": [{"name": "LLM"}, {"name": "RAG"}],
                            }
                        ]
                    }
                )
            ]
        )
        client = HeadHunterClient(base_url="https://api.hh.ru", user_agent="test-agent")
        client.session = session

        vacancies = client.search_vacancies_by_query(
            SearchQuery(
                name="ai_primary",
                text="LLM backend",
                priority=10,
                area=113,
                per_page=50,
                pages=1,
                detailed=False,
                order_by="publication_time",
                search_field="name",
            )
        )

        self.assertEqual(len(vacancies), 1)
        self.assertEqual(vacancies[0].source, "hh_api:ai_primary")
        self.assertEqual(session.calls[0]["url"], "https://api.hh.ru/vacancies")
        self.assertEqual(session.calls[0]["params"]["text"], "LLM backend")
        self.assertEqual(session.calls[0]["params"]["page"], 0)
        self.assertEqual(session.calls[0]["params"]["per_page"], 50)
        self.assertEqual(session.calls[0]["params"]["area"], 113)
        self.assertEqual(session.calls[0]["params"]["order_by"], "publication_time")
        self.assertEqual(session.calls[0]["params"]["search_field"], "name")

    def test_search_vacancies_by_query_fetches_details_when_requested(self) -> None:
        session = FakeSession(
            [
                FakeResponse({"items": [{"id": "101", "name": "AI Backend Engineer"}]}),
                FakeResponse(
                    {
                        "id": "101",
                        "name": "AI Backend Engineer",
                        "alternate_url": "https://hh.example/101",
                        "employer": {"name": "AI Team"},
                        "salary": {"from": 400000, "to": 500000, "currency": "RUR"},
                        "area": {"name": "Remote"},
                        "schedule": {"name": "Remote"},
                        "employment": {"name": "Full-time"},
                        "experience": {"name": "3-6 years"},
                        "description": "LLM integrations and RAG pipelines.",
                        "key_skills": [{"name": "LLM"}, {"name": "RAG"}],
                    }
                ),
            ]
        )
        client = HeadHunterClient(base_url="https://api.hh.ru", user_agent="test-agent")
        client.session = session

        vacancies = client.search_vacancies_by_query(
            SearchQuery(name="ai_primary", text="LLM backend", priority=10, pages=1, detailed=True)
        )

        self.assertEqual(len(vacancies), 1)
        self.assertEqual(session.calls[1]["url"], "https://api.hh.ru/vacancies/101")

    def test_raises_clear_error_on_bad_response(self) -> None:
        session = FakeSession([FakeResponse({"error": "rate limit"}, status_code=429, text="too many requests")])
        client = HeadHunterClient(base_url="https://api.hh.ru", user_agent="test-agent")
        client.session = session

        with self.assertRaises(HeadHunterApiError):
            client.search_vacancies_by_query(SearchQuery(name="ai_primary", text="LLM backend", priority=10))


if __name__ == "__main__":
    unittest.main()
