# Yukti IOCL — End-to-End Reproducible Build Manual & Live Execution Checklist (`build.md`)

> **BLUF:** This document is both the **reproducible step-by-step engineering manual** and the **live execution checklist** to build, verify, and deploy the **Indian Oil Corporation Limited (IOCL) Finance & Downstream Intelligence Agent** (`yukti-finance-iocl`).
> - **Scope:** **100% Finance, Refinery/Pipeline/Marketing Economics, Treasury, Market & Valuation Agent** (**HR is completely excluded**).
> - **Two Core Data Sources (Regenerated & Reloaded End-to-End):**
>   1. **IOCL Statutory & Operational Filings (`FY17–FY26`):** IOCL Annual Reports (Ind-AS Schedule III Standalone & Consolidated P&L, Balance Sheet, Cash Flow, Ratios, Notes, MD&A), Quarterly Investor Decks & PPAC Downstream Anchors (9 Standalone Refineries + CPCL, Pipelines, Retail/Product Marketing), and IOCL Finance/DoA/Hedging/MoU Policy RAG (`text-embedding-005` 768-d vectors in BigQuery).
>   2. **Yahoo Finance & Market Benchmarks (`IOC.NS`, `BZ=F`, `CL=F`, `INR=X`, Singapore GRM):** Consolidated `IOC.NS` financials cross-walk, live/12-year daily equity & commodity feeds, Damodaran/RBI WACC (`fact_wacc_annual`), and live `NSE:IOC` DCF valuation.
> - **Brand Identity:** Official **IndianOil** emblem (`/brand/iocl_logo.png` + `.svg`), IndianOil Saffron Orange (`#F37021`) & Navy (`#003366`) design tokens (`58/58` WCAG contrast checks), and EN/HI/Hinglish Gemini Live voice.

---

## 0. Hard Isolation Guardrails (Non-Negotiable)

| Boundary | IOCL Target (Allowed) | ONGC Production Demo (NEVER TOUCH) |
|---|---|---|
| **Workspace Folder** | `/usr/local/google/home/amandeepsinghs/o&g agentic transformation/Oil & Gas Agent Portfolio/cloud_run_apps/Yukti IOCL` | `.../cloud_run_apps/HR and Finance_ONGC` |
| **GCP Project** | **`yukti-finance-iocl`** (`asia-south1`, `gcloud` profile `iocl`) | `ongc-hr-finance-agent` |
| **GitHub Repository** | **`https://github.com/amandeepsinghs-cyber/iocl-finance-agent.git`** | `.../HR-Finance-Agent-ONGC.git` |
| **Local Dev Ports** | Frontend **`:3400`** · FastAPI Backend **`:8195`** | `:3300` / `:8095` |
| **Git Commit / Push** | Pause for explicit user approval before `git commit` / `git push` | Never touch |

---

## 1. Master Live Execution Checklist (Updated After Every Step)

Legend: `[x]` Verified Done · `[-]` In Progress · `[ ]` Pending

- [x] **Step 0 — Pre-Flight Auth, Scope Lock & GCP Infrastructure Provisioning (`yukti-finance-iocl`)**
  - *Status:* **COMPLETED & VERIFIED** (`2026-11-16 17:33 UTC`)
  - *Verified Evidence:*
    - `gcloud` CLI (`admin@amandeepsinghs.altostrat.com`) & ADC token valid; named configuration `iocl` active (`project=yukti-finance-iocl`, `region=asia-south1`).
    - Git `origin` wired exclusively to `https://github.com/amandeepsinghs-cyber/iocl-finance-agent.git`.
    - Enabled 10 GCP APIs (`bigquery`, `storage`, `aiplatform`, `discoveryengine`, `run`, `cloudbuild`, `artifactregistry`, `firestore`, `secretmanager`, `iap`).
    - Created GCS buckets (`asia-south1`, uniform access, public-access-prevented): `gs://yukti-finance-iocl-landing`, `gs://yukti-finance-iocl-docs`.
    - Created BigQuery datasets (`asia-south1`): `hrfin_bronze_v3`, `hrfin_silver_v3`, `hrfin_gold_v3`, `hrfin_stage_v3`, `hrfin_ref_v3`, `hrfin_docs` *(canonical `hrfin_gold`, `hrfin_silver`, `hrfin_bronze`, `hrfin_stage`, `hrfin_ref` & Firestore `(default)` DB added in Step 1B)*.
    - Created Secret Manager secret `yukti-persona-signing-key` (`version 1` enabled).
- [x] **Step 1 — Codebase Project Parameterization, Port Isolation (`:3400`/`:8195`) & Canonical Dataset/Firestore Setup**
  - *Status:* **COMPLETED & VERIFIED** (`2026-11-16 17:44 UTC`)
  - *Verified Evidence:*
    - Replaced `ongc-hr-finance-agent` across 293 tracked files; `git grep "ongc-hr-finance-agent"` outside guardrail docs = **`0` matches**.
    - `app.config.GCP_PROJECT` verified `yukti-finance-iocl` (immune to host ambient `GOOGLE_CLOUD_PROJECT`); `DEFAULT_ALLOWED_ORIGINS` = `http://localhost:3400,http://127.0.0.1:3400`; local/container ports aligned to `:3400` (UI) and `:8195` (FastAPI); `93` offline backend config/security tests passed.
    - All 12 BigQuery datasets (`hrfin_bronze`, `hrfin_silver`, `hrfin_gold`, `hrfin_stage`, `hrfin_ref`, `hrfin_gold_staging` + `_v3` variants + `hrfin_docs`), Firestore `(default)` Native DB (`asia-south1`), and Artifact Registry `yukti-repo` (`asia-south1`) created and verified in `yukti-finance-iocl`.
- [x] **Step 2 — Strip HR Surfaces & Configure IOCL Finance-Only Personas + RBAC**
  - *Status:* **COMPLETED & VERIFIED** (`2026-11-16 18:05 UTC`)
  - *Verified Evidence:*
    - Removed HR roles (`DIR_HR`, `E1_HR..E4_HR`) from UI `PERSONA_DIRECTORY` (`personas.ts`), `app_users.yaml`, `dim_app_user.csv`, and disabled `hr_transfer_agent` from `agents/registry.yaml`, `coordinator.py`, `router.py`, and schemas (`answer_contract.schema.json`, `answerContract.ts`).
    - Configured 8 IOCL Finance & Downstream personas (`CMD` accepting `CHAIRMAN` alias, `DIR_FIN`, `DIR_REF`, `DIR_MKT`, and Grades `A–D` mapped on `E1_FIN..E4_FIN` accepting `A_FIN..D_FIN` aliases) + `DEMO_ADMIN` with Access Request routing to `DIR_FIN` / `CMD`.
    - `pytest` on `test_rbac_policy.py`, `test_personas_v3.py`, `test_access_requests.py`, `test_auth_tokens.py`, `test_role_escalation.py`, `test_contract_v3.py`, `test_catalog_consistency.py`, `test_h1_hardening.py`, `test_security_headers.py`, `agents/test_router.py`, `agents/test_tools_rbac.py` green.
- [x] **Step 3 — Data Source 2: Yahoo Finance (`IOC.NS`) & Macro/GRM Market Feeds + WACC (`fact_wacc_annual`)**
  - *Status:* **COMPLETED & VERIFIED** (`2026-11-16 18:12 UTC`)
  - *Verified Evidence:*
    - `financial_build/scripts/fetch_iocl_market_and_wacc.py` fetched 12y daily Yahoo Finance history (`iocl_daily.json` 2,963d, `brent_daily.json` 3,033d, `wti_daily.json` 3,031d, `inr_daily.json` 3,138d) + calibrated `grm_daily.json` (2,772d); added `"grm"` and `"iocl"` support to `oil_prices.py` & `oil_intent.py`.
    - Populated `market_prices_seed.csv` for `IOC.NS` (`FY17–FY26`, FY26 close `₹135.40` on `2026-03-30`, `1,412.1238 Cr` shares) and computed 10-yr IOCL WACC (`FY26 = 9.2534%`, `Ke = 11.5124%`, `Kd = 7.15%`, `wE = 0.633391`, `wD = 0.366609`) in `fact_wacc_annual.parquet`, `fact_wacc_input.parquet`, and BQ `hrfin_gold` / `hrfin_gold_v3`.
    - `load_fy26_wacc_default()` -> `9.2534`, `load_fy26_market_price_default()` -> `135.4`; `pytest test_oil_overlay.py test_wacc_metric.py test_dcf_fixture.py` (`71 passed`).
- [x] **Step 4 — Data Source 1A: IOCL 10-Year (`FY17–FY26`) 3-Statement, Ratios & Downstream Sub-Ledger SSOT**
  - *Status:* **COMPLETED & VERIFIED** (`2026-11-16 18:30 UTC`)
  - *Verified Evidence:*
    - `financial_build/scripts/build_iocl_10yr_ssot.py` generated `iocl_10yr_*.json`, `dim_financial_line.csv`, `fact_snapshot.parquet` (930 verified rows), `ssot_refinery_economics_360` (120 rows: 9 refineries totaling `70.25 MMTPA` + 3 division recon rows), `fact_marketing_sales` (70 rows), `fact_pipeline_ops` (30 rows), `fact_segment` (90 rows), `subsidiary_financials` (60 rows), and `fact_mou_scorecard` (24 rows); deleted obsolete `ongc_10yr_*.json` files and updated `Dockerfile`, `compiler.py`, `statement_builder.py`, `export_legacy_json.py`, and statement/bridge tests.
    - `financial_build/scripts/verify_iocl_identities.py`: **`600 / 600` PASS (`0` FAIL, `max_abs_delta = 0.000000`)**.
    - `financial_build/scripts/load_iocl_bq.py`: populated all Gold/Silver/Bronze + `_v3` tables and views (`v_fin_statement_as_reported`, `v_fin_trend_latest`, `v_refinery_pnl_v3`, etc.) in `yukti-finance-iocl` (`asia-south1`).
- [x] **Step 5 — Data Source 1B: Download All 10 IOCL Annual Report PDFs (`FY17–FY26`) + Build BigQuery Vector RAG (`ix_doc_chunks_ar` + `financial_notes_chunks`)** *(COMPLETED & VERIFIED)*
  - *Goal:* Download all 10 official IOCL Annual Reports (`FY17–FY26` PDFs from NSE Archives / `iocl.com`) into `knowledge/public_sources/grounding_data/raw/` + upload to `gs://yukti-finance-iocl-docs/annual_reports/`, extract layout-preserving page text (`pdftotext -layout` -> `IOCL_AR_FY*.txt`), run deterministic page-preserving chunker (`chunk_ar.py` -> `doc_chunks_ar.jsonl`), embed every verbatim AR page chunk + Schedule III Note/MD&A context chunk with Vertex AI `text-embedding-005` (`768-d`), load `hrfin_docs.doc_chunks_ar` (`8,437` rows with ACTIVE IVF COSINE `VECTOR INDEX ix_doc_chunks_ar`) & `hrfin_docs.financial_notes_chunks` (`136` rows) + `ssot_financial_line_context` (`255` rows), and populate `rulebooks_clause_index.csv` + `hrfin_docs.rulebooks_clauses` (`40` clauses) with IOCL Finance/DoA/Hedging/MoU policies (`0` HR rules).
  - *Gate:* All 10 IOCL AR PDFs (`FY17–FY26`) verified on disk & in `gs://yukti-finance-iocl-docs/annual_reports/`; `hrfin_docs.doc_chunks_ar` (`8,437` rows) & `financial_notes_chunks` (`136` rows) populated with 768-d embeddings; live `VECTOR_SEARCH` & AR retriever tests verified.
- [x] **Step 6 — Semantic Layer, Certified SQL Library, CFO Diagnostic Levers (`L01–L10`) & `NSE:IOC` DCF Valuation Engine** *(COMPLETED & VERIFIED)*
  - *Goal:* Update `semantic_model.yaml`, `compiler.py`, `statement_builder.py`, `insight_context.py`, `entities.json`, `entity_aliases.yaml`, `certified/library.yaml` (`Q01–Q30` + `answer_cache_warmup.json`), and `DEFAULT_TEXT_MODEL` (`gemini-3-flash-preview` in `global`) for IOCL OMC metrics (`gross_revenue_cr`, `excise_duty_cr`, `net_revenue_cr`, `refinery_grm_usd_bbl`, `gross_refining_margin_usd_bbl`, `refinery_throughput_mmt`, `refinery_distillate_yield_pct`, `refinery_fuel_loss_pct`, `pipeline_throughput_mmt`, `marketing_volume_mmt`). Update `fin_diagnostics/levers.yaml` (`L01–L10` OMC levers) and `app/finance/dcf/` + `dcf_agent.py` for IOCL Downstream FCFF valuation (`NSE:IOC`, `1,412.1238 Cr` shares, `9.2534%` WACC) + `.xlsx` export.
  - *Gate:* Planner (`32/32`) + SQL compiler (`54/54` SSOT + `133/133` metrics BQ dry-run) + provenance + agent + DCF unit/integration tests pass; live DCF run produces valid intrinsic value/share, WACC × g sensitivity grid, and `.xlsx` workbook.
- [x] **Step 7 — Official IndianOil Logos, Saffron/Navy Design Tokens, UI Copy, Voice Prompts & Architecture Portal**
  - *Goal:* Generate/install crisp official IndianOil logos (`public/brand/iocl_logo.png`, `public/brand/iocl_logo.svg`, `src/app/icon.png`, `public/favicon.ico`) and remove `ongc_logo.png` from UI surfaces. Update `tokens.json` to IndianOil Saffron Orange (`#F37021`) & Navy (`#003366`), regenerate CSS (`npm run tokens`), update `TopBar.tsx` ("Yukti AI Agent · Finance & Downstream Intelligence · Indian Oil Corporation Limited"), `page.tsx` Finance starters/greeting, `OilOverlayBar.tsx` (Brent / WTI / Singapore GRM / USD-INR), `live_session.py` (`YUKTI_LIVE_SYSTEM_PROMPT` + IOCL refinery pronunciations), PDF/DOCX/XLSX export headers, and `public/architecture/portal.html`.
  - *Gate:* Verified: `npm run lint:tokens` (`76` files OK), `npm run lint:contrast` (`58` WCAG pairs PASS), `npm run typecheck` (`0` errors), `npm run build` (`next build` + `70` theme tokens OK), `test:bridge` (`49`), `test:statement` (`12`), `test:portfolio` (`14`), `test:compat` (`199 + 4`), and `test_v19_frontend.ts` (`10`) all exit `0`.
- [x] **Step 8 — End-to-End Verification Suite (30 IOCL Finance Scenarios, RBAC Matrix & Zero-ONGC Sweep)**
  - *Goal:* Execute curated IOCL Finance verification suite across all 6 Finance & Downstream pillars (P&L Gross/Net Excise, Refinery GRM 360, Balance Sheet/Debt/Capex, Cash Flow/MoU, Yahoo `IOC.NS` + WACC + DCF + What-If, Finance DoA RAG + RBAC), run backend `pytest` + frontend build, and verify `0` runtime `"ongc"` leaks.
  - *Gate:* Verified: `verify_iocl_identities.py` (`612/612` PASS, `max_abs_delta=0.000000`), `run_iocl_30_questions_eval.py` (`35/35` turns PASS: `30/30` roots + `5/5` follow-ups), full backend `pytest -q tests/` (`1876 passed`, `0 failed` with `YUKTI_LIVE_BQ=1`), and `git grep -ni --untracked "ongc"` across runtime app paths (`0` hits, exit `1`).
- [x] **Step 9 — Cloud Run Deployment (`yukti-iocl` in `yukti-finance-iocl`) & Live Smoke Test**
  - *Status:* **COMPLETED & VERIFIED** (`2026-11-16 21:38 UTC`)
  - *Verified Evidence:*
    - Built image `asia-south1-docker.pkg.dev/yukti-finance-iocl/yukti-repo/yukti-iocl:v1` via Cloud Build (`4281fea8-1ae0-4703-9f5e-c0962e4c886a`) and deployed Cloud Run service **`yukti-iocl`** (`yukti-iocl-00001-dv6`, `Ready=True`, `asia-south1`, `yukti-iocl-sa@yukti-finance-iocl.iam.gserviceaccount.com`, `YUKTI_PERSONA_SIGNING_KEY=yukti-persona-signing-key:latest`).
    - Live URLs: **`https://yukti-iocl-u7thdacpua-el.a.run.app`** (`https://yukti-iocl-304306246468.asia-south1.run.app`), secured behind **Identity-Aware Proxy (IAP)** with `roles/iap.httpsResourceAccessor` bound to `user:admin@amandeepsinghs.altostrat.com`.
    - Live HTTP smoke checks passed (`200 OK`): `/health` (`project=yukti-finance-iocl`, `text_model=gemini-3-flash-preview`), `/brand/iocl_logo.png` (`171,397` bytes), `/` (`Indian Oil Corporation Limited`, `0` ONGC logos), `/api/auth/personas` (`8` IOCL Finance/Downstream roles + `DEMO_ADMIN`, `0` HR roles), `/api/auth/session`, and `/api/turn` (`FY26` Gross Revenue `₹8,86,224.41 Cr`, PBT `₹49,153.42 Cr`, Standalone PAT `₹36,802.42 Cr`).
- [x] **Step 10 — Final Documentation Sync & Pause Before Git Commit / Push**
  - *Status:* **COMPLETED (AWAITING EXPLICIT GIT COMMIT / PUSH APPROVAL)** (`2026-11-16 21:39 UTC`)
  - *Verified Evidence:* Synced `build.md`, `APP_LINK.md`, `next_steps.md`, `financial_build/build.md`, `financial_build/03_execution_checklist.md`, and `financial_build/05_curated_30_questions_and_followups.md`. Paused per Command Execution Protocol before running `git commit` or `git push origin iocl/init`.

---

## 2. Important Questions Catalog for IOCL (100% Finance & Downstream Scope)

Because **Indian Oil Corporation Limited (IOCL)** is India's largest downstream Oil Marketing Company (OMC) and refiner—operating **9 standalone refineries (~70.25 MMTPA) + CPCL (~10.5 MMTPA = ~80.8 MMTPA group refining capacity)**, **~19,700+ km of pipelines**, **~37,500+ retail fuel outlets**, **Indane LPG**, **SERVO lubricants**, and **Panipat/Paradip petrochemicals**—the questions an IOCL **Chairman**, **Director (Finance)**, **Director (Refineries)**, **Director (Marketing)**, or **Grade A–D Finance Officer** asks are fundamentally different from upstream E&P:

### Pillar 1: Schedule III Statement of Profit & Loss & Gross-vs-Net Excise Bridge (`FY17–FY26`)
1. **Q01 (Single-Year Schedule III P&L + Waterfall):** *"Show the Schedule III Profit and Loss statement of IOCL for FY26"* → Follow-ups: *"Plot it as a waterfall chart"*, *"What was Central Excise Duty vs Net Revenue from Operations?"*, *"Compare Standalone PAT vs Consolidated Group PAT (`IOC.NS`)."*
2. **Q02 (10-Year Revenue, EBITDA & PAT Trajectory):** *"Show IOCL's 10-year Revenue Net of Excise, EBITDA, and PAT trend from FY17 to FY26"* → Follow-ups: *"Why did PAT collapse to ₹8,242 Cr in FY23 despite record revenue?"*, *"Why did PAT surge to an all-time high of ₹39,619 Cr in FY24?"*, *"Overlay Brent crude and USD/INR on the 10-year PAT chart."*
3. **Q03 (Gross vs. Net Revenue & Central Excise Duty Accounting):** *"Compare IOCL Gross Revenue including Excise Duty vs Net Revenue from Operations across FY17 to FY26"* → Follow-ups: *"Why must EBITDA margin and Receivable Days use Net Revenue rather than Gross Revenue?"*
4. **Q04 (Raw Material Crude Basket & Inventory Gain/Loss Bridge):** *"Break down IOCL's Cost of Materials Consumed and Inventory Valuation Gain/Loss from FY20 to FY26"* → Follow-ups: *"How much of FY22 and FY24 refining profit came from inventory gains vs core GRM?"*, *"What was our High-Sulphur vs Low-Sulphur crude processing mix?"*
5. **Q05 (Retail Auto-Fuel Marketing Margin & LPG Buffer Recovery):** *"How did MS/HSD retail price freezes and domestic LPG under-recoveries impact IOCL's P&L in FY23 vs FY25–FY26?"* → Follow-ups: *"How did the Government's ₹10,801 Cr one-time LPG grant in FY23 and buffer recovery mechanism affect PBT?"*
6. **Q06 (Standalone vs. Consolidated `IOC.NS` Group Reconciliation):** *"Reconcile IOCL Standalone PAT to Consolidated Group PAT (`IOC.NS` on Yahoo Finance) for FY24, FY25, and FY26"* → Follow-ups: *"How much EBITDA and PAT did CPCL (Chennai Petroleum), Lanka IOC, and JV petrochemicals/LNG contribute?"*

### Pillar 2: Refinery Economics 360, Pipeline Logistics & Product Marketing (`FY17–FY26`)
7. **Q07 (Refinery-Wise GRM & EBITDA Ranking):** *"Rank all IOCL refineries by Gross Refining Margin ($/bbl) and EBITDA in FY26"* → Follow-ups: *"Why do Paradip and Panipat outperform Digboi, Guwahati, and Bongaigaon on GRM?"*, *"Compare IOCL average GRM against the Singapore Complex GRM benchmark over 10 years."*
8. **Q08 (Refinery Capacity Utilization & Crude Throughput):** *"Show crude throughput (MMT) and capacity utilization % across Panipat, Paradip, Koyali, Mathura, Haldia, Barauni, Bongaigaon, Guwahati, and Digboi"* → Follow-ups: *"Which refineries ran above 100% nameplate capacity in FY26?"*
9. **Q09 (Distillate Yield % & Fuel-and-Loss / Energy Intensity MBN):** *"Compare distillate yield % and fuel & loss % across all 9 IOCL refineries"* → Follow-ups: *"How many crores of annual margin uplift do we unlock if high-fuel-loss refineries improve Fuel & Loss by 0.5%?"*
10. **Q10 (Pipeline Network Economics):** *"What was IOCL's crude, product, and gas pipeline throughput (MMT) and EBITDA contribution from FY17 to FY26?"* → Follow-ups: *"What is the freight cost saving per MT-km of pipeline movement vs coastal/rail movement?"*
11. **Q11 (Domestic Marketing Volumes & Product Mix):** *"Break down IOCL's domestic petroleum product sales volume (MMT) across MS (Petrol), HSD (Diesel), ATF, Indane LPG, Bitumen, and SERVO Lubes in FY26"* → Follow-ups: *"How has ATF and Petrol volume grown since the FY21 COVID trough?"*, *"What is our retail outlet count and market share?"*
12. **Q12 (Ind AS 108 Statutory Segments — Petroleum, Petrochemicals & Gas/Others):** *"Compare revenue, EBIT, and ROCE across IOCL's Petroleum Products, Petrochemicals, and Other Business segments from FY17 to FY26"* → Follow-ups: *"Why were Petrochemical margins compressed in FY23–FY25 and what drives the Panipat/Paradip petchem recovery?"*

### Pillar 3: Schedule III Balance Sheet, Borrowings, Working Capital & Mega-Capex (`FY17–FY26`)
13. **Q13 (Schedule III Balance Sheet & Solvency):** *"Show IOCL's Schedule III Balance Sheet for FY26"* → Follow-ups: *"Verify Total Assets equal Equity plus Liabilities"*, *"Show the 10-year growth of Net Worth and Capital Employed from FY17 to FY26."*
14. **Q14 (Total Debt, Net Debt & Debt-to-Equity Trajectory):** *"How did IOCL's Total Borrowings and Debt-to-Equity ratio move from FY17 to FY26?"* → Follow-ups: *"Why did borrowings spike above ₹1.32 Lakh Cr in FY23 and drop sharply in FY24?"*, *"What is the split between Long-Term, Short-Term Working Capital, and Foreign Currency debt?"*
15. **Q15 (Working Capital Cycle — Inventories, Receivables & Crude Payables):** *"Show IOCL's Inventory Days, Receivable Days, and Net Working Capital across FY17–FY26"* → Follow-ups: *"How much cash is released by reducing crude + finished product inventory holding by 3 days?"*
16. **Q16 (CWIP & Refinery/Petchem/Green Mega-Capex Pipeline):** *"Break down IOCL's Capital Expenditure and CWIP across Refinery Expansions (Panipat P25, Barauni BR-9, Koyali), Pipelines, Petrochemicals, and Net-Zero 2046 Renewables"* → Follow-ups: *"Which CWIP projects have the highest IRR and nearest commissioning dates?"*

### Pillar 4: Ind-AS 7 Cash Flow Statement, Dividends & DPE Maharatna MoU (`FY17–FY26`)
17. **Q17 (Ind-AS 7 Cash Flow Statement & FCF Bridge):** *"Show IOCL's Cash Flow Statement for FY26 and plot the Operating-to-Free-Cash-Flow waterfall"* → Follow-ups: *"Compare Operating Cash Flow vs Capex across all 10 years FY17–FY26."*
18. **Q18 (Shareholder Returns — EPS, Bonus Issues, Dividend Payout & Exchequer Contribution):** *"Show IOCL's EPS, Dividend per Share, Dividend Payout Ratio, and Total Contribution to Central & State Exchequers from FY17 to FY26."*
19. **Q19 (Financial Ratios & Return Metrics Scorecard):** *"Show IOCL's complete Financial Ratios scorecard (ROCE, ROE, EBITDA Margin, PAT Margin, Current Ratio, Interest Coverage, Debt/Equity) for FY26 vs 10-year history."*
20. **Q20 (MoPNG / DPE Maharatna MoU Scorecard):** *"How is IOCL tracking against its FY26 MoPNG / DPE Maharatna MoU targets across Crude Throughput, Revenue, Capex, Operating Margin, and Green Energy milestones?"*

### Pillar 5: Yahoo Finance (`IOC.NS`), Macro Sensitivity, WACC, CFO Levers & Live DCF Valuation
21. **Q21 (Live Commodity & FX Overlays):** *"Show live Brent crude, WTI, Singapore GRM, and USD/INR exchange rate trends and their correlation with IOCL quarterly/annual earnings."*
22. **Q22 (GRM & Marketing Margin What-If Sensitivity):** *"What is the annualized impact on IOCL EBITDA and PAT if Gross Refining Margin improves by $1.50/bbl across ~70 MMT throughput, or if retail auto-fuel margin drops by ₹0.50/litre?"*
23. **Q23 (USD/INR Exchange Rate Sensitivity):** *"What happens to IOCL's crude import bill, foreign currency debt servicing, and PBT if the Rupee depreciates by ₹3 per US dollar?"*
24. **Q24 (10-Year WACC Attribution Bridge):** *"What is IOCL's WACC in FY26, and how did Cost of Equity (Ke), After-Tax Cost of Debt (Kd), Beta, and Debt/Market-Cap weights change from FY22 to FY26?"*
25. **Q25 (Director Finance Top-5 Turnaround & Margin Levers):** *"What are the top 5 quantified actions the Director (Finance) should execute in FY27 to expand IOCL's EBITDA, ROCE, and Free Cash Flow?"* (Covers `L01–L10`: High-Sulphur Opportunity Crude Basket Optimization, Refinery Fuel & Loss / MBN Heat Integration, Petchem Naphtha/Off-Gas Integration, Pipeline vs Coastal/Rail Primary Freight Shift, Working Capital & Foreign Currency Debt Optimization).
26. **Q26 (Live `NSE:IOC` Multi-Stage DCF Valuation):** *"Run a DCF valuation for IOCL (`NSE:IOC`) using FY26 SSOT actuals and live market price"* → Follow-ups: *"Re-run DCF assuming WACC is 50 bps lower and terminal GRM is $7.5/bbl"*, *"Export the full DCF valuation model to Excel."*

### Pillar 6: Finance Policy RAG, Persona RBAC & Executive Deliverables
27. **Q27 (Delegation of Financial Powers — DoA & Crude Tender Governance):** *"Under IOCL's Delegation of Financial Powers (DoA), what are the approval thresholds for spot crude oil cargo procurement, refinery turnaround capex, and Board Finance Committee sign-off?"*
28. **Q28 (Commodity & Forex Risk Management Policy RAG):** *"What does IOCL's Risk Management & Hedging Policy permit for crack-spread hedging, inventory price protection, and USD/INR forward cover?"*
29. **Q29 (Junior Finance Officer RBAC Refusal & Access Request Workflow):** Signed in as **Grade A / Grade B Finance Officer (`A_FIN` / `B_FIN`)**: *"Show confidential counterparty credit exposure by trader and unpublished Q1 Board draft refinery margin sub-ledgers"* → Polite policy-grounded refusal (`R-CONF` / aggregate fallback) → **"Request Access"** → **Director (Finance)** approves in `ApprovalsBell`!
30. **Q30 (Executive Board Note & Multi-Format Export):** *"Draft a Board Note for the Chairman and Director (Finance) on FY26 Refinery GRM performance and FY27 Capex funding plan, and export the statement as PDF and Excel."*

---

## 3. Step-by-Step Reproducible Build Instructions

Anyone cloning `https://github.com/amandeepsinghs-cyber/iocl-finance-agent.git` can reproduce the complete IOCL platform from scratch by executing the 10 steps below in order.

### Step 0: GCP Project Provisioning & Isolation (`yukti-finance-iocl`)
```bash
export CLOUDSDK_METRICS_ENVIRONMENT=datacloud.jetski
gcloud config configurations create iocl --activate || gcloud config configurations activate iocl
gcloud config set project yukti-finance-iocl --configuration=iocl
gcloud config set compute/region asia-south1 --configuration=iocl

gcloud services enable \
  bigquery.googleapis.com storage.googleapis.com aiplatform.googleapis.com \
  discoveryengine.googleapis.com run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com firestore.googleapis.com \
  secretmanager.googleapis.com iap.googleapis.com \
  --project=yukti-finance-iocl

gcloud storage buckets create gs://yukti-finance-iocl-landing --project=yukti-finance-iocl --location=asia-south1 --uniform-bucket-level-access --public-access-prevention
gcloud storage buckets create gs://yukti-finance-iocl-docs    --project=yukti-finance-iocl --location=asia-south1 --uniform-bucket-level-access --public-access-prevention

for ds in hrfin_bronze hrfin_silver hrfin_gold hrfin_stage hrfin_ref hrfin_gold_staging \
          hrfin_bronze_v3 hrfin_silver_v3 hrfin_gold_v3 hrfin_stage_v3 hrfin_ref_v3 hrfin_docs; do
  bq mk --dataset --location=asia-south1 --label datacloud:jetski "yukti-finance-iocl:${ds}" || true
done

gcloud firestore databases create --database="(default)" --location=asia-south1 --type=firestore-native --project=yukti-finance-iocl || true

python3 -c "import secrets; print(secrets.token_urlsafe(48), end='')" | \
  gcloud secrets create yukti-persona-signing-key --project=yukti-finance-iocl --replication-policy=automatic --data-file=-
```

### Step 1: Parameterize Project Config & Isolate Ports (`:3400` / `:8195`)
1. In `yukti/backend/app/config.py`:
   - Set `GCP_PROJECT = os.getenv("TARGET_PROJECT") or os.getenv("YUKTI_GCP_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT") or "yukti-finance-iocl"`.
   - Set `COMPANY_SHORT_NAME = "IOCL"`, `COMPANY_FULL_NAME = "Indian Oil Corporation Limited"`.
   - Set `DEFAULT_ALLOWED_ORIGINS = "http://localhost:3400,http://127.0.0.1:3400"`.
2. Replace all `ongc-hr-finance-agent` project IDs in `start_cloudrun.sh`, `financial_ssot/`, `financial_build/`, `yukti/`, and `scripts/` with `yukti-finance-iocl`.
3. Set local dev frontend proxy (`yukti/frontend/server.js`, `package.json`) to `:3400` and local FastAPI backend (`yukti/backend/run.py`) to `:8195`.
4. **Verify:** `git grep "ongc-hr-finance-agent" -- ':!IOCL_ADAPTATION_PLAN.md' ':!next_steps.md' ':!build.md'` returns `0` matches.

### Step 2: Remove HR & Configure IOCL Finance-Only Personas + RBAC
1. Update `yukti/backend/app/brain/rbac_policy.yaml`, `yukti/backend/app/brain/app_users.yaml`, `yukti/contracts/answer_contract.schema.json`, `yukti/frontend/src/contracts/answerContract.ts`, and `yukti/frontend/src/personas.ts`:
   - **Leadership Personas:**
     - `CHAIRMAN` (or `CMD` alias supported in backend contract for backward compatibility): **Arvinder Singh Sahney** — *Chairman, IndianOil*
     - `DIR_FIN`: **Anuj Jain** — *Director (Finance) & CFO*
     - `DIR_REF`: **Arvind Kumar** — *Director (Refineries)*
     - `DIR_MKT`: **V. Satish Kumar** — *Director (Marketing)*
   - **IOCL Officer Grades `A–D` (Finance & Commercial Cadre — Junior Tier):**
     - `E1_FIN` (UI Chip: **`Grade A · Finance`**) — *Accounts Officer (Grade A), Corporate Finance Delhi*
     - `E2_FIN` (UI Chip: **`Grade B · Pricing & Excise`**) — *Finance Officer (Grade B), Marketing HQ Mumbai*
     - `E3_FIN` (UI Chip: **`Grade C · Treasury & FX`**) — *Manager (Finance — Grade C), Crude & Forex Desk*
     - `E4_FIN` (UI Chip: **`Grade D · Refinery Costing`**) — *Sr. Manager (Finance — Grade D), Panipat Refinery*
   - Remove HR personas (`DIR_HR`, `E1_HR..E4_HR`) from UI `PERSONA_DIRECTORY` and `/api/auth/personas` response, disable `hr_transfer` in `yukti/backend/app/agents/registry.yaml`, and remove HR subjects from UI suggestions/greetings.
2. Configure confidential Finance data classes (`fin_confidential_subledger`, `board_draft_pack`, `counterparty_credit_named`) so Leadership/Directors have `allow` while `Grade A–D` officers receive policy-compliant `aggregate` / `refuse` with the interactive **Request Access → Director Finance Approval** workflow.

### Step 3: Regenerate Yahoo Finance (`IOC.NS`), Macro Feeds & WACC
1. Run `financial_build/scripts/fetch_iocl_market_and_wacc.py` to:
   - Fetch live & 12-year daily history from Yahoo Finance (`IOC.NS`, `BZ=F`, `CL=F`, `INR=X`) into `yukti/backend/app/market/history/` (`iocl_nse_daily.json`, `brent_daily.json`, `wti_daily.json`, `inr_daily.json`, plus `grm_daily.json` Singapore Complex GRM series).
   - Write `knowledge/public_sources/market_data/manual/market_prices_seed.csv` with `IOC.NS` FY17–FY26 closing prices, shares outstanding (`1,412.12 Cr` post-bonus), market capitalization, and dividend yield.
   - Compute 10-year IOCL WACC (`FY17–FY26`) into `financial_ssot/out/fact_wacc_input.parquet` and `financial_ssot/out/fact_wacc_annual.parquet`, and load `hrfin_gold.fact_wacc_annual` & `hrfin_gold_v3.fact_wacc_annual` in BigQuery.

### Step 4: Regenerate IOCL 10-Year (`FY17–FY26`) 3-Statement, Ratios & Downstream 360 SSOT
1. Run `financial_build/scripts/build_iocl_10yr_ssot.py` to generate:
   - `financial_build/data/iocl_10yr_corporate_wide.json` (`10` FYs × `140+` columns; also mirrored to canonical filenames read by `Dockerfile` / snapshot loader or updated cleanly in `Dockerfile` + `statement_builder.py`).
   - `financial_build/data/iocl_10yr_schedule_iii_lines.json` (`240` rows: Gross Revenue, Excise Duty, Net Revenue, Crude Consumed, Purchases, Inventory Change, Employee Cost, Finance Cost, DD&A, Other Exp, PBT, Exceptional, Tax, Standalone PAT, Consolidated PAT).
   - `financial_build/data/iocl_10yr_balance_sheet_lines.json` (`240` rows).
   - `financial_build/data/iocl_10yr_cash_flow_lines.json` (`180` rows).
   - `financial_build/data/iocl_10yr_ratios_lines.json` (`180` rows: GRM $/bbl, Core GRM, Singapore GRM spread, Refining Utilization %, Distillate Yield %, Fuel & Loss %, Pipeline & Marketing MMT, ROCE, ROE, D/E, Receivable & Inventory Days).
   - `financial_ssot/dim_financial_line.csv` & `financial_ssot/out/fact_snapshot.parquet`.
   - Downstream 360 Sub-Ledgers:
     - `ssot_refinery_economics_360` (`9` standalone IOCL refineries × `10` FYs = `90` refinery rows + Pipeline/Marketing/Petchem corporate reconciliation rows so `SUM == Standalone P&L`).
     - `fact_marketing_sales` (`7` product categories × `10` FYs = `70` rows: `MS`, `HSD`, `ATF`, `Indane LPG`, `Bitumen`, `SERVO Lubes`, `Petrochemicals`).
     - `fact_pipeline_ops` (`3` network types × `10` FYs = `30` rows: `Crude Oil Pipelines`, `Product Pipelines`, `Gas Pipelines`).
     - `subsidiary_financials` (`6` group entities × `10` FYs = `60` rows: `CPCL (Chennai Petroleum)`, `Lanka IOC`, `IOC Middle East FZE`, `IndOil Montney / Overseas Upstream`, `Petronet LNG & HURL JVs`, `Consolidation Eliminations` — reconciling Standalone to Yahoo `IOC.NS` Consolidated).
2. Run `financial_build/scripts/verify_iocl_identities.py` (`200+` accounting & reconciliation checks; require `0.00 Cr` error).
3. Run `financial_build/scripts/load_iocl_bq.py` to populate both `hrfin_gold` / `hrfin_silver` / `hrfin_bronze` and `hrfin_gold_v3` / `hrfin_silver_v3` / `hrfin_bronze_v3` (plus `v_fin_statement_as_reported`, `v_fin_trend_latest`, `v_refinery_pnl_v3`, and `recon_checks`).

### Step 5: Build & Embed IOCL Annual Reports Contextual RAG + Finance Policy Corpus
1. Generate IOCL markdown dossiers in `financial_build/context_reports/`:
   - `01_IOCL_FY17_to_FY26_Chronological_MDA_Dossier.md`
   - `02_IOCL_Schedule_III_Notes_Context_Catalog.md`
   - `03_IOCL_Director_Finance_Action_Playbook.md`
   - `financial_build/04_yahoo_finance_vs_annual_report_mapping.md`
2. Run `financial_build/scripts/build_and_load_iocl_rag.py`:
   - Generates `ssot_financial_line_context` (`100+` rows across `FY17–FY26`) and loads into `hrfin_gold.ssot_financial_line_context` & `hrfin_gold_v3.ssot_financial_line_context`.
   - Generates `130+` IOCL Annual Report MD&A / Schedule III Notes / Refinery & Capex chunks + IOCL Finance Policy documents (DoA, Commodity/FX Hedging, Accounting Policy, Maharatna MoU), computes `768-d` embeddings via Vertex AI `text-embedding-005`, uploads docs to `gs://yukti-finance-iocl-docs`, and loads `hrfin_docs.financial_notes_chunks` & `hrfin_docs.doc_chunks_ar`.
   - Replaces `data_bank/landing/documents/rulebooks_clause_index.csv` and templates with IOCL Finance/DoA/Treasury/MoU policies & Board Note templates.

### Step 6: Adapt Semantic Layer, Certified SQL, CFO Levers & `NSE:IOC` DCF
1. Update `yukti/backend/app/brain/semantic_model.yaml`, `yukti/backend/app/semantic/semantic_model.yaml`, `entities.json`, `entity_aliases.yaml`, `definitions.yaml`, `compiler.py`, `statement_builder.py`, and `insight_context.py` for IOCL OMC subjects (`corporate`, `refinery_economics`, `marketing_sales`, `pipeline_ops`, `subsidiary_finance`, `mou`, `capex`, `ratios`).
2. Rewrite `yukti/backend/app/brain/certified/library.yaml` around IOCL's 30 Finance & Downstream scenarios.
3. Update `yukti/backend/app/agents/fin_diagnostics/levers.yaml` (`L01–L10` OMC levers) and `yukti/backend/app/finance/dcf/` + `dcf_agent.py` for `IOC.NS` Downstream FCFF valuation.

### Step 7: IndianOil Logos, Saffron/Navy Theme, Voice & Architecture Portal
1. Place official high-resolution IndianOil emblem in `yukti/frontend/public/brand/iocl_logo.svg`, `yukti/frontend/public/brand/iocl_logo.png`, `yukti/frontend/src/app/icon.png`, and `yukti/frontend/public/favicon.ico`.
2. Update `yukti/frontend/src/design/tokens.json` with IndianOil Saffron Orange (`#F37021` / accessible dark-on-light & light-on-dark variants) and IndianOil Navy (`#003366`), run `npm run tokens`, and pass `npm run lint:tokens && npm run lint:contrast` (`58/58` pairs).
3. Update `TopBar.tsx`, `page.tsx`, `OilOverlayBar.tsx` (adding Singapore GRM benchmark toggle), `PersonaPicker.tsx`, `live_session.py`, `ui_control.py`, export templates (`report.html.j2`, `pdf_export.py`), and `public/architecture/portal.html` to 100% IndianOil Finance identity.

### Step 8: Automated Verification Gates
```bash
cd yukti/backend && uv run pytest
cd ../frontend && npm run lint:tokens && npm run lint:contrast && npx tsc --noEmit && npm run build
uv run python ../../financial_build/scripts/run_iocl_30_questions_eval.py
```

### Step 9: Cloud Run Deployment (`yukti-iocl` in `yukti-finance-iocl`)
```bash
export CLOUDSDK_METRICS_ENVIRONMENT=datacloud.jetski
gcloud builds submit --project=yukti-finance-iocl --region=asia-south1 \
  --tag asia-south1-docker.pkg.dev/yukti-finance-iocl/yukti-repo/yukti-iocl:v1 .

gcloud run deploy yukti-iocl \
  --project=yukti-finance-iocl \
  --region=asia-south1 \
  --image=asia-south1-docker.pkg.dev/yukti-finance-iocl/yukti-repo/yukti-iocl:v1 \
  --set-secrets=YUKTI_PERSONA_SIGNING_KEY=yukti-persona-signing-key:latest \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=yukti-finance-iocl,TARGET_PROJECT=yukti-finance-iocl,YUKTI_GCP_PROJECT=yukti-finance-iocl,YUKTI_ENV=prod,YUKTI_AUTH_MODE=demo,YUKTI_PLANNER=1,YUKTI_CONTRACT_V3_FIELDS=all" \
  --min-instances=1 --max-instances=5 --memory=2Gi --cpu=2 \
  --no-cpu-throttling --session-affinity --timeout=300
```

### Step 10: Final Audit & Sponsor Commit Confirmation
- Verify live Cloud Run URL `/health` and E2E queries, update `build.md` checklist to `[x]` across Steps 0–9, and pause for explicit sponsor sign-off before `git commit` / `git push`.
