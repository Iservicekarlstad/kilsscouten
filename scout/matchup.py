"""Jämförelse 'vi mot dem' och inbördes möten, sett från vårt lag."""
from __future__ import annotations

from html import escape as e

from .analyze import Report
from .parse import GameRef

BASE = "https://stats.swehockey.se"


def _pct(x):
    return "–" if x is None else f"{x * 100:.0f} %"


def _sv(x):
    return "–" if x is None else f"{x:.3f}".lstrip("0")


def head_to_head(scheds: list[list[GameRef]], a: str, b: str) -> list[GameRef]:
    seen, out = set(), []
    for sched in scheds:
        for g in sched:
            key = (g.date, g.home, g.away)
            if {g.home, g.away} == {a, b} and key not in seen:
                seen.add(key)
                out.append(g)
    return sorted(out, key=lambda g: (g.date, g.time))


def keys(us: Report, them: Report) -> list[str]:
    """Korta matchnycklar som ställer deras styrkor/svagheter mot våra."""
    out = []
    tu, tt = us.totals, them.totals

    top = them.players[0] if them.players else None
    if top and top.points:
        pp = f", varav {top.pp_points} i powerplay" if top.pp_points else ""
        out.append(f"Stäng {top.name} (#{top.num}): {top.points} poäng på {top.gp} matcher{pp}.")

    if them.pp["pct"] is not None and them.pp["opps"] >= 6 and them.pp["pct"] >= 0.20:
        out.append(f"Deras powerplay går in på {_pct(them.pp['pct'])}. Vi tar "
                   f"{tu['pim_pg']:.1f} utvisningsminuter per match, så disciplinen avgör.")
    if them.pk["pct"] is not None and them.pk["opps"] >= 6 and them.pk["pct"] <= 0.80:
        out.append(f"Deras boxplay håller bara {_pct(them.pk['pct'])}. Vårt powerplay "
                   f"({_pct(us.pp['pct'])}) kan avgöra, så kör på dem och tvinga fram utvisningar.")
    elif tt["pim_pg"] >= 9:
        out.append(f"De tar {tt['pim_pg']:.1f} utvisningsminuter per match. Vårt powerplay "
                   f"({_pct(us.pp['pct'])}) får chanser.")

    their = {p: v["gf"] - v["ga"] for p, v in them.periods.items() if p != "ÖT"}
    ours = {p: v["gf"] - v["ga"] for p, v in us.periods.items() if p != "ÖT"}
    if their and ours:
        weak = min(their, key=their.get)
        strong = max(ours, key=ours.get)
        if their[weak] < 0 and weak == strong:
            w, s = them.periods[weak], us.periods[strong]
            out.append(f"Period {weak} är deras svagaste ({w['gf']}–{w['ga']}) och vår starkaste "
                       f"({s['gf']}–{s['ga']}).")

    tot_ga = sum(v["ga"] for v in them.buckets.values())
    if tot_ga >= 6 and them.buckets["15–20"]["ga"] / tot_ga >= 0.35:
        out.append(f"{_pct(them.buckets['15–20']['ga'] / tot_ga)} av deras insläppta mål kommer "
                   f"sista fem minuterna av en period. Håll trycket uppe hela vägen.")

    if them.goalies:
        g = them.goalies[0]
        if g["sv"] is not None and g["gp"] >= 2:
            word = "het" if g["sv"] >= 0.915 else "sårbar" if g["sv"] <= 0.890 else "stabil"
            out.append(f"Förstemålvakt {g['name']} är {word}: {_sv(g['sv'])} på {g['gp']} matcher.")
    return out[:6]


def render(us: Report, them: Report, h2h: list[GameRef]) -> str:
    tu, tt = us.totals, them.totals
    rows = [
        ("Gjorda mål / match", tu["gf_pg"], tt["gf_pg"], True, lambda x: f"{x:.1f}"),
        ("Insläppta mål / match", tu["ga_pg"], tt["ga_pg"], False, lambda x: f"{x:.1f}"),
        ("Skott för / match", tu["sf_pg"], tt["sf_pg"], True, lambda x: f"{x:.1f}"),
        ("Skott emot / match", tu["sa_pg"], tt["sa_pg"], False, lambda x: f"{x:.1f}"),
        ("Powerplay", us.pp["pct"], them.pp["pct"], True, _pct),
        ("Boxplay", us.pk["pct"], them.pk["pct"], True, _pct),
        ("Utvisningsmin / match", tu["pim_pg"], tt["pim_pg"], False, lambda x: f"{x:.1f}"),
        ("Räddningsprocent", tu["sv_pct"], tt["sv_pct"], True, _sv),
    ]
    trs = []
    for label, a, b, hib, fmt in rows:
        edge = ""
        fa = "–" if a is None else fmt(a)
        fb = "–" if b is None else fmt(b)
        if a is not None and b is not None and fa != fb:
            ours_better = (a > b) == hib
            edge = "us" if ours_better else "them"
        trs.append(f'<tr><td class="mu-v {"win" if edge == "us" else ""}">{fa}</td>'
                   f'<td class="mu-l">{label}</td>'
                   f'<td class="mu-v {"win" if edge == "them" else ""}">{fb}</td></tr>')

    form_us = f"{tu['w']}–{tu['l']}"
    form_them = f"{tt['w']}–{tt['l']}"

    h2h_html = ""
    if h2h:
        items = []
        for g in h2h:
            if g.played:
                link = f'<a href="{BASE}/Game/Events/{g.game_id}" target="_blank" rel="noopener">{g.home_goals}–{g.away_goals}</a>'
            else:
                link = f'<span class="muted">{e(g.time)}</span>'
            items.append(f"<li><span class='muted'>{g.date}</span> {e(g.home)} – {e(g.away)} <b>{link}</b></li>")
        h2h_html = f'<div class="mu-h2h"><h3>Inbördes möten i serien</h3><ul class="plain">{"".join(items)}</ul></div>'

    keys_html = "".join(f"<li>{e(k)}</li>" for k in keys(us, them))
    return f"""
<section class="matchup">
  <h2>{e(us.team)} mot {e(them.team)}</h2>
  <div class="mu-grid">
    <div class="tw"><table class="mu-table">
      <thead><tr><th class="mu-v">{e(us.team)}<br><span class="muted">{form_us} senaste {tu['gp']}</span></th>
      <th></th><th class="mu-v">{e(them.team)}<br><span class="muted">{form_them} senaste {tt['gp']}</span></th></tr></thead>
      <tbody>{''.join(trs)}</tbody></table></div>
    <div>
      <h3>Matchnycklar</h3>
      <ul class="keys">{keys_html}</ul>
      {h2h_html}
    </div>
  </div>
  <p class="note">Markerat värde = det lag som har fördel. Underlaget är varje lags senaste {max(tu['gp'], tt['gp'])} matcher.</p>
</section>"""
