"""
Watchdog за изменениями vault.
Когда контент-план меняется в Obsidian (через Syncthing) — пишет в Telegram.
"""

import asyncio
import logging
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from telegram import Bot
from config.settings import Settings

logger = logging.getLogger(__name__)

DEBOUNCE_SECONDS = 5  # Syncthing пишет файл частями — ждём перед уведомлением


class _VaultHandler(FileSystemEventHandler):
    """Ловит события ФС и кидает пути изменённых .md файлов в asyncio-очередь."""

    def __init__(self, loop: asyncio.AbstractEventLoop, queue: asyncio.Queue):
        self.loop = loop
        self.queue = queue

    def _push(self, path: str):
        if not path.endswith(".md"):
            return
        asyncio.run_coroutine_threadsafe(self.queue.put(path), self.loop)

    def on_modified(self, event):
        if not event.is_directory:
            self._push(event.src_path)

    def on_created(self, event):
        if not event.is_directory:
            self._push(event.src_path)


async def start_watcher(settings: Settings):
    """
    Следит за vault и уведомляет в Telegram при изменении контент-плана.
    Запускается параллельно с ботом и планировщиком через asyncio.gather().
    """
    vault = settings.vault_path
    plan_abs = str(Path(vault) / settings.content_plan_file)

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[str] = asyncio.Queue()

    handler = _VaultHandler(loop, queue)
    observer = Observer()
    observer.schedule(handler, vault, recursive=True)
    observer.start()
    logger.info(f"Watchdog запущен: слежу за {vault}")

    bot = Bot(token=settings.telegram_token)
    # debounce: path → время последнего события
    pending: dict[str, float] = {}

    try:
        while True:
            try:
                path = await asyncio.wait_for(queue.get(), timeout=1.0)
                pending[path] = loop.time()
            except asyncio.TimeoutError:
                # Проверяем ожидающие уведомления у которых debounce истёк
                now = loop.time()
                for path, t in list(pending.items()):
                    if now - t >= DEBOUNCE_SECONDS:
                        del pending[path]
                        await _on_file_changed(bot, settings, path, plan_abs)
    except Exception as e:
        logger.error(f"Ошибка watchdog: {e}", exc_info=True)
    finally:
        observer.stop()
        observer.join()
        logger.info("Watchdog остановлен")


async def _on_file_changed(bot: Bot, settings: Settings, path: str, plan_abs: str):
    """Реагирует на изменение файла. Уведомляет только об изменениях контент-плана."""
    if path != plan_abs:
        logger.debug(f"Изменён файл vault (не план): {Path(path).name}")
        return

    logger.info(f"Контент-план изменён в Obsidian: {path}")
    try:
        await bot.send_message(
            chat_id=settings.telegram_owner_id,
            text="📝 Контент-план обновлён в Obsidian.",
        )
    except Exception as e:
        logger.error(f"Watchdog: не удалось отправить уведомление: {e}")
