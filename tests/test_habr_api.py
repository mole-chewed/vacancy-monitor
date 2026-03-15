import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from vacancy_monitor.adapters.habr_adapter import HabrCareerAdapter
from vacancy_monitor.models import SearchQuery
from vacancy_monitor.sources.habr_api import parse_job_page, parse_listing_page

SAMPLE_LISTING_HTML = """
<html><body>
<script type="application/json" data-ssr-state="true">
{
  "vacancies": {
    "list": [
      {
        "id": 1000165249,
        "href": "/vacancies/1000165249",
        "title": "Senior Ruby on Rails Developer",
        "remoteWork": true,
        "publishedDate": {"date": "2026-03-12T12:00:00+03:00", "title": "12 марта"},
        "company": {"title": "Ruby Co", "href": "/companies/ruby-co"},
        "employment": "full_time",
        "salary": {"from": 250000, "to": 350000, "currency": "rur", "formatted": "от 250 000 до 350 000 ₽"},
        "divisions": [{"title": "Бэкенд разработчик"}],
        "skills": [{"title": "Ruby on Rails"}, {"title": "PostgreSQL"}],
        "locations": [{"title": "Москва"}],
        "archived": false,
        "hidden": false
      }
    ],
    "meta": {"totalResults": 1, "perPage": 25, "currentPage": 1, "totalPages": 1}
  }
}
</script>
</body></html>
"""

SAMPLE_DETAIL_HTML = """
<html><body>
<script type="application/json" data-ssr-state="true">
{
  "vacancy": {
    "id": 1000165249,
    "href": "/vacancies/1000165249",
    "title": "Senior Ruby on Rails Developer",
    "remoteWork": true,
    "publishedDate": {"date": "2026-03-12T12:00:00+03:00", "title": "12 марта"},
    "company": {"title": "Ruby Co", "href": "/companies/ruby-co"},
    "employment": "full_time",
    "employmentType": "Полный рабочий день",
    "salary": {"from": 250000, "to": 350000, "currency": "rur", "formatted": "от 250 000 до 350 000 ₽"},
    "divisions": [{"title": "Бэкенд разработчик"}],
    "skills": [{"title": "Ruby on Rails"}, {"title": "PostgreSQL"}, {"title": "Sidekiq"}],
    "locations": [{"title": "Москва"}],
    "description": "<p>Rails, Sidekiq, PostgreSQL, API integrations.</p>",
    "archived": false,
    "hidden": false
  }
}
</script>
</body></html>
"""


class HabrCareerApiTestCase(unittest.TestCase):
    def test_parse_listing_page_extracts_vacancies_and_meta(self) -> None:
        items, total_pages = parse_listing_page(SAMPLE_LISTING_HTML, base_url="https://career.habr.com")

        self.assertEqual(total_pages, 1)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], 1000165249)
        self.assertEqual(items[0]["url"], "https://career.habr.com/vacancies/1000165249")
        self.assertEqual(items[0]["company"]["href"], "https://career.habr.com/companies/ruby-co")

    def test_parse_job_page_extracts_structured_vacancy(self) -> None:
        payload = parse_job_page(
            SAMPLE_DETAIL_HTML,
            fallback_url="https://career.habr.com/vacancies/1000165249",
            base_url="https://career.habr.com",
        )

        self.assertEqual(payload["id"], 1000165249)
        self.assertEqual(payload["title"], "Senior Ruby on Rails Developer")
        self.assertIn("Rails", payload["description"])

    def test_adapter_normalizes_habr_jobs(self) -> None:
        class FakeClient:
            def search_jobs(self, query: SearchQuery):
                self.last_query = query
                items, _ = parse_listing_page(SAMPLE_LISTING_HTML, base_url="https://career.habr.com")
                return items

            def get_job(self, external_id: str, *, raw_item=None):
                return parse_job_page(
                    SAMPLE_DETAIL_HTML,
                    fallback_url="https://career.habr.com/vacancies/1000165249",
                    base_url="https://career.habr.com",
                )

        adapter = HabrCareerAdapter(FakeClient())
        vacancies = adapter.search(SearchQuery(source="habr", name="habr_ruby_primary", text="Ruby разработчик", pages=1))

        self.assertEqual(len(vacancies), 1)
        self.assertEqual(vacancies[0].external_id, "habr:1000165249")
        self.assertEqual(vacancies[0].source, "habr_html:habr_ruby_primary")
        self.assertEqual(vacancies[0].company, "Ruby Co")
        self.assertEqual(vacancies[0].salary_from, 250000)


if __name__ == "__main__":
    unittest.main()
