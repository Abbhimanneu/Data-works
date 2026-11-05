import argparse
import json
import os
import sys
import uuid
from datetime import date
from pathlib import Path

from tripforge import checks, costs, extract, geo, plan, render_map, render_pdf, store

ROOT = Path(__file__).resolve().parents[2]
CONFIG = Path(os.getenv("TRIPFORGE_CONFIG", ROOT / "config"))
DB = Path(os.getenv("TRIPFORGE_DB", ROOT / "data" / "tripforge.duckdb"))
MODEL = os.getenv("TRIPFORGE_MODEL", "qwen3:8b")


def _cached_llm(path: Path):
    def call(_notes: str) -> str:
        return path.read_text(encoding="utf-8")

    return call


def main() -> None:
    p = argparse.ArgumentParser(prog="tripforge", description="notes -> itinerary, map, PDF")
    p.add_argument("notes", type=Path, help="markdown/text file with your rough trip notes")
    p.add_argument("--days", type=int)
    p.add_argument("--travelers", type=int)
    p.add_argument("--budget", type=int, help="total budget in INR")
    p.add_argument("--tier", choices=["budget", "mid", "comfort"])
    p.add_argument("--pace", choices=["slow", "normal", "fast"])
    p.add_argument("--start", type=date.fromisoformat, help="YYYY-MM-DD")
    p.add_argument("--out", type=Path, help="output folder, default out/<notes name>")
    p.add_argument("--brief", type=Path, help="use this brief JSON instead of calling the LLM")
    p.add_argument("--seed", type=Path, help="CSV of known coordinates to preload")
    p.add_argument("--offline", action="store_true", help="no network: cache and seed only")
    p.add_argument("--refresh", action="store_true", help="ignore the cached LLM extraction")
    a = p.parse_args()

    notes = a.notes.read_text(encoding="utf-8")
    name = a.notes.stem
    out = a.out or ROOT / "out" / name
    con = store.connect(DB)
    overrides = {
        "days": a.days,
        "travelers": a.travelers,
        "budget_inr": a.budget,
        "tier": a.tier,
        "pace": a.pace,
    }

    llm = _cached_llm(a.brief) if a.brief else None
    brief, cached = extract.extract(con, notes, overrides, MODEL, llm=llm, refresh=a.refresh)
    print(
        f"brief: {brief.country}, {brief.days} days, {len(brief.cities)} cities, "
        f"{len(brief.places)} places "
        f"({'cache' if cached else 'brief file' if a.brief else 'llm ' + MODEL})"
    )

    if a.seed:
        print(f"seed: {geo.load_seed(con, a.seed)} coordinates")
    g = geo.Geocoder(con, offline=a.offline)
    coords, unresolved = {}, []
    for pl in brief.places:
        hit = g.lookup(pl.name, pl.city, brief.country)
        if hit:
            coords[pl.name] = (hit.lat, hit.lon)
        else:
            unresolved.append(pl.name)
    print(f"geocode: {len(coords)} found, {len(unresolved)} missing, {g.calls} API calls")

    stops, overflow = plan.build(brief, coords, a.start)
    cfg = costs.load(CONFIG, brief.country)
    lines = costs.estimate(brief, stops, cfg)
    issues = checks.run(brief, unresolved, overflow, stops, lines)
    for i in issues:
        print(f"  {i.severity:5} {i.check}: {i.detail}")
    if any(i.severity == "error" for i in issues):
        sys.exit("errors above: fix the notes or add coordinates to the seed, then rerun")

    run_id = uuid.uuid4().hex[:12]
    total = sum(c.amount_inr for c in lines)
    con.execute(
        "insert into runs values (?, ?, ?, ?, ?, ?, now())",
        [run_id, name, extract.input_hash(notes, overrides), brief.days, total, len(issues)],
    )
    con.executemany(
        "insert into itinerary_stops values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                run_id,
                s.day,
                s.date,
                s.city,
                s.seq,
                s.place,
                s.kind,
                s.hours,
                s.lat,
                s.lon,
                s.km_from_prev,
            )
            for s in stops
        ],
    )
    con.executemany(
        "insert into cost_lines values (?, ?, ?, ?, ?, ?)",
        [(run_id, c.day, c.category, c.item, c.amount_inr, c.basis) for c in lines],
    )

    title = f"{brief.country}: {brief.days}-day plan"
    out.mkdir(parents=True, exist_ok=True)
    map_path = render_map.render(stops, out / "map.html", title)
    pdf_path = render_pdf.render(
        brief, stops, lines, issues, out / "itinerary.pdf", title, notes, map_path.name
    )
    (out / "itinerary.json").write_text(
        json.dumps(
            {
                "brief": brief.model_dump(mode="json"),
                "stops": [s.model_dump(mode="json") for s in stops],
                "costs": [c.model_dump() for c in lines],
                "issues": [i.__dict__ for i in issues],
                "total_inr": total,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"total ≈ ₹{total:,.0f} ({brief.travelers} pax)\n{pdf_path}\n{map_path}")


if __name__ == "__main__":
    main()
