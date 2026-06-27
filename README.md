# Automated Quant Data Analyst

This folder contains the application layer for the Automated Quant/Data Analyst system.

The application is intentionally separate from the MCP server infrastructure in:

```text
C:\MachineLearning\MCP_servers
```

The MCP folder owns tool servers. This folder owns the deployable product that calls those tools programmatically.

## What This Application Does

The app produces market analysis reports by orchestrating several MCP tools at runtime:

1. Load the runtime financial analyst skill from `skills/financial-data-analyst/SKILL.md`.
2. Call the finance MCP for deterministic price history and technical indicators.
3. Call Tavily MCP for current qualitative market news.
4. Call SQLite MCP to create/update local market tracking tables.
5. Call Filesystem MCP to write Markdown reports.
6. Return a structured API response containing the report, saved path, tool calls, and warnings.

The app exposes this workflow as an HTTP API through FastAPI.

## Why The App Is Separate From MCP Servers

This project should be deployable as a production application. MCP servers are infrastructure dependencies, similar to databases, queues, or internal APIs.

Keeping the app separate gives cleaner operations:

- MCP servers can be deployed once and shared by multiple applications.
- The app can be deployed independently, scaled independently, and versioned independently.
- The app talks to MCP over HTTP/SSE instead of importing server code directly.
- Skills are packaged with the app because they are runtime application behavior, not MCP server infrastructure.
- Future production deployment can point `MCP_GATEWAY_URL` at staging, production, or remote MCP gateways without moving application code.

## Folder Structure

```text
Automated_Quant_Data_Analyst/
|-- Dockerfile
|-- docker-compose.yml
|-- init_db.py
|-- requirements.txt
|-- market_analyst/
|   |-- __init__.py
|   |-- config.py
|   |-- main.py
|   |-- mcp_client.py
|   |-- models.py
|   |-- report_service.py
|   `-- skill_loader.py
`-- skills/
    `-- financial-data-analyst/
        `-- SKILL.md
```

## Main Components

### `market_analyst/main.py`

FastAPI entry point.

Endpoints:

- `GET /health`
- `POST /reports/daily`

`/reports/daily` accepts ticker and workflow options, then delegates to `MarketReportService`.

### `market_analyst/config.py`

Runtime settings loaded from environment variables.

Important settings:

| Setting | Default | Purpose |
|---|---|---|
| `MCP_GATEWAY_URL` | `http://localhost:8000` in local Python, `http://host.docker.internal:8000` in Docker | Base URL for the MCP gateway. |
| `FINANCIAL_ANALYST_SKILL_PATH` | bundled skill path | Runtime skill file to load. |
| `DEFAULT_HISTORY_PERIOD` | `1y` | Default period for indicator calculations. |
| `DEFAULT_TREND_PERIOD` | `3mo` | Default period for trend calculations. |
| `REPORT_DIRECTORY` | `/data/fs/reports` | Filesystem MCP container path for reports. |
| `REPORT_TIMEZONE` | `Asia/Calcutta` | Date timezone for report titles and filenames. |

### `market_analyst/mcp_client.py`

Small MCP client wrapper using the official Python MCP client.

Responsibilities:

- Open SSE sessions to MCP gateway server routes.
- List available tools.
- Call specific tools.
- Try first matching tool name when MCP package versions differ.
- Decode MCP text tool responses into JSON when possible.

MCP route pattern:

```text
{MCP_GATEWAY_URL}/servers/{server}/sse
```

Examples:

```text
http://localhost:8000/servers/finance/sse
http://localhost:8000/servers/sqlite/sse
http://localhost:8000/servers/filesystem/sse
```

### `market_analyst/report_service.py`

Workflow orchestration layer.

This is where the app turns a request into a report:

1. Load the financial analyst skill.
2. Initialize SQLite tables.
3. For each ticker:
   - fetch OHLCV history from finance MCP
   - calculate indicators from finance MCP
   - calculate trend metrics from finance MCP
   - fetch recent news from Tavily MCP
   - persist latest price, indicators, and sentiment to SQLite MCP
4. Render Markdown.
5. Save Markdown through Filesystem MCP.
6. Return the full result.

### `market_analyst/models.py`

Pydantic request and response models.

### `market_analyst/skill_loader.py`

Loads the runtime skill from disk. This is deliberately simple: the skill is data/configuration for the app, not a developer-only prompt.

### `skills/financial-data-analyst/SKILL.md`

The runtime analyst skill.

The app loads this file during report generation and uses its instructions as the report contract. This is how skills are made part of application runtime behavior rather than only being editor-agent behavior.

### `init_db.py`

Utility script that initializes the SQLite MCP schema through the MCP gateway.

It calls:

```text
{MCP_GATEWAY_URL}/servers/sqlite/sse
```

and creates:

- `daily_prices`
- `technical_indicators`
- `market_sentiment`

The application also initializes tables automatically during report generation, so this script is useful for manual setup and verification but is not strictly required for every run.

## Runtime MCP Dependencies

The app expects the MCP server stack to be running from:

```text
C:\MachineLearning\MCP_servers
```

Required MCP servers:

| MCP server | Used for |
|---|---|
| `finance` | Price history, technical indicators, trend metrics. |
| `tavily` | Recent market news and qualitative context. |
| `sqlite` | Local persistence for prices, indicators, and sentiment. |
| `filesystem` | Markdown report output. |

Optional MCP servers may exist in the gateway, but these four are the core application path.

## Start MCP Servers First

From the MCP servers folder:

```powershell
cd C:\MachineLearning\MCP_servers
docker compose up -d --build
```

Confirm the gateway is reachable:

```powershell
Invoke-RestMethod http://localhost:8000/status
```

## Run The Application With Docker

From this folder:

```powershell
cd C:\MachineLearning\Automated_Quant_Data_Analyst
docker compose up -d --build
```

The app listens on:

```text
http://localhost:8080
```

Health check:

```powershell
Invoke-RestMethod http://localhost:8080/health
```

Because the app container is outside the MCP compose network, it defaults to:

```text
MCP_GATEWAY_URL=http://host.docker.internal:8000
```

That points from the app container back to the host-published MCP gateway port.

## Run The Application Locally Without Docker

From this folder:

```powershell
cd C:\MachineLearning\Automated_Quant_Data_Analyst
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:MCP_GATEWAY_URL = "http://localhost:8000"
uvicorn market_analyst.main:app --host 127.0.0.1 --port 8080
```

Then open:

```text
http://localhost:8080/docs
```

## API Usage

### Health

```powershell
Invoke-RestMethod http://localhost:8080/health
```

Response:

```json
{
  "status": "ok"
}
```

### Generate Daily Report

```powershell
$body = @{
  tickers = @("AAPL", "BTC-USD")
  history_period = "1y"
  trend_period = "1mo"
  interval = "1d"
  persist = $true
  save_report = $true
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8080/reports/daily `
  -ContentType 'application/json' `
  -Body $body
```

Request fields:

| Field | Type | Meaning |
|---|---|---|
| `tickers` | list of strings | Symbols to analyze, e.g. `AAPL`, `MSFT`, `BTC-USD`. |
| `history_period` | string | Period used by finance MCP for history and indicators. |
| `trend_period` | string | Period used for trend metrics. |
| `interval` | string | Candle interval, usually `1d`. |
| `persist` | boolean | Whether to write data to SQLite MCP. |
| `save_report` | boolean | Whether to write Markdown through Filesystem MCP. |

Response fields:

| Field | Meaning |
|---|---|
| `report_path` | Host-visible report path when saved, e.g. `data/fs/reports/2026-06-28-Market-Analysis.md`. |
| `markdown` | Full report content. |
| `skill_path` | Skill file loaded by the application runtime. |
| `tool_calls` | MCP servers/tools called and whether each returned successfully. |
| `warnings` | Non-fatal problems, such as unavailable sentiment search. |

## Report Output Location

The app saves reports through the filesystem MCP, not by writing directly to the app container filesystem.

Inside the filesystem MCP container, reports are written to:

```text
/data/fs/reports
```

On the host machine, this maps to:

```text
C:\MachineLearning\MCP_servers\data\fs\reports
```

This is expected because the filesystem MCP server owns file writes. The application requests file writes through MCP.

## SQLite Persistence

The app creates and updates three tables through the SQLite MCP.

### `daily_prices`

Stores latest close and volume by ticker/date.

Columns:

- `id`
- `ticker`
- `date`
- `close_price`
- `volume`
- `created_at`

### `technical_indicators`

Stores computed technical indicators by ticker/date.

Columns:

- `ticker`
- `date`
- `sma_50`
- `sma_200`
- `rsi`
- `volatility_20d_annualized`
- `created_at`

### `market_sentiment`

Stores qualitative news summary and score by ticker/date.

Columns:

- `ticker`
- `date`
- `news_summary`
- `sentiment_score`
- `created_at`

## Runtime Skill Behavior

The skill file is not only documentation. The app loads it at runtime and includes its rules in the report-generation flow.

Current skill rules include:

- Use finance MCP for math and indicators.
- Cross-reference price movement with recent news when available.
- Persist prices, indicators, and sentiment when persistence is enabled.
- Save final reports through filesystem MCP when report saving is enabled.
- Format reports with Executive Summary, Technical Analysis, and Sentiment Analysis.
- Mark unavailable data clearly instead of inventing values.
- Treat output as research, not financial advice.

This pattern makes the skill deployable with the app. A future LLM-based report writer can load the same skill and use it as its instruction contract.

## Environment Variables

| Variable | Docker default | Local default | Description |
|---|---|---|---|
| `MCP_GATEWAY_URL` | `http://host.docker.internal:8000` | `http://localhost:8000` | MCP gateway base URL. |
| `FINANCIAL_ANALYST_SKILL_PATH` | bundled path | bundled path | Override skill file path. |
| `DEFAULT_HISTORY_PERIOD` | `1y` | `1y` | Default indicator period. |
| `DEFAULT_TREND_PERIOD` | `3mo` | `3mo` | Default trend period. |
| `REPORT_DIRECTORY` | `/data/fs/reports` | `/data/fs/reports` | Path understood by filesystem MCP. |
| `REPORT_TIMEZONE` | `Asia/Calcutta` | `Asia/Calcutta` | Date timezone for reports. |

## Important Boundary Rules

Do not add MCP server source code to this application folder.

Do not add application source code to `C:\MachineLearning\MCP_servers`.

The correct relationship is:

```text
Application -> MCP gateway -> MCP servers
```

not:

```text
Application imports MCP server code directly
```

## Troubleshooting

### The app cannot connect to MCP

Check that MCP servers are running:

```powershell
cd C:\MachineLearning\MCP_servers
docker ps
Invoke-RestMethod http://localhost:8000/status
```

If the app runs in Docker, confirm `MCP_GATEWAY_URL` is:

```text
http://host.docker.internal:8000
```

If the app runs locally, use:

```text
http://localhost:8000
```

### Finance calls return empty or stale errors

Restart the gateway after rebuilding `finance-mcp`:

```powershell
cd C:\MachineLearning\MCP_servers
docker compose restart mcp-gateway
```

### Reports are not written

The filesystem MCP only allows paths under `/data/fs` inside the filesystem MCP container. Use:

```text
REPORT_DIRECTORY=/data/fs/reports
```

Host-visible output should appear under:

```text
C:\MachineLearning\MCP_servers\data\fs\reports
```

### Tavily sentiment is unavailable

Confirm `TAVILY_API_KEY` is set in the MCP servers `.env` file and the Tavily container is healthy.

### Dates look wrong

Set:

```text
REPORT_TIMEZONE=Asia/Calcutta
```

The report date uses this timezone for titles and filenames.

## Production Hardening Roadmap

Recommended next steps before production use:

- Add automated tests for `McpGatewayClient` using mocked MCP responses.
- Add service-level tests for `/reports/daily` with stubbed MCP servers.
- Add structured logging with report IDs and ticker IDs.
- Add request timeouts around MCP calls.
- Add retry policy for transient network/provider failures.
- Replace naive sentiment scoring with an explicit sentiment model or LLM call governed by the runtime skill.
- Add authentication to the FastAPI app.
- Add OpenAPI examples for report requests.
- Add CI checks for formatting, type checking, and tests.
- Version skill files and include skill version in report metadata.
- Add provider abstraction if finance MCP moves from Yahoo Finance to a licensed feed.

## Quick Start Summary

1. Start MCP servers:

```powershell
cd C:\MachineLearning\MCP_servers
docker compose up -d --build
```

2. Start app:

```powershell
cd C:\MachineLearning\Automated_Quant_Data_Analyst
docker compose up -d --build
```

3. Generate report:

```powershell
$body = @{ tickers = @("AAPL"); persist = $true; save_report = $true } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://localhost:8080/reports/daily -ContentType 'application/json' -Body $body
```
