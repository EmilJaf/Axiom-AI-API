from fastapi import APIRouter, Depends
from app import dependencies

from app.routers.admin import keys, logs, prices, stats, tasks, workers, users, analytics


router = APIRouter(
    prefix="/admin",
    dependencies=[Depends(dependencies.get_current_admin_user_and_key)],
    tags=["Admin"],
    include_in_schema=False
)

router.include_router(users.router)
router.include_router(keys.router)
router.include_router(prices.router)
router.include_router(logs.router)
router.include_router(stats.router)
router.include_router(tasks.router)
router.include_router(workers.router)
router.include_router(analytics.router)