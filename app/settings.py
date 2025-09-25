from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Set, List

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8')

    APP_TITLE: str = "Main API v3"
    APP_VERSION: str = "3.0.0"

    DATABASE_URL: str
    MONGO_URI: str
    AWS_REGION: str
    ADMIN_API_KEY: str

    WORKER_MAX_CONCURRENT_TASKS: int = 40
    WORKER_MODELS_TO_IGNORE: List[str] = Field(default_factory=lambda: ["some-models-to-ignore"])

    WORKER_ID: str = Field('main-1', validation_alias='WORKER_NAME')

    MODELS_WITH_DURATION_COST: Set[str] = Field(default_factory=lambda: {"video-model"})


    ALLOWED_ORIGINS: List[str] = Field(default_factory=lambda: ['*'])

settings = Settings()