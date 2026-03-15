import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from vacancy_monitor.cv import CvExtractionError, extract_cv_text


class CvTestCase(unittest.TestCase):
    def test_missing_cv_raises_clear_error(self) -> None:
        with self.assertRaises(CvExtractionError) as ctx:
            extract_cv_text("/tmp/does-not-exist-cv.pdf")

        self.assertIn("CV file not found", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
