import unittest
from pathlib import Path
import tempfile
import sys
from contextlib import redirect_stderr
import io
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from vacancy_monitor.cli import _hydrate_ranked_vacancies, _ranked_vacancies, _warn_if_history_missing
from vacancy_monitor.config import load_profile
from vacancy_monitor.pipeline import hydrate_ranked_vacancies as pipeline_hydrate_ranked_vacancies
from vacancy_monitor.models import ApplicationStatus, RankedVacancy, WorkFormat
from vacancy_monitor.normalization import vacancy_from_payload
from vacancy_monitor.reporting import build_application_report_markdown
from vacancy_monitor.scoring import analyze_vacancy
from vacancy_monitor.sources.json_import import load_vacancies_from_json
from vacancy_monitor.storage import Storage


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

        self.assertIn("# Отчет по вакансиям", report)
        self.assertIn("## Откликнуться сейчас", report)
        self.assertIn("## Проверить вручную", report)
        self.assertIn("## Пропустить", report)
        self.assertIn("GenAI Backend Engineer", report)

    def test_ranked_vacancies_filter_to_remote_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = Storage(Path(temp_dir) / "vacancy_monitor.db")
            storage.init_db()
            storage.upsert_vacancies(load_vacancies_from_json("data/sample_vacancies.json"))

            ranked = _ranked_vacancies(storage, "config/profile.example.toml", excluded=set())

        self.assertTrue(ranked)
        self.assertTrue(all(item.vacancy.work_format == WorkFormat.REMOTE for item in ranked))
        self.assertNotIn("product-ai-003", {item.vacancy.external_id for item in ranked})

    def test_ranked_vacancies_can_filter_to_single_source_family(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = Storage(Path(temp_dir) / "vacancy_monitor.db")
            storage.init_db()
            storage.upsert_vacancies(
                [
                    vacancy_from_payload(
                        {
                            "id": "hh-ruby-1",
                            "name": "Senior Ruby on Rails Developer",
                            "alternate_url": "https://hh.example/hh-ruby-1",
                            "employer": {"name": "Ruby Co"},
                            "area": {"name": "Remote"},
                            "schedule": {"name": "Remote"},
                            "employment": {"name": "Full-time"},
                            "experience": {"name": "3-6 years"},
                            "description": "Ruby on Rails, Sidekiq, PostgreSQL.",
                            "key_skills": [{"name": "Ruby on Rails"}],
                        },
                        source="hh_api:ruby_primary",
                    ),
                    vacancy_from_payload(
                        {
                            "id": "remotive-ruby-1",
                            "name": "Senior Ruby on Rails Developer",
                            "alternate_url": "https://remotive.example/remotive-ruby-1",
                            "employer": {"name": "Remotive Ruby Co"},
                            "area": {"name": "Remote"},
                            "schedule": {"name": "Remote"},
                            "employment": {"name": "Full-time"},
                            "experience": {"name": "3-6 years"},
                            "description": "Ruby on Rails, Sidekiq, PostgreSQL.",
                            "key_skills": [{"name": "Ruby on Rails"}],
                        },
                        source="remotive_api:ruby_primary",
                    ),
                ]
            )

            ranked = _ranked_vacancies(storage, "config/profile.example.toml", excluded=set(), source_name="hh")

        self.assertEqual(len(ranked), 1)
        self.assertEqual(ranked[0].vacancy.external_id, "hh-ruby-1")

    def test_ranked_vacancies_exclude_ignored_ids_dir(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            storage = Storage(temp_path / "vacancy_monitor.db")
            storage.init_db()
            storage.upsert_vacancies(load_vacancies_from_json("data/sample_vacancies.json"))
            (temp_path / "profile.toml").write_text(
                Path("config/profile.example.toml")
                .read_text(encoding="utf-8")
                .replace('ignored_vacancy_ids_dir = "ignored_vacancies.example"', 'ignored_vacancy_ids_dir = "ignored_vacancies"'),
                encoding="utf-8",
            )
            ignored_dir = temp_path / "ignored_vacancies"
            ignored_dir.mkdir()
            (ignored_dir / "json_import.txt").write_text("genai-backend-001\n", encoding="utf-8")

            ranked = _ranked_vacancies(storage, str(temp_path / "profile.toml"), excluded=set())

        self.assertNotIn("genai-backend-001", {item.vacancy.external_id for item in ranked})

    def test_ranked_vacancies_exclude_archived_hh_items_already_in_storage(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = Storage(Path(temp_dir) / "vacancy_monitor.db")
            storage.init_db()
            storage.upsert_vacancies(
                [
                    vacancy_from_payload(
                        {
                            "id": "130090775",
                            "name": "Senior Ruby Developer",
                            "alternate_url": "https://hh.example/130090775",
                            "employer": {"name": "Ruby Co"},
                            "area": {"name": "Remote"},
                            "schedule": {"name": "Remote"},
                            "employment": {"name": "Full-time"},
                            "experience": {"name": "3-6 years"},
                            "description": "Ruby on Rails, PostgreSQL, Sidekiq.",
                            "archived": True,
                        },
                        source="hh_api:ruby_primary",
                    ),
                    vacancy_from_payload(
                        {
                            "id": "130090776",
                            "name": "Senior Ruby on Rails Developer",
                            "alternate_url": "https://hh.example/130090776",
                            "employer": {"name": "Ruby Co"},
                            "area": {"name": "Remote"},
                            "schedule": {"name": "Remote"},
                            "employment": {"name": "Full-time"},
                            "experience": {"name": "3-6 years"},
                            "description": "Ruby on Rails, PostgreSQL, Sidekiq.",
                        },
                        source="hh_api:ruby_primary",
                    ),
                ]
            )

            ranked = _ranked_vacancies(storage, "config/profile.example.toml", excluded=set(), source_name="hh")

        self.assertEqual([item.vacancy.external_id for item in ranked], ["130090776"])

    def test_hydrate_ranked_vacancies_refreshes_shortlist_details(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = Storage(Path(temp_dir) / "vacancy_monitor.db")
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

    def test_pipeline_hydration_skips_unsupported_adapters_without_warning(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = Storage(Path(temp_dir) / "vacancy_monitor.db")
            storage.init_db()
            vacancy = vacancy_from_payload(
                {
                    "id": "wwr-1",
                    "name": "Senior Ruby on Rails Developer",
                    "alternate_url": "https://weworkremotely.example/wwr-1",
                    "employer": {"name": "WWR Ruby Co"},
                    "area": {"name": "Remote"},
                    "schedule": {"name": "Remote"},
                    "employment": {"name": "Full-time"},
                    "experience": {"name": "3-6 years"},
                    "description": "Ruby on Rails, Sidekiq, PostgreSQL.",
                    "key_skills": [{"name": "Ruby on Rails"}],
                },
                source="weworkremotely_html:weworkremotely_ruby_primary",
            )
            storage.upsert_vacancies([vacancy])
            ranked = _ranked_vacancies(storage, "config/profile.example.toml", excluded=set(), source_name="weworkremotely")

            class UnsupportedAdapter:
                supports_detail_hydration = False

                def fetch_details(self, external_id: str):
                    raise AssertionError("fetch_details should not be called")

                def normalize(self, raw_item, raw_details=None):
                    raise AssertionError("normalize should not be called")

            with patch("vacancy_monitor.pipeline.LOGGER.warning") as warning_mock:
                hydrated = pipeline_hydrate_ranked_vacancies(
                    ranked,
                    adapters={"weworkremotely": UnsupportedAdapter()},
                    storage=storage,
                    profile=load_profile("config/profile.example.toml"),
                    excluded=set(),
                    limit=1,
                )

        self.assertEqual(len(hydrated), 1)
        warning_mock.assert_not_called()

    def test_warn_if_history_missing_when_excluding_applied_statuses(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = Storage(Path(temp_dir) / "vacancy_monitor.db")
            storage.init_db()
            stream = io.StringIO()
            with redirect_stderr(stream):
                _warn_if_history_missing(storage, {ApplicationStatus.APPLIED})

        self.assertIn("application_history is empty", stream.getvalue())


if __name__ == "__main__":
    unittest.main()
