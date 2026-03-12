from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
from typing import Iterator

from hh_monitor.models import (
    ApplicationRecord,
    ApplicationStatus,
    MatchLabel,
    RankedVacancy,
    RecommendedAction,
    SalaryRange,
    UiApplicationEntry,
    Vacancy,
    VacancyAnalysis,
    VacancyTrack,
    WorkFormat,
)


class Storage:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS vacancies (
                    external_id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    title TEXT NOT NULL,
                    company TEXT NOT NULL,
                    url TEXT,
                    salary_from INTEGER,
                    salary_to INTEGER,
                    salary_currency TEXT,
                    salary_gross INTEGER,
                    location TEXT NOT NULL,
                    work_format TEXT NOT NULL,
                    employment_type TEXT NOT NULL,
                    experience_level TEXT NOT NULL,
                    description TEXT NOT NULL,
                    requirements TEXT NOT NULL,
                    key_skills_json TEXT NOT NULL,
                    normalized_text TEXT NOT NULL,
                    raw_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS application_history (
                    vacancy_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    note TEXT,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(vacancy_id) REFERENCES vacancies(external_id)
                );

                CREATE TABLE IF NOT EXISTS ranking_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    total_vacancies INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS ranking_results (
                    run_id INTEGER NOT NULL,
                    vacancy_id TEXT NOT NULL,
                    track TEXT NOT NULL,
                    score INTEGER NOT NULL,
                    priority_bucket INTEGER NOT NULL,
                    label TEXT NOT NULL,
                    action TEXT NOT NULL,
                    reasons_json TEXT NOT NULL,
                    concerns_json TEXT NOT NULL,
                    matched_keywords_json TEXT NOT NULL,
                    red_flags_json TEXT NOT NULL,
                    expected_salary TEXT NOT NULL,
                    cover_letter_json TEXT NOT NULL,
                    summary_ru TEXT NOT NULL,
                    generated_at TEXT NOT NULL,
                    PRIMARY KEY (run_id, vacancy_id),
                    FOREIGN KEY(run_id) REFERENCES ranking_runs(id),
                    FOREIGN KEY(vacancy_id) REFERENCES vacancies(external_id)
                );
                """
            )

    def upsert_vacancies(self, vacancies: list[Vacancy]) -> int:
        if not vacancies:
            return 0

        with self.connect() as conn:
            conn.executemany(
                """
                INSERT INTO vacancies (
                    external_id, source, title, company, url,
                    salary_from, salary_to, salary_currency, salary_gross,
                    location, work_format, employment_type, experience_level,
                    description, requirements, key_skills_json, normalized_text,
                    raw_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(external_id) DO UPDATE SET
                    source=excluded.source,
                    title=excluded.title,
                    company=excluded.company,
                    url=excluded.url,
                    salary_from=excluded.salary_from,
                    salary_to=excluded.salary_to,
                    salary_currency=excluded.salary_currency,
                    salary_gross=excluded.salary_gross,
                    location=excluded.location,
                    work_format=excluded.work_format,
                    employment_type=excluded.employment_type,
                    experience_level=excluded.experience_level,
                    description=excluded.description,
                    requirements=excluded.requirements,
                    key_skills_json=excluded.key_skills_json,
                    normalized_text=excluded.normalized_text,
                    raw_json=excluded.raw_json,
                    updated_at=excluded.updated_at
                """,
                [
                    (
                        vacancy.external_id,
                        vacancy.source,
                        vacancy.title,
                        vacancy.company,
                        vacancy.url,
                        vacancy.salary.amount_from,
                        vacancy.salary.amount_to,
                        vacancy.salary.currency,
                        None if vacancy.salary.gross is None else int(vacancy.salary.gross),
                        vacancy.location,
                        vacancy.work_format.value,
                        vacancy.employment_type,
                        vacancy.experience_level,
                        vacancy.description,
                        vacancy.requirements,
                        json.dumps(vacancy.key_skills, ensure_ascii=False),
                        vacancy.normalized_text,
                        json.dumps(vacancy.raw_data, ensure_ascii=False),
                        vacancy.created_at,
                        vacancy.created_at,
                    )
                    for vacancy in vacancies
                ],
            )
        return len(vacancies)

    def upsert_placeholder_vacancies_for_applications(self, entries: list[UiApplicationEntry]) -> int:
        if not entries:
            return 0

        placeholders: list[Vacancy] = []
        for entry in entries:
            placeholders.append(
                Vacancy(
                    external_id=entry.vacancy_id,
                    source="hh_ui_history",
                    title=entry.title or f"Vacancy {entry.vacancy_id}",
                    company=entry.company or "Unknown company",
                    url=entry.url,
                    salary=SalaryRange(amount_from=None, amount_to=None, currency=None, gross=None),
                    location="Unknown location",
                    work_format=WorkFormat.UNKNOWN,
                    employment_type="Unknown",
                    experience_level="Unknown",
                    description="Imported from hh.ru UI history",
                    requirements="Imported from hh.ru UI history",
                    key_skills=[],
                    normalized_text=(entry.title or "").lower(),
                    raw_data={
                        "source": "hh_ui_history",
                        "vacancy_id": entry.vacancy_id,
                        "url": entry.url,
                        "title": entry.title,
                        "company": entry.company,
                        "note": entry.note,
                    },
                )
            )
        return self.upsert_vacancies(placeholders)

    def import_application_entries(self, entries: list[UiApplicationEntry]) -> int:
        if not entries:
            return 0

        self.upsert_placeholder_vacancies_for_applications(entries)
        with self.connect() as conn:
            conn.executemany(
                """
                INSERT INTO application_history (vacancy_id, status, note, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(vacancy_id) DO UPDATE SET
                    status=excluded.status,
                    note=excluded.note,
                    updated_at=excluded.updated_at
                """,
                [
                    (
                        entry.vacancy_id,
                        entry.status.value,
                        entry.note,
                        ApplicationRecord(vacancy_id=entry.vacancy_id, status=entry.status, note=entry.note).updated_at,
                    )
                    for entry in entries
                ],
            )
        return len(entries)

    def sync_application_entries(self, entries: list[UiApplicationEntry]) -> int:
        if not entries:
            with self.connect() as conn:
                conn.execute("DELETE FROM application_history")
            return 0

        imported = self.import_application_entries(entries)
        vacancy_ids = [entry.vacancy_id for entry in entries]
        placeholders = ", ".join("?" for _ in vacancy_ids)
        with self.connect() as conn:
            conn.execute(f"DELETE FROM application_history WHERE vacancy_id NOT IN ({placeholders})", vacancy_ids)
        return imported

    def list_vacancies(self, exclude_statuses: set[ApplicationStatus] | None = None) -> list[Vacancy]:
        query = "SELECT v.* FROM vacancies v LEFT JOIN application_history a ON a.vacancy_id = v.external_id"
        params: list[str] = []
        if exclude_statuses:
            placeholders = ", ".join("?" for _ in exclude_statuses)
            query += f" WHERE a.status IS NULL OR a.status NOT IN ({placeholders})"
            params.extend(status.value for status in exclude_statuses)
        query += " ORDER BY v.updated_at DESC, v.external_id ASC"

        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_vacancy(row) for row in rows]

    def get_application_statuses(self) -> dict[str, ApplicationStatus]:
        with self.connect() as conn:
            rows = conn.execute("SELECT vacancy_id, status FROM application_history").fetchall()
        return {row["vacancy_id"]: ApplicationStatus(row["status"]) for row in rows}

    def mark_application(self, record: ApplicationRecord) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO application_history (vacancy_id, status, note, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(vacancy_id) DO UPDATE SET
                    status=excluded.status,
                    note=excluded.note,
                    updated_at=excluded.updated_at
                """,
                (record.vacancy_id, record.status.value, record.note, record.updated_at),
            )

    def list_application_history(self) -> list[ApplicationRecord]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT vacancy_id, status, note, updated_at FROM application_history ORDER BY updated_at DESC, vacancy_id ASC"
            ).fetchall()
        return [
            ApplicationRecord(
                vacancy_id=row["vacancy_id"],
                status=ApplicationStatus(row["status"]),
                note=row["note"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]

    def save_ranking_results(self, ranked: list[RankedVacancy]) -> int:
        if not ranked:
            return 0
        with self.connect() as conn:
            cursor = conn.execute(
                "INSERT INTO ranking_runs (created_at, total_vacancies) VALUES (?, ?)",
                (ranked[0].analysis.generated_at if ranked else "", len(ranked)),
            )
            run_id = int(cursor.lastrowid)
            conn.executemany(
                """
                INSERT INTO ranking_results (
                    run_id, vacancy_id, track, score, priority_bucket, label, action,
                    reasons_json, concerns_json, matched_keywords_json, red_flags_json,
                    expected_salary, cover_letter_json, summary_ru, generated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    self._analysis_row(run_id, item.analysis)
                    for item in ranked
                ],
            )
        return run_id

    def get_latest_ranking(self) -> list[tuple[VacancyAnalysis, Vacancy]]:
        with self.connect() as conn:
            latest = conn.execute("SELECT id FROM ranking_runs ORDER BY id DESC LIMIT 1").fetchone()
            if latest is None:
                return []
            rows = conn.execute(
                """
                SELECT rr.*, v.*
                FROM ranking_results rr
                JOIN vacancies v ON v.external_id = rr.vacancy_id
                WHERE rr.run_id = ?
                ORDER BY rr.priority_bucket ASC, rr.score DESC, rr.vacancy_id ASC
                """,
                (latest["id"],),
            ).fetchall()
        return [(self._row_to_analysis(row), self._row_to_vacancy(row)) for row in rows]

    def vacancy_exists(self, vacancy_id: str) -> bool:
        with self.connect() as conn:
            row = conn.execute("SELECT 1 FROM vacancies WHERE external_id = ?", (vacancy_id,)).fetchone()
        return row is not None

    def get_vacancy(self, vacancy_id: str) -> Vacancy | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM vacancies WHERE external_id = ?", (vacancy_id,)).fetchone()
        if row is None:
            return None
        return self._row_to_vacancy(row)

    def _analysis_row(self, run_id: int, analysis: VacancyAnalysis) -> tuple[object, ...]:
        return (
            run_id,
            analysis.vacancy_id,
            analysis.track.value,
            analysis.score,
            analysis.priority_bucket,
            analysis.label.value,
            analysis.action.value,
            json.dumps(analysis.reasons, ensure_ascii=False),
            json.dumps(analysis.concerns, ensure_ascii=False),
            json.dumps(analysis.matched_keywords, ensure_ascii=False),
            json.dumps(analysis.red_flags, ensure_ascii=False),
            analysis.expected_salary,
            json.dumps(analysis.cover_letter_outline, ensure_ascii=False),
            analysis.summary_ru,
            analysis.generated_at,
        )

    def _row_to_vacancy(self, row: sqlite3.Row) -> Vacancy:
        return Vacancy(
            external_id=row["external_id"],
            source=row["source"],
            title=row["title"],
            company=row["company"],
            url=row["url"],
            salary=SalaryRange(
                amount_from=row["salary_from"],
                amount_to=row["salary_to"],
                currency=row["salary_currency"],
                gross=None if row["salary_gross"] is None else bool(row["salary_gross"]),
            ),
            location=row["location"],
            work_format=WorkFormat(row["work_format"]),
            employment_type=row["employment_type"],
            experience_level=row["experience_level"],
            description=row["description"],
            requirements=row["requirements"],
            key_skills=json.loads(row["key_skills_json"]),
            normalized_text=row["normalized_text"],
            raw_data=json.loads(row["raw_json"]),
            created_at=row["created_at"],
        )

    def _row_to_analysis(self, row: sqlite3.Row) -> VacancyAnalysis:
        return VacancyAnalysis(
            vacancy_id=row["vacancy_id"],
            track=VacancyTrack(row["track"]),
            score=row["score"],
            priority_bucket=row["priority_bucket"],
            label=MatchLabel(row["label"]),
            action=RecommendedAction(row["action"]),
            reasons=json.loads(row["reasons_json"]),
            concerns=json.loads(row["concerns_json"]),
            matched_keywords=json.loads(row["matched_keywords_json"]),
            red_flags=json.loads(row["red_flags_json"]),
            expected_salary=row["expected_salary"],
            cover_letter_outline=json.loads(row["cover_letter_json"]),
            summary_ru=row["summary_ru"],
            generated_at=row["generated_at"],
        )
