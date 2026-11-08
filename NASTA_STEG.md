# Nästa steg: få Kils AIK-sidan att uppdateras utan Claude/Mac

Läget 2026-11-08:

## Klart
- `python3 -m scout.site --netlify` bygger `public/index.html` (alla 8 lag i HockeyTvåan Herr Region Väst C, serie-id 21090, sett från Kils AIK).
- `.github/workflows/uppdatera.yml`: GitHub Actions kör bygget kl. 06 och 22 UTC (07/23 svensk vintertid), kör testerna och committar `public/index.html`. Det startas också manuellt via workflow_dispatch.
- `netlify.toml`: Netlify publicerar `public/` och bygger inget självt.
- Lokalt git-repo på branch `main` med en commit. Inget är pushat och ingen remote finns.
- Nuvarande claude.ai-sida: https://claude.ai/artifact/4ueHJEFavRaB38eFaBjBd3 (uppdateras av den schemalagda Claude-uppgiften `kil-scouting-uppdatering` kl. 07 och 23 så länge appen är öppen).

## Kvar att göra
1. **Skicka upp koden till GitHub** som ett privat repo `kil-scouting` på användarens konto (samma e-post som claude.ai).
   - Datorn saknar `gh` och GitHub-inloggning. Användaren försöker få en GitHub-connector i sessionen. Kontrollera vilka GitHub-verktyg som finns. Kan de skapa repo och pusha filer (inklusive `.github/workflows/`), använd dem.
   - Annars: ladda ner GitHub CLI (officiell, `gh_2.103.3_macOS_arm64.zip`, 14 MB från github.com/cli/cli) till hemkatalogen efter användarens OK. Användaren loggar in själv med `gh auth login --web` (engångskod). Skapa sedan repot och pusha.
2. **Koppla Netlify** (användaren gör det själv i Netlify-gränssnittet): Add new site → Import an existing project → GitHub → `kil-scouting`. Inställningarna läses från `netlify.toml`.
3. **Kör workflowen en gång manuellt** (Actions → "Uppdatera scoutrapporter" → Run workflow) och kontrollera att stats.swehockey.se svarar från GitHubs servrar och att Netlify-sidan visar data.
4. När Netlify-sidan fungerar: ge användaren länken till tränarna och fråga om den schemalagda Claude-uppgiften ska stängas av.

Användaren skriver på svenska och vill ha svar på svenska.
