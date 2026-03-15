from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from vacancy_monitor import main
from vacancy_monitor.cli import build_parser


class PackageAliasTestCase(unittest.TestCase):
    def test_vacancy_monitor_alias_exposes_main(self) -> None:
        self.assertTrue(callable(main))

    def test_vacancy_monitor_cli_parser_builds(self) -> None:
        parser = build_parser()
        self.assertIsNotNone(parser)


if __name__ == "__main__":
    unittest.main()
