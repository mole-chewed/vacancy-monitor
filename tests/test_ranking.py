from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from hh_monitor.config import load_profile
from hh_monitor.models import ApplicationStatus, VacancyTrack
from hh_monitor.normalization import vacancy_from_payload
from hh_monitor.ranking import build_ranked_vacancies


class RankingTestCase(unittest.TestCase):
    def test_build_ranked_vacancies_prefers_ruby_then_mixed_then_ai(self) -> None:
        profile = load_profile("config/profile.example.toml")
        vacancies = [
            vacancy_from_payload(
                {
                    "id": "ruby-1",
                    "name": "Senior Ruby on Rails Developer",
                    "alternate_url": "https://hh.example/ruby-1",
                    "employer": {"name": "Ruby Co"},
                    "salary": {"from": 420000, "to": 500000, "currency": "RUR"},
                    "area": {"name": "Remote"},
                    "schedule": {"name": "Remote"},
                    "employment": {"name": "Full-time"},
                    "experience": {"name": "Более 6 лет"},
                    "description": "Ruby on Rails, Sidekiq, PostgreSQL, Redis, APIs, AWS.",
                    "key_skills": [{"name": "Ruby on Rails"}, {"name": "Sidekiq"}],
                },
                source="hh_api:ruby_primary",
            ),
            vacancy_from_payload(
                {
                    "id": "mixed-1",
                    "name": "Backend Engineer (Ruby + LLM Integrations)",
                    "alternate_url": "https://hh.example/mixed-1",
                    "employer": {"name": "Mixed Co"},
                    "salary": {"from": 410000, "to": 480000, "currency": "RUR"},
                    "area": {"name": "Remote"},
                    "schedule": {"name": "Remote"},
                    "employment": {"name": "Full-time"},
                    "experience": {"name": "3-6 years"},
                    "description": "Ruby backend, PostgreSQL, Redis, APIs, OpenAI, LLM integrations, RAG, pgvector.",
                    "key_skills": [{"name": "Ruby"}, {"name": "OpenAI"}, {"name": "RAG"}],
                },
                source="hh_api:ai_primary",
            ),
            vacancy_from_payload(
                {
                    "id": "ai-1",
                    "name": "LLM Integration Engineer",
                    "alternate_url": "https://hh.example/ai-1",
                    "employer": {"name": "AI Co"},
                    "salary": {"from": 400000, "to": 470000, "currency": "RUR"},
                    "area": {"name": "Remote"},
                    "schedule": {"name": "Remote"},
                    "employment": {"name": "Full-time"},
                    "experience": {"name": "3-6 years"},
                    "description": "OpenAI, Anthropic, RAG, vector search, backend APIs, platform work.",
                    "key_skills": [{"name": "LLM"}, {"name": "RAG"}],
                },
                source="hh_api:ai_primary",
            ),
        ]

        ranked = build_ranked_vacancies(
            vacancies,
            profile=profile,
            statuses={vacancy.external_id: ApplicationStatus.NEW for vacancy in vacancies},
        )

        self.assertEqual([item.vacancy.external_id for item in ranked], ["ruby-1", "mixed-1", "ai-1"])
        self.assertEqual([item.analysis.track for item in ranked], [VacancyTrack.RUBY, VacancyTrack.MIXED, VacancyTrack.AI])
        self.assertTrue(all(item.vacancy.priority_score is not None for item in ranked))
        self.assertTrue(all(item.vacancy.final_recommendation is not None for item in ranked))

    def test_build_ranked_vacancies_accepts_naive_published_at(self) -> None:
        profile = load_profile("config/profile.example.toml")
        vacancy = vacancy_from_payload(
            {
                "id": "ruby-naive-1",
                "name": "Senior Ruby on Rails Developer",
                "alternate_url": "https://hh.example/ruby-naive-1",
                "employer": {"name": "Ruby Co"},
                "area": {"name": "Remote"},
                "schedule": {"name": "Remote"},
                "employment": {"name": "Full-time"},
                "experience": {"name": "Более 6 лет"},
                "published_at": "2026-03-10T10:00:00",
                "description": "Ruby on Rails, Sidekiq, PostgreSQL, Redis, APIs, AWS.",
                "key_skills": [{"name": "Ruby on Rails"}, {"name": "Sidekiq"}],
            },
            source="hh_api:ruby_primary",
        )

        ranked = build_ranked_vacancies(
            [vacancy],
            profile=profile,
            statuses={vacancy.external_id: ApplicationStatus.NEW},
        )

        self.assertEqual(len(ranked), 1)
        self.assertIsNotNone(ranked[0].vacancy.priority_score)


if __name__ == "__main__":
    unittest.main()
