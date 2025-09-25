from datetime import datetime, timezone, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from starlette import status
from starlette.responses import Response

from app import dependencies
from app.database.log_repository import AdminLogRepository
from app.database.main_models import AdminLog

router = APIRouter(
    prefix="/workers",
    tags=["Admin - API Workers"]
)


class WorkerStatus(BaseModel):
    worker_id: str
    last_heartbeat: datetime
    status: str
    current_task_id: Optional[str] = None
    is_alive: bool
    class Config:
        from_attributes = True



@router.get("/status", response_model=List[WorkerStatus])
async def get_workers_status(
        tasks_db=Depends(dependencies.get_tasks_database)
):
    status_collection = tasks_db.get_collection("worker_status")
    workers_cursor = status_collection.find()

    result = []
    now_utc = datetime.now(timezone.utc)

    async for worker_doc in workers_cursor:
        last_heartbeat_aware = worker_doc['last_heartbeat'].replace(tzinfo=timezone.utc)
        is_alive = (now_utc - last_heartbeat_aware) < timedelta(seconds=30)


        worker_data = {
            "worker_id": str(worker_doc["_id"]),
            "last_heartbeat": worker_doc["last_heartbeat"],
            "status": worker_doc["status"],
            "current_task_id": worker_doc.get("current_task_id"),
            "is_alive": is_alive
        }

        result.append(worker_data)

    return result


@router.delete("/{worker_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_worker_status(
        worker_id: str,
        tasks_db=Depends(dependencies.get_tasks_database),
        log_repo: AdminLogRepository = Depends(dependencies.get_log_repository)
):

    status_collection = tasks_db.get_collection("worker_status")


    delete_result = await status_collection.delete_one({"_id": worker_id})


    if delete_result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Worker not found")


    log_entry = AdminLog(
        admin_key_id=1,
        action=f"Deleted stale worker record: {worker_id}"
    )
    await log_repo.create(log_entry)

    return Response(status_code=status.HTTP_204_NO_CONTENT)