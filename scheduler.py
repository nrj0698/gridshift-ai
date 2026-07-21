from __future__ import annotations

from dataclasses import dataclass
import math

import pandas as pd


@dataclass(frozen=True)
class ScheduleResult:
    """The result returned by the carbon-aware scheduler."""

    start_time: pd.Timestamp
    end_time: pd.Timestamp
    duration_hours: float

    average_intensity: float
    immediate_average_intensity: float

    energy_kwh: float
    scheduled_emissions_g: float
    immediate_emissions_g: float

    avoided_emissions_g: float
    reduction_percentage: float


def find_greenest_window(
    forecast: pd.DataFrame,
    duration_hours: float,
    deadline_hours: float,
    power_watts: float,
) -> ScheduleResult:
    """
    Find the lowest-carbon continuous execution window.

    Parameters
    ----------
    forecast:
        DataFrame containing timestamp and carbon_intensity columns.

    duration_hours:
        Number of hours required by the workload.

    deadline_hours:
        The workload must finish within this many hours from now.

    power_watts:
        Estimated average electrical power used by the workload.

    Returns
    -------
    ScheduleResult
        Details of the recommended execution window and its
        estimated environmental impact.
    """
    required_columns = {
        "timestamp",
        "carbon_intensity",
    }

    missing_columns = required_columns.difference(
        forecast.columns
    )

    if missing_columns:
        missing_text = ", ".join(sorted(missing_columns))
        raise ValueError(
            f"Forecast is missing required columns: {missing_text}"
        )

    if duration_hours <= 0:
        raise ValueError(
            "Duration must be greater than zero."
        )

    if deadline_hours <= 0:
        raise ValueError(
            "Deadline must be greater than zero."
        )

    if power_watts <= 0:
        raise ValueError(
            "Power must be greater than zero."
        )

    if deadline_hours < duration_hours:
        raise ValueError(
            "The completion deadline must be at least as long "
            "as the workload duration."
        )

    data = (
        forecast
        .sort_values("timestamp")
        .reset_index(drop=True)
        .copy()
    )

    if len(data) < 2:
        raise ValueError(
            "At least two forecast records are required."
        )

    time_differences = (
        data["timestamp"]
        .diff()
        .dropna()
    )

    interval = time_differences.median()

    interval_hours = (
        interval.total_seconds() / 3600
    )

    if interval_hours <= 0:
        raise ValueError(
            "Forecast timestamps must be in increasing order."
        )

    # Convert workload duration into forecast rows.
    duration_steps = math.ceil(
        duration_hours / interval_hours
    )

    # Only examine rows available before the deadline.
    deadline_steps = math.floor(
        deadline_hours / interval_hours
    )

    available_steps = min(
        deadline_steps,
        len(data),
    )

    if duration_steps > available_steps:
        raise ValueError(
            "There is not enough forecast data before the deadline "
            "to schedule this workload."
        )

    available_intensity = (
        data.loc[
            : available_steps - 1,
            "carbon_intensity",
        ]
        .astype(float)
    )

    # Calculate the total intensity of every continuous window.
    window_totals = (
        available_intensity
        .rolling(window=duration_steps)
        .sum()
        .shift(-(duration_steps - 1))
        .dropna()
    )

    best_start_index = int(
        window_totals.idxmin()
    )

    best_end_index = (
        best_start_index + duration_steps
    )

    best_window = data.iloc[
        best_start_index:best_end_index
    ]

    immediate_window = data.iloc[
        0:duration_steps
    ]

    average_intensity = float(
        best_window["carbon_intensity"].mean()
    )

    immediate_average_intensity = float(
        immediate_window[
            "carbon_intensity"
        ].mean()
    )

    actual_duration_hours = (
        duration_steps * interval_hours
    )

    energy_kwh = (
        power_watts
        / 1000
        * actual_duration_hours
    )

    scheduled_emissions_g = (
        average_intensity * energy_kwh
    )

    immediate_emissions_g = (
        immediate_average_intensity * energy_kwh
    )

    avoided_emissions_g = (
        immediate_emissions_g
        - scheduled_emissions_g
    )

    if immediate_emissions_g == 0:
        reduction_percentage = 0.0
    else:
        reduction_percentage = (
            avoided_emissions_g
            / immediate_emissions_g
            * 100
        )

    start_time = best_window.iloc[0][
        "timestamp"
    ]

    end_time = (
        start_time
        + duration_steps * interval
    )

    return ScheduleResult(
        start_time=start_time,
        end_time=end_time,
        duration_hours=actual_duration_hours,
        average_intensity=average_intensity,
        immediate_average_intensity=(
            immediate_average_intensity
        ),
        energy_kwh=energy_kwh,
        scheduled_emissions_g=(
            scheduled_emissions_g
        ),
        immediate_emissions_g=(
            immediate_emissions_g
        ),
        avoided_emissions_g=(
            avoided_emissions_g
        ),
        reduction_percentage=(
            reduction_percentage
        ),
    )
