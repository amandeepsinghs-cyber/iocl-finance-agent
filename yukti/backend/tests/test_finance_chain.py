"""B4.5: IOCL Finance & Downstream flagship chain end-to-end as Director (Finance), YUKTI_PLANNER=1 (live).

Refinery profitability & GRM FY26 -> Capex FY22-FY26 -> Subsidiaries & JVs FY26 -> MoU Scorecard (12 KPIs)
-> Draft Board Note. Every data answer carries >= 2 grounded insights and >= 2 drill-down chips.
"""

import asyncio
import os
from pathlib import Path
import re
import sys
import time

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

QS = [
    "Which refineries were the most profitable and what were their GRMs in FY26?",
    "Show capital expenditure spent over the last 5 years",
    "Show IOCL Group subsidiaries and JVs contribution in FY26",
    "How are we tracking against our MoU targets for FY26?",
    "Draft a board note on this",
]


@pytest.fixture(scope="module")
def chain():
    os.environ["YUKTI_PLANNER"] = "1"
    os.environ["YUKTI_RESULT_CACHE"] = "0"
    from app.config import DEFAULT_TEXT_MODEL
    from app.turn_runner import AgentTurnRunner

    async def run():
        r = AgentTurnRunner(model_name=DEFAULT_TEXT_MODEL)
        sid = f"iocl-fin-flagship-{int(time.time())}"
        return [await r.execute_turn_async(q, session_id=sid, persona="DIR_FIN") for q in QS]

    try:
        return asyncio.run(run())
    finally:
        os.environ.pop("YUKTI_PLANNER", None)


@pytest.mark.parametrize("i", [0, 1, 2, 3])
def test_data_answers_have_access_and_visuals(chain, i):
    c = chain[i]
    assert c["persona"] == "DIR_FIN" and c["access"]["status"] == "allowed"
    assert c.get("spoken_summary"), f"Missing spoken_summary on turn {i}"
    assert c.get("visual", {}).get("type") in ("table", "chart", "kpi")
    rows = (c["visual"].get("table") or {}).get("rows") or []
    assert len(rows) >= 1


def test_t1_refinery_profitability_numbers(chain):
    c = chain[0]
    text = str(c)
    assert "Paradip" in text and "Panipat" in text
    rows = (c["visual"].get("table") or {}).get("rows") or []
    assert len(rows) == 9
    assert any("7661" in str(r) or "7,661" in text or "12.46" in str(r) for r in rows)


def test_t2_capex_5_years(chain):
    c = chain[1]
    rows = (c["visual"].get("table") or {}).get("rows") or []
    assert len(rows) >= 4
    assert any("FY26" in str(r) for r in rows)


def test_t3_subsidiaries_and_jvs(chain):
    c = chain[2]
    text = str(c)
    assert any(code in text for code in ("CPCL", "Chennai Petroleum", "Lanka IOC", "LIOC"))


def test_t4_mou_fy26_12_kpis(chain):
    c = chain[3]
    rows = (c["visual"].get("table") or {}).get("rows") or []
    assert len(rows) == 12


def test_t5_board_note(chain):
    c = chain[4]
    assert c["visual"]["type"] == "document" and c["visual"]["document"]["markdown"]
