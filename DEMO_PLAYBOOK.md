# Yukti IOCL — 6-Act Executive Demo Practice Playbook (~12 Minutes)

- **Live App:** https://yukti-iocl-u7thdacpua-el.a.run.app
- **Interactive Practice Page:** https://yukti-iocl-u7thdacpua-el.a.run.app/demo
- **Architecture Portal:** https://yukti-iocl-u7thdacpua-el.a.run.app/architecture

> Keep `/demo` open only while rehearsing; during the live executive session, present solely from `/` so the canvas stays 100% authentic and uncluttered.

---

## Act 1 — Statutory Financial Truth: Schedule III P&L & 5-Year Cash Flow (2.5 min · Persona: `CMD`)
1. **Ask:** *"Show IOCL's Schedule III Profit and Loss statement for FY26."*
   - **Highlight:** Verbatim FY26 Annual Report p.205 lines — Gross Revenue `₹8,86,224.41 Cr`, Total Income `₹8,91,212.72 Cr` (cleanly anchoring the `Income` section), PBT `₹48,784.41 Cr`, PAT `₹36,802.42 Cr`, EPS `₹26.72`.
2. **Ask:** *"Can I see the Cash Flow statement for the past 5 years?"*
   - **Highlight:** Indented Ind-AS 7 Cash Flow line items as rows × `FY26..FY22` as columns + **Free Cash Flow (FY26) = `+₹44,977 Cr`** (`OCF ₹71,399 Cr` less `Capex ₹26,421 Cr`), setting up the valuation transition.

## Act 2 — Live Yahoo Finance Stock Price → Live-Priced DCF Valuation & Formula Export (4.5 min · Persona: `CMD`)
3. **Ask:** *"Can I see IOCL's stock price movement for the past 5 years?"*
   - **Narrate & Highlight:** Mention that Yukti is connected to **live market data via the Yahoo Finance API (`IOC.NS`, Brent `BZ=F`, USD/INR `INR=X`)**. Point to today's live `NSE:IOC` share price KPI tile (`~₹150.50/sh`) and the 5-year daily close trajectory.
4. **Ask:** *"Run the DCF valuation model for IOCL on the live market price and tell me if it is undervalued or overvalued."* → Say ***"Please go ahead."*** (or click **Proceed**).
   - **Highlight:** Human-in-the-loop confirmation card pre-populated with the exact **live Yahoo Finance `NSE:IOC` price**, 6 interactive tabs (`Summary`, `FCFF`, `WACC`, `Bridge`, `Sensitivity`, IOCL OMC `Tornado`), intrinsic value `₹265.26/sh` vs. live `NSE:IOC` market price.
5. **Ask:** *"And what are the analysts saying online?"*
   - **Highlight:** Live Vertex AI **Google Search Grounding** comparing current Street brokerage targets on `NSE:IOC` against our DCF intrinsic value and live share price.
6. **Ask:** *"Can you change the WACC to 10.25% instead of 9.25% and run the analysis again?"*
   - **Highlight:** Full 6-tab recomputation (`₹265.26 → ₹218.12/sh`). Then click **Export → Excel (.xlsx)** (9-sheet IB-formatted live-formula workbook: `Cover`, `Assumptions`, `WACC`, `Historical`, `Forecast`, `Valuation`, `Sensitivity`, `Tornado`, `Sources`) or **Google Sheets** (1-click cloud spreadsheet).
7. **Ask:** *"Can you tell me the growth rate you have assumed from 2027 onwards in revenue, operating profit, and FCF, and does it match historical trend? Give me a plot."* → Follow up: *"And now extend this plot to 2036."*
   - **Highlight:** Assumed `FY27–FY36` CAGRs vs. verified `FY17–FY26` historical trends, then continuous 20-year `FY17–FY36` trajectory stitching actuals + forecast.

## Act 3 — Downstream Refineries, Retail Fuel Build-Up & Brent Correlation (2.5 min · Persona: `CMD`)
8. **Ask:** *"Rank all IOCL refineries by GRM ($/bbl) and EBITDA in FY26."*
   - **Highlight:** 9 standalone refineries (`70.25 MMTPA`), led by Panipat, Paradip, and Koyali.
9. **Ask:** *"Can you show me the diesel price in Delhi for the past 10 years?"*
   - **Highlight:** 10-year PPAC/IOCL retail Diesel (HSD) trajectory (`₹54.71/L` → `₹87.67/L`) + Delhi Central Excise & State VAT tax stack.
10. **Ask:** *"Show IOCL's gross revenue for the past 5 years."* → *"Overlay Brent on this chart."* → *"Why did revenue increase in FY26 even when Brent crude fell?"*
    - **Highlight:** Yukti preserves the chart + Brent overlay and explains OMC economics: `+5.0%` marketing volume growth (`105.1 MMT`), steady domestic retail pump prices, and cheaper crude feedstock driving FY26 PAT up `+183.9%` to `₹36,802 Cr`.

## Act 4 — 10-Year Annual Report Deep-QA Vector RAG (1.5 min · Persona: `CMD`)
11. **Ask:** *"What were IOCL's contingent liabilities and green hydrogen plans in the FY26 Annual Report?"*
    - **Highlight:** Grounded `[AR FY26 p.NN]` citations pulled live from `8,437` embedded chunks across all 10 Annual Reports (`FY17–FY26`, `3,311` pages) in BigQuery `hrfin_docs.doc_chunks_ar`.

## Act 5 — Maharatna MoU Governance & Zero-Leak RBAC (1.5 min · `CMD` → `E1_FIN`)
12. **Ask (`CMD`):** *"How is IOCL tracking against its MoPNG/DPE Maharatna MoU targets?"*
    - **Highlight:** MoPNG/DPE scorecard vs. Excellent targets.
13. **Switch Persona to `Grade A Officer (E1_FIN)` & Ask:** *"Run the DCF valuation model for IOCL."*
    - **Highlight:** Deterministic RBAC refusal with policy citation and safe alternative — proving zero data leakage.

## Act 6 — Bilingual Gemini Live Voice & Architecture Close (1 min · Persona: `CMD`)
14. **Switch back to `CMD` & Speak (Hindi/Hinglish):** *"FY26 mein IndianOil ka net profit aur top 3 refineries kaun si rahi?"*
    - **Close:** Open `/architecture` ("How Yukti works") to highlight Cloud Run IAP, BigQuery SSOT, Firestore, and Vertex AI Gemini.
