#!/usr/bin/env python3
from __future__ import annotations
import datetime as dt
import html
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parent
CFG = ROOT / "config.yaml"
OUT = ROOT / "output"

def esc(s):
    return str(s).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")

def ics_dt(s):
    d = dt.datetime.fromisoformat(s)
    return d.astimezone(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")

def event(uid, title, start, end=None, description="", location=""):
    lines = [
        "BEGIN:VEVENT",
        f"UID:{uid}@tgt",
        f"DTSTAMP:{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        f"DTSTART:{ics_dt(start)}",
    ]
    if end:
        lines.append(f"DTEND:{ics_dt(end)}")
    lines += [
        f"SUMMARY:{esc(title)}",
        f"LOCATION:{esc(location)}",
        f"DESCRIPTION:{esc(description)}",
        "END:VEVENT",
    ]
    return lines

def main():
    if not CFG.exists():
        raise SystemExit("Copy config.example.yaml to config.yaml first. Keep config.yaml private.")

    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    OUT.mkdir(exist_ok=True)
    trip = cfg["trip"]
    travellers = int(trip.get("travellers", 1))

    rows = []
    total = 0.0
    cal = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "PRODID:-//TGT Control Centre//EN",
        f"X-WR-CALNAME:{esc(trip['name'])}",
    ]

    for i, b in enumerate(cfg.get("bookings", []), 1):
        cost = float(b.get("total_cost") or 0)
        total += cost
        rows.append((b.get("start", "")[:10], b["title"], b.get("category", "Booking"), cost, b.get("currency", trip.get("base_currency", "EUR"))))
        desc = f"{b.get('category','Booking')}\nCost: {cost:,.0f} {b.get('currency','')}\n{b.get('notes','')}\n{b.get('url','')}"
        cal += event(f"booking-{i}", b["title"], b["start"], b.get("end"), desc, b.get("location", ""))
        if b.get("refundable_until"):
            cal += event(
                f"cancel-{i}",
                "Cancellation deadline · " + b["title"],
                b["refundable_until"],
                description="Last stated refundable/cancellation deadline.",
            )

    for i, t in enumerate(cfg.get("transport", []), 1):
        cost = float(t.get("total_cost") or 0)
        total += cost
        rows.append((t.get("start", "")[:10], t["title"], "Transport", cost, t.get("currency", trip.get("base_currency", "EUR"))))
        cal += event(
            f"transport-{i}",
            t["title"],
            t["start"],
            t.get("end"),
            f"Cost: {cost:,.0f} {t.get('currency','')}\n{t.get('notes','')}",
        )

    cal.append("END:VCALENDAR")
    (OUT / "tgt.ics").write_text("\r\n".join(cal) + "\r\n", encoding="utf-8")

    per_person = total / travellers if travellers else total
    md = [
        f"# {trip['name']}",
        "",
        trip.get("subtitle", ""),
        "",
        f"**Dates:** {trip['start_date']} → {trip['end_date']}",
        "",
        f"**Travellers:** {travellers}",
        "",
        f"**Tracked total:** {total:,.0f} {trip.get('base_currency','EUR')}",
        "",
        f"**Approx. per person:** {per_person:,.0f} {trip.get('base_currency','EUR')}",
        "",
        "## Bookings",
        "",
    ]
    for d, title, cat, cost, curr in sorted(rows):
        md.append(f"- **{d}** · {title} · {cat} · {cost:,.0f} {curr}")
    (OUT / "summary.md").write_text("\n".join(md), encoding="utf-8")

    stop_cards = []
    for s in cfg.get("stops", []):
        stop_cards.append(
            "<article><h2>" + html.escape(s["city"]) + "</h2><div>" +
            html.escape(s.get("accommodation", "")) + "</div><small>" +
            html.escape(s["arrive"][:10]) + " → " + html.escape(s["depart"][:10]) +
            "</small><p>" + html.escape(s.get("notes", "")) + "</p></article>"
        )

    page = (
        "<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width'>"
        "<title>" + html.escape(trip["name"]) + "</title><style>"
        "body{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;max-width:900px;margin:40px auto;padding:0 18px;background:#f4f5f7;color:#17191c}"
        "header{margin-bottom:30px}article{background:#fff;border-radius:14px;padding:18px;margin:12px 0;box-shadow:0 1px 5px #0001}"
        "h1{font-size:36px;margin-bottom:4px}small{color:#777}.metric{display:inline-block;background:#fff;border-radius:12px;padding:12px 16px;margin:5px 8px 5px 0}"
        "</style></head><body><header><h1>" + html.escape(trip["name"]) + "</h1><div>" +
        html.escape(trip.get("subtitle", "")) + "</div><div class='metric'>Total " +
        f"{total:,.0f} {trip.get('base_currency','EUR')}" + "</div><div class='metric'>≈ " +
        f"{per_person:,.0f} pp</div></header>" + "".join(stop_cards) + "</body></html>"
    )
    (OUT / "index.html").write_text(page, encoding="utf-8")
    print(f"Built {trip['name']} control centre")

if __name__ == "__main__":
    main()
