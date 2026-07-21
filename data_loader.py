from __future__ import annotations

import re
from typing import IO

import pandas as pd


DUBLIN_TIMEZONE = "Europe/Dublin"


def normalise_column_name(name: str) -> str:
    """
    Convert a column name into a simplified comparison form.

    Example:
        "CO2 Intensity (gCO2/kWh)" -> "co2intensitygco2kwh"
    """
    return re.sub(
        pattern=r"[^a-z0-9]",
        repl="",
        string=str(name).lower(),
    )


def find_column(
    dataframe: pd.DataFrame,
    candidates: list[str],
) -> str | None:
    """Find a DataFrame column using normalised candidate names."""
    normalised_columns = {
        normalise_column_name(column): column
        for column in dataframe.columns
    }

    for candidate in candidates:
        candidate_normalised = normalise_column_name(candidate)

        if candidate_normalised in normalised_columns:
            return normalised_columns[candidate_normalised]

    return None


def parse_timestamps(
    values: pd.Series,
) -> pd.Series:
    """
    Parse timestamps and ensure they use the Europe/Dublin timezone.
    """
    timestamps = pd.to_datetime(
        values,
        errors="coerce",
        dayfirst=True,
        format="mixed",
    )

    if timestamps.dt.tz is None:
        timestamps = timestamps.dt.tz_localize(
            DUBLIN_TIMEZONE,
            ambiguous="NaT",
            nonexistent="shift_forward",
        )
    else:
        timestamps = timestamps.dt.tz_convert(
            DUBLIN_TIMEZONE
        )

    return timestamps


def load_carbon_csv(
    csv_file: str | IO[bytes],
) -> pd.DataFrame:
    """
    Load carbon-intensity data from an EirGrid-style CSV.

    The returned DataFrame always contains:

        timestamp
        carbon_intensity
    """
    try:
        raw_data = pd.read_csv(csv_file)
    except Exception as error:
        raise ValueError(
            f"Could not read the CSV file: {error}"
        ) from error

    if raw_data.empty:
        raise ValueError(
            "The uploaded CSV file is empty."
        )

    timestamp_column = find_column(
        raw_data,
        [
            "timestamp",
            "effective time",
            "effective_time",
            "datetime",
            "date time",
            "date",
            "time",
        ],
    )

    intensity_column = find_column(
        raw_data,
        [
            "carbon intensity",
            "carbon_intensity",
            "co2 intensity",
            "co₂ intensity",
            "gco2/kwh",
            "value",
        ],
    )

    field_column = find_column(
        raw_data,
        [
            "field name",
            "field_name",
            "metric",
            "measurement",
            "series",
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

    if timestamp_column is None:
        available = ", ".join(
            str(column) for column in raw_data.columns
        )

        raise ValueError(
            "Could not identify the timestamp column. "
            f"Available columns: {available}"
        )

    if intensity_column is None:
        available = ", ".join(
            str(column) for column in raw_data.columns
        )

        raise ValueError(
            "Could not identify the carbon-intensity column. "
            f"Available columns: {available}"
        )

    filtered_data = raw_data.copy()

    # Some EirGrid exports contain several measurements in one CSV.
    # If a field-name column exists, retain only CO2-intensity rows.
    if field_column is not None:
        field_values = (
            filtered_data[field_column]
            .astype(str)
            .str.lower()
        )

        carbon_rows = (
            field_values.str.contains(
                r"co.?2|carbon",
                regex=True,
                na=False,
            )
            &
            field_values.str.contains(
                "intens",
                regex=False,
                na=False,
            )
        )

        if carbon_rows.any():
            filtered_data = filtered_data.loc[
                carbon_rows
            ].copy()

    # If multiple regions exist, prefer Republic of Ireland data.
    if region_column is not None:
        region_values = (
            filtered_data[region_column]
            .astype(str)
            .str.strip()
            .str.upper()
        )

        preferred_regions = {
            "ROI",
            "IRELAND",
            "IE",
            "REPUBLIC OF IRELAND",
        }

        ireland_rows = region_values.isin(
            preferred_regions
        )

        if ireland_rows.any():
            filtered_data = filtered_data.loc[
                ireland_rows
            ].copy()

    numeric_values = (
        filtered_data[intensity_column]
        .astype(str)
        .str.replace(",", "", regex=False)
        .str.extract(
            r"(-?\d+(?:\.\d+)?)",
            expand=False,
        )
    )

    cleaned_data = pd.DataFrame(
        {
            "timestamp": parse_timestamps(
                filtered_data[timestamp_column]
            ),
            "carbon_intensity": pd.to_numeric(
                numeric_values,
                errors="coerce",
            ),
        }
    )

    cleaned_data = cleaned_data.dropna(
        subset=[
            "timestamp",
            "carbon_intensity",
        ]
    )

    # Carbon intensity should not be negative.
    cleaned_data = cleaned_data.loc[
        cleaned_data["carbon_intensity"] >= 0
    ]

    # Multiple source rows can occasionally share a timestamp.
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
            "carbon-intensity records."
        )

    return cleaned_data


def select_latest_window(
    data: pd.DataFrame,
    hours: int = 48,
) -> pd.DataFrame:
    """
    Select the latest requested time window from historical data.
    """
    if hours <= 0:
        raise ValueError(
            "Window hours must be greater than zero."
        )

    ordered_data = (
        data
        .sort_values("timestamp")
        .reset_index(drop=True)
    )

    latest_timestamp = ordered_data[
        "timestamp"
    ].max()

    earliest_timestamp = (
        latest_timestamp
        - pd.Timedelta(hours=hours)
    )

    window = ordered_data.loc[
        ordered_data["timestamp"]
        >= earliest_timestamp
    ].copy()

    window = window.reset_index(drop=True)

    if len(window) < 2:
        raise ValueError(
            "Not enough data exists inside the selected window."
        )

    return window
