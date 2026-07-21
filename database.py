from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sqlite3

import pandas as pd


DUBLIN_TIMEZONE = "Europe/Dublin"
DEFAULT_DATABASE_PATH = Path("data/gridshift.db")

VALID_STATUSES = {
    "scheduled",
    "running",
    "completed",
    "failed",
    "cancelled",
}


@dataclass(frozen=True)
class JobRecord:
    """One workload stored in the GridShift database."""

    id: int
    workload_name: str

    earliest_start: pd.Timestamp
    deadline: pd.Timestamp

    duration_hours: float
    power_watts: float

    recommended_start: pd.Timestamp
    recommended_end: pd.Timestamp

    average_intensity: float
    energy_kwh: float

    scheduled_emissions_g: float
    baseline_emissions_g: float
    avoided_emissions_g: float
    reduction_percentage: float

    candidate_count: int
    source_label: str
    status: str

    created_at: pd.Timestamp
    updated_at: pd.Timestamp


def _database_path(
    database_path: str | Path,
) -> Path:
    path = Path(database_path)
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    return path


def _connect(
    database_path: str | Path,
) -> sqlite3.Connection:
    path = _database_path(database_path)

    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute(
        "PRAGMA foreign_keys = ON"
    )

    return connection


def initialise_database(
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> Path:
    """Create the database and jobs table when necessary."""

    path = _database_path(database_path)

    with _connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                workload_name TEXT NOT NULL,

                earliest_start TEXT NOT NULL,
                deadline TEXT NOT NULL,

                duration_hours REAL NOT NULL
                    CHECK (duration_hours > 0),

                power_watts REAL NOT NULL
                    CHECK (power_watts > 0),

                recommended_start TEXT NOT NULL,
                recommended_end TEXT NOT NULL,

                average_intensity REAL NOT NULL
                    CHECK (average_intensity >= 0),

                energy_kwh REAL NOT NULL
                    CHECK (energy_kwh >= 0),

                scheduled_emissions_g REAL NOT NULL
                    CHECK (scheduled_emissions_g >= 0),

                baseline_emissions_g REAL NOT NULL
                    CHECK (baseline_emissions_g >= 0),

                avoided_emissions_g REAL NOT NULL,
                reduction_percentage REAL NOT NULL,

                candidate_count INTEGER NOT NULL
                    CHECK (candidate_count >= 1),

                source_label TEXT NOT NULL,

                status TEXT NOT NULL
                    CHECK (
                        status IN (
                            'scheduled',
                            'running',
                            'completed',
                            'failed',
                            'cancelled'
                        )
                    ),

                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
            index_jobs_status
            ON jobs(status)
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
            index_jobs_recommended_start
            ON jobs(recommended_start)
            """
        )

    return path


def _normalise_timestamp(
    value: str | pd.Timestamp,
    field_name: str,
) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)

    if timestamp.tzinfo is None:
        raise ValueError(
            f"{field_name} must include timezone information."
        )

    return timestamp


def _to_storage_timestamp(
    timestamp: pd.Timestamp,
) -> str:
    return timestamp.tz_convert(
        "UTC"
    ).isoformat()


def _from_storage_timestamp(
    value: str,
    timezone_name: str = DUBLIN_TIMEZONE,
) -> pd.Timestamp:
    return pd.Timestamp(value).tz_convert(
        timezone_name
    )


def _validate_status(
    status: str,
) -> str:
    normalised_status = status.strip().lower()

    if normalised_status not in VALID_STATUSES:
        allowed = ", ".join(
            sorted(VALID_STATUSES)
        )

        raise ValueError(
            f"Invalid job status '{status}'. "
            f"Allowed values: {allowed}."
        )

    return normalised_status


def create_job(
    *,
    workload_name: str,
    earliest_start: str | pd.Timestamp,
    deadline: str | pd.Timestamp,
    duration_hours: float,
    power_watts: float,
    recommended_start: str | pd.Timestamp,
    recommended_end: str | pd.Timestamp,
    average_intensity: float,
    energy_kwh: float,
    scheduled_emissions_g: float,
    baseline_emissions_g: float,
    avoided_emissions_g: float,
    reduction_percentage: float,
    candidate_count: int,
    source_label: str,
    status: str = "scheduled",
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> int:
    """
    Store one GridShift recommendation and return its database ID.
    """

    clean_name = workload_name.strip()
    clean_source_label = source_label.strip()

    if not clean_name:
        raise ValueError(
            "Workload name cannot be empty."
        )

    if not clean_source_label:
        raise ValueError(
            "Source label cannot be empty."
        )

    if duration_hours <= 0:
        raise ValueError(
            "Duration must be greater than zero."
        )

    if power_watts <= 0:
        raise ValueError(
            "Power must be greater than zero."
        )

    if candidate_count < 1:
        raise ValueError(
            "Candidate count must be at least one."
        )

    nonnegative_values = {
        "average_intensity": average_intensity,
        "energy_kwh": energy_kwh,
        "scheduled_emissions_g": (
            scheduled_emissions_g
        ),
        "baseline_emissions_g": (
            baseline_emissions_g
        ),
    }

    for field_name, value in nonnegative_values.items():
        if value < 0:
            raise ValueError(
                f"{field_name} cannot be negative."
            )

    earliest = _normalise_timestamp(
        earliest_start,
        "Earliest start",
    )

    completion_deadline = _normalise_timestamp(
        deadline,
        "Deadline",
    )

    recommended_begin = _normalise_timestamp(
        recommended_start,
        "Recommended start",
    )

    recommended_finish = _normalise_timestamp(
        recommended_end,
        "Recommended end",
    )

    if earliest >= completion_deadline:
        raise ValueError(
            "Earliest start must occur before the deadline."
        )

    if recommended_begin < earliest:
        raise ValueError(
            "Recommended start cannot be before "
            "the earliest allowed start."
        )

    if recommended_finish <= recommended_begin:
        raise ValueError(
            "Recommended end must occur after "
            "the recommended start."
        )

    if recommended_finish > completion_deadline:
        raise ValueError(
            "Recommended schedule cannot finish "
            "after the deadline."
        )

    clean_status = _validate_status(status)

    now = datetime.now(
        timezone.utc
    ).isoformat()

    initialise_database(database_path)

    with _connect(database_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO jobs (
                workload_name,
                earliest_start,
                deadline,
                duration_hours,
                power_watts,
                recommended_start,
                recommended_end,
                average_intensity,
                energy_kwh,
                scheduled_emissions_g,
                baseline_emissions_g,
                avoided_emissions_g,
                reduction_percentage,
                candidate_count,
                source_label,
                status,
                created_at,
                updated_at
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                clean_name,
                _to_storage_timestamp(earliest),
                _to_storage_timestamp(
                    completion_deadline
                ),
                float(duration_hours),
                float(power_watts),
                _to_storage_timestamp(
                    recommended_begin
                ),
                _to_storage_timestamp(
                    recommended_finish
                ),
                float(average_intensity),
                float(energy_kwh),
                float(scheduled_emissions_g),
                float(baseline_emissions_g),
                float(avoided_emissions_g),
                float(reduction_percentage),
                int(candidate_count),
                clean_source_label,
                clean_status,
                now,
                now,
            ),
        )

        job_id = cursor.lastrowid

    if job_id is None:
        raise RuntimeError(
            "The database did not return a job ID."
        )

    return int(job_id)


def _row_to_job(
    row: sqlite3.Row,
) -> JobRecord:
    return JobRecord(
        id=int(row["id"]),
        workload_name=str(
            row["workload_name"]
        ),
        earliest_start=(
            _from_storage_timestamp(
                row["earliest_start"]
            )
        ),
        deadline=_from_storage_timestamp(
            row["deadline"]
        ),
        duration_hours=float(
            row["duration_hours"]
        ),
        power_watts=float(
            row["power_watts"]
        ),
        recommended_start=(
            _from_storage_timestamp(
                row["recommended_start"]
            )
        ),
        recommended_end=(
            _from_storage_timestamp(
                row["recommended_end"]
            )
        ),
        average_intensity=float(
            row["average_intensity"]
        ),
        energy_kwh=float(
            row["energy_kwh"]
        ),
        scheduled_emissions_g=float(
            row["scheduled_emissions_g"]
        ),
        baseline_emissions_g=float(
            row["baseline_emissions_g"]
        ),
        avoided_emissions_g=float(
            row["avoided_emissions_g"]
        ),
        reduction_percentage=float(
            row["reduction_percentage"]
        ),
        candidate_count=int(
            row["candidate_count"]
        ),
        source_label=str(
            row["source_label"]
        ),
        status=str(row["status"]),
        created_at=pd.Timestamp(
            row["created_at"]
        ),
        updated_at=pd.Timestamp(
            row["updated_at"]
        ),
    )


def get_job(
    job_id: int,
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> JobRecord | None:
    """Retrieve one saved job by its ID."""

    initialise_database(database_path)

    with _connect(database_path) as connection:
        row = connection.execute(
            """
            SELECT *
            FROM jobs
            WHERE id = ?
            """,
            (int(job_id),),
        ).fetchone()

    if row is None:
        return None

    return _row_to_job(row)


def list_jobs(
    *,
    limit: int = 100,
    status: str | None = None,
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> list[JobRecord]:
    """
    Return saved jobs, newest first.
    """

    if limit < 1:
        raise ValueError(
            "Limit must be at least one."
        )

    initialise_database(database_path)

    parameters: list[object] = []

    query = """
        SELECT *
        FROM jobs
    """

    if status is not None:
        clean_status = _validate_status(status)

        query += """
            WHERE status = ?
        """

        parameters.append(clean_status)

    query += """
        ORDER BY id DESC
        LIMIT ?
    """

    parameters.append(int(limit))

    with _connect(database_path) as connection:
        rows = connection.execute(
            query,
            parameters,
        ).fetchall()

    return [
        _row_to_job(row)
        for row in rows
    ]


def update_job_status(
    job_id: int,
    status: str,
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> None:
    """Update the lifecycle status of one stored workload."""

    clean_status = _validate_status(status)

    initialise_database(database_path)

    updated_at = datetime.now(
        timezone.utc
    ).isoformat()

    with _connect(database_path) as connection:
        cursor = connection.execute(
            """
            UPDATE jobs
            SET
                status = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                clean_status,
                updated_at,
                int(job_id),
            ),
        )

        if cursor.rowcount == 0:
            raise ValueError(
                f"No saved job exists with ID {job_id}."
            )


def count_jobs(
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> int:
    """Return the number of jobs stored in the database."""

    initialise_database(database_path)

    with _connect(database_path) as connection:
        row = connection.execute(
            """
            SELECT COUNT(*) AS total
            FROM jobs
            """
        ).fetchone()

    return int(row["total"])
