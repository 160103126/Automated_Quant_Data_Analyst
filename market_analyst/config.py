from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel


class Settings(BaseModel):
    mcp_gateway_url: str = "http://localhost:8000"
    skill_path: Path = Path(__file__).resolve().parents[1] / "skills" / "financial-data-analyst" / "SKILL.md"
    default_history_period: str = "1y"
    default_trend_period: str = "3mo"
    report_directory: str = "/data/fs/reports"
    report_timezone: str = "Asia/Calcutta"


@lru_cache
def get_settings() -> Settings:
    import os

    return Settings(
        mcp_gateway_url=os.getenv("MCP_GATEWAY_URL", Settings().mcp_gateway_url).rstrip("/"),
        skill_path=Path(os.getenv("FINANCIAL_ANALYST_SKILL_PATH", str(Settings().skill_path))),
        default_history_period=os.getenv("DEFAULT_HISTORY_PERIOD", Settings().default_history_period),
        default_trend_period=os.getenv("DEFAULT_TREND_PERIOD", Settings().default_trend_period),
        report_directory=os.getenv("REPORT_DIRECTORY", Settings().report_directory),
        report_timezone=os.getenv("REPORT_TIMEZONE", Settings().report_timezone),
    )
