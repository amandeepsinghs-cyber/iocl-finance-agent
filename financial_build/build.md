# IOCL 10-Year Finance & Downstream SSOT Build (`yukti-finance-iocl`)

## Overview
- **Company:** Indian Oil Corporation Limited (IOCL · `NSE:IOC` / `IOC.NS`)
- **Target GCP Project:** `yukti-finance-iocl` (`asia-south1`)
- **Scope:** 100% Finance & Downstream Intelligence (`FY17`–`FY26`) — Schedule III Standalone & Consolidated 3-Statements, Gross vs. Net Revenue & Central Excise Duty Bridge, Refinery Economics 360 (`9` Standalone Refineries), Pipelines (`3` Networks), Product Marketing (`7` Product Categories), Statutory Segments (`3` Ind-AS 108 Segments), Subsidiary & JV Group Reconciliation (`6` Entities), DPE/MoPNG Maharatna MoU (`FY25`–`FY26`), WACC (`FY17`–`FY26`), and Annual Report Contextual RAG (`FY17`–`FY26`).

## Implemented Deliverables
1. **10-Year Structured Finance & Downstream Datasets (`financial_build/data/` & `financial_ssot/out/`):**
   - Generated via `financial_build/scripts/build_iocl_10yr_ssot.py` and `financial_build/scripts/fetch_iocl_market_and_wacc.py` (`1,412.1238 Cr` bonus-adjusted shares, FY26 Basic EPS `₹26.06/share`, Book Value per Share `₹144.85/share`, WACC `9.2534%`).
   - Core JSONs & Parquets: `iocl_10yr_corporate_wide.json` (`10` FYs × `131` columns), `iocl_10yr_schedule_iii_lines.json` (`240` rows), `iocl_10yr_balance_sheet_lines.json` (`240` rows), `iocl_10yr_cash_flow_lines.json` (`180` rows), `iocl_10yr_ratios_lines.json` (`180` rows), `ssot_refinery_economics_360` (`120` rows across 9 standalone refineries + corporate downstream/petchem reconciliation), `fact_marketing_sales` (`70` rows), `fact_pipeline_ops` (`30` rows), `fact_segment` (`90` rows), `fact_mou_scorecard` (`24` rows across `12` parameters), `subsidiary_financials` (`60` rows across `6` group entities), `fact_wacc_annual` (`10` rows), `fact_wacc_input` (`170` rows), and `fact_snapshot.parquet`.
2. **Zero-Tolerance Accounting Reconciliation Gate (`financial_build/scripts/verify_iocl_identities.py`):**
   - **Verified Result:** `612 checks executed | 612 PASS | 0 FAIL | max_abs_delta=0.000000` (Assets == Equity + Liabilities, OCF + ICF + FCF == Net Cash Change, Closing Cash continuity, Gross - Excise == Net Revenue, 9-Refinery Sum + Marketing/Petchem/Pipeline == Standalone Totals, Standalone + Subs/JVs/Eliminations == Consolidated PAT, EPS & BVPS exact to `1,412.1238 Cr` shares).
3. **Live BigQuery Lakehouse & Views (`yukti-finance-iocl` · `asia-south1`):**
   - Populated via `financial_build/scripts/load_iocl_bq.py` across `hrfin_gold` and `hrfin_gold_v3` (`18` tables + `7` views including `v_fin_statement_as_reported`, `v_fin_trend_latest`, `v_refinery_pnl_v3`, `v_fin_yahoo_view`, and `recon_checks`).
4. **Contextual RAG & Governance Policy Corpus (`hrfin_docs`):**
   - `8,437` verbatim chunked/embedded IOCL Annual Report paragraphs across all 10 reports (`FY17`–`FY26`) in `hrfin_docs.doc_chunks_ar`.
   - `136` executive contextual chunks in `hrfin_docs.financial_notes_chunks` + `255` rows in `hrfin_gold.ssot_financial_line_context` + `40` IOCL Finance Governance/DoA/Hedging/MoU policy clauses in `hrfin_docs.rulebooks_clauses` / `silver_chunks`.
5. **End-to-End Conversational Verification (`financial_build/scripts/run_iocl_30_questions_eval.py`):**
   - **Result:** `35/35 turns PASS` (`30/30` curated IOCL root scenarios `Q01`–`Q30` + `5/5` multi-turn follow-ups `Q01_FU`, `Q02_FU`, `Q07_FU`, `Q13_FU`, `Q17_FU`) executed live against `yukti-finance-iocl` BigQuery + `gemini-3-flash-preview` (`100.0%` pass rate). Details in [05_curated_30_questions_and_followups.md](file:///usr/local/google/home/amandeepsinghs/o%26g%20agentic%20transformation/Oil%20%26%20Gas%20Agent%20Portfolio/cloud_run_apps/Yukti%20IOCL/financial_build/05_curated_30_questions_and_followups.md).
