---
name: financial-data-analyst
description: Produce daily market analysis reports by combining deterministic MCP-based market data, technical indicators, persisted history, and current news sentiment. Use when an application or agent needs an executive summary, technical analysis, and sentiment analysis for listed tickers, equities, ETFs, or crypto tickers.
---

# Financial Data Analyst

Use this skill as a runtime instruction contract for market reports.

## Rules

- Never calculate technical indicators or complex market math in language model text. Call the finance MCP for history, moving averages, RSI, trend, drawdown, and volatility.
- Cross-reference price movement with recent news sentiment from Tavily when available.
- Persist raw latest prices, indicators, and sentiment summaries into SQLite before writing the final report when persistence is enabled.
- Save final reports through the filesystem MCP when report saving is enabled.
- Format reports with these sections in order: Executive Summary, Technical Analysis, Sentiment Analysis.
- Mark unavailable data clearly instead of inventing values.
- Treat all outputs as research, not financial advice.

## Runtime MCP Contract

- finance: `fetch_stock_history`, `calculate_technical_indicators`, `calculate_trend`
- tavily: search recent qualitative market news
- sqlite: create/update `daily_prices`, `technical_indicators`, and `market_sentiment`
- filesystem: write Markdown reports under `reports/`
