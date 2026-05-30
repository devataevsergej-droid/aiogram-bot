from __future__ import annotations

import logging
from datetime import UTC, datetime

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import Settings
from bots.job_bot.db import SupabaseRepository
from bots.job_bot.keyboards.common.channel import weekly_stats_keyboard
from services.job_text import weekly_stats_text

logger = logging.getLogger(__name__)


async def reset_daily_usage(repo: SupabaseRepository) -> None:
    await repo.reset_daily_usage()


async def reset_monthly_usage(repo: SupabaseRepository) -> None:
    await repo.reset_monthly_usage()


async def unpin_due_messages(repo: SupabaseRepository, bot: Bot, settings: Settings) -> None:
    for item in await repo.list_due_unpins():
        try:
            await bot.unpin_chat_message(settings.channel_id, item["channel_message_id"])
            await repo.mark_unpin_done(item["id"])
        except Exception:
            logger.exception("Failed to unpin scheduled message %s", item["id"])
            await repo.mark_unpin_done(item["id"], failed=True)


async def post_weekly_stats(repo: SupabaseRepository, bot: Bot, settings: Settings) -> None:
    stats = await repo.weekly_stats()
    await bot.send_message(
        settings.channel_id,
        weekly_stats_text(stats),
        reply_markup=weekly_stats_keyboard(settings.bot_username),
    )


def setup_scheduler(repo: SupabaseRepository, bot: Bot, settings: Settings) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=UTC)
    scheduler.add_job(reset_daily_usage, "cron", hour=0, minute=0, args=[repo], id="reset_daily_usage", replace_existing=True)
    scheduler.add_job(
        reset_monthly_usage,
        "cron",
        day=1,
        hour=0,
        minute=5,
        args=[repo],
        id="reset_monthly_usage",
        replace_existing=True,
    )
    scheduler.add_job(
        unpin_due_messages,
        "interval",
        minutes=10,
        args=[repo, bot, settings],
        id="unpin_due_messages",
        replace_existing=True,
        next_run_time=datetime.now(UTC),
    )
    scheduler.add_job(
        post_weekly_stats,
        "cron",
        day_of_week="mon",
        hour=9,
        minute=0,
        args=[repo, bot, settings],
        id="post_weekly_stats",
        replace_existing=True,
    )
    scheduler.start()
    return scheduler
