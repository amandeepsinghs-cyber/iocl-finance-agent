from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# SPEC-03 §6.2 Voice and text confirmation (deterministic, no LLM)
CONFIRM_RE = re.compile(
    r"^\s*(?:(?:please|kindly|yes,?\s*please|ok(?:ay)?,?\s*please|sure,?\s*please)\s+)?"
    r"(yes|yeah|yep|sure|ok(ay)?|go\s+ahead|do\s+it|run(\s+(?:it|the\s+dcf|the\s+model))?|start(\s+it)?|please\s+run|haan\s+ji|haan|ha|chalao|kar\s+do|chala\s+do|हाँ|चलाओ|proceed|confirm)"
    r"(?=$|[\s,.!?;:])",
    re.IGNORECASE,
)

CANCEL_RE = re.compile(
    r"(?:^\s*|\b)(no|nope|cancel|stop|don'?t|mat karo|nahi|रद्द|नहीं)(?=$|[\s,.!?;:])",
    re.IGNORECASE,
)

_EDIT_LINK = r"(?:\s+(?:is|be|was|should\s+be|to\s+be|set|changed|change|equal|equals|at|as|of|to|=|from\s+\d+(?:\.\d+)?\s*%?\s+to)){0,3}\s*"

WACC_EDIT_RE = re.compile(
    r"\b(?:wacc|discount rate|cost of capital)" + _EDIT_LINK + r"(\d+(?:\.\d+)?)\s*(?:%|percent|pct)?(?!\s*(?:years?|crore|cr|bbl))",
    re.IGNORECASE,
)

GROWTH_EDIT_RE = re.compile(
    r"\b(?:terminal growth|terminal g|perpetual growth|long[- ]term growth)" + _EDIT_LINK + r"(-?\d+(?:\.\d+)?)\s*(?:%|percent|pct)?",
    re.IGNORECASE,
)

BRENT_EDIT_RE = re.compile(
    r"\bbrent\s*(?:at|=|to|of|is)?\s*\$?\s*(\d+(?:\.\d+)?)\b",
    re.IGNORECASE,
)

SHARE_PRICE_EDIT_RE = re.compile(
    r"\b(?:market|share|stock)\s+price\s*(?:of|=|to|is|at)?\s*(?:₹|rs\.?|inr)?\s*(\d+(?:\.\d+)?)\b",
    re.IGNORECASE,
)

GENERIC_EDIT_RE = re.compile(
    r"\b(edit|change|modify|update)\b",
    re.IGNORECASE,
)

QUESTION_LEAD_RE = re.compile(
    r"^\s*(what|why|how|which|who|when|where|show|tell)\b",
    re.IGNORECASE,
)


def extract_voice_edits(text: str) -> Dict[str, float]:
    """Extract parameter overrides spoken or typed by the user per SPEC-03 §6.2."""
    if not text:
        return {}
    edits: Dict[str, float] = {}
    m_wacc = WACC_EDIT_RE.search(text)
    if m_wacc:
        edits["wacc_pct"] = float(m_wacc.group(1))
    m_g = GROWTH_EDIT_RE.search(text)
    if m_g:
        edits["terminal_g_pct"] = float(m_g.group(1))
    m_brent = BRENT_EDIT_RE.search(text)
    if m_brent:
        edits["brent_usd"] = float(m_brent.group(1))
    m_px = SHARE_PRICE_EDIT_RE.search(text)
    if m_px:
        val_px = float(m_px.group(1))
        if 20.0 <= val_px <= 1000.0:
            edits["market_price_inr"] = val_px
    return edits


DCF_SELECT_RE = re.compile(
    r"\b(dcf|discounted\s+cash\s*flow|valuation(?:\s+model)?|intrinsic\s+value)\b",
    re.IGNORECASE,
)

EMAIL_SELECT_RE = re.compile(
    r"\b(email|e-mail|mail|send\s+(?:the\s+)?email|transfer)\b",
    re.IGNORECASE,
)


def _match_explicit_agent(text: str, active: Dict[str, Dict[str, Any]]) -> Optional[str]:
    """Return the action_id explicitly named by the user when disambiguating multiple pending proposals."""
    want_dcf = bool(DCF_SELECT_RE.search(text or ""))
    want_email = bool(EMAIL_SELECT_RE.search(text or ""))
    if want_dcf and not want_email:
        for aid, pa in reversed(list(active.items())):
            if str(pa.get("agent") or "").lower() == "dcf_agent":
                return aid
    if want_email and not want_dcf:
        for aid, pa in reversed(list(active.items())):
            if str(pa.get("agent") or "").lower() != "dcf_agent":
                return aid
    return None


def detect_confirm_intent(text: str) -> Optional[str]:
    """Classify an utterance against SPEC-03 §6.2 into 'confirm', 'cancel', 'edit', or None."""
    cleaned = (text or "").strip()
    if not cleaned:
        return None

    # Disambiguation replies like "No, just show the DCF first." select DCF rather than cancelling
    # (V2: only as a short reply — a long "Run the 10-year DCF valuation agent against …" proposal echo is not consent)
    _n_words = len(re.findall(r"[\w'’]+", cleaned))
    _proposal_echo = bool(re.search(r"\b(agent|against|10[\s-]*year|share\s+price|live\s+nse|it\s+takes|seconds?)\b", cleaned, re.I))
    if (
        DCF_SELECT_RE.search(cleaned)
        and re.search(r"\b(just|show|run|first|only|instead)\b", cleaned, re.IGNORECASE)
        and _n_words <= 9
        and not _proposal_echo
    ):
        return "confirm"

    if CANCEL_RE.search(cleaned):
        return "cancel"

    edits = extract_voice_edits(cleaned)
    if edits:
        return "edit"

    if not QUESTION_LEAD_RE.search(cleaned) and GENERIC_EDIT_RE.search(cleaned):
        return "edit"

    if CONFIRM_RE.search(cleaned):
        # V2 (plan_fix.md v12): a long "Run the 10-year DCF valuation agent against …" sentence (e.g. the voice model
        # echoing the proposal) is a NEW request, not the user's consent. Affirmative openers always confirm;
        # imperative "run/start/do it" confirms only as a short reply.
        words = re.findall(r"[\w'’]+", cleaned)
        affirmative_start = re.match(
            r"^\s*(?:(?:please|kindly)\s+)?(?:yes|yeah|yep|sure|ok(?:ay)?|go\s+ahead|proceed|confirm|haan|ha|हाँ|हां)\b", cleaned, re.I
        )
        if not affirmative_start and len(words) > 5:
            return None
        return "confirm"

    return None


def _is_expired(expires_at: Optional[str]) -> bool:
    if not expires_at:
        return False
    try:
        dt = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt <= datetime.now(timezone.utc)
    except ValueError:
        return False


def get_active_pending_actions(session_state: Any) -> Dict[str, Dict[str, Any]]:
    raw = getattr(session_state, "pending_actions", None) or {}
    active: Dict[str, Dict[str, Any]] = {}
    expired_ids = []
    for aid, pa in list(raw.items()):
        if isinstance(pa, dict) and _is_expired(pa.get("expires_at")):
            expired_ids.append(aid)
        elif isinstance(pa, dict) and not pa.get("disabled"):
            active[aid] = pa
    for aid in expired_ids:
        raw.pop(aid, None)
    return active


async def resolve_pending_proposal_async(
    text: str,
    session_state: Any,
) -> Optional[Dict[str, Any]]:
    """Deterministically resolve voice/text confirmation, cancellation, or edit against session_state.pending_actions."""
    if session_state is None:
        return None
    active = get_active_pending_actions(session_state)
    if not active:
        return None

    intent = detect_confirm_intent(text)
    edits = extract_voice_edits(text)
    if intent is None and not edits:
        return None

    utterance_clean = (text or "").strip()
    echo_text = f"You said: {utterance_clean}"
    lang = getattr(session_state, "language", "en") or "en"
    persona = getattr(session_state, "persona", "CMD") or "CMD"

    # Deduplicate stale proposals belonging to the same agent (keep newest per agent)
    latest_by_agent: Dict[str, str] = {}
    for aid, pa_item in list(active.items()):
        ag = str(pa_item.get("agent") or aid)
        if ag in latest_by_agent:
            old_id = latest_by_agent[ag]
            active.pop(old_id, None)
            session_state.pending_actions.pop(old_id, None)
        latest_by_agent[ag] = aid

    # SPEC-03 §6.2: if two distinct non-expired proposals exist, check if user disambiguated first
    selected_id: Optional[str] = None
    if len(active) >= 2:
        selected_id = _match_explicit_agent(text, active)
        if selected_id is None:
            msg = "Run the DCF or the email send?"
            return {
                "action": "clarify_multiple",
                "echo": echo_text,
                "contract": {
                    "contract_version": 3,
                    "turn_id": f"turn-clarify-pa-{int(datetime.now(timezone.utc).timestamp() * 1000)}",
                    "language": lang,
                    "persona": persona,
                    "spoken_summary": msg,
                    "display_text": msg,
                    "visual": {"type": "none", "mode": "replace"},
                    "access": {"status": "allowed"},
                },
            }

    if selected_id is not None:
        action_id, pa = selected_id, active[selected_id]
    else:
        action_id, pa = next(iter(active.items()))

    if intent == "cancel":
        session_state.pending_actions.pop(action_id, None)
        msg = "Cancelled. No agent was run."
        return {
            "action": "cancel",
            "action_id": action_id,
            "echo": echo_text,
            "contract": {
                "contract_version": 3,
                "turn_id": f"turn-cancel-{action_id}",
                "language": lang,
                "persona": persona,
                "spoken_summary": msg,
                "display_text": msg,
                "visual": {"type": "none", "mode": "replace"},
                "access": {"status": "allowed"},
            },
        }

    if intent == "edit":
        updated_pa = dict(pa)
        inputs = dict(updated_pa.get("inputs") or {})
        editable = [dict(item) for item in (updated_pa.get("editable_inputs") or [])]
        changed_parts = []
        for k, v in edits.items():
            inputs[k] = v
            for item in editable:
                if item.get("key") == k:
                    item["value"] = v
                    item["edited_by_user"] = True
            if k == "wacc_pct":
                label, unit = "WACC", "%"
            elif k == "terminal_g_pct":
                label, unit = "terminal g", "%"
            elif k == "market_price_inr":
                label, unit = "NSE:IOC share price", " ₹/sh"
            else:
                label, unit = "Brent", " USD/bbl"
            changed_parts.append(f"{label} = {v}{unit}")
        updated_pa["inputs"] = inputs
        updated_pa["editable_inputs"] = editable
        change_str = ", ".join(changed_parts) if changed_parts else "updated assumptions"
        summary = f"Updated assumptions ({change_str}). Shall I run the {updated_pa.get('agent', 'agent')} with these values?"
        updated_pa["summary"] = summary
        session_state.pending_actions[action_id] = updated_pa
        return {
            "action": "edit",
            "action_id": action_id,
            "overrides": edits,
            "echo": echo_text,
            "contract": {
                "contract_version": 3,
                "turn_id": f"turn-edit-{action_id}",
                "language": lang,
                "persona": persona,
                "spoken_summary": summary,
                "display_text": summary,
                "visual": {"type": "none", "mode": "replace"},
                "proposed_action": updated_pa,
                "access": {"status": "allowed"},
            },
        }

    # intent == "confirm"
    from app.jobs.executor import get_executor

    executor = get_executor()
    session_state.pending_actions.pop(action_id, None)
    # Z1: stamp the confirming principal so the job result (and its Excel export) belongs to them
    pa = dict(pa)
    pa.setdefault("owner_persona", str(getattr(session_state, "persona", "") or "CMD").upper())
    if getattr(session_state, "principal_emp_id", None):
        pa.setdefault("owner_emp_id", str(session_state.principal_emp_id))
    job = await executor.submit_job(pa, session_state.session_id)
    started_msg = f"Starting {pa.get('agent', 'dcf_agent')}. I will announce the result as soon as it finishes."
    return {
        "action": "confirm",
        "action_id": action_id,
        "job": job,
        "echo": echo_text,
        "contract": {
            "contract_version": 3,
            "turn_id": f"turn-job-start-{job['id']}",
            "language": lang,
            "persona": persona,
            "spoken_summary": started_msg,
            "display_text": started_msg,
            "visual": {"type": "none", "mode": "replace"},
            "job": job,
            "access": {"status": "allowed"},
        },
    }
