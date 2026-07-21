from io import BytesIO

import pytest

from data_loader import load_carbon_csv


def csv_bytes(content: str) -> BytesIO:
    return BytesIO(content.encode("utf-8"))


def test_loads_eirgrid_style_csv() -> None:
    source = csv_bytes(
        """EffectiveTime,FieldName,Region,Value
21-Jul-2026 00:00:00,CO2 INTENSITY,ROI,240
21-Jul-2026 00:15:00,CO2 INTENSITY,ROI,220
21-Jul-2026 00:30:00,CO2 INTENSITY,ROI,200
"""
    )

    result = load_carbon_csv(source)

    assert len(result) == 3

    assert list(result.columns) == [
        "timestamp",
        "carbon_intensity",
    ]

    assert result.iloc[0][
        "carbon_intensity"
    ] == pytest.approx(240.0)

    assert str(result["timestamp"].dt.tz) == (
        "Europe/Dublin"
    )


def test_filters_non_carbon_measurements() -> None:
    source = csv_bytes(
        """EffectiveTime,FieldName,Region,Value
21-Jul-2026 00:00:00,SYSTEM DEMAND,ROI,4500
21-Jul-2026 00:00:00,CO2 INTENSITY,ROI,210
21-Jul-2026 00:15:00,SYSTEM DEMAND,ROI,4400
21-Jul-2026 00:15:00,CO2 INTENSITY,ROI,190
"""
    )

    result = load_carbon_csv(source)

    assert result[
        "carbon_intensity"
    ].tolist() == [210.0, 190.0]


def test_prefers_roi_region() -> None:
    source = csv_bytes(
        """EffectiveTime,FieldName,Region,Value
21-Jul-2026 00:00:00,CO2 INTENSITY,ALL,300
21-Jul-2026 00:00:00,CO2 INTENSITY,ROI,210
21-Jul-2026 00:15:00,CO2 INTENSITY,ALL,280
21-Jul-2026 00:15:00,CO2 INTENSITY,ROI,190
"""
    )

    result = load_carbon_csv(source)

    assert result[
        "carbon_intensity"
    ].tolist() == [210.0, 190.0]


def test_rejects_missing_timestamp_column() -> None:
    source = csv_bytes(
        """Something,Value
CO2 INTENSITY,200
CO2 INTENSITY,180
"""
    )

    with pytest.raises(
        ValueError,
        match="timestamp column",
    ):
        load_carbon_csv(source)
