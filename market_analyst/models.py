from pydantic import BaseModel, Field


class DailyReportRequest(BaseModel):
    tickers: list[str] = Field(default_factory=lambda: ["AAPL", "BTC-USD"])
    history_period: str = "1y"
    trend_period: str = "3mo"
    interval: str = "1d"
    persist: bool = True
    save_report: bool = True


class DailyReportResponse(BaseModel):
    report_path: str | None
    markdown: str
    skill_path: str
    tool_calls: list[dict]
    warnings: list[str] = Field(default_factory=list)
    llm_used: bool = False
    graph_used: bool = False
