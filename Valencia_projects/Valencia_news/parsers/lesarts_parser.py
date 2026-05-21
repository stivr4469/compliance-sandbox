"""
Парсер Les Arts — главного оперного театра Валенсии (lesarts.com).

Скрапит страницы программы через requests+BeautifulSoup.
Требует куки CookieConsent=1 для получения полного HTML.
Парсит события за текущий и следующий месяц.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from typing import Optional

import requests
from bs4 import BeautifulSoup

from parsers.base import ParsedArticle

logger = logging.getLogger(__name__)

BASE_URL = "https://www.lesarts.com"
PROGRAMACION_URL = f"{BASE_URL}/es/programacion.html"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-ES,es;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Cookie": "CookieConsent=1",
}

# Месяцы для парсинга вперёд (текущий + N следующих)
_MONTHS_AHEAD = 3

# Таблица перевода сокращений месяцев
_MONTH_MAP = {
    "01": 1, "02": 2, "03": 3, "04": 4, "05": 5, "06": 6,
    "07": 7, "08": 8, "09": 9, "10": 10, "11": 11, "12": 12,
}


class LesArtsParser:
    """
    Парсит программу Les Arts.

    Стратегия:
    1. Загружает страницы программы за текущий и следующие N месяцев
    2. Извлекает события из элементов [aria-label^='Información de la actividad']
    3. Парсит даты формата 'VI 22.05.26 | 19:30 h' и 'Del VI 22.05.26 al SA 30.05.26'
    4. Возвращает ParsedArticle с датой, местом, категорией в тексте
    """

    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.headers.update(_HEADERS)

    def parse(self, known_urls: Optional[set] = None) -> list[ParsedArticle]:
        known_urls = known_urls or set()
        now = datetime.now(timezone.utc)
        articles: list[ParsedArticle] = []
        seen_urls: set[str] = set()

        # Текущий месяц + следующие N
        months = _get_upcoming_months(now, _MONTHS_AHEAD)

        for year, month in months:
            try:
                url = PROGRAMACION_URL if (year == now.year and month == now.month) \
                    else f"{PROGRAMACION_URL}?mes={year}-{month}"
                html = self._fetch(url)
                if not html:
                    continue

                new_articles = self._parse_page(html, known_urls, seen_urls, now)
                articles.extend(new_articles)
                logger.info("LesArts: %d-%02d → %d событий", year, month, len(new_articles))

                if (year, month) != months[-1]:
                    time.sleep(0.5)

            except Exception as exc:
                logger.error("LesArts: ошибка парсинга %d-%02d: %s", year, month, exc)

        logger.info("LesArts: итого %d новых событий", len(articles))
        return articles

    def _parse_page(
        self,
        html: str,
        known_urls: set,
        seen_urls: set,
        now: datetime,
    ) -> list[ParsedArticle]:
        soup = BeautifulSoup(html, "html.parser")
        articles: list[ParsedArticle] = []

        events = soup.find_all(
            attrs={"aria-label": lambda x: x and "Información de la actividad" in x}
        )

        for ev in events:
            try:
                article = self._parse_event(ev, known_urls, seen_urls, now)
                if article:
                    articles.append(article)
            except Exception as exc:
                logger.debug("LesArts: ошибка события: %s", exc)

        return articles

    def _parse_event(
        self,
        ev,
        known_urls: set,
        seen_urls: set,
        now: datetime,
    ) -> Optional[ParsedArticle]:
        title = ev.get("aria-label", "").replace("Información de la actividad ", "").strip()
        if not title:
            return None

        # URL события
        link = ev.find("a", href=re.compile(r"/programacion/c/"))
        if not link:
            return None
        href = link.get("href", "")
        url = href if href.startswith("http") else BASE_URL + href

        if url in seen_urls or url in known_urls:
            return None

        # Изображение
        img = ev.find("img")
        image_url = None
        if img and img.get("src"):
            src = img["src"]
            image_url = src if src.startswith("http") else BASE_URL + src

        # Извлекаем все текстовые узлы из дочерних элементов без вложенных
        leaf_texts = []
        for el in ev.find_all(True):
            if not el.find(True):  # листовой элемент
                t = el.get_text(strip=True)
                if t and len(t) > 2 and t not in ("Comprar", "2025-26", "2026-27"):
                    leaf_texts.append(t)

        # Дата: ищем паттерны вида "VI 22.05.26 | 19:30 h" или "Del VI 22.05.26 al SA 30.05.26"
        date_str = ""
        start_dt: Optional[datetime] = None
        for t in leaf_texts:
            m = re.search(r"(\d{2}\.\d{2}\.\d{2})", t)
            if m:
                date_str = t.strip()
                start_dt = _parse_lesarts_date(m.group(1))
                break

        # Пропускаем прошедшие события
        if start_dt and start_dt < now:
            return None

        published_at = start_dt or now

        # Категория: последний листовой текст обычно это категория
        category = leaf_texts[-1] if leaf_texts else ""
        known_categories = {"Òpera", "Lied", "Dansa", "Simfònic", "Flamenco",
                            "Per a tots", "Musicals", "Educación", "Bandes",
                            "Altres músiques", "Barroc i Música Antiga"}
        if category not in known_categories:
            category = ""

        # Место: ищем текст с названиями залов
        venue = ""
        venue_keywords = ["Sala Principal", "Auditori", "Teatre Martín", "Aula Magistral",
                         "Teatre Comentador", "jardins"]
        for t in leaf_texts:
            if any(kw.lower() in t.lower() for kw in venue_keywords):
                venue = t
                break

        # Субтитр (описание спектакля)
        subtitle = ""
        for t in leaf_texts:
            if t != title and t != date_str and t != category and t != venue:
                if len(t) > 5 and not re.match(r"^\d{2}\.\d{2}\.\d{2}", t):
                    subtitle = t
                    break

        # Формируем текст для AI
        parts = [title]
        if subtitle:
            parts.append(subtitle)
        if category:
            parts.append(f"Categoría: {category}.")
        if date_str:
            parts.append(f"Fecha: {date_str}.")
        if venue:
            parts.append(f"Lugar: {venue}.")
        parts.append("Palau de les Arts Reina Sofía, Ciudad de las Artes y las Ciencias, València.")

        full_text = " ".join(parts)

        seen_urls.add(url)
        return ParsedArticle(
            url=url,
            title=title,
            text=full_text,
            image_url=image_url,
            published_at=published_at,
            event_end_date=published_at,  # разовое событие — начало = конец
            source_name="Les Arts",
            source_url=BASE_URL,
            region="valencia",
        )

    def _fetch(self, url: str) -> Optional[str]:
        try:
            resp = self._session.get(url, timeout=15)
            resp.raise_for_status()
            return resp.text
        except Exception as exc:
            logger.error("LesArts: ошибка загрузки %s: %s", url, exc)
            return None


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def _get_upcoming_months(now: datetime, count: int) -> list[tuple[int, int]]:
    """Возвращает список (year, month) начиная с текущего месяца."""
    months = []
    year, month = now.year, now.month
    for _ in range(count + 1):
        months.append((year, month))
        month += 1
        if month > 12:
            month = 1
            year += 1
    return months


def _parse_lesarts_date(date_str: str) -> Optional[datetime]:
    """
    Парсит дату формата DD.MM.YY → datetime UTC.
    Пример: '22.05.26' → 2026-05-22
    """
    try:
        day, month, year_short = date_str.split(".")
        year = 2000 + int(year_short)
        return datetime(int(year), int(month), int(day), 20, 0, tzinfo=timezone.utc)
    except Exception:
        return None
