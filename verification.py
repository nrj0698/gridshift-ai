from __future__ import annotations

from dataclasses import dataclass
from typing import IO

import pandas as pd

from data_loader import (
    filter_ireland_rows,
    find_column,
    parse_timestamps,
    to_numeric,
)
from database import JobRecord


DUBLIN_TIMEZONE = "Europe/Dublin"


@dataclass(frozen=True)
class VerificationResult:
    """Actual-carbon verification for one scheduled workload."""

    job_id: int

    scheduled_start: pd.Timestamp
    scheduled_end: pd.Timestamp

    baseline_start: pd.Timestamp
    baseline_end: pd.Timestamp

    forecast_average_intensity: float
    actual_average_intensity: float

    forecast_error: float
    forecast_absolute_error: float
    forecast_error_percentage: float

    actual_baseline_average_intensity: float

    energy_kwh: float

    actual_scheduled_emissions_g: float
    actual_baseline_emissions_g: float

    realised_avoided_emissions_g: float
    realised_reduction_percentage: float

    scheduled_point_count: int
    baseline_point_count: int


def load_actual_carbon_csv(
    csv_file: str | IO[bytes],
) -> pd.DataFrame:
    """
    Load measured CO₂ intensity from an EirGrid CSV.

    Unlike the normal GridShift loader, this function deliberately
    ignores forecast values and requires measured intensity data.

    Supported formats:

    Wide:
        Date & Time
        Region
        CO2 INTENSITY (gCO2/kWh)
        CO2 FORECAST (gCO2/kWh)

    Long:
        EffectiveTime
        FieldName
        Region
        Value
    """
    try:
        raw_data = pd.read_csv(csv_file)
    except Exception as error:
        raise ValueError(
            f"Could not read the actual-intensity CSV: {error}"
        ) from error

    if raw_data.empty:
        raise ValueError(
            "The actual-intensity CSV is empty."
        )

    timestamp_column = find_column(
        raw_data,
        [
            "date & time",
            "date and time",
            "timestamp",
            "effective time",
            "effective_time",
            "effectivetime",
            "datetime",
            "date time",
        ],
    )

    region_column = find_column(
        raw_data,
        [
            "region",
            "jurisdiction",
            "area",
        ],
    )

    actual_column = find_column(
        raw_data,
        [
            "co2 intensity (gco2/kwh)",
            "co2 intensity",
            "carbon intensity",
            "carbon_intensity",
        ],
    )

    field_column = find_column(
        raw_data,
        [
            "field name",
            "field_name",
            "fieldname",
            "metric",
            "measurement",
            "series",
        ],
    )

    value_column = find_column(
        raw_data,
        [
            "value",
            "measurement value",
            "measurement_value",
        ],
    )

    if timestamp_column is None:
        available_columns = ", ".join(
            str(column)
            for column in raw_data.columns
        )

        raise ValueError(
            "Could not identify the timestamp column. "
            f"Available columns: {available_columns}"
        )

    filtered_data = filter_ireland_rows(
        raw_data,
        region_column,
    )

    selected_data: pd.DataFrame | None = None
    selected_values: pd.Series | None = None
    selected_column: str | None = None

    # Wide EirGrid format.
    if actual_column is not None:
        actual_values = to_numeric(
            filtered_data[actual_column]
        )

        if actual_values.notna().sum() >= 2:
            selected_data = filtered_data.copy()
            selected_values = actual_values
            selected_column = actual_column

    # Long EirGrid format.
    if (
        selected_data is None
        and field_column is not None
        and value_column is not None
    ):
        field_values = (
            filtered_data[field_column]
            .astype(str)
            .str.strip()
            .str.lower()
        )

        carbon_rows = field_values.str.contains(
            r"co.?2|carbon",
            regex=True,
            na=False,
        )

        intensity_rows = field_values.str.contains(
            "intens",
            regex=False,
            na=False,
        )

        non_forecast_rows = ~field_values.str.contains(
            "forecast",
            regex=False,
            na=False,
        )

        actual_rows = (
            carbon_rows
            & intensity_rows
            & non_forecast_rows
        )

        actual_long_data = filtered_data.loc[
            actual_rows
        ].copy()

        actual_long_values = to_numeric(
            actual_long_data[value_column]
        )

        if actual_long_values.notna().sum() >= 2:
            selected_data = actual_long_data
            selected_values = actual_long_values
            selected_column = value_column

    if (
        selected_data is None
        or selected_values is None
    ):
        raise ValueError(
            "The CSV does not contain at least two usable "
            "measured CO₂-intensity values. It may contain "
            "forecast data only."
        )

    cleaned_data = pd.DataFrame(
        {
            "timestamp": parse_timestamps(
                selected_data[timestamp_column]
            ),
            "carbon_intensity": selected_values,
        }
    )

    cleaned_data = cleaned_data.dropna(
        subset=[
            "timestamp",
            "carbon_intensity",
        ]
    )

    cleaned_data = cleaned_data.loc[
        cleaned_data["carbon_intensity"] >= 0
    ]

    cleaned_data = (
        cleaned_data
        .groupby(
            "timestamp",
            as_index=False,
        )["carbon_intensity"]
        .mean()
        .sort_values("timestamp")
        .reset_index(drop=True)
    )

    if len(cleaned_data) < 2:
        raise ValueError(
            "The CSV did not contain enough usable "
            "actual-intensity records."
        )

    cleaned_data.attrs["data_kind"] = "actual"
    cleaned_data.attrs["selected_column"] = selected_column
    cleaned_data.attrs["region"] = "Ireland"

    return cleaned_data


def _prepare_actual_data(
    actual_data: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.Timedelta]:
    required_columns = {
        "timestamp",
        "carbon_intensity",
    }

    missing_columns = required_columns.difference(
        actual_data.columns
    )

    if missing_columns:
        missing_text = ", ".join(
            sorted(missing_columns)
        )

        raise ValueError(
            "Actual data is missing required columns: "
            f"{missing_text}"
        )

    if len(actual_data) < 2:
        raise ValueError(
            "At least two actual-intensity records are required."
        )

    data = actual_data.copy()

    data["timestamp"] = parse_timestamps(
        data["timestamp"]
    )

    data["carbon_intensity"] = pd.to_numeric(
        data["carbon_intensity"],
        errors="coerce",
    )

    data = data.dropna(
        subset=[
            "timestamp",
            "carbon_intensity",
        ]
    )

    data = data.loc[
        data["carbon_intensity"] >= 0
    ]

    data = (
        data
        .groupby(
            "timestamp",
            as_index=False,
        )["carbon_intensity"]
        .mean()
        .sort_values("timestamp")
        .reset_index(drop=True)
    )

    if len(data) < 2:
        raise ValueError(
            "Not enough valid actual-intensity records remain."
        )

    differences = (
        data["timestamp"]
        .diff()
        .dropna()
    )

    positive_differences = differences.loc[
        differences > pd.Timedelta(0)
    ]

    if positive_differences.empty:
        raise ValueError(
            "Actual-data timestamps must increase."
        )

    # Mode handles occasional gaps better than the median.
    interval_modes = positive_differences.mode()

    interval = (
        interval_modes.iloc[0]
        if not interval_modes.empty
        else positive_differences.min()
    )

    if interval <= pd.Timedelta(0):
        raise ValueError(
            "Actual-data interval must be greater than zero."
        )

    return data, interval


def _window_average(
    actual_data: pd.DataFrame,
    *,
    start_time: pd.Timestamp,
    end_time: pd.Timestamp,
) -> tuple[float, int]:
    """
    Calculate a complete interval-weighted average.

    The function rejects windows with missing measurement points
    instead of silently averaging incomplete data.
    """
    data, interval = _prepare_actual_data(
        actual_data
    )

    start = pd.Timestamp(start_time)
    end = pd.Timestamp(end_time)

    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError(
            "Verification timestamps must include timezone "
            "information."
        )

    data_timezone = data["timestamp"].dt.tz

    start = start.tz_convert(data_timezone)
    end = end.tz_convert(data_timezone)

    if end <= start:
        raise ValueError(
            "Verification window end must occur after its start."
        )

    duration_seconds = (
        end - start
    ).total_seconds()

    interval_seconds = interval.total_seconds()

    steps_float = (
        duration_seconds
        / interval_seconds
    )

    steps = round(steps_float)

    if (
        steps < 1
        or abs(steps_float - steps) > 1e-9
    ):
        raise ValueError(
            "The verification window is not aligned with the "
            "actual-data interval."
        )

    expected_timestamps = pd.date_range(
        start=start,
        periods=steps,
        freq=interval,
    )

    indexed_data = (
        data
        .set_index("timestamp")
        ["carbon_intensity"]
    )

    missing_timestamps = (
        expected_timestamps
        .difference(indexed_data.index)
    )

    if not missing_timestamps.empty:
        first_missing = missing_timestamps[0]

        raise ValueError(
            "Actual intensity data does not completely cover the "
            "verification window. First missing timestamp: "
            f"{first_missing}."
        )

    values = indexed_data.reindex(
        expected_timestamps
    )

    if values.isna().any():
        raise ValueError(
            "Actual intensity data contains missing values inside "
            "the verification window."
        )

    return (
        float(values.mean()),
        int(len(values)),
    )


def verify_job_against_actuals(
    job: JobRecord,
    actual_data: pd.DataFrame,
) -> VerificationResult:
    """
    Compare the forecast used by a saved job against measured
    EirGrid intensity.

    The realised savings comparison uses the same estimated energy
    for both schedules. This isolates the effect of choosing a
    different grid period.
    """
    scheduled_average, scheduled_count = (
        _window_average(
            actual_data,
            start_time=job.recommended_start,
            end_time=job.recommended_end,
        )
    )

    baseline_start = job.earliest_start

    baseline_end = (
        baseline_start
        + pd.Timedelta(
            hours=job.duration_hours
        )
    )

    baseline_average, baseline_count = (
        _window_average(
            actual_data,
            start_time=baseline_start,
            end_time=baseline_end,
        )
    )

    forecast_error = (
        scheduled_average
        - job.average_intensity
    )

    forecast_absolute_error = abs(
        forecast_error
    )

    if job.average_intensity == 0:
        forecast_error_percentage = 0.0
    else:
        forecast_error_percentage = (
            forecast_error
            / job.average_intensity
            * 100
        )

    actual_scheduled_emissions = (
        scheduled_average
        * job.energy_kwh
    )

    actual_baseline_emissions = (
        baseline_average
        * job.energy_kwh
    )

    realised_avoided_emissions = (
        actual_baseline_emissions
        - actual_scheduled_emissions
    )

    if actual_baseline_emissions == 0:
        realised_reduction_percentage = 0.0
    else:
        realised_reduction_percentage = (
            realised_avoided_emissions
            / actual_baseline_emissions
            * 100
        )

    return VerificationResult(
        job_id=job.id,
        scheduled_start=job.recommended_start,
        scheduled_end=job.recommended_end,
        baseline_start=baseline_start,
        baseline_end=baseline_end,
        forecast_average_intensity=(
            job.average_intensity
        ),
        actual_average_intensity=(
            scheduled_average
        ),
        forecast_error=forecast_error,
        forecast_absolute_error=(
            forecast_absolute_error
        ),
        forecast_error_percentage=(
            forecast_error_percentage
        ),
        actual_baseline_average_intensity=(
            baseline_average
        ),
        energy_kwh=job.energy_kwh,
        actual_scheduled_emissions_g=(
            actual_scheduled_emissions
        ),
        actual_baseline_emissions_g=(
            actual_baseline_emissions
        ),
        realised_avoided_emissions_g=(
            realised_avoided_emissions
        ),
        realised_reduction_percentage=(
            realised_reduction_percentage
        ),
        scheduled_point_count=(
            scheduled_count
        ),
        baseline_point_count=(
            baseline_count
        ),
    )
