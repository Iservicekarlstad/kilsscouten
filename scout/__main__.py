"""Scoutrapport: välj en klubb, få en analys av dess senaste matcher.

Exempel:
    python3 -m scout                                  # interaktivt
    python3 -m scout --serie SHL --lag "Växjö" -n 10
    python3 -m scout --serier                         # lista serier
"""
from __future__ import annotations

import argparse
import re
import sys
import webbrowser
from pathlib import Path

from . import data
from .analyze import analyze
from .fetch import Fetcher
from .report import render

ROOT = Path(__file__).resolve().parent.parent


def _choose(prompt: str, options: list[str]) -> int:
    for i, o in enumerate(options, 1):
        print(f"  {i:>3}. {o}")
    while True:
        a = input(f"{prompt}: ").strip()
        if a.isdigit() and 1 <= int(a) <= len(options):
            return int(a) - 1
        hits = [i for i, o in enumerate(options) if a.lower() in o.lower()] if a else []
        if len(hits) == 1:
            return hits[0]
        print("  Ange ett nummer eller en unik del av namnet.")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="scout", description="Scoutrapport från stats.swehockey.se")
    ap.add_argument("--serie", help="Seriens namn (t.ex. SHL) eller id (t.ex. 20961)")
    ap.add_argument("--lag", help="Lagets namn eller del av det")
    ap.add_argument("-n", "--matcher", type=int, default=10, help="Antal senaste matcher (standard 10)")
    ap.add_argument("--serier", action="store_true", help="Lista tillgängliga serier")
    ap.add_argument("--ut", help="Sökväg för HTML-rapporten")
    ap.add_argument("--oppna", action="store_true", help="Öppna rapporten i webbläsaren")
    args = ap.parse_args(argv)

    f = Fetcher(ROOT / ".cache")

    if args.serier:
        for lg in data.leagues(f):
            print(f"{lg.league_id:>7}  {lg.name}  ({lg.group})")
        return 0

    if args.serie:
        league = data.find_league(f, args.serie)
    else:
        ls = data.leagues(f)[:40]
        league = ls[_choose("Välj serie", [f"{lg.name} ({lg.group})" for lg in ls])]
    sched = data.schedule(f, league.league_id)
    league.name = data.league_title(f, league.league_id) or league.name
    print(f"Serie: {league.name} ({league.league_id})")
    all_teams = data.teams(sched)
    if not all_teams:
        print("Hittade inga matcher i serien.")
        return 1
    team = data.find_team(all_teams, args.lag) if args.lag else all_teams[_choose("Välj lag", all_teams)]

    refs = data.recent_games(sched, team, args.matcher)
    if not refs:
        print(f"{team} har inga spelade matcher i {league.name} ännu.")
        return 1
    print(f"Lag: {team} – analyserar {len(refs)} matcher")
    games = [data.load_game(f, ref) for ref in refs]

    rep = analyze(team, games, league.name)
    html = render(rep, data.next_game(sched, team))

    slug = re.sub(r"[^a-z0-9]+", "-", team.lower().translate(str.maketrans("åäöé", "aaoe"))).strip("-")
    out = Path(args.ut) if args.ut else ROOT / "rapporter" / f"{slug}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"\nRapport: {out}")
    for i in rep.insights[:5]:
        print(f"  [{ {'hot': 'SE UPP', 'chans': 'CHANS', 'info': 'INFO'}[i.kind] }] {i.title}: {i.text}")
    if args.oppna:
        webbrowser.open(out.as_uri())
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
