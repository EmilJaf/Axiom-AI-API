from sqlalchemy import Column, Integer, String, Date, Float, BigInteger, UniqueConstraint, DateTime, func
from sqlalchemy.orm import declarative_base


Base = declarative_base()


class DailySystemStats(Base):
    """Витрина данных №1: Агрегаты по дням для быстрых дашбордов."""
    __tablename__ = 'daily_system_stats'

    date = Column(Date, primary_key=True)
    tasks_completed = Column(Integer, nullable=False, default=0)
    total_revenue = Column(Float, nullable=False, default=0.0)
    total_prime_cost = Column(Float, nullable=False, default=0.0)
    profit = Column(Float, nullable=False, default=0.0)


class UserKeyModelStats(Base):
    """Витрина данных №2: Агрегаты по пользователю, ключу и модели."""
    __tablename__ = 'user_key_model_stats'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_telegram_id = Column(BigInteger, nullable=False)
    api_key_id = Column(Integer, nullable=False)
    model_name = Column(String(100), nullable=False)
    total_tasks_completed = Column(Integer, nullable=False, default=0)
    total_spending = Column(Float, nullable=False, default=0.0)


    __table_args__ = (
        UniqueConstraint('user_telegram_id', 'api_key_id', 'model_name', name='uq_user_key_model_stats'),
    )


class CompletedTaskLog(Base):
    """Таблица фактов: Детальный лог каждой задачи для глубокого анализа."""
    __tablename__ = 'completed_task_log'

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_mongo_id = Column(String(36), index=True, nullable=False)
    user_telegram_id = Column(BigInteger, index=True, nullable=False)
    api_key_id = Column(Integer, index=True, nullable=False)
    model_name = Column(String(100), index=True, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now(), index=True)
    cost = Column(Float, nullable=False)
    prime_cost = Column(Float, nullable=False)