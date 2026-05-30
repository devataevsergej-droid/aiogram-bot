from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from config import get_settings
from .db import SupabaseRepository
from .handlers.job import router as job_router
from health import start_health_server
from scheduler import setup_scheduler


async def run_bot() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    bot = Bot(token=settings.bot_token)
    repo = SupabaseRepository(settings.supabase_url, settings.supabase_key)
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher["repo"] = repo
    dispatcher["settings"] = settings
    dispatcher.include_router(job_router)
    setup_scheduler(repo, bot, settings)

    if settings.webhook_url:
        await bot.set_webhook(settings.webhook_url)
        await start_health_server(
            settings.health_host,
            settings.health_port,
            dispatcher=dispatcher,
            bot=bot,
            webhook_path=settings.webhook_path,
        )
        await asyncio.Event().wait()
        return

    await start_health_server(settings.health_host, settings.health_port)
    await dispatcher.start_polling(bot)


def main() -> None:
    asyncio.run(run_bot())


if __name__ == "__main__":
    main()
