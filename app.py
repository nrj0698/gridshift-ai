from __future__ import annotations

import plotly.express as px
import streamlit as st

from carbon_data import generate_demo_forecast
from data_loader import load_carbon_csv, select_latest_window
from scheduler import find_greenest_window


st.set_page_config(
    page_title="GridShift AI",
    page_icon="🌱",
    layout="wide",
)


# -------------------------------------------------------------------
# Session state
# -------------------------------------------------------------------

for key, default_value in {
    "schedule_result": None,
    "schedule_inputs": None,
    "data_signature": None,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default_value


# -------------------------------------------------------------------
# Data source
# -------------------------------------------------------------------

st.sidebar.header("Data source")

source = st.sidebar.radio(
    "Choose grid data",
    [
        "Demo forecast",
        "EirGrid CSV replay",
    ],
)

is_historical_replay = False
source_label = "Demo forecast"
uploaded_name = None


if source == "EirGrid CSV replay":
    uploaded_file = st.sidebar.file_uploader(
        "Upload an EirGrid CO₂ CSV",
        type=["csv"],
    )

    if uploaded_file is None:
        st.sidebar.info(
            "Upload a CSV. Demo data is being used for now."
        )

        forecast = generate_demo_forecast(hours=48)
        source_label = "Demo forecast fallback"

    else:
        try:
            uploaded_name = uploaded_file.name

            historical_data = load_carbon_csv(
                uploaded_file
            )

            forecast = select_latest_window(
                historical_data,
                hours=48,
            )

            is_historical_replay = True
            source_label = "EirGrid historical replay"

            st.sidebar.success(
                f"Loaded {len(forecast):,} records "
                f"from {uploaded_name}."
            )

        except ValueError as error:
            st.error(str(error))
            st.stop()

else:
    forecast = generate_demo_forecast(hours=48)


current_signature = (
    source_label,
    uploaded_name,
    len(forecast),
    str(forecast.iloc[0]["timestamp"]),
    str(forecast.iloc[-1]["timestamp"]),
)


if (
    st.session_state.data_signature is not None
    and st.session_state.data_signature
    != current_signature
):
    st.session_state.schedule_result = None
    st.session_state.schedule_inputs = None
    st.session_state.data_signature = None


current_intensity = float(
    forecast.iloc[0]["carbon_intensity"]
)


# -------------------------------------------------------------------
# Header
# -------------------------------------------------------------------

st.title("🌱 GridShift AI")

st.subheader(
    "Carbon-aware scheduling for flexible AI workloads"
)

st.info(
    "Enter the workload duration, deadline and estimated power. "
    "GridShift will find the lowest-carbon continuous execution "
    "window."
)


if is_historical_replay:
    st.warning(
        "Historical replay mode uses past measured data, "
        "not a future forecast."
    )
else:
    st.caption(
        "Prototype mode currently uses simulated Irish grid data."
    )


st.caption(
    f"Active data source: **{source_label}**"
)

st.divider()


# -------------------------------------------------------------------
# Workload form
# -------------------------------------------------------------------

st.header("Configure your AI workload")


with st.form("workload_form"):
    workload_name = st.text_input(
        "Workload name",
        value="Generate product embeddings",
    )

    col1, col2, col3 = st.columns(3)

    with col1:
        duration_hours = st.number_input(
            "Workload duration (hours)",
            min_value=0.25,
            max_value=24.0,
            value=3.0,
            step=0.25,
        )

    with col2:
        deadline_hours = st.number_input(
            "Must finish within (hours)",
            min_value=0.25,
            max_value=48.0,
            value=18.0,
            step=0.25,
        )

    with col3:
        power_watts = st.number_input(
            "Average workload power (watts)",
            min_value=10,
            max_value=5000,
            value=350,
            step=10,
        )

    submitted = st.form_submit_button(
        "Calculate greenest schedule",
        type="primary",
    )


# -------------------------------------------------------------------
# Run scheduler
# -------------------------------------------------------------------

if submitted:
    try:
        result = find_greenest_window(
            forecast=forecast,
            duration_hours=float(duration_hours),
            deadline_hours=float(deadline_hours),
            power_watts=float(power_watts),
        )

        st.session_state.schedule_result = result

        st.session_state.schedule_inputs = {
            "workload_name": (
                workload_name.strip()
                or "Unnamed workload"
            ),
            "deadline_hours": float(deadline_hours),
            "power_watts": float(power_watts),
        }

        st.session_state.data_signature = (
            current_signature
        )

    except ValueError as error:
        st.session_state.schedule_result = None
        st.session_state.schedule_inputs = None
        st.session_state.data_signature = None

        st.error(str(error))


result = st.session_state.schedule_result
saved_inputs = st.session_state.schedule_inputs


# -------------------------------------------------------------------
# Overview
# -------------------------------------------------------------------

st.divider()

st.header("Scheduling overview")

metric1, metric2, metric3 = st.columns(3)


metric1.metric(
    (
        "Replay starting intensity"
        if is_historical_replay
        else "Current grid intensity"
    ),
    f"{current_intensity:.0f} gCO₂/kWh",
)


metric2.metric(
    "Recommended start",
    (
        result.start_time.strftime("%a %H:%M")
        if result
        else "Not calculated"
    ),
)


metric3.metric(
    "Estimated reduction",
    (
        f"{result.reduction_percentage:.1f}%"
        if result
        else "Not calculated"
    ),
)


# -------------------------------------------------------------------
# Forecast chart
# -------------------------------------------------------------------

st.divider()

st.header(
    "Irish grid historical replay"
    if is_historical_replay
    else "48-hour Irish grid forecast"
)


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


if result:
    figure.add_vrect(
        x0=result.start_time,
        x1=result.end_time,
        opacity=0.22,
        line_width=1,
        annotation_text="Recommended window",
        annotation_position="top left",
    )

    selected_window = forecast.loc[
        (
            forecast["timestamp"]
            >= result.start_time
        )
        & (
            forecast["timestamp"]
            < result.end_time
        )
    ]

    figure.add_scatter(
        x=selected_window["timestamp"],
        y=selected_window["carbon_intensity"],
        mode="markers",
        marker={"size": 10},
        name="Scheduled workload",
    )


figure.update_layout(
    xaxis_title="Time in Ireland",
    yaxis_title="Carbon intensity (gCO₂/kWh)",
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
# Results
# -------------------------------------------------------------------

if result and saved_inputs:
    st.divider()

    st.header("Recommended schedule")

    st.success(
        f"Run '{saved_inputs['workload_name']}' from "
        f"{result.start_time.strftime('%A %d %B at %H:%M')} "
        f"until "
        f"{result.end_time.strftime('%A %d %B at %H:%M')}."
    )

    immediate_col, shifted_col = st.columns(2)

    with immediate_col:
        st.subheader("Run immediately")

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

    with shifted_col:
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

    impact1, impact2, impact3 = st.columns(3)

    impact1.metric(
        "Estimated energy",
        f"{result.energy_kwh:.2f} kWh",
    )

    impact2.metric(
        "Estimated CO₂ avoided",
        f"{result.avoided_emissions_g:.1f} gCO₂",
    )

    impact3.metric(
        "Scheduled duration",
        f"{result.duration_hours:g} hours",
    )

    st.subheader("Why this window was selected")

    st.write(
        f"GridShift evaluated every continuous "
        f"{result.duration_hours:g}-hour window before the "
        f"{saved_inputs['deadline_hours']:g}-hour deadline."
    )

    st.write(
        f"The selected window averages "
        f"{result.average_intensity:.1f} gCO₂/kWh, "
        f"compared with "
        f"{result.immediate_average_intensity:.1f} "
        f"gCO₂/kWh when running immediately."
    )

    st.write(
        f"At {saved_inputs['power_watts']:.0f} watts, "
        f"estimated energy use is "
        f"{result.energy_kwh:.2f} kWh."
    )

    if result.avoided_emissions_g > 0:
        st.write(
            f"The estimated saving is "
            f"{result.avoided_emissions_g:.1f} gCO₂ "
            f"({result.reduction_percentage:.1f}%)."
        )

    elif result.avoided_emissions_g == 0:
        st.write(
            "There is no estimated carbon benefit "
            "from delaying this job."
        )

    else:
        st.warning(
            "No cleaner valid window exists before "
            "the chosen deadline."
        )

    st.caption(
        "All energy and emissions figures are estimates "
        "based on the supplied power value and selected "
        "grid dataset."
    )


# -------------------------------------------------------------------
# Data table
# -------------------------------------------------------------------

with st.expander("View grid data"):
    display_data = forecast.copy()

    display_data["timestamp"] = (
        display_data["timestamp"]
        .dt.strftime("%a %d %b %Y, %H:%M")
    )

    column_names = {
        "timestamp": "Time",
        "carbon_intensity": (
            "Carbon intensity (gCO₂/kWh)"
        ),
    }

    if "renewable_percentage" in display_data.columns:
        column_names["renewable_percentage"] = (
            "Estimated renewables (%)"
        )

    display_data = display_data.rename(
        columns=column_names
    )

    st.dataframe(
        display_data,
        width="stretch",
        hide_index=True,
    )
