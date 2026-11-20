#!/usr/bin/env python3
"""Generate a monochrome GitHub stats card for a profile README.

Standard library only. Reads the public GitHub API (with an optional token)
and writes ``assets/stats.svg``.

Environment:
    GITHUB_TOKEN   optional, raises rate limits (set in the workflow)
    GH_LOGIN       optional, defaults to "adikhw"
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

LOGIN = os.environ.get("GH_LOGIN", "adikhw")
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
API = "https://api.github.com"
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "stats.svg"

W, H = 820, 264
PAD = 28
MONO = "'JetBrains Mono','SFMono-Regular',Menlo,Consolas,monospace"

INK = "#ededed"
MUTED = "#7a7a7a"
FAINT = "#4a4a4a"
LINE = "#242424"
TRACK = "#1c1c1c"
BAR = "#d6d6d6"
BG = "#0d0d0d"


def api(path: str):
    data, _ = api_raw(path)
    return data


def api_raw(path: str):
    req = urllib.request.Request(API + path)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", f"{LOGIN}-stats-card")
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    with urllib.request.urlopen(req, timeout=30) as res:
        return json.load(res), res.headers


def repo_commits(full_name: str, branch: str) -> int:
    """Count commits on one branch using the Link header's last page."""
    try:
        data, headers = api_raw(f"/repos/{full_name}/commits?sha={branch}&per_page=1")
    except (urllib.error.HTTPError, urllib.error.URLError):
        return 0
    match = re.search(r'[?&]page=(\d+)>;\s*rel="last"', headers.get("Link", ""))
    return int(match.group(1)) if match else len(data)


def collect() -> dict:
    user = api(f"/users/{LOGIN}")
    repos = api(f"/users/{LOGIN}/repos?per_page=100&sort=updated")

    langs: dict[str, int] = {}
    for repo in repos:
        if repo.get("fork"):
            continue
        try:
            data = api(f"/repos/{LOGIN}/{repo['name']}/languages")
        except (urllib.error.HTTPError, urllib.error.URLError):
            continue
        for name, size in data.items():
            langs[name] = langs.get(name, 0) + size

    # Skip the profile repo itself: its refresh commits would inflate the
    # number by one every day without any real work behind it.
    commits = sum(
        repo_commits(r["full_name"], r.get("default_branch", "main"))
        for r in repos
        if not r.get("fork") and r["full_name"].lower() != f"{LOGIN}/{LOGIN}".lower()
    )

    return {
        "repos": user.get("public_repos", len(repos)),
        "commits": commits,
        "stars": sum(r.get("stargazers_count", 0) for r in repos),
        "langs": langs,
    }


def esc(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def short(n: int) -> str:
    if n >= 1000:
        return f"{n / 1000:.1f}k".replace(".0k", "k")
    return str(n)


def build(data: dict) -> str:
    langs = sorted(data["langs"].items(), key=lambda kv: kv[1], reverse=True)[:5]
    total = sum(data["langs"].values()) or 1

    parts: list[str] = []
    add = parts.append

    add(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" role="img" aria-labelledby="title">')
    add(f"<title id=\"title\">GitHub stats for {esc(LOGIN)}</title>")
    add(
        f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="14" '
        f'fill="{BG}" stroke="{LINE}" />'
    )

    # header
    add(
        f'<text x="{PAD}" y="46" font-family="{MONO}" font-size="20" '
        f'font-weight="700" fill="{INK}">{esc(LOGIN)}</text>'
    )
    add(
        f'<text x="{W - PAD}" y="45" text-anchor="end" font-family="{MONO}" '
        f'font-size="11" fill="{MUTED}">~/adikhw $ stats --all</text>'
    )
    add(f'<line x1="{PAD}" y1="62" x2="{W - PAD}" y2="62" stroke="{LINE}" />')

    # stat grid
    cells = [
        (PAD, 96, "REPOS", short(data["repos"])),
        (PAD, 152, "COMMITS", short(data["commits"])),
        (196, 96, "STARS", short(data["stars"])),
        (196, 152, "LANGUAGES", short(len(data["langs"]))),
    ]
    for x, y, label, value in cells:
        add(
            f'<text x="{x}" y="{y}" font-family="{MONO}" font-size="9" '
            f'letter-spacing="1.6" fill="{MUTED}">{label}</text>'
        )
        add(
            f'<text x="{x}" y="{y + 28}" font-family="{MONO}" font-size="24" '
            f'font-weight="700" fill="{INK}">{esc(value)}</text>'
        )

    # language panel
    add(f'<line x1="330" y1="86" x2="330" y2="208" stroke="{LINE}" />')
    add(
        f'<text x="362" y="96" font-family="{MONO}" font-size="9" '
        f'letter-spacing="1.6" fill="{MUTED}">LANGUAGES</text>'
    )

    bar_x, bar_w = 452, 268
    y = 118
    for name, size in langs:
        pct = size / total * 100
        fill_w = max(2.0, bar_w * pct / 100)
        add(
            f'<text x="362" y="{y + 4}" font-family="{MONO}" font-size="11" '
            f'fill="{INK}">{esc(name)}</text>'
        )
        add(
            f'<rect x="{bar_x}" y="{y - 6}" width="{bar_w}" height="6" rx="3" '
            f'fill="{TRACK}" />'
        )
        add(
            f'<rect x="{bar_x}" y="{y - 6}" width="{fill_w:.1f}" height="6" '
            f'rx="3" fill="{BAR}" />'
        )
        add(
            f'<text x="{W - PAD}" y="{y + 4}" text-anchor="end" '
            f'font-family="{MONO}" font-size="10" fill="{MUTED}">{pct:.0f}%</text>'
        )
        y += 24

    # footer
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    add(f'<line x1="{PAD}" y1="226" x2="{W - PAD}" y2="226" stroke="{LINE}" />')
    add(
        f'<text x="{PAD}" y="246" font-family="{MONO}" font-size="9" '
        f'fill="{FAINT}">generated {stamp}</text>'
    )
    add(
        f'<text x="{W - PAD}" y="246" text-anchor="end" font-family="{MONO}" '
        f'font-size="9" fill="{FAINT}">github.com/{esc(LOGIN)}</text>'
    )

    add("</svg>")
    return "\n".join(parts) + "\n"


def main() -> int:
    try:
        data = collect()
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
        print(f"stats: GitHub API unavailable ({exc}); keeping existing card", file=sys.stderr)
        return 0 if OUT.exists() else 1

    svg = build(data)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if OUT.exists() and OUT.read_text(encoding="utf-8") == svg:
        print("stats: unchanged")
        return 0
    OUT.write_text(svg, encoding="utf-8")
    print(f"stats: wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
