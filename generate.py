#!/usr/bin/env python3
"""Build one Apple-Calendar-compatible .ics feed from several public empty-leg sources.

Sources are deliberately independent: if one website changes or is unavailable, the
other sources still produce a valid feed. No login credentials are required.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import html
import os
import re
import sys
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import urljoin

import requests
import yaml
from bs4 import BeautifulSoup
from dateutil import parser as dateparser
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config.yaml"
OUTPUT = ROOT / "docs" / "empty-legs.ics"
UA = "Mozilla/5.0 (compatible; EmptyLegCalendar/1.0; +https://github.com/)"
TODAY = dt.datetime.now(dt.timezone.utc).date()

EU_COUNTRIES = {
    "AL","AD","AT","BY","BE","BA","BG","HR","CY","CZ","DK","EE","FI","FR","DE","GR","HU","IS","IE","IT",
    "LV","LI","LT","LU","MT","MD","MC","ME","NL","MK","NO","PL","PT","RO","SM","RS","SK","SI","ES","SE",
    "CH","UA","GB","VA"
}

MONTHS = {m.lower(): i for i, m in enumerate([
    "January","February","March","April","May","June","July","August","September","October","November","December"
], 1)}

JETFLY_TZ = {
    "bournemouth":"Europe/London", "london":"Europe/London", "farnborough":"Europe/London", "biggin hill":"Europe/London",
    "oxford":"Europe/London", "manchester":"Europe/London", "birmingham":"Europe/London",
    "geneva":"Europe/Zurich", "lausanne":"Europe/Zurich", "payerne":"Europe/Zurich", "sion":"Europe/Zurich",
    "saanen":"Europe/Zurich", "zurich":"Europe/Zurich", "bern":"Europe/Zurich", "lugano":"Europe/Zurich",
    "paris":"Europe/Paris", "le touquet":"Europe/Paris", "annemasse":"Europe/Paris", "laval":"Europe/Paris",
    "gray":"Europe/Paris", "cannes":"Europe/Paris", "nice":"Europe/Paris",
    "stuttgart":"Europe/Berlin", "munich":"Europe/Berlin", "frankfurt":"Europe/Berlin", "berlin":"Europe/Berlin",
    "vienna":"Europe/Vienna", "salzburg":"Europe/Vienna", "innsbruck":"Europe/Vienna",
    "luxembourg":"Europe/Luxembourg", "amsterdam":"Europe/Amsterdam", "antwerp":"Europe/Brussels", "brussels":"Europe/Brussels",
    "naples":"Europe/Rome", "grosseto":"Europe/Rome", "milan":"Europe/Rome", "rome":"Europe/Rome", "olbia":"Europe/Rome",
    "bolzano":"Europe/Rome", "venice":"Europe/Rome",
}

@dataclasses.dataclass
class Leg:
    source: str
    origin: str
    destination: str
    start: dt.date | dt.datetime
    end: dt.date | dt.datetime
    origin_name: str = ""
    destination_name: str = ""
    aircraft: str = ""
    pax: Optional[int] = None
    price: Optional[float] = None
    currency: str = ""
    booking_url: str = ""
    description: str = ""
    source_uid: str = ""
    country_from: str = ""
    country_to: str = ""
    exact_time: bool = False

    @property
    def date(self) -> dt.date:
        return self.start.date() if isinstance(self.start, dt.datetime) else self.start

    def key(self) -> tuple:
        return (
            self.origin.upper(), self.destination.upper(), self.date.isoformat(),
            re.sub(r"\W+", "", self.aircraft.lower())[:30]
        )

    def uid(self) -> str:
        if self.source_uid:
            return self.source_uid
        raw = "|".join(map(str, (self.source, *self.key())))
        return hashlib.sha1(raw.encode()).hexdigest() + "@emptylegs.local"


def get(url: str, timeout: int = 30) -> requests.Response:
    r = requests.get(url, timeout=timeout, headers={"User-Agent": UA, "Accept-Language": "en-GB,en;q=0.9"})
    r.raise_for_status()
    return r


def unfold_ics(text: str) -> list[str]:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out: list[str] = []
    for line in lines:
        if line.startswith((" ", "\t")) and out:
            out[-1] += line[1:]
        else:
            out.append(line)
    return out


def ics_value(lines: list[str], name: str) -> str:
    for line in lines:
        if line.startswith(name + ":") or line.startswith(name + ";"):
            return line.split(":", 1)[1]
    return ""


def parse_ics_dt(value: str) -> dt.datetime | dt.date:
    if re.fullmatch(r"\d{8}", value):
        return dt.datetime.strptime(value, "%Y%m%d").date()
    if value.endswith("Z"):
        return dt.datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=dt.timezone.utc)
    return dt.datetime.strptime(value[:15], "%Y%m%dT%H%M%S")


def source_globeair(cfg: dict) -> list[Leg]:
    text = get(cfg["url"]).text
    lines = unfold_ics(text)
    events, cur = [], None
    for line in lines:
        if line == "BEGIN:VEVENT": cur = []
        elif line == "END:VEVENT" and cur is not None:
            try:
                summary = ics_value(cur, "SUMMARY")
                m = re.search(r"(?:\[\d+%\]\s*)?(.+?)\s*\(([A-Z]{3,4})\)\s*>\s*(.+?)\s*\(([A-Z]{3,4})\)", summary)
                if not m: cur = None; continue
                desc = ics_value(cur, "DESCRIPTION").replace("\\n", "\n")
                price_m = re.search(r"Current price:\s*€\s*([\d,.]+)", desc)
                ac_m = re.search(r"Aircraft:\s*([^,\n]+)", desc)
                pax_m = re.search(r"max\.\s*(\d+)\s*pax", desc, re.I)
                url_m = re.search(r"https://fly\.globeair\.com/el/[A-Za-z0-9]+", desc)
                start = parse_ics_dt(ics_value(cur, "DTSTART"))
                end = parse_ics_dt(ics_value(cur, "DTEND"))
                events.append(Leg(
                    source="GlobeAir", origin=m.group(2), destination=m.group(4),
                    origin_name=m.group(1).strip(), destination_name=m.group(3).strip(),
                    start=start, end=end, aircraft=ac_m.group(1).strip() if ac_m else "Citation Mustang",
                    pax=int(pax_m.group(1)) if pax_m else 4,
                    price=float(price_m.group(1).replace(",", "")) if price_m else None,
                    currency="EUR" if price_m else "", booking_url=url_m.group(0) if url_m else cfg["url"],
                    description=desc, source_uid=ics_value(cur, "UID"), exact_time=isinstance(start, dt.datetime)
                ))
            except Exception as e:
                print(f"GlobeAir event skipped: {e}", file=sys.stderr)
            cur = None
        elif cur is not None:
            cur.append(line)
    return events


def source_jetfly(cfg: dict) -> list[Leg]:
    text = BeautifulSoup(get(cfg["url"]).text, "html.parser").get_text(" ", strip=True)
    date_pat = re.compile(r"\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(20\d{2})\b")
    matches = list(date_pat.finditer(text))
    out: list[Leg] = []
    block_pat = re.compile(
        r"\b(PC-12|PC-24)\b\s+(\d{1,2}:\d{2})\s+(.+?)\s+(\d{1,2}:\d{2})\s+(.+?)(?=(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b|\bPC-(?:12|24)\b|$)",
        re.I
    )
    for i, dm in enumerate(matches):
        day, month, year = int(dm.group(1)), MONTHS[dm.group(2).lower()], int(dm.group(3))
        d = dt.date(year, month, day)
        segment = text[dm.end() : matches[i+1].start() if i+1 < len(matches) else len(text)]
        for m in block_pat.finditer(segment):
            aircraft, dep_s, origin, arr_s, dest = m.groups()
            origin = re.sub(r"\s+", " ", origin).strip(" -–,")
            dest = re.sub(r"\s+", " ", dest).strip(" -–,")
            dest = re.split(r"\s+(?:Sunday|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday)\b", dest)[0].strip()
            tzname = JETFLY_TZ.get(origin.lower(), "Europe/Zurich")
            tz = ZoneInfo(tzname)
            dep = dt.datetime.combine(d, dt.time.fromisoformat(dep_s), tzinfo=tz)
            arr_local = dt.datetime.combine(d, dt.time.fromisoformat(arr_s), tzinfo=ZoneInfo(JETFLY_TZ.get(dest.lower(), tzname)))
            if arr_local.astimezone(dt.timezone.utc) <= dep.astimezone(dt.timezone.utc):
                arr_local += dt.timedelta(days=1)
            out.append(Leg(
                source="Jetfly", origin=origin, destination=dest, origin_name=origin, destination_name=dest,
                start=dep.astimezone(dt.timezone.utc), end=arr_local.astimezone(dt.timezone.utc), aircraft=aircraft.upper(),
                booking_url=cfg["url"], description="Jetfly empty leg. Confirm availability directly with Jetfly.", exact_time=True
            ))
    return out


def infer_year(month: int, day: int) -> int:
    y = TODAY.year
    candidate = dt.date(y, month, day)
    if candidate < TODAY - dt.timedelta(days=60):
        y += 1
    return y


def source_privjet(cfg: dict) -> list[Leg]:
    text = BeautifulSoup(get(cfg["url"]).text, "html.parser").get_text(" ", strip=True)
    aircraft_anchor = r"(?:Cessna|Dassault|Bombardier|Gulfstream|Pilatus|Embraer|Hawker|Learjet|Challenger|Citation|Falcon|Global|King Air|Beechcraft|Beechjet|HondaJet|Phenom|Private Jet)"
    pat = re.compile(
        r"(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun),\s+"
        r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})\s+"
        r"(.+?)\s+([A-Z]{4})(?:\s*·\s*[^→]+)?\s*→\s*(?:(?:\d+h(?:\s*\d+m)?|\d+m|—)\s*)?"
        r"(.+?)\s+([A-Z]{4})(?:\s*·\s*.*?)?\s+(" + aircraft_anchor + r".+?)\s+·\s+(\d+)\s+passengers\s+TOTAL PRICE\s*([€$£])\s*([\d,.]+)",
        re.I
    )
    out = []
    for m in pat.finditer(text):
        month_s, day_s, origin_name, origin, dest_name, dest, aircraft, pax, symbol, price_s = m.groups()
        month = MONTHS[month_s.lower()]
        d = dt.date(infer_year(month, int(day_s)), month, int(day_s))
        currency = {"€":"EUR", "$":"USD", "£":"GBP"}[symbol]
        out.append(Leg(
            source="PrivJet", origin=origin.upper(), destination=dest.upper(),
            origin_name=origin_name.strip(), destination_name=dest_name.strip(), start=d, end=d + dt.timedelta(days=1),
            aircraft=aircraft.strip(), pax=int(pax), price=float(price_s.replace(",", "")), currency=currency,
            booking_url=cfg["url"], description="Price shown by PrivJet includes its stated service fee. Confirm live availability before booking."
        ))
    return out


def parse_albajet_date(s: str) -> Optional[dt.date]:
    s = re.sub(r"^(Available\s+(?:From|To)\s+)", "", s, flags=re.I).strip()
    try:
        return dateparser.parse(s, dayfirst=False, fuzzy=True).date()
    except Exception:
        return None


def source_albajet(cfg: dict) -> list[Leg]:
    base = cfg["url"]
    out: list[Leg] = []
    max_pages = int(cfg.get("max_pages", 20))
    for p in range(1, max_pages + 1):
        url = base if p == 1 else f"{base}?p={p}"
        try:
            soup = BeautifulSoup(get(url).text, "html.parser")
        except Exception as e:
            print(f"AlbaJet page {p} failed: {e}", file=sys.stderr)
            break
        rows = soup.find_all("tr")
        found = 0
        for row in rows:
            cells = [c.get_text(" ", strip=True) for c in row.find_all("td")]
            if len(cells) < 5:
                continue
            fm = re.match(r"^([A-Z0-9]{3,4})\s+(.+?),\s*([A-Z]{2})$", cells[0])
            tm = re.match(r"^([A-Z0-9]{3,4})\s+(.+?),\s*([A-Z]{2})$", cells[1])
            if not (fm and tm):
                continue
            d1, d2 = parse_albajet_date(cells[2]), parse_albajet_date(cells[3])
            if not d1 or not d2:
                continue
            acm = re.match(r"^(?:Aircraft\s+)?(.+?)(?:\s+(\d+)\s+seats)?$", cells[4], re.I)
            aircraft = acm.group(1).strip() if acm else cells[4]
            pax = int(acm.group(2)) if acm and acm.group(2) else None
            details_link = row.find("a", href=True)
            out.append(Leg(
                source="AlbaJet", origin=fm.group(1), destination=tm.group(1),
                origin_name=fm.group(2), destination_name=tm.group(2), country_from=fm.group(3), country_to=tm.group(3),
                start=d1, end=d2 + dt.timedelta(days=1), aircraft=aircraft, pax=pax,
                booking_url=urljoin(base, details_link["href"]) if details_link else base,
                description=f"Availability window published by AlbaJet: {d1.isoformat()} through {d2.isoformat()}. Confirm exact timing and price before booking."
            ))
            found += 1
        if found == 0:
            break
    return out


def europe_ok(leg: Leg) -> bool:
    if leg.country_from or leg.country_to:
        return leg.country_from in EU_COUNTRIES and leg.country_to in EU_COUNTRIES
    if len(leg.origin) == 4 and len(leg.destination) == 4:
        return leg.origin[0] in {"E", "L"} and leg.destination[0] in {"E", "L"}
    return True


def filter_legs(legs: Iterable[Leg], cfg: dict) -> list[Leg]:
    cal = cfg["calendar"]
    filt = cfg.get("filters", {})
    horizon = TODAY + dt.timedelta(days=int(cal.get("horizon_days", 30)))
    touch = {x.upper() for x in filt.get("must_touch_airports", [])}
    max_eur = filt.get("max_price_eur")
    result = []
    for leg in legs:
        if leg.date < TODAY or leg.date > horizon:
            continue
        if cal.get("europe_only", True) and not europe_ok(leg):
            continue
        if touch and leg.origin.upper() not in touch and leg.destination.upper() not in touch:
            continue
        if max_eur is not None and leg.currency == "EUR" and leg.price is not None and leg.price > float(max_eur):
            continue
        result.append(leg)
    return result


def dedupe(legs: list[Leg]) -> list[Leg]:
    priority = {"GlobeAir": 0, "Jetfly": 1, "PrivJet": 2, "AlbaJet": 3}
    best: dict[tuple, Leg] = {}
    for leg in legs:
        k = leg.key()
        old = best.get(k)
        if old is None:
            best[k] = leg
            continue
        old_rank = (0 if old.exact_time else 1, priority.get(old.source, 9), 0 if old.price is not None else 1)
        new_rank = (0 if leg.exact_time else 1, priority.get(leg.source, 9), 0 if leg.price is not None else 1)
        if new_rank < old_rank:
            best[k] = leg
    return list(best.values())


def esc(s: str) -> str:
    return str(s).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r", "").replace("\n", "\\n")


def fold(line: str, limit: int = 73) -> str:
    if len(line) <= limit:
        return line
    chunks = [line[:limit]]
    rest = line[limit:]
    while rest:
        chunks.append(" " + rest[:limit-1])
        rest = rest[limit-1:]
    return "\r\n".join(chunks)


def fmt_dt(v: dt.datetime) -> str:
    return v.astimezone(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def fmt_date(v: dt.date) -> str:
    return v.strftime("%Y%m%d")


def event_lines(leg: Leg, now: dt.datetime) -> list[str]:
    route = f"{leg.origin} → {leg.destination}"
    price = ""
    if leg.price is not None:
        sym = {"EUR":"€", "USD":"$", "GBP":"£"}.get(leg.currency, leg.currency + " ")
        price = f"{sym}{leg.price:,.0f} · "
    ac = f" · {leg.aircraft}" if leg.aircraft else ""
    summary = f"✈ {price}{route}{ac}"
    desc_parts = [f"Source: {leg.source}"]
    if leg.origin_name or leg.destination_name:
        desc_parts.append(f"Route: {leg.origin_name or leg.origin} → {leg.destination_name or leg.destination}")
    if leg.pax:
        desc_parts.append(f"Capacity: {leg.pax} passengers")
    if leg.price is not None:
        desc_parts.append(f"Published price: {leg.currency} {leg.price:,.0f} (whole aircraft unless the source states otherwise)")
    if leg.description:
        desc_parts.append(leg.description)
    if leg.booking_url:
        desc_parts.append(f"Source / booking: {leg.booking_url}")
    desc_parts.append("Empty-leg schedules can change or disappear at short notice. Confirm with the operator/broker before making connecting travel plans.")
    lines = ["BEGIN:VEVENT", f"UID:{esc(leg.uid())}", f"DTSTAMP:{fmt_dt(now)}"]
    if isinstance(leg.start, dt.datetime):
        lines += [f"DTSTART:{fmt_dt(leg.start)}", f"DTEND:{fmt_dt(leg.end)}"]
    else:
        lines += [f"DTSTART;VALUE=DATE:{fmt_date(leg.start)}", f"DTEND;VALUE=DATE:{fmt_date(leg.end)}"]
    lines += [
        f"SUMMARY:{esc(summary)}",
        f"LOCATION:{esc(leg.origin_name or leg.origin)}",
        f"DESCRIPTION:{esc(chr(10).join(desc_parts))}",
        f"URL:{esc(leg.booking_url)}" if leg.booking_url else "",
        "TRANSP:TRANSPARENT",
        "X-MICROSOFT-CDO-BUSYSTATUS:FREE",
        "STATUS:CONFIRMED",
        "END:VEVENT",
    ]
    return [x for x in lines if x]


def write_calendar(legs: list[Leg], cfg: dict) -> None:
    now = dt.datetime.now(dt.timezone.utc)
    name = cfg["calendar"].get("name", "Private Jet Empty Legs")
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
        "PRODID:-//EmptyLegCalendar//EN", f"X-WR-CALNAME:{esc(name)}",
        f"X-PUBLISHED-TTL:PT{int(cfg['calendar'].get('refresh_minutes',30))}M",
        f"REFRESH-INTERVAL;VALUE=DURATION:PT{int(cfg['calendar'].get('refresh_minutes',30))}M",
    ]
    for leg in sorted(legs, key=lambda x: (x.date, x.origin, x.destination)):
        lines.extend(event_lines(leg, now))
    lines.append("END:VCALENDAR")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("\r\n".join(fold(x) for x in lines) + "\r\n", encoding="utf-8")


def main() -> int:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    all_legs: list[Leg] = []
    adapters = [("globeair", source_globeair), ("jetfly", source_jetfly), ("privjet", source_privjet), ("albajet", source_albajet)]
    for name, fn in adapters:
        scfg = cfg.get("sources", {}).get(name, {})
        if not scfg.get("enabled", False):
            continue
        try:
            legs = fn(scfg)
            print(f"{name}: {len(legs)} parsed")
            all_legs.extend(legs)
        except Exception as e:
            print(f"{name}: FAILED: {e}", file=sys.stderr)
    all_legs = filter_legs(all_legs, cfg)
    all_legs = dedupe(all_legs)
    all_legs = sorted(all_legs, key=lambda x: (x.date, 0 if x.exact_time else 1, x.price if x.price is not None else 10**9))
    max_events = int(cfg["calendar"].get("max_events", 300))
    all_legs = all_legs[:max_events]
    write_calendar(all_legs, cfg)
    print(f"Wrote {len(all_legs)} events to {OUTPUT}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
