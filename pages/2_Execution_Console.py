from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from database import (
    DEFAULT_DATABASE_PATH,
    get_job,
    list_jobs,
)
from execution_database import (
    cancel_job_run,
    create_job_run,
    initialise_execution_database,
    list_due_job_runs,
    list_job_runs,
)
from execution_ui import (
    extract_output_paths,
    read_log_tail,
    summarise_output_file,
)
from trusted_tasks import (
    build_trusted_command,
    list_trusted_tasks,
)


# -------------------------------------------------------------------
# Page setup
# -------------------------------------------------------------------

st.set_page_config(
    page_title="GridShift Execution Console",
    page_icon="⚙️",
    layout="wide",
)

try:
    initialise_execution_database(
        DEFAULT_DATABASE_PATH
    )
except Exception as error:
    st.error(
        f"Could not initialise the execution database: {error}"
    )
    st.stop()


# -------------------------------------------------------------------
# Constants and helpers
# -------------------------------------------------------------------

RUN_STATUS_LABELS = {
    "queued": "Queued",
    "running": "Running",
    "completed": "Completed",
    "failed": "Failed",
    "cancelled": "Cancelled",
}

JOB_STATUS_LABELS = {
    "scheduled": "Scheduled",
    "running": "Running",
    "completed": "Completed",
    "failed": "Failed",
    "cancelled": "Cancelled",
}

RUN_STATUS_ICONS = {
    "queued": "🕒",
    "running": "⚙️",
    "completed": "✅",
    "failed": "❌",
    "cancelled": "🚫",
}


def format_timestamp(
    timestamp: pd.Timestamp | None,
) -> str:
    if timestamp is None:
        return "Not available"

    return timestamp.strftime(
        "%d %b %Y, %H:%M:%S %Z"
    )


def format_run_title(
    run,
) -> str:
    icon = RUN_STATUS_ICONS.get(
        run.status,
        "•",
    )

    label = RUN_STATUS_LABELS.get(
        run.status,
        run.status.title(),
    )

    return (
        f"{icon} Execution #{run.id} · "
        f"{run.task_id} · {label}"
    )


# -------------------------------------------------------------------
# Load current state
# -------------------------------------------------------------------

all_jobs = list_jobs(
    limit=500,
    database_path=DEFAULT_DATABASE_PATH,
)

all_runs = list_job_runs(
    limit=1000,
    database_path=DEFAULT_DATABASE_PATH,
)

due_runs = list_due_job_runs(
    limit=100,
    database_path=DEFAULT_DATABASE_PATH,
)

runs_by_job: dict[int, list] = {}

for run in all_runs:
    runs_by_job.setdefault(
        run.job_id,
        [],
    ).append(run)


# -------------------------------------------------------------------
# Header
# -------------------------------------------------------------------

st.title("⚙️ GridShift Execution Console")

st.write(
    "Queue and inspect trusted local workloads attached to "
    "saved GridShift schedules."
)

st.warning(
    "The Streamlit application does not execute workloads itself. "
    "The separate worker process must be running in another "
    "Terminal window."
)

worker_col, refresh_col = st.columns(
    [4, 1]
)

with worker_col:
    st.code(
        "python worker.py --poll-seconds 15",
        language="bash",
    )

with refresh_col:
    st.write("")
    st.write("")

    if st.button(
        "Refresh console",
        type="primary",
        use_container_width=True,
    ):
        st.rerun()


# -------------------------------------------------------------------
# Summary
# -------------------------------------------------------------------

queued_count = sum(
    run.status == "queued"
    for run in all_runs
)

running_count = sum(
    run.status == "running"
    for run in all_runs
)

completed_count = sum(
    run.status == "completed"
    for run in all_runs
)

failed_count = sum(
    run.status == "failed"
    for run in all_runs
)

summary_1, summary_2, summary_3, summary_4 = (
    st.columns(4)
)

summary_1.metric(
    "Queued",
    queued_count,
)

summary_2.metric(
    "Running",
    running_count,
)

summary_3.metric(
    "Completed",
    completed_count,
)

summary_4.metric(
    "Failed",
    failed_count,
)

if due_runs:
    st.warning(
        f"{len(due_runs)} queued execution(s) are due now. "
        "Start or refresh the worker process to run them."
    )

st.divider()


# -------------------------------------------------------------------
# Filters
# -------------------------------------------------------------------

st.header("Saved workloads")

if not all_jobs:
    st.info(
        "No saved workloads exist yet. Return to the main "
        "GridShift page, calculate a schedule and save it."
    )
    st.stop()

filter_col_1, filter_col_2 = st.columns(2)

with filter_col_1:
    job_status_filter = st.selectbox(
        "Job status",
        options=[
            "All",
            "Scheduled",
            "Running",
            "Completed",
            "Failed",
            "Cancelled",
        ],
    )

with filter_col_2:
    execution_filter = st.selectbox(
        "Execution state",
        options=[
            "All",
            "No execution",
            "Queued",
            "Running",
            "Completed",
            "Failed",
            "Cancelled",
        ],
    )


def job_is_visible(
    job,
) -> bool:
    if (
        job_status_filter != "All"
        and JOB_STATUS_LABELS.get(
            job.status,
            job.status.title(),
        )
        != job_status_filter
    ):
        return False

    job_runs = runs_by_job.get(
        job.id,
        [],
    )

    if execution_filter == "All":
        return True

    if execution_filter == "No execution":
        return len(job_runs) == 0

    required_status = execution_filter.lower()

    return any(
        run.status == required_status
        for run in job_runs
    )


visible_jobs = [
    job
    for job in all_jobs
    if job_is_visible(job)
]

if not visible_jobs:
    st.info(
        "No saved workloads match the selected filters."
    )


# -------------------------------------------------------------------
# Workload cards
# -------------------------------------------------------------------

trusted_tasks = list_trusted_tasks()

task_by_id = {
    task.task_id: task
    for task in trusted_tasks
}

task_ids = list(
    task_by_id
)


for job in visible_jobs:
    job_runs = runs_by_job.get(
        job.id,
        [],
    )

    active_run = next(
        (
            run
            for run in job_runs
            if run.status
            in {
                "queued",
                "running",
            }
        ),
        None,
    )

    latest_run = (
        job_runs[0]
        if job_runs
        else None
    )

    job_status_label = (
        JOB_STATUS_LABELS.get(
            job.status,
            job.status.title(),
        )
    )

    title = (
        f"Job #{job.id} · "
        f"{job.workload_name} · "
        f"{job_status_label}"
    )

    with st.expander(
        title,
        expanded=(
            active_run is not None
        ),
    ):
        detail_1, detail_2, detail_3 = (
            st.columns(3)
        )

        detail_1.metric(
            "Scheduled start",
            job.recommended_start.strftime(
                "%d %b %H:%M"
            ),
        )

        detail_2.metric(
            "Duration",
            f"{job.duration_hours:g} hours",
        )

        detail_3.metric(
            "Estimated reduction",
            f"{job.reduction_percentage:.1f}%",
        )

        st.write(
            f"**Execution window:** "
            f"{format_timestamp(job.recommended_start)} "
            f"to {format_timestamp(job.recommended_end)}"
        )

        st.write(
            f"**Deadline:** "
            f"{format_timestamp(job.deadline)}"
        )

        st.write(
            f"**Workload power:** "
            f"{job.power_watts:.0f} watts"
        )

        st.write(
            f"**Forecast source:** "
            f"{job.source_label}"
        )

        st.write(
            f"**Saved job status:** "
            f"{job_status_label}"
        )

        st.divider()

        # -----------------------------------------------------------
        # Queue a trusted task
        # -----------------------------------------------------------

        if (
            active_run is None
            and job.status == "scheduled"
        ):
            st.subheader("Queue a trusted workload")

            selected_task_id = st.selectbox(
                "Trusted task",
                options=task_ids,
                format_func=(
                    lambda task_id:
                    task_by_id[task_id].label
                ),
                key=f"task_for_job_{job.id}",
            )

            selected_task = task_by_id[
                selected_task_id
            ]

            st.caption(
                selected_task.description
            )

            parameters: dict[
                str,
                object,
            ] = {}

            if (
                selected_task_id
                == "demo_ai_batch"
            ):
                item_count = st.number_input(
                    "Number of sample records",
                    min_value=1,
                    max_value=1000,
                    value=20,
                    step=1,
                    key=(
                        f"items_for_job_{job.id}"
                    ),
                )

                parameters["items"] = int(
                    item_count
                )

            command_preview = (
                build_trusted_command(
                    selected_task_id,
                    parameters,
                )
            )

            with st.expander(
                "View trusted command arguments"
            ):
                st.code(
                    "\n".join(
                        command_preview
                    ),
                    language="text",
                )

                st.caption(
                    "The worker executes this argument list with "
                    "shell=False. Arbitrary shell commands are "
                    "not accepted."
                )

            if st.button(
                "Queue trusted execution",
                type="primary",
                key=f"queue_job_{job.id}",
            ):
                try:
                    run_id = create_job_run(
                        job_id=job.id,
                        task_id=selected_task_id,
                        parameters=parameters,
                        database_path=(
                            DEFAULT_DATABASE_PATH
                        ),
                    )

                    st.success(
                        f"Execution #{run_id} was queued."
                    )

                    st.rerun()

                except (
                    ValueError,
                    RuntimeError,
                ) as error:
                    st.error(
                        f"Could not queue the execution: {error}"
                    )

        elif active_run is not None:
            active_label = (
                RUN_STATUS_LABELS.get(
                    active_run.status,
                    active_run.status.title(),
                )
            )

            if active_run.status == "queued":
                st.info(
                    f"Execution #{active_run.id} is queued. "
                    f"It becomes eligible at "
                    f"{format_timestamp(job.recommended_start)}."
                )

                now_dublin = pd.Timestamp.now(
                    tz="Europe/Dublin"
                )

                if (
                    now_dublin
                    >= job.recommended_start
                ):
                    st.warning(
                        "The scheduled start time has arrived. "
                        "The worker will execute this job during "
                        "its next polling cycle."
                    )

                if st.button(
                    "Cancel queued execution",
                    key=(
                        f"cancel_run_{active_run.id}"
                    ),
                ):
                    try:
                        cancel_job_run(
                            active_run.id,
                            database_path=(
                                DEFAULT_DATABASE_PATH
                            ),
                        )

                        st.success(
                            f"Execution #{active_run.id} "
                            "was cancelled."
                        )

                        st.rerun()

                    except ValueError as error:
                        st.error(
                            f"Could not cancel the execution: "
                            f"{error}"
                        )

            else:
                st.warning(
                    f"Execution #{active_run.id} is "
                    f"{active_label.lower()}."
                )

        elif job.status != "scheduled":
            st.info(
                "This saved job is not in the Scheduled state, "
                "so a new execution cannot be queued."
            )

        # -----------------------------------------------------------
        # Execution history
        # -----------------------------------------------------------

        st.subheader("Execution history")

        if not job_runs:
            st.caption(
                "No execution has been attached to this job."
            )

        for run in job_runs:
            with st.expander(
                format_run_title(run),
                expanded=(
                    latest_run is not None
                    and run.id
                    == latest_run.id
                ),
            ):
                run_detail_1, run_detail_2 = (
                    st.columns(2)
                )

                run_detail_1.write(
                    f"**Queued:** "
                    f"{format_timestamp(run.queued_at)}"
                )

                run_detail_1.write(
                    f"**Started:** "
                    f"{format_timestamp(run.started_at)}"
                )

                run_detail_2.write(
                    f"**Finished:** "
                    f"{format_timestamp(run.finished_at)}"
                )

                run_detail_2.write(
                    f"**Return code:** "
                    f"{run.return_code}"
                    if run.return_code is not None
                    else "**Return code:** Not available"
                )

                st.write(
                    f"**Task:** `{run.task_id}`"
                )

                st.write(
                    "**Parameters:**"
                )

                st.json(
                    run.parameters
                )

                if run.error_message:
                    st.error(
                        run.error_message
                    )

                if run.log_path:
                    try:
                        full_log_content = read_log_tail(
                            run.log_path,
                            maximum_characters=50_000,
                        )

                        displayed_log = read_log_tail(
                            run.log_path,
                            maximum_characters=12_000,
                        )

                        st.write(
                            "**Worker log:**"
                        )

                        st.code(
                            displayed_log,
                            language="text",
                        )

                        st.download_button(
                            "Download log",
                            data=full_log_content,
                            file_name=Path(
                                run.log_path
                            ).name,
                            mime="text/plain",
                            key=(
                                f"download_log_{run.id}"
                            ),
                        )

                        output_paths = (
                            extract_output_paths(
                                full_log_content
                            )
                        )

                        if output_paths:
                            st.write(
                                "**Generated outputs:**"
                            )

                        for output_path in output_paths:
                            summary = (
                                summarise_output_file(
                                    output_path
                                )
                            )

                            if summary:
                                st.json(
                                    summary
                                )

                            try:
                                output_bytes = (
                                    output_path.read_bytes()
                                )

                                st.download_button(
                                    label=(
                                        "Download "
                                        f"{output_path.name}"
                                    ),
                                    data=output_bytes,
                                    file_name=(
                                        output_path.name
                                    ),
                                    mime=(
                                        "application/json"
                                        if output_path.suffix.lower()
                                        == ".json"
                                        else (
                                            "application/octet-stream"
                                        )
                                    ),
                                    key=(
                                        f"download_output_"
                                        f"{run.id}_"
                                        f"{output_path.name}"
                                    ),
                                )

                            except OSError as error:
                                st.warning(
                                    f"Could not read output file "
                                    f"{output_path.name}: {error}"
                                )

                    except ValueError as error:
                        st.warning(
                            f"The stored log path could not be "
                            f"opened safely: {error}"
                        )

                elif run.status in {
                    "completed",
                    "failed",
                }:
                    st.caption(
                        "This execution has no stored log path."
                    )
