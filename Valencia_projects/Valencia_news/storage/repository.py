"""
Репозитории для работы с данными в БД.
Инкапсулируют все запросы, бизнес-логика не знает о SQLAlchemy напрямую.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from storage.models import Article, PublishLog, Source

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ArticleRepository
# ---------------------------------------------------------------------------

class ArticleRepository:
    """Операции с таблицей articles."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def save_article(self, article: Article) -> Article:
        """
        Сохраняет статью в БД.
        Если статья с таким URL уже существует — возвращает существующую.
        """
        existing = self.get_by_url(article.url)
        if existing is not None:
            logger.debug("Статья уже существует: %s", article.url)
            return existing

        self._session.add(article)
        self._session.flush()  # Получаем id без полного commit
        logger.debug("Сохранена новая статья id=%s: %s", article.id, article.title)
        return article

    def get_by_url(self, url: str) -> Optional[Article]:
        """Возвращает статью по URL или None, если не найдена."""
        stmt = select(Article).where(Article.url == url)
        return self._session.scalars(stmt).first()

    def get_unpublished(self, limit: int = 20) -> list[Article]:
        """
        Возвращает неопубликованные статьи, отсортированные по важности (по убыванию).
        Используется при формировании дайджеста.
        """
        stmt = (
            select(Article)
            .where(Article.is_published.is_(False))
            .where(Article.summary_ru.isnot(None))  # Только те, у кого есть саммари
            .order_by(Article.importance_score.desc().nulls_last(), Article.published_at.desc())
            .limit(limit)
        )
        return list(self._session.scalars(stmt).all())

    def get_recent_urls(self, hours: int = 24, channel: str | None = None) -> set[str]:
        """
        Возвращает множество URL статей, полученных за последние N часов.
        Используется для быстрой проверки дубликатов при парсинге.
        """
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        stmt = select(Article.url).where(Article.fetched_at >= since)
        if channel is not None:
            stmt = stmt.where(Article.channel == channel)
        rows = self._session.scalars(stmt).all()
        return set(rows)

    def get_recent_urls_for_sources(
        self,
        hours: int,
        source_names: list[str],
        channel: str | None = None,
    ) -> set[str]:
        """URLs для конкретных источников за последние N часов."""
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        stmt = select(Article.url).where(
            Article.fetched_at >= since,
            Article.source_name.in_(source_names),
        )
        if channel is not None:
            stmt = stmt.where(Article.channel == channel)
        return set(self._session.scalars(stmt).all())

    def get_latest_for_export(
        self,
        channel: str,
        limit: int = 50,
        min_published_at: Optional[datetime] = None,
    ) -> list[Article]:
        """Последние N статей канала с непустым summary_ru, для JSON-экспорта.

        min_published_at: если указан, исключает статьи с published_at < порога
        (используется для канала events чтобы не показывать прошедшие события).
        """
        conditions = [
            Article.channel == channel,
            Article.summary_ru.isnot(None),
            Article.summary_ru != "",
        ]
        if min_published_at is not None:
            conditions.append(
                (Article.published_at >= min_published_at) | Article.published_at.is_(None)
            )
        stmt = (
            select(Article)
            .where(*conditions)
            .order_by(Article.published_at.desc())
            .limit(limit)
        )
        return list(self._session.scalars(stmt).all())

    def get_events_for_export(self, limit: int = 200, today_midnight: Optional[datetime] = None) -> list[Article]:
        """События для сайта: только те, что ещё не закончились.

        Логика фильтрации:
        - event_end_date заполнена → показываем если event_end_date >= today_midnight
        - event_end_date не заполнена → показываем если published_at >= today_midnight
          (для старых записей без event_end_date, принимаем published_at как дату события)
        """
        from sqlalchemy import or_, and_
        cutoff = today_midnight
        conditions = [
            Article.channel == "events",
            Article.summary_ru.isnot(None),
            Article.summary_ru != "",
        ]
        if cutoff is not None:
            conditions.append(
                or_(
                    and_(Article.event_end_date.isnot(None), Article.event_end_date >= cutoff),
                    and_(Article.event_end_date.is_(None), Article.published_at >= cutoff),
                    and_(Article.event_end_date.is_(None), Article.published_at.is_(None)),
                )
            )
        stmt = (
            select(Article)
            .where(*conditions)
            .order_by(Article.published_at.desc())
            .limit(limit)
        )
        return list(self._session.scalars(stmt).all())

    def mark_published(
        self,
        article_id: int,
        telegram_message_id: Optional[int] = None,
    ) -> None:
        """Помечает статью как опубликованную и сохраняет ID сообщения в Telegram."""
        stmt = (
            update(Article)
            .where(Article.id == article_id)
            .values(is_published=True, telegram_message_id=telegram_message_id)
        )
        self._session.execute(stmt)
        logger.debug(
            "Статья id=%s помечена как опубликованная (telegram_msg=%s)",
            article_id,
            telegram_message_id,
        )

    def get_articles_since(self, dt: datetime) -> list[Article]:
        """
        Возвращает все статьи, опубликованные (published_at) начиная с dt.
        Используется для построения ретроспективных дайджестов.
        """
        stmt = (
            select(Article)
            .where(Article.published_at >= dt)
            .order_by(Article.published_at.desc())
        )
        return list(self._session.scalars(stmt).all())

    def get_by_id(self, article_id: int) -> Optional[Article]:
        """Возвращает статью по первичному ключу."""
        return self._session.get(Article, article_id)


# ---------------------------------------------------------------------------
# SourceRepository
# ---------------------------------------------------------------------------

class SourceRepository:
    """Операции с таблицей sources."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_all_active(self, channel: str | None = None) -> list[Source]:
        """Возвращает активные источники, опционально фильтруя по каналу."""
        stmt = select(Source).where(Source.is_active.is_(True))
        if channel is not None:
            stmt = stmt.where(Source.channel == channel)
        return list(self._session.scalars(stmt.order_by(Source.name)).all())

    def get_by_feed_url(self, feed_url: str) -> Optional[Source]:
        """Находит источник по URL ленты."""
        stmt = select(Source).where(Source.feed_url == feed_url)
        return self._session.scalars(stmt).first()

    def update_last_fetched(self, source_id: int) -> None:
        """Обновляет время последнего успешного опроса источника."""
        stmt = (
            update(Source)
            .where(Source.id == source_id)
            .values(last_fetched=datetime.now(timezone.utc))
        )
        self._session.execute(stmt)

    def increment_fail_count(self, source_id: int) -> None:
        """
        Увеличивает счётчик неудач источника.
        При превышении порога (max_source_fail_count) источник будет деактивирован
        внешней логикой.
        """
        source = self._session.get(Source, source_id)
        if source is not None:
            source.fail_count += 1
            logger.warning(
                "Источник id=%s (%s): счётчик ошибок = %d",
                source_id,
                source.name,
                source.fail_count,
            )

    def reset_fail_count(self, source_id: int) -> None:
        """Сбрасывает счётчик неудач после успешного опроса."""
        stmt = (
            update(Source)
            .where(Source.id == source_id)
            .values(fail_count=0)
        )
        self._session.execute(stmt)

    def deactivate(self, source_id: int) -> None:
        """Деактивирует источник (например, при слишком большом числе ошибок)."""
        stmt = (
            update(Source)
            .where(Source.id == source_id)
            .values(is_active=False)
        )
        self._session.execute(stmt)
        logger.warning("Источник id=%s деактивирован", source_id)

    def seed_sources(self, sources: list[dict]) -> int:
        """
        Добавляет источники из списка словарей, если они ещё не существуют.
        Ключ уникальности — feed_url.

        Структура элемента:
            {
                "name": str,
                "feed_url": str,
                "site_url": str,      # опционально
                "region": str,        # "spain" | "valencia"
            }

        Возвращает число добавленных источников.
        """
        added = 0
        for data in sources:
            feed_url = data.get("feed_url", "")
            if not feed_url:
                logger.warning("Пропускаем источник без feed_url: %s", data)
                continue

            existing = self.get_by_feed_url(feed_url)
            if existing is not None:
                correct_channel = data.get("channel", "news")
                if existing.channel != correct_channel:
                    existing.channel = correct_channel
                    logger.info("Обновлён channel источника %s: %s", existing.name, correct_channel)
                continue

            source = Source(
                name=data["name"],
                feed_url=feed_url,
                site_url=data.get("site_url"),
                region=data.get("region", "spain"),
                channel=data.get("channel", "news"),
                is_active=data.get("is_active", True),
            )
            self._session.add(source)
            added += 1
            logger.info("Добавлен источник: %s (%s)", source.name, feed_url)

        if added:
            self._session.flush()
        return added


# ---------------------------------------------------------------------------
# PublishLogRepository
# ---------------------------------------------------------------------------

class PublishLogRepository:
    """Операции с журналом публикаций."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create_log(
        self,
        digest_type: str,
        articles_fetched: int = 0,
        articles_published: int = 0,
        status: str = "success",
        error_message: Optional[str] = None,
    ) -> PublishLog:
        """
        Создаёт запись в журнале публикаций.

        Args:
            digest_type: "morning" или "evening"
            articles_fetched: сколько статей получено из источников
            articles_published: сколько опубликовано в Telegram
            status: "success" | "partial" | "failed"
            error_message: текст ошибки при неуспешном завершении
        """
        log = PublishLog(
            run_at=datetime.now(timezone.utc),
            digest_type=digest_type,
            articles_fetched=articles_fetched,
            articles_published=articles_published,
            status=status,
            error_message=error_message,
        )
        self._session.add(log)
        self._session.flush()  # Получаем id сразу
        logger.info(
            "Лог создан: id=%s digest=%s status=%s published=%d",
            log.id,
            digest_type,
            status,
            articles_published,
        )
        return log

    def update_log(self, log_id: int, **kwargs) -> None:
        """
        Обновляет поля существующей записи журнала.

        Пример:
            repo.update_log(log_id=5, status="failed", error_message="timeout")
        """
        allowed_fields = {
            "articles_fetched",
            "articles_published",
            "status",
            "error_message",
        }
        filtered = {k: v for k, v in kwargs.items() if k in allowed_fields}

        if not filtered:
            logger.warning("update_log id=%s: нет допустимых полей для обновления", log_id)
            return

        stmt = update(PublishLog).where(PublishLog.id == log_id).values(**filtered)
        self._session.execute(stmt)
        logger.debug("Лог id=%s обновлён: %s", log_id, filtered)

    def get_recent_logs(self, limit: int = 10) -> list[PublishLog]:
        """Возвращает последние N записей журнала для мониторинга."""
        stmt = (
            select(PublishLog)
            .order_by(PublishLog.run_at.desc())
            .limit(limit)
        )
        return list(self._session.scalars(stmt).all())
