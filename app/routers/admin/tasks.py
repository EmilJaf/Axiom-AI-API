from typing import List, Optional, Any, Dict

from bson import ObjectId, errors
from fastapi import APIRouter, Query, Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorCollection

from app import dependencies
from app.database.log_repository import AdminLogRepository
from app.database.main_models import AdminLog
from app.database.mongo_db import get_task_collection
from app.database.repositories.user_repository import ApiKeyRepository
from app.schemas import TaskStatusResponse

router = APIRouter(
    prefix="/tasks",
    tags=["Admin - API Tasks"]
)



class TaskDetailResponse(TaskStatusResponse):
    user_telegram_id: Optional[int] = None
    api_key_id: Optional[int] = None
    model: Optional[str] = None
    params: Optional[Dict[str, Any]] = None
    cost: Optional[float] = None



@router.get("", response_model=List[TaskStatusResponse])
async def get_all_tasks(
        status: Optional[str] = Query(None, enum=["pending", "processing", "completed", "failed"]),
        search: Optional[str] = Query(None, description="Поиск по ID задачи"),
        model: Optional[str] = Query(None, description="Фильтр по названию модели"),
        skip: int = 0,
        limit: int = 50,
        tasks_collection: AsyncIOMotorCollection = Depends(get_task_collection),
):
    query = {}
    if status:
        query["status"] = status


    if model:
        query["model"] = model


    if search:
        try:
            obj_id = ObjectId(search)
            query["$or"] = [
                {"_id": obj_id},
                {"_id": search}
            ]
        except errors.InvalidId:
            query["_id"] = search


    cursor = tasks_collection.find(query).sort("created_at", -1).skip(skip).limit(limit)

    result = []
    async for doc in cursor:
        task_data = {
            "task_id": str(doc.get("_id")),
            "status": doc.get("status"),
            "result": doc.get("result"),
            "error": doc.get("error"),
            "created_at": doc.get("created_at")
        }
        result.append(TaskStatusResponse.model_validate(task_data))

    return result



@router.get("/{task_id}", response_model=TaskDetailResponse)
async def get_task_by_id(
        task_id: str,
        tasks_collection: AsyncIOMotorCollection = Depends(get_task_collection),
):


    task = await tasks_collection.find_one({"_id": task_id})

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")



    task_data = {
        "task_id": str(task.get("_id")),
        "status": task.get("status"),
        "result": task.get("result"),
        "error": task.get("error"),
        "user_telegram_id": task.get("user_telegram_id"),
        "api_key_id": task.get("api_key_id"),
        "model": task.get("model"),
        "params": task.get("params"),
        "cost": task.get("cost"),
    }


    return task_data


@router.post("/{task_id}/retry")
async def retry_failed_task(
        task_id: str,
        tasks_collection: AsyncIOMotorCollection = Depends(get_task_collection),
        log_repo: AdminLogRepository = Depends(dependencies.get_log_repository)
):

    result = await tasks_collection.find_one_and_update(
        {"_id": task_id, "status": "failed"},
        {"$set": {"status": "pending", "error": None}}
    )
    if not result:
        raise HTTPException(status_code=404, detail="Failed task not found or status is not 'failed'")

    log_entry = AdminLog(
        admin_key_id=1,
        action=f"Retried task {task_id}",
    )

    await log_repo.create(log_entry)

    return {"message": "Task sent for reprocessing"}


@router.post("/{task_id}/refund", description="Refund was processed")
async def refund_failed_task(
        task_id: str,
        tasks_collection: AsyncIOMotorCollection = Depends(get_task_collection),
        key_repo: ApiKeyRepository = Depends(dependencies.get_key_repository),
        log_repo: AdminLogRepository = Depends(dependencies.get_log_repository)
):

    task = await tasks_collection.find_one({"_id": task_id})
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    key_id = task.get("api_key_id")
    cost = task.get("cost")

    if not (key_id and cost and cost > 0):
        raise HTTPException(status_code=400, detail="Task has no cost or key to refund")

    await key_repo.refund_balance(key_id=key_id, amount=cost)
    await tasks_collection.update_one(
        {"_id": task_id},
        {"$set": {"error": f"Manual refund processed. Original error: {task.get('error')}"}}
    )

    log_entry = AdminLog(
        admin_key_id=1,
        action=f"Maked refund for task {task_id}. Amount: {cost}. Key ID: {key_id}"
    )

    await log_repo.create(log_entry)

    return {"message": f"Refund of {cost} for key_id {key_id} completed."}