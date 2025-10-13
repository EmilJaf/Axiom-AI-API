from datetime import date, datetime, timedelta, timezone
from typing import Optional, Dict, Any, List

from sqlalchemy import select, func, and_
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from app.database.analytics_models import DailySystemStats, UserKeyModelStats, CompletedTaskLog


class AnalyticsRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self.session_factory = session_factory

    async def log_and_update_stats_on_completion(
            self, task_id: str, user_telegram_id: int, api_key_id: int, model_name: str,
            cost: float, prime_cost: float, created_at: datetime
    ):
        """Главный метод: атомарно пишет в три таблицы после завершения задачи."""
        async with self.session_factory() as session:

            log_entry = CompletedTaskLog(
                task_mongo_id=task_id, user_telegram_id=user_telegram_id, api_key_id=api_key_id,
                model_name=model_name, cost=cost, prime_cost=prime_cost, created_at=created_at
            )
            session.add(log_entry)


            today = created_at.date()
            profit = cost - prime_cost
            stmt_daily = mysql_insert(DailySystemStats).values(
                date=today, tasks_completed=1, total_revenue=cost,
                total_prime_cost=prime_cost, profit=profit
            )
            stmt_daily_upsert = stmt_daily.on_duplicate_key_update(
                tasks_completed=DailySystemStats.tasks_completed + 1,
                total_revenue=DailySystemStats.total_revenue + stmt_daily.inserted.total_revenue,
                total_prime_cost=DailySystemStats.total_prime_cost + stmt_daily.inserted.total_prime_cost,
                profit=DailySystemStats.profit + stmt_daily.inserted.profit
            )
            await session.execute(stmt_daily_upsert)


            stmt_user_key = mysql_insert(UserKeyModelStats).values(
                user_telegram_id=user_telegram_id, api_key_id=api_key_id, model_name=model_name,
                total_tasks_completed=1, total_spending=cost
            )
            stmt_user_key_upsert = stmt_user_key.on_duplicate_key_update(
                total_tasks_completed=UserKeyModelStats.total_tasks_completed + 1,
                total_spending=UserKeyModelStats.total_spending + stmt_user_key.inserted.total_spending
            )
            await session.execute(stmt_user_key_upsert)

            await session.commit()


    async def get_detailed_activity(self, start_time: datetime, end_time: datetime, api_key_id: int = None):
        """Получает детальную активность за период, опционально фильтруя по ключу."""
        async with self.session_factory() as session:
            stmt = select(CompletedTaskLog).where(
                CompletedTaskLog.created_at.between(start_time, end_time)
            )
            if api_key_id:
                stmt = stmt.where(CompletedTaskLog.api_key_id == api_key_id)

            result = await session.execute(stmt)
            return result.scalars().all()

    async def get_completed_tasks_count_for_period(self, hours: int) -> int:
        async with self.session_factory() as session:
            time_ago = datetime.now(timezone.utc) - timedelta(hours=hours)
            stmt = select(func.count(CompletedTaskLog.id)).where(
                CompletedTaskLog.created_at >= time_ago
            )
            result = await session.scalar(stmt)
            return result or 0

    async def get_overall_model_usage(self):
        async with self.session_factory() as session:
            stmt = select(
                UserKeyModelStats.model_name,
                func.sum(UserKeyModelStats.total_tasks_completed).label('usage_count')
            ).group_by(UserKeyModelStats.model_name).order_by(func.sum(UserKeyModelStats.total_tasks_completed).desc())
            result = await session.execute(stmt)
            return result.all()

    async def get_profitability_for_period(self, start_date: date, end_date: date):
        async with self.session_factory() as session:
            stmt = select(DailySystemStats).where(
                DailySystemStats.date.between(start_date, end_date)
            ).order_by(DailySystemStats.date.asc())
            result = await session.execute(stmt)
            return result.scalars().all()

    async def create_usage_report(self, start_date: date, end_date: date, key_id: Optional[int]) -> Dict[str, Any]:
        async with self.session_factory() as session:

            start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
            end_dt = datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc)


            where_clause = [CompletedTaskLog.created_at.between(start_dt, end_dt)]
            if key_id is not None:
                where_clause.append(CompletedTaskLog.api_key_id == key_id)


            profit_stmt = select(
                func.sum(CompletedTaskLog.cost).label('total_revenue'),
                func.sum(CompletedTaskLog.prime_cost).label('total_prime_cost')
            ).where(*where_clause)

            profit_result = (await session.execute(profit_stmt)).first()
            total_profit = (profit_result.total_revenue or 0) - (profit_result.total_prime_cost or 0)


            model_usage_stmt = select(
                CompletedTaskLog.model_name,
                func.count().label('count')
            ).where(*where_clause).group_by(CompletedTaskLog.model_name).order_by(func.count().desc())

            model_usage_result = (await session.execute(model_usage_stmt)).all()

            return {
                "total_profit": total_profit,
                "model_usage": model_usage_result
            }

    async def get_user_summary(self, telegram_id: int) -> Dict[str, Any]:
        async with self.session_factory() as session:
            stmt = select(
                func.sum(UserKeyModelStats.total_spending).label("total_spending"),
                func.sum(UserKeyModelStats.total_tasks_completed).label("total_tasks")
            ).where(UserKeyModelStats.user_telegram_id == telegram_id)

            summary = (await session.execute(stmt)).first()

            model_usage_stmt = select(
                UserKeyModelStats.model_name,
                func.sum(UserKeyModelStats.total_tasks_completed).label("count")
            ).where(UserKeyModelStats.user_telegram_id == telegram_id).group_by(UserKeyModelStats.model_name)

            model_usage = (await session.execute(model_usage_stmt)).all()

            return {
                "total_spending": summary.total_spending or 0.0,
                "total_tasks": summary.total_tasks or 0,
                "model_usage": model_usage
            }

    async def get_analytics_report(
            self,
            start_date: date,
            end_date: date,
            user_telegram_id: Optional[int] = None,
            api_key_id: Optional[int] = None,
            model_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Строит детализированный отчет по логам с гибкими фильтрами.
        """
        async with self.session_factory() as session:
            start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
            end_dt = datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc)


            query = select(CompletedTaskLog).where(
                CompletedTaskLog.created_at.between(start_dt, end_dt)
            )
            if user_telegram_id:
                query = query.where(CompletedTaskLog.user_telegram_id == user_telegram_id)
            if api_key_id:
                query = query.where(CompletedTaskLog.api_key_id == api_key_id)
            if model_name:
                query = query.where(CompletedTaskLog.model_name == model_name)


            report_subquery = query.subquery()


            summary_stmt = select(
                func.count().label("total_generations"),
                func.sum(report_subquery.c.cost).label("total_revenue"),
                func.sum(report_subquery.c.prime_cost).label("total_prime_cost")
            ).select_from(report_subquery)

            summary_result = (await session.execute(summary_stmt)).first()


            model_breakdown_stmt = select(
                report_subquery.c.model_name,
                func.count().label("count"),
                func.sum(report_subquery.c.cost).label("revenue")
            ).select_from(report_subquery).group_by(report_subquery.c.model_name).order_by(func.count().desc())

            model_breakdown_result = (await session.execute(model_breakdown_stmt)).all()

            total_revenue = summary_result.total_revenue or 0
            total_prime_cost = summary_result.total_prime_cost or 0

            return {
                "total_generations": summary_result.total_generations or 0,
                "total_revenue": total_revenue,
                "total_profit": total_revenue - total_prime_cost,
                "model_breakdown": model_breakdown_result
            }

    async def get_daily_activity(
            self,
            user_telegram_id: Optional[int] = None,
            api_key_id: Optional[int] = None
    ) -> List:
        """
        Собирает агрегированные данные по дням для построения графика активности.
        Возвращает данные за последние 30 дней.
        """
        async with self.session_factory() as session:

            end_date = date.today()
            start_date = end_date - timedelta(days=30)


            stmt = (
                select(
                    func.date(CompletedTaskLog.created_at).label('date'),
                    func.count().label('count')
                )
                .where(func.date(CompletedTaskLog.created_at).between(start_date, end_date))
            )


            if user_telegram_id:
                stmt = stmt.where(CompletedTaskLog.user_telegram_id == user_telegram_id)
            if api_key_id:
                stmt = stmt.where(CompletedTaskLog.api_key_id == api_key_id)


            stmt = stmt.group_by(func.date(CompletedTaskLog.created_at)).order_by(
                func.date(CompletedTaskLog.created_at).asc())

            result = await session.execute(stmt)
            return result.all()

    async def get_key_summary(self, api_key_id: int) -> Dict[str, Any]:
        """
        Собирает сводную статистику по одному ключу из агрегированной таблицы.
        """
        async with self.session_factory() as session:

            summary_stmt = select(
                func.sum(UserKeyModelStats.total_spending).label("total_spending"),
                func.sum(UserKeyModelStats.total_tasks_completed).label("total_tasks_completed")
            ).where(UserKeyModelStats.api_key_id == api_key_id)
            summary_result = (await session.execute(summary_stmt)).first()


            model_usage_stmt = select(
                UserKeyModelStats.model_name.label("model"),
                func.sum(UserKeyModelStats.total_tasks_completed).label("count")
            ).where(UserKeyModelStats.api_key_id == api_key_id).group_by(UserKeyModelStats.model_name)
            model_usage_result = (await session.execute(model_usage_stmt)).all()

            return {
                "total_spending": summary_result.total_spending or 0.0,
                "total_tasks_completed": summary_result.total_tasks_completed or 0,
                "model_usage": model_usage_result
            }

    async def get_debit_transactions_for_key(self, api_key_id: int) -> List:
        """
        Получает историю списаний (debit) для ключа из детального лога.
        """
        async with self.session_factory() as session:
            stmt = select(
                CompletedTaskLog.created_at,
                CompletedTaskLog.cost,
                CompletedTaskLog.task_mongo_id,
                CompletedTaskLog.model_name
            ).where(CompletedTaskLog.api_key_id == api_key_id).order_by(CompletedTaskLog.created_at.desc())

            result = await session.execute(stmt)
            return result.all()