"""Compare an uploaded portfolio snapshot against the user's BL-HRP CSV export.

This module intentionally does not rerun the model with new dates/assumptions;
it uses the saved target weights from the source Black–Litterman × HRP application.
"""
import re
import unicodedata

import numpy as np
import pandas as pd

TARGET_COL = "Poids BL-HRP (%)"


def _clean_name(value):
    if pd.isna(value):
        return ""
    text = unicodedata.normalize("NFKD", str(value).casefold())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]", "", text)


def _clean_ticker(value):
    if pd.isna(value):
        return ""
    return str(value).strip().upper().replace(" ", "")


def _base_ticker(value):
    return _clean_ticker(value).split(".")[0]


def read_model_export(file):
    """Read 'bl_hrp_allocation.csv' exported by the supplied BL-HRP dashboard."""
    df = pd.read_csv(file, sep=None, engine="python")
    df.columns = [str(col).strip() for col in df.columns]
    needed = ["Ticker", TARGET_COL]
    missing = [col for col in needed if col not in df]
    if missing:
        raise ValueError("This must be the CSV exported by the BL-HRP application, containing " + ", ".join(needed))
    if "Position" not in df.columns:
        df["Position"] = df["Ticker"].fillna("")
    df["Ticker"] = df["Ticker"].fillna("").astype(str).str.strip()
    df["Position"] = df["Position"].fillna("").astype(str).str.strip()
    if df["Ticker"].eq("").any() or df["Ticker"].duplicated().any():
        raise ValueError("BL-HRP CSV has empty or duplicate tickers. Check its source output.")
    values = pd.to_numeric(df[TARGET_COL], errors="coerce")
    if values.isna().any() or (values < -1e-12).any():
        raise ValueError("BL-HRP weights must be numeric and non-negative.")
    # The source app exports percentage points (e.g. 4.2 for 4.2%).
    df["Target Weight"] = values.clip(lower=0).astype(float) / 100.0
    total = float(df["Target Weight"].sum())
    if not np.isfinite(total) or not (0.98 <= total <= 1.02):
        raise ValueError(f"Model target weights add to {total:.2%}, not approximately 100%. Verify the CSV and original model constraints.")
    # Only correct tiny rounding differences introduced by the model's 3 d.p. export.
    if abs(total - 1.0) <= 0.0005:
        df["Target Weight"] /= total
    return df[["Ticker", "Position", "Target Weight"]].copy()


def build_comparison(holdings, model):
    """Outer-join model weights and snapshot weights with conservative matching.

    Match by exact ticker first, then exact normalized name, then a UNIQUE
    exchange-stripped ticker base. Never silently force ambiguous matches.
    """
    df = holdings.copy()
    df["Current Weight"] = df["Market Value"].astype(float) / float(df["Market Value"].sum())
    if "Ticker" not in df:
        df["Ticker"] = ""
    df["Ticker"] = df["Ticker"].fillna("").astype(str)
    df["name_key"] = df["Asset Name"].map(_clean_name)
    df["ticker_key"] = df["Ticker"].map(_clean_ticker)
    df["base_key"] = df["Ticker"].map(_base_ticker)

    target = model.copy()
    target["name_key"] = target["Position"].map(_clean_name)
    target["ticker_key"] = target["Ticker"].map(_clean_ticker)
    target["base_key"] = target["Ticker"].map(_base_ticker)
    used = set()
    rows = []

    def single_unused(where):
        indexes = [i for i in target.index if i not in used and where(i)]
        return indexes[0] if len(indexes) == 1 else None

    for _, row in df.iterrows():
        ticker_key = row["ticker_key"]
        name_key = row["name_key"]
        base_key = row["base_key"]
        idx = None
        method = "No match"
        if ticker_key:
            idx = single_unused(lambda i: target.at[i, "ticker_key"] == ticker_key)
            if idx is not None:
                method = "Exact ticker"
        if idx is None and name_key:
            idx = single_unused(lambda i: target.at[i, "name_key"] == name_key)
            if idx is not None:
                method = "Exact company name"
        if idx is None and base_key:
            # base ticker can only be trusted if unique on BOTH sides
            current_same = int(df["base_key"].eq(base_key).sum())
            target_same = int(target["base_key"].eq(base_key).sum())
            if current_same == 1 and target_same == 1:
                idx = single_unused(lambda i: target.at[i, "base_key"] == base_key)
                if idx is not None:
                    method = "Unique base ticker — verify exchange"
        if idx is None:
            weight = 0.0
            target_position = ""
            target_ticker = ""
            status = "Not in model export"
        else:
            used.add(idx)
            weight = float(target.at[idx, "Target Weight"])
            target_position = str(target.at[idx, "Position"])
            target_ticker = str(target.at[idx, "Ticker"])
            status = "Matched"
        rows.append({
            "Current asset": row["Asset Name"],
            "Current ticker": row["Ticker"],
            "Model position": target_position,
            "Model ticker": target_ticker,
            "Current weight": float(row["Current Weight"]),
            "BL-HRP target weight": weight,
            "Difference": weight - float(row["Current Weight"]),
            "Match status": status,
            "Match method": method,
        })
    for idx in target.index:
        if idx not in used:
            rows.append({
                "Current asset": "",
                "Current ticker": "",
                "Model position": target.at[idx, "Position"],
                "Model ticker": target.at[idx, "Ticker"],
                "Current weight": 0.0,
                "BL-HRP target weight": float(target.at[idx, "Target Weight"]),
                "Difference": float(target.at[idx, "Target Weight"]),
                "Match status": "Model-only; eligibility unverified",
                "Match method": "Not matched",
            })
    out = pd.DataFrame(rows)
    match_weight = float(out.loc[out["Match status"].eq("Matched"), "Current weight"].sum())
    target_hhi = float(np.square(model["Target Weight"].astype(float)).sum())
    return out, {
        "matched_current_weight": match_weight,
        "target_hhi": target_hhi,
        "model_assets": len(model),
        "matched_assets": len(used),
        "unmatched_current": int(out["Match status"].eq("Not in model export").sum()),
        "unmatched_model": int(out["Match status"].eq("Model-only; eligibility unverified").sum()),
    }
