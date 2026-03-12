import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from hh_monitor.classifier import classify_vacancy
from hh_monitor.models import VacancyTrack
from hh_monitor.normalization import vacancy_from_payload
from hh_monitor.sources.json_import import load_vacancies_from_json


class ClassifierTestCase(unittest.TestCase):
    def test_sample_track_classification(self) -> None:
        vacancies = load_vacancies_from_json("data/sample_vacancies.json")
        tracks = {vacancy.external_id: classify_vacancy(vacancy).track for vacancy in vacancies}

        self.assertEqual(tracks["genai-backend-001"], VacancyTrack.AI)
        self.assertEqual(tracks["ruby-rails-002"], VacancyTrack.RUBY)
        self.assertEqual(tracks["product-ai-003"], VacancyTrack.OTHER)
        self.assertEqual(tracks["ml-research-004"], VacancyTrack.OTHER)

    def test_org_leadership_1c_ai_title_stays_other(self) -> None:
        vacancy = vacancy_from_payload(
            {
                "id": "org-lead-1c-001",
                "name": "Руководитель отдела разработок 1С (с интеграцией AI-решений)",
                "alternate_url": "https://hh.example/org-lead-1c-001",
                "employer": {"name": "Legacy Corp"},
                "area": {"name": "Ростов-на-Дону"},
                "schedule": {"name": "Удаленная работа"},
                "employment": {"name": "Полная занятость"},
                "experience": {"name": "Более 6 лет"},
                "description": "Руководить отделом 1С, внедрять AI-решения, автоматизацию и интеграции.",
                "key_skills": [{"name": "1С"}, {"name": "AI"}, {"name": "Интеграции"}],
            }
        )

        assessment = classify_vacancy(vacancy)

        self.assertEqual(assessment.track, VacancyTrack.OTHER)
        self.assertIn("org-leadership-heavy", assessment.red_flags)
        self.assertIn("legacy-stack-heavy", assessment.red_flags)


if __name__ == "__main__":
    unittest.main()
