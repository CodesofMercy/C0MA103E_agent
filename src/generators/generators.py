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
    Генерация музыки через официальный Suno API.
    Документация: https://docs.sunoapi.org/

    Стиль C0MA103E: hardstyle, hardbass, witch house, dark industrial.
    При stems=True — Suno возвращает до 12 независимых дорожек (drums, bass, synth, ...).
    Пользователь получает полный микс + стемы для работы в DAW.
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
        Генерирует трек и (при stems=True) скачивает стемы.
        Возвращает список путей: [full_mix.mp3, drums.wav, bass.wav, ...]
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        out_dir = self._make_output_dir(vault_gen_path, task_id)
        saved_files = []

        async with httpx.AsyncClient(timeout=120) as http:
            # 1. Создать генерацию
            logger.info(f"MusicGenerator: Suno API, style={style}, stems={stems}")
            resp = await http.post(
                f"{self.BASE_URL}/music/generate",
                headers=headers,
                json={
                    "prompt": description,
                    "style": style,
                    "instrumental": True,
                    "stems": stems,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            generation_id = data["generation_id"]

            # 2. Ждать завершения (polling)
            for _ in range(60):
                await asyncio.sleep(5)
                status_resp = await http.get(
                    f"{self.BASE_URL}/music/status/{generation_id}",
                    headers=headers,
                )
                status_resp.raise_for_status()
                status = status_resp.json()
                if status.get("status") == "complete":
                    break
                if status.get("status") == "failed":
                    raise RuntimeError(f"Suno генерация провалилась: {status}")
            else:
                raise TimeoutError("Suno: таймаут ожидания генерации (5 мин)")

            # 3. Скачать полный микс
            audio_url = status["audio_url"]
            full_path = out_dir / f"{task_id}_full.mp3"
            audio_resp = await http.get(audio_url, timeout=120)
            audio_resp.raise_for_status()
            full_path.write_bytes(audio_resp.content)
            saved_files.append(str(full_path))
            logger.info(f"Полный микс: {full_path}")

            # 4. Скачать стемы если доступны
            if stems and status.get("stems"):
                for stem_name, stem_url in status["stems"].items():
                    stem_path = out_dir / f"{task_id}_{stem_name}.wav"
                    stem_resp = await http.get(stem_url, timeout=120)
                    stem_resp.raise_for_status()
                    stem_path.write_bytes(stem_resp.content)
                    saved_files.append(str(stem_path))
                    logger.info(f"Стем {stem_name}: {stem_path}")

        prompt_summary = f"{description} | style: {style}"
        self._write_companion_note(
            out_dir, task_id, "Трек", prompt_summary, "Suno API", saved_files
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
