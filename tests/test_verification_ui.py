import pandas as pd
import pytest

from database import JobRecord
from verification import VerificationResult
from verification_ui import (
    build_verification_chart_data,
    build_verification_export,
    describe_verification_outcome,
)


def create_job() -> JobRecord:
    created_at = pd.Timestamp(
        "2026-07-21 10:00",
        tz="UTC",
    )

    return JobRecord(
        id=8,
        workload_name="Generate embeddings",
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
        source_label="EirGrid forecast",
        status="completed",
        created_at=created_at,
        updated_at=created_at,
    )


def create_result(
    realised_saving: float = 50.0,
) -> VerificationResult:
    realised_reduction = (
        realised_saving
        / 100
        * 100
    )

    return VerificationResult(
        job_id=8,
        scheduled_start=pd.Timestamp(
            "2026-07-21 13:00",
            tz="Europe/Dublin",
        ),
        scheduled_end=pd.Timestamp(
            "2026-07-21 14:00",
            tz="Europe/Dublin",
        ),
        baseline_start=pd.Timestamp(
            "2026-07-21 12:00",
            tz="Europe/Dublin",
        ),
        baseline_end=pd.Timestamp(
            "2026-07-21 13:00",
            tz="Europe/Dublin",
        ),
        forecast_average_intensity=100.0,
        actual_average_intensity=100.0,
        forecast_error=0.0,
        forecast_absolute_error=0.0,
        forecast_error_percentage=0.0,
        actual_baseline_average_intensity=200.0,
        energy_kwh=0.5,
        actual_scheduled_emissions_g=50.0,
        actual_baseline_emissions_g=(
            50.0 + realised_saving
        ),
        realised_avoided_emissions_g=(
            realised_saving
        ),
        realised_reduction_percentage=(
            realised_reduction
        ),
        scheduled_point_count=4,
        baseline_point_count=4,
    )


def test_labels_baseline_and_scheduled_windows() -> None:
    data = pd.DataFrame(
        {
            "timestamp": pd.date_range(
                start="2026-07-21 11:45",
                periods=10,
                freq="15min",
                tz="Europe/Dublin",
            ),
            "carbon_intensity": [
                210,
                200,
                200,
                200,
                200,
                120,
                100,
                80,
                100,
                110,
            ],
        }
    )

    result = build_verification_chart_data(
        data,
        create_job(),
    )

    assert "Baseline window" in (
        result["period"].tolist()
    )

    assert "Scheduled window" in (
        result["period"].tolist()
    )


def test_builds_export_report() -> None:
    export = build_verification_export(
        job=create_job(),
        result=create_result(),
        source_label="Measured EirGrid data",
    )

    assert len(export) == 1

    assert export.iloc[0][
        "job_id"
    ] == 8

    assert export.iloc[0][
        "realised_avoided_emissions_g"
    ] == pytest.approx(50.0)


def test_describes_successful_outcome() -> None:
    presentation, message = (
        describe_verification_outcome(
            create_result(
                realised_saving=50.0
            )
        )
    )

    assert presentation == "success"
    assert "realised reduction" in message


def test_describes_negative_outcome() -> None:
    presentation, message = (
        describe_verification_outcome(
            create_result(
                realised_saving=-10.0
            )
        )
    )

    assert presentation == "warning"
    assert "more carbon intensive" in message
