from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd

VALID_PREDICTION_MODES = {"heuristic"}
DEFAULT_PREDICTION_MODE = "heuristic"


def resolve_prediction_mode(mode: str | None = None) -> str:
    return DEFAULT_PREDICTION_MODE


def _as_date(value: datetime | date | None = None) -> date:
    if value is None:
        return datetime.now().date()
    if isinstance(value, datetime):
        return value.date()
    return value


def _next_occurrence(month: int, today: date) -> date:
    year = today.year if month > today.month or (month == today.month and today.day <= 15) else today.year + 1
    return date(year, month, 15)


def _base_payload(
    *,
    requested_mode: str,
    mode_used: str,
    predicted_checkin_date: date,
    send_date: date,
    stay_nights: int,
    history_points_used: int,
    prediction_source: str,
) -> dict[str, Any]:
    return {
        "requested_mode": requested_mode,
        "mode_used": mode_used,
        "prediction_source": prediction_source,
        "predicted_checkin_date": predicted_checkin_date.isoformat(),
        "send_date": send_date.isoformat(),
        "send_offset_days": max(1, (predicted_checkin_date - send_date).days),
        "stay_nights": stay_nights,
        "history_points_used": history_points_used,
    }


def _heuristic_prediction(
    customer_rows: pd.DataFrame,
    *,
    requested_mode: str,
    today: date,
) -> dict[str, Any]:
    months = customer_rows["CHECKIN_DATE"].dt.month.tolist()
    most_common_month = Counter(months).most_common(1)[0][0]

    avg_leadtime = float(customer_rows["AVG_BOOKING_LEADTIME"].iloc[0] or 14)
    avg_stay = float(customer_rows["AVG_LENGTH_STAY"].iloc[0] or 1)

    predicted_checkin = _next_occurrence(most_common_month, today)
    send_date = predicted_checkin - timedelta(days=max(int(round(avg_leadtime)), 14))

    return _base_payload(
        requested_mode=requested_mode,
        mode_used="heuristic",
        predicted_checkin_date=predicted_checkin,
        send_date=send_date,
        stay_nights=max(1, int(round(avg_stay))),
        history_points_used=int(len(customer_rows)),
        prediction_source="seasonality_leadtime",
    )


def predict_next_trip(
    customer_rows: pd.DataFrame,
    *,
    mode: str | None = None,
    send_offset_days: int | None = None,
    min_history: int | None = None,
    today: datetime | date | None = None,
) -> dict[str, Any]:
    requested_mode = resolve_prediction_mode(mode)
    today_date = _as_date(today)
    heuristic = _heuristic_prediction(
        customer_rows,
        requested_mode=requested_mode,
        today=today_date,
    )
    return heuristic
