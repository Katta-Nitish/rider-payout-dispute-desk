# Rider Payout Dispute Desk

AI-powered agent that handles rider payout complaints for QuickDrop, a delivery company. Built using **LangGraph** (5-action routing agent), **LangChain**, and **FastAPI**, backed by a zero-setup **SQLite** engine.

It investigates payout discrepancies against trip and payout records, auto-pays small corrections via PaySwift, and escalates edge cases or high-value claims to human ops.

## Quick Start

```bash
docker compose up --build
# Service: http://localhost:8000  |  PaySwift sandbox: http://localhost:8081
# Interactive Ops & WhatsApp Simulator UI: http://localhost:8000/
```

### Run Locally (Without Docker)
```bash
# Terminal 1: PaySwift sandbox
python payswift/server.pyc

# Terminal 2: FastAPI app (uses SQLite local.db out-of-the-box)
uvicorn app:app --port 8000
```

## Run Evals

```bash
pip install requests
python evals/run.py http://localhost:8000
```

## Run Tests

```bash
pytest -v
```

## Agent Design: LangGraph 5-Action Routing Architecture

The agent implements a stateful **LangGraph `StateGraph`** implementing a 5-action routing architecture (**Retrieve**, **Clarify**, **Tool**, **Answer**, **Refuse**):

```
                        Incoming WhatsApp Webhook
                                   │
                                   ▼
                       [LangGraph Router Node]
                                   │
        ┌───────────────┬──────────┴──────────────┬────────────────┐
        ▼               ▼                         ▼                ▼
    [Refuse]        [Clarify]                [Retrieve]         [Answer]
(Prompt injection, (Missing date          (Query trips &           │
  out-of-window,   & order ID)             payout CSVs)            │
 unknown rider)         │                         │                │
        │               │                         ▼                │
        │               │                      [Tool]              │
        │               │                (Policy math, surge,      │
        │               │                 PaySwift auto-pay        │
        │               │                  or ops approval)        │
        │               │                         │                │
        │               │                         ▼                │
        └───────────────┴───────────────────► [Answer] ◄───────────┘
                                                  │
                                                  ▼
                                            Outgoing Reply
```

### 1. The 5 LangGraph Actions:
- **`router`**: Extracts entities (Hinglish dates in IST, order IDs) via regex and an optional **LangChain Runnable** (`PromptTemplate | RunnableLambda`) calling `gemini-3.5-flash-lite`. Evaluates security guardrails and routes execution.
- **`refuse`**: Intercepts prompt injection attacks (*"ignore previous rules"*, *"approve all"*), cross-rider impersonation, and out-of-window disputes (>7 days), routing them safely to human ops without payment.
- **`clarify`**: Prompts the rider for missing date or order ID when complaints are vague.
- **`retrieve`**: Fetches authoritative CSV records (`trips.csv`, `payout_lines.csv`, `riders.csv`) and queries the PaySwift ledger.
- **`tool`**: Deterministically calculates exact fares, surges, and penalties. If $\le ₹200$ and first payout today, triggers PaySwift tool call with SHA-256 idempotency key; otherwise routes to Ops Approval.
- **`answer`**: Synthesizes a clear Hinglish reply explaining the resolution or why no payout was due.

### 2. What the Model Decides vs. What Code Decides:
- **What LangChain / Gemini 3.5 Flash Lite Decides (Optional)**: Entity and intent parsing from messy natural language.
- **What Code Decides (Always)**: All arithmetic, rounding (`Decimal(ROUND_HALF_UP)`), policy enforcement, ledger reconciliation, and money authorization. The LLM is never trusted with money calculations.

### 3. Database: Zero-Setup SQLite
The service uses **SQLite** (`sqlite:///./local.db`) with thread-safe connection pooling, eliminating the need for an external database container while maintaining full SQL compliance.

### 4. Interactive Ops & Simulation UI
Open `http://localhost:8000/` to access:
- **WhatsApp Simulator**: Send real-time test messages as any rider and inspect live responses.
- **Ops Review Queue**: Approve & Pay or Reject pending disputes.
- **Audit Trace**: Visual timeline of all LangGraph state transitions and tool calls.

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./local.db` | SQLite connection string |
| `PAYSWIFT_BASE_URL` | `http://payswift:8081` | PaySwift sandbox URL |
| `GEMINI_API_KEY` | *(empty)* | Optional: Enables LangChain Gemini extraction |
| `GEMINI_MODEL` | `gemini-3.5-flash-lite` | Gemini model to use |

## Assumptions & Guardrails
1. **Deterministic over Generative**: Exact policy formulas prevent hallucinations in money movements.
2. **Fail-Closed**: If PaySwift is unresponsive, the agent escalates to ops rather than double-paying.
3. **Idempotency**: Webhook dedup via `message_id`; payment dedup via deterministic SHA-256 keys.
4. **Data Exports are Authoritative**: CSV exports are the source of truth.
5. **Implausible Distance**: Trips $> 250\text{ km}$ are flagged for ops review.
