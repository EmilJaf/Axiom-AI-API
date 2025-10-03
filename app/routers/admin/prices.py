from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app import dependencies
from app.database.repositories.log_repository import AdminLogRepository
from app.database.main_models import AdminLog, Price
from app.database.repositories.price_repository import PriceRepository

router = APIRouter(
    prefix="/prices",
    tags=["Admin - API Prices"]
)


class PriceUpdate(BaseModel):
    cost: float
    prime_cost: float


class StatusUpdate(BaseModel):
    is_active: bool


class PriceResponse(BaseModel):
    model_name: str
    cost: float
    prime_cost: float
    is_active: bool
    class Config:
        from_attributes = True


@router.get("", response_model=List[PriceResponse])
async def get_all_prices(
    price_repo: PriceRepository = Depends(dependencies.get_price_repository)
):
    return await price_repo.get_all()


@router.put("/{model_name}", response_model=PriceResponse)
async def update_price(
    model_name: str,
    data: PriceUpdate,
    price_repo: PriceRepository = Depends(dependencies.get_price_repository),
    log_repo: AdminLogRepository = Depends(dependencies.get_log_repository)
):
    price_obj = Price(
        model_name=model_name,
        cost=data.cost,
        prime_cost=data.prime_cost
    )
    await price_repo.upsert(price_obj)

    updated_price = await price_repo.get_by_model_name(model_name)

    log_entry = AdminLog(
        admin_key_id=1,
        action=f"Updated price for {model_name} to {data.cost}"
    )

    await log_repo.create(log_entry)

    return updated_price


@router.patch("/{model_name}/status", response_model=PriceResponse)
async def update_model_status(
    model_name: str,
    data: StatusUpdate,
    price_repo: PriceRepository = Depends(dependencies.get_price_repository),
    log_repo: AdminLogRepository = Depends(dependencies.get_log_repository)
):
    updated_price = await price_repo.update_status(model_name, data.is_active)
    if not updated_price:
        raise HTTPException(status_code=404, detail="Model not found")

    log_entry = AdminLog(
        admin_key_id=1,
        action=f"Updated status for {model_name}"
    )

    await log_repo.create(log_entry)

    return updated_price
