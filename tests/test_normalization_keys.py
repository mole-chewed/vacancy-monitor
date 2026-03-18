import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from vacancy_monitor.normalization import normalize_company_key, normalize_title_key


class NormalizeCompanyKeyTestCase(unittest.TestCase):
    def test_strips_ooo_prefix(self) -> None:
        self.assertEqual(normalize_company_key("ООО Рога и Копыта"), "рога и копыта")

    def test_strips_inc_suffix(self) -> None:
        self.assertEqual(normalize_company_key("Apex Inc."), "apex")

    def test_strips_llc(self) -> None:
        self.assertEqual(normalize_company_key("Acme LLC"), "acme")

    def test_strips_ltd(self) -> None:
        self.assertEqual(normalize_company_key("FooBar Ltd."), "foobar")

    def test_strips_zao(self) -> None:
        self.assertEqual(normalize_company_key("ЗАО Технологии"), "технологии")

    def test_case_insensitive(self) -> None:
        self.assertEqual(normalize_company_key("APEX"), normalize_company_key("apex"))
        self.assertEqual(normalize_company_key("Apex"), normalize_company_key("apex"))

    def test_collapses_whitespace(self) -> None:
        self.assertEqual(normalize_company_key("Roga   i   Kopyta"), "roga i kopyta")

    def test_empty_and_none(self) -> None:
        self.assertEqual(normalize_company_key(""), "")
        self.assertEqual(normalize_company_key("  "), "")

    def test_strips_html(self) -> None:
        self.assertEqual(normalize_company_key("<b>Apex</b> Inc."), "apex")

    def test_same_company_different_legal_forms(self) -> None:
        self.assertEqual(
            normalize_company_key("ООО Яндекс"),
            normalize_company_key("АО Яндекс"),
        )


class NormalizeTitleKeyTestCase(unittest.TestCase):
    def test_basic_normalization(self) -> None:
        self.assertEqual(normalize_title_key("Senior Ruby Developer"), "senior ruby developer")

    def test_preserves_seniority(self) -> None:
        self.assertNotEqual(
            normalize_title_key("Junior Ruby Developer"),
            normalize_title_key("Senior Ruby Developer"),
        )

    def test_case_insensitive(self) -> None:
        self.assertEqual(
            normalize_title_key("SENIOR RUBY DEVELOPER"),
            normalize_title_key("Senior Ruby Developer"),
        )

    def test_collapses_whitespace(self) -> None:
        self.assertEqual(
            normalize_title_key("Senior   Ruby   Developer"),
            "senior ruby developer",
        )

    def test_empty(self) -> None:
        self.assertEqual(normalize_title_key(""), "")


class CrossProviderDeduplicationTestCase(unittest.TestCase):
    def test_same_company_matches_across_providers(self) -> None:
        hh_company = normalize_company_key("Apex")
        rabota_company = normalize_company_key("Apex")
        self.assertEqual(hh_company, rabota_company)

        hh_title = normalize_title_key("Senior Ruby Developer")
        rabota_title = normalize_title_key("Senior Ruby Developer")
        self.assertEqual(hh_title, rabota_title)

    def test_company_with_legal_suffix_matches_without(self) -> None:
        self.assertEqual(
            normalize_company_key("Apex Inc."),
            normalize_company_key("Apex"),
        )


if __name__ == "__main__":
    unittest.main()
