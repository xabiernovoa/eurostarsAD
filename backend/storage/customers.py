from __future__ import annotations

from pathlib import Path

import pandas as pd

from backend.paths import CUSTOMERS_PATH


def load_customers_df(path: str | Path | None = None) -> pd.DataFrame:
    path = Path(path or CUSTOMERS_PATH)
    df = pd.read_csv(path, sep=";", dtype={"GUEST_ID": str, "HOTEL_ID": str})
    if "GUEST_ID" in df.columns:
        df["GUEST_ID"] = df["GUEST_ID"].astype(str).str.strip().str.strip('"')
    if "HOTEL_ID" in df.columns:
        df["HOTEL_ID"] = df["HOTEL_ID"].astype(str).str.strip().str.strip('"')
    if "CHECKIN_DATE" in df.columns:
        df["CHECKIN_DATE"] = pd.to_datetime(df["CHECKIN_DATE"])
    if "CHECKOUT_DATE" in df.columns:
        df["CHECKOUT_DATE"] = pd.to_datetime(df["CHECKOUT_DATE"])
    return df
