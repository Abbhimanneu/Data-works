"""Cost model. Every number comes from config/costs/<country>.yaml and says so in `basis`."""

import math
from pathlib import Path

import yaml

from tripforge.models import CostLine, Stop, TripBrief
from tripforge.plan import city_days


def load(config_dir: Path, country: str) -> dict:
    path = config_dir / "costs" / f"{country.lower().replace(' ', '_')}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"no cost file for {country}: create {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def estimate(brief: TripBrief, stops: list[Stop], cfg: dict) -> list[CostLine]:
    fx = cfg["fx"]["inr_per_local"]
    cur = cfg["fx"]["currency"]
    t = cfg["tiers"][brief.tier]
    n = brief.travelers
    rooms = math.ceil(n / cfg.get("people_per_room", 2))
    inr = lambda local: round(local * fx, 0)  # noqa: E731
    lines: list[CostLine] = []

    intl = cfg.get("international_flight_inr", {}).get(brief.tier)
    if intl:
        lines.append(
            CostLine(
                day=None,
                category="Flights",
                item="International return flight",
                amount_inr=intl * n,
                basis=f"₹{intl:,} x {n} pax (config estimate)",
            )
        )

    for city, first, nd in city_days(brief):
        nights = nd if first + nd - 1 < brief.days else nd - 1
        for d in range(first, first + nd):
            lines.append(
                CostLine(
                    day=d,
                    category="Food",
                    item=f"Meals in {city}",
                    amount_inr=inr(t["food_per_person_day"] * n),
                    basis=f"{t['food_per_person_day']:,} {cur} x {n} pax",
                )
            )
            lines.append(
                CostLine(
                    day=d,
                    category="Local transport",
                    item=f"Grab/taxi in {city}",
                    amount_inr=inr(t["local_transport_per_day"] * rooms),
                    basis=f"{t['local_transport_per_day']:,} {cur} x {rooms} ride group",
                )
            )
        city_override = cfg.get("stay_overrides", {}).get(city, {}).get(brief.tier)
        per_night = city_override or t["stay_per_room_night"]
        if nights > 0:
            lines.append(
                CostLine(
                    day=first,
                    category="Stay",
                    item=f"{nights} night(s) in {city}",
                    amount_inr=inr(per_night * rooms * nights),
                    basis=f"{per_night:,} {cur} x {rooms} room x {nights} night",
                )
            )

    order = [c.name for c in brief.cities]
    legs = cfg.get("legs", {})
    for prev, nxt in zip(order, order[1:], strict=False):
        leg = legs.get(f"{prev} -> {nxt}") or legs.get(f"{nxt} -> {prev}")
        first = next(f for name, f, _ in city_days(brief) if name == nxt)
        if leg:
            price = leg.get(brief.tier, leg.get("mid"))
            lines.append(
                CostLine(
                    day=first,
                    category="Transfers",
                    item=f"{prev} to {nxt} ({leg['mode']})",
                    amount_inr=inr(price * n),
                    basis=f"{price:,} {cur} x {n} pax",
                )
            )
        else:
            lines.append(
                CostLine(
                    day=first,
                    category="Transfers",
                    item=f"{prev} to {nxt}",
                    amount_inr=0,
                    basis="MISSING: add this leg to the cost file",
                )
            )

    fees = cfg.get("entry_fees", {})
    default_fee = cfg.get("default_fee_by_kind", {})
    for s in stops:
        fee = fees.get(s.place)
        basis = f"{fee:,} {cur} x {n} pax" if fee is not None else None
        if fee is None:
            fee = default_fee.get(s.kind, 0)
            basis = f"default for {s.kind}: {fee:,} {cur} x {n} pax"
        if fee:
            lines.append(
                CostLine(
                    day=s.day,
                    category="Entry & activities",
                    item=s.place,
                    amount_inr=inr(fee * n),
                    basis=basis,
                )
            )

    buf = cfg.get("buffer_pct", 0)
    if buf:
        sub = sum(line.amount_inr for line in lines)
        lines.append(
            CostLine(
                day=None,
                category="Buffer",
                item=f"{buf}% contingency",
                amount_inr=round(sub * buf / 100, 0),
                basis=f"{buf}% of subtotal",
            )
        )
    rank = {"Flights": 0, "Buffer": 2}
    return sorted(lines, key=lambda c: (rank.get(c.category, 1), c.day or 0))
