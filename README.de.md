# daily-github-pulse

> Jeden Tag wissen, was auf GitHub, GitLab, Gitea und Bitbucket gerade durch die Decke geht.

[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](https://python.org)
[![Tests](https://github.com/alisadeghiaghili/daily-github-pulse/actions/workflows/tests.yml/badge.svg)](https://github.com/alisadeghiaghili/daily-github-pulse/actions)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Contributing](https://img.shields.io/badge/contributions-welcome-brightgreen)](CONTRIBUTING.md)

[فارسی](README.md) | [English](README.en.md)

---

`daily-github-pulse` macht Trending-Entdeckung zu einem einzigen Befehl:

```bash
python daily_github_pulse.py                           # GitHub (Standard)
python daily_github_pulse.py --forge gitlab            # GitLab
python daily_github_pulse.py --forge gitea --gitea-url https://codeberg.org
python daily_github_pulse.py --forge github,gitlab     # Beide zusammengeführt
```

Das Ergebnis: Repositories, die **heute** die meisten Sterne gesammelt haben, zusammen mit der echten täglichen Wachstumsrate — nicht nur die Gesamtanzahl.

```
======================================================================
#1  openai/openai-python
    Stars: 24,312  Forks: 3,201  Lang: Python
  Δ +418 ⭐ total  |  ~418.0 ⭐/day
    https://github.com/openai/openai-python
```

---

## In 30 Sekunden loslegen

```bash
git clone https://github.com/alisadeghiaghili/daily-github-pulse.git
cd daily-github-pulse
pip install -r requirements.txt

# Empfehlung: GitHub-Token hinzufügen (erhöht Limit auf 5.000 Anfragen/Std.)
cp .env.example .env
# GITHUB_TOKEN=ghp_... in .env setzen

python github_repo_of_the_day.py
```

Keine komplexe Konfiguration. Einfach starten.

---

## Praxisbeispiele

```bash
# Beste Python-Repos der letzten Woche
python github_repo_of_the_day.py -l python -p week

# Auf der Suche nach LLM- und Agent-Projekten?
python github_repo_of_the_day.py --bool-query '(LLM OR GPT) AND agent AND NOT benchmark'

# Wildcard: analy?e → analyse OR analyze
python github_repo_of_the_day.py --keywords "analy?e" --wildcard

# Trendige Entwickler
python github_repo_of_the_day.py --developers -l python

# CSV-Export
python github_repo_of_the_day.py -l go -o csv -f ergebnisse.csv

# KI-Filter — nur produktionsreife Inference-Server
python github_repo_of_the_day.py --keywords LLM --ai-filter --ai-filter-query "produktionsreife LLM-Inference-Server"
```

---

## Warum dieses Tool?

| Das Problem | Die Lösung |
|---|---|
| GitHub Trending zeigt nur die Gesamtanzahl der Sterne | **Star Velocity** — die tatsächliche Wachstumsrate heute (`⭐/day`) |
| Suche ist binär — entweder Treffer oder nicht | **Vollständige Boolean-Suche**: `(LLM OR GPT) AND agent AND NOT survey` |
| Wildcard-Muster müssen manuell erweitert werden | **Wildcard-Erweiterung** via NLTK: `analy?e` → `analyse OR analyze` |
| Ergebnisse sind voll mit Papers und Übersichtsartikeln | **KI-Filter** — Absicht in natürlicher Sprache beschreiben |
| Jeder Aufruf beginnt bei Null | **Snapshots** — Stern-Delta seit dem letzten Aufruf |

---

## Wie Star Velocity funktioniert

Bei jedem Aufruf werden die Sternanzahlen in `~/.daily-github-pulse/snapshots.json` gespeichert. Beim nächsten Aufruf erscheinen zwei Zahlen:

- **Δ raw** — gesamte Sterne seit dem letzten Snapshot
- **~N ⭐/day** — zeitnormalisierte Tagesrate (bleibt sinnvoll, auch nach mehreren Wochen Pause)

```bash
# Snapshot für diesen Aufruf überspringen
python github_repo_of_the_day.py --no-snapshot

# Alle gespeicherten Snapshots löschen
python github_repo_of_the_day.py --clear-snapshots
```

---

## Stichwortsuche

### Einzelnes Stichwort

```bash
python github_repo_of_the_day.py --keyword "vector database"
```

### Mehrere Stichwörter mit Boolean-Operator

```bash
# AND: beide Begriffe müssen vorkommen
python github_repo_of_the_day.py --keywords LLM agent --keyword-op AND

# OR: mindestens ein Begriff
python github_repo_of_the_day.py --keywords LLM GPT Claude --keyword-op OR

# Ausschließen von Begriffen
python github_repo_of_the_day.py --keywords LLM agent --keyword-not benchmark survey
```

### Vollständiger Boolean-Ausdruck

```bash
python github_repo_of_the_day.py --bool-query '(LLM OR GPT) AND agent AND NOT benchmark'
```

| Syntax | Bedeutung | Beispiel |
|---|---|---|
| `A AND B` | Beide müssen vorkommen | `LLM AND agent` |
| `A OR B` | Mindestens einer | `LLM OR GPT` |
| `NOT A` | Begriff ausschließen | `NOT benchmark` |
| `(A OR B) AND C` | Gruppierung | `(LLM OR GPT) AND agent` |
| `"mehrere Wörter"` | Phrase als ein Begriff | `"large language model"` |

### Wildcard-Erweiterung

Erfordert `pip install nltk`.

```bash
# ? = genau ein Zeichen
python github_repo_of_the_day.py --keywords "analy?e" --wildcard
# → Abfrage wird zu: (analyse OR analyze)

# * = beliebig viele Zeichen
python github_repo_of_the_day.py --keywords "optimiz*" agent --wildcard
# → Abfrage wird zu: (optimize OR optimized OR optimizing ...) AND agent
```

> Ohne `nltk` ist `--wildcard` ein No-op — Begriffe werden unverändert weitergegeben. Kein Absturz.

### Suchbereich

```bash
# Standard: nur Name und Beschreibung
python github_repo_of_the_day.py --keywords MCP server

# Auch README durchsuchen (langsamer — ein extra API-Aufruf pro Seite)
python github_repo_of_the_day.py --keywords MCP server -s name,description,readme
```

---

## KI-Relevanzfilter

Ergebnisse werden durch ein LLM nachgefiltert, das Beschreibung und README jedes Repos liest und entscheidet, ob es zur Absicht passt.

```bash
python github_repo_of_the_day.py --keywords LLM --ai-filter --ai-filter-query "produktionsreife LLM-Inference-Server"

# Mit Fallback, wenn das LLM nicht verfügbar ist
python github_repo_of_the_day.py --keywords agent --ai-filter --ai-filter-query "autonome Coding-Agenten" --ai-filter-fallback passthrough
```

### Unterstützte Backends

**OpenAI-kompatibel** (OpenAI, Ollama, LM Studio, Groq, Together AI, OpenRouter, vLLM):

```env
AI_PROVIDER=openai
AI_BASE_URL=https://api.openai.com/v1
AI_MODEL=gpt-4o-mini
AI_API_KEY=sk-...
```

**Lokales Ollama:**

```env
AI_BASE_URL=http://localhost:11434/v1
AI_MODEL=llama3.2
AI_API_KEY=ollama
```

**Anthropic (natives Claude-API):**

```env
AI_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-haiku-4-5
```

| `--ai-filter-fallback` | Verhalten bei nicht verfügbarem LLM |
|---|---|
| `fail` _(Standard)_ | Beenden mit Fehler |
| `passthrough` | Warnung + alle Ergebnisse ungefiltert anzeigen |

---

## GitHub Rate Limits

| Authentifizierung | Limit |
|---|---|
| Kein Token | 60 Anfragen/Std. |
| Mit Token | 5.000 Anfragen/Std. |

Token erstellen → [github.com/settings/tokens](https://github.com/settings/tokens)

---

## Alle Optionen

<details>
<summary>Vollständige Flag-Referenz</summary>

| Kategorie | Flag | Beschreibung |
|---|---|---|
| Forge | `--forge NAME[,NAME...]` | Zu durchsuchende Plattform: `github` (Standard), `gitlab`, `gitea`, `bitbucket` |
| Forge | `--gitea-url URL` | Gitea/Codeberg Instanz-URL |
| Modus | `--developers` | Trendige Entwickler statt Repos anzeigen |
| Filter | `-l LANG` | Programmiersprache (z.B. `python`, `go`, `rust`) |
| Filter | `-p PERIOD` | Zeitfenster: `day` / `week` / `month` |
| Filter | `-n N` | Ergebnisse pro Kategorie (Standard: 10) |
| Suche | `--keyword TERM` | Einzelnes Stichwort (legacy) |
| Suche | `--keywords A B` | Mehrere Stichwörter mit Boolean-Operator |
| Suche | `--keyword-op AND\|OR` | Operator für `--keywords` |
| Suche | `--keyword-not A B` | Begriffe ausschließen |
| Suche | `--bool-query 'EXPR'` | Vollständiger Boolean-Ausdruck |
| Suche | `--search-in SCOPE` | `name`, `description`, `readme` |
| Suche | `--wildcard` | Wildcard-Erweiterung via NLTK |
| Ausgabe | `-o json\|csv` | Ausgabeformat |
| Ausgabe | `-f DATEI` | In Datei schreiben statt stdout |
| Snapshot | `--no-snapshot` | Velocity-Tracking für diesen Aufruf deaktivieren |
| Snapshot | `--clear-snapshots` | Alle gespeicherten Snapshots löschen |
| KI | `--ai-filter` | LLM-Relevanzfilter aktivieren |
| KI | `--ai-filter-query "QUERY"` | Absicht in natürlicher Sprache |
| KI | `--ai-filter-fallback` | `fail` oder `passthrough` |
| Auth | `--token TOKEN` | GitHub-Token (überschreibt `.env`) |

</details>

---

## Export

```bash
# JSON nach stdout (mit jq pipen)
python github_repo_of_the_day.py -o json | jq '.[].full_name'

# CSV in Datei
python github_repo_of_the_day.py -o csv -f ergebnisse.csv

# Entwickler als JSON
python github_repo_of_the_day.py --developers -o json
```

**CSV-Felder (Repos):** `rank`, `category`, `full_name`, `stars`, `star_delta`, `daily_velocity`, `forks`, `language`, `description`, `created_at`, `updated_at`, `url`

**CSV-Felder (Entwickler):** `rank`, `login`, `name`, `company`, `location`, `public_repos`, `followers`, `following`, `url`

---

## Tests ausführen

```bash
pip install pytest
pytest tests/ -v
```

221 Tests — kein Internetzugang erforderlich (alle APIs vollständig gemockt).

---

## Mitwirken

Alle Details in [CONTRIBUTING.md](CONTRIBUTING.md) — Setup, Code-Stil, Commit-Konventionen und PR-Checkliste.

---

## Lizenz

[MIT](LICENSE)
