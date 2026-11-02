# ClearMind — Information Overload Shield

A privacy-first multi-agent system that reads device usage exports, detects overload patterns and proposes a personalised 7-day digital-detox plan for users aged 16–25.

## Why this exists

Young people consume many hours of content per day and rarely notice overload as it happens. Existing apps report screen time but do not explain which patterns cause the problem or what to change. ClearMind parses real exports (Apple Screen Time, Google Digital Wellbeing, TikTok and Instagram data downloads), scores overload and keeps a human in the loop for every step of the plan.

## Architecture

```
Frontend (React + Vite)
        │ HTTP
FastAPI backend (api/main.py)
        │ A2A
┌───────┼──────────┬──────────┐
Parser  Analyzer   Coach      Guard
Agent   Agent      Agent      Agent
        │
MCP server (export parsers)
```

| Agent | Role |
|-------|------|
| Parser | Reads and normalises exports through the MCP server |
| Analyzer | Orchestrates, detects patterns, computes the Overload Score |
| Coach | Conversational agent that builds the detox plan with user approval |
| Guard | Checks consent gates and that no raw data is persisted |

## Run with Docker

```bash
git clone https://github.com/iencislennon/cleanmind
cd cleanmind
cp .env.example .env        # add GEMINI_API_KEY
docker build -t clearmind .
docker run --rm -p 8000:8000 --env-file .env clearmind
curl localhost:8000/health  # {"status":"ok","service":"clearmind-api"}
```

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env        # add GEMINI_API_KEY
./scripts/run_local.sh
```

Frontend only: `cd frontend && npm ci && npm run build`.

## Supported inputs

| Source | Format |
|--------|--------|
| Apple Screen Time | XML |
| Google Digital Wellbeing | CSV |
| TikTok data download | JSON |
| Instagram data download | JSON |

## Privacy

Data is processed within a session. When the session ends, raw data is discarded and only aggregated metrics (Overload Score, top patterns) remain. The Guard agent enforces consent gates at each step.

## Tests and quality

```bash
pytest tests/
```

Status of CI, dependency audit and staging deployment: not yet configured.

## Limitations

- Requires a Gemini API key; there is no offline demo mode yet.
- Synthetic Screen Time fixtures are not yet included.

## License

MIT
