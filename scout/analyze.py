"""Räknar fram en scoutingrapport om ett lag ur dess senaste matcher."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .parse import Game

INFRACTIONS_SV = {
    "tripping": "Fällning", "hooking": "Hakning", "holding": "Fasthållning",
    "holding the stick": "Fasthållning av klubba", "slashing": "Slashing",
    "interference": "Interference", "roughing": "Ruffning", "high sticking": "Hög klubba",
    "high-sticking": "Hög klubba", "crosschecking": "Crosschecking",
    "cross-checking": "Crosschecking", "boarding": "Boarding", "charging": "Charging",
    "elbowing": "Armbåge", "delay of game": "Fördröjning av spelet",
    "too many players": "För många spelare på isen",
    "too many men": "För många spelare på isen",
    "too many players on the ice": "För många spelare på isen",
    "team penalty": "Lagstraff",
    "unsportsmanlike conduct": "Osportsligt uppträdande", "misconduct": "Personligt straff",
    "game misconduct": "Matchstraff (GM)", "match penalty": "Matchstraff",
    "kneeing": "Knä", "checking to the head": "Tackling mot huvudet",
    "illegal check to the head": "Tackling mot huvudet", "diving": "Filmning",
    "embellishment": "Filmning", "fighting": "Slagsmål", "spearing": "Spjutning",
    "butt-ending": "Klubbände", "checking from behind": "Tackling bakifrån",
    "clipping": "Clipping", "head-butting": "Skalle", "kicking": "Sparkning",
    "abuse of officials": "Ovårdat uppträdande mot domare",
    "illegal equipment": "Otillåten utrustning", "broken stick": "Bruten klubba",
    "closing hand on the puck": "Stängd hand om pucken",
    "throwing the stick": "Kastad klubba", "bench minor": "Lagstraff",
}

UNIT_SV = {"1st Line": "Kedja 1", "2nd Line": "Kedja 2", "3rd Line": "Kedja 3",
           "4th Line": "Kedja 4", "5th Line": "Kedja 5", "Goalies": "Målvakter",
           "Extra Players": "Extraspelare"}


def sv_infraction(s: str) -> str:
    return INFRACTIONS_SV.get(s.strip().lower(), s.strip() or "Okänd")


def mmss(secs: float) -> str:
    secs = int(round(secs))
    return f"{secs // 60}:{secs % 60:02d}"


# ---------------------------------------------------------------- dataklasser

@dataclass
class PlayerStat:
    name: str
    num: int | None = None
    pos: str = ""
    unit: str = ""
    gp: int = 0
    goals: int = 0
    assists: int = 0
    pp_goals: int = 0
    pp_assists: int = 0
    sh_points: int = 0
    gwg: int = 0
    plus: int = 0
    minus: int = 0
    pim: int = 0
    penalties: int = 0
    points_by_game: dict = field(default_factory=dict)  # game_id -> poäng

    @property
    def points(self) -> int:
        return self.goals + self.assists

    @property
    def pp_points(self) -> int:
        return self.pp_goals + self.pp_assists

    @property
    def plus_minus(self) -> int:
        return self.plus - self.minus


@dataclass
class GameSummary:
    game_id: int
    date: str
    opponent: str
    home: bool
    gf: int
    ga: int
    overtime: bool
    sf: int
    sa: int
    pim: int

    @property
    def result(self) -> str:
        if self.gf > self.ga:
            return "VÖ" if self.overtime else "V"
        return "FÖ" if self.overtime else "F"


@dataclass
class Insight:
    kind: str     # "hot" = styrka att se upp med, "chans" = svaghet att utnyttja, "info"
    title: str
    text: str
    weight: float = 1.0


@dataclass
class Report:
    team: str
    league: str
    games: list[GameSummary]
    players: list[PlayerStat]
    goalies: list[dict]
    periods: dict
    buckets: dict
    strength_for: Counter
    strength_against: Counter
    pp: dict
    pk: dict
    penalties_by_type: Counter
    penalties_by_period: Counter
    penalized_players: list[PlayerStat]
    units: list[dict]
    latest_lineup: list[dict]
    coach: str
    situations: dict
    insights: list[Insight]
    totals: dict


# ---------------------------------------------------------------- analys

def _period_secs(period, secs: int) -> int | None:
    if isinstance(period, int) and 1 <= period <= 3:
        return secs - (period - 1) * 1200
    return None


def _strength_kind(tokens: list[str]) -> str:
    t = [x.upper() for x in tokens]
    if any(x.startswith("PS") for x in t):
        return "Straff"
    if any(x.startswith("PP") for x in t):
        return "PP"
    if any(x.startswith("SH") for x in t):
        return "SH"
    if "EN" in t or "ENG" in t:
        return "Tom bur"
    return "5 mot 5"


def _goalie_out(game: Game, team: str, secs: int) -> bool:
    state = False
    for m in sorted(game.misc, key=lambda m: m.secs):
        if m.team != team or m.kind not in ("GK In", "GK Out"):
            continue
        if m.secs > secs:
            break
        if m.secs == secs and m.kind == "GK Out" and secs >= 3600:
            break
        state = m.kind == "GK Out"
    return state


def _minor_count(pens, team: str, secs: int) -> int:
    return sum(1 for p in pens if p.team == team and p.secs == secs and p.minutes in (2, 4, 5))


def analyze(team: str, games: list[Game], league: str = "") -> Report:
    players: dict[str, PlayerStat] = {}
    goalies: dict[str, dict] = {}
    periods = {p: {"gf": 0, "ga": 0, "sf": 0, "sa": 0} for p in ("1", "2", "3", "ÖT")}
    buckets = {b: {"gf": 0, "ga": 0} for b in ("0–5", "5–10", "10–15", "15–20")}
    s_for, s_against = Counter(), Counter()
    pp = {"opps": 0, "goals": 0, "against_sh": 0}
    pk = {"opps": 0, "against": 0, "sh_goals": 0}
    pen_type, pen_period = Counter(), Counter()
    unit_stats = defaultdict(lambda: {"gf": 0, "ga": 0, "goals": 0, "points": 0, "games": 0})
    summaries: list[GameSummary] = []
    sit = {"first_goal": {"w": 0, "l": 0}, "conceded_first": {"w": 0, "l": 0},
           "lead_after_2": {"w": 0, "l": 0}, "trail_after_2": {"w": 0, "l": 0},
           "tied_after_2": {"w": 0, "l": 0}, "comebacks": 0, "blown_leads": 0,
           "pulls": [], "timeouts": [], "one_goal": {"w": 0, "l": 0}}
    coach = ""
    latest_lineup: list[dict] = []

    def player(name: str, num=None) -> PlayerStat:
        p = players.get(name)
        if p is None:
            p = players[name] = PlayerStat(name, num)
        if num is not None:
            p.num = num
        return p

    for g in sorted(games, key=lambda x: x.date):
        home = g.home == team
        A = g.home_abbr if home else g.away_abbr
        B = g.away_abbr if home else g.home_abbr
        gf, ga = (g.home_goals, g.away_goals) if home else (g.away_goals, g.home_goals)
        my_st, op_st = (g.home_stats, g.away_stats) if home else (g.away_stats, g.home_stats)
        won = gf > ga
        summaries.append(GameSummary(g.game_id, g.date, g.away if home else g.home, home,
                                     gf, ga, g.overtime, my_st.shots, op_st.shots, my_st.pim))
        if abs(gf - ga) == 1:
            sit["one_goal"]["w" if won else "l"] += 1

        # Laguppställning: nummer -> namn, enhet, position
        lu = g.lineups.get(A)
        num_map: dict[int, tuple[str, str, str]] = {}
        if lu:
            coach = lu.head_coach or coach
            for lp in lu.players:
                if lp.num is not None:
                    num_map[lp.num] = (lp.name, lp.unit, lp.pos)
                if lp.pos == "G":
                    continue
                ps = player(lp.name, lp.num)
                ps.gp += 1
                ps.pos, ps.unit = lp.pos, lp.unit
            for unit in {lp.unit for lp in lu.players if "Line" in lp.unit}:
                unit_stats[unit]["games"] += 1

        # Perioder och skott
        for i, (h, a) in enumerate(g.periods):
            key = str(i + 1) if i < 3 else "ÖT"
            if key == "ÖT" and i > 3:
                continue  # straffläggning räknas inte som period
            mine, theirs = (h, a) if home else (a, h)
            periods[key]["gf"] += mine
            periods[key]["ga"] += theirs
        for i, s in enumerate(my_st.shots_by_period[:3]):
            periods[str(i + 1)]["sf"] += s
        for i, s in enumerate(op_st.shots_by_period[:3]):
            periods[str(i + 1)]["sa"] += s

        # Mål
        goals = sorted([x for x in g.goals if x.period != "SO"], key=lambda x: x.secs)
        my_score = op_score = 0
        first_set = False
        led = trailed = False
        winning_goal_no = ga + 1 if won else None
        for x in goals:
            ours = x.team == A
            kind = _strength_kind(x.strength)
            if kind == "5 mot 5" and _goalie_out(g, B if ours else A, x.secs):
                kind = "Tom bur"
            if ours:
                my_score += 1
                s_for[kind] += 1
            else:
                op_score += 1
                s_against[kind] += 1
            if not first_set:
                sit["first_goal" if ours else "conceded_first"]["w" if won else "l"] += 1
                first_set = True
            if my_score > op_score:
                led = True
            if my_score < op_score:
                trailed = True

            ps_ = _period_secs(x.period, x.secs)
            if ps_ is not None:
                b = list(buckets)[min(ps_ // 300, 3)]
                buckets[b]["gf" if ours else "ga"] += 1

            if ours:
                if kind == "PP":
                    pp["goals"] += 1
                if kind == "SH":
                    pk["sh_goals"] += 1
                sc = player(x.scorer[1], x.scorer[0])
                sc.goals += 1
                sc.points_by_game[g.game_id] = sc.points_by_game.get(g.game_id, 0) + 1
                if kind == "PP":
                    sc.pp_goals += 1
                if kind == "SH":
                    sc.sh_points += 1
                if won and winning_goal_no and my_score == winning_goal_no:
                    sc.gwg += 1
                for an, aname in x.assists:
                    ap = player(aname, an)
                    ap.assists += 1
                    ap.points_by_game[g.game_id] = ap.points_by_game.get(g.game_id, 0) + 1
                    if kind == "PP":
                        ap.pp_assists += 1
                    if kind == "SH":
                        ap.sh_points += 1
                if x.scorer[0] in num_map:
                    unit = num_map[x.scorer[0]][1]
                    if "Line" in unit:
                        unit_stats[unit]["goals"] += 1
                for n in [x.scorer[0]] + [a[0] for a in x.assists]:
                    if n in num_map and "Line" in num_map[n][1]:
                        unit_stats[num_map[n][1]]["points"] += 1
            else:
                if kind == "PP":
                    pk["against"] += 1
                if kind == "SH":
                    pp["against_sh"] += 1

            # Plus/minus och kedjor på isen (inte powerplaymål)
            on_ice = x.pos if ours else x.neg
            if kind not in ("PP", "Straff"):
                units_on = Counter()
                for n in on_ice:
                    if n not in num_map:
                        continue
                    name, unit, pos = num_map[n]
                    if pos == "G":
                        continue
                    if ours:
                        player(name, n).plus += 1
                    else:
                        player(name, n).minus += 1
                    if "Line" in unit and pos == "F":
                        units_on[unit] += 1
                if kind == "5 mot 5":
                    for unit, c in units_on.items():
                        if c >= 2:
                            unit_stats[unit]["gf" if ours else "ga"] += 1

        if won and trailed:
            sit["comebacks"] += 1
        if not won and led:
            sit["blown_leads"] += 1

        # Ställning efter två perioder
        if len(g.periods) >= 2:
            h2 = sum(p[0] for p in g.periods[:2])
            a2 = sum(p[1] for p in g.periods[:2])
            m2, o2 = (h2, a2) if home else (a2, h2)
            key = "lead_after_2" if m2 > o2 else "trail_after_2" if m2 < o2 else "tied_after_2"
            sit[key]["w" if won else "l"] += 1

        # Utvisningar och PP-lägen
        for p in g.penalties:
            if p.team == A:
                pen_type[sv_infraction(p.infraction)] += 1
                pen_period[str(p.period) if p.period in (1, 2, 3) else "ÖT"] += 1
                if p.player[0] is not None:  # lagstraff har inget nummer
                    pl = player(p.player[1], p.player[0])
                    pl.pim += p.minutes
                    pl.penalties += 1
        for secs in sorted({p.secs for p in g.penalties}):
            net = _minor_count(g.penalties, B, secs) - _minor_count(g.penalties, A, secs)
            if net > 0:
                pp["opps"] += 1
            elif net < 0:
                pk["opps"] += 1

        # Målvakter
        for gl in g.goalies:
            if gl.team != A:
                continue
            d = goalies.setdefault(gl.player[1], {"name": gl.player[1], "num": gl.player[0],
                                                   "gp": 0, "starts": 0, "saves": 0, "shots": 0})
            d["gp"] += 1
            d["saves"] += gl.saves
            d["shots"] += gl.shots
        for m in g.misc:
            if m.team == A and m.kind == "GK In" and m.secs == 0 and m.player:
                if m.player[1] in goalies:
                    goalies[m.player[1]]["starts"] += 1

        # Målvaktsbyten sent och timeouts
        for m in g.misc:
            if m.team != A:
                continue
            if m.kind == "GK Out" and 2700 <= m.secs < 3600:
                before = [x for x in goals if x.secs <= m.secs]
                diff = sum(1 for x in before if x.team == A) - sum(1 for x in before if x.team == B)
                if diff < 0:
                    sit["pulls"].append({"left": 3600 - m.secs, "diff": diff, "game": g.game_id})
            if m.kind == "TO":
                before = [x for x in goals if x.secs <= m.secs]
                diff = sum(1 for x in before if x.team == A) - sum(1 for x in before if x.team == B)
                sit["timeouts"].append({"secs": m.secs, "diff": diff})

    # Senaste laguppställning med produktion
    last = max(games, key=lambda x: x.date) if games else None
    if last:
        A = last.abbr(team)
        lu = last.lineups.get(A)
        if lu:
            units: dict[str, list] = {}
            for lp in lu.players:
                units.setdefault(lp.unit, []).append(lp)
            for unit, lps in units.items():
                rows = []
                for lp in lps:
                    ps = players.get(lp.name)
                    gd = goalies.get(lp.name)
                    rows.append({"num": lp.num, "name": lp.name, "pos": lp.pos,
                                 "points": ps.points if ps else 0,
                                 "goals": ps.goals if ps else 0,
                                 "pm": ps.plus_minus if ps else 0,
                                 "sv": (gd["saves"] / gd["shots"]) if gd and gd["shots"] else None})
                latest_lineup.append({"unit": UNIT_SV.get(unit, unit), "players": rows})

    n = len(summaries) or 1
    skaters = [p for p in players.values() if p.pos != "G" and p.name not in goalies]
    skaters.sort(key=lambda p: (-p.points, -p.goals, -p.pp_points, p.name))
    penalized = sorted([p for p in skaters if p.pim], key=lambda p: (-p.pim, -p.penalties))

    units = []
    for unit in sorted(unit_stats):
        u = unit_stats[unit]
        units.append({"unit": UNIT_SV.get(unit, unit), **u})

    gl_list = sorted(goalies.values(), key=lambda d: -d["shots"])
    for d in gl_list:
        d["sv"] = d["saves"] / d["shots"] if d["shots"] else None
        d["gaa"] = (d["shots"] - d["saves"]) / d["gp"] if d["gp"] else None

    totals = {
        "gp": len(summaries),
        "w": sum(1 for s in summaries if s.gf > s.ga),
        "l": sum(1 for s in summaries if s.gf < s.ga),
        "otw": sum(1 for s in summaries if s.result == "VÖ"),
        "otl": sum(1 for s in summaries if s.result == "FÖ"),
        "gf": sum(s.gf for s in summaries), "ga": sum(s.ga for s in summaries),
        "sf": sum(s.sf for s in summaries), "sa": sum(s.sa for s in summaries),
        "pim": sum(s.pim for s in summaries),
        "has_on_ice": any(x.pos or x.neg for g in games for x in g.goals),
    }
    totals.update({
        "gf_pg": totals["gf"] / n, "ga_pg": totals["ga"] / n,
        "sf_pg": totals["sf"] / n, "sa_pg": totals["sa"] / n,
        "pim_pg": totals["pim"] / n,
        "sh_pct": totals["gf"] / totals["sf"] if totals["sf"] else None,
        "sv_pct": 1 - totals["ga"] / totals["sa"] if totals["sa"] else None,
    })
    pp["pct"] = pp["goals"] / pp["opps"] if pp["opps"] else None
    pk["pct"] = 1 - pk["against"] / pk["opps"] if pk["opps"] else None

    rep = Report(team, league, summaries, skaters, gl_list, periods, buckets, s_for, s_against,
                 pp, pk, pen_type, pen_period, penalized, units, latest_lineup, coach, sit, [],
                 totals)
    rep.insights = build_insights(rep)
    return rep


# ---------------------------------------------------------------- insikter

def _pct(x: float | None) -> str:
    return "–" if x is None else f"{x * 100:.0f} %"


def build_insights(r: Report) -> list[Insight]:
    ins: list[Insight] = []
    t, n = r.totals, max(r.totals["gp"], 1)

    # Farligaste spelarna
    top = [p for p in r.players if p.points > 0][:3]
    if top:
        parts = [f"{p.name} (#{p.num}) {p.points} p ({p.goals}+{p.assists})" for p in top]
        ins.append(Insight("hot", "Farligaste spelarna",
                           "Mest poäng senaste matcherna: " + ", ".join(parts) + ".", 10))

    # Formstarka
    last3 = [s.game_id for s in r.games[-3:]]
    hot = [p for p in r.players if sum(p.points_by_game.get(g, 0) for g in last3) >= 4]
    if hot:
        txt = ", ".join(f"{p.name} ({sum(p.points_by_game.get(g, 0) for g in last3)} p)"
                        for p in hot[:3])
        ins.append(Insight("hot", "I form just nu", f"{txt} på de tre senaste matcherna.", 8))

    # Powerplay
    if r.pp["opps"] >= 6 and r.pp["pct"] is not None:
        spec = sorted([p for p in r.players if p.pp_points], key=lambda p: -p.pp_points)[:3]
        who = (" Nyckelspelare i PP: " + ", ".join(f"{p.name} ({p.pp_points} p)" for p in spec) + ".") if spec else ""
        if r.pp["pct"] >= 0.22:
            ins.append(Insight("hot", "Farligt powerplay",
                               f"PP {_pct(r.pp['pct'])} ({r.pp['goals']} mål på {r.pp['opps']} lägen). "
                               f"Disciplin är avgörande, undvik onödiga utvisningar.{who}", 9))
        elif r.pp["pct"] <= 0.12:
            ins.append(Insight("chans", "Svagt powerplay",
                               f"Bara {_pct(r.pp['pct'])} i PP ({r.pp['goals']}/{r.pp['opps']}). "
                               f"Deras PP är inget stort hot.{who}", 5))
    # Boxplay
    if r.pk["opps"] >= 6 and r.pk["pct"] is not None:
        if r.pk["pct"] <= 0.78:
            ins.append(Insight("chans", "Läckande boxplay",
                               f"Boxplay {_pct(r.pk['pct'])}: släppt in {r.pk['against']} mål på "
                               f"{r.pk['opps']} lägen i numerärt underläge. Vårt PP kan avgöra.", 9))
        elif r.pk["pct"] >= 0.88:
            ins.append(Insight("hot", "Starkt boxplay",
                               f"Boxplay {_pct(r.pk['pct'])} ({r.pk['against']} insläppta på "
                               f"{r.pk['opps']}). Räkna inte med att PP avgör.", 6))

    # Disciplin
    if t["pim_pg"] >= 10 or (r.penalties_by_type and sum(r.penalties_by_type.values()) / n >= 4.5):
        common = ", ".join(f"{k} ({v})" for k, v in r.penalties_by_type.most_common(3))
        who = ", ".join(f"{p.name} ({p.pim} min)" for p in r.penalized_players[:3])
        ins.append(Insight("chans", "Drar på sig utvisningar",
                           f"{t['pim_pg']:.1f} utvisningsminuter per match. Vanligast: {common}. "
                           f"Mest utvisade: {who}. Spela med fart och tvinga dem att haka.", 8))

    # Perioder
    diffs = {p: v["gf"] - v["ga"] for p, v in r.periods.items() if p != "ÖT"}
    if diffs:
        best = max(diffs, key=diffs.get)
        worst = min(diffs, key=diffs.get)
        b, w = r.periods[best], r.periods[worst]
        if diffs[best] >= 3:
            ins.append(Insight("hot", f"Starka i period {best}",
                               f"Målskillnad {b['gf']}–{b['ga']} i period {best}.", 6))
        if diffs[worst] <= -3:
            ins.append(Insight("chans", f"Svaga i period {worst}",
                               f"Målskillnad {w['gf']}–{w['ga']} i period {worst}. Tryck på där.", 7))

    # Tidsmönster
    tot_ga = sum(v["ga"] for v in r.buckets.values())
    tot_gf = sum(v["gf"] for v in r.buckets.values())
    if tot_ga >= 6:
        late = r.buckets["15–20"]["ga"] / tot_ga
        early = r.buckets["0–5"]["ga"] / tot_ga
        if late >= 0.35:
            ins.append(Insight("chans", "Släpper in i slutet av perioder",
                               f"{_pct(late)} av insläppta mål kommer de sista 5 minuterna av en period.", 7))
        if early >= 0.35:
            ins.append(Insight("chans", "Sega starter",
                               f"{_pct(early)} av insläppta mål kommer de första 5 minuterna av en period. "
                               f"Gå hårt ut.", 7))
    if tot_gf >= 6 and r.buckets["15–20"]["gf"] / tot_gf >= 0.35:
        ins.append(Insight("hot", "Avslutar perioder starkt",
                           f"{_pct(r.buckets['15–20']['gf'] / tot_gf)} av deras mål kommer de sista 5 minuterna.", 6))

    # Målvakt
    if r.goalies:
        g1 = r.goalies[0]
        if g1["sv"] is not None and g1["gp"] >= 2:
            if g1["sv"] >= 0.920:
                ins.append(Insight("hot", "Het målvakt",
                                   f"{g1['name']} har {g1['sv']:.3f} i räddningsprocent på {g1['gp']} matcher.", 7))
            elif g1["sv"] <= 0.885:
                ins.append(Insight("chans", "Sårbar målvakt",
                                   f"{g1['name']} har bara {g1['sv']:.3f} i räddningsprocent. "
                                   f"Skjut mycket och sök returer.", 8))

    # Skott
    if t["sa_pg"] - t["sf_pg"] >= 5:
        ins.append(Insight("chans", "Blir utskjutna",
                           f"De släpper till {t['sa_pg']:.1f} skott per match men skjuter bara {t['sf_pg']:.1f}.", 6))
    elif t["sf_pg"] - t["sa_pg"] >= 5:
        ins.append(Insight("hot", "Dominerar skottstatistiken",
                           f"{t['sf_pg']:.1f} skott för mot {t['sa_pg']:.1f} emot per match.", 6))

    # Kedjeberoende
    total_goals = sum(u["goals"] for u in r.units)
    if total_goals >= 6 and r.units:
        top_u = max(r.units, key=lambda u: u["goals"])
        share = top_u["goals"] / total_goals
        if share >= 0.45:
            ins.append(Insight("chans", f"Beroende av {top_u['unit'].lower()}",
                               f"{top_u['unit']} står för {_pct(share)} av målen. "
                               f"Matcha er bästa defensiva femma mot den.", 7))
        elif share <= 0.32:
            ins.append(Insight("hot", "Bred poängproduktion",
                               "Målen är jämnt fördelade över kedjorna. Det går inte att stänga en enskild femma.", 5))

    # Matchsituationer
    s = r.situations
    if s["comebacks"] >= 2:
        ins.append(Insight("hot", "Ger aldrig upp",
                           f"{s['comebacks']} vinster efter att ha legat under.", 5))
    if s["blown_leads"] >= 2:
        ins.append(Insight("chans", "Tappar ledningar",
                           f"{s['blown_leads']} förluster trots att de ledde. Fortsätt pressa även i underläge.", 6))
    cf = s["conceded_first"]
    if cf["w"] + cf["l"] >= 3 and cf["l"] / (cf["w"] + cf["l"]) >= 0.75:
        ins.append(Insight("chans", "Första målet är viktigt",
                           f"När de släpper in första målet har de förlorat {cf['l']} av {cf['w'] + cf['l']}.", 7))
    if s["pulls"]:
        avg = sum(p["left"] for p in s["pulls"]) / len(s["pulls"])
        ins.append(Insight("info", "Målvaktsbyte i underläge",
                           f"Tar ut målvakten i snitt med {mmss(avg)} kvar ({len(s['pulls'])} gånger).", 3))

    ins.sort(key=lambda i: -i.weight)
    return ins
