from io import BytesIO

import pandas as pd
import pytest

from database import JobRecord
from verification import (
    load_actual_carbon_csv,
    verify_job_against_actuals,
)


def create_job_record() -> JobRecord:
    created_at = pd.Timestamp(
        "2026-07-21 10:00",
        tz="UTC",
    )

    return JobRecord(
        id=1,
        workload_name="Verification test",
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
        created_at=created_at,
        updated_at=created_at,
    )


def create_actual_data() -> pd.DataFrame:
    timestamps = pd.date_range(
        start="2026-07-21 12:00",
        periods=8,
        freq="15min",
        tz="Europe/Dublin",
    )

    return pd.DataFrame(
        {
            "timestamp": timestamps,
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


def test_loads_actual_column_instead_of_forecast() -> None:
    source = BytesIO(
        b"""Date & Time,Region,CO2 INTENSITY (gCO2/kWh),CO2 FORECAST (gCO2/kWh)
21-Jul-2026 12:00:00,Ireland,210,150
21-Jul-2026 12:15:00,Ireland,200,140
21-Jul-2026 12:30:00,Ireland,190,130
"""
    )

    result = load_actual_carbon_csv(
        source
    )

    assert result[
        "carbon_intensity"
    ].tolist() == [
        210.0,
        200.0,
        190.0,
    ]

    assert result.attrs[
        "data_kind"
    ] == "actual"


def test_calculates_realised_savings() -> None:
    result = verify_job_against_actuals(
        create_job_record(),
        create_actual_data(),
    )

    assert result.actual_average_intensity == (
        pytest.approx(100.0)
    )

    assert (
        result.actual_baseline_average_intensity
        == pytest.approx(200.0)
    )

    assert result.forecast_error == pytest.approx(
        0.0
    )

    assert result.actual_scheduled_emissions_g == (
        pytest.approx(50.0)
    )

    assert result.actual_baseline_emissions_g == (
        pytest.approx(100.0)
    )

    assert result.realised_avoided_emissions_g == (
        pytest.approx(50.0)
    )

    assert result.realised_reduction_percentage == (
        pytest.approx(50.0)
    )


def test_rejects_missing_actual_coverage() -> None:
    actual_data = create_actual_data().drop(
        index=6
    )

    with pytest.raises(
        ValueError,
        match="does not completely cover",
    ):
        verify_job_against_actuals(
            create_job_record(),
            actual_data,
        )


def test_rejects_forecast_only_csv() -> None:
    source = BytesIO(
        b"""Date & Time,Region,CO2 INTENSITY (gCO2/kWh),CO2 FORECAST (gCO2/kWh)
21-Jul-2026 12:00:00,Ireland,,150
21-Jul-2026 12:15:00,Ireland,,140
21-Jul-2026 12:30:00,Ireland,,130
"""
    )

    with pytest.raises(
        ValueError,
        match="forecast data only",
    ):
        load_actual_carbon_csv(
            source
        )
