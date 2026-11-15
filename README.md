# Scoutrapport

Välj ett lag, så hämtar verktyget dess senaste matchprotokoll från stats.swehockey.se och skapar en scoutingrapport om motståndaren (HTML, utskriftsvänlig).

Kräver bara Python 3.9+. Inga paket behöver installeras.

## Användning

```bash
python3 -m scout                                   # interaktivt: välj serie och lag
python3 -m scout --serie SHL --lag "Växjö" -n 10   # direkt
python3 -m scout --serie Hockeyettan --lag "Nyköping" --oppna
python3 -m scout --serier                          # lista alla serier med id
```

Rapporten sparas i `rapporter/<lag>.html`. Hämtade sidor cachas i `.cache/`. Spelade matcher hämtas bara en gång.

## Vad rapporten innehåller

- Nyckelinsikter: "Se upp med" (deras styrkor) och "Möjligheter" (svagheter att utnyttja)
- Form, mål och skott per match, PP, boxplay, utvisningsminuter, räddningsprocent
- Spelare: poäng, PP-poäng, matchvinnande mål, +/-, utvisningar, form senaste tre matcherna
- Senaste laguppställningen och kedjornas produktion (inklusive 5 mot 5 på isen)
- Perioder, när i perioden målen kommer, och spelform vid mål
- Disciplin: vanligaste utvisningar och mest utvisade spelare
- Målvakter, matchsituationer (första mål, ställning efter två, vändningar, målvakt ut, timeouts)

## Struktur

| Fil | Ansvar |
|---|---|
| `scout/fetch.py` | HTTP med diskcache och fördröjning |
| `scout/parse.py` | Tolkar serier, spelschema, matchhändelser och laguppställningar |
| `scout/data.py` | Hittar serie och lag, senaste och nästa match |
| `scout/analyze.py` | All statistik och de regelbaserade insikterna |
| `scout/report.py` | HTML-rapporten |

Tester: `python3 -m unittest discover -s tests -t .`

## Begränsningar

Protokollen saknar tekningar och skott per spelare. Insikterna är regler med tröskelvärden och ingen jämförelse mot seriesnitt ännu.

## Kils AIK-sidan (GitHub Pages)

`python3 -m scout.site --web` bygger `public/index.html` med alla lag i HockeyTvåan Herr Region Väst C, sett från Kils AIK.
GitHub Actions (`.github/workflows/uppdatera.yml`) bygger och publicerar sidan till GitHub Pages varannan timme 06–24 svensk tid och vid varje push.
Kör en uppdatering direkt under Actions → "Uppdatera scoutrapporter" → Run workflow.

Live: https://iservicekarlstad.github.io/kilsscouten/
