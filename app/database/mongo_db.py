from motor.motor_asyncio import AsyncIOMotorClient

from app.settings import settings



mongo_uri = settings.MONGO_URI
mongo_client = AsyncIOMotorClient(mongo_uri, tz_aware=True)
database = mongo_client.task_db


def get_task_collection():
    return database.get_collection("tasks")