from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.settings import settings


db_url = settings.DATABASE_URL


engine = create_async_engine(db_url,
                             echo=False,
                             pool_recycle=3600
                             )

async_session_factory = async_sessionmaker(engine, expire_on_commit=False)