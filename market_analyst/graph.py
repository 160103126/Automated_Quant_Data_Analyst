from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypedDict

from langgraph.graph import END, StateGraph

from .skill_loader import load_skill

if TYPE_CHECKING:
    from .report_service import MarketReportService


class MarketReportState(TypedDict, total=False):
    tickers: list[str]
    history_period: str
    trend_period: str
    interval: str
    persist: bool
    save_report: bool
    skill: str
    analyses: list[dict[str, Any]]
    markdown: str
    report_path: str | None
    tool_calls: list[dict[str, Any]]
    warnings: list[str]
    llm_used: bool
    graph_used: bool


def build_market_report_graph(service: MarketReportService):
    graph = StateGraph(MarketReportState)

    async def load_runtime_skill(state: MarketReportState) -> MarketReportState:
        return {"skill": load_skill(service.settings.skill_path)}

    async def initialize_storage(state: MarketReportState) -> MarketReportState:
        warnings = state.setdefault("warnings", [])
        tool_calls = state.setdefault("tool_calls", [])
        await service._initialize_sqlite(warnings, tool_calls)
        return {"warnings": warnings, "tool_calls": tool_calls}

    async def collect_market_data(state: MarketReportState) -> MarketReportState:
        tool_calls = state.setdefault("tool_calls", [])
        warnings = state.setdefault("warnings", [])
        analyses: list[dict[str, Any]] = []
        for ticker in [ticker.strip().upper() for ticker in state["tickers"] if ticker.strip()]:
            analyses.append(
                await service._analyze_ticker(
                    ticker,
                    state["history_period"],
                    state["trend_period"],
                    state["interval"],
                    tool_calls,
                    warnings,
                ),
            )
        return {"analyses": analyses, "warnings": warnings, "tool_calls": tool_calls}

    async def enhance_sentiment(state: MarketReportState) -> MarketReportState:
        analyses, llm_used = await service._enhance_sentiment_with_llm(
            state["analyses"],
            state["skill"],
            state.setdefault("warnings", []),
        )
        return {"analyses": analyses, "llm_used": llm_used}

    async def persist_results(state: MarketReportState) -> MarketReportState:
        if not state["persist"]:
            return {}
        tool_calls = state.setdefault("tool_calls", [])
        warnings = state.setdefault("warnings", [])
        for analysis in state["analyses"]:
            await service._persist_ticker_analysis(analysis, warnings, tool_calls)
        return {"warnings": warnings, "tool_calls": tool_calls}

    async def write_report(state: MarketReportState) -> MarketReportState:
        markdown, llm_used = await service._render_llm_markdown(
            state["analyses"],
            state["skill"],
            state.setdefault("warnings", []),
        )
        return {"markdown": markdown, "llm_used": bool(state.get("llm_used")) or llm_used}

    async def save_report(state: MarketReportState) -> MarketReportState:
        if not state["save_report"]:
            return {"report_path": None}
        tool_calls = state.setdefault("tool_calls", [])
        warnings = state.setdefault("warnings", [])
        report_path = await service._save_report(state["markdown"], warnings, tool_calls)
        return {"report_path": report_path, "warnings": warnings, "tool_calls": tool_calls}

    graph.add_node("load_runtime_skill", load_runtime_skill)
    graph.add_node("initialize_storage", initialize_storage)
    graph.add_node("collect_market_data", collect_market_data)
    graph.add_node("enhance_sentiment", enhance_sentiment)
    graph.add_node("persist_results", persist_results)
    graph.add_node("write_report", write_report)
    graph.add_node("save_report", save_report)

    graph.set_entry_point("load_runtime_skill")
    graph.add_edge("load_runtime_skill", "initialize_storage")
    graph.add_edge("initialize_storage", "collect_market_data")
    graph.add_edge("collect_market_data", "enhance_sentiment")
    graph.add_edge("enhance_sentiment", "persist_results")
    graph.add_edge("persist_results", "write_report")
    graph.add_edge("write_report", "save_report")
    graph.add_edge("save_report", END)

    return graph.compile()
