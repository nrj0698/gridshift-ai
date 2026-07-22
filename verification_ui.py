from __future__ import annotations

import pandas as pd

from database import JobRecord
from verification import VerificationResult


def build_verification_chart_data(
    actual_data: pd.DataFrame,
    job: JobRecord,
) -> pd.DataFrame:
    """
    Prepare actual-intensity data for the verification chart.

    Records are labelled according to whether they belong to the
    baseline window, scheduled window, both windows or surrounding
    context.
    """
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

    data = actual_data.copy()

    data["timestamp"] = pd.to_datetime(
        data["timestamp"],
        errors="coerce",
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

    data = (
        data
        .sort_values("timestamp")
        .reset_index(drop=True)
    )

    baseline_start = job.earliest_start

    baseline_end = (
        baseline_start
        + pd.Timedelta(
            hours=job.duration_hours
        )
    )

    comparison_start = min(
        baseline_start,
        job.recommended_start,
    )

    comparison_end = max(
        baseline_end,
        job.recommended_end,
    )

    # Include a small amount of surrounding context.
    if len(data) >= 2:
        interval = (
            data["timestamp"]
            .diff()
            .dropna()
            .median()
        )
    else:
        interval = pd.Timedelta(minutes=30)

    context_start = (
        comparison_start
        - interval
    )

    context_end = (
        comparison_end
        + interval
    )

    data = data.loc[
        (
            data["timestamp"]
            >= context_start
        )
        &
        (
            data["timestamp"]
            <= context_end
        )
    ].copy()

    def classify_timestamp(
        timestamp: pd.Timestamp,
    ) -> str:
        in_baseline = (
            baseline_start
            <= timestamp
            < baseline_end
        )

        in_scheduled = (
            job.recommended_start
            <= timestamp
            < job.recommended_end
        )

        if in_baseline and in_scheduled:
            return "Both windows"

        if in_baseline:
            return "Baseline window"

        if in_scheduled:
            return "Scheduled window"

        return "Context"

    data["period"] = (
        data["timestamp"]
        .map(classify_timestamp)
    )

    return data


def build_verification_export(
    *,
    job: JobRecord,
    result: VerificationResult,
    source_label: str,
) -> pd.DataFrame:
    """
    Create a one-row report suitable for CSV download.
    """
    return pd.DataFrame(
        [
            {
                "job_id": job.id,
                "workload_name": job.workload_name,
                "job_status": job.status,
                "forecast_source": job.source_label,
                "actual_source": source_label,
                "scheduled_start": (
                    result.scheduled_start.isoformat()
                ),
                "scheduled_end": (
                    result.scheduled_end.isoformat()
                ),
                "baseline_start": (
                    result.baseline_start.isoformat()
                ),
                "baseline_end": (
                    result.baseline_end.isoformat()
                ),
                "energy_kwh": result.energy_kwh,
                "forecast_average_intensity": (
                    result.forecast_average_intensity
                ),
                "actual_average_intensity": (
                    result.actual_average_intensity
                ),
                "forecast_error": (
                    result.forecast_error
                ),
                "forecast_absolute_error": (
                    result.forecast_absolute_error
                ),
                "forecast_error_percentage": (
                    result.forecast_error_percentage
                ),
                "actual_baseline_average_intensity": (
                    result.actual_baseline_average_intensity
                ),
                "actual_scheduled_emissions_g": (
                    result.actual_scheduled_emissions_g
                ),
                "actual_baseline_emissions_g": (
                    result.actual_baseline_emissions_g
                ),
                "realised_avoided_emissions_g": (
                    result.realised_avoided_emissions_g
                ),
                "realised_reduction_percentage": (
                    result.realised_reduction_percentage
                ),
                "scheduled_point_count": (
                    result.scheduled_point_count
                ),
                "baseline_point_count": (
                    result.baseline_point_count
                ),
            }
        ]
    )


def describe_verification_outcome(
    result: VerificationResult,
) -> tuple[str, str]:
    """
    Return a presentation type and explanation for the result.
    """
    tolerance = 1e-9

    if (
        result.realised_avoided_emissions_g
        > tolerance
    ):
        return (
            "success",
            (
                "The scheduled window was cleaner than the "
                "baseline window. GridShift produced a realised "
                f"reduction of "
                f"{result.realised_reduction_percentage:.1f}%."
            ),
        )

    if abs(
        result.realised_avoided_emissions_g
    ) <= tolerance:
        return (
            "neutral",
            (
                "The scheduled and baseline windows produced "
                "approximately the same estimated emissions."
            ),
        )

    return (
        "warning",
        (
            "The scheduled window was more carbon intensive than "
            "the baseline window when measured against actual "
            "grid data."
        ),
    )
