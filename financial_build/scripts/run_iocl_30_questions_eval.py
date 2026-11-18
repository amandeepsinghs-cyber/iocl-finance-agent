#!/usr/bin/env python3
"""
Step 8 End-to-End Evaluation: 30 Curated IOCL Finance & Downstream Questions (Q01-Q30) + Follow-ups.

Executes all 30 curated IndianOil CFO/Board scenarios from build.md §2 plus multi-turn follow-ups
directly through yukti.backend's AgentTurnRunner against live BigQuery (yukti-finance-iocl) and
Vertex AI (gemini-3-flash-preview / text-embedding-005), saving structured results to:
  financial_build/data/iocl_30_questions_eval_results.json
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Dict, List

os.environ.pop("GOOGLE_CLOUD_PROJECT", None)
os.environ["TARGET_PROJECT"] = "yukti-finance-iocl"
os.environ["YUKTI_GCP_PROJECT"] = "yukti-finance-iocl"
os.environ.setdefault("YUKTI_LIVE_BQ", "1")
os.environ.setdefault("YUKTI_PLANNER", "1")
os.environ.setdefault("YUKTI_RESULT_CACHE", "0")
os.environ.setdefault("CLOUDSDK_METRICS_ENVIRONMENT", "datacloud.jetski")

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "yukti" / "backend"
OUT_JSON = REPO_ROOT / "financial_build" / "data" / "iocl_30_questions_eval_results.json"

sys.path.insert(0, str(BACKEND_DIR))

from app.config import DEFAULT_TEXT_MODEL  # noqa: E402
from app.turn_runner import AgentTurnRunner  # noqa: E402


CASES: List[Dict[str, Any]] = [
    # Pillar 1: Schedule III Statement of Profit & Loss & Gross-vs-Net Excise Bridge
    {
        "id": "Q01",
        "pillar": "P1_PNL",
        "persona": "CMD",
        "query": "Show the Schedule III Profit and Loss statement of IOCL for FY26",
        "expect_access": "allowed",
        "expect_any": ["8,86,224", "886224", "36,802", "36802"],
        "followup": {
            "id": "Q01_FU",
            "query": "Plot it as a waterfall chart",
            "expect_access": "allowed",
            "expect_visual_types": ["chart", "statement"],
        },
    },
    {
        "id": "Q02",
        "pillar": "P1_PNL",
        "persona": "DIR_FIN",
        "query": "Show IOCL's 10-year Revenue Net of Excise, EBITDA, and PAT trend from FY17 to FY26",
        "expect_access": "allowed",
        "expect_any": ["FY17", "FY26", "36,802", "7,84,157", "784157"],
        "followup": {
            "id": "Q02_FU",
            "query": "Overlay Brent crude and USD/INR on the 10-year PAT chart",
            "expect_access": "allowed",
        },
    },
    {
        "id": "Q03",
        "pillar": "P1_PNL",
        "persona": "CMD",
        "query": "Compare IOCL Gross Revenue including Excise Duty vs Net Revenue from Operations across FY17 to FY26",
        "expect_access": "allowed",
        "expect_any": ["8,86,224", "7,84,157", "1,02,066", "excise"],
    },
    {
        "id": "Q04",
        "pillar": "P1_PNL",
        "persona": "DIR_FIN",
        "query": "Break down IOCL's Cost of Materials Consumed and Inventory Valuation changes from FY20 to FY26",
        "expect_access": "allowed",
        "expect_any": ["cost of materials", "inventory", "material", "FY26"],
    },
    {
        "id": "Q05",
        "pillar": "P1_PNL",
        "persona": "CMD",
        "query": "How did MS/HSD retail price freezes and domestic LPG under-recoveries impact IOCL's P&L in FY23 vs FY25-FY26?",
        "expect_access": "allowed",
        "expect_any": ["FY23", "LPG", "8,24", "8241", "margin", "under-recover"],
    },
    {
        "id": "Q06",
        "pillar": "P1_PNL",
        "persona": "DIR_FIN",
        "query": "Reconcile IOCL Standalone PAT to Consolidated Group PAT (IOC.NS) for FY24, FY25, and FY26, including CPCL and Lanka IOC",
        "expect_access": "allowed",
        "expect_any": ["CPCL", "Lanka IOC", "36,802", "consolidated", "standalone"],
    },
    # Pillar 2: Refinery Economics 360, Pipeline Logistics & Product Marketing
    {
        "id": "Q07",
        "pillar": "P2_DOWNSTREAM",
        "persona": "DIR_REF",
        "query": "Rank all IOCL refineries by Gross Refining Margin ($/bbl) and PBT in FY26",
        "expect_access": "allowed",
        "expect_any": ["Paradip", "Panipat", "12.46", "7,661"],
        "followup": {
            "id": "Q07_FU",
            "query": "Compare IOCL corporate GRM against Singapore Complex GRM over 10 years",
            "expect_access": "allowed",
        },
    },
    {
        "id": "Q08",
        "pillar": "P2_DOWNSTREAM",
        "persona": "CMD",
        "query": "Show crude throughput (MMT) and capacity utilization % across Panipat, Paradip, Koyali, Mathura, Haldia, Barauni, Bongaigaon, Guwahati, and Digboi in FY26",
        "expect_access": "allowed",
        "expect_any": ["Panipat", "Paradip", "75.45", "16.42", "Digboi"],
    },
    {
        "id": "Q09",
        "pillar": "P2_DOWNSTREAM",
        "persona": "DIR_REF",
        "query": "Compare distillate yield % and fuel & loss % across all 9 IOCL refineries in FY26",
        "expect_access": "allowed",
        "expect_any": ["distillate", "fuel", "Paradip", "Panipat"],
    },
    {
        "id": "Q10",
        "pillar": "P2_DOWNSTREAM",
        "persona": "CMD",
        "query": "What was IOCL's crude, product, and gas pipeline throughput (MMT) and EBITDA contribution from FY17 to FY26?",
        "expect_access": "allowed",
        "expect_any": ["pipeline", "MMT", "EBITDA", "FY26"],
    },
    {
        "id": "Q11",
        "pillar": "P2_DOWNSTREAM",
        "persona": "DIR_MKT",
        "query": "Break down IOCL's domestic petroleum product sales volume (MMT) across MS, HSD, ATF, Indane LPG, Bitumen, and Lubes in FY26",
        "expect_access": "allowed",
        "expect_any": ["105.1", "HSD", "LPG", "MMT", "sales"],
    },
    {
        "id": "Q12",
        "pillar": "P2_DOWNSTREAM",
        "persona": "DIR_FIN",
        "query": "Compare revenue, EBIT, and capital employed across IOCL's Petroleum Products, Petrochemicals, and Other Business segments from FY17 to FY26",
        "expect_access": "allowed",
        "expect_any": ["Petroleum", "Petrochemical", "segment", "FY26"],
    },
    # Pillar 3: Schedule III Balance Sheet, Borrowings, Working Capital & Mega-Capex
    {
        "id": "Q13",
        "pillar": "P3_BALANCE_SHEET",
        "persona": "CMD",
        "query": "Show IOCL's Schedule III Balance Sheet for FY26",
        "expect_access": "allowed",
        "expect_any": ["4,91,535", "491535", "2,04,544", "204544"],
        "followup": {
            "id": "Q13_FU",
            "query": "Show the 10-year growth of Net Worth and Capital Employed from FY17 to FY26",
            "expect_access": "allowed",
        },
    },
    {
        "id": "Q14",
        "pillar": "P3_BALANCE_SHEET",
        "persona": "DIR_FIN",
        "query": "How did IOCL's Total Borrowings and Debt-to-Equity ratio move from FY17 to FY26?",
        "expect_access": "allowed",
        "expect_any": ["1,10,668", "110668", "debt", "borrowing"],
    },
    {
        "id": "Q15",
        "pillar": "P3_BALANCE_SHEET",
        "persona": "DIR_FIN",
        "query": "Show IOCL's Inventory Days, Receivable Days, and Net Working Capital across FY17 to FY26",
        "expect_access": "allowed",
        "expect_any": ["inventory", "receivable", "working capital", "days"],
    },
    {
        "id": "Q16",
        "pillar": "P3_BALANCE_SHEET",
        "persona": "CMD",
        "query": "Show IOCL's Capital Expenditure spent and CWIP across FY17 to FY26",
        "expect_access": "allowed",
        "expect_any": ["capex", "CWIP", "capital expenditure", "FY26"],
    },
    # Pillar 4: Ind-AS 7 Cash Flow Statement, Dividends & DPE Maharatna MoU
    {
        "id": "Q17",
        "pillar": "P4_CASHFLOW_MOU",
        "persona": "DIR_FIN",
        "query": "Show IOCL's Cash Flow Statement for FY26",
        "expect_access": "allowed",
        "expect_any": ["operating", "investing", "financing", "cash flow"],
        "followup": {
            "id": "Q17_FU",
            "query": "Plot the Cash Flow statement as a waterfall chart",
            "expect_access": "allowed",
        },
    },
    {
        "id": "Q18",
        "pillar": "P4_CASHFLOW_MOU",
        "persona": "CMD",
        "query": "Show IOCL's Basic EPS, Dividend per Share, and Total Contribution to Central & State Exchequers from FY17 to FY26",
        "expect_access": "allowed",
        "expect_any": ["26.06", "2,41,890", "241890", "EPS", "exchequer"],
    },
    {
        "id": "Q19",
        "pillar": "P4_CASHFLOW_MOU",
        "persona": "DIR_FIN",
        "query": "Show IOCL's complete Financial Ratios scorecard (ROCE, ROE, EBITDA Margin, Current Ratio, Debt/Equity) for FY26 vs 10-year history",
        "expect_access": "allowed",
        "expect_any": ["ROCE", "ROE", "EBITDA", "FY26"],
    },
    {
        "id": "Q20",
        "pillar": "P4_CASHFLOW_MOU",
        "persona": "CMD",
        "query": "How is IOCL tracking against its FY26 MoPNG / DPE Maharatna MoU targets?",
        "expect_access": "allowed",
        "expect_any": ["MoU", "throughput", "capex", "target"],
    },
    # Pillar 5: Yahoo Finance (IOC.NS), Macro Sensitivity, WACC, CFO Levers & DCF Valuation
    {
        "id": "Q21",
        "pillar": "P5_MARKET_DCF",
        "persona": "CMD",
        "query": "Plot Brent crude oil price for the past 5 years",
        "expect_access": "allowed",
        "expect_any": ["Brent", "$/bbl", "BZ=F"],
    },
    {
        "id": "Q22",
        "pillar": "P5_MARKET_DCF",
        "persona": "DIR_REF",
        "query": "What-if: If Gross Refining Margin improves by $1.50/bbl or Brent moves to $70/bbl, how do IOCL EBITDA and PAT change?",
        "expect_access": "allowed",
        "expect_any": ["GRM", "EBITDA", "PAT", "Brent"],
    },
    {
        "id": "Q23",
        "pillar": "P5_MARKET_DCF",
        "persona": "DIR_FIN",
        "query": "What happens to IOCL's financials if USD/INR depreciates by ₹3 per US dollar?",
        "expect_access": "allowed",
        "expect_any": ["rupee", "INR", "USD", "dollar", "forex"],
    },
    {
        "id": "Q24",
        "pillar": "P5_MARKET_DCF",
        "persona": "DIR_FIN",
        "query": "What is IOCL's WACC in FY26, and what are Cost of Equity (Ke), After-Tax Cost of Debt (Kd), Beta, and capital weights?",
        "expect_access": "allowed",
        "expect_any": ["9.25", "11.51", "7.15", "WACC"],
    },
    {
        "id": "Q25",
        "pillar": "P5_MARKET_DCF",
        "persona": "DIR_FIN",
        "query": "What are the top 5 quantified CFO turnaround levers to expand IOCL EBITDA, ROCE, and Free Cash Flow in FY27?",
        "expect_access": "allowed",
        "expect_any": ["GRM", "lever", "EBITDA", "FCF", "L0"],
    },
    {
        "id": "Q26",
        "pillar": "P5_MARKET_DCF",
        "persona": "DIR_FIN",
        "query": "Run a DCF valuation for IOCL (NSE:IOC) using FY26 SSOT actuals and market price",
        "expect_access": "allowed",
        "expect_any": ["DCF", "WACC", "135.4", "9.25", "intrinsic", "valuation"],
    },
    # Pillar 6: Finance Policy RAG, Persona RBAC & Executive Deliverables
    {
        "id": "Q27",
        "pillar": "P6_POLICY_RBAC_DOC",
        "persona": "CMD",
        "query": "Under IOCL's Delegation of Financial Powers (DoA), what are the approval thresholds for spot crude oil cargo procurement and refinery turnaround capex?",
        "expect_access": "allowed",
        "expect_any": ["DoA", "Delegation", "crude", "IOCL-DOA"],
    },
    {
        "id": "Q28",
        "pillar": "P6_POLICY_RBAC_DOC",
        "persona": "DIR_FIN",
        "query": "What does IOCL's Risk Management & Hedging Policy permit for crack-spread hedging, inventory price protection, and USD/INR forward cover?",
        "expect_access": "allowed",
        "expect_any": ["hedg", "crack", "inventory", "IOCL-HEDGING"],
    },
    {
        "id": "Q29",
        "pillar": "P6_POLICY_RBAC_DOC",
        "persona": "E2_FIN",
        "query": "Show confidential counterparty credit exposure by customer sub-ledger and unpublished Board draft pack",
        "expect_access": "refused",
        "expect_any": ["restricted", "approval", "Director (Finance)", "Chairman"],
    },
    {
        "id": "Q30",
        "pillar": "P6_POLICY_RBAC_DOC",
        "persona": "CMD",
        "query": "Draft a Board Note for the Chairman and Director (Finance) on FY26 Refinery GRM performance and FY27 Capex funding plan",
        "expect_access": "allowed",
        "expect_visual_types": ["document"],
        "expect_any": ["Board", "Refinery", "GRM", "Capex"],
    },
]


def _evaluate_response(case: Dict[str, Any], resp: Dict[str, Any], elapsed_ms: float) -> Dict[str, Any]:
    acc_status = (resp.get("access") or {}).get("status", "unknown")
    vis_type = (resp.get("visual") or {}).get("type", "none")
    spoken = resp.get("spoken_summary") or ""
    display = resp.get("display_text") or ""
    blob = json.dumps(resp, ensure_ascii=False, default=str)

    errors: List[str] = []
    if not resp.get("turn_id"):
        errors.append("missing turn_id")
    if not spoken.strip() and not display.strip():
        errors.append("empty spoken_summary and display_text")
    exp_acc = case.get("expect_access", "allowed")
    if exp_acc == "refused":
        if acc_status != "refused":
            errors.append(f"expected access=refused, got {acc_status}")
    elif acc_status not in ("allowed", "partial"):
        errors.append(f"expected access=allowed, got {acc_status}")

    exp_vis = case.get("expect_visual_types")
    if exp_vis and vis_type not in exp_vis:
        errors.append(f"expected visual.type in {exp_vis}, got {vis_type}")

    exp_any = case.get("expect_any") or []
    if exp_any and not any(tok.lower() in blob.lower() for tok in exp_any):
        errors.append(f"none of {exp_any} found in contract payload")

    return {
        "id": case["id"],
        "pillar": case.get("pillar", "FOLLOWUP"),
        "persona": case["persona"],
        "query": case["query"],
        "status": "PASS" if not errors else "FAIL",
        "elapsed_ms": round(elapsed_ms, 1),
        "access_status": acc_status,
        "visual_type": vis_type,
        "tool_called": resp.get("tool_called"),
        "n_sources": len(resp.get("sources") or []),
        "spoken_preview": (spoken or display)[:220],
        "errors": errors,
    }


async def main() -> int:
    runner = AgentTurnRunner(model_name=DEFAULT_TEXT_MODEL)
    records: List[Dict[str, Any]] = []
    run_tag = int(time.time())

    for case in CASES:
        sid = f"iocl-30q-{case['id'].lower()}-{run_tag}"
        t0 = time.perf_counter()
        try:
            resp = await runner.execute_turn_async(
                case["query"],
                session_id=sid,
                persona=case["persona"],
            )
            rec = _evaluate_response(case, resp, (time.perf_counter() - t0) * 1000.0)
        except Exception as exc:
            rec = {
                "id": case["id"],
                "pillar": case["pillar"],
                "persona": case["persona"],
                "query": case["query"],
                "status": "FAIL",
                "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 1),
                "access_status": "error",
                "visual_type": "none",
                "tool_called": None,
                "n_sources": 0,
                "spoken_preview": "",
                "errors": [repr(exc)],
            }
        records.append(rec)
        print(f"[{rec['status']}] {rec['id']} ({rec['persona']}, {rec['elapsed_ms']}ms, vis={rec['visual_type']}): {rec['spoken_preview'][:90]}")
        if rec["errors"]:
            print(f"       ERRORS: {rec['errors']}")

        fu = case.get("followup")
        if fu:
            fu_case = {**fu, "pillar": case["pillar"], "persona": case["persona"]}
            t1 = time.perf_counter()
            try:
                resp_fu = await runner.execute_turn_async(
                    fu["query"],
                    session_id=sid,
                    persona=case["persona"],
                )
                rec_fu = _evaluate_response(fu_case, resp_fu, (time.perf_counter() - t1) * 1000.0)
            except Exception as exc:
                rec_fu = {
                    "id": fu["id"],
                    "pillar": case["pillar"],
                    "persona": case["persona"],
                    "query": fu["query"],
                    "status": "FAIL",
                    "elapsed_ms": round((time.perf_counter() - t1) * 1000.0, 1),
                    "access_status": "error",
                    "visual_type": "none",
                    "tool_called": None,
                    "n_sources": 0,
                    "spoken_preview": "",
                    "errors": [repr(exc)],
                }
            records.append(rec_fu)
            print(f"[{rec_fu['status']}] {rec_fu['id']} ({rec_fu['persona']}, {rec_fu['elapsed_ms']}ms, vis={rec_fu['visual_type']}): {rec_fu['spoken_preview'][:90]}")
            if rec_fu["errors"]:
                print(f"       ERRORS: {rec_fu['errors']}")

    total = len(records)
    passed = sum(1 for r in records if r["status"] == "PASS")
    q30_records = [r for r in records if not r["id"].endswith("_FU")]
    q30_passed = sum(1 for r in q30_records if r["status"] == "PASS")
    fu_records = [r for r in records if r["id"].endswith("_FU")]
    fu_passed = sum(1 for r in fu_records if r["status"] == "PASS")

    summary = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "project": "yukti-finance-iocl",
        "model": DEFAULT_TEXT_MODEL,
        "total_turns": total,
        "total_passed": passed,
        "q30_total": len(q30_records),
        "q30_passed": q30_passed,
        "followups_total": len(fu_records),
        "followups_passed": fu_passed,
        "results": records,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSUMMARY: {passed}/{total} turns PASS (Q01-Q30: {q30_passed}/{len(q30_records)}, Follow-ups: {fu_passed}/{len(fu_records)}) -> {OUT_JSON}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
