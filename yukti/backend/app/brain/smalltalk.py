"""Small talk and capability answers for turns the data planner does not handle (26-Oct).

Greetings ("Hi Yukti, how are you?"), "What can you do?", and other non-data turns used to fall through to the retired
legacy agent and show the generic error E-PLN-1234. This module answers them with one plain Gemini call: no tools, no
data access, English/Hindi/Hinglish only, and never any figures (so it cannot invent numbers). If the model is slow or
unavailable, a deterministic reply is used instead.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any, Dict, List, Optional

from google import genai
from google.genai import types

from app.config import DEFAULT_TEXT_MODEL, GCP_PROJECT, VERTEX_TEXT_LOCATION

logger = logging.getLogger("yukti.brain.smalltalk")

_HR_STARTERS = [
    "How many executives have been posted in Delhi for 5 years or more?",
    "Show headcount by discipline",
    "What is the transfer policy for station tenure?",
]
_FIN_STARTERS = [
    "Show IOCL's P&L statement for FY26",
    "Rank all IOCL refineries by GRM and EBITDA in FY26",
    "How is IOCL tracking against its FY26 MoU targets?",
]
_CMD_STARTERS = [
    "Show IOCL's Schedule III Profit and Loss statement for FY26",
    "Rank all IOCL refineries by GRM ($/bbl) and EBITDA in FY26",
    "How is IOCL tracking against its MoPNG/DPE Maharatna MoU targets?",
]


def starters_for(persona: str) -> List[str]:
    p = (persona or "").upper()
    if p == "CMD":
        return list(_CMD_STARTERS)
    return list(_FIN_STARTERS)


def _scope_for(persona: str) -> str:
    p = (persona or "").upper()
    if p == "CMD":
        return "Corporate Finance & Downstream Operations across IOCL (Schedule III P&L, Balance Sheet, Cash Flow, Refinery GRM, Pipelines, Marketing, MoU targets, NSE:IOC DCF, and DoA/Hedging policies)"
    return "IOCL Finance & Downstream Operations (Schedule III P&L, Balance Sheet, Cash Flow, Refinery GRM, Pipelines, Marketing, WACC, MoU targets, and Finance/DoA policies)"


_SYSTEM = """You are Yukti, the voice-first Finance & Downstream Intelligence agent for Indian Oil Corporation Limited (IOCL).
Reply to the user's message in 1-3 short, warm, professional sentences (Indian boardroom register).
Rules:
- Reply in the language named below ("Reply language"). Never any other language.
- Never state numbers, figures, names of employees, or facts about IOCL data. You have no data in this reply.
- For greetings: greet back briefly and offer help.
- For brief acknowledgments or conversational fillers (e.g. "all right, I'll do one now", "okay, got it", "sounds good"): acknowledge warmly in one short sentence and invite the next question.
- For "what can you do" / help: say in one or two sentences what you can help with, using the scope given.
- If the message is a data or policy question you could not answer, say you couldn't fetch that just now and ask the
  user to rephrase it more specifically (e.g. with a year, location or metric). Do not guess an answer.
- If the message looks cut off or incomplete (e.g. "Can you tell"), ask the user to finish the question.
- If the message is unclear or seems to be noise, ask the user to repeat.
Return plain text only."""

_CONCEPT_SYSTEM = """You are Yukti, the executive Finance & Downstream Intelligence assistant for Indian Oil Corporation Limited (IOCL).
The user is asking a conceptual, definitional, or terminology question about corporate finance, accounting (Ind AS / Companies Act Schedule III), or Oil & Gas downstream economics.
Rules:
- Answer directly and accurately in 2-4 crisp, boardroom-register sentences.
- Lead with the direct answer (e.g. "Yes, they refer to the same financial statement...").
- Explain the Indian regulatory / IOCL context cleanly where helpful (e.g. Companies Act 2013 Schedule III / Ind AS vs. IFRS / US GAAP terminology, GRM, WACC, EBITDA vs. EBIT).
- Do NOT invent or quote specific IOCL rupee figures, percentages, or FY results (no database query was run for this conceptual explanation).
- Reply in the language named below ("Reply language"). Plain text only, complete sentences."""

_CONCEPT_LEAD_RE = re.compile(
    r"(?:"
    r"\b(?:what(?:'s|\s+is|\s+are)\s+the\s+difference\s+(?:between|in))\b|"
    r"\b(?:difference\s+(?:between|in)\s+[a-z0-9&\s/-]{2,60})\b|"
    r"\b(?:are\s+.{2,50}\s+(?:the\s+)?same(?:\s+thing)?)\b|"
    r"\b(?:is\s+.{2,50}\s+(?:the\s+)?same\s+(?:as|thing))\b|"
    r"\b(?:or\s+(?:are\s+they|they\s+are)\s+(?:the\s+)?same(?:\s+thing)?)\b|"
    r"^\s*(?:what\s+(?:does|is|are)\s+(?:a\s+|an\s+|the\s+)?(?:p&l|profit\s+and\s+loss|income\s+statement|balance\s+sheet|cash\s+flow\s+statement|ebitda|ebit|pbidt|pat|pbt|grm|gross\s+refining\s+margin|wacc|dcf|fcff|fcf|capex|opex|schedule\s+(?:iii|3)|ind\s*as\s*\d+|standalone|consolidated|working\s+capital|crack\s+spread|excise\s+duty)\b)|"
    r"^\s*(?:define|explain)\s+(?:the\s+difference|what\s+is|what\s+are|p&l|income\s+statement|balance\s+sheet|ebitda|ebit|grm|wacc|dcf|fcff|schedule\s+(?:iii|3)|standalone\s+vs\s+consolidated)\b|"
    r"\b(?:where\s+is\s+(?:the\s+)?(?:free\s+cash\s+flow|fcf|capex|operating\s+cash\s+flow|debt|borrowings)\s+in\s+(?:this|the\s+p&l|the\s+income\s+statement))\b|"
    r"\b(?:cannot\s+see\s+(?:the\s+)?(?:free\s+cash\s+flow|fcf|capex)\b)|"
    r"^\s*how\s+(?:is|do\s+you\s+calculate)\s+(?:grm|wacc|ebitda|fcff|roce|roe|eps|net\s+revenue)\s+(?:calculated|computed|defined)\b"
    r")",
    re.I,
)

_DATA_REQUEST_GUARD_RE = re.compile(
    r"\b(?:fy\s?\d{2}|201\d|202\d|203\d|last\s+\d+\s+years?|past\s+\d+\s+years?|plot|chart|graph|table|rank|run\s+(?:the\s+)?dcf|show\s+(?:me\s+)?(?:iocl|indianoil|the)\s+(?:fy|schedule|p&l|balance|cash|diesel|petrol|refiner))\b",
    re.I,
)


def detect_conceptual_finance_question(query: str) -> bool:
    """True when the user asks a pure conceptual/terminology finance question rather than requesting IOCL data."""
    q = (query or "").strip()
    if not q or _DATA_REQUEST_GUARD_RE.search(q):
        return False
    return bool(_CONCEPT_LEAD_RE.search(q))


def _conceptual_fallback(query: str) -> str:
    q = (query or "").lower()
    if ("p&l" in q or "profit and loss" in q or "profit & loss" in q) and ("income statement" in q or "income stateemnt" in q):
        return (
            "Yes — they refer to the same financial statement. Under India's Companies Act (Schedule III, Ind AS), "
            "IndianOil reports it as the Statement of Profit and Loss (P&L), whereas IFRS and US GAAP usage commonly "
            "calls it the Income Statement; both summarize revenue, expenses, tax, and net profit over a reporting period."
        )
    if "ebitda" in q and "ebit" in q:
        return (
            "EBITDA measures operating earnings before interest, taxes, depreciation, and amortisation (operating cash profitability), "
            "whereas EBIT deducts depreciation and amortisation to show accounting operating profit."
        )
    if "standalone" in q and "consolidated" in q:
        return (
            "Standalone financials reflect Indian Oil Corporation Limited as a single legal entity, whereas Consolidated financials "
            "combine IOCL with its subsidiaries (such as CPCL and Lanka IOC) and its share of joint ventures and associates."
        )
    return (
        "That is a standard corporate finance term under Ind AS and Schedule III reporting. "
        "If you would like to see the corresponding IndianOil figures for a specific fiscal year, just ask and I will pull them from our verified statements."
    )


async def conceptual_finance_reply(query: str, language: str) -> str:
    reply_lang = {"hi": "Hindi (Devanagari)", "hi-en": "Hinglish (Roman script)"}.get(language, "Indian English")
    prompt = f"{_CONCEPT_SYSTEM}\n\nReply language: {reply_lang}.\nUser question: {query}"
    try:
        cfg = types.GenerateContentConfig(
            temperature=0.2,
            max_output_tokens=280,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        )
        resp = await asyncio.wait_for(
            _get_client().aio.models.generate_content(model=DEFAULT_TEXT_MODEL, contents=prompt, config=cfg),
            timeout=8,
        )
        text = (resp.text or "").strip()
        if text and not re.search(r"₹\s*\d|\b\d[\d,]*\s*(?:crore|cr|mmt|mmtpa)\b", text, re.I):
            return text
    except Exception as e:
        logger.warning(f"conceptual_finance: model call failed ({type(e).__name__}); using deterministic explanation")
    return _conceptual_fallback(query)


async def build_conceptual_finance_contract(
    query: str, persona: str, turn_id: str, language: str, t0: float
) -> Dict[str, Any]:
    text = await conceptual_finance_reply(query, language)
    return {
        "turn_id": turn_id,
        "language": language,
        "persona": persona,
        "spoken_summary": text,
        "display_text": text,
        "visual": {"type": "none", "mode": "replace"},
        "insights": [],
        "sources": [],
        "suggestions": starters_for(persona),
        "access": {"status": "allowed"},
        "export_options": [],
        "status_events": ["Answered conceptual finance question"],
        "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
    }

_client: Optional[genai.Client] = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(vertexai=True, project=GCP_PROJECT, location=VERTEX_TEXT_LOCATION)
    return _client


_DIGITS = re.compile(r"\d")


def _fallback_text(query: str, persona: str, language: str) -> str:
    q = (query or "").lower()
    if language == "hi":
        if re.search(r"(kya kar|madad|help)", q):
            return f"Main {_scope_for(persona)} se jude sawalon mein aapki madad kar sakti hoon. Aap neeche diye sawal se shuru kar sakte hain."
        return "Namaste! Main Yukti hoon. Bataiye, main aapki kya madad kar sakti hoon?"
    if re.search(r"(what can you do|help|capabilit|what do you do)", q):
        return f"I can answer questions on {_scope_for(persona)}, show the right table or chart, and draft notes. Try one of the questions below."
    if re.search(r"\b(hi|hello|hey|namaste|good (morning|afternoon|evening)|how are you)\b", q):
        return "Hello! I'm doing well, thank you. How can I help you today?"
    return "Sorry, I couldn't work that out. Could you rephrase it with a little more detail, such as a year, location or metric?"


async def smalltalk_reply(query: str, persona: str, language: str) -> str:
    reply_lang = {"hi": "Hindi (Devanagari)", "hi-en": "Hinglish (Roman script)"}.get(language, "Indian English")
    prompt = (
        f"{_SYSTEM}\n\nUser role: {persona}. You can help with: {_scope_for(persona)}.\n"
        f"Reply language: {reply_lang}.\nUser message: {query}"
    )
    try:
        cfg = types.GenerateContentConfig(
            temperature=0.3,
            max_output_tokens=160,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        )
        resp = await asyncio.wait_for(
            _get_client().aio.models.generate_content(model=DEFAULT_TEXT_MODEL, contents=prompt, config=cfg),
            timeout=6,
        )
        text = (resp.text or "").strip()
        # guard: this reply has no data, so it must not carry figures
        if text and not _DIGITS.search(text):
            return text
        logger.info("smalltalk: model reply rejected (empty or contained digits); using fallback")
    except Exception as e:  # noqa: BLE001 - any failure falls back to a deterministic reply
        logger.warning(f"smalltalk: model call failed ({type(e).__name__}); using fallback")
    return _fallback_text(query, persona, language)


async def build_smalltalk_contract(
    query: str, persona: str, turn_id: str, language: str, t0: float
) -> Dict[str, Any]:
    text = await smalltalk_reply(query, persona, language)
    return {
        "turn_id": turn_id,
        "language": language,
        "persona": persona,
        "spoken_summary": text,
        "display_text": text,
        "visual": {"type": "none", "mode": "replace"},
        "insights": [],
        "sources": [],
        "suggestions": starters_for(persona),
        "access": {"status": "allowed"},
        "export_options": [],
        "status_events": ["Answered conversationally (no data used)"],
        "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
    }
