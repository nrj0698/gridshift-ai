from __future__ import annotations

import numpy as np
import pandas as pd


DUBLIN_TIMEZONE = "Europe/Dublin"


def generate_demo_forecast(hours: int = 48) -> pd.DataFrame:
    """
    Generate a simulated hourly carbon-intensity forecast.

    This is demo data only. It will later be replaced with real
    Irish electricity-grid data.

    Parameters
    ----------
    hours:
        Number of hourly forecast points to generate.

    Returns
    -------
    pandas.DataFrame
        A table containing timestamps, carbon intensity and an
        estimated renewable-energy percentage.
    """
    if hours < 2:
        raise ValueError("hours must be at least 2")

    start_time = pd.Timestamp.now(
        tz=DUBLIN_TIMEZONE
    ).floor("h")

    timestamps = pd.date_range(
        start=start_time,
        periods=hours,
        freq="h",
    )

    hour_of_day = timestamps.hour.to_numpy()

    # Simulate higher grid demand during morning and evening peaks.
    morning_peak = 35 * np.exp(
        -((hour_of_day - 9) / 2.5) ** 2
    )

    evening_peak = 60 * np.exp(
        -((hour_of_day - 18) / 3.0) ** 2
    )

    # Simulate lower demand overnight.
    overnight_reduction = 45 * np.exp(
        -((hour_of_day - 3) / 3.0) ** 2
    )

    # Simulate changing wind generation over the forecast period.
    wind_effect = 55 * np.sin(
        np.linspace(0, 3 * np.pi, hours) + 0.6
    )

    # Use a fixed seed so the demo does not change randomly
    # every time Streamlit reruns.
    random_generator = np.random.default_rng(seed=42)
    noise = random_generator.normal(
        loc=0,
        scale=9,
        size=hours,
    )

    carbon_intensity = (
        235
        + morning_peak
        + evening_peak
        - overnight_reduction
        - wind_effect
        + noise
    )

    carbon_intensity = np.clip(
        carbon_intensity,
        90,
        420,
    ).round()

    renewable_percentage = np.clip(
        82 - carbon_intensity * 0.18,
        10,
        80,
    ).round()

    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "carbon_intensity": carbon_intensity,
            "renewable_percentage": renewable_percentage,
        }
    )
