"""Regression tests for the portfolio and universe engine."""
from io import BytesIO
import math

import numpy as np
import pandas as pd
import pytest

from portfolio_engine import (
    standardise_portfolio, metrics, apply_trades, sector_exposure,
    read_lookthrough, risk_from_prices, combine_universe,
)
from universe_builder import read_catalog_file


class Upload:
    def __init__(self, data: bytes, name: str):
        self.data = data
        self.name = name

    def getvalue(self):
        return self.data


@pytest.fixture
def example():
    return standardise_portfolio(pd.DataFrame([
        {"Asset Name": "Company A", "Ticker": "AAA", "Asset Type": "Stock", "Sector": "Banks", "Market Value": 50},
        {"Asset Name": "Company B", "Ticker": "BBB", "Asset Type": "Stock", "Sector": "Chemicals", "Market Value": 30},
        {"Asset Name": "Cash", "Asset Type": "Cash", "Market Value": 20},
    ]))


def test_baseline_metrics(example):
    x = metrics(example)
    assert x["total"] == 100
    assert x["cash"] == 20
    assert x["count"] == 2
    assert math.isclose(x["hhi"], (50 / 80)**2 + (30 / 80)**2)
    assert math.isclose(x["hhi_cash"], .5**2 + .3**2 + .2**2)
    assert math.isclose(x["top5"], .8)


def test_scenario_cash_conservation(example):
    simulated = apply_trades(example, [10, -15, 0])
    assert math.isclose(simulated["Market Value"].sum(), 100)
    assert dict(zip(simulated["Ticker"], simulated["Market Value"]))["AAA"] == 60
    assert simulated.loc[simulated["Asset Type"].eq("Cash"), "Market Value"].iloc[0] == 25
    assert metrics(simulated)["hhi"] != metrics(example)["hhi"]


def test_cannot_overspend_or_oversell(example):
    with pytest.raises(ValueError, match="Insufficient cash"):
        apply_trades(example, [40, 0, 0])
    with pytest.raises(ValueError, match="Insufficient cash"):
        apply_trades(example, [0, -40, 0])


def test_sector_exposure_and_etf_lookthrough(example):
    extended = pd.concat([example, pd.DataFrame([{
        "Asset Name": "ETF C", "Ticker": "CCC", "ISIN": "",
        "Asset Type": "ETF", "Sector": "", "Market Value": 40,
    }])], ignore_index=True)
    direct, coverage = sector_exposure(extended)
    assert math.isclose(direct["Total sector (€)"].sum(), 80)
    assert coverage["total_etf"] == 40
    assert coverage["classified_etf"] == 0

    file = Upload(b"Ticker,ICB Sector,Weight\nCCC,Banks,0.25\nCCC,Chemicals,0.75\n", "etf.csv")
    look = read_lookthrough(file)
    result, cov = sector_exposure(extended, look)
    assert math.isclose(result["Total sector (€)"].sum(), 120)
    assert math.isclose(cov["classified_etf"], 40)


def test_universe_csv_export_roundtrip_with_utf8_bom():
    # This exact encoding is used by the site's own "Download universe" button.
    selected = pd.DataFrame([{
        "Name": "L'Oréal", "Ticker": "OR", "ISIN": "FR0000120321",
        "Type": "Stock", "Exchange": "XPAR",
        "Source": "Previously selected",
    }])
    encoded = selected.to_csv(index=False).encode("utf-8-sig")
    restored = read_catalog_file(Upload(encoded, "nextwise_selected_universe.csv"))
    assert len(restored) == 1
    assert restored.iloc[0]["Name"] == "L'Oréal"
    assert restored.iloc[0]["Type"] == "Stock"


def test_added_asset_is_scenario_eligible(example):
    additional = [{"Name": "New ETF", "Ticker": "EEE", "ISIN": "",
                   "Type": "ETF", "Exchange": ""}]
    with_new = combine_universe(example, additional)
    assert "EEE" in set(with_new["Ticker"])
    idx = list(with_new["Ticker"]).index("EEE")
    trades = [0] * len(with_new)
    trades[idx] = 10
    assert math.isclose(apply_trades(with_new, trades).loc[idx, "Market Value"], 10)


def test_historical_risk_not_claimed_without_full_prices(example):
    dates = pd.date_range("2026-01-01", periods=100, freq="B")
    a = 100 * np.cumprod(1 + .002 + .01 * np.sin(np.arange(100)))
    b = 100 * np.cumprod(1 + .001 + .01 * np.cos(np.arange(100)))
    prices = pd.DataFrame({"Date": dates, "AAA": a, "BBB": b})
    out = risk_from_prices(example, prices, annual_rf=.02, asof="2026-11-20")
    assert out["history_days"] >= 60
    assert out["annual_vol"] > 0
    assert out["div_ratio"] > 0
    assert out["max_drawdown"] <= 0
    with pytest.raises(ValueError, match="Missing historical price"):
        risk_from_prices(example, prices.drop(columns=["AAA"]), asof="2026-11-20")
