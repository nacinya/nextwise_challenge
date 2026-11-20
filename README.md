# NextWise Portfolio Lab

A minimalist, white Streamlit app for building a NextWise-eligible **investment universe**, analysing a dated portfolio and comparing cash-funded trade scenarios against the current portfolio and the team's existing Black–Litterman × HRP allocations.

## Deployment

- Repo: \`nacinya/nextwise_challenge\`
- Branch: \`main\`
- Main file: \`app.py\`
- Theme: \`.streamlit/config.toml\`
- Site: Streamlit Community Cloud

Existing portfolio optimisation notebooks have been preserved.

## Page 1 — Investment universe

1. Use the **Stocks / ETFs** dropdown and ticker, name or ISIN search.
2. Search historical holdings (labelled as examples, not proof of current eligibility), upload an available-instruments CSV, or manually add an asset verified on NextWise.
3. Add your selected instruments to the universe and **Download investment universe** to save it.
4. Restore the exported CSV in a later session; the parser supports UTF-8 BOM as used by the app's own exports.
5. Click **Continue to analysis →** when at least one instrument has been selected.

Universe inputs aren't persisted to a shared database yet. Download the CSV before closing your browser session.

## Page 2 — Portfolio analysis

**1. Current portfolio inputs:** Upload a dated holdings snapshot (.csv/.xlsx), or manually enter EUR market values for instruments in the selected universe and the cash balance. The selected universe is a candidate pool, not proof of what the account holds.

**2. Overview:** Total portfolio value, cash, number of lines, position-level HHI including/excluding cash, effective number of positions, top-five/top-ten concentration, weight chart, holdings table.

**3. Sector allocation:** ICB sector labels for direct stocks. Optionally upload a separate ETF **ICB sector look-through** file with columns \`Ticker,ICB Sector,Weight\`; weights may be 0–1 fractions or 0–100 percentages. Incomplete coverage is flagged. A GICS broad sector breakdown must not be inserted as though it were ICB.

**4. Risk and performance:** Optionally upload EUR-denominated historical daily adjusted closing prices, with a \`Date\` column and a column per invested asset ticker. With adequate overlapping observations, the app estimates volatility, Sharpe, diversification ratio, correlations, constant-weight historical max drawdown and risk contributions. These aren't the competition's official 180-week ex-ante metric or realized returns of a changing portfolio.

**5. Scenario lab:** Enter signed amounts (\`Trade (€)\`): positive to buy, negative to sell. Can include unowned selected-universe assets. Buys use available cash or proceeds from sales. Scenarios conserve portfolio value and recalculate concentration, sector allocation and indicative UCITS 5/10/40; historical risk metrics are recalculated only if all required price histories are supplied. Download the proposed portfolio CSV.

**6. Black–Litterman:** Run the team's **original** BL × HRP application using its existing assumptions. In **Paramètres → Allocation Complète (Export)** download \`bl_hrp_allocation.csv\`, then upload it to this app. Compare both the *current* and the *proposed* scenario weights against the original \`Poids BL-HRP (%)\` output. Instruments in the model but not in NextWise are not deemed automatically eligible.

## Limitations and verification

- This application doesn't connect to a live NextWise trading catalogue or automatically place orders.
- Scenario changes are hypothetical; no transaction costs, market impact or execution slippage are modelled.
- Position-level HHI is not NextWise's full look-through HHI for ETFs.
- UCITS 5/10/40 is an **indicative position-level screen**, not an official or legal compliance determination.
- Actual gross competition performance requires an account NAV/cash-flow history, not a single snapshot.
- The input price matrix must use a consistent currency and appropriate adjusted prices for a meaningful comparison.
- Uploaded universe / portfolio / model files are session inputs. Do not upload confidential credentials or protected client data.
- For the current competition's rules see [NextWise](https://www.nextwise.fr/en/le-reglement).

## Quality checks

GitHub Actions runs \`python -m py_compile\` on the Python modules and regression tests covering scenario cash reconciliation, HHI, sector look-through, CSV restoration and historical price calculations.

## Local development

\`\`\`bash
pip install -r requirements.txt
streamlit run app.py
\`\`\`
