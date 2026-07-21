import pandas as pd
import pytest

from database import (
    create_job,
    get_job,
)
from verification import (
    verify_job_against_actuals,
)
from verification_database import (
    get_verification,
    list_verifications,
    save_verification,
)


def create_actual_data() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.date_range(
                start="2026-07-21 12:00",
                periods=8,
                freq="15min",
                tz="Europe/Dublin",
            ),
            "carbon_intensity": [
                200,
                200,
                200,
                200,
                120,
                100,
                80,
                100,
            ],
        }
    )


def test_saves_and_reads_verification(
    tmp_path,
) -> None:
    database_path = (
        tmp_path
        / "gridshift.db"
    )

    job_id = create_job(
        workload_name="Verification database test",
        earliest_start=pd.Timestamp(
            "2026-07-21 12:00",
            tz="Europe/Dublin",
        ),
        deadline=pd.Timestamp(
            "2026-07-21 16:00",
            tz="Europe/Dublin",
        ),
        duration_hours=1.0,
        power_watts=500.0,
        recommended_start=pd.Timestamp(
            "2026-07-21 13:00",
            tz="Europe/Dublin",
        ),
        recommended_end=pd.Timestamp(
            "2026-07-21 14:00",
            tz="Europe/Dublin",
        ),
        average_intensity=100.0,
        energy_kwh=0.5,
        scheduled_emissions_g=50.0,
        baseline_emissions_g=100.0,
        avoided_emissions_g=50.0,
        reduction_percentage=50.0,
        candidate_count=4,
        source_label="Test forecast",
        status="completed",
        database_path=database_path,
    )

    job = get_job(
        job_id,
        database_path=database_path,
    )

    assert job is not None

    result = verify_job_against_actuals(
        job,
        create_actual_data(),
    )

    save_verification(
        result,
        source_label="Test actual data",
        database_path=database_path,
    )

    saved = get_verification(
        job_id,
        database_path=database_path,
    )

    assert saved is not None

    assert saved.actual_average_intensity == (
        pytest.approx(100.0)
    )

    assert saved.realised_avoided_emissions_g == (
        pytest.approx(50.0)
    )

    assert len(
        list_verifications(
            database_path=database_path
        )
    ) == 1
