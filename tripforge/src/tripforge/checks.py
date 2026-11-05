from dataclasses import dataclass

from tripforge.models import CostLine, Stop, TripBrief

MAX_UNRESOLVED_SHARE = 0.3
MAX_LEG_KM = 40  # inside one city day


@dataclass(frozen=True)
class Issue:
    severity: str  # error | warn
    check: str
    detail: str


def run(
    brief: TripBrief,
    unresolved: list[str],
    overflow: list[str],
    stops: list[Stop],
    costs: list[CostLine],
) -> list[Issue]:
    issues: list[Issue] = []
    total_places = len(brief.places) or 1

    share = len(unresolved) / total_places
    if unresolved:
        sev = "error" if share > MAX_UNRESOLVED_SHARE else "warn"
        issues.append(
            Issue(
                sev,
                "geocode",
                f"{len(unresolved)}/{total_places} places not found: " + ", ".join(unresolved),
            )
        )

    known = {c.name.lower() for c in brief.cities}
    orphans = [p.name for p in brief.places if p.city.lower() not in known]
    if orphans:
        issues.append(
            Issue(
                "warn", "city_mismatch", "places in cities not on the route: " + ", ".join(orphans)
            )
        )

    nights = sum(c.nights for c in brief.cities)
    if nights != brief.days - 1:
        issues.append(
            Issue(
                "warn",
                "nights",
                f"{nights} nights listed for a {brief.days}-day trip; "
                "last city was stretched or cut to fit",
            )
        )

    if overflow:
        issues.append(Issue("warn", "capacity", "did not fit the pace: " + ", ".join(overflow)))

    musts = {p.name for p in brief.places if p.must}
    missing_musts = musts - {s.place for s in stops}
    if missing_musts:
        issues.append(
            Issue(
                "error", "must_see", "must-see places dropped: " + ", ".join(sorted(missing_musts))
            )
        )

    long_legs = [
        f"day {s.day}: {s.place} ({s.km_from_prev} km)"
        for s in stops
        if s.km_from_prev > MAX_LEG_KM
    ]
    if long_legs:
        issues.append(Issue("warn", "long_leg", "; ".join(long_legs)))

    missing_legs = [c.item for c in costs if c.basis.startswith("MISSING")]
    if missing_legs:
        issues.append(Issue("warn", "cost_gap", "no price for: " + ", ".join(missing_legs)))

    total = sum(c.amount_inr for c in costs)
    if brief.budget_inr and total > brief.budget_inr:
        over = total - brief.budget_inr
        issues.append(
            Issue("warn", "budget", f"estimate ₹{total:,.0f} is ₹{over:,.0f} over budget")
        )
    return issues
