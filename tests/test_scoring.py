import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from vacancy_monitor.config import load_profile
from vacancy_monitor.models import MatchLabel, VacancyTrack
from vacancy_monitor.normalization import vacancy_from_payload
from vacancy_monitor.scoring import analyze_vacancy
from vacancy_monitor.sources.json_import import load_vacancies_from_json


class ScoringTestCase(unittest.TestCase):
    def test_ruby_role_ranks_above_ai_role(self) -> None:
        profile = load_profile("config/profile.example.toml")
        vacancies = {vacancy.external_id: vacancy for vacancy in load_vacancies_from_json("data/sample_vacancies.json")}

        ai_analysis = analyze_vacancy(vacancies["genai-backend-001"], profile)
        ruby_analysis = analyze_vacancy(vacancies["ruby-rails-002"], profile)
        product_analysis = analyze_vacancy(vacancies["product-ai-003"], profile)
        research_analysis = analyze_vacancy(vacancies["ml-research-004"], profile)

        self.assertEqual(ai_analysis.track, VacancyTrack.AI)
        self.assertEqual(ai_analysis.label, MatchLabel.STRONG_AI)
        self.assertEqual(ruby_analysis.track, VacancyTrack.RUBY)
        self.assertEqual(ruby_analysis.label, MatchLabel.STRONG_RUBY)
        self.assertLess(ruby_analysis.priority_bucket, ai_analysis.priority_bucket)
        self.assertEqual(product_analysis.label, MatchLabel.SKIP)
        self.assertEqual(research_analysis.label, MatchLabel.SKIP)

    def test_python_heavy_ai_role_is_transition_match(self) -> None:
        profile = load_profile("config/profile.example.toml")
        vacancy = vacancy_from_payload(
            {
                "id": "ai-platform-005",
                "name": "AI Platform Engineer",
                "alternate_url": "https://hh.example/ai-platform-005",
                "employer": {"name": "LLM Platform Team"},
                "salary": {"from": 430000, "to": 520000, "currency": "RUR"},
                "area": {"name": "Remote"},
                "schedule": {"name": "Remote"},
                "employment": {"name": "Full-time"},
                "experience": {"name": "3-6 years"},
                "description": (
                    "Build AI platform services, LLM integrations, RAG pipelines, vector DB infrastructure, "
                    "FastAPI services, production Python, and agent orchestration."
                ),
                "key_skills": [{"name": "LLM"}, {"name": "RAG"}, {"name": "FastAPI"}, {"name": "Python"}],
            }
        )

        analysis = analyze_vacancy(vacancy, profile)

        self.assertEqual(analysis.track, VacancyTrack.AI)
        self.assertEqual(analysis.label, MatchLabel.AI_TRANSITION)
        self.assertEqual(analysis.priority_bucket, 4)
        self.assertTrue(any("Python" in concern or "python" in concern for concern in analysis.concerns))

    def test_product_genai_title_is_not_promoted_to_ai_priority(self) -> None:
        profile = load_profile("config/profile.example.toml")
        vacancy = vacancy_from_payload(
            {
                "id": "genai-product-006",
                "name": "Руководитель продукта GenAI и агентных сценариев",
                "alternate_url": "https://hh.example/genai-product-006",
                "employer": {"name": "AI Product Org"},
                "area": {"name": "Москва"},
                "schedule": {"name": "Удаленная работа"},
                "employment": {"name": "Полная занятость"},
                "experience": {"name": "Более 6 лет"},
                "description": "Отвечать за стратегию продукта, roadmap, метрики и запуск GenAI сценариев.",
                "key_skills": [{"name": "GenAI"}, {"name": "Product Management"}],
            }
        )

        analysis = analyze_vacancy(vacancy, profile)

        self.assertNotEqual(analysis.label, MatchLabel.STRONG_AI)
        self.assertEqual(analysis.track, VacancyTrack.OTHER)
        self.assertEqual(analysis.label, MatchLabel.SKIP)
        self.assertTrue(any("product" in concern for concern in analysis.concerns))

    def test_data_scientist_role_is_not_top_ai_match(self) -> None:
        profile = load_profile("config/profile.example.toml")
        vacancy = vacancy_from_payload(
            {
                "id": "data-scientist-007",
                "name": "Data Scientist (ML/LLM)",
                "alternate_url": "https://hh.example/data-scientist-007",
                "employer": {"name": "AI Corp"},
                "area": {"name": "Москва"},
                "schedule": {"name": "Удаленная работа"},
                "employment": {"name": "Полная занятость"},
                "experience": {"name": "3-6 лет"},
                "description": "Строить ML/LLM решения, анализ данных, Data Science, Python, модели.",
                "key_skills": [{"name": "Python"}, {"name": "LLM"}, {"name": "Data Science"}],
            }
        )

        analysis = analyze_vacancy(vacancy, profile)

        self.assertNotEqual(analysis.label, MatchLabel.STRONG_AI)
        self.assertTrue(any("data science" in concern.lower() for concern in analysis.concerns))

    def test_qa_ai_role_is_not_top_ai_match(self) -> None:
        profile = load_profile("config/profile.example.toml")
        vacancy = vacancy_from_payload(
            {
                "id": "qa-ai-008",
                "name": "QA automation engineer AI Team",
                "alternate_url": "https://hh.example/qa-ai-008",
                "employer": {"name": "AI QA Org"},
                "area": {"name": "Москва"},
                "schedule": {"name": "Удаленная работа"},
                "employment": {"name": "Полная занятость"},
                "experience": {"name": "3-6 лет"},
                "description": "QA automation, testing AI services, test automation, quality assurance.",
                "key_skills": [{"name": "QA"}, {"name": "Automation"}, {"name": "AI"}],
            }
        )

        analysis = analyze_vacancy(vacancy, profile)

        self.assertNotEqual(analysis.label, MatchLabel.STRONG_AI)
        self.assertTrue(any("qa" in concern.lower() for concern in analysis.concerns))

    def test_org_leadership_1c_ai_role_is_skipped(self) -> None:
        profile = load_profile("config/profile.example.toml")
        vacancy = vacancy_from_payload(
            {
                "id": "org-lead-1c-009",
                "name": "Руководитель отдела разработок 1С (с интеграцией AI-решений)",
                "alternate_url": "https://hh.example/org-lead-1c-009",
                "employer": {"name": "Legacy AI Org"},
                "area": {"name": "Ростов-на-Дону"},
                "schedule": {"name": "Удаленная работа"},
                "employment": {"name": "Полная занятость"},
                "experience": {"name": "Более 6 лет"},
                "description": "Управлять отделом 1С, развивать автоматизацию, AI-сценарии и интеграции.",
                "key_skills": [{"name": "1С"}, {"name": "AI"}, {"name": "Автоматизация"}],
            }
        )

        analysis = analyze_vacancy(vacancy, profile)

        self.assertEqual(analysis.track, VacancyTrack.OTHER)
        self.assertEqual(analysis.label, MatchLabel.SKIP)
        self.assertTrue(any("department-lead" in concern.lower() for concern in analysis.concerns))
        self.assertTrue(any("1c" in concern.lower() or "bitrix" in concern.lower() for concern in analysis.concerns))

    def test_us_or_canada_remote_role_is_skipped_for_geo_fit(self) -> None:
        profile = load_profile("config/profile.example.toml")
        vacancy = vacancy_from_payload(
            {
                "id": "geo-us-canada-010",
                "name": "Ruby on Rails Developer",
                "alternate_url": "https://hh.example/geo-us-canada-010",
                "employer": {"name": "North America Only Inc"},
                "area": {"name": "US or Canada"},
                "schedule": {"name": "Remote"},
                "employment": {"name": "Full-time"},
                "experience": {"name": "3-6 years"},
                "description": "Senior Ruby on Rails role for candidates in the US or Canada only.",
                "key_skills": [{"name": "Ruby on Rails"}, {"name": "PostgreSQL"}],
            }
        )

        analysis = analyze_vacancy(vacancy, profile)

        self.assertEqual(analysis.label, MatchLabel.SKIP)
        self.assertTrue(any("geography incompatible" in concern for concern in analysis.concerns))

    def test_timezone_only_remote_role_gets_concern(self) -> None:
        profile = load_profile("config/profile.example.toml")
        vacancy = vacancy_from_payload(
            {
                "id": "geo-timezone-011",
                "name": "Backend Ruby on Rails Developer",
                "alternate_url": "https://hh.example/geo-timezone-011",
                "employer": {"name": "Timezone Co"},
                "area": {"name": "Pacific Time Zone"},
                "schedule": {"name": "Remote"},
                "employment": {"name": "Full-time"},
                "experience": {"name": "3-6 years"},
                "description": "Ruby backend role aligned with Pacific Time Zone collaboration.",
                "key_skills": [{"name": "Ruby on Rails"}, {"name": "API"}],
            }
        )

        analysis = analyze_vacancy(vacancy, profile)

        self.assertNotEqual(analysis.label, MatchLabel.SKIP)
        self.assertTrue(any("timezone overlap" in concern.lower() for concern in analysis.concerns))


if __name__ == "__main__":
    unittest.main()
