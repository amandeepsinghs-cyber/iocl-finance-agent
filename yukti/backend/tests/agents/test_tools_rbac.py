import pytest
from app.agents.types import AgentContext
from app.agents.doc_export import tool as doc_tool
from app.agents.fin_diagnostics import tool as fin_tool
from app.agents.registry import get_registry


@pytest.mark.asyncio
async def test_rbac_fin_diagnostics():
    ctx = AgentContext(persona="E1_FIN", session=None, turn_id="t1", language="en")
    res = await fin_tool.run(ctx, {})
    assert "visual" in res or "access" in res


@pytest.mark.asyncio
async def test_rbac_dcf_agent_registry():
    registry = get_registry()
    agent = registry.get_agent("dcf_agent")
    assert agent is not None
    assert agent.requires_role == ["CMD", "DIR_FIN", "DIR_REF", "DIR_MKT", "E1_FIN", "E2_FIN", "E3_FIN", "E4_FIN"]
    assert registry.get_agent("hr_transfer_agent") is None
