# C0MA103E Agent — Roadmap

## Phase 1 — MVP ✅ ЗАВЕРШЕНА

**Цель:** бот отвечает на `/start` и `/plan`, читает vault, присылает утренний дейли.

- [x] Структура проекта
- [x] `AgentBrain` — чтение vault + Claude API (AsyncAnthropic, async/await)
- [x] `C0MA103EBot` — Telegram-бот с командами + сплитинг длинных сообщений (≤4096)
- [x] `Scheduler` — утренний дейли в 09:00 Europe/Moscow
- [x] Syncthing Mac ↔ VPS — vault синхронизирован
- [x] Деплой на VPS: Docker + GitHub (`/root/c0ma103e`, контейнер `c0ma103e-agent-1`)
- [x] Workflow: `git push` → VPS `git pull && docker compose up -d --build`
- [x] system_prompt.md загружается из config/prompts/ — Telegram-формат без markdown

## Phase 2 — Генераторы ✅ КОД ГОТОВ / ⚠️ API требуют проверки

**Цель:** агент генерирует изображения, видео и музыку через Claude Tool Use API.
Файлы → `vault/04 - Генерация/` (Syncthing → Obsidian) + немедленно в Telegram.

**Инструменты:**
- Изображения: Replicate FLUX.1-dev (финал) + FLUX.1-schnell (черновик) ✅ работает
- Видео: fal.ai + Kling AI ⏳ не оплачен
- Музыка: sunoapi.org (неофициальный API, официального от Suno нет)
- Стемы любого файла (резерв): Meta Demucs через Replicate

**Что сделано:**
- [x] `generators.py` — ImageGenerator, VideoGenerator, MusicGenerator, StemSeparator
- [x] `brain.py` — `generate_content()` с Claude Tool Use API
- [x] `telegram_bot.py` — `/generate`, `cmd_queue`, сплитинг сообщений ≤4096 символов
- [x] `src/sync/watcher.py` — watchdog на изменения vault (подключён в agent.py)
- [x] `system_prompt.md` — правила генерации промптов C0MA103E
- [x] `settings.py/yaml` — все ключи: replicate, fal, suno

**Статус API:**
- REPLICATE_API_KEY — в .env на VPS ✅
- SUNO_API_KEY — в .env на VPS, эндпоинты исправлены ⚠️ требует тест
- FAL_KEY — ⏳ fal.ai баланс не пополнен, видео недоступно

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
