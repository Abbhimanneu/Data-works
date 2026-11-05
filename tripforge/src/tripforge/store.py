from pathlib import Path

import duckdb

DDL = """
create table if not exists extractions (
    input_hash  varchar,
    model       varchar,
    brief_json  json not null,
    created_at  timestamp default now(),
    primary key (input_hash, model)
);
create table if not exists geocode_cache (
    query         varchar primary key,
    lat           double,
    lon           double,
    display_name  varchar,
    source        varchar not null,   -- nominatim | seed | miss
    fetched_at    timestamp default now()
);
create table if not exists runs (
    run_id      varchar primary key,
    trip        varchar,
    input_hash  varchar,
    days        integer,
    total_inr   double,
    warnings    integer,
    created_at  timestamp default now()
);
create table if not exists itinerary_stops (
    run_id varchar, day integer, date date, city varchar, seq integer, place varchar,
    kind varchar, hours double, lat double, lon double, km_from_prev double
);
create table if not exists cost_lines (
    run_id varchar, day integer, category varchar, item varchar, amount_inr double, basis varchar
);
"""


def connect(path: Path) -> duckdb.DuckDBPyConnection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path))
    con.execute(DDL)
    return con
