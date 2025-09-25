import asyncio
import logging
from typing import Dict, Any
import aiohttp
from botocore.client import BaseClient



logger = logging.getLogger(__name__)



async def generate_video(
    session: aiohttp.ClientSession,
    s3_client: BaseClient,
    params: Dict[str, Any],
    task_id: str
) -> Dict[str, Any]:

    logger.info(f"TaskID: {task_id} | ExampleProvider, params: {params}")

    await asyncio.sleep(5)

    logger.info(f"TaskID: {task_id} | Video Model")

    return {"video_url": f"https://example.com/videos/mock_video_{task_id}.mp4"}



async def generate_image(
        session: aiohttp.ClientSession,
        s3_client: BaseClient,
        params: Dict[str, Any],
        task_id: str
) -> Dict[str, Any]:
    logger.info(f"TaskID: {task_id} | ExampleProvider, params: {params}")

    await asyncio.sleep(5)

    logger.info(f"TaskID: {task_id} | Image Model")

    num_images = params.get("num_images", 1)
    image_urls = [f"https://example.com/images/mock_image_{task_id}_{i}.png" for i in range(num_images)]

    return {"image_urls": image_urls}



async def generate(
        session: aiohttp.ClientSession,
        s3_client: BaseClient,
        params: Dict[str, Any],
        task_id: str
) -> Dict[str, Any]:
    logger.info(f"TaskID: {task_id} | ExampleProvider, params: {params}")

    await asyncio.sleep(5)

    model_name = params.get('model_name')

    logger.warning(f"TaskID: {task_id} | Unknown model. Default answer.")

    return {"result": f"Mock result for model {model_name} (task {task_id})"}
