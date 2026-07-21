import pandas as pd
import pytest

from scheduler import find_ranked_greenest_windows


def create_half_hour_forecast(
    carbon_values: list[float],
) -> pd.DataFrame:
    timestamps = pd.date_range(
        start="2026-07-21 00:00",
        periods=len(carbon_values),
        freq="30min",
        tz="Europe/Dublin",
    )

    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "carbon_intensity": carbon_values,
        }
    )


def test_respects_earliest_start() -> None:
    forecast = create_half_hour_forecast(
        [
            50,
            50,
            300,
            250,
            200,
            150,
        ]
    )

    result = find_ranked_greenest_windows(
        forecast=forecast,
        duration_hours=1.0,
        earliest_start_hours=1.0,
        deadline_hours=3.0,
        power_watts=300,
        top_n=3,
    )

    expected_start = pd.Timestamp(
        "2026-07-21 02:00",
        tz="Europe/Dublin",
    )

    expected_end = pd.Timestamp(
        "2026-07-21 03:00",
        tz="Europe/Dublin",
    )

    assert result.start_time == expected_start
    assert result.end_time == expected_end

    # The cleaner 00:00–01:00 period is excluded because
    # it occurs before the earliest allowed start.
    assert result.average_intensity == pytest.approx(
        175.0
    )


def test_returns_ranked_alternatives() -> None:
    forecast = create_half_hour_forecast(
        [
            300,
            290,
            200,
            180,
            100,
            110,
            120,
            250,
        ]
    )

    result = find_ranked_greenest_windows(
        forecast=forecast,
        duration_hours=1.0,
        earliest_start_hours=1.0,
        deadline_hours=4.0,
        power_watts=400,
        top_n=3,
    )

    assert result.start_time == pd.Timestamp(
        "2026-07-21 02:00",
        tz="Europe/Dublin",
    )

    assert result.average_intensity == pytest.approx(
        105.0
    )

    assert len(result.alternatives) == 2

    first_alternative = result.alternatives[0]
    second_alternative = result.alternatives[1]

    assert first_alternative.rank == 2
    assert first_alternative.start_time == pd.Timestamp(
        "2026-07-21 02:30",
        tz="Europe/Dublin",
    )
    assert first_alternative.average_intensity == (
        pytest.approx(115.0)
    )

    assert second_alternative.rank == 3
    assert second_alternative.start_time == pd.Timestamp(
        "2026-07-21 01:30",
        tz="Europe/Dublin",
    )
    assert second_alternative.average_intensity == (
        pytest.approx(140.0)
    )


def test_reports_interval_and_candidate_count() -> None:
    forecast = create_half_hour_forecast(
        [300, 280, 260, 200, 180, 160]
    )

    result = find_ranked_greenest_windows(
        forecast=forecast,
        duration_hours=1.0,
        earliest_start_hours=0.5,
        deadline_hours=3.0,
        power_watts=250,
        top_n=3,
    )

    assert result.interval_minutes == pytest.approx(
        30.0
    )

    # Allowed starts are 00:30, 01:00, 01:30 and 02:00.
    assert result.candidate_count == 4


def test_detects_when_running_at_first_valid_time_is_best() -> None:
    forecast = create_half_hour_forecast(
        [
            100,
            110,
            150,
            180,
            200,
            220,
        ]
    )

    result = find_ranked_greenest_windows(
        forecast=forecast,
        duration_hours=1.0,
        earliest_start_hours=0.0,
        deadline_hours=3.0,
        power_watts=300,
        top_n=3,
    )

    assert result.start_time == pd.Timestamp(
        "2026-07-21 00:00",
        tz="Europe/Dublin",
    )

    assert result.avoided_emissions_g == pytest.approx(
        0.0
    )

    assert result.reduction_percentage == pytest.approx(
        0.0
    )

    assert result.has_carbon_benefit is False


def test_rejects_irregular_forecast_intervals() -> None:
    forecast = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2026-07-21 00:00",
                    "2026-07-21 00:30",
                    "2026-07-21 01:30",
                ]
            ).tz_localize("Europe/Dublin"),
            "carbon_intensity": [
                200,
                180,
                150,
            ],
        }
    )

    with pytest.raises(
        ValueError,
        match="consistent interval",
    ):
        find_ranked_greenest_windows(
            forecast=forecast,
            duration_hours=0.5,
            earliest_start_hours=0.0,
            deadline_hours=1.5,
            power_watts=300,
            top_n=3,
        )


def test_rejects_job_that_cannot_fit_after_earliest_start() -> None:
    forecast = create_half_hour_forecast(
        [200, 190, 180, 170, 160, 150]
    )

    with pytest.raises(
        ValueError,
        match="cannot fit",
    ):
        find_ranked_greenest_windows(
            forecast=forecast,
            duration_hours=2.0,
            earliest_start_hours=2.0,
            deadline_hours=3.0,
            power_watts=300,
            top_n=3,
        )
