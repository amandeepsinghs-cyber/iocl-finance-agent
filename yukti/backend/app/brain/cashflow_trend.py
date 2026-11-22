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
    mask = (df["scope"] == "standalone") & df["line_code"].isin(
        ["CF.CFO", "CF.CFI", "CF.CFF", "CF.NET_CHANGE_CCE", "CAPEX.TOTAL", "CF.WC_SUBTOTAL", "CF.TAX_PAID"]
    )
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


# ---------------------------------------------------------------------------------------------- V4: cash flow variance

_CF_WHY_RE = re.compile(r"\b(why|reasons?|explain|what\s+happened|what\s+caused|what\s+drove|how\s+come)\b", re.I)
_CF_SUBJ_RE = re.compile(r"\b(net\s+cash|cash[\s-]*flows?|operating\s+cash|ocf|cash\s+generat\w*)\b", re.I)
_CF_LOW_RE = re.compile(r"\b(reduc\w*|drop\w*|fell|fall\w*|declin\w*|decreas\w*|lower|less|low|down|weak\w*|shrank|shrink\w*)\b", re.I)
_CF_HIGH_RE = re.compile(r"\b(increas\w*|rose|rise|jump\w*|surg\w*|doubl\w*|improv\w*|higher|grew)\b", re.I)


def detect_cashflow_variance(query: str, session_state: Any = None) -> Optional[Dict[str, Any]]:
    """'Why did net cash / operating cash flow reduce in FY24-25?' → OCF bridge request."""
    q = (query or "").strip()
    if not q or not _CF_SUBJ_RE.search(q) or not (_CF_WHY_RE.search(q) or _CF_LOW_RE.search(q) and re.search(r"\b(fy|20\d\d|\d\d\s*[-–]\s*\d\d)", q, re.I)):
        return None
    if re.search(r"\b(dcf|fcff|forecast|2036|valuation|wacc|discounted)\b", q, re.I):
        return None
    from app.brain.profit_explainer import _years_in

    years = _years_in(q)
    # numbers matched to an operating cash flow value (e.g. "we have the cash flow to be 33,286")
    data = _cf_by_fy()
    for m in re.finditer(r"(?<![\w.])(\d{1,3}(?:,\d{2,3})+|\d{4,6})(?![\w])", q):
        n = float(m.group(1).replace(",", ""))
        for fy in _FYS:
            v = (data.get(fy) or {}).get("CF.CFO")
            if v and abs(n - v) / abs(v) <= 0.015 and fy not in years:
                years.append(fy)
    if not years and session_state is not None:
        years = _years_in(str(getattr(session_state, "last_user_query", "") or ""))
    return {"kind": "cashflow_variance", "years": years, "low": bool(_CF_LOW_RE.search(q)), "high": bool(_CF_HIGH_RE.search(q))}


def _resolve_cf_target(req: Dict[str, Any]) -> str:
    data = _cf_by_fy()
    years = [y for y in req.get("years") or [] if y in data and y != _FYS[0]]
    if years:
        if req.get("low") and not req.get("high"):
            return min(years, key=lambda fy: data[fy].get("CF.CFO", 0.0))
        return years[0]
    if req.get("low") and not req.get("high"):
        for fy in reversed(_FYS[1:]):
            cur, prv = data.get(fy, {}).get("CF.CFO"), data.get(f"FY{int(fy[2:]) - 1:02d}", {}).get("CF.CFO")
            if cur is not None and prv is not None and cur < prv:
                return fy
    return _FYS[-1]


def build_cashflow_variance_contract(req: Dict[str, Any], persona: str, turn_id: str, language: str, t0: float) -> Dict[str, Any]:
    from app.brain.profit_explainer import _ops_by_fy, _pnl_by_fy

    fy_to = _resolve_cf_target(req)
    fy_from = f"FY{int(fy_to[2:]) - 1:02d}"
    cf, pnl, ops = _cf_by_fy(), _pnl_by_fy(), _ops_by_fy()
    a, b = cf.get(fy_from) or {}, cf.get(fy_to) or {}
    pa, pb = pnl.get(fy_from) or {}, pnl.get(fy_to) or {}
    if "CF.CFO" not in a or "CF.CFO" not in b or "PL.PBT" not in pa or "PL.PBT" not in pb:
        raise RuntimeError("cash flow bridge inputs unavailable")

    def parts(c: Dict[str, float], p: Dict[str, float]) -> Dict[str, float]:
        wc, tax = c.get("CF.WC_SUBTOTAL", 0.0), c.get("CF.TAX_PAID", 0.0)
        return {"pbt": p["PL.PBT"], "wc": wc, "tax": tax, "noncash": c["CF.CFO"] - p["PL.PBT"] - wc - tax}

    pf, pt = parts(a, pa), parts(b, pb)
    d = {k: pt[k] - pf[k] for k in pf}
    ocf_a, ocf_b = a["CF.CFO"], b["CF.CFO"]
    chg = (ocf_b - ocf_a) / abs(ocf_a) * 100 if ocf_a else 0.0
    fell = ocf_b < ocf_a
    grm_a = (ops.get(fy_from) or {}).get("gross_refining_margin_usd_bbl")
    grm_b = (ops.get(fy_to) or {}).get("gross_refining_margin_usd_bbl")

    labels = {"pbt": "Profit before tax", "noncash": "Depreciation & other non-cash items", "wc": "Working capital", "tax": "Income tax paid"}
    rows: List[Dict[str, Any]] = [{"step": f"{fy_from} operating cash flow", "amount_cr": round(ocf_a, 2), "value": round(ocf_a, 2), "type": "total"}]
    for k in ("pbt", "noncash", "wc", "tax"):
        rows.append({"step": labels[k], "amount_cr": round(d[k], 2), "value": round(d[k], 2), "type": "delta"})
    rows.append({"step": f"{fy_to} operating cash flow", "amount_cr": round(ocf_b, 2), "value": round(ocf_b, 2), "type": "total"})

    main = max(("pbt", "wc", "tax", "noncash"), key=lambda k: abs(d[k]) if d[k] * (ocf_b - ocf_a) > 0 else -1)
    reason = {
        "pbt": f"profit before tax {'dropped' if d['pbt'] < 0 else 'rose'} by {fmt_inr_cr(abs(d['pbt']))}"
        + (f" as the refining margin went from ${grm_a:.2f} to ${grm_b:.2f} a barrel" if grm_a is not None and grm_b is not None else ""),
        "wc": f"working capital {'released' if d['wc'] > 0 else 'absorbed'} {fmt_inr_cr(abs(d['wc']))} {'more' if d['wc'] > 0 else 'less'} cash than the year before",
        "tax": f"tax paid {'fell' if d['tax'] > 0 else 'rose'} by {fmt_inr_cr(abs(d['tax']))}",
        "noncash": f"non-cash items moved by {fmt_inr_cr(d['noncash'], signed=True)}",
    }
    s1 = (
        f"IOCL's operating cash flow {'fell' if fell else 'rose'} from {fmt_inr_cr(ocf_a)} in {fy_from} to {fmt_inr_cr(ocf_b)} in {fy_to} "
        f"({f'{chg:+.0f}'.replace('-', '−')}%), mainly because {reason[main]}."
    )
    others = [k for k in ("pbt", "wc", "tax") if k != main and abs(d[k]) > 500]
    s2 = ""
    if others:
        bits = []
        for k in others:
            same_dir = d[k] * (ocf_b - ocf_a) > 0
            bits.append(("" if same_dir else "partly offset by ") + reason[k])
        s2 = "; ".join(bits)
        s2 = s2[0].upper() + s2[1:] + "."
    spoken = f"{s1} {s2}".strip()
    display = spoken if len(spoken) <= 590 else s1
    title = f"Why {fy_to} operating cash flow {'fell' if fell else 'rose'}: bridge {fy_from} → {fy_to} (₹ crore)"
    insights = [
        f"Operating cash flow {fy_from} {fmt_inr_cr(ocf_a)} → {fy_to} {fmt_inr_cr(ocf_b)} ({chg:+.1f}%).",
        f"Profit before tax {fmt_inr_cr(d['pbt'], signed=True)}; working capital {fmt_inr_cr(d['wc'], signed=True)}; tax paid {fmt_inr_cr(d['tax'], signed=True)}; non-cash & other {fmt_inr_cr(d['noncash'], signed=True)}.",
    ]
    return {
        "contract_version": 3,
        "turn_id": turn_id,
        "language": language,
        "persona": persona,
        "spoken_summary": spoken,
        "display_text": display,
        "visual": {
            "type": "chart",
            "mode": "replace",
            "title": title,
            "subtitle": "Standalone · Ind AS 7 operating cash flow bridge · verified Annual Report SSOT",
            "chart": {"kind": "waterfall", "title": title, "x": "step", "y": "amount_cr", "category": "step", "value": "amount_cr",
                      "unit": "₹ Cr", "sort": "none", "data": rows},
            "table": {"columns": ["step", "amount_cr", "type"], "rows": [{k: r[k] for k in ("step", "amount_cr", "type")} for r in rows],
                      "total_rows": len(rows), "masking": {"level": "none"}},
            "kpis": [
                {"label": f"Operating cash flow {fy_from}", "value": round(ocf_a, 2), "unit": "₹ crore"},
                {"label": f"Operating cash flow {fy_to}", "value": round(ocf_b, 2), "unit": "₹ crore", "delta": f"{chg:+.1f}% YoY"},
                {"label": f"Profit before tax {fy_to}", "value": round(pb["PL.PBT"], 2), "unit": "₹ crore"},
            ],
        },
        "insights": insights,
        "insights_v2": [{"kind": k, "text": t} for k, t in zip(["headline", "comparison"], insights)],
        "context_chips": [
            {"label": persona, "kind": "role"},
            {"label": f"{fy_from} → {fy_to}", "kind": "period"},
            {"label": "Cash flow variance bridge", "kind": "subject"},
        ],
        "sources": [{"kind": "data", "object": "fact_snapshot (Standalone Cash Flow, Ind AS 7)", "sql": f"CF.CFO, CF.WC_SUBTOTAL, CF.TAX_PAID, PL.PBT {fy_from}→{fy_to}"}],
        "suggestions": [f"Why did profit fall in {fy_to}?", "Show the cash flow trend for the past 10 years", "Run the DCF valuation model for IOCL"],
        "access": {"status": "allowed"},
        "export_options": ["xlsx", "sheets", "pdf"],
        "status_events": [f"Computed verified operating cash flow bridge {fy_from}→{fy_to}"],
        "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
    }
