# Yukti IOCL — 6-Act Executive Demo Practice Playbook (~12 Minutes)

- **Live App:** https://yukti-iocl-u7thdacpua-el.a.run.app
- **Interactive Practice Page:** https://yukti-iocl-u7thdacpua-el.a.run.app/demo
- **Architecture Portal:** https://yukti-iocl-u7thdacpua-el.a.run.app/architecture

> Keep `/demo` open only while rehearsing; during the live executive session, present solely from `/` so the canvas stays 100% authentic and uncluttered.

---

## Act 1 — Statutory Financial Truth (2 min · Persona: `CMD`)
1. **Ask:** *"Show IOCL's Schedule III Profit and Loss statement for FY26."*
   - **Highlight:** Verbatim FY26 Annual Report p.205 lines — Revenue `₹8,86,224.41 Cr`, PBT `₹48,784.41 Cr`, PAT `₹36,802.42 Cr`, EPS `₹26.72`.
2. **Ask:** *"Can I see the income statement for the past 5 years?"*
   - **Highlight:** Indented Schedule III line items as rows × `FY26..FY22` as columns + YoY %.

## Act 2 — Downstream Refineries & Retail Fuel Reality (2 min · Persona: `CMD`)
3. **Ask:** *"Rank all IOCL refineries by GRM ($/bbl) and EBITDA in FY26."*
   - **Highlight:** 9 standalone refineries (`70.25 MMTPA`), led by Panipat, Paradip, and Koyali.
4. **Ask:** *"Can you show me the diesel price in Delhi for the past 10 years?"*
   - **Highlight:** 10-year PPAC/IOCL retail Diesel (HSD) trajectory (`₹54.71/L` → `₹87.67/L`) + Delhi Central Excise & State VAT tax stack.

## Act 3 — 10-Year Annual Report Deep-QA Vector RAG (1.5 min · Persona: `CMD`)
5. **Ask:** *"What were IOCL's contingent liabilities and green hydrogen plans in the FY26 Annual Report?"*
   - **Highlight:** Grounded `[AR FY26 p.NN]` citations pulled live from `8,437` embedded chunks across all 10 Annual Reports (`FY17–FY26`, `3,311` pages) in BigQuery `hrfin_docs.doc_chunks_ar`.

## Act 4 — Flagship DCF Valuation, Live Street Consensus & Excel/Sheets Export (4 min · Persona: `CMD`)
6. **Ask:** *"Run the DCF valuation model for IOCL."* → Confirm (**Proceed** or say *"Run the DCF"*).
   - **Highlight:** Human-in-the-loop confirmation, 6 interactive tabs (`Summary`, `FCFF`, `WACC`, `Bridge`, `Sensitivity`, IOCL OMC `Tornado`), intrinsic value `₹265.26/sh` vs. `₹135.40/sh` market close.
7. **Ask:** *"And what are the analysts saying online?"*
   - **Highlight:** Live Vertex AI **Google Search Grounding** comparing current Street brokerage targets on `NSE:IOC` against our DCF intrinsic value.
8. **Ask:** *"Can you change the WACC to 10.25% instead of 9.25% and run the analysis again?"*
   - **Highlight:** Full 6-tab recomputation (`₹265.26 → ₹218.12/sh`). Then click **Export → Excel (.xlsx) or Google Sheets** to download the 8-sheet live-formula workbook (`Cover`, `Assumptions`, `WACC`, `Historical`, `Forecast`, `Valuation`, `Sensitivity`, `Tornado`, `Sources`).
9. **Ask:** *"Can you tell me the growth rate you have assumed from 2027 onwards in revenue, operating profit, and FCF, and does it match historical trend? Give me a plot."*
   - **Highlight:** Assumed `FY27–FY36` CAGRs (e.g., Revenue `2.00%`) plotted against verified `FY17–FY26` historical trends.
10. **Ask:** *"And now extend this plot to 2036."*
    - **Highlight:** Continuous 20-year `FY17–FY36` trajectory stitching 10 years of verified Annual Report actuals + 10 years of DCF forecast.

## Act 5 — Maharatna MoU Governance & Zero-Leak RBAC (1.5 min · `CMD` → `E1_FIN`)
11. **Ask (`CMD`):** *"How is IOCL tracking against its MoPNG/DPE Maharatna MoU targets?"*
    - **Highlight:** MoPNG/DPE scorecard vs. Excellent targets.
12. **Switch Persona to `Grade A Officer (E1_FIN)` & Ask:** *"Run the DCF valuation model for IOCL."*
    - **Highlight:** Deterministic RBAC refusal with policy citation and safe alternative — proving zero data leakage.

## Act 6 — Bilingual Gemini Live Voice & Architecture Close (1 min · Persona: `CMD`)
13. **Switch back to `CMD` & Speak (Hindi/Hinglish):** *"FY26 mein IndianOil ka net profit aur top 3 refineries kaun si rahi?"*
    - **Close:** Open `/architecture` ("How Yukti works") to highlight Cloud Run IAP, BigQuery SSOT, Firestore, and Vertex AI Gemini.
