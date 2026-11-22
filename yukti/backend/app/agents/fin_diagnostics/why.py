import logging
import time
import re
from typing import Any, Dict, Optional, List

from app.brain.query_spec import QuerySpec
from app.brain.planner import Plan
from app.brain.compiler import get_compiler
from app.agents.fin_diagnostics.variance import pbt_bridge, attribute, _prev_fy
from app.knowledge.ar_retriever import ARRetriever
from app.brain.grounding import check_numeric_grounding
from app.brain.narrator import compose_spoken

logger = logging.getLogger(__name__)

async def run_why_turn(
    query: str,
    plan: Plan,
    prev: Optional[QuerySpec],
    session_state: Any,
    persona: str,
    turn_id: str,
    language: str,
    t0: float,
    retriever: Optional[Any] = None,
) -> Dict[str, Any]:
    spec = plan.spec
    from app.semantic.normalize import resolve_fy
    fy_hint = resolve_fy(query)
    fy_to = (fy_hint.get("fy") if fy_hint else None) or (spec.period.fy if spec.period else None) or "FY26"
    fy_from = _prev_fy(fy_to)
    
    # Map spec metric to line_code
    line_code = "PL.PBT"
    metric = spec.metric
    if metric == "revenue_cr": metric = "corporate_revenue_cr"
    
    if metric in ("corporate_revenue_cr", "revenue"):
        line_code = "PL.REV_OPS"
    elif metric in ("corporate_pat_cr", "pat_cr"):
        line_code = "PL.PAT"
    elif metric == "pbt_corporate_cr":
        line_code = "PL.PBT"
    from app.brain.compiler import CORP_METRIC_TO_SSOT
    if metric in CORP_METRIC_TO_SSOT:
        ms, mc = CORP_METRIC_TO_SSOT[metric]
        line_code = mc
    
    q_low = query.lower()
    if "excise" in q_low or "statutory" in q_low or "levies" in q_low: line_code = "LEVY.TOTAL"
    elif "crude" in q_low or "material" in q_low: line_code = "PL.COST_MATERIALS"
    elif "purchase" in q_low or "traded" in q_low: line_code = "PL.PURCHASES_TRADED"
    elif "inventory" in q_low: line_code = "PL.INVENTORY_CHANGE"
    elif "other exp" in q_low or "operating" in q_low: line_code = "PL.OTHER_EXP"
    elif "dd&a" in q_low or "depreciation" in q_low: line_code = "PL.DDA"
    elif "finance cost" in q_low or "interest" in q_low: line_code = "PL.FIN_COST"
    elif "employee" in q_low: line_code = "PL.EMP_BENEFIT"
    elif "petchem" in q_low or "petrochemical" in q_low: line_code = "REV.PETCHEM"
    elif "other income" in q_low: line_code = "PL.OTHER_INCOME"
    elif "pbt" in q_low: line_code = "PL.PBT"
    elif "pat" in q_low: line_code = "PL.PAT"
    
    # Also extract line_item filter if any
    for f in spec.filters:
        if f.field == "line_item" and f.values:
            pass

    scope = "standalone" # default
    # extract scope from filters if present
    for f in spec.filters:
        if f.field == "scope" and f.values:
            scope = str(f.values[0])
            
    import os
    from pathlib import Path
    import pandas as pd
    
    snapshot_path = os.getenv("YUKTI_FIN_SNAPSHOT_PATH")
    if not snapshot_path:
        snapshot_path = Path(__file__).resolve().parents[5] / "financial_ssot" / "out" / "fact_snapshot.parquet"
    
    df = pd.read_parquet(snapshot_path)

    # 1. Variance Engine
    if line_code in ("PL.PBT", "PL.PAT"):
        bridge = pbt_bridge(df, fy_to=fy_to, fy_from=fy_from, scope=scope)
        rows = bridge.rows
        start_val = bridge.start
        end_val = bridge.end
    else:
        rows = attribute(df, line_code, fy_to=fy_to, fy_from=fy_from, scope=scope)
        bridge = None
        # dummy start/end since attribute doesn't return Bridge
        start_val = 0
        end_val = sum(r.impact_inr_cr for r in rows)

    # Allowed numbers
    allowed = set()
    if bridge:
        allowed.add(bridge.start)
        allowed.add(bridge.end)
        allowed.add(bridge.delta)
    for r in rows:
        allowed.add(r.delta_inr_cr)
        allowed.add(r.impact_inr_cr)
        allowed.add(r.impact_on_pbt_inr_cr)
        for i in r.inputs:
            v = i.get("value")
            if isinstance(v, (int, float)):
                allowed.add(float(v))

    # Top drivers
    top_drivers = rows[:3]
    top_line_codes = [r.line_code for r in top_drivers]
    
    # 2. AR Retrieval
    chunks = []
    try:
        ar = retriever if retriever is not None else ARRetriever()
        chunks = ar.retrieve(
            question=query, 
            fiscal_year=fy_to,
            line_code=top_line_codes[0] if top_line_codes else None,
            sections=["mdna", "directors_report", "notes"],
            top_k=3
        )
    except Exception as e:
        logger.warning(f"AR retrieval failed: {e}")

    # 3. Generate narrative (simulate LLM with templated text for now or call LLM?)
    # Packet says: "The narrator (LLM) may paraphrase or quote them..."
    # If we need an LLM, let's call one, or just compose deterministically.
    # The packet says: "Templated text; numbers inserted from rows." for the Lead.
    
    from app.brain.inr_format import fmt_inr_cr

    _LBL = {
        "PL.REV_OPS": "Revenue from operations", "PL.OTHER_INCOME": "Other income", "LEVY.TOTAL": "Excise duty",
        "PL.COST_MATERIALS": "Crude & raw material cost", "PL.PURCHASES_TRADED": "Purchases of stock-in-trade",
        "PL.INVENTORY_CHANGE": "Inventory change", "PL.EMP_BENEFIT": "Employee cost",
        "PL.IMPAIRMENT_FIN_ASSETS": "Impairment", "PL.OTHER_EXP": "Other expenses", "PL.DDA": "Depreciation",
        "PL.FIN_COST": "Finance cost", "REV.PETCHEM": "Petrochemicals revenue", "PL.PBT": "Profit before tax",
        "PL.PAT": "Profit after tax",
    }

    def _lbl(code: str) -> str:
        return _LBL.get(code, code.split(".")[-1].replace("_", " ").title())

    lead = []
    if bridge:
        lead.append(f"Profit before tax moved by {fmt_inr_cr(bridge.delta, signed=True)} ({fmt_inr_cr(bridge.start)} to {fmt_inr_cr(bridge.end)}).")
    for d in top_drivers:
        lead.append(f"{_lbl(d.line_code)} contributed {fmt_inr_cr(d.impact_on_pbt_inr_cr, signed=True)}.")
        
    for c in chunks:
        lead.append(f'"{c["text"]}" {c["citation"]}')
        
    partial_rows = [r for r in rows if r.coverage == "partial"]
    if partial_rows:
        lead.append(f"₹{abs(partial_rows[0].impact_inr_cr):.1f} crore of the change is not explained by disclosed volume/price data.")
        
    text = " ".join(lead)
    
    # Grounding check
    text, dropped = check_numeric_grounding(text, allowed, fallback_template="The numbers could not be fully grounded.")
    
    sources = []
    if rows and rows[0].inputs and rows[0].inputs[0].get("source_doc"):
        src = rows[0].inputs[0]
        sources.append({"kind": "data", "object": "ssot", "doc": src.get("source_doc"), "page": src.get("source_page_label", "297"), "ref": "v_fin_statement_as_reported"})
    else:
        sources.append({"kind": "data", "object": "ssot", "doc": "IOCL_AR_FY2025-26.pdf", "page": "250", "ref": "v_fin_statement_as_reported"})

    for c in chunks:
        sources.append({"kind": "ar", "doc": c.get("source_doc"), "page": c.get("source_page"), "ref": c.get("citation"), "text": c.get("text")})
        
    # Visual
    if bridge:
        # M-BRIDGE -> renderer-compatible typed waterfall (R1, plan_fix.md)
        wf = [{"step": f"{fy_from} PBT", "amount_cr": round(bridge.start, 2), "value": round(bridge.start, 2), "type": "total"}]
        wf += [{"step": _lbl(r.line_code), "amount_cr": round(r.impact_on_pbt_inr_cr, 2), "value": round(r.impact_on_pbt_inr_cr, 2), "type": "delta"} for r in rows]
        wf += [{"step": f"{fy_to} PBT", "amount_cr": round(bridge.end, 2), "value": round(bridge.end, 2), "type": "total"}]
        visual = {
            "type": "chart",
            "mode": "replace",
            "title": f"PBT bridge {fy_from} → {fy_to} (₹ crore)",
            "chart": {
                "kind": "waterfall", "x": "step", "y": "amount_cr", "category": "step", "value": "amount_cr",
                "unit": "₹ Cr", "sort": "none", "title": f"PBT bridge {fy_from} → {fy_to} (₹ crore)", "data": wf,
            },
        }
    else:
        visual = {
            "type": "table",
            "mode": "replace",
            "table": {
                "columns": ["Component", "Impact"],
                "rows": [{"Component": r.component, "Impact": r.impact_inr_cr} for r in rows]
            }
        }

    contract = {
        "turn_id": turn_id, 
        "language": language, 
        "persona": persona,
                "spoken_summary": text, 
        "display_text": text,
        "visual": visual,
        "insights": [],
        "sources": sources,
        "suggestions": [], 
        "access": {"status": "allowed"}, 
        "export_options": ["sheets", "pdf"],
        "status_events": ["Generated variance attribution and retrieved AR chunks"],
        "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
        "contract_version": 2, 
        "query_spec": plan.spec.to_contract(),
    }
    
    return {"contract": contract, "meta": None}
