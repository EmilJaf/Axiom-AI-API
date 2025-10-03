from sqlalchemy.future import select
from sqlalchemy.dialects.mysql import insert as mysql_insert

from app.database.main_models import Price


class PriceRepository:
    def __init__(self, session_factory):
        self.session_factory = session_factory

    async def get_all(self) -> list[Price]:
        async with self.session_factory() as session:
            result = await session.execute(select(Price))
            return result.scalars().all()

    async def get_by_model_name(self, model_name: str) -> Price | None:
        async with self.session_factory() as session:
            return await session.get(Price, model_name)

    async def upsert(self, price: Price):
        async with self.session_factory() as session:
            stmt = mysql_insert(Price).values(
                model_name=price.model_name, cost=price.cost, prime_cost=price.prime_cost
            )
            on_duplicate_key_stmt = stmt.on_duplicate_key_update(
                cost=stmt.inserted.cost,
                prime_cost=stmt.inserted.prime_cost
            )
            await session.execute(on_duplicate_key_stmt)
            await session.commit()

    async def update_status(self, model_name: str, new_status: bool) -> Price | None:
        async with self.session_factory() as session:
            price = await session.get(Price, model_name)
            if price:
                price.is_active = new_status
                await session.commit()
                await session.refresh(price)
            return price