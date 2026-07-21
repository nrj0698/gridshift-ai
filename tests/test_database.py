import pandas as pd
import pytest

from database import (
    count_jobs,
    create_job,
    get_job,
    list_jobs,
    update_job_status,
)


def valid_job_values() -> dict:
    return {
        "workload_name": "Generate embeddings",
        "earliest_start": pd.Timestamp(
            "2026-07-21 12:00",
            tz="Europe/Dublin",
        ),
        "deadline": pd.Timestamp(
            "2026-07-21 22:00",
            tz="Europe/Dublin",
        ),
        "duration_hours": 3.0,
        "power_watts": 350.0,
        "recommended_start": pd.Timestamp(
            "2026-07-21 18:00",
            tz="Europe/Dublin",
        ),
        "recommended_end": pd.Timestamp(
            "2026-07-21 21:00",
            tz="Europe/Dublin",
        ),
        "average_intensity": 165.2,
        "energy_kwh": 1.05,
        "scheduled_emissions_g": 173.46,
        "baseline_emissions_g": 200.0,
        "avoided_emissions_g": 26.54,
        "reduction_percentage": 13.27,
        "candidate_count": 15,
        "source_label": "EirGrid CO₂ forecast",
    }


def test_creates_and_reads_job(
    tmp_path,
) -> None:
    database_path = tmp_path / "jobs.db"

    job_id = create_job(
        **valid_job_values(),
        database_path=database_path,
    )

    saved_job = get_job(
        job_id,
        database_path=database_path,
    )

    assert saved_job is not None
    assert saved_job.id == job_id
    assert saved_job.workload_name == (
        "Generate embeddings"
    )
    assert saved_job.status == "scheduled"
    assert saved_job.power_watts == pytest.approx(
        350.0
    )
    assert saved_job.recommended_start == (
        pd.Timestamp(
            "2026-07-21 18:00",
            tz="Europe/Dublin",
        )
    )

    assert count_jobs(
        database_path
    ) == 1


def test_lists_jobs_newest_first(
    tmp_path,
) -> None:
    database_path = tmp_path / "jobs.db"

    first_values = valid_job_values()
    first_values["workload_name"] = "First job"

    second_values = valid_job_values()
    second_values["workload_name"] = "Second job"

    create_job(
        **first_values,
        database_path=database_path,
    )

    create_job(
        **second_values,
        database_path=database_path,
    )

    jobs = list_jobs(
        database_path=database_path,
    )

    assert len(jobs) == 2
    assert jobs[0].workload_name == "Second job"
    assert jobs[1].workload_name == "First job"


def test_updates_job_status(
    tmp_path,
) -> None:
    database_path = tmp_path / "jobs.db"

    job_id = create_job(
        **valid_job_values(),
        database_path=database_path,
    )

    update_job_status(
        job_id,
        "completed",
        database_path=database_path,
    )

    saved_job = get_job(
        job_id,
        database_path=database_path,
    )

    assert saved_job is not None
    assert saved_job.status == "completed"


def test_rejects_invalid_status(
    tmp_path,
) -> None:
    database_path = tmp_path / "jobs.db"

    values = valid_job_values()
    values["status"] = "waiting-for-magic"

    with pytest.raises(
        ValueError,
        match="Invalid job status",
    ):
        create_job(
            **values,
            database_path=database_path,
        )


def test_rejects_schedule_after_deadline(
    tmp_path,
) -> None:
    database_path = tmp_path / "jobs.db"

    values = valid_job_values()

    values["recommended_end"] = pd.Timestamp(
        "2026-07-21 23:00",
        tz="Europe/Dublin",
    )

    with pytest.raises(
        ValueError,
        match="after the deadline",
    ):
        create_job(
            **values,
            database_path=database_path,
        )
