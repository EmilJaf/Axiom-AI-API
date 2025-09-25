import uuid
from typing import Optional

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload
from sqlalchemy.future import select

from app.database.main_models import User, ApiKey


class BaseRepository:
    def __init__(self, session_factory: async_sessionmaker):
        self.session_factory = session_factory


class UserRepository(BaseRepository):
    async def get_or_create(self, telegram_id: int) -> User:
        async with self.session_factory() as session:
            result = await session.execute(
                select(User).filter_by(telegram_id=telegram_id)
            )
            user = result.scalars().first()

            if not user:
                user = User(telegram_id=telegram_id)
                session.add(user)
                await session.commit()
                await session.refresh(user)
            return user

    async def get_with_keys(self, telegram_id: int) -> User | None:
        async with self.session_factory() as session:
            result = await session.execute(
                select(User)
                .options(selectinload(User.keys))
                .filter_by(telegram_id=telegram_id)
            )
            return result.scalars().first()

    async def get_all_users(self, session: AsyncSession) -> list[User]:

        result = await session.execute(select(User).order_by(User.telegram_id))
        return result.scalars().all()


class ApiKeyRepository(BaseRepository):
    async def get_by_key_with_owner(self, key_value: str) -> ApiKey | None:
        async with self.session_factory() as session:
            result = await session.execute(
                select(ApiKey)
                .options(selectinload(ApiKey.owner))
                .filter_by(key_value=key_value)
            )
            return result.scalars().first()


    async def create_for_user(self, user: User, balance: float) -> ApiKey:

        async with self.session_factory() as session:
            new_key_value = str(uuid.uuid4())
            db_key = ApiKey(
                key_value=new_key_value,
                balance=balance,
                owner_id=user.telegram_id
            )
            session.add(db_key)
            await session.commit()
            await session.refresh(db_key)
            return db_key


    async def update_balance(self, key_id: int, new_balance: float):
        async with self.session_factory() as session:
            stmt = update(ApiKey).where(ApiKey.id == key_id).values(balance=new_balance)
            await session.execute(stmt)
            await session.commit()

    async def get_all_keys_with_owner(self) -> list[ApiKey]:
        async with self.session_factory() as session:
            result = await session.execute(
                select(ApiKey).options(selectinload(ApiKey.owner))
            )
            return result.scalars().all()


    async def refund_balance(self, key_id: int, amount: float):

        async with self.session_factory() as session:
            stmt = (
                update(ApiKey)
                .where(ApiKey.id == key_id)
                .values(balance=ApiKey.balance + amount)
            )
            await session.execute(stmt)
            await session.commit()


    async def deduct_from_balance(self, key_id: int, amount: float) -> bool:
        async with self.session_factory() as session:
            stmt = (
                update(ApiKey)
                .where(
                    ApiKey.id == key_id,
                    ApiKey.balance >= amount
                )
                .values(balance=ApiKey.balance - amount)
            )
            result = await session.execute(stmt)
            await session.commit()

            return result.rowcount > 0

    async def update_balance_by_id(self, key_id: int, new_balance: float) -> Optional[ApiKey]:
        async with self.session_factory() as session:
            stmt = (
                update(ApiKey)
                .where(ApiKey.id == key_id)
                .values(balance=new_balance)
            )
            result = await session.execute(stmt)


            if result.rowcount == 0:
                await session.rollback()
                return None

            updated_key = await session.get(ApiKey, key_id)
            await session.commit()

            return updated_key

    async def delete_key_by_id(self, key_id: int) -> bool:
        async with self.session_factory() as session:
            key_to_delete = await session.get(ApiKey, key_id)
            if not key_to_delete:
                return False

            await session.delete(key_to_delete)
            await session.commit()
            return True

    async def add_to_balance(self, key_value: str, amount: float) -> ApiKey | None:
        async with self.session_factory() as session:
            stmt = (
                update(ApiKey)
                .where(ApiKey.key_value == key_value)
                .values(balance=ApiKey.balance + amount)
            )
            result = await session.execute(stmt)
            if result.rowcount == 0:
                return None

            get_stmt = select(ApiKey).filter_by(key_value=key_value)
            updated_key_result = await session.execute(get_stmt)
            updated_key = updated_key_result.scalars().one()
            await session.commit()
            return updated_key

    async def get_by_id(self, key_id: int) -> ApiKey | None:
        async with self.session_factory() as session:
            return await session.get(ApiKey, key_id)