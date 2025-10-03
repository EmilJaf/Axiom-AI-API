from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app import dependencies
from app.database.repositories.log_repository import AdminLogRepository


router = APIRouter(
    prefix="/logs",
    tags=["Admin - API Logs"]
)



class AdminLogResponse(BaseModel):
    id: int
    timestamp: datetime
    admin_key_id: int
    action: str
    class Config: from_attributes = True



@router.get("", response_model=List[AdminLogResponse])
async def get_admin_logs(
    skip: int = 0, limit: int = 100,
    log_repo: AdminLogRepository = Depends(dependencies.get_log_repository)
):
    return await log_repo.get_all_paginated(skip=skip, limit=limit)
