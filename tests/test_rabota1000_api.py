import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from vacancy_monitor.adapters.rabota1000_adapter import Rabota1000Adapter
from vacancy_monitor.models import SearchQuery, WorkFormat
from vacancy_monitor.sources.rabota1000_api import parse_listing_page

SAMPLE_LISTING_HTML = (FIXTURES / "rabota1000_listing.html").read_text(encoding="utf-8")


class Rabota1000ApiTestCase(unittest.TestCase):
    def test_parse_listing_page_extracts_jobs(self) -> None:
        jobs = parse_listing_page(SAMPLE_LISTING_HTML, base_url="https://rabota1000.ru")

        self.assertEqual(len(jobs), 2)
        self.assertEqual(jobs[0]["id"], "88633992")
        self.assertEqual(jobs[0]["company"], "Appbooster")
        self.assertEqual(jobs[0]["source_site"], "hh.ru")
        self.assertEqual(jobs[1]["source_site"], "careerist.ru")

    def test_adapter_normalizes_rabota1000_jobs(self) -> None:
        class FakeClient:
            def search_jobs(self, query: SearchQuery):
                self.last_query = query
                return parse_listing_page(SAMPLE_LISTING_HTML, base_url="https://rabota1000.ru")

            def resolve_job_type(self, query: SearchQuery):
                return "6" if query.schedule == "remote" else None

        adapter = Rabota1000Adapter(FakeClient())
        vacancies = adapter.search(
            SearchQuery(
                source="rabota1000",
                name="rabota1000_ruby_primary",
                text="Ruby on Rails",
                pages=1,
                schedule="remote",
            )
        )

        self.assertEqual(len(vacancies), 2)
        self.assertEqual(vacancies[0].external_id, "rabota1000:88633992")
        self.assertEqual(vacancies[0].source, "rabota1000_html:rabota1000_ruby_primary")
        self.assertEqual(vacancies[0].salary_from, 260000)
        self.assertEqual(vacancies[0].work_format, WorkFormat.REMOTE)
        self.assertIn("sidekiq", vacancies[0].normalized_text)


if __name__ == "__main__":
    unittest.main()
