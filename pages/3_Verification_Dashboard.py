from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from database import (
    DEFAULT_DATABASE_PATH,
    get_job,
    list_jobs,
)
from verification import (
    load_actual_carbon_csv,
    verify_job_against_actuals,
)
from verification_database import (
    get_verification,
    initialise_verification_database,
    list_verifications,
    save_verification,
)
from verification_ui import (
    build_verification_chart_data,
    build_verification_export,
    describe_verification_outcome,
)


# -------------------------------------------------------------------
# Page configuration
# -------------------------------------------------------------------

st.set_page_config(
    page_title="GridShift Verification",
    page_icon="✅",
    layout="wide",
)

try:
    initialise_verification_database(
        DEFAULT_DATABASE_PATH
    )
except Exception as error:
    st.error(
        f"Could not initialise the verification database: {error}"
    )
    st.stop()


# -------------------------------------------------------------------
# Session state
# -------------------------------------------------------------------

SESSION_DEFAULTS = {
    "verification_result": None,
    "verification_actual_data": None,
    "verification_job_id": None,
    "verification_file_signature": None,
    "verification_source_label": None,
}

for key, default_value in SESSION_DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = default_value


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------

def format_job_option(
    job_id: int,
) -> str:
    job = jobs_by_id[job_id]

    return (
        f"#{job.id} · {job.workload_name} · "
        f"{job.recommended_start.strftime('%d %b %H:%M')} · "
        f"{job.status.title()}"
    )


def format_timestamp(
    timestamp: pd.Timestamp,
) -> str:
    return timestamp.strftime(
        "%d %b %Y, %H:%M %Z"
    )


# -------------------------------------------------------------------
# Load jobs and history
# -------------------------------------------------------------------

all_jobs = list_jobs(
    limit=500,
    database_path=DEFAULT_DATABASE_PATH,
)

jobs_by_id = {
    job.id: job
    for job in all_jobs
}

verification_history = list_verifications(
    limit=500,
    database_path=DEFAULT_DATABASE_PATH,
)


# -------------------------------------------------------------------
# Header
# -------------------------------------------------------------------

st.title("✅ Forecast Verification Dashboard")

st.write(
    "Compare GridShift's carbon forecast with measured EirGrid "
    "CO₂ intensity after the scheduled workload period has passed."
)

st.info(
    "Upload an EirGrid CSV containing measured values under the "
    "`CO2 INTENSITY` column. Forecast-only CSV files cannot be "
    "used for verification."
)

if not all_jobs:
    st.warning(
        "No saved GridShift jobs exist yet. Create and save a "
        "schedule on the main page first."
    )
    st.stop()


# -------------------------------------------------------------------
# Verification summary
# -------------------------------------------------------------------

verified_job_ids = {
    record.job_id
    for record in verification_history
}

completed_job_count = sum(
    job.status == "completed"
    for job in all_jobs
)

positive_verifications = sum(
    record.realised_avoided_emissions_g > 0
    for record in verification_history
)

total_realised_savings = sum(
    max(
        record.realised_avoided_emissions_g,
        0.0,
    )
    for record in verification_history
)

summary_1, summary_2, summary_3, summary_4 = (
    st.columns(4)
)

summary_1.metric(
    "Saved jobs",
    len(all_jobs),
)

summary_2.metric(
    "Completed jobs",
    completed_job_count,
)

summary_3.metric(
    "Verified jobs",
    len(verified_job_ids),
)

summary_4.metric(
    "Realised CO₂ avoided",
    f"{total_realised_savings:.1f} gCO₂",
)

st.caption(
    f"Positive verification outcomes: {positive_verifications}"
)

st.divider()


# -------------------------------------------------------------------
# Select the job
# -------------------------------------------------------------------

st.header("Verify a saved workload")

default_job_index = 0

completed_job_ids = [
    job.id
    for job in all_jobs
    if job.status == "completed"
]

job_options = (
    completed_job_ids
    if completed_job_ids
    else list(jobs_by_id)
)

selected_job_id = st.selectbox(
    "Saved GridShift job",
    options=job_options,
    index=default_job_index,
    format_func=format_job_option,
)

selected_job = jobs_by_id[
    selected_job_id
]

if (
    st.session_state.verification_job_id
    is not None
    and st.session_state.verification_job_id
    != selected_job_id
):
    st.session_state.verification_result = None
    st.session_state.verification_actual_data = None
    st.session_state.verification_file_signature = None
    st.session_state.verification_source_label = None

st.session_state.verification_job_id = (
    selected_job_id
)


# -------------------------------------------------------------------
# Selected-job information
# -------------------------------------------------------------------

job_detail_1, job_detail_2, job_detail_3 = (
    st.columns(3)
)

job_detail_1.metric(
    "Forecast average",
    (
        f"{selected_job.average_intensity:.1f} "
        "gCO₂/kWh"
    ),
)

job_detail_2.metric(
    "Estimated saving",
    (
        f"{selected_job.avoided_emissions_g:.1f} "
        "gCO₂"
    ),
)

job_detail_3.metric(
    "Estimated reduction",
    (
        f"{selected_job.reduction_percentage:.1f}%"
    ),
)

st.write(
    f"**Scheduled window:** "
    f"{format_timestamp(selected_job.recommended_start)} "
    f"to {format_timestamp(selected_job.recommended_end)}"
)

baseline_end = (
    selected_job.earliest_start
    + pd.Timedelta(
        hours=selected_job.duration_hours
    )
)

st.write(
    f"**Baseline window:** "
    f"{format_timestamp(selected_job.earliest_start)} "
    f"to {format_timestamp(baseline_end)}"
)

st.write(
    f"**Forecast source:** "
    f"{selected_job.source_label}"
)

st.write(
    f"**Saved job status:** "
    f"{selected_job.status.title()}"
)

if selected_job.status != "completed":
    st.warning(
        "This job is not marked Completed. Verification is still "
        "possible, but the result only validates the scheduled "
        "grid period—not whether the workload actually executed."
    )

existing_verification = get_verification(
    selected_job.id,
    database_path=DEFAULT_DATABASE_PATH,
)

if existing_verification is not None:
    st.success(
        "A saved verification already exists for this job. "
        "Running verification again will replace it."
    )

st.divider()


# -------------------------------------------------------------------
# Actual-data upload
# -------------------------------------------------------------------

st.header("Upload measured EirGrid data")

uploaded_file = st.file_uploader(
    "Actual CO₂-intensity CSV",
    type=["csv"],
    help=(
        "The file must contain measured CO₂-intensity values "
        "covering both the baseline and scheduled windows."
    ),
)

actual_source_label = st.text_input(
    "Actual-data source label",
    value=(
        "EirGrid measured CO₂ intensity"
        if uploaded_file is None
        else (
            f"EirGrid measured CO₂ intensity · "
            f"{uploaded_file.name}"
        )
    ),
)

actual_data = None

if uploaded_file is not None:
    file_signature = (
        uploaded_file.name,
        uploaded_file.size,
    )

    if (
        st.session_state.verification_file_signature
        is not None
        and st.session_state.verification_file_signature
        != file_signature
    ):
        st.session_state.verification_result = None
        st.session_state.verification_actual_data = None

    st.session_state.verification_file_signature = (
        file_signature
    )

    try:
        uploaded_file.seek(0)

        actual_data = load_actual_carbon_csv(
            uploaded_file
        )

        st.session_state.verification_actual_data = (
            actual_data
        )

        data_interval = (
            actual_data["timestamp"]
            .diff()
            .dropna()
            .median()
        )

        data_interval_minutes = (
            data_interval.total_seconds()
            / 60
        )

        actual_start = actual_data.iloc[0][
            "timestamp"
        ]

        actual_end = (
            actual_data.iloc[-1]["timestamp"]
            + data_interval
        )

        upload_col_1, upload_col_2, upload_col_3 = (
            st.columns(3)
        )

        upload_col_1.metric(
            "Measured records",
            len(actual_data),
        )

        upload_col_2.metric(
            "Data interval",
            f"{data_interval_minutes:g} minutes",
        )

        upload_col_3.metric(
            "Coverage",
            (
                f"{actual_start.strftime('%d %b %H:%M')} "
                f"to {actual_end.strftime('%d %b %H:%M')}"
            ),
        )

        required_start = min(
            selected_job.earliest_start,
            selected_job.recommended_start,
        )

        required_end = max(
            baseline_end,
            selected_job.recommended_end,
        )

        if (
            actual_start <= required_start
            and actual_end >= required_end
        ):
            st.success(
                "The uploaded data appears to cover both required "
                "verification windows."
            )

        else:
            st.warning(
                "The uploaded data may not fully cover the "
                "baseline and scheduled windows."
            )

    except ValueError as error:
        st.session_state.verification_actual_data = None
        st.session_state.verification_result = None

        st.error(
            f"Could not load measured EirGrid data: {error}"
        )


# -------------------------------------------------------------------
# Calculate verification
# -------------------------------------------------------------------

if actual_data is not None:
    if st.button(
        "Calculate actual performance",
        type="primary",
    ):
        try:
            calculated_result = (
                verify_job_against_actuals(
                    selected_job,
                    actual_data,
                )
            )

            st.session_state.verification_result = (
                calculated_result
            )

            st.session_state.verification_actual_data = (
                actual_data
            )

            st.session_state.verification_source_label = (
                actual_source_label.strip()
                or "Measured EirGrid CO₂ intensity"
            )

        except ValueError as error:
            st.session_state.verification_result = None

            st.error(
                f"Could not verify this job: {error}"
            )


verification_result = (
    st.session_state.verification_result
)

stored_actual_data = (
    st.session_state.verification_actual_data
)

stored_source_label = (
    st.session_state.verification_source_label
)


# -------------------------------------------------------------------
# Verification result
# -------------------------------------------------------------------

if (
    verification_result is not None
    and verification_result.job_id
    == selected_job.id
    and stored_actual_data is not None
):
    st.divider()
    st.header("Verification result")

    metric_1, metric_2, metric_3, metric_4 = (
        st.columns(4)
    )

    metric_1.metric(
        "Forecast average",
        (
            f"{verification_result.forecast_average_intensity:.1f} "
            "gCO₂/kWh"
        ),
    )

    metric_2.metric(
        "Actual average",
        (
            f"{verification_result.actual_average_intensity:.1f} "
            "gCO₂/kWh"
        ),
    )

    metric_3.metric(
        "Forecast error",
        (
            f"{verification_result.forecast_error:+.1f} "
            "gCO₂/kWh"
        ),
    )

    metric_4.metric(
        "Absolute error",
        (
            f"{verification_result.forecast_absolute_error:.1f} "
            "gCO₂/kWh"
        ),
    )

    realised_1, realised_2, realised_3 = (
        st.columns(3)
    )

    realised_1.metric(
        "Actual scheduled emissions",
        (
            f"{verification_result.actual_scheduled_emissions_g:.1f} "
            "gCO₂"
        ),
    )

    realised_2.metric(
        "Actual baseline emissions",
        (
            f"{verification_result.actual_baseline_emissions_g:.1f} "
            "gCO₂"
        ),
    )

    realised_3.metric(
        "Realised reduction",
        (
            f"{verification_result.realised_reduction_percentage:.1f}%"
        ),
        delta=(
            f"{verification_result.realised_avoided_emissions_g:+.1f} "
            "gCO₂"
        ),
    )

    outcome_type, outcome_message = (
        describe_verification_outcome(
            verification_result
        )
    )

    if outcome_type == "success":
        st.success(outcome_message)

    elif outcome_type == "warning":
        st.warning(outcome_message)

    else:
        st.info(outcome_message)

    st.subheader("Forecast versus actual")

    chart_data = build_verification_chart_data(
        stored_actual_data,
        selected_job,
    )

    figure = px.line(
        chart_data,
        x="timestamp",
        y="carbon_intensity",
        markers=True,
        labels={
            "timestamp": "Time",
            "carbon_intensity": (
                "Actual carbon intensity (gCO₂/kWh)"
            ),
        },
    )

    figure.add_vrect(
        x0=verification_result.baseline_start,
        x1=verification_result.baseline_end,
        opacity=0.12,
        line_width=1,
        annotation_text="Baseline",
        annotation_position="top left",
    )

    figure.add_vrect(
        x0=verification_result.scheduled_start,
        x1=verification_result.scheduled_end,
        opacity=0.22,
        line_width=1,
        annotation_text="GridShift",
        annotation_position="top right",
    )

    figure.add_hline(
        y=(
            verification_result
            .forecast_average_intensity
        ),
        line_dash="dash",
        annotation_text=(
            "Forecast scheduled average"
        ),
        annotation_position="bottom right",
    )

    figure.update_layout(
        hovermode="x unified",
        legend_title_text="",
        xaxis_title="Time in Ireland",
        yaxis_title=(
            "Carbon intensity (gCO₂/kWh)"
        ),
    )

    st.plotly_chart(
        figure,
        width="stretch",
        config={
            "displaylogo": False,
            "scrollZoom": False,
        },
    )

    comparison_rows = pd.DataFrame(
        [
            {
                "Window": "Baseline",
                "Start": (
                    verification_result
                    .baseline_start
                    .strftime("%d %b %H:%M")
                ),
                "End": (
                    verification_result
                    .baseline_end
                    .strftime("%d %b %H:%M")
                ),
                "Actual average": (
                    verification_result
                    .actual_baseline_average_intensity
                ),
                "Actual emissions": (
                    verification_result
                    .actual_baseline_emissions_g
                ),
            },
            {
                "Window": "GridShift schedule",
                "Start": (
                    verification_result
                    .scheduled_start
                    .strftime("%d %b %H:%M")
                ),
                "End": (
                    verification_result
                    .scheduled_end
                    .strftime("%d %b %H:%M")
                ),
                "Actual average": (
                    verification_result
                    .actual_average_intensity
                ),
                "Actual emissions": (
                    verification_result
                    .actual_scheduled_emissions_g
                ),
            },
        ]
    )

    st.dataframe(
        comparison_rows,
        width="stretch",
        hide_index=True,
        column_config={
            "Actual average": st.column_config.NumberColumn(
                "Actual average (gCO₂/kWh)",
                format="%.1f",
            ),
            "Actual emissions": st.column_config.NumberColumn(
                "Actual emissions (gCO₂)",
                format="%.1f",
            ),
        },
    )

    st.subheader("Save and export")

    action_col_1, action_col_2 = (
        st.columns(2)
    )

    with action_col_1:
        if st.button(
            "Save verification",
            type="primary",
        ):
            try:
                save_verification(
                    verification_result,
                    source_label=(
                        stored_source_label
                        or "Measured EirGrid CO₂ intensity"
                    ),
                    database_path=(
                        DEFAULT_DATABASE_PATH
                    ),
                )

                st.success(
                    f"Verification for job "
                    f"#{selected_job.id} was saved."
                )

                st.rerun()

            except ValueError as error:
                st.error(
                    f"Could not save verification: {error}"
                )

    export_data = build_verification_export(
        job=selected_job,
        result=verification_result,
        source_label=(
            stored_source_label
            or "Measured EirGrid CO₂ intensity"
        ),
    )

    with action_col_2:
        st.download_button(
            "Download verification CSV",
            data=export_data.to_csv(
                index=False
            ),
            file_name=(
                f"gridshift_verification_"
                f"job_{selected_job.id}.csv"
            ),
            mime="text/csv",
        )

    st.caption(
        "Realised emissions remain estimates because workload "
        "energy consumption is based on the saved power value."
    )


# -------------------------------------------------------------------
# Verification history
# -------------------------------------------------------------------

st.divider()
st.header("Verification history")

verification_history = list_verifications(
    limit=500,
    database_path=DEFAULT_DATABASE_PATH,
)

if not verification_history:
    st.info(
        "No verification results have been saved yet."
    )

else:
    history_rows = []

    for record in verification_history:
        job = get_job(
            record.job_id,
            database_path=DEFAULT_DATABASE_PATH,
        )

        history_rows.append(
            {
                "Job ID": record.job_id,
                "Workload": (
                    job.workload_name
                    if job is not None
                    else "Deleted job"
                ),
                "Verified": (
                    record.verified_at.strftime(
                        "%d %b %Y %H:%M UTC"
                    )
                ),
                "Forecast average": (
                    record.forecast_average_intensity
                ),
                "Actual average": (
                    record.actual_average_intensity
                ),
                "Absolute error": (
                    record.forecast_absolute_error
                ),
                "Realised CO₂ avoided": (
                    record.realised_avoided_emissions_g
                ),
                "Realised reduction": (
                    record.realised_reduction_percentage
                ),
            }
        )

    history_frame = pd.DataFrame(
        history_rows
    )

    st.dataframe(
        history_frame,
        width="stretch",
        hide_index=True,
        column_config={
            "Forecast average": (
                st.column_config.NumberColumn(
                    "Forecast average",
                    format="%.1f gCO₂/kWh",
                )
            ),
            "Actual average": (
                st.column_config.NumberColumn(
                    "Actual average",
                    format="%.1f gCO₂/kWh",
                )
            ),
            "Absolute error": (
                st.column_config.NumberColumn(
                    "Absolute error",
                    format="%.1f gCO₂/kWh",
                )
            ),
            "Realised CO₂ avoided": (
                st.column_config.NumberColumn(
                    "Realised CO₂ avoided",
                    format="%.1f gCO₂",
                )
            ),
            "Realised reduction": (
                st.column_config.NumberColumn(
                    "Realised reduction",
                    format="%.1f%%",
                )
            ),
        },
    )
