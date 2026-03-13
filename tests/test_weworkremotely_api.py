from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from hh_monitor.adapters.weworkremotely_adapter import WeWorkRemotelyAdapter
from hh_monitor.models import SearchQuery, WorkFormat
from hh_monitor.sources.weworkremotely_api import parse_job_page, parse_listing_page


SAMPLE_HTML = """
<section class="jobs">
  <article>
    <ul>
      <li class=" new-listing-container feature ">
        <a class="listing-link--unlocked" href="/remote-jobs/onthegosystems-senior-ruby-on-rails-developer-1">
          <div class=" new-listing paid-logo ">
            <div class="new-listing__header">
              <h3 class="new-listing__header__title">
                <span class="new-listing__header__title__text">Senior Ruby on Rails Developer</span>
              </h3>
              <div class=" new-listing__header__icons ">
                <p class="new-listing__header__icons__date"> 28d </p>
              </div>
            </div>
            <p class="new-listing__company-name"> OnTheGoSystems <img alt="" /></p>
            <p class="new-listing__company-headquarters"> Remote <i class="fa-solid fa-location-dot"></i></p>
            <div class="new-listing__categories">
              <p class="new-listing__categories__category"> Full-Time </p>
              <p class="new-listing__categories__category"> 🇷🇺 Russian Federation </p>
              <p class="new-listing__categories__category"> 🇺🇦 Ukraine </p>
            </div>
          </div>
        </a>
      </li>
      <li class=" new-listing-container ">
        <a class="listing-link--unlocked" href="/remote-jobs/curotec-full-stack-developer-ruby-on-rails-react">
          <div class=" new-listing ">
            <div class="new-listing__header">
              <h3 class="new-listing__header__title">
                <span class="new-listing__header__title__text">Full Stack Developer (Ruby on Rails/React)</span>
              </h3>
              <div class=" new-listing__header__icons paid-logo ">
                <p class="new-listing__header__icons__date"> 5d </p>
              </div>
            </div>
            <p class="new-listing__company-name"> Curotec <img alt="" /></p>
            <p class="new-listing__company-headquarters"> Wayne, PA <i class="fa-solid fa-location-dot"></i></p>
            <div class="new-listing__categories">
              <p class="new-listing__categories__category"> Full-Time </p>
              <p class="new-listing__categories__category"> Anywhere in the World </p>
            </div>
          </div>
        </a>
      </li>
    </ul>
  </article>
</section>
"""

SAMPLE_DETAIL_HTML = """
<html>
  <head>
    <script type="application/ld+json">
      {
        "@context": "http://schema.org",
        "@type": "JobPosting",
        "title": "Senior Ruby on Rails Developer",
        "description": "<p>Build and maintain Ruby on Rails applications with PostgreSQL and Sidekiq.</p>",
        "hiringOrganization": {"@type": "Organization", "name": "OnTheGoSystems"},
        "jobLocation": {"@type": "Place", "address": "Remote"},
        "url": "https://weworkremotely.com/remote-jobs/onthegosystems-senior-ruby-on-rails-developer-1"
      }
    </script>
  </head>
</html>
"""


class WeWorkRemotelyApiTestCase(unittest.TestCase):
    def test_parse_listing_page_extracts_jobs(self) -> None:
        jobs = parse_listing_page(SAMPLE_HTML, base_url="https://weworkremotely.com")

        self.assertEqual(len(jobs), 2)
        self.assertEqual(jobs[0]["id"], "onthegosystems-senior-ruby-on-rails-developer-1")
        self.assertEqual(jobs[0]["company"], "OnTheGoSystems")
        self.assertIn("Russian Federation", jobs[0]["categories"][1])
        self.assertEqual(jobs[1]["url"], "https://weworkremotely.com/remote-jobs/curotec-full-stack-developer-ruby-on-rails-react")

    def test_adapter_normalizes_weworkremotely_jobs(self) -> None:
        class FakeClient:
            def fetch_listing_page(self, url: str):
                self.last_url = url
                return parse_listing_page(SAMPLE_HTML, base_url="https://weworkremotely.com")

        adapter = WeWorkRemotelyAdapter(FakeClient())
        vacancies = adapter.search(
            SearchQuery(
                source="weworkremotely",
                name="weworkremotely_ruby_primary",
                text="Ruby on Rails",
                source_url="https://weworkremotely.com/remote-ruby-on-rails-jobs",
            )
        )

        self.assertEqual(len(vacancies), 2)
        self.assertEqual(vacancies[0].external_id, "weworkremotely:onthegosystems-senior-ruby-on-rails-developer-1")
        self.assertEqual(vacancies[0].source, "weworkremotely_html:weworkremotely_ruby_primary")
        self.assertEqual(vacancies[0].work_format, WorkFormat.REMOTE)
        self.assertIn("Russian Federation", vacancies[0].requirements)

    def test_parse_job_page_extracts_description(self) -> None:
        detail = parse_job_page(
            SAMPLE_DETAIL_HTML,
            fallback_url="https://weworkremotely.com/remote-jobs/onthegosystems-senior-ruby-on-rails-developer-1",
        )

        self.assertIn("Ruby on Rails applications", detail["description"])
        self.assertEqual(detail["company"], "OnTheGoSystems")
        self.assertEqual(detail["location"], "Remote")

    def test_adapter_merges_listing_and_detail_payloads(self) -> None:
        class FakeClient:
            def fetch_listing_page(self, url: str):
                return parse_listing_page(SAMPLE_HTML, base_url="https://weworkremotely.com")

            def get_job(self, external_id: str, *, raw_item=None):
                self.last_external_id = external_id
                self.last_raw_item = raw_item
                return parse_job_page(SAMPLE_DETAIL_HTML, fallback_url=raw_item["url"])

        adapter = WeWorkRemotelyAdapter(FakeClient())
        raw_listing = parse_listing_page(SAMPLE_HTML, base_url="https://weworkremotely.com")[0]
        vacancy = adapter.normalize(
            {**raw_listing, "_query_name": "weworkremotely_ruby_primary"},
            adapter.fetch_details("weworkremotely:onthegosystems-senior-ruby-on-rails-developer-1", raw_item=raw_listing),
        )

        self.assertIn("PostgreSQL and Sidekiq", vacancy.description_raw)
        self.assertEqual(vacancy.company, "OnTheGoSystems")


if __name__ == "__main__":
    unittest.main()
