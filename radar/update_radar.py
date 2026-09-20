#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import html
import json
import re
from pathlib import Path
from urllib.parse import quote_plus

import feedparser
import yaml

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "radar" / "queries.yaml"
OUT_DIR = ROOT / "docs"
RADAR_DIR = OUT_DIR / "radar"
OUT_MD = RADAR_DIR / "latest.md"
OUT_JSON = RADAR_DIR / "items.json"
OUT_HTML = RADAR_DIR / "index.html"
OUT_WEEKLY = RADAR_DIR / "weekly.md"
OUT_HOME = OUT_DIR / "index.html"

NOW = dt.datetime.now(dt.timezone.utc)
MAX_AGE_DAYS = 21
MAX_ITEMS = 100

SIGNAL_TERMS = {
    "telenor": 12, "telia": 6, "elisa": 6, "tdc": 6, "globalconnect": 6,
    "atnorth": 7, "equinix": 7, "google": 6, "microsoft": 6, "aws": 6,
    "hyperscaler": 8, "data center": 6, "data centre": 6, "ai infrastructure": 9,
    "gigafactory": 8, "gpu": 6, "neocloud": 8, "dark fiber": 8, "dark fibre": 8,
    "subsea cable": 7, "acquisition": 8, "acquire": 7, "merger": 8,
    "investment": 5, "billion": 5, "sovereignty": 7, "network": 3,
}

SECTION_MAP = {
    "Nordic AI infrastructure": "AI / DC",
    "Datacentres": "AI / DC",
    "GPU cloud and neocloud": "AI / DC",
    "Operators": "Telecom",
    "Fibre and connectivity": "Telecom",
    "Telecom M&A": "M&A",
    "EU tech sovereignty": "Regulation",
}

SECTIONS = ["AI / DC", "Telecom", "M&A", "Regulation"]

def clean(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()

def parsed_time(entry) -> dt.datetime:
    t = entry.get("published_parsed") or entry.get("updated_parsed")
    if t:
        return dt.datetime(*t[:6], tzinfo=dt.timezone.utc)
    return NOW

def signal_score(item: dict) -> int:
    text = (item.get("title", "") + " " + item.get("summary", "")).lower()
    score = 0
    for term, weight in SIGNAL_TERMS.items():
        if term in text:
            score += weight
    age_days = max(0, (NOW - dt.datetime.fromisoformat(item["published"])).days)
    score += max(0, 7 - age_days)
    if item.get("source", "").lower() in {
        "reuters", "financial times", "bloomberg", "eu digital strategy",
        "telenor group", "telenor", "google cloud press corner"
    }:
        score += 4
    return score

def why_it_matters(item: dict) -> str:
    text = (item.get("title", "") + " " + item.get("summary", "")).lower()
    if "telenor" in text:
        return "Direct Telenor relevance"
    if any(x in text for x in ["acquisition", "acquire", "merger", "m&a"]):
        return "Market structure / M&A"
    if any(x in text for x in ["sovereignty", "commission", "regulation", "act", "eu "]):
        return "Policy / sovereignty"
    if any(x in text for x in ["dark fiber", "dark fibre", "network", "subsea", "connectivity"]):
        return "Connectivity demand / network"
    if any(x in text for x in ["data center", "data centre", "hyperscaler", "gpu", "neocloud", "ai infrastructure"]):
        return "AI / datacentre demand"
    if any(x in text for x in ["investment", "billion", "capacity", "expand"]):
        return "Capacity / investment signal"
    return "Nordic infrastructure signal"

def fetch_query(name: str, query: str) -> list[dict]:
    url = "https://news.google.com/rss/search?q=" + quote_plus(query) + "&hl=en-GB&gl=NO&ceid=NO:en"
    feed = feedparser.parse(url)
    rows = []
    for e in feed.entries:
        published = parsed_time(e)
        if published < NOW - dt.timedelta(days=MAX_AGE_DAYS):
            continue
        item = {
            "category": name,
            "section": SECTION_MAP.get(name, name),
            "title": clean(e.get("title", "")),
            "url": e.get("link", ""),
            "published": published.isoformat(),
            "source": clean((e.get("source") or {}).get("title", "")) if isinstance(e.get("source"), dict) else "",
            "summary": clean(e.get("summary", ""))[:500],
        }
        item["score"] = signal_score(item)
        item["why"] = why_it_matters(item)
        rows.append(item)
    return rows

def dedupe(items: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for x in sorted(items, key=lambda r: r["published"], reverse=True):
        key = re.sub(r"\W+", "", x["title"].lower())[:120]
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(x)
    return out

def card(item: dict, telenor=False) -> str:
    title = html.escape(item["title"])
    url = html.escape(item["url"], quote=True)
    source = html.escape(item.get("source") or "Source")
    date = html.escape(item["published"][:10])
    why = html.escape(item.get("why", ""))
    badge = "Telenor relevance" if telenor else item["section"]
    return (
        "<article class='card' data-section='" + html.escape(item["section"]) + "'>"
        "<div class='topline'><span class='badge'>" + html.escape(badge) + "</span>"
        "<span class='date'>" + date + "</span></div>"
        "<a class='headline' target='_blank' rel='noopener' href='" + url + "'>" + title + "</a>"
        "<div class='bottom'><span>" + source + "</span><span>•</span><span>" + why + "</span></div>"
        "</article>"
    )

def build_weekly(items: list[dict]) -> str:
    cutoff = NOW - dt.timedelta(days=7)
    recent = [x for x in items if dt.datetime.fromisoformat(x["published"]) >= cutoff]
    top = sorted(recent, key=lambda x: (x["score"], x["published"]), reverse=True)[:12]
    lines = [
        "# Weekly Nordic Infrastructure Brief",
        "",
        f"_Seven days through {NOW.strftime('%Y-%m-%d')} · public sources only_",
        "",
        "## What matters",
        "",
    ]
    for x in top[:7]:
        lines.append(f"- **{x['title']}** — {x['why']}. [{x.get('source') or 'Source'}]({x['url']})")
    lines += ["", "## By theme", ""]
    for sec in SECTIONS:
        rows = [x for x in top if x["section"] == sec]
        if not rows:
            continue
        lines += [f"### {sec}", ""]
        for x in rows[:4]:
            lines.append(f"- [{x['title']}]({x['url']}) — {x['why']}")
        lines.append("")
    return "\n".join(lines)

def write(items: list[dict]) -> None:
    RADAR_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps({"updated_at": NOW.isoformat(), "items": items}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    md = [
        "# Nordic AI / Datacentre / Connectivity Radar",
        "",
        f"_Updated {NOW.strftime('%Y-%m-%d %H:%M UTC')} · public web sources only_",
        "",
    ]
    for sec in SECTIONS:
        rows = [x for x in items if x["section"] == sec]
        if not rows:
            continue
        md += [f"## {sec}", ""]
        for x in rows[:12]:
            src = f" — {x['source']}" if x.get("source") else ""
            md.append(f"- [{x['title']}]({x['url']}) · {x['published'][:10]}{src}")
        md.append("")
    OUT_MD.write_text("\n".join(md), encoding="utf-8")
    OUT_WEEKLY.write_text(build_weekly(items), encoding="utf-8")

    top_signals = sorted(items, key=lambda x: (x["score"], x["published"]), reverse=True)[:8]
    telenor_items = [
        x for x in sorted(items, key=lambda x: (x["score"], x["published"]), reverse=True)
        if x["score"] >= 9
    ][:12]

    section_html = []
    for sec in SECTIONS:
        rows = [x for x in items if x["section"] == sec][:25]
        if rows:
            section_html.append(
                "<section id='" + re.sub(r"\W+", "-", sec.lower()).strip("-") + "'>"
                "<h2>" + html.escape(sec) + "</h2>" + "".join(card(x) for x in rows) + "</section>"
            )

    page = """<!doctype html>
<html lang='en'>
<head>
<meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1,viewport-fit=cover'>
<meta name='theme-color' content='#0b0d10'>
<meta name='apple-mobile-web-app-capable' content='yes'>
<meta name='apple-mobile-web-app-status-bar-style' content='black-translucent'>
<meta name='apple-mobile-web-app-title' content='Infra Radar'>
<link rel='manifest' href='./manifest.webmanifest'>
<link rel='icon' href='./icon.svg' type='image/svg+xml'>
<title>Nordic Infrastructure Radar</title>
<style>
:root{--bg:#0b0d10;--panel:#14171c;--panel2:#1b1f25;--text:#f4f5f7;--muted:#959ca7;--line:#262b33;--accent:#e9edf4}
*{box-sizing:border-box}html{background:var(--bg)}body{margin:0;background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"SF Pro Display","Segoe UI",sans-serif}
.wrap{max-width:980px;margin:auto;padding:28px 18px 70px}header{padding:22px 2px 20px}.eyebrow{font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}
h1{font-size:38px;line-height:1.02;letter-spacing:-.035em;margin:9px 0 10px}.sub{color:var(--muted);font-size:14px}
.controls{position:sticky;top:0;z-index:10;background:rgba(11,13,16,.94);backdrop-filter:blur(18px);padding:10px 0 14px;border-bottom:1px solid var(--line)}
input{width:100%;border:1px solid var(--line);background:var(--panel);color:var(--text);border-radius:13px;padding:13px 14px;font-size:16px;outline:none}
.chips{display:flex;gap:8px;overflow:auto;padding-top:10px;-webkit-overflow-scrolling:touch}.chip{white-space:nowrap;border:1px solid var(--line);background:var(--panel);color:var(--muted);border-radius:999px;padding:8px 12px;font-size:13px}
.chip.active{background:var(--text);color:var(--bg)}h2{font-size:24px;letter-spacing:-.025em;margin:34px 0 12px}
.hero{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.card{background:var(--panel);border:1px solid var(--line);border-radius:15px;padding:15px 16px;margin:9px 0}
.hero .card{margin:0}.topline,.bottom{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.topline{justify-content:space-between;margin-bottom:8px}.badge{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.07em;background:var(--panel2);padding:5px 8px;border-radius:999px;color:#cbd1da}.date,.bottom{font-size:12px;color:var(--muted)}
.headline{display:block;color:var(--text);text-decoration:none;font-weight:650;font-size:17px;line-height:1.28;letter-spacing:-.012em;margin-bottom:10px}
.bottom{line-height:1.35}.section-note{color:var(--muted);font-size:13px;margin-top:-5px;margin-bottom:12px}
.links{display:flex;gap:10px;margin-top:18px}.links a{color:var(--text);font-size:13px;text-decoration:none;border:1px solid var(--line);border-radius:10px;padding:9px 11px}
.hidden{display:none!important}
@media(max-width:650px){.wrap{padding:18px 14px 60px}h1{font-size:32px}.hero{grid-template-columns:1fr}.controls{top:-1px}h2{font-size:22px}}
</style>
</head>
<body><div class='wrap'>
<header><div class='eyebrow'>Strategy intelligence</div><h1>Nordic Infrastructure Radar</h1>
<div class='sub'>AI infrastructure · datacentres · connectivity · telecom · M&A · regulation<br>Updated """ + NOW.strftime("%d %b %Y · %H:%M UTC") + """</div>
<div class='links'><a href='./weekly.md'>7-day brief</a><a href='./latest.md'>Text view</a></div></header>
<div class='controls'><input id='search' type='search' placeholder='Search Telenor, Google, atNorth, fibre…'>
<div class='chips'><button class='chip active' data-filter='all'>All</button><button class='chip' data-filter='telenor'>Telenor relevance</button><button class='chip' data-filter='AI / DC'>AI / DC</button><button class='chip' data-filter='Telecom'>Telecom</button><button class='chip' data-filter='M&A'>M&A</button><button class='chip' data-filter='Regulation'>Regulation</button></div></div>
<section class='filterable' data-group='all'><h2>Top signals</h2><div class='section-note'>Highest-signal developments across the radar right now.</div><div class='hero'>""" +
"".join(card(x) for x in top_signals) + """</div></section>
<section class='filterable' data-group='telenor'><h2>Telenor relevance</h2><div class='section-note'>Developments most likely to matter for Nordic connectivity, wholesale, AI/DC demand or competitive positioning.</div>""" +
"".join(card(x, True) for x in telenor_items) + """</section>""" +
"".join(section_html) + """
</div>
<script>
const cards=[...document.querySelectorAll('.card')], sections=[...document.querySelectorAll('section')], chips=[...document.querySelectorAll('.chip')], search=document.getElementById('search');
let filter='all';
function apply(){
 const q=search.value.toLowerCase().trim();
 cards.forEach(c=>{const group=c.closest('section')?.dataset.group||c.dataset.section; const okFilter=filter==='all'||(filter==='telenor'?group==='telenor':c.dataset.section===filter); const okQ=!q||c.innerText.toLowerCase().includes(q); c.classList.toggle('hidden',!(okFilter&&okQ));});
 sections.forEach(s=>{const visible=[...s.querySelectorAll('.card')].some(c=>!c.classList.contains('hidden'));s.classList.toggle('hidden',!visible)});
}
chips.forEach(b=>b.onclick=()=>{chips.forEach(x=>x.classList.remove('active'));b.classList.add('active');filter=b.dataset.filter;apply()});
search.addEventListener('input',apply);
</script></body></html>"""

    OUT_HTML.write_text(page, encoding="utf-8")
    OUT_HOME.write_text(
        "<!doctype html><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<meta http-equiv='refresh' content='0; url=./radar/'><title>Nordic Infrastructure Radar</title>"
        "<a href='./radar/'>Open Nordic Infrastructure Radar</a>",
        encoding="utf-8",
    )

def main():
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    items = []
    for q in cfg["queries"]:
        items.extend(fetch_query(q["name"], q["query"]))
    items = dedupe(items)[:MAX_ITEMS]
    write(items)
    print(f"Wrote {len(items)} radar items")

if __name__ == "__main__":
    main()
