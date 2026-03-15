from pathlib import Path
import io
import sys
import unittest
from contextlib import redirect_stderr
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from vacancy_monitor.cli import main
from vacancy_monitor.ui.playwright_exporter import PlaywrightUnavailableError


class CliExportTestCase(unittest.TestCase):
    def test_export_ui_history_returns_error_when_playwright_is_unavailable(self) -> None:
        with patch(
            "vacancy_monitor.cli.export_hh_page",
            side_effect=PlaywrightUnavailableError("Playwright is not installed"),
        ):
            with redirect_stderr(io.StringIO()):
                exit_code = main(
                    [
                        "export-ui-history",
                        "--url",
                        "https://hh.ru/applicant/negotiations",
                        "--output",
                        "/tmp/hh_export_test.html",
                    ]
                )

        self.assertEqual(exit_code, 1)

    def test_export_my_applications_uses_configured_default_url(self) -> None:
        captured = {}

        def fake_export_command(args):
            captured["url"] = args.url
            captured["sync_missing"] = args.sync_missing
            return 0

        with patch("vacancy_monitor.cli.export_ui_history_command", side_effect=fake_export_command):
            exit_code = main(
                [
                    "export-my-applications",
                    "--output",
                    "/tmp/hh_export_test.html",
                    "--login-wait-seconds",
                    "0",
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(captured["url"], "https://simferopol.hh.ru/applicant/negotiations")
        self.assertTrue(captured["sync_missing"])

    def test_export_my_applications_can_disable_sync_missing(self) -> None:
        captured = {}

        def fake_export_command(args):
            captured["url"] = args.url
            captured["sync_missing"] = args.sync_missing
            return 0

        with patch("vacancy_monitor.cli.export_ui_history_command", side_effect=fake_export_command):
            exit_code = main(
                [
                    "export-my-applications",
                    "--output",
                    "/tmp/hh_export_test.html",
                    "--login-wait-seconds",
                    "0",
                    "--no-sync-missing",
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertFalse(captured["sync_missing"])


if __name__ == "__main__":
    unittest.main()
