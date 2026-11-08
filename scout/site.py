"""Bygger artifact-sidan: alla lag i serien med färdiga rapporter, sett från vårt lag.

    python3 -m scout.site            # skriver artifact/kil-scouting.html
"""
from __future__ import annotations

import datetime
import json
import re
import sys
from html import escape as e
from pathlib import Path
from zoneinfo import ZoneInfo

from . import data
from .analyze import analyze
from .fetch import Fetcher
from .matchup import head_to_head, render as render_matchup
from .report import render_body

ROOT = Path(__file__).resolve().parent.parent
LEAGUES = [21090]          # HockeyTvåan Herr Region Väst C
OUR_TEAM = "Kils AIK"
N_GAMES = 10
OUT = ROOT / "artifact" / "kil-scouting.html"

STHLM = ZoneInfo("Europe/Stockholm")
SV_DAYS = ["mån", "tis", "ons", "tors", "fre", "lör", "sön"]


def slug(name: str) -> str:
    s = name.lower().translate(str.maketrans("åäöéü", "aaoeu"))
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-") or "lag"


def nice_date(iso: str) -> str:
    try:
        d = datetime.date.fromisoformat(iso)
    except ValueError:
        return iso
    return f"{SV_DAYS[d.weekday()]} {d.day}/{d.month}"


def build(out: Path = OUT, verbose: bool = True, standalone: bool = False) -> Path:
    f = Fetcher(ROOT / ".cache", verbose=verbose)
    leagues = []
    for lid in LEAGUES:
        sched = data.schedule(f, lid)
        leagues.append({"id": lid, "name": data.league_title(f, lid) or f"Serie {lid}", "sched": sched})
    scheds = [lg["sched"] for lg in leagues]

    reports, team_league, team_sched = {}, {}, {}
    for lg in leagues:
        for team in data.teams(lg["sched"]):
            refs = data.recent_games(lg["sched"], team, N_GAMES)
            team_league[team], team_sched[team] = lg["name"], lg["sched"]
            if verbose:
                print(f"{team}: {len(refs)} matcher")
            games = [data.load_game(f, r) for r in refs]
            reports[team] = analyze(team, games, lg["name"]) if games else None

    if OUR_TEAM not in reports:
        raise SystemExit(f"{OUR_TEAM} finns inte i serierna {LEAGUES}")
    us = reports[OUR_TEAM]
    our_sched = team_sched[OUR_TEAM]

    upcoming = data.upcoming_games(our_sched, OUR_TEAM)[:3]

    teams = {}
    for team, rep in reports.items():
        tid = slug(team)
        nxt = data.next_game(team_sched[team], team)
        if rep is None:
            html = (f"<header><div class='eyebrow'>Scoutrapport · {e(team_league[team])}</div>"
                    f"<h1>{e(team)}</h1><div class='meta'>Inga spelade matcher ännu.</div></header>")
        else:
            top = ""
            if team != OUR_TEAM and us is not None:
                top = render_matchup(us, rep, head_to_head(scheds, OUR_TEAM, team))
            html = render_body(rep, nxt, extra_top=top)
        teams[tid] = {"team": team, "league": team_league[team], "html": html}

    default = slug(OUR_TEAM)
    if upcoming:
        g = upcoming[0]
        default = slug(g.away if g.home == OUR_TEAM else g.home)

    payload = {
        "our": slug(OUR_TEAM),
        "default": default,
        "updated": datetime.datetime.now(STHLM).strftime("%Y-%m-%d %H:%M"),
        "leagues": [{"name": lg["name"], "teams": [slug(t) for t in data.teams(lg["sched"])]} for lg in leagues],
        "teams": teams,
        "upcoming": [{
            "id": slug(g.away if g.home == OUR_TEAM else g.home),
            "opp": g.away if g.home == OUR_TEAM else g.home,
            "where": "Hemma" if g.home == OUR_TEAM else "Borta",
            "when": f"{nice_date(g.date)} {g.time}",
        } for g in upcoming],
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    html = standalone_page(payload) if standalone else page(payload)
    out.write_text(html, encoding="utf-8")
    if verbose:
        print(f"Skrev {out} ({out.stat().st_size // 1024} kB)")
    return out


def page(payload: dict) -> str:
    blob = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    return TEMPLATE.replace("__CSS__", CSS).replace("__DATA__", blob)


def standalone_page(payload: dict) -> str:
    """Komplett HTML-dokument för vanlig webbhosting (Netlify)."""
    head, body = page(payload).split('<div class="topbar">', 1)
    return ('<!doctype html>\n<html lang="sv"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
            '<meta name="robots" content="noindex,nofollow">'
            '<style>body{margin:0}[hidden]{display:none!important}img{max-width:100%}</style>'
            f'{head}</head><body><div class="topbar">{body}</body></html>')


TEMPLATE = """<title>Kils AIK Scoutrapporter</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700&family=Barlow:wght@400;500;600&display=swap">
<style>__CSS__</style>
<div class="topbar">
  <div class="topbar-in">
    <div class="brand"><span class="brand-mark">KIL</span><span class="brand-txt">Motståndarscouting</span></div>
    <label class="pick" for="team"><span>Lag</span><select id="team"></select></label>
  </div>
</div>
<div class="wrap">
  <div class="quick" id="quick"></div>
  <main id="report"></main>
  <p class="updated" id="updated"></p>
</div>
<script type="application/json" id="data">__DATA__</script>
<script>
(function () {
  var D = JSON.parse(document.getElementById('data').textContent);
  var sel = document.getElementById('team');
  D.leagues.forEach(function (lg) {
    var og = document.createElement('optgroup');
    og.label = lg.name;
    lg.teams.forEach(function (id) {
      var t = D.teams[id];
      og.appendChild(new Option(t.team + (id === D.our ? ' (vårt lag)' : ''), id));
    });
    sel.appendChild(og);
  });

  var quick = document.getElementById('quick');
  if (D.upcoming.length) {
    var lbl = document.createElement('span');
    lbl.className = 'quick-label';
    lbl.textContent = 'Kommande matcher';
    quick.appendChild(lbl);
    D.upcoming.forEach(function (u) {
      var a = document.createElement('a');
      a.href = '#' + u.id;
      a.className = 'qchip';
      a.dataset.id = u.id;
      var w = document.createElement('span'); w.className = 'qwhen'; w.textContent = u.when + ' · ' + u.where;
      var o = document.createElement('span'); o.className = 'qopp'; o.textContent = u.opp;
      a.appendChild(w); a.appendChild(o);
      quick.appendChild(a);
    });
  }
  var self = document.createElement('a');
  self.href = '#' + D.our; self.className = 'qchip self'; self.dataset.id = D.our;
  self.innerHTML = '<span class="qwhen">Självscouting</span><span class="qopp"></span>';
  self.querySelector('.qopp').textContent = D.teams[D.our].team;
  quick.appendChild(self);

  document.getElementById('updated').textContent =
    'Data från stats.swehockey.se, uppdaterad ' + D.updated + '.';

  function show(id) {
    if (!D.teams[id]) id = D.default;
    sel.value = id;
    document.getElementById('report').innerHTML = D.teams[id].html;
    document.title = D.teams[id].team + ' · Kils AIK Scoutrapporter';
    Array.prototype.forEach.call(quick.querySelectorAll('.qchip'), function (c) {
      c.classList.toggle('on', c.dataset.id === id);
    });
  }
  sel.addEventListener('change', function () { location.hash = sel.value; });
  window.addEventListener('hashchange', function () {
    show(location.hash.slice(1));
    window.scrollTo(0, 0);
  });
  show(location.hash.slice(1) || D.default);
})();
</script>
"""

CSS = """
/* Layout: smal toppbar med lagval, därunder en kolumn med rapportkort. Isblå neutraler, mörkblå accent. */
:root{
  --bg:#eef2f6;--surface:#ffffff;--ink:#121820;--muted:#5d6b7c;--line:#d9e0e8;
  --accent:#123c69;--accent-ink:#ffffff;--accent-soft:#dce7f3;
  --threat:#b42318;--threat-bg:#fdf0ee;--chance:#08734a;--chance-bg:#e9f7f0;--info-bg:#eef1f5;
  --for:#1d5fa8;--against:#c8372d;
  --f-display:"Barlow Condensed","Arial Narrow",Arial,sans-serif;
  --f-body:"Barlow",-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --bg:#0c1117;--surface:#141b24;--ink:#e7edf4;--muted:#93a1b2;--line:#253140;
  --accent:#7fb3ec;--accent-ink:#0c1117;--accent-soft:#1a2a3d;
  --threat:#ff8f7f;--threat-bg:#2a1714;--chance:#5fd49c;--chance-bg:#10261c;--info-bg:#18202a;
  --for:#6aa9ff;--against:#ff6f63;color-scheme:dark}}
:root[data-theme="dark"]{
  --bg:#0c1117;--surface:#141b24;--ink:#e7edf4;--muted:#93a1b2;--line:#253140;
  --accent:#7fb3ec;--accent-ink:#0c1117;--accent-soft:#1a2a3d;
  --threat:#ff8f7f;--threat-bg:#2a1714;--chance:#5fd49c;--chance-bg:#10261c;--info-bg:#18202a;
  --for:#6aa9ff;--against:#ff6f63;color-scheme:dark}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--ink);font:15px/1.5 var(--f-body)}
body::before{content:"";position:fixed;inset:0 0 auto;height:env(safe-area-inset-top,0px);z-index:10;background:var(--accent)}
.topbar{position:sticky;top:env(safe-area-inset-top,0px);z-index:5;background:var(--accent);color:var(--accent-ink)}
.topbar-in,.wrap{max-width:1100px;margin:0 auto;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
.topbar-in{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:10px 16px;padding-block:10px}
.brand{display:flex;align-items:center;gap:10px}
.brand-mark{font:700 20px/1 var(--f-display);letter-spacing:.06em;border:2px solid currentColor;border-radius:6px;padding:4px 7px}
.brand-txt{font:600 19px/1 var(--f-display);letter-spacing:.04em;text-transform:uppercase}
.pick{display:flex;align-items:center;gap:8px;font:600 13px var(--f-display);letter-spacing:.08em;text-transform:uppercase}
.pick select{font:500 15px var(--f-body);padding:7px 10px;border-radius:8px;border:0;background:var(--surface);color:var(--ink);max-width:70vw}
.pick select:focus-visible,.qchip:focus-visible,a:focus-visible{outline:3px solid var(--for);outline-offset:2px}
.wrap{padding-block:16px 48px}
.quick{display:flex;flex-wrap:wrap;align-items:stretch;gap:8px;margin-bottom:8px}
.quick-label{width:100%;font:600 12px var(--f-display);letter-spacing:.1em;text-transform:uppercase;color:var(--muted)}
.qchip{display:flex;flex-direction:column;gap:1px;text-decoration:none;color:var(--ink);background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:7px 12px;min-width:0}
.qchip:hover{border-color:var(--accent)}
.qchip.on{background:var(--accent-soft);border-color:var(--accent)}
.qchip.self{margin-left:auto}
.qwhen{font-size:12px;color:var(--muted)}
.qopp{font:600 17px/1.15 var(--f-display);letter-spacing:.02em}
.updated{color:var(--muted);font-size:12px;margin:24px 0 0}

header{margin:18px 0 14px}
.eyebrow{text-transform:uppercase;letter-spacing:.1em;font:600 13px var(--f-display);color:var(--for)}
h1{font:700 clamp(32px,6vw,46px)/1.05 var(--f-display);margin:4px 0;text-wrap:balance;letter-spacing:.01em}
.meta{color:var(--muted)}
.next{margin-top:10px;display:inline-block;background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:6px 12px}
h2{font:700 22px/1.2 var(--f-display);margin:0 0 12px;letter-spacing:.02em;text-wrap:balance}
h3{font:600 13px var(--f-display);margin:0 0 8px;text-transform:uppercase;letter-spacing:.1em}
.hot-h{color:var(--threat)}.chans-h{color:var(--chance)}
section{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:18px;margin:14px 0;min-width:0}
section.cols2,section.kpis{background:none;border:0;padding:0}
.cols2{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}
section.cols2>div{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:18px;min-width:0}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px}
.kpi{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:12px 14px;min-width:0}
.kpi-label{font:600 12px var(--f-display);color:var(--muted);text-transform:uppercase;letter-spacing:.08em}
.kpi-value{font:700 28px/1.15 var(--f-display);margin:4px 0;font-variant-numeric:tabular-nums}
.kpi-value small{color:var(--muted);font-weight:500}.kpi-sub{font-size:12px;color:var(--muted)}
.chips{display:flex;flex-wrap:wrap;gap:3px}
.chip{display:inline-block;min-width:24px;text-align:center;font:700 12px/1.4 var(--f-display);border-radius:4px;padding:1px 3px;color:var(--surface)}
.chip.win{background:var(--chance)}.chip.loss{background:var(--against)}.chip.sm{font-size:11px}
.ins{border-radius:8px;padding:10px 14px;margin-bottom:8px}
.ins h4{margin:0 0 2px;font:700 17px/1.25 var(--f-display);letter-spacing:.02em}.ins p{margin:0}
.ins.hot{background:var(--threat-bg);box-shadow:inset 3px 0 0 var(--threat)}
.ins.chans{background:var(--chance-bg);box-shadow:inset 3px 0 0 var(--chance)}
.ins.info{background:var(--info-bg);box-shadow:inset 3px 0 0 var(--muted)}
.tw{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}
th,td{padding:6px 8px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}
table.wrap td{white-space:normal}
th{font:600 12px var(--f-display);letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
.r{text-align:right}.strong{font-weight:600}.num,.muted{color:var(--muted)}
.note{font-size:12px;color:var(--muted);margin:8px 0 0}
.dot{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:3px;background:var(--line)}
.dot.d1{background:color-mix(in srgb,var(--chance) 40%,var(--line))}
.dot.d2{background:color-mix(in srgb,var(--chance) 70%,var(--line))}.dot.d3{background:var(--chance)}
.barcell{width:40%;min-width:110px}
.bar{display:inline-block;height:10px;border-radius:3px;vertical-align:middle;margin-right:6px}
.bar.for{background:var(--for)}.bar.against{background:var(--against)}
.lineup{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
.unit h4{margin:0 0 4px;font:600 13px var(--f-display);letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.unit ul{list-style:none;margin:0;padding:0}
.unit li{display:flex;gap:6px;font-size:13px;padding:2px 0;border-bottom:1px dashed var(--line)}
.unit .num{width:24px}.unit .pn{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.unit .pos{color:var(--muted);width:14px}.unit .pts{font-weight:600}
ul.plain{list-style:none;padding:0;margin:8px 0 0}ul.plain li{padding:2px 0}
a{color:var(--for)}
footer{color:var(--muted);font-size:12px;margin-top:20px}

.matchup{border:2px solid var(--accent)}
.mu-grid{display:grid;grid-template-columns:minmax(0,1.1fr) minmax(0,1fr);gap:20px}
.mu-table th,.mu-table td{text-align:center}
.mu-table .mu-v{width:30%;font:600 18px var(--f-display);text-transform:none;letter-spacing:.01em;color:var(--ink)}
.mu-table th.mu-v{font-size:16px;white-space:normal;line-height:1.2}
.mu-table th .muted{font:500 12px var(--f-body)}
.mu-table .mu-l{color:var(--muted);font-size:13px;white-space:normal}
.mu-table td.win{color:var(--chance);background:var(--chance-bg)}
.keys{margin:0;padding-left:18px}.keys li{margin-bottom:6px}
.mu-h2h{margin-top:14px}
@media (max-width:760px){.cols2,.lineup,.mu-grid{grid-template-columns:minmax(0,1fr)}.qchip.self{margin-left:0}}
@media (prefers-reduced-motion:reduce){*{scroll-behavior:auto!important}}
"""


if __name__ == "__main__":
    # python3 -m scout.site [-q] [--netlify]   (--netlify skriver public/index.html)
    if "--netlify" in sys.argv:
        build(ROOT / "public" / "index.html", verbose="-q" not in sys.argv, standalone=True)
    else:
        build(verbose="-q" not in sys.argv)
