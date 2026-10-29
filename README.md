# Rider Payout Dispute Desk

AI-powered agent that handles rider payout complaints for QuickDrop, a delivery company. It talks to riders via WhatsApp-style messaging, investigates payout discrepancies against trip/payout records, auto-pays small corrections via PaySwift, and escalates anything risky to the ops team.

## Quick Start

```bash
docker compose up --build
# Service: http://localhost:8000  |  PaySwift sandbox: http://localhost:8081
# Ops dashboard: http://localhost:8000/
```

## Run Evals

```bash
pip install requests
python evals/run.py http://localhost:8000
```

## Run Tests (no Docker needed)

```bash
pip install -r requirements.txt pytest
pytest -q
```

## Agent Design

### Architecture: Deterministic Agent with Optional LLM Extraction

All money calculations, policy checks, and payment decisions are made by **deterministic Python code** — never by an LLM. An optional Gemini call assists only with extracting structured metadata (complaint type, order IDs, dates) from natural-language rider messages. The agent works fully without any API key.

```
Rider message
  → Idempotent webhook (dedup by message_id)
  → Intent & entity extraction (regex + optional LLM)
  → Safety checks (injection guard, date window, rider validation)
  → Investigation (trip lookup → fare calc → payout comparison)
  → Decision engine (auto-pay ≤ ₹200 | ops approval | escalation)
  → PaySwift payment (with retries + idempotency key + ledger verify)
  → Reply to rider
```

### What the Model Decides (optional, when `GEMINI_API_KEY` is set)

- Extracts complaint types (`surge` / `incentive` / `penalty` / `general`) from Hinglish messages
- Extracts order IDs and dates from free-form text
- **Never** computes amounts, approves payments, or changes policy

### What Deterministic Code Decides (always)

| Decision | How |
|----------|-----|
| Fare calculation | ₹25 base + ₹6/km after 2 km × surge, `Decimal(ROUND_HALF_UP)` |
| Payment authorization | Auto-pay ≤ ₹200, once per rider per day; else → ops |
| Duplicate protection | Idempotent `message_id`, idempotent PaySwift key + ledger check |
| Safety rails | Prompt-injection regex, identity-switch block, 7-day window |
| Fail-closed | PaySwift unreachable → escalate, never pay blind |

### Tools the Agent Uses

| Tool | Type | Purpose |
|------|------|---------|
| Trip lookup | Data | Find rider's trips by date or trip_id from CSV |
| Fare calculator | Compute | Deterministic fare from policy formula |
| Payout checker | Data | Compare expected fare vs `payout_lines.csv` |
| PaySwift client | API | GET ledger, POST payments with retries + idempotency |
| LLM extractor | API (optional) | Gemini call for NL → structured metadata |

### API Endpoints

| Endpoint | Description |
|----------|-------------|
| `POST /messages` | Webhook for rider messages → `{"reply": "..."}` |
| `GET /trace/{rider_id}` | Full audit trail of agent actions |
| `GET /ops/pending` | Items awaiting ops approval/review |
| `POST /ops/{id}/approve` | Approve and pay a pending item |
| `POST /ops/{id}/reject` | Reject a pending item |
| `GET /` | Ops dashboard (HTML) |
| `GET /health` | Health check |

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | `sqlite:///./local.db` | PostgreSQL connection string |
| `PAYSWIFT_BASE_URL` | Yes | `http://payswift:8081` | PaySwift sandbox URL |
| `GEMINI_API_KEY` | No | *(empty)* | Enables LLM-assisted extraction |
| `GEMINI_MODEL` | No | `gemini-2.0-flash` | Gemini model to use |

## Assumptions

1. **Deterministic over generative** — money calculations must be exact; LLM is never trusted with amounts or authorization
2. **Fail closed** — if PaySwift or the ledger can't be verified, escalate instead of paying
3. **Hinglish** — riders write in Hindi-English mix; regex handles common patterns, Gemini assists edge cases
4. **Single-rider conversations** — each WhatsApp number maps to one `rider_id`
5. **IST calendar day** — "day" for policy = IST calendar day
6. **CSV exports are authoritative** — trip and payout CSVs are the source of truth
7. **Distance > 250 km is implausible** — flagged; surge delta estimated from base payout when possible

## What I Skipped

- **Rich ops dashboard** — functional but minimal HTML, no JS framework or websockets
- **Rider notification after ops approval** — approved payments don't push-notify the rider
- **Rate limiting on webhook** — trusted internal service, no auth on `/messages`
- **Full LLM conversation memory** — state tracks date/disputes across turns, but no full chat history sent to model
