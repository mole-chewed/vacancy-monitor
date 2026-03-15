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

from hh_monitor.models import SearchQuery, VacancyTrack


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
class RankingPreferences:
    primary_track: VacancyTrack
    secondary_track: VacancyTrack
    primary_track_weight: float
    mixed_track_weight: float
    secondary_track_weight: float


@dataclass(frozen=True)
class CandidateProfile:
    name: str
    summary: str
    preferred_language: str
    applicant_history_url: str | None
    ignored_vacancy_ids_path: str | None
    ignored_vacancy_ids: frozenset[str]
    ignored_vacancy_ids_by_source: dict[str, frozenset[str]]
    preferences: CandidatePreferences
    salary: SalaryExpectation
    weights: ScoringWeights
    ranking: RankingPreferences
    keyword_overrides: dict[str, list[str]]
    search_queries: list[SearchQuery]


@dataclass(frozen=True)
class AppSettings:
    db_path: Path
    log_level: str
    habr_base_url: str
    habr_user_agent: str
    hh_api_base_url: str
    hh_user_agent: str
    hh_api_token: str | None
    remotive_api_base_url: str
    remotive_user_agent: str
    remoteok_api_base_url: str
    remoteok_user_agent: str
    weworkremotely_base_url: str
    weworkremotely_user_agent: str
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
        habr_base_url=_env_get("HABR_BASE_URL", "https://career.habr.com", env_file) or "https://career.habr.com",
        habr_user_agent=_env_get("HABR_USER_AGENT", "hh-positions-validation/0.1 (+local-cli)", env_file)
        or "hh-positions-validation/0.1 (+local-cli)",
        hh_api_base_url=_env_get("HH_API_BASE_URL", "https://api.hh.ru", env_file) or "https://api.hh.ru",
        hh_user_agent=_env_get("HH_USER_AGENT", "hh-positions-validation/0.1 (+local-cli)", env_file)
        or "hh-positions-validation/0.1 (+local-cli)",
        hh_api_token=_env_get("HH_API_TOKEN", None, env_file),
        remotive_api_base_url=_env_get("REMOTIVE_API_BASE_URL", "https://remotive.com", env_file)
        or "https://remotive.com",
        remotive_user_agent=_env_get("REMOTIVE_USER_AGENT", "hh-positions-validation/0.1 (+local-cli)", env_file)
        or "hh-positions-validation/0.1 (+local-cli)",
        remoteok_api_base_url=_env_get("REMOTEOK_API_BASE_URL", "https://remoteok.com", env_file)
        or "https://remoteok.com",
        remoteok_user_agent=_env_get("REMOTEOK_USER_AGENT", "hh-positions-validation/0.1 (+local-cli)", env_file)
        or "hh-positions-validation/0.1 (+local-cli)",
        weworkremotely_base_url=_env_get("WEWORKREMOTELY_BASE_URL", "https://weworkremotely.com", env_file)
        or "https://weworkremotely.com",
        weworkremotely_user_agent=_env_get(
            "WEWORKREMOTELY_USER_AGENT", "hh-positions-validation/0.1 (+local-cli)", env_file
        )
        or "hh-positions-validation/0.1 (+local-cli)",
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
    files = data.get("files", {})
    ranking = data.get("ranking", {})
    salary = data["salary"]
    weights = data["weights"]
    ignored_vacancy_ids_path = _optional_str(files.get("ignored_vacancy_ids_path")) if isinstance(files, dict) else None
    ignored_vacancy_ids_dir = _optional_str(files.get("ignored_vacancy_ids_dir")) if isinstance(files, dict) else None
    resolved_ignored_path = _resolve_optional_path(path, ignored_vacancy_ids_path)
    resolved_ignored_dir = _resolve_optional_path(path, ignored_vacancy_ids_dir)
    ignored_by_source = _load_vacancy_id_dir(resolved_ignored_dir)

    return CandidateProfile(
        name=candidate["name"],
        summary=candidate["summary"],
        preferred_language=candidate.get("preferred_language", "ru"),
        applicant_history_url=_optional_str(hh.get("applicant_history_url")) if isinstance(hh, dict) else None,
        ignored_vacancy_ids_path=str(resolved_ignored_path) if resolved_ignored_path is not None else None,
        ignored_vacancy_ids=_load_vacancy_id_file(resolved_ignored_path),
        ignored_vacancy_ids_by_source=ignored_by_source,
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
        ranking=RankingPreferences(
            primary_track=VacancyTrack(_optional_str(ranking.get("primary_track")) or VacancyTrack.RUBY.value),
            secondary_track=VacancyTrack(_optional_str(ranking.get("secondary_track")) or VacancyTrack.AI.value),
            primary_track_weight=float(ranking.get("primary_track_weight", 1.35)),
            mixed_track_weight=float(ranking.get("mixed_track_weight", 1.2)),
            secondary_track_weight=float(ranking.get("secondary_track_weight", 1.0)),
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
                source=_optional_str(payload.get("source")) or "hh",
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
                source_url=_optional_str(payload.get("source_url")),
                search_field=_optional_str(payload.get("search_field")),
                experience=_optional_str(payload.get("experience")),
                employment=_optional_str(payload.get("employment")),
                schedule=_optional_str(payload.get("schedule")),
                order_by=_optional_str(payload.get("order_by")),
            )
        )

    queries.sort(key=lambda item: (item.priority, item.name))
    return queries


def _resolve_optional_path(config_path: Path, raw_path: str | None) -> Path | None:
    if not raw_path:
        return None
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return (config_path.parent / path).resolve()


def _load_vacancy_id_file(path: Path | None) -> frozenset[str]:
    if path is None or not path.exists():
        return frozenset()
    vacancy_ids: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        vacancy_ids.add(line)
    return frozenset(vacancy_ids)


def _load_vacancy_id_dir(path: Path | None) -> dict[str, frozenset[str]]:
    if path is None or not path.exists() or not path.is_dir():
        return {}
    result: dict[str, frozenset[str]] = {}
    for entry in sorted(path.glob("*.txt")):
        result[entry.stem.lower()] = _load_vacancy_id_file(entry)
    return result


def source_family(source_name: str) -> str:
    prefix = source_name.split(":", 1)[0]
    if prefix.endswith("_api"):
        prefix = prefix[: -len("_api")]
    if prefix.endswith("_html"):
        prefix = prefix[: -len("_html")]
    if prefix.startswith("hh"):
        return "hh"
    return prefix


def vacancy_is_ignored(profile: CandidateProfile, vacancy) -> bool:
    external_id = getattr(vacancy, "external_id", "")
    source_name = getattr(vacancy, "source", "")
    if external_id in profile.ignored_vacancy_ids:
        return True
    source_ignored = profile.ignored_vacancy_ids_by_source.get(source_family(source_name), frozenset())
    if not source_ignored:
        return False
    raw_id = external_id.split(":", 1)[-1] if ":" in external_id else external_id
    return external_id in source_ignored or raw_id in source_ignored


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)
