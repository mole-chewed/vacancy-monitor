import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from vacancy_monitor.config import load_profile
from vacancy_monitor.models import ApplicationStatus, RankedVacancy
from vacancy_monitor.openai_reporting import build_report_evidence, generate_openai_application_report
from vacancy_monitor.scoring import analyze_vacancy
from vacancy_monitor.sources.json_import import load_vacancies_from_json


class _FakeResponse:
    def __init__(self, output_text: str) -> None:
        self.output_text = output_text


class _FakeResponsesApi:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeResponse("# LLM report\n\nok")


class _FakeClient:
    def __init__(self) -> None:
        self.responses = _FakeResponsesApi()


class OpenAIReportingTestCase(unittest.TestCase):
    def test_build_report_evidence_contains_profile_and_vacancies(self) -> None:
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
        cv_text = "Alexander Kharitonov CV text"

        evidence = build_report_evidence(profile, cv_text, ranked)

        self.assertEqual(evidence["candidate_profile"]["preferences"]["remote_only"], True)
        self.assertEqual(evidence["candidate_cv_text"], cv_text)
        self.assertEqual(len(evidence["vacancies_compact"]), 4)
        self.assertEqual(len(evidence["vacancies_detailed"]), 4)
        self.assertIn("deterministic_score", evidence["vacancies_compact"][0])
        self.assertIn("url", evidence["vacancies_compact"][0])
        self.assertIn("summary_text", evidence["vacancies_compact"][0])
        self.assertIn("description", evidence["vacancies_detailed"][0])

    def test_generate_application_report_uses_openai_client(self) -> None:
        profile = load_profile("config/profile.example.toml")
        vacancy = next(item for item in load_vacancies_from_json("data/sample_vacancies.json") if item.external_id == "genai-backend-001")
        ranked = [
            RankedVacancy(
                vacancy=vacancy,
                analysis=analyze_vacancy(vacancy, profile),
                application_status=ApplicationStatus.NEW,
            )
        ]
        fake_client = _FakeClient()

        def factory(_: str):
            return fake_client

        report = generate_openai_application_report(
            api_key="test-key",
            model="gpt-5",
            profile=profile,
            cv_text="Alexander Kharitonov CV text",
            ranked=ranked,
            client_factory=factory,
        )

        self.assertEqual(report, "# LLM report\n\nok\n")
        self.assertEqual(len(fake_client.responses.calls), 1)
        self.assertEqual(fake_client.responses.calls[0]["model"], "gpt-5")
        self.assertIn("genai-backend-001", fake_client.responses.calls[0]["input"])
        self.assertEqual(fake_client.responses.calls[0]["max_output_tokens"], 12000)

    def test_generate_application_report_uses_bounded_evidence_budget(self) -> None:
        profile = load_profile("config/profile.example.toml")
        vacancy = next(
            item for item in load_vacancies_from_json("data/sample_vacancies.json") if item.external_id == "genai-backend-001"
        )
        ranked = [
            RankedVacancy(
                vacancy=vacancy,
                analysis=analyze_vacancy(vacancy, profile),
                application_status=ApplicationStatus.NEW,
            )
        ]
        fake_client = _FakeClient()

        def factory(_: str):
            return fake_client

        report = generate_openai_application_report(
            api_key="test-key",
            model="gpt-5",
            profile=profile,
            cv_text="Alexander Kharitonov CV text " * 1000,
            ranked=ranked,
            top_apply=5,
            top_maybe=5,
            top_skip=2,
            client_factory=factory,
        )

        self.assertEqual(report, "# LLM report\n\nok\n")
        self.assertEqual(len(fake_client.responses.calls), 1)
        request_input = fake_client.responses.calls[0]["input"]
        self.assertIn('"vacancies_compact_count": 1', request_input)
        self.assertIn('"vacancies_detailed_count": 1', request_input)

    def test_generate_application_report_excludes_skip_vacancies(self) -> None:
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
        fake_client = _FakeClient()

        def factory(_: str):
            return fake_client

        generate_openai_application_report(
            api_key="test-key",
            model="gpt-5",
            profile=profile,
            cv_text="Alexander Kharitonov CV text",
            ranked=ranked,
            client_factory=factory,
        )

        request_input = fake_client.responses.calls[0]["input"]
        self.assertNotIn("product-ai-003", request_input)


if __name__ == "__main__":
    unittest.main()
