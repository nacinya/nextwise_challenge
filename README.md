# NextWise Portfolio Analytics

Streamlit app for analysing dated NextWise portfolio snapshots, and comparing current weights with the **Black–Litterman × HRP** allocation exported by the team's existing model.

## Deploy

- Repository: `nacinya/nextwise_challenge`
- Branch: `main`
- Main file: `app.py`
- Dependencies: `requirements.txt`

Deploy in [Streamlit Community Cloud](https://share.streamlit.io/). If you have the deployment form open already, refresh the page after the files were added.

## Use the app

1. Export a dated portfolio CSV or Excel file from your NextWise holdings. Recommended columns are `Asset Name`, `Ticker`, `Asset Type`, `Sector` and `Market Value`. Cash should be a row with name or type `Cash`. Optionally supply `Quantity` and `Market Price` instead of market value.
2. Upload it in the Streamlit sidebar. The initial portfolio is a **fictional demonstration**, not the real NextWise account.
3. The allocation overview reports portfolio weights, position-level HHI, effective positions, and top-five/ten concentration. Sector analysis currently covers **direct stocks only**.
4. For the Black–Litterman comparison, run the supplied **Black–Litterman × HRP** model using the chosen model parameters and dates, open its **Paramètres → Allocation Complète (Export)** section and download `bl_hrp_allocation.csv`.
5. Upload that CSV to the **Black–Litterman comparison** tab. The upload parser reads the original `Ticker`, `Position`, and `Poids BL-HRP (%)` fields and compares the exported model target weights to the actual portfolio snapshot.

## Important limitations

- The **source Black–Litterman × HRP model is not recomputed here**. For reproducibility, this dashboard uses its exported model weights rather than substituting a new model or new market data.
- The source model's universe is broader than the historical NextWise holdings. The app flags unmatched assets and does not assume any model instrument is eligible for trading in NextWise.
- The source model's **"Équipondéré (Avant)"** means an equal-weight reference benchmark — it is **not** the team's actual historical portfolio.
- Position-level HHI treats ETFs as one instrument; full ICB look-through and official NextWise rule checks are pending.
- Do not upload private account credentials or sensitive portfolio files to a public application.

The original NextWise portfolio optimisation notebook in this repository is preserved.
