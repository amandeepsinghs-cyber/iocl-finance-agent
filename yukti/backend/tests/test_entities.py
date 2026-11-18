"""Unit tests for IOCL entity dictionary (Step 6)."""

import json
from pathlib import Path
import sys
import yaml
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.semantic.entities import get_entities


@pytest.fixture(scope="module")
def ents():
    return get_entities()


def test_resolve_wc_mumbai(ents):
    assert ents.resolve_wc("Mumbai mein marketing budget kya hai?") == "WC-MUM"


def test_resolve_wcs_delhi_vs_mumbai(ents):
    assert ents.resolve_wcs("Compare Delhi vs Mumbai") == ["WC-DEL", "WC-MUM"]


def test_resolve_wc_panipat(ents):
    assert ents.resolve_wc("What is capex at Panipat refinery?") == "WC-PNP"


def test_resolve_wc_koyali(ents):
    assert ents.resolve_wc("Crude throughput at Koyali Gujarat refinery") == "WC-KOY"


def test_resolve_wc_delhi_hindi(ents):
    assert ents.resolve_wc("दिल्ली में कितने कार्यालय") == "WC-DEL"


def test_resolve_region_north_east(ents):
    res = ents.resolve_region("North East refineries")
    assert res is not None
    name, codes = res
    assert "north east" in name
    assert set(codes) == {"WC-BGR", "WC-GUW", "WC-DGB"}


def test_replace_codes(ents):
    assert ents.replace_codes("REF-PNP and REF-PRD") == "Panipat Refinery & Petrochemical Complex and Paradip Refinery"
    assert ents.replace_codes("WC-ZZZ") == "WC-ZZZ"
    nested_input = {
        "level1": ["REF-KYL", {"level2": "REF-MTR"}],
        "other": 123,
    }
    expected_output = {
        "level1": ["Gujarat (Koyali) Refinery", {"level2": "Mathura Refinery"}],
        "other": 123,
    }
    assert ents.replace_codes(nested_input) == expected_output


def test_resolve_refinery(ents):
    if hasattr(ents, "resolve_refinery"):
        assert ents.resolve_refinery("Paradip GRM in FY26") == "REF-PRD"


def test_resolve_grades(ents):
    assert set(ents.grades.keys()) == {"A", "B", "C", "D", "E", "F", "G", "H", "I"}


def test_resolve_disciplines(ents):
    assert "DISC-FIN" in ents.resolve_disciplines("finance accounts pricing")


def test_all_codes_in_aliases_yaml_exist_in_entities_json():
    sem_dir = Path(__file__).resolve().parent.parent / "app" / "semantic"
    ej = json.loads((sem_dir / "entities.json").read_text(encoding="utf-8"))
    ay = yaml.safe_load((sem_dir / "entity_aliases.yaml").read_text(encoding="utf-8")) or {}

    for code in ay.get("work_centres", {}):
        assert code in ej.get("work_centres", {}), f"work_centre {code} not in entities.json"

    for code in ay.get("refineries", {}):
        assert code in ej.get("refineries", {}), f"refinery {code} not in entities.json"

    for code in ay.get("subsidiaries", {}):
        assert code in ej.get("subsidiaries", {}), f"subsidiary {code} not in entities.json"

    for code in ay.get("products", {}):
        assert code in ej.get("products", {}), f"product {code} not in entities.json"

    for code in ay.get("pipelines", {}):
        assert code in ej.get("pipelines", {}), f"pipeline {code} not in entities.json"

    for code in ay.get("disciplines", {}):
        assert code in ej.get("disciplines", {}), f"discipline {code} not in entities.json"

    for code in ay.get("grades", {}):
        assert code in ej.get("grades", {}), f"grade {code} not in entities.json"

    for group_name, codes in (ay.get("discipline_groups") or {}).items():
        for code in codes:
            assert code in ej.get("disciplines", {}), f"discipline_group {group_name} code {code} not in entities.json"

    for region_name, reg_cfg in (ay.get("regions") or {}).items():
        for code in reg_cfg.get("wc_ids") or []:
            assert code in ej.get("work_centres", {}), f"region {region_name} wc_id {code} not in entities.json"


def test_work_centres_and_refineries_count(ents):
    assert len(ents.work_centres) == 13
    assert len(ents.refineries) == 12
