"""
Форматирование статей для публикации в Telegram.

Telegram ограничивает длину сообщения 4096 символами.
Форматтер автоматически разбивает дайджест на блоки нужного размера.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from urllib.parse import quote_plus

from models import ProcessedArticle

logger = logging.getLogger(__name__)

# Максимальная длина одного Telegram-сообщения
TELEGRAM_MAX_LENGTH = 4096

# Эмодзи для категорий
CATEGORY_EMOJI: dict[str, str] = {
    "политика": "🏛",
    "экономика": "💼",
    "общество": "👥",
    "происшествия": "🚨",
    "спорт": "⚽",
    "культура": "🎭",
    "технологии": "💻",
    "погода": "🌤",
    "другое": "📰",
}

# Эмодзи для регионов
REGION_EMOJI: dict[str, str] = {
    "valencia": "🟠",  # Цвет Валенсийского сообщества
    "spain": "🇪🇸",
    "international": "🌍",
}

import os as _os

WEBSITE_URL: str = _os.getenv("WEBSITE_URL", "https://valencia-news.vercel.app")


def _get_moscow_time() -> str:
    """Возвращает текущее время по Москве в формате ЧЧ:ММ."""
    from datetime import timedelta
    utc_now = datetime.now(timezone.utc)
    moscow_offset = timedelta(hours=3)
    moscow_time = utc_now + moscow_offset
    return moscow_time.strftime("%H:%M")


def _get_date_str() -> str:
    """Возвращает текущую дату в формате 'ДД месяца'."""
    months = {
        1: "января", 2: "февраля", 3: "марта", 4: "апреля",
        5: "мая", 6: "июня", 7: "июля", 8: "августа",
        9: "сентября", 10: "октября", 11: "ноября", 12: "декабря",
    }
    now = datetime.now(timezone.utc)
    return f"{now.day} {months[now.month]}"


class MessageFormatter:
    """
    Форматирует список статей в сообщения для Telegram.

    Поддерживает два режима: утренний (morning) и вечерний (evening) дайджест.
    """

    def format_digest(
        self,
        articles: list[ProcessedArticle],
        digest_type: str,
    ) -> list[str]:
        """
        Формирует список сообщений для Telegram.

        Args:
            articles: Список обработанных статей (уже отранжированных).
            digest_type: 'morning' или 'evening'.

        Returns:
            Список строк — каждая строка одно Telegram-сообщение (≤4096 символов).
            Первый элемент всегда шапка дайджеста.
        """
        if not articles:
            logger.warning("format_digest вызван с пустым списком статей")
            return [self._build_header(digest_type, 0)]

        # Собираем строки для каждой статьи
        article_blocks = [self.format_article(a) for a in articles]

        # Разбиваем на сообщения, соблюдая лимит длины
        messages = self._pack_into_messages(article_blocks)

        # Вставляем шапку первым сообщением
        header = self._build_header(digest_type, len(articles))
        return [header] + messages

    def format_article(self, article: ProcessedArticle) -> str:
        """
        Форматирует одну статью в блок Telegram MarkdownV2.

        Формат:
            *Заголовок на русском*

            Тизер (1 предложение)
            📍 Место (если есть)

            🟠 Валенсия · [Подробнее →](https://valencia-news.vercel.app)
        """
        region_emoji = REGION_EMOJI.get(article.region.lower(), "🌍")
        region_label = _region_label(article.region)

        display_title = getattr(article, "title_ru", "") or article.title

        # Для Telegram используем teaser_ru, fallback — summary_ru
        teaser = getattr(article, "teaser_ru", "").strip()
        if not teaser:
            teaser = article.summary_ru

        title_escaped = _escape_markdown(display_title)
        teaser_escaped = _escape_markdown(teaser)
        region_escaped = _escape_markdown(region_label)

        location = getattr(article, "location", "")
        location_line = ""
        if location:
            location_escaped = _escape_markdown(location)
            location_line = f"\n📍 {location_escaped}"

        article_url = getattr(article, "url", "") or WEBSITE_URL
        site_link = f"[Подробнее →]({_escape_url(article_url)})"

        block = (
            f"*{title_escaped}*\n"
            f"\n"
            f"{teaser_escaped}"
            f"{location_line}\n"
            f"\n"
            f"{region_emoji} {region_escaped} · {site_link}"
        )

        return block

    def _build_header(self, digest_type: str, article_count: int) -> str:
        """Формирует шапку дайджеста."""
        date_str = _get_date_str()

        if digest_type == "morning":
            emoji = "🇪🇸"
            title = "Испания и Валенсия"
        else:
            emoji = "🌆"
            title = "Испания и Валенсия"

        header = (
            f"{emoji} *{_escape_markdown(title)}* \\| {_escape_markdown(date_str)}\n"
        )
        return header

    def _pack_into_messages(self, blocks: list[str]) -> list[str]:
        """Каждая статья — отдельное сообщение."""
        return [block[:TELEGRAM_MAX_LENGTH] for block in blocks]


def _region_label(region: str) -> str:
    """Возвращает читаемое название региона."""
    labels = {
        "valencia": "Валенсия",
        "spain": "Испания",
        "international": "Международные",
    }
    return labels.get(region.lower(), region.capitalize())


_MD_SPECIAL_RE = re.compile(r'([_*\[\]()~`>#+=|{}.!\-\\])')


def _escape_markdown(text: str) -> str:
    """Экранирует спецсимволы для Telegram MarkdownV2."""
    return _MD_SPECIAL_RE.sub(r'\\\1', text)


def _escape_url(url: str) -> str:
    """
    Экранирует символы в URL для Telegram MarkdownV2 inline-ссылок.

    В URL-части [text](url) нужно экранировать только ')' и '\'.
    """
    return url.replace("\\", "\\\\").replace(")", "\\)")
