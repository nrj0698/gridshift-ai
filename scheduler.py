from __future__ import annotations

from dataclasses import dataclass
import math

import pandas as pd


@dataclass(frozen=True)
class ScheduleOption:
    """
    One valid execution-window option.
    """

    rank: int

    start_time: pd.Timestamp
    end_time: pd.Timestamp

    duration_hours: float
    average_intensity: float

    energy_kwh: float
    emissions_g: float

    avoided_emissions_g: float
    reduction_percentage: float


@dataclass(frozen=True)
class ScheduleResult:
    """
    Complete result returned by the carbon-aware scheduler.

    The original attributes remain available so the current
    Streamlit application and existing tests continue to work.
    """

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

    alternatives: tuple[ScheduleOption, ...] = ()

    earliest_start_time: pd.Timestamp | None = None
    deadline_time: pd.Timestamp | None = None

    interval_minutes: float | None = None
    candidate_count: int = 0

    @property
    def has_carbon_benefit(self) -> bool:
        """
        Return True when the recommended window is cleaner than
        the first valid execution window.
        """
        return self.avoided_emissions_g > 1e-9


def _prepare_forecast(
    forecast: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.Timedelta, float]:
    """
    Validate and standardise the supplied forecast.
    """
    required_columns = {
        "timestamp",
        "carbon_intensity",
    }

    missing_columns = required_columns.difference(
        forecast.columns
    )

    if missing_columns:
        missing_text = ", ".join(
            sorted(missing_columns)
        )

        raise ValueError(
            "Forecast is missing required columns: "
            f"{missing_text}"
        )

    if len(forecast) < 2:
        raise ValueError(
            "At least two forecast records are required."
        )

    data = forecast.copy()

    data["timestamp"] = pd.to_datetime(
        data["timestamp"],
        errors="coerce",
    )

    data["carbon_intensity"] = pd.to_numeric(
        data["carbon_intensity"],
        errors="coerce",
    )

    if data["timestamp"].isna().any():
        raise ValueError(
            "Forecast contains invalid timestamps."
        )

    if data["carbon_intensity"].isna().any():
        raise ValueError(
            "Forecast contains invalid carbon-intensity values."
        )

    if (
        data["carbon_intensity"] < 0
    ).any():
        raise ValueError(
            "Carbon-intensity values cannot be negative."
        )

    data = (
        data
        .sort_values("timestamp")
        .reset_index(drop=True)
    )

    time_differences = (
        data["timestamp"]
        .diff()
        .dropna()
    )

    if (
        time_differences
        <= pd.Timedelta(0)
    ).any():
        raise ValueError(
            "Forecast timestamps must be unique and increasing."
        )

    interval = time_differences.iloc[0]

    if not time_differences.eq(interval).all():
        raise ValueError(
            "Forecast timestamps must use one consistent interval. "
            "Missing or irregular time periods were detected."
        )

    interval_hours = (
        interval.total_seconds()
        / 3600
    )

    if interval_hours <= 0:
        raise ValueError(
            "Forecast interval must be greater than zero."
        )

    return data, interval, interval_hours


def _ceil_steps(
    hours: float,
    interval_hours: float,
) -> int:
    """
    Convert hours into complete scheduling intervals.
    """
    return math.ceil(
        hours / interval_hours - 1e-12
    )


def _floor_steps(
    hours: float,
    interval_hours: float,
) -> int:
    """
    Convert a scheduling horizon into complete intervals.
    """
    return math.floor(
        hours / interval_hours + 1e-12
    )


def find_ranked_greenest_windows(
    forecast: pd.DataFrame,
    duration_hours: float,
    deadline_hours: float,
    power_watts: float,
    earliest_start_hours: float = 0.0,
    top_n: int = 3,
) -> ScheduleResult:
    """
    Rank valid continuous execution windows by carbon intensity.

    Parameters
    ----------
    forecast:
        DataFrame containing timestamp and carbon_intensity.

    duration_hours:
        Requested workload duration.

    deadline_hours:
        Workload must finish within this many hours from the
        beginning of the forecast.

    power_watts:
        Estimated average electrical power consumed while running.

    earliest_start_hours:
        Workload cannot start before this many hours from the
        beginning of the forecast.

    top_n:
        Number of ranked options to retain, including the best
        recommendation.

    Returns
    -------
    ScheduleResult
        Best execution window, baseline comparison and alternatives.
    """
    if duration_hours <= 0:
        raise ValueError(
            "Duration must be greater than zero."
        )

    if deadline_hours <= 0:
        raise ValueError(
            "Deadline must be greater than zero."
        )

    if earliest_start_hours < 0:
        raise ValueError(
            "Earliest start cannot be negative."
        )

    if power_watts <= 0:
        raise ValueError(
            "Power must be greater than zero."
        )

    if top_n < 1:
        raise ValueError(
            "top_n must be at least 1."
        )

    if deadline_hours < duration_hours:
        raise ValueError(
            "The completion deadline must be at least as long "
            "as the workload duration."
        )

    if earliest_start_hours >= deadline_hours:
        raise ValueError(
            "Earliest start must occur before the deadline."
        )

    available_time = (
        deadline_hours
        - earliest_start_hours
    )

    if available_time < duration_hours:
        raise ValueError(
            "The workload cannot fit between the earliest start "
            "and completion deadline."
        )

    data, interval, interval_hours = (
        _prepare_forecast(forecast)
    )

    duration_steps = _ceil_steps(
        duration_hours,
        interval_hours,
    )

    earliest_start_step = _ceil_steps(
        earliest_start_hours,
        interval_hours,
    )

    deadline_step = _floor_steps(
        deadline_hours,
        interval_hours,
    )

    available_end_step = min(
        deadline_step,
        len(data),
    )

    latest_start_step = (
        available_end_step
        - duration_steps
    )

    if earliest_start_step > latest_start_step:
        dataset_horizon = (
            len(data)
            * interval_hours
        )

        raise ValueError(
            "No valid execution window fits inside the available "
            "forecast coverage. "
            f"The dataset provides approximately "
            f"{dataset_horizon:g} hours."
        )

    actual_duration_hours = (
        duration_steps
        * interval_hours
    )

    energy_kwh = (
        power_watts
        / 1000
        * actual_duration_hours
    )

    raw_candidates: list[
        tuple[int, float]
    ] = []

    for start_step in range(
        earliest_start_step,
        latest_start_step + 1,
    ):
        end_step = (
            start_step
            + duration_steps
        )

        window = data.iloc[
            start_step:end_step
        ]

        average_intensity = float(
            window["carbon_intensity"].mean()
        )

        raw_candidates.append(
            (
                start_step,
                average_intensity,
            )
        )

    if not raw_candidates:
        raise ValueError(
            "No valid scheduling candidates were found."
        )

    baseline_start_step = (
        earliest_start_step
    )

    baseline_end_step = (
        baseline_start_step
        + duration_steps
    )

    baseline_window = data.iloc[
        baseline_start_step:
        baseline_end_step
    ]

    baseline_average_intensity = float(
        baseline_window[
            "carbon_intensity"
        ].mean()
    )

    baseline_emissions_g = (
        baseline_average_intensity
        * energy_kwh
    )

    ranked_candidates = sorted(
        raw_candidates,
        key=lambda candidate: (
            candidate[1],
            candidate[0],
        ),
    )

    ranked_options: list[
        ScheduleOption
    ] = []

    for rank, (
        start_step,
        average_intensity,
    ) in enumerate(
        ranked_candidates[:top_n],
        start=1,
    ):
        start_time = data.iloc[
            start_step
        ]["timestamp"]

        end_time = (
            start_time
            + duration_steps * interval
        )

        emissions_g = (
            average_intensity
            * energy_kwh
        )

        avoided_emissions_g = (
            baseline_emissions_g
            - emissions_g
        )

        if baseline_emissions_g == 0:
            reduction_percentage = 0.0
        else:
            reduction_percentage = (
                avoided_emissions_g
                / baseline_emissions_g
                * 100
            )

        # Avoid displaying negative zero caused by floating point.
        if abs(avoided_emissions_g) < 1e-9:
            avoided_emissions_g = 0.0

        if abs(reduction_percentage) < 1e-9:
            reduction_percentage = 0.0

        ranked_options.append(
            ScheduleOption(
                rank=rank,
                start_time=start_time,
                end_time=end_time,
                duration_hours=(
                    actual_duration_hours
                ),
                average_intensity=(
                    average_intensity
                ),
                energy_kwh=energy_kwh,
                emissions_g=emissions_g,
                avoided_emissions_g=(
                    avoided_emissions_g
                ),
                reduction_percentage=(
                    reduction_percentage
                ),
            )
        )

    recommended = ranked_options[0]

    earliest_start_time = data.iloc[
        earliest_start_step
    ]["timestamp"]

    deadline_time = (
        data.iloc[0]["timestamp"]
        + deadline_step * interval
    )

    return ScheduleResult(
        start_time=recommended.start_time,
        end_time=recommended.end_time,
        duration_hours=(
            recommended.duration_hours
        ),
        average_intensity=(
            recommended.average_intensity
        ),
        immediate_average_intensity=(
            baseline_average_intensity
        ),
        energy_kwh=recommended.energy_kwh,
        scheduled_emissions_g=(
            recommended.emissions_g
        ),
        immediate_emissions_g=(
            baseline_emissions_g
        ),
        avoided_emissions_g=(
            recommended.avoided_emissions_g
        ),
        reduction_percentage=(
            recommended.reduction_percentage
        ),
        alternatives=tuple(
            ranked_options[1:]
        ),
        earliest_start_time=(
            earliest_start_time
        ),
        deadline_time=deadline_time,
        interval_minutes=(
            interval_hours * 60
        ),
        candidate_count=len(
            raw_candidates
        ),
    )


def find_greenest_window(
    forecast: pd.DataFrame,
    duration_hours: float,
    deadline_hours: float,
    power_watts: float,
) -> ScheduleResult:
    """
    Backward-compatible scheduler used by the current application.

    It assumes the workload may start immediately and returns only
    the best execution window.
    """
    return find_ranked_greenest_windows(
        forecast=forecast,
        duration_hours=duration_hours,
        deadline_hours=deadline_hours,
        power_watts=power_watts,
        earliest_start_hours=0.0,
        top_n=1,
    )
