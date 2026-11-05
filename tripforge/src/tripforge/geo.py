import csv
import math
import time
from pathlib import Path

import httpx

from tripforge.models import GeoPoint

NOMINATIM = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "tripforge/0.1 (+https://github.com/Abbhimanneu/Data-works)"
MIN_INTERVAL = 1.1  # public Nominatim policy: max 1 request/second


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def load_seed(con, path: Path) -> int:
    if not path.exists():
        return 0
    with open(path, encoding="utf-8") as f:
        rows = [
            (r["query"], float(r["lat"]), float(r["lon"]), r["display_name"], "seed")
            for r in csv.DictReader(f)
        ]
    con.executemany(
        """insert into geocode_cache (query, lat, lon, display_name, source)
           values (?, ?, ?, ?, ?) on conflict do nothing""",
        rows,
    )
    return len(rows)


class Geocoder:
    def __init__(
        self, con, offline: bool = False, fetch=None, sleep=time.sleep, clock=time.monotonic
    ):
        self.con, self.offline = con, offline
        self.fetch = fetch or self._nominatim
        self.sleep, self.clock = sleep, clock
        self._last = float("-inf")
        self.calls = 0

    def _nominatim(self, q: str) -> list[dict]:
        r = httpx.get(
            NOMINATIM,
            params={"q": q, "format": "jsonv2", "limit": 1},
            headers={"User-Agent": USER_AGENT},
            timeout=15,
        )
        r.raise_for_status()
        return r.json()

    def _throttle(self) -> None:
        wait = MIN_INTERVAL - (self.clock() - self._last)
        if wait > 0:
            self.sleep(wait)
        self._last = self.clock()

    def lookup(self, place: str, city: str, country: str) -> GeoPoint | None:
        q = f"{place}, {city}, {country}"
        row = self.con.execute(
            "select lat, lon, display_name, source from geocode_cache where query = ?", [q]
        ).fetchone()
        if row:
            if row[3] == "miss":
                return None
            return GeoPoint(query=q, lat=row[0], lon=row[1], display_name=row[2], source=row[3])
        if self.offline:
            return None

        self._throttle()
        self.calls += 1
        try:
            hits = self.fetch(q)
        except httpx.HTTPError:
            return None  # network trouble is not cached as a miss
        if not hits:
            self.con.execute(
                "insert into geocode_cache (query, source) values (?, 'miss') "
                "on conflict do nothing",
                [q],
            )
            return None
        h = hits[0]
        self.con.execute(
            """insert into geocode_cache (query, lat, lon, display_name, source)
               values (?, ?, ?, ?, 'nominatim') on conflict do nothing""",
            [q, float(h["lat"]), float(h["lon"]), h.get("display_name", "")],
        )
        return GeoPoint(
            query=q,
            lat=float(h["lat"]),
            lon=float(h["lon"]),
            display_name=h.get("display_name", ""),
            source="nominatim",
        )
