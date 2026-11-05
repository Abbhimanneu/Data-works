"""Raw notes -> TripBrief. The LLM is called once per (notes, model); the result is cached."""

import hashlib
import json
from collections.abc import Callable

from tripforge.models import TripBrief

SYSTEM = """You turn rough travel notes into a structured trip brief.
Rules:
- Use only places and cities the notes mention or clearly imply. Do not invent restaurants.
- cities: in travel order, with nights per city. Sum of nights should equal days - 1.
- arrive_by: how the traveller reaches that city from the previous one (first city: "flight").
- places: concrete, geocodable names ("Temple of Literature", not "a temple"), each with its city.
- hours: realistic time on site. must=true only if the notes stress it.
- Numbers in the notes (days, budget in INR, travellers) override defaults.
Return JSON matching the schema."""


def input_hash(notes: str, overrides: dict) -> str:
    payload = notes.strip() + "\n" + json.dumps(overrides, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def ollama_llm(model: str) -> Callable[[str], str]:
    from ollama import Client

    def call(notes: str) -> str:
        resp = Client().chat(
            model=model,
            messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": notes}],
            format=TripBrief.model_json_schema(),
            options={"temperature": 0},
            think=False,
        )
        return resp.message.content

    return call


def extract(
    con,
    notes: str,
    overrides: dict,
    model: str,
    llm: Callable[[str], str] | None = None,
    refresh: bool = False,
) -> tuple[TripBrief, bool]:
    """Returns (brief, from_cache)."""
    h = input_hash(notes, overrides)
    if not refresh:
        row = con.execute(
            "select brief_json from extractions where input_hash = ? and model = ?", [h, model]
        ).fetchone()
        if row:
            return TripBrief.model_validate_json(row[0]), True

    raw = (llm or ollama_llm(model))(notes)
    data = json.loads(raw)
    data.update({k: v for k, v in overrides.items() if v is not None})
    brief = TripBrief.model_validate(data)
    con.execute(
        """insert into extractions (input_hash, model, brief_json) values (?, ?, ?)
           on conflict do update set brief_json = excluded.brief_json, created_at = now()""",
        [h, model, brief.model_dump_json()],
    )
    return brief, False
