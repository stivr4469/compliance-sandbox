"""
Экспортер данных из SQLite в JSON для сайта-агрегатора.

Вызывается из channel_orchestrator.py после каждого дайджеста.
"""
from __future__ import annotations

import json
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from storage.database import get_session
from storage.models import Article
from storage.repository import ArticleRepository

logger = logging.getLogger(__name__)

CHANNELS = ["news", "events", "tourism", "gastronomy"]
DATA_DIR = Path(__file__).parent / "website" / "public" / "data"


def export_to_website() -> None:
    """Читает из SQLite, пишет JSON в website/public/data/."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    now_utc = datetime.now(timezone.utc)
    today_midnight = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)

    with get_session() as session:
        repo = ArticleRepository(session)
        CHANNEL_LIMITS = {"news": 100, "events": 200}
        for channel in CHANNELS:
            limit = CHANNEL_LIMITS.get(channel, 50)
            if channel == "events":
                articles = repo.get_events_for_export(limit=limit, today_midnight=today_midnight)
            else:
                articles = repo.get_latest_for_export(channel=channel, limit=limit)
            data = {
                "updated_at": now_utc.isoformat(),
                "channel": channel,
                "articles": [_to_dict(a) for a in articles],
            }
            out = DATA_DIR / f"{channel}.json"
            try:
                out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                logger.info("Экспорт %s: %d статей → %s", channel, len(articles), out)
            except OSError as e:
                logger.error("Не удалось записать %s: %s", out, e)
                raise


def git_push_website(commit_message: str = "data: обновление данных сайта") -> None:
    """git add + commit + push для обновления Vercel.

    Пропускает commit если нет изменений в данных.
    Вызывать из корня git-репозитория.
    """
    try:
        subprocess.run(["git", "add", "website/public/data/"], check=True, timeout=30)
        result = subprocess.run(["git", "diff", "--cached", "--quiet"], capture_output=True)
        if result.returncode == 0:
            logger.info("Нет изменений в данных сайта — git push пропущен")
            return
        subprocess.run(["git", "commit", "-m", commit_message], check=True, timeout=30)
        subprocess.run(["git", "push", "origin", "main"], check=True, timeout=60)
        logger.info("Данные сайта обновлены и запушены на Vercel")
    except subprocess.CalledProcessError as exc:
        logger.error("Git операция не удалась: %s (код: %d)", exc.cmd, exc.returncode)
        raise


def _to_dict(a: Article) -> dict[str, object]:
    return {
        "id": a.id,
        "title_ru": a.title_ru or _title_from_summary(a.summary_ru) or a.title,
        "summary_ru": a.summary_ru or "",
        "source_name": a.source_name or "",
        "url": a.url,
        "image_url": a.image_url,
        "category": a.category or "другое",
        "published_at": a.published_at.isoformat() if a.published_at else "",
        "channel": a.channel,
    }


def _title_from_summary(summary: str | None) -> str:
    """Извлекает первое предложение summary_ru как заголовок если title_ru отсутствует."""
    if not summary:
        return ""
    for sep in ('.', '!', '?'):
        idx = summary.find(sep)
        if 20 < idx < 120:
            return summary[:idx + 1].strip()
    return summary[:100].strip()
