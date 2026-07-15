# Brevo → SQLite sync (zonder API-key)

Haalt Brevo-data op via de Claude MCP-connectie en schrijft ze naar een lokale
SQLite-databank. Geen API-key nodig, omdat het ophalen via Claude gebeurt.

## Hoe het werkt

```
Brevo  --(MCP, via Claude)-->  payloads/*.json  --(ingest.py)-->  brevo.db
```

- **Claude** haalt de data op (heeft de Brevo-connectie) en dumpt ruwe JSON in `payloads/`.
- **ingest.py** is een gewoon, deterministisch script dat die JSON idempotent
  wegschrijft naar `brevo.db` (upsert op id, dus opnieuw draaien werkt bij).

## Gebruiken

In Claude Code, één commando:

- `/sync-brevo`            → lijsten + segmenten + campagnes (snel)
- `/sync-brevo alles`      → ook alle ~50.000 contacten (zwaar, duurt langer)
- `/sync-brevo contacten`  → enkel contacten (incrementeel: enkel gewijzigde)

Of gewoon vragen: "sync de Brevo-data".

## Databank bekijken

```bash
sqlite3 ~/Documents/Claude/brevo-sync/brevo.db
```

Tabellen: `contacts`, `lists`, `segments`, `campaigns`, `campaign_stats`, `sync_runs`.

Voorbeelden:
```sql
-- Top campagnes op open-rate
SELECT c.name, s.sent, s.opens_rate
FROM campaign_stats s JOIN campaigns c ON c.id = s.campaign_id
ORDER BY s.opens_rate DESC LIMIT 10;

-- Contacten per lijst tellen (via de lijst-tabel)
SELECT name, unique_subscribers FROM lists ORDER BY unique_subscribers DESC;

-- Wanneer laatst gesynct
SELECT * FROM sync_runs ORDER BY id DESC LIMIT 5;
```

## Beperking

Dit draait niet volledig vanzelf (geen nachtelijke cron), want zonder API-key is
er telkens een Claude-sessie nodig. "Één commando wanneer je verse data wil" is
de best mogelijke aanpak binnen die randvoorwaarde. Wil je later tóch echt
automatisch draaien, dan is een Brevo API-key + GitHub Action de weg.

## Bestanden

- `schema.sql`  — databank-structuur
- `ingest.py`   — JSON payloads → SQLite (deterministisch, idempotent)
- `payloads/`   — tijdelijke JSON van Claude; na ingest verplaatst naar `payloads/_done/`
- `brevo.db`    — de SQLite-databank
