import asyncio
import logging
import sys
from contextlib import asynccontextmanager, suppress

from aiogram.types import Update
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from app.api.models import Base
from app.bot.create_bot import bot, dp
from app.bot.handlers.admin_router import admin_router
from app.bot.handlers.user_router import user_router
from app.config import settings
from app.database import engine
from app.pages.router import router as router_pages
from app.api.router import router as router_api
from app.services.giveaways import finish_due_giveaways, publish_due_giveaways, refresh_active_giveaways

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s", stream=sys.stdout)


async def giveaway_worker() -> None:
    refresh_tick = 0
    while True:
        try:
            await publish_due_giveaways(bot)
            refresh_tick += 1
            if refresh_tick % 4 == 0:
                await refresh_active_giveaways(bot)
            await finish_due_giveaways(bot)
        except Exception:
            logging.exception("Giveaway worker failed")
        await asyncio.sleep(15)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.info("Starting application...")
    dp.include_router(user_router)
    dp.include_router(admin_router)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        columns = await conn.exec_driver_sql("PRAGMA table_info(tg_giveaways)")
        column_names = {row[1] for row in columns.fetchall()}
        if "require_captcha" not in column_names:
            await conn.exec_driver_sql("ALTER TABLE tg_giveaways ADD COLUMN require_captcha BOOLEAN NOT NULL DEFAULT 1")

    webhook_url = settings.get_webhook_url()
    await bot.set_webhook(
        url=webhook_url,
        allowed_updates=dp.resolve_used_update_types(),
        secret_token=settings.TG_SECRET,
        drop_pending_updates=True,
    )
    worker = asyncio.create_task(giveaway_worker())
    app.state.giveaway_worker = worker
    logging.info("Webhook set to %s", webhook_url)
    yield
    logging.info("Shutting down application...")
    worker = getattr(app.state, "giveaway_worker", None)
    if worker:
        worker.cancel()
        with suppress(asyncio.CancelledError):
            await worker
    await bot.delete_webhook()
    logging.info("Webhook deleted")


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="app/static"), "static")


@app.post("/webhook")
async def webhook(request: Request) -> None:
    if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != settings.TG_SECRET:
        logging.info("Webhook secret mismatch, skipping update")
        return

    update = Update.model_validate(await request.json(), context={"bot": bot})
    await dp.feed_update(bot, update)


app.include_router(router_pages)
app.include_router(router_api)
