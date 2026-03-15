import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from vacancy_monitor.config import load_profile
from vacancy_monitor.models import ApplicationRecord, ApplicationStatus, RankedVacancy, UiApplicationEntry
from vacancy_monitor.scoring import analyze_vacancy
from vacancy_monitor.sources.json_import import load_vacancies_from_json
from vacancy_monitor.storage import Storage


class StorageTestCase(unittest.TestCase):
    def test_storage_excludes_applied_and_persists_latest_ranking(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = Storage(Path(temp_dir) / "vacancy_monitor.db")
            storage.init_db()

            vacancies = load_vacancies_from_json("data/sample_vacancies.json")
            storage.upsert_vacancies(vacancies)
            storage.mark_application(
                ApplicationRecord(vacancy_id="ruby-rails-002", status=ApplicationStatus.APPLIED, note=None)
            )

            visible = storage.list_vacancies(exclude_statuses={ApplicationStatus.APPLIED})
            self.assertEqual(
                {vacancy.external_id for vacancy in visible},
                {"genai-backend-001", "product-ai-003", "ml-research-004"},
            )

            profile = load_profile("config/profile.example.toml")
            ranked = [
                RankedVacancy(
                    vacancy=vacancy,
                    analysis=analyze_vacancy(vacancy, profile),
                    application_status=ApplicationStatus.NEW,
                )
                for vacancy in visible
            ]
            storage.save_ranking_results(ranked)

            latest = storage.get_latest_ranking()
            self.assertEqual(len(latest), 3)
            self.assertEqual(latest[0][0].vacancy_id, "genai-backend-001")
            self.assertEqual(latest[0][1].title, "GenAI Backend Engineer")

    def test_sync_application_entries_replaces_stale_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = Storage(Path(temp_dir) / "vacancy_monitor.db")
            storage.init_db()

            storage.import_application_entries(
                [
                    UiApplicationEntry(
                        vacancy_id="keep-001",
                        url="https://hh.ru/vacancy/keep-001",
                        title="Keep vacancy",
                        company="Acme",
                        status=ApplicationStatus.APPLIED,
                        note=None,
                    ),
                    UiApplicationEntry(
                        vacancy_id="stale-002",
                        url="https://hh.ru/vacancy/stale-002",
                        title="Stale vacancy",
                        company="Acme",
                        status=ApplicationStatus.APPLIED,
                        note=None,
                    ),
                ]
            )

            imported = storage.sync_application_entries(
                [
                    UiApplicationEntry(
                        vacancy_id="keep-001",
                        url="https://hh.ru/vacancy/keep-001",
                        title="Keep vacancy",
                        company="Acme",
                        status=ApplicationStatus.INTERVIEW,
                        note=None,
                    )
                ]
            )

            self.assertEqual(imported, 1)
            rows = storage.list_application_history()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].vacancy_id, "keep-001")
            self.assertEqual(rows[0].status, ApplicationStatus.INTERVIEW)


if __name__ == "__main__":
    unittest.main()
