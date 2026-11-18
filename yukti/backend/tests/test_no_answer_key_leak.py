"""Tests guaranteeing separation from external evaluation artifacts and certified library integrity."""

from pathlib import Path
import yaml

BACKEND_DIR = Path(__file__).resolve().parent.parent
APP_DIR = BACKEND_DIR / "app"
CERTIFIED_DIR = BACKEND_DIR / "certified"
CERTIFIED_FILE = CERTIFIED_DIR / "library.yaml"
BRAIN_CERTIFIED_FILE = APP_DIR / "brain" / "certified" / "library.yaml"


def test_no_answer_key_imports_in_app():
    """Asserts that no file in app/** imports or references answer_key (except optional cache.py)."""
    violations = []
    for p in APP_DIR.rglob("*.py"):
        if p.name == "cache.py":
            continue
        text = p.read_text(encoding="utf-8")
        if "answer_key" in text:
            violations.append(str(p))

    assert not violations, f"Found references to answer_key in application code: {violations}"


def test_certified_library_provenance_and_integrity():
    """Asserts that certified/library.yaml contains the 30 IOCL Q01-Q30 queries with provenance."""
    assert CERTIFIED_FILE.exists(), f"Missing certified library file: {CERTIFIED_FILE}"
    assert BRAIN_CERTIFIED_FILE.exists(), f"Missing brain certified library file: {BRAIN_CERTIFIED_FILE}"
    data = yaml.safe_load(CERTIFIED_FILE.read_text(encoding="utf-8"))
    queries = data.get("queries", [])
    assert len(queries) == 30, f"Expected 30 IOCL certified queries, got {len(queries)}"
    expected_ids = [f"Q{i:02d}" for i in range(1, 31)]
    assert [q["id"] for q in queries] == expected_ids

    for q in queries:
        qid = q["id"]
        prov = q.get("provenance", {})
        assert prov.get("source_file", "").endswith(f"{qid}.sql")
        assert len(prov.get("sha256", "")) == 64
        assert len(q.get("parameterized_sql", "")) > 20
        assert q.get("visual_kind") in {"table", "bar_chart", "kpi_card", "refusal", "document"}
