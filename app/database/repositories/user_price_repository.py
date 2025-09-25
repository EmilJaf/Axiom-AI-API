from decimal import Decimal
from typing import List, Optional

from sqlalchemy import select, delete
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.database.main_models import UserPrice


class UserPriceRepository:

    def __init__(self, session_factory: async_sessionmaker):
        self.session_factory = session_factory

    async def get_price(self, user_telegram_id: int, model_name: str) -> Optional[UserPrice]:

        async with self.session_factory() as session:
            stmt = select(UserPrice).where(
                UserPrice.user_telegram_id == user_telegram_id,
                UserPrice.model_name == model_name
            )
            result = await session.execute(stmt)
            return result.scalars().first()

    async def set_or_update_price(
            self,
            user_telegram_id: int,
            model_name: str,
            custom_cost: Decimal
    ) -> UserPrice:

        async with self.session_factory() as session:

            stmt = mysql_insert(UserPrice).values(
                user_telegram_id=user_telegram_id,
                model_name=model_name,
                custom_cost=custom_cost
            )


            on_duplicate_key_stmt = stmt.on_duplicate_key_update(
                custom_cost=stmt.inserted.custom_cost
            )

            await session.execute(on_duplicate_key_stmt)
            await session.commit()


            return await self.get_price(user_telegram_id, model_name)

    async def delete_price(self, user_telegram_id: int, model_name: str) -> bool:

        async with self.session_factory() as session:
            stmt = delete(UserPrice).where(
                UserPrice.user_telegram_id == user_telegram_id,
                UserPrice.model_name == model_name
            )
            result = await session.execute(stmt)
            await session.commit()

            return result.rowcount > 0

    async def get_all_for_user(self, user_telegram_id: int) -> List[UserPrice]:

        async with self.session_factory() as session:
            stmt = select(UserPrice).where(UserPrice.user_telegram_id == user_telegram_id)
            result = await session.execute(stmt)
            return result.scalars().all()