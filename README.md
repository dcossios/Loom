# Loom — Self-Improving Organizational Brain

Loom is a self-hosted **corporate brain**: a single, queryable knowledge graph that captures your
company's code, data, conversations and decisions so AI agents can recall context, connect facts,
and act — and keep improving as new information flows in.

It runs as a Docker stack built on [**Cognee**](https://github.com/topoteretes/cognee) (the ECL
memory engine) with **FalkorDB** as the graph database. A cron sidecar continuously ingests your
sources, and any MCP-capable agent (e.g. **Hermes Agent**) connects to the brain as a tool.

> Built on Cognee. See [`PRD.md`](PRD.md) for the product vision and [`CLAUDE.md`](CLAUDE.md) for
> deep architecture notes.

---

## Architecture

```
                         ┌──────────────────────────────┐
   sources               │            cognee            │  HTTP API :8000
   ┌────────────┐  add   │  add → cognify → search       │  (single writer)
   │ codebase   │ ─────► │                               │
   │ database   │ files  │  Graph  = FalkorDB  (:6379)   │ ◄── cognee-mcp :8001
   │ Linear     │ ─────► │  Vector = LanceDB   (local)   │     (MCP, client mode)
   │ Sentry     │        │  Rel    = SQLite    (local)   │            ▲
   │ Slack      │        └──────────────────────────────┘            │ MCP/HTTP
   └────────────┘                  ▲                                  │
        ▲                          │ POST /add + /cognify        ┌─────────┐
        │ cron (extract→JSON)      │                             │ Hermes  │
   ┌──────────────┐                │                             │ Agent   │
   │ ingestion-cron├───────────────┘                             └─────────┘
   └──────────────┘
```

- **Single-writer model**: only the `cognee` service writes to the stores. The ingestion sidecar
  and the MCP server push everything through the cognee HTTP API.
- **Three memories** (the self-improving-agent pattern): *factual* = code + database + SaaS data
  (this repo), *behavioral* + *procedural* = the agent's own instructions and skills (Hermes side).

---

## Prerequisites

- **Docker** + **Docker Compose**
- An **LLM API key** (OpenAI by default) — needed for `cognify` and embeddings. The stack boots
  without it, but graph construction (`cognify`) fails until it is set.

---

## Install & Run

```bash
git clone https://github.com/dcossios/Loom.git
cd Loom

# Create your env file and set the LLM key (other creds can be added later)
cp .env.template .env
#   edit .env -> LLM_API_KEY="sk-..."

docker compose up -d --build
```

This starts three services:

| Service          | Port(s)                | Role                                   |
|------------------|------------------------|----------------------------------------|
| `cognee`         | `8000`                 | HTTP API (add / cognify / search)      |
| `falkordb`       | `6379`, UI `3001`      | Graph database (+ FalkorDB Browser)    |
| `ingestion-cron` | —                      | Cron sidecar that feeds the brain      |

Verify it's up:

```bash
curl -f http://localhost:8000/health
# {"status":"ready","health":"healthy",...}
```

Stop with `docker compose down`. Default stores (LanceDB + SQLite) and the FalkorDB volume persist
between restarts.

---

## Ingest your data (factual memory)

The `ingestion-cron` sidecar pulls each source, uploads it to the cognee API, and runs `cognify`.
Configure sources in `.env`, then either wait for the cron schedule or trigger an immediate pass by
setting `RUN_ON_START=true` on the `ingestion-cron` service and restarting it.

### Codebase
Mount your repo (read-only) into the sidecar and point `REPO_PATH` at it. In `docker-compose.yml`,
under the `ingestion-cron` service, uncomment and edit:

```yaml
    volumes:
      - /ABS/PATH/to/your/repo:/repos/flowly:ro
```

Source files are ingested as text and cognified into dataset `flowly_code`.

### Database (read-only)
Use a **read-only** DB user — only `SELECT`s are issued.

```bash
DB_INGEST_URL=postgresql://readonly:pass@host.docker.internal:5432/yourdb
DB_INGEST_TABLES=users,subscriptions,tickets   # or set DB_INGEST_QUERY="SELECT ..."
```

### SaaS connectors (Linear / Sentry / Slack)
Set the token(s); a connector with no token simply skips.

| Source | Env vars | Where to get the token |
|--------|----------|------------------------|
| **Linear** | `LINEAR_API_KEY` | Settings → Security & access → Personal API keys |
| **Sentry** | `SENTRY_AUTH_TOKEN`, `SENTRY_ORG`, `SENTRY_PROJECT` | Settings → Auth Tokens (scopes `project:read`, `event:read`) |
| **Slack**  | `SLACK_BOT_TOKEN`, `SLACK_CHANNELS` | api.slack.com/apps → bot scopes `channels:history,channels:read,groups:history,users:read` → install → **invite the bot to the channels** |

> Gmail ships as a stub (`ingestion/ingest_gmail.py`) — fill in `fetch_records()` to enable it.

### Manual / one-off
```bash
curl -F 'data=@./notes.md' -F 'datasetName=docs' http://localhost:8000/api/v1/add
curl -X POST http://localhost:8000/api/v1/cognify \
  -H 'Content-Type: application/json' -d '{"datasets":["docs"]}'
```

---

## Query the brain

```bash
curl -X POST http://localhost:8000/api/v1/search \
  -H 'Content-Type: application/json' \
  -d '{"search_type":"GRAPH_COMPLETION","query":"What does the auth module do?"}'
```

Other useful endpoints: `POST /api/v1/recall` (auto-routed query), `POST /api/v1/remember`
(store + cognify), `POST /api/v1/improve` (feedback loop). Search types include `GRAPH_COMPLETION`,
`RAG_COMPLETION`, `CHUNKS`, `SUMMARIES`, `CYPHER`, `TEMPORAL` and more (see `CLAUDE.md`).

Inspect the graph directly in the **FalkorDB Browser** at <http://localhost:3001>, or:

```bash
docker compose exec falkordb redis-cli GRAPH.LIST
```

---

## Connect Hermes Agent (MCP over HTTP)

Loom exposes its tools through Cognee's **MCP server**, run in *client mode* so every write still
goes through the single cognee writer. [Hermes Agent](https://hermes-agent.nousresearch.com/) keeps
its own personal memory and skills and calls Loom as a shared source of truth — it does **not**
replace Hermes' native memory.

### 1. Start the MCP server

```bash
docker compose --profile mcp up -d --build cognee-mcp
```

This serves MCP at **`http://<HOST>:8001/mcp`** and proxies to the cognee API
(`API_URL=http://cognee:8000`). Check the logs show `API mode enabled: http://cognee:8000`.

### 2. Install Hermes Agent

```bash
curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash
hermes setup
```

### 3. Point Hermes at Loom

Edit `~/.hermes/config.yaml` and add an MCP server entry (use the host's IP/domain if Hermes runs
on a different machine than the Docker stack):

```yaml
mcp_servers:
  cognee:
    url: "http://localhost:8001/mcp"
    tools:
      include: [search, recall, remember, save_interaction, cognify, list_data]
```

Then reload from a Hermes chat:

```
/reload-mcp
```

Now Hermes can `recall`/`search` your org brain and `remember`/`save_interaction` back into it.
Verify by asking Hermes to recall something you ingested.

> **Tip:** to keep the brain read-mostly for the agent, narrow `tools.include` to
> `[search, recall, list_data]`.

---

## Configuration reference

Key variables in `.env` (full list and provider options in `.env.template` and `CLAUDE.md`):

| Variable | Purpose |
|----------|---------|
| `LLM_API_KEY`, `LLM_MODEL` | LLM for cognify/search (default `openai/gpt-4o-mini`) |
| `GRAPH_DATABASE_PROVIDER=falkor` | Graph backend (FalkorDB community adapter) |
| `GRAPH_DATABASE_URL=falkordb`, `GRAPH_DATABASE_PORT=6379` | FalkorDB connection |
| `VECTOR_DB_PROVIDER=lancedb`, `DB_PROVIDER=sqlite` | Local vector + relational stores |
| `ENABLE_BACKEND_ACCESS_CONTROL=False`, `REQUIRE_AUTHENTICATION=False` | Single-user/single-writer posture |
| `REPO_PATH`, `DB_INGEST_URL`, `LINEAR_API_KEY`, `SENTRY_AUTH_TOKEN`, `SLACK_BOT_TOKEN` | Ingestion sources |

---

## Resources

- Cognee docs: <https://docs.cognee.ai/>
- Community plugins & DB adapters (incl. FalkorDB): <https://github.com/topoteretes/cognee-community>
- Hermes Agent docs: <https://hermes-agent.nousresearch.com/docs>

## License

Apache-2.0 (inherited from Cognee). See [`LICENSE`](LICENSE).
