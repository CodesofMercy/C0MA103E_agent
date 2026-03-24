"""
Генераторы контента для C0MA103E.

Стек Phase 2:
- ImageGenerator  : Replicate API (FLUX.1-dev для финала, FLUX.1-schnell для черновиков)
- VideoGenerator  : fal.ai (Kling AI)
- MusicGenerator  : Suno официальный API (watermark-free, 12 стемов)
- StemSeparator   : Meta Demucs через Replicate (резерв — разделить любой аудиофайл)

Все генераторы асинхронные, возвращают список сохранённых путей.
"""

import asyncio
import logging
import httpx
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)


class GeneratorBase:
    """Базовый класс: создаёт папку вывода и companion .md-заметку для Obsidian."""

    def _make_output_dir(self, vault_gen_path: Path, task_id: str) -> Path:
        today = date.today().isoformat()
        out = vault_gen_path / today / task_id
        out.mkdir(parents=True, exist_ok=True)
        return out

    def _write_companion_note(
        self,
        out_dir: Path,
        task_id: str,
        kind: str,
        prompt: str,
        model: str,
        files: list[str],
    ):
        """
        Создаёт .md-заметку рядом с файлами.
        Obsidian рендерит ![[file.jpg]] / ![[file.mp3]] прямо в заметке.
        """
        embeds = "\n".join(f"![[{Path(f).name}]]" for f in files)
        content = (
            f"# {kind}: {task_id}\n"
            f"Дата: {date.today().isoformat()}\n"
            f"Задача: {task_id}\n"
            f"Промпт: {prompt}\n"
            f"Модель: {model}\n"
            f"Статус: ожидает одобрения\n\n"
            f"{embeds}\n"
        )
        note_path = out_dir / f"{task_id}.md"
        note_path.write_text(content, encoding="utf-8")
        logger.info(f"Companion note: {note_path}")


class ImageGenerator(GeneratorBase):
    """
    Генерация изображений через Replicate API.

    Модели:
    - FLUX.1-dev    (black-forest-labs/flux-dev)   — финальное качество
    - FLUX.1-schnell (black-forest-labs/flux-schnell) — черновик, быстро и дёшево
    """

    MODEL_DEV = "black-forest-labs/flux-dev"
    MODEL_SCHNELL = "black-forest-labs/flux-schnell"

    FORMAT_SIZES = {
        "post": (1024, 1024),    # 1:1 лента Instagram
        "story": (576, 1024),    # 9:16 сторис
        "cover": (1024, 1024),   # 1:1 обложка альбома
    }

    def __init__(self, api_key: str):
        self.api_key = api_key

    async def generate(
        self,
        prompt: str,
        task_id: str,
        vault_gen_path: Path,
        fmt: str = "post",
        draft: bool = False,
    ) -> list[str]:
        """
        Генерирует изображение и сохраняет в vault_gen_path/[дата]/[task_id]/.

        Возвращает список путей к сохранённым файлам (jpg).
        """
        import replicate

        model = self.MODEL_SCHNELL if draft else self.MODEL_DEV
        width, height = self.FORMAT_SIZES.get(fmt, (1024, 1024))
        suffix = "_draft" if draft else ""
        filename = f"{task_id}{suffix}.jpg"

        out_dir = self._make_output_dir(vault_gen_path, task_id)
        out_path = out_dir / filename

        logger.info(f"ImageGenerator: {model}, prompt={prompt[:60]}...")

        client = replicate.Client(api_token=self.api_key)
        output = await asyncio.to_thread(
            client.run,
            model,
            input={
                "prompt": prompt,
                "width": width,
                "height": height,
                "num_outputs": 1,
                "output_format": "jpg",
                "output_quality": 90,
            },
        )

        # output — список URL-объектов от Replicate
        image_url = str(output[0])
        async with httpx.AsyncClient() as http:
            resp = await http.get(image_url, timeout=60)
            resp.raise_for_status()
            out_path.write_bytes(resp.content)

        logger.info(f"Изображение сохранено: {out_path}")
        self._write_companion_note(
            out_dir, task_id, "Изображение", prompt, model, [str(out_path)]
        )
        return [str(out_path)]


class VideoGenerator(GeneratorBase):
    """
    Генерация видео через fal.ai (Kling AI).

    Модель: fal-ai/kling-video/v1.6/standard/text-to-video
    Документация: https://fal.ai/models/fal-ai/kling-video
    """

    MODEL = "fal-ai/kling-video/v1.6/standard/text-to-video"

    def __init__(self, api_key: str):
        self.api_key = api_key

    async def generate(
        self,
        prompt: str,
        task_id: str,
        vault_gen_path: Path,
        duration: int = 5,
    ) -> list[str]:
        """
        Генерирует видео и сохраняет в vault.
        duration: 5 или 10 секунд.
        Возвращает список путей к файлам.
        """
        import fal_client

        out_dir = self._make_output_dir(vault_gen_path, task_id)
        filename = f"{task_id}.mp4"
        out_path = out_dir / filename

        logger.info(f"VideoGenerator: Kling AI, {duration}s, prompt={prompt[:60]}...")

        result = await asyncio.to_thread(
            fal_client.run,
            self.MODEL,
            arguments={
                "prompt": prompt,
                "duration": str(duration),
                "aspect_ratio": "9:16",
            },
        )

        video_url = result["video"]["url"]
        async with httpx.AsyncClient() as http:
            resp = await http.get(video_url, timeout=300)
            resp.raise_for_status()
            out_path.write_bytes(resp.content)

        logger.info(f"Видео сохранено: {out_path}")
        self._write_companion_note(
            out_dir, task_id, "Видео", prompt, self.MODEL, [str(out_path)]
        )
        return [str(out_path)]


class MusicGenerator(GeneratorBase):
    """
    Генерация музыки через sunoapi.org.
    Документация: https://docs.sunoapi.org/

    POST /api/v1/generate — создаёт задачу, возвращает taskId
    GET  /api/v1/generate/record-info?taskId=... — polling статуса
    Статусы: PENDING → GENERATING → SUCCESS / FAILED
    API генерирует 2 варианта трека на каждый запрос.
    Стемы не поддерживаются — только полный микс.
    """

    BASE_URL = "https://api.sunoapi.org/api/v1"

    def __init__(self, api_key: str):
        self.api_key = api_key

    async def generate(
        self,
        description: str,
        style: str,
        task_id: str,
        vault_gen_path: Path,
        stems: bool = True,
    ) -> list[str]:
        """
        Генерирует 2 варианта трека (sunoapi.org всегда возвращает пару).
        Возвращает список путей к .mp3 файлам.
        stems игнорируется — sunoapi.org не поддерживает стемы.
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        out_dir = self._make_output_dir(vault_gen_path, task_id)
        saved_files = []

        # title обязателен в customMode=True, берём из task_id
        title = task_id.replace("-", " ").replace("_", " ")[:80]

        async with httpx.AsyncClient(timeout=300) as http:
            # 1. Создать генерацию — POST /api/v1/generate
            # customMode=True нужен чтобы передать style отдельно от prompt
            # Обязательные поля: customMode, instrumental, callBackUrl, model,
            #                    prompt, style, title (в customMode)
            logger.info(f"MusicGenerator: Suno API, style={style}")
            resp = await http.post(
                f"{self.BASE_URL}/generate",
                headers=headers,
                json={
                    "customMode": True,
                    "model": "V4",
                    "prompt": description[:3000],
                    "style": style[:200],
                    "title": title,
                    "instrumental": True,
                    "callBackUrl": "https://httpbin.org/post",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            logger.info(f"Suno generate response: {data}")

            if data.get("code") != 200 or not data.get("data"):
                raise RuntimeError(f"Suno: ошибка при создании задачи: {data}")

            suno_task_id = data["data"]["taskId"]
            logger.info(f"Suno: задача создана, taskId={suno_task_id}")

            # 2. Polling — GET /api/v1/generate/record-info?taskId=...
            # Статусы: PENDING, GENERATING, SUCCESS, FAILED
            # audio_url готов через ~2-3 мин после старта
            songs = None
            for attempt in range(72):  # до 6 минут (72 × 5s)
                await asyncio.sleep(5)
                status_resp = await http.get(
                    f"{self.BASE_URL}/generate/record-info",
                    headers=headers,
                    params={"taskId": suno_task_id},
                )
                status_resp.raise_for_status()
                status_data = status_resp.json()
                status = status_data.get("data", {}).get("status")
                logger.info(f"Suno polling [{attempt+1}]: status={status}")

                if status == "SUCCESS":
                    songs = status_data["data"]["response"]["data"]
                    break
                if status == "FAILED":
                    raise RuntimeError(f"Suno генерация провалилась: {status_data}")
            else:
                raise TimeoutError("Suno: таймаут ожидания генерации (6 мин)")

            # 3. Скачать оба варианта трека
            for i, song in enumerate(songs[:2]):
                audio_url = song.get("audio_url") or song.get("stream_audio_url")
                if not audio_url:
                    logger.warning(f"Suno: нет audio_url для варианта {i+1}")
                    continue
                suffix = f"_v{i + 1}"
                song_path = out_dir / f"{task_id}{suffix}.mp3"
                audio_resp = await http.get(audio_url, timeout=120)
                audio_resp.raise_for_status()
                song_path.write_bytes(audio_resp.content)
                saved_files.append(str(song_path))
                logger.info(f"Трек вариант {i+1}: {song_path}")

        prompt_summary = f"{description} | style: {style}"
        self._write_companion_note(
            out_dir, task_id, "Трек", prompt_summary, "Suno V4", saved_files
        )
        return saved_files


class StemSeparator(GeneratorBase):
    """
    Разделение любого аудиофайла на стемы через Meta Demucs (Replicate).
    Используется как резерв — когда нужно разделить внешний файл, не только Suno.

    Модель: cjwbw/demucs — 4 стема: vocals, drums, bass, other
    """

    MODEL = "cjwbw/demucs"

    def __init__(self, replicate_api_key: str):
        self.api_key = replicate_api_key

    async def separate(
        self,
        audio_path: str,
        task_id: str,
        vault_gen_path: Path,
    ) -> list[str]:
        """
        Разделяет аудиофайл на стемы.
        audio_path — путь к .mp3/.wav на диске.
        Возвращает список путей к стемам.
        """
        import replicate

        out_dir = self._make_output_dir(vault_gen_path, f"{task_id}_stems")
        saved_files = []

        logger.info(f"StemSeparator: Demucs, input={audio_path}")

        client = replicate.Client(api_token=self.api_key)

        with open(audio_path, "rb") as f:
            result = await asyncio.to_thread(
                client.run,
                self.MODEL,
                input={"audio": f, "model": "htdemucs"},
            )

        async with httpx.AsyncClient(timeout=300) as http:
            for stem_name, stem_url in result.items():
                stem_path = out_dir / f"{task_id}_{stem_name}.wav"
                resp = await http.get(str(stem_url), timeout=120)
                resp.raise_for_status()
                stem_path.write_bytes(resp.content)
                saved_files.append(str(stem_path))
                logger.info(f"Demucs стем {stem_name}: {stem_path}")

        return saved_files
