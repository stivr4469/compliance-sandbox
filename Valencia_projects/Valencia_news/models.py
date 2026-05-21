"""
Базовые модели данных, используемые во всём приложении.

ParsedArticle — результат парсинга источника новостей.
ProcessedArticle — статья, обогащённая AI-обработкой.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ParsedArticle:
    """
    Статья, полученная от парсера.

    Поля соответствуют минимально необходимому набору для дальнейшей обработки.
    """

    url: str
    title: str
    source_name: str  # Например: "El País", "Las Provincias"
    region: str  # "valencia" | "spain" | "international"
    published_at: datetime
    content: str = ""  # Полный текст статьи (может быть пустым при RSS-только)
    image_url: str | None = None
    language: str = "es"  # Исходный язык статьи
    event_end_date: datetime | None = None  # Дата окончания события (для канала events)


@dataclass
class ProcessedArticle(ParsedArticle):
    """
    Статья после AI-обработки: содержит перевод, оценку важности и категорию.

    Расширяет ParsedArticle тремя полями, заполняемыми ArticleProcessor.
    """

    title_ru: str = ""  # Заголовок на русском языке
    teaser_ru: str = ""  # Тизер на русском (1-2 предложения, для превью)
    summary_ru: str = ""  # Краткое содержание на русском (2-3 предложения)
    importance_score: float = 0.0  # От 0.0 (неважно) до 1.0 (критически важно)
    category: str = "другое"  # Одна из фиксированных категорий
    location: str = ""  # Адрес/место проведения (если есть в тексте)
