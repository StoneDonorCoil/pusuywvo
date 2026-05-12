"""
FastAPI wrapper for the Telegram bot.
Runs the bot in polling mode as a background task alongside a health-check endpoint.
"""

import asyncio
import logging

from contextlib import asynccontextmanager
from fastapi import FastAPI

from aiogram import Bot, Dispatcher, Router
from aiogram.types import Update

import config
import database as db

# Import all handlers by importing bot module
from bot import router as bot_router, bot as tg_bot, dp

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

polling_task = None


async def start_polling():
    await db.init_db()
    logger.info("Starting bot polling...")
    await dp.start_polling(tg_bot)


@asynccontextmanager
async def lifespan(application: FastAPI):
    global polling_task
    polling_task = asyncio.create_task(start_polling())
    logger.info("Bot polling started as background task")
    yield
    # Shutdown
    if polling_task and not polling_task.done():
        await dp.stop_polling()
        polling_task.cancel()
        try:
            await polling_task
        except asyncio.CancelledError:
            pass
    logger.info("Bot stopped")


app = FastAPI(title="Edu Store Bot", lifespan=lifespan)


@app.get("/")
async def health():
    return {"status": "ok", "bot": "running"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
