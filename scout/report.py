"""Renderar en Report till en fristående, utskriftsvänlig HTML-sida."""
from __future__ import annotations

import datetime
from html import escape

from .analyze import Report, mmss

BASE = "https://stats.swehockey.se"


def _pct(x, digits=0):
    return "–" if x is None else f"{x * 100:.{digits}f} %"


def _sv(x):
    return "–" if x is None else f"{x:.3f}".lstrip("0")


def _bar(value: float, maxv: float, cls: str) -> str:
    w = 0 if not maxv else max(2, round(75 * value / maxv))  # lämna plats för siffran
    return f'<span class="bar {cls}" style="width:{w}%"></span>'


def _wl(d: dict) -> str:
    return f"{d['w']}–{d['l']}" if d["w"] + d["l"] else "–"


def render(r: Report, next_game=None) -> str:
    """Fristående HTML-dokument."""
    return f"""<!doctype html>
<html lang="sv"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Scoutrapport {escape(r.team)}</title>
<style>{CSS}</style></head>
<body><main>{render_body(r, next_game)}</main></body></html>"""


def render_body(r: Report, next_game=None, extra_top: str = "") -> str:
    """Rapportens innehåll utan dokumentskal (används även i artifact-sidan)."""
    t = r.totals
    e = escape
    dates = [g.date for g in r.games]
    span = f"{dates[0]} – {dates[-1]}" if dates else ""

    # ---------- KPI
    chips = "".join(f'<span class="chip {"win" if g.gf > g.ga else "loss"}" '
                    f'title="{e(g.date)} {e(g.opponent)} {g.gf}–{g.ga}">{g.result}</span>'
                    for g in r.games)
    kpis = [
        ("Form", f'<div class="chips">{chips}</div>',
         f"{t['w']} V ({t['otw']} ÖT) · {t['l']} F ({t['otl']} ÖT)"),
        ("Mål per match", f"{t['gf_pg']:.1f} <small>–</small> {t['ga_pg']:.1f}", "gjorda – insläppta"),
        ("Skott per match", f"{t['sf_pg']:.1f} <small>–</small> {t['sa_pg']:.1f}", "för – emot"),
        ("Powerplay", _pct(r.pp["pct"]), f"{r.pp['goals']} mål på {r.pp['opps']} lägen"),
        ("Boxplay", _pct(r.pk["pct"]), f"{r.pk['against']} insläppta på {r.pk['opps']}"),
        ("Utv.min per match", f"{t['pim_pg']:.1f}", f"{t['pim']} min totalt"),
        ("Räddning", _sv(t["sv_pct"]), f"skytte {_pct(t['sh_pct'], 1)}"),
    ]
    kpi_html = "".join(f'<div class="kpi"><div class="kpi-label">{a}</div>'
                       f'<div class="kpi-value">{b}</div><div class="kpi-sub">{c}</div></div>'
                       for a, b, c in kpis)

    # ---------- Insikter
    def ins_list(kind):
        items = [i for i in r.insights if i.kind == kind]
        if not items:
            return '<p class="muted">Inget som sticker ut i underlaget.</p>'
        return "".join(f'<div class="ins {kind}"><h4>{e(i.title)}</h4><p>{e(i.text)}</p></div>'
                       for i in items)

    info = [i for i in r.insights if i.kind == "info"]
    info_html = "".join(f'<div class="ins info"><h4>{e(i.title)}</h4><p>{e(i.text)}</p></div>'
                        for i in info)

    # ---------- Spelare
    on_ice = t.get("has_on_ice", True)
    last3 = [g.game_id for g in r.games[-3:]]
    rows = []
    for p in r.players[:15]:
        form = "".join(f'<span class="dot d{min(p.points_by_game.get(g, 0), 3)}" '
                       f'title="{p.points_by_game.get(g, 0)} p"></span>' for g in last3)
        rows.append(
            f"<tr><td class='num'>{p.num if p.num is not None else ''}</td><td>{e(p.name)}</td>"
            f"<td>{e(p.pos or '')}</td><td class='r'>{p.gp}</td><td class='r'>{p.goals}</td>"
            f"<td class='r'>{p.assists}</td><td class='r strong'>{p.points}</td>"
            f"<td class='r'>{p.pp_points}</td><td class='r'>{p.gwg}</td>"
            f"<td class='r'>{format(p.plus_minus, '+d') if on_ice else '–'}</td><td class='r'>{p.pim}</td><td>{form}</td></tr>")
    players_html = "".join(rows)

    # ---------- Uppställning
    lineup_html = ""
    for u in r.latest_lineup:
        if u["unit"] == "Extraspelare" and not u["players"]:
            continue
        ps = "".join(
            f'<li><span class="num">{p["num"] if p["num"] is not None else ""}</span>'
            f'<span class="pn">{e(p["name"])}</span><span class="pos">{p["pos"]}</span>'
            f'<span class="pts">{(_sv(p["sv"]) if p["pos"] == "G" else str(p["points"]) + " p")}</span></li>'
            for p in u["players"])
        lineup_html += f'<div class="unit"><h4>{e(u["unit"])}</h4><ul>{ps}</ul></div>'

    pm_note = ("+/- räknas på alla mål utom powerplaymål, utifrån protokollets uppgifter om vilka som var på isen."
               if on_ice else "+/- visas inte: protokollen i den här serien anger inte vilka spelare som var på isen vid mål.")
    units_html = "".join(
        f"<tr><td>{e(u['unit'])}</td><td class='r'>{u['goals']}</td><td class='r'>{u['points']}</td>"
        + (f"<td class='r'>{u['gf']}</td><td class='r'>{u['ga']}</td><td class='r'>{u['gf'] - u['ga']:+d}</td>"
           if on_ice else "")
        + "</tr>"
        for u in r.units)
    unit_head = ('<th class="r">5v5 +</th><th class="r">5v5 −</th><th class="r">Netto</th>' if on_ice else "")
    unit_note = ("Kedja = numrering i respektive matchs uppställning. 5v5 +/− = mål där minst två av kedjans forwards var på isen."
                 if on_ice else "Kedja = numrering i respektive matchs uppställning. Mål och poäng räknas på målskytt och assisterande.")

    # ---------- Perioder och tid
    pmax = max([max(v["gf"], v["ga"]) for v in r.periods.values()] + [1])
    per_html = ""
    for p, v in r.periods.items():
        if p == "ÖT" and v["gf"] + v["ga"] == 0:
            continue
        shots = f"{v['sf']}–{v['sa']}" if p != "ÖT" else ""
        per_html += (f"<tr><td>{'Period ' + p if p != 'ÖT' else 'Övertid'}</td>"
                     f"<td class='barcell'>{_bar(v['gf'], pmax, 'for')}<b>{v['gf']}</b></td>"
                     f"<td class='barcell'>{_bar(v['ga'], pmax, 'against')}<b>{v['ga']}</b></td>"
                     f"<td class='r'>{shots}</td></tr>")
    bmax = max([max(v["gf"], v["ga"]) for v in r.buckets.values()] + [1])
    buck_html = "".join(
        f"<tr><td>min {k}</td><td class='barcell'>{_bar(v['gf'], bmax, 'for')}<b>{v['gf']}</b></td>"
        f"<td class='barcell'>{_bar(v['ga'], bmax, 'against')}<b>{v['ga']}</b></td></tr>"
        for k, v in r.buckets.items())

    kinds = ["5 mot 5", "PP", "SH", "Tom bur", "Straff"]
    smax = max([r.strength_for.get(k, 0) for k in kinds] + [r.strength_against.get(k, 0) for k in kinds] + [1])
    str_html = "".join(
        f"<tr><td>{k}</td><td class='barcell'>{_bar(r.strength_for.get(k, 0), smax, 'for')}"
        f"<b>{r.strength_for.get(k, 0)}</b></td><td class='barcell'>"
        f"{_bar(r.strength_against.get(k, 0), smax, 'against')}<b>{r.strength_against.get(k, 0)}</b></td></tr>"
        for k in kinds if r.strength_for.get(k, 0) or r.strength_against.get(k, 0))

    # ---------- Disciplin
    tmax = max(list(r.penalties_by_type.values()) + [1])
    pen_html = "".join(
        f"<tr><td>{e(k)}</td><td class='barcell'>{_bar(v, tmax, 'against')}<b>{v}</b></td></tr>"
        for k, v in r.penalties_by_type.most_common(8))
    penp_html = "".join(
        f"<li>{e(p.name)} <span class='muted'>#{p.num}</span> <b>{p.pim} min</b> "
        f"<span class='muted'>({p.penalties} utv.)</span></li>"
        for p in r.penalized_players[:6])
    pper = " · ".join(f"P{k}: {r.penalties_by_period.get(k, 0)}" for k in ("1", "2", "3"))

    # ---------- Målvakter
    gk_html = "".join(
        f"<tr><td class='num'>{g['num'] or ''}</td><td>{e(g['name'])}</td><td class='r'>{g['gp']}</td>"
        f"<td class='r'>{g['starts']}</td><td class='r'>{g['saves']}/{g['shots']}</td>"
        f"<td class='r strong'>{_sv(g['sv'])}</td>"
        f"<td class='r'>{'' if g['gaa'] is None else format(g['gaa'], '.2f')}</td></tr>"
        for g in r.goalies)

    # ---------- Situationer
    s = r.situations
    pulls = s["pulls"]
    pull_txt = (f"{len(pulls)} gånger, i snitt {mmss(sum(p['left'] for p in pulls) / len(pulls))} kvar"
                if pulls else "Inga registrerade i underläge")
    late_to = [x for x in s["timeouts"] if x["secs"] >= 3300]
    to_txt = (f"{len(s['timeouts'])} st, varav {len(late_to)} under sista 5 min"
              if s["timeouts"] else "Inga")
    sit_rows = [
        ("Gör första målet", _wl(s["first_goal"])),
        ("Släpper in första målet", _wl(s["conceded_first"])),
        ("Leder efter 2 perioder", _wl(s["lead_after_2"])),
        ("Oavgjort efter 2 perioder", _wl(s["tied_after_2"])),
        ("Under efter 2 perioder", _wl(s["trail_after_2"])),
        ("Enmålsmatcher", _wl(s["one_goal"])),
        ("Vändningar (vinst efter underläge)", str(s["comebacks"])),
        ("Tappade ledningar", str(s["blown_leads"])),
        ("Målvakt ut i underläge", pull_txt),
        ("Timeouts", to_txt),
    ]
    sit_html = "".join(f"<tr><td>{a}</td><td class='r strong'>{b}</td></tr>" for a, b in sit_rows)

    # ---------- Matcher
    games_html = "".join(
        f"<tr><td>{g.date}</td><td>{'H' if g.home else 'B'}</td><td>{e(g.opponent)}</td>"
        f"<td class='r'><span class='chip sm {'win' if g.gf > g.ga else 'loss'}'>{g.result}</span> "
        f"{g.gf}–{g.ga}</td><td class='r'>{g.sf}–{g.sa}</td><td class='r'>{g.pim}</td>"
        f"<td class='r'><a href='{BASE}/Game/Events/{g.game_id}' target='_blank'>Protokoll</a></td></tr>"
        for g in reversed(r.games))

    nxt = ""
    if next_game:
        nxt = (f'<div class="next">Nästa match: <b>{e(next_game.home)} – {e(next_game.away)}</b> '
               f'{e(next_game.date)} {e(next_game.time)} {e(next_game.venue)}</div>')

    today = datetime.date.today().isoformat()
    return f"""<header>
  <div class="eyebrow">Scoutrapport · {e(r.league)}</div>
  <h1>{e(r.team)}</h1>
  <div class="meta">Senaste {t['gp']} matcherna ({span}) · Huvudtränare: {e(r.coach or '–')} · Skapad {today}</div>
  {nxt}
</header>
{extra_top}

<section class="kpis">{kpi_html}</section>

<section>
  <h2>Nyckelinsikter</h2>
  <div class="cols2">
    <div><h3 class="hot-h">Se upp med</h3>{ins_list('hot')}</div>
    <div><h3 class="chans-h">Möjligheter</h3>{ins_list('chans')}</div>
  </div>
  {info_html}
</section>

<section>
  <h2>Spelare att se upp med</h2>
  <div class="tw"><table>
    <thead><tr><th>#</th><th>Spelare</th><th>Pos</th><th class="r">GP</th><th class="r">M</th>
    <th class="r">A</th><th class="r">P</th><th class="r">PP-p</th><th class="r">GWG</th>
    <th class="r">+/-</th><th class="r">Utv</th><th>Form (3 senaste)</th></tr></thead>
    <tbody>{players_html}</tbody></table></div>
  <p class="note">{pm_note}</p>
</section>

<section class="cols2">
  <div>
    <h2>Senaste uppställning</h2>
    <div class="lineup">{lineup_html}</div>
  </div>
  <div>
    <h2>Kedjornas produktion</h2>
    <div class="tw"><table><thead><tr><th>Femma</th><th class="r">Mål</th><th class="r">Poäng</th>
    {unit_head}</tr></thead>
    <tbody>{units_html}</tbody></table></div>
    <p class="note">{unit_note}</p>
  </div>
</section>

<section class="cols2">
  <div>
    <h2>Perioder</h2>
    <div class="tw"><table class="bars"><thead><tr><th></th><th>Gjorda</th><th>Insläppta</th><th class="r">Skott</th></tr></thead>
    <tbody>{per_html}</tbody></table></div>
  </div>
  <div>
    <h2>När i perioden?</h2>
    <div class="tw"><table class="bars"><thead><tr><th></th><th>Gjorda</th><th>Insläppta</th></tr></thead>
    <tbody>{buck_html}</tbody></table></div>
  </div>
</section>

<section class="cols2">
  <div>
    <h2>Spelform vid mål</h2>
    <div class="tw"><table class="bars"><thead><tr><th></th><th>Gjorda</th><th>Insläppta</th></tr></thead>
    <tbody>{str_html}</tbody></table></div>
  </div>
  <div>
    <h2>Disciplin</h2>
    <div class="tw"><table class="bars"><tbody>{pen_html}</tbody></table></div>
    <p class="note">Per period: {pper}</p>
    <ul class="plain">{penp_html}</ul>
  </div>
</section>

<section class="cols2">
  <div>
    <h2>Målvakter</h2>
    <div class="tw"><table><thead><tr><th>#</th><th>Målvakt</th><th class="r">GP</th><th class="r">Start</th>
    <th class="r">Räddn.</th><th class="r">Rdd%</th><th class="r">GAA</th></tr></thead>
    <tbody>{gk_html}</tbody></table></div>
  </div>
  <div>
    <h2>Matchsituationer</h2>
    <div class="tw"><table class="wrap"><tbody>{sit_html}</tbody></table></div>
  </div>
</section>

<section>
  <h2>Matcher i underlaget</h2>
  <div class="tw"><table><thead><tr><th>Datum</th><th></th><th>Motstånd</th><th class="r">Resultat</th>
  <th class="r">Skott</th><th class="r">Utv.min</th><th></th></tr></thead>
  <tbody>{games_html}</tbody></table></div>
</section>

<footer>
  Källa: matchprotokoll från stats.swehockey.se. Protokollen saknar tekningar och skott per spelare,
  så de momenten ingår inte. Insikterna är regelbaserade och bygger på ett litet urval matcher, så läs dem som indikationer.
</footer>"""


CSS = """
:root{--bg:#f6f7f9;--card:#fff;--ink:#14171c;--muted:#667085;--line:#e4e7ec;
--accent:#0b5cad;--hot:#c4320a;--hot-bg:#fef3f2;--chans:#067647;--chans-bg:#ecfdf3;
--info-bg:#f2f4f7;--for:#0b5cad;--against:#d92d20}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#0f1115;--card:#171a20;
--ink:#eceef2;--muted:#98a2b3;--line:#2a2f38;--accent:#6aa9ff;--hot:#ff8a65;--hot-bg:#2a1712;
--chans:#4ade80;--chans-bg:#0f2418;--info-bg:#1d2129;--for:#6aa9ff;--against:#ff6b5e}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
main{max-width:1100px;margin:0 auto;padding:32px 16px 64px}
header{margin-bottom:20px}.eyebrow{text-transform:uppercase;letter-spacing:.08em;font-size:12px;
color:var(--accent);font-weight:700}h1{font-size:36px;margin:4px 0}.meta{color:var(--muted)}
.next{margin-top:10px;display:inline-block;background:var(--card);border:1px solid var(--line);
border-radius:8px;padding:6px 12px}
h2{font-size:18px;margin:0 0 12px}h3{font-size:14px;margin:0 0 8px;text-transform:uppercase;letter-spacing:.05em}
.hot-h{color:var(--hot)}.chans-h{color:var(--chans)}
section{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:20px;margin:16px 0}
section.cols2,section.kpis{background:none;border:0;padding:0}
.cols2{display:grid;grid-template-columns:1fr 1fr;gap:16px}
section.cols2>div{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:20px;min-width:0}
section>.cols2>div{min-width:0}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px}
.kpi-label{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.05em}
.kpi-value{font-size:24px;font-weight:700;margin:4px 0;font-variant-numeric:tabular-nums}
.kpi-value small{color:var(--muted);font-weight:400}.kpi-sub{font-size:12px;color:var(--muted)}
.chips{display:flex;flex-wrap:wrap;gap:3px}.chip{display:inline-block;min-width:22px;text-align:center;
font-size:11px;font-weight:700;border-radius:4px;padding:2px 3px;color:#fff}
.chip.win{background:var(--chans)}.chip.loss{background:var(--against)}.chip.sm{font-size:10px}
.ins{border-radius:8px;padding:10px 14px;margin-bottom:8px}.ins h4{margin:0 0 2px;font-size:15px}
.ins p{margin:0}.ins.hot{background:var(--hot-bg);border-left:4px solid var(--hot)}
.ins.chans{background:var(--chans-bg);border-left:4px solid var(--chans)}
.ins.info{background:var(--info-bg);border-left:4px solid var(--muted)}
.tw{overflow-x:auto}table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}
th,td{padding:6px 8px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}
table.wrap td{white-space:normal}
th{font-size:12px;color:var(--muted);font-weight:600}.r{text-align:right}.strong{font-weight:700}
.num{color:var(--muted)}.muted{color:var(--muted)}.note{font-size:12px;color:var(--muted);margin:8px 0 0}
.dot{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:3px;background:var(--line)}
.dot.d1{background:color-mix(in srgb,var(--chans) 45%,transparent)}.dot.d2{background:color-mix(in srgb,var(--chans) 75%,transparent)}
.dot.d3{background:var(--chans)}
.barcell{width:40%;min-width:110px}.bar{display:inline-block;height:10px;border-radius:3px;vertical-align:middle;margin-right:6px}
.bar.for{background:var(--for)}.bar.against{background:var(--against)}
.lineup{display:grid;grid-template-columns:1fr 1fr;gap:10px}.unit h4{margin:0 0 4px;font-size:13px;color:var(--muted)}
.unit ul{list-style:none;margin:0;padding:0}.unit li{display:flex;gap:6px;font-size:13px;padding:2px 0;border-bottom:1px dashed var(--line)}
.unit .num{width:24px}.unit .pn{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.unit .pos{color:var(--muted);width:14px}.unit .pts{font-weight:600}
ul.plain{list-style:none;padding:0;margin:8px 0 0}ul.plain li{padding:2px 0}
a{color:var(--accent)}footer{color:var(--muted);font-size:12px;margin-top:24px}
@media (max-width:760px){.cols2,.lineup{grid-template-columns:1fr}h1{font-size:28px}}
@media print{body{background:#fff}section,section.cols2>div,.kpi{break-inside:avoid;border-color:#ccc}
main{padding:0}a{color:inherit;text-decoration:none}}
"""
