"""B3.3/B3.4: IOCL Finance-only RBAC policy matrix (8 personas x 14 data classes),
topic guard, small-cell suppression, confidential Finance/Board pack gating, and contract enforcement (offline)."""

import copy
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.brain.query_spec import Filter, QuerySpec
from app.brain.rbac import (
    decide,
    enforce_contract,
    load_policy,
    persona_class,
    row_actions,
    suppress_small_cells,
    to_aggregate,
)

PERSONAS = ["CMD", "DIR_FIN", "DIR_REF", "DIR_MKT", "E1_FIN", "E2_FIN", "E3_FIN", "E4_FIN"]
CLASSES = ["general", "named", "pay", "apar", "sensitive"]

EXPECTED = {
    "CMD":     dict(general="allow", named="allow", pay="allow", apar="allow", sensitive="allow"),
    "DIR_FIN": dict(general="allow", named="allow", pay="allow", apar="allow", sensitive="allow"),
    "DIR_REF": dict(general="allow", named="allow", pay="allow", apar="allow", sensitive="allow"),
    "DIR_MKT": dict(general="allow", named="allow", pay="allow", apar="allow", sensitive="allow"),
    "E1_FIN":  dict(general="allow", named="aggregate", pay="refuse", apar="refuse", sensitive="refuse"),
    "E2_FIN":  dict(general="allow", named="aggregate", pay="refuse", apar="refuse", sensitive="refuse"),
    "E3_FIN":  dict(general="allow", named="aggregate", pay="refuse", apar="refuse", sensitive="refuse"),
    "E4_FIN":  dict(general="allow", named="aggregate", pay="refuse", apar="refuse", sensitive="refuse"),
}


@pytest.mark.parametrize("persona", PERSONAS)
@pytest.mark.parametrize("data_class", CLASSES)
def test_rbac_matrix(persona, data_class):
    assert decide(persona, [data_class], director_function_scope=False).action == EXPECTED[persona][data_class]


V2_PERSONAS = [
    "CMD",
    "DIR_FIN",
    "DIR_REF",
    "DIR_MKT",
    "E1_FIN",
    "E2_FIN",
    "E3_FIN",
    "E4_FIN",
]

V2_DATA_CLASSES = [
    "general_hr",
    "general_fin",
    "fin_internal",
    "fin_confidential",
    "board_draft_pack",
    "policy",
    "named",
    "pay_aggregate",
    "pay_individual",
    "apar",
    "sensitive",
    "self",
    "board_confidential",
    "valuation_run",
]

EXPECTED_V2_DIR_SCOPE_TRUE = {}
for _sp in ("CMD", "DIR_FIN", "DIR_REF", "DIR_MKT"):
    EXPECTED_V2_DIR_SCOPE_TRUE[_sp] = {dc: "allow" for dc in V2_DATA_CLASSES}

for _jp in ("E1_FIN", "E2_FIN", "E3_FIN", "E4_FIN"):
    EXPECTED_V2_DIR_SCOPE_TRUE[_jp] = {
        "general_hr": "aggregate",
        "general_fin": "allow",
        "fin_internal": "aggregate",
        "fin_confidential": "refuse",
        "board_draft_pack": "refuse",
        "policy": "allow",
        "named": "aggregate",
        "pay_aggregate": "allow",
        "pay_individual": "refuse",
        "apar": "refuse",
        "sensitive": "refuse",
        "self": "allow",
        "board_confidential": "refuse",
        "valuation_run": "allow",
    }


@pytest.mark.parametrize("persona", V2_PERSONAS)
@pytest.mark.parametrize("data_class", V2_DATA_CLASSES)
def test_rbac_v2_matrix_112(persona: str, data_class: str):
    """8 IOCL personas x 14 data classes = 112 decisions match rbac_policy.yaml."""
    dec = decide(persona, [data_class], director_function_scope=True)
    assert dec.action == EXPECTED_V2_DIR_SCOPE_TRUE[persona][data_class], (persona, data_class, dec)


@pytest.mark.parametrize("persona", V2_PERSONAS)
def test_public_statements_and_dcf_allowed_for_all_8_personas(persona: str):
    """All 8 IOCL Finance personas can access public statutory statements, policy, WACC, and DCF."""
    for dc in ("general_fin", "policy", "valuation_run"):
        assert decide(persona, [dc]).action == "allow"


@pytest.mark.parametrize("persona", ("E1_FIN", "E2_FIN", "E3_FIN", "E4_FIN"))
def test_confidential_finance_classes_refused_or_aggregated_for_grades_a_to_d(persona: str):
    """Grades A-D refuse confidential Finance/Board packs and aggregate named sub-ledgers."""
    for dc in ("fin_confidential", "board_draft_pack", "board_confidential", "sensitive"):
        assert decide(persona, [dc]).action == "refuse"
    assert decide(persona, ["named"]).action == "aggregate"
    assert decide(persona, ["general_fin"], "Show counterparty credit sub-ledger exposure").action == "refuse"
    assert decide(persona, ["general_fin"], "Show board draft pack for Q4").action == "refuse"


def test_matrix_is_complete_and_unknown_persona_is_junior():
    pol = load_policy()
    for cls in pol["matrix"].values():
        assert set(cls) == set(CLASSES)
    assert persona_class("SOMEONE") == "junior"


def test_most_restrictive_class_wins():
    assert decide("E2_FIN", ["general_fin", "named", "fin_confidential"]).action == "refuse"
    assert decide("E2_FIN", ["general_fin", "named"]).action == "aggregate"


@pytest.mark.parametrize("q,expected", [
    ("What is the average salary of GMs in Delhi?", "refuse"),
    ("Show APAR ratings by grade", "refuse"),
    ("How many vigilance cases are pending?", "refuse"),
    ("Show counterparty credit sub-ledger watchlist", "refuse"),
    ("Show FY26 refinery throughput and GRM by refinery", "allow"),
])
def test_junior_topic_guard(q, expected):
    assert decide("E3_FIN", ["general_fin"], q).action == expected


def test_topic_guard_does_not_apply_to_leadership():
    assert decide("CMD", ["general_fin"], "Show counterparty credit sub-ledger watchlist").action == "allow"
    assert decide("DIR_FIN", ["general_fin"], "Show board draft pack for Q4").action == "allow"
    assert decide("DIR_REF", ["general_fin"], "Show counterparty credit sub-ledger watchlist").action == "allow"
    assert decide("DIR_MKT", ["general_fin"], "Show board draft pack for Q4").action == "allow"


def test_to_aggregate_turns_roster_into_counts_by_grade():
    s = QuerySpec(metric="headcount", grain="row", filters=[Filter(field="wc", value="WC-DEL")])
    a = to_aggregate(s)
    assert a.grain == "aggregate" and a.dimensions == ["grade"] and a.filters == s.filters
    b = to_aggregate(s.model_copy(update={"dimensions": ["discipline"]}))
    assert b.dimensions == ["discipline"]


def test_small_cell_suppression():
    rows = [{"grade": "A", "headcount": 3}, {"grade": "B", "headcount": 5}, {"grade": "C", "headcount": 0},
            {"grade": "D", "avg_age": 2.0}]
    out, n = suppress_small_cells(rows, ["headcount", "avg_age"], apply_secondary=False)
    assert out[0]["headcount"] == "<5" and out[1]["headcount"] == 5 and out[2]["headcount"] == 0
    assert out[3]["avg_age"] == 2.0
    assert n == 1


def test_row_actions_empty_after_hr_strip():
    assert row_actions("CMD", "workforce") == []
    assert row_actions("DIR_FIN", "field_pnl") == []
    assert row_actions("E2_FIN", "workforce") == []


def _contract(cols, rows, status="allowed", vtype="table"):
    return {"turn_id": "t", "language": "en", "spoken_summary": "Here.", "display_text": "Here.",
            "access": {"status": status}, "sources": [{"kind": "data"}],
            "visual": {"type": vtype, "mode": "replace", "table": {"columns": cols, "rows": rows},
                       "chart": {"kind": "bar", "data": copy.deepcopy(rows)}}}


def test_enforce_contract_masks_named_for_junior_and_sets_partial():
    c = _contract(["emp_name", "grade", "headcount"],
                  [{"emp_name": "A", "grade": "B", "headcount": 2}])
    out = enforce_contract(copy.deepcopy(c), "E2_FIN")
    t = out["visual"]["table"]
    assert t["columns"] == ["grade", "headcount"]
    assert "emp_name" not in t["rows"][0]
    assert t["rows"][0]["headcount"] == "<5"
    assert out["access"]["status"] == "partial" and t["masking"]["level"] == "partial"
    assert "chart" not in out["visual"]
    assert "hidden" in out["spoken_summary"]


def test_enforce_contract_leaves_leadership_and_directors_untouched():
    c = _contract(["counterparty_name", "credit_exposure_inr_cr"], [{"counterparty_name": "X Ltd", "credit_exposure_inr_cr": 120.0}])
    for sp in ("CMD", "DIR_FIN", "DIR_REF", "DIR_MKT"):
        assert enforce_contract(copy.deepcopy(c), sp) == c


def test_enforce_contract_refuses_confidential_credit_for_junior():
    c = _contract(["counterparty_name", "credit_exposure_inr_cr"], [{"counterparty_name": "X Ltd", "credit_exposure_inr_cr": 120.0}])
    out = enforce_contract(copy.deepcopy(c), "E2_FIN")
    assert out["access"]["status"] == "refused"
    assert out["access"]["code"] == "R-FUNC"
    assert out["visual"]["type"] == "refusal"


def test_refusal_never_ships_granular_visual():
    c = _contract(["emp_name"], [{"emp_name": "A"}], status="refused", vtype="chart")
    out = enforce_contract(c, "DIR_FIN")
    assert out["visual"]["type"] == "refusal" and "chart" not in out["visual"]


def test_enforce_is_idempotent():
    c = _contract(["emp_id", "headcount"], [{"emp_id": "EMP-1", "headcount": 12}])
    once = enforce_contract(copy.deepcopy(c), "E3_FIN")
    twice = enforce_contract(copy.deepcopy(once), "E3_FIN")
    assert once == twice


def test_secondary_suppression():
    rows = [
        {"grade": "A", "headcount": 10},
        {"grade": "B", "headcount": 2},
        {"grade": "C", "headcount": 20},
    ]
    out, n = suppress_small_cells(rows, ["headcount"], threshold=5, by_name=False)
    assert out[1]["headcount"] == "<5"
    assert out[0]["headcount"] == "suppressed"
    assert out[2]["headcount"] == 20
    assert n == 2


def test_enforce_contract_refuses_pay_for_junior():
    c = _contract(["emp_name", "grade", "gross_salary_inr", "headcount"],
                  [{"emp_name": "A", "grade": "B", "gross_salary_inr": 1, "headcount": 2}])
    out = enforce_contract(copy.deepcopy(c), "E2_FIN")
    assert out["access"]["status"] == "refused"
    assert out["access"]["code"] == "R-PAY"
    assert out["visual"]["type"] == "refusal"


def test_b3_junior_text_and_document_scrubbed():
    c = {"turn_id": "t", "language": "en", "spoken_summary": "Ramesh Goswami has the overdue invoice.",
         "display_text": "Ramesh Goswami ...", "insights": ["Ramesh Goswami overdue"], "access": {"status": "allowed"},
         "sources": [{"kind": "data"}],
         "visual": {"type": "document", "mode": "replace", "document": {"markdown": "| Ramesh Goswami | B |"},
                    "table": {"columns": ["name", "grade"], "rows": [{"name": "Ramesh Goswami", "grade": "B"}]}}}
    out = enforce_contract(c, "E2_FIN")
    assert "Ramesh Goswami" not in str(out)
    assert out["visual"]["type"] != "document" and out["access"]["status"] == "partial"


def test_r4_e1_e4_query_data_tool_absent():
    from app.agent import create_yukti_agent
    from app.auth import Principal, reset_active_principal, set_active_principal

    token = Principal(emp_id="EMP-100152", display_name="Praveen Nair", persona="E2_FIN", function="FIN", grade="B", designation="Test")
    token_auth = set_active_principal(token)
    try:
        agent = create_yukti_agent()
        tool_names = [t.__name__ for t in agent.tools]
        assert "query_data" not in tool_names
    finally:
        reset_active_principal(token_auth)
