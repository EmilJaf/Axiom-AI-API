from sqlalchemy.future import select

from app.database.main_models import AdminLog


class AdminLogRepository:
    def __init__(self, session_factory):
        self.session_factory = session_factory

    async def create(self, log: AdminLog):
        async with self.session_factory() as session:
            session.add(log)
            await session.commit()

    async def get_all_paginated(self, skip: int = 0, limit: int = 100) -> list[AdminLog]:
        async with self.session_factory() as session:
            result = await session.execute(
                select(AdminLog).order_by(AdminLog.id.desc()).offset(skip).limit(limit)
            )
            return result.scalars().all()

    async def get_all_by_action_text(self, text: str) -> list[AdminLog]:
        async with self.session_factory() as session:
            result = await session.execute(
                select(AdminLog)
                .where(AdminLog.action.like(f"%{text}%"))
                .order_by(AdminLog.id.desc())
            )
            return result.scalars().all()