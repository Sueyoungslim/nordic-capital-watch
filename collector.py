#!/usr/bin/env python3
"""
Nordic Capital Watch — collector.py
Hämtar RSS-feeds, filtrerar på techbolag i Sverige & Norge,
väljer de 15 viktigaste nyheterna och skickar till Slack.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

import feedparser
import requests

# ── Konfiguration ────────────────────────────────────────────────────────────

SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")
LOOKBACK_DAYS = 4   # Hämta nyheter de senaste N dagarna
MAX_ARTICLES = 15   # Antal artiklar att skicka till Slack

FEEDS = [
    # Sverige
    {"url": "https://www.breakit.se/feed/artiklar",  "country": "SE", "source": "Breakit",         "weight": 3},
    {"url": "https://mfn.se/all/rss",                "country": "SE", "source": "MFN",             "weight": 2},
    {"url": "https://www.realtid.se/feed/",          "country": "SE", "source": "Realtid",         "weight": 2},
    # Norge
    {"url": "https://e24.no/rss2/e24no",             "country": "NO", "source": "E24",             "weight": 3},
    {"url": "https://digi.no/rss",                   "country": "NO", "source": "Digi.no",         "weight": 2},
]

# Nyckelord för att identifiera techbolag-nyheter
KEYWORDS = [
    # Bolagstyp / bransch
    "startup", "techbolag", "tech", "saas", "fintech", "proptech", "medtech",
    "edtech", "deeptech", "ai", "artificiell intelligens", "mjukvara", "software",
    "plattform", "app", "digital", "e-handel", "ecommerce", "cloud", "moln",
    # Kapital
    "nyemission", "kapitalrunda", "seed", "serie a", "serie b", "serie c",
    "notering", "börsnotering", "ipo", "venture", "riskkapital", "finansiering",
    "emission", "investering", "förvärv",
    # Norska
    "emisjon", "kapitalrunde", "børsnotering", "risikokapital", "oppkjøp",
    # Engelska
    "funding", "raises", "investment", "acquisition", "series a", "series b",
    "pre-seed", "seed round", "listing", "ipo",
]

# Ord som höjer relevansen — nyheten handlar tydligt om ett techbolag
BOOST_KEYWORDS = [
    "startup", "techbolag", "saas", "fintech", "proptech", "medtech",
    "ai", "artificiell intelligens", "funding", "raises", "nyemission",
    "kapitalrunda", "börsnotering", "ipo", "emisjon", "kapitalrunde",
]

# ── Hjälpfunktioner ──────────────────────────────────────────────────────────

def parse_date(entry) -> datetime | None:
    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None)
        if t:
            try:
                return datetime(*t[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    return None


def is_recent(entry, cutoff: datetime) -> bool:
    dt = parse_date(entry)
    return dt is not None and dt >= cutoff


def score_entry(entry, source_weight: int) -> int:
    """Returnera relevanspoäng. Högre = viktigare."""
    text = " ".join([
        getattr(entry, "title", ""),
        getattr(entry, "summary", ""),
        getattr(entry, "description", ""),
    ]).lower()

    if not any(kw in text for kw in KEYWORDS):
        return 0

    score = source_weight
    score += sum(1 for kw in KEYWORDS if kw in text)
    score += sum(2 for kw in BOOST_KEYWORDS if kw in text)
    return score


def excerpt(entry, max_chars: int = 120) -> str:
    """Kort sammanfattning från RSS-posten."""
    raw = getattr(entry, "summary", "") or getattr(entry, "description", "")
    # Rensa enkla HTML-taggar
    import re
    clean = re.sub(r"<[^>]+>", "", raw).strip()
    clean = re.sub(r"\s+", " ", clean)
    if len(clean) > max_chars:
        clean = clean[:max_chars].rsplit(" ", 1)[0] + "…"
    return clean


def fetch_feed(feed_cfg: dict, cutoff: datetime) -> list[dict]:
    url = feed_cfg["url"]
    try:
        parsed = feedparser.parse(url)
        if parsed.bozo and not parsed.entries:
            print(f"  [WARN] {feed_cfg['source']}: {parsed.bozo_exception}", file=sys.stderr)
            return []
    except Exception as e:
        print(f"  [ERROR] {feed_cfg['source']}: {e}", file=sys.stderr)
        return []

    results = []
    for entry in parsed.entries:
        if not is_recent(entry, cutoff):
            continue
        s = score_entry(entry, feed_cfg["weight"])
        if s == 0:
            continue
        results.append({
            "title":   getattr(entry, "title", "(ingen rubrik)").strip(),
            "link":    getattr(entry, "link", ""),
            "excerpt": excerpt(entry),
            "date":    parse_date(entry),
            "source":  feed_cfg["source"],
            "country": feed_cfg["country"],
            "score":   s,
        })

    print(f"  {feed_cfg['source']}: {len(parsed.entries)} inlägg → {len(results)} matchade")
    return results


# ── Slack-formatering ────────────────────────────────────────────────────────

DAYS_SV    = ["Måndag", "Tisdag", "Onsdag", "Torsdag", "Fredag", "Lördag", "Söndag"]
MONTHS_SV  = ["januari", "februari", "mars", "april", "maj", "juni",
               "juli", "augusti", "september", "oktober", "november", "december"]


def format_date_sv(dt: datetime) -> str:
    return f"{DAYS_SV[dt.weekday()]} {dt.day} {MONTHS_SV[dt.month - 1]} {dt.year}"


def next_report_date(today: datetime) -> str:
    wd = today.weekday()
    delta = (3 - wd) if wd < 3 else (7 - wd) if wd >= 3 else 4
    if wd == 3:
        delta = 4  # Torsdag → nästa måndag
    nxt = today + timedelta(days=delta)
    return f"{DAYS_SV[nxt.weekday()]} {nxt.day} {MONTHS_SV[nxt.month - 1]}"


def build_slack_message(articles: list[dict]) -> dict:
    now = datetime.now(timezone.utc)

    se = [a for a in articles if a["country"] == "SE"]
    no = [a for a in articles if a["country"] == "NO"]

    def render_section(flag: str, label: str, items: list[dict]) -> dict:
        if not items:
            return {
                "type": "section",
                "text": {"type": "mrkdwn",
                         "text": f"*{flag} {label}*\n_Inga matchande nyheter denna period_"}
            }
        lines = []
        for a in items:
            link_text = f"<{a['link']}|{a['title']}>" if a["link"] else a["title"]
            line = f"• {link_text}  _via {a['source']}_"
            if a["excerpt"]:
                line += f"\n  _{a['excerpt']}_"
            lines.append(line)
        return {
            "type": "section",
            "text": {"type": "mrkdwn",
                     "text": f"*{flag} {label} ({len(items)})*\n" + "\n".join(lines)}
        }

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text",
                     "text": f"🔔 Nordic Tech Watch — {format_date_sv(now)}"}
        },
        {
            "type": "context",
            "elements": [{"type": "mrkdwn",
                           "text": f"_De {len(articles)} viktigaste technyheterna från Sverige & Norge de senaste {LOOKBACK_DAYS} dagarna_"}]
        },
        {"type": "divider"},
        render_section("🇸🇪", "Sverige", se),
        {"type": "divider"},
        render_section("🇳🇴", "Norge", no),
        {"type": "divider"},
        {
            "type": "context",
            "elements": [{"type": "mrkdwn",
                           "text": f"_Nästa rapport: {next_report_date(now)}_"}]
        },
    ]

    fallback = f"Nordic Tech Watch — {len(articles)} nyheter ({len(se)} SE, {len(no)} NO)"
    return {"text": fallback, "blocks": blocks}


# ── Huvud ────────────────────────────────────────────────────────────────────

def main():
    if not SLACK_WEBHOOK_URL:
        print("ERROR: SLACK_WEBHOOK_URL är inte satt.", file=sys.stderr)
        sys.exit(1)

    cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    print(f"Hämtar nyheter från {cutoff.strftime('%Y-%m-%d %H:%M')} UTC...\n")

    all_articles: list[dict] = []
    seen: set[str] = set()

    for feed in FEEDS:
        for a in fetch_feed(feed, cutoff):
            key = a["link"] or a["title"]
            if key not in seen:
                seen.add(key)
                all_articles.append(a)

    # Sortera efter relevanspoäng (högst först), sedan datum
    all_articles.sort(key=lambda a: (-a["score"], -(a["date"].timestamp() if a["date"] else 0)))

    # Välj de N viktigaste, men bevara landsbalans om möjligt
    se_all = [a for a in all_articles if a["country"] == "SE"]
    no_all = [a for a in all_articles if a["country"] == "NO"]

    # Fördela ~60/40 mellan SE och NO, justerat efter tillgång
    n_se = min(len(se_all), round(MAX_ARTICLES * 0.6))
    n_no = min(len(no_all), MAX_ARTICLES - n_se)
    n_se = min(len(se_all), MAX_ARTICLES - n_no)  # fyll upp om NO är litet

    selected = se_all[:n_se] + no_all[:n_no]
    # Sortera slutlistan: SE först, sedan NO; inom varje grupp högst poäng
    selected.sort(key=lambda a: (a["country"], -a["score"]))

    print(f"\nVäljer {len(selected)} artiklar (SE: {n_se}, NO: {n_no})")

    payload = build_slack_message(selected)

    print("Skickar till Slack...")
    resp = requests.post(SLACK_WEBHOOK_URL, json=payload, timeout=10)
    if resp.status_code == 200:
        print("Slack: OK")
    else:
        print(f"Slack: FEL {resp.status_code} — {resp.text}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
