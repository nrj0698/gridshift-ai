from __future__ import annotations

import argparse
from pathlib import Path

from database import (
    DEFAULT_DATABASE_PATH,
    get_job,
)
from verification import (
    load_actual_carbon_csv,
    verify_job_against_actuals,
)
from verification_database import (
    save_verification,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify a saved GridShift schedule against "
            "actual EirGrid CO₂-intensity data."
        )
    )

    parser.add_argument(
        "--job-id",
        type=int,
        required=True,
    )

    parser.add_argument(
        "--csv",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--source-label",
        default="EirGrid measured CO₂ intensity",
    )

    return parser.parse_args()


def main() -> None:
    arguments = parse_arguments()

    job = get_job(
        arguments.job_id,
        database_path=DEFAULT_DATABASE_PATH,
    )

    if job is None:
        raise SystemExit(
            f"No saved job exists with ID "
            f"{arguments.job_id}."
        )

    actual_data = load_actual_carbon_csv(
        arguments.csv
    )

    result = verify_job_against_actuals(
        job,
        actual_data,
    )

    save_verification(
        result,
        source_label=arguments.source_label,
        database_path=DEFAULT_DATABASE_PATH,
    )

    print()
    print(
        f"Verified job #{result.job_id}"
    )

    print(
        "Forecast average:",
        f"{result.forecast_average_intensity:.1f}",
        "gCO2/kWh",
    )

    print(
        "Actual average:",
        f"{result.actual_average_intensity:.1f}",
        "gCO2/kWh",
    )

    print(
        "Forecast error:",
        f"{result.forecast_error:+.1f}",
        "gCO2/kWh",
    )

    print(
        "Actual baseline average:",
        f"{result.actual_baseline_average_intensity:.1f}",
        "gCO2/kWh",
    )

    print(
        "Realised CO2 avoided:",
        f"{result.realised_avoided_emissions_g:.1f}",
        "gCO2",
    )

    print(
        "Realised reduction:",
        f"{result.realised_reduction_percentage:.1f}%",
    )


if __name__ == "__main__":
    main()
