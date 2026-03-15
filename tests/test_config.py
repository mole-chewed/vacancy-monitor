from pathlib import Path
import tempfile
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from hh_monitor.config import load_profile, vacancy_is_ignored
from hh_monitor.normalization import vacancy_from_weworkremotely_payload


class ConfigTestCase(unittest.TestCase):
    def test_profile_loads_search_queries_in_priority_order(self) -> None:
        profile = load_profile("config/profile.example.toml")

        self.assertEqual(
            [query.name for query in profile.search_queries],
            [
                "ruby_primary",
                "weworkremotely_ruby_primary",
                "habr_ruby_primary",
                "remotive_ruby_primary",
                "remoteok_ruby_primary",
                "remotive_ai_transition",
                "habr_ai_transition",
                "ai_primary",
                "remoteok_ai_transition",
                "ai_transition",
            ],
        )
        self.assertEqual(profile.search_queries[0].priority, 10)
        self.assertEqual(profile.search_queries[0].source, "hh")
        self.assertEqual(profile.search_queries[1].source, "weworkremotely")
        self.assertEqual(profile.search_queries[1].source_url, "https://weworkremotely.com/remote-ruby-on-rails-jobs")
        self.assertEqual(profile.search_queries[2].source, "habr")
        self.assertEqual(profile.search_queries[3].source, "remotive")
        self.assertEqual(profile.search_queries[4].source, "remoteok")
        self.assertFalse(profile.search_queries[0].detailed)
        self.assertIsNone(profile.search_queries[0].area)
        self.assertTrue(profile.search_queries[0].fetch_all)
        self.assertEqual(profile.search_queries[0].per_page, 100)

    def test_profile_includes_applicant_history_url(self) -> None:
        profile = load_profile("config/profile.example.toml")

        self.assertEqual(profile.applicant_history_url, "https://simferopol.hh.ru/applicant/negotiations")
        self.assertTrue(profile.preferences.remote_only)
        self.assertTrue(profile.ignored_vacancy_ids_path.endswith("config/ignored_vacancy_ids.example.txt"))
        self.assertEqual(profile.ignored_vacancy_ids, frozenset())
        self.assertIn("habr", profile.ignored_vacancy_ids_by_source)
        self.assertIn("hh", profile.ignored_vacancy_ids_by_source)
        self.assertIn("remotive", profile.ignored_vacancy_ids_by_source)
        self.assertIn("remoteok", profile.ignored_vacancy_ids_by_source)
        self.assertIn("weworkremotely", profile.ignored_vacancy_ids_by_source)
        self.assertEqual(profile.ranking.primary_track.value, "ruby")
        self.assertEqual(profile.ranking.secondary_track.value, "ai")
        self.assertEqual(profile.ranking.primary_track_weight, 1.35)
        self.assertEqual(profile.ranking.mixed_track_weight, 1.2)
        self.assertEqual(profile.ranking.secondary_track_weight, 1.0)
        self.assertEqual(profile.defaults.report.cv_path, "data/Alexander_Kharitonov_CV_ENG_2026.pdf")
        self.assertEqual(profile.defaults.report.output_path, "data/application_report.md")
        self.assertEqual(profile.defaults.report.hydrate_top, 20)
        self.assertEqual(profile.defaults.export_my_applications.output_path, "data/hh_applied_history.html")
        self.assertEqual(profile.defaults.export_my_applications.storage_state_path, "data/hh_storage_state.json")
        self.assertEqual(profile.defaults.export_my_applications.login_wait_seconds, 0)

    def test_profile_loads_ignored_vacancy_ids_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / "ignored_ids.txt").write_text("# comment\n131083362\n130438587\n", encoding="utf-8")
            ignored_dir = temp_path / "ignored_vacancies"
            ignored_dir.mkdir()
            (ignored_dir / "remoteok.txt").write_text("1130651\n", encoding="utf-8")
            (temp_path / "profile.toml").write_text(
                """
[candidate]
name = "Test"
summary = "Summary"
preferred_language = "ru"

[preferences]
remote_only = true
remote_preferred = true
accept_russia = true
accept_moscow_hybrid = true
full_time_preferred = true
long_term_contract_ok = true

[files]
ignored_vacancy_ids_path = "ignored_ids.txt"
ignored_vacancy_ids_dir = "ignored_vacancies"

[defaults.report]
cv_path = "data/cv.pdf"
output_path = "data/report.md"
hydrate_top = 11
top_apply = 7
top_maybe = 6
top_skip = 2

[defaults.export_my_applications]
output_path = "data/apps.html"
storage_state_path = "data/state.json"
login_wait_seconds = 3
import_status = "saved"

[salary]
currency = "RUR"
minimum = 1
target = 2
stretch = 3

[weights]
ai_track_boost = 1
ruby_track_boost = 1
remote_bonus = 1
hybrid_bonus = 1
onsite_penalty = 1
python_strong_penalty = 1
frontend_penalty = 1
product_penalty = 1
ml_research_penalty = 1
n8n_penalty = 1
                """.strip(),
                encoding="utf-8",
            )

            profile = load_profile(temp_path / "profile.toml")

        self.assertEqual(profile.ignored_vacancy_ids, frozenset({"131083362", "130438587"}))
        self.assertEqual(profile.ignored_vacancy_ids_by_source["remoteok"], frozenset({"1130651"}))
        self.assertEqual(profile.defaults.report.output_path, "data/report.md")
        self.assertEqual(profile.defaults.report.hydrate_top, 11)
        self.assertEqual(profile.defaults.export_my_applications.output_path, "data/apps.html")
        self.assertEqual(profile.defaults.export_my_applications.storage_state_path, "data/state.json")
        self.assertEqual(profile.defaults.export_my_applications.import_status, "saved")

    def test_source_specific_ignore_matches_weworkremotely_html_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            ignored_dir = temp_path / "ignored_vacancies"
            ignored_dir.mkdir()
            (ignored_dir / "weworkremotely.txt").write_text("example-role\n", encoding="utf-8")
            (temp_path / "profile.toml").write_text(
                """
[candidate]
name = "Test"
summary = "Summary"
preferred_language = "ru"

[preferences]
remote_only = true
remote_preferred = true
accept_russia = true
accept_moscow_hybrid = true
full_time_preferred = true
long_term_contract_ok = true

[files]
ignored_vacancy_ids_dir = "ignored_vacancies"

[salary]
currency = "RUR"
minimum = 1
target = 2
stretch = 3

[weights]
ai_track_boost = 1
ruby_track_boost = 1
remote_bonus = 1
hybrid_bonus = 1
onsite_penalty = 1
python_strong_penalty = 1
frontend_penalty = 1
product_penalty = 1
ml_research_penalty = 1
n8n_penalty = 1
                """.strip(),
                encoding="utf-8",
            )

            profile = load_profile(temp_path / "profile.toml")
            vacancy = vacancy_from_weworkremotely_payload(
                {
                    "id": "example-role",
                    "title": "Senior Ruby on Rails Developer",
                    "company": "Test Co",
                    "location": "Remote",
                    "categories": ["Full-Time", "Russian Federation"],
                    "url": "https://weworkremotely.com/remote-jobs/example-role",
                },
                source="weworkremotely_html:test",
            )

        self.assertTrue(vacancy_is_ignored(profile, vacancy))


if __name__ == "__main__":
    unittest.main()
