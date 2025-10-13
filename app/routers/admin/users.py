from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorCollection
from pydantic import BaseModel, Field
from sqlalchemy import select
from starlette import status
from starlette.responses import Response

from app import schemas, dependencies
from app.database.repositories.analytics_repository import AnalyticsRepository
from app.database.repositories.log_repository import AdminLogRepository
from app.database.main_models import User, AdminLog
from app.database.mongo_db import get_task_collection
from app.database.repositories.user_price_repository import UserPriceRepository
from app.database.repositories.user_repository import UserRepository
from app.dependencies import get_user_price_repository
from app.routers.admin.keys import ApiKey

router = APIRouter(
    prefix="/users",
    tags=["Admin - Users"]
)


class UserCoefficientUpdate(BaseModel):
    coefficient: float = 1.0


class UserApiKeyInfo(BaseModel):
    key_id: int
    key_value_partial: str
    balance: float
    class Config: from_attributes = True

class UserCustomPriceInfo(BaseModel):
    model_name: str
    custom_cost: float
    class Config: from_attributes = True



class UserProfileResponse(schemas.UserAnalyticsResponse):
    coefficient: float
    api_keys: List[UserApiKeyInfo]
    custom_prices: List[UserCustomPriceInfo]


class UserBase(BaseModel):
    telegram_id: int
    coefficient: float
    class Config:
        from_attributes = True

class UserCreate(UserBase):
    pass

class UserWithKeys(UserBase):
    keys: List[ApiKey]
    class Config:
        from_attributes = True


class UserPriceResponse(BaseModel):
    user_telegram_id: int
    model_name: str
    custom_cost: Decimal

    class Config:
        from_attributes = True


class UserPriceSet(BaseModel):
    model_name: str = Field(..., description="Название модели, например, 'gpt-4o-image'")
    custom_cost: Decimal = Field(
        ...,
        gt=0,
        description="Новая персональная цена для модели. Должна быть больше нуля."
    )



@router.get("", response_model=List[UserBase])
async def get_all_users(
        skip: int = 0,
        limit: int = 100,
        user_repo: UserRepository = Depends(dependencies.get_user_repository)
):

    async with user_repo.session_factory() as session:
        result = await session.execute(select(User).offset(skip).limit(limit))
        return result.scalars().all()



@router.patch("/{telegram_id}/coefficient", response_model=UserBase)
async def update_user_coefficient(
        telegram_id: int,
        data: UserCoefficientUpdate,
        user_repo: UserRepository = Depends(dependencies.get_user_repository),
        log_repo: AdminLogRepository = Depends(dependencies.get_log_repository)
):

    async with user_repo.session_factory() as session:
        user = await session.get(User, telegram_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        user.coefficient = data.coefficient
        await session.commit()
        await session.refresh(user)

        log_entry = AdminLog(
            admin_key_id=1,
            action=f"Changed coefficient for {telegram_id}. New coefficient: {data.coefficient}",
        )

        await log_repo.create(log_entry)

        return user



@router.get("/{telegram_id}/keys", response_model=UserWithKeys)
async def get_any_user_keys(
        telegram_id: int,
        user_repo: UserRepository = Depends(dependencies.get_user_repository),
):
    user_with_keys = await user_repo.get_with_keys(telegram_id=telegram_id)
    if not user_with_keys:
        raise HTTPException(status_code=404, detail="User not found")
    return user_with_keys


@router.get("/{telegram_id}/profile", response_model=UserProfileResponse)
async def get_user_profile(
        telegram_id: int,
        user_repo: UserRepository = Depends(dependencies.get_user_repository),
        user_price_repo: UserPriceRepository = Depends(dependencies.get_user_price_repository),
        tasks_collection: AsyncIOMotorCollection = Depends(get_task_collection),  # Оставляем для failed_tasks

        analytics_repo: AnalyticsRepository = Depends(dependencies.get_analytics_repository)
):

    user_with_keys = await user_repo.get_with_keys(telegram_id=telegram_id)
    if not user_with_keys:
        raise HTTPException(status_code=404, detail="User not found")
    custom_prices = await user_price_repo.get_all_for_user(telegram_id)


    user_summary = await analytics_repo.get_user_summary(telegram_id)


    failed_tasks = await tasks_collection.count_documents({
        "user_telegram_id": telegram_id,
        "status": "failed"
    })


    return UserProfileResponse(
        telegram_id=telegram_id,
        coefficient=user_with_keys.coefficient,
        api_keys=[
            UserApiKeyInfo(
                key_id=key.id,
                key_value_partial=f"{key.key_value[:4]}...{key.key_value[-4:]}",
                balance=float(key.balance)
            ) for key in user_with_keys.keys
        ],
        custom_prices=[
            UserCustomPriceInfo(
                model_name=price.model_name,
                custom_cost=float(price.custom_cost)
            ) for price in custom_prices
        ],

        total_spending=user_summary["total_spending"],
        total_tasks=user_summary["total_tasks"],
        model_usage=[schemas.UserStatItem(model=row.model_name, count=row.count) for row in
                     user_summary["model_usage"]],


        failed_tasks=failed_tasks,
        daily_activity=[]
    )

@router.get("/{telegram_id}/prices", response_model=List[UserPriceResponse])
async def get_user_custom_prices(
        telegram_id: int,
        repo: UserPriceRepository = Depends(get_user_price_repository)
):

    prices = await repo.get_all_for_user(telegram_id)
    return prices


@router.post("/{telegram_id}/prices", response_model=UserPriceResponse)
async def set_user_custom_price(
        telegram_id: int,
        price_data: UserPriceSet,
        repo: UserPriceRepository = Depends(get_user_price_repository)
):

    updated_price = await repo.set_or_update_price(
        user_telegram_id=telegram_id,
        model_name=price_data.model_name,
        custom_cost=price_data.custom_cost
    )
    return updated_price


@router.delete("/{telegram_id}/prices/{model_name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_custom_price(
        telegram_id: int,
        model_name: str,
        repo: UserPriceRepository = Depends(get_user_price_repository)
):

    deleted = await repo.delete_price(
        user_telegram_id=telegram_id,
        model_name=model_name
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Кастомная цена для данного пользователя и модели не найдена."
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)