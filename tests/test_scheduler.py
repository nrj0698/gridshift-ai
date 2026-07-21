import pandas as pd
import pytest

from scheduler import find_greenest_window


def create_forecast(
    carbon_values: list[float],
) -> pd.DataFrame:
    """
    Create a predictable hourly forecast for testing.

    Real timestamps are unnecessary here. We only need ordered,
    hourly records and known carbon-intensity values.
    """
    timestamps = pd.date_range(
        start="2026-07-21 00:00",
        periods=len(carbon_values),
        freq="h",
        tz="Europe/Dublin",
    )

    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "carbon_intensity": carbon_values,
        }
    )


def test_finds_greenest_three_hour_window() -> None:
    forecast = create_forecast(
        [
            300,
            280,
            260,
            120,
            100,
            110,
            250,
            270,
        ]
    )

    result = find_greenest_window(
        forecast=forecast,
        duration_hours=3,
        deadline_hours=8,
        power_watts=400,
    )

    expected_start = pd.Timestamp(
        "2026-07-21 03:00",
        tz="Europe/Dublin",
    )

    expected_end = pd.Timestamp(
        "2026-07-21 06:00",
        tz="Europe/Dublin",
    )

    assert result.start_time == expected_start
    assert result.end_time == expected_end

    assert result.average_intensity == pytest.approx(
        110.0
    )

    assert result.immediate_average_intensity == (
        pytest.approx(280.0)
    )

    # 400 watts × 3 hours = 1.2 kWh
    assert result.energy_kwh == pytest.approx(1.2)

    # 110 gCO₂/kWh × 1.2 kWh = 132 gCO₂
    assert result.scheduled_emissions_g == pytest.approx(
        132.0
    )

    # 280 gCO₂/kWh × 1.2 kWh = 336 gCO₂
    assert result.immediate_emissions_g == pytest.approx(
        336.0
    )

    assert result.avoided_emissions_g == pytest.approx(
        204.0
    )

    assert result.reduction_percentage == pytest.approx(
        60.7142857
    )


def test_does_not_schedule_after_deadline() -> None:
    forecast = create_forecast(
        [
            200,
            190,
            180,
            170,
            50,
            40,
        ]
    )

    result = find_greenest_window(
        forecast=forecast,
        duration_hours=2,
        deadline_hours=4,
        power_watts=300,
    )

    # The very clean values 50 and 40 occur after the deadline,
    # so the scheduler must not select them.
    expected_start = pd.Timestamp(
        "2026-07-21 02:00",
        tz="Europe/Dublin",
    )

    expected_end = pd.Timestamp(
        "2026-07-21 04:00",
        tz="Europe/Dublin",
    )

    assert result.start_time == expected_start
    assert result.end_time == expected_end
    assert result.average_intensity == pytest.approx(
        175.0
    )


def test_rejects_deadline_shorter_than_duration() -> None:
    forecast = create_forecast(
        [200, 180, 160, 140, 120]
    )

    with pytest.raises(
        ValueError,
        match=(
            "deadline must be at least as long "
            "as the workload duration"
        ),
    ):
        find_greenest_window(
            forecast=forecast,
            duration_hours=5,
            deadline_hours=3,
            power_watts=350,
        )


def test_rejects_missing_carbon_column() -> None:
    forecast = pd.DataFrame(
        {
            "timestamp": pd.date_range(
                start="2026-07-21",
                periods=5,
                freq="h",
                tz="Europe/Dublin",
            )
        }
    )

    with pytest.raises(
        ValueError,
        match="carbon_intensity",
    ):
        find_greenest_window(
            forecast=forecast,
            duration_hours=2,
            deadline_hours=5,
            power_watts=350,
        )


def test_rounds_fractional_duration_up_to_full_interval() -> None:
    forecast = create_forecast(
        [300, 250, 100, 110, 120, 240]
    )

    result = find_greenest_window(
        forecast=forecast,
        duration_hours=2.5,
        deadline_hours=6,
        power_watts=200,
    )

    # With hourly forecast data, a 2.5-hour job occupies
    # three complete forecast intervals.
    assert result.duration_hours == pytest.approx(3.0)

    expected_start = pd.Timestamp(
        "2026-07-21 02:00",
        tz="Europe/Dublin",
    )

    assert result.start_time == expected_start
