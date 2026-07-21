from __future__ import annotations

import pandas as pd

from database import (
    DEFAULT_DATABASE_PATH,
    create_job,
)
from execution_database import (
    create_job_run,
    initialise_execution_database,
)


def main() -> None:
    initialise_execution_database(
        DEFAULT_DATABASE_PATH
    )

    now = pd.Timestamp.now(
        tz="Europe/Dublin"
    ).floor("s")

    duration_hours = 2 / 60
    power_watts = 100.0
    energy_kwh = (
        duration_hours
        * power_watts
        / 1000
    )

    scheduled_intensity = 150.0
    baseline_intensity = 210.0

    scheduled_emissions = (
        scheduled_intensity
        * energy_kwh
    )

    baseline_emissions = (
        baseline_intensity
        * energy_kwh
    )

    avoided_emissions = (
        baseline_emissions
        - scheduled_emissions
    )

    reduction_percentage = (
        avoided_emissions
        / baseline_emissions
        * 100
    )

    job_id = create_job(
        workload_name=(
            "Trusted local worker demonstration"
        ),
        earliest_start=(
            now
            - pd.Timedelta(minutes=1)
        ),
        deadline=(
            now
            + pd.Timedelta(minutes=15)
        ),
        duration_hours=duration_hours,
        power_watts=power_watts,
        recommended_start=now,
        recommended_end=(
            now
            + pd.Timedelta(minutes=2)
        ),
        average_intensity=(
            scheduled_intensity
        ),
        energy_kwh=energy_kwh,
        scheduled_emissions_g=(
            scheduled_emissions
        ),
        baseline_emissions_g=(
            baseline_emissions
        ),
        avoided_emissions_g=(
            avoided_emissions
        ),
        reduction_percentage=(
            reduction_percentage
        ),
        candidate_count=1,
        source_label=(
            "Local worker demonstration"
        ),
        status="scheduled",
        database_path=(
            DEFAULT_DATABASE_PATH
        ),
    )

    run_id = create_job_run(
        job_id=job_id,
        task_id="demo_ai_batch",
        parameters={
            "items": 20,
        },
        database_path=(
            DEFAULT_DATABASE_PATH
        ),
    )

    print(
        f"Created job #{job_id}"
    )

    print(
        f"Queued execution #{run_id}"
    )


if __name__ == "__main__":
    main()
