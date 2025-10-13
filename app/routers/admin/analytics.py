from datetime import date, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app import dependencies
from app.database.repositories.analytics_repository import AnalyticsRepository

class DailyActivityItem(BaseModel):
    date: date
    count: int

router = APIRouter(
    prefix="/analytics",
    tags=["Admin - Analytics"]
)

class ModelBreakdownItem(BaseModel):
    model_name: str
    count: int
    revenue: float

class AnalyticsReportResponse(BaseModel):
    total_generations: int
    total_revenue: float
    total_profit: float
    model_breakdown: List[ModelBreakdownItem]

@router.get("/report", response_model=AnalyticsReportResponse)
async def get_analytics_report(
    analytics_repo: AnalyticsRepository = Depends(dependencies.get_analytics_repository),
    start_date: date = Query(..., description="Начальная дата в формате YYYY-MM-DD"),
    end_date: date = Query(..., description="Конечная дата в формате YYYY-MM-DD"),
    user_telegram_id: Optional[int] = Query(None),
    api_key_id: Optional[int] = Query(None),
    model_name: Optional[str] = Query(None)
):
    report = await analytics_repo.get_analytics_report(
        start_date=start_date,
        end_date=end_date,
        user_telegram_id=user_telegram_id,
        api_key_id=api_key_id,
        model_name=model_name
    )
    return report


@router.get("/activity", response_model=List[DailyActivityItem])
async def get_activity_chart_data(
    analytics_repo: AnalyticsRepository = Depends(dependencies.get_analytics_repository),
    user_telegram_id: Optional[int] = Query(None),
    api_key_id: Optional[int] = Query(None),
):
    """Возвращает данные для построения графика активности за 30 дней."""

    activity_data = await analytics_repo.get_daily_activity(
        user_telegram_id=user_telegram_id,
        api_key_id=api_key_id
    )
    return activity_data