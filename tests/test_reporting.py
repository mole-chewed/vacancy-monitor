import unittest
from pathlib import Path
import tempfile
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from hh_monitor.cli import _hydrate_ranked_vacancies, _ranked_vacancies
from hh_monitor.config import load_profile
from hh_monitor.models import ApplicationStatus, RankedVacancy, WorkFormat
from hh_monitor.normalization import vacancy_from_payload
from hh_monitor.reporting import build_application_report_markdown
from hh_monitor.scoring import analyze_vacancy
from hh_monitor.sources.json_import import load_vacancies_from_json
from hh_monitor.storage import Storage


class ReportingTestCase(unittest.TestCase):
    def test_report_groups_ranked_vacancies(self) -> None:
        profile = load_profile("config/profile.example.toml")
        vacancies = load_vacancies_from_json("data/sample_vacancies.json")
        ranked = [
            RankedVacancy(
                vacancy=vacancy,
                analysis=analyze_vacancy(vacancy, profile),
                application_status=ApplicationStatus.NEW,
            )
            for vacancy in vacancies
        ]
        ranked.sort(key=lambda item: (item.analysis.priority_bucket, -item.analysis.score, item.vacancy.title.lower()))

        report = build_application_report_markdown(profile, ranked, top_apply=5, top_maybe=5, top_skip=5)

        self.assertIn("# Отчет по вакансиям hh.ru", report)
        self.assertIn("## Откликнуться сейчас", report)
        self.assertIn("## Проверить вручную", report)
        self.assertIn("## Пропустить", report)
        self.assertIn("GenAI Backend Engineer", report)

    def test_ranked_vacancies_filter_to_remote_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = Storage(Path(temp_dir) / "hh_monitor.db")
            storage.init_db()
            storage.upsert_vacancies(load_vacancies_from_json("data/sample_vacancies.json"))

            ranked = _ranked_vacancies(storage, "config/profile.example.toml", excluded=set())

        self.assertTrue(ranked)
        self.assertTrue(all(item.vacancy.work_format == WorkFormat.REMOTE for item in ranked))
        self.assertNotIn("product-ai-003", {item.vacancy.external_id for item in ranked})

    def test_hydrate_ranked_vacancies_refreshes_shortlist_details(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = Storage(Path(temp_dir) / "hh_monitor.db")
            storage.init_db()
            storage.upsert_vacancies(
                [
                    vacancy_from_payload(
                        {
                            "id": "101",
                            "name": "GenAI Backend Engineer",
                            "alternate_url": "https://hh.example/101",
                            "employer": {"name": "AI Integrations Lab"},
                            "salary": {"from": 420000, "to": 520000, "currency": "RUR"},
                            "area": {"name": "Remote"},
                            "schedule": {"name": "Remote"},
                            "employment": {"name": "Full-time"},
                            "experience": {"name": "3-6 years"},
                            "description": "",
                            "snippet": {"requirement": "LLM integrations", "responsibility": "Build backend"},
                            "key_skills": [{"name": "LLM"}, {"name": "RAG"}],
                        },
                        source="hh_api:ai_primary",
                    ),
                ]
            )

            class FakeClient:
                def get_vacancy(self, vacancy_id: str):
                    self.last_id = vacancy_id
                    return {
                        "id": vacancy_id,
                        "name": "GenAI Backend Engineer",
                        "alternate_url": "https://hh.example/101",
                        "employer": {"name": "AI Integrations Lab"},
                        "salary": {"from": 420000, "to": 520000, "currency": "RUR"},
                        "area": {"name": "Remote"},
                        "schedule": {"name": "Remote"},
                        "employment": {"name": "Full-time"},
                        "experience": {"name": "3-6 years"},
                        "description": "Detailed description from hh.ru detail endpoint.",
                        "key_skills": [{"name": "LLM"}, {"name": "RAG"}],
                    }

            ranked = _hydrate_ranked_vacancies(
                storage,
                config_path="config/profile.example.toml",
                excluded=set(),
                settings=SimpleNamespace(hh_api_base_url="", hh_user_agent="", hh_api_token=None),
                limit=1,
                client=FakeClient(),
            )

            self.assertEqual(len(ranked), 1)
            self.assertIn("Detailed description", ranked[0].vacancy.description)


if __name__ == "__main__":
    unittest.main()
