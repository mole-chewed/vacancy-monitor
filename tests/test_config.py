from pathlib import Path
import tempfile
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from hh_monitor.config import load_profile


class ConfigTestCase(unittest.TestCase):
    def test_profile_loads_search_queries_in_priority_order(self) -> None:
        profile = load_profile("config/profile.example.toml")

        self.assertEqual([query.name for query in profile.search_queries], ["ruby_primary", "ai_primary", "ai_transition"])
        self.assertEqual(profile.search_queries[0].priority, 10)
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
        self.assertEqual(profile.ranking.primary_track.value, "ruby")
        self.assertEqual(profile.ranking.secondary_track.value, "ai")
        self.assertEqual(profile.ranking.primary_track_weight, 1.35)
        self.assertEqual(profile.ranking.mixed_track_weight, 1.2)
        self.assertEqual(profile.ranking.secondary_track_weight, 1.0)

    def test_profile_loads_ignored_vacancy_ids_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / "ignored_ids.txt").write_text("# comment\n131083362\n130438587\n", encoding="utf-8")
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


if __name__ == "__main__":
    unittest.main()
