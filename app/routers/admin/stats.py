from datetime import datetime, timezone, timedelta, date
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from motor.motor_asyncio import AsyncIOMotorCollection
from pydantic import BaseModel
from sqlalchemy import select, func

from app import dependencies
from app.database.main_models import User, ApiKey
from app.database.mongo_db import get_task_collection
from app.database.repositories.user_repository import UserRepository

router = APIRouter(
    prefix="/stats",
    tags=["Admin - API Stats"]
)


class AdminDashboardStats(BaseModel):
    total_users: int
    total_keys: int
    tasks_pending: int
    tasks_processing: int
    tasks_completed_24h: int
    tasks_failed_24h: int
    total_system_balance: float


class ModelUsageStat(BaseModel):
    model: str
    count: int

class UsageReport(BaseModel):
    period_start: date
    period_end: date
    total_profit: float
    model_usage: List[ModelUsageStat]



class DailyProfitability(BaseModel):
    date: str
    revenue: float
    prime_cost: float
    profit: float



@router.get("", response_model=AdminDashboardStats)
async def get_dashboard_stats(
        user_repo: UserRepository = Depends(dependencies.get_user_repository),
        tasks_collection: AsyncIOMotorCollection = Depends(get_task_collection),
):

    async with user_repo.session_factory() as session:
        total_users = await session.scalar(select(func.count(User.telegram_id)))
        total_keys = await session.scalar(select(func.count(ApiKey.id)))
        total_system_balance = await session.scalar(select(func.sum(ApiKey.balance)))

    tasks_pending = await tasks_collection.count_documents({"status": "pending"})
    tasks_processing = await tasks_collection.count_documents({"status": "processing"})


    twenty_four_hours_ago = datetime.now(timezone.utc) - timedelta(hours=24)


    tasks_completed_24h = await tasks_collection.count_documents({
        "status": "completed",
        "created_at": {"$gte": twenty_four_hours_ago}
    })
    tasks_failed_24h = await tasks_collection.count_documents({
        "status": "failed",
        "created_at": {"$gte": twenty_four_hours_ago}
    })

    return {
        "total_users": total_users or 0,
        "total_keys": total_keys or 0,
        "tasks_pending": tasks_pending,
        "tasks_processing": tasks_processing,
        "tasks_completed_24h": tasks_completed_24h,
        "tasks_failed_24h": tasks_failed_24h,
        "total_system_balance": float(total_system_balance or 0.0)
    }

@router.get("/models", response_model=List[ModelUsageStat])
async def get_model_usage_stats(
    tasks_collection: AsyncIOMotorCollection = Depends(get_task_collection)
):

    pipeline = [
        {"$match": {"status": "completed"}},
        {"$group": {"_id": "$model", "count": {"$sum": 1}}},
        {"$project": {"model": "$_id", "count": "$count", "_id": 0}}
    ]
    cursor = tasks_collection.aggregate(pipeline)
    return await cursor.to_list(length=None)



@router.get("/profitability", response_model=List[DailyProfitability])
async def get_profitability_stats(
    tasks_collection: AsyncIOMotorCollection = Depends(get_task_collection)
):

    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    pipeline = [
        {"$match": {"status": "completed", "created_at": {"$gte": thirty_days_ago}}},
        {"$group": {
            "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}},
            "total_revenue": {"$sum": "$cost"},
            "total_prime_cost": {"$sum": "$prime_cost"}
        }},
        {"$sort": {"_id": 1}},
        {"$project": {
            "date": "$_id",
            "revenue": "$total_revenue",
            "prime_cost": "$total_prime_cost",
            "profit": {"$subtract": ["$total_revenue", "$total_prime_cost"]},
            "_id": 0
        }}
    ]
    return await tasks_collection.aggregate(pipeline).to_list(length=None)


@router.get("/usage-report", response_model=UsageReport)
async def get_usage_report(
    tasks_collection: AsyncIOMotorCollection = Depends(get_task_collection),
    start_date: Optional[date] = Query(None, description="Начальная дата в формате YYYY-MM-DD. По умолчанию: 30 дней назад."),
    end_date: Optional[date] = Query(None, description="Конечная дата в формате YYYY-MM-DD. По умолчанию: сегодня."),
    key_id: Optional[int] = Query(None, description="ID API-ключа для фильтрации отчета.")
):

    if end_date is None:
        end_date = datetime.now(timezone.utc).date()
    if start_date is None:
        start_date = end_date - timedelta(days=30)

    start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
    end_dt = datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc)


    match_query = {
        "status": "completed",
        "created_at": {"$gte": start_dt, "$lte": end_dt}
    }

    if key_id is not None:
        match_query["api_key_id"] = key_id


    pipeline = [
        {"$match": match_query},
        {
            "$facet": {
                "model_usage": [
                    {"$group": {"_id": "$model", "count": {"$sum": 1}}},
                    {"$project": {"model": "$_id", "count": "$count", "_id": 0}},
                    {"$sort": {"count": -1}}
                ],
                "profit_calculation": [
                    {
                        "$group": {
                            "_id": None,
                            "total_revenue": {"$sum": "$cost"},
                            "total_prime_cost": {"$sum": "$prime_cost"}
                        }
                    }
                ]
            }
        }
    ]


    aggregation_result = await tasks_collection.aggregate(pipeline).to_list(length=1)

    if not aggregation_result:
        return UsageReport(
            period_start=start_date,
            period_end=end_date,
            total_profit=0.0,
            model_usage=[]
        )

    data = aggregation_result[0]
    model_usage_stats = data.get("model_usage", [])
    profit_data = data.get("profit_calculation", [])

    total_profit = 0.0
    if profit_data:
        revenue = profit_data[0].get("total_revenue", 0) or 0
        prime_cost = profit_data[0].get("total_prime_cost", 0) or 0
        total_profit = float(revenue) - float(prime_cost)

    return UsageReport(
        period_start=start_date,
        period_end=end_date,
        total_profit=round(total_profit, 6),
        model_usage=model_usage_stats
    )
