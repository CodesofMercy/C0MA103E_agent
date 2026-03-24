# C0MA103E Agent — Архитектура

## Схема системы (целевая)

```
Mac (Obsidian vault, ~/Documents/Buisnesses/C0MA103E/)
        ↕  Syncthing (real-time, двусторонний)
VPS  (/data/vault/C0MA103E/)
        ↓
    [Research]     — тренды и новости (Tavily API)
        ↓
    [AgentBrain]   — читает план, принимает решения (Claude API + Tool Use)
        ↓
    [Generators]   — FLUX (фото) / Kling (видео) / Suno (музыка+стемы)
        ↓
    [Approval]     — предложение → inline-кнопки в Telegram → ✅/❌
        ↓
    [Publishers]   — Telegram-канал / YouTube / TikTok
                     (Instagram — инструкция вместо автопоста)
        ↓
    [C0MA103EBot]  — уведомляет, принимает команды, хранит решения
        ↑
        Ты — одобряешь / отклоняешь / присылаешь метрики / даёшь вводные
```

## Компоненты

### `config/`
- `settings.py` — загрузка конфигурации (`.env` + `settings.yaml`)
- `settings.yaml` — не-секретные настройки: модель, пути, расписание

### `src/agent/`
- `brain.py` — `AgentBrain`: читает vault, Claude API + Tool Use, обновляет план, запускает генераторы
- `scheduler.py` — APScheduler: утренний цикл (09:00), вечерний check-in (21:00)

### `src/bot/`
- `telegram_bot.py` — `C0MA103EBot`: команды `/start /plan /week /queue /generate`, inline-кнопки согласования, приём фото/метрик

### `src/generators/`
- `generators.py` — `ImageGenerator` (Replicate/FLUX), `VideoGenerator` (fal.ai/Kling), `MusicGenerator` (Suno + стемы), `StemSeparator` (Demucs)

### `src/sync/`
- `watcher.py` — watchdog за изменениями vault, уведомляет при изменении контент-плана

### `src/publishers/` *(Phase 3)*
- `telegram_channel.py` — постинг в Telegram-канал (бот как админ)
- `youtube.py` — загрузка видео через YouTube Data API v3 (OAuth2)
- `tiktok.py` — загрузка через TikTok Content Posting API

### `src/research/` *(Phase 4)*
- `trends.py` — поиск трендов и новостей через Tavily API

### `src/approval/` *(Phase 3)*
- `flow.py` — state machine: предложение → inline-кнопки → исполнение или инструкция

## Стек

| Компонент       | Технология                                      |
|-----------------|-------------------------------------------------|
| Язык            | Python 3.11+                                    |
| AI-мозг         | Anthropic Claude API (claude-sonnet-4-6) + Tool Use |
| Telegram-бот    | python-telegram-bot 20.x                        |
| Расписание      | APScheduler 3.x (AsyncIOScheduler)              |
| Синхронизация   | Syncthing (Mac ↔ VPS)                           |
| Изображения     | Replicate API (FLUX.1-dev / FLUX.1-schnell)     |
| Видео           | fal.ai (Kling AI v1.6)                          |
| Музыка          | Suno официальный API + до 12 стемов             |
| Стемы (резерв)  | Meta Demucs через Replicate                     |
| Публикация      | YouTube Data API v3, TikTok Content Posting API |
| Тренды          | Tavily API                                      |
| Конфиги         | .env + config/settings.yaml                     |

## Синхронизация vault

```
Mac:  ~/Documents/Buisnesses/C0MA103E/
          ↕  Syncthing (real-time)
VPS:  /data/vault/C0MA103E/
```

Агент читает и пишет `/data/vault/C0MA103E/` на VPS.
Изменения появляются в Obsidian на Mac через ~2-5 секунд.

## Безопасность

- Бот отвечает только `TELEGRAM_OWNER_ID` (проверка в `_is_owner()`)
- Секреты только в `.env`, никогда в git
- `data/generated/` и `data/queue/` в `.gitignore`
