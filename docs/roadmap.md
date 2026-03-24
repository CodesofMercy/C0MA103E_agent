# C0MA103E Agent — Roadmap

## Phase 1 — MVP ✅ ЗАВЕРШЕНА

**Цель:** бот отвечает на `/start` и `/plan`, читает vault, присылает утренний дейли.

- [x] Структура проекта
- [x] `AgentBrain` — чтение vault + Claude API
- [x] `C0MA103EBot` — Telegram-бот с командами
- [x] `Scheduler` — утренний дейли в 09:00
- [x] Заполнить `.env` (токены)
- [x] Запустить локально — бот отвечает на `/start`
- [x] Настроить Syncthing Mac ↔ VPS — 4 файла, статус idle
- [x] Задеплоить на VPS (rsync → /opt/C0MA103E-agent)
- [x] Настроить systemd-сервис (автозапуск, Restart=always)
- [x] Часовой пояс Europe/Moscow (UTC+3) — дейли в 09:00 МСК = 11:00 ТШК
- [x] system_prompt.md загружается из config/prompts/ — формат Telegram чистый

## Phase 2 — Генераторы 🔄 В ПРОЦЕССЕ

**Цель:** агент генерирует изображения, видео и музыку через Claude Tool Use API.
Файлы → `vault/04 - Генерация/` (Syncthing → Obsidian) + немедленно в Telegram.

**Инструменты (финальный выбор):**
- Изображения: Replicate FLUX.1-dev (финал) + FLUX.1-schnell (черновик)
- Видео: fal.ai + Kling AI (вместо Runway — стабильный SDK, лучший price/quality)
- Музыка: Suno официальный API — полный микс + до 12 стемов (drums, bass, synth...)
- Стемы любого файла (резерв): Meta Demucs через Replicate

**Что сделано:**
- [x] `generators.py` — реализованы ImageGenerator, VideoGenerator, MusicGenerator, StemSeparator
- [x] `brain.py` — `generate_content()` с Claude Tool Use API (агент сам решает что генерировать)
- [x] `telegram_bot.py` — `/generate` запускает фоновую задачу, `cmd_queue` отправляет файлы
- [x] `system_prompt.md` — правила генерации промптов в стиле C0MA103E
- [x] `settings.py/yaml` — добавлены `fal_api_key`, `suno_api_key`, `generation_vault_dir`
- [x] `requirements.txt` — добавлен `fal-client`

**Осталось (деплой на VPS):**
- [x] Добавить `REPLICATE_API_KEY` в `.env` — готово
- [x] Добавить `SUNO_API_KEY` в `.env` — готово
- [ ] Добавить `FAL_KEY` в `.env` — ⏳ fal.ai не оплачен, видео временно недоступно
- [ ] `pip install fal-client` на VPS
- [ ] Создать папку `vault/04 - Генерация/` (создаётся автоматически при первой генерации)
- [ ] Проверить `/generate обложка для ближайшего трека`
- [ ] Watchdog на изменения vault (src/sync/watcher.py) — подключить в main.py

## Phase 3 — Автопубликация

**Цель:** агент сам публикует на платформы где это возможно, на остальных — инструктирует.

**Принцип:** агент предлагает → ты одобряешь inline-кнопками в Telegram → агент публикует / отправляет инструкцию.

| Платформа | Автопостинг | Как |
|-----------|-------------|-----|
| Telegram-канал | ✅ Легко | Бот — админ канала |
| YouTube | ✅ Возможно | YouTube Data API v3 (OAuth2) |
| TikTok | ⚠️ Сложно | TikTok Content Posting API (нужна верификация приложения) |
| Instagram | ❌ | API закрыт — бот присылает инструкцию + файл |

**Что нужно реализовать:**
- [ ] `src/publishers/telegram_channel.py` — постинг в канал (бот уже есть, нужен CHANNEL_ID)
- [ ] `src/publishers/youtube.py` — загрузка видео через YouTube Data API v3
  - Библиотека: `google-api-python-client` + `google-auth-oauthlib`
  - Ключи: OAuth2 (одноразовая настройка), потом auto-refresh токен
- [ ] `src/publishers/tiktok.py` — загрузка через TikTok Content Posting API
  - Предупреждение: требует верификации TikTok Developer App
- [ ] `src/approval/` — flow "предложение → кнопки ✅/❌ → исполнение"
  - Telegram InlineKeyboardMarkup (уже в python-telegram-bot)
  - `CallbackQueryHandler` для обработки ответов
  - Хранение ожидающих решений (in-memory dict или файл в vault)

**Новые настройки (.env):**
```
TELEGRAM_CHANNEL_ID=@c0ma103e  # или числовой ID
YOUTUBE_CLIENT_SECRET=...      # JSON файл от Google Cloud Console
TIKTOK_CLIENT_KEY=...
TIKTOK_CLIENT_SECRET=...
```

## Phase 4 — Ежедневный цикл (Daily Loop)

**Цель:** агент работает каждый день, не раз в неделю.

**Текущее:** утренний дейли в 09:00 — только читает план и сообщает.
**Нужно:** полный цикл каждый день:

```
09:00 — Агент анализирует план + тренды → генерирует контент дня
        → присылает на согласование (✅/❌)
После одобрения → публикует / инструктирует
Вечер (21:00) — check-in: "Задачи дня выполнены?"
                → если нет → предлагает перенести / объяснить почему
```

**Что нужно реализовать:**
- [ ] `src/research/trends.py` — поиск трендов и новостей
  - Tavily API (`tavily-python`) — лучший для AI-агентов, $0.01/запрос
  - Или Brave Search API как альтернатива
  - Ключи: `TAVILY_API_KEY`
- [ ] Расширить `scheduler.py`:
  - `daily_content_loop()` — утром: исследование + генерация + запрос согласования
  - `evening_checkin()` — вечером: "выполнено?"
  - Убрать `weekly_plan` — заменить на ежедневный цикл

## Phase 5 — Аналитика

**Цель:** агент знает как работает контент, учитывает это в следующих решениях.

**Модель:** ты сам присылаешь метрики → агент сохраняет → учитывает при планировании.
Пример: "вчерашний рилс набрал 4к, трек в сторис — 900"

- [ ] `vault/05 - Аналитика/metrics.md` — файл куда агент пишет метрики
- [ ] `brain.py` — метод `log_metrics(text)`: парсит свободный текст → сохраняет в vault
- [ ] Claude учитывает metrics.md при генерации плана и выборе форматов
- [ ] YouTube Analytics API (часть google-api-python-client) — автосбор если подключён YouTube
- [ ] TikTok Analytics API — автосбор если подключён TikTok

## Phase 6 — Музыкальный workflow

- [x] Suno официальный API — реализован в Phase 2
- [ ] Шаблоны описаний треков для разных жанров (hardstyle vs witch house vs dark industrial)
- [ ] Интеграция стемов с DAW через vault (файлы появляются прямо в Obsidian)
- [ ] Автозагрузка трека на YouTube / SoundCloud после одобрения

## Что НЕ автоматизируется (принципиально)

- Публикация в Instagram (API закрыт)
- Финальный монтаж видео
- Прослушивание и одобрение треков
- Живые съёмки и фотосессии
- Решения об образе и анонимности
