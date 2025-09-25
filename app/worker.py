import asyncio
import logging
from datetime import datetime, timezone

import aiobotocore.client
import aiohttp
from aiobotocore.session import get_session
from aiohttp import ClientTimeout
from motor.motor_asyncio import AsyncIOMotorCollection

from app.aws.aws_config import AWS_REGION
from app.database.engine import async_session_factory
from app.database.mongo_db import get_task_collection
from app.database.repositories.user_repository import ApiKeyRepository

from app.services.providers import example_provider
from app.settings import settings

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [WORKER] - %(message)s'
)

logging.info("Worker starting....")

WORKER_ID = settings.WORKER_ID

MAX_CONCURRENT_TASKS = settings.WORKER_MAX_CONCURRENT_TASKS

MODELS_TO_IGNORE = settings.WORKER_MODELS_TO_IGNORE

MONGO_QUERY = {"status": "pending", "model": {"$nin": MODELS_TO_IGNORE}}




logger = logging.LoggerAdapter(logging.getLogger(__name__), {'worker_id': WORKER_ID})


MODEL_PROCESSORS = {

    'image-model': example_provider.generate_image,
    'video-model': example_provider.generate_video,
    'random-model-1': example_provider.generate,
    'random-model-2': example_provider.generate
}


async def process_task(session: aiohttp.ClientSession,
                       s3_client: aiobotocore.client.BaseClient,
                       task: dict,
                       tasks_collection: AsyncIOMotorCollection,
                       status_collection: AsyncIOMotorCollection,
                       key_repo: ApiKeyRepository,
                       semaphore: asyncio.Semaphore):


    task_id = task["_id"]
    async with semaphore:
        logger.info(f"TaskID: {task_id} | Starting task")
        await update_worker_status(status_collection, "processing", task_id)

        model_name = task["model"]
        params = task.get("params", {})

        try:
            processor = MODEL_PROCESSORS.get(model_name)
            if not processor:
                raise ValueError(f"Not found processor for '{model_name}'")



            result_data = await processor(
                session=session,
                s3_client=s3_client,
                params=params,
                task_id=task_id
            )


            update_data = {"status": "completed", "result": result_data}
            await tasks_collection.update_one({"_id": task_id}, {"$set": update_data})
            logger.info(f"TaskID: {task_id} | Done")

        except Exception as e:
            logger.error(f"TaskID: {task_id} | Error: {e}", exc_info=True)
            await tasks_collection.update_one({"_id": task_id}, {"$set": {"status": "failed", "error": str(e)}})
            await refund_on_failure(task, key_repo)

        finally:
            await update_worker_status(status_collection, "idle")


async def refund_on_failure(
        task: dict,
        key_repo: ApiKeyRepository
):

    key_id_to_refund = task.get("api_key_id")
    cost_to_refund = task.get("cost")
    task_id = task["_id"]

    if key_id_to_refund and cost_to_refund is not None:
        try:
            logger.warning(f"TaskID: {task_id} | Refund {cost_to_refund} api key ID: {key_id_to_refund}")
            await key_repo.refund_balance(key_id=key_id_to_refund, amount=cost_to_refund)
            logger.info(f"TaskID: {task_id} | Refund done")
        except Exception as refund_error:
            logger.critical(
                f"TaskID: {task_id} | Refund error! API key ID: {key_id_to_refund}, Amount: {cost_to_refund}. Error: {refund_error}",
                exc_info=True)
    else:
        logger.error(f"TaskID: {task_id} | Unable to refund: no api_key_id or cost.")


async def update_worker_status(status_collection: AsyncIOMotorCollection, status: str, current_task_id: str | None = None):

    await status_collection.update_one(
        {"_id": WORKER_ID},
        {"$set": {"last_heartbeat": datetime.now(timezone.utc), "status": status, "current_task_id": current_task_id}},
        upsert=True
    )


async def recover_stuck_tasks(tasks_collection: AsyncIOMotorCollection):

    logging.info("Checking for stuck tasks...")
    result = await tasks_collection.update_many({"status": "processing"}, {"$set": {"status": "pending"}})
    if result.modified_count > 0:
        logging.warning(f"Recovered {result.modified_count} stuck tasks.")
    else:
        logging.info("Stuck tasks not found.")



async def main():

    tasks_collection = get_task_collection()
    status_collection = tasks_collection.database.get_collection("worker_status")

    await recover_stuck_tasks(tasks_collection)
    logger.info(f"Worker {WORKER_ID} started. Max concurrent tasks: {MAX_CONCURRENT_TASKS}")

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)
    timeout = ClientTimeout(total=600)

    key_repo = ApiKeyRepository(async_session_factory)


    session = get_session()
    async with aiohttp.ClientSession(timeout=timeout) as http_session:
        async with session.create_client(
                's3',
                region_name=AWS_REGION,
        ) as s3_client:
            while True:
                try:
                    await update_worker_status(status_collection, "idle")
                    task = await tasks_collection.find_one_and_update(
                        MONGO_QUERY,
                        {"$set": {"status": "processing", "processed_by": WORKER_ID}},
                    )
                    if task:
                        logger.info(f"TaskID: {task['_id']} | Start processing.")
                        asyncio.create_task(process_task(http_session, s3_client, task, tasks_collection, status_collection, key_repo, semaphore))
                    else:
                        await asyncio.sleep(5)
                except Exception as e:
                    logger.critical(f"Critical error in worker: {e}", exc_info=True)
                    await asyncio.sleep(15)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info(f"Worker {WORKER_ID} stopped.")
    except Exception as e:
        logging.critical(f"Worker {WORKER_ID} failed to start. Error: {e}", exc_info=True)