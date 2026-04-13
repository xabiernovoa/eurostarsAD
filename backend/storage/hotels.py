from __future__ import annotations

from pathlib import Path

import pandas as pd

from backend.paths import HOTELS_PATH


def load_hotels_df(path: str | Path | None = None) -> pd.DataFrame:
    path = Path(path or HOTELS_PATH)
    df = pd.read_csv(path, sep=";", dtype={"ID": str})
    if "ID" in df.columns:
        df["ID"] = df["ID"].astype(str).str.strip().str.strip('"')
    return df
