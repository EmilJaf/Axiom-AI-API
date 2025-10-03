from fastapi import HTTPException
from starlette import status

from app.constants import MODELS_WITH_DURATION_COST
from app.database.main_models import User
from app.database.repositories.price_repository import PriceRepository
from app.database.repositories.user_price_repository import UserPriceRepository


async def get_final_cost(
        user: User,
        model_name: str,
        model_params: dict,
        price_repo: PriceRepository,
        user_price_repo: UserPriceRepository
) -> tuple[float, float]:


    if model_name in MODELS_WITH_DURATION_COST:
        multiplier = model_params.get('duration', 1) or 1
    else:
        multiplier = model_params.get('num_images', 1) or 1


    user_specific_price = await user_price_repo.get_price(user.telegram_id, model_name)

    if user_specific_price:
        base_cost = float(user_specific_price.custom_cost)
        base_price_obj = await price_repo.get_by_model_name(model_name)

        base_prime_cost = float(base_price_obj.prime_cost) if base_price_obj else 0.0

        final_cost = round(base_cost * multiplier, 6)
        prime_cost = round(base_prime_cost * multiplier, 6)

    else:
        price_obj = await price_repo.get_by_model_name(model_name)
        if not price_obj:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Price for model '{model_name}' is not set."
            )
        base_cost = float(price_obj.cost)
        base_prime_cost = float(price_obj.prime_cost)

        final_cost = round(base_cost * multiplier * user.coefficient, 6)
        prime_cost = round(base_prime_cost * multiplier, 6)



    return final_cost, prime_cost