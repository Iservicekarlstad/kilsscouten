import unittest
from pathlib import Path

from scout.analyze import analyze
from scout.parse import parse_game, parse_leagues, parse_lineups, parse_schedule

F = Path(__file__).parent / "fixtures"


def _game():
    g = parse_game((F / "events_1109941.html").read_text(encoding="utf-8"), 1109941)
    for i, lu in enumerate(parse_lineups((F / "lineup_1109941.html").read_text(encoding="utf-8"))):
        g.lineups[g.home_abbr if i == 0 else g.away_abbr] = lu
    return g


class ParseTests(unittest.TestCase):
    def test_game_header(self):
        g = _game()
        self.assertEqual((g.home, g.away), ("Frölunda HC", "Växjö Lakers HC"))
        self.assertEqual((g.home_goals, g.away_goals), (5, 4))
        self.assertEqual(g.home_stats.shots, 25)
        self.assertEqual(g.away_stats.shots_by_period, [7, 10, 10])
        self.assertEqual(g.home_stats.pp_pct, 20.0)

    def test_goals(self):
        g = _game()
        self.assertEqual(len(g.goals), 9)
        pp = [x for x in g.goals if "PP1" in x.strength][0]
        self.assertEqual(pp.scorer, (8, "Samuel Johannesson"))
        self.assertEqual([a[1] for a in pp.assists], ["Patrik Puistola", "Filip Cederqvist"])
        self.assertEqual(pp.secs, 25 * 60 + 4)

    def test_penalties_and_goalies(self):
        g = _game()
        self.assertEqual(len(g.penalties), 7)
        self.assertEqual(g.penalties[0].infraction, "Delay of game")
        self.assertEqual(len(g.goalies), 2)

    def test_lineup_positions_home_and_away(self):
        lus = parse_lineups((F / "lineup_1109941.html").read_text(encoding="utf-8"))
        pos = {(lu.team, p.name): p.pos for lu in lus for p in lu.players}
        self.assertEqual(pos[("Frölunda HC", "Henrik Tömmernes")], "D")
        self.assertEqual(pos[("Växjö Lakers HC", "Keegan Lowe")], "D")
        self.assertEqual(pos[("Växjö Lakers HC", "Dennis Rasmussen")], "F")

    def test_schedule_and_leagues(self):
        games = parse_schedule((F / "schedule_20961.html").read_text(encoding="utf-8"))
        self.assertEqual(sum(g.played for g in games), 100)
        self.assertTrue(any(not g.played for g in games))
        leagues = parse_leagues((F / "home.html").read_text(encoding="utf-8"))
        self.assertEqual(leagues[0].name, "SHL")

    def test_hockeyettan_shorthanded(self):
        g = parse_game((F / "events_h1.html").read_text(encoding="utf-8"), 1)
        self.assertEqual(g.goals[0].strength, ["SH1"])


class UpcomingTests(unittest.TestCase):
    def test_next_game_skips_played_and_past_unreported(self):
        import datetime
        from scout.data import next_game
        from scout.parse import GameRef
        d = lambda n: (datetime.date.today() + datetime.timedelta(days=n)).isoformat()
        games = [
            GameRef(1, d(-3), "19:00", "Kils AIK", "A", 3, 1),   # spelad
            GameRef(None, d(-1), "19:00", "B", "Kils AIK"),       # gammal utan resultat
            GameRef(None, d(4), "16:00", "Kils AIK", "D"),
            GameRef(None, d(2), "19:00", "C", "Kils AIK"),
        ]
        self.assertEqual(next_game(games, "Kils AIK").home, "C")


class AnalyzeTests(unittest.TestCase):
    def test_vaxjo_single_game(self):
        r = analyze("Växjö Lakers HC", [_game()])
        self.assertEqual((r.totals["gf"], r.totals["ga"]), (4, 5))
        self.assertEqual((r.pp["opps"], r.pk["opps"]), (2, 5))
        self.assertEqual(r.pk["against"], 1)
        self.assertEqual(r.situations["blown_leads"], 1)
        self.assertEqual(len(r.situations["pulls"]), 2)
        top = {p.name: p for p in r.players}
        self.assertEqual(top["Karl Henriksson"].goals, 2)
        self.assertEqual(top["Dennis Rasmussen"].plus_minus, 2)


if __name__ == "__main__":
    unittest.main()
