"""Minimal smoke tests for both Streamlit navigation stages."""
from streamlit.testing.v1 import AppTest


def test_universe_home_renders_without_importing_portfolio():
    at = AppTest.from_file("app.py", default_timeout=30).run()
    assert len(at.exception) == 0, [x.message for x in at.exception]
    assert any("Your investment universe" in x.value for x in at.title)


def test_analysis_manual_mode_renders():
    at = AppTest.from_file("app.py", default_timeout=30)
    at.session_state["nw_page"] = "analysis"
    at.session_state["nextwise_selected_universe"] = {
        "Stock:AAA:companya": {
            "Name": "Company A", "Ticker": "AAA", "ISIN": "",
            "Type": "Stock", "Exchange": "", "Source": "User confirmed",
        }
    }
    at.run()
    assert len(at.exception) == 0, [x.message for x in at.exception]
    assert any("Portfolio analysis" in x.value for x in at.title)
