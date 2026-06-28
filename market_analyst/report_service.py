from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .config import Settings
from .graph import build_market_report_graph
from .llm import create_gemini_model
from .mcp_client import McpGatewayClient
from .skill_loader import load_skill


class MarketReportService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.mcp = McpGatewayClient(settings.mcp_gateway_url)
        self._llm = None

    async def build_daily_report(
        self,
        tickers: list[str],
        history_period: str,
        trend_period: str,
        interval: str,
        persist: bool,
        save_report: bool,
    ) -> dict[str, Any]:
        if self.settings.enable_llm_reporting:
            try:
                graph = build_market_report_graph(self)
                state = await graph.ainvoke({
                    "tickers": tickers,
                    "history_period": history_period,
                    "trend_period": trend_period,
                    "interval": interval,
                    "persist": persist,
                    "save_report": save_report,
                    "tool_calls": [],
                    "warnings": [],
                    "llm_used": False,
                    "graph_used": True,
                })
                return {
                    "report_path": state.get("report_path"),
                    "markdown": state.get("markdown", ""),
                    "skill_path": str(self.settings.skill_path),
                    "tool_calls": state.get("tool_calls", []),
                    "warnings": state.get("warnings", []),
                    "llm_used": bool(state.get("llm_used")),
                    "graph_used": True,
                }
            except Exception as exc:
                fallback = await self._build_deterministic_report(
                    tickers,
                    history_period,
                    trend_period,
                    interval,
                    persist,
                    save_report,
                )
                fallback["warnings"].append(f"LangGraph/Gemini workflow unavailable; deterministic fallback used: {exc}")
                fallback["graph_used"] = False
                fallback["llm_used"] = False
                return fallback

        return await self._build_deterministic_report(
            tickers,
            history_period,
            trend_period,
            interval,
            persist,
            save_report,
        )

    async def _build_deterministic_report(
        self,
        tickers: list[str],
        history_period: str,
        trend_period: str,
        interval: str,
        persist: bool,
        save_report: bool,
    ) -> dict[str, Any]:
        skill = load_skill(self.settings.skill_path)
        tool_calls: list[dict[str, Any]] = []
        warnings: list[str] = []
        analyses: list[dict[str, Any]] = []

        await self._initialize_sqlite(warnings, tool_calls)

        for ticker in [ticker.strip().upper() for ticker in tickers if ticker.strip()]:
            analysis = await self._analyze_ticker(ticker, history_period, trend_period, interval, tool_calls, warnings)
            analyses.append(analysis)
            if persist:
                await self._persist_ticker_analysis(analysis, warnings, tool_calls)

        markdown = self._render_markdown(analyses, skill)
        report_path = None
        if save_report:
            report_path = await self._save_report(markdown, warnings, tool_calls)

        return {
            "report_path": report_path,
            "markdown": markdown,
            "skill_path": str(self.settings.skill_path),
            "tool_calls": tool_calls,
            "warnings": warnings,
            "llm_used": False,
            "graph_used": False,
        }

    async def _analyze_ticker(
        self,
        ticker: str,
        history_period: str,
        trend_period: str,
        interval: str,
        tool_calls: list[dict[str, Any]],
        warnings: list[str],
    ) -> dict[str, Any]:
        history = await self._call("finance", "fetch_stock_history", {
            "ticker": ticker,
            "period": history_period,
            "interval": interval,
        }, tool_calls)
        indicators = await self._call("finance", "calculate_technical_indicators", {
            "ticker": ticker,
            "period": history_period,
            "interval": interval,
        }, tool_calls)
        trend = await self._call("finance", "calculate_trend", {
            "ticker": ticker,
            "period": trend_period,
            "interval": interval,
        }, tool_calls)

        sentiment = await self._fetch_sentiment(ticker, warnings, tool_calls)
        return {
            "ticker": ticker,
            "history": history,
            "indicators": indicators,
            "trend": trend,
            "sentiment": sentiment,
        }

    async def _fetch_sentiment(
        self,
        ticker: str,
        warnings: list[str],
        tool_calls: list[dict[str, Any]],
    ) -> dict[str, Any]:
        query = f"{ticker} market news last 24 hours catalysts price movement"
        candidates = ["tavily_search", "tavily-search", "search"]
        try:
            tool, result = await self.mcp.call_first_available(
                "tavily",
                candidates,
                {"query": query, "max_results": 5, "search_depth": "advanced"},
            )
            tool_calls.append({"server": "tavily", "tool": tool, "ok": not self._has_error(result)})
            return self._summarize_sentiment(result)
        except Exception as exc:
            warnings.append(f"Tavily sentiment unavailable for {ticker}: {exc}")
            return {"summary": "Sentiment search unavailable.", "score": None, "sources": []}

    async def _initialize_sqlite(self, warnings: list[str], tool_calls: list[dict[str, Any]]) -> None:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS daily_prices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                date TEXT NOT NULL,
                close_price REAL,
                volume INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ticker, date)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS technical_indicators (
                ticker TEXT NOT NULL,
                date TEXT NOT NULL,
                sma_50 REAL,
                sma_200 REAL,
                rsi REAL,
                volatility_20d_annualized REAL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(ticker, date)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS market_sentiment (
                ticker TEXT NOT NULL,
                date TEXT NOT NULL,
                news_summary TEXT,
                sentiment_score REAL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(ticker, date)
            )
            """,
        ]
        for statement in statements:
            await self._sqlite_statement(statement, warnings, tool_calls)

    async def _persist_ticker_analysis(
        self,
        analysis: dict[str, Any],
        warnings: list[str],
        tool_calls: list[dict[str, Any]],
    ) -> None:
        ticker = analysis["ticker"]
        latest = (analysis.get("history") or {}).get("latest") or {}
        indicators = analysis.get("indicators") or {}
        sentiment = analysis.get("sentiment") or {}
        as_of = latest.get("date") or indicators.get("date") or self._report_date()

        await self._sqlite_statement(
            """
            INSERT INTO daily_prices (ticker, date, close_price, volume)
            VALUES (:ticker, :date, :close_price, :volume)
            """,
            warnings,
            tool_calls,
            {"ticker": ticker, "date": as_of, "close_price": latest.get("close"), "volume": latest.get("volume")},
        )
        await self._sqlite_statement(
            """
            INSERT INTO technical_indicators
            (ticker, date, sma_50, sma_200, rsi, volatility_20d_annualized)
            VALUES (:ticker, :date, :sma_50, :sma_200, :rsi, :volatility)
            """,
            warnings,
            tool_calls,
            {
                "ticker": ticker,
                "date": as_of,
                "sma_50": indicators.get("sma_50"),
                "sma_200": indicators.get("sma_200"),
                "rsi": indicators.get("rsi"),
                "volatility": indicators.get("volatility_20d_annualized"),
            },
        )
        await self._sqlite_statement(
            """
            INSERT INTO market_sentiment (ticker, date, news_summary, sentiment_score)
            VALUES (:ticker, :date, :summary, :score)
            """,
            warnings,
            tool_calls,
            {"ticker": ticker, "date": as_of, "summary": sentiment.get("summary"), "score": sentiment.get("score")},
        )

    async def _sqlite_statement(
        self,
        statement: str,
        warnings: list[str],
        tool_calls: list[dict[str, Any]],
        params: dict[str, Any] | None = None,
    ) -> None:
        candidates = ["write_query", "execute_query", "query"]
        if params:
            for k, v in params.items():
                if v is None:
                    v = "NULL"
                elif isinstance(v, str):
                    v = f"'{v.replace(chr(39), chr(39)+chr(39))}'"
                statement = statement.replace(f":{k}", str(v))
        arguments_options = [{"query": statement}]
        last_error: Exception | None = None
        for arguments in arguments_options:
            try:
                tool, result = await self.mcp.call_first_available("sqlite", candidates, arguments)
                if self._has_error(result):
                    raise RuntimeError(f"SQL Error: {result.get('error') or result}")
                tool_calls.append({"server": "sqlite", "tool": tool, "ok": not self._has_error(result)})
                return
            except Exception as exc:
                last_error = exc
        warnings.append(f"SQLite statement skipped: {last_error}")

    async def _save_report(
        self,
        markdown: str,
        warnings: list[str],
        tool_calls: list[dict[str, Any]],
    ) -> str | None:
        filename = f"{self._report_date()}-Market-Analysis.md"
        path = f"{self.settings.report_directory.rstrip('/')}/{filename}"
        try:
            tool, result = await self.mcp.call_first_available(
                "filesystem",
                ["create_directory", "create-dir", "mkdir"],
                {"path": self.settings.report_directory},
            )
            tool_calls.append({"server": "filesystem", "tool": tool, "ok": not self._has_error(result)})
            if self._has_error(result):
                warnings.append(f"Filesystem directory create failed: {result.get('error')}")
                return None
        except Exception:
            pass

        try:
            tool, result = await self.mcp.call_first_available(
                "filesystem",
                ["write_file", "write-file"],
                {"path": path, "content": markdown},
            )
            tool_calls.append({"server": "filesystem", "tool": tool, "ok": not self._has_error(result)})
            if self._has_error(result):
                warnings.append(f"Filesystem report write failed: {result.get('error')}")
                return None
            return self._workspace_report_path(path)
        except Exception as exc:
            warnings.append(f"Filesystem report save unavailable: {exc}")
            return None

    def _workspace_report_path(self, mcp_path: str) -> str:
        prefix = "/data/fs/"
        if mcp_path.startswith(prefix):
            return f"data/fs/{mcp_path[len(prefix):]}"
        return mcp_path

    async def _call(self, server: str, tool: str, arguments: dict[str, Any], tool_calls: list[dict[str, Any]]) -> Any:
        result = await self.mcp.call_tool(server, tool, arguments)
        tool_calls.append({"server": server, "tool": tool, "ok": not self._has_error(result)})
        return result

    def _summarize_sentiment(self, result: Any) -> dict[str, Any]:
        text = json.dumps(result) if not isinstance(result, str) else result
        text = self._clean_text(text)
        positive_terms = ["beat", "upgrade", "surge", "record", "growth", "bullish", "rally"]
        negative_terms = ["miss", "downgrade", "fall", "lawsuit", "bearish", "slump", "concern"]
        lower = text.lower()
        raw_score = 5 + sum(term in lower for term in positive_terms) - sum(term in lower for term in negative_terms)
        return {
            "summary": text[:1200],
            "score": max(1, min(10, raw_score)),
            "sources": [],
            "raw": result,
        }

    async def _enhance_sentiment_with_llm(
        self,
        analyses: list[dict[str, Any]],
        skill: str,
        warnings: list[str],
    ) -> tuple[list[dict[str, Any]], bool]:
        llm = self._get_llm(warnings)
        if llm is None:
            return analyses, False

        prompt = (
            "You are a market sentiment analyst. Use only the supplied market/news data. "
            "Return strict JSON with this shape: "
            "{\"sentiment\": [{\"ticker\": \"AAPL\", \"score\": 1-10, \"summary\": \"...\", \"sources\": [\"...\"]}]}.\n\n"
            f"Runtime skill rules:\n{skill}\n\n"
            f"Ticker analyses JSON:\n{json.dumps(self._compact_analyses_for_llm(analyses), default=str)}"
        )
        try:
            content = await self._ainvoke_llm(llm, prompt)
            parsed = self._extract_json_object(content)
            sentiment_items = {item.get("ticker"): item for item in parsed.get("sentiment", []) if isinstance(item, dict)}
            for analysis in analyses:
                item = sentiment_items.get(analysis["ticker"])
                if not item:
                    continue
                analysis["sentiment"] = {
                    "summary": item.get("summary") or (analysis.get("sentiment") or {}).get("summary"),
                    "score": item.get("score"),
                    "sources": item.get("sources") or [],
                    "raw": (analysis.get("sentiment") or {}).get("raw"),
                }
            return analyses, True
        except Exception as exc:
            warnings.append(f"Gemini sentiment enhancement unavailable: {exc}")
            return analyses, False

    async def _render_llm_markdown(
        self,
        analyses: list[dict[str, Any]],
        skill: str,
        warnings: list[str],
    ) -> tuple[str, bool]:
        llm = self._get_llm(warnings)
        if llm is None:
            return self._render_markdown(analyses, skill), False

        prompt = (
            "Write a concise professional daily market report in Markdown. "
            "Use only the supplied data; do not invent prices, dates, indicators, sources, or causes. "
            "Keep these exact sections in order: Executive Summary, Technical Analysis, Sentiment Analysis. "
            "End with: 'Research only. Not financial advice.'\n\n"
            f"Report date: {self._report_date()}\n\n"
            f"Runtime skill rules:\n{skill}\n\n"
            f"Analyses JSON:\n{json.dumps(self._compact_analyses_for_llm(analyses), default=str)}"
        )
        try:
            markdown = await self._ainvoke_llm(llm, prompt)
            markdown = markdown.strip()
            if not markdown:
                raise RuntimeError("Gemini returned an empty report")
            return markdown, True
        except Exception as exc:
            warnings.append(f"Gemini report writer unavailable: {exc}")
            return self._render_markdown(analyses, skill), False

    def _get_llm(self, warnings: list[str]):
        if not self.settings.enable_llm_reporting:
            return None
        if self._llm is not None:
            return self._llm
        try:
            self._llm = create_gemini_model(self.settings)
            return self._llm
        except Exception as exc:
            warnings.append(f"Gemini model initialization unavailable: {exc}")
            return None

    async def _ainvoke_llm(self, llm: Any, prompt: str) -> str:
        response = await llm.ainvoke(prompt)
        content = getattr(response, "content", response)
        if isinstance(content, list):
            return "\n".join(str(part.get("text", part)) if isinstance(part, dict) else str(part) for part in content)
        return str(content)

    def _extract_json_object(self, text: str) -> dict[str, Any]:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.startswith("json"):
                cleaned = cleaned[4:].strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start >= 0 and end > start:
                return json.loads(cleaned[start : end + 1])
            raise

    def _compact_analyses_for_llm(self, analyses: list[dict[str, Any]]) -> list[dict[str, Any]]:
        compact: list[dict[str, Any]] = []
        for analysis in analyses:
            sentiment = analysis.get("sentiment") or {}
            compact.append({
                "ticker": analysis.get("ticker"),
                "latest": (analysis.get("history") or {}).get("latest"),
                "indicators": analysis.get("indicators"),
                "trend": analysis.get("trend"),
                "sentiment": {
                    "summary": sentiment.get("summary"),
                    "score": sentiment.get("score"),
                    "sources": sentiment.get("sources", []),
                    "raw": sentiment.get("raw"),
                },
            })
        return compact

    def _clean_text(self, text: str) -> str:
        replacements = {
            "â€“": "-",
            "â€”": "-",
            "â€˜": "'",
            "â€™": "'",
            "â€œ": '"',
            "â€�": '"',
            "â€¦": "...",
            "âš¡": "",
        }
        for source, target in replacements.items():
            text = text.replace(source, target)
        return text

    def _render_markdown(self, analyses: list[dict[str, Any]], skill: str) -> str:
        lines = [
            f"# Daily Market Report - {self._report_date()}",
            "",
            "## Executive Summary",
            "",
        ]
        for analysis in analyses:
            trend = analysis.get("trend") or {}
            indicators = analysis.get("indicators") or {}
            lines.append(
                f"- {analysis['ticker']}: close {trend.get('latest_close')}, "
                f"{trend.get('percent_change')}% over {trend.get('period')}; "
                f"RSI {indicators.get('rsi')}, 20d vol {indicators.get('volatility_20d_annualized')}."
            )

        lines.extend(["", "## Technical Analysis", ""])
        lines.append("| Ticker | Date | Close | SMA 50 | SMA 200 | RSI | 20d Vol | Trend % | Max Drawdown % |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
        for analysis in analyses:
            indicators = analysis.get("indicators") or {}
            trend = analysis.get("trend") or {}
            lines.append(
                f"| {analysis['ticker']} | {indicators.get('date')} | {indicators.get('close_price')} | "
                f"{indicators.get('sma_50')} | {indicators.get('sma_200')} | {indicators.get('rsi')} | "
                f"{indicators.get('volatility_20d_annualized')} | {trend.get('percent_change')} | "
                f"{trend.get('max_drawdown_percent')} |"
            )

        lines.extend(["", "## Sentiment Analysis", ""])
        for analysis in analyses:
            sentiment = analysis.get("sentiment") or {}
            lines.extend([
                f"### {analysis['ticker']}",
                "",
                f"Sentiment score: {sentiment.get('score')}",
                "",
                sentiment.get("summary") or "No sentiment summary available.",
                "",
            ])

        lines.extend([
            "## Runtime Skill Rules Applied",
            "",
            "The application loaded the financial analyst skill at runtime and used its rules to shape collection, persistence, and report format.",
            "",
            "<details><summary>Loaded skill</summary>",
            "",
            "```markdown",
            skill,
            "```",
            "",
            "</details>",
        ])
        return "\n".join(lines)

    def _has_error(self, result: Any) -> bool:
        return isinstance(result, dict) and bool(result.get("error"))

    def _report_date(self) -> str:
        try:
            return datetime.now(ZoneInfo(self.settings.report_timezone)).date().isoformat()
        except ZoneInfoNotFoundError:
            return date.today().isoformat()
