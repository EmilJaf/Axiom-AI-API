from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from typing import Tuple

from app.database.repositories.log_repository import AdminLogRepository
from app.database.repositories.price_repository import PriceRepository
from app.database.engine import async_session_factory


from app.database.mongo_db import database as mongo_database_instance
from app.database.repositories.user_price_repository import UserPriceRepository
from app.database.repositories.user_repository import UserRepository, ApiKeyRepository
from app.database.main_models import User, ApiKey
from app.settings import settings


ADMIN_API_KEY = settings.ADMIN_API_KEY

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


def get_user_repository() -> UserRepository:
    return UserRepository(async_session_factory)


def get_key_repository() -> ApiKeyRepository:
    return ApiKeyRepository(async_session_factory)


async def get_current_user_and_key(
        token: str = Depends(oauth2_scheme),
        key_repository: ApiKeyRepository = Depends(get_key_repository)
) -> Tuple[User, ApiKey]:
    api_key_obj = await key_repository.get_by_key_with_owner(key_value=token)

    if api_key_obj is None or api_key_obj.owner is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return api_key_obj.owner, api_key_obj


async def get_current_admin_user_and_key(auth_data: Tuple[User, ApiKey] = Depends(get_current_user_and_key)) -> Tuple[User, ApiKey]:

    _user, api_key = auth_data

    if api_key.key_value != ADMIN_API_KEY:

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator rights required"
        )


    return auth_data


def get_price_repository() -> PriceRepository:
    return PriceRepository(async_session_factory)

def get_log_repository() -> AdminLogRepository:
    return AdminLogRepository(async_session_factory)


def get_tasks_database():
    return mongo_database_instance


def get_user_price_repository() -> UserPriceRepository:
    return UserPriceRepository(async_session_factory)
