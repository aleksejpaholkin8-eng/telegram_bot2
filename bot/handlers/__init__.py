from aiogram import Router

from bot.handlers.common import router as common_router
from bot.handlers.admin import router as admin_router
from bot.handlers.tracks import router as tracks_router
from bot.handlers.system_cmds import router as system_cmds_router
from bot.handlers.ai import router as ai_router

router = Router()

router.include_router(common_router)
router.include_router(admin_router)
router.include_router(tracks_router)
router.include_router(system_cmds_router)
router.include_router(ai_router)
