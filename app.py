"""NextWise Portfolio Lab — a first Streamlit prototype.

Use an uploaded portfolio snapshot. No account credentials or live trading.
"""
import io
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="NextWise Portfolio Lab", page_icon="📈", layout="wide")

REQUIRED = ["Asset Name", "Market Value"]


def demo_portfolio():
    """Small fictional demo; not the NextWise team's actual holdings."""
    return pd.DataFrame(
        [
            ["Sample Industrials A", "Stock", "Electronic and Electrical Equipment", 15000],
            ["Sample Industrials B", "Stock", "Aerospace and Defense", 12000],
            ["Sample Technology A", "Stock", "Technology Hardware and Equipment", 11000],
            ["Sample Bank A", "Stock", "Banks", 9500],
            ["Sample Food A", "Stock", "Food Producers", 7500],
            ["Sample Healthcare ETF", "ETF", "ETF — look-through pending", 14000],
            ["Sample Global ETF", "ETF", "ETF — look-through pending", 12500],
            ["Cash", "Cash", "Cash", 18500],
        ],
        columns=["Asset Name", "Asset Type", "Sector", "Market Value"],
    )


def numeric_value(value):
    if pd.isna(value):
        return np.nan
    if isinstance(value, (int, float, np.integer, np.floating)):
        return float(value)
    clean = str(value).strip().replace("€", "").replace("£", "").replace("$", "")
    clean = clean.replace(",", "").replace("\u00a0", "").replace(" ", "")
    if clean.startswith("(") and clean.endswith(")"):
        clean = "-" + clean[1:-1]
    try:
        return float(clean)
    except ValueError:
        return np.nan


def load_data(upload):
    content = io.BytesIO(upload.getvalue())
    if upload.name.lower().endswith(".csv"):
        return pd.read_csv(content)
    return pd.read_excel(content)


def normalize_portfolio(raw):
    aliases = {
        "asset name": "Asset Name",
        "asset": "Asset Name",
        "name": "Asset Name",
        "ticker": "Ticker",
        "asset type": "Asset Type",
        "type": "Asset Type",
        "sector": "Sector",
        "market value": "Market Value",
        "market value (€)": "Market Value",
        "value": "Market Value",
        "quantity": "Quantity",
        "market price": "Market Price",
    }
    df = raw.rename(columns={col: aliases.get(str(col).strip().lower(), str(col).strip()) for col in raw.columns}).copy()
    if "Asset Name" not in df.columns:
        raise ValueError("The file needs an 'Asset Name' column.")
    if "Market Value" not in df.columns:
        if {"Quantity", "Market Price"}.issubset(df.columns):
            df["Market Value"] = df["Quantity"].map(numeric_value) * df["Market Price"].map(numeric_value)
        else:
            raise ValueError("Add 'Market Value', or both 'Quantity' and 'Market Price'.")
    df["Asset Name"] = df["Asset Name"].fillna("").astype(str).str.strip()
    df = df[df["Asset Name"].ne("")].copy()
    df = df[~df["Asset Name"].str.lower().isin(["total", "total portfolio", "holdings subtotal", "invested total"])].copy()
    df["Market Value"] = df["Market Value"].map(numeric_value)
    if df["Market Value"].isna().any():
        raise ValueError("Some market values are missing or cannot be read as numbers.")
    if (df["Market Value"] < 0).any():
        raise ValueError("Negative market values need separate short-position handling; this prototype supports non-negative position values.")
    for col in ["Asset Type", "Sector"]:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("").astype(str).str.strip()
    if df["Market Value"].sum() <= 0:
        raise ValueError("Total portfolio value must be positive.")
    return df.reset_index(drop=True)


st.title("📈 NextWise Portfolio Lab")
st.caption("Portfolio analytics prototype • Upload a dated snapshot and recalculate concentration metrics")
st.sidebar.header("Input data")
portfolio_file = st.sidebar.file_uploader("Portfolio snapshot (CSV or XLSX)", type=["csv", "xlsx"])
snapshot_date = st.sidebar.date_input("Portfolio snapshot date")
st.sidebar.caption("Expected columns: Asset Name, Market Value, Asset Type and Sector. Optional: Quantity and Market Price.")
st.sidebar.info("Uploads are processed within this app session. Do not upload confidential information to a public app without checking your team's policy.")

try:
    holdings = normalize_portfolio(load_data(portfolio_file) if portfolio_file is not None else demo_portfolio())
except Exception as exc:
    st.error(f"Cannot read portfolio: {exc}")
    st.stop()

if portfolio_file is None:
    st.warning("Showing a FICTIONAL DEMO portfolio. Upload your own snapshot for real NextWise results.")
else:
    st.success(f"Loaded {len(holdings)} rows from {portfolio_file.name}.")

cash_mask = holdings["Asset Name"].str.casefold().eq("cash") | holdings["Asset Type"].str.casefold().eq("cash")
cash = float(holdings.loc[cash_mask, "Market Value"].sum())
positions = holdings.loc[~cash_mask].copy()
total = float(holdings["Market Value"].sum())
invested_value = float(positions["Market Value"].sum())
if invested_value <= 0:
    st.error("Add at least one invested position to calculate concentration.")
    st.stop()

positions["Portfolio Weight"] = positions["Market Value"] / total
positions["Invested Weight"] = positions["Market Value"] / invested_value
hhi_invested = float(np.square(positions["Invested Weight"]).sum())
hhi_with_cash = float(np.square(holdings["Market Value"] / total).sum())
effective_positions = 1.0 / hhi_invested
top5 = float(positions["Market Value"].nlargest(5).sum() / total)
top10 = float(positions["Market Value"].nlargest(10).sum() / total)

st.caption(f"Analysis date: {snapshot_date:%d %B %Y} • Snapshot values are static until you upload a new file.")
m1, m2, m3, m4 = st.columns(4)
m1.metric("Portfolio value", f"€{total:,.2f}")
m2.metric("Invested positions", f"{len(positions)}")
m3.metric("Cash", f"€{cash:,.2f}", f"{cash / total:.2%} of portfolio", delta_color="off")
m4.metric("HHI (excluding cash)", f"{hhi_invested:.5f}")
m5, m6, m7, m8 = st.columns(4)
m5.metric("HHI (including cash)", f"{hhi_with_cash:.5f}")
m6.metric("Effective positions", f"{effective_positions:.2f}")
m7.metric("Top 5 concentration", f"{top5:.2%}")
m8.metric("Top 10 concentration", f"{top10:.2%}")

overview, holdings_tab, methodology = st.tabs(["Allocation overview", "Holdings", "Methodology & next steps"])
with overview:
    st.subheader("Position weights — share of total portfolio")
    plot_data = positions.sort_values("Portfolio Weight", ascending=True)
    fig = px.bar(plot_data, x="Portfolio Weight", y="Asset Name", orientation="h", labels={"Portfolio Weight": "Portfolio weight", "Asset Name": ""})
    fig.update_xaxes(tickformat=".1%")
    fig.update_layout(height=max(380, len(positions) * 27 + 100), margin=dict(l=0, r=15, t=10, b=0))
    st.plotly_chart(fig, use_container_width=True)

    stock_only = positions[positions["Asset Type"].str.casefold().eq("stock")]
    st.subheader("Direct stocks by reported sector")
    st.caption("Only directly held stocks appear below. ETF look-through and exact ICB classification checks are NOT yet included.")
    if not stock_only.empty and stock_only["Sector"].ne("").any():
        sector_table = stock_only.groupby("Sector", as_index=False)["Market Value"].sum().sort_values("Market Value", ascending=False)
        sector_table["% of total portfolio"] = sector_table["Market Value"] / total
        st.dataframe(sector_table, use_container_width=True, hide_index=True, column_config={
            "Market Value": st.column_config.NumberColumn("Direct stock exposure (€)", format="€%.2f"),
            "% of total portfolio": st.column_config.NumberColumn("Portfolio weight", format="percent"),
        })
    else:
        st.info("Provide 'Asset Type' = Stock and a 'Sector' column to view direct stock exposure.")

with holdings_tab:
    st.subheader("All invested positions")
    st.dataframe(positions.sort_values("Market Value", ascending=False), use_container_width=True, hide_index=True,
        column_config={
            "Market Value": st.column_config.NumberColumn("Market Value (€)", format="€%.2f"),
            "Portfolio Weight": st.column_config.NumberColumn("Weight of portfolio", format="percent"),
            "Invested Weight": st.column_config.NumberColumn("Weight excluding cash", format="percent"),
        })
    download = holdings.to_csv(index=False).encode("utf-8")
    st.download_button("Download normalized portfolio CSV", download, file_name="nextwise_portfolio_normalized.csv", mime="text/csv")

with methodology:
    st.markdown(
        """
        **V1 calculates:** portfolio weights, concentration (HHI), effective number of positions,
        top 5 and top 10 weights, and a preliminary **direct-stock-only** sector view.

        - **Invested-only HHI:** sum of squared weights after excluding cash.
        - **Including-cash HHI:** sum of squared portfolio weights including cash as one position.
        - **Effective positions:** 1 / invested-only HHI.
        - **Top 5/10:** largest invested positions divided by **total portfolio value** (including cash).
        - **Sector view:** direct holdings only; **not an official NextWise ICB look-through result**.

        **Planned next:** verified ICB sector look-through for ETFs, historical price-based risk
        measures, eligible investment universe upload, Black–Litterman integration and
        scenario comparisons. No live trading or brokerage connection is included.
        """
    )
