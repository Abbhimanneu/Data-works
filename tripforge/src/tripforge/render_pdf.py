"""Dark-theme PDF: summary, route chart, day-by-day plan, costs, checks, assumptions."""

from collections import defaultdict
from io import BytesIO
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.enums import TA_LEFT  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle  # noqa: E402
from reportlab.lib.units import mm  # noqa: E402
from reportlab.pdfbase import pdfmetrics  # noqa: E402
from reportlab.pdfbase.ttfonts import TTFont  # noqa: E402
from reportlab.platypus import (  # noqa: E402
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from tripforge.checks import Issue  # noqa: E402
from tripforge.models import CostLine, Stop, TripBrief  # noqa: E402
from tripforge.plan import city_days  # noqa: E402

BG, PANEL, LINE = colors.HexColor("#0d1117"), colors.HexColor("#161b22"), colors.HexColor("#30363d")
TEXT, MUTED = colors.HexColor("#e6edf3"), colors.HexColor("#8b949e")
WARN, BAD = colors.HexColor("#d29922"), colors.HexColor("#f85149")
CITY_COLORS = ["#58a6ff", "#3fb950", "#d29922", "#f778ba", "#a371f7", "#39c5cf", "#ff7b72"]


def _font() -> str:
    # DejaVu has the ₹ glyph; Helvetica does not
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/Library/Fonts/DejaVuSans.ttf",
        str(Path(matplotlib.get_data_path()) / "fonts/ttf/DejaVuSans.ttf"),
    ):
        if Path(path).exists():
            pdfmetrics.registerFont(TTFont("DejaVu", path))
            bold = path.replace("DejaVuSans.ttf", "DejaVuSans-Bold.ttf")
            if Path(bold).exists():
                pdfmetrics.registerFont(TTFont("DejaVu-Bold", bold))
                return "DejaVu"
    return "Helvetica"


FONT = _font()
BOLD = "DejaVu-Bold" if FONT == "DejaVu" else "Helvetica-Bold"
S = {
    "h1": ParagraphStyle("h1", fontName=BOLD, fontSize=20, leading=24, textColor=TEXT),
    "h2": ParagraphStyle(
        "h2", fontName=BOLD, fontSize=13, leading=17, textColor=TEXT, spaceBefore=10, spaceAfter=6
    ),
    "p": ParagraphStyle(
        "p", fontName=FONT, fontSize=9.5, leading=13, textColor=TEXT, alignment=TA_LEFT
    ),
    "muted": ParagraphStyle("m", fontName=FONT, fontSize=8.5, leading=11, textColor=MUTED),
    "cell": ParagraphStyle("c", fontName=FONT, fontSize=8.5, leading=10.5, textColor=TEXT),
}


def inr(x: float) -> str:
    s = f"{abs(round(x)):d}"
    if len(s) > 3:  # Indian grouping: 12,34,567
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts) + "," + tail
    return ("-" if x < 0 else "") + "₹" + s


def _bg(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(BG)
    canvas.rect(0, 0, A4[0], A4[1], fill=1, stroke=0)
    canvas.setFont(FONT, 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(
        15 * mm,
        8 * mm,
        "tripforge · estimates, verify before booking · map data © OpenStreetMap contributors",
    )
    canvas.drawRightString(A4[0] - 15 * mm, 8 * mm, f"{doc.page}")
    canvas.restoreState()


def _table(rows, widths, header=True, zebra=True):
    t = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
    style = [
        ("FONT", (0, 0), (-1, -1), FONT, 8.5),
        ("TEXTCOLOR", (0, 0), (-1, -1), TEXT),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    if header:
        style += [
            ("BACKGROUND", (0, 0), (-1, 0), PANEL),
            ("FONT", (0, 0), (-1, 0), BOLD, 8.5),
            ("TEXTCOLOR", (0, 0), (-1, 0), MUTED),
        ]
    if zebra:
        for r in range(1 if header else 0, len(rows)):
            if r % 2 == 0:
                style.append(("BACKGROUND", (0, r), (-1, r), PANEL))
    t.setStyle(TableStyle(style))
    return t


def _route_png(stops: list[Stop]) -> BytesIO:
    fig, ax = plt.subplots(figsize=(6.2, 6.6), dpi=160)
    fig.patch.set_facecolor("#0d1117")
    ax.set_facecolor("#0d1117")
    cities = list(dict.fromkeys(s.city for s in stops))
    ax.plot([s.lon for s in stops], [s.lat for s in stops], color="#30363d", lw=1, zorder=1)
    for i, c in enumerate(cities):
        cs = [s for s in stops if s.city == c]
        col = CITY_COLORS[i % len(CITY_COLORS)]
        ax.scatter([s.lon for s in cs], [s.lat for s in cs], s=28, color=col, zorder=2, label=c)
        ax.annotate(
            c,
            (sum(s.lon for s in cs) / len(cs), sum(s.lat for s in cs) / len(cs)),
            xytext=(10, 0),
            textcoords="offset points",
            color="#e6edf3",
            fontsize=9,
            fontweight="bold",
        )
    ax.set_aspect("equal", adjustable="datalim")
    for side in ax.spines.values():
        side.set_color("#30363d")
    ax.tick_params(colors="#8b949e", labelsize=7)
    ax.set_xlabel("longitude", color="#8b949e", fontsize=7)
    ax.set_ylabel("latitude", color="#8b949e", fontsize=7)
    ax.grid(color="#21262d", lw=0.5)
    buf = BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png", facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf


def render(
    brief: TripBrief,
    stops: list[Stop],
    costs: list[CostLine],
    issues: list[Issue],
    out: Path,
    title: str,
    notes: str,
    map_name: str,
) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(out),
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        title=title,
        author="tripforge",
    )
    W = A4[0] - 30 * mm
    total = sum(c.amount_inr for c in costs)
    per_head = total / brief.travelers
    el = []

    el.append(Paragraph(title, S["h1"]))
    first = stops[0].date if stops and stops[0].date else None
    when = f"{first:%d %b %Y} · " if first else ""
    el.append(
        Paragraph(
            f"{when}{brief.days} days · {brief.travelers} traveller(s) · "
            f"{brief.tier} tier · {brief.pace} pace",
            S["muted"],
        )
    )
    el.append(Spacer(1, 8))

    budget_txt = inr(brief.budget_inr) if brief.budget_inr else "not set"
    status, status_hex = "within budget", "#3fb950"
    if brief.budget_inr and total > brief.budget_inr:
        status, status_hex = f"{inr(total - brief.budget_inr)} over", "#f85149"
    kpi = [
        [
            Paragraph("<b>Estimated total</b>", S["muted"]),
            Paragraph("<b>Per person</b>", S["muted"]),
            Paragraph("<b>Budget</b>", S["muted"]),
            Paragraph("<b>Checks</b>", S["muted"]),
        ],
        [
            Paragraph(f"<font size=13>{inr(total)}</font>", S["p"]),
            Paragraph(f"<font size=13>{inr(per_head)}</font>", S["p"]),
            Paragraph(
                f"<font size=13>{budget_txt}</font><br/>"
                f"<font color='{status_hex}'>"
                f"{status if brief.budget_inr else ''}</font>",
                S["p"],
            ),
            Paragraph(
                f"<font size=13>{sum(i.severity == 'error' for i in issues)} errors · "
                f"{sum(i.severity == 'warn' for i in issues)} warnings</font>",
                S["p"],
            ),
        ],
    ]
    kt = Table(kpi, colWidths=[W / 4] * 4)
    kt.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), PANEL),
                ("BOX", (0, 0), (-1, -1), 0.6, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, LINE),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    el.append(kt)
    el.append(Spacer(1, 10))

    route = " → ".join(f"{c.name} ({c.nights}n)" for c in brief.cities)
    el.append(Paragraph(f"<b>Route:</b> {route}", S["p"]))
    if brief.interests:
        el.append(Paragraph(f"<b>Interests:</b> {', '.join(brief.interests)}", S["p"]))
    el.append(
        Paragraph(
            f"Interactive map with every stop: <b>{map_name}</b> (open in a browser)", S["muted"]
        )
    )
    el.append(Spacer(1, 6))
    if stops:
        el.append(Image(_route_png(stops), width=W * 0.72, height=W * 0.72 * 6.6 / 6.2))
    el.append(PageBreak())

    el.append(Paragraph("Day by day", S["h2"]))
    by_day = defaultdict(list)
    for s in stops:
        by_day[s.day].append(s)
    day_cost = defaultdict(float)
    for c in costs:
        if c.day:
            day_cost[c.day] += c.amount_inr
    for day in range(1, brief.days + 1):
        ds = by_day.get(day, [])
        city = (
            ds[0].city if ds else next((c for c, f, n in city_days(brief) if f <= day < f + n), "")
        )
        date_txt = f" · {ds[0].date:%a %d %b}" if ds and ds[0].date else ""
        head = Paragraph(
            f"<b>Day {day} · {city}</b>{date_txt}"
            f"<font color='#8b949e'>   ~{inr(day_cost[day])}</font>",
            S["p"],
        )
        rows = [["#", "Place", "Type", "Hours", "Km from prev"]]
        rows += [
            [
                str(s.seq),
                Paragraph(s.place, S["cell"]),
                s.kind,
                f"{s.hours:g}",
                f"{s.km_from_prev:g}" if s.seq > 1 else "-",
            ]
            for s in ds
        ]
        if not ds:
            rows.append(["", Paragraph("Free / travel day", S["cell"]), "", "", ""])
        el.append(
            KeepTogether(
                [
                    head,
                    Spacer(1, 3),
                    _table(
                        rows,
                        [
                            8 * mm,
                            W - 8 * mm - 26 * mm - 16 * mm - 26 * mm,
                            26 * mm,
                            16 * mm,
                            26 * mm,
                        ],
                    ),
                    Spacer(1, 8),
                ]
            )
        )

    el.append(PageBreak())
    el.append(Paragraph("Costs", S["h2"]))
    by_cat = defaultdict(float)
    for c in costs:
        by_cat[c.category] += c.amount_inr
    rows = [["Category", "Amount", "Share"]]
    rows += [
        [k, inr(v), f"{v / total:.0%}" if total else "-"]
        for k, v in sorted(by_cat.items(), key=lambda kv: -kv[1])
    ]
    rows.append(
        [Paragraph("<b>Total</b>", S["cell"]), Paragraph(f"<b>{inr(total)}</b>", S["cell"]), "100%"]
    )
    el.append(_table(rows, [W * 0.5, W * 0.3, W * 0.2]))
    el.append(Spacer(1, 10))
    el.append(Paragraph("Line items", S["h2"]))
    rows = [["Day", "Category", "Item", "Amount", "Basis"]]
    rows += [
        [
            str(c.day or "-"),
            c.category,
            Paragraph(c.item, S["cell"]),
            inr(c.amount_inr),
            Paragraph(c.basis, S["cell"]),
        ]
        for c in costs
    ]
    el.append(_table(rows, [11 * mm, 30 * mm, 50 * mm, 24 * mm, W - 115 * mm]))

    el.append(PageBreak())
    el.append(Paragraph("Checks", S["h2"]))
    if issues:
        rows = [["Severity", "Check", "Detail"]]
        rows += [[i.severity.upper(), i.check, Paragraph(i.detail, S["cell"])] for i in issues]
        t = _table(rows, [22 * mm, 26 * mm, W - 48 * mm])
        for r, i in enumerate(issues, start=1):
            t.setStyle(
                TableStyle([("TEXTCOLOR", (0, r), (0, r), BAD if i.severity == "error" else WARN)])
            )
        el.append(t)
    else:
        el.append(Paragraph("All checks passed.", S["p"]))

    el.append(Paragraph("Assumptions", S["h2"]))
    for line in [
        "Costs come from config/costs/<country>.yaml; every line shows its basis.",
        "Currency converted at the rate and date in that file. Card and ATM fees not included.",
        "Distances are straight-line between stops, not road distance.",
        "Places and city order come from an LLM reading your notes, then checked by code.",
        "Locations from OpenStreetMap Nominatim, cached locally.",
    ]:
        el.append(Paragraph("• " + line, S["p"]))
    el.append(Paragraph("Your notes", S["h2"]))
    el.append(Paragraph(notes.strip().replace("\n", "<br/>"), S["muted"]))

    doc.build(el, onFirstPage=_bg, onLaterPages=_bg)
    return out
