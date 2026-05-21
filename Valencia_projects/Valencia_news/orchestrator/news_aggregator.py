"""
Агрегатор новостей для одного Telegram-канала.

Каждый экземпляр привязан к конкретному каналу (news / events / tourism / gastronomy),
использует соответствующие источники, персону и ID чата.
"""

from __future__ import annotations

import logging
import time as _time
from datetime import datetime, timedelta, timezone
from typing import Optional

from ai.deduplicator import Deduplicator
from ai.gemini_client import GeminiClient
from ai.processor import ArticleProcessor
from ai.quality_checker import filter_articles as quality_filter
from ai.ranker import Ranker
from config import config
from models import ParsedArticle, ProcessedArticle
from notifier.formatter import MessageFormatter
from notifier.publisher import TelegramPublisher, CAPTION_MAX_LENGTH
from orchestrator.channel_config import ChannelConfig
from parsers.base import ParsedArticle as ParserParsedArticle
from parsers.collector import NewsCollector
from sources.registry import get_sources_by_channel
from sources.static_content import (
    StaticContentSource,
    build_gastronomy_sources,
    build_tourism_source,
)
from storage.database import get_session
from storage.models import Article
from storage.repository import ArticleRepository, PublishLogRepository, SourceRepository

logger = logging.getLogger(__name__)


def _parser_to_model(art: ParserParsedArticle) -> ParsedArticle:
    return ParsedArticle(
        url=art.url,
        title=art.title,
        source_name=art.source_name,
        region=art.region,
        published_at=art.published_at or datetime.now(timezone.utc),
        content=art.text,
        image_url=art.image_url,
        language="es",
        event_end_date=getattr(art, "event_end_date", None),
    )


class NewsAggregator:
    """
    Полный пайплайн для одного Telegram-канала:
    Источники → Парсинг → Дедупликация → AI → Ранжирование → Telegram.

    Один экземпляр = один канал. ChannelOrchestrator создаёт по одному
    экземпляру на каждый активный канал.
    """

    def __init__(self, channel_cfg: ChannelConfig, gemini_client: GeminiClient) -> None:
        self._cfg = channel_cfg
        self._collector = NewsCollector()
        self._processor = ArticleProcessor(client=gemini_client)
        self._deduplicator = Deduplicator()
        self._ranker = Ranker()
        self._formatter = MessageFormatter()
        self._publisher = TelegramPublisher(
            bot_token=config.telegram.bot_token,
            channel_id=channel_cfg.chat_id,
        )
        self._static_sources: list[StaticContentSource] = self._build_static_sources()

        logger.info(
            "NewsAggregator[%s] инициализирован → %s",
            channel_cfg.channel,
            channel_cfg.display_name,
        )

    # -------------------------------------------------------------------
    # Публичный API
    # -------------------------------------------------------------------

    def run_digest(self, digest_type: str = "morning") -> None:
        """Полный цикл сбора и публикации дайджеста."""
        logger.info("[%s] === Запуск дайджеста: %s ===", self._cfg.channel, digest_type)
        start = datetime.now(timezone.utc)
        fetched = published = 0
        status = "success"
        error_msg: Optional[str] = None

        try:
            # Шаг 1: Источники
            rss_sources = self._get_or_seed_sources()
            logger.info("[%s] RSS-источников: %d", self._cfg.channel, len(rss_sources))

            # Шаг 2: known_urls (дедупликация)
            known_urls = self._get_known_urls()

            # Шаг 3: Сбор из RSS
            raw: list[ParserParsedArticle] = []
            if rss_sources:
                raw = self._collector.collect(sources=rss_sources, known_urls=known_urls)
            logger.info("[%s] Собрано из RSS: %d", self._cfg.channel, len(raw))

            # Шаг 3.5: Статический контент (туризм/гастрономия)
            static_articles: list[ParsedArticle] = []
            for src in self._static_sources:
                static_articles.extend(src.fetch(known_urls=known_urls, limit=3))
            logger.info("[%s] Статический контент: %d", self._cfg.channel, len(static_articles))

            # Шаг 4: Объединяем и дедуплицируем
            model_articles = [_parser_to_model(a) for a in raw] + static_articles
            unique = self._deduplicator.deduplicate_batch(
                articles=model_articles, known_urls=known_urls
            )
            logger.info("[%s] После дедупликации: %d", self._cfg.channel, len(unique))

            # Шаг 4.5: Фильтр устаревших
            cutoff = datetime.now(timezone.utc) - timedelta(hours=config.max_article_age_hours)
            unique = [a for a in unique if a.published_at is None or a.published_at >= cutoff]
            fetched = len(unique)

            if not unique:
                logger.info("[%s] Нет новых статей.", self._cfg.channel)
                self._log(digest_type, 0, 0, "success")
                return

            # Шаг 5: AI-обработка с персоной канала
            persona = self._cfg.persona_prompt
            if not persona:
                logger.warning(
                    "[%s] Файл персоны не найден: %s",
                    self._cfg.channel,
                    self._cfg.persona_file,
                )
            processed: list[ProcessedArticle] = []
            to_process = unique[:60]
            for article in to_process:
                try:
                    processed.append(self._processor.process_article(article, persona_prompt=persona))
                except Exception as exc:
                    logger.error("[%s] Ошибка AI '%s': %s", self._cfg.channel, article.title[:50], exc)

            logger.info("[%s] AI обработал: %d", self._cfg.channel, len(processed))

            # Шаг 5.5: Фильтры
            processed = [a for a in processed if a.importance_score > 0.05]
            processed = self._deduplicator.deduplicate_by_summary(processed)
            processed = quality_filter(processed, self._cfg.channel)

            # Шаг 6: Ранжирование
            ch = self._cfg.channel
            if ch in ("tourism", "gastronomy"):
                # Для тематических каналов: все статьи по убыванию важности
                top = sorted(processed, key=lambda a: a.importance_score, reverse=True)[:config.max_articles_per_digest]
                logger.info("[%s] Отобрано для публикации: %d (без регионального фильтра)", ch, len(top))
            else:
                top = self._ranker.rank(articles=processed, max_count=config.max_articles_per_digest)
                logger.info("[%s] Отобрано для публикации: %d", ch, len(top))

            if not top:
                self._log(digest_type, fetched, 0, "partial")
                return

            # Шаг 6.5: Сохраняем все прошедшие фильтр статьи в БД для сайта
            # (is_published=False — Telegram не получит, но сайт покажет)
            self._save_website_articles(processed)

            # Шаг 7: Форматирование и публикация топа в Telegram
            messages = self._formatter.format_digest(articles=top, digest_type=digest_type)
            sent_ids = self._publisher.publish_digest(messages=messages, articles=top)
            published = self._save_articles(top, sent_ids[0] if sent_ids else None)

            self._log(digest_type, fetched, published, "success")
            elapsed = (datetime.now(timezone.utc) - start).total_seconds()
            logger.info(
                "[%s] === Дайджест завершён за %.1f с. Опубликовано: %d ===",
                self._cfg.channel, elapsed, published,
            )

        except Exception as exc:
            status = "failed"
            error_msg = str(exc)
            logger.error("[%s] Критическая ошибка: %s", self._cfg.channel, exc, exc_info=True)
            self._log(digest_type, fetched, published, status, error_msg)

    def run_events_digest(self, events_per_run: Optional[int] = None) -> None:
        """
        Публикация событий из афишных источников (по одному сообщению на событие).
        Используется только каналом 'events'.
        """
        if self._cfg.channel != "events":
            logger.warning(
                "[%s] run_events_digest вызван для не-events канала — пропускаем.",
                self._cfg.channel,
            )
            return

        n = events_per_run if events_per_run is not None else config.schedule.events_per_run
        logger.info("[events] === Запуск афиши: %d событий ===", n)
        start = datetime.now(timezone.utc)
        published_count = 0

        try:
            rss_sources = self._get_or_seed_sources()
            known_urls = self._get_known_event_urls()

            raw: list[ParserParsedArticle] = []
            if rss_sources:
                raw = self._collector.collect(sources=rss_sources, known_urls=known_urls)
            logger.info("[events] Собрано событий: %d", len(raw))

            # Кастомные парсеры фильтруют прошедшие даты внутри себя.
            # RSS-источники (Valencia CF, Feria Valencia и др.) могут отдавать вчерашние статьи —
            # отсекаем всё старше 36 часов.
            _EVENTS_CUSTOM_SOURCES = frozenset({
                "Les Arts", "Palau de la Música", "Valencia.es Agenda", "CCCC Exposiciones",
                "Museo Bellas Artes Valencia", "Fundación Bancaja", "IVAM",
            })
            now_utc = datetime.now(timezone.utc)
            cutoff_rss = now_utc - timedelta(hours=36)
            raw = [
                a for a in raw
                if a.source_name in _EVENTS_CUSTOM_SOURCES
                or a.published_at is None
                or a.published_at >= cutoff_rss
            ]
            logger.info("[events] После фильтра устаревших RSS: %d", len(raw))

            # Не публикуем события, до которых больше 30 дней.
            # Для кастомных парсеров published_at = дата события.
            cutoff_future = now_utc + timedelta(days=30)
            raw = [
                a for a in raw
                if a.published_at is None
                or a.published_at <= cutoff_future
            ]
            logger.info("[events] После фильтра дальних событий (>30 дн): %d", len(raw))

            if not raw:
                self._log("events", 0, 0, "success")
                return

            model_articles = [_parser_to_model(a) for a in raw]
            persona = self._cfg.persona_prompt
            if not persona:
                logger.warning(
                    "[%s] Файл персоны не найден: %s",
                    self._cfg.channel,
                    self._cfg.persona_file,
                )

            processed: list[ProcessedArticle] = []
            for article in model_articles:
                try:
                    processed.append(self._processor.process_article(article, persona_prompt=persona))
                except Exception as exc:
                    logger.error("[events] Ошибка AI '%s': %s", article.title[:50], exc)

            processed = [a for a in processed if a.importance_score > 0.05]
            processed = self._deduplicator.deduplicate_by_summary(processed)
            processed = quality_filter(processed, "events")
            top_events = sorted(processed, key=lambda a: a.importance_score, reverse=True)[:n]
            logger.info("[events] Отобрано для афиши: %d", len(top_events))

            if not top_events:
                self._log("events", len(raw), 0, "partial")
                return

            for event in top_events:
                try:
                    text = self._formatter.format_article(event)
                    msg_id: Optional[int] = None
                    if event.image_url:
                        msg_id = self._publisher.send_photo(event.image_url, text[:CAPTION_MAX_LENGTH])
                    if msg_id is None:
                        msg_id = self._publisher.send_message(text)
                    if msg_id is not None:
                        published_count += 1
                        self._save_articles([event], message_id_hint=msg_id)
                    _time.sleep(0.5)
                except Exception as exc:
                    logger.error("[events] Ошибка публикации '%s': %s", event.title[:50], exc)

            self._log("events", len(raw), published_count, "success")
            elapsed = (datetime.now(timezone.utc) - start).total_seconds()
            logger.info("[events] === Афиша завершена за %.1f с. Опубликовано: %d ===", elapsed, published_count)

        except Exception as exc:
            logger.error("[events] Критическая ошибка: %s", exc, exc_info=True)
            self._log("events", 0, published_count, "failed", str(exc))

    # -------------------------------------------------------------------
    # Вспомогательные методы
    # -------------------------------------------------------------------

    def _build_static_sources(self) -> list[StaticContentSource]:
        """Создаёт статические источники контента для tourism/gastronomy каналов."""
        channel = self._cfg.channel
        if channel == "tourism":
            return [build_tourism_source(config.data_dir)]
        if channel == "gastronomy":
            return build_gastronomy_sources(config.data_dir)
        return []

    def _get_or_seed_sources(self) -> list[dict]:
        """Возвращает RSS-источники для данного канала, досевает новые из реестра."""
        channel = self._cfg.channel
        with get_session() as session:
            repo = SourceRepository(session)
            channel_sources_dicts = get_sources_by_channel(channel)
            added = repo.seed_sources(channel_sources_dicts)
            if added:
                logger.info("[%s] Добавлено новых источников: %d", channel, added)
            active = repo.get_all_active(channel=channel)
            return [
                {"name": s.name, "feed_url": s.feed_url, "site_url": s.site_url or "", "region": s.region}
                for s in active
            ]

    def _get_known_urls(self) -> set[str]:
        """URL статей данного канала за 7 дней."""
        with get_session() as session:
            return ArticleRepository(session).get_recent_urls(
                hours=24 * 7, channel=self._cfg.channel
            )

    def _get_known_event_urls(self) -> set[str]:
        """URL событий: 3 дня для обычных событий, 30 дней для выставок."""
        # Выставки месяцами остаются актуальными — без длинного окна они
        # будут повторно публиковаться каждые 3 дня весь срок работы.
        _EXHIBITION_SOURCES = [
            "IVAM", "Museo Bellas Artes Valencia",
            "CCCC Exposiciones", "Fundación Bancaja",
        ]
        with get_session() as session:
            repo = ArticleRepository(session)
            recent = repo.get_recent_urls(hours=24 * 3, channel=self._cfg.channel)
            exhibitions = repo.get_recent_urls_for_sources(
                hours=24 * 30,
                source_names=_EXHIBITION_SOURCES,
                channel=self._cfg.channel,
            )
            return recent | exhibitions

    def _processed_to_storage_article(self, art: ProcessedArticle) -> Article:
        return Article(
            url=art.url,
            title=art.title,
            title_ru=art.title_ru,
            teaser_ru=art.teaser_ru,
            original_text=art.content,
            summary_ru=art.summary_ru,
            category=art.category,
            importance_score=art.importance_score,
            source_name=art.source_name,
            source_url=None,
            region=art.region,
            published_at=art.published_at,
            is_published=False,
            image_url=art.image_url,
            channel=self._cfg.channel,
            event_end_date=art.event_end_date,
        )

    def _save_website_articles(self, articles: list[ProcessedArticle]) -> int:
        """Сохраняет все обработанные статьи в БД для сайта (без публикации в Telegram)."""
        count = 0
        with get_session() as session:
            repo = ArticleRepository(session)
            for art in articles:
                try:
                    with session.begin_nested():
                        db_art = self._processed_to_storage_article(art)
                        saved = repo.save_article(db_art)
                        if saved.id is not None:
                            count += 1
                except Exception as exc:
                    logger.error("[%s] Ошибка сохранения для сайта '%s': %s", self._cfg.channel, art.title[:50], exc)
        logger.info("[%s] Сохранено для сайта: %d статей", self._cfg.channel, count)
        return count

    def _save_articles(
        self,
        articles: list[ProcessedArticle],
        message_id_hint: Optional[int],
    ) -> int:
        count = 0
        with get_session() as session:
            repo = ArticleRepository(session)
            for art in articles:
                try:
                    with session.begin_nested():  # savepoint — ошибка одной статьи не откатывает остальные
                        db_art = self._processed_to_storage_article(art)
                        saved = repo.save_article(db_art)
                        if saved.id is not None:
                            repo.mark_published(saved.id, telegram_message_id=message_id_hint)
                            count += 1
                except Exception as exc:
                    logger.error("[%s] Ошибка сохранения '%s': %s", self._cfg.channel, art.title[:50], exc)
        return count

    def _log(
        self,
        digest_type: str,
        fetched: int,
        published: int,
        status: str,
        error_msg: Optional[str] = None,
    ) -> None:
        try:
            with get_session() as session:
                PublishLogRepository(session).create_log(
                    digest_type=f"{self._cfg.channel}:{digest_type}",
                    articles_fetched=fetched,
                    articles_published=published,
                    status=status,
                    error_message=error_msg,
                )
        except Exception as exc:
            logger.error("[%s] Ошибка записи в журнал: %s", self._cfg.channel, exc)
