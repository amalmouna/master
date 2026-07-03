"""Conversion DataFrame -> liste de dicts JSON-compatibles (NaN -> None, types
numpy -> types Python natifs), requise avant tout envoi à PostgREST."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd


def _json_safe_value(v):
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, np.floating):
        return None if np.isnan(v) else float(v)
    if isinstance(v, np.bool_):
        return bool(v)
    if isinstance(v, pd.Timestamp):
        return v.isoformat()
    return v


def records_json_safe(df: pd.DataFrame) -> list[dict]:
    records = df.to_dict(orient="records")
    return [{k: _json_safe_value(v) for k, v in row.items()} for row in records]
