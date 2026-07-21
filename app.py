from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from carbon_data import generate_demo_forecast
from data_loader import load_carbon_csv, select_latest_window
from scheduler import find_greenest_window


# -------------------------------------------------------------------
# Page configuration
# -------------------------------------------------------------------

st.set_page_config(
    page_title="GridShift AI",
    page_icon="🌱",
    layout="wide",
)


# -------------------------------------------------------------------
# Session state
# -------------------------------------------------------------------

DEFAULT_SESSION_VALUES = {
    "schedule_result": None,
    "schedule_inputs": None,
    "schedule_source_signature": None,
}

for key, default_value in DEFAULT_SESSION_VALUES.items():
    if key not in st.session_state:
        st.session_state[key] = default_value


# -------------------------------------------------------------------
# Data source selection
# -------------------------------------------------------------------

st.sidebar.header("Data source")

selected_source = st.sidebar.radio(
    "Choose grid data",
    options=[
        "Demo forecast",
        "EirGrid forecast CSV",
    ],
)

is_historical_replay = False
is_official_forecast = False

source_label = "Demo forecast"
uploaded_filename = None
selected_column = None


if selected_source == "EirGrid forecast CSV":
    uploaded_file = st.sidebar.file_uploader(
        "Upload an EirGrid CO₂ CSV",
        type=["csv"],
        help=(
            "Upload the original CSV exported from the "
            "EirGrid Smart Grid Dashboard."
        ),
    )

    if uploaded_file is None:
        st.sidebar.info(
            "Upload an EirGrid CSV to use official data. "
            "Demo data is being used until then."
        )

        forecast = generate_demo_forecast(hours=48)
        source_label = "Demo forecast fallback"

    else:
        try:
            uploaded_filename = uploaded_file.name

            loaded_data = load_carbon_csv(
                uploaded_file
            )

            forecast = select_latest_window(
                loaded_data,
                hours=48,
            )

            data_kind = forecast.attrs.get(
                "data_kind",
                "actual",
            )

            selected_column = forecast.attrs.get(
                "selected_column"
            )

            if data_kind == "forecast":
                is_official_forecast = True
                source_label = "EirGrid CO₂ forecast"

            else:
                is_historical_replay = True
                source_label = "EirGrid historical replay"

            st.sidebar.success(
                f"Loaded {len(forecast):,} usable records "
                f"from {uploaded_filename}."
            )

            if selected_column:
                st.sidebar.caption(
                    f"Selected column: {selected_column}"
                )

        except ValueError as error:
            st.error(
                f"Could not load the uploaded CSV: {error}"
            )
            st.stop()

else:
    forecast = generate_demo_forecast(hours=48)


# -------------------------------------------------------------------
# Validate and describe the active dataset
# -------------------------------------------------------------------

forecast = (
    forecast
    .sort_values("timestamp")
    .reset_index(drop=True)
    .copy()
)

if len(forecast) < 2:
    st.error(
        "At least two grid-data records are required."
    )
    st.stop()


time_differences = (
    forecast["timestamp"]
    .diff()
    .dropna()
)

median_interval = time_differences.median()

interval_hours = (
    median_interval.total_seconds()
    / 3600
)

if interval_hours <= 0:
    st.error(
        "The grid-data timestamps are not in a valid order."
    )
    st.stop()


available_horizon_hours = (
    len(forecast) * interval_hours
)

current_intensity = float(
    forecast.iloc[0]["carbon_intensity"]
)

first_timestamp = forecast.iloc[0]["timestamp"]
last_timestamp = forecast.iloc[-1]["timestamp"]


source_signature = (
    source_label,
    uploaded_filename,
    len(forecast),
    str(first_timestamp),
    str(last_timestamp),
    round(
        float(
            forecast["carbon_intensity"].sum()
        ),
        4,
    ),
)


# Remove a recommendation calculated using a different dataset.
if (
    st.session_state.schedule_source_signature
    is not None
    and
    st.session_state.schedule_source_signature
    != source_signature
):
    st.session_state.schedule_result = None
    st.session_state.schedule_inputs = None
    st.session_state.schedule_source_signature = None


st.sidebar.divider()
st.sidebar.subheader("Dataset information")

st.sidebar.write(
    f"Records: **{len(forecast):,}**"
)

st.sidebar.write(
    f"Interval: **{interval_hours * 60:.0f} minutes**"
)

st.sidebar.write(
    f"Available horizon: "
    f"**{available_horizon_hours:g} hours**"
)

st.sidebar.write(
    "First timestamp:"
)

st.sidebar.code(
    first_timestamp.strftime(
        "%Y-%m-%d %H:%M %Z"
    )
)

st.sidebar.write(
    "Last timestamp:"
)

st.sidebar.code(
    last_timestamp.strftime(
        "%Y-%m-%d %H:%M %Z"
    )
)


# -------------------------------------------------------------------
# Page introduction
# -------------------------------------------------------------------

st.title("🌱 GridShift AI")

st.subheader(
    "Carbon-aware scheduling for flexible AI workloads"
)

st.info(
    "Enter the workload duration, completion deadline and "
    "estimated power consumption. GridShift will evaluate every "
    "valid continuous execution window and recommend the one with "
    "the lowest forecast carbon emissions."
)


if is_historical_replay:
    st.warning(
        "Historical replay mode is active. GridShift is scheduling "
        "against past measured values, not future predictions."
    )

elif is_official_forecast:
    st.success(
        "Official EirGrid CO₂ forecast data is loaded."
    )

else:
    st.caption(
        "Prototype mode is using simulated Irish grid data."
    )


st.caption(
    f"Active data source: **{source_label}**"
)

st.divider()


# -------------------------------------------------------------------
# Workload constraints
# -------------------------------------------------------------------

st.header("Configure your AI workload")


maximum_deadline = min(
    48.0,
    available_horizon_hours,
)

maximum_duration = min(
    24.0,
    maximum_deadline,
)

minimum_step = float(interval_hours)

default_duration = min(
    3.0,
    maximum_duration,
)

default_deadline = min(
    18.0,
    maximum_deadline,
)

# Ensure the default deadline is not shorter than the duration.
default_deadline = max(
    default_deadline,
    default_duration,
)

widget_suffix = str(
    abs(hash(source_signature))
)


with st.form(
    f"workload_form_{widget_suffix}"
):
    workload_name = st.text_input(
        "Workload name",
        value="Generate product embeddings",
    )

    input_col_1, input_col_2, input_col_3 = (
        st.columns(3)
    )

    with input_col_1:
        duration_hours = st.number_input(
            "Workload duration (hours)",
            min_value=minimum_step,
            max_value=float(maximum_duration),
            value=float(default_duration),
            step=minimum_step,
            help=(
                "The continuous amount of time required by "
                "the workload."
            ),
        )

    with input_col_2:
        deadline_hours = st.number_input(
            "Must finish within (hours)",
            min_value=minimum_step,
            max_value=float(maximum_deadline),
            value=float(default_deadline),
            step=minimum_step,
            help=(
                "The workload must finish within this many "
                "hours from the beginning of the dataset."
            ),
        )

    with input_col_3:
        power_watts = st.number_input(
            "Average workload power (watts)",
            min_value=10,
            max_value=5000,
            value=350,
            step=10,
            help=(
                "Estimated average electrical power consumed "
                "while the workload is running."
            ),
        )

    st.caption(
        f"The active dataset uses "
        f"{interval_hours * 60:.0f}-minute scheduling intervals."
    )

    submitted = st.form_submit_button(
        "Calculate greenest schedule",
        type="primary",
    )


# -------------------------------------------------------------------
# Run the scheduling algorithm
# -------------------------------------------------------------------

if submitted:
    try:
        calculated_result = find_greenest_window(
            forecast=forecast,
            duration_hours=float(duration_hours),
            deadline_hours=float(deadline_hours),
            power_watts=float(power_watts),
        )

        st.session_state.schedule_result = (
            calculated_result
        )

        st.session_state.schedule_inputs = {
            "workload_name": (
                workload_name.strip()
                or "Unnamed workload"
            ),
            "requested_duration_hours": float(
                duration_hours
            ),
            "deadline_hours": float(
                deadline_hours
            ),
            "power_watts": float(
                power_watts
            ),
        }

        st.session_state.schedule_source_signature = (
            source_signature
        )

    except ValueError as error:
        st.session_state.schedule_result = None
        st.session_state.schedule_inputs = None
        st.session_state.schedule_source_signature = None

        st.error(str(error))


result = st.session_state.schedule_result
saved_inputs = st.session_state.schedule_inputs


# -------------------------------------------------------------------
# Scheduling overview
# -------------------------------------------------------------------

st.divider()
st.header("Scheduling overview")

overview_col_1, overview_col_2, overview_col_3 = (
    st.columns(3)
)


if is_historical_replay:
    intensity_metric_label = (
        "Replay starting intensity"
    )

elif is_official_forecast:
    intensity_metric_label = (
        "Forecast starting intensity"
    )

else:
    intensity_metric_label = (
        "Current simulated intensity"
    )


with overview_col_1:
    st.metric(
        label=intensity_metric_label,
        value=(
            f"{current_intensity:.0f} "
            "gCO₂/kWh"
        ),
    )


with overview_col_2:
    st.metric(
        label="Recommended start",
        value=(
            result.start_time.strftime(
                "%a %H:%M"
            )
            if result is not None
            else "Not calculated"
        ),
    )


with overview_col_3:
    st.metric(
        label="Estimated reduction",
        value=(
            f"{result.reduction_percentage:.1f}%"
            if result is not None
            else "Not calculated"
        ),
    )


# -------------------------------------------------------------------
# Grid-data chart
# -------------------------------------------------------------------

st.divider()


if is_historical_replay:
    chart_title = (
        "Irish grid historical replay"
    )

elif is_official_forecast:
    chart_title = (
        "EirGrid CO₂ forecast"
    )

else:
    chart_title = (
        "48-hour simulated Irish grid forecast"
    )


st.header(chart_title)


figure = px.line(
    forecast,
    x="timestamp",
    y="carbon_intensity",
    markers=True,
    labels={
        "timestamp": "Time",
        "carbon_intensity": (
            "Carbon intensity (gCO₂/kWh)"
        ),
    },
)


if result is not None:
    figure.add_vrect(
        x0=result.start_time,
        x1=result.end_time,
        opacity=0.22,
        line_width=1,
        annotation_text="Recommended window",
        annotation_position="top left",
    )

    recommended_window = forecast.loc[
        (
            forecast["timestamp"]
            >= result.start_time
        )
        &
        (
            forecast["timestamp"]
            < result.end_time
        )
    ]

    figure.add_scatter(
        x=recommended_window["timestamp"],
        y=recommended_window[
            "carbon_intensity"
        ],
        mode="markers",
        marker={
            "size": 11,
        },
        name="Scheduled workload",
    )


figure.update_layout(
    xaxis_title="Time in Ireland",
    yaxis_title=(
        "Carbon intensity (gCO₂/kWh)"
    ),
    hovermode="x unified",
    legend_title_text="",
)


st.plotly_chart(
    figure,
    width="stretch",
    config={
        "displaylogo": False,
        "scrollZoom": False,
    },
)


# -------------------------------------------------------------------
# Recommendation details
# -------------------------------------------------------------------

if result is not None and saved_inputs is not None:
    st.divider()
    st.header("Recommended schedule")

    workload_display_name = saved_inputs[
        "workload_name"
    ]

    st.success(
        f"Run '{workload_display_name}' from "
        f"{result.start_time.strftime('%A %d %B at %H:%M')} "
        f"until "
        f"{result.end_time.strftime('%A %d %B at %H:%M')}."
    )


    baseline_title = (
        "Replay starting window"
        if is_historical_replay
        else "Run at the first available time"
    )


    immediate_col, scheduled_col = st.columns(2)


    with immediate_col:
        st.subheader(baseline_title)

        st.metric(
            "Average carbon intensity",
            (
                f"{result.immediate_average_intensity:.1f} "
                "gCO₂/kWh"
            ),
        )

        st.metric(
            "Estimated emissions",
            (
                f"{result.immediate_emissions_g:.1f} "
                "gCO₂"
            ),
        )


    with scheduled_col:
        st.subheader("GridShift schedule")

        st.metric(
            "Average carbon intensity",
            (
                f"{result.average_intensity:.1f} "
                "gCO₂/kWh"
            ),
        )

        st.metric(
            "Estimated emissions",
            (
                f"{result.scheduled_emissions_g:.1f} "
                "gCO₂"
            ),
            delta=(
                f"-{result.avoided_emissions_g:.1f} "
                "gCO₂"
            ),
            delta_color="inverse",
        )


    impact_col_1, impact_col_2, impact_col_3 = (
        st.columns(3)
    )


    with impact_col_1:
        st.metric(
            "Estimated energy",
            f"{result.energy_kwh:.2f} kWh",
        )


    with impact_col_2:
        st.metric(
            "Estimated CO₂ avoided",
            (
                f"{result.avoided_emissions_g:.1f} "
                "gCO₂"
            ),
        )


    with impact_col_3:
        st.metric(
            "Scheduled duration",
            f"{result.duration_hours:g} hours",
        )


    st.subheader("Why this window was selected")

    st.write(
        f"GridShift evaluated every continuous "
        f"{result.duration_hours:g}-hour window available "
        f"before the "
        f"{saved_inputs['deadline_hours']:g}-hour deadline."
    )

    st.write(
        f"The recommended window has an average carbon "
        f"intensity of {result.average_intensity:.1f} "
        f"gCO₂/kWh. The first available execution window "
        f"has an average intensity of "
        f"{result.immediate_average_intensity:.1f} "
        f"gCO₂/kWh."
    )

    st.write(
        f"At an estimated average power consumption of "
        f"{saved_inputs['power_watts']:.0f} watts, "
        f"the workload would consume approximately "
        f"{result.energy_kwh:.2f} kWh."
    )


    if result.avoided_emissions_g > 0:
        st.write(
            f"Scheduling the workload in the recommended window "
            f"could avoid approximately "
            f"{result.avoided_emissions_g:.1f} grams of CO₂, "
            f"an estimated reduction of "
            f"{result.reduction_percentage:.1f}%."
        )

    elif result.avoided_emissions_g == 0:
        st.write(
            "The scheduler found no carbon advantage over "
            "the first available execution window."
        )

    else:
        st.warning(
            "No cleaner valid window was available before "
            "the selected deadline."
        )


    st.caption(
        "Energy and carbon figures are estimates based on the "
        "provided power value and the active grid dataset."
    )


# -------------------------------------------------------------------
# Raw grid-data table
# -------------------------------------------------------------------

with st.expander("View grid data"):
    display_data = forecast.copy()

    display_data["timestamp"] = (
        display_data["timestamp"]
        .dt.strftime(
            "%a %d %b %Y, %H:%M"
        )
    )

    renamed_columns = {
        "timestamp": "Time",
        "carbon_intensity": (
            "Carbon intensity (gCO₂/kWh)"
        ),
    }

    if (
        "renewable_percentage"
        in display_data.columns
    ):
        renamed_columns[
            "renewable_percentage"
        ] = "Estimated renewables (%)"

    display_data = display_data.rename(
        columns=renamed_columns
    )

    st.dataframe(
        display_data,
        width="stretch",
        hide_index=True,
    )
