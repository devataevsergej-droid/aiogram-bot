import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from src.artel_bot.handlers.masterclass import router as masterclass_router
from src.job_bot.db import SupabaseRepository
from src.job_bot.config import get_settings


async def main():
    logging.basicConfig(level=logging.INFO)
    
    # Получаем токен для Artel бота из переменной окружения
    token = os.getenv("ARTEL_BOT_TOKEN")
    if not token:
        logging.error("ARTEL_BOT_TOKEN not set")
        return
    
    settings = get_settings()
    bot = Bot(token=token)
    repo = SupabaseRepository(settings.supabase_url, settings.supabase_key)
    
    dp = Dispatcher(storage=MemoryStorage())
    dp["repo"] = repo
    dp.include_router(masterclass_router)
    
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
    