"""Multi-year Cash Flow Trend skill (R4, plan_fix.md).

Handles "show me the total cash flow for the past 10 years" / "cash flow trend for the past 5 years" with a verified
multi-series chart (Operating, Investing, Financing CF and Free Cash Flow = OCF − Capex) from `fact_snapshot.parquet`
(standalone, FY17–FY26). Never lets Annual Report RAG claim the series is unavailable.
"""
from __future__ import annotations

import re
import time
from functools import lru_cache
from typing import Any, Dict, List, Optional

from app.brain.inr_format import fmt_inr_cr

_CF_RE = re.compile(r"\bcash[\s-]*flows?\b", re.I)
_TREND_RE = re.compile(
    r"\b(total|trend|trends|past|last|over\s+the\s+(?:past|last)|history|historical|decade|years?|yrs?|movement|plot|chart|graph)\b", re.I
)
_EXCLUDE_RE = re.compile(
    r"\b(statement|dcf|fcff|forecast|2036|fy36|extend|overlay|stock|share\s+price|valuation|wacc|what[\s-]+if|explain|why)\b", re.I
)
_WORDNUM = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
_FYS = [f"FY{y:02d}" for y in range(17, 27)]


def detect_cashflow_trend(query: str) -> Optional[Dict[str, Any]]:
    q = (query or "").strip()
    if not q or not _CF_RE.search(q) or not _TREND_RE.search(q) or _EXCLUDE_RE.search(q):
        return None
    years = 10
    m = re.search(r"\b(\d{1,2}|two|three|four|five|six|seven|eight|nine|ten)\s*(?:years?|yrs?)\b", q, re.I)
    if m:
        n = m.group(1).lower()
        years = int(n) if n.isdigit() else _WORDNUM.get(n, 10)
    elif re.search(r"\bdecade\b", q, re.I):
        years = 10
    return {"kind": "cashflow_trend", "years": max(2, min(10, years))}


@lru_cache(maxsize=1)
def _cf_by_fy() -> Dict[str, Dict[str, float]]:
    import pandas as pd
    from app.finance.dcf.inputs import SNAPSHOT_PARQUET

    df = pd.read_parquet(SNAPSHOT_PARQUET)
    mask = (df["scope"] == "standalone") & df["line_code"].isin(["CF.CFO", "CF.CFI", "CF.CFF", "CF.NET_CHANGE_CCE", "CAPEX.TOTAL"])
    if "is_latest_vintage" in df.columns:
        mask &= df["is_latest_vintage"] == True  # noqa: E712
    out: Dict[str, Dict[str, float]] = {}
    for _, r in df[mask].iterrows():
        try:
            v = float(r["value_inr_cr"])
        except (TypeError, ValueError):
            continue
        if v == v:
            out.setdefault(str(r["fiscal_year"]), {}).setdefault(str(r["line_code"]), v)
    return out


def build_cashflow_trend_contract(req: Dict[str, Any], persona: str, turn_id: str, language: str, t0: float) -> Dict[str, Any]:
    data = _cf_by_fy()
    fys = [fy for fy in _FYS if "CF.CFO" in data.get(fy, {})][-int(req.get("years") or 10):]
    if len(fys) < 2:
        raise RuntimeError("cash flow series unavailable")
    rows: List[Dict[str, Any]] = []
    for fy in fys:
        d = data[fy]
        capex = abs(d.get("CAPEX.TOTAL", 0.0))
        rows.append({
            "fiscal_year": fy,
            "operating_cf_cr": round(d.get("CF.CFO", 0.0), 2),
            "investing_cf_cr": round(d.get("CF.CFI", 0.0), 2),
            "financing_cf_cr": round(d.get("CF.CFF", 0.0), 2),
            "free_cash_flow_cr": round(d.get("CF.CFO", 0.0) - capex, 2),
            "net_change_in_cash_cr": round(d.get("CF.NET_CHANGE_CCE", 0.0), 2) if "CF.NET_CHANGE_CCE" in d else None,
        })
    first, last = rows[0], rows[-1]
    tot_ocf = sum(r["operating_cf_cr"] for r in rows)
    tot_fcf = sum(r["free_cash_flow_cr"] for r in rows)
    hi = max(rows, key=lambda r: r["operating_cf_cr"])
    lo = min(rows, key=lambda r: r["operating_cf_cr"])
    n = len(rows)
    title = f"IOCL cash flow trend · {first['fiscal_year']}–{last['fiscal_year']} (₹ crore, standalone)"
    spoken = (
        f"Over the last {n} years, IOCL generated {fmt_inr_cr(tot_ocf)} of operating cash flow and {fmt_inr_cr(tot_fcf)} of free cash flow after capex. "
        f"Operating cash flow went from {fmt_inr_cr(first['operating_cf_cr'])} in {first['fiscal_year']} to {fmt_inr_cr(last['operating_cf_cr'])} in {last['fiscal_year']}, "
        f"peaking in {hi['fiscal_year']} and lowest in {lo['fiscal_year']} at {fmt_inr_cr(lo['operating_cf_cr'])}."
    )
    insights = [
        f"Cumulative {first['fiscal_year']}–{last['fiscal_year']}: OCF {fmt_inr_cr(tot_ocf)}, free cash flow {fmt_inr_cr(tot_fcf)}.",
        f"Highest OCF {hi['fiscal_year']} ({fmt_inr_cr(hi['operating_cf_cr'])}); lowest {lo['fiscal_year']} ({fmt_inr_cr(lo['operating_cf_cr'])}).",
        f"{last['fiscal_year']}: free cash flow {fmt_inr_cr(last['free_cash_flow_cr'])}; financing outflow {fmt_inr_cr(last['financing_cf_cr'])} (debt repayment, dividends, interest).",
    ]
    chart_rows = [{k: v for k, v in r.items() if k != "net_change_in_cash_cr"} for r in rows]
    return {
        "contract_version": 3,
        "turn_id": turn_id,
        "language": language,
        "persona": persona,
        "spoken_summary": spoken,
        "display_text": spoken,
        "visual": {
            "type": "chart",
            "mode": "replace",
            "title": title,
            "subtitle": "Operating, Investing, Financing cash flow and Free Cash Flow (OCF − Capex) · verified Annual Report SSOT",
            "chart": {
                "kind": "grouped_bar", "title": title, "data": chart_rows, "x": "fiscal_year", "y": "operating_cf_cr",
                "category": "fiscal_year", "value": "operating_cf_cr", "unit": "₹ Cr",
            },
            "table": {"columns": list(rows[0].keys()), "rows": rows, "total_rows": len(rows), "masking": {"level": "none"}},
            "kpis": [
                {"label": f"Total OCF ({first['fiscal_year']}–{last['fiscal_year']})", "value": round(tot_ocf, 2), "unit": "₹ crore"},
                {"label": f"Total free cash flow ({n} yrs)", "value": round(tot_fcf, 2), "unit": "₹ crore", "delta": "OCF less Capex"},
                {"label": f"OCF {last['fiscal_year']}", "value": last["operating_cf_cr"], "unit": "₹ crore"},
            ],
        },
        "insights": insights,
        "insights_v2": [{"kind": k, "text": t} for k, t in zip(["headline", "comparison", "note"], insights)],
        "context_chips": [
            {"label": persona, "kind": "role"},
            {"label": f"{first['fiscal_year']}–{last['fiscal_year']}", "kind": "period"},
            {"label": "Cash flow trend", "kind": "subject"},
        ],
        "sources": [{"kind": "data", "object": "fact_snapshot (Standalone Cash Flow, Ind AS 7)", "sql": "CF.CFO, CF.CFI, CF.CFF, CAPEX.TOTAL"}],
        "suggestions": [
            "Show the cash flow statement for FY26",
            "Can I see IOCL's stock price movement for the past 5 years?",
            "Run the DCF valuation model for IOCL",
        ],
        "access": {"status": "allowed"},
        "export_options": ["xlsx", "sheets", "pdf"],
        "status_events": [f"Loaded {n}-year verified cash flow series"],
        "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
    }
