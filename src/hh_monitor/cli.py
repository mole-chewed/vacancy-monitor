from __future__ import annotations

import argparse
import logging
from pathlib import Path
import sys

from hh_monitor.config import load_profile, load_settings
from hh_monitor.cover_letters import build_cover_letter_filename, build_cover_letter_ru
from hh_monitor.cv import CvExtractionError, extract_cv_text
from hh_monitor.models import ApplicationRecord, ApplicationStatus, MatchLabel, RankedVacancy, VacancyTrack, WorkFormat
from hh_monitor.openai_reporting import (
    OpenAIReportGenerationError,
    OpenAIReportingUnavailableError,
    generate_openai_application_report,
)
from hh_monitor.scoring import analyze_vacancy
from hh_monitor.sources.json_import import load_vacancies_from_json
from hh_monitor.storage import Storage
from hh_monitor.ui.history_import import load_ui_application_entries
from hh_monitor.ui.playwright_exporter import ExportPageNotReadyError, PlaywrightUnavailableError, export_hh_page


LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="hh.ru vacancy monitor")
    parser.add_argument("--config", default="config/profile.toml", help="Path to TOML candidate profile")
    parser.add_argument("--env-file", default=".env", help="Path to .env file")
    parser.add_argument("--db-path", default=None, help="Override SQLite database path")

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-db", help="Initialize SQLite database")

    import_json = subparsers.add_parser("import-json", help="Import vacancies from JSON or JSONL")
    import_json.add_argument("--input", required=True, help="Path to source JSON/JSONL file")
    import_json.add_argument("--source", default="json_import", help="Logical source name")

    fetch_hh = subparsers.add_parser("fetch-hh", help="Fetch vacancies from hh.ru public API")
    fetch_hh.add_argument("--text", required=True, help="Search text")
    fetch_hh.add_argument("--per-page", type=int, default=20, help="Items per page")
    fetch_hh.add_argument("--pages", type=int, default=1, help="Number of pages to fetch")
    fetch_hh.add_argument("--area", type=int, default=None, help="hh.ru area id")
    fetch_hh.add_argument("--only-with-salary", action="store_true", help="Filter to vacancies with salary")
    fetch_hh.add_argument("--detailed", action="store_true", help="Fetch per-vacancy detail endpoint")
    fetch_hh.add_argument("--dry-run", action="store_true", help="Print the request params without calling hh.ru")

    subparsers.add_parser("list-searches", help="Print hh.ru search queries from profile config")
    fetch_profile = subparsers.add_parser("fetch-hh-profile", help="Fetch vacancies from hh.ru using profile searches")
    fetch_profile.add_argument("--limit-queries", type=int, default=None, help="Only run the first N configured queries")
    fetch_profile.add_argument("--dry-run", action="store_true", help="Print configured requests without calling hh.ru")

    rank = subparsers.add_parser("rank", help="Classify and rank stored vacancies")
    rank.add_argument("--top", type=int, default=20, help="Number of ranked vacancies to print")
    rank.add_argument(
        "--exclude-statuses",
        default="applied,ignore,rejected,interview",
        help="Comma-separated application statuses to exclude from ranking",
    )

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
    export_my_apps.add_argument("--output", required=True, help="Output HTML path")
    export_my_apps.add_argument("--browser", default="chromium", choices=["chromium", "firefox", "webkit"])
    export_my_apps.add_argument("--headless", action="store_true", help="Run browser headlessly")
    export_my_apps.add_argument(
        "--login-wait-seconds",
        type=int,
        default=90,
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
    report.add_argument("--output", default="data/application_report.md", help="Markdown report output path")
    report.add_argument(
        "--cv-path",
        default="data/Alexander_Kharitonov_CV_ENG_2026.pdf",
        help="Path to the candidate CV PDF that will be sent to OpenAI together with vacancy evidence",
    )
    report.add_argument("--top-apply", type=int, default=25, help="How many apply-now vacancies to include")
    report.add_argument("--top-maybe", type=int, default=25, help="How many manual-review vacancies to include")
    report.add_argument("--top-skip", type=int, default=10, help="How many skip vacancies to include")
    report.add_argument(
        "--exclude-statuses",
        default="applied,ignore,rejected,interview",
        help="Comma-separated application statuses to exclude from ranking",
    )

    cover_letters = subparsers.add_parser("draft-cover-letters", help="Generate Russian cover letters for vacancy ids")
    cover_letters.add_argument(
        "--vacancy-id",
        dest="vacancy_ids",
        action="append",
        required=True,
        help="Vacancy external id. Repeat the flag for multiple vacancies.",
    )
    cover_letters.add_argument("--output-dir", default="data/cover_letters", help="Directory for generated markdown files")

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
    vacancies = load_vacancies_from_json(args.input, source=args.source)
    inserted = storage.upsert_vacancies(vacancies)
    print(f"Imported {inserted} vacancies from {args.input}")
    return 0


def fetch_hh_command(args: argparse.Namespace) -> int:
    from hh_monitor.sources.hh_api import HeadHunterClient
    from hh_monitor.models import SearchQuery

    settings = load_settings(args.env_file)
    configure_logging(settings.log_level)
    query = SearchQuery(
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
    client = HeadHunterClient(
        base_url=settings.hh_api_base_url,
        user_agent=settings.hh_user_agent,
        api_token=settings.hh_api_token,
    )
    vacancies = client.search_vacancies_by_query(query)
    inserted = storage.upsert_vacancies(vacancies)
    print(f"Fetched and saved {inserted} vacancies from hh.ru")
    return 0


def list_searches_command(args: argparse.Namespace) -> int:
    profile = load_profile(args.config)
    if not profile.search_queries:
        print("No hh.ru search queries configured in profile.")
        return 0

    for query in profile.search_queries:
        print(
            f"{query.priority:>3} | {query.name} | label={query.label} | pages={query.pages} | per_page={query.per_page}"
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
        extras.append(f"detailed={query.detailed}")
        extras.append(f"only_with_salary={query.only_with_salary}")
        print(f"    options={', '.join(extras)}")
    return 0


def fetch_hh_profile_command(args: argparse.Namespace) -> int:
    from hh_monitor.sources.hh_api import HeadHunterClient

    settings = load_settings(args.env_file)
    configure_logging(settings.log_level)
    profile = load_profile(args.config)
    if not profile.search_queries:
        print("No hh.ru search queries configured in profile.", file=sys.stderr)
        return 1

    queries = profile.search_queries[: args.limit_queries] if args.limit_queries else profile.search_queries
    if args.dry_run:
        for query in queries:
            print(f"{query.name} ({query.label}):")
            for page in range(query.pages):
                params = query.to_params()
                params["page"] = page
                print(f"    {params}")
        return 0

    storage = Storage(Path(args.db_path) if args.db_path else settings.db_path)
    storage.init_db()
    client = HeadHunterClient(
        base_url=settings.hh_api_base_url,
        user_agent=settings.hh_user_agent,
        api_token=settings.hh_api_token,
    )

    total = 0
    for query in queries:
        vacancies = client.search_vacancies_by_query(query)
        inserted = storage.upsert_vacancies(vacancies)
        total += inserted
        print(f"{query.name}: fetched {len(vacancies)} vacancies, saved {inserted}")
    print(f"Total fetched and saved from hh.ru profile queries: {total}")
    return 0


def _parse_statuses(raw_statuses: str) -> set[ApplicationStatus]:
    statuses: set[ApplicationStatus] = set()
    for item in raw_statuses.split(","):
        normalized = item.strip()
        if not normalized:
            continue
        statuses.add(ApplicationStatus(normalized))
    return statuses


def _ranked_vacancies(storage: Storage, config_path: str, excluded: set[ApplicationStatus]) -> list[RankedVacancy]:
    profile = load_profile(config_path)
    statuses = storage.get_application_statuses()
    vacancies = storage.list_vacancies(exclude_statuses=excluded)
    if profile.preferences.remote_only:
        vacancies = [vacancy for vacancy in vacancies if vacancy.work_format == WorkFormat.REMOTE]
    ranked: list[RankedVacancy] = []
    for vacancy in vacancies:
        analysis = analyze_vacancy(vacancy, profile)
        if analysis.track not in {VacancyTrack.AI, VacancyTrack.RUBY}:
            continue
        ranked.append(
            RankedVacancy(
                vacancy=vacancy,
                analysis=analysis,
                application_status=statuses.get(vacancy.external_id, ApplicationStatus.NEW),
            )
        )
    ranked.sort(
        key=lambda item: (
            item.analysis.priority_bucket,
            -item.analysis.score,
            -len(item.analysis.reasons),
            item.vacancy.title.lower(),
        )
    )
    return ranked


def _label_ru(label: MatchLabel) -> str:
    mapping = {
        MatchLabel.STRONG_AI: "AI Priority Match",
        MatchLabel.AI_TRANSITION: "AI Transition Match",
        MatchLabel.MODERATE_AI: "Moderate AI Match",
        MatchLabel.STRONG_RUBY: "Strong Ruby Match",
        MatchLabel.MODERATE_RUBY: "Moderate Ruby Match",
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
        print(f"    Outline: {' | '.join(analysis.cover_letter_outline)}")
        if vacancy.url:
            print(f"    URL: {vacancy.url}")
        print("")


def rank_command(args: argparse.Namespace) -> int:
    storage = resolve_storage(args)
    ranked = _ranked_vacancies(storage, args.config, _parse_statuses(args.exclude_statuses))
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
    target_url = args.url or profile.applicant_history_url
    if not target_url:
        print(
            "Applicant history URL is not configured. Add [hh].applicant_history_url to your profile or pass --url.",
            file=sys.stderr,
        )
        return 1
    export_values = vars(args).copy()
    export_values["url"] = target_url
    export_values["sync_missing"] = not args.no_sync_missing
    export_args = argparse.Namespace(**export_values)
    return export_ui_history_command(export_args)


def report_command(args: argparse.Namespace) -> int:
    settings = load_settings(args.env_file)
    configure_logging(settings.log_level)
    storage = Storage(Path(args.db_path) if args.db_path else settings.db_path)
    storage.init_db()
    ranked = _ranked_vacancies(storage, args.config, _parse_statuses(args.exclude_statuses))
    if ranked:
        storage.save_ranking_results(ranked)

    profile = load_profile(args.config)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        cv_text = extract_cv_text(args.cv_path)
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
            top_apply=args.top_apply,
            top_maybe=args.top_maybe,
            top_skip=args.top_skip,
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


def draft_cover_letters_command(args: argparse.Namespace) -> int:
    storage = resolve_storage(args)
    profile = load_profile(args.config)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    generated_paths: list[Path] = []
    missing_ids: list[str] = []
    for vacancy_id in args.vacancy_ids:
        vacancy = storage.get_vacancy(vacancy_id)
        if vacancy is None:
            missing_ids.append(vacancy_id)
            continue
        analysis = analyze_vacancy(vacancy, profile)
        content = build_cover_letter_ru(profile, vacancy, analysis)
        filename = build_cover_letter_filename(vacancy)
        output_path = output_dir / filename
        output_path.write_text(content, encoding="utf-8")
        generated_paths.append(output_path)

    index_lines = ["# Draft Cover Letters", ""]
    for path in generated_paths:
        index_lines.append(f"- {path.name}")
    (output_dir / "index.md").write_text("\n".join(index_lines).strip() + "\n", encoding="utf-8")

    for path in generated_paths:
        print(f"Generated {path}")
    if missing_ids:
        print(f"Vacancy ids not found: {', '.join(missing_ids)}", file=sys.stderr)
        return 1
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
    if args.command == "fetch-hh":
        return fetch_hh_command(args)
    if args.command == "list-searches":
        return list_searches_command(args)
    if args.command == "fetch-hh-profile":
        return fetch_hh_profile_command(args)
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
    if args.command == "draft-cover-letters":
        return draft_cover_letters_command(args)
    if args.command == "history":
        return history_command(args)
    if args.command == "show-latest":
        return show_latest_command(args)

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
