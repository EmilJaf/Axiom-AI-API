import asyncio
import json
import logging
import traceback
from datetime import datetime

import aio_pika
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

WORKER_ID = settings.WORKER_ID
MAX_CONCURRENT_TASKS = settings.WORKER_MAX_CONCURRENT_TASKS
QUEUE_NAME = 'general_tasks_queue'

logger = logging.getLogger(__name__)

MODEL_PROCESSORS = {
    'image-model': example_provider.generate_image,
    'video-model': example_provider.generate_video,
    'random-model-one': example_provider.generate,
    'random-model-two': example_provider.generate
}


async def process_task(session: aiohttp.ClientSession,
                       s3_client: aiobotocore.client.BaseClient,
                       task_data: dict,
                       tasks_collection: AsyncIOMotorCollection,
                       key_repo: ApiKeyRepository):
    task_id = task_data["_id"]
    logger.info(f"TaskID: {task_id} | Начинаю обработку.")


    filter_query = {"_id": task_id}
    update_data = {
        "$setOnInsert": {
            "user_telegram_id": task_data["user_telegram_id"],
            "api_key_id": task_data["api_key_id"],
            "model": task_data["model"],
            "params": task_data.get("params", {}),
            "cost": task_data.get("cost"),
            "prime_cost": task_data.get("prime_cost"),
            "created_at": datetime.fromisoformat(task_data["created_at"])
        },
        "$set": {
            "status": "processing",
            "processed_by": WORKER_ID,
            "result": None,
            "error": None
        }
    }
    await tasks_collection.find_one_and_update(filter_query, update_data, upsert=True)

    model_name = task_data["model"]
    params = task_data.get("params", {})

    try:

        processor = MODEL_PROCESSORS.get(model_name)
        if not processor:
            raise ValueError(f"Не найден обработчик для модели '{model_name}'")

        result_data = await processor(
            session=session,
            s3_client=s3_client,
            params=params,
            task_id=task_id
        )

        update_data = {"status": "completed", "result": result_data}
        await tasks_collection.update_one({"_id": task_id}, {"$set": update_data})
        logger.info(f"TaskID: {task_id} | Задача успешно завершена.")

    except Exception as e:
        logger.error(f"TaskID: {task_id} | Ошибка при обработке: {e}", exc_info=True)
        await tasks_collection.update_one({"_id": task_id}, {"$set": {"status": "failed", "error": str(e)}})
        await refund_on_failure(task_data, key_repo)



async def refund_on_failure(task: dict, key_repo: ApiKeyRepository):
    key_id_to_refund = task.get("api_key_id")
    cost_to_refund = task.get("cost")
    task_id = task["_id"]

    if key_id_to_refund and cost_to_refund is not None:
        try:
            logger.warning(f"TaskID: {task_id} | Возврат {cost_to_refund} на ключ ID: {key_id_to_refund}")
            await key_repo.refund_balance(key_id=key_id_to_refund, amount=cost_to_refund)
            logger.info(f"TaskID: {task_id} | Возврат выполнен.")
        except Exception as refund_error:
            logger.critical(
                f"TaskID: {task_id} | Ошибка возврата! Ключ ID: {key_id_to_refund}, Сумма: {cost_to_refund}. Ошибка: {refund_error}",
                exc_info=True)
    else:
        logger.error(f"TaskID: {task_id} | Невозможно выполнить возврат: нет api_key_id или cost.")


async def main():
    tasks_collection = get_task_collection()
    key_repo = ApiKeyRepository(async_session_factory)

    logger.info(f"Воркер {WORKER_ID} запущен. Максимум одновременных задач: {MAX_CONCURRENT_TASKS}")

    timeout = ClientTimeout(total=600)
    aws_session = get_session()


    connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)

    async with connection:
        channel = await connection.channel()

        await channel.set_qos(prefetch_count=MAX_CONCURRENT_TASKS)

        dlx_name = f"{QUEUE_NAME}.dlx"
        dlq_name = f"{QUEUE_NAME}.dlq"


        dlx = await channel.declare_exchange(dlx_name, aio_pika.ExchangeType.FANOUT)


        dlq = await channel.declare_queue(dlq_name, durable=True)

        await dlq.bind(dlx)

        queue = await channel.declare_queue(
            QUEUE_NAME,
            durable=True,
            arguments={
                "x-dead-letter-exchange": dlx_name
            }
        )
        async with aiohttp.ClientSession(timeout=timeout) as http_session:
            async with aws_session.create_client('s3', region_name=AWS_REGION) as s3_client:


                async def on_message(message: aio_pika.IncomingMessage):
                    try:
                        async with message.process(requeue=False):

                            task_data = json.loads(message.body.decode())
                            logger.info(f"TaskID: {task_data['_id']} | Задача получена из очереди.")


                            await process_task(
                                session=http_session,
                                s3_client=s3_client,
                                task_data=task_data,
                                tasks_collection=tasks_collection,
                                key_repo=key_repo
                            )

                    except Exception as e:

                        error_traceback = traceback.format_exc()
                        task_id = task_data['_id'] if task_data else "unknown_id"

                        logging.error(
                            f"TaskID: {task_id} | КРИТИЧЕСКАЯ ОШИБКА. Задача будет отправлена в DLQ. Ошибка: {e}",
                            exc_info=True)


                await queue.consume(on_message)

                logger.info(" [*] Ожидание задач. Для выхода нажмите CTRL+C")
                await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info(f"Воркер {WORKER_ID} остановлен.")
    except Exception as e:
        logging.critical(f"Воркер {WORKER_ID} упал с критической ошибкой: {e}", exc_info=True)