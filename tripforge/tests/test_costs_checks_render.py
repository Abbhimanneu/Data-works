from pathlib import Path

from tripforge import checks, costs, render_map, render_pdf
from tripforge.plan import build

CONFIG = Path(__file__).resolve().parents[1] / "config"


def _run(brief, coords):
    stops, overflow = build(brief, coords)
    lines = costs.estimate(brief, stops, costs.load(CONFIG, brief.country))
    return stops, overflow, lines


def test_stay_nights_match_route(brief, coords):
    _, _, lines = _run(brief, coords)
    stay = [c for c in lines if c.category == "Stay"]
    nights = sum(int(c.item.split()[0]) for c in stay)
    assert nights == brief.days - 1


def test_every_line_has_a_basis_and_flights_first(brief, coords):
    _, _, lines = _run(brief, coords)
    assert all(c.basis for c in lines)
    assert lines[0].category == "Flights" and lines[-1].category == "Buffer"


def test_missing_leg_is_flagged_not_guessed(brief, coords):
    odd = brief.model_copy(
        update={"cities": [*brief.cities[:-1], brief.cities[-1].model_copy(update={"name": "Hue"})]}
    )
    stops, overflow, lines = _run(odd, coords)
    issues = checks.run(odd, [], overflow, stops, lines)
    assert any(i.check == "cost_gap" for i in issues)


def test_budget_and_unresolved_checks(brief, coords):
    stops, overflow, lines = _run(brief, coords)
    tight = brief.model_copy(update={"budget_inr": 1000})
    names = [p.name for p in brief.places][:10]
    issues = {i.check: i.severity for i in checks.run(tight, names, overflow, stops, lines)}
    assert issues["budget"] == "warn"
    assert issues["geocode"] == "error"  # 10/24 > 30%


def test_renders_pdf_and_map(tmp_path, brief, coords):
    stops, overflow, lines = _run(brief, coords)
    issues = checks.run(brief, [], overflow, stops, lines)
    pdf = render_pdf.render(
        brief, stops, lines, issues, tmp_path / "t.pdf", "Test", "notes", "map.html"
    )
    html = render_map.render(stops, tmp_path / "map.html", "Test")
    assert pdf.read_bytes()[:4] == b"%PDF" and pdf.stat().st_size > 20_000
    assert html.read_text().count("L.circleMarker") == len(stops)


def test_indian_number_format():
    assert render_pdf.inr(216524) == "₹2,16,524"
    assert render_pdf.inr(300000) == "₹3,00,000"
    assert render_pdf.inr(999) == "₹999"
