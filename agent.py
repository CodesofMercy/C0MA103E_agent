"""
C0MA103E Agent — точка входа.
Запускает Telegram-бота и планировщик задач параллельно.

Запуск:
    python main.py
"""

import asyncio
import logging
import os
from src.bot.telegram_bot import start_bot
from src.agent.scheduler import start_scheduler
from src.sync.watcher import start_watcher
from config.settings import load_settings

os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("logs/agent.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


async def main():
    logger.info("C0MA103E Agent запускается...")
    settings = load_settings()

    if not settings.telegram_token:
        logger.error("TELEGRAM_TOKEN не задан в .env")
        return
    if not settings.anthropic_api_key:
        logger.error("ANTHROPIC_API_KEY не задан в .env")
        return
    if not settings.telegram_owner_id:
        logger.error("TELEGRAM_OWNER_ID не задан в .env")
        return

    logger.info(f"Vault: {settings.vault_path}")
    logger.info(f"Модель: {settings.claude_model}")

    await asyncio.gather(
        start_bot(settings),
        start_scheduler(settings),
        start_watcher(settings),
    )


if __name__ == "__main__":
    asyncio.run(main())
