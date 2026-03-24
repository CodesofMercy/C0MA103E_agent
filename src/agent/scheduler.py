"""
Планировщик задач агента.
Утром присылает дейли, в воскресенье напоминает о генерации контента.
"""

import asyncio
import logging
from zoneinfo import ZoneInfo
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from config.settings import Settings

logger = logging.getLogger(__name__)


async def daily_briefing(settings: Settings):
    """
    Каждое утро в 09:00 — агент пишет тебе что делать сегодня.
    """
    from src.agent.brain import AgentBrain
    from telegram import Bot

    logger.info("Запуск утреннего дейли...")
    brain = AgentBrain(settings)
    bot = Bot(token=settings.telegram_token)

    try:
        tasks = await brain.get_today_tasks()
        await bot.send_message(
            chat_id=settings.telegram_owner_id,
            text=f"☀️ Доброе утро. C0MA103E дейли:\n\n{tasks}",
        )
        logger.info("Дейли отправлен")
    except Exception as e:
        logger.error(f"Ошибка дейли: {e}")


async def weekly_reminder(settings: Settings):
    """
    По воскресеньям в 12:00 — напоминание о генерации контента на неделю.
    После MVP: подключить generators и запускать автоматически.
    """
    from telegram import Bot

    bot = Bot(token=settings.telegram_token)
    try:
        await bot.send_message(
            chat_id=settings.telegram_owner_id,
            text=(
                "📅 Воскресенье — время планировать следующую неделю.\n\n"
                "Напиши /week чтобы увидеть план.\n"
                "Напиши /generate когда генераторы будут подключены."
            ),
        )
    except Exception as e:
        logger.error(f"Ошибка еженедельного напоминания: {e}")


async def start_scheduler(settings: Settings):
    tz = ZoneInfo("Europe/Moscow")  # UTC+3, московское время
    scheduler = AsyncIOScheduler(timezone=tz)

    # Утренний дейли — каждый день в 09:00 по Москве
    scheduler.add_job(
        daily_briefing,
        CronTrigger(hour=9, minute=0, timezone=tz),
        args=[settings],
        id="daily_briefing",
        name="Утренний дейли",
    )

    # Еженедельное напоминание — каждое воскресенье в 12:00 по Москве
    scheduler.add_job(
        weekly_reminder,
        CronTrigger(day_of_week="sun", hour=12, minute=0, timezone=tz),
        args=[settings],
        id="weekly_reminder",
        name="Еженедельное напоминание",
    )

    scheduler.start()
    logger.info("Планировщик запущен (дейли в 09:00, напоминание вс 12:00 — Europe/Moscow)")

    # Держим живым
    while True:
        await asyncio.sleep(60)
