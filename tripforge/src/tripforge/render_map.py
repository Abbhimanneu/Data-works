from pathlib import Path

import folium

from tripforge.models import Stop

PALETTE = [
    "#58a6ff",
    "#3fb950",
    "#d29922",
    "#f778ba",
    "#a371f7",
    "#ff7b72",
    "#39c5cf",
    "#e3b341",
    "#7ee787",
    "#ffa657",
]


def render(stops: list[Stop], out: Path, title: str) -> Path:
    if not stops:
        raise ValueError("nothing to map")
    lat = sum(s.lat for s in stops) / len(stops)
    lon = sum(s.lon for s in stops) / len(stops)
    m = folium.Map(location=[lat, lon], zoom_start=6, tiles="OpenStreetMap", control_scale=True)
    # dark mode without a paid tile key: invert the OSM tiles, keep markers untouched
    css = (
        ".leaflet-tile-pane{filter:invert(1) hue-rotate(180deg) brightness(.95) contrast(.9)}"
        ".leaflet-container{background:#0d1117}"
    )
    m.get_root().header.add_child(folium.Element(f"<title>{title}</title><style>{css}</style>"))

    for day in sorted({s.day for s in stops}):
        day_stops = [s for s in stops if s.day == day]
        color = PALETTE[(day - 1) % len(PALETTE)]
        label = f"Day {day} · {day_stops[0].city}"
        if day_stops[0].date:
            label += f" · {day_stops[0].date:%a %d %b}"
        layer = folium.FeatureGroup(name=label)
        if len(day_stops) > 1:
            folium.PolyLine(
                [(s.lat, s.lon) for s in day_stops], color=color, weight=3, opacity=0.8
            ).add_to(layer)
        for s in day_stops:
            folium.CircleMarker(
                (s.lat, s.lon),
                radius=7,
                color=color,
                fill=True,
                fill_opacity=0.9,
                tooltip=f"D{s.day}.{s.seq} {s.place}",
                popup=folium.Popup(
                    f"<b>Day {s.day}, stop {s.seq}</b><br>{s.place}<br>{s.kind} · {s.hours:g} h",
                    max_width=220,
                ),
            ).add_to(layer)
        layer.add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)
    m.fit_bounds(
        [
            [min(s.lat for s in stops), min(s.lon for s in stops)],
            [max(s.lat for s in stops), max(s.lon for s in stops)],
        ]
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    m.save(str(out))
    return out
