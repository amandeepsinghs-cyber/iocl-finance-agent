# Cross-Walk Mapping: Yahoo Finance (`IOC.NS`) ↔ IOCL Annual Report (Schedule III) ↔ BigQuery SSOT

This document defines the exact mathematical and schema mapping between **Yahoo Finance (`https://finance.yahoo.com/quote/IOC.NS/financials/`)**, **IOCL’s Official Annual Reports (Ind-AS Schedule III & Notes 2–35)**, and **Yukti’s BigQuery Financial Cube (`yukti-finance-iocl.hrfin_gold`)**.

---

## 1. Critical Distinction: Standalone IOCL vs. Consolidated Group (`IOC.NS`)

| Metric (FY25 / FY26) | IOCL Standalone (Annual Report Primary Schedule III) | IOCL Consolidated (`IOC.NS` on Yahoo Finance & Group AR) | Reconciliation Bridge |
|---|---|---|---|
| **Gross Revenue from Operations** | **`₹8,45,513.00 Cr`** (`FY25`) / **`₹8,86,224.41 Cr`** (`FY26`) | **`₹8,58,940.00 Cr`** (`FY25`) / **`₹9,02,480.00 Cr`** (`FY26`) | Adds subsidiary **CPCL** (Manali 10.5 MMTPA refinery), **Lanka IOC**, **IOC Middle East**, & **IndOil Overseas** revenue, net of inter-company crude/product eliminations (`CONSOL_ADJ`). |
| **Excise Duty (Note 28)** | **`₹89,562.99 Cr`** (`FY25`) / **`₹1,02,066.54 Cr`** (`FY26`) | Included inside Gross Revenue / Tax adjustment on Yahoo | Ind-AS 115 includes Central Excise Duty in Revenue (`Gross`) and expenses it on the face of P&L (`Excise Duty`), whereas Yahoo Finance may display Net Revenue or Gross Revenue depending on period adjustment. |
| **Net Revenue (Net of Excise)** | **`₹7,55,950.01 Cr`** (`FY25`) / **`₹7,84,157.87 Cr`** (`FY26`) | — | Exact identity: `gross_revenue_inr_cr - excise_duty_inr_cr = net_revenue_inr_cr` (`0.00 Cr` plug). |
| **Standalone vs. Consolidated PAT** | **`₹12,961.57 Cr`** (`FY25`) / **`₹36,802.42 Cr`** (`FY26`) | **`₹13,598.40 Cr`** (`FY25`) / **`₹39,639.54 Cr`** (`FY26`) | Reconciled in `hrfin_silver.subsidiary_financials`: Standalone PAT (`₹36,802.42 Cr`) + Group entities & JVs (`Petronet LNG`, `HURL`, `CPCL`, `Lanka IOC`, `IOCME`, `CONSOL_ADJ`) `+₹2,837.12 Cr` = `₹39,639.54 Cr`. |

---

## 2. Line-by-Line P&L Mapping Table (Schedule III ↔ Yahoo `IOC.NS` ↔ BigQuery SSOT)

| # | IOCL Schedule III Line | Yahoo Finance (`IOC.NS`) Equivalent | BigQuery Column (`ssot_corporate_annual_360`) | Reconciliation Formula |
|---:|---|---|---|---|
| **1** | **I. Revenue from Operations (Gross)** *(Note 28)* | `Total Revenue` *(gross)* | `gross_revenue_inr_cr` | `petroleum_products_revenue_inr_cr + petchem_and_other_op_rev_inr_cr` |
| **2** | **II. Other Income** *(Note 29)* | `Other Income Expense` | `other_income_inr_cr` | Interest, subsidiary/JV dividends & miscellaneous |
| **3** | **III. Total Income (`I + II`)** | `Total Revenue + Other Income` | `total_income_inr_cr` | `gross_revenue_inr_cr + other_income_inr_cr` |
| **4** | **Excise Duty on Sale of Goods** *(Note 28)* | *(Lumped in Cost of Revenue / Excise)* | `statutory_levies_total_inr_cr` (`excise_duty_inr_cr`) | Union Central Excise remitted on MS/HSD/ATF/etc. |
| **5** | **Revenue from Operations (Net of Excise)** | `Normalized Net Revenue` | `net_revenue_inr_cr` | `gross_revenue_inr_cr - excise_duty_inr_cr` |
| **6** | **Cost of Materials Consumed** *(Note 30)* | `Cost Of Revenue` *(crude part)* | `cost_of_materials_consumed_inr_cr` | Crude oil & feedstock consumed across 9 refineries |
| **7** | **Purchases of Stock-in-Trade** | `Cost Of Revenue` *(traded part)* | `purchases_stock_in_trade_inr_cr` | Traded finished products, CPCL off-take & LNG |
| **8** | **Changes in Inventories** | `Cost Of Revenue` *(inventory adj)* | `inventory_change_inr_cr` | Opening less closing FG/WIP/Stock-in-Trade |
| **9** | **Employee Benefits Expense** *(Note 32)* | `Selling General & Admin` | `employee_benefit_net_pnl_inr_cr` | Staff salaries, PF & superannuation benefits |
| **10** | **Other Operating Expenses** *(Note 33)* | `Other Operating Expenses` | `other_expenses_inr_cr` | Power & fuel, stores, repairs, bottling, freight & FX |
| **11** | **EBITDA / PBIDT** | `Normalized EBITDA` | `ebitda_inr_cr` | `total_income - excise - (materials + purchases + inv_chg + emp + other_exp)` |
| **12** | **Depreciation & Amortisation (DD&A)** *(Note 2)* | `Reconciled Depreciation` | `dda_inr_cr` | Refinery, petchem & pipeline depreciation |
| **13** | **Finance Costs** *(Note 34)* | `Interest Expense` | `finance_costs_inr_cr` | NCD/term loan/CP interest + Ind AS 116 lease interest |
| **14** | **IV. Total Expenses** | `Total Expenses` | `total_expenses_inr_cr` | Sum of Lines `4 + 6 + 7 + 8 + 9 + 10 + 12 + 13` |
| **15** | **V. PBT before Exceptional Items** | `Pretax Income` *(pre-unusual)* | `pbt_pre_exc_inr_cr` | `total_income_inr_cr - total_expenses_inr_cr` |
| **16** | **VI. Exceptional Items** *(FY20 `-₹11,305 Cr`)* | `Special Income/Charges` | `exceptional_items_inr_cr` | COVID crude NRV inventory write-down |
| **17** | **VII. Profit Before Tax (PBT)** | `Pretax Income` | `pbt_inr_cr` | `pbt_pre_exc_inr_cr + exceptional_items_inr_cr` |
| **18** | **VIII. Total Tax Expense** *(Note 35)* | `Tax Provision` | `tax_expense_total_inr_cr` | `current_tax_inr_cr + deferred_tax_inr_cr` |
| **19** | **IX. Profit After Tax (PAT)** | `Net Income` *(Standalone vs `IOC.NS` Consolidated)* | `pat_inr_cr` / `consolidated_pat_inr_cr` | `pbt_inr_cr - tax_expense_total_inr_cr` |

---

## 3. Downstream 360 Sub-Ledger Tables (`hrfin_gold` & `hrfin_silver`)
- `hrfin_gold.ssot_refinery_economics_360` / `v_refinery_pnl_v3`: `9` IOCL Standalone Refineries (`70.25 MMTPA`) + `3` division reconciliation rows × `10` FYs -> `SUM == Corporate Throughput (75.451 MMT)` and `SUM == Corporate Standalone P&L (0.00 Cr delta)`.
- `hrfin_gold.fact_marketing_sales`: `7` product categories × `10` FYs -> `SUM == Corporate Product Sales (105.117 MMT)`.
- `hrfin_gold.fact_pipeline_ops`: `3` pipeline network types × `10` FYs -> `SUM == Corporate Pipeline Throughput (105.556 MMT)`.
- `hrfin_silver.subsidiary_financials`: `6` group entities incl. `CPCL` (`10.50 MMTPA` subsidiary) -> reconciles Standalone PAT to `IOC.NS` Consolidated PAT.
