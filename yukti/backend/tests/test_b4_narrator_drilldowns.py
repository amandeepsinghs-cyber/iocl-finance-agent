"""B4.2 drill-down chips and B4.3 narrator grounding (offline)."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.brain.drilldowns import make_drilldowns
from app.brain.insights import Insight
from app.brain.narrator import allowed_numbers, compose_spoken, grounding_violations
from app.brain.query_spec import Filter, QuerySpec, SpecPatch, apply_patch

PARADIP = QuerySpec(metric="refinery_grm_usd_bbl", filters=[Filter(field="refinery", value="REF-PRD")])


def _executable(spec, chip):
    if "spec_patch" not in chip:
        return True
    apply_patch(spec, SpecPatch.model_validate(chip["spec_patch"]))  # raises if not a valid patch
    return True


def test_at_least_two_executable_chips_per_data_answer():
    cases = [
        (PARADIP, "CMD", "aggregate"),
        (QuerySpec(metric="refinery_pbt_cr", dimensions=["refinery"]), "DIR_FIN", "aggregate"),
        (QuerySpec(metric="capex_actual_cr"), "CMD", "aggregate"),
        (QuerySpec(metric="corporate_revenue_cr", dimensions=["fy"]), "CMD", "aggregate"),
        (QuerySpec(metric="mou_scorecard"), "DIR_FIN", "row"),
        (PARADIP, "E2_FIN", "aggregate"),
    ]
    for spec, persona, grain in cases:
        chips = make_drilldowns(spec, persona, grain)
        assert 2 <= len(chips) <= 3, (spec.metric, persona, chips)
        assert all(_executable(spec, c) for c in chips)


def test_drilldown_never_offers_row_grain_to_junior():
    for c in make_drilldowns(PARADIP, "E2_FIN", "aggregate"):
        assert c.get("spec_patch") != {"grain": "row"}


def test_compare_chip_uses_valid_spec_patch():
    chips = make_drilldowns(PARADIP, "DIR_REF", "aggregate", max_n=5)
    assert len(chips) >= 2
    for c in chips:
        assert _executable(PARADIP, c)


def test_grounding_flags_invented_numbers_only():
    rows = [{"refinery": "Panipat", "throughput": 16.42}, {"refinery": "Paradip", "throughput": 16.18}]
    ins = [Insight(kind="headline", text="Panipat throughput is 16.42 MMT out of 75.45 MMT.", facts=[16.42, 75.45])]
    allowed = allowed_numbers(rows, ins, PARADIP, extra=[75.45])
    assert grounding_violations("Panipat has 16.42 of 75.45 MMT in FY26, as of 31-Mar-2026.", allowed) == []
    assert grounding_violations("Haldia has 812 MMT throughput.", allowed) == ["812"]
    assert grounding_violations("Top 3 refineries.", allowed) == []  # small structural integers


def test_compose_spoken_is_2_to_4_sentences_and_falls_back_on_ungrounded():
    rows = [{"d": "A", "v": 10}, {"d": "B", "v": 20}]
    allowed = allowed_numbers(rows, [], None, extra=[30])
    good = compose_spoken("30 employees across 2 groups. Highest: B (20).",
                          [Insight(kind="headline", text="B holds 66.7% of the total.", facts=[66.7])],
                          allowed | {66.7})
    assert 2 <= good["sentences"] <= 4 and good["ungrounded"] == []
    bad = compose_spoken("30 employees across 2 groups.", [Insight(kind="note", text="That is 45% more than 2019.")],
                         allowed)
    assert "45" not in bad["text"] and bad["ungrounded"] == []



def test_headline_values_and_roster_mix_cover_kpi_and_roster_answers():
    from app.brain.insights import InsightContext, compute_insights
    kpi = InsightContext(metric="headcount", metric_label="Employees", unit="employees", dim=None,
                         value_col="headcount", rows=[{"headcount": 419, "avg_age": 47.2}], scope=["Delhi HQ"])
    ins = compute_insights(kpi)
    assert len(ins) >= 2 and ins[0].text == "Employees: 419 (Delhi HQ)."
    roster = InsightContext(metric="headcount", metric_label="Employees", unit="employees", dim=None, value_col=None,
                            grain="row", rows=[{"grade": "E3", "discipline": "HR", "station_tenure_years": 6.0},
                                               {"grade": "E3", "discipline": "IT", "station_tenure_years": 5.5},
                                               {"grade": "E5", "discipline": "HR", "station_tenure_years": 7.0}])
    ins2 = compute_insights(roster)
    texts = [i.text for i in ins2]
    assert any("largest grade group is E3: 2 of 3" in t for t in texts) and len(ins2) >= 2


def test_top_two_gap_for_two_way_and_non_additive():
    from app.brain.insights import InsightContext, top_two_gap
    ctx = InsightContext(metric="m", metric_label="EBITDA margin", unit="pct", dim="asset", value_col="m",
                         rows=[{"asset": "Ankleshwar", "m": 69.2}, {"asset": "Bassein", "m": 64.2}, {"asset": "MH", "m": 58.1}])
    ins = top_two_gap(ctx)
    assert ins.text == "Ankleshwar leads Bassein by 5.0 pts (69.2% vs 64.2%)."
    add3 = InsightContext(metric="h", metric_label="Employees", unit="employees", dim="wc", value_col="h",
                          rows=[{"wc": "A", "h": 3}, {"wc": "B", "h": 2}, {"wc": "C", "h": 1}])
    assert top_two_gap(add3) is None
