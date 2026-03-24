"""
Загрузка конфигурации из .env и config/settings.yaml
"""

import os
import yaml
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    # Telegram
    telegram_token: str
    telegram_owner_id: int  # твой личный chat_id — бот пишет только тебе

    # Anthropic
    anthropic_api_key: str
    claude_model: str

    # Vault (путь на VPS после Syncthing)
    vault_path: str
    content_plan_file: str  # относительно vault_path

    # Генераторы
    replicate_api_key: str   # FLUX.1-dev / Demucs
    fal_api_key: str         # Kling AI (видео)
    suno_api_key: str        # Suno официальный API

    # Пути
    generated_dir: str
    queue_dir: str
    generation_vault_dir: str  # vault/04 - Генерация/ — попадает в Obsidian через Syncthing


def load_settings() -> Settings:
    with open("config/settings.yaml", "r") as f:
        cfg = yaml.safe_load(f)

    return Settings(
        telegram_token=os.getenv("TELEGRAM_TOKEN", ""),
        telegram_owner_id=int(os.getenv("TELEGRAM_OWNER_ID", "0")),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        claude_model=cfg.get("claude_model", "claude-sonnet-4-6"),
        vault_path=cfg.get("vault_path", "/data/vault/C0MA103E"),
        content_plan_file=cfg.get(
            "content_plan_file", "02 - Контент-план/Контент-план — Месяц 1.md"
        ),
        replicate_api_key=os.getenv("REPLICATE_API_KEY", ""),
        fal_api_key=os.getenv("FAL_KEY", ""),
        suno_api_key=os.getenv("SUNO_API_KEY", ""),
        generated_dir=cfg.get("generated_dir", "data/generated"),
        queue_dir=cfg.get("queue_dir", "data/queue"),
        generation_vault_dir=cfg.get("generation_vault_dir", "04 - Генерация"),
    )
