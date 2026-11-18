"""P2H.1 / SPEC-06 §4.1 & §8: 8 IOCL Finance personas, alias normalization, UnknownPersona, and dim_app_user completeness."""

from __future__ import annotations

import csv
from pathlib import Path
import re
import sys

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.access_control import (
    ALL_PERSONAS_ORDERED,
    DIRECTOR_PERSONAS,
    JUNIOR_FIN_PERSONAS,
    JUNIOR_HR_PERSONAS,
    JUNIOR_PERSONAS,
    SENIOR_PERSONAS,
    VALID_PERSONAS,
    UnknownPersona,
    check_access,
    normalize_persona,
)
from app.auth import ADMIN_PERSONA_ID, PERSONA_DIRECTORY, issue_token, verify_token

REPO_ROOT = Path(__file__).resolve().parents[3]
DIM_APP_USER_CSV = REPO_ROOT / "data_bank" / "landing" / "sap" / "dim_app_user.csv"
APP_USERS_YAML = Path(__file__).resolve().parent.parent / "app" / "brain" / "app_users.yaml"

CANONICAL_8 = [
    "CMD",
    "DIR_FIN",
    "DIR_REF",
    "DIR_MKT",
    "E1_FIN",
    "E2_FIN",
    "E3_FIN",
    "E4_FIN",
]


def test_valid_personas_exact_8():
    assert set(VALID_PERSONAS) == set(CANONICAL_8)
    assert len(VALID_PERSONAS) == 8
    assert list(ALL_PERSONAS_ORDERED) == CANONICAL_8
    assert set(SENIOR_PERSONAS) == {"CMD", "DIR_FIN", "DIR_REF", "DIR_MKT"}
    assert set(DIRECTOR_PERSONAS) == {"DIR_FIN", "DIR_REF", "DIR_MKT"}
    assert set(JUNIOR_HR_PERSONAS) == set()
    assert set(JUNIOR_FIN_PERSONAS) == {"E1_FIN", "E2_FIN", "E3_FIN", "E4_FIN"}
    assert set(JUNIOR_PERSONAS) == set(JUNIOR_FIN_PERSONAS)


@pytest.mark.parametrize("persona_id", CANONICAL_8)
def test_canonical_personas_normalize_to_self(persona_id: str):
    assert normalize_persona(persona_id) == persona_id
    assert normalize_persona(persona_id.lower()) == persona_id
    assert normalize_persona(f"  {persona_id}  ") == persona_id


@pytest.mark.parametrize(
    "alias,expected",
    [
        ("cmd", "CMD"),
        ("CHAIRMAN", "CMD"),
        ("Chairman, IndianOil", "CMD"),
        ("Director Finance", "DIR_FIN"),
        ("Director (Finance)", "DIR_FIN"),
        ("dir-fin", "DIR_FIN"),
        ("Director Refineries", "DIR_REF"),
        ("Director (Refineries)", "DIR_REF"),
        ("dir-ref", "DIR_REF"),
        ("Director Marketing", "DIR_MKT"),
        ("Director (Marketing)", "DIR_MKT"),
        ("dir-mkt", "DIR_MKT"),
        ("A_FIN", "E1_FIN"),
        ("B_FIN", "E2_FIN"),
        ("C_FIN", "E3_FIN"),
        ("D_FIN", "E4_FIN"),
        ("Grade A Finance", "E1_FIN"),
        ("Grade B Finance", "E2_FIN"),
        ("Grade C Finance", "E3_FIN"),
        ("Grade D Finance", "E4_FIN"),
        ("E1 Finance Officer", "E1_FIN"),
        ("e1-fin", "E1_FIN"),
        ("E2 Finance Executive", "E2_FIN"),
        ("e2-fin", "E2_FIN"),
        ("E3 Finance Officer", "E3_FIN"),
        ("e3-fin", "E3_FIN"),
        ("E4 Finance Manager", "E4_FIN"),
        ("e4-fin", "E4_FIN"),
    ],
)
def test_persona_aliases_normalize(alias: str, expected: str):
    assert normalize_persona(alias) == expected


@pytest.mark.parametrize(
    "auth_alias,expected",
    [
        ("CHAIRMAN", "CMD"),
        ("A_FIN", "E1_FIN"),
        ("B_FIN", "E2_FIN"),
        ("C_FIN", "E3_FIN"),
        ("D_FIN", "E4_FIN"),
    ],
)
def test_auth_token_aliases_normalize(auth_alias: str, expected: str):
    tok = issue_token(auth_alias)
    p = verify_token(tok)
    assert p.persona == expected


@pytest.mark.parametrize(
    "bad_persona",
    [
        "DIR_HR",
        "E1_HR",
        "E2_HR",
        "E3_HR",
        "E4_HR",
        "E5_HR",
        "E0_FIN",
        "ADMIN",
        "GUEST",
        "INTERN",
        "SUPERUSER",
        "",
        "   ",
        None,
    ],
)
def test_unknown_or_removed_hr_persona_raises_never_coerces(bad_persona):
    """BUG-27 / SPEC-06 AC-1: Unknown or removed HR personas raise UnknownPersona (never coerced)."""
    with pytest.raises(UnknownPersona):
        normalize_persona(bad_persona)


def test_demo_admin_and_8_personas_in_auth_directory():
    """SPEC-06 AC-2: PERSONA_DIRECTORY contains all 8 IOCL personas and ADMIN_PERSONA_ID is DEMO_ADMIN."""
    assert set(PERSONA_DIRECTORY.keys()) == set(CANONICAL_8)
    assert ADMIN_PERSONA_ID == "DEMO_ADMIN"
    expected_wcs = {
        "CMD": "WC-DEL",
        "DIR_FIN": "WC-DEL",
        "DIR_REF": "WC-DEL",
        "DIR_MKT": "WC-MUM",
        "E1_FIN": "WC-DEL",
        "E2_FIN": "WC-MUM",
        "E3_FIN": "WC-DEL",
        "E4_FIN": "WC-PNP",
    }
    for pid in CANONICAL_8:
        entry = PERSONA_DIRECTORY[pid]
        assert bool(entry.get("is_admin", False)) is False
        assert re.fullmatch(r"EMP-\d{6}", entry["emp_id"]), f"Invalid emp_id for {pid}: {entry}"
        assert entry["wc_id"] == expected_wcs[pid]
        assert entry["display_name"] not in ("", "Chairman & CEO", "Director", "Director (Finance)")


def test_dim_app_user_csv_and_yaml_completeness():
    """SPEC-06 AC-2 & D-60: 8 IOCL seeded rows in dim_app_user.csv and app_users.yaml pass all completeness flags."""
    assert DIM_APP_USER_CSV.exists(), f"Missing {DIM_APP_USER_CSV}"
    assert APP_USERS_YAML.exists(), f"Missing {APP_USERS_YAML}"

    with DIM_APP_USER_CSV.open("r", encoding="utf-8") as f:
        csv_rows = list(csv.DictReader(f))
    assert len(csv_rows) == 8

    yaml_data = yaml.safe_load(APP_USERS_YAML.read_text(encoding="utf-8"))
    yaml_personas = yaml_data.get("personas") or {}
    assert set(yaml_personas.keys()) == set(CANONICAL_8)

    csv_by_id = {r["persona_id"]: r for r in csv_rows}
    assert set(csv_by_id.keys()) == set(CANONICAL_8)

    assert csv_by_id["CMD"]["emp_id"] == "EMP-000001"
    assert csv_by_id["CMD"]["display_name"] == "Arvinder Singh Sahney"
    assert csv_by_id["CMD"]["functional_designation"] == "Chairman, IndianOil"
    assert csv_by_id["DIR_FIN"]["emp_id"] == "EMP-000003"
    assert csv_by_id["DIR_FIN"]["display_name"] == "Anuj Jain"
    assert csv_by_id["DIR_FIN"]["functional_designation"] == "Director (Finance) & CFO"
    assert csv_by_id["DIR_REF"]["emp_id"] == "EMP-000002"
    assert csv_by_id["DIR_REF"]["display_name"] == "Arvind Kumar"
    assert csv_by_id["DIR_REF"]["functional_designation"] == "Director (Refineries)"
    assert csv_by_id["DIR_MKT"]["emp_id"] == "EMP-000004"
    assert csv_by_id["DIR_MKT"]["display_name"] == "Saumitra P. Srivastava"
    assert csv_by_id["DIR_MKT"]["functional_designation"] == "Director (Marketing)"
    assert csv_by_id["E1_FIN"]["grade"] == "A"
    assert csv_by_id["E2_FIN"]["grade"] == "B"
    assert csv_by_id["E3_FIN"]["grade"] == "C"
    assert csv_by_id["E4_FIN"]["grade"] == "D"
    assert csv_by_id["E4_FIN"]["wc_id"] == "WC-PNP"

    for pid in CANONICAL_8:
        r = csv_by_id[pid]
        y = yaml_personas[pid]
        assert r["emp_id"] == y["emp_id"] == PERSONA_DIRECTORY[pid]["emp_id"]
        assert r["display_name"] == y["display_name"] == PERSONA_DIRECTORY[pid]["display_name"]
        assert str(r["synthetic"]).lower() == "true"
        assert y["synthetic"] is True
        for ok_flag in ("ok_pay", "ok_leave", "ok_posting", "ok_apar"):
            assert str(r[ok_flag]).lower() == "true"
            assert y[ok_flag] is True


@pytest.mark.parametrize("persona_id", CANONICAL_8)
@pytest.mark.parametrize(
    "query,expected_code",
    [
        ("Show Arvinder Singh Sahney's APAR rating", "R-APAR"),
        ("Show Arvinder Singh Sahney's medical records", "R-SENS"),
        ("What is Arvind Kumar's APAR score?", "R-APAR"),
        ("Show Anuj Jain's medical claim history", "R-SENS"),
        ("Show Saumitra P. Srivastava's medical records", "R-SENS"),
    ],
)
def test_d66_office_holder_apar_and_medical_refused_for_every_persona(
    persona_id: str, query: str, expected_code: str
):
    """D-66: Any persona asking for IOCL office-holder APAR or medical records is refused."""
    from app.brain.rbac import OFFICE_HOLDER_REFUSAL_COPY, decide

    pol = decide(persona_id, question=query)
    assert pol.action == "refuse"
    assert pol.code == expected_code
    assert pol.rule_ref == "D-66"
    assert pol.reason == OFFICE_HOLDER_REFUSAL_COPY

    acc = check_access(persona_id, query=query)
    assert acc.status == "refused"
    assert acc.code == expected_code
    assert acc.rule_ref == "D-66"
    assert acc.reason == OFFICE_HOLDER_REFUSAL_COPY


@pytest.mark.parametrize("persona_id", CANONICAL_8)
def test_d66_enforce_contract_and_export_rbac_refuse_office_holder_apar_and_medical(persona_id: str):
    from app.brain.rbac import OFFICE_HOLDER_REFUSAL_COPY, enforce_contract
    from app.export_audit import enforce_export_rbac

    apar_contract = {
        "turn_id": "t-d66-apar",
        "persona": persona_id,
        "spoken_summary": "Arvinder Singh Sahney APAR is 94.6.",
        "display_text": "Arvinder Singh Sahney APAR is 94.6.",
        "visual": {
            "type": "table",
            "mode": "replace",
            "table": {
                "columns": ["emp_id", "name", "numerical_score", "final_rating"],
                "rows": [
                    {
                        "emp_id": "EMP-000001",
                        "name": "Arvinder Singh Sahney",
                        "numerical_score": 94.6,
                        "final_rating": "Outstanding",
                    }
                ],
            },
        },
        "access": {"status": "allowed"},
    }
    enforced = enforce_contract(apar_contract, persona_id, query="show CMD APAR")
    assert enforced["access"]["status"] == "refused"
    assert enforced["access"]["code"] == "R-APAR"
    assert enforced["access"]["rule_ref"] == "D-66"
    assert enforced["access"]["reason"] == OFFICE_HOLDER_REFUSAL_COPY
    assert enforced["visual"]["table"]["rows"] == []

    masked_c, masked_flag, _, _, _ = enforce_export_rbac(apar_contract, persona_id)
    assert masked_flag is True
    assert masked_c["access"]["status"] == "refused"
    assert masked_c["access"]["code"] == "R-APAR"
    assert masked_c["access"]["rule_ref"] == "D-66"
    assert masked_c["visual"]["table"]["rows"] == []
