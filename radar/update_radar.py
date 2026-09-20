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
OUT_MD = ROOT / "docs" / "radar" / "latest.md"
OUT_JSON = ROOT / "docs" / "radar" / "items.json"
OUT_HTML = ROOT / "docs" / "radar" / "index.html"

NOW = dt.datetime.now(dt.timezone.utc)
MAX_AGE_DAYS = 21
MAX_ITEMS = 80

def clean(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()

def parsed_time(entry) -> dt.datetime:
    t = entry.get("published_parsed") or entry.get("updated_parsed")
    if t:
        return dt.datetime(*t[:6], tzinfo=dt.timezone.utc)
    return NOW

def fetch_query(name: str, query: str) -> list[dict]:
    url = "https://news.google.com/rss/search?q=" + quote_plus(query) + "&hl=en-GB&gl=NO&ceid=NO:en"
    feed = feedparser.parse(url)
    rows = []
    for e in feed.entries:
        published = parsed_time(e)
        if published < NOW - dt.timedelta(days=MAX_AGE_DAYS):
            continue
        rows.append({
            "category": name,
            "title": clean(e.get("title", "")),
            "url": e.get("link", ""),
            "published": published.isoformat(),
            "source": clean((e.get("source") or {}).get("title", "")) if isinstance(e.get("source"), dict) else "",
            "summary": clean(e.get("summary", ""))[:500],
        })
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

def write(items: list[dict]) -> None:
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps({"updated_at": NOW.isoformat(), "items": items}, ensure_ascii=False, indent=2), encoding="utf-8")

    md = [
        "# Nordic AI / Datacentre / Connectivity Radar",
        "",
        f"_Updated {NOW.strftime('%Y-%m-%d %H:%M UTC')} · public web sources only_",
        "",
    ]
    bycat = {}
    for x in items:
        bycat.setdefault(x["category"], []).append(x)
    for cat, rows in bycat.items():
        md += [f"## {cat}", ""]
        for x in rows[:12]:
            src = f" — {x['source']}" if x.get("source") else ""
            date = x["published"][:10]
            md.append(f"- [{x['title']}]({x['url']}) · {date}{src}")
        md.append("")
    OUT_MD.write_text("\n".join(md), encoding="utf-8")

    cards = []
    for x in items[:60]:
        cards.append(
            "<article><div class='meta'>" + html.escape(x["category"]) + " · " + html.escape(x["published"][:10]) +
            (" · " + html.escape(x["source"]) if x.get("source") else "") +
            "</div><a href='" + html.escape(x["url"], quote=True) + "'>" + html.escape(x["title"]) + "</a></article>"
        )
    page = """<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width'>
<title>Nordic Infrastructure Radar</title><style>
body{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;max-width:900px;margin:40px auto;padding:0 18px;background:#f6f7f9;color:#15171a}
h1{font-size:32px;margin-bottom:6px}.sub{color:#666;margin-bottom:28px}article{background:white;padding:16px 18px;border-radius:12px;margin:10px 0;box-shadow:0 1px 4px #00000010}
article a{font-size:17px;font-weight:600;color:#111;text-decoration:none}.meta{font-size:12px;color:#777;margin-bottom:7px}
</style></head><body><h1>Nordic AI / Datacentre / Connectivity Radar</h1><div class='sub'>Updated """ + NOW.strftime("%Y-%m-%d %H:%M UTC") + """ · public sources</div>""" + "".join(cards) + "</body></html>"
    OUT_HTML.write_text(page, encoding="utf-8")

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
