#!/usr/bin/env python3
"""Render Ahsan's animated contribution signal from GitHub's public calendar."""
import argparse
import hashlib
import html
import json
import re
import time
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

USERNAME = "Ahsan-Umair"
START_YEAR = 2025
TIMEZONE = "Asia/Karachi"

class CalendarParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.cells = {}
        self.tooltips = {}
        self.current = None
        self.parts = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("data-date") and attrs.get("id"):
            self.cells[attrs["id"]] = attrs["data-date"]
        if tag == "tool-tip":
            self.current = attrs.get("for")
            self.parts = []

    def handle_data(self, data):
        if self.current:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag == "tool-tip" and self.current:
            self.tooltips[self.current] = "".join(self.parts).strip()
            self.current = None

def parse_calendar(source, year, as_of):
    parser = CalendarParser()
    parser.feed(source)
    result = {}
    for identifier, text_date in parser.cells.items():
        day = date.fromisoformat(text_date)
        if day.year != year or day > as_of:
            continue
        tooltip = parser.tooltips.get(identifier, "")
        match = re.search(r"([\d,]+)\s+contributions?\s+on\b", tooltip)
        if match:
            count = int(match.group(1).replace(",", ""))
        elif re.search(r"No\s+contributions\s+on\b", tooltip):
            count = 0
        else:
            raise ValueError(f"Unrecognized contribution count for {day}")
        if text_date in result and result[text_date] != count:
            raise ValueError(f"Conflicting contribution count for {day}")
        result[text_date] = count
    last_day = min(as_of, date(year, 12, 31))
    expected = (last_day - date(year, 1, 1)).days + 1
    if len(result) != expected:
        raise ValueError(f"Incomplete {year} calendar: {len(result)} of {expected} days")
    return result

def fetch_calendar(username, year, as_of):
    url = f"https://github.com/users/{username}/contributions?from={year}-01-01&to={year}-12-31"
    request = Request(url, headers={"User-Agent": "Ahsan-Umair-contribution-signal", "Accept-Language": "en"})
    last_error = None
    for attempt in range(3):
        try:
            with urlopen(request, timeout=30) as response:
                return parse_calendar(response.read().decode("utf-8"), year, as_of)
        except Exception as error:
            last_error = error
            if attempt < 2:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"Could not read the {year} contribution calendar") from last_error

def summarize(days, as_of):
    total = sum(days.values())
    longest = run = 0
    longest_start = longest_end = run_start = None
    for text_date in sorted(days):
        day = date.fromisoformat(text_date)
        if day > as_of:
            continue
        if days[text_date] > 0:
            if run == 0:
                run_start = text_date
            run += 1
            if run > longest:
                longest, longest_start, longest_end = run, run_start, text_date
        else:
            run = 0
    end = as_of
    # Today's unfinished day does not break yesterday's ongoing streak.
    if days.get(end.isoformat(), 0) == 0:
        end -= timedelta(days=1)
    current = 0
    cursor = end
    while days.get(cursor.isoformat(), 0) > 0:
        current += 1
        cursor -= timedelta(days=1)
    recent_start = as_of - timedelta(days=364)
    return {
        "total_contributions": total,
        "last_365_days": sum(n for d, n in days.items() if recent_start.isoformat() <= d <= as_of.isoformat()),
        "current_streak": current,
        "current_start": (cursor + timedelta(days=1)).isoformat() if current else None,
        "current_end": end.isoformat() if current else None,
        "longest_streak": longest,
        "longest_start": longest_start,
        "longest_end": longest_end,
        "active_days_30": sum(days.get((as_of - timedelta(days=i)).isoformat(), 0) > 0 for i in range(30)),
    }

def short_date(value):
    return date.fromisoformat(value).strftime("%d %b %Y").lstrip("0") if value else "No activity yet"

def render_svg(snapshot):
    stats = snapshot["stats"]
    days = snapshot["daily_counts"]
    as_of = date.fromisoformat(snapshot["as_of"])
    username = html.escape(snapshot["username"])
    current = stats["current_streak"]
    since = f'Since {short_date(stats["current_start"])}' if current else "Your next contribution starts a new streak"
    through = short_date(stats["current_end"]) if current else "—"
    recent = [(as_of - timedelta(days=41-i)).isoformat() for i in range(42)]
    peak = max([days.get(d, 0) for d in recent] + [1])
    bars = []
    for i, day in enumerate(recent):
        count = days.get(day, 0)
        height = 9 if count == 0 else 14 + 65 * (count / peak) ** 0.55
        x, y = 527 + i * 14.8, 387 - height
        color = "#25344b" if count == 0 else "#a78bfa" if count == peak else "#22d3ee"
        bars.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="9.2" height="{height:.1f}" rx="3" fill="{color}" opacity=".88"><title>{day}: {count} contributions</title></rect>')
    bars = "".join(bars)
    today_count = days.get(as_of.isoformat(), 0)
    updated = datetime.fromisoformat(snapshot["generated_at"]).astimezone(ZoneInfo(TIMEZONE)).strftime("%d %b %Y · %H:%M PKT")
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="480" viewBox="0 0 1200 480" role="img" aria-labelledby="title desc">
<title id="title">{username} — Contribution Signal</title>
<desc id="desc">{current} day current streak; {stats["longest_streak"]} day longest streak; {stats["total_contributions"]} all-time contributions. Public activity and shared private contribution counts from GitHub's calendar.</desc>
<defs>
  <linearGradient id="bg" x2="1" y2="1"><stop stop-color="#091627"/><stop offset="1" stop-color="#080e1c"/></linearGradient>
  <linearGradient id="accent"><stop stop-color="#22d3ee"/><stop offset="1" stop-color="#a78bfa"/></linearGradient>
  <linearGradient id="sweep"><stop stop-color="#22d3ee" stop-opacity="0"/><stop offset=".5" stop-color="#22d3ee" stop-opacity=".19"/><stop offset="1" stop-color="#22d3ee" stop-opacity="0"/></linearGradient>
  <pattern id="grid" width="28" height="28" patternUnits="userSpaceOnUse"><path d="M28 0H0V28" fill="none" stroke="#1c3550" stroke-width=".6"/></pattern>
  <clipPath id="timeline"><rect x="515" y="291" width="636" height="105" rx="6"/></clipPath>
  <filter id="glow" x="-60%" y="-60%" width="220%" height="220%"><feGaussianBlur stdDeviation="3" result="blur"/><feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
  <path id="signal" d="M51 331H88L103 317L116 342L132 297L151 357L170 324L184 331H218L230 312L245 345L267 301L284 352L302 329H359L372 315L388 340L405 320L419 331H449"/>
</defs>
<style>
text{{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}}
.label{{font-size:12px;font-weight:600;letter-spacing:2px;fill:#8ea4bf}}
.small{{font-size:13px;fill:#8ea4bf}}
.value{{font-size:47px;font-weight:700;fill:#e6f6ff}}
@keyframes live{{0%,100%{{opacity:1}}50%{{opacity:.3}}}}
@keyframes drift{{to{{stroke-dashoffset:-180}}}}
@keyframes sweep{{from{{transform:translateX(-120px)}}to{{transform:translateX(700px)}}}}
.live{{animation:live 2.6s ease-in-out infinite}}
.trace{{animation:drift 12s linear infinite}}
.sweep{{animation:sweep 8s linear infinite}}
@media (prefers-reduced-motion:reduce){{.live,.trace,.sweep{{animation:none}}.orb{{display:none}}}}
</style>
<rect x="1" y="1" width="1198" height="478" rx="20" fill="url(#bg)" stroke="#29415c"/>
<rect x="2" y="2" width="1196" height="476" rx="20" fill="url(#grid)" opacity=".32"/>
<path d="M24 1H1180" stroke="url(#accent)" stroke-width="2"/>
<circle cx="35" cy="34" r="4" fill="#22d3ee" class="live"/>
<text x="50" y="39" class="label" style="fill:#22d3ee">CONTRIBUTION SIGNAL</text>
<text x="1159" y="39" class="small" text-anchor="end">{username} / activity.monitor</text>
<path d="M28 61H1172" stroke="#233b54"/>
<rect x="28" y="84" width="450" height="319" rx="14" fill="#0a1729" stroke="#26455c"/>
<text x="51" y="113" class="label" style="fill:#22d3ee">CONTINUOUS MOMENTUM</text>
<text x="50" y="217" font-size="100" font-weight="750" fill="url(#accent)">{current:02d}</text>
<text x="245" y="214" font-size="20" fill="#b8d0e7">days</text>
<text x="53" y="255" font-size="15" fill="#e6f6ff">{since}</text>
<text x="53" y="281" class="small">Active through {through}</text>
<use href="#signal" fill="none" stroke="#173b51" stroke-width="3"/>
<use href="#signal" fill="none" stroke="#22d3ee" stroke-width="2" stroke-dasharray="14 7" class="trace" opacity=".86"/>
<circle r="4" fill="#d4faff" filter="url(#glow)" class="orb"><animateMotion dur="6s" repeatCount="indefinite"><mpath href="#signal"/></animateMotion></circle>
<text x="53" y="381" class="small">{stats["active_days_30"]}/30 recent days active</text>
<rect x="501" y="84" width="315" height="157" rx="14" fill="#0d1b2e" stroke="#2a3e59"/>
<text x="524" y="113" class="label">ALL-TIME CONTRIBUTIONS</text>
<text x="523" y="174" class="value">{stats["total_contributions"]:,}</text>
<text x="525" y="214" class="small">{stats["last_365_days"]:,} in the past 365 days</text>
<rect x="837" y="84" width="335" height="157" rx="14" fill="#12182f" stroke="#413759"/>
<text x="860" y="113" class="label" style="fill:#a78bfa">LONGEST RUN</text>
<text x="860" y="174" class="value" style="fill:#c4b5fd">{stats["longest_streak"]:02d}<tspan font-size="19" font-weight="400" fill="#9eacd0"> days</tspan></text>
<text x="861" y="214" class="small">{short_date(stats["longest_start"])} — {short_date(stats["longest_end"])}</text>
<rect x="501" y="263" width="671" height="140" rx="14" fill="#091526" stroke="#263e58"/>
<text x="524" y="287" class="label">42-DAY ACTIVITY PULSE</text>
<text x="1149" y="287" class="small" text-anchor="end">TODAY / {today_count:02d}</text>
<g clip-path="url(#timeline)">{bars}<rect x="515" y="300" width="110" height="88" fill="url(#sweep)" class="sweep"/></g>
<path d="M28 425H1172" stroke="#233b54"/>
<circle cx="38" cy="450" r="3" fill="#34d399" class="live"/>
<text x="51" y="455" font-size="12" fill="#86a9bb">GitHub calendar · public + shared private activity</text>
<text x="1158" y="455" font-size="12" fill="#7895ad" text-anchor="end">Synced {updated}</text>
</svg>
'''

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--as-of", type=date.fromisoformat)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parents[1] / "assets")
    args = parser.parse_args()
    today = args.as_of or datetime.now(ZoneInfo(TIMEZONE)).date()
    days = {}
    for year in range(START_YEAR, today.year + 1):
        if args.cache_dir:
            source = (args.cache_dir / f"contributions-{year}.html").read_text()
            days.update(parse_calendar(source, year, today))
        else:
            days.update(fetch_calendar(USERNAME, year, today))
    stats = summarize(days, today)
    fingerprint = hashlib.sha256(json.dumps([today.isoformat(), days], sort_keys=True).encode()).hexdigest()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    data_path = args.output_dir / "contributions.json"
    previous = json.loads(data_path.read_text()) if data_path.exists() else {}
    generated_at = previous.get("generated_at") if previous.get("fingerprint") == fingerprint else None
    snapshot = {
        "username": USERNAME,
        "as_of": today.isoformat(),
        "source": "https://github.com/users/Ahsan-Umair/contributions",
        "timezone": TIMEZONE,
        "scope": "public calendar including anonymized shared private activity",
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "fingerprint": fingerprint,
        "stats": stats,
        "daily_counts": dict(sorted(days.items())),
    }
    rendered = render_svg(snapshot)
    # Both inputs were fully validated before replacing the previous good card.
    data_path.write_text(json.dumps(snapshot, indent=2) + "\n")
    (args.output_dir / "contribution-signal.svg").write_text(rendered)
    print(json.dumps(stats, indent=2))

if __name__ == "__main__":
    main()
