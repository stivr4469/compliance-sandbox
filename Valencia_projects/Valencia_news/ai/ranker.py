"""
Ранжирование обработанных статей для формирования дайджеста.

Критерии отбора:
  - Основной: importance_score (AI) + rule_boost (детерминированный).
  - Региональный баланс: 11+ валенсийских статей, 3-4 серьёзных национальных.
  - Национальные: только политика/экономика/серьёзные происшествия, не спорт/погода/развлечения.
"""

from __future__ import annotations

import logging
import re

from models import ProcessedArticle

logger = logging.getLogger(__name__)

VALENCIA_REGION = "valencia"

# Лимит национальных статей (политика/экономика/серьёзное)
MAX_SPAIN_ARTICLES = 4
MIN_SPAIN_ARTICLES = 3

# Категории, которые отбираются из национальных источников
_SPAIN_ALLOWED_CATEGORIES = frozenset(["политика", "экономика", "происшествия"])

# Минимальный порог важности для национальных статей
_SPAIN_MIN_IMPORTANCE = 0.5

# ---------------------------------------------------------------------------
# Детерминированные буст-правила поверх AI-оценки
# Если паттерн найден в заголовке или саммари → прибавляем boost к importance_score
# ---------------------------------------------------------------------------
_BOOST_RULES: list[tuple[float, re.Pattern]] = [
    # Анонс сезона / крупной программы
    (0.30, re.compile(
        r"temporada\s+\d{4}|nueva\s+temporada|programa(?:ción)?\s+\d{4}|"
        r"presenta\s+su\s+(temporada|programación)|"
        r"новый\s+сезон|программа\s+сезона|объявляет\s+программу|сезон\s+\d{4}",
        re.I,
    )),
    # Мировые / испанские премьеры
    (0.25, re.compile(
        r"estreno\s+(mundial|absoluto|en\s+españa)|primera\s+vez\s+en\s+españa|"
        r"мировая\s+премьера|первая\s+постановка|впервые\s+в\s+испани",
        re.I,
    )),
    # Имена мировых звёзд (культура)
    (0.20, re.compile(
        r"Cecilia\s+Bartoli|Lang\s+Lang|Lisette\s+Oropesa|Plácido\s+Domingo|"
        r"Jonas\s+Kaufmann|Anna\s+Netrebko|Christopher\s+Maltman|"
        r"Andrea\s+Bocelli|Андреа\s+Бочелли|Лэнг\s+Лэнг",
        re.I,
    )),
    # Главные культурные институции Валенсии
    (0.15, re.compile(
        r"Palau\s+de\s+les\s+Arts|Les\s+Arts|Palau\s+de\s+la\s+Música|"
        r"Ciudad\s+de\s+las\s+Artes|IVAM",
        re.I,
    )),
    # Крупнейшие события и награды
    (0.15, re.compile(
        r"Premio\s+Nobel|Premio\s+Goya|Grammy|Festival\s+de\s+Cannes|Óscar|"
        r"Нобелевская\s+премия|Оскар|Гойя|Каннский\s+фестиваль",
        re.I,
    )),
    # Дана / катастрофы / чрезвычайные события Валенсии
    (0.20, re.compile(
        r"\bdana\b|inundaci|emergencia|catástrofe|дана\b|наводнение|затопление|чрезвычайн",
        re.I,
    )),
]


def _rule_boost(article: ProcessedArticle) -> float:
    """Возвращает суммарный буст на основе ключевых паттернов в тексте статьи."""
    text = " ".join(filter(None, [
        getattr(article, "title_ru", ""),
        article.title,
        article.summary_ru or "",
    ]))
    total = 0.0
    for boost, pattern in _BOOST_RULES:
        if pattern.search(text):
            total += boost
    return min(total, 0.4)  # максимальный буст — 0.4, не даём уйти за 1.4


class Ranker:
    """
    Отбирает топ-N статей из обработанного списка.

    Приоритет — Валенсия. Из национальных берутся только серьёзные материалы
    (политика, экономика, происшествия) с importance >= 0.5.
    """

    def rank(
        self,
        articles: list[ProcessedArticle],
        max_count: int = 15,
    ) -> list[ProcessedArticle]:
        """
        Ранжирует статьи и возвращает топ-N с учётом регионального баланса.

        Алгоритм:
          1. Разбиваем статьи на валенсийские и национальные.
          2. Национальные фильтруем: только серьёзные категории + importance >= 0.5.
          3. Берём 3-4 лучших национальных.
          4. Оставшиеся места заполняем валенсийскими (по importance desc).
          5. Финальная сортировка по importance.

        Args:
            articles: Все обработанные статьи.
            max_count: Максимальное количество статей в дайджесте.

        Returns:
            Список из max_count (или меньше) статей.
        """
        if not articles:
            logger.warning("Ranker получил пустой список статей")
            return []

        valencia_articles = [
            a for a in articles if a.region.lower() == VALENCIA_REGION
        ]
        other_articles = [
            a for a in articles if a.region.lower() != VALENCIA_REGION
        ]

        valencia_sorted = sorted(
            valencia_articles, key=lambda a: a.importance_score + _rule_boost(a), reverse=True
        )

        # Национальные: серьёзные категории ИЛИ высокий rule_boost (крупный культурный анонс)
        # rule_boost >= 0.25 означает «мировая премьера / сезон крупной институции» —
        # такие статьи важнее категориального фильтра
        spain_serious = [
            a for a in other_articles
            if (a.category in _SPAIN_ALLOWED_CATEGORIES or _rule_boost(a) >= 0.25)
            and a.importance_score >= _SPAIN_MIN_IMPORTANCE
        ]
        spain_sorted = sorted(spain_serious, key=lambda a: a.importance_score + _rule_boost(a), reverse=True)

        logger.debug(
            "Ранжирование: %d валенсийских, %d серьёзных национальных (из %d), лимит=%d",
            len(valencia_sorted),
            len(spain_sorted),
            len(other_articles),
            max_count,
        )

        # Берём 3-4 лучших национальных
        spain_quota = min(MAX_SPAIN_ARTICLES, len(spain_sorted))
        selected_spain = spain_sorted[:spain_quota]

        # Оставшиеся места отдаём Валенсии
        valencia_slots = max_count - len(selected_spain)
        selected_valencia = valencia_sorted[:valencia_slots]

        combined = selected_valencia + selected_spain

        # Добиваем Valencia если национальных не хватило
        already_selected_urls = {a.url for a in combined}
        if len(combined) < max_count:
            for article in valencia_sorted[valencia_slots:]:
                if article.url not in already_selected_urls:
                    combined.append(article)
                    already_selected_urls.add(article.url)
                    if len(combined) >= max_count:
                        break

        result = sorted(combined, key=lambda a: a.importance_score + _rule_boost(a), reverse=True)[:max_count]

        spain_in_result = [a for a in result if a.region.lower() != VALENCIA_REGION]
        val_in_result = [a for a in result if a.region.lower() == VALENCIA_REGION]
        logger.info(
            "Ранжирование завершено: %d Валенсия + %d Испания = %d статей (из %d)",
            len(val_in_result),
            len(spain_in_result),
            len(result),
            len(articles),
        )

        return result
