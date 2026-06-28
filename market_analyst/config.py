from dotenv import load_dotenv
load_dotenv()
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
    enable_llm_reporting: bool = True
    google_cloud_project: str | None = None
    google_cloud_location: str = "us-central1"
    gemini_model: str = "gemini-2.5-flash"
    llm_temperature: float = 0.2


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
        enable_llm_reporting=os.getenv("ENABLE_LLM_REPORTING", "true").lower() in {"1", "true", "yes", "on"},
        google_cloud_project=os.getenv("GOOGLE_CLOUD_PROJECT") or None,
        google_cloud_location=os.getenv("GOOGLE_CLOUD_LOCATION", Settings().google_cloud_location),
        gemini_model=os.getenv("GEMINI_MODEL", Settings().gemini_model),
        llm_temperature=float(os.getenv("LLM_TEMPERATURE", str(Settings().llm_temperature))),
    )
