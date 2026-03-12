from pathlib import Path
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

        self.assertEqual([query.name for query in profile.search_queries], ["ai_primary", "ai_transition", "ruby_primary"])
        self.assertEqual(profile.search_queries[0].priority, 10)
        self.assertFalse(profile.search_queries[0].detailed)
        self.assertIsNone(profile.search_queries[0].area)
        self.assertTrue(profile.search_queries[0].fetch_all)
        self.assertEqual(profile.search_queries[0].per_page, 100)

    def test_profile_includes_applicant_history_url(self) -> None:
        profile = load_profile("config/profile.example.toml")

        self.assertEqual(profile.applicant_history_url, "https://simferopol.hh.ru/applicant/negotiations")
        self.assertTrue(profile.preferences.remote_only)


if __name__ == "__main__":
    unittest.main()
