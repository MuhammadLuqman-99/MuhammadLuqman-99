#!/usr/bin/env python3
"""Render the last N days of GitHub contributions as a line-chart SVG (dark + light).

Runs in GitHub Actions with the default GITHUB_TOKEN (see contribution-graph.yml).
Locally:  GITHUB_TOKEN=$(gh auth token) python3 .github/scripts/contribution_graph.py
Outputs:  <OUT_DIR>/github-contribution-graph-dark.svg and -light.svg
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import sys
import urllib.request

USER = os.environ.get("GH_USER", "MuhammadLuqman-99")
DAYS = int(os.environ.get("DAYS", "31"))
OUT_DIR = os.environ.get("OUT_DIR", "dist")
TITLE = os.environ.get("TITLE", "Luqman the coder's Contribution Graph")

W, H = 1200, 340
PAD_L, PAD_R, PAD_T, PAD_B = 72, 32, 64, 56
FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"

THEMES = {
    "dark": dict(title="#c9d1d9", sub="#8b949e", axis="#8b949e", grid="#21262d",
                 line="#58a6ff", dot="#0d1117"),
    "light": dict(title="#24292f", sub="#57606a", axis="#57606a", grid="#d0d7de",
                  line="#0969da", dot="#ffffff"),
}

QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar { weeks { contributionDays { date contributionCount } } }
    }
  }
}"""


def fetch_days() -> list[dict]:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        sys.exit("GITHUB_TOKEN is not set")
    now = dt.datetime.now(dt.timezone.utc)
    to = now.replace(hour=23, minute=59, second=59, microsecond=0)
    frm = (to - dt.timedelta(days=DAYS - 1)).replace(hour=0, minute=0, second=0)
    payload = json.dumps({
        "query": QUERY,
        "variables": {"login": USER, "from": frm.isoformat(), "to": to.isoformat()},
    }).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql", data=payload,
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json",
                 "User-Agent": "contribution-graph"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    if data.get("errors"):
        sys.exit(f"GraphQL error: {data['errors']}")
    weeks = data["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    days = sorted((d for w in weeks for d in w["contributionDays"]), key=lambda d: d["date"])
    return days[-DAYS:]


def nice_max(value: int) -> int:
    if value <= 4:
        return 4
    mag = 10 ** int(math.log10(value))
    for step in (1, 2, 2.5, 5, 10):
        if step * mag >= value:
            return int(step * mag)
    return value


def smooth_path(pts: list[tuple[float, float]], top: float, base: float) -> str:
    """Catmull-Rom spline converted to cubic Béziers, control points clamped to the plot."""
    d = f"M{pts[0][0]:.1f},{pts[0][1]:.1f}"
    n = len(pts)
    for i in range(n - 1):
        p0 = pts[i - 1] if i > 0 else pts[i]
        p1, p2 = pts[i], pts[i + 1]
        p3 = pts[i + 2] if i + 2 < n else p2
        c1y = min(base, max(top, p1[1] + (p2[1] - p0[1]) / 6))
        c2y = min(base, max(top, p2[1] - (p3[1] - p1[1]) / 6))
        d += (f" C{p1[0] + (p2[0] - p0[0]) / 6:.1f},{c1y:.1f}"
              f" {p2[0] - (p3[0] - p1[0]) / 6:.1f},{c2y:.1f} {p2[0]:.1f},{p2[1]:.1f}")
    return d


def render(days: list[dict], theme: str) -> str:
    t = THEMES[theme]
    counts = [d["contributionCount"] for d in days]
    total = sum(counts)
    y_max = nice_max(max(counts) if counts else 0)
    plot_w = W - PAD_L - PAD_R
    plot_h = H - PAD_T - PAD_B
    base = PAD_T + plot_h
    step = plot_w / max(1, len(days) - 1)
    pts = [(PAD_L + i * step, base - (c / y_max) * plot_h) for i, c in enumerate(counts)]

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
        f'font-family="{FONT}" role="img" aria-label="{TITLE}">',
        "<defs>",
        f'<linearGradient id="area" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{t["line"]}" stop-opacity="0.35"/>'
        f'<stop offset="1" stop-color="{t["line"]}" stop-opacity="0.02"/></linearGradient>',
        "</defs>",
        f'<text x="{PAD_L}" y="30" font-size="18" font-weight="600" fill="{t["title"]}">{TITLE}</text>',
        f'<text x="{W - PAD_R}" y="30" font-size="12" text-anchor="end" fill="{t["sub"]}">'
        f'{total} contributions in the last {len(days)} days</text>',
    ]

    # horizontal grid + y labels
    ticks = 4
    for k in range(ticks + 1):
        y = base - plot_h * k / ticks
        parts.append(f'<line x1="{PAD_L}" y1="{y:.1f}" x2="{W - PAD_R}" y2="{y:.1f}" '
                     f'stroke="{t["grid"]}" stroke-width="1"/>')
        parts.append(f'<text x="{PAD_L - 10}" y="{y + 4:.1f}" font-size="11" text-anchor="end" '
                     f'fill="{t["axis"]}">{int(y_max * k / ticks)}</text>')

    # x labels (day of month)
    label_every = 1 if len(days) <= 31 else max(1, len(days) // 31)
    for i, d in enumerate(days):
        if i % label_every:
            continue
        parts.append(f'<text x="{pts[i][0]:.1f}" y="{base + 20}" font-size="11" text-anchor="middle" '
                     f'fill="{t["axis"]}">{int(d["date"][-2:])}</text>')

    # axis titles
    parts.append(f'<text x="{PAD_L + plot_w / 2:.1f}" y="{H - 14}" font-size="11" text-anchor="middle" '
                 f'fill="{t["sub"]}">Days</text>')
    parts.append(f'<text transform="translate(22,{PAD_T + plot_h / 2:.1f}) rotate(-90)" font-size="11" '
                 f'text-anchor="middle" fill="{t["sub"]}">Contributions</text>')

    if pts:
        line = smooth_path(pts, PAD_T, base)
        parts.append(f'<path d="{line} L{pts[-1][0]:.1f},{base} L{pts[0][0]:.1f},{base} Z" fill="url(#area)"/>')
        parts.append(f'<path d="{line}" fill="none" stroke="{t["line"]}" stroke-width="2.5" '
                     f'stroke-linejoin="round" stroke-linecap="round"/>')
        for (x, y), c in zip(pts, counts):
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="{t["dot"]}" '
                         f'stroke="{t["line"]}" stroke-width="1.5"><title>{c}</title></circle>')

    parts.append("</svg>")
    return "\n".join(parts)


def main() -> None:
    days = fetch_days()
    os.makedirs(OUT_DIR, exist_ok=True)
    for theme in THEMES:
        path = os.path.join(OUT_DIR, f"github-contribution-graph-{theme}.svg")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(render(days, theme))
        print("wrote", path)
    print(f"{sum(d['contributionCount'] for d in days)} contributions over {len(days)} days "
          f"({days[0]['date']} → {days[-1]['date']})")


if __name__ == "__main__":
    main()
