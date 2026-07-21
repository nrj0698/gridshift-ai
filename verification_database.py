from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sqlite3

import pandas as pd

from database import (
    DEFAULT_DATABASE_PATH,
    get_job,
    initialise_database,
)
from verification import VerificationResult


DUBLIN_TIMEZONE = "Europe/Dublin"


@dataclass(frozen=True)
class VerificationRecord:
    job_id: int
    source_label: str

    scheduled_start: pd.Timestamp
    scheduled_end: pd.Timestamp

    baseline_start: pd.Timestamp
    baseline_end: pd.Timestamp

    forecast_average_intensity: float
    actual_average_intensity: float

    forecast_error: float
    forecast_absolute_error: float
    forecast_error_percentage: float

    actual_baseline_average_intensity: float
    energy_kwh: float

    actual_scheduled_emissions_g: float
    actual_baseline_emissions_g: float

    realised_avoided_emissions_g: float
    realised_reduction_percentage: float

    scheduled_point_count: int
    baseline_point_count: int

    verified_at: pd.Timestamp


def _connect(
    database_path: str | Path,
) -> sqlite3.Connection:
    connection = sqlite3.connect(
        Path(database_path)
    )

    connection.row_factory = sqlite3.Row
    connection.execute(
        "PRAGMA foreign_keys = ON"
    )

    return connection


def _to_utc_iso(
    value: pd.Timestamp,
) -> str:
    timestamp = pd.Timestamp(value)

    if timestamp.tzinfo is None:
        raise ValueError(
            "Verification timestamp must include timezone."
        )

    return timestamp.tz_convert(
        "UTC"
    ).isoformat()


def _from_storage_timestamp(
    value: str,
) -> pd.Timestamp:
    return pd.Timestamp(value).tz_convert(
        DUBLIN_TIMEZONE
    )


def initialise_verification_database(
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> Path:
    path = initialise_database(
        database_path
    )

    with _connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS job_verifications (
                job_id INTEGER PRIMARY KEY,

                source_label TEXT NOT NULL,

                scheduled_start TEXT NOT NULL,
                scheduled_end TEXT NOT NULL,

                baseline_start TEXT NOT NULL,
                baseline_end TEXT NOT NULL,

                forecast_average_intensity REAL NOT NULL,
                actual_average_intensity REAL NOT NULL,

                forecast_error REAL NOT NULL,
                forecast_absolute_error REAL NOT NULL,
                forecast_error_percentage REAL NOT NULL,

                actual_baseline_average_intensity REAL NOT NULL,
                energy_kwh REAL NOT NULL,

                actual_scheduled_emissions_g REAL NOT NULL,
                actual_baseline_emissions_g REAL NOT NULL,

                realised_avoided_emissions_g REAL NOT NULL,
                realised_reduction_percentage REAL NOT NULL,

                scheduled_point_count INTEGER NOT NULL,
                baseline_point_count INTEGER NOT NULL,

                verified_at TEXT NOT NULL,

                FOREIGN KEY(job_id)
                    REFERENCES jobs(id)
                    ON DELETE CASCADE
            )
            """
        )

    return Path(path)


def save_verification(
    result: VerificationResult,
    *,
    source_label: str,
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> None:
    clean_source_label = source_label.strip()

    if not clean_source_label:
        raise ValueError(
            "Verification source label cannot be empty."
        )

    initialise_verification_database(
        database_path
    )

    job = get_job(
        result.job_id,
        database_path=database_path,
    )

    if job is None:
        raise ValueError(
            f"No saved job exists with ID {result.job_id}."
        )

    verified_at = datetime.now(
        timezone.utc
    ).isoformat()

    values = (
        int(result.job_id),
        clean_source_label,
        _to_utc_iso(result.scheduled_start),
        _to_utc_iso(result.scheduled_end),
        _to_utc_iso(result.baseline_start),
        _to_utc_iso(result.baseline_end),
        float(result.forecast_average_intensity),
        float(result.actual_average_intensity),
        float(result.forecast_error),
        float(result.forecast_absolute_error),
        float(result.forecast_error_percentage),
        float(
            result.actual_baseline_average_intensity
        ),
        float(result.energy_kwh),
        float(result.actual_scheduled_emissions_g),
        float(result.actual_baseline_emissions_g),
        float(result.realised_avoided_emissions_g),
        float(result.realised_reduction_percentage),
        int(result.scheduled_point_count),
        int(result.baseline_point_count),
        verified_at,
    )

    with _connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO job_verifications (
                job_id,
                source_label,
                scheduled_start,
                scheduled_end,
                baseline_start,
                baseline_end,
                forecast_average_intensity,
                actual_average_intensity,
                forecast_error,
                forecast_absolute_error,
                forecast_error_percentage,
                actual_baseline_average_intensity,
                energy_kwh,
                actual_scheduled_emissions_g,
                actual_baseline_emissions_g,
                realised_avoided_emissions_g,
                realised_reduction_percentage,
                scheduled_point_count,
                baseline_point_count,
                verified_at
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            ON CONFLICT(job_id)
            DO UPDATE SET
                source_label = excluded.source_label,
                scheduled_start = excluded.scheduled_start,
                scheduled_end = excluded.scheduled_end,
                baseline_start = excluded.baseline_start,
                baseline_end = excluded.baseline_end,
                forecast_average_intensity =
                    excluded.forecast_average_intensity,
                actual_average_intensity =
                    excluded.actual_average_intensity,
                forecast_error = excluded.forecast_error,
                forecast_absolute_error =
                    excluded.forecast_absolute_error,
                forecast_error_percentage =
                    excluded.forecast_error_percentage,
                actual_baseline_average_intensity =
                    excluded.actual_baseline_average_intensity,
                energy_kwh = excluded.energy_kwh,
                actual_scheduled_emissions_g =
                    excluded.actual_scheduled_emissions_g,
                actual_baseline_emissions_g =
                    excluded.actual_baseline_emissions_g,
                realised_avoided_emissions_g =
                    excluded.realised_avoided_emissions_g,
                realised_reduction_percentage =
                    excluded.realised_reduction_percentage,
                scheduled_point_count =
                    excluded.scheduled_point_count,
                baseline_point_count =
                    excluded.baseline_point_count,
                verified_at = excluded.verified_at
            """,
            values,
        )


def _row_to_record(
    row: sqlite3.Row,
) -> VerificationRecord:
    return VerificationRecord(
        job_id=int(row["job_id"]),
        source_label=str(row["source_label"]),
        scheduled_start=_from_storage_timestamp(
            row["scheduled_start"]
        ),
        scheduled_end=_from_storage_timestamp(
            row["scheduled_end"]
        ),
        baseline_start=_from_storage_timestamp(
            row["baseline_start"]
        ),
        baseline_end=_from_storage_timestamp(
            row["baseline_end"]
        ),
        forecast_average_intensity=float(
            row["forecast_average_intensity"]
        ),
        actual_average_intensity=float(
            row["actual_average_intensity"]
        ),
        forecast_error=float(
            row["forecast_error"]
        ),
        forecast_absolute_error=float(
            row["forecast_absolute_error"]
        ),
        forecast_error_percentage=float(
            row["forecast_error_percentage"]
        ),
        actual_baseline_average_intensity=float(
            row["actual_baseline_average_intensity"]
        ),
        energy_kwh=float(row["energy_kwh"]),
        actual_scheduled_emissions_g=float(
            row["actual_scheduled_emissions_g"]
        ),
        actual_baseline_emissions_g=float(
            row["actual_baseline_emissions_g"]
        ),
        realised_avoided_emissions_g=float(
            row["realised_avoided_emissions_g"]
        ),
        realised_reduction_percentage=float(
            row["realised_reduction_percentage"]
        ),
        scheduled_point_count=int(
            row["scheduled_point_count"]
        ),
        baseline_point_count=int(
            row["baseline_point_count"]
        ),
        verified_at=pd.Timestamp(
            row["verified_at"]
        ),
    )


def get_verification(
    job_id: int,
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> VerificationRecord | None:
    initialise_verification_database(
        database_path
    )

    with _connect(database_path) as connection:
        row = connection.execute(
            """
            SELECT *
            FROM job_verifications
            WHERE job_id = ?
            """,
            (int(job_id),),
        ).fetchone()

    if row is None:
        return None

    return _row_to_record(row)


def list_verifications(
    *,
    limit: int = 100,
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> list[VerificationRecord]:
    if limit < 1:
        raise ValueError(
            "Limit must be at least one."
        )

    initialise_verification_database(
        database_path
    )

    with _connect(database_path) as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM job_verifications
            ORDER BY verified_at DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()

    return [
        _row_to_record(row)
        for row in rows
    ]
