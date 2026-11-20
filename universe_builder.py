"""NextWise investment universe builder.

No direct NextWise account/API integration: search covers the user-imported
instrument catalogue and clearly labelled examples from a historical portfolio.
"""
import io
import re
import pandas as pd
import streamlit as st


COLUMNS = ["Name", "Ticker", "ISIN", "Type", "Exchange", "Source"]

# Previously held on 17 November 2026; these are SEARCH STARTERS, not a live
# list of securities currently tradeable on the NextWise platform.
HISTORICAL_HOLDINGS = [
    ("Air Liquide", "AI", "Stock"),
    ("ASM International", "ASM", "Stock"),
    ("ASML Holding", "ASML", "Stock"),
    ("BNP Paribas", "BNP", "Stock"),
    ("Dassault Aviation", "AM", "Stock"),
    ("Eramet", "ERA", "Stock"),
    ("Glanbia", "GL9", "Stock"),
    ("Legrand", "LR", "Stock"),
    ("Leonardo", "LDO", "Stock"),
    ("Nexans", "NEX", "Stock"),
    ("Orange", "ORA", "Stock"),
    ("Prysmian", "PRY", "Stock"),
    ("Schneider Electric", "SU", "Stock"),
    ("SPIE", "SPIE", "Stock"),
    ("Technip Energies", "TE", "Stock"),
    ("Thales", "HO", "Stock"),
    ("AMPEA USA Value", "USVE", "ETF"),
    ("Franklin Future of Health & Wellness ETF", "FOHW", "ETF"),
    ("iShares Agribusiness", "ISAE", "ETF"),
    ("Invesco Nasdaq Biotech", "SBIO", "ETF"),
    ("L&G Battery Value-Chain", "BATT", "ETF"),
    ("L&G Cyber Security", "ISPY", "ETF"),
    ("MSCI World Health Care", "WHCA", "ETF"),
    ("SPDR MSCI World Consumer Staples", "WCOS", "ETF"),
    ("VanEck Uranium & Nuclear", "NUCL", "ETF"),
]
EXAMPLE_SOURCE = "Previously held (17 Nov snapshot; recheck eligibility)"


def reference_catalog():
    return pd.DataFrame(
        [{"Name": n, "Ticker": t, "ISIN": "", "Type": k, "Exchange": "", "Source": EXAMPLE_SOURCE}
         for n, t, k in HISTORICAL_HOLDINGS],
        columns=COLUMNS,
    )


def normalise_type(value):
    s = str(value or "").strip().casefold()
    if s in {"stock", "stocks", "equity", "equities", "action", "actions", "share", "shares"}:
        return "Stock"
    if s in {"etf", "etfs", "exchange traded fund", "exchange-traded fund"}:
        return "ETF"
    return ""


def instrument_key(item):
    name = re.sub(r"\s+", "", str(item.get("Name", "")).strip().casefold())
    ticker = str(item.get("Ticker", "")).strip().upper()
    isin = str(item.get("ISIN", "")).strip().upper()
    if isin and re.fullmatch(r"[A-Z]{2}[A-Z0-9]{10}", isin):
        return "isin:" + isin
    if ticker:
        return f"{item.get('Type', '')}:{ticker}:{name}"
    return f"{item.get('Type', '')}:{name}"


def read_catalog_file(file, source="Imported catalogue (verify NextWise availability)"):
    """Read a CSV/XLSX with user-supplied stock and ETF candidates."""
    data = io.BytesIO(file.getvalue())
    raw = pd.read_csv(data, sep=None, engine="python") if file.name.lower().endswith(".csv") else pd.read_excel(data)
    aliases = {
        "name": "Name", "asset name": "Name", "instrument": "Name",
        "instrument name": "Name", "nom": "Name", "libellé": "Name",
        "designation": "Name", "désignation": "Name", "security name": "Name",
        "ticker": "Ticker", "symbol": "Ticker", "mnemonic": "Ticker",
        "mnémonique": "Ticker", "code": "Ticker",
        "isin": "ISIN", "code isin": "ISIN",
        "type": "Type", "asset type": "Type", "product type": "Type",
        "instrument type": "Type", "catégorie": "Type", "category": "Type",
        "exchange": "Exchange", "market": "Exchange", "marché": "Exchange",
        "venue": "Exchange", "place": "Exchange",
    }
    rename = {}
    for col in raw.columns:
        normalized = str(col).strip().casefold()
        if normalized in aliases:
            rename[col] = aliases[normalized]
    raw = raw.rename(columns=rename)
    if "Name" not in raw.columns or "Type" not in raw.columns:
        raise ValueError("Your file needs at least Name (or Asset Name) and Type (Stock / ETF).")
    df = pd.DataFrame(index=raw.index)
    for field in COLUMNS[:-1]:
        df[field] = raw[field].fillna("").astype(str).str.strip() if field in raw.columns else ""
    df["Type"] = df["Type"].map(normalise_type)
    invalid = df["Type"].eq("") | df["Name"].eq("")
    if invalid.any():
        raise ValueError(f"{int(invalid.sum())} rows are missing an instrument name or contain a type other than Stock/ETF.")
    df["Ticker"] = df["Ticker"].str.upper()
    df["ISIN"] = df["ISIN"].str.upper()
    bad_isin = df["ISIN"].ne("") & ~df["ISIN"].str.fullmatch(r"[A-Z]{2}[A-Z0-9]{10}")
    if bad_isin.any():
        raise ValueError(f"{int(bad_isin.sum())} ISINs do not match the usual 12-character ISIN format.")
    df["Source"] = source
    return df[COLUMNS].drop_duplicates(subset=["Name", "Ticker", "ISIN", "Type"]).reset_index(drop=True)


def add_row(row):
    item = {column: str(row.get(column, "")).strip() for column in COLUMNS}
    if item["Type"] not in ("Stock", "ETF"):
        raise ValueError("Only stocks and ETFs are supported.")
    if not item["Name"]:
        raise ValueError("Enter an instrument name.")
    key = instrument_key(item)
    st.session_state["nextwise_selected_universe"][key] = item


def render_universe_builder():
    st.markdown("## Build your investment universe")
    st.write(
        "Search for stocks and ETFs you want to analyse. Assemble a universe to feed into "
        "the portfolio analytics and Black–Litterman comparison."
    )
    st.info(
        "**Availability:** This is NOT a live NextWise search. Start with previously held "
        "instruments, upload a list from NextWise, or add instruments you've personally "
        "confirmed are available there. The app cannot independently verify tradeability."
    )

    if "nextwise_selected_universe" not in st.session_state:
        st.session_state["nextwise_selected_universe"] = {}

    with st.expander("📂 Import the available NextWise stock / ETF list", expanded=False):
        st.write(
            "If NextWise lets you export its list of available instruments, upload it here. "
            "A CSV or Excel file with **Name** and **Type** (Stock or ETF) is sufficient. "
            "Ticker, ISIN and Exchange are useful optional columns."
        )
        uploaded_catalog = st.file_uploader(
            "Upload NextWise instruments (CSV or Excel)",
            type=["csv", "xlsx"], key="nw_catalog_file",
        )
        template = pd.DataFrame([{
            "Name": "Example Company (replace me)",
            "Ticker": "EXAMPLE",
            "ISIN": "",
            "Type": "Stock",
            "Exchange": "",
        }]).to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download blank-format template",
            data=template, file_name="nextwise_instrument_template.csv",
            mime="text/csv", key="nw_template",
        )
        st.caption(
            "Even a list copied from NextWise should be checked against the live trading "
            "screen before an order. No credentials or account connection are used."
        )

    show_examples = st.checkbox(
        "Include historical holdings as search examples", value=True, key="nw_examples",
        help="These were previously held in the portfolio; this does not confirm current eligibility.",
    )
    frames = [reference_catalog()] if show_examples else []
    if uploaded_catalog is not None:
        try:
            imported = read_catalog_file(uploaded_catalog)
            frames.append(imported)
            st.success(f"Loaded {len(imported)} instruments from your uploaded catalogue.")
        except Exception as exc:
            st.error(f"Catalogue could not be read: {exc}")

    catalogue = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=COLUMNS)
    if not catalogue.empty:
        catalogue["Asset key"] = catalogue.apply(instrument_key, axis=1)
        # An imported record with an ISIN may coexist with a historical ticker-only entry.
        catalogue = catalogue.drop_duplicates(subset=["Asset key"], keep="last").reset_index(drop=True)
    else:
        catalogue["Asset key"] = pd.Series(dtype=str)

    left, right = st.columns([1, 3])
    with left:
        asset_kind = st.selectbox(
            "Instrument type", ["All", "Stocks", "ETFs"], key="nw_type",
            help="Dropdown to filter the universe by stocks or ETFs.",
        )
    with right:
        query = st.text_input(
            "Search name, ticker or ISIN",
            placeholder="Search ASML, agribusiness, ISAE, or an ISIN…",
            key="nw_search",
        )

    matches = catalogue.copy()
    if asset_kind != "All":
        matches = matches[matches["Type"].eq("Stock" if asset_kind == "Stocks" else "ETF")]
    if query.strip():
        query_value = query.casefold().strip()
        matches = matches[
            matches[["Name", "Ticker", "ISIN", "Exchange"]]
            .fillna("").astype(str)
            .apply(lambda row: any(query_value in str(v).casefold() for v in row), axis=1)
        ]
    matches = matches.head(60)
    st.caption(f"{len(matches)} displayed matches · {len(catalogue)} instruments in the searchable list")
    if matches.empty:
        st.info("No matches yet. Import the NextWise catalogue or add a verified stock / ETF below.")
    else:
        st.dataframe(
            matches[COLUMNS], hide_index=True, use_container_width=True,
            height=min(360, 40 + len(matches) * 35),
        )
        options = matches["Asset key"].tolist()
        lookup = matches.set_index("Asset key").to_dict("index")
        chosen = st.multiselect(
            "Choose instruments to add",
            options=options,
            format_func=lambda key: (
                f"{lookup[key]['Name']} · {lookup[key]['Ticker']} "
                f"({lookup[key]['Type']})"
            ),
            key="nw_search_selection",
        )
        if st.button("➕ Add selected to universe", type="primary", disabled=not chosen):
            for key in chosen:
                add_row(lookup[key])
            st.success(f"Added {len(chosen)} selected instruments.")
            st.rerun()

    with st.expander("➕ Add a stock or ETF not in the list", expanded=False):
        with st.form("nw_add_manual", clear_on_submit=True):
            a, b = st.columns(2)
            with a:
                name = st.text_input("Instrument name *")
                ticker = st.text_input("Ticker / symbol")
                isin = st.text_input("ISIN (optional)")
            with b:
                kind = st.selectbox("Instrument type *", ["Stock", "ETF"])
                exchange = st.text_input("Euronext exchange (optional)")
                confirmed = st.checkbox("I checked this instrument on NextWise")
            submitted = st.form_submit_button("Add instrument to universe")
        if submitted:
            if not name.strip():
                st.error("Enter an instrument name.")
            elif not confirmed:
                st.warning("Please confirm this instrument appears in NextWise before marking it as available.")
            elif isin.strip() and not re.fullmatch(r"[A-Za-z]{2}[A-Za-z0-9]{10}", isin.strip()):
                st.error("ISIN must contain 12 characters (two letters followed by ten letters/numbers).")
            elif not (ticker.strip() or isin.strip()):
                st.error("Provide a ticker or ISIN to identify the instrument.")
            else:
                add_row({
                    "Name": name, "Ticker": ticker.upper(), "ISIN": isin.upper(),
                    "Type": kind, "Exchange": exchange,
                    "Source": "Manually entered — user confirmed in NextWise",
                })
                st.success(f"Added {name.strip()}.")
                st.rerun()

    st.divider()
    selected = list(st.session_state["nextwise_selected_universe"].values())
    selected_df = pd.DataFrame(selected, columns=COLUMNS)
    num_stock = int(selected_df["Type"].eq("Stock").sum()) if not selected_df.empty else 0
    num_etf = int(selected_df["Type"].eq("ETF").sum()) if not selected_df.empty else 0
    m1, m2, m3 = st.columns(3)
    m1.metric("Universe instruments", len(selected))
    m2.metric("Stocks", num_stock)
    m3.metric("ETFs", num_etf)
    st.subheader("Your selected investment universe")
    if selected_df.empty:
        st.caption("Your universe is empty. Select instruments above to get started.")
    else:
        st.dataframe(
            selected_df, hide_index=True, use_container_width=True,
            height=min(420, 40 + len(selected_df) * 35),
        )
        remove_labels = {
            instrument_key(row): f"{row['Name']} ({row['Ticker'] or row['ISIN']})"
            for row in selected
        }
        removed = st.multiselect(
            "Select instruments to remove",
            options=list(remove_labels),
            format_func=lambda key: remove_labels[key],
            key="nw_to_remove",
        )
        if st.button("Remove selected", disabled=not removed):
            for key in removed:
                st.session_state["nextwise_selected_universe"].pop(key, None)
            st.rerun()

        st.download_button(
            "⬇ Download investment universe (CSV)",
            selected_df.to_csv(index=False).encode("utf-8-sig"),
            file_name="nextwise_selected_universe.csv", mime="text/csv",
            type="primary", key="nw_download",
        )
    with st.expander("Restore a previously saved universe"):
        saved = st.file_uploader(
            "Upload a previously downloaded universe CSV",
            type=["csv"], key="nw_restore",
        )
        if st.button("Restore instruments from CSV", disabled=saved is None):
            try:
                restored = read_catalog_file(saved, source="Restored saved universe (recheck availability)")
                for item in restored.to_dict("records"):
                    add_row(item)
                st.success(f"Restored {len(restored)} records.")
                st.rerun()
            except Exception as exc:
                st.error(f"Could not restore CSV: {exc}")
    st.caption(
        "Selected instruments are held in your current browser session, not a shared database. "
        "Download the CSV to preserve them or share with the team. "
        "Portfolio analysis and model comparisons remain on the other tabs."
    )
