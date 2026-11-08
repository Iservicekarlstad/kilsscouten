"""Tolkar HTML från stats.swehockey.se till dataklasser.

Sajten genereras av "Teamsport Manager" och har delvis trasig nästling
(<td> inuti <td>), så vi delar på '<tr' och '<td' i stället för att
lita på en strikt HTML-parser.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------- hjälpare

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s)


def clean(s: str) -> str:
    s = re.sub(r"<br\s*/?>", " ", s)
    s = re.sub(r"<[^>]+>", " ", s)
    return " ".join(html.unescape(s).split())


def _cells(row: str) -> list[str]:
    return ["<td" + c for c in row.split("<td")[1:]]


def to_secs(mmss: str) -> int:
    m, s = mmss.split(":")
    return int(m) * 60 + int(s)


def split_player(text: str) -> tuple[int | None, str]:
    """'21. Puistola, Patrik' -> (21, 'Patrik Puistola')"""
    m = re.match(r"\s*(\d+)\.\s*(.+)", text)
    if not m:
        return None, text.strip()
    num, rest = int(m.group(1)), m.group(2).strip()
    if "," in rest:
        last, first = rest.split(",", 1)
        rest = f"{first.strip()} {last.strip()}"
    return num, rest


# ---------------------------------------------------------------- ligor

@dataclass
class League:
    league_id: int
    name: str
    group: str


def parse_leagues(page: str) -> list[League]:
    s = _norm(page)
    out, seen, group = [], set(), ""
    for m in re.finditer(
        r'<h\d[^>]*>(.*?)</h\d>|<a[^>]+href="/ScheduleAndResults/\w+/(\d+)"[^>]*>(.*?)</a>', s
    ):
        if m.group(1) is not None:
            group = clean(m.group(1))
            continue
        lid, name = int(m.group(2)), clean(m.group(3))
        if name and lid not in seen:
            seen.add(lid)
            out.append(League(lid, name, group))
    return out


# ---------------------------------------------------------------- spelschema

@dataclass
class GameRef:
    game_id: int | None
    date: str
    time: str
    home: str
    away: str
    home_goals: int | None = None
    away_goals: int | None = None
    periods: list[tuple[int, int]] = field(default_factory=list)
    venue: str = ""

    @property
    def played(self) -> bool:
        return self.game_id is not None and self.home_goals is not None


def parse_schedule(page: str) -> list[GameRef]:
    s = _norm(page)
    games: list[GameRef] = []
    cur_date = ""
    for row in s.split("<tr")[1:]:
        m = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", row)
        if m:
            cur_date = m.group(1)
        cells = _cells(row)
        texts = [clean(c) for c in cells]
        tm = re.search(r"\b(\d{2}:\d{2})\b", clean(row))
        time_ = tm.group(1) if tm else ""

        idx = next((i for i, c in enumerate(cells) if "Game/Events/" in c), None)
        if idx is not None and idx > 0:
            gid = int(re.search(r"Game/Events/(\d+)", cells[idx]).group(1))
            teams = texts[idx - 1]
            if " - " not in teams:
                continue
            home, away = [t.strip() for t in teams.split(" - ", 1)]
            res = re.match(r"(\d+)\s*-\s*(\d+)", texts[idx])
            periods = []
            if idx + 1 < len(texts):
                periods = [(int(a), int(b)) for a, b in re.findall(r"(\d+)-(\d+)", texts[idx + 1])]
            venue = texts[-1] if len(texts) > idx + 2 else ""
            g = GameRef(gid, cur_date, time_, home, away, venue=venue, periods=periods)
            if res:
                g.home_goals, g.away_goals = int(res.group(1)), int(res.group(2))
            games.append(g)
            continue

        # Kommande match (ingen länk ännu)
        for t in texts:
            if " - " in t and not re.match(r"^\d", t):
                home, away = [x.strip() for x in t.split(" - ", 1)]
                games.append(GameRef(None, cur_date, time_, home, away, venue=texts[-1] if texts else ""))
                break
    return games


# ---------------------------------------------------------------- matchhändelser

@dataclass
class Goal:
    period: int | str
    secs: int
    team: str            # förkortning, t.ex. "FRÖ"
    score: tuple[int, int]
    strength: list[str]  # t.ex. ["PP1"], ["EQ"], ["SH1"], ["EN"]
    scorer: tuple[int | None, str]
    assists: list[tuple[int | None, str]]
    pos: list[int]
    neg: list[int]


@dataclass
class Penalty:
    period: int | str
    secs: int
    team: str
    minutes: int
    player: tuple[int | None, str]
    infraction: str


@dataclass
class Misc:
    period: int | str
    secs: int
    team: str
    kind: str            # "GK In", "GK Out", "TO", "Powerbreak", ...
    player: tuple[int | None, str] | None = None


@dataclass
class GoalieLine:
    team: str
    player: tuple[int | None, str]
    saves: int
    shots: int


@dataclass
class TeamStats:
    shots: int = 0
    shots_by_period: list[int] = field(default_factory=list)
    saves: int = 0
    pim: int = 0
    pp_pct: float | None = None
    pp_time: str = ""


@dataclass
class Game:
    game_id: int
    date: str
    league: str
    home: str
    away: str
    home_abbr: str
    away_abbr: str
    home_goals: int
    away_goals: int
    periods: list[tuple[int, int]]
    home_stats: TeamStats
    away_stats: TeamStats
    goals: list[Goal] = field(default_factory=list)
    penalties: list[Penalty] = field(default_factory=list)
    misc: list[Misc] = field(default_factory=list)
    goalies: list[GoalieLine] = field(default_factory=list)
    lineups: dict = field(default_factory=dict)   # abbr -> Lineup

    def abbr(self, team_name: str) -> str:
        return self.home_abbr if team_name == self.home else self.away_abbr

    @property
    def overtime(self) -> bool:
        return len(self.periods) > 3


PERIOD_MAP = {"1st period": 1, "2nd period": 2, "3rd period": 3}


def _period_of(label: str) -> int | str:
    label = label.strip()
    if label in PERIOD_MAP:
        return PERIOD_MAP[label]
    low = label.lower()
    if "overtime" in low:
        return 4
    if "shot" in low or "shootout" in low:
        return "SO"
    return label


def _pct(s: str) -> float | None:
    m = re.search(r"([\d,\.]+)\s*%", s)
    return float(m.group(1).replace(",", ".")) if m else None


def parse_game(page: str, game_id: int) -> Game:
    s = _norm(page)
    title = clean(re.search(r"<title>(.*?)</title>", s).group(1))
    abbr_m = re.match(r"(.+?) - (.+?) \(", title)
    home_abbr, away_abbr = abbr_m.group(1).strip(), abbr_m.group(2).strip()

    names = clean(re.search(r'<th class="tdTitle"[^>]*><h2>(.*?)</h2>', s).group(1))
    home, away = [x.strip() for x in names.split(" - ", 1)]
    h3 = [clean(x) for x in re.findall(r"<h3[^>]*>(.*?)</h3>", s)]
    date = h3[0][:10] if h3 else ""
    league = h3[1] if len(h3) > 1 else ""

    # Huvudstatistik: varje etikett förekommer två gånger, hemma (vänster) sedan borta.
    hs, as_ = TeamStats(), TeamStats()
    for label in ("Shots", "Saves", "PIM", "PP"):
        found = re.findall(
            r'<td class="tdOdd ?">\s*' + label + r"\s*</td><td[^>]*><strong>([^<]*)</strong></td>"
            r"<td[^>]*>\s*\(([^)]*)\)",
            s,
        )
        for st, (val, extra) in zip((hs, as_), found[:2]):
            if label == "Shots":
                st.shots = int(val)
                st.shots_by_period = [int(x) for x in re.findall(r"\d+", extra)]
            elif label == "Saves":
                st.saves = int(val)
            elif label == "PIM":
                st.pim = int(val)
            elif label == "PP":
                st.pp_pct, st.pp_time = _pct(val), extra.strip()

    score = re.search(r'font-weight: bold;">\s*(\d+)\s*-\s*(\d+)\s*</div>\s*<div>\s*\(([^)]*)\)', s)
    hg, ag = int(score.group(1)), int(score.group(2))
    periods = [(int(a), int(b)) for a, b in re.findall(r"(\d+)-(\d+)", score.group(3))]

    g = Game(game_id, date, league, home, away, home_abbr, away_abbr, hg, ag, periods, hs, as_)

    actions = s.find("<h2>Actions</h2>")
    period: int | str | None = None
    for row in s[actions:].split("<tr")[1:]:
        hm = re.search(r"<h3>(.*?)</h3>", row)
        if hm:
            label = clean(hm.group(1))
            period = None if "Goalkeeper" in label else _period_of(label)
            continue
        cells = _cells(row)
        texts = [clean(c) for c in cells]
        if len(texts) < 4:
            continue

        if period is None:  # målvaktssammanfattning
            if len(texts) >= 5 and texts[2] in (home_abbr, away_abbr):
                sm = re.search(r"\((\d+)/(\d+)\)", texts[4])
                if sm:
                    g.goalies.append(GoalieLine(texts[2], split_player(texts[3]),
                                                int(sm.group(1)), int(sm.group(2))))
            continue

        if not re.match(r"\d+:\d+$", texts[0]):
            continue
        secs, kind, team = to_secs(texts[0]), texts[1], texts[2]

        gm = re.match(r"(\d+)-(\d+)\s*\(([^)]*)\)", kind)
        if gm:
            pcell = cells[3]
            scorer = split_player(clean(pcell.split("<span")[0]))
            assists = [split_player(clean(a)) for a in
                       re.findall(r'title="[^"]*Assists[^"]*">(.*?)</div>', pcell)]
            rest = texts[4] if len(texts) > 4 else ""
            pos = re.search(r"Pos\. Part\.:([\d ,]*)", rest)
            neg = re.search(r"Neg\. Part\.:([\d ,]*)", rest)
            g.goals.append(Goal(
                period, secs, team, (int(gm.group(1)), int(gm.group(2))),
                [x for x in re.split(r"[ ,]+", gm.group(3)) if x],
                scorer, assists,
                [int(x) for x in re.findall(r"\d+", pos.group(1))] if pos else [],
                [int(x) for x in re.findall(r"\d+", neg.group(1))] if neg else [],
            ))
            continue

        pm = re.match(r"(\d+)\s*min", kind)
        if pm:
            infr = texts[4] if len(texts) > 4 else ""
            infr = re.sub(r"\(\s*\d+:\d+\s*-\s*\d+:\d+\s*\)", "", infr).strip()
            g.penalties.append(Penalty(period, secs, team, int(pm.group(1)),
                                       split_player(texts[3]), infr))
            continue

        player = split_player(texts[3]) if re.match(r"\d+\.", texts[3]) else None
        g.misc.append(Misc(period, secs, team, kind, player))
    return g


# ---------------------------------------------------------------- laguppställning

@dataclass
class LineupPlayer:
    num: int | None
    name: str
    unit: str      # "Goalies", "1st Line", ..., "Extra Players"
    pos: str       # "G", "D", "F", "X"


@dataclass
class Lineup:
    team: str
    head_coach: str
    players: list[LineupPlayer]


def parse_lineups(page: str) -> list[Lineup]:
    s = _norm(page)
    out = []
    for sec in re.split(r'<th class="tdSubTitle"[^>]*>', s)[1:]:
        hm = re.match(r"\s*<h3>(.*?)</h3>", sec)
        if not hm or "lineUpPlayer" not in sec:
            continue
        team = re.sub(r"\s*\([^)]*\)\s*$", "", clean(hm.group(1)))
        coach = re.search(r"Head Coach:\s*</strong>\s*([^<]+)", sec)
        coach_name = split_player("0. " + coach.group(1).strip())[1] if coach else ""
        players, unit, row_i = [], "", 0
        for row in sec.split("<tr")[1:]:
            um = re.search(r"<strong>\s*(Goalies|\d\w* Line|Extra Players)\s*</strong>", row)
            if um:
                unit, row_i = um.group(1), 0
            else:
                row_i += 1
            for p in re.findall(r'<div class="lineUpPlayer[^"]*">(.*?)</div>', row):
                num, name = split_player(clean(p))
                if unit == "Goalies":
                    pos = "G"
                elif "Line" in unit:
                    # Hemmalaget visas med backar överst, bortalaget spegelvänt.
                    d_row = 0 if len(out) == 0 else 1
                    pos = "D" if row_i == d_row else "F"
                else:
                    pos = "X"
                players.append(LineupPlayer(num, name, unit, pos))
        out.append(Lineup(team, coach_name, players))
    return out
