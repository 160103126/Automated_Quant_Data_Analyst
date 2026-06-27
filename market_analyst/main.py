from fastapi import Depends, FastAPI

from .config import Settings, get_settings
from .models import DailyReportRequest, DailyReportResponse
from .report_service import MarketReportService

app = FastAPI(title="Automated Quant Data Analyst", version="0.1.0")


def get_service(settings: Settings = Depends(get_settings)) -> MarketReportService:
    return MarketReportService(settings)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/reports/daily", response_model=DailyReportResponse)
async def daily_report(
    request: DailyReportRequest,
    service: MarketReportService = Depends(get_service),
) -> dict:
    return await service.build_daily_report(
        tickers=request.tickers,
        history_period=request.history_period,
        trend_period=request.trend_period,
        interval=request.interval,
        persist=request.persist,
        save_report=request.save_report,
    )
