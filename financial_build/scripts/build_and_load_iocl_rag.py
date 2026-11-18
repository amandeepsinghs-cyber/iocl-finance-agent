#!/usr/bin/env python3
"""
Step 5.2 RAG & Context Bridge Builder for Yukti IOCL:
  1. Generates `ssot_financial_line_context` (255 rows across FY17-FY26 + multi-year decadal
     context, using exact verified metrics from `iocl_10yr_corporate_wide.json`) and loads
     it into BOTH `yukti-finance-iocl.hrfin_gold.ssot_financial_line_context` and
     `yukti-finance-iocl.hrfin_gold_v3.ssot_financial_line_context`.
  2. Generates ~145 structured `financial_notes_chunks` across IOCL's 4 context dossiers,
     10-yr P&L/BS/CF/Downstream-360 narratives, 9 standalone refineries, 3 pipeline
     networks, 7 marketing product categories, CPCL & group subsidiaries, Schedule III
     Notes 2-35, and CFO Diagnostic Levers L01-L10.
  3. Embeds all `financial_notes_chunks` via Vertex AI `text-embedding-005` (768-d,
     `task_type="RETRIEVAL_DOCUMENT"`, `us-central1`) and loads them into
     `yukti-finance-iocl.hrfin_docs.financial_notes_chunks` (+ attempts IVF vector index).
  4. Saves local JSON / JSONL artifacts in `financial_build/data/` and updates
     `financial_build/data/snapshot_manifest.json`.

Mandatory Attribution:
  - Every BigQuery load & query carries `labels={"datacloud": "jetski"}`.
  - Never touches `ongc-hr-finance-agent`.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from google import genai
from google.genai import types as genai_types
from google.cloud import bigquery

PROJECT_ID = os.getenv("TARGET_PROJECT") or os.getenv("YUKTI_GCP_PROJECT") or "yukti-finance-iocl"
BQ_LOCATION = "asia-south1"
VERTEX_LOCATION = os.getenv("YUKTI_VERTEX_LOCATION", "us-central1")
EMBEDDING_MODEL = "text-embedding-005"
EMBEDDING_DIM = 768
ATTRIBUTION_LABELS = {"datacloud": "jetski"}

assert PROJECT_ID != "ongc-hr-finance-agent", "Guardrail: must never target ONGC project"

REPO_ROOT = Path(__file__).resolve().parents[2]
BUILD_DIR = REPO_ROOT / "financial_build"
DATA_DIR = BUILD_DIR / "data"
CONTEXT_DIR = BUILD_DIR / "context_reports"
CROSSWALK_MD = BUILD_DIR / "04_yahoo_finance_vs_annual_report_mapping.md"

LINE_CTX_JSON = DATA_DIR / "ssot_financial_line_context.json"
CORPUS_JSONL = DATA_DIR / "financial_notes_corpus.jsonl"
EMBED_CACHE_JSONL = REPO_ROOT / "financial_ssot" / "out" / "financial_notes_chunks_embeddings.jsonl"
MANIFEST_PATH = DATA_DIR / "snapshot_manifest.json"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Part 1: SSOT Financial Line Context Builder (>= 250 rows across FY17-FY26)
# ---------------------------------------------------------------------------
LINE_SPECS: List[Tuple[str, str, str, str, str, str, str]] = [
    # (line_code, corp_key, statement_type, line_name, note_ref, hist_10yr, action_hint)
    (
        "PL.REV_OPS",
        "gross_revenue_inr_cr",
        "PNL",
        "Revenue from Operations (Gross)",
        "Schedule III I / Note 28",
        "Gross Revenue scaled ~2.0x over FY17-FY26 from Rs 4,45,441.90 Cr (FY17) to peak Rs 9,34,952.66 Cr (FY23) and Rs 8,86,224.41 Cr (FY26).",
        "Monitor crude pass-through vs retail pump realization lag and expand higher-margin petrochemical and specialty lube share above 8% of turnover.",
    ),
    (
        "LEVY.TOTAL",
        "excise_duty_inr_cr",
        "PNL",
        "Excise Duty on Sale of Goods",
        "Note 28 / Statutory Levies",
        "Central Excise remitted peaked at Rs 1,36,832.86 Cr (26.6% of Gross Revenue) in FY21 and stands at Rs 1,02,066.54 Cr (11.5%) in FY26.",
        "Always evaluate operating profitability ratios against Net Revenue (ex-excise) so union duty cuts/hikes do not distort EBITDA margin benchmarking.",
    ),
    (
        "REV.NET_OF_EXCISE",
        "net_revenue_inr_cr",
        "PNL",
        "Revenue from Operations (Net of Excise Duty)",
        "Schedule III I (Net)",
        "Net Revenue rose from Rs 3,59,942.15 Cr (FY17) to Rs 8,39,472.20 Cr (FY23) and Rs 7,84,157.87 Cr (FY26) across 105.117 MMT product sales.",
        "Anchor working capital days and segmental EBITDA margin KPIs strictly on Net Revenue ex-excise.",
    ),
    (
        "PL.COST_MATERIALS",
        "cost_of_materials_consumed_inr_cr",
        "PNL",
        "Cost of Materials Consumed (Crude & Feedstock)",
        "Note 30",
        "Crude throughput costs stood at Rs 3,81,790.55 Cr in FY26 (down from Rs 4,40,693.11 Cr in FY23), tracking Brent, USD/INR, and 75.451 MMT throughput.",
        "Use AI crude-basket LP to optimize heavy/high-TAN opportunity crudes at Paradip and Koyali, protecting Core GRM above $9.50/bbl (L02).",
    ),
    (
        "PL.PURCHASES_TRADED",
        "purchases_stock_in_trade_inr_cr",
        "PNL",
        "Purchases of Stock-in-Trade",
        "Schedule III IV(b)",
        "Product purchases totaled Rs 2,56,981.77 Cr in FY26 (up from Rs 1,41,925.49 Cr in FY17), balancing finished fuel demand beyond captive refinery slate.",
        "Synchronize Panipat P-25 and Koyali/Barauni brownfield expansions to replace high-cost imported finished fuels with captive refinery slate.",
    ),
    (
        "PL.OTHER_EXP",
        "other_expenses_inr_cr",
        "PNL",
        "Other Operating Expenses",
        "Note 33",
        "Other Operating Expenses stood at Rs 57,600.40 Cr in FY26 (vs Rs 51,279.08 Cr in FY25), covering refinery fuel & power, rail/road freight, bottling, and FX differences.",
        "Execute rail-to-pipeline freight shift (6.5 MMT -> Rs 685 Cr/yr saving, L04) and trim refinery Fuel & Loss -30 bps (Rs 940 Cr/yr saving, L01).",
    ),
    (
        "PL.PBIDT",
        "ebitda_inr_cr",
        "PNL",
        "EBITDA / PBIDT",
        "Analytical Memo",
        "Standalone EBITDA ranged from Rs 22,356.08 Cr (FY20 COVID) and Rs 28,487.85 Cr (FY23) to Rs 74,181.60 Cr (FY24) and Rs 73,718.25 Cr (FY26).",
        "Buffer cyclical crack swings by pairing 25%-35% Singapore gasoil crack hedges with premium retail XP95/SERVO mix expansion (L06, L08).",
    ),
    (
        "PL.DDA",
        "dda_inr_cr",
        "PNL",
        "Depreciation and Amortisation (DD&A)",
        "Note 2",
        "Annual DD&A nearly tripled over the decade from Rs 6,222.97 Cr (FY17) to Rs 16,964.82 Cr (FY26) following Paradip, BS-VI, Ind AS 116 ROU, and brownfield capitalizations.",
        "Track post-capitalization capacity ramp-up and distillate yield uplift on every major unit transferred out of CWIP.",
    ),
    (
        "PL.FIN_COST",
        "finance_costs_inr_cr",
        "PNL",
        "Finance Costs",
        "Note 34",
        "Finance Costs moved from Rs 3,445.43 Cr (FY17) to Rs 8,731.59 Cr (FY25) and eased to Rs 7,969.02 Cr (FY26) as Total Debt dropped Rs 23,797.32 Cr YoY.",
        "Retire Rs 10,000 Cr short-term CP/WCDL facilities out of FY27 OCF to cut annual interest expense by ~Rs 720 Cr/yr (L07).",
    ),
    (
        "PL.EXCEPTIONAL",
        "exceptional_items_inr_cr",
        "PNL",
        "Exceptional Items",
        "Schedule III VI",
        "Reported Exceptional Items were -Rs 11,304.64 Cr in FY20 (COVID crude/product NRV shock) and +Rs 1,838.02 Cr in FY25, with nil balance in FY26.",
        "Enforce dynamic cargo-in-transit hedging and tight crude DIO limits (<= 55.6 days) to limit sudden crude crash NRV shocks (L05).",
    ),
    (
        "PL.TAX",
        "tax_expense_total_inr_cr",
        "PNL",
        "Total Tax Expense",
        "Note 35",
        "IOCL elected Section 115BAA (25.168% rate) in FY20 (creating a -Rs 5,007.34 Cr net tax credit); FY26 tax expense was Rs 11,981.99 Cr on Rs 48,784.41 Cr PBT (24.56%).",
        "Coordinate asset capitalization cut-off dates (before March 31) and R&D/green-capex tax planning under Sec 115BAA.",
    ),
    (
        "PL.PAT",
        "pat_inr_cr",
        "PNL",
        "Profit After Tax (PAT — Standalone)",
        "Schedule III IX",
        "10-yr cumulative Standalone PAT tops Rs 2,02,304.69 Cr, with peaks in FY24 (Rs 39,618.84 Cr) and FY26 (Rs 36,802.42 Cr) and trough in FY20 (Rs 1,313.23 Cr).",
        "Maintain balanced capital allocation: 30-40% dividend payout while funding capex largely via internal accruals (L09).",
    ),
    (
        "PL.CONSOL_PAT",
        "consolidated_pat_inr_cr",
        "PNL",
        "Consolidated Profit After Tax (IOC.NS)",
        "Consolidated P&L",
        "Consolidated PAT (Rs 43,677.32 Cr in FY26 vs Standalone Rs 36,802.42 Cr) consolidates CPCL (51.89%), Lanka IOC (75.12%), IOCME, HURL & Petronet LNG.",
        "Track CPCL GRM spread and JV dividend repatriation (HURL, Petronet LNG) quarterly alongside Yahoo Finance IOC.NS consensus.",
    ),
    (
        "BS.PPE_NET",
        "refinery_petchem_ppe_inr_cr",
        "BALANCE_SHEET",
        "Property, Plant & Equipment (Net Block, incl. ROU)",
        "Note 2",
        "Standalone Net PPE (excl. CWIP) expanded from Rs 1,06,900.73 Cr (FY17) to Rs 1,82,388.60 Cr (FY25) and Rs 1,87,894.12 Cr (FY26) across refineries, pipelines, and marketing assets.",
        "Benchmark unit ROCE per refinery/pipeline division and accelerate commissioning of Panipat, Koyali, and Barauni brownfield revamps.",
    ),
    (
        "BS.CWIP",
        "cwip_inr_cr",
        "BALANCE_SHEET",
        "Capital Work-in-Progress (CWIP)",
        "Note 2.1",
        "CWIP expanded from Rs 10,223.36 Cr (FY17) and Rs 57,024.23 Cr (FY24) to Rs 73,453.16 Cr (FY25) and Rs 82,577.56 Cr (FY26) during brownfield waves.",
        "Monitor Stage-Gate Capex Discipline (L09): penalize >15% cost overrun or >6-month schedule slippage on Panipat P-25 and PX/PTA trains.",
    ),
    (
        "BS.INVENTORIES",
        "inventories_inr_cr",
        "BALANCE_SHEET",
        "Inventories (Crude & Petroleum Products)",
        "Note 11",
        "Closing inventories grew from Rs 62,240.87 Cr (FY17) to Rs 1,13,853.41 Cr (FY23) and stand at Rs 1,07,484.12 Cr (DIO 61.42 days) in FY26.",
        "Trim crude/product holding float by 3 days to release working capital and cut short-term borrowing costs (L05).",
    ),
    (
        "BS.TRADE_REC_C",
        "receivables_outstanding_inr_cr",
        "BALANCE_SHEET",
        "Trade Receivables",
        "Note 13",
        "Trade Receivables remain lean at Rs 14,229.15 Cr in FY26 (DSO 5.86 days), reflecting rapid cash/card retail collections offset by aviation/institutional B2B credit.",
        "Enforce automated credit-limit lockouts on aviation/institutional accounts >30 days past due and reconcile OMC pool settlements monthly.",
    ),
    (
        "BS.EQUITY.TOTAL",
        "net_worth_inr_cr",
        "BALANCE_SHEET",
        "Total Equity (Net Worth)",
        "Notes 17-18",
        "Net Worth doubled from Rs 99,728.72 Cr (FY17) to Rs 2,04,544.34 Cr (FY26; BVPS Rs 148.53 on year-end shares post 1:1 FY18 & 1:2 FY23 bonus issues).",
        "Sustain >= 15% ROE through cycle via disciplined deleveraging and non-fuel/specialty chemical margin expansion.",
    ),
    (
        "BS.BORROW_TOTAL_10YR",
        "total_debt_inr_cr",
        "BALANCE_SHEET",
        "Total Debt (Long-Term + Short-Term Borrowings)",
        "Notes 19 & 22",
        "Total Debt surged to Rs 1,32,495.45 Cr (FY23) and Rs 1,34,465.54 Cr (FY25) before dropping -Rs 23,797.32 Cr to Rs 1,10,668.22 Cr (FY26).",
        "Target Debt-to-Equity <= 0.50x in FY27 by retiring Rs 10,000+ Cr working-capital CP/WCDL debt out of operating cash flow (L07).",
    ),
    (
        "CF.CFO",
        "operating_cash_flow_inr_cr",
        "CASH_FLOW",
        "Net Cash Generated by Operating Activities (OCF)",
        "Ind AS 7 Operating",
        "OCF ranged from Rs 7,190.30 Cr (FY20) and Rs 20,985.35 Cr (FY23) to Rs 68,096.60 Cr (FY24) and record Rs 71,398.57 Cr (FY26).",
        "Keep OCF/EBITDA cash conversion >= 85% by preventing inventory bloat and recovering GoI LPG under-recovery receivables promptly.",
    ),
    (
        "CAPEX.TOTAL",
        "total_capex_spent_inr_cr",
        "CASH_FLOW",
        "Total Capital Expenditure Outflow",
        "Schedule III / Capex",
        "Annual PPE/CWIP/intangible capex cash outflow moved from Rs 13,979.42 Cr (FY17) to peak Rs 35,209.07 Cr (FY24) and Rs 26,421.09 Cr (FY26).",
        "Ring-fence >= 12% post-tax equity IRR hurdle rate for expansion & green hydrogen investments per IOCL-CAPALLOC policy (L09).",
    ),
    (
        "REF.THROUGHPUT_MMT",
        "refining_throughput_mmt",
        "REFINERY_360",
        "Refinery Crude Throughput (MMT — Standalone 9 Refineries)",
        "Downstream 360 Refineries",
        "Crude processed across 9 IOCL refineries expanded from 65.19 MMT (FY17) to all-time record 75.451 MMT (107.4% utilization on 70.25 MMTPA) in FY26.",
        "Sustain >= 104% utilization across coastal/large hubs (Panipat, Paradip, Koyali) while upgrading fuel & energy efficiency at North-East units (L01).",
    ),
    (
        "REF.GRM_USD_BBL",
        "gross_refining_margin_usd_bbl",
        "REFINERY_360",
        "Gross Refining Margin ($/bbl)",
        "Downstream 360 GRM",
        "Reported GRM cycled from $0.08/bbl (FY20 COVID NRV loss; Core $4.10) to all-time record $19.52/bbl (FY23), moderating to $4.80 (FY25) and rebounding to $10.85/bbl (Core $9.95) in FY26.",
        "Track Core GRM vs Reported GRM weekly and optimize Singapore crack + heavy crude discount capture across Paradip and Panipat (L02).",
    ),
    (
        "PIP.THROUGHPUT_MMT",
        "pipeline_throughput_mmt",
        "REFINERY_360",
        "Cross-Country Pipeline Throughput (MMT)",
        "Downstream 360 Pipelines",
        "Pipeline throughput scaled from 82.49 MMT (FY17) across 16,203 km to all-time high 105.556 MMT across ~19,760 km (Crude, Product, Gas) in FY26.",
        "Shift 6.5 MMT inland fuel distribution from costly rail/road rakes onto newly commissioned Paradip-Hyderabad & Koyali-Sanganer pipeline spurs (L04).",
    ),
    (
        "MKT.SALES_MMT",
        "marketing_sales_mmt",
        "REFINERY_360",
        "Total Petroleum Product Sales Volume (MMT)",
        "Downstream 360 Marketing",
        "Total Marketing Sales including exports grew from 84.10 MMT (FY17) to record 105.117 MMT (FY26) across HSD, MS, LPG, ATF, Bitumen & Petchem.",
        "Drive higher retail margin per KL via XP95/XtraGreen high-octane mix (12% -> 18%) and SERVO lubricant channel penetration (L08).",
    ),
]


def _fmt_val(line_code: str, val: float) -> str:
    if line_code == "REF.GRM_USD_BBL":
        return f"${val:.2f}/bbl"
    if line_code.endswith("_MMT"):
        return f"{val:.3f} MMT"
    return f"Rs {val:,.2f} Cr"


def build_line_context_rows(corp_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows_by_fy = {r["fiscal_year"]: r for r in corp_rows}
    fys = sorted(rows_by_fy.keys(), key=lambda x: int(x.replace("FY", "")))
    out: List[Dict[str, Any]] = []

    for fy_idx, fy in enumerate(fys):
        rec = rows_by_fy[fy]
        prev_rec = rows_by_fy[fys[fy_idx - 1]] if fy_idx > 0 else None
        brent = rec.get("brent_avg_usd_bbl")
        fx = rec.get("fx_inr_per_usd")
        grm = rec.get("gross_refining_margin_usd_bbl")
        core_grm = rec.get("core_grm_usd_bbl")
        tp = rec.get("refining_throughput_mmt")
        driver = rec.get("primary_driver_note", "")
        bs_driver = rec.get("balance_sheet_driver_note", "")

        for line_code, col_key, stmt_type, line_name, note_ref, hist_ctx, action in LINE_SPECS:
            amt = float(rec.get(col_key, 0.0) or 0.0)
            prev_amt = float(prev_rec.get(col_key, 0.0) or 0.0) if prev_rec else None
            yoy_delta = round(amt - prev_amt, 4) if prev_amt is not None else None
            yoy_pct = (
                round(((amt - prev_amt) / abs(prev_amt)) * 100.0, 2)
                if prev_amt not in (None, 0.0)
                else None
            )

            delta_phrase = ""
            if yoy_delta is not None and yoy_pct is not None:
                sign = "+" if yoy_delta >= 0 else ""
                delta_phrase = f" ({sign}{yoy_delta:,.2f}, {sign}{yoy_pct:.1f}% YoY vs {fys[fy_idx - 1]})"
            elif yoy_delta is not None:
                sign = "+" if yoy_delta >= 0 else ""
                delta_phrase = f" ({sign}{yoy_delta:,.2f} YoY vs {fys[fy_idx - 1]})"

            what_happened = (
                f"In {fy}, IOCL {line_name} stood at {_fmt_val(line_code, amt)}{delta_phrase}. "
                f"Macro backdrop: Brent ${brent}/bbl, USD/INR Rs {fx}, GRM ${grm}/bbl (Core ${core_grm}/bbl), "
                f"Refinery Throughput {tp} MMT."
            )
            ar_ctx = (
                f"[{fy} Annual Report {note_ref}] {driver if stmt_type in ('PNL', 'REFINERY_360') else bs_driver}"
            ).strip()

            out.append(
                {
                    "context_id": f"CTX-{fy}-{line_code}",
                    "fy": fy,
                    "statement_type": stmt_type,
                    "line_code": line_code,
                    "line_name": line_name,
                    "note_ref": note_ref,
                    "amount_cr": round(amt, 4),
                    "prev_amount_cr": round(prev_amt, 4) if prev_amt is not None else None,
                    "yoy_delta_cr": yoy_delta,
                    "yoy_delta_pct": yoy_pct,
                    "what_happened_summary": what_happened,
                    "annual_report_context": ar_ctx,
                    "historical_10yr_context": hist_ctx,
                    "director_finance_action": action,
                    "source_citation": f"IOCL Annual Report {fy} ({note_ref}); hrfin_gold.ssot_corporate_annual_360",
                }
            )

    # Also add 5 decadal summary rows (`FY17_FY26`) for ratios & flagship multi-year trends
    fy17 = rows_by_fy["FY17"]
    fy26 = rows_by_fy["FY26"]
    decadal_specs = [
        (
            "RATIO.ROCE",
            "roce_pct",
            "RATIOS",
            "Return on Capital Employed (ROCE %)",
            "Financial Ratios",
            f"10-yr IOCL Consolidated ROCE expanded from {fy17['roce_pct']}% (FY17) to peak 22.92% (FY24) and {fy26['roce_pct']}% in FY26.",
            "Sustain ROCE > 15% by completing CWIP capitalization at Panipat/Koyali and pruning working-capital debt (L07, L09).",
        ),
        (
            "RATIO.DEBT_EQUITY",
            "debt_to_equity_ratio",
            "RATIOS",
            "Debt-to-Equity Ratio (x)",
            "Notes 17-22 / Ratios",
            f"Debt-to-Equity moved from {fy17['debt_to_equity_ratio']}x (FY17) to stress peak 1.24x (FY20 COVID) and deleveraged cleanly to {fy26['debt_to_equity_ratio']}x in FY26.",
            "Keep D/E anchored <= 0.55x through peak P-25 capex cycle to preserve AAA domestic rating and 7.15% pretax Kd.",
        ),
        (
            "RATIO.PBIDT_MARGIN_PCT",
            "ebitda_margin_pct",
            "RATIOS",
            "EBITDA Margin (% of Net Revenue)",
            "Analytical Ratios",
            f"EBITDA / Net Revenue averaged ~7.5%-10.3% outside price-freeze troughs, finishing FY26 at {fy26['ebitda_margin_pct']}% (vs {fy17['ebitda_margin_pct']}% in FY17).",
            "Grow structural margin via Fuel & Loss -30 bps (L01), Pipeline shift (L04), and XP95/SERVO mix (L08).",
        ),
        (
            "RATIO.INVENTORY_DAYS",
            "inventory_days",
            "RATIOS",
            "Inventory Holding Days (DIO)",
            "Note 11 / Working Capital",
            f"Inventory holding days stood at {fy17['inventory_days']} days (FY17), spiked to 76.2 days (FY21 price surge), and normalized to {fy26['inventory_days']} days in FY26.",
            "Reduce DIO by 3 days (58.6 -> 55.6 days) to unlock ~Rs 4,800 Cr working capital cash (L05).",
        ),
        (
            "OTH.EXCHEQUER",
            "exchequer_contribution_inr_cr",
            "RATIOS",
            "Contribution to National Exchequer (Rs Cr)",
            "Statutory Disclosures",
            f"IOCL contributed Rs 17-26+ Lakh Cr cumulatively over FY17-FY26, peaking at Rs 2,64,436 Cr (FY22) and totaling Rs {fy26['exchequer_contribution_inr_cr']:,.2f} Cr in FY26.",
            "Continue clean tax/excise compliance while transparently breaking out Excise pass-through in investor/Board decks.",
        ),
    ]
    for line_code, col_key, stmt_type, line_name, note_ref, hist_ctx, action in decadal_specs:
        v17 = float(fy17[col_key])
        v26 = float(fy26[col_key])
        delta = round(v26 - v17, 4)
        pct = round((delta / abs(v17)) * 100.0, 2) if v17 else None
        out.append(
            {
                "context_id": f"CTX-FY17_FY26-{line_code}",
                "fy": "FY17_FY26",
                "statement_type": stmt_type,
                "line_code": line_code,
                "line_name": line_name,
                "note_ref": note_ref,
                "amount_cr": round(v26, 4),
                "prev_amount_cr": round(v17, 4),
                "yoy_delta_cr": delta,
                "yoy_delta_pct": pct,
                "what_happened_summary": f"Over FY17-FY26, {line_name} moved from {v17:,.2f} (FY17) to {v26:,.2f} (FY26).",
                "annual_report_context": hist_ctx,
                "historical_10yr_context": hist_ctx,
                "director_finance_action": action,
                "source_citation": f"IOCL Annual Reports FY17-FY26 ({note_ref}); hrfin_gold.ssot_corporate_annual_360",
            }
        )

    return out


# ---------------------------------------------------------------------------
# Part 2: `financial_notes_chunks` Corpus Builder (140+ RAG Chunks)
# ---------------------------------------------------------------------------
def _parse_markdown_sections(md_path: Path, default_stmt: str, default_fy: str, prefix: str) -> List[Dict[str, Any]]:
    text = md_path.read_text(encoding="utf-8")
    sections = re.split(r"(?m)^(?=## )", text)
    chunks: List[Dict[str, Any]] = []
    idx = 0
    for sec in sections:
        sec = sec.strip()
        if not sec or sec.startswith("# ") and "\n" not in sec:
            continue
        lines = sec.splitlines()
        heading = lines[0].lstrip("#").strip() if lines else prefix
        # Split large sections at ### subheadings
        if len(sec) > 2200 and "\n### " in sec:
            subs = re.split(r"(?m)^(?=### )", sec)
        else:
            subs = [sec]
        for sub in subs:
            sub = sub.strip()
            if len(sub) < 80:
                continue
            idx += 1
            sub_head = sub.splitlines()[0].lstrip("#").strip()
            fy = default_fy
            m_fy = re.search(r"\b(FY(?:1[7-9]|2[0-6]))\b", sub_head)
            if m_fy:
                fy = m_fy.group(1)
            stmt = default_stmt
            low = (heading + " " + sub_head).lower()
            if "balance sheet" in low or "debt" in low or "inventory" in low or "equity" in low:
                stmt = "BALANCE_SHEET"
            elif "cash flow" in low or "capex" in low:
                stmt = "CASH_FLOW"
            elif "refiner" in low or "pipeline" in low or "marketing" in low or "downstream" in low:
                stmt = "REFINERY_360"
            elif "yahoo" in low or "consolidated" in low:
                stmt = "CONSOLIDATED"
            chunks.append(
                {
                    "chunk_id": f"{prefix}-{idx:03d}",
                    "fy": fy,
                    "statement_type": stmt,
                    "note_ref": sub_head[:90],
                    "line_codes": _infer_line_codes(sub),
                    "title": f"{heading[:60]} — {sub_head[:90]}" if sub_head != heading else heading[:140],
                    "content": sub[:3200],
                    "source_citation": f"financial_build/{md_path.name} ({sub_head[:60]})",
                }
            )
    return chunks


def _infer_line_codes(text: str) -> List[str]:
    low = text.lower()
    codes: List[str] = []
    rules = [
        ("gross revenue", "PL.REV_OPS"),
        ("excise", "LEVY.TOTAL"),
        ("net revenue", "REV.NET_OF_EXCISE"),
        ("ebitda", "PL.PBIDT"),
        ("exceptional", "PL.EXCEPTIONAL"),
        ("pat", "PL.PAT"),
        ("consolidated", "PL.CONSOL_PAT"),
        ("ppe", "BS.PPE_NET"),
        ("cwip", "BS.CWIP"),
        ("inventori", "BS.INVENTORIES"),
        ("receivable", "BS.TRADE_REC_C"),
        ("net worth", "BS.EQUITY.TOTAL"),
        ("debt", "BS.BORROW_TOTAL_10YR"),
        ("lease", "BS.LEASE_LIAB_NC"),
        ("operating cash", "CF.CFO"),
        ("capex", "CAPEX.TOTAL"),
        ("roce", "RATIO.ROCE"),
        ("grm", "REF.GRM_USD_BBL"),
        ("throughput", "REF.THROUGHPUT_MMT"),
        ("pipeline", "PIP.THROUGHPUT_MMT"),
        ("marketing", "MKT.SALES_MMT"),
    ]
    for kw, code in rules:
        if kw in low and code not in codes:
            codes.append(code)
    return codes or ["PL.REV_OPS", "PL.PAT"]


def build_financial_notes_chunks(
    corp_rows: List[Dict[str, Any]],
    ref_rows: List[Dict[str, Any]],
    mkt_rows: List[Dict[str, Any]],
    pip_rows: List[Dict[str, Any]],
    sub_rows: List[Dict[str, Any]],
    seg_rows: List[Dict[str, Any]],
    mou_rows: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    chunks: List[Dict[str, Any]] = []

    # A. Context Reports 01..03 + Crosswalk 04
    for md_path, default_stmt, default_fy, prefix in [
        (CONTEXT_DIR / "01_FY17_to_FY26_Chronological_MDA_Dossier.md", "CHRONOLOGY", "FY17_FY26", "IOCL-DOC1"),
        (CONTEXT_DIR / "02_Schedule_III_Notes_5_to_37_Context_Catalog.md", "PNL", "FY26", "IOCL-DOC2"),
        (CONTEXT_DIR / "03_Director_Finance_Action_Playbook.md", "REFINERY_360", "FY26", "IOCL-DOC3"),
        (CROSSWALK_MD, "CONSOLIDATED", "FY26", "IOCL-XWLK"),
    ]:
        chunks.extend(_parse_markdown_sections(md_path, default_stmt, default_fy, prefix))

    # B. Year-by-year 4-lens deep-dive chunks (10 FYs * 4 = 40 chunks)
    mkt_by_fy: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in mkt_rows:
        mkt_by_fy[r["fiscal_year"]].append(r)
    pip_by_fy: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in pip_rows:
        pip_by_fy[r["fiscal_year"]].append(r)
    ref_by_fy: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in ref_rows:
        if r.get("is_refinery"):
            ref_by_fy[r["fiscal_year"]].append(r)

    for rec in corp_rows:
        fy = rec["fiscal_year"]
        # 1. P&L
        chunks.append(
            {
                "chunk_id": f"IOCL-{fy}-PNL",
                "fy": fy,
                "statement_type": "PNL",
                "note_ref": f"Schedule III Statement of P&L ({fy})",
                "line_codes": ["PL.REV_OPS", "LEVY.TOTAL", "REV.NET_OF_EXCISE", "PL.PBIDT", "PL.PAT", "PL.CONSOL_PAT"],
                "title": f"IOCL {fy} Statement of Profit & Loss: Revenue, Excise, EBITDA & PAT",
                "content": (
                    f"In {fy}, IOCL Standalone Gross Revenue from Operations was Rs {rec['gross_revenue_inr_cr']:,.2f} Cr "
                    f"(Petroleum Products Rs {rec['petroleum_products_revenue_inr_cr']:,.2f} Cr; Petchem/Pipelines/Other "
                    f"Rs {rec['petchem_and_other_op_rev_inr_cr']:,.2f} Cr). Central Excise Duty (Note 28) was "
                    f"Rs {rec['excise_duty_inr_cr']:,.2f} Cr, leaving Net Revenue of Rs {rec['net_revenue_inr_cr']:,.2f} Cr. "
                    f"Other Income (Note 29) contributed Rs {rec['other_income_inr_cr']:,.2f} Cr. Cost of Materials Consumed "
                    f"(Note 30) was Rs {rec['cost_of_materials_consumed_inr_cr']:,.2f} Cr and Purchases of Stock-in-Trade "
                    f"Rs {rec['purchases_stock_in_trade_inr_cr']:,.2f} Cr. Standalone EBITDA stood at Rs {rec['ebitda_inr_cr']:,.2f} Cr "
                    f"({rec['ebitda_margin_pct']}% of Net Revenue), DD&A Rs {rec['dda_inr_cr']:,.2f} Cr, Finance Costs "
                    f"Rs {rec['finance_costs_inr_cr']:,.2f} Cr, Exceptional Items Rs {rec['exceptional_items_inr_cr']:,.2f} Cr, "
                    f"PBT Rs {rec['pbt_inr_cr']:,.2f} Cr, Tax Rs {rec['tax_expense_total_inr_cr']:,.2f} Cr (effective rate "
                    f"{rec['effective_tax_rate_pct']}%), Standalone PAT Rs {rec['pat_inr_cr']:,.2f} Cr, and Consolidated PAT "
                    f"(IOC.NS) Rs {rec['consolidated_pat_inr_cr']:,.2f} Cr. Key driver: {rec.get('primary_driver_note', '')}"
                ),
                "source_citation": f"IOCL Annual Report {fy} Standalone & Consolidated P&L",
            }
        )
        # 2. Balance Sheet
        chunks.append(
            {
                "chunk_id": f"IOCL-{fy}-BS",
                "fy": fy,
                "statement_type": "BALANCE_SHEET",
                "note_ref": f"Schedule III Balance Sheet Notes 2-25 ({fy})",
                "line_codes": ["BS.PPE_NET", "BS.CWIP", "BS.INVENTORIES", "BS.TRADE_REC_C", "BS.EQUITY.TOTAL", "BS.BORROW_TOTAL_10YR"],
                "title": f"IOCL {fy} Balance Sheet: Fixed Assets, Working Capital, Net Worth & Borrowings",
                "content": (
                    f"At 31 March {fy}, IOCL Standalone Total Assets stood at Rs {rec['total_assets_inr_cr']:,.2f} Cr: "
                    f"Net PPE (incl. ROU) Rs {rec['refinery_petchem_ppe_inr_cr']:,.2f} Cr, CWIP Rs {rec['cwip_inr_cr']:,.2f} Cr, "
                    f"Non-Current Investments Rs {rec['investments_subsidiaries_jv_inr_cr']:,.2f} Cr, Inventories "
                    f"Rs {rec['inventories_inr_cr']:,.2f} Cr (DIO {rec['inventory_days']} days), Trade Receivables "
                    f"Rs {rec['receivables_outstanding_inr_cr']:,.2f} Cr (DSO {rec['receivable_days']} days), Cash & Bank "
                    f"Rs {rec['cash_and_bank_inr_cr']:,.2f} Cr. Total Equity (Net Worth) was Rs {rec['net_worth_inr_cr']:,.2f} Cr "
                    f"(BVPS Rs {rec['book_value_per_share_inr']:,.2f} on {rec['shares_outstanding_cr']} Cr shares). "
                    f"Total Debt stood at Rs {rec['total_debt_inr_cr']:,.2f} Cr (Long-Term Rs {rec['long_term_debt_inr_cr']:,.2f} Cr, "
                    f"Short-Term Rs {rec['short_term_debt_inr_cr']:,.2f} Cr; D/E {rec['debt_to_equity_ratio']}x, "
                    f"Net Debt/EBITDA {rec['net_debt_to_ebitda_ratio']}x). {rec.get('balance_sheet_driver_note', '')}"
                ),
                "source_citation": f"IOCL Annual Report {fy} Standalone Balance Sheet",
            }
        )
        # 3. Cash Flow & Capital Allocation
        chunks.append(
            {
                "chunk_id": f"IOCL-{fy}-CF",
                "fy": fy,
                "statement_type": "CASH_FLOW",
                "note_ref": f"Ind AS 7 Cash Flow & Capital Allocation ({fy})",
                "line_codes": ["CF.CFO", "CAPEX.TOTAL", "CF.CFI", "CF.CFF", "RATIO.DPS"],
                "title": f"IOCL {fy} Cash Flow, Capex, Free Cash Flow, Dividends & Exchequer",
                "content": (
                    f"In {fy}, IOCL generated Operating Cash Flow (CFO) of Rs {rec['operating_cash_flow_inr_cr']:,.2f} Cr "
                    f"(OCF/EBITDA {rec['ocf_to_ebitda_pct']}%), after income tax paid of Rs {abs(rec['income_tax_paid_cf_inr_cr']):,.2f} Cr "
                    f"and working capital movement of Rs {rec['working_capital_change_cf_inr_cr']:,.2f} Cr. Capital expenditure "
                    f"outflow totaled Rs {rec['total_capex_spent_inr_cr']:,.2f} Cr, yielding Free Cash Flow of "
                    f"Rs {rec['free_cash_flow_inr_cr']:,.2f} Cr (FCF/share Rs {rec['fcf_per_share_inr']:,.2f}). "
                    f"Dividends paid in cash were Rs {abs(rec['dividend_paid_cf_inr_cr']):,.2f} Cr (DPS Rs {rec['dividend_per_share_inr']:,.2f}, "
                    f"dividend yield {rec['dividend_yield_pct']}%, closing price Rs {rec['iocl_close_price_inr']:,.2f}, market cap "
                    f"Rs {rec['market_cap_inr_cr']:,.2f} Cr). Contribution to National Exchequer: Rs {rec['exchequer_contribution_inr_cr']:,.2f} Cr; "
                    f"CSR disbursed: Rs {rec['csr_disbursed_inr_cr']:,.2f} Cr."
                ),
                "source_citation": f"IOCL Annual Report {fy} Statement of Cash Flows",
            }
        )
        # 4. Downstream 360
        top_refs = sorted(ref_by_fy[fy], key=lambda x: x["throughput_mmt"], reverse=True)[:3]
        top_ref_txt = "; ".join(f"{r['refinery_name']} ({r['throughput_mmt']} MMT, GRM ${r['grm_usd_bbl']}/bbl)" for r in top_refs)
        pip_txt = "; ".join(f"{p['pipeline_code']} {p['throughput_mmt']} MMT ({p['capacity_utilization_pct']}% util)" for p in pip_by_fy[fy])
        mkt_txt = "; ".join(f"{m['product_code']} {m['sales_volume_mmt']} MMT" for m in mkt_by_fy[fy][:4])
        chunks.append(
            {
                "chunk_id": f"IOCL-{fy}-D360",
                "fy": fy,
                "statement_type": "REFINERY_360",
                "note_ref": f"Downstream 360 Operational KPIs ({fy})",
                "line_codes": ["REF.THROUGHPUT_MMT", "REF.GRM_USD_BBL", "REF.CORE_GRM_USD_BBL", "PIP.THROUGHPUT_MMT", "MKT.SALES_MMT"],
                "title": f"IOCL {fy} Downstream 360: Refineries, GRM vs Singapore, Pipelines & Marketing",
                "content": (
                    f"In {fy}, IOCL processed {rec['refining_throughput_mmt']} MMT crude across 9 refineries "
                    f"({rec['refining_capacity_utilization_pct']}% capacity utilization on {rec['refining_capacity_mmtpa']} MMTPA), "
                    f"achieving Reported GRM of ${rec['gross_refining_margin_usd_bbl']}/bbl (Core GRM ${rec['core_grm_usd_bbl']}/bbl, "
                    f"Singapore benchmark ${rec['singapore_benchmark_grm_usd_bbl']}/bbl, premium ${rec['grm_premium_over_singapore_usd_bbl']}/bbl), "
                    f"Distillate Yield {rec['distillate_yield_pct']}%, and Fuel & Loss {rec['fuel_and_loss_pct']}%. "
                    f"Top refineries: {top_ref_txt}. Pipelines moved {rec['pipeline_throughput_mmt']} MMT ({pip_txt}). "
                    f"Marketing sales totaled {rec['marketing_sales_mmt']} MMT ({mkt_txt})."
                ),
                "source_citation": f"IOCL Annual Report {fy} Operational Highlights & Downstream 360",
            }
        )

    # C. 9 Refineries (2 chunks each = 18 chunks)
    ref_hist: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in ref_rows:
        if r.get("is_refinery"):
            ref_hist[r["refinery_id"]].append(r)

    for ref_id, rlist in sorted(ref_hist.items()):
        rlist.sort(key=lambda x: int(x["fiscal_year"].replace("FY", "")))
        r17, r26 = rlist[0], rlist[-1]
        r25 = next((x for x in rlist if x["fiscal_year"] == "FY25"), rlist[-2])
        name = r26["refinery_name"]
        avg_grm = sum(x["grm_usd_bbl"] for x in rlist) / len(rlist)
        max_tp = max(rlist, key=lambda x: x["throughput_mmt"])
        chunks.append(
            {
                "chunk_id": f"IOCL-REF-{ref_id}-10YR",
                "fy": "FY17_FY26",
                "statement_type": "REFINERY_360",
                "note_ref": f"Refinery Operational Profile ({ref_id})",
                "line_codes": ["REF.THROUGHPUT_MMT", "REF.GRM_USD_BBL"],
                "title": f"{name} ({r26['state']}, {r26['region']}): 10-Year Throughput, GRM & Energy Profile",
                "content": (
                    f"{name} ({ref_id}, {r26['state']}) has installed capacity of {r26['installed_capacity_mmtpa']} MMTPA "
                    f"within IOCL Standalone's 70.25 MMTPA total (80.75 MMTPA group incl. CPCL). Over FY17-FY26, throughput evolved "
                    f"from {r17['throughput_mmt']} MMT (FY17) to {r26['throughput_mmt']} MMT (FY26, {r26['capacity_utilization_pct']}% "
                    f"utilization), peaking at {max_tp['throughput_mmt']} MMT in {max_tp['fiscal_year']}. 10-yr average GRM is "
                    f"${avg_grm:.2f}/bbl (FY26 GRM ${r26['grm_usd_bbl']}/bbl vs FY25 ${r25['grm_usd_bbl']}/bbl). FY26 Distillate Yield "
                    f"is {r26['distillate_yield_pct']}%, Fuel & Loss is {r26['fuel_and_loss_pct']}%, and unit opex is ${r26['opex_usd_bbl']}/bbl."
                ),
                "source_citation": f"IOCL Downstream 360 `ssot_refinery_economics_360` ({ref_id})",
            }
        )
        chunks.append(
            {
                "chunk_id": f"IOCL-REF-{ref_id}-PNL",
                "fy": "FY26",
                "statement_type": "REFINERY_360",
                "note_ref": f"Refinery P&L Contribution ({ref_id}, FY25-FY26)",
                "line_codes": ["PL.PBIDT", "PL.PBT", "REF.THROUGHPUT_MMT", "REF.GRM_USD_BBL"],
                "title": f"{name} ({ref_id}) FY25-FY26 Refinery P&L, EBITDA & Cost Economics",
                "content": (
                    f"In FY26, {name} ({ref_id}) generated Gross Revenue of Rs {r26['gross_revenue_inr_cr']:,.2f} Cr "
                    f"(Net Revenue Rs {r26['net_revenue_inr_cr']:,.2f} Cr), Refinery EBITDA of Rs {r26['ebitda_inr_cr']:,.2f} Cr "
                    f"(vs Rs {r25['ebitda_inr_cr']:,.2f} Cr in FY25), DD&A Rs {r26['dda_inr_cr']:,.2f} Cr, and PBT of "
                    f"Rs {r26['pbt_inr_cr']:,.2f} Cr on {r26['throughput_mmt']} MMT throughput. Note: standalone division financials "
                    f"reconcile with 0.00 Cr delta to IOCL Corporate Standalone P&L in `v_refinery_pnl_v3`."
                ),
                "source_citation": f"IOCL Downstream 360 `v_refinery_pnl_v3` ({ref_id})",
            }
        )

    # D. Subsidiaries, JVs & Consolidation Bridge (7 chunks)
    sub_hist: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in sub_rows:
        sub_hist[r["entity_code"]].append(r)
    for ecode, slist in sorted(sub_hist.items()):
        slist.sort(key=lambda x: int(x["fiscal_year"].replace("FY", "")))
        s26 = slist[-1]
        s25 = slist[-2]
        chunks.append(
            {
                "chunk_id": f"IOCL-SUB-{ecode}",
                "fy": "FY26",
                "statement_type": "CONSOLIDATED",
                "note_ref": f"Consolidated Group Entity ({ecode})",
                "line_codes": ["PL.CONSOL_PAT", "BS.INVESTMENTS_NC"],
                "title": f"IOCL Group Entity {s26['entity_name']} ({ecode}): FY25-FY26 Financials & Consolidation",
                "content": (
                    f"{s26['entity_name']} ({ecode}, IOCL equity holding {s26['iocl_equity_holding_pct']}%) recorded FY26 revenue of "
                    f"Rs {s26['revenue_inr_cr']:,.2f} Cr, EBITDA Rs {s26['ebitda_inr_cr']:,.2f} Cr, Entity PAT "
                    f"Rs {s26['pat_inr_cr']:,.2f} Cr, and IOCL Share of PAT Rs {s26['iocl_share_pat_inr_cr']:,.2f} Cr "
                    f"(vs Rs {s25['iocl_share_pat_inr_cr']:,.2f} Cr in FY25). ROCE: {s26['roce_pct']}%; Dividend received by IOCL: "
                    f"Rs {s26['dividend_received_by_iocl_inr_cr']:,.2f} Cr. {s26.get('notes', '')}"
                ),
                "source_citation": f"IOCL Consolidated Financial Statements / `subsidiary_financials` ({ecode})",
            }
        )

    # E. Marketing Products & Pipeline Networks (10 chunks)
    mkt_hist: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in mkt_rows:
        mkt_hist[r["product_code"]].append(r)
    for pcode, mlist in sorted(mkt_hist.items()):
        mlist.sort(key=lambda x: int(x["fiscal_year"].replace("FY", "")))
        m17, m26 = mlist[0], mlist[-1]
        chunks.append(
            {
                "chunk_id": f"IOCL-MKT-{pcode}",
                "fy": "FY17_FY26",
                "statement_type": "REFINERY_360",
                "note_ref": f"Marketing Product Mix ({pcode})",
                "line_codes": ["MKT.SALES_MMT", "PL.REV_OPS"],
                "title": f"IOCL Marketing Product {m26['product_category']} ({pcode}): 10-Year Volume, Share & Margin",
                "content": (
                    f"IOCL Marketing sales of {m26['product_category']} ({pcode}, {m26['product_group']}) scaled from "
                    f"{m17['sales_volume_mmt']} MMT (FY17) to {m26['sales_volume_mmt']} MMT (FY26; India market share "
                    f"{m26['market_share_india_pct']}%, revenue Rs {m26['revenue_inr_cr']:,.2f} Cr, gross marketing margin "
                    f"Rs {m26['gross_marketing_margin_inr_kl']:,.2f}/KL). {m26.get('notes', '')}"
                ),
                "source_citation": f"IOCL Marketing Operations `fact_marketing_sales` ({pcode})",
            }
        )

    pip_hist: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in pip_rows:
        pip_hist[r["pipeline_code"]].append(r)
    for pcode, plist in sorted(pip_hist.items()):
        plist.sort(key=lambda x: int(x["fiscal_year"].replace("FY", "")))
        p17, p26 = plist[0], plist[-1]
        chunks.append(
            {
                "chunk_id": f"IOCL-PIP-{pcode}",
                "fy": "FY17_FY26",
                "statement_type": "REFINERY_360",
                "note_ref": f"Pipeline Network ({pcode})",
                "line_codes": ["PIP.THROUGHPUT_MMT", "PL.PBIDT"],
                "title": f"IOCL Pipeline Network {pcode}: Length, Throughput, Utilization & Tariff EBITDA",
                "content": (
                    f"IOCL's {p26['pipeline_type']} expanded from {p17['pipeline_length_km']:,.0f} km / {p17['throughput_mmt']} MMT (FY17) "
                    f"to {p26['pipeline_length_km']:,.0f} km / {p26['throughput_mmt']} MMT (FY26, {p26['capacity_utilization_pct']}% utilization). "
                    f"FY26 Tariff Revenue reached Rs {p26['tariff_revenue_inr_cr']:,.2f} Cr and EBITDA Rs {p26['ebitda_inr_cr']:,.2f} Cr "
                    f"at unit operating cost of Rs {p26['unit_operating_cost_inr_mt']:,.2f}/MT."
                ),
                "source_citation": f"IOCL Pipelines Division `fact_pipeline_ops` ({pcode})",
            }
        )

    # F. Ind AS 108 Segments (FY26) & MoU Scorecard (FY25-FY26)
    seg26 = defaultdict(dict)
    for r in seg_rows:
        if r["fiscal_year"] == "FY26" and r["scope"] == "standalone":
            seg26[r["segment_code"]][r["metric"]] = r["value_inr_cr"]
    for scode, metrics in sorted(seg26.items()):
        chunks.append(
            {
                "chunk_id": f"IOCL-SEG-{scode}-FY26",
                "fy": "FY26",
                "statement_type": "PNL",
                "note_ref": f"Ind AS 108 Segment Reporting ({scode})",
                "line_codes": ["PL.REV_OPS", "PL.PBT", "OTH.CAPITAL_EMPLOYED"],
                "title": f"IOCL Ind AS 108 Segment {scode} (FY26): Revenue, EBIT Result & Capital Employed",
                "content": (
                    f"Under Ind AS 108 Segment Disclosures (FY26 Standalone), segment {scode} recorded Segment Revenue "
                    f"of Rs {metrics.get('segment_revenue', 0.0):,.2f} Cr, Segment EBIT Result of "
                    f"Rs {metrics.get('segment_result_ebit', 0.0):,.2f} Cr, Segment Assets "
                    f"Rs {metrics.get('segment_assets', 0.0):,.2f} Cr, and Capital Employed "
                    f"Rs {metrics.get('segment_capital_employed', 0.0):,.2f} Cr."
                ),
                "source_citation": f"IOCL Annual Report FY26 Ind AS 108 Segment Note ({scode})",
            }
        )

    mou_fy26 = [m for m in mou_rows if m["fiscal_year"] == "FY26"]
    if mou_fy26:
        mou_lines = "; ".join(
            f"{m['parameter_id']} ({m['parameter_name']}): Actual {m['actual_achievement']} {m['unit_of_measure']} "
            f"vs Excellent {m['excellent_target']} [{m['achieved_rating']}]"
            for m in mou_fy26[:8]
        )
        chunks.append(
            {
                "chunk_id": "IOCL-MOU-FY25-FY26",
                "fy": "FY26",
                "statement_type": "RATIOS",
                "note_ref": "DPE / MoPNG MoU Scorecard FY25-FY26",
                "line_codes": ["REV.NET_OF_EXCISE", "PL.PBIDT", "REF.THROUGHPUT_MMT", "CAPEX.TOTAL"],
                "title": "IOCL DPE MoU Performance Scorecard (FY25 vs FY26): Rating & KPI Achievement",
                "content": (
                    f"IOCL's DPE / MoPNG Memorandum of Understanding (MoU) tracks financial, downstream efficiency, capex, and "
                    f"ESG targets on a 100-point composite scale (FY25 composite score 3.82 'Very Good'; FY26 composite score "
                    f"4.35 'Excellent'). Key FY26 actuals: {mou_lines}."
                ),
                "source_citation": "IOCL DPE MoU Scorecard `fact_mou_scorecard` (FY25-FY26)",
            }
        )

    # G. Specific Schedule III Technical Notes & CFO Levers L01-L10 (16 chunks)
    technical_notes = [
        (
            "IOCL-NOTE-EXCISE",
            "FY17_FY26",
            "PNL",
            "Note 28: Central Excise Duty & Exchequer",
            ["LEVY.TOTAL", "REV.NET_OF_EXCISE"],
            "Gross vs Net Revenue & Excise Duty Pass-Through (Ind AS 115 / Note 28)",
            "Under Ind AS 115, IOCL presents Revenue from Operations Gross of Central Excise Duty (Rs 8,86,224.41 Cr in FY26) and reports Central Excise Duty (Rs 1,02,066.54 Cr in FY26) as a separate line item in Expenses, leaving Net Revenue of Rs 7,84,157.87 Cr. Excise peaked at Rs 1,36,832.00 Cr (26.6% of turnover) in FY21 during pandemic duty hikes before normalizing after November 2021 and May 2022 central duty cuts.",
        ),
        (
            "IOCL-NOTE-FY20-COVID",
            "FY20",
            "PNL",
            "Schedule III Line VI: Exceptional NRV Write-Down & Tax Regime Shift",
            ["PL.EXCEPTIONAL", "REF.GRM_USD_BBL", "BS.LEASE_LIAB_NC"],
            "FY20 COVID-19 Crude Crash (Rs 11,305 Cr Exceptional Loss), Core GRM & Ind AS 116",
            "In Q4 FY20, global lockdowns collapsed Brent crude below $23/bbl, forcing an exceptional inventory Net Realizable Value (NRV) write-down of Rs 11,305.00 Cr on Schedule III Line VI. Reported GRM sank to $0.08/bbl despite Core GRM holding at $4.10/bbl. Simultaneously, IOCL adopted Ind AS 116 Leases (bringing time-charter tankers and retail outlet leases onto the balance sheet) and shifted to the 25.168% Section 115BAA corporate tax regime.",
        ),
        (
            "IOCL-NOTE-LPG-GRANT",
            "FY23",
            "PNL",
            "Note 28 / LPG Subsidy & Price Freeze",
            ["PL.REV_OPS", "PL.PAT", "BS.BORROW_TOTAL_10YR"],
            "FY23 Retail MS/HSD Price Freeze, Rs 10,801 Cr GoI LPG Grant & 1:2 Bonus Shares",
            "In FY23, despite achieving all-time high Gross Revenue (Rs 9,34,953.00 Cr) and record Reported GRM ($19.52/bbl), unrecovered retail petrol/diesel margins compressed Marketing profitability. GoI sanctioned a one-time Rs 10,801.00 Cr LPG under-recovery grant recognized in operating revenue, protecting Rs 8,241.82 Cr Standalone PAT, while Total Debt expanded to Rs 1,32,495 Cr. IOCL also issued 1:2 bonus equity shares expanding paid-up shares to 1,412.1238 Cr.",
        ),
        (
            "IOCL-NOTE-LPG-DEPOSIT",
            "FY26",
            "BALANCE_SHEET",
            "Notes 24-25: Indane LPG Consumer Security Deposits",
            ["BS.OTHER_C_LIAB", "BS.LIAB.CURRENT.TOTAL"],
            "Structural Negative Working Capital: Indane LPG Security Deposits Float",
            "IOCL holds over Rs 34,000 Cr of Indane LPG consumer cylinder and regulator security deposits inside Other Current Liabilities (Notes 24-25), alongside ~Rs 46,000+ Cr of crude trade payables (15-45 day suppliers credit). Combined with ultra-low 6.1-day DSO on retail fuel sales, this creates structural negative Net Working Capital (~-Rs 38,000 Cr in FY26) that partially funds Capex without interest cost.",
        ),
        (
            "IOCL-NOTE-WACC-VAL",
            "FY26",
            "RATIOS",
            "DCF Valuation & WACC Capital Structure (NSE:IOC)",
            ["BS.BORROW_TOTAL_10YR", "PL.FIN_COST", "BS.EQUITY.TOTAL"],
            "NSE:IOC Share Count (1,412.1238 Cr), Debt, WACC (9.25%) & GRM Sensitivity",
            "IOCL equity base comprises 1,412.1238 Cr shares (NSE: IOC / Yahoo: IOC.NS; FY26 closing price Rs 135.40; Market Cap Rs 1,91,201.56 Cr). Against FY26 Standalone Total Debt of Rs 1,10,668.00 Cr and Cash of Rs 1,185.40 Cr (Net Debt Rs 1,09,482.60 Cr), FY26 WACC is 9.2534% (Ke 11.42%, pretax Kd 7.15%, post-tax Kd 5.35%). Each $1.00/bbl GRM move alters Standalone annual EBITDA by ~Rs 4,400-4,600 Cr.",
        ),
        (
            "IOCL-NOTE-CAPEX-P25",
            "FY26",
            "CASH_FLOW",
            "Major Refinery Expansions: Panipat P-25, Koyali & Barauni",
            ["BS.CWIP", "CAPEX.TOTAL", "BS.PPE_NET"],
            "Ongoing Brownfield Refinery & Petchem Capex Wave (70.25 -> 88+ MMTPA)",
            "IOCL invested Rs 36,910 Cr (FY25) and Rs 34,210 Cr (FY26) in brownfield refining and integrated petrochemicals: Panipat P-25 expansion (15.0 -> 25.0 MMTPA + PX/PTA), Gujarat/Koyali expansion (13.7 -> 18.0 MMTPA + lube base oil), Barauni expansion (6.0 -> 9.0 MMTPA), and cross-country product pipeline spurs (Paradip-Hyderabad, Koyali-Sanganer).",
        ),
        (
            "IOCL-NOTE-2-PPE",
            "FY26",
            "BALANCE_SHEET",
            "Note 2 & 2.1: Property, Plant & Equipment and CWIP Capitalization",
            ["BS.PPE_NET", "BS.CWIP", "PL.DDA"],
            "Net PPE (Rs 1,87,894.12 Cr) & CWIP (Rs 82,577.56 Cr) Capitalization Cycle",
            "Standalone Net PPE reached Rs 1,87,894.12 Cr in FY26 (+3.0% YoY vs Rs 1,82,388.60 Cr in FY25), while CWIP rose to Rs 82,577.56 Cr (vs Rs 73,453.16 Cr in FY25) during Panipat P-25, Koyali, and Barauni brownfield expansion. FY26 DD&A stood at Rs 16,964.82 Cr.",
        ),
        (
            "IOCL-NOTE-4-INV",
            "FY26",
            "BALANCE_SHEET",
            "Note 4: Non-Current Investments in Subsidiaries, JVs & FVOCI",
            ["BS.INVESTMENTS_NC", "PL.CONSOL_PAT"],
            "Strategic Non-Current Investments (Rs 64,771.13 Cr): CPCL, Petronet LNG, HURL & Equities",
            "Non-Current Investments totaled Rs 64,771.13 Cr in FY26, anchored by 51.89% control in Chennai Petroleum (CPCL), 75.12% in Lanka IOC, 100% in IOCME & IndOil Global, joint ventures HURL (29.67%) and Petronet LNG (12.50%), plus quoted FVOCI stakes in ONGC and Oil India.",
        ),
        (
            "IOCL-NOTE-11-INVENT",
            "FY26",
            "BALANCE_SHEET",
            "Note 11: Inventories Valuation (FIFO vs NRV) & DIO",
            ["BS.INVENTORIES", "RATIO.INVENTORY_DAYS", "PL.INVENTORY_CHANGE"],
            "Crude & Product Inventories (Rs 1,07,484.12 Cr, DIO 61.42 Days) & NRV Sensitivity",
            "Inventories of Rs 1,07,484.12 Cr in FY26 (61.42 days DIO) comprise crude pipeline/tank buffer plus finished fuels valued at lower of FIFO cost and Net Realizable Value (NRV). Crude volatility creates timing differences between Reported GRM and Core GRM.",
        ),
        (
            "IOCL-NOTE-13-TRADE-REC",
            "FY26",
            "BALANCE_SHEET",
            "Note 13: Trade Receivables & Institutional Credit",
            ["BS.TRADE_REC_C", "RATIO.DEBTORS_TURNOVER_DAYS"],
            "Ultra-Lean Trade Receivables (Rs 14,229.15 Cr, DSO 5.86 Days) via Retail Cash Velocity",
            "Trade Receivables stood at Rs 14,229.15 Cr in FY26 (DSO 5.86 days on Net Revenue), reflecting rapid 1-3 day dealer settlement across retail outlets, balanced against institutional credit to Indian Railways, Defence, domestic airlines (ATF), and OMC inter-company accounts.",
        ),
        (
            "IOCL-NOTE-17-BONUS",
            "FY26",
            "BALANCE_SHEET",
            "Notes 17-18: Share Capital, Reserves & Bonus History",
            ["BS.SHARE_CAPITAL", "BS.OTHER_EQUITY", "BS.EQUITY.TOTAL"],
            "Net Worth (Rs 2,04,544.34 Cr), FY18 1:1 & FY23 1:2 Bonus Issues, BVPS Rs 148.53",
            "IOCL expanded paid-up share capital through 1:1 bonus shares in FY18 and 1:2 bonus shares in FY23 (share capital Rs 13,771.56 Cr net of ESOP trust; 1,412.12 Cr issued shares of Rs 10 face value). Net Worth doubled from Rs 99,728.72 Cr (FY17) to Rs 2,04,544.34 Cr (FY26), lifting BVPS to Rs 148.53.",
        ),
        (
            "IOCL-NOTE-19-DEBT",
            "FY26",
            "BALANCE_SHEET",
            "Notes 19 & 22: Borrowings Composition & De-Leveraging",
            ["BS.BORROW_NC", "BS.BORROW_CUR", "BS.BORROW_TOTAL_10YR"],
            "Debt Mix (Rs 1,10,668.22 Cr Total = Rs 52,380.18 Cr LT + Rs 58,288.04 Cr ST) & D/E 0.54x",
            "IOCL reduced Total Borrowings by Rs 23,797.32 Cr in FY26 to Rs 1,10,668.22 Cr (Rs 52,380.18 Cr Non-Current + Rs 58,288.04 Cr Current Borrowings; plus Rs 8,545.60 Cr LT and Rs 3,388.78 Cr ST lease liabilities), lowering Debt-to-Equity from 0.75x (FY25) and 1.24x (FY20) to 0.54x while maintaining domestic AAA credit rating.",
        ),
        (
            "IOCL-NOTE-30-33-OPEX",
            "FY26",
            "PNL",
            "Notes 30-33: Crude Consumed, Fuel & Power, Employee & Freight Costs",
            ["PL.COST_MATERIALS", "PL.EMP_BENEFIT", "PL.OTHER_EXP"],
            "FY26 Cost Structure: Crude Consumed Rs 3,81,790.55 Cr, Employee Rs 10,788.96 Cr, Other Exp Rs 57,600.40 Cr",
            "In FY26, Cost of Materials Consumed reached Rs 3,81,790.55 Cr; Purchases of Stock-in-Trade were Rs 2,56,981.77 Cr; Employee Benefits Expense across 29,110 staff totaled Rs 10,788.96 Cr; Impairment loss on financial assets was Rs 2,366.75 Cr; and Other Expenses (Note 33) totaled Rs 57,600.40 Cr spanning refinery fuel/power, freight, bottling, and FX differences.",
        ),
        (
            "IOCL-NOTE-34-35-FIN-TAX",
            "FY26",
            "PNL",
            "Notes 34-35: Finance Costs, Interest Coverage & Sec 115BAA Tax",
            ["PL.FIN_COST", "PL.TAX_CURRENT", "PL.TAX_DEFERRED"],
            "FY26 Finance Costs Rs 7,969.02 Cr & Tax Expense Rs 11,981.99 Cr (24.56% ETR)",
            "Finance Costs eased -8.7% YoY from Rs 8,731.59 Cr (FY25) to Rs 7,969.02 Cr (FY26) alongside -Rs 23,797.32 Cr debt reduction. Total Tax Expense of Rs 11,981.99 Cr (Current Rs 11,757.63 Cr + Deferred Rs 224.36 Cr) reflects a 24.56% effective rate on Rs 48,784.41 Cr PBT under Sec 115BAA.",
        ),
        (
            "IOCL-NOTE-DIVIDEND-TSR",
            "FY17_FY26",
            "CASH_FLOW",
            "Dividend History, Payout Ratio & Maharatna Cash Return",
            ["RATIO.DPS", "CF.FIN_DIV_PAID", "OTH.DIVIDEND_DECLARED"],
            "10-Year Cash Dividend Distribution (FY26 Rs 13,769.24 Cr CF Outflow)",
            "IOCL distributed Rs 13,769.24 Cr in cash dividends in FY26 Cash Flow (37.4% of Rs 36,802.42 Cr Standalone PAT), following Rs 9,642.35 Cr in FY25 and Rs 11,021.81 Cr in FY24.",
        ),
    ]
    for cid, fy, stmt, nref, lcodes, title, content in technical_notes:
        chunks.append(
            {
                "chunk_id": cid,
                "fy": fy,
                "statement_type": stmt,
                "note_ref": nref,
                "line_codes": lcodes,
                "title": title,
                "content": content,
                "source_citation": f"IOCL Annual Report Notes ({nref})",
            }
        )

    lever_specs = [
        ("L01", "Refinery Fuel & Loss Reduction (-30 bps: 8.20% -> 7.90%)", "Rs 940 Cr/yr EBITDA", "Deploy flare-gas recovery, FCC flue-gas expanders, and WHRSG at Barauni, Haldia, Mathura, and NE units to cut internal energy consumption from 8.20% to 7.90% (~0.226 MMT crude equivalent saved)."),
        ("L02", "Opportunity Heavy Crude Slate & LP GRM Uplift (+$0.35/bbl)", "Rs 1,620 Cr/yr EBITDA", "Increase heavy/high-TAN opportunity crude share by +3.5 pp across Paradip and Koyali coker/hydrocracker trains via AI LP crude-blend optimization (DoA Clause 2.1)."),
        ("L03", "Distillate & Petchem Yield Shift (+50 bps: 82.8% -> 83.3%)", "Rs 1,180 Cr/yr EBITDA", "Upgrade vacuum residue conversion at Panipat/Paradip and shift naphtha feed toward higher-margin specialty polymers and butyl rubber intermediates."),
        ("L04", "Rail/Road to Pipeline Freight Shift (6.5 MMT modal migration)", "Rs 685 Cr/yr EBITDA", "Migrate 6.5 MMT inland HSD/MS depot dispatches from rail/road tankers (Rs 1,650/MT) onto Paradip-Hyderabad & Koyali-Sanganer pipelines (Rs 845/MT)."),
        ("L05", "Crude & Product Inventory DIO Compression (-3 days: 58.6 -> 55.6d)", "Rs 4,800 Cr Cash / Rs 340 Cr/yr Interest", "Tighten VLCC demurrage windows and coastal tank float by 3 DIO days to release ~Rs 4,800 Cr working capital and save Rs 340 Cr/yr short-term finance cost."),
        ("L06", "Commodity Crack & Unpriced Cargo Hedging (25%-35% band)", "Rs 1,100 Cr/yr Volatility Buffer", "Use IOCL-HEDGING Committee approved zero-cost collars and gasoil crack swaps covering 25%-35% of unpriced cargoes-in-transit."),
        ("L07", "Short-Term CP/WCDL De-Leveraging (-Rs 10,000 Cr Debt Paydown)", "Rs 720 Cr/yr Finance Cost Saving", "Apply FY27 OCF surplus and GoI LPG compensation receipts to retire Rs 10,000 Cr short-term WCDL/CP facilities, compressing WACC < 9.0% and D/E < 0.50x."),
        ("L08", "Premium Retail Fuel Mix (XP95/XtraGreen 12% -> 18% & SERVO)", "Rs 890 Cr/yr Marketing EBITDA", "Scale XP95 high-octane petrol, XtraGreen additive diesel, and SERVO synthetic lubes across highway COCO retail outlets (+Rs 1,400/KL differential)."),
        ("L09", "Stage-Gate Capex Hurdle Discipline (>= 12% Post-Tax Equity IRR)", "Rs 1,500 Cr/yr Capex Avoidance", "Enforce IOCL-CAPALLOC independent IRR gating on >Rs 100 Cr brownfield/petchem/CGD outlays and penalize CWIP execution delays > 6 months."),
        ("L10", "Green Hydrogen & Captive Solar Power Wheeling (35% Grid Shift)", "Rs 410 Cr/yr Opex & ESG Credit", "Shift 35% of grid power at Panipat & Mathura to captive solar + green hydrogen electrolyzer integration, lowering refinery emission intensity and Note 33 power cost."),
    ]
    for lcode, ltitle, impact, detail in lever_specs:
        chunks.append(
            {
                "chunk_id": f"IOCL-LEVER-{lcode}",
                "fy": "FY26",
                "statement_type": "REFINERY_360",
                "note_ref": f"CFO Diagnostic Lever {lcode}",
                "line_codes": ["PL.PBIDT", "REF.GRM_USD_BBL", "CAPEX.TOTAL", "BS.BORROW_TOTAL_10YR"],
                "title": f"CFO Action Lever {lcode}: {ltitle} ({impact})",
                "content": f"[{lcode}] {ltitle} | Quantified Impact: {impact}. Execution Playbook: {detail}",
                "source_citation": f"IOCL Director (Finance) Action Playbook ({lcode})",
            }
        )

    return chunks


# ---------------------------------------------------------------------------
# Part 3: Embed & Load to BigQuery (`labels={"datacloud": "jetski"}`)
# ---------------------------------------------------------------------------
def embed_chunks(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    cache: Dict[str, Tuple[str, List[float]]] = {}
    if EMBED_CACHE_JSONL.exists():
        for line in EMBED_CACHE_JSONL.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            obj = json.loads(line)
            if obj.get("chunk_id") and isinstance(obj.get("embedding"), list):
                cache[obj["chunk_id"]] = (obj.get("text_sha", ""), obj["embedding"])

    client = genai.Client(vertexai=True, project=PROJECT_ID, location=VERTEX_LOCATION)
    to_embed: List[Tuple[int, Dict[str, Any], str]] = []
    for idx, ch in enumerate(chunks):
        embed_text = f"{ch['title']}\nFY: {ch['fy']} | Ref: {ch['note_ref']}\n{ch['content']}"
        sha = hashlib.sha256(embed_text.encode("utf-8")).hexdigest()[:16]
        if ch["chunk_id"] in cache and cache[ch["chunk_id"]][0] == sha and len(cache[ch["chunk_id"]][1]) == EMBEDDING_DIM:
            ch["embedding"] = cache[ch["chunk_id"]][1]
        else:
            to_embed.append((idx, ch, sha))

    print(f"[notes_chunks] total={len(chunks)} cached={len(chunks) - len(to_embed)} to_embed={len(to_embed)}", flush=True)
    batch_size = 32
    for start in range(0, len(to_embed), batch_size):
        batch = to_embed[start : start + batch_size]
        texts = [f"{ch['title']}\nFY: {ch['fy']} | Ref: {ch['note_ref']}\n{ch['content']}" for _, ch, _ in batch]
        for attempt in range(4):
            try:
                resp = client.models.embed_content(
                    model=EMBEDDING_MODEL,
                    contents=texts,
                    config=genai_types.EmbedContentConfig(
                        task_type="RETRIEVAL_DOCUMENT",
                        output_dimensionality=EMBEDDING_DIM,
                    ),
                )
                for (orig_idx, ch, sha), emb in zip(batch, resp.embeddings):
                    vec = [float(x) for x in emb.values]
                    ch["embedding"] = vec
                    cache[ch["chunk_id"]] = (sha, vec)
                break
            except Exception as exc:
                if attempt == 3:
                    raise
                print(f"  retry {attempt + 1} after embedding error: {exc}", flush=True)
                time.sleep(2 ** (attempt + 1))

    EMBED_CACHE_JSONL.parent.mkdir(parents=True, exist_ok=True)
    with EMBED_CACHE_JSONL.open("w", encoding="utf-8") as fh:
        for ch in chunks:
            embed_text = f"{ch['title']}\nFY: {ch['fy']} | Ref: {ch['note_ref']}\n{ch['content']}"
            sha = hashlib.sha256(embed_text.encode("utf-8")).hexdigest()[:16]
            fh.write(json.dumps({"chunk_id": ch["chunk_id"], "text_sha": sha, "embedding": ch["embedding"]}) + "\n")

    return chunks


def load_bigquery(line_ctx_rows: List[Dict[str, Any]], note_chunks: List[Dict[str, Any]]) -> None:
    bq = bigquery.Client(project=PROJECT_ID, location=BQ_LOCATION)

    # Ensure datasets
    for ds_name in ("hrfin_gold", "hrfin_gold_v3", "hrfin_docs"):
        ds = bigquery.Dataset(f"{PROJECT_ID}.{ds_name}")
        ds.location = BQ_LOCATION
        bq.create_dataset(ds, exists_ok=True)

    # 1. Load ssot_financial_line_context into hrfin_gold & hrfin_gold_v3
    line_ctx_schema = [
        bigquery.SchemaField("context_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("fy", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("statement_type", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("line_code", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("line_name", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("note_ref", "STRING"),
        bigquery.SchemaField("amount_cr", "FLOAT64"),
        bigquery.SchemaField("prev_amount_cr", "FLOAT64"),
        bigquery.SchemaField("yoy_delta_cr", "FLOAT64"),
        bigquery.SchemaField("yoy_delta_pct", "FLOAT64"),
        bigquery.SchemaField("what_happened_summary", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("annual_report_context", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("historical_10yr_context", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("director_finance_action", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("source_citation", "STRING", mode="REQUIRED"),
    ]
    for ds_name in ("hrfin_gold", "hrfin_gold_v3"):
        table_id = f"{PROJECT_ID}.{ds_name}.ssot_financial_line_context"
        cfg = bigquery.LoadJobConfig(
            schema=line_ctx_schema,
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
            labels=ATTRIBUTION_LABELS,
        )
        bq.load_table_from_json(line_ctx_rows, table_id, job_config=cfg).result()
        t = bq.get_table(table_id)
        print(f"Loaded {table_id}: {t.num_rows} rows", flush=True)

    # 2. Load hrfin_docs.financial_notes_chunks
    notes_schema = [
        bigquery.SchemaField("chunk_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("fy", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("statement_type", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("note_ref", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("line_codes", "STRING", mode="REPEATED"),
        bigquery.SchemaField("title", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("content", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("source_citation", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("embedding", "FLOAT64", mode="REPEATED"),
    ]
    notes_table_id = f"{PROJECT_ID}.hrfin_docs.financial_notes_chunks"
    cfg_notes = bigquery.LoadJobConfig(
        schema=notes_schema,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        labels=ATTRIBUTION_LABELS,
    )
    bq.load_table_from_json(note_chunks, notes_table_id, job_config=cfg_notes).result()
    t_notes = bq.get_table(notes_table_id)
    t_notes.description = "IOCL FY17-FY26 Schedule III Notes, Downstream 360, Yahoo IOC.NS Crosswalk & CFO Levers (text-embedding-005 768-d)"
    bq.update_table(t_notes, ["description"])
    print(f"Loaded {notes_table_id}: {t_notes.num_rows} rows", flush=True)

    # 3. Create Vector Index if supported (BigQuery IVF works seamlessly or falls back gracefully if < min rows)
    ix_sql = f"""
    CREATE VECTOR INDEX IF NOT EXISTS ix_financial_notes_chunks
    ON `{notes_table_id}`(embedding)
    OPTIONS(index_type='IVF', distance_type='COSINE')
    """
    try:
        bq.query(ix_sql, job_config=bigquery.QueryJobConfig(labels=ATTRIBUTION_LABELS)).result()
        print("Created vector index ix_financial_notes_chunks on hrfin_docs.financial_notes_chunks", flush=True)
    except Exception as exc:
        print(f"Note on vector index creation (VECTOR_SEARCH still works brute-force on {t_notes.num_rows} rows): {exc}", flush=True)


def load_bigquery_cli(line_ctx_rows: List[Dict[str, Any]], note_chunks: Optional[List[Dict[str, Any]]] = None) -> None:
    line_ctx_schema_json = [
        {"name": "context_id", "type": "STRING", "mode": "REQUIRED"},
        {"name": "fy", "type": "STRING", "mode": "REQUIRED"},
        {"name": "statement_type", "type": "STRING", "mode": "REQUIRED"},
        {"name": "line_code", "type": "STRING", "mode": "REQUIRED"},
        {"name": "line_name", "type": "STRING", "mode": "REQUIRED"},
        {"name": "note_ref", "type": "STRING", "mode": "NULLABLE"},
        {"name": "amount_cr", "type": "FLOAT64", "mode": "NULLABLE"},
        {"name": "prev_amount_cr", "type": "FLOAT64", "mode": "NULLABLE"},
        {"name": "yoy_delta_cr", "type": "FLOAT64", "mode": "NULLABLE"},
        {"name": "yoy_delta_pct", "type": "FLOAT64", "mode": "NULLABLE"},
        {"name": "what_happened_summary", "type": "STRING", "mode": "REQUIRED"},
        {"name": "annual_report_context", "type": "STRING", "mode": "REQUIRED"},
        {"name": "historical_10yr_context", "type": "STRING", "mode": "REQUIRED"},
        {"name": "director_finance_action", "type": "STRING", "mode": "REQUIRED"},
        {"name": "source_citation", "type": "STRING", "mode": "REQUIRED"},
    ]
    with tempfile.TemporaryDirectory(prefix="iocl_rag_bq_") as tmpdir:
        tmp = Path(tmpdir)
        ndjson_p = tmp / "ssot_financial_line_context.jsonl"
        schema_p = tmp / "ssot_financial_line_context.schema.json"
        ndjson_p.write_text("\n".join(json.dumps(r) for r in line_ctx_rows) + "\n", encoding="utf-8")
        schema_p.write_text(json.dumps(line_ctx_schema_json, indent=2), encoding="utf-8")
        for ds_name in ("hrfin_gold", "hrfin_gold_v3"):
            table_id = f"{PROJECT_ID}:{ds_name}.ssot_financial_line_context"
            subprocess.run(
                [
                    "bq",
                    "load",
                    "--replace",
                    "--source_format=NEWLINE_DELIMITED_JSON",
                    f"--project_id={PROJECT_ID}",
                    f"--location={BQ_LOCATION}",
                    "--label",
                    "datacloud:jetski",
                    f"--schema={schema_p}",
                    table_id,
                    str(ndjson_p),
                ],
                check=True,
            )
            print(f"[bq-cli] Loaded {table_id}: {len(line_ctx_rows)} rows", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="IOCL RAG & Context Bridge Builder")
    parser.add_argument("--local-only", action="store_true", help="Only regenerate local JSON/JSONL files; skip Vertex/BQ")
    parser.add_argument("--bq-cli", action="store_true", help="Use bq CLI (subprocess) instead of Python BQ client")
    parser.add_argument("--skip-embed", action="store_true", help="Skip Vertex embedding call (only reload ssot_financial_line_context if --bq-cli)")
    args = parser.parse_args()

    corp_rows = _load_json(DATA_DIR / "iocl_10yr_corporate_wide.json")
    ref_rows = _load_json(DATA_DIR / "ssot_refinery_economics_360.json")
    mkt_rows = _load_json(DATA_DIR / "fact_marketing_sales.json")
    pip_rows = _load_json(DATA_DIR / "fact_pipeline_ops.json")
    sub_rows = _load_json(DATA_DIR / "subsidiary_financials.json")
    seg_rows = _load_json(DATA_DIR / "fact_segment.json")
    mou_rows = _load_json(DATA_DIR / "fact_mou_scorecard.json")

    line_ctx_rows = build_line_context_rows(corp_rows)
    LINE_CTX_JSON.write_text(json.dumps(line_ctx_rows, indent=2), encoding="utf-8")
    print(f"Wrote {LINE_CTX_JSON}: {len(line_ctx_rows)} rows", flush=True)

    note_chunks = build_financial_notes_chunks(corp_rows, ref_rows, mkt_rows, pip_rows, sub_rows, seg_rows, mou_rows)
    with CORPUS_JSONL.open("w", encoding="utf-8") as fh:
        for ch in note_chunks:
            fh.write(json.dumps({k: v for k, v in ch.items() if k != "embedding"}) + "\n")
    print(f"Wrote {CORPUS_JSONL}: {len(note_chunks)} chunks", flush=True)

    if MANIFEST_PATH.exists():
        manifest = _load_json(MANIFEST_PATH)
    else:
        manifest = {"files": {}}
    for p in (LINE_CTX_JSON, CORPUS_JSONL):
        manifest.setdefault("files", {})[p.name] = hashlib.sha256(p.read_bytes()).hexdigest()
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    if args.local_only:
        return
    if args.bq_cli:
        embedded = None if args.skip_embed else embed_chunks(note_chunks)
        load_bigquery_cli(line_ctx_rows, embedded)
        return

    embedded_chunks = embed_chunks(note_chunks)
    load_bigquery(line_ctx_rows, embedded_chunks)


if __name__ == "__main__":
    main()
