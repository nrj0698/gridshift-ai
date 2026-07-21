from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from carbon_data import generate_demo_forecast
from data_loader import load_carbon_csv, select_latest_window
from database import (
    DEFAULT_DATABASE_PATH,
    count_jobs,
    create_job,
    initialise_database,
    list_jobs,
    update_job_status,
)
from scheduler import find_ranked_greenest_windows


# -------------------------------------------------------------------
# Page configuration and database startup
# -------------------------------------------------------------------

st.set_page_config(
    page_title="GridShift AI",
    page_icon="🌱",
    layout="wide",
)

try:
    initialise_database(DEFAULT_DATABASE_PATH)
except Exception as error:
    st.error(
        f"Could not initialise the local database: {error}"
    )
    st.stop()


# -------------------------------------------------------------------
# Session state
# -------------------------------------------------------------------

SESSION_DEFAULTS = {
    "schedule_result": None,
    "schedule_inputs": None,
    "schedule_source_signature": None,
    "saved_job_id": None,
}

for key, default_value in SESSION_DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = default_value


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------

STATUS_OPTIONS = [
    "scheduled",
    "running",
    "completed",
    "failed",
    "cancelled",
]

STATUS_LABELS = {
    "scheduled": "Scheduled",
    "running": "Running",
    "completed": "Completed",
    "failed": "Failed",
    "cancelled": "Cancelled",
}


def format_timestamp(
    timestamp: pd.Timestamp,
) -> str:
    return timestamp.strftime(
        "%a %d %b, %H:%M"
    )


def format_job_timestamp(
    timestamp: pd.Timestamp,
) -> str:
    return timestamp.strftime(
        "%d %b %Y, %H:%M %Z"
    )


# -------------------------------------------------------------------
# Data-source selection
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
            "Upload an original CSV exported from the "
            "EirGrid Smart Grid Dashboard."
        ),
    )

    if uploaded_file is None:
        st.sidebar.info(
            "Upload an EirGrid CSV to use official data. "
            "Demo data is active until then."
        )

        forecast = generate_demo_forecast(
            hours=48
        )

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
    forecast = generate_demo_forecast(
        hours=48
    )


# -------------------------------------------------------------------
# Validate and describe the dataset
# -------------------------------------------------------------------

forecast_attributes = forecast.attrs.copy()

forecast = (
    forecast
    .sort_values("timestamp")
    .reset_index(drop=True)
    .copy()
)

forecast.attrs = forecast_attributes

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

interval = time_differences.median()

if not time_differences.eq(interval).all():
    st.error(
        "The active grid dataset contains missing or irregular "
        "time intervals."
    )
    st.stop()

interval_hours = (
    interval.total_seconds()
    / 3600
)

interval_minutes = (
    interval.total_seconds()
    / 60
)

if interval_hours <= 0:
    st.error(
        "The grid-data interval must be greater than zero."
    )
    st.stop()

forecast_start = forecast.iloc[0][
    "timestamp"
]

forecast_end = (
    forecast.iloc[-1]["timestamp"]
    + interval
)

available_horizon_hours = (
    forecast_end
    - forecast_start
).total_seconds() / 3600

starting_intensity = float(
    forecast.iloc[0]["carbon_intensity"]
)

source_signature = (
    source_label,
    uploaded_filename,
    len(forecast),
    str(forecast_start),
    str(forecast_end),
    round(
        float(
            forecast["carbon_intensity"].sum()
        ),
        4,
    ),
)

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
    st.session_state.saved_job_id = None


# -------------------------------------------------------------------
# Sidebar information
# -------------------------------------------------------------------

st.sidebar.divider()
st.sidebar.subheader("Dataset information")

st.sidebar.write(
    f"Records: **{len(forecast):,}**"
)

st.sidebar.write(
    f"Interval: **{interval_minutes:g} minutes**"
)

st.sidebar.write(
    f"Coverage: **{available_horizon_hours:g} hours**"
)

st.sidebar.write(
    "Coverage starts:"
)

st.sidebar.code(
    forecast_start.strftime(
        "%Y-%m-%d %H:%M %Z"
    )
)

st.sidebar.write(
    "Coverage ends:"
)

st.sidebar.code(
    forecast_end.strftime(
        "%Y-%m-%d %H:%M %Z"
    )
)

st.sidebar.divider()
st.sidebar.subheader("Saved workloads")

st.sidebar.metric(
    "Jobs in local database",
    count_jobs(DEFAULT_DATABASE_PATH),
)

st.sidebar.caption(
    "Saved locally in data/gridshift.db and excluded from Git."
)


# -------------------------------------------------------------------
# Page introduction
# -------------------------------------------------------------------

st.title("🌱 GridShift AI")

st.subheader(
    "Carbon-aware scheduling for flexible AI workloads"
)

st.info(
    "Choose when your workload may begin, when it must finish, "
    "how long it will run and how much power it consumes. "
    "GridShift evaluates every valid execution window and ranks "
    "the lowest-carbon options."
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
# Scheduling-time options
# -------------------------------------------------------------------

earliest_start_options = (
    forecast["timestamp"]
    .tolist()
)

deadline_options = [
    forecast_start
    + step_number * interval
    for step_number in range(
        1,
        len(forecast) + 1,
    )
]

default_duration = min(
    3.0,
    available_horizon_hours,
)

default_duration_steps = max(
    1,
    round(
        default_duration
        / interval_hours
    ),
)

default_duration = (
    default_duration_steps
    * interval_hours
)

default_deadline_hours = min(
    18.0,
    available_horizon_hours,
)

default_deadline_index = max(
    default_duration_steps - 1,
    min(
        len(deadline_options) - 1,
        round(
            default_deadline_hours
            / interval_hours
        ) - 1,
    ),
)


# -------------------------------------------------------------------
# Workload form
# -------------------------------------------------------------------

st.header("Configure your AI workload")

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

    first_row_col_1, first_row_col_2 = (
        st.columns(2)
    )

    with first_row_col_1:
        earliest_start_time = st.selectbox(
            "Earliest allowed start",
            options=earliest_start_options,
            index=0,
            format_func=format_timestamp,
            help=(
                "GridShift will not schedule the workload "
                "before this time."
            ),
        )

    with first_row_col_2:
        deadline_time = st.selectbox(
            "Completion deadline",
            options=deadline_options,
            index=default_deadline_index,
            format_func=format_timestamp,
            help=(
                "The workload must finish at or before "
                "this timestamp."
            ),
        )

    second_row_col_1, second_row_col_2 = (
        st.columns(2)
    )

    with second_row_col_1:
        duration_hours = st.number_input(
            "Workload duration (hours)",
            min_value=float(interval_hours),
            max_value=float(
                min(
                    24.0,
                    available_horizon_hours,
                )
            ),
            value=float(default_duration),
            step=float(interval_hours),
            help=(
                "The workload runs continuously for this "
                "amount of time."
            ),
        )

    with second_row_col_2:
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
        f"{interval_minutes:g}-minute scheduling intervals."
    )

    submitted = st.form_submit_button(
        "Find greenest schedules",
        type="primary",
    )


# -------------------------------------------------------------------
# Run Scheduler V2
# -------------------------------------------------------------------

if submitted:
    earliest_start_hours = (
        earliest_start_time
        - forecast_start
    ).total_seconds() / 3600

    deadline_hours = (
        deadline_time
        - forecast_start
    ).total_seconds() / 3600

    try:
        calculated_result = (
            find_ranked_greenest_windows(
                forecast=forecast,
                duration_hours=float(
                    duration_hours
                ),
                earliest_start_hours=float(
                    earliest_start_hours
                ),
                deadline_hours=float(
                    deadline_hours
                ),
                power_watts=float(
                    power_watts
                ),
                top_n=4,
            )
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
            "earliest_start_time": (
                earliest_start_time
            ),
            "deadline_time": (
                deadline_time
            ),
            "earliest_start_hours": float(
                earliest_start_hours
            ),
            "deadline_hours": float(
                deadline_hours
            ),
            "power_watts": float(
                power_watts
            ),
            "source_label": source_label,
        }

        st.session_state.schedule_source_signature = (
            source_signature
        )

        st.session_state.saved_job_id = None

    except ValueError as error:
        st.session_state.schedule_result = None
        st.session_state.schedule_inputs = None
        st.session_state.schedule_source_signature = None
        st.session_state.saved_job_id = None

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
    intensity_label = (
        "Replay starting intensity"
    )

elif is_official_forecast:
    intensity_label = (
        "Forecast starting intensity"
    )

else:
    intensity_label = (
        "Current simulated intensity"
    )

with overview_col_1:
    st.metric(
        label=intensity_label,
        value=(
            f"{starting_intensity:.0f} "
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
# Forecast chart
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
        annotation_text="Best window",
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
        name="Best schedule",
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
# Recommendation details and save action
# -------------------------------------------------------------------

if (
    result is not None
    and saved_inputs is not None
):
    st.divider()
    st.header("Best schedule")

    workload_display_name = saved_inputs[
        "workload_name"
    ]

    st.success(
        f"Run '{workload_display_name}' from "
        f"{result.start_time.strftime('%A %d %B at %H:%M')} "
        f"until "
        f"{result.end_time.strftime('%A %d %B at %H:%M')}."
    )

    summary_col_1, summary_col_2 = (
        st.columns(2)
    )

    with summary_col_1:
        st.subheader("First valid window")

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

    with summary_col_2:
        st.subheader("GridShift recommendation")

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
            "Candidate windows evaluated",
            f"{result.candidate_count}",
        )

    if result.has_carbon_benefit:
        st.success(
            f"Delaying this workload to the recommended period "
            f"could reduce estimated operational emissions by "
            f"{result.reduction_percentage:.1f}%."
        )

    else:
        st.info(
            "The first valid execution window is already the "
            "lowest-carbon option. GridShift recommends running "
            "the workload without an additional delay."
        )

    st.subheader("Why this window was selected")

    st.write(
        f"GridShift evaluated "
        f"{result.candidate_count} valid continuous windows "
        f"between "
        f"{saved_inputs['earliest_start_time'].strftime('%H:%M')} "
        f"and the "
        f"{saved_inputs['deadline_time'].strftime('%H:%M')} "
        f"completion deadline."
    )

    st.write(
        f"The selected window averages "
        f"{result.average_intensity:.1f} gCO₂/kWh. "
        f"The first valid window averages "
        f"{result.immediate_average_intensity:.1f} "
        f"gCO₂/kWh."
    )

    st.write(
        f"At an estimated average power of "
        f"{saved_inputs['power_watts']:.0f} watts, "
        f"the workload consumes approximately "
        f"{result.energy_kwh:.2f} kWh."
    )

    st.subheader("Alternative schedules")

    if result.alternatives:
        alternative_rows = []

        for option in result.alternatives:
            alternative_rows.append(
                {
                    "Rank": option.rank,
                    "Start": (
                        option.start_time.strftime(
                            "%a %H:%M"
                        )
                    ),
                    "End": (
                        option.end_time.strftime(
                            "%a %H:%M"
                        )
                    ),
                    "Average intensity": (
                        f"{option.average_intensity:.1f} "
                        "gCO₂/kWh"
                    ),
                    "Estimated emissions": (
                        f"{option.emissions_g:.1f} "
                        "gCO₂"
                    ),
                    "Reduction": (
                        f"{option.reduction_percentage:.1f}%"
                    ),
                }
            )

        st.dataframe(
            pd.DataFrame(
                alternative_rows
            ),
            width="stretch",
            hide_index=True,
        )

    else:
        st.info(
            "No additional valid execution windows "
            "were available."
        )

    st.subheader("Save this schedule")

    if st.session_state.saved_job_id is None:
        if st.button(
            "Save schedule to local database",
            type="primary",
            key="save_schedule_button",
        ):
            try:
                job_id = create_job(
                    workload_name=(
                        workload_display_name
                    ),
                    earliest_start=(
                        saved_inputs[
                            "earliest_start_time"
                        ]
                    ),
                    deadline=(
                        saved_inputs[
                            "deadline_time"
                        ]
                    ),
                    duration_hours=(
                        result.duration_hours
                    ),
                    power_watts=(
                        saved_inputs[
                            "power_watts"
                        ]
                    ),
                    recommended_start=(
                        result.start_time
                    ),
                    recommended_end=(
                        result.end_time
                    ),
                    average_intensity=(
                        result.average_intensity
                    ),
                    energy_kwh=(
                        result.energy_kwh
                    ),
                    scheduled_emissions_g=(
                        result.scheduled_emissions_g
                    ),
                    baseline_emissions_g=(
                        result.immediate_emissions_g
                    ),
                    avoided_emissions_g=(
                        result.avoided_emissions_g
                    ),
                    reduction_percentage=(
                        result.reduction_percentage
                    ),
                    candidate_count=(
                        result.candidate_count
                    ),
                    source_label=(
                        saved_inputs[
                            "source_label"
                        ]
                    ),
                    status="scheduled",
                    database_path=(
                        DEFAULT_DATABASE_PATH
                    ),
                )

                st.session_state.saved_job_id = (
                    job_id
                )

                st.success(
                    f"Schedule saved as job #{job_id}."
                )

                st.rerun()

            except (
                ValueError,
                RuntimeError,
            ) as error:
                st.error(
                    f"Could not save the schedule: {error}"
                )

    else:
        st.success(
            f"This recommendation is saved as job "
            f"#{st.session_state.saved_job_id}."
        )

    st.caption(
        "Energy and carbon figures are estimates based on the "
        "provided power value and active grid dataset."
    )


# -------------------------------------------------------------------
# Raw grid data
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


# -------------------------------------------------------------------
# Saved-job dashboard
# -------------------------------------------------------------------

st.divider()
st.header("Saved workload dashboard")

st.caption(
    "Schedules in this section are stored in your local SQLite "
    "database and remain available after Streamlit restarts."
)

all_jobs = list_jobs(
    limit=500,
    database_path=DEFAULT_DATABASE_PATH,
)

if not all_jobs:
    st.info(
        "No jobs have been saved yet. Calculate a schedule and "
        "use the save button above."
    )

else:
    total_avoided = sum(
        max(
            job.avoided_emissions_g,
            0.0,
        )
        for job in all_jobs
    )

    completed_count = sum(
        job.status == "completed"
        for job in all_jobs
    )

    active_count = sum(
        job.status in {
            "scheduled",
            "running",
        }
        for job in all_jobs
    )

    dashboard_col_1, dashboard_col_2, dashboard_col_3 = (
        st.columns(3)
    )

    dashboard_col_1.metric(
        "Saved jobs",
        len(all_jobs),
    )

    dashboard_col_2.metric(
        "Active jobs",
        active_count,
    )

    dashboard_col_3.metric(
        "Estimated CO₂ avoided",
        f"{total_avoided:.1f} gCO₂",
        help=(
            "Sum of positive estimated savings "
            "across saved jobs."
        ),
    )

    st.caption(
        f"Completed jobs: {completed_count}"
    )

    status_filter = st.selectbox(
        "Filter jobs by status",
        options=[
            "All"
        ]
        + [
            STATUS_LABELS[status]
            for status in STATUS_OPTIONS
        ],
    )

    if status_filter == "All":
        visible_jobs = all_jobs

    else:
        selected_status = next(
            status
            for status, label
            in STATUS_LABELS.items()
            if label == status_filter
        )

        visible_jobs = [
            job
            for job in all_jobs
            if job.status == selected_status
        ]

    if not visible_jobs:
        st.info(
            "No saved jobs match the selected status."
        )

    for job in visible_jobs:
        expander_title = (
            f"#{job.id} · "
            f"{job.workload_name} · "
            f"{STATUS_LABELS[job.status]}"
        )

        with st.expander(
            expander_title
        ):
            job_col_1, job_col_2, job_col_3 = (
                st.columns(3)
            )

            job_col_1.metric(
                "Recommended start",
                job.recommended_start.strftime(
                    "%d %b %H:%M"
                ),
            )

            job_col_2.metric(
                "Estimated emissions",
                (
                    f"{job.scheduled_emissions_g:.1f} "
                    "gCO₂"
                ),
            )

            job_col_3.metric(
                "Estimated reduction",
                (
                    f"{job.reduction_percentage:.1f}%"
                ),
            )

            st.write(
                f"**Execution window:** "
                f"{format_job_timestamp(job.recommended_start)} "
                f"to "
                f"{format_job_timestamp(job.recommended_end)}"
            )

            st.write(
                f"**Constraints:** earliest start "
                f"{format_job_timestamp(job.earliest_start)}; "
                f"deadline "
                f"{format_job_timestamp(job.deadline)}"
            )

            st.write(
                f"**Workload:** "
                f"{job.duration_hours:g} hours at "
                f"{job.power_watts:.0f} watts"
            )

            st.write(
                f"**Data source:** "
                f"{job.source_label}"
            )

            st.caption(
                f"Saved "
                f"{format_job_timestamp(job.created_at)}"
            )

            status_col, action_col = (
                st.columns(
                    [2, 1]
                )
            )

            with status_col:
                chosen_status = st.selectbox(
                    "Job status",
                    options=STATUS_OPTIONS,
                    index=STATUS_OPTIONS.index(
                        job.status
                    ),
                    format_func=(
                        lambda value:
                        STATUS_LABELS[value]
                    ),
                    key=(
                        f"status_select_{job.id}"
                    ),
                )

            with action_col:
                st.write("")
                st.write("")

                update_clicked = st.button(
                    "Update status",
                    key=(
                        f"update_status_{job.id}"
                    ),
                    disabled=(
                        chosen_status
                        == job.status
                    ),
                )

            if update_clicked:
                try:
                    update_job_status(
                        job.id,
                        chosen_status,
                        database_path=(
                            DEFAULT_DATABASE_PATH
                        ),
                    )

                    st.success(
                        f"Job #{job.id} updated to "
                        f"{STATUS_LABELS[chosen_status]}."
                    )

                    st.rerun()

                except ValueError as error:
                    st.error(
                        f"Could not update "
                        f"job #{job.id}: {error}"
                    )
