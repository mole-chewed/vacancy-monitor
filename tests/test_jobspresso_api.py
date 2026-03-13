from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from hh_monitor.adapters.jobspresso_adapter import JobspressoAdapter
from hh_monitor.models import SearchQuery, WorkFormat
from hh_monitor.sources.jobspresso_api import parse_search_page


SAMPLE_HTML = """
<article id="post-27421" class="row post-27421 job_listing type-job_listing status-publish has-post-thumbnail hentry job_listing_category-full-time job_listing_type-developer job-type-engineer">
  <header class="entry-header col-sm-3 col-xs-12">
    <div class="entry-author">
      Written by <a class="author-link entry-author__link" href="https://jobspresso.co/author/jobspresso/" rel="author">Bold Penguin<br>⚲&nbsp;Anywhere in US</a>
    </div>
    <div class="entry-meta">
      <data class="entry-date entry-meta__date" value="November 1"><a href="https://jobspresso.co/job/senior-ruby-on-rails-software-engineer/" rel="bookmark">November 1</a></data>
    </div>
  </header>
  <div class="entry col-sm-9 col-xs-12">
    <h2 class="entry-title"><a href="https://jobspresso.co/job/senior-ruby-on-rails-software-engineer/" rel="bookmark">Senior Ruby on Rails Software Engineer</a></h2>
    <div class="entry-summary"><p>Build Rails services and backend APIs.</p><p><a href="https://jobspresso.co/job/senior-ruby-on-rails-software-engineer/" rel="bookmark" class="button button--size-medium">Continue Reading</a></p></div>
  </div>
</article>
<article id="post-19021" class="row post-19021 job_listing type-job_listing status-publish has-post-thumbnail hentry job_listing_category-full-time job_listing_type-developer job-type-engineer job_position_filled">
  <header class="entry-header col-sm-3 col-xs-12">
    <div class="entry-author">
      Written by <a class="author-link entry-author__link" href="https://jobspresso.co/author/jobspresso/" rel="author">SurveyMonkey<br>⚲&nbsp;Pacific Time Zone</a>
    </div>
    <div class="entry-meta">
      <data class="entry-date entry-meta__date" value="February 6"><a href="https://jobspresso.co/job/ruby-rails-engineer/" rel="bookmark">February 6</a></data>
    </div>
  </header>
  <div class="entry col-sm-9 col-xs-12">
    <h2 class="entry-title"><a href="https://jobspresso.co/job/ruby-rails-engineer/" rel="bookmark">Ruby on Rails Engineer</a></h2>
    <div class="entry-summary"><p>Old filled job.</p></div>
  </div>
</article>
"""


class JobspressoApiTestCase(unittest.TestCase):
    def test_parse_search_page_skips_filled_roles(self) -> None:
        jobs = parse_search_page(SAMPLE_HTML)

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["id"], "27421")
        self.assertEqual(jobs[0]["company"], "Bold Penguin")
        self.assertEqual(jobs[0]["employment_type"], "Full-Time")

    def test_adapter_normalizes_jobspresso_jobs(self) -> None:
        class FakeClient:
            def search_jobs(self, query_text: str, pages: int = 1):
                self.last_query = query_text
                self.last_pages = pages
                return parse_search_page(SAMPLE_HTML)

            def get_job(self, external_id: str):
                raise NotImplementedError

        adapter = JobspressoAdapter(FakeClient())
        vacancies = adapter.search(
            SearchQuery(source="jobspresso", name="jobspresso_ruby_primary", text="ruby on rails", pages=2)
        )

        self.assertEqual(len(vacancies), 1)
        self.assertEqual(vacancies[0].external_id, "jobspresso:27421")
        self.assertEqual(vacancies[0].source, "jobspresso_html:jobspresso_ruby_primary")
        self.assertEqual(vacancies[0].work_format, WorkFormat.REMOTE)
        self.assertIn("Rails services", vacancies[0].description_raw)


if __name__ == "__main__":
    unittest.main()
