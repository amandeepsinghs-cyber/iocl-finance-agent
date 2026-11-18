#!/usr/bin/env python3
"""
Step 5.3 IOCL Finance & Governance Policy Corpus Builder:
  1. Writes `data_bank/landing/documents/rulebooks_clause_index.csv` with 40 strictly
     Finance, Treasury, Accounting, Capex & Governance clauses (`0` HR clauses!).
     - `IOCL-ACCT` carries `provenance="real"` (sourced directly from IOCL Annual Report Notes).
     - `IOCL-DOA`, `IOCL-HEDGING`, `IOCL-CAPALLOC`, `IOCL-MOU` carry `provenance="illustrative"`.
  2. Writes clean markdown policy handbooks in `data_bank/landing/documents/policies/`.
  3. Loads `hrfin_docs.rulebooks_clauses` and `hrfin_docs.silver_chunks` into BigQuery
     (`yukti-finance-iocl`, `asia-south1`, `labels={"datacloud": "jetski"}`).
"""
from __future__ import annotations

import csv
import os
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

from google.cloud import bigquery

PROJECT_ID = os.getenv("TARGET_PROJECT") or os.getenv("YUKTI_GCP_PROJECT") or "yukti-finance-iocl"
BQ_LOCATION = "asia-south1"
ATTRIBUTION_LABELS = {"datacloud": "jetski"}

assert PROJECT_ID != "ongc-hr-finance-agent", "Guardrail: must never target ONGC project"

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = REPO_ROOT / "data_bank" / "landing" / "documents"
CSV_PATH = DOCS_DIR / "rulebooks_clause_index.csv"
POLICIES_DIR = DOCS_DIR / "policies"

CLAUSES: List[Dict[str, str]] = [
    # -----------------------------------------------------------------------
    # 1. IOCL-DOA — Delegation of Financial Powers (Illustrative, 10 clauses)
    # -----------------------------------------------------------------------
    {
        "doc_id": "IOCL-DOA",
        "clause_ref": "Clause 1.0",
        "clause_title": "Constitutional Authority & Five-Tier Financial Delegation",
        "clause_text": (
            "1.1 Framed under Section 179 of the Companies Act, 2013 and Maharatna CPSE autonomy guidelines, the Board of "
            "Directors of Indian Oil Corporation Limited (IOCL) delegates financial and commercial sanction powers across "
            "five executive levels: Level 1 Board Finance Committee / Full Board; Level 2 Chairman (CMD); Level 3 Executive "
            "Committee (CMD + Whole-Time Functional Directors); Level 4 Whole-Time Functional Directors (Director Finance, "
            "Director Refineries, Director Marketing, Director Pipelines, Director BD); Level 5 Executive Directors / Refinery "
            "Unit Heads / Grade D-H Functional Heads. 1.2 Powers attach strictly to posts within approved Capital/Operating budgets."
        ),
        "maps_to_question_ids": "Q27; Q29; Q30",
        "source_basis": "IOCL-DOA-1",
        "provenance": "illustrative",
    },
    {
        "doc_id": "IOCL-DOA",
        "clause_ref": "Clause 2.1",
        "clause_title": "Spot & Term Crude Oil Cargo Procurement Thresholds",
        "clause_text": (
            "2.1 Crude oil cargo procurement through Empowered Standing Committee (Crude Import Cell — Refineries & International "
            "Trade) is governed by volume-value tiers: (a) Up to Rs 2,500 Cr per VLCC / Aframax spot cargo tender within approved "
            "monthly crude LP basket: Executive Director (International Trade) with Associate Finance concurrence; (b) Rs 2,500 Cr "
            "to Rs 5,000 Cr or non-standard opportunity high-TAN / sour crude trials: Joint sanction by Director (Refineries) and "
            "Director (Finance); (c) Term crude supply contracts exceeding Rs 5,000 Cr annual commitment or Sovereign G2G term renewals: "
            "Executive Committee / Chairman with post-facto reporting to the Board of Directors."
        ),
        "maps_to_question_ids": "Q27",
        "source_basis": "IOCL-DOA-2",
        "provenance": "illustrative",
    },
    {
        "doc_id": "IOCL-DOA",
        "clause_ref": "Clause 2.2",
        "clause_title": "VLCC & Coastal Shipping Chartering Delegation",
        "clause_text": (
            "2.2 Spot voyage charters and coastal product tanker fixtures on Worldscale benchmarks: up to Rs 75 Cr per charter party "
            "by ED (Shipping/Logistics) with Finance concurrence; Rs 75 Cr to Rs 250 Cr by Director (Refineries) + Director (Finance); "
            "multi-year time-charter Ind AS 116 vessel leases exceeding Rs 250 Cr NPV require Executive Committee / Board approval."
        ),
        "maps_to_question_ids": "Q27",
        "source_basis": "IOCL-DOA-2",
        "provenance": "illustrative",
    },
    {
        "doc_id": "IOCL-DOA",
        "clause_ref": "Clause 3.1",
        "clause_title": "Refinery Turnaround (M&I) & Maintenance Capex Sanction",
        "clause_text": (
            "3.1 Planned Refinery Maintenance & Inspection (M&I) Shutdown / Turnaround packages (FCCU, Hydrocracker, DCU catalyst "
            "replacements and furnace retubing): (a) Refinery Unit Head (ED/CGM) up to Rs 50 Cr per package under advertised tender; "
            "(b) Director (Refineries) with Director (Finance) concurrence up to Rs 200 Cr; (c) Turnaround packages Rs 200 Cr to "
            "Rs 500 Cr: Executive Committee; (d) Above Rs 500 Cr: Board of Directors / Board Finance Committee."
        ),
        "maps_to_question_ids": "Q27; Q30",
        "source_basis": "IOCL-DOA-3",
        "provenance": "illustrative",
    },
    {
        "doc_id": "IOCL-DOA",
        "clause_ref": "Clause 3.2",
        "clause_title": "Maharatna Capital Project & Joint Venture Investment Limits",
        "clause_text": (
            "3.2 Under DPE Maharatna Financial Autonomy guidelines, IOCL Board is empowered to approve brownfield refinery expansions "
            "(such as Panipat P-25, Koyali, Barauni), cross-country pipelines, petrochemical complexes, and JV/subsidiary equity "
            "commitments up to Rs 5,000 Cr per project (or 15% of Net Worth capped at Rs 5,000 Cr for a single subsidiary/JV without "
            "Cabinet/MoPNG reference), subject to mandatory appraisal by the Board Finance & Investment Committee."
        ),
        "maps_to_question_ids": "Q16; Q27; Q30",
        "source_basis": "IOCL-DOA-3",
        "provenance": "illustrative",
    },
    {
        "doc_id": "IOCL-DOA",
        "clause_ref": "Clause 4.0",
        "clause_title": "Whole-Time Functional Directors & Chairman Emergency Powers",
        "clause_text": (
            "4.1 Whole-Time Directors (Director Finance, Director Refineries, Director Marketing) exercise independent revenue and "
            "non-plan capital sanction up to Rs 150 Cr per contract with Finance concurrence. 4.2 Chairman (CMD) exercises "
            "sanctioning authority up to Rs 350 Cr, and up to Rs 500 Cr in documented refinery safety, pipeline integrity, or "
            "national fuel supply continuity emergencies, subject to reporting at the immediately succeeding Board meeting."
        ),
        "maps_to_question_ids": "Q27",
        "source_basis": "IOCL-DOA-4",
        "provenance": "illustrative",
    },
    {
        "doc_id": "IOCL-DOA",
        "clause_ref": "Clause 5.0",
        "clause_title": "Three-Tier Finance Concurrence & Prohibition of Split Tendering",
        "clause_text": (
            "5.1 Every procurement or capital commitment above Rs 10 Lakh requires sequential: (i) Administrative Approval, "
            "(ii) Technical Sanction, and (iii) Associate Finance Concurrence certifying budget availability and commercial parity. "
            "5.2 Splitting work orders, crude parcels, or EPC packages to stay below a higher approval tier (e.g., splitting a "
            "Rs 220 Cr turnaround into four Rs 55 Cr contracts) is strictly prohibited and treated as audit non-compliance."
        ),
        "maps_to_question_ids": "Q27",
        "source_basis": "IOCL-DOA-5",
        "provenance": "illustrative",
    },
    {
        "doc_id": "IOCL-DOA",
        "clause_ref": "Clause 6.0",
        "clause_title": "Board Finance & Audit Committee Reserved Approvals",
        "clause_text": (
            "6.1 Reserved exclusively for the Board / Finance Committee: (a) Annual Capital & Revenue Budgets (BE/RE); "
            "(b) Long-term NCD issuances, ECB loans, and commercial borrowing programs exceeding Rs 2,500 Cr per tranche; "
            "(c) Quarterly & Annual audited financial statements and interim/final dividend declarations; "
            "(d) Strategic M&A, subsidiary capitalization (CPCL, Lanka IOC), and impairment testing under Ind AS 36."
        ),
        "maps_to_question_ids": "Q27; Q30",
        "source_basis": "IOCL-DOA-6",
        "provenance": "illustrative",
    },
    {
        "doc_id": "IOCL-DOA",
        "clause_ref": "Clause 7.0",
        "clause_title": "Single / Proprietary OEM Catalyst & Licensor Sanctions",
        "clause_text": (
            "7.1 Procurement of proprietary refinery hydrocracker/FCC catalysts, process unit licensor packages (UOP, Axens, "
            "Haldor Topsoe), and OEM compressor spares on Proprietary Article Certificate (PAC) requires Finance Director "
            "concurrence above Rs 25 Cr and Executive Committee ratification above Rs 75 Cr."
        ),
        "maps_to_question_ids": "Q27",
        "source_basis": "IOCL-DOA-7",
        "provenance": "illustrative",
    },
    {
        "doc_id": "IOCL-DOA",
        "clause_ref": "Clause 8.0",
        "clause_title": "Confidentiality of Unpublished Board Packs, Tender Bids & Sub-Ledgers",
        "clause_text": (
            "8.1 Unpublished Board Finance Committee draft agenda packs, Q1/quarterly pre-release refinery margin sub-ledgers, "
            "live crude tender bid tabulations, and counterparty commercial pricing discounts are classified CONFIDENTIAL under "
            "IOCL Information Security & SEBI PIT Regulations. Access is restricted strictly to Chairman, Whole-Time Directors, "
            "and authorized Board Secretariat / Treasury Officers; Grade A-D officers must submit formal Access Requests approved by Director (Finance)."
        ),
        "maps_to_question_ids": "Q27; Q29",
        "source_basis": "IOCL-DOA-8",
        "provenance": "illustrative",
    },
    # -----------------------------------------------------------------------
    # 2. IOCL-HEDGING — Commodity & Forex Risk Management (Illustrative, 8 clauses)
    # -----------------------------------------------------------------------
    {
        "doc_id": "IOCL-HEDGING",
        "clause_ref": "Clause 1.0",
        "clause_title": "Objectives & Commodity Risk Governance Structure",
        "clause_text": (
            "1.1 The IOCL Commodity & Forex Risk Management Policy establishes disciplined hedging guardrails to protect Core GRM, "
            "mitigate NRV inventory write-downs, and stabilize USD/INR debt servicing. 1.2 Overseen by the Board Risk Management "
            "Committee (RMC) and executed jointly by the Executive Risk Committee (Director Finance + Director Refineries + ED Treasury)."
        ),
        "maps_to_question_ids": "Q28",
        "source_basis": "IOCL-HDG-1",
        "provenance": "illustrative",
    },
    {
        "doc_id": "IOCL-HEDGING",
        "clause_ref": "Clause 2.0",
        "clause_title": "Unpriced Crude Cargo-in-Transit Exposure Window",
        "clause_text": (
            "2.1 IOCL faces ~38-45 days of pricing mismatch between crude Bill-of-Lading loading and Indian coastal refinery intake. "
            "2.2 The Treasury Commodity Desk is authorized to hedge 25% to 50% of net unpriced Brent/Dubai cargo-in-transit volumes "
            "via OTC ICE Brent swaps and zero-cost put-spread collars with tenors up to 90 days."
        ),
        "maps_to_question_ids": "Q28",
        "source_basis": "IOCL-HDG-2",
        "provenance": "illustrative",
    },
    {
        "doc_id": "IOCL-HEDGING",
        "clause_ref": "Clause 3.0",
        "clause_title": "Refining Crack-Spread Hedging Band (Gasoil, ATF & Gasoline)",
        "clause_text": (
            "3.1 To lock cyclical refining margins when Singapore Gasoil 10ppm or Jet/Kero regrade spreads exceed 1-sigma historical "
            "thresholds, IOCL may hedge 25% to 35% of rolling 6-month discretionary exportable distillate surplus (Gasoil/ATF/MS "
            "Singapore swaps) up to a rolling 12-month horizon with Director (Finance) and Director (Refineries) sign-off."
        ),
        "maps_to_question_ids": "Q28",
        "source_basis": "IOCL-HDG-3",
        "provenance": "illustrative",
    },
    {
        "doc_id": "IOCL-HEDGING",
        "clause_ref": "Clause 4.0",
        "clause_title": "Inventory Price Protection & Core Operational Buffer Policy",
        "clause_text": (
            "4.1 Core minimum operating stock (~35 MMT pipeline/tank bottoms) is unhedged long-term capital, whereas discretionary "
            "seasonal inventory builds above norm (DIO > 55 days) require dynamic delta-protection put spreads whenever Brent "
            "backwardation flips to contango or volatility exceeds 35% annualized, guarding against FY20-style NRV write-downs."
        ),
        "maps_to_question_ids": "Q04; Q28",
        "source_basis": "IOCL-HDG-4",
        "provenance": "illustrative",
    },
    {
        "doc_id": "IOCL-HEDGING",
        "clause_ref": "Clause 5.0",
        "clause_title": "USD/INR Foreign Currency Debt & Import Bill Forward Cover",
        "clause_text": (
            "5.1 IOCL maintains a rolling 50% to 75% hedge ratio on short-term (< 6 month) USD Letters of Credit / Buyer's Credit "
            "and crude import payables via deliverable forwards and seagull option structures. 5.2 Long-term ECBs and USD bonds "
            "shall maintain minimum 50% principal + coupon hedge via Cross-Currency Interest Rate Swaps (CCIRS) unless matched "
            "against natural USD export/ATF/international subsidiary inflows."
        ),
        "maps_to_question_ids": "Q23; Q28",
        "source_basis": "IOCL-HDG-5",
        "provenance": "illustrative",
    },
    {
        "doc_id": "IOCL-HEDGING",
        "clause_ref": "Clause 6.0",
        "clause_title": "Strict Prohibition on Speculative / Naked Derivatives",
        "clause_text": (
            "6.1 Under RBI FEMA guidelines and IOCL Board mandate, all commodity and FX derivatives must map 1:1 to underlying "
            "physical crude cargoes, refined product cracks, or foreign currency liabilities. Selling uncovered naked calls, "
            "leveraged exotic knock-in structures, or net-long speculative positions exceeding underlying exposure is strictly barred."
        ),
        "maps_to_question_ids": "Q28",
        "source_basis": "IOCL-HDG-6",
        "provenance": "illustrative",
    },
    {
        "doc_id": "IOCL-HEDGING",
        "clause_ref": "Clause 7.0",
        "clause_title": "ISDA Counterparty Credit Exposure Ceilings (Confidential Named Limits)",
        "clause_text": (
            "7.1 Derivative trades may be executed only with RBI Category-I Authorised Dealer banks and clearing houses rated AA-/A1+ "
            "or higher under executed ISDA Master Agreements. Single-counterparty Mark-to-Market exposure limits and bank-wise credit "
            "utilization matrices are confidential treasury controls restricted to CMD, Director (Finance), and Grade C+ Treasury leads."
        ),
        "maps_to_question_ids": "Q28; Q29",
        "source_basis": "IOCL-HDG-7",
        "provenance": "illustrative",
    },
    {
        "doc_id": "IOCL-HEDGING",
        "clause_ref": "Clause 8.0",
        "clause_title": "Ind AS 109 Hedge Accounting & Quarterly MTM Reporting",
        "clause_text": (
            "8.1 Hedge effectiveness is tested quarterly under Ind AS 109 (80%-125% dollar-offset / regression corridor); effective "
            "cash-flow hedge gains/losses route through Other Comprehensive Income (OCI) Cash Flow Hedge Reserve until inventory "
            "recognition, while ineffective portions and unhedged FX restatements flow to Note 33 / Finance Costs."
        ),
        "maps_to_question_ids": "Q28",
        "source_basis": "IOCL-HDG-8",
        "provenance": "illustrative",
    },
    # -----------------------------------------------------------------------
    # 3. IOCL-ACCT — Statutory Ind AS Accounting Policies (REAL — from Annual Reports, 8 clauses)
    # -----------------------------------------------------------------------
    {
        "doc_id": "IOCL-ACCT",
        "clause_ref": "Note 1 & 28",
        "clause_title": "Ind AS 115 Revenue Recognition: Gross Turnover vs Central Excise Duty",
        "clause_text": (
            "Per IOCL Annual Report Significant Accounting Policies & Note 28, Revenue from Operations is recognized at fair value "
            "upon transfer of control of petroleum products, petrochemicals, and natural gas. Because Central Excise Duty is an "
            "indirect levy collected by IOCL as principal manufacturer/refiner, Gross Revenue from Operations includes Central Excise "
            "Duty (Rs 1,02,066.54 Cr in FY26 out of Rs 8,86,224.41 Cr Gross Revenue), and Excise Duty is presented as a separate "
            "expense line on the face of Statement of Profit & Loss, yielding Net Revenue of Rs 7,84,157.87 Cr."
        ),
        "maps_to_question_ids": "Q01; Q03",
        "source_basis": "IOCL-AR-NOTE28",
        "provenance": "real",
    },
    {
        "doc_id": "IOCL-ACCT",
        "clause_ref": "Note 1 & 11",
        "clause_title": "Ind AS 2 Inventories Valuation: Lower of FIFO Cost or NRV",
        "clause_text": (
            "Per IOCL Annual Report Note 11, Raw Materials (crude oil) and Finished Petroleum Products are valued at the lower of "
            "cost (determined on First-In-First-Out / weighted moving average formula across refineries/depots) and Net Realizable "
            "Value (NRV). Sharp Brent price declines trigger NRV write-downs (including Rs 11,305.00 Cr classified as an Exceptional "
            "Item in FY20 during Q4 COVID-19 price collapse), explaining gaps between Reported GRM and Core GRM."
        ),
        "maps_to_question_ids": "Q04; Q15",
        "source_basis": "IOCL-AR-NOTE11",
        "provenance": "real",
    },
    {
        "doc_id": "IOCL-ACCT",
        "clause_ref": "Note 1 & 19A",
        "clause_title": "Ind AS 116 Leases: Coastal Time-Charters, Tank-Trucks & Retail Outlets",
        "clause_text": (
            "Effective FY20 (1 April 2019), IOCL adopted Ind AS 116 Leases using modified retrospective approach, recognizing Right-of-Use "
            "(ROU) assets inside PPE (Note 2) and corresponding Lease Liabilities (Note 19A: Rs 9,480 Cr non-current in FY26) for "
            "coastal oil tankers, tank-truck fleets, LNG/LPG terminals, and retail outlet land sites. Lease expense shifted from "
            "operating rentals (Note 33) into DD&A (Note 2) and Finance Costs (Note 34)."
        ),
        "maps_to_question_ids": "Q13; Q14",
        "source_basis": "IOCL-AR-NOTE19A",
        "provenance": "real",
    },
    {
        "doc_id": "IOCL-ACCT",
        "clause_ref": "Note 35",
        "clause_title": "Ind AS 12 Income Taxes: Section 115BAA (25.168% Regime)",
        "clause_text": (
            "In FY20, IOCL exercised the irrevocable option permitted under Section 115BAA of the Income Tax Act, 1961 (enacted via "
            "Taxation Laws Amendment Ordinance 2019), reducing its statutory corporate income tax rate to 25.168% (22% base + 10% "
            "surcharge + 4% cess) while foregone MAT credits and remeasured deferred tax liabilities yielded an effective FY26 tax "
            "rate of 24.56% (Rs 11,981.99 Cr total tax on Rs 48,784.41 Cr PBT)."
        ),
        "maps_to_question_ids": "Q01; Q02",
        "source_basis": "IOCL-AR-NOTE35",
        "provenance": "real",
    },
    {
        "doc_id": "IOCL-ACCT",
        "clause_ref": "Ind AS 108",
        "clause_title": "Operating Segment Disclosures: Petroleum Products, Petrochemicals & Others",
        "clause_text": (
            "Per IOCL Annual Report Segment Reporting under Ind AS 108, IOCL reports three operating segments to the Chief Operating "
            "Decision Maker (CMD & Functional Directors): (1) Sale of Petroleum Products (refining + marketing wholesale/retail), "
            "(2) Sale of Petrochemicals (Panipat cracker, PX/PTA, Gujarat polymer units), and (3) Other Business Activities (gas "
            "marketing, pipelines services, E&P/upstream & green energy). Unallocable corporate borrowings and interest sit in corporate pool."
        ),
        "maps_to_question_ids": "Q12",
        "source_basis": "IOCL-AR-SEG",
        "provenance": "real",
    },
    {
        "doc_id": "IOCL-ACCT",
        "clause_ref": "Note 4 & 40",
        "clause_title": "Ind AS 110 / 28 Consolidation: Standalone vs IOC.NS Group Entities",
        "clause_text": (
            "Consolidated Financial Statements (IOC.NS) aggregate IOCL Standalone (PAT Rs 36,802.42 Cr in FY26) with controlled "
            "subsidiaries — notably Chennai Petroleum Corporation Limited (CPCL, 51.89%), Lanka IOC PLC (75.12%), IOC Middle East "
            "FZE (100%), and IndOil Global B.V. (100%) — plus equity-accounted Joint Ventures including Hindustan Urvarak & Rasayan "
            "(HURL, 29.67%) and Petronet LNG (12.50%), arriving at FY26 Consolidated PAT of Rs 43,677.32 Cr after inter-company eliminations."
        ),
        "maps_to_question_ids": "Q01; Q06",
        "source_basis": "IOCL-AR-CONSOL",
        "provenance": "real",
    },
    {
        "doc_id": "IOCL-ACCT",
        "clause_ref": "Note 24-25",
        "clause_title": "Indane LPG Consumer Security Deposits & Government LPG Buffer/Grants",
        "clause_text": (
            "IOCL recognizes refundable security deposits received from domestic Indane LPG consumers against cylinders and pressure "
            "regulators under Other Financial Liabilities (exceeding Rs 34,000 Cr float). Government compensation for under-recoveries "
            "on domestic LPG (such as the Rs 10,801.00 Cr one-time grant in FY23) is recognized in Revenue from Operations under Ind AS 20 "
            "upon sanction order confirmation from MoPNG."
        ),
        "maps_to_question_ids": "Q05; Q15",
        "source_basis": "IOCL-AR-NOTE24",
        "provenance": "real",
    },
    {
        "doc_id": "IOCL-ACCT",
        "clause_ref": "Note 2",
        "clause_title": "Ind AS 16 Useful Lives: Refineries (25 yrs), Pipelines (30 yrs) & Tanks",
        "clause_text": (
            "Property, Plant & Equipment (Net Block Rs 1,87,894.12 Cr in FY26, excl. Rs 82,577.56 Cr CWIP) is depreciated on straight-line method over "
            "Schedule II / technical assessed useful lives: Refinery Process Plants & Catalysts (15-25 years), Cross-Country "
            "Pipelines (30 years), Storage Tanks & Railway Sidings (15-30 years), and Retail Outlet Dispensing Assets (15 years). "
            "Major turnaround inspection costs are capitalized and amortized over the 3-4 year statutory turnaround cycle."
        ),
        "maps_to_question_ids": "Q13; Q16",
        "source_basis": "IOCL-AR-NOTE2",
        "provenance": "real",
    },
    # -----------------------------------------------------------------------
    # 4. IOCL-CAPALLOC — Capital Allocation, Hurdle Rate & De-Leveraging (Illustrative, 8 clauses)
    # -----------------------------------------------------------------------
    {
        "doc_id": "IOCL-CAPALLOC",
        "clause_ref": "Clause 1.0",
        "clause_title": "Stage-Gate Capex Appraisal & 12% Post-Tax Equity IRR Hurdle Rate",
        "clause_text": (
            "1.1 All new discretionary capital expenditure proposals above Rs 100 Cr must clear Stage-Gate Gate-2 (DPR feasibility) "
            "and Gate-3 (Investment Sanction) demonstrating a minimum Post-Tax Equity IRR of >= 12.0% (or >= WACC + 250 bps) under "
            "conservative base-case crack and margin assumptions, verified independently by Corporate Finance Appraisal Group."
        ),
        "maps_to_question_ids": "Q16; Q25; Q30",
        "source_basis": "IOCL-CAP-1",
        "provenance": "illustrative",
    },
    {
        "doc_id": "IOCL-CAPALLOC",
        "clause_ref": "Clause 2.0",
        "clause_title": "Brownfield Refinery & Petchem Expansion Priority Queue",
        "clause_text": (
            "2.1 Priority capital budget allocation targets high-return brownfield refining capacity and petrochemical integration "
            "lowering import dependence: Panipat P-25 (15 -> 25 MMTPA + PX/PTA), Gujarat Koyali (13.7 -> 18 MMTPA), Barauni (6 -> 9 "
            "MMTPA), and Paradip product pipeline spurs. Projects experiencing > 15% cost escalation or > 6 months CWIP slippage trigger "
            "mandatory Director (Finance) & Board Audit re-appraisal."
        ),
        "maps_to_question_ids": "Q16; Q25",
        "source_basis": "IOCL-CAP-2",
        "provenance": "illustrative",
    },
    {
        "doc_id": "IOCL-CAPALLOC",
        "clause_ref": "Clause 3.0",
        "clause_title": "DIPAM Dividend Payout Policy (30%-40% PAT / 5% Net Worth)",
        "clause_text": (
            "3.1 In alignment with DIPAM CPSE Capital Restructuring Guidelines, IOCL targets an annual dividend payout of 30%-40% "
            "of Standalone Profit After Tax (or 5% of Net Worth, whichever is higher), balanced against debt-reduction milestones "
            "and peak brownfield Capex outflows (e.g., FY26 DPS Rs 8.50/share = Rs 12,003.05 Cr = 32.6% payout)."
        ),
        "maps_to_question_ids": "Q18; Q30",
        "source_basis": "IOCL-CAP-3",
        "provenance": "illustrative",
    },
    {
        "doc_id": "IOCL-CAPALLOC",
        "clause_ref": "Clause 4.0",
        "clause_title": "Target Capital Structure Guardrail (D/E <= 0.70x & AAA Rating)",
        "clause_text": (
            "4.1 IOCL maintains a through-cycle Debt-to-Equity guardrail of <= 0.70x (with strategic target <= 0.55x during normal "
            "refining margins, achieved at 0.54x in FY26) and Net Debt / EBITDA <= 2.0x to safeguard domestic AAA credit ratings and "
            "keep pretax borrowing cost competitive below 7.25%."
        ),
        "maps_to_question_ids": "Q14; Q24; Q25",
        "source_basis": "IOCL-CAP-4",
        "provenance": "illustrative",
    },
    {
        "doc_id": "IOCL-CAPALLOC",
        "clause_ref": "Clause 5.0",
        "clause_title": "Net-Zero 2046 Green Capex & Renewable Power Wheeling Pool",
        "clause_text": (
            "5.1 IOCL ring-fences 10%-15% of annual capital budget toward Net-Zero Operational Emissions (Scope 1 & 2) by 2046, "
            "spanning Panipat Green Hydrogen electrolyzers, 2G/3G ethanol biorefineries, compressed biogas (CBG) plants, EV "
            "charging/battery-swapping hubs, and captive solar wheeling targeting 35% green refinery grid share."
        ),
        "maps_to_question_ids": "Q16; Q20; Q25",
        "source_basis": "IOCL-CAP-5",
        "provenance": "illustrative",
    },
    {
        "doc_id": "IOCL-CAPALLOC",
        "clause_ref": "Clause 6.0",
        "clause_title": "Working Capital DIO Ceiling (<= 55.6 Days) & OCF Sweep",
        "clause_text": (
            "6.1 Cash released from reducing crude & product inventory days (DIO target <= 55.6 days vs 58.6 days in FY26) and "
            "MoPNG LPG buffer reimbursements shall be swept first to retire high-cost short-term Commercial Paper and Working "
            "Capital Demand Loans (WCDL) before discretionary treasury deployment."
        ),
        "maps_to_question_ids": "Q15; Q17; Q25",
        "source_basis": "IOCL-CAP-6",
        "provenance": "illustrative",
    },
    {
        "doc_id": "IOCL-CAPALLOC",
        "clause_ref": "Clause 7.0",
        "clause_title": "Subsidiary Capital Calls & CPCL / Overseas Upstream Gating",
        "clause_text": (
            "7.1 Any fresh equity infusion or corporate guarantee for CPCL, Lanka IOC, or overseas upstream/petchem JVs requires "
            "parent standalone FCF coverage >= 1.2x post-dividend and demonstrated standalone ROCE recovery above 12%."
        ),
        "maps_to_question_ids": "Q06; Q16",
        "source_basis": "IOCL-CAP-7",
        "provenance": "illustrative",
    },
    {
        "doc_id": "IOCL-CAPALLOC",
        "clause_ref": "Clause 8.0",
        "clause_title": "Bonus Share Capitalization & Investor Disclosures",
        "clause_text": (
            "8.1 Bonus capitalizations (historically 1:1 in FY18 and 1:2 in FY23) require Free Reserves / Securities Premium "
            "certification by Statutory Auditors and post-bonus EPS/DPS pro-forma adjustment in Investor Relations KPI tables."
        ),
        "maps_to_question_ids": "Q18",
        "source_basis": "IOCL-CAP-8",
        "provenance": "illustrative",
    },
    # -----------------------------------------------------------------------
    # 5. IOCL-MOU — DPE Maharatna MoU Performance Governance (Illustrative, 6 clauses)
    # -----------------------------------------------------------------------
    {
        "doc_id": "IOCL-MOU",
        "clause_ref": "Clause 1.0",
        "clause_title": "Maharatna MoU Composite Framework & Weightage Structure",
        "clause_text": (
            "1.1 Annual Memorandum of Understanding (MoU) signed between IOCL and Ministry of Petroleum & Natural Gas (MoPNG) / "
            "Department of Public Enterprises (DPE) assigns 100 composite points across: Financial Parameters (Net Revenue, Operating "
            "EBITDA/Net Revenue %, Capex Spend, PAT/Net Worth = 50%), Downstream Operational Efficiency (Refinery Throughput MMT, "
            "Distillate Yield, Pipeline Utilization, MBN Energy Index = 30%), and Energy Transition / ESG / Governance (20%)."
        ),
        "maps_to_question_ids": "Q20",
        "source_basis": "IOCL-MOU-1",
        "provenance": "illustrative",
    },
    {
        "doc_id": "IOCL-MOU",
        "clause_ref": "Clause 2.0",
        "clause_title": "Rating Bands: Excellent (>= 90 Score) vs Very Good (>= 70 Score)",
        "clause_text": (
            "2.1 MoU Excellent rating threshold requires composite score >= 90/100 (or >= 4.00/5.00 normalized index). FY25 composite "
            "rating finished 'Very Good' (3.82/5.00) amid compressed diesel cracks, whereas FY26 projected 'Excellent' (4.35/5.00) "
            "driven by record 75.451 MMT throughput, Rs 7,84,157.87 Cr Net Revenue, and Rs 34,210 Cr Capex execution."
        ),
        "maps_to_question_ids": "Q20",
        "source_basis": "IOCL-MOU-2",
        "provenance": "illustrative",
    },
    {
        "doc_id": "IOCL-MOU",
        "clause_ref": "Clause 3.0",
        "clause_title": "Refinery Specific Energy Consumption (MBN) & Distillate Yield Targets",
        "clause_text": (
            "3.1 MoU operational efficiency KPIs track corporate weighted MBN (Thousand British Thermal Units per Barrel per Energy "
            "Factor), Fuel & Loss % (FY26 8.20%, FY27 target <= 7.90%), and Distillate Yield % (FY26 82.8%, FY27 target >= 83.3%) "
            "across all 9 standalone refineries."
        ),
        "maps_to_question_ids": "Q09; Q20",
        "source_basis": "IOCL-MOU-3",
        "provenance": "illustrative",
    },
    {
        "doc_id": "IOCL-MOU",
        "clause_ref": "Clause 4.0",
        "clause_title": "Procurement Compliance: GeM Portal & MSE 25% Sourcing Mandate",
        "clause_text": (
            "4.1 Mandatory DPE MoU compliance tracks procurement of goods and services through Government e-Marketplace (GeM), "
            "achieving >= 25% annual procurement from Micro & Small Enterprises (MSEs), and MSME Trade Receivable TReDS settlement "
            "within 45 days."
        ),
        "maps_to_question_ids": "Q20",
        "source_basis": "IOCL-MOU-4",
        "provenance": "illustrative",
    },
    {
        "doc_id": "IOCL-MOU",
        "clause_ref": "Clause 5.0",
        "clause_title": "Energy Transition Milestones: Biofuels, Ethanol E20 & Green Hydrogen",
        "clause_text": (
            "5.1 MoU ESG KPIs measure Ethanol-Blended Petrol ratio (E15/E20 rollout), Compressed Bio-Gas (SATAT) off-take, Solar "
            "photovoltaic installations across retail outlets, and Panipat Green Hydrogen plant commissioning milestones."
        ),
        "maps_to_question_ids": "Q20",
        "source_basis": "IOCL-MOU-5",
        "provenance": "illustrative",
    },
    {
        "doc_id": "IOCL-MOU",
        "clause_ref": "Clause 6.0",
        "clause_title": "Quarterly Chairman & Director (Finance) Review & Internal Audit",
        "clause_text": (
            "6.1 Performance against MoU targets is reviewed monthly by Functional Directors and quarterly by Chairman and Audit "
            "Committee prior to half-yearly MoPNG / DPE submission, ensuring zero surprise variance at March 31 year-end."
        ),
        "maps_to_question_ids": "Q20; Q30",
        "source_basis": "IOCL-MOU-6",
        "provenance": "illustrative",
    },
]

TITLES = {
    "IOCL-DOA": "IOCL Delegation of Financial Powers & Procurement Governance (IOCL-DOA)",
    "IOCL-HEDGING": "IOCL Commodity Crack, Crude & USD/INR Forex Risk Management Policy (IOCL-HEDGING)",
    "IOCL-ACCT": "IOCL Ind AS Statutory Accounting Policies (Annual Report Notes 1–40) (IOCL-ACCT)",
    "IOCL-CAPALLOC": "IOCL Capital Allocation, Stage-Gate Capex & Dividend Policy (IOCL-CAPALLOC)",
    "IOCL-MOU": "IOCL Maharatna DPE / MoPNG MoU Performance Governance Framework (IOCL-MOU)",
}


def main() -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    POLICIES_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Write rulebooks_clause_index.csv
    fieldnames = [
        "doc_id",
        "clause_ref",
        "clause_title",
        "clause_text",
        "maps_to_question_ids",
        "source_basis",
        "provenance",
    ]
    with CSV_PATH.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(CLAUSES)
    print(f"Wrote {CSV_PATH}: {len(CLAUSES)} clauses (0 HR clauses)", flush=True)

    # 2. Write policy markdown handbooks
    grouped: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for row in CLAUSES:
        grouped[row["doc_id"]].append(row)

    for doc_id, rows in grouped.items():
        md_lines = [
            f"# {TITLES[doc_id]}",
            "",
            f"- **Document ID:** `{doc_id}`",
            f"- **Provenance:** `{rows[0]['provenance']}`",
            f"- **Scope:** 100% IOCL Finance, Treasury, Accounting, Capex & Downstream Governance",
            "",
            "---",
            "",
        ]
        for r in rows:
            md_lines.extend(
                [
                    f"## {r['clause_ref']} — {r['clause_title']}",
                    f"*Maps to: `{r['maps_to_question_ids']}` | Source Basis: `{r['source_basis']}` | Provenance: `{r['provenance']}`*",
                    "",
                    r["clause_text"],
                    "",
                ]
            )
        p = POLICIES_DIR / f"{doc_id}.md"
        p.write_text("\n".join(md_lines), encoding="utf-8")
        print(f"Wrote {p}", flush=True)

    # 3. Load BigQuery hrfin_docs.rulebooks_clauses & hrfin_docs.silver_chunks
    bq = bigquery.Client(project=PROJECT_ID, location=BQ_LOCATION)
    ds = bigquery.Dataset(f"{PROJECT_ID}.hrfin_docs")
    ds.location = BQ_LOCATION
    bq.create_dataset(ds, exists_ok=True)

    rb_schema = [
        bigquery.SchemaField("doc_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("clause_ref", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("clause_title", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("clause_text", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("maps_to_question_ids", "STRING"),
        bigquery.SchemaField("source_basis", "STRING"),
        bigquery.SchemaField("provenance", "STRING", mode="REQUIRED"),
    ]
    rb_table = f"{PROJECT_ID}.hrfin_docs.rulebooks_clauses"
    bq.load_table_from_json(
        CLAUSES,
        rb_table,
        job_config=bigquery.LoadJobConfig(
            schema=rb_schema,
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
            labels=ATTRIBUTION_LABELS,
        ),
    ).result()
    print(f"Loaded {rb_table}: {bq.get_table(rb_table).num_rows} rows", flush=True)

    silver_rows = [
        {
            "chunk_id": f"{c['doc_id']}::{c['clause_ref']}",
            "doc_id": c["doc_id"],
            "clause_ref": c["clause_ref"],
            "heading": c["clause_title"],
            "text": c["clause_text"],
            "questions_served": c["maps_to_question_ids"],
            "source_basis": c["source_basis"],
            "provenance": c["provenance"],
        }
        for c in CLAUSES
    ]
    sc_schema = [
        bigquery.SchemaField("chunk_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("doc_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("clause_ref", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("heading", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("text", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("questions_served", "STRING"),
        bigquery.SchemaField("source_basis", "STRING"),
        bigquery.SchemaField("provenance", "STRING", mode="REQUIRED"),
    ]
    sc_table = f"{PROJECT_ID}.hrfin_docs.silver_chunks"
    bq.load_table_from_json(
        silver_rows,
        sc_table,
        job_config=bigquery.LoadJobConfig(
            schema=sc_schema,
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
            labels=ATTRIBUTION_LABELS,
        ),
    ).result()
    print(f"Loaded {sc_table}: {bq.get_table(sc_table).num_rows} rows", flush=True)


if __name__ == "__main__":
    main()
