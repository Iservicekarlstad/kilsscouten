"""Samlar in serier, lag och ett lags senaste matcher."""
from __future__ import annotations

import datetime
import difflib
import html
import re

from .fetch import Fetcher
from .parse import (Game, GameRef, League, parse_game, parse_leagues, parse_lineups,
                    parse_schedule)

SIX_HOURS = 6 * 3600


def leagues(f: Fetcher) -> list[League]:
    return parse_leagues(f.get("/", max_age=24 * 3600))


def find_league(f: Fetcher, query: str) -> League:
    ls = leagues(f)
    if query.isdigit():
        for lg in ls:
            if lg.league_id == int(query):
                return lg
        return League(int(query), f"Serie {query}", "")
    exact = [lg for lg in ls if lg.name.lower() == query.lower()]
    if exact:
        return exact[0]
    part = [lg for lg in ls if query.lower() in lg.name.lower()]
    if part:
        return part[0]
    raise SystemExit(f"Hittar ingen serie som matchar '{query}'. Kör med --serier för att lista.")


def league_title(f: Fetcher, league_id: int) -> str | None:
    """Fullständigt namn, t.ex. 'HockeyTvåan Herr Region Väst C', från spelschemats <title>."""
    page = f.get(f"/ScheduleAndResults/Schedule/{league_id}", max_age=SIX_HOURS)
    m = re.search(r"<title>(.*?)</title>", page, re.S)
    if not m:
        return None
    t = html.unescape(m.group(1)).split("|")[0]
    t = re.sub(r"\s+-\s+\d{4}-\d{2}\s*$", "", " ".join(t.split()))
    return t.strip() or None


def schedule(f: Fetcher, league_id: int) -> list[GameRef]:
    return parse_schedule(f.get(f"/ScheduleAndResults/Schedule/{league_id}", max_age=SIX_HOURS))


def teams(games: list[GameRef]) -> list[str]:
    return sorted({g.home for g in games} | {g.away for g in games})


def find_team(all_teams: list[str], query: str) -> str:
    q = query.lower()
    hits = [t for t in all_teams if q in t.lower()]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        exact = [t for t in hits if t.lower() == q]
        if exact:
            return exact[0]
        raise SystemExit(f"'{query}' matchar flera lag: {', '.join(hits)}")
    close = difflib.get_close_matches(query, all_teams, n=3, cutoff=0.5)
    hint = f" Menade du: {', '.join(close)}?" if close else ""
    raise SystemExit(f"Hittar inget lag '{query}' i serien.{hint}")


def recent_games(games: list[GameRef], team: str, n: int) -> list[GameRef]:
    played = [g for g in games if g.played and team in (g.home, g.away)]
    played.sort(key=lambda g: (g.date, g.time))
    return played[-n:]


def next_game(games: list[GameRef], team: str) -> GameRef | None:
    upcoming = [g for g in games if not g.played and team in (g.home, g.away)]
    upcoming.sort(key=lambda g: (g.date, g.time))
    return upcoming[0] if upcoming else None


def load_game(f: Fetcher, ref: GameRef) -> Game:
    """Matcher äldre än tre dygn cachas för alltid; nyare kan få rättade protokoll."""
    game_id = ref.game_id
    try:
        old = (datetime.date.today() - datetime.date.fromisoformat(ref.date)).days > 3
    except ValueError:
        old = False
    age = None if old else 3600
    g = parse_game(f.get(f"/Game/Events/{game_id}", max_age=age), game_id)
    try:
        for i, lu in enumerate(parse_lineups(f.get(f"/Game/LineUps/{game_id}", max_age=age))):
            key = g.home_abbr if lu.team == g.home else g.away_abbr if lu.team == g.away else (
                g.home_abbr if i == 0 else g.away_abbr)
            g.lineups[key] = lu
    except Exception as e:  # uppställning saknas i vissa serier
        print(f"  (ingen laguppställning för match {game_id}: {e})")
    return g
