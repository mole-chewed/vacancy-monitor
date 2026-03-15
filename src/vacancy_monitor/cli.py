from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from vacancy_monitor.config import load_profile, load_settings, source_family, vacancy_is_ignored
from vacancy_monitor.cv import CvExtractionError, extract_cv_text
from vacancy_monitor.models import ApplicationRecord, ApplicationStatus, MatchLabel, RankedVacancy, WorkFormat
from vacancy_monitor.openai_reporting import (
    OpenAIReportGenerationError,
    OpenAIReportingUnavailableError,
    generate_openai_application_report,
)
from vacancy_monitor.pipeline import build_adapter_registry, fetch_search_queries
from vacancy_monitor.pipeline import hydrate_ranked_vacancies as pipeline_hydrate_ranked_vacancies
from vacancy_monitor.ranking import build_ranked_vacancies
from vacancy_monitor.sources.json_import import load_vacancies_from_json
from vacancy_monitor.storage import Storage
from vacancy_monitor.ui.history_import import load_ui_application_entries
from vacancy_monitor.ui.playwright_exporter import ExportPageNotReadyError, PlaywrightUnavailableError, export_hh_page

LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Multi-source vacancy monitor")
    parser.add_argument("--config", default="config/profile.toml", help="Path to TOML candidate profile")
    parser.add_argument("--env-file", default=".env", help="Path to .env file")
    parser.add_argument("--db-path", default=None, help="Override SQLite database path")

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-db", help="Initialize SQLite database")

    import_json = subparsers.add_parser("import-json", help="Import vacancies from JSON or JSONL")
    import_json.add_argument("--input", required=True, help="Path to source JSON/JSONL file")
    import_json.add_argument("--source", default="json_import", help="Logical source name")

    fetch_habr = subparsers.add_parser("fetch-habr", help="Fetch vacancies from Habr Career public search")
    fetch_habr.add_argument("--text", required=True, help="Search text")
    fetch_habr.add_argument("--per-page", type=int, default=25, help="Items per page")
    fetch_habr.add_argument("--pages", type=int, default=1, help="Number of pages to fetch")
    fetch_habr.add_argument("--only-with-salary", action="store_true", help="Filter to vacancies with salary")
    fetch_habr.add_argument("--dry-run", action="store_true", help="Print the configured request without calling Habr")

    fetch_hh = subparsers.add_parser("fetch-hh", help="Fetch vacancies from hh.ru public API")
    fetch_hh.add_argument("--text", required=True, help="Search text")
    fetch_hh.add_argument("--per-page", type=int, default=20, help="Items per page")
    fetch_hh.add_argument("--pages", type=int, default=1, help="Number of pages to fetch")
    fetch_hh.add_argument("--area", type=int, default=None, help="hh.ru area id")
    fetch_hh.add_argument("--only-with-salary", action="store_true", help="Filter to vacancies with salary")
    fetch_hh.add_argument("--detailed", action="store_true", help="Fetch per-vacancy detail endpoint")
    fetch_hh.add_argument("--dry-run", action="store_true", help="Print the request params without calling hh.ru")

    fetch_remoteok = subparsers.add_parser("fetch-remoteok", help="Fetch vacancies from Remote OK public API")
    fetch_remoteok.add_argument("--text", required=True, help="Search text")
    fetch_remoteok.add_argument("--dry-run", action="store_true", help="Print the configured request without calling Remote OK")

    fetch_remotive = subparsers.add_parser("fetch-remotive", help="Fetch vacancies from Remotive public API")
    fetch_remotive.add_argument("--text", required=True, help="Search text")
    fetch_remotive.add_argument("--dry-run", action="store_true", help="Print the configured request without calling Remotive")

    fetch_wwr = subparsers.add_parser("fetch-weworkremotely", help="Fetch vacancies from We Work Remotely")
    fetch_wwr.add_argument("--url", required=True, help="Listing page URL")
    fetch_wwr.add_argument("--text", default="Ruby on Rails", help="Search label text")
    fetch_wwr.add_argument("--dry-run", action="store_true", help="Print the configured request without calling We Work Remotely")

    subparsers.add_parser("list-searches", help="Print configured source queries from profile config")
    parser_list = subparsers.choices["list-searches"]
    parser_list.add_argument("--source", default=None, help="Only show configured queries for one source family, for example hh")
    fetch_profile = subparsers.add_parser("fetch-profile", help="Fetch vacancies from all configured source adapters")
    fetch_profile.add_argument("--limit-queries", type=int, default=None, help="Only run the first N configured queries")
    fetch_profile.add_argument("--source", default=None, help="Only run configured queries for one source family, for example hh")
    fetch_profile.add_argument("--dry-run", action="store_true", help="Print configured requests without calling APIs")
    fetch_profile = subparsers.add_parser("fetch-hh-profile", help="Compatibility alias for fetch-profile")
    fetch_profile.add_argument("--limit-queries", type=int, default=None, help="Only run the first N configured queries")
    fetch_profile.add_argument("--source", default=None, help="Only run configured queries for one source family, for example hh")
    fetch_profile.add_argument("--dry-run", action="store_true", help="Print configured requests without calling hh.ru")

    rank = subparsers.add_parser("rank", help="Classify and rank stored vacancies")
    rank.add_argument("--top", type=int, default=20, help="Number of ranked vacancies to print")
    rank.add_argument(
        "--exclude-statuses",
        default="applied,ignore,rejected,interview",
        help="Comma-separated application statuses to exclude from ranking",
    )
    rank.add_argument("--source", default=None, help="Only rank one source family, for example hh")

    mark = subparsers.add_parser("mark", help="Mark vacancy status")
    mark.add_argument("--vacancy-id", required=True, help="Vacancy external id")
    mark.add_argument(
        "--status",
        required=True,
        choices=[status.value for status in ApplicationStatus if status != ApplicationStatus.NEW],
        help="Application status",
    )
    mark.add_argument("--note", default=None, help="Optional note")

    import_ui = subparsers.add_parser("import-ui-history", help="Import applied history from saved hh.ru HTML or JSON")
    import_ui.add_argument("--input", required=True, help="Path to saved hh.ru UI HTML or JSON file")
    import_ui.add_argument(
        "--status",
        default=ApplicationStatus.APPLIED.value,
        choices=[status.value for status in ApplicationStatus if status != ApplicationStatus.NEW],
        help="Status to assign to imported entries",
    )
    import_ui.add_argument("--note", default=None, help="Optional note to attach to imported entries")
    import_ui.add_argument(
        "--sync-missing",
        action="store_true",
        help="Replace stored application history with the imported set instead of only upserting",
    )

    export_ui = subparsers.add_parser("export-ui-history", help="Export hh.ru applied-history page via Playwright")
    export_ui.add_argument("--url", required=True, help="Target hh.ru page URL to export")
    export_ui.add_argument("--output", required=True, help="Output HTML path")
    export_ui.add_argument("--browser", default="chromium", choices=["chromium", "firefox", "webkit"])
    export_ui.add_argument("--headless", action="store_true", help="Run browser headlessly")
    export_ui.add_argument(
        "--login-wait-seconds",
        type=int,
        default=90,
        help="Time to wait for manual login/session recovery before capture",
    )
    export_ui.add_argument("--timeout-seconds", type=int, default=30, help="Timeout for page operations")
    export_ui.add_argument("--max-scrolls", type=int, default=12, help="How many scroll attempts to load more entries")
    export_ui.add_argument("--storage-state", default=None, help="Existing Playwright storage state JSON path")
    export_ui.add_argument("--save-storage-state", default=None, help="Where to save Playwright storage state JSON")
    export_ui.add_argument("--user-data-dir", default=None, help="Persistent browser profile directory")
    export_ui.add_argument("--screenshot", default=None, help="Optional screenshot output path")
    export_ui.add_argument(
        "--import-status",
        default=None,
        choices=[status.value for status in ApplicationStatus if status != ApplicationStatus.NEW],
        help="If set, import the exported file into application history with this status",
    )
    export_ui.add_argument(
        "--sync-missing",
        action="store_true",
        help="When importing exported results, replace stored application history with the imported set",
    )

    export_my_apps = subparsers.add_parser(
        "export-my-applications",
        help="Export your hh.ru applications page via Playwright using configured default URL",
    )
    export_my_apps.add_argument("--output", default=None, help="Output HTML path")
    export_my_apps.add_argument("--browser", default="chromium", choices=["chromium", "firefox", "webkit"])
    export_my_apps.add_argument("--headless", action="store_true", help="Run browser headlessly")
    export_my_apps.add_argument(
        "--login-wait-seconds",
        type=int,
        default=None,
        help="Time to wait for manual login/session recovery before capture",
    )
    export_my_apps.add_argument("--timeout-seconds", type=int, default=30, help="Timeout for page operations")
    export_my_apps.add_argument("--max-scrolls", type=int, default=12, help="How many scroll attempts to load more entries")
    export_my_apps.add_argument("--storage-state", default=None, help="Existing Playwright storage state JSON path")
    export_my_apps.add_argument("--save-storage-state", default=None, help="Where to save Playwright storage state JSON")
    export_my_apps.add_argument("--user-data-dir", default=None, help="Persistent browser profile directory")
    export_my_apps.add_argument("--screenshot", default=None, help="Optional screenshot output path")
    export_my_apps.add_argument(
        "--import-status",
        default=None,
        choices=[status.value for status in ApplicationStatus if status != ApplicationStatus.NEW],
        help="If set, import the exported file into application history with this status",
    )
    export_my_apps.add_argument(
        "--url",
        default=None,
        help="Override the configured HH_APPLICANT_HISTORY_URL if needed",
    )
    export_my_apps.add_argument(
        "--no-sync-missing",
        action="store_true",
        help="Keep existing history rows that are not present in the latest negotiations export",
    )

    report = subparsers.add_parser("report", help="Generate a markdown application report from ranked vacancies")
    report.add_argument("--output", default=None, help="Markdown report output path")
    report.add_argument(
        "--cv-path",
        default=None,
        help="Path to the candidate CV PDF that will be sent to OpenAI together with vacancy evidence",
    )
    report.add_argument(
        "--hydrate-top",
        type=int,
        default=None,
        help="Fetch hh.ru vacancy details for the top N shortlisted vacancies before sending evidence to OpenAI",
    )
    report.add_argument("--top-apply", type=int, default=None, help="How many apply-now vacancies to include")
    report.add_argument("--top-maybe", type=int, default=None, help="How many manual-review vacancies to include")
    report.add_argument("--top-skip", type=int, default=None, help="How many skip vacancies to include")
    report.add_argument(
        "--exclude-statuses",
        default="applied,ignore,rejected,interview",
        help="Comma-separated application statuses to exclude from ranking",
    )
    report.add_argument("--source", default=None, help="Only report on one source family, for example hh")

    subparsers.add_parser("history", help="Show application history")
    subparsers.add_parser("show-latest", help="Show latest saved ranking from SQLite")

    return parser


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def resolve_storage(args: argparse.Namespace) -> Storage:
    settings = load_settings(args.env_file)
    configure_logging(settings.log_level)
    db_path = Path(args.db_path) if args.db_path else settings.db_path
    storage = Storage(db_path)
    storage.init_db()
    return storage


def import_json_command(args: argparse.Namespace) -> int:
    storage = resolve_storage(args)
    profile = load_profile(args.config)
    vacancies = _filter_ignored_vacancies(load_vacancies_from_json(args.input, source=args.source), profile)
    inserted = storage.upsert_vacancies(vacancies)
    print(f"Imported {inserted} vacancies from {args.input}")
    return 0


def fetch_hh_command(args: argparse.Namespace) -> int:
    from vacancy_monitor.models import SearchQuery

    settings = load_settings(args.env_file)
    configure_logging(settings.log_level)
    profile = load_profile(args.config)
    query = SearchQuery(
        source="hh",
        name="ad_hoc",
        text=args.text,
        area=args.area,
        per_page=args.per_page,
        pages=args.pages,
        only_with_salary=args.only_with_salary,
        detailed=args.detailed,
    )
    if args.dry_run:
        print(f"hh.ru request plan for {query.name}:")
        for page in range(query.pages):
            params = query.to_params()
            params["page"] = page
            print(params)
        return 0

    storage = Storage(Path(args.db_path) if args.db_path else settings.db_path)
    storage.init_db()
    adapters = build_adapter_registry(settings)
    inserted, _, _ = fetch_search_queries(adapters, [query], profile=profile, storage=storage)
    print(f"Fetched and saved {inserted} vacancies from hh.ru")
    return 0


def fetch_habr_command(args: argparse.Namespace) -> int:
    from vacancy_monitor.models import SearchQuery
    from vacancy_monitor.sources.habr_api import HabrCareerClient

    settings = load_settings(args.env_file)
    configure_logging(settings.log_level)
    profile = load_profile(args.config)
    query = SearchQuery(
        source="habr",
        name="ad_hoc",
        text=args.text,
        per_page=args.per_page,
        pages=args.pages,
        only_with_salary=args.only_with_salary,
    )
    if args.dry_run:
        client = HabrCareerClient(base_url=settings.habr_base_url, user_agent=settings.habr_user_agent)
        print(f"Habr Career request plan for {query.name}:")
        for page in range(1, max(query.pages, 1) + 1):
            print(client.build_search_preview(query, page))
        return 0

    storage = Storage(Path(args.db_path) if args.db_path else settings.db_path)
    storage.init_db()
    adapters = build_adapter_registry(settings)
    inserted, _, _ = fetch_search_queries(adapters, [query], profile=profile, storage=storage)
    print(f"Fetched and saved {inserted} vacancies from Habr Career")
    return 0


def fetch_remoteok_command(args: argparse.Namespace) -> int:
    from vacancy_monitor.models import SearchQuery

    settings = load_settings(args.env_file)
    configure_logging(settings.log_level)
    profile = load_profile(args.config)
    query = SearchQuery(source="remoteok", name="ad_hoc", text=args.text, fetch_all=True, pages=1, per_page=100)
    if args.dry_run:
        print(f"Remote OK request plan for {query.name}:")
        print({"source": query.source, "endpoint": "/api", "query_filter": query.text})
        return 0

    storage = Storage(Path(args.db_path) if args.db_path else settings.db_path)
    storage.init_db()
    adapters = build_adapter_registry(settings)
    inserted, _, _ = fetch_search_queries(adapters, [query], profile=profile, storage=storage)
    print(f"Fetched and saved {inserted} vacancies from Remote OK")
    return 0


def fetch_remotive_command(args: argparse.Namespace) -> int:
    from vacancy_monitor.models import SearchQuery

    settings = load_settings(args.env_file)
    configure_logging(settings.log_level)
    profile = load_profile(args.config)
    query = SearchQuery(source="remotive", name="ad_hoc", text=args.text, fetch_all=True, pages=1, per_page=100)
    if args.dry_run:
        print(f"Remotive request plan for {query.name}:")
        print({"source": query.source, "endpoint": "/api/remote-jobs", "query_filter": query.text})
        return 0

    storage = Storage(Path(args.db_path) if args.db_path else settings.db_path)
    storage.init_db()
    adapters = build_adapter_registry(settings)
    inserted, _, _ = fetch_search_queries(adapters, [query], profile=profile, storage=storage)
    print(f"Fetched and saved {inserted} vacancies from Remotive")
    return 0


def fetch_weworkremotely_command(args: argparse.Namespace) -> int:
    from vacancy_monitor.models import SearchQuery

    settings = load_settings(args.env_file)
    configure_logging(settings.log_level)
    profile = load_profile(args.config)
    query = SearchQuery(
        source="weworkremotely",
        name="ad_hoc",
        text=args.text,
        fetch_all=False,
        pages=1,
        per_page=100,
        source_url=args.url,
    )
    if args.dry_run:
        print(f"We Work Remotely request plan for {query.name}:")
        print({"source": query.source, "url": query.source_url, "query_filter": query.text})
        return 0

    storage = Storage(Path(args.db_path) if args.db_path else settings.db_path)
    storage.init_db()
    adapters = build_adapter_registry(settings)
    inserted, _, _ = fetch_search_queries(adapters, [query], profile=profile, storage=storage)
    print(f"Fetched and saved {inserted} vacancies from We Work Remotely")
    return 0


def list_searches_command(args: argparse.Namespace) -> int:
    profile = load_profile(args.config)
    if profile.ignored_vacancy_ids_by_source:
        for source_name, values in sorted(profile.ignored_vacancy_ids_by_source.items()):
            print(f"Ignored vacancy ids [{source_name}]: {len(values)}")
    if not profile.search_queries:
        print("No source queries configured in profile.")
        return 0

    queries = _filter_queries_by_source(profile.search_queries, args.source)
    if not queries:
        print("No source queries match the requested filter.")
        return 0

    for query in queries:
        print(
            f"{query.priority:>3} | {query.source} | {query.name} | label={query.label} | pages={query.pages} | per_page={query.per_page}"
        )
        print(f"    text={query.text}")
        extras = []
        if query.area is not None:
            extras.append(f"area={query.area}")
        if query.order_by:
            extras.append(f"order_by={query.order_by}")
        if query.search_field:
            extras.append(f"search_field={query.search_field}")
        if query.schedule:
            extras.append(f"schedule={query.schedule}")
        if query.employment:
            extras.append(f"employment={query.employment}")
        if query.experience:
            extras.append(f"experience={query.experience}")
        if query.source_url:
            extras.append(f"source_url={query.source_url}")
        extras.append(f"fetch_all={query.fetch_all}")
        extras.append(f"detailed={query.detailed}")
        extras.append(f"only_with_salary={query.only_with_salary}")
        print(f"    options={', '.join(extras)}")
    return 0


def fetch_profile_command(args: argparse.Namespace) -> int:
    settings = load_settings(args.env_file)
    configure_logging(settings.log_level)
    profile = load_profile(args.config)
    if not profile.search_queries:
        print("No search queries configured in profile.", file=sys.stderr)
        return 1

    queries = _filter_queries_by_source(profile.search_queries, args.source)
    queries = queries[: args.limit_queries] if args.limit_queries else queries
    if not queries:
        print("No configured queries match the requested filter.", file=sys.stderr)
        return 1
    if args.dry_run:
        for query in queries:
            print(f"{query.source}:{query.name} ({query.label}):")
            if query.source == "habr":
                from vacancy_monitor.sources.habr_api import HabrCareerClient

                client = HabrCareerClient(base_url=settings.habr_base_url, user_agent=settings.habr_user_agent)
                preview_pages = query.pages if not query.fetch_all else 3
                for page in range(1, max(preview_pages, 1) + 1):
                    print(f"    {client.build_search_preview(query, page)}")
                if query.fetch_all:
                    print("    ... fetch_all=true, will continue until Habr pages are exhausted")
            elif query.source == "hh":
                preview_pages = query.pages if not query.fetch_all else 3
                for page in range(preview_pages):
                    params = query.to_params()
                    params["page"] = page
                    print(f"    {params}")
                if query.fetch_all:
                    print("    ... fetch_all=true, will continue until hh.ru pages are exhausted")
            elif query.source == "remoteok":
                print(f"    {{'endpoint': '/api', 'query_filter': {query.text!r}}}")
            elif query.source == "remotive":
                print(f"    {{'endpoint': '/api/remote-jobs', 'query_filter': {query.text!r}}}")
            elif query.source == "weworkremotely":
                print(f"    {{'url': {query.source_url!r}, 'query_filter': {query.text!r}}}")
            else:
                print("    source adapter placeholder only")
        return 0

    storage = Storage(Path(args.db_path) if args.db_path else settings.db_path)
    storage.init_db()
    adapters = build_adapter_registry(settings)
    total, _, details = fetch_search_queries(adapters, queries, profile=profile, storage=storage)
    for query, fetched, saved in details:
        print(f"{query.source}:{query.name}: fetched {fetched} vacancies, saved {saved}")
    print(f"Total fetched and saved from configured profile queries: {total}")
    return 0


def _parse_statuses(raw_statuses: str) -> set[ApplicationStatus]:
    statuses: set[ApplicationStatus] = set()
    for item in raw_statuses.split(","):
        normalized = item.strip()
        if not normalized:
            continue
        statuses.add(ApplicationStatus(normalized))
    return statuses


def _filter_ignored_vacancies(vacancies: list, profile) -> list:
    if not profile.ignored_vacancy_ids_by_source:
        return vacancies
    filtered = [vacancy for vacancy in vacancies if not vacancy_is_ignored(profile, vacancy)]
    skipped = len(vacancies) - len(filtered)
    if skipped:
        LOGGER.info("Skipped %s vacancies from ignored-vacancy file", skipped)
    return filtered


def _filter_archived_vacancies(vacancies: list) -> list:
    filtered = [vacancy for vacancy in vacancies if not getattr(vacancy, "is_archived", False)]
    skipped = len(vacancies) - len(filtered)
    if skipped:
        LOGGER.info("Skipped %s archived vacancies", skipped)
    return filtered


def _filter_queries_by_source(queries, source_name: str | None):
    if not source_name:
        return list(queries)
    normalized = source_name.strip().lower()
    return [query for query in queries if source_family(query.source) == normalized]


def _filter_vacancies_by_source(vacancies, source_name: str | None):
    if not source_name:
        return list(vacancies)
    normalized = source_name.strip().lower()
    return [vacancy for vacancy in vacancies if source_family(vacancy.source) == normalized]


def _ranked_vacancies(
    storage: Storage,
    config_path: str,
    excluded: set[ApplicationStatus],
    *,
    source_name: str | None = None,
) -> list[RankedVacancy]:
    profile = load_profile(config_path)
    statuses = storage.get_application_statuses()
    vacancies = storage.list_vacancies(exclude_statuses=excluded)
    vacancies = _filter_archived_vacancies(vacancies)
    vacancies = _filter_vacancies_by_source(vacancies, source_name)
    if profile.ignored_vacancy_ids_by_source:
        vacancies = [vacancy for vacancy in vacancies if not vacancy_is_ignored(profile, vacancy)]
    if profile.preferences.remote_only:
        vacancies = [vacancy for vacancy in vacancies if vacancy.work_format == WorkFormat.REMOTE]
    return build_ranked_vacancies(vacancies, profile=profile, statuses=statuses)


def _hydrate_ranked_vacancies(
    storage: Storage,
    *,
    config_path: str,
    excluded: set[ApplicationStatus],
    settings,
    limit: int,
    client=None,
    source_name: str | None = None,
) -> list[RankedVacancy]:
    if limit <= 0:
        return _ranked_vacancies(storage, config_path, excluded, source_name=source_name)

    ranked = _ranked_vacancies(storage, config_path, excluded, source_name=source_name)
    if not ranked:
        return ranked

    if client is not None:
        from vacancy_monitor.adapters.base import AdapterCapabilities, BaseAdapter
        from vacancy_monitor.normalization import vacancy_from_payload

        class InlineHHAdapter(BaseAdapter):
            source_name = "hh"
            capabilities = AdapterCapabilities(supports_detail_hydration=True)

            def search(self, query, **kwargs):
                raise NotImplementedError

            def fetch_details(self, external_id: str, *, raw_item=None):
                return client.get_vacancy(external_id)

            def normalize(self, raw_item, raw_details=None):
                return vacancy_from_payload(raw_details or raw_item, source=raw_item.get("source", "hh_api:test"))

        adapters: dict[str, BaseAdapter] = {"hh": InlineHHAdapter()}
    else:
        adapters = build_adapter_registry(settings)
    profile = load_profile(config_path)
    return pipeline_hydrate_ranked_vacancies(
        ranked,
        adapters=adapters,
        storage=storage,
        profile=profile,
        excluded=excluded,
        limit=limit,
    )


def _label_ru(label: MatchLabel) -> str:
    mapping = {
        MatchLabel.STRONG_AI: "Strong AI Match",
        MatchLabel.AI_TRANSITION: "AI Transition Match",
        MatchLabel.MODERATE_AI: "Moderate AI Match",
        MatchLabel.STRONG_RUBY: "Ruby Primary Match",
        MatchLabel.MODERATE_RUBY: "Ruby Core Match",
        MatchLabel.POSSIBLE: "Possible Match",
        MatchLabel.SKIP: "Skip",
    }
    return mapping[label]


def _print_ranked(items: list[RankedVacancy], top: int) -> None:
    if not items:
        print("Нет вакансий для ранжирования.")
        return

    for index, item in enumerate(items[:top], start=1):
        vacancy = item.vacancy
        analysis = item.analysis
        print(f"[{index}] {vacancy.title} | {_label_ru(analysis.label)} | score={analysis.score} | action={analysis.action.value}")
        print(f"    Компания: {vacancy.company}")
        print(f"    Трек: {analysis.track.value} | Формат: {vacancy.work_format.value} | Локация: {vacancy.location}")
        print(f"    Зарплата в вакансии: {vacancy.salary.display()} | Ожидание: {analysis.expected_salary}")
        print(f"    Почему подходит: {', '.join(analysis.reasons) if analysis.reasons else 'совпадений мало'}")
        print(f"    Что проверить: {', '.join(analysis.concerns) if analysis.concerns else 'существенных красных флагов нет'}")
        print(f"    Итог: {analysis.summary_ru}")
        if vacancy.url:
            print(f"    URL: {vacancy.url}")
        print("")


def _warn_if_history_missing(storage: Storage, excluded: set[ApplicationStatus]) -> None:
    tracked_statuses = {ApplicationStatus.APPLIED, ApplicationStatus.INTERVIEW, ApplicationStatus.REJECTED, ApplicationStatus.IGNORE}
    if not (excluded & tracked_statuses):
        return
    if storage.application_history_count() > 0:
        return
    print(
        "Warning: application_history is empty, so applied/rejected/interview vacancies cannot be excluded. "
        "Run export-my-applications against this same --db-path first.",
        file=sys.stderr,
    )


def _resolve_export_my_applications_args(args: argparse.Namespace, profile) -> argparse.Namespace:
    defaults = profile.defaults.export_my_applications
    resolved = argparse.Namespace(**vars(args))
    resolved.output = args.output or defaults.output_path
    resolved.storage_state = args.storage_state or defaults.storage_state_path
    resolved.save_storage_state = args.save_storage_state or defaults.save_storage_state_path
    resolved.login_wait_seconds = (
        args.login_wait_seconds if args.login_wait_seconds is not None else defaults.login_wait_seconds
    )
    resolved.import_status = args.import_status or defaults.import_status
    return resolved


def _resolve_report_args(args: argparse.Namespace, profile) -> argparse.Namespace:
    defaults = profile.defaults.report
    resolved = argparse.Namespace(**vars(args))
    resolved.output = args.output or defaults.output_path
    resolved.cv_path = args.cv_path or defaults.cv_path
    resolved.hydrate_top = args.hydrate_top if args.hydrate_top is not None else defaults.hydrate_top
    resolved.top_apply = args.top_apply if args.top_apply is not None else defaults.top_apply
    resolved.top_maybe = args.top_maybe if args.top_maybe is not None else defaults.top_maybe
    resolved.top_skip = args.top_skip if args.top_skip is not None else defaults.top_skip
    resolved.source = args.source or defaults.source
    return resolved


def rank_command(args: argparse.Namespace) -> int:
    storage = resolve_storage(args)
    excluded = _parse_statuses(args.exclude_statuses)
    _warn_if_history_missing(storage, excluded)
    ranked = _ranked_vacancies(storage, args.config, excluded, source_name=args.source)
    if ranked:
        storage.save_ranking_results(ranked)
    _print_ranked(ranked, args.top)
    print(f"Сохранено результатов: {len(ranked)}")
    return 0


def mark_command(args: argparse.Namespace) -> int:
    storage = resolve_storage(args)
    if not storage.vacancy_exists(args.vacancy_id):
        print(f"Vacancy not found: {args.vacancy_id}", file=sys.stderr)
        return 1

    storage.mark_application(
        ApplicationRecord(
            vacancy_id=args.vacancy_id,
            status=ApplicationStatus(args.status),
            note=args.note,
        )
    )
    print(f"Updated {args.vacancy_id} -> {args.status}")
    return 0


def import_ui_history_command(args: argparse.Namespace) -> int:
    storage = resolve_storage(args)
    entries = load_ui_application_entries(
        path=args.input,
        default_status=ApplicationStatus(args.status),
        note=args.note,
    )
    imported = storage.sync_application_entries(entries) if args.sync_missing else storage.import_application_entries(entries)
    print(f"Imported {imported} UI history entries from {args.input}")
    return 0


def export_ui_history_command(args: argparse.Namespace) -> int:
    try:
        result = export_hh_page(
            url=args.url,
            output_path=args.output,
            browser_name=args.browser,
            headless=args.headless,
            timeout_ms=args.timeout_seconds * 1000,
            login_wait_seconds=args.login_wait_seconds,
            max_scrolls=args.max_scrolls,
            storage_state_path=args.storage_state,
            save_storage_state_path=args.save_storage_state,
            user_data_dir=args.user_data_dir,
            screenshot_path=args.screenshot,
        )
    except PlaywrightUnavailableError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except ExportPageNotReadyError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(
        f"Exported hh.ru page to {result.output_path} "
        f"(title={result.page_title!r}, final_url={result.final_url}, vacancy_links={result.vacancy_link_count})"
    )
    print(f"Metadata saved to {result.metadata_path}")

    if args.import_status:
        storage = resolve_storage(args)
        entries = load_ui_application_entries(
            path=result.output_path,
            default_status=ApplicationStatus(args.import_status),
            note=f"Imported from Playwright export: {Path(result.output_path).name}",
        )
        imported = storage.sync_application_entries(entries) if args.sync_missing else storage.import_application_entries(entries)
        print(f"Imported {imported} UI history entries into SQLite")
    return 0


def export_my_applications_command(args: argparse.Namespace) -> int:
    profile = load_profile(args.config)
    resolved_args = _resolve_export_my_applications_args(args, profile)
    target_url = resolved_args.url or profile.applicant_history_url
    if not target_url:
        print(
            "Applicant history URL is not configured. Add [hh].applicant_history_url to your profile or pass --url.",
            file=sys.stderr,
        )
        return 1
    export_values = vars(resolved_args).copy()
    export_values["url"] = target_url
    export_values["sync_missing"] = not resolved_args.no_sync_missing
    export_args = argparse.Namespace(**export_values)
    return export_ui_history_command(export_args)


def report_command(args: argparse.Namespace) -> int:
    settings = load_settings(args.env_file)
    configure_logging(settings.log_level)
    storage = Storage(Path(args.db_path) if args.db_path else settings.db_path)
    storage.init_db()
    excluded = _parse_statuses(args.exclude_statuses)
    _warn_if_history_missing(storage, excluded)
    profile = load_profile(args.config)
    resolved_args = _resolve_report_args(args, profile)
    ranked = _hydrate_ranked_vacancies(
        storage,
        config_path=args.config,
        excluded=excluded,
        settings=settings,
        limit=resolved_args.hydrate_top,
        source_name=resolved_args.source,
    )
    if ranked:
        storage.save_ranking_results(ranked)

    output_path = Path(resolved_args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        cv_text = extract_cv_text(resolved_args.cv_path)
    except CvExtractionError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    try:
        report_text = generate_openai_application_report(
            api_key=settings.openai_api_key,
            model=settings.openai_report_model,
            profile=profile,
            cv_text=cv_text,
            ranked=ranked,
            top_apply=resolved_args.top_apply,
            top_maybe=resolved_args.top_maybe,
            top_skip=resolved_args.top_skip,
        )
    except (OpenAIReportingUnavailableError, OpenAIReportGenerationError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    output_path.write_text(report_text, encoding="utf-8")
    print(f"Saved OpenAI report to {output_path}")
    print(f"Vacancies analyzed: {len(ranked)}")
    print(f"Remote-only filter: {profile.preferences.remote_only}")
    print(f"Model: {settings.openai_report_model}")
    return 0


def history_command(args: argparse.Namespace) -> int:
    storage = resolve_storage(args)
    rows = storage.list_application_history()
    if not rows:
        print("История откликов пустая.")
        return 0

    for row in rows:
        note = f" | note={row.note}" if row.note else ""
        print(f"{row.updated_at} | {row.vacancy_id} | {row.status.value}{note}")
    return 0


def show_latest_command(args: argparse.Namespace) -> int:
    storage = resolve_storage(args)
    latest = storage.get_latest_ranking()
    if not latest:
        print("Сохраненных результатов ранжирования пока нет.")
        return 0

    ranked = [
        RankedVacancy(vacancy=vacancy, analysis=analysis, application_status=ApplicationStatus.NEW)
        for analysis, vacancy in latest
    ]
    _print_ranked(ranked, top=len(ranked))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "init-db":
        storage = resolve_storage(args)
        LOGGER.info("Initialized database at %s", storage.db_path)
        print(f"Initialized database: {storage.db_path}")
        return 0
    if args.command == "import-json":
        return import_json_command(args)
    if args.command == "fetch-habr":
        return fetch_habr_command(args)
    if args.command == "fetch-hh":
        return fetch_hh_command(args)
    if args.command == "fetch-remoteok":
        return fetch_remoteok_command(args)
    if args.command == "fetch-remotive":
        return fetch_remotive_command(args)
    if args.command == "fetch-weworkremotely":
        return fetch_weworkremotely_command(args)
    if args.command == "list-searches":
        return list_searches_command(args)
    if args.command == "fetch-profile":
        return fetch_profile_command(args)
    if args.command == "fetch-hh-profile":
        return fetch_profile_command(args)
    if args.command == "rank":
        return rank_command(args)
    if args.command == "mark":
        return mark_command(args)
    if args.command == "import-ui-history":
        return import_ui_history_command(args)
    if args.command == "export-ui-history":
        return export_ui_history_command(args)
    if args.command == "export-my-applications":
        return export_my_applications_command(args)
    if args.command == "report":
        return report_command(args)
    if args.command == "history":
        return history_command(args)
    if args.command == "show-latest":
        return show_latest_command(args)

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
