import json

import pytest

from tripforge import extract, geo


def test_haversine_hanoi_to_hcmc():
    km = geo.haversine_km(21.0285, 105.8542, 10.7769, 106.7009)
    assert 1130 < km < 1150


def test_geocoder_caches_hits_and_misses(con):
    calls = []

    def fake(q):
        calls.append(q)
        return [] if "Nowhere" in q else [{"lat": "21.0", "lon": "105.8", "display_name": q}]

    g = geo.Geocoder(con, fetch=fake, sleep=lambda s: None)
    assert g.lookup("Hoan Kiem Lake", "Hanoi", "Vietnam").lat == 21.0
    assert g.lookup("Hoan Kiem Lake", "Hanoi", "Vietnam").source == "nominatim"
    assert g.lookup("Nowhere Cafe", "Hanoi", "Vietnam") is None
    assert g.lookup("Nowhere Cafe", "Hanoi", "Vietnam") is None
    assert len(calls) == 2


def test_geocoder_throttles_to_policy(con):
    t = [0.0]
    slept = []

    def sleep(s):
        slept.append(s)
        t[0] += s

    g = geo.Geocoder(con, fetch=lambda q: [{"lat": 1, "lon": 1}], sleep=sleep, clock=lambda: t[0])
    for i in range(3):
        g.lookup(f"P{i}", "C", "X")
    assert len(slept) == 2 and all(s >= 1.0 for s in slept)


def test_offline_never_calls_network(con):
    g = geo.Geocoder(con, offline=True, fetch=lambda q: pytest.fail("network call"))
    assert g.lookup("Anything", "Hanoi", "Vietnam") is None


def test_extraction_cached_per_notes_and_overrides(con, brief):
    calls = []

    def llm(notes):
        calls.append(notes)
        return brief.model_dump_json()

    b1, c1 = extract.extract(con, "notes", {"days": 10}, "m", llm=llm)
    b2, c2 = extract.extract(con, "notes", {"days": 10}, "m", llm=llm)
    assert (c1, c2) == (False, True) and len(calls) == 1
    extract.extract(con, "notes", {"days": 9}, "m", llm=llm)
    assert len(calls) == 2


def test_cli_overrides_beat_llm(con, brief):
    raw = brief.model_dump_json()
    b, _ = extract.extract(con, "n", {"budget_inr": 999, "tier": None}, "m", llm=lambda n: raw)
    assert b.budget_inr == 999 and b.tier == brief.tier


def test_bad_llm_output_is_rejected(con):
    bad = json.dumps({"country": "Vietnam", "days": 0, "cities": [], "places": []})
    with pytest.raises(ValueError):
        extract.extract(con, "n", {}, "m", llm=lambda n: bad)
    assert con.execute("select count(*) from extractions").fetchone()[0] == 0
