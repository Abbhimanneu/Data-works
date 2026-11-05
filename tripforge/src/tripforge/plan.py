"""Places + cities -> ordered stops per day. Pure functions, no I/O."""

import math
from datetime import date, timedelta

from tripforge.geo import haversine_km
from tripforge.models import Stop, TripBrief

HOURS_PER_DAY = {"slow": 5.0, "normal": 7.0, "fast": 9.0}
TRANSFER_DAY_FACTOR = 0.5  # arrival day in a new city has half the time


def city_days(brief: TripBrief) -> list[tuple[str, int, int]]:
    """[(city, first_day, n_days)]. Each night gives a day in that city; the last city gets
    the remaining days so the total always equals brief.days."""
    out, day = [], 1
    for i, c in enumerate(brief.cities):
        last = i == len(brief.cities) - 1
        n = max(1, brief.days - day + 1) if last else max(1, c.nights)
        n = min(n, brief.days - day + 1)
        if n <= 0:
            break
        out.append((c.name, day, n))
        day += n
    return out


def _sweep_order(points: list[tuple[str, float, float, float, str]]):
    lat0 = sum(p[1] for p in points) / len(points)
    lon0 = sum(p[2] for p in points) / len(points)
    return sorted(points, key=lambda p: (math.atan2(p[1] - lat0, p[2] - lon0), p[0]))


EVENING = {"nightlife"}


def _cost(p) -> float:
    # evening stops happen after the day's sightseeing, so they don't use the day budget
    return 0.0 if p[4] in EVENING else p[3]


def _nearest_neighbour(points):
    if not points:
        return points
    late = [p for p in points if p[4] in EVENING]
    points = [p for p in points if p[4] not in EVENING] or late
    if points is late:
        late = []
    start = min(points, key=lambda p: (p[2], p[1]))  # westmost, deterministic
    route, left = [start], [p for p in points if p is not start]
    while left:
        cur = route[-1]
        nxt = min(left, key=lambda p: (haversine_km(cur[1], cur[2], p[1], p[2]), p[0]))
        route.append(nxt)
        left.remove(nxt)
    return route + late


def build(
    brief: TripBrief,
    coords: dict[str, tuple[float, float]],
    start: date | None = None,
) -> tuple[list[Stop], list[str]]:
    """coords: place name -> (lat, lon) for places that geocoded.
    Returns stops and names of places that did not fit."""
    cap = HOURS_PER_DAY[brief.pace]
    stops: list[Stop] = []
    overflow: list[str] = []

    for idx, (city, first_day, n_days) in enumerate(city_days(brief)):
        pts = [
            (p.name, *coords[p.name], p.hours, p.kind, p.must)
            for p in brief.places
            if p.city.lower() == city.lower() and p.name in coords
        ]
        pts = [
            (n, la, lo, h, k) for n, la, lo, h, k, m in sorted(pts, key=lambda x: (not x[5], x[0]))
        ]
        if not pts:
            continue

        budgets = [
            cap * (TRANSFER_DAY_FACTOR if (d == 0 and idx > 0) else 1.0) for d in range(n_days)
        ]
        must = {pl.name for pl in brief.places if pl.must}
        ordered = _sweep_order(pts)  # keeps neighbours together
        total = sum(_cost(p) for p in ordered)
        targets = [min(b, total * b / sum(budgets)) for b in budgets]

        buckets: list[list] = [[] for _ in range(n_days)]
        used = [0.0] * n_days
        spill = []
        d = 0
        for p in ordered:
            while d < n_days - 1 and buckets[d] and used[d] + _cost(p) > targets[d] + 0.5:
                d += 1
            if used[d] + _cost(p) <= budgets[d] or not buckets[d]:
                buckets[d].append(p)
                used[d] += _cost(p)
            else:
                spill.append(p)
        # a spilled must-see replaces the longest optional stop that frees enough time
        for p in [x for x in spill if x[0] in must]:
            spill.remove(p)
            for j in sorted(range(n_days), key=lambda j: used[j]):
                optional = sorted(
                    (q for q in buckets[j] if q[0] not in must), key=lambda q: -_cost(q)
                )
                if used[j] + _cost(p) <= budgets[j]:
                    buckets[j].append(p)
                    used[j] += _cost(p)
                    break
                drop = next(
                    (q for q in optional if used[j] - _cost(q) + _cost(p) <= budgets[j]), None
                )
                if drop:
                    buckets[j].remove(drop)
                    buckets[j].append(p)
                    used[j] += _cost(p) - _cost(drop)
                    spill.append(drop)
                    break
            else:
                # longer than any day allows (overnight cruise, trek): give it a day of its own
                j = max(range(n_days), key=lambda j: (budgets[j], -j))
                spill += [q for q in buckets[j] if q[0] not in must]
                buckets[j] = [q for q in buckets[j] if q[0] in must] + [p]
                used[j] = sum(_cost(q) for q in buckets[j])
        overflow += [p[0] for p in spill]

        for k, bucket in enumerate(buckets):
            day = first_day + k
            prev = None
            for seq, p in enumerate(_nearest_neighbour(bucket), start=1):
                km = haversine_km(prev[1], prev[2], p[1], p[2]) if prev else 0.0
                stops.append(
                    Stop(
                        day=day,
                        date=start + timedelta(days=day - 1) if start else None,
                        city=city,
                        seq=seq,
                        place=p[0],
                        kind=p[4],
                        hours=p[3],
                        lat=p[1],
                        lon=p[2],
                        km_from_prev=round(km, 1),
                    )
                )
                prev = p
    return stops, overflow
