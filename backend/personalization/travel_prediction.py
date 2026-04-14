from __future__ import annotations

import os
from collections import Counter
from datetime import date, datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

VALID_PREDICTION_MODES = {"heuristic", "regression"}
DEFAULT_PREDICTION_MODE = "heuristic"
DEFAULT_REGRESSION_SEND_OFFSET_DAYS = 21
DEFAULT_REGRESSION_MIN_HISTORY = 2


def resolve_prediction_mode(mode: str | None = None) -> str:
    raw = (mode or os.environ.get("TRAVEL_PREDICTION_MODE", DEFAULT_PREDICTION_MODE)).strip().lower()
    if raw not in VALID_PREDICTION_MODES:
        return DEFAULT_PREDICTION_MODE
    return raw


def resolve_regression_send_offset_days(send_offset_days: int | None = None) -> int:
    raw = (
        send_offset_days
        if send_offset_days is not None
        else os.environ.get(
            "TRAVEL_REGRESSION_SEND_OFFSET_DAYS",
            DEFAULT_REGRESSION_SEND_OFFSET_DAYS,
        )
    )
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return DEFAULT_REGRESSION_SEND_OFFSET_DAYS


def resolve_regression_min_history(min_history: int | None = None) -> int:
    raw = (
        min_history
        if min_history is not None
        else os.environ.get(
            "TRAVEL_REGRESSION_MIN_HISTORY",
            DEFAULT_REGRESSION_MIN_HISTORY,
        )
    )
    try:
        return max(2, int(raw))
    except (TypeError, ValueError):
        return DEFAULT_REGRESSION_MIN_HISTORY


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
    fallback_reason: str | None = None,
    prediction_source: str,
    regression_r2: float | None = None,
    regression_interval_days: int | None = None,
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
        "fallback_reason": fallback_reason,
        "regression_r2": round(regression_r2, 4) if regression_r2 is not None else None,
        "regression_interval_days": regression_interval_days,
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


def _regression_prediction(
    customer_rows: pd.DataFrame,
    *,
    requested_mode: str,
    today: date,
    send_offset_days: int,
    min_history: int,
) -> tuple[dict[str, Any] | None, str | None]:
    history = (
        customer_rows.sort_values("CHECKIN_DATE")["CHECKIN_DATE"]
        .dropna()
        .dt.normalize()
        .drop_duplicates()
        .tolist()
    )

    if len(history) < min_history:
        return None, "insufficient_history"

    anchor = history[0].date()
    last_trip = history[-1].date()
    if anchor >= last_trip:
        return None, "insufficient_variance"

    x_train = np.arange(len(history), dtype=float)
    y_train = np.array([(value.date() - anchor).days for value in history], dtype=float)
    slope, intercept = np.polyfit(x_train, y_train, 1)
    y_fitted = slope * x_train + intercept
    ss_res = float(np.sum((y_train - y_fitted) ** 2))
    ss_tot = float(np.sum((y_train - y_train.mean()) ** 2))
    regression_r2 = 1.0 if ss_tot == 0 else max(0.0, 1.0 - (ss_res / ss_tot))

    floor_date = max(last_trip, today)
    predicted_checkin: date | None = None
    predicted_interval_days: int | None = None

    max_future_steps = max(len(history) + 6, 8)
    for next_index in range(len(history), len(history) + max_future_steps):
        predicted_offset = float((slope * float(next_index)) + intercept)
        candidate = anchor + timedelta(days=int(round(predicted_offset)))
        if candidate <= floor_date:
            continue
        predicted_checkin = candidate
        predicted_interval_days = (candidate - last_trip).days
        break

    if predicted_checkin is None:
        return None, "predicted_date_not_future"
    if predicted_interval_days is None or predicted_interval_days <= 0:
        return None, "non_positive_interval"

    avg_stay = float(customer_rows["AVG_LENGTH_STAY"].iloc[0] or 1)
    send_date = predicted_checkin - timedelta(days=send_offset_days)

    return (
        _base_payload(
            requested_mode=requested_mode,
            mode_used="regression",
            predicted_checkin_date=predicted_checkin,
            send_date=send_date,
            stay_nights=max(1, int(round(avg_stay))),
            history_points_used=len(history),
            prediction_source="linear_regression_checkin_dates",
            regression_r2=regression_r2,
            regression_interval_days=predicted_interval_days,
        ),
        None,
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

    if requested_mode != "regression":
        return heuristic

    regression_payload, failure_reason = _regression_prediction(
        customer_rows,
        requested_mode=requested_mode,
        today=today_date,
        send_offset_days=resolve_regression_send_offset_days(send_offset_days),
        min_history=resolve_regression_min_history(min_history),
    )
    if regression_payload is not None:
        return regression_payload

    heuristic["prediction_source"] = "seasonality_leadtime_fallback"
    heuristic["fallback_reason"] = failure_reason
    return heuristic
