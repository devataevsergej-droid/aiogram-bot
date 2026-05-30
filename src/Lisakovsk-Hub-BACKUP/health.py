from __future__ import annotations

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.types import Update


async def health_check(_: web.Request) -> web.Response:
    return web.Response(text="OK")


async def telegram_webhook(request: web.Request) -> web.Response:
    bot: Bot = request.app["bot"]
    dispatcher: Dispatcher = request.app["dispatcher"]
    update_data = await request.json()
    update = Update.model_validate(update_data, context={"bot": bot})
    await dispatcher.feed_update(bot, update)
    return web.Response(text="OK")


def create_app(dispatcher: Dispatcher | None = None, bot: Bot | None = None, webhook_path: str = "/webhook") -> web.Application:
    app = web.Application()
    app.router.add_get("/", health_check)
    app.router.add_get("/health", health_check)
    if dispatcher is not None and bot is not None:
        app["dispatcher"] = dispatcher
        app["bot"] = bot
        app.router.add_post(webhook_path, telegram_webhook)
    return app


async def start_health_server(
    host: str,
    port: int,
    dispatcher: Dispatcher | None = None,
    bot: Bot | None = None,
    webhook_path: str = "/webhook",
) -> web.AppRunner:
    app = create_app(dispatcher=dispatcher, bot=bot, webhook_path=webhook_path)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    return runner
