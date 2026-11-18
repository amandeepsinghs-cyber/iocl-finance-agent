# IOCL Financial & Downstream Build Execution Checklist (`yukti-finance-iocl`)

## Build & Verification Gates

| Gate / Script | Status | Verified Result | Notes |
| --- | --- | --- | --- |
| Market & WACC Builder (`fetch_iocl_market_and_wacc.py`) | ✅ Complete | `10` WACC years (`FY17–FY26`), `170` inputs | Yahoo Finance `IOC.NS`, `BZ=F`, `CL=F`, `INR=X`; FY26 WACC `9.2534%` (`Ke 11.5124%`, `Kd pre-tax 7.15%`, `Beta 0.6267`, `Tax 25.168%`). |
| 10-Yr SSOT Builder (`build_iocl_10yr_ssot.py`) | ✅ Complete | `930` statement lines, `10` FYs × `131` cols | Share-count divisor (`1,412.1238 Cr`) verified (`FY26 EPS ₹26.06`, `BVPS ₹144.85`, `Revenue ₹886,224.41 Cr`, `PAT ₹36,802.42 Cr`). |
| Identity Gate (`verify_iocl_identities.py`) | ✅ Pass | `612 / 612 PASS` (`max_abs_delta=0.000000`) | Zero-tolerance check across BS, P&L, CF, 9-Refinery Sum, Segments, and Consolidated PAT. |
| Contextual RAG (`build_and_load_iocl_rag.py` + `chunk_ar.py`) | ✅ Complete | `8,437` AR chunks + `136` note chunks (`768-d`) | Vertex AI `text-embedding-005` embeddings across all 10 IOCL Annual Reports (`FY17–FY26`) + 40 policy clauses. |
| Certified Queries (`library.yaml` + Warmup Cache) | ✅ Complete | `30 / 30` certified queries (`Q01–Q30`) | Full SQL templates mapped in `app/brain/certified/library.yaml` + warmed cache contracts. |
| 30-Question E2E Eval (`run_iocl_30_questions_eval.py`) | ✅ Pass | `35 / 35 PASS` (`30/30` roots + `5/5` follow-ups) | Executed live via `AgentTurnRunner` against `yukti-finance-iocl` & `gemini-3-flash-preview`. |

## Live BigQuery Asset Inventory (`yukti-finance-iocl` · `asia-south1`)

| BigQuery Object (`hrfin_gold` & `hrfin_gold_v3`) | Status | Row Count | Purpose |
| --- | --- | --- | --- |
| `ssot_corporate_annual_360` | ✅ Loaded | `10` | Wide 10-year (`FY17–FY26`) IOCL corporate, macro & downstream scorecard |
| `fact_financial_statement_line` | ✅ Loaded | `930` | Normalized Ind-AS Schedule III P&L, Balance Sheet, Cash Flow, Excise & Ratio lines |
| `dim_financial_line` | ✅ Loaded | `87` | Canonical line-code taxonomy, hierarchy & formulas |
| `ssot_corporate_pnl_lines` | ✅ Loaded | `240` | Schedule III Statement of Profit & Loss (`FY17–FY26`) |
| `ssot_corporate_balance_sheet_lines` | ✅ Loaded | `240` | Schedule III Balance Sheet (`FY17–FY26`) |
| `ssot_corporate_cash_flow_lines` | ✅ Loaded | `180` | Ind-AS 7 Cash Flow Statement (`FY17–FY26`) |
| `ssot_corporate_ratios_lines` | ✅ Loaded | `180` | Financial, Working Capital & Downstream operating ratios (`FY17–FY26`) |
| `ssot_refinery_economics_360` | ✅ Loaded | `120` | `9` standalone refineries (`75.451 MMT`, `$10.85/bbl` weighted GRM in FY26) + corporate reconciliation rows |
| `fact_marketing_sales` | ✅ Loaded | `70` | Product volumes & margins (`MS`, `HSD`, `ATF`, `LPG`, `Bitumen`, `Lubes`, `Petchem`; `105.117 MMT` FY26) |
| `fact_pipeline_ops` | ✅ Loaded | `30` | Crude Oil, Petroleum Product & Gas pipelines throughput & EBITDA (`FY17–FY26`) |
| `fact_segment` | ✅ Loaded | `90` | Ind-AS 108 segments (Petroleum Products, Petrochemicals, Other Businesses) |
| `fact_mou_scorecard` | ✅ Loaded | `24` | `12` MoPNG/DPE Maharatna MoU parameters (`FY25–FY26`) |
| `fact_wacc_annual` | ✅ Loaded | `10` | Annual `IOC.NS` CAPM WACC (`FY26 WACC = 9.2534%`) |
| `fact_wacc_input` | ✅ Loaded | `170` | Granular lineage inputs (G-Sec `rf`, ERP, unlevered/relevered beta, equity MV, debt BV, shares) |
| `ssot_financial_line_context` | ✅ Loaded | `255` | Line-level FY17–FY26 AR variance drivers & CFO commentary |
| `recon_checks` | ✅ Loaded | `612` | Automated identity verification ledger (`0` conflicts in `fact_financial_line_conflict`) |
| `hrfin_docs.doc_chunks_ar` | ✅ Loaded | `8,437` | Verbatim chunked & embedded IOCL Annual Report corpus (`FY17–FY26`) |
| `hrfin_docs.financial_notes_chunks` | ✅ Loaded | `136` | Schedule III Notes, MD&A events & CFO action chunks (`768-d`) |
| `hrfin_docs.rulebooks_clauses` / `silver_chunks` | ✅ Loaded | `40` | IOCL Delegation of Financial Powers (DoA), Commodity/FX Hedging, Accounting Policy & MoU rules |
