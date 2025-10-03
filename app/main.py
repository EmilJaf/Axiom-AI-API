import json

from aiobotocore.session import get_session
from fastapi import FastAPI, Depends, HTTPException
from contextlib import asynccontextmanager
from typing import Tuple

import aio_pika
from motor.motor_asyncio import AsyncIOMotorCollection
from starlette import status
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import HTMLResponse

from app.aws.aws_config import AWS_REGION
from app.database.main_models import Base, ApiKey, User
from app.database.repositories.user_price_repository import UserPriceRepository
from app.database.repositories.user_repository import UserRepository, ApiKeyRepository
from app.database.engine import engine
from app.database.mongo_db import get_task_collection
from app.database.repositories.price_repository import PriceRepository
from app import schemas
from app import dependencies
from app.documentation import API_DESCRIPTION
from app.routers import admin_main_router
from app.routers.admin.users import UserCreate, UserBase, UserWithKeys
from app.schemas import TaskStatusResponse
from app.services.generation_service import GenerationService
from app.settings import settings


AUTH_DEPENDENCY = Depends(dependencies.get_current_user_and_key)



@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session = get_session()

    async with session.create_client('s3', region_name=AWS_REGION) as s3_client:

        app.state.s3_client = s3_client

        try:
            connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
            channel = await connection.channel()

            app.state.rabbitmq_channel = channel
            app.state.rabbitmq_connection = connection
            print("Successfully connected to RabbitMQ")

            yield

        finally:
            if connection:
                await connection.close()
                print("RabbitMQ connection closed")

app = FastAPI(
    title=settings.APP_TITLE,
    version=settings.APP_VERSION,
    description=API_DESCRIPTION,
    lifespan=lifespan
)

MODELS_WITH_DURATION_COST = settings.MODELS_WITH_DURATION_COST

app.include_router(admin_main_router.router)



app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)




@app.post("/users", response_model=UserBase, tags=["User Management"], include_in_schema=False)
async def create_user(
    user_schema: UserCreate,
    user_repo: UserRepository = Depends(dependencies.get_user_repository)
):

    user = await user_repo.get_or_create(telegram_id=user_schema.telegram_id)
    answer = {'telegram_id': user.telegram_id, 'coefficient': user.coefficient}
    return answer


@app.get("/me/keys", response_model=UserWithKeys, tags=["My Account"], include_in_schema=False)
async def get_my_keys(
    auth_data: Tuple[User, ApiKey] = AUTH_DEPENDENCY,
    user_repo: UserRepository = Depends(dependencies.get_user_repository),
):

    user, _ = auth_data
    user_with_keys = await user_repo.get_with_keys(telegram_id=user.telegram_id)
    return user_with_keys


@app.get("/me/balance", response_model=schemas.Balance, tags=["My Account"], include_in_schema=False)
async def get_my_key_balance(auth_data: Tuple[User, ApiKey] = AUTH_DEPENDENCY):

    _, api_key = auth_data
    return {"key_balance": api_key.balance}


@app.get("/tasks/{task_id}", response_model=TaskStatusResponse, tags=["Tasks"])
async def get_task_status(
    task_id: str,
    tasks_collection: AsyncIOMotorCollection = Depends(get_task_collection),
    auth_data: Tuple[User, ApiKey] = AUTH_DEPENDENCY
):

    user, _ = auth_data

    task = await tasks_collection.find_one({"_id": task_id})
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")


    if task.get("user_telegram_id") != user.telegram_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this task"
        )

    return TaskStatusResponse(
        task_id=task["_id"],
        status=task["status"],
        result=task.get("result"),
        error=task.get("error")
    )


@app.post("/generate", response_model=schemas.GenerateAcceptedResponse, status_code=status.HTTP_202_ACCEPTED,
          tags=["Core Logic"])
async def generate(
        request_data: schemas.GenerateRequest,
        auth_data: Tuple[User, ApiKey] = AUTH_DEPENDENCY,
        key_repo: ApiKeyRepository = Depends(dependencies.get_key_repository),
        price_repo: PriceRepository = Depends(dependencies.get_price_repository),
        user_price_repo: UserPriceRepository = Depends(dependencies.get_user_price_repository)
):

    user, api_key = auth_data

    service = GenerationService(
        user=user,
        api_key=api_key,
        key_repo=key_repo,
        price_repo=price_repo,
        user_price_repo=user_price_repo,
    )

    task_id, task_message_body = await service.prepare_generation_task(request_data.params)

    channel: aio_pika.Channel = app.state.rabbitmq_channel

    routing_key = 'general_tasks_queue'


    dlx_name = f"{routing_key}.dlx"
    queue_arguments = {
        "x-dead-letter-exchange": dlx_name
    }

    await channel.declare_queue(
        routing_key,
        durable=True,
        arguments=queue_arguments
    )

    await channel.default_exchange.publish(
        aio_pika.Message(
            body=json.dumps(task_message_body, default=str).encode(),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT
        ),
        routing_key=routing_key
    )

    return schemas.GenerateAcceptedResponse(task_id=task_id)



@app.get("/docs/elements", response_class=HTMLResponse, include_in_schema=False)
async def get_elements_docs():
    return """
    <!doctype html>
    <html lang="en">
      <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no">
        <title>Main API V3</title>
        <script src="https://unpkg.com/@stoplight/elements/web-components.min.js"></script>
        <link rel="stylesheet" href="https://unpkg.com/@stoplight/elements/styles.min.css">
      </head>
      <body>
        <elements-api
          apiDescriptionUrl="/openapi.json" 
          router="hash"
          layout="sidebar"
        />
      </body>
    </html>
"""

