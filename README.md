# Group Ops Dashboard — Quantaco FSE Take-Home

Real-time operations dashboard for a hospitality group (~40 venues). Ops can see today’s sales by venue, top sellers, anomaly flags, and drill into a venue — updated within seconds as POS transactions stream in.

## Quick start (one command)

```bash
./run.sh
```

- UI: http://127.0.0.1:5173  
- Login: **ops / ops1234**  

Live POS stream (optional, second terminal):

```bash
source .venv/bin/activate
TOKEN=$(./scripts/print_token.sh)
python scripts/simulate_transactions.py --token "$TOKEN" --backfill
```

## Manual local (if you prefer separate terminals)

```bash
# Backend
source .venv/bin/activate
cd backend && pip install -r requirements.txt
python manage.py migrate && python manage.py seed_demo
python manage.py runserver

# Frontend
cd frontend && npm install && npm run dev
```

## What I built (and why)

### Problem framing

Ops need a **single live picture** of trade during the day. Focus:

1. Ranked venue sales + group KPIs  
2. Top items (group + per venue)  
3. Anomaly cues (sales drop / void-refund spike) with mute  
4. Venue side panel (hourly trade + sellers + baseline)  
5. Real-time refresh without page reload  

### Architecture

```
POS Simulator ──POST──► Django/DRF ingest ──► SQLite
                              │                    │
                              │                    └── HourlyRollup (on write)
                              ├── EventBus (in-process; Redis optional)
                              │         │
                              │         ▼
React Dashboard ◄── SSE ── /api/stream/
        │
        └──GET── /api/dashboard/ + /api/venues/:id/
                 POST /api/venues/:id/ack/
```

| Layer | Choice | Why |
|---|---|---|
| Backend | Django + DRF | Required stack |
| DB | SQLite | Zero-ops local demo; 40 venues is small |
| Real-time | SSE + in-process EventBus | One-way dashboard updates; no page refresh |
| Ingest | Idempotent POST + dead-letter | Safe POS retries; bad payloads retained |
| Aggregates | `HourlyRollup` on ingest | Fast dashboard reads |
| Alerts | Daypart baseline (+ prior-hour fallback) | Less naive than adjacent-hour only |
| Auth | DRF `ObtainAuthToken` | Stock token login |
| Frontend | React + Vite + TS + Mantine | Typed UI with readable component primitives |

### Anomaly rules (tunable in `settings.py`)

- **Sales drop**: last-hour sales &lt; 45% of **daypart baseline** (avg same `hour_of_day` over lookback). Falls back to prior hour if history is thin.  
- **Void/refund spike**: voids+refunds ≥ 18% of last-hour transactions (min 3 txns)  
- **Ack**: `POST /api/venues/:id/ack/` mutes that alert type until end of local day  

### Real-time

Ingest publishes on an in-process bus (Redis if `REDIS_URL` is set). SSE clients refresh; React debounces ~400ms then refetches. Token on query string because `EventSource` cannot set headers.

## Alternatives & trade-offs

| Decision | Chosen | Alternative | Trade-off |
|---|---|---|---|
| Fan-out | In-process EventBus (+ optional Redis) | Django Channels WebSockets | Enough for local demo; Redis helps multi-process |
| Storage | SQLite | Postgres | SQLite wins local simplicity; Postgres for concurrent prod writes |
| Aggregates | Hourly rollups | Pure on-read | Rollups add write complexity; much faster reads |
| Ingest conflicts | 200 duplicate | 409 Conflict | 200+`status` is friendlier for POS at-least-once retries |

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/auth/login/` | `{username,password}` → `{token}` |
| POST | `/api/transactions/` | Ingest (201 created / 200 duplicate / 400 + dead-letter) |
| GET | `/api/dashboard/` | Group snapshot from rollups |
| GET | `/api/venues/:id/` | Venue drill-down |
| POST | `/api/venues/:id/ack/` | Mute alert type until end of day |
| GET | `/api/stream/?token=` | SSE stream |

## Tests

```bash
source .venv/bin/activate
cd backend
python manage.py test ops
```

Covers anomalies, ack, idempotent ingest, dead-letter, rollups, and SSE bus publish/subscribe.

## Project layout

```
backend/          Django (ops, accounts, config)
frontend/         React dashboard
scripts/          POS simulator + print_token.sh
run.sh            One-command local start
```

## Assumptions

- “Today” is the current calendar day; times on screen use the browser’s local timezone.  
- Top sellers from **sale** line items only (voids/refunds don’t count as “selling”)  
- POS `total` trusted (shape validated)  
- One ops role for the demo  

## Extras

Clear populated demo data and stream fresh sales (venv active: `source .venv/bin/activate`):

```bash
cd backend
python manage.py clear_demo_data --yes
```

That deletes transactions and related rollups/alerts. Venues and the `ops` login stay.

Then from repo root, stream again:

```bash
TOKEN=$(./scripts/print_token.sh)
python scripts/simulate_transactions.py --token "$TOKEN" --backfill
```

Optional simulator flags:

```bash
# Faster updates
python scripts/simulate_transactions.py --token "$TOKEN" --interval 0.5

# Push more voids/refunds at one venue (good for alert demos)
python scripts/simulate_transactions.py --token "$TOKEN" --spike-venue VEN-03
```
