# Curated 30 IOCL Finance & Downstream Questions + Multi-Turn Follow-ups (End-to-End Verification Transcript)

This catalog documents the live end-to-end execution of all **30 curated IOCL Finance & Downstream scenarios (`Q01–Q30`)** plus **5 multi-turn follow-ups (`Q01_FU`, `Q02_FU`, `Q07_FU`, `Q13_FU`, `Q17_FU`)** across all 6 functional pillars against live BigQuery (`yukti-finance-iocl`) and Vertex AI (`gemini-3-flash-preview` / `text-embedding-005`).

- **Generated:** `2026-11-16T21:12:33Z`
- **Source Run Artifact:** [iocl_30_questions_eval_results.json](file:///usr/local/google/home/amandeepsinghs/o%26g%20agentic%20transformation/Oil%20%26%20Gas%20Agent%20Portfolio/cloud_run_apps/Yukti%20IOCL/financial_build/data/iocl_30_questions_eval_results.json)
- **Result Summary:** **`35 / 35` turns PASS (`100.0%`)** — `30 / 30` Root Questions + `5 / 5` Follow-ups across `CMD`, `DIR_FIN`, `DIR_REF`, `DIR_MKT`, and `E2_FIN`.

---

## Scorecard Summary

| ID | Pillar | Persona | Query | Visual | Access | Latency | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `Q01` | Pillar 1: P&L & Excise | `CMD` | Show the Schedule III Profit and Loss statement of IOCL for FY26 | `table` | `allowed` | `6699.7 ms` | ✅ PASS |
| `Q01_FU` | Pillar 1: P&L & Excise | `CMD` | Plot it as a waterfall chart | `chart` | `allowed` | `9.2 ms` | ✅ PASS |
| `Q02` | Pillar 1: P&L & Excise | `DIR_FIN` | Show IOCL's 10-year Revenue Net of Excise, EBITDA, and PAT trend from FY17 to FY26 | `chart` | `allowed` | `3812.3 ms` | ✅ PASS |
| `Q02_FU` | Pillar 1: P&L & Excise | `DIR_FIN` | Overlay Brent crude and USD/INR on the 10-year PAT chart | `chart` | `allowed` | `3559.8 ms` | ✅ PASS |
| `Q03` | Pillar 1: P&L & Excise | `CMD` | Compare IOCL Gross Revenue including Excise Duty vs Net Revenue from Operations across FY17 to FY26 | `chart` | `allowed` | `4002.8 ms` | ✅ PASS |
| `Q04` | Pillar 1: P&L & Excise | `DIR_FIN` | Break down IOCL's Cost of Materials Consumed and Inventory Valuation changes from FY20 to FY26 | `table` | `allowed` | `4421.3 ms` | ✅ PASS |
| `Q05` | Pillar 1: P&L & Excise | `CMD` | How did MS/HSD retail price freezes and domestic LPG under-recoveries impact IOCL's P&L in FY23 vs FY25-FY26? | `table` | `allowed` | `3294.5 ms` | ✅ PASS |
| `Q06` | Pillar 1: P&L & Excise | `DIR_FIN` | Reconcile IOCL Standalone PAT to Consolidated Group PAT (IOC.NS) for FY24, FY25, and FY26, including CPCL and Lanka IOC | `table` | `allowed` | `2331.3 ms` | ✅ PASS |
| `Q07` | Pillar 2: Downstream 360 | `DIR_REF` | Rank all IOCL refineries by Gross Refining Margin ($/bbl) and PBT in FY26 | `table` | `allowed` | `4554.4 ms` | ✅ PASS |
| `Q07_FU` | Pillar 2: Downstream 360 | `DIR_REF` | Compare IOCL corporate GRM against Singapore Complex GRM over 10 years | `chart` | `allowed` | `3419.0 ms` | ✅ PASS |
| `Q08` | Pillar 2: Downstream 360 | `CMD` | Show crude throughput (MMT) and capacity utilization % across Panipat, Paradip, Koyali, Mathura, Haldia, Barauni, Bongaigaon, Guwahati, and Digboi in FY26 | `table` | `allowed` | `3884.3 ms` | ✅ PASS |
| `Q09` | Pillar 2: Downstream 360 | `DIR_REF` | Compare distillate yield % and fuel & loss % across all 9 IOCL refineries in FY26 | `chart` | `allowed` | `3808.1 ms` | ✅ PASS |
| `Q10` | Pillar 2: Downstream 360 | `CMD` | What was IOCL's crude, product, and gas pipeline throughput (MMT) and EBITDA contribution from FY17 to FY26? | `chart` | `allowed` | `2610.1 ms` | ✅ PASS |
| `Q11` | Pillar 2: Downstream 360 | `DIR_MKT` | Break down IOCL's domestic petroleum product sales volume (MMT) across MS, HSD, ATF, Indane LPG, Bitumen, and Lubes in FY26 | `kpi` | `allowed` | `4319.6 ms` | ✅ PASS |
| `Q12` | Pillar 2: Downstream 360 | `DIR_FIN` | Compare revenue, EBIT, and capital employed across IOCL's Petroleum Products, Petrochemicals, and Other Business segments from FY17 to FY26 | `chart` | `allowed` | `2542.9 ms` | ✅ PASS |
| `Q13` | Pillar 3: Balance Sheet | `CMD` | Show IOCL's Schedule III Balance Sheet for FY26 | `table` | `allowed` | `4987.1 ms` | ✅ PASS |
| `Q13_FU` | Pillar 3: Balance Sheet | `CMD` | Show the 10-year growth of Net Worth and Capital Employed from FY17 to FY26 | `chart` | `allowed` | `3534.1 ms` | ✅ PASS |
| `Q14` | Pillar 3: Balance Sheet | `DIR_FIN` | How did IOCL's Total Borrowings and Debt-to-Equity ratio move from FY17 to FY26? | `chart` | `allowed` | `3381.2 ms` | ✅ PASS |
| `Q15` | Pillar 3: Balance Sheet | `DIR_FIN` | Show IOCL's Inventory Days, Receivable Days, and Net Working Capital across FY17 to FY26 | `chart` | `allowed` | `2543.3 ms` | ✅ PASS |
| `Q16` | Pillar 3: Balance Sheet | `CMD` | Show IOCL's Capital Expenditure spent and CWIP across FY17 to FY26 | `chart` | `allowed` | `3538.5 ms` | ✅ PASS |
| `Q17` | Pillar 4: Cash Flow & MoU | `DIR_FIN` | Show IOCL's Cash Flow Statement for FY26 | `table` | `allowed` | `5109.6 ms` | ✅ PASS |
| `Q17_FU` | Pillar 4: Cash Flow & MoU | `DIR_FIN` | Plot the Cash Flow statement as a waterfall chart | `chart` | `allowed` | `1298.0 ms` | ✅ PASS |
| `Q18` | Pillar 4: Cash Flow & MoU | `CMD` | Show IOCL's Basic EPS, Dividend per Share, and Total Contribution to Central & State Exchequers from FY17 to FY26 | `chart` | `allowed` | `3698.9 ms` | ✅ PASS |
| `Q19` | Pillar 4: Cash Flow & MoU | `DIR_FIN` | Show IOCL's complete Financial Ratios scorecard (ROCE, ROE, EBITDA Margin, Current Ratio, Debt/Equity) for FY26 vs 10-year history | `table` | `allowed` | `5608.9 ms` | ✅ PASS |
| `Q20` | Pillar 4: Cash Flow & MoU | `CMD` | How is IOCL tracking against its FY26 MoPNG / DPE Maharatna MoU targets? | `clause` | `allowed` | `3.7 ms` | ✅ PASS |
| `Q21` | Pillar 5: Market, WACC & DCF | `CMD` | Plot Brent crude oil price for the past 5 years | `chart` | `allowed` | `87.0 ms` | ✅ PASS |
| `Q22` | Pillar 5: Market, WACC & DCF | `DIR_REF` | What-if: If Gross Refining Margin improves by $1.50/bbl or Brent moves to $70/bbl, how do IOCL EBITDA and PAT change? | `chart` | `allowed` | `2985.9 ms` | ✅ PASS |
| `Q23` | Pillar 5: Market, WACC & DCF | `DIR_FIN` | What happens to IOCL's financials if USD/INR depreciates by ₹3 per US dollar? | `chart` | `allowed` | `2887.6 ms` | ✅ PASS |
| `Q24` | Pillar 5: Market, WACC & DCF | `DIR_FIN` | What is IOCL's WACC in FY26, and what are Cost of Equity (Ke), After-Tax Cost of Debt (Kd), Beta, and capital weights? | `table` | `allowed` | `2246.4 ms` | ✅ PASS |
| `Q25` | Pillar 5: Market, WACC & DCF | `DIR_FIN` | What are the top 5 quantified CFO turnaround levers to expand IOCL EBITDA, ROCE, and Free Cash Flow in FY27? | `actions` | `allowed` | `1645.1 ms` | ✅ PASS |
| `Q26` | Pillar 5: Market, WACC & DCF | `DIR_FIN` | Run a DCF valuation for IOCL (NSE:IOC) using FY26 SSOT actuals and market price | `none` | `allowed` | `22.9 ms` | ✅ PASS |
| `Q27` | Pillar 6: Policy, RBAC & Docs | `CMD` | Under IOCL's Delegation of Financial Powers (DoA), what are the approval thresholds for spot crude oil cargo procurement and refinery turnaround capex? | `clause` | `allowed` | `3.8 ms` | ✅ PASS |
| `Q28` | Pillar 6: Policy, RBAC & Docs | `DIR_FIN` | What does IOCL's Risk Management & Hedging Policy permit for crack-spread hedging, inventory price protection, and USD/INR forward cover? | `clause` | `allowed` | `3.7 ms` | ✅ PASS |
| `Q29` | Pillar 6: Policy, RBAC & Docs | `E2_FIN` | Show confidential counterparty credit exposure by customer sub-ledger and unpublished Board draft pack | `refusal` | `refused` | `10.9 ms` | ✅ PASS |
| `Q30` | Pillar 6: Policy, RBAC & Docs | `CMD` | Draft a Board Note for the Chairman and Director (Finance) on FY26 Refinery GRM performance and FY27 Capex funding plan | `document` | `allowed` | `2.7 ms` | ✅ PASS |

---

## Pillar-by-Pillar Observed Contract Briefings

### Pillar 1: Schedule III Statement of Profit & Loss & Gross-vs-Net Excise Bridge (`Q01–Q06`)
- **`Q01` (`CMD` · `table` · `6699.7 ms`):** For FY26, IOCL's Schedule III Gross Revenue from Operations is `₹886,224.41 crore`, Total Income is `₹891,864.41 crore`, Total Expenses are `₹842,710.99 crore`, Profit Before Tax is `₹49,153.42 crore`, and Standalone PAT is `₹36,802.42 crore`.
  - **`Q01_FU` (`CMD` · `chart` · `9.2 ms`):** Generates the FY26 P&L waterfall bridge from `₹886,224.41 crore` revenue to `₹36,802.42 crore` PAT.
- **`Q02` (`DIR_FIN` · `chart` · `3812.3 ms`):** Net revenue from operations ex-excise moved from `₹359,873 crore` in `FY17` to `₹784,157.87 crore` in `FY26`.
  - **`Q02_FU` (`DIR_FIN` · `chart` · `3559.8 ms`):** Standalone PAT moved from `₹19,106.4 crore` (`FY17`) to `₹36,802.42 crore` (`FY26`) with macro overlay capability.
- **`Q03` (`CMD` · `chart` · `4002.8 ms`):** Gross revenue from operations moved from `₹445,373 crore` in `FY17` to `₹886,224.41 crore` in `FY26` across the 10-year Excise bridge.
- **`Q04` (`DIR_FIN` · `table` · `4421.3 ms`):** Crude & materials consumed moved from `₹262,180 crore` in `FY20` to `₹396,820 crore` in `FY26`.
- **`Q05` (`CMD` · `table` · `3294.5 ms`):** IOCL Schedule III P&L Trend (`FY23–FY26`) moved from `₹934,953 crore` revenue in `FY23` to `₹886,224.41 crore` in `FY26`; highest PAT `FY24` (`₹39,618.84 cr`) vs lowest `FY23` (`₹8,241.82 cr`) during fuel price freezes.
- **`Q06` (`DIR_FIN` · `table` · `2331.3 ms`):** Reconciles `₹9,743.74 crore` across `6` group entities (`FY24–FY26`), led by Chennai Petroleum Corporation Limited (`₹4,910.6 crore`) and Petronet LNG, HURL & Joint Ventures/Associates (`₹4,032 crore`), alongside Lanka IOC (`LIOC`).

### Pillar 2: Refinery Economics 360, Pipeline Logistics & Product Marketing (`Q07–Q12`)
- **`Q07` (`DIR_REF` · `table` · `4554.4 ms`):** Ranks all `9` standalone refineries: highest GRM at Paradip Refinery (`$12.46/bbl`) and Panipat (`$11.54/bbl`); lowest at Digboi (`$7.96/bbl`).
  - **`Q07_FU` (`DIR_REF` · `chart` · `3419.0 ms`):** Corporate Reported GRM moved from `$10.22/bbl` in `FY17` to `$10.85/bbl` in `FY26` vs Singapore Complex benchmark.
- **`Q08` (`CMD` · `table` · `3884.3 ms`):** Total FY26 standalone throughput `75.45 MMT` across all `9` refineries led by Panipat (`16.42 MMT`) and Paradip (`16.18 MMT`).
- **`Q09` (`DIR_REF` · `chart` · `3808.1 ms`):** Compares distillate yield % (highest Paradip & Panipat at `84.2%`, lowest Mathura at `82.8%`) and fuel & loss % across all `9` refineries.
- **`Q10` (`CMD` · `chart` · `2610.1 ms`):** `903.44 MMT` cumulative throughput across IOCL's `3` pipeline networks (`FY17–FY26`), led by Crude Oil Pipelines (`492.37 MMT`) and Petroleum Product Pipelines (`370.41 MMT`).
- **`Q11` (`DIR_MKT` · `kpi` · `4319.6 ms`):** FY26 domestic product sales volume `105.12 MMT` (`+4.84 MMT` / `+4.8%` vs `FY25`).
- **`Q12` (`DIR_FIN` · `chart` · `2542.9 ms`):** `₹6,900,449.41 crore` cumulative revenue across `3` Ind-AS 108 segments (`FY17–FY26`), led by `PETROLEUM_PRODUCTS` (`₹6,561,166.62 crore`, `95.1%`) and `PETROCHEMICALS` (`₹256,617.15 crore`).

### Pillar 3: Schedule III Balance Sheet, Borrowings, Working Capital & Capex (`Q13–Q16`)
- **`Q13` (`CMD` · `table` · `4987.1 ms`):** As of 31 March `FY26`, Total Assets stand at `₹477,282.34 crore` (`Non-Current ₹368,150 crore`, `Current ₹109,132.34 crore`), Total Equity `₹204,544.34 crore`.
  - **`Q13_FU` (`CMD` · `chart` · `3534.1 ms`):** Standalone Net Worth moved from `₹99,729 crore` (`FY17`) to `₹204,544.34 crore` (`FY26`).
- **`Q14` (`DIR_FIN` · `chart` · `3381.2 ms`):** Total borrowings moved from `₹54,820 crore` in `FY17` to `₹110,668 crore` in `FY26`.
- **`Q15` (`DIR_FIN` · `chart` · `2543.3 ms`):** Dedicated `working_capital` trajectory across `FY17–FY26` tracking Inventory Days (`75.34` in `FY17` → `58.65` in `FY26`), Receivable Days (`DSO`), Trade Payables, Current Ratio, and Net Working Capital.
- **`Q16` (`CMD` · `chart` · `3538.5 ms`):** Capital expenditure spent moved from `₹16,850 crore` in `FY17` to `₹34,210 crore` in `FY26`.

### Pillar 4: Ind-AS 7 Cash Flow Statement, Ratios & Maharatna MoU (`Q17–Q20`)
- **`Q17` (`DIR_FIN` · `table` · `5109.6 ms`):** In `FY26`, OCF = `₹66,480 crore`, Investing = `−₹32,960 crore`, Financing = `−₹33,177.35 crore`.
  - **`Q17_FU` (`DIR_FIN` · `chart` · `1298.0 ms`):** Converts the `FY26` Cash Flow statement into a multi-step waterfall chart.
- **`Q18` (`CMD` · `chart` · `3698.9 ms`):** Basic EPS moved from `₹13.53` in `FY17` to `₹26.06` in `FY26` (`1,412.1238 Cr` bonus-adjusted shares).
- **`Q19` (`DIR_FIN` · `table` · `5608.9 ms`):** `FY26` scorecard: EBITDA Margin (Net Revenue) `9.5%`, Standalone PAT Margin `4.7%`, Consolidated ROCE `18.1%`, ROE `18.0%`, Debt-to-Equity `0.54x`, and Basic EPS `₹26.06/share`.
- **`Q20` (`CMD` · `clause` · `3.7 ms`):** Cites IOCL Maharatna DPE/MoPNG MoU Governance Framework Clause `1.0` (`50%` financial parameters + `50%` downstream efficiency targets).

### Pillar 5: Yahoo Finance (`IOC.NS`), Sensitivity What-If, WACC, Turnaround Levers & DCF (`Q21–Q26`)
- **`Q21` (`CMD` · `chart` · `87.0 ms`):** 5-year Brent crude history (`BZ=F`), peaking at `$127.98/bbl` (`08 Mar 2022`), bottoming at `$58.92/bbl` (`16 Dec 2025`), latest `$92.34/bbl`.
- **`Q22` (`DIR_REF` · `chart` · `2985.9 ms`):** `DIR_REF` (functional director tier) simulates `$1.50/bbl` GRM & `$70/bbl` Brent sensitivity across all `9` IOCL refineries (`+EBITDA` & `+PAT`).
- **`Q23` (`DIR_FIN` · `chart` · `2887.6 ms`):** Simulates `₹3/USD` INR depreciation sensitivity across `3` downstream financial impact records.
- **`Q24` (`DIR_FIN` · `table` · `2246.4 ms`):** `FY26` `WACC = 9.2534%` (`Ke = 11.51%`, Pre-tax `Kd = 7.15%`, tax rate `25.17%`, Relevered Beta `0.6267`, Equity MV `₹191,201.57 crore` vs Debt BV `₹110,668 crore`) across all `17` input parameters.
- **`Q25` (`DIR_FIN` · `actions` · `1645.1 ms`):** Generates top `5` quantified CFO turnaround levers for `FY27` (`FY26` baseline), including Inventory DIO compression (`-3 days`), pipeline freight shift, receivable DSO discipline, CWIP commissioning, and crude slate optimization.
- **`Q26` (`DIR_FIN` · `none` · `22.9 ms`):** Triggers the interactive background DCF Valuation agent confirmation prompt (`NSE:IOC`, `1,412.1238 Cr` shares, `9.2534%` WACC).

### Pillar 6: Finance Policy RAG, Governance RBAC & Board Deliverables (`Q27–Q30`)
- **`Q27` (`CMD` · `clause` · `3.8 ms`):** Retrieves `IOCL Delegation of Financial Powers (DoA) — Clause 2.1` (spot & term crude oil cargo procurement thresholds).
- **`Q28` (`DIR_FIN` · `clause` · `3.7 ms`):** Retrieves `IOCL Commodity & Forex Risk Management Policy — Clause 5.0` (`50%–75%` rolling `<6 month` USD/INR hedge mandate).
- **`Q29` (`E2_FIN` · `refusal` · `10.9 ms`):** Policy-enforced RBAC refusal (`access.status = "refused"`) blocking confidential counterparty credit sub-ledgers & unpublished Board draft packs for Officer Grade B (`E2_FIN`).
- **`Q30` (`CMD` · `document` · `2.7 ms`):** Generates grounded Executive Memorandum (`Board Note: Downstream & Financial Review`) exportable to `.docx`, `.pdf`, `.xlsx`, and `.eml`.
