from datetime import date

from tripforge.plan import HOURS_PER_DAY, build, city_days


def test_city_days_cover_every_day(brief):
    spans = city_days(brief)
    assert spans[0] == ("Hanoi", 1, 3)
    assert sum(n for _, _, n in spans) == brief.days


def test_last_city_absorbs_mismatch(brief):
    short = brief.model_copy(update={"days": 8})
    assert sum(n for _, _, n in city_days(short)) == 8


def test_every_must_see_is_scheduled(brief, coords):
    stops, _ = build(brief, coords)
    placed = {s.place for s in stops}
    assert {p.name for p in brief.places if p.must} <= placed


def test_day_budget_respected_except_single_long_stop(brief, coords):
    stops, _ = build(brief, coords)
    cap = HOURS_PER_DAY[brief.pace]
    for day in {s.day for s in stops}:
        ds = [s for s in stops if s.day == day and s.kind != "nightlife"]
        assert sum(s.hours for s in ds) <= cap or len(ds) == 1


def test_nightlife_goes_last(brief, coords):
    stops, _ = build(brief, coords)
    for s in stops:
        if s.kind == "nightlife":
            later = [x for x in stops if x.day == s.day and x.seq > s.seq]
            assert not later


def test_dates_and_determinism(brief, coords):
    a, _ = build(brief, coords, date(2027, 1, 10))
    b, _ = build(brief, coords, date(2027, 1, 10))
    assert a == b
    assert a[0].date == date(2027, 1, 10)
    assert max(s.date for s in a) <= date(2027, 1, 19)


def test_ungeocoded_places_are_skipped_not_crashing(brief, coords):
    partial = {k: v for k, v in coords.items() if not k.startswith("Ha")}
    stops, _ = build(brief, partial)
    assert all(s.place in partial for s in stops)
