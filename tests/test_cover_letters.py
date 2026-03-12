import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from hh_monitor.config import load_profile
from hh_monitor.cover_letters import build_cover_letter_filename, build_cover_letter_ru
from hh_monitor.scoring import analyze_vacancy
from hh_monitor.sources.json_import import load_vacancies_from_json


class CoverLettersTestCase(unittest.TestCase):
    def test_ai_cover_letter_mentions_role_and_company(self) -> None:
        profile = load_profile("config/profile.example.toml")
        vacancy = next(
            item for item in load_vacancies_from_json("data/sample_vacancies.json") if item.external_id == "genai-backend-001"
        )
        analysis = analyze_vacancy(vacancy, profile)

        letter = build_cover_letter_ru(profile, vacancy, analysis)

        self.assertIn(vacancy.title, letter)
        self.assertIn(vacancy.company, letter)
        self.assertIn("13+ лет опыта в backend-разработке", letter)
        self.assertIn("AI-track", letter)

    def test_cover_letter_filename_uses_vacancy_id(self) -> None:
        vacancy = next(
            item for item in load_vacancies_from_json("data/sample_vacancies.json") if item.external_id == "ruby-rails-002"
        )

        filename = build_cover_letter_filename(vacancy)

        self.assertTrue(filename.startswith("ruby-rails-002_"))
        self.assertTrue(filename.endswith(".md"))


if __name__ == "__main__":
    unittest.main()
