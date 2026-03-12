from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import ast
import os
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback
    tomllib = None

from hh_monitor.models import SearchQuery


@dataclass(frozen=True)
class SalaryExpectation:
    currency: str
    minimum: int
    target: int
    stretch: int


@dataclass(frozen=True)
class CandidatePreferences:
    remote_only: bool
    remote_preferred: bool
    accept_russia: bool
    accept_moscow_hybrid: bool
    full_time_preferred: bool
    long_term_contract_ok: bool


@dataclass(frozen=True)
class ScoringWeights:
    ai_track_boost: int
    ruby_track_boost: int
    remote_bonus: int
    hybrid_bonus: int
    onsite_penalty: int
    python_strong_penalty: int
    frontend_penalty: int
    product_penalty: int
    ml_research_penalty: int
    n8n_penalty: int


@dataclass(frozen=True)
class CandidateProfile:
    name: str
    summary: str
    preferred_language: str
    applicant_history_url: str | None
    preferences: CandidatePreferences
    salary: SalaryExpectation
    weights: ScoringWeights
    keyword_overrides: dict[str, list[str]]
    search_queries: list[SearchQuery]


@dataclass(frozen=True)
class AppSettings:
    db_path: Path
    log_level: str
    hh_api_base_url: str
    hh_user_agent: str
    hh_api_token: str | None
    openai_api_key: str | None
    openai_report_model: str


def load_dotenv(env_path: str | Path = ".env") -> dict[str, str]:
    path = Path(env_path)
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        values[key.strip()] = raw_value.strip().strip('"').strip("'")
    return values


def _env_get(key: str, default: str | None = None, env_file: dict[str, str] | None = None) -> str | None:
    if key in os.environ:
        return os.environ[key]
    if env_file and key in env_file:
        return env_file[key]
    return default


def load_settings(env_path: str | Path = ".env") -> AppSettings:
    env_file = load_dotenv(env_path)
    db_path = Path(_env_get("APP_DB_PATH", "data/hh_monitor.db", env_file) or "data/hh_monitor.db")

    return AppSettings(
        db_path=db_path,
        log_level=(_env_get("APP_LOG_LEVEL", "INFO", env_file) or "INFO").upper(),
        hh_api_base_url=_env_get("HH_API_BASE_URL", "https://api.hh.ru", env_file) or "https://api.hh.ru",
        hh_user_agent=_env_get("HH_USER_AGENT", "hh-positions-validation/0.1 (+local-cli)", env_file)
        or "hh-positions-validation/0.1 (+local-cli)",
        hh_api_token=_env_get("HH_API_TOKEN", None, env_file),
        openai_api_key=_env_get("OPENAI_API_KEY", None, env_file),
        openai_report_model=_env_get("OPENAI_REPORT_MODEL", "gpt-5", env_file) or "gpt-5",
    )


def load_profile(config_path: str | Path = "config/profile.toml") -> CandidateProfile:
    path = Path(config_path)
    if not path.exists():
        path = Path("config/profile.example.toml")

    data = _load_toml(path.read_text(encoding="utf-8"))

    candidate = data["candidate"]
    preferences = data["preferences"]
    hh = data.get("hh", {})
    salary = data["salary"]
    weights = data["weights"]

    return CandidateProfile(
        name=candidate["name"],
        summary=candidate["summary"],
        preferred_language=candidate.get("preferred_language", "ru"),
        applicant_history_url=_optional_str(hh.get("applicant_history_url")) if isinstance(hh, dict) else None,
        preferences=CandidatePreferences(
            remote_only=bool(preferences.get("remote_only", preferences.get("remote_preferred", False))),
            remote_preferred=bool(preferences["remote_preferred"]),
            accept_russia=bool(preferences["accept_russia"]),
            accept_moscow_hybrid=bool(preferences["accept_moscow_hybrid"]),
            full_time_preferred=bool(preferences["full_time_preferred"]),
            long_term_contract_ok=bool(preferences["long_term_contract_ok"]),
        ),
        salary=SalaryExpectation(
            currency=salary["currency"],
            minimum=int(salary["minimum"]),
            target=int(salary["target"]),
            stretch=int(salary["stretch"]),
        ),
        weights=ScoringWeights(
            ai_track_boost=int(weights["ai_track_boost"]),
            ruby_track_boost=int(weights["ruby_track_boost"]),
            remote_bonus=int(weights["remote_bonus"]),
            hybrid_bonus=int(weights["hybrid_bonus"]),
            onsite_penalty=int(weights["onsite_penalty"]),
            python_strong_penalty=int(weights["python_strong_penalty"]),
            frontend_penalty=int(weights["frontend_penalty"]),
            product_penalty=int(weights["product_penalty"]),
            ml_research_penalty=int(weights["ml_research_penalty"]),
            n8n_penalty=int(weights["n8n_penalty"]),
        ),
        keyword_overrides={key: list(values) for key, values in data.get("keywords", {}).items()},
        search_queries=_load_search_queries(data.get("search", {})),
    )


def _load_toml(text: str) -> dict[str, object]:
    if tomllib is not None:
        return tomllib.loads(text)
    return _parse_simple_toml(text)


def _parse_simple_toml(text: str) -> dict[str, object]:
    result: dict[str, object] = {}
    current_section: dict[str, object] | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section_name = line[1:-1].strip()
            section = _ensure_nested_section(result, section_name)
            current_section = section
            continue
        if "=" not in line or current_section is None:
            continue
        key, raw_value = line.split("=", 1)
        current_section[key.strip()] = _parse_toml_value(raw_value.strip())

    return result


def _parse_toml_value(value: str) -> object:
    normalized = value
    if value == "true":
        normalized = "True"
    elif value == "false":
        normalized = "False"
    return ast.literal_eval(normalized)


def _ensure_nested_section(root: dict[str, object], section_name: str) -> dict[str, object]:
    current: dict[str, object] = root
    for part in section_name.split("."):
        next_value = current.get(part)
        if not isinstance(next_value, dict):
            next_value = {}
            current[part] = next_value
        current = next_value
    return current


def _load_search_queries(raw_search: object) -> list[SearchQuery]:
    if not isinstance(raw_search, dict):
        return []

    queries: list[SearchQuery] = []
    for name, payload in raw_search.items():
        if not isinstance(payload, dict):
            continue
        enabled = bool(payload.get("enabled", True))
        text = payload.get("text")
        if not enabled or not text:
            continue
        queries.append(
            SearchQuery(
                name=name,
                label=str(payload.get("label", name.replace("_", " ").title())),
                text=str(text),
                priority=int(payload.get("priority", 100)),
                area=_optional_int(payload.get("area")),
                per_page=int(payload.get("per_page", 20)),
                pages=int(payload.get("pages", 1)),
                fetch_all=bool(payload.get("fetch_all", False)),
                only_with_salary=bool(payload.get("only_with_salary", False)),
                detailed=bool(payload.get("detailed", False)),
                search_field=_optional_str(payload.get("search_field")),
                experience=_optional_str(payload.get("experience")),
                employment=_optional_str(payload.get("employment")),
                schedule=_optional_str(payload.get("schedule")),
                order_by=_optional_str(payload.get("order_by")),
            )
        )

    queries.sort(key=lambda item: (item.priority, item.name))
    return queries


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)
