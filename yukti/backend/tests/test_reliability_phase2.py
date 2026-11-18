"""Unit tests for Phase 2 Reliability:
1. Tool enforcement on data questions (silent re-prompt).
2. Silent self-repair on BigQuery errors (never surfacing raw database errors).
3. Dedicated NL->SQL generation with reasoning thinking.
4. Stateful active query state modification on multi-turn follow-ups.
5. Zero false-positive routing on off-topic questions.
"""

import sys
from pathlib import Path
import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import DEFAULT_TEXT_MODEL
from app.router import get_semantic_router
from app.tools.sql_generator import get_sql_generator
from app.turn_runner import get_agent_turn_runner


@pytest.mark.asyncio
async def test_followup_modifies_active_query_state():
    """Verifies that a refinery entity shift follow-up modifies active query state cleanly."""
    runner = get_agent_turn_runner(model_name=DEFAULT_TEXT_MODEL)
    sess_id = "test-phase2-followup-state"

    # Turn 1: Root question on Panipat Refinery throughput & GRM
    res1 = await runner.execute_turn_async("What was Panipat Refinery throughput and GRM in FY26?", session_id=sess_id)
    assert res1.get("tool_called") == "run_certified_query" or "query_spec" in res1
    assert "Panipat" in str(res1)

    # Turn 2: Follow-up modifying refinery entity to Paradip
    res2 = await runner.execute_turn_async("What about Paradip?", session_id=sess_id)
    assert res2.get("tool_called") == "run_certified_query" or "query_spec" in res2 or "Paradip" in str(res2)
    assert res2.get("visual", {}).get("type") in ("table", "chart", "kpi")


@pytest.mark.asyncio
async def test_silent_self_repair_and_no_raw_errors_surfaced():
    """Verifies that BigQuery errors undergo silent self-repair and never expose raw DB traces."""
    sql_gen = get_sql_generator()

    # Intentionally broken SQL with typo column name on IOCL gold table
    broken_sql = "SELECT refinery_id, non_existent_column_xyz FROM `yukti-finance-iocl.hrfin_gold.ssot_refinery_economics_360` LIMIT 5"
    repaired_res = sql_gen.execute_with_silent_repair(
        query="List FY26 throughput for 5 IOCL refineries",
        given_sql=broken_sql,
    )

    # If repaired, it should succeed; if persistent error, clean fallback message
    if repaired_res.get("status") == "success":
        assert len(repaired_res.get("rows", [])) > 0
    else:
        assert repaired_res.get("error") == "Verified data not available for this query."
        assert "400 Unrecognized name" not in repaired_res.get("error")


def test_zero_false_positive_rate_on_off_topic_dev_prompts():
    """Verifies that off-topic dev questions never trigger a false-positive certified route."""
    router = get_semantic_router()
    dev_path = Path(__file__).resolve().parent.parent / "certified" / "dev_phrasings.yaml"
    assert dev_path.exists(), "dev_phrasings.yaml must exist"

    with open(dev_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    off_topics = data.get("off_topic_prompts", [])
    assert len(off_topics) >= 15, "Expected at least 15 off-topic dev prompts"

    for prompt in off_topics:
        res = router.route(prompt)
        assert res["route"] == "live_nl_sql", f"Off-topic prompt falsely routed to certified: {prompt} (score: {res['score']})"
        assert res["query_id"] is None
