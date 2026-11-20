"""Pure calculations for NextWise portfolio analysis.

All metrics are educational proxies unless explicitly labelled otherwise.
The competition may apply separate ETF look-through and historical definitions.
"""
from __future__ import annotations

import io
import math
import re

import numpy as np
import pandas as pd


COLUMNS = ["Asset Name", "Ticker", "ISIN", "Asset Type", "Sector", "Market Value"]
TOTAL_NAMES = {"total", "total portfolio", "holdings subtotal", "invested total", "portfolio total"}
BROAD_SECTOR_LABELS = {
    "industrials", "information technology", "materials", "financials",
    "consumer staples", "health care", "healthcare", "energy", "energy services",
    "communication services", "consumer discretionary", "utilities", "real estate",
}
# Existing direct-stock ICB classifications from the historical holdings analysis.
# They are defaults, not live eligibility or re-verified index facts.
HISTORICAL_STOCK_SECTORS = {
    "AI": "Chemicals",
    "ASM": "Technology Hardware and Equipment",
    "ASML": "Technology Hardware and Equipment",
    "BNP": "Banks",
    "AM": "Aerospace and Defense",
    "ERA": "Industrial Metals and Mining",
    "GL9": "Food Producers",
    "LR": "Electronic and Electrical Equipment",
    "LDO": "Aerospace and Defense",
    "NEX": "Electronic and Electrical Equipment",
    "ORA": "Telecommunications Service Providers",
    "PRY": "Electronic and Electrical Equipment",
    "SU": "Electronic and Electrical Equipment",
    "SPIE": "Construction and Materials",
    "TE": "Oil Gas and Coal",
    "HO": "Aerospace and Defense",
}


def parse_eur(value):
    if pd.isna(value) or str(value).strip() == "":
        return np.nan
    if isinstance(value, (float, int, np.integer, np.floating)):
        return float(value)
    text = str(value).replace("\u00a0", "").replace(" ", "")
    text = re.sub(r"[€$£]", "", text)
    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]
    text = text.replace(",", "")
    try:
        return float(text)
    except (TypeError, ValueError):
        return np.nan


def read_uploaded_table(upload):
    raw = io.BytesIO(upload.getvalue())
    if upload.name.lower().endswith(".csv"):
        return pd.read_csv(raw, encoding="utf-8-sig", sep=None, engine="python")
    return pd.read_excel(raw)


def standardise_portfolio(source):
    """Standardize portfolio rows; keep cash as a separate, non-tradable row."""
    data = source.copy()
    aliases = {
        "asset name": "Asset Name", "name": "Asset Name", "instrument": "Asset Name",
        "ticker": "Ticker", "symbol": "Ticker", "isin": "ISIN",
        "asset type": "Asset Type", "type": "Asset Type",
        "sector": "Sector", "icb sector": "Sector",
        "market value": "Market Value", "market value (€)": "Market Value",
        "portfolio value": "Market Value", "value": "Market Value",
        "quantity": "Quantity", "market price": "Market Price",
    }
    data = data.rename(columns={
        col: aliases.get(str(col).lstrip("\ufeff").strip().lower(), str(col).strip())
        for col in data.columns
    })
    if data.columns.duplicated().any():
        raise ValueError("Duplicate columns after normalizing the file headings.")
    if "Asset Name" not in data:
        raise ValueError("Your snapshot needs an Asset Name or Name column.")
    if "Market Value" not in data:
        if "Quantity" in data and "Market Price" in data:
            data["Market Value"] = data["Quantity"].map(parse_eur) * data["Market Price"].map(parse_eur)
        else:
            raise ValueError("Add Market Value, or Quantity and Market Price.")
    data["Asset Name"] = data["Asset Name"].fillna("").astype(str).str.strip()
    data = data.loc[data["Asset Name"].ne("") & ~data["Asset Name"].str.casefold().isin(TOTAL_NAMES)].copy()
    for col in ["Ticker", "ISIN", "Asset Type", "Sector"]:
        if col not in data:
            data[col] = ""
        data[col] = data[col].fillna("").astype(str).str.strip()
    data["Ticker"] = data["Ticker"].str.upper()
    data["ISIN"] = data["ISIN"].str.upper()
    data["Market Value"] = data["Market Value"].map(parse_eur)
    if data["Market Value"].isna().any():
        raise ValueError("At least one non-total row has a missing/invalid market value.")
    if (data["Market Value"] < -1e-8).any():
        raise ValueError("Negative holding market values are not supported; input short/derivative exposures separately.")
    data["Market Value"] = data["Market Value"].clip(lower=0)
    data["Asset Type"] = data["Asset Type"].map(
        lambda val: "Cash" if val.casefold() == "cash" else
        "Stock" if val.casefold() in ("stock", "equity", "shares", "share") else
        "ETF" if val.casefold() == "etf" else
        "ETP" if val.casefold() == "etp" else val
    )
    cash_mask = data["Asset Name"].str.casefold().eq("cash") | data["Asset Type"].eq("Cash")
    data.loc[cash_mask, ["Asset Name", "Ticker", "Asset Type", "Sector"]] = ["Cash", "", "Cash", ""]
    if cash_mask.sum() > 1:
        cash_sum = data.loc[cash_mask, "Market Value"].sum()
        data = data.loc[~cash_mask].copy()
        data = pd.concat([data, pd.DataFrame([{
            "Asset Name": "Cash", "Ticker": "", "ISIN": "", "Asset Type": "Cash",
            "Sector": "", "Market Value": float(cash_sum)
        }])], ignore_index=True)
    if not (data["Asset Type"] == "Cash").any():
        data = pd.concat([data, pd.DataFrame([{
            "Asset Name": "Cash", "Ticker": "", "ISIN": "", "Asset Type": "Cash",
            "Sector": "", "Market Value": 0.0
        }])], ignore_index=True)
    if not data.empty and data["Market Value"].sum() < 0:
        raise ValueError("Portfolio value cannot be negative.")
    return data[COLUMNS].reset_index(drop=True)


def metrics(holdings):
    value = float(holdings["Market Value"].sum())
    cash = float(holdings.loc[holdings["Asset Type"].eq("Cash"), "Market Value"].sum())
    pos = holdings.loc[~holdings["Asset Type"].eq("Cash") & holdings["Market Value"].gt(1e-8)].copy()
    invested = float(pos["Market Value"].sum())
    weights = pos["Market Value"] / value if value > 0 else pd.Series(dtype=float)
    invested_w = pos["Market Value"] / invested if invested > 0 else pd.Series(dtype=float)
    full_weights = holdings["Market Value"] / value if value > 0 else pd.Series(dtype=float)
    hhi = float(np.square(invested_w).sum()) if invested else None
    hhi_all = float(np.square(full_weights).sum()) if value else None
    large = weights[weights > .05 + 1e-12]
    max_weight = float(weights.max()) if len(weights) else 0.0
    big_sum = float(large.sum())
    ucits_position_screen = bool((max_weight <= .10 + 1e-10) and (big_sum <= .40 + 1e-10))
    return {
        "total": value, "invested": invested, "cash": cash,
        "count": len(pos), "stock_count": int(pos["Asset Type"].eq("Stock").sum()),
        "etf_count": int(pos["Asset Type"].eq("ETF").sum()),
        "hhi": hhi, "hhi_cash": hhi_all, "effective": 1 / hhi if hhi else None,
        "top5": float(weights.nlargest(5).sum()),
        "top10": float(weights.nlargest(10).sum()),
        "max_weight": max_weight, "big_sum": big_sum, "big_count": len(large),
        "ucits_screen": ucits_position_screen,
        "positions": pos,
    }


def blank_portfolio_from_universe(selected):
    if not selected:
        return standardise_portfolio(pd.DataFrame([{
            "Asset Name": "Cash", "Asset Type": "Cash", "Market Value": 0.0,
        }]))
    rows = []
    for item in selected:
        ticker = str(item.get("Ticker", "")).strip().upper()
        kind = str(item.get("Type", "Stock")).strip()
        rows.append({
            "Asset Name": str(item.get("Name", "")),
            "Ticker": ticker,
            "ISIN": str(item.get("ISIN", "")),
            "Asset Type": kind,
            "Sector": HISTORICAL_STOCK_SECTORS.get(ticker, "") if kind == "Stock" else "",
            "Market Value": 0.0,
        })
    return standardise_portfolio(pd.DataFrame(rows))


def combine_universe(current, selected):
    """Include zero-value selected assets for scenario trades, conservatively matched."""
    result = standardise_portfolio(current)
    existing_ticker = set(result["Ticker"].str.upper()) - {""}
    existing_isin = set(result["ISIN"].str.upper()) - {""}
    existing_name = set(result["Asset Name"].str.casefold())
    extra = []
    for item in selected:
        name = str(item.get("Name", "")).strip()
        ticker = str(item.get("Ticker", "")).strip().upper()
        isin = str(item.get("ISIN", "")).strip().upper()
        if (isin and isin in existing_isin) or (ticker and ticker in existing_ticker) or name.casefold() in existing_name:
            continue
        extra.append({
            "Asset Name": name, "Ticker": ticker, "ISIN": isin,
            "Asset Type": item.get("Type", ""), "Sector": HISTORICAL_STOCK_SECTORS.get(ticker, "") if item.get("Type") == "Stock" else "",
            "Market Value": 0.0,
        })
        existing_ticker.add(ticker) if ticker else None
        existing_isin.add(isin) if isin else None
        existing_name.add(name.casefold())
    if extra:
        result = pd.concat([result, pd.DataFrame(extra)[COLUMNS]], ignore_index=True)
    return result.reset_index(drop=True)


def apply_trades(holdings, trades):
    """Positive = buy, negative = sell, with EUR cash settlement and no leverage."""
    df = holdings.copy().reset_index(drop=True)
    if len(trades) != len(df):
        raise ValueError("The trade editor has become out of sync; reload the analysis page.")
    trade = pd.to_numeric(pd.Series(trades), errors="coerce")
    if trade.isna().any() or not np.isfinite(trade).all():
        raise ValueError("Every trade must contain a finite euro amount.")
    if np.abs(trade).sum() > 1e12:
        raise ValueError("Scenario trade sizes are outside supported limits.")
    if (trade[df["Asset Type"].eq("Cash").to_numpy()].abs() > 1e-8).any():
        raise ValueError("Cash changes automatically; do not trade the cash row.")
    updated = df["Market Value"].astype(float).to_numpy() + trade.to_numpy()
    cash_idx = df.index[df["Asset Type"].eq("Cash")]
    if len(cash_idx) != 1:
        raise ValueError("Expected exactly one cash row.")
    i = int(cash_idx[0])
    updated[i] -= float(trade.sum())
    if (updated < -1e-7).any():
        raise ValueError("Insufficient cash for purchases or a sale exceeds the owned position value.")
    df["Market Value"] = np.maximum(updated, 0)
    if not math.isclose(float(df["Market Value"].sum()), float(holdings["Market Value"].sum()), abs_tol=.01):
        raise ValueError("Scenario fails the portfolio-value reconciliation.")
    return df


def read_lookthrough(upload):
    """ETF look-through data: Ticker, ICB Sector, Weight (% values or fractions)."""
    raw = read_uploaded_table(upload)
    cols = {str(c).lstrip("\ufeff").strip().casefold(): c for c in raw.columns}
    keys = {"ticker": "Ticker", "icb sector": "ICB Sector", "weight": "Weight"}
    if any(k not in cols for k in keys):
        raise ValueError("ETF look-through needs Ticker, ICB Sector and Weight columns.")
    df = raw[[cols[k] for k in keys]].copy()
    df.columns = list(keys.values())
    df["Ticker"] = df["Ticker"].fillna("").astype(str).str.strip().str.upper()
    df["ICB Sector"] = df["ICB Sector"].fillna("").astype(str).str.strip()
    df["Weight"] = pd.to_numeric(df["Weight"], errors="coerce")
    if (df["Ticker"] == "").any() or (df["ICB Sector"] == "").any() or df["Weight"].isna().any():
        raise ValueError("ETF look-through has incomplete rows.")
    if (df["Weight"] < 0).any():
        raise ValueError("ETF look-through weights must not be negative.")
    # Use one consistent unit for the entire file.
    if (df["Weight"] > 1 + 1e-6).any():
        df["Weight"] /= 100
    if (df["Weight"] > 1).any():
        raise ValueError("ETF look-through weights exceed 100%.")
    if (df.groupby("Ticker")["Weight"].sum() > 1.005).any():
        raise ValueError("ETF look-through weights sum above 100% for at least one ETF.")
    return df


def sector_exposure(holdings, lookthrough=None):
    """Return ICB-labelled exposure and coverage. Never assign an ETF to one broad sector."""
    direct = holdings.loc[
        holdings["Asset Type"].eq("Stock") & holdings["Market Value"].gt(0)
    ].copy()
    direct["Sector"] = direct["Sector"].fillna("").astype(str).str.strip()
    valid = direct["Sector"].ne("") & ~direct["Sector"].str.casefold().isin(BROAD_SECTOR_LABELS)
    direct_valid = direct.loc[valid]
    stocks_by = direct_valid.groupby("Sector")["Market Value"].sum()
    exposed = pd.DataFrame({"ICB Sector": stocks_by.index, "Direct stocks (€)": stocks_by.values})
    etf_rows = []
    covered_etf = 0.0
    etfs = holdings.loc[holdings["Asset Type"].eq("ETF") & holdings["Market Value"].gt(0)]
    if lookthrough is not None and not lookthrough.empty:
        if etfs["Ticker"].eq("").any() or etfs["Ticker"].duplicated().any():
            raise ValueError("Give each ETF a unique ticker before applying ETF look-through data.")
        for _, etf in etfs.iterrows():
            subset = lookthrough[lookthrough["Ticker"].eq(etf["Ticker"])]
            for _, s in subset.iterrows():
                amount = float(etf["Market Value"] * s["Weight"])
                etf_rows.append({"ICB Sector": s["ICB Sector"], "ETF look-through (€)": amount})
                covered_etf += amount
    if etf_rows:
        group = pd.DataFrame(etf_rows).groupby("ICB Sector", as_index=False)["ETF look-through (€)"].sum()
        exposed = exposed.merge(group, how="outer", on="ICB Sector")
    if "ETF look-through (€)" not in exposed:
        exposed["ETF look-through (€)"] = 0.0
    if "Direct stocks (€)" not in exposed:
        exposed["Direct stocks (€)"] = 0.0
    exposed[["Direct stocks (€)", "ETF look-through (€)"]] = exposed[["Direct stocks (€)", "ETF look-through (€)"]].fillna(0.0)
    exposed["Total sector (€)"] = exposed["Direct stocks (€)"] + exposed["ETF look-through (€)"]
    total = float(holdings["Market Value"].sum())
    exposed["% of portfolio"] = exposed["Total sector (€)"] / total if total else 0
    exposed = exposed.sort_values("Total sector (€)", ascending=False).reset_index(drop=True)
    classified_direct = float(direct_valid["Market Value"].sum())
    total_etf = float(etfs["Market Value"].sum())
    return exposed, {
        "n_sectors": len(exposed),
        "classified_direct": classified_direct,
        "total_direct": float(direct["Market Value"].sum()),
        "classified_etf": covered_etf,
        "total_etf": total_etf,
        "classified_pct": (classified_direct + covered_etf) / total if total else 0,
    }


def risk_from_prices(holdings, price_table, annual_rf=0.0, asof=None):
    """Constant-weight historical scenario using EUR-denominated DAILY prices.

    This is a historical proxy, NOT realized competition returns or the official
    NextWise 180-week ex ante estimator.
    """
    data = price_table.copy()
    if "Date" not in data.columns:
        raise ValueError("The historical price CSV needs a Date column and a ticker column for each invested asset.")
    data["Date"] = pd.to_datetime(data["Date"], errors="coerce", utc=True)
    data = data.dropna(subset=["Date"]).sort_values("Date").drop_duplicates(subset=["Date"], keep="last").set_index("Date")
    if asof is not None:
        date = pd.Timestamp(asof)
        if date.tzinfo is None:
            date = date.tz_localize("UTC")
        data = data.loc[data.index <= date]
    if len(data) < 61:
        raise ValueError("Supply at least 61 dated daily price observations (60 daily returns).")
    invested = holdings.loc[
        ~holdings["Asset Type"].eq("Cash") & holdings["Market Value"].gt(1e-8)
    ].copy()
    if invested.empty:
        raise ValueError("No invested assets to estimate risk.")
    tickers = invested["Ticker"].fillna("").astype(str).str.strip().str.upper()
    if tickers.eq("").any() or tickers.duplicated().any():
        raise ValueError("Every invested position needs a unique ticker to match its historical price series.")
    price_cols = {str(col).strip().upper(): col for col in data.columns}
    missing = [t for t in tickers if t not in price_cols]
    if missing:
        raise ValueError("Missing historical price columns for: " + ", ".join(missing[:15]))
    matrix = data[[price_cols[t] for t in tickers]].copy()
    matrix.columns = tickers.tolist()
    matrix = matrix.apply(pd.to_numeric, errors="coerce")
    matrix = matrix.where(matrix > 0)
    returns = matrix.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan).dropna(how="any")
    if len(returns) < 60:
        raise ValueError("Fewer than 60 overlapping daily returns after aligning all invested assets.")
    total = float(holdings["Market Value"].sum())
    if total <= 0:
        raise ValueError("Portfolio must have positive value.")
    weights = invested["Market Value"].to_numpy(dtype=float) / total
    port_returns = pd.Series(returns.to_numpy() @ weights, index=returns.index, name="Portfolio")
    annual_factor = 252
    individual_vols = returns.std(ddof=1).to_numpy() * math.sqrt(annual_factor)
    annual_vol = float(port_returns.std(ddof=1) * math.sqrt(annual_factor))
    annual_mean = float(port_returns.mean() * annual_factor)
    sharpe = (annual_mean - float(annual_rf)) / annual_vol if annual_vol > 0 else None
    diversification_ratio = float(np.dot(weights, individual_vols) / annual_vol) if annual_vol > 0 else None
    cumulative = (1 + port_returns).cumprod()
    drawdown = cumulative / cumulative.cummax() - 1
    covariance = returns.cov().to_numpy(dtype=float) * annual_factor
    marginal = covariance @ weights
    risk_contrib = (weights * marginal / annual_vol) if annual_vol > 0 else np.zeros_like(weights)
    contribution = pd.DataFrame({
        "Ticker": tickers.to_numpy(), "Annual risk contribution": risk_contrib,
        "Portfolio weight": weights,
    })
    return {
        "annual_vol": annual_vol,
        "annual_mean": annual_mean,
        "sharpe": sharpe,
        "div_ratio": diversification_ratio,
        "max_drawdown": float(drawdown.min()),
        "history_days": len(returns),
        "history_years": float((returns.index.max() - returns.index.min()).days / 365.25),
        "returns": port_returns, "drawdown": drawdown,
        "correlation": returns.corr(), "contribution": contribution,
    }
