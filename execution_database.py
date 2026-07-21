from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

import pandas as pd

from database import (
    DEFAULT_DATABASE_PATH,
    get_job,
    initialise_database,
)


VALID_RUN_STATUSES = {
    "queued",
    "running",
    "completed",
    "failed",
    "cancelled",
}


@dataclass(frozen=True)
class JobRun:
    """
    One queued or completed local workload execution.
    """

    id: int
    job_id: int
    task_id: str
    parameters: dict[str, object]
    status: str

    log_path: str | None
    return_code: int | None
    error_message: str | None

    queued_at: pd.Timestamp
    started_at: pd.Timestamp | None
    finished_at: pd.Timestamp | None


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


def _utc_now() -> pd.Timestamp:
    return pd.Timestamp.now(
        tz="UTC"
    )


def _to_utc_iso(
    value: pd.Timestamp | str,
) -> str:
    timestamp = pd.Timestamp(value)

    if timestamp.tzinfo is None:
        raise ValueError(
            "Timestamp must include timezone information."
        )

    return timestamp.tz_convert(
        "UTC"
    ).isoformat()


def initialise_execution_database(
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> Path:
    """
    Create the job-runs table when it does not exist.
    """
    path = initialise_database(
        database_path
    )

    with _connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS job_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                job_id INTEGER NOT NULL,
                task_id TEXT NOT NULL,
                parameters_json TEXT NOT NULL,

                status TEXT NOT NULL
                    CHECK (
                        status IN (
                            'queued',
                            'running',
                            'completed',
                            'failed',
                            'cancelled'
                        )
                    ),

                log_path TEXT,
                return_code INTEGER,
                error_message TEXT,

                queued_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,

                FOREIGN KEY(job_id)
                    REFERENCES jobs(id)
                    ON DELETE CASCADE
            )
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
            index_job_runs_status
            ON job_runs(status)
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
            index_job_runs_job_id
            ON job_runs(job_id)
            """
        )

    return Path(path)


def _row_to_job_run(
    row: sqlite3.Row,
) -> JobRun:
    return JobRun(
        id=int(row["id"]),
        job_id=int(row["job_id"]),
        task_id=str(row["task_id"]),
        parameters=json.loads(
            row["parameters_json"]
        ),
        status=str(row["status"]),
        log_path=(
            str(row["log_path"])
            if row["log_path"] is not None
            else None
        ),
        return_code=(
            int(row["return_code"])
            if row["return_code"] is not None
            else None
        ),
        error_message=(
            str(row["error_message"])
            if row["error_message"] is not None
            else None
        ),
        queued_at=pd.Timestamp(
            row["queued_at"]
        ),
        started_at=(
            pd.Timestamp(row["started_at"])
            if row["started_at"] is not None
            else None
        ),
        finished_at=(
            pd.Timestamp(row["finished_at"])
            if row["finished_at"] is not None
            else None
        ),
    )


def create_job_run(
    *,
    job_id: int,
    task_id: str,
    parameters: dict[str, object] | None = None,
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> int:
    """
    Attach a trusted execution task to a saved GridShift job.
    """
    initialise_execution_database(
        database_path
    )

    saved_job = get_job(
        job_id,
        database_path=database_path,
    )

    if saved_job is None:
        raise ValueError(
            f"No saved job exists with ID {job_id}."
        )

    if saved_job.status != "scheduled":
        raise ValueError(
            "Only jobs with status 'scheduled' "
            "can be queued."
        )

    clean_task_id = task_id.strip()

    if not clean_task_id:
        raise ValueError(
            "Task ID cannot be empty."
        )

    clean_parameters = (
        parameters.copy()
        if parameters is not None
        else {}
    )

    try:
        parameters_json = json.dumps(
            clean_parameters,
            sort_keys=True,
        )
    except TypeError as error:
        raise ValueError(
            "Task parameters must be JSON serialisable."
        ) from error

    with _connect(database_path) as connection:
        existing_run = connection.execute(
            """
            SELECT id
            FROM job_runs
            WHERE
                job_id = ?
                AND status IN (
                    'queued',
                    'running'
                )
            LIMIT 1
            """,
            (int(job_id),),
        ).fetchone()

        if existing_run is not None:
            raise ValueError(
                "This job already has a queued or "
                "running execution."
            )

        cursor = connection.execute(
            """
            INSERT INTO job_runs (
                job_id,
                task_id,
                parameters_json,
                status,
                queued_at
            )
            VALUES (?, ?, ?, 'queued', ?)
            """,
            (
                int(job_id),
                clean_task_id,
                parameters_json,
                _utc_now().isoformat(),
            ),
        )

        run_id = cursor.lastrowid

    if run_id is None:
        raise RuntimeError(
            "The database did not return a run ID."
        )

    return int(run_id)


def get_job_run(
    run_id: int,
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> JobRun | None:
    initialise_execution_database(
        database_path
    )

    with _connect(database_path) as connection:
        row = connection.execute(
            """
            SELECT *
            FROM job_runs
            WHERE id = ?
            """,
            (int(run_id),),
        ).fetchone()

    if row is None:
        return None

    return _row_to_job_run(row)


def list_job_runs(
    *,
    job_id: int | None = None,
    limit: int = 100,
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> list[JobRun]:
    if limit < 1:
        raise ValueError(
            "Limit must be at least one."
        )

    initialise_execution_database(
        database_path
    )

    query = """
        SELECT *
        FROM job_runs
    """

    parameters: list[object] = []

    if job_id is not None:
        query += """
            WHERE job_id = ?
        """

        parameters.append(
            int(job_id)
        )

    query += """
        ORDER BY id DESC
        LIMIT ?
    """

    parameters.append(
        int(limit)
    )

    with _connect(database_path) as connection:
        rows = connection.execute(
            query,
            parameters,
        ).fetchall()

    return [
        _row_to_job_run(row)
        for row in rows
    ]


def list_due_job_runs(
    *,
    now: pd.Timestamp | None = None,
    limit: int = 20,
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> list[JobRun]:
    """
    Return queued runs whose recommended start time has arrived.
    """
    if limit < 1:
        raise ValueError(
            "Limit must be at least one."
        )

    initialise_execution_database(
        database_path
    )

    current_time = (
        now
        if now is not None
        else _utc_now()
    )

    current_time_iso = _to_utc_iso(
        current_time
    )

    with _connect(database_path) as connection:
        rows = connection.execute(
            """
            SELECT run.*
            FROM job_runs AS run
            INNER JOIN jobs AS job
                ON job.id = run.job_id
            WHERE
                run.status = 'queued'
                AND job.status = 'scheduled'
                AND job.recommended_start <= ?
            ORDER BY
                job.recommended_start ASC,
                run.id ASC
            LIMIT ?
            """,
            (
                current_time_iso,
                int(limit),
            ),
        ).fetchall()

    return [
        _row_to_job_run(row)
        for row in rows
    ]


def claim_job_run(
    run_id: int,
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> bool:
    """
    Atomically move one queued run into the running state.

    Returns False when another worker already claimed it.
    """
    initialise_execution_database(
        database_path
    )

    started_at = _utc_now().isoformat()

    with _connect(database_path) as connection:
        connection.execute(
            "BEGIN IMMEDIATE"
        )

        row = connection.execute(
            """
            SELECT job_id
            FROM job_runs
            WHERE id = ?
            """,
            (int(run_id),),
        ).fetchone()

        if row is None:
            connection.rollback()

            raise ValueError(
                f"No execution exists with ID {run_id}."
            )

        cursor = connection.execute(
            """
            UPDATE job_runs
            SET
                status = 'running',
                started_at = ?
            WHERE
                id = ?
                AND status = 'queued'
            """,
            (
                started_at,
                int(run_id),
            ),
        )

        if cursor.rowcount != 1:
            connection.rollback()
            return False

        connection.execute(
            """
            UPDATE jobs
            SET
                status = 'running',
                updated_at = ?
            WHERE id = ?
            """,
            (
                started_at,
                int(row["job_id"]),
            ),
        )

        connection.commit()

    return True


def finish_job_run(
    *,
    run_id: int,
    succeeded: bool,
    return_code: int | None,
    log_path: str | Path | None,
    error_message: str | None = None,
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> None:
    """
    Mark a running execution as completed or failed.
    """
    initialise_execution_database(
        database_path
    )

    run_status = (
        "completed"
        if succeeded
        else "failed"
    )

    job_status = run_status
    finished_at = _utc_now().isoformat()

    clean_log_path = (
        str(log_path)
        if log_path is not None
        else None
    )

    with _connect(database_path) as connection:
        connection.execute(
            "BEGIN IMMEDIATE"
        )

        row = connection.execute(
            """
            SELECT job_id
            FROM job_runs
            WHERE id = ?
            """,
            (int(run_id),),
        ).fetchone()

        if row is None:
            connection.rollback()

            raise ValueError(
                f"No execution exists with ID {run_id}."
            )

        cursor = connection.execute(
            """
            UPDATE job_runs
            SET
                status = ?,
                return_code = ?,
                log_path = ?,
                error_message = ?,
                finished_at = ?
            WHERE
                id = ?
                AND status = 'running'
            """,
            (
                run_status,
                return_code,
                clean_log_path,
                error_message,
                finished_at,
                int(run_id),
            ),
        )

        if cursor.rowcount != 1:
            connection.rollback()

            raise ValueError(
                "Only a running execution can be finished."
            )

        connection.execute(
            """
            UPDATE jobs
            SET
                status = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                job_status,
                finished_at,
                int(row["job_id"]),
            ),
        )

        connection.commit()


def cancel_job_run(
    run_id: int,
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> None:
    """
    Cancel an execution that has not started.
    """
    initialise_execution_database(
        database_path
    )

    cancelled_at = _utc_now().isoformat()

    with _connect(database_path) as connection:
        connection.execute(
            "BEGIN IMMEDIATE"
        )

        row = connection.execute(
            """
            SELECT job_id
            FROM job_runs
            WHERE id = ?
            """,
            (int(run_id),),
        ).fetchone()

        if row is None:
            connection.rollback()

            raise ValueError(
                f"No execution exists with ID {run_id}."
            )

        cursor = connection.execute(
            """
            UPDATE job_runs
            SET
                status = 'cancelled',
                finished_at = ?
            WHERE
                id = ?
                AND status = 'queued'
            """,
            (
                cancelled_at,
                int(run_id),
            ),
        )

        if cursor.rowcount != 1:
            connection.rollback()

            raise ValueError(
                "Only a queued execution can be cancelled."
            )

        connection.execute(
            """
            UPDATE jobs
            SET
                status = 'cancelled',
                updated_at = ?
            WHERE id = ?
            """,
            (
                cancelled_at,
                int(row["job_id"]),
            ),
        )

        connection.commit()
