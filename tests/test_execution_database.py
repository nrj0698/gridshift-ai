import pandas as pd
import pytest

from database import (
    create_job,
    get_job,
)
from execution_database import (
    claim_job_run,
    create_job_run,
    finish_job_run,
    get_job_run,
    list_due_job_runs,
)


def create_saved_job(
    database_path,
) -> int:
    start = pd.Timestamp(
        "2026-07-21 12:00",
        tz="Europe/Dublin",
    )

    return create_job(
        workload_name="Worker test",
        earliest_start=start,
        deadline=(
            start
            + pd.Timedelta(hours=3)
        ),
        duration_hours=1.0,
        power_watts=300.0,
        recommended_start=(
            start
            + pd.Timedelta(hours=1)
        ),
        recommended_end=(
            start
            + pd.Timedelta(hours=2)
        ),
        average_intensity=150.0,
        energy_kwh=0.3,
        scheduled_emissions_g=45.0,
        baseline_emissions_g=60.0,
        avoided_emissions_g=15.0,
        reduction_percentage=25.0,
        candidate_count=4,
        source_label="Test forecast",
        database_path=database_path,
    )


def test_creates_and_reads_job_run(
    tmp_path,
) -> None:
    database_path = (
        tmp_path
        / "gridshift.db"
    )

    job_id = create_saved_job(
        database_path
    )

    run_id = create_job_run(
        job_id=job_id,
        task_id="demo_ai_batch",
        parameters={
            "items": 10,
        },
        database_path=database_path,
    )

    saved_run = get_job_run(
        run_id,
        database_path=database_path,
    )

    assert saved_run is not None
    assert saved_run.job_id == job_id
    assert saved_run.status == "queued"
    assert saved_run.parameters == {
        "items": 10
    }


def test_rejects_duplicate_active_run(
    tmp_path,
) -> None:
    database_path = (
        tmp_path
        / "gridshift.db"
    )

    job_id = create_saved_job(
        database_path
    )

    create_job_run(
        job_id=job_id,
        task_id="demo_ai_batch",
        database_path=database_path,
    )

    with pytest.raises(
        ValueError,
        match="already has",
    ):
        create_job_run(
            job_id=job_id,
            task_id="demo_ai_batch",
            database_path=database_path,
        )


def test_lists_due_runs(
    tmp_path,
) -> None:
    database_path = (
        tmp_path
        / "gridshift.db"
    )

    job_id = create_saved_job(
        database_path
    )

    run_id = create_job_run(
        job_id=job_id,
        task_id="demo_ai_batch",
        database_path=database_path,
    )

    due_runs = list_due_job_runs(
        now=pd.Timestamp(
            "2026-07-21 13:01",
            tz="Europe/Dublin",
        ),
        database_path=database_path,
    )

    assert [
        run.id
        for run in due_runs
    ] == [run_id]


def test_claim_updates_run_and_job(
    tmp_path,
) -> None:
    database_path = (
        tmp_path
        / "gridshift.db"
    )

    job_id = create_saved_job(
        database_path
    )

    run_id = create_job_run(
        job_id=job_id,
        task_id="demo_ai_batch",
        database_path=database_path,
    )

    assert claim_job_run(
        run_id,
        database_path=database_path,
    ) is True

    saved_run = get_job_run(
        run_id,
        database_path=database_path,
    )

    saved_job = get_job(
        job_id,
        database_path=database_path,
    )

    assert saved_run is not None
    assert saved_run.status == "running"

    assert saved_job is not None
    assert saved_job.status == "running"


def test_finish_updates_run_and_job(
    tmp_path,
) -> None:
    database_path = (
        tmp_path
        / "gridshift.db"
    )

    job_id = create_saved_job(
        database_path
    )

    run_id = create_job_run(
        job_id=job_id,
        task_id="demo_ai_batch",
        database_path=database_path,
    )

    claim_job_run(
        run_id,
        database_path=database_path,
    )

    finish_job_run(
        run_id=run_id,
        succeeded=True,
        return_code=0,
        log_path="/tmp/run.log",
        database_path=database_path,
    )

    saved_run = get_job_run(
        run_id,
        database_path=database_path,
    )

    saved_job = get_job(
        job_id,
        database_path=database_path,
    )

    assert saved_run is not None
    assert saved_run.status == "completed"
    assert saved_run.return_code == 0

    assert saved_job is not None
    assert saved_job.status == "completed"
