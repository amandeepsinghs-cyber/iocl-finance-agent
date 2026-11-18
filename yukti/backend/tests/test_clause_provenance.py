"""P0.7 (BUG-31, D-35): synthetic policy clauses carry provenance "illustrative" in data, contract and UI."""

import asyncio
import csv
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import RULEBOOKS_CSV_PATH  # noqa: E402
from app.tools.policy_search import PolicySearchEngine  # noqa: E402

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"


def _rows():
    with open(RULEBOOKS_CSV_PATH, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def test_csv_every_row_has_provenance_and_no_hr_or_jrtp():
    rows = _rows()
    assert len(rows) == 40
    assert all(r.get("provenance") in ("real", "illustrative") for r in rows), "missing/invalid provenance"
    assert not [r for r in rows if r["doc_id"] in ("JRTP", "Leave Rules", "HR Manual", "R&P/Promotion")]
    assert len([r for r in rows if r["doc_id"] == "IOCL-ACCT" and r["provenance"] == "real"]) == 8
    assert not [r for r in rows if r["doc_id"] == "IOCL-DOA" and r["provenance"] == "real"]


def test_iocl_doa_clause_payload_is_illustrative():
    eng = PolicySearchEngine()
    hits = eng.search_local("IOCL-DOA spot crude oil cargo procurement threshold", top_k=3)
    assert hits, "no IOCL-DOA clause found"
    doa = [h for h in hits if "Delegation of Financial Powers" in h["doc_id"] and "2.1" in h["clause_ref"]]
    assert doa and all(h["provenance"] == "illustrative" for h in doa)
    assert "2,500" in doa[0]["text"]


def test_search_results_always_carry_provenance():
    eng = PolicySearchEngine()
    for q in ("spot crude oil cargo procurement threshold", "crack-spread hedging band",
              "Ind AS 115 Central Excise Duty", "stage-gate equity IRR hurdle rate", "DPE Maharatna MoU"):
        for h in eng.search_local(q, top_k=3):
            assert h.get("provenance") in ("real", "illustrative"), (q, h.get("clause_ref"))


@pytest.mark.asyncio
async def test_iocl_doa_policy_answer_is_illustrative_and_has_no_hr_footer(monkeypatch):
    monkeypatch.setenv("YUKTI_PLANNER", "0")
    from app.config import DEFAULT_TEXT_MODEL
    from app.turn_runner import AgentTurnRunner

    runner = AgentTurnRunner(model_name=DEFAULT_TEXT_MODEL)
    c = await runner.execute_turn_async(
        "What are the IOCL-DOA approval thresholds for spot crude oil cargo procurement?",
        session_id="p07-iocl-doa",
        persona="CMD",
    )
    vis = c.get("visual") or {}
    assert vis.get("type") == "clause", f"expected a clause card, got {vis.get('type')}"
    clause = vis["clause"]
    assert clause["provenance"] == "illustrative"
    assert "Delegation of Financial Powers" in (clause.get("doc_title") or "")
    assert "JRTP" not in (clause.get("doc_title") or "") and "ONGC" not in (clause.get("text") or "")
    assert "Statutory" not in (vis.get("subtitle") or "")


def test_clause_renderer_has_badge_and_no_hardcoded_jrtp_footer():
    src = (FRONTEND / "components" / "renderers" / "ClauseRenderer.tsx").read_text(encoding="utf-8")
    assert "'Job Rotation & Transfer Policy (JRTP)'" not in src  # the old hard-coded fallback title/footer
    assert "Illustrative" in src and "Illustrative policy clause for IOCL demo; internal rulebook text is not public." in src
    assert "clause.provenance !== 'real'" in src  # default-safe: unknown provenance renders as Illustrative
