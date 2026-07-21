from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import time

import pandas as pd

from database import (
    DEFAULT_DATABASE_PATH,
    get_job,
)
from execution_database import (
    claim_job_run,
    finish_job_run,
    get_job_run,
    initialise_execution_database,
    list_due_job_runs,
)
from trusted_tasks import (
    PROJECT_ROOT,
    build_trusted_command,
    get_trusted_task,
)


LOG_DIRECTORY = (
    PROJECT_ROOT
    / "logs"
)


def execute_claimed_run(
    run_id: int,
) -> None:
    """
    Execute one job run that has already been claimed.
    """
    run = get_job_run(
        run_id,
        database_path=DEFAULT_DATABASE_PATH,
    )

    if run is None:
        raise ValueError(
            f"No execution exists with ID {run_id}."
        )

    job = get_job(
        run.job_id,
        database_path=DEFAULT_DATABASE_PATH,
    )

    if job is None:
        finish_job_run(
            run_id=run.id,
            succeeded=False,
            return_code=None,
            log_path=None,
            error_message=(
                "The saved GridShift job no longer exists."
            ),
            database_path=DEFAULT_DATABASE_PATH,
        )
        return

    now_dublin = pd.Timestamp.now(
        tz="Europe/Dublin"
    )

    if now_dublin > job.deadline:
        finish_job_run(
            run_id=run.id,
            succeeded=False,
            return_code=None,
            log_path=None,
            error_message=(
                "The execution deadline passed before "
                "the worker started the workload."
            ),
            database_path=DEFAULT_DATABASE_PATH,
        )

        print(
            f"Run #{run.id} failed because its "
            "deadline passed."
        )
        return

    LOG_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    log_path = (
        LOG_DIRECTORY
        / f"run_{run.id}.log"
    ).resolve()

    try:
        task = get_trusted_task(
            run.task_id
        )

        command = build_trusted_command(
            run.task_id,
            run.parameters,
        )

        with log_path.open(
            "w",
            encoding="utf-8",
        ) as log_file:
            started_at = datetime.now(
                timezone.utc
            ).isoformat()

            log_file.write(
                f"GridShift run ID: {run.id}\n"
            )

            log_file.write(
                f"GridShift job ID: {run.job_id}\n"
            )

            log_file.write(
                f"Trusted task: {run.task_id}\n"
            )

            log_file.write(
                f"Started at: {started_at}\n"
            )

            log_file.write(
                "Command arguments:\n"
            )

            for argument in command:
                log_file.write(
                    f"  {argument}\n"
                )

            log_file.write(
                "\n--- Workload output ---\n"
            )

            log_file.flush()

            completed_process = subprocess.run(
                command,
                cwd=PROJECT_ROOT,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
                shell=False,
                check=False,
                timeout=task.timeout_seconds,
            )

            return_code = (
                completed_process.returncode
            )

        succeeded = return_code == 0

        finish_job_run(
            run_id=run.id,
            succeeded=succeeded,
            return_code=return_code,
            log_path=log_path,
            error_message=(
                None
                if succeeded
                else (
                    "The workload exited with "
                    f"return code {return_code}."
                )
            ),
            database_path=DEFAULT_DATABASE_PATH,
        )

        final_status = (
            "completed"
            if succeeded
            else "failed"
        )

        print(
            f"Run #{run.id} {final_status}. "
            f"Log: {log_path}"
        )

    except subprocess.TimeoutExpired:
        with log_path.open(
            "a",
            encoding="utf-8",
        ) as log_file:
            log_file.write(
                "\nWorkload exceeded its configured timeout.\n"
            )

        finish_job_run(
            run_id=run.id,
            succeeded=False,
            return_code=None,
            log_path=log_path,
            error_message=(
                "The workload exceeded its configured timeout."
            ),
            database_path=DEFAULT_DATABASE_PATH,
        )

        print(
            f"Run #{run.id} failed due to timeout."
        )

    except Exception as error:
        with log_path.open(
            "a",
            encoding="utf-8",
        ) as log_file:
            log_file.write(
                f"\nWorker error: {error}\n"
            )

        finish_job_run(
            run_id=run.id,
            succeeded=False,
            return_code=None,
            log_path=log_path,
            error_message=str(error),
            database_path=DEFAULT_DATABASE_PATH,
        )

        print(
            f"Run #{run.id} failed: {error}"
        )


def run_once() -> int:
    """
    Execute all currently due queued workloads.
    """
    due_runs = list_due_job_runs(
        database_path=DEFAULT_DATABASE_PATH,
    )

    processed_count = 0

    for run in due_runs:
        claimed = claim_job_run(
            run.id,
            database_path=DEFAULT_DATABASE_PATH,
        )

        if not claimed:
            continue

        print(
            f"Claimed run #{run.id} "
            f"for job #{run.job_id}."
        )

        execute_claimed_run(
            run.id
        )

        processed_count += 1

    return processed_count


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run trusted GridShift workloads "
            "when their scheduled time arrives."
        )
    )

    parser.add_argument(
        "--once",
        action="store_true",
        help=(
            "Check once for due workloads and then exit."
        ),
    )

    parser.add_argument(
        "--poll-seconds",
        type=int,
        default=15,
        help=(
            "Seconds between checks in continuous mode."
        ),
    )

    arguments = parser.parse_args()

    if arguments.poll_seconds < 1:
        parser.error(
            "--poll-seconds must be at least 1"
        )

    return arguments


def main() -> None:
    arguments = parse_arguments()

    initialise_execution_database(
        DEFAULT_DATABASE_PATH
    )

    if arguments.once:
        processed = run_once()

        print(
            f"Worker finished. "
            f"Processed {processed} run(s)."
        )

        return

    print(
        "GridShift worker started. "
        f"Checking every "
        f"{arguments.poll_seconds} seconds."
    )

    try:
        while True:
            processed = run_once()

            if processed:
                print(
                    f"Processed {processed} run(s)."
                )

            time.sleep(
                arguments.poll_seconds
            )

    except KeyboardInterrupt:
        print(
            "\nGridShift worker stopped."
        )


if __name__ == "__main__":
    main()
