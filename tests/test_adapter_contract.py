import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from vacancy_monitor.adapters.habr_adapter import HabrCareerAdapter
from vacancy_monitor.adapters.hh_adapter import HHAdapter
from vacancy_monitor.adapters.linkedin_adapter import LinkedInAdapter
from vacancy_monitor.adapters.remoteok_adapter import RemoteOkAdapter
from vacancy_monitor.adapters.remotive_adapter import RemotiveAdapter
from vacancy_monitor.adapters.weworkremotely_adapter import WeWorkRemotelyAdapter
from vacancy_monitor.models import SearchQuery
from vacancy_monitor.normalization import vacancy_from_payload
from vacancy_monitor.pipeline import fetch_search_queries
from vacancy_monitor.sources.habr_api import parse_job_page as parse_habr_job_page
from vacancy_monitor.sources.habr_api import parse_listing_page as parse_habr_listing_page
from vacancy_monitor.sources.weworkremotely_api import parse_job_page as parse_wwr_job_page
from vacancy_monitor.sources.weworkremotely_api import parse_listing_page as parse_wwr_listing_page


def _read_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _read_json_fixture(name: str) -> object:
    return json.loads(_read_fixture(name))


class AdapterCapabilitiesTestCase(unittest.TestCase):
    def test_adapters_expose_explicit_capabilities(self) -> None:
        self.assertTrue(HHAdapter(object()).capabilities.supports_detail_hydration)
        self.assertTrue(HHAdapter(object()).capabilities.supports_remote_filtering)
        self.assertTrue(HabrCareerAdapter(object()).capabilities.supports_pagination)
        self.assertFalse(HabrCareerAdapter(object()).capabilities.supports_remote_filtering)
        self.assertTrue(RemoteOkAdapter(object()).capabilities.supports_remote_filtering)
        self.assertTrue(RemotiveAdapter(object()).capabilities.supports_detail_hydration)
        self.assertTrue(WeWorkRemotelyAdapter(object()).capabilities.requires_source_url)
        self.assertFalse(LinkedInAdapter().capabilities.supports_search)

    def test_fetch_search_queries_rejects_non_searchable_adapters(self) -> None:
        class StubProfile:
            ignored_vacancy_ids_by_source: dict[str, frozenset[str]] = {}

        with self.assertRaisesRegex(RuntimeError, "does not support search"):
            fetch_search_queries(
                {"linkedin": LinkedInAdapter()},
                [SearchQuery(source="linkedin", name="linkedin_ruby", text="ruby")],
                profile=StubProfile(),
            )


class ProviderFixtureParsingTestCase(unittest.TestCase):
    def test_hh_fixture_normalizes_to_expected_vacancy(self) -> None:
        vacancy = vacancy_from_payload(_read_json_fixture("hh_search_item.json"), source="hh_api:ruby_primary")

        self.assertEqual(vacancy.external_id, "101")
        self.assertEqual(vacancy.company, "Ruby Co")
        self.assertEqual(vacancy.salary_from, 400000)
        self.assertIn("Rails", vacancy.description_raw)

    def test_habr_fixtures_parse_and_normalize(self) -> None:
        listing, total_pages = parse_habr_listing_page(_read_fixture("habr_listing.html"), base_url="https://career.habr.com")
        detail = parse_habr_job_page(
            _read_fixture("habr_detail.html"),
            fallback_url="https://career.habr.com/vacancies/1000165249",
            base_url="https://career.habr.com",
        )

        class FakeClient:
            def search_jobs(self, query: SearchQuery):
                return listing

            def get_job(self, external_id: str, *, raw_item=None):
                return detail

        vacancy = HabrCareerAdapter(FakeClient()).normalize({**listing[0], "_query_name": "habr_ruby_primary"}, detail)

        self.assertEqual(total_pages, 1)
        self.assertEqual(vacancy.external_id, "habr:1000165249")
        self.assertIn("Sidekiq", vacancy.description_raw)

    def test_remoteok_fixture_normalizes_to_expected_vacancy(self) -> None:
        payload = _read_json_fixture("remoteok_jobs.json")[1]

        class FakeClient:
            def search_jobs(self, query_text: str):
                return [payload]

            def get_job(self, external_id: str):
                return payload

        vacancy = RemoteOkAdapter(FakeClient()).search(
            SearchQuery(source="remoteok", name="remoteok_ruby_primary", text="Ruby Rails backend")
        )[0]

        self.assertEqual(vacancy.external_id, "remoteok:101")
        self.assertEqual(vacancy.salary_to, 120000)
        self.assertIn("ruby on rails", vacancy.normalized_text.lower())

    def test_remotive_fixture_normalizes_to_expected_vacancy(self) -> None:
        payload = _read_json_fixture("remotive_jobs.json")["jobs"][0]

        class FakeClient:
            def search_jobs(self, query_text: str):
                return [payload]

            def get_job(self, external_id: str):
                return payload

        vacancy = RemotiveAdapter(FakeClient()).search(
            SearchQuery(source="remotive", name="remotive_ruby_primary", text="Ruby Rails backend")
        )[0]

        self.assertEqual(vacancy.external_id, "remotive:101")
        self.assertEqual(vacancy.company, "Ruby Co")
        self.assertEqual(vacancy.employment_type, "full_time")

    def test_weworkremotely_fixtures_parse_and_normalize(self) -> None:
        listing = parse_wwr_listing_page(_read_fixture("weworkremotely_listing.html"), base_url="https://weworkremotely.com")
        detail = parse_wwr_job_page(
            _read_fixture("weworkremotely_detail.html"),
            fallback_url="https://weworkremotely.com/remote-jobs/onthegosystems-senior-ruby-on-rails-developer-1",
        )

        class FakeClient:
            def fetch_listing_page(self, url: str):
                return listing

            def get_job(self, external_id: str, *, raw_item=None):
                return detail

        vacancy = WeWorkRemotelyAdapter(FakeClient()).normalize(
            {**listing[0], "_query_name": "weworkremotely_ruby_primary"},
            detail,
        )

        self.assertTrue(any("Russian Federation" in item for item in listing[0]["categories"]))
        self.assertEqual(vacancy.external_id, "weworkremotely:onthegosystems-senior-ruby-on-rails-developer-1")
        self.assertIn("Sidekiq", vacancy.description_raw)


if __name__ == "__main__":
    unittest.main()
