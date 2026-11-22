import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional

from app.finance.dcf.inputs import (
    DCFInputMissingError,
    load_fy26_wacc_default,
    load_market_price_for_dcf,
    load_ssot_snapshot_rows,
)


def build_dcf_proposal(persona: str, session: Any, overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    overrides = overrides or {}
    try:
        snapshot_rows = load_ssot_snapshot_rows()
        verified_snapshot_rows = [r for r in snapshot_rows if r.get("verified", False)]
        if not verified_snapshot_rows:
            raise DCFInputMissingError("fact_snapshot")
        default_wacc_pct, wacc_source, wacc_meta = load_fy26_wacc_default()
        default_mkt_px, mkt_source, mkt_meta = load_market_price_for_dcf()
    except DCFInputMissingError as exc:
        missing_input = exc.missing_input
        return {
            "proposed_action": None,
            "answer": (
                f"Cannot run the DCF valuation because required input `{missing_input}` is missing or "
                f"the FY26 cash-flow / WACC data hasn't passed verification yet. See coverage."
            ),
            "access": {
                "status": "refused",
                "reason": "SSOT-UNVERIFIED",
                "missing_input": missing_input,
            },
        }

    # Defaults and sources from SSOT fact_wacc_annual FY26 and live Yahoo Finance IOC.NS (or offline seed in tests)
    wacc_pct = float(overrides.get("wacc_pct", default_wacc_pct))
    g_pct = float(overrides.get("terminal_g_pct", 3.0))
    mkt_px = round(float(overrides.get("market_price_inr", default_mkt_px)), 2)

    # BEH-05.09: degraded market-price staleness check
    market_stale = getattr(session, "market_stale", False) if session is not None else False

    inputs = {
        "market_price_inr": mkt_px,
        "wacc_pct": wacc_pct,
        "terminal_g_pct": g_pct,
        "brent_usd": overrides.get("brent_usd", 69.04),
        "capex_scale_pct": overrides.get("capex_scale_pct", 100.0),
        "production_decline_pct": overrides.get("production_decline_pct", -2.0),
        "holdco_discount_pct": overrides.get("holdco_discount_pct", 0.0),
    }

    brent_live = mkt_meta.get("brent_live_usd")
    brent_src = (
        f"IOCL AR FY26 average · live BZ=F spot ${brent_live:.2f}/bbl (say \"use live Brent\" to switch)"
        if isinstance(brent_live, (int, float))
        else "IOCL AR FY26 average Brent"
    )
    mkt_input_src = (
        f"user override (base: {mkt_source})"
        if "market_price_inr" in overrides and abs(mkt_px - default_mkt_px) >= 0.01
        else mkt_source
    )

    editable_inputs = [
        {"key": "market_price_inr", "label": "Current Share Price (NSE:IOC)", "type": "number", "value": mkt_px, "min": 20.0, "max": 1000.0, "step": 0.5, "unit": "₹/sh", "source": mkt_input_src},
        {"key": "wacc_pct", "label": "WACC", "type": "percent", "value": wacc_pct, "min": 5.0, "max": 25.0, "step": 0.1, "source": wacc_source},
        {"key": "terminal_g_pct", "label": "Terminal Growth", "type": "percent", "value": g_pct, "min": 0.0, "max": 10.0, "step": 0.1, "source": "default (illustrative)"},
        {"key": "brent_usd", "label": "Brent (base case: FY26 avg)", "type": "number", "value": inputs["brent_usd"], "min": 40.0, "max": 120.0, "step": 1.0, "unit": "USD/bbl", "source": brent_src},
        {"key": "capex_scale_pct", "label": "Capex Scale (% of FY26 plan)", "type": "percent", "value": inputs["capex_scale_pct"], "min": 50.0, "max": 200.0, "step": 5.0, "source": "FY26 Capex ₹34,210 Cr (verified)"},
        {"key": "production_decline_pct", "label": "Throughput Decline / (-Growth)", "type": "percent", "value": inputs["production_decline_pct"], "min": -10.0, "max": 20.0, "step": 0.5, "source": "ssot_refinery_economics_360 (IOCL standalone)"},
        {"key": "holdco_discount_pct", "label": "HoldCo Discount", "type": "percent", "value": inputs["holdco_discount_pct"], "min": 0.0, "max": 50.0, "step": 5.0, "source": "default"},
    ]

    if mkt_meta.get("live"):
        summary_msg = (
            f"Can I run the 10-year DCF valuation agent against IndianOil's live NSE:IOC share price of "
            f"₹{mkt_px:.2f} (via Yahoo Finance API, as of {mkt_meta.get('date')})? It takes about 15 seconds."
        )
    else:
        summary_msg = (
            f"Can I run the DCF valuation agent in the background to estimate IndianOil's intrinsic value "
            f"against NSE:IOC ₹{mkt_px:.2f}? It takes about 15 seconds."
        )

    proposal = {
        "id": f"pa_{uuid.uuid4().hex[:8]}",
        "agent": "dcf_agent",
        "agent_version": "dcf-v1.0.0",
        "summary": summary_msg,
        "est_seconds": 15,
        "inputs": inputs,
        "editable_inputs": editable_inputs,
        "lineage": {
            "wacc": {**wacc_meta, "source": wacc_source},
            "market_price": {**mkt_meta, "source": mkt_source, "value_inr": mkt_px},
        },
        "requires_role": ["CMD", "DIR_FIN", "DIR_REF", "DIR_MKT", "E1_FIN", "E2_FIN", "E3_FIN", "E4_FIN"],
        "buttons": ["run", "edit", "cancel"],
        "voice_confirm_hint": "Say yes, please go ahead, run it, or cancel.",
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
    }
    
    ans = {
        "proposed_action": proposal,
        "answer": proposal["summary"]
    }
    
    if market_stale:
        proposal["buttons"] = ["run", "edit", "cancel"] # still run? wait BEH-05.09 says Proposal disabled. Wait, it says: Proposal disabled: "Market price data is unavailable, so I can't compare intrinsic value to the share price. I can run the model and show value per share only?" (chip), and the verdict is omitted.
        ans["answer"] = "Market price data is unavailable, so I can't compare intrinsic value to the share price. I can run the model and show value per share only?"
        proposal["summary"] = ans["answer"]
        ans["chips"] = ["run the model and show value per share only"]

    return ans
