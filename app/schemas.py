from datetime import datetime
from typing import List, Literal, Optional, Any, Annotated, Union

from pydantic import BaseModel, Field



class VideoModelParams(BaseModel):
    model_name: Literal["video-model"]
    prompt: str = Field(..., description="Main prompt for generation")
    image_url: Optional[str] = Field(None, description='URL / Base 64 of image')
    duration: Literal[5, 10] = Field(5, description='Duration of video')
    translate: bool = False


class ImageModelParams(BaseModel):
    model_name: Literal["image-model"]
    prompt: str = Field(..., description="Main prompt for generation")
    negative_prompt: Optional[str] = Field(None, description='Negative prompt for generation')
    num_images: int = Field(1, ge=1, le=4)


class RandomModelOneParams(BaseModel):
    model_name: Literal["random-model"]
    prompt: str = Field(..., description="Main prompt for generation")


class RandomModelTwoParams(BaseModel):
    model_name: Literal["random-model"]
    prompt: str = Field(..., description="Main prompt for generation")




AnyModelParams = Annotated[
    Union[
        VideoModelParams,
        ImageModelParams,
        RandomModelOneParams,
        RandomModelTwoParams
    ],
    Field(discriminator="model_name")
]

class GenerateRequest(BaseModel):
    params: AnyModelParams

class GenerateAcceptedResponse(BaseModel):
    message: str = "Task accepted for processing"
    task_id: str


TaskStatus = Literal["pending", "processing", "completed", "failed"]


class TaskStatusResponse(BaseModel):
    task_id: str
    status: TaskStatus
    result: Optional[Any] = None
    error: Optional[str] = None
    created_at: Optional[datetime] = None
    class Config:
        from_attributes = True



class Balance(BaseModel):
    key_balance: float


class UserStatItem(BaseModel):
    model: str
    count: int


class DailyActivity(BaseModel):
    date: str
    count: int


class UserAnalyticsResponse(BaseModel):
    telegram_id: int
    total_spending: float
    total_tasks: int
    failed_tasks: int
    model_usage: List[UserStatItem]
    daily_activity: List[DailyActivity]