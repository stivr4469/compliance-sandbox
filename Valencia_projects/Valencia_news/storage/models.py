"""
SQLAlchemy 2.0 модели данных для Valencia News Aggregator.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Базовый класс для всех моделей."""
    pass


class Article(Base):
    """
    Новостная статья.
    Хранит оригинальный текст, AI-саммари и метаданные публикации.
    """

    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Уникальная ссылка на статью — используется для дедупликации
    url: Mapped[str] = mapped_column(String(2048), unique=True, nullable=False, index=True)

    # Заголовок статьи
    title: Mapped[str] = mapped_column(String(512), nullable=False)

    # Заголовок на русском языке (генерируется AI)
    title_ru: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    # Тизер на русском (1-2 предложения, для превью в Telegram)
    teaser_ru: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)

    # Оригинальный текст статьи (может быть длинным)
    original_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Краткое саммари на русском, сгенерированное Gemini
    summary_ru: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Категория: política, economía, sociedad и т.д.
    category: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)

    # Балл важности от 0.0 до 1.0, выставляемый Gemini
    importance_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Название источника (El País, Las Provincias и т.д.)
    source_name: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)

    # URL сайта-источника
    source_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)

    # Регион: "spain" или "valencia"
    region: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)

    # Дата публикации статьи на сайте-источнике
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)

    # Когда статья была получена нашим агрегатором
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now(), server_default=func.now()
    )

    # Опубликована ли статья в Telegram
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # ID сообщения в Telegram (заполняется после публикации)
    telegram_message_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # URL изображения к статье (для превью в Telegram)
    image_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)

    # Канал публикации: "news" | "events" | "tourism" | "gastronomy"
    channel: Mapped[str] = mapped_column(
        String(32), nullable=False, default="news", server_default="news", index=True
    )

    # Дата окончания события (для афиши): для разовых = published_at, для выставок = дата закрытия
    event_end_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    def __init__(self, **kwargs: object) -> None:
        kwargs.setdefault("channel", "news")
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        return f"<Article id={self.id} title={self.title!r} published={self.is_published}>"


class Source(Base):
    """
    Источник новостей (RSS-лента или сайт).
    """

    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Читаемое название источника
    name: Mapped[str] = mapped_column(String(256), nullable=False)

    # URL RSS/Atom ленты
    feed_url: Mapped[str] = mapped_column(String(2048), nullable=False, unique=True, index=True)

    # Домашний URL сайта
    site_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)

    # Регион: "spain", "valencia" и т.д.
    region: Mapped[str] = mapped_column(String(32), nullable=False, default="spain")

    # Активен ли источник (можно отключить без удаления)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Когда последний раз успешно опрашивался
    last_fetched: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Счётчик последовательных неудачных попыток
    fail_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Канал которому принадлежит источник: "news" | "events" | "tourism" | "gastronomy"
    channel: Mapped[str] = mapped_column(
        String(32), nullable=False, default="news", server_default="news"
    )

    def __repr__(self) -> str:
        return f"<Source id={self.id} name={self.name!r} active={self.is_active}>"


class PublishLog(Base):
    """
    Журнал запусков агрегатора.
    Фиксирует каждый выпуск дайджеста для мониторинга.
    """

    __tablename__ = "publish_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Время запуска
    run_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now(), server_default=func.now()
    )

    # Сколько статей было получено из источников
    articles_fetched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Сколько статей опубликовано в этом выпуске
    articles_published: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Тип дайджеста: "morning" или "evening"
    digest_type: Mapped[str] = mapped_column(String(16), nullable=False)

    # Статус: "success", "partial", "failed"
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="success")

    # Сообщение об ошибке, если статус не "success"
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<PublishLog id={self.id} type={self.digest_type!r} "
            f"status={self.status!r} published={self.articles_published}>"
        )
