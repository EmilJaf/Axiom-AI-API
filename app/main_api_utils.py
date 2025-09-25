from fastapi import HTTPException
from starlette import status

from app.database.main_models import User
from app.database.price_repository import PriceRepository
from app.database.repositories.user_price_repository import UserPriceRepository


async def get_final_cost(
        user: User,
        model_name: str,
        num_images: int,
        duration: int,
        price_repo: PriceRepository,
        user_price_repo: UserPriceRepository
) -> tuple[float, float]:


    user_specific_price = await user_price_repo.get_price(user.telegram_id, model_name)

    if user_specific_price:
        base_cost = float(user_specific_price.custom_cost)

        final_cost = round(base_cost * (duration or num_images), 6)

        base_price_obj = await price_repo.get_by_model_name(model_name)
        prime_cost = round(float(base_price_obj.prime_cost) * (duration or num_images), 6) if base_price_obj else 0.0

    else:

        price_obj = await price_repo.get_by_model_name(model_name)
        if not price_obj:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Price for model '{model_name}' is not set."
            )
        base_cost = float(price_obj.cost)
        base_prime_cost = float(price_obj.prime_cost)

        final_cost = round(base_cost * (duration or num_images) * user.coefficient, 6)
        prime_cost = round(base_prime_cost * (duration or num_images), 6)

    return final_cost, prime_cost