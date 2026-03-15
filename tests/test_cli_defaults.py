from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from vacancy_monitor.cli import _resolve_export_my_applications_args, _resolve_report_args, build_parser
from vacancy_monitor.config import load_profile


class CliDefaultsTestCase(unittest.TestCase):
    def test_report_command_uses_profile_defaults(self) -> None:
        profile = load_profile("config/profile.example.toml")
        parser = build_parser()
        args = parser.parse_args(["report"])

        resolved = _resolve_report_args(args, profile)

        self.assertEqual(resolved.output, "data/application_report.md")
        self.assertEqual(resolved.cv_path, "data/Alexander_Kharitonov_CV_ENG_2026.pdf")
        self.assertEqual(resolved.hydrate_top, 20)
        self.assertEqual(resolved.top_apply, 5)
        self.assertEqual(resolved.top_maybe, 5)
        self.assertEqual(resolved.top_skip, 2)

    def test_report_command_cli_flags_override_profile_defaults(self) -> None:
        profile = load_profile("config/profile.example.toml")
        parser = build_parser()
        args = parser.parse_args(
            [
                "report",
                "--output",
                "data/custom.md",
                "--cv-path",
                "data/custom.pdf",
                "--hydrate-top",
                "9",
                "--top-apply",
                "3",
                "--top-maybe",
                "4",
                "--top-skip",
                "1",
                "--source",
                "hh",
            ]
        )

        resolved = _resolve_report_args(args, profile)

        self.assertEqual(resolved.output, "data/custom.md")
        self.assertEqual(resolved.cv_path, "data/custom.pdf")
        self.assertEqual(resolved.hydrate_top, 9)
        self.assertEqual(resolved.top_apply, 3)
        self.assertEqual(resolved.top_maybe, 4)
        self.assertEqual(resolved.top_skip, 1)
        self.assertEqual(resolved.source, "hh")

    def test_export_my_applications_uses_profile_defaults(self) -> None:
        profile = load_profile("config/profile.example.toml")
        parser = build_parser()
        args = parser.parse_args(["export-my-applications"])

        resolved = _resolve_export_my_applications_args(args, profile)

        self.assertEqual(resolved.output, "data/applied_history.html")
        self.assertEqual(resolved.storage_state, "data/browser_storage_state.json")
        self.assertEqual(resolved.login_wait_seconds, 0)
        self.assertEqual(resolved.import_status, "applied")


if __name__ == "__main__":
    unittest.main()
