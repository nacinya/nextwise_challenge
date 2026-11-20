"""NextWise Portfolio Lab: portfolio universe → analysis → editable trade scenarios.

Uses supplied snapshot, instrument, ETF ICB and historical EUR price data. No
broker connection, trade execution, live NextWise catalogue or automatic prices.
"""
from datetime import date
import io

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from universe_builder import render_universe_builder
from portfolio_engine import (
    COLUMNS, HISTORICAL_STOCK_SECTORS, read_uploaded_table,
    standardise_portfolio, blank_portfolio_from_universe,
    combine_universe, apply_trades, metrics, read_lookthrough,
    sector_exposure, risk_from_prices,
)
from bl_comparison import read_model_export, build_comparison

st.set_page_config(
    page_title="NextWise | Portfolio Lab", page_icon="◯",
    layout="wide", initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
:root { color-scheme: light; }
html, body, [data-testid="stApp"], .stApp {
  background-color: #ffffff !important;
  color: #17202c !important;
}
.block-container { max-width: 1180px; padding-top: 2.6rem; padding-bottom: 4rem; }
h1, h2, h3 { color: #111827 !important; letter-spacing: -.025em; }
h1 { font-weight: 650 !important; }
h2 { font-weight: 600 !important; }
p, label { color: #374151; }
[data-testid="stMetric"] {
  padding: 16px 18px; border: 1px solid #e6e9ed; border-radius: 10px;
  background: #fff;
}
[data-testid="stMetricLabel"] { color: #6b7280; }
[data-testid="stMetricValue"] { font-weight: 600; letter-spacing: -.02em; }
[data-testid="stDataFrame"] { border: 1px solid #edf0f2; border-radius: 10px; }
[data-testid="stTabs"] [data-baseweb="tab-list"] { gap: 12px; border-bottom: 1px solid #e5e7eb; }
[data-testid="stTabs"] button[data-baseweb="tab"] { color: #6b7280; }
[data-testid="stButton"] button[kind="primary"],
[data-testid="stFormSubmitButton"] button[kind="primary"] {
  background-color: #162335; border-color: #162335; color: white;
}
[data-testid="stButton"] button, [data-testid="stDownloadButton"] button {
  border-radius: 7px; font-weight: 500;
}
div[data-testid="stAlert"] { border-radius: 8px; }
</style>
""", unsafe_allow_html=True)


def route(page):
    st.session_state["nw_page"] = page
    st.rerun()


def display_money(value):
    return f"€{value:,.2f}"


def display_pct(value):
    return "—" if value is None else f"{value:.2%}"


def display_number(value, decimals=4):
    return "—" if value is None else f"{value:.{decimals}f}"


def page_title(title, subtitle):
    st.title(title)
    st.caption(subtitle)


def show_metric_row(stats):
    p = st.columns(4)
    p[0].metric("Portfolio value", display_money(stats["total"]))
    p[1].metric("Cash balance", display_money(stats["cash"]))
    p[2].metric("Invested positions", str(stats["count"]))
    p[3].metric("HHI · invested only", display_number(stats["hhi"], 5))
    q = st.columns(4)
    q[0].metric("Effective positions", display_number(stats["effective"], 2))
    q[1].metric("Top 5 concentration", display_pct(stats["top5"]))
    q[2].metric("Top 10 concentration", display_pct(stats["top10"]))
    q[3].metric("HHI · including cash", display_number(stats["hhi_cash"], 5))


def simple_bar(positions, total):
    if positions.empty or total <= 0:
        st.info("Add market values to holdings to display the allocation.")
        return
    data = positions.copy().sort_values("Market Value", ascending=True)
    data["Weight"] = data["Market Value"] / total
    fig = px.bar(
        data, x="Weight", y="Asset Name", orientation="h",
        hover_data=["Ticker", "Asset Type"], labels={"Weight": "Portfolio weight", "Asset Name": ""},
        color_discrete_sequence=["#34465d"],
    )
    fig.update_layout(
        template="plotly_white",
        height=max(320, 34 * len(data) + 90),
        margin=dict(l=0, r=10, t=10, b=0),
        font=dict(color="#475569"),
        showlegend=False,
        paper_bgcolor="#ffffff", plot_bgcolor="#ffffff",
        xaxis=dict(tickformat=".0%", gridcolor="#eff1f4", zeroline=False),
        yaxis=dict(showgrid=False, title=""),
    )
    st.plotly_chart(fig, use_container_width=True)


def change_comparison(before, after):
    fields = [
        ("Number of positions", "count", False),
        ("Position HHI (invested)", "hhi", False),
        ("Effective positions", "effective", False),
        ("HHI including cash", "hhi_cash", False),
        ("Top 5 concentration", "top5", True),
        ("Top 10 concentration", "top10", True),
        ("Largest position", "max_weight", True),
        ("Cash", "cash", "money"),
    ]
    out = []
    for label, key, pct in fields:
        a, b = before[key], after[key]
        fmt = (
            (lambda z: display_pct(z)) if pct is True else
            (lambda z: display_money(z)) if pct == "money" else
            (lambda z: str(z)) if key == "count" else
            (lambda z: display_number(z, 5 if "hhi" in key.lower() else 2))
        )
        delta = "—" if a is None or b is None else (
            f"{b - a:+.2%}" if pct is True else
            f"{b - a:+,.2f}" if pct == "money" else
            f"{b - a:+.5f}" if key in ("hhi", "hhi_cash") else
            f"{b - a:+.2f}"
        )
        out.append({"Metric": label, "Current": fmt(a), "Scenario": fmt(b), "Change": delta})
    return pd.DataFrame(out)


def risk_comparison(before, after):
    fields = [
        ("Annualised volatility", "annual_vol", True),
        ("Estimated annual return", "annual_mean", True),
        ("Estimated Sharpe ratio", "sharpe", False),
        ("Diversification ratio", "div_ratio", False),
        ("Historical max drawdown · static weights", "max_drawdown", True),
    ]
    rows = []
    for label, key, percentage in fields:
        a, b = before.get(key), after.get(key)
        fmt = (lambda v: display_pct(v)) if percentage else (lambda v: display_number(v, 3))
        change = "—" if a is None or b is None else f"{(b-a):+.2%}" if percentage else f"{(b-a):+.3f}"
        rows.append({"Metric": label, "Current": fmt(a), "Scenario": fmt(b), "Change": change})
    return pd.DataFrame(rows)


def load_base(selected):
    mode = st.radio(
        "How would you like to enter the current portfolio?",
        ["Upload current portfolio", "Enter allocations manually"],
        horizontal=True, key="nw_input_mode",
        help="Your investment universe determines which assets can be added in the scenario lab. It does not automatically supply holding values.",
    )
    if mode == "Upload current portfolio":
        upload = st.file_uploader(
            "Upload portfolio snapshot (.csv or .xlsx)",
            type=["csv", "xlsx"], key="nw_snapshot",
        )
        st.caption("Required: Asset Name and Market Value. Recommended: Ticker, Asset Type, Sector and ISIN. Cash should be a separate row.")
        if upload is None:
            st.info("Upload the latest holdings snapshot before calculating performance and concentration.")
            return None
        try:
            base = standardise_portfolio(read_uploaded_table(upload))
            if base["Market Value"].sum() <= 0:
                st.error("The uploaded portfolio has no positive value.")
                return None
        except Exception as exc:
            st.error(f"Could not read the portfolio: {exc}")
            return None
    else:
        if not selected:
            st.info("Return to the homepage to select stocks or ETFs.")
            return None
        blank = blank_portfolio_from_universe(selected)
        manual = blank.loc[blank["Asset Type"].ne("Cash")].copy().reset_index(drop=True)
        st.caption("Enter each position's market value in euros. Sector is editable; only ICB sectors should be used for the sector metric.")
        manual["Market Value"] = manual["Market Value"].astype(float)
        signature = "|".join(
            sorted(str(item.get("ISIN") or item.get("Ticker") or item.get("Name")) for item in selected)
        )
        edited = st.data_editor(
            manual, hide_index=True, use_container_width=True, num_rows="fixed",
            disabled=["Asset Name", "Ticker", "ISIN", "Asset Type"],
            column_config={
                "Market Value": st.column_config.NumberColumn("Current market value (€)", format="€%.2f", min_value=0.0),
                "Sector": st.column_config.TextColumn("ICB sector (for stocks)"),
            },
            key=f"nw_manual_{signature}",
        )
        cash = st.number_input(
            "Uninvested cash (€)", min_value=0.0,
            value=0.0, step=500.0, key="nw_manual_cash",
        )
        if edited["Market Value"].isna().any():
            st.error("Please complete all market value entries.")
            return None
        base = standardise_portfolio(pd.concat([
            edited, pd.DataFrame([{
                "Asset Name": "Cash", "Ticker": "", "ISIN": "",
                "Asset Type": "Cash", "Sector": "", "Market Value": cash,
            }]),
        ], ignore_index=True))
        if base["Market Value"].sum() <= 0:
            st.info("Enter at least one holding value or cash balance to start the analysis.")
            return None
    return combine_universe(base, selected)


if "nw_page" not in st.session_state:
    st.session_state["nw_page"] = "home"

selected = list(st.session_state.get("nextwise_selected_universe", {}).values())

if st.session_state["nw_page"] == "home":
    st.markdown("NEXTWISE  /  PORTFOLIO LAB")
    page_title("Your investment universe", "01  /  Select the stocks and ETFs you want to analyse.")
    render_universe_builder()
    selected = list(st.session_state.get("nextwise_selected_universe", {}).values())
    st.divider()
    left, right = st.columns([3, 1])
    left.caption("After selecting instruments, the next page will let you upload your current portfolio or enter positions manually.")
    if right.button("Continue to analysis →", type="primary", use_container_width=True, disabled=not selected):
        route("analysis")
    st.stop()

top_left, top_right = st.columns([4, 1])
top_left.markdown("NEXTWISE  /  PORTFOLIO LAB")
if top_right.button("← Edit universe", use_container_width=True):
    route("home")

page_title("Portfolio analysis", "02  /  Understand concentration, risk and the effect of proposed trades.")
st.caption(f"Selected universe: {len(selected)} instruments. This is a static analysis, not a live trading connection.")

with st.expander("1. Current portfolio inputs", expanded=True):
    snap_date = st.date_input("Snapshot date", value=date.today(), key="nw_asof")
    portfolio = load_base(selected)

if portfolio is None:
    st.stop()

base = metrics(portfolio)
if base["total"] <= 0:
    st.warning("Enter a nonzero portfolio value.")
    st.stop()

overview_tab, sectors_tab, risk_tab, scenario_tab, bl_tab, method_tab = st.tabs([
    "Overview", "Sector allocation", "Risk & performance", "Scenario lab",
    "Black–Litterman", "Methodology",
])

with overview_tab:
    st.subheader("Portfolio at a glance")
    show_metric_row(base)
    st.caption("HHI uses positions as single securities; ETF look-through is not applied to these figures.")
    st.markdown("#### Current position weights")
    simple_bar(base["positions"], base["total"])
    st.markdown("#### Holdings")
    display = portfolio.copy()
    display["Portfolio weight"] = display["Market Value"] / base["total"]
    st.dataframe(
        display.loc[display["Market Value"].gt(0)],
        use_container_width=True, hide_index=True,
        column_config={
            "Market Value": st.column_config.NumberColumn(format="€%.2f"),
            "Portfolio weight": st.column_config.NumberColumn(format="percent"),
        },
    )
    st.download_button(
        "Download current portfolio (CSV)",
        portfolio.to_csv(index=False).encode("utf-8-sig"),
        file_name="nextwise_portfolio_snapshot.csv", mime="text/csv",
    )

with sectors_tab:
    st.subheader("ICB sector allocation")
    st.caption("Direct stock classifications and optionally verified ETF underlying ICB allocations.")
    lookthrough_file = st.file_uploader(
        "Optional: upload ETF ICB look-through (CSV or Excel)",
        type=["csv", "xlsx"], key="nw_lookthrough",
    )
    st.caption("File columns: Ticker, ICB Sector, Weight. Use fractions (0.25) or percentages (25) consistently.")
    lookthrough = None
    if lookthrough_file is not None:
        try:
            lookthrough = read_lookthrough(lookthrough_file)
        except Exception as exc:
            st.error(f"ETF sector breakdown couldn't be read: {exc}")
    try:
        sectors_now, sector_meta = sector_exposure(portfolio, lookthrough)
    except Exception as exc:
        st.error(f"Sector calculation couldn't be completed: {exc}")
        sectors_now, sector_meta = pd.DataFrame(), None
    if sector_meta is not None:
        a, b, c = st.columns(3)
        a.metric("ICB sectors represented", str(sector_meta["n_sectors"]))
        b.metric("Direct stock coverage", display_pct(
            sector_meta["classified_direct"] / sector_meta["total_direct"] if sector_meta["total_direct"] else None
        ))
        c.metric("ETF look-through coverage", display_pct(
            sector_meta["classified_etf"] / sector_meta["total_etf"] if sector_meta["total_etf"] else None
        ))
        if not sectors_now.empty:
            st.dataframe(
                sectors_now, hide_index=True, use_container_width=True,
                column_config={
                    "Direct stocks (€)": st.column_config.NumberColumn(format="€%.2f"),
                    "ETF look-through (€)": st.column_config.NumberColumn(format="€%.2f"),
                    "Total sector (€)": st.column_config.NumberColumn(format="€%.2f"),
                    "% of portfolio": st.column_config.NumberColumn(format="percent"),
                },
            )
            fig = px.bar(
                sectors_now.sort_values("Total sector (€)", ascending=True),
                x="% of portfolio", y="ICB Sector", orientation="h",
                color_discrete_sequence=["#34465d"],
            )
            fig.update_layout(
                template="plotly_white", height=max(320, len(sectors_now) * 33 + 90),
                margin=dict(l=0, r=10, t=10, b=0),
                xaxis=dict(tickformat=".0%", gridcolor="#eef0f2"),
                yaxis=dict(title=""),
            )
            st.plotly_chart(fig, use_container_width=True)
        if sector_meta["classified_etf"] + 0.01 < sector_meta["total_etf"]:
            st.warning("ETF exposure is incomplete. Do not interpret this as the official NextWise number of ICB sectors.")

with risk_tab:
    st.subheader("Risk and performance")
    st.caption(
        "Historical estimates require **EUR-denominated daily closing prices**, adjusted for relevant corporate actions. "
        "This prototype assumes constant portfolio weights; it does not reconstruct actual trades."
    )
    prices_file = st.file_uploader(
        "Upload historical daily prices (CSV or Excel)",
        type=["csv", "xlsx"], key="nw_prices",
    )
    rf = st.number_input("Assumed annual risk-free rate (%)", min_value=-5.0, max_value=20.0,
                         value=2.0, step=0.25, key="nw_rf") / 100.0
    st.caption("Historical price file: Date, then one column per holding ticker. All prices must share the same EUR currency basis.")
    historic_prices = None
    risk_now = None
    if prices_file is not None:
        try:
            historic_prices = read_uploaded_table(prices_file)
            risk_now = risk_from_prices(portfolio, historic_prices, annual_rf=rf, asof=snap_date)
        except Exception as exc:
            st.warning(f"Risk estimate unavailable: {exc}")
    if risk_now is not None:
        k = st.columns(4)
        k[0].metric("Volatility · annualised", display_pct(risk_now["annual_vol"]))
        k[1].metric("Estimated Sharpe ratio", display_number(risk_now["sharpe"], 2))
        k[2].metric("Diversification ratio", display_number(risk_now["div_ratio"], 2))
        k[3].metric("Max drawdown · backtest", display_pct(risk_now["max_drawdown"]))
        st.caption(
            f"{risk_now['history_days']} overlapping daily returns. "
            "Not the competition's official 180-week ex-ante calculation. "
            "Historical return and Sharpe are estimates, not realized NextWise P&L."
        )
        fig = px.line(
            x=risk_now["drawdown"].index, y=risk_now["drawdown"].values,
            labels={"x": "Date", "y": "Drawdown"}, title="Historical drawdown (constant weights)",
        )
        fig.update_layout(template="plotly_white", title_font_size=16)
        fig.update_traces(line_color="#34465d")
        fig.update_yaxes(tickformat=".0%")
        st.plotly_chart(fig, use_container_width=True)
        st.markdown("#### Correlations between invested positions")
        corr = risk_now["correlation"]
        fig_corr = px.imshow(corr, color_continuous_scale="RdBu", zmin=-1, zmax=1, aspect="auto")
        fig_corr.update_layout(template="plotly_white", height=max(390, len(corr) * 24), margin=dict(l=0, r=0, t=20, b=0))
        st.plotly_chart(fig_corr, use_container_width=True)
        st.markdown("#### Contribution to annualised volatility")
        st.dataframe(risk_now["contribution"], hide_index=True, use_container_width=True,
                     column_config={
                         "Annual risk contribution": st.column_config.NumberColumn(format="percent"),
                         "Portfolio weight": st.column_config.NumberColumn(format="percent"),
                     })
    else:
        st.info("Upload historical daily prices to calculate volatility, Sharpe ratio, diversification ratio, correlations and historical drawdown.")
    st.markdown("#### Indicative UCITS 5/10/40 concentration screen")
    a, b, c = st.columns(3)
    a.metric("Largest position", display_pct(base["max_weight"]))
    b.metric("Sum of positions above 5%", display_pct(base["big_sum"]))
    c.metric("Position-level screen", "Pass" if base["ucits_screen"] else "Review")
    st.caption("Only an indicative position-level check; the official classification, ETF treatment, UCITS applicability and other fund rules require separate verification.")
    st.markdown("#### Actual NextWise gross performance")
    st.info("Not available from a single holdings snapshot. We need dated portfolio NAV / cash-flow records to calculate actual competition performance reliably.")

with scenario_tab:
    st.subheader("Test purchases, sales and removals")
    st.caption(
        "Enter signed euro amounts below. Positive = buy; negative = sell. "
        "Buy orders use existing cash plus proceeds from sales. Total portfolio value is conserved."
    )
    candidates = portfolio.loc[portfolio["Asset Type"].ne("Cash")].reset_index(drop=True).copy()
    editor = pd.DataFrame({
        "Asset Name": candidates["Asset Name"],
        "Ticker": candidates["Ticker"],
        "Asset Type": candidates["Asset Type"],
        "ICB Sector": candidates["Sector"],
        "Current (€)": candidates["Market Value"],
        "Trade (€)": np.zeros(len(candidates), dtype=float),
    })
    edits = st.data_editor(
        editor, key="nw_scenario_editor", hide_index=True, use_container_width=True,
        num_rows="fixed", disabled=["Asset Name", "Ticker", "Asset Type", "ICB Sector", "Current (€)"],
        column_config={
            "Current (€)": st.column_config.NumberColumn(format="€%.2f"),
            "Trade (€)": st.column_config.NumberColumn(help="Positive = buy / negative = sell.", format="€%.2f"),
        },
    )
    signed = pd.to_numeric(edits["Trade (€)"], errors="coerce")
    if signed.isna().any():
        st.error("All trade amounts must be valid euro numbers.")
    else:
        all_trades = []
        iter_trades = iter(signed.to_list())
        for _, item in portfolio.iterrows():
            all_trades.append(0.0 if item["Asset Type"] == "Cash" else float(next(iter_trades)))
        try:
            proposed = apply_trades(portfolio, all_trades)
        except Exception as exc:
            st.warning(f"Scenario cannot be applied: {exc}")
        else:
            after = metrics(proposed)
            st.markdown("#### Before and after")
            st.dataframe(change_comparison(base, after), hide_index=True, use_container_width=True)
            u1, u2 = st.columns(2)
            u1.metric("Current cash", display_money(base["cash"]))
            u2.metric("Cash after proposed trades", display_money(after["cash"]))
            has_trade = bool((signed.abs() > 1e-8).any())
            if not has_trade:
                st.caption("Set at least one trade to compare alternative allocations.")
            old_sector, old_cov = sector_exposure(portfolio, lookthrough)
            new_sector, new_cov = sector_exposure(proposed, lookthrough)
            st.markdown("#### Sector allocation change (partial if ETF look-through is missing)")
            a = old_sector.set_index("ICB Sector")["% of portfolio"].rename("Current")
            b = new_sector.set_index("ICB Sector")["% of portfolio"].rename("Scenario")
            changes = pd.concat([a, b], axis=1).fillna(0.0)
            changes["Change"] = changes["Scenario"] - changes["Current"]
            st.dataframe(changes.reset_index(), hide_index=True, use_container_width=True,
                         column_config={name: st.column_config.NumberColumn(format="percent") for name in ["Current", "Scenario", "Change"]})
            st.caption(
                f"ICB sectors: {old_cov['n_sectors']} → {new_cov['n_sectors']}. "
                "This can miss ETF indirect exposures until look-through data is provided."
            )
            st.markdown("#### UCITS screen")
            st.write(
                f"Current: **{'Pass' if base['ucits_screen'] else 'Review'}** · "
                f"Scenario: **{'Pass' if after['ucits_screen'] else 'Review'}**"
            )
            if historic_prices is not None:
                try:
                    riska = risk_now or risk_from_prices(portfolio, historic_prices, annual_rf=rf, asof=snap_date)
                    riskb = risk_from_prices(proposed, historic_prices, annual_rf=rf, asof=snap_date)
                    st.markdown("#### Historical risk estimates — before and after")
                    st.dataframe(risk_comparison(riska, riskb), hide_index=True, use_container_width=True)
                except Exception as exc:
                    st.info("Scenario risk comparison is incomplete: " + str(exc))
            st.download_button(
                "Download proposed portfolio (CSV)",
                proposed.to_csv(index=False).encode("utf-8-sig"),
                file_name="nextwise_proposed_portfolio.csv", mime="text/csv",
            )

with bl_tab:
    st.subheader("Compare with the existing Black–Litterman × HRP model")
    st.caption(
        "Your supplied model exports **Poids BL-HRP (%)** as target weights. "
        "Import that output; this app does not silently rerun the model on a different universe."
    )
    bl_file = st.file_uploader("Upload bl_hrp_allocation.csv", type=["csv"], key="nw_bl_export")
    if bl_file is not None:
        try:
            bl_weights = read_model_export(bl_file)
            result, info = build_comparison(portfolio.loc[portfolio["Market Value"].gt(0)], bl_weights)
        except Exception as exc:
            st.error(f"Black–Litterman comparison unavailable: {exc}")
        else:
            a, b, c = st.columns(3)
            a.metric("Matching model assets", str(info["matched_assets"]))
            b.metric("Current portfolio matched", display_pct(info["matched_current_weight"]))
            c.metric("BL–HRP target HHI", display_number(info["target_hhi"], 5))
            st.warning(
                "The model has a separate investment universe and model date. "
                "Model-only assets are not automatically eligible for NextWise, "
                "and its equal-weight benchmark is not your actual portfolio."
            )
            st.dataframe(result, hide_index=True, use_container_width=True, column_config={
                "Current weight": st.column_config.NumberColumn(format="percent"),
                "BL-HRP target weight": st.column_config.NumberColumn(format="percent"),
                "Difference": st.column_config.NumberColumn(format="percent"),
            })
            st.download_button(
                "Download BL–HRP comparison (CSV)", result.to_csv(index=False).encode("utf-8-sig"),
                file_name="nextwise_bl_hrp_comparison.csv", mime="text/csv",
            )
    else:
        st.info(
            "Run the original BL × HRP app → Paramètres → Allocation Complète (Export) "
            "→ Télécharger CSV, then upload that CSV here."
        )

with method_tab:
    st.subheader("Methodology and coverage")
    st.markdown("""
**Portfolio concentration** — HHI is the sum of squared weights. We show both the
invested-only version and the version that includes cash. The reciprocal of the
invested-only HHI is the effective number of equally weighted positions.

**Sector allocation** — Direct stocks are classified using the supplied ICB
sector labels. ETFs are only included when you upload an underlying ICB
look-through file, because an ETF is not equivalent to a single ICB sector.
Unclassified holdings reduce sector coverage.

**Historical risk** — If you upload sufficient daily EUR price observations,
we estimate annualised volatility, annualised Sharpe, diversification ratio,
correlations and drawdown for a **constant-weight historical strategy**.
This is not the realized return of your changing NextWise portfolio nor
NextWise's specified 180-week ex-ante volatility estimator.

**UCITS screen** — A preliminary security-level check for a 10% maximum position
and a 40% maximum aggregate weight of positions above 5%. It is not a legal
UCITS compliance certificate or a replica of the competition's assessment.

**Black–Litterman** — Imports the recommendation from the original
Black–Litterman × HRP model you supplied. Its asset universe, historical
window and assumptions are not replaced with fictional data.

**Scenario mechanics** — Buy/sell changes are financed by available cash and
sales, with no borrowing, execution costs or market-price slippage. This
model is useful for comparing allocations but does not predict next-day
stock returns.

**Not yet available** — Actual gross competition return, official
ETF look-through HHI, exact NextWise leaderboard score, transaction-cost-aware
rebalance and automatically verified NextWise tradeable assets.
""")
    st.markdown(
        "NextWise methodology: [Official competition rules]"
        "(https://www.nextwise.fr/en/le-reglement)"
    )
