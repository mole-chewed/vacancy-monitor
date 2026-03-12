from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from hh_monitor.models import ApplicationStatus
from hh_monitor.storage import Storage
from hh_monitor.ui.history_import import (
    load_ui_application_entries,
    parse_application_entries_from_html,
    parse_application_entries_from_json,
)


class UiHistoryImportTestCase(unittest.TestCase):
    def test_parse_negotiations_html_maps_statuses(self) -> None:
        html = """
        <div data-qa="negotiations-list">
          <div data-qa="negotiations-item">
            <span data-qa="negotiations-tag negotiations-item-interview">Собеседование</span>
            <a href="/vacancy/130598166?hhtmFrom=negotiation_list">
              <span data-qa="negotiations-item-vacancy">Архитектор-инженер по искусственному интеллекту</span>
            </a>
            <a href="/employer/4768936?hhtmFrom=negotiation_list">
              <div data-qa="negotiations-item-company">ЛИАН</div>
            </a>
          </div>
          <div data-qa="negotiations-item">
            <span data-qa="negotiations-tag negotiations-item-discard">Отказ</span>
            <a href="/vacancy/131088044?hhtmFrom=negotiation_list">
              <span data-qa="negotiations-item-vacancy">Ruby on Rails программист</span>
            </a>
            <a href="/employer/1791395?hhtmFrom=negotiation_list">
              <div data-qa="negotiations-item-company">Acme</div>
            </a>
          </div>
          <div data-qa="negotiations-item">
            <span data-qa="negotiations-tag negotiations-item-not-viewed">Не просмотрен</span>
            <a href="/vacancy/129619536?hhtmFrom=negotiation_list">
              <span data-qa="negotiations-item-vacancy">Разработчик платформы GenAI</span>
            </a>
          </div>
        </div>
        """
        entries = parse_application_entries_from_html(html)
        by_id = {entry.vacancy_id: entry for entry in entries}

        self.assertEqual(len(entries), 3)
        self.assertEqual(by_id["130598166"].status, ApplicationStatus.INTERVIEW)
        self.assertEqual(by_id["130598166"].company, "ЛИАН")
        self.assertEqual(by_id["131088044"].status, ApplicationStatus.REJECTED)
        self.assertEqual(by_id["129619536"].status, ApplicationStatus.APPLIED)

    def test_parse_html_extracts_unique_vacancy_links(self) -> None:
        html = """
        <html><body>
          <a href="https://hh.ru/vacancy/131100786">Senior FullStack в GenAI</a>
          <a href="/vacancy/130990992">Ruby on Rails разработчик</a>
          <a href="/vacancy/130990992">Ruby on Rails разработчик</a>
        </body></html>
        """
        entries = parse_application_entries_from_html(html)

        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0].vacancy_id, "131100786")
        self.assertEqual(entries[1].vacancy_id, "130990992")
        self.assertEqual(entries[1].url, "https://hh.ru/vacancy/130990992")

    def test_parse_json_extracts_nested_vacancy_records(self) -> None:
        payload = """
        {
          "items": [
            {
              "vacancy": {
                "id": "131040146",
                "name": "Middle Ruby on Rails разработчик",
                "alternate_url": "https://hh.ru/vacancy/131040146"
              },
              "employer": {"name": "Appbooster"}
            }
          ]
        }
        """
        entries = parse_application_entries_from_json(payload, default_status=ApplicationStatus.SAVED)

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].vacancy_id, "131040146")
        self.assertEqual(entries[0].status, ApplicationStatus.SAVED)

    def test_storage_import_creates_placeholders_and_history(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = Storage(Path(temp_dir) / "hh_monitor.db")
            storage.init_db()

            entries = load_ui_application_entries("data/sample_hh_responses.html")
            imported = storage.import_application_entries(entries)

            self.assertEqual(imported, 2)
            history = storage.list_application_history()
            self.assertEqual(len(history), 2)
            self.assertTrue(storage.vacancy_exists("131100786"))
            self.assertEqual(history[0].status, ApplicationStatus.APPLIED)

    def test_dedupe_prefers_stronger_status(self) -> None:
        html = """
        <div data-qa="negotiations-item">
          <span data-qa="negotiations-tag negotiations-item-not-viewed">Не просмотрен</span>
          <a href="/vacancy/130598166"><span data-qa="negotiations-item-vacancy">GenAI role</span></a>
        </div>
        <div data-qa="negotiations-item">
          <span data-qa="negotiations-tag negotiations-item-interview">Собеседование</span>
          <a href="/vacancy/130598166"><span data-qa="negotiations-item-vacancy">GenAI role</span></a>
        </div>
        """
        entries = parse_application_entries_from_html(html)

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].status, ApplicationStatus.INTERVIEW)


if __name__ == "__main__":
    unittest.main()
