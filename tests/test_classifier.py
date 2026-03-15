import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from vacancy_monitor.classifier import classify_vacancy
from vacancy_monitor.models import VacancyTrack
from vacancy_monitor.normalization import vacancy_from_payload
from vacancy_monitor.sources.json_import import load_vacancies_from_json


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

    def test_ml_research_title_is_hard_excluded(self) -> None:
        vacancy = vacancy_from_payload(
            {
                "id": "ml-hard-exclude-001",
                "name": "Machine Learning Engineer",
                "alternate_url": "https://hh.example/ml-hard-exclude-001",
                "employer": {"name": "ML Lab"},
                "area": {"name": "Remote"},
                "schedule": {"name": "Удаленная работа"},
                "employment": {"name": "Полная занятость"},
                "experience": {"name": "3-6 лет"},
                "description": "Build model training pipelines in PyTorch and fine-tune LLMs with LoRA.",
                "key_skills": [{"name": "PyTorch"}, {"name": "LoRA"}],
            }
        )

        assessment = classify_vacancy(vacancy)

        self.assertEqual(assessment.track, VacancyTrack.OTHER)
        self.assertIn("hard-excluded-ml-research", assessment.red_flags)

    def test_russian_ml_engineer_title_is_hard_excluded(self) -> None:
        vacancy = vacancy_from_payload(
            {
                "id": "ml-hard-exclude-ru-001",
                "name": "ML-инженер",
                "alternate_url": "https://hh.example/ml-hard-exclude-ru-001",
                "employer": {"name": "ML Lab"},
                "area": {"name": "Remote"},
                "schedule": {"name": "Удаленная работа"},
                "employment": {"name": "Полная занятость"},
                "experience": {"name": "3-6 лет"},
                "description": "Обучение моделей, PyTorch и TensorFlow.",
                "key_skills": [{"name": "PyTorch"}],
            }
        )

        assessment = classify_vacancy(vacancy)

        self.assertEqual(assessment.track, VacancyTrack.OTHER)
        self.assertIn("hard-excluded-ml-research", assessment.red_flags)

    def test_diffusion_and_computer_vision_body_is_hard_excluded(self) -> None:
        vacancy = vacancy_from_payload(
            {
                "id": "vision-hard-exclude-001",
                "name": "AI Engineer",
                "alternate_url": "https://hh.example/vision-hard-exclude-001",
                "employer": {"name": "Vision Studio"},
                "area": {"name": "Remote"},
                "schedule": {"name": "Удаленная работа"},
                "employment": {"name": "Полная занятость"},
                "experience": {"name": "3-6 лет"},
                "description": "Develop diffusion pipelines, image generation pipelines, and computer vision pipelines.",
                "key_skills": [{"name": "Stable Diffusion"}, {"name": "Computer Vision"}],
            }
        )

        assessment = classify_vacancy(vacancy)

        self.assertEqual(assessment.track, VacancyTrack.OTHER)
        self.assertIn("hard-excluded-ml-research", assessment.red_flags)

    def test_automation_only_role_without_backend_depth_is_other(self) -> None:
        vacancy = vacancy_from_payload(
            {
                "id": "automation-only-001",
                "name": "Automation Engineer (n8n / Zapier)",
                "alternate_url": "https://hh.example/automation-only-001",
                "employer": {"name": "Automation Shop"},
                "area": {"name": "Remote"},
                "schedule": {"name": "Удаленная работа"},
                "employment": {"name": "Полная занятость"},
                "experience": {"name": "1-3 года"},
                "description": "Build workflow automation in n8n, Zapier, and low-code tools for business teams.",
                "key_skills": [{"name": "n8n"}, {"name": "Zapier"}],
            }
        )

        assessment = classify_vacancy(vacancy)

        self.assertEqual(assessment.track, VacancyTrack.OTHER)
        self.assertIn("automation-only", assessment.red_flags)

    def test_architect_title_is_other(self) -> None:
        vacancy = vacancy_from_payload(
            {
                "id": "architect-001",
                "name": "GenAI Архитектор",
                "alternate_url": "https://hh.example/architect-001",
                "employer": {"name": "AI Systems Co"},
                "area": {"name": "Remote"},
                "schedule": {"name": "Удаленная работа"},
                "employment": {"name": "Полная занятость"},
                "experience": {"name": "3-6 лет"},
                "description": "Design AI architecture and solution blueprints.",
                "key_skills": [{"name": "GenAI"}, {"name": "Architecture"}],
            }
        )

        assessment = classify_vacancy(vacancy)

        self.assertEqual(assessment.track, VacancyTrack.OTHER)
        self.assertIn("architect-heavy", assessment.red_flags)

    def test_python_title_without_ruby_is_other(self) -> None:
        vacancy = vacancy_from_payload(
            {
                "id": "python-title-001",
                "name": "Python разработчик (LLM)",
                "alternate_url": "https://hh.example/python-title-001",
                "employer": {"name": "LLM Shop"},
                "area": {"name": "Remote"},
                "schedule": {"name": "Удаленная работа"},
                "employment": {"name": "Полная занятость"},
                "experience": {"name": "3-6 лет"},
                "description": "Build Python services around LLM integrations.",
                "key_skills": [{"name": "Python"}, {"name": "LLM"}],
            }
        )

        assessment = classify_vacancy(vacancy)

        self.assertEqual(assessment.track, VacancyTrack.OTHER)

    def test_fullstack_title_is_other(self) -> None:
        vacancy = vacancy_from_payload(
            {
                "id": "fullstack-title-001",
                "name": "Senior FullStack в GenAI",
                "alternate_url": "https://hh.example/fullstack-title-001",
                "employer": {"name": "GenAI Product"},
                "area": {"name": "Remote"},
                "schedule": {"name": "Удаленная работа"},
                "employment": {"name": "Полная занятость"},
                "experience": {"name": "3-6 лет"},
                "description": "Build frontend and backend AI product features.",
                "key_skills": [{"name": "React"}, {"name": "GenAI"}],
            }
        )

        assessment = classify_vacancy(vacancy)

        self.assertEqual(assessment.track, VacancyTrack.OTHER)


if __name__ == "__main__":
    unittest.main()
