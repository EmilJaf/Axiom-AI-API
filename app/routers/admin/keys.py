import re
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorCollection
from pydantic import BaseModel
from starlette import status
from starlette.responses import Response

from app import dependencies
from app.database.repositories.log_repository import AdminLogRepository
from app.database.main_models import AdminLog
from app.database.mongo_db import get_task_collection
from app.database.repositories.user_repository import ApiKeyRepository, UserRepository

router = APIRouter(
    prefix="/keys",
    tags=["Admin - API Keys"]
)


class ApiKeyInfo(BaseModel):
    key_id: int
    key_value_partial: str
    owner_id: int
    balance: float


class ApiKeyBase(BaseModel):
    balance: float = 0.0

class AdminKeyCreateRequest(BaseModel):
    telegram_id: int
    balance: float


class KeyBalanceUpdate(BaseModel):
    balance: float


class ApiKey(ApiKeyBase):
    id: int
    key_value: str
    owner_id: int
    class Config:
        from_attributes = True


class ModelUsageStatKeys(BaseModel):
    model: str
    count: int


class KeyTopUpRequest(BaseModel):
    amount: float


class Transaction(BaseModel):
    timestamp: datetime
    type: Literal['credit', 'debit', 'refund']
    amount: float
    description: str


class KeyHistoryResponse(BaseModel):
    key_id: int
    key_value: str
    owner_id: int
    transactions: List[Transaction]


class KeyAnalyticsResponse(BaseModel):
    key_id: int
    key_value_partial: str
    owner_id: int
    balance: float
    total_spending: float
    total_tasks_completed: int
    total_tasks_failed: int
    model_usage: List[ModelUsageStatKeys]
    daily_activity: List[Dict[str, Any]]



@router.get("", response_model=List[ApiKeyInfo])
async def get_all_keys_list(
        key_repo: ApiKeyRepository = Depends(dependencies.get_key_repository)
):


    all_keys = await key_repo.get_all_keys_with_owner()

    return [
        ApiKeyInfo(
            key_id=key.id,
            key_value_partial=f"{key.key_value[:4]}...{key.key_value[-4:]}",
            owner_id=key.owner_id,
            balance=float(key.balance)
        ) for key in all_keys
    ]


@router.post("", response_model=ApiKey, status_code=201)
async def create_api_key_for_user(
        request_data: AdminKeyCreateRequest,
        user_repo: UserRepository = Depends(dependencies.get_user_repository),
        key_repo: ApiKeyRepository = Depends(dependencies.get_key_repository),
        log_repo: AdminLogRepository = Depends(dependencies.get_log_repository)
):

    user = await user_repo.get_or_create(telegram_id=request_data.telegram_id)
    api_key = await key_repo.create_for_user(user=user, balance=request_data.balance)

    log_entry = AdminLog(
        admin_key_id=1,
        action=f"Created Key {api_key.id} for user {user.telegram_id}"
    )
    await log_repo.create(log_entry)
    return api_key



@router.patch("/{key_id}/balance", response_model=ApiKey)
async def update_key_balance(
    key_id: int,
    data: KeyBalanceUpdate,
    key_repo: ApiKeyRepository = Depends(dependencies.get_key_repository)
):
    updated_key = await key_repo.update_balance_by_id(key_id=key_id, new_balance=data.balance)
    if not updated_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Key not found")
    return updated_key


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_key(
    key_id: int,
    key_repo: ApiKeyRepository = Depends(dependencies.get_key_repository),
    log_repo: AdminLogRepository = Depends(dependencies.get_log_repository)
):
    deleted = await key_repo.delete_key_by_id(key_id=key_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Key not found")

    log_entry = AdminLog(
        admin_key_id=1,
        action=f"Deleted key {key_id}",
    )

    await log_repo.create(log_entry)

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/{key_value}/topup", response_model=ApiKey)
async def top_up_key_balance(
        key_value: str,
        top_up_data: KeyTopUpRequest,
        key_repo: ApiKeyRepository = Depends(dependencies.get_key_repository),
        log_repo: AdminLogRepository = Depends(dependencies.get_log_repository)
):
    updated_key = await key_repo.add_to_balance(
        key_value=key_value,
        amount=top_up_data.amount
    )
    if not updated_key:
        raise HTTPException(status_code=404, detail="API Key to top up not found")

    log_entry = AdminLog(
        admin_key_id=1,
        action=f"Updated balance for {key_value} by {top_up_data.amount}"
    )

    await log_repo.create(log_entry)

    return updated_key


@router.get("/{key_id}/analytics", response_model=KeyAnalyticsResponse)
async def get_key_analytics(
        key_id: int,
        key_repo: ApiKeyRepository = Depends(dependencies.get_key_repository),
        tasks_collection: AsyncIOMotorCollection = Depends(get_task_collection),
):

    api_key = await key_repo.get_by_id(key_id)
    if not api_key:
        raise HTTPException(status_code=404, detail="API Key not found")


    match_query = {"api_key_id": key_id}


    completed_tasks = await tasks_collection.count_documents({**match_query, "status": "completed"})
    failed_tasks = await tasks_collection.count_documents({**match_query, "status": "failed"})


    spending_pipeline = [
        {"$match": {**match_query, "status": "completed"}},
        {"$group": {"_id": None, "total": {"$sum": "$cost"}}}
    ]
    spending_result = await tasks_collection.aggregate(spending_pipeline).to_list(length=1)
    total_spending = spending_result[0]['total'] if spending_result else 0.0


    model_usage_pipeline = [
        {"$match": {**match_query, "status": "completed"}},
        {"$group": {"_id": "$model", "count": {"$sum": 1}}},
        {"$project": {"model": "$_id", "count": "$count", "_id": 0}}
    ]
    model_usage = await tasks_collection.aggregate(model_usage_pipeline).to_list(length=None)


    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    daily_activity_pipeline = [
        {"$match": {**match_query, "created_at": {"$gte": thirty_days_ago}}},
        {"$group": {"_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}}, "count": {"$sum": 1}}},
        {"$project": {"date": "$_id", "count": "$count", "_id": 0}},
        {"$sort": {"date": 1}}
    ]
    daily_activity = await tasks_collection.aggregate(daily_activity_pipeline).to_list(length=None)

    return KeyAnalyticsResponse(
        key_id=api_key.id,
        key_value_partial=f"{api_key.key_value[:4]}...{api_key.key_value[-4:]}",
        owner_id=api_key.owner_id,
        balance=float(api_key.balance),
        total_spending=float(total_spending),
        total_tasks_completed=completed_tasks,
        total_tasks_failed=failed_tasks,
        model_usage=model_usage,
        daily_activity=daily_activity
    )



@router.get("/{key_id}/history", response_model=KeyHistoryResponse)
async def get_key_transaction_history(
        key_id: int,
        key_repo: ApiKeyRepository = Depends(dependencies.get_key_repository),
        tasks_collection: AsyncIOMotorCollection = Depends(get_task_collection),
        log_repo: AdminLogRepository = Depends(dependencies.get_log_repository)
):

    key = await key_repo.get_by_id(key_id)
    if not key:
        raise HTTPException(status_code=404, detail="Key not found")

    transactions = []


    debit_tasks_cursor = tasks_collection.find(
        {"api_key_id": key_id, "status": "completed"}
    )
    async for task in debit_tasks_cursor:
        task_timestamp = task.get('created_at', datetime.now(timezone.utc))

        transactions.append(Transaction(
            timestamp=task_timestamp,
            type='debit',
            amount=-abs(task.get('cost', 0)),
            description=f"Списание за задачу {str(task['_id'])} ({task.get('model')})"
        ))

    logs = await log_repo.get_all_by_action_text(f"Maked refund for task")
    for log in logs:

        amount_match = re.search(r"Amount: ([\d\.]+)", log.action)


        if amount_match:
            cleaned_amount_str = amount_match.group(1).rstrip('.')
            amount = float(cleaned_amount_str)

            aware_timestamp = log.timestamp.replace(tzinfo=timezone.utc)
            transactions.append(Transaction(
                timestamp=aware_timestamp,
                type='refund',
                amount=amount,
                description=log.action
            ))


    transactions.sort(key=lambda x: x.timestamp.replace(tzinfo=timezone.utc), reverse=True)

    return KeyHistoryResponse(
        key_id=key.id,
        key_value=f"{key.key_value[:4]}...{key.key_value[-4:]}",
        owner_id=key.owner_id,
        transactions=transactions
    )