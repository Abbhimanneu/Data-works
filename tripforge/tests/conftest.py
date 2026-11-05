import json
from pathlib import Path

import pytest

from tripforge import store
from tripforge.models import TripBrief

EX = Path(__file__).resolve().parents[1] / "examples" / "vietnam"


@pytest.fixture
def con(tmp_path):
    return store.connect(tmp_path / "t.duckdb")


@pytest.fixture
def brief() -> TripBrief:
    return TripBrief.model_validate(json.loads((EX / "brief.json").read_text()))


@pytest.fixture
def coords():
    import csv

    with open(EX / "geocode_seed.csv", encoding="utf-8") as f:
        return {
            r["query"].split(",")[0]: (float(r["lat"]), float(r["lon"])) for r in csv.DictReader(f)
        }
