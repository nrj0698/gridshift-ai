from __future__ import annotations

import re
from typing import IO

import pandas as pd


DUBLIN_TIMEZONE = "Europe/Dublin"


def normalise_column_name(name: str) -> str:
    """
    Convert a column name into a simplified comparison form.

    Example:
        "CO2 FORECAST (gCO2/kWh)"
        becomes
        "co2forecastgco2kwh"
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
    """
    Find a DataFrame column using normalised candidate names.
    """
    normalised_columns = {
        normalise_column_name(column): column
        for column in dataframe.columns
    }

    for candidate in candidates:
        normalised_candidate = normalise_column_name(
            candidate
        )

        if normalised_candidate in normalised_columns:
            return normalised_columns[
                normalised_candidate
            ]

    return None


def parse_timestamps(
    values: pd.Series,
) -> pd.Series:
    """
    Parse timestamps and attach the Europe/Dublin timezone.
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


def to_numeric(
    values: pd.Series,
) -> pd.Series:
    """
    Extract numeric values from a CSV column.
    """
    extracted_values = (
        values
        .astype(str)
        .str.replace(",", "", regex=False)
        .str.extract(
            r"(-?\d+(?:\.\d+)?)",
            expand=False,
        )
    )

    return pd.to_numeric(
        extracted_values,
        errors="coerce",
    )


def filter_ireland_rows(
    dataframe: pd.DataFrame,
    region_column: str | None,
) -> pd.DataFrame:
    """
    Prefer Republic of Ireland rows when a region column exists.
    """
    if region_column is None:
        return dataframe.copy()

    region_values = (
        dataframe[region_column]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    ireland_rows = region_values.isin(
        {
            "ROI",
            "IRELAND",
            "IE",
            "REPUBLIC OF IRELAND",
        }
    )

    if ireland_rows.any():
        return dataframe.loc[
            ireland_rows
        ].copy()

    return dataframe.copy()


def load_carbon_csv(
    csv_file: str | IO[bytes],
) -> pd.DataFrame:
    """
    Load carbon data from either of these EirGrid CSV formats:

    Wide format:
        Date & Time
        Region
        CO2 INTENSITY (gCO2/kWh)
        CO2 FORECAST (gCO2/kWh)

    Long format:
        EffectiveTime
        FieldName
        Region
        Value

    Forecast values are preferred when at least two usable
    forecast records exist. Otherwise, measured intensity values
    are used.

    Returns
    -------
    pandas.DataFrame
        Columns:
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

    forecast_column = find_column(
        raw_data,
        [
            "co2 forecast (gco2/kwh)",
            "co2 forecast",
            "carbon forecast",
            "forecast carbon intensity",
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
    data_kind: str | None = None

    # ---------------------------------------------------------------
    # Format 1: wide EirGrid CSV
    # ---------------------------------------------------------------

    if forecast_column is not None:
        forecast_values = to_numeric(
            filtered_data[forecast_column]
        )
    else:
        forecast_values = pd.Series(
            index=filtered_data.index,
            dtype=float,
        )

    if actual_column is not None:
        actual_values = to_numeric(
            filtered_data[actual_column]
        )
    else:
        actual_values = pd.Series(
            index=filtered_data.index,
            dtype=float,
        )

    forecast_count = int(
        forecast_values.notna().sum()
    )

    actual_count = int(
        actual_values.notna().sum()
    )

    if forecast_count >= 2:
        selected_data = filtered_data.copy()
        selected_values = forecast_values
        selected_column = forecast_column
        data_kind = "forecast"

    elif actual_count >= 2:
        selected_data = filtered_data.copy()
        selected_values = actual_values
        selected_column = actual_column
        data_kind = "actual"

    # ---------------------------------------------------------------
    # Format 2: long EirGrid CSV
    # ---------------------------------------------------------------

    elif (
        field_column is not None
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

        forecast_rows = (
            carbon_rows
            & field_values.str.contains(
                "forecast",
                regex=False,
                na=False,
            )
        )

        intensity_rows = (
            carbon_rows
            & field_values.str.contains(
                "intens",
                regex=False,
                na=False,
            )
        )

        forecast_long_data = filtered_data.loc[
            forecast_rows
        ].copy()

        actual_long_data = filtered_data.loc[
            intensity_rows
        ].copy()

        forecast_long_values = to_numeric(
            forecast_long_data[value_column]
        )

        actual_long_values = to_numeric(
            actual_long_data[value_column]
        )

        if (
            forecast_long_values
            .notna()
            .sum()
            >= 2
        ):
            selected_data = forecast_long_data
            selected_values = forecast_long_values
            selected_column = value_column
            data_kind = "forecast"

        elif (
            actual_long_values
            .notna()
            .sum()
            >= 2
        ):
            selected_data = actual_long_data
            selected_values = actual_long_values
            selected_column = value_column
            data_kind = "actual"

    if (
        selected_data is None
        or selected_values is None
        or data_kind is None
    ):
        available_columns = ", ".join(
            str(column)
            for column in raw_data.columns
        )

        raise ValueError(
            "The CSV does not contain at least two usable "
            "CO₂ forecast or intensity values. "
            f"Available columns: {available_columns}"
        )

    cleaned_data = pd.DataFrame(
        {
            "timestamp": parse_timestamps(
                selected_data[timestamp_column]
            ),
            "carbon_intensity": (
                selected_values
            ),
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
            "carbon-intensity records."
        )

    cleaned_data.attrs["data_kind"] = data_kind
    cleaned_data.attrs["selected_column"] = (
        selected_column
    )
    cleaned_data.attrs["region"] = "Ireland"

    return cleaned_data


def select_latest_window(
    data: pd.DataFrame,
    hours: int = 48,
) -> pd.DataFrame:
    """
    Select the latest requested time window from the data.
    """
    if hours <= 0:
        raise ValueError(
            "Window hours must be greater than zero."
        )

    ordered_data = (
        data
        .sort_values("timestamp")
        .reset_index(drop=True)
        .copy()
    )

    ordered_data.attrs = data.attrs.copy()

    latest_timestamp = ordered_data[
        "timestamp"
    ].max()

    earliest_timestamp = (
        latest_timestamp
        - pd.Timedelta(hours=hours)
    )

    window = (
        ordered_data.loc[
            ordered_data["timestamp"]
            >= earliest_timestamp
        ]
        .reset_index(drop=True)
        .copy()
    )

    window.attrs = data.attrs.copy()

    if len(window) < 2:
        raise ValueError(
            "Not enough data exists inside the selected window."
        )

    return window
