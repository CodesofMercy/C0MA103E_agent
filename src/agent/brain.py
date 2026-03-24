"""
Мозг агента.
Читает контент-план из vault, анализирует через Claude API,
возвращает структурированные задачи и запускает генераторы через Tool Use.
"""

import logging
import re
from datetime import date
from pathlib import Path
from anthropic import AsyncAnthropic
from config.settings import Settings

logger = logging.getLogger(__name__)

_FALLBACK_PROMPT = (
    "Ты — менеджер музыкального проекта C0MA103E. "
    "Анализируй контент-план и выдавай конкретные задачи. "
    "Отвечай кратко, по делу, в формате Telegram-сообщения. "
    "Используй эмодзи умеренно. Язык — русский."
)

# Инструменты, которые Claude может вызывать для генерации контента
GENERATION_TOOLS = [
    {
        "name": "generate_image",
        "description": (
            "Генерирует изображение для публикации C0MA103E. "
            "Промпт пиши на английском в стиле dark industrial / dystopian signal. "
            "Никогда не включай лица, людей, узнаваемые детали."
        ),
        "input_schema": {
            "type": "object",
            "required": ["prompt", "format", "task_id"],
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Промпт на английском для FLUX",
                },
                "format": {
                    "type": "string",
                    "enum": ["post", "story", "cover"],
                    "description": "post=1:1 лента, story=9:16 сторис, cover=1:1 обложка",
                },
                "task_id": {
                    "type": "string",
                    "description": "Slug задачи из контент-плана, напр. post-ig-2024-03-24",
                },
                "draft": {
                    "type": "boolean",
                    "description": "true=черновик (FLUX-schnell, дёшево), false=финал (FLUX-dev)",
                },
            },
        },
    },
    {
        "name": "generate_video",
        "description": (
            "Генерирует короткое видео через Kling AI (fal.ai). "
            "Используй для Reels / сторис в стиле C0MA103E."
        ),
        "input_schema": {
            "type": "object",
            "required": ["prompt", "task_id"],
            "properties": {
                "prompt": {"type": "string"},
                "duration": {
                    "type": "integer",
                    "enum": [5, 10],
                    "description": "Длина видео в секундах",
                },
                "task_id": {"type": "string"},
            },
        },
    },
    {
        "name": "generate_music",
        "description": (
            "Генерирует музыкальный трек через официальный Suno API. "
            "Всегда запрашивай стемы — пользователю нужны отдельные дорожки для DAW."
        ),
        "input_schema": {
            "type": "object",
            "required": ["description", "style", "task_id"],
            "properties": {
                "description": {
                    "type": "string",
                    "description": "Текстовое описание трека",
                },
                "style": {
                    "type": "string",
                    "description": "Жанр и стиль, напр. 'hardstyle dark industrial cold mechanical'",
                },
                "stems": {
                    "type": "boolean",
                    "description": "Запросить отдельные стемы (drums, bass, synth...)",
                },
                "task_id": {"type": "string"},
            },
        },
    },
]


def _load_system_prompt() -> str:
    path = Path("config/prompts/system_prompt.md")
    if path.exists():
        return path.read_text(encoding="utf-8")
    logger.warning("system_prompt.md не найден, используется fallback")
    return _FALLBACK_PROMPT


class AgentBrain:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.vault = Path(settings.vault_path)
        self.system_prompt = _load_system_prompt()

    def read_content_plan(self) -> str:
        """Читает markdown-файл контент-плана из vault."""
        plan_path = self.vault / self.settings.content_plan_file
        if not plan_path.exists():
            logger.warning(f"Контент-план не найден: {plan_path}")
            return "(контент-план не найден)"
        return plan_path.read_text(encoding="utf-8")

    def read_concept(self) -> str:
        """Читает файл концепции персонажа."""
        concept_path = self.vault / "01 - Концепция и Лор" / "КОНЦЕПЦИЯ — C0MA103E.md"
        if not concept_path.exists():
            return ""
        return concept_path.read_text(encoding="utf-8")

    def _vault_gen_path(self) -> Path:
        """Путь к папке генерации в vault (попадает в Obsidian через Syncthing)."""
        p = self.vault / self.settings.generation_vault_dir
        p.mkdir(parents=True, exist_ok=True)
        return p

    async def get_today_tasks(self) -> str:
        """
        Спрашивает Claude: что нужно сделать сегодня по контент-плану?
        Возвращает текст для Telegram.
        """
        plan = self.read_content_plan()
        today = date.today().strftime("%d.%m.%Y")

        try:
            response = await self.client.messages.create(
                model=self.settings.claude_model,
                max_tokens=1000,
                system=self.system_prompt,
                messages=[{
                    "role": "user",
                    "content": (
                        f"Сегодня: {today}\n\n"
                        f"Контент-план:\n{plan}\n\n"
                        "Что нужно сделать сегодня? Что нужно подготовить заранее? "
                        "Если сегодня нет задач — что ближайшее?"
                    ),
                }],
            )
            return response.content[0].text
        except Exception as e:
            logger.error(f"Ошибка Claude API (get_today_tasks): {e}")
            return f"⚠️ Не удалось получить задачи от Claude: {e}"

    async def get_week_tasks(self) -> str:
        """Возвращает задачи на текущую неделю."""
        plan = self.read_content_plan()
        today = date.today().strftime("%d.%m.%Y")

        try:
            response = await self.client.messages.create(
                model=self.settings.claude_model,
                max_tokens=1500,
                system=self.system_prompt,
                messages=[{
                    "role": "user",
                    "content": (
                        f"Сегодня: {today}\n\n"
                        f"Контент-план:\n{plan}\n\n"
                        "Дай обзор задач на эту неделю. "
                        "Что нужно создать, что опубликовать, что подготовить?"
                    ),
                }],
            )
            return response.content[0].text
        except Exception as e:
            logger.error(f"Ошибка Claude API (get_week_tasks): {e}")
            return f"⚠️ Не удалось получить план недели от Claude: {e}"

    async def handle_owner_command(self, text: str, attachments: list = None) -> str:
        """
        Обрабатывает произвольную команду от владельца.
        Например: "вот фотки с фотосессии, добавь в план на эту пятницу"
        Возвращает ответ + при необходимости обновляет файлы в vault.
        """
        plan = self.read_content_plan()
        concept = self.read_concept()

        attachment_info = ""
        if attachments:
            attachment_info = f"\nВладелец прислал {len(attachments)} файл(ов)."

        try:
            response = await self.client.messages.create(
                model=self.settings.claude_model,
                max_tokens=2000,
                system=(
                    "Ты — менеджер музыкального проекта C0MA103E. "
                    "Помогаешь владельцу управлять контент-планом и проектом. "
                    "Когда нужно обновить план — возвращай обновлённый markdown целиком "
                    "внутри тегов <updated_plan>...</updated_plan>. "
                    "Язык ответа — русский."
                ),
                messages=[{
                    "role": "user",
                    "content": (
                        f"Концепция проекта:\n{concept}\n\n"
                        f"Текущий контент-план:\n{plan}\n\n"
                        f"Команда владельца: {text}{attachment_info}\n\n"
                        "Что делаем? Если нужно обновить план — верни обновлённую версию."
                    ),
                }],
            )
        except Exception as e:
            logger.error(f"Ошибка Claude API (handle_owner_command): {e}")
            return f"⚠️ Не удалось обработать команду: {e}"

        result = response.content[0].text

        # Если агент вернул обновлённый план — сохраняем в vault
        updated = re.search(r"<updated_plan>(.*?)</updated_plan>", result, re.DOTALL)
        if updated:
            self._save_content_plan(updated.group(1).strip())
            logger.info("Контент-план обновлён агентом")

        return result

    async def generate_content(self, user_request: str) -> tuple[str, list[str]]:
        """
        Claude анализирует запрос и контент-план, затем вызывает нужные генераторы
        через Tool Use API. Возвращает (ответ_агента, список_сгенерированных_файлов).

        Пример запросов:
        - "сгенерируй обложку для трека"
        - "сделай пост для Instagram на эту пятницу"
        - "создай трек в стиле hardbass для следующего релиза"
        """
        plan = self.read_content_plan()
        today = date.today().strftime("%d.%m.%Y")

        messages = [{
            "role": "user",
            "content": (
                f"Сегодня: {today}\n\n"
                f"Контент-план:\n{plan}\n\n"
                f"Запрос: {user_request}\n\n"
                "ОБЯЗАТЕЛЬНО вызови инструменты generate_image / generate_video / generate_music — "
                "не отвечай текстом, не давай инструкции, не объясняй. "
                "Просто вызови нужный инструмент прямо сейчас."
            ),
        }]

        all_files: list[str] = []
        agent_text = ""

        # Agentic loop: Claude может вызвать несколько инструментов за один раз
        while True:
            response = await self.client.messages.create(
                model=self.settings.claude_model,
                max_tokens=2000,
                system=self.system_prompt,
                tools=GENERATION_TOOLS,
                messages=messages,
            )

            # Собираем текст из ответа
            for block in response.content:
                if hasattr(block, "text"):
                    agent_text += block.text

            # Если нет tool_use — Claude закончил
            if response.stop_reason != "tool_use":
                break

            # Обрабатываем все вызовы инструментов
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                result_content, files = await self._handle_tool_call(
                    block.name, block.input
                )
                all_files.extend(files)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result_content,
                })

            # Добавляем ответ Claude и результаты инструментов в историю
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

        return agent_text.strip(), all_files

    async def _handle_tool_call(
        self, tool_name: str, tool_input: dict
    ) -> tuple[str, list[str]]:
        """
        Диспетчер вызовов инструментов.
        Возвращает (строка_результата_для_Claude, список_файлов).
        """
        from src.generators.generators import ImageGenerator, VideoGenerator, MusicGenerator

        vault_gen = self._vault_gen_path()

        try:
            if tool_name == "generate_image":
                gen = ImageGenerator(self.settings.replicate_api_key)
                files = await gen.generate(
                    prompt=tool_input["prompt"],
                    task_id=tool_input["task_id"],
                    vault_gen_path=vault_gen,
                    fmt=tool_input.get("format", "post"),
                    draft=tool_input.get("draft", False),
                )
                return f"Изображение создано: {files[0]}", files

            elif tool_name == "generate_video":
                gen = VideoGenerator(self.settings.fal_api_key)
                files = await gen.generate(
                    prompt=tool_input["prompt"],
                    task_id=tool_input["task_id"],
                    vault_gen_path=vault_gen,
                    duration=tool_input.get("duration", 5),
                )
                return f"Видео создано: {files[0]}", files

            elif tool_name == "generate_music":
                gen = MusicGenerator(self.settings.suno_api_key)
                files = await gen.generate(
                    description=tool_input["description"],
                    style=tool_input["style"],
                    task_id=tool_input["task_id"],
                    vault_gen_path=vault_gen,
                    stems=tool_input.get("stems", True),
                )
                stems_count = len(files) - 1
                return f"Трек создан: {files[0]}, стемов: {stems_count}", files

            else:
                return f"Неизвестный инструмент: {tool_name}", []

        except Exception as e:
            logger.error(f"Ошибка инструмента {tool_name}: {e}")
            return f"Ошибка при генерации ({tool_name}): {e}", []

    def _save_content_plan(self, content: str):
        """Сохраняет обновлённый план в vault (Syncthing донесёт до Mac)."""
        plan_path = self.vault / self.settings.content_plan_file
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text(content, encoding="utf-8")
        logger.info(f"План сохранён: {plan_path}")
