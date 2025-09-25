import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from starlette import status


from app import schemas
from app.database.main_models import User, ApiKey, Price
from app.database.repositories.user_repository import ApiKeyRepository
from app.database.price_repository import PriceRepository
from app.database.repositories.user_price_repository import UserPriceRepository
from app.main_api_utils import get_final_cost
from motor.motor_asyncio import AsyncIOMotorCollection

from app.schemas import AnyModelParams
from app.settings import settings

MODELS_WITH_DURATION_COST = settings.MODELS_WITH_DURATION_COST


class GenerationService:


    def __init__(
            self,
            user: User,
            api_key: ApiKey,
            key_repo: ApiKeyRepository,
            price_repo: PriceRepository,
            user_price_repo: UserPriceRepository,
            tasks_collection: AsyncIOMotorCollection,
    ):

        self.user = user
        self.api_key = api_key
        self.key_repo = key_repo
        self.price_repo = price_repo
        self.user_price_repo = user_price_repo
        self.tasks_collection = tasks_collection

    async def create_generation_task(self, model_params: AnyModelParams) -> str:

        model_name = model_params.model_name

        price_obj = await self._validate_and_get_price(model_name)

        final_cost, prime_cost = await self._calculate_costs(model_params, price_obj)

        await self._deduct_funds(final_cost)

        task_id = str(uuid.uuid4())

        task_document = self._prepare_task_document(
            task_id, model_params, final_cost, prime_cost
        )

        await self.tasks_collection.insert_one(task_document)

        return task_id

    async def _validate_and_get_price(self, model_name: str) -> Price:

        price_obj = await self.price_repo.get_by_model_name(model_name)

        if not price_obj:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Price for model '{model_name}' is not set in the admin panel",
            )


        if not price_obj.is_active:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Model '{model_name}' is temporarily disabled by the administrator",
            )

        return price_obj

    async def _calculate_costs(self, model_params: schemas.AnyModelParams, price_obj: Price) -> tuple[float, float]:

        model_name = model_params.model_name


        multiplier = 1

        if model_name in MODELS_WITH_DURATION_COST:
            multiplier = model_params.duration if hasattr(model_params, 'duration') and model_params.duration > 0 else 1

        elif hasattr(model_params, 'num_images') and model_params.num_images > 0:
            multiplier = model_params.num_images


        final_cost, prime_cost = await get_final_cost(
            user=self.user,
            model_name=model_name,
            num_images=multiplier if model_name not in MODELS_WITH_DURATION_COST else 1,
            duration=multiplier if model_name in MODELS_WITH_DURATION_COST else 1,
            price_repo=self.price_repo,
            user_price_repo=self.user_price_repo,
        )

        return final_cost, prime_cost

    async def _deduct_funds(self, amount: float):

        was_deducted = await self.key_repo.deduct_from_balance(
            key_id=self.api_key.id, amount=amount
        )

        if not was_deducted:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=f"Insufficient funds. Required: {amount}. Please top up your balance.",
            )

    def _prepare_task_document(
            self,
            task_id: str,
            model_params: schemas.AnyModelParams,
            final_cost: float,
            prime_cost: float,
    ) -> dict:

        return {
            "_id": task_id,
            "status": "pending",
            "user_telegram_id": self.user.telegram_id,
            "created_at": datetime.now(timezone.utc),
            "api_key_id": self.api_key.id,
            "model": model_params.model_name,
            "params": model_params.dict(),
            "cost": final_cost,
            "prime_cost": prime_cost,
            "result": None,
            "error": None,
        }