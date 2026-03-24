"""
Telegram-бот — интерфейс между тобой и агентом.
Принимает команды, отправляет уведомления с файлами.
"""

import asyncio
import logging
from pathlib import Path
from telegram import Update, Bot
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from config.settings import Settings

logger = logging.getLogger(__name__)


class C0MA103EBot:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.owner_id = settings.telegram_owner_id
        # bot_instance заполняется в start_bot() — нужен для send_notification из фоновых задач
        self.bot_instance: Bot | None = None

    def _is_owner(self, update: Update) -> bool:
        """Бот отвечает только тебе."""
        return update.effective_user.id == self.owner_id

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_owner(update):
            return
        await update.message.reply_text(
            "C0MA103E Agent активен.\n\n"
            "/plan — показать план на сегодня\n"
            "/week — план на неделю\n"
            "/generate — запустить генерацию контента\n"
            "/queue — что готово и ждёт публикации\n"
            "\nИли просто напиши мне — я передам агенту."
        )

    async def cmd_plan(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показывает что нужно сделать сегодня."""
        if not self._is_owner(update):
            return
        await update.message.reply_text("Читаю контент-план...")
        from src.agent.brain import AgentBrain
        brain = AgentBrain(self.settings)
        result = await brain.get_today_tasks()
        for chunk in self._split(result):
            await update.message.reply_text(chunk)

    async def cmd_week(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показывает план на неделю."""
        if not self._is_owner(update):
            return
        await update.message.reply_text("Читаю план на неделю...")
        from src.agent.brain import AgentBrain
        brain = AgentBrain(self.settings)
        result = await brain.get_week_tasks()
        for chunk in self._split(result):
            await update.message.reply_text(chunk)

    async def cmd_queue(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показывает и отправляет файлы, готовые к публикации."""
        if not self._is_owner(update):
            return
        queue_dir = Path(self.settings.queue_dir)
        files = sorted(queue_dir.glob("*")) if queue_dir.exists() else []
        if not files:
            await update.message.reply_text("Очередь пуста.")
            return

        await update.message.reply_text(f"Готово к публикации: {len(files)} файл(ов). Отправляю...")
        for f in files:
            caption = f.name
            try:
                with open(f, "rb") as fh:
                    suffix = f.suffix.lower()
                    if suffix in (".jpg", ".jpeg", ".png", ".webp"):
                        await self.bot_instance.send_photo(
                            chat_id=self.owner_id, photo=fh, caption=caption
                        )
                    elif suffix == ".mp4":
                        await self.bot_instance.send_video(
                            chat_id=self.owner_id, video=fh, caption=caption
                        )
                    else:
                        await self.bot_instance.send_document(
                            chat_id=self.owner_id, document=fh, caption=caption
                        )
            except Exception as e:
                logger.error(f"Ошибка отправки {f.name}: {e}")
                await update.message.reply_text(f"⚠️ Не удалось отправить {f.name}: {e}")

    async def cmd_generate(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Запускает генерацию контента через Claude Tool Use API.
        Пример: /generate пост для Instagram на эту пятницу
        """
        if not self._is_owner(update):
            return

        # Текст после /generate, например "/generate обложка для трека X"
        args_text = " ".join(context.args) if context.args else ""
        request = args_text or "сгенерируй контент по контент-плану на ближайшие задачи"

        await update.message.reply_text(f"⏳ Запускаю генерацию...\nЗапрос: {request}")

        # Запускаем в фоне — бот не ждёт, пользователь получит уведомление когда готово
        asyncio.create_task(
            self._run_generation_and_notify(request)
        )

    async def _run_generation_and_notify(self, request: str):
        """
        Фоновая задача: запускает generate_content(), затем отправляет файлы.
        Не блокирует event loop бота.
        """
        from src.agent.brain import AgentBrain
        brain = AgentBrain(self.settings)

        try:
            agent_text, files = await brain.generate_content(request)

            if agent_text:
                await self.send_notification(self.bot_instance, agent_text)

            if not files:
                await self.send_notification(
                    self.bot_instance, "⚠️ Генерация завершена, но файлы не созданы."
                )
                return

            # Отправляем каждый файл отдельным сообщением
            for file_path in files:
                p = Path(file_path)
                if not p.exists():
                    logger.warning(f"Файл не найден: {file_path}")
                    continue
                await self.send_notification(
                    self.bot_instance,
                    f"✅ {p.name}\nВыложи когда готов.",
                    file_path=file_path,
                )

        except Exception as e:
            logger.error(f"Ошибка генерации: {e}")
            await self.send_notification(
                self.bot_instance, f"⚠️ Ошибка при генерации: {e}"
            )

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Произвольное сообщение от тебя.
        Передаётся агенту как команда в свободной форме.
        Пример: "вот новые фотки, добавь в план на эту пятницу"
        """
        if not self._is_owner(update):
            return

        user_text = update.message.text
        logger.info(f"Команда от владельца: {user_text}")

        await update.message.reply_text(f"Принято: «{user_text}»\nОбрабатываю...")

        from src.agent.brain import AgentBrain
        brain = AgentBrain(self.settings)
        result = await brain.handle_owner_command(user_text)
        for chunk in self._split(result):
            await update.message.reply_text(chunk)

    async def handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Получает фотографии — агент добавляет их в очередь/план."""
        if not self._is_owner(update):
            return
        # Скачиваем наибольшее фото
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        out_dir = Path(self.settings.queue_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        dest = out_dir / f"{photo.file_unique_id}.jpg"
        await file.download_to_drive(str(dest))
        logger.info(f"Фото сохранено: {dest}")

        caption = update.message.caption or ""
        await update.message.reply_text(
            f"Фото сохранено в очередь: {dest.name}\n"
            + (f"Подпись: {caption}" if caption else "Подписи нет.")
        )

    @staticmethod
    def _split(text: str, max_len: int = 4096) -> list[str]:
        """Режет текст на куски ≤ max_len символов, разбивая по переносам строк."""
        if len(text) <= max_len:
            return [text]
        chunks, current = [], []
        current_len = 0
        for line in text.splitlines(keepends=True):
            if current_len + len(line) > max_len:
                if current:
                    chunks.append("".join(current))
                current, current_len = [line], len(line)
            else:
                current.append(line)
                current_len += len(line)
        if current:
            chunks.append("".join(current))
        return chunks

    async def send_notification(self, bot: Bot, text: str, file_path: str = None):
        """
        Агент вызывает этот метод чтобы написать тебе.
        Опционально прикладывает файл (видео, фото, аудио, документ).
        """
        if not file_path:
            for chunk in self._split(text):
                await bot.send_message(chat_id=self.owner_id, text=chunk)
            return

        p = Path(file_path)
        suffix = p.suffix.lower()
        with open(file_path, "rb") as f:
            if suffix in (".jpg", ".jpeg", ".png", ".webp"):
                await bot.send_photo(chat_id=self.owner_id, photo=f, caption=text)
            elif suffix == ".mp4":
                await bot.send_video(chat_id=self.owner_id, video=f, caption=text)
            elif suffix in (".mp3", ".wav", ".ogg", ".flac"):
                await bot.send_audio(chat_id=self.owner_id, audio=f, caption=text)
            else:
                await bot.send_document(chat_id=self.owner_id, document=f, caption=text)


async def start_bot(settings: Settings):
    bot_handler = C0MA103EBot(settings)
    app = Application.builder().token(settings.telegram_token).build()

    # Сохраняем ссылку на Bot для фоновых задач
    bot_handler.bot_instance = app.bot

    app.add_handler(CommandHandler("start", bot_handler.cmd_start))
    app.add_handler(CommandHandler("plan", bot_handler.cmd_plan))
    app.add_handler(CommandHandler("week", bot_handler.cmd_week))
    app.add_handler(CommandHandler("queue", bot_handler.cmd_queue))
    app.add_handler(CommandHandler("generate", bot_handler.cmd_generate))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot_handler.handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, bot_handler.handle_photo))

    logger.info("Telegram-бот запущен")
    async with app:
        await app.start()
        await app.updater.start_polling()
        await asyncio.Event().wait()  # ждём бесконечно, пока не прервут
