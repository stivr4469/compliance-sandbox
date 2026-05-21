"""
Парсер официальной повестки города Валенсия (valencia.es/cas/agenda-de-la-ciudad).

Страница листинга содержит инлайн-JSON var eventosInicio = [...] с данными
о 80+ событиях. Для каждого нового события дополнительно загружается страница
детали — там адрес площадки и полное описание.
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests
from bs4 import BeautifulSoup

from parsers.base import ParsedArticle

logger = logging.getLogger(__name__)

BASE_URL = "https://www.valencia.es"
LISTING_URL = f"{BASE_URL}/cas/agenda-de-la-ciudad"
DETAIL_URL_TEMPLATE = f"{BASE_URL}/cas/agenda-de-la-ciudad/-/content/{{slug}}"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-ES,es;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Только события не старше этого количества дней (ограничивает кол-во запросов)
_MAX_EVENT_AGE_DAYS = 30


class ValenciaAgendaParser:
    """
    Парсит официальную повестку города Валенсии.

    Стратегия:
    1. Загружает страницу листинга → извлекает eventosInicio JSON
    2. Фильтрует события: не старше 30 дней
    3. Для URL не в known_urls: загружает страницу детали (адрес, описание)
    4. Возвращает список ParsedArticle
    """

    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.headers.update(_HEADERS)

    def parse(self, known_urls: Optional[set] = None) -> list[ParsedArticle]:
        known_urls = known_urls or set()

        html = self._fetch(LISTING_URL)
        if not html:
            logger.warning("ValenciaAgenda: не удалось загрузить страницу листинга")
            return []

        events = self._extract_events_json(html)
        if not events:
            logger.warning("ValenciaAgenda: eventosInicio не найден на странице")
            return []

        logger.info("ValenciaAgenda: найдено %d событий в JSON", len(events))

        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=_MAX_EVENT_AGE_DAYS)
        articles: list[ParsedArticle] = []

        for event in events:
            try:
                article = self._process_event(event, known_urls, cutoff, now)
                if article:
                    articles.append(article)
            except Exception as exc:
                logger.debug("ValenciaAgenda: ошибка события '%s': %s", event.get("content", "?")[:40], exc)

        logger.info("ValenciaAgenda: собрано %d статей", len(articles))
        return articles

    # ------------------------------------------------------------------
    # Внутренние методы
    # ------------------------------------------------------------------

    def _process_event(
        self,
        event: dict,
        known_urls: set,
        cutoff: datetime,
        now: datetime,
    ) -> Optional[ParsedArticle]:
        slug = event.get("url", "").strip()
        if not slug:
            return None

        url = DETAIL_URL_TEMPLATE.format(slug=slug)
        title = event.get("content", "").strip()
        if not title:
            return None

        # Даты из Unix-timestamp (миллисекунды)
        start_ts = _parse_timestamp(event.get("startDate"))
        end_ts = _parse_timestamp(event.get("endDate"))

        # Отсекаем прошедшие события: если событие уже закончилось сегодня — пропускаем
        if end_ts and end_ts < now:
            return None
        # Если нет endDate — однодневное событие, пропускаем если старт уже прошёл
        if not end_ts and start_ts and start_ts < now:
            return None

        published_at = start_ts or datetime.now(timezone.utc)

        # Изображение
        image_path = event.get("image", "")
        image_url = f"{BASE_URL}{image_path}" if image_path else None

        # Базовый текст из данных листинга
        categoria = event.get("categoria", "")
        date_str = _format_date_range(start_ts, end_ts)
        base_text = f"{title}. Categoría: {categoria}. Fecha: {date_str}."

        # Детальная страница — только для новых событий
        if url not in known_urls:
            time.sleep(0.3)
            detail = self._fetch_detail(url)
            if detail:
                venue_name, address, schedule_info, description = detail
                full_text = _build_full_text(
                    title, categoria, date_str, venue_name, address, schedule_info, description
                )
            else:
                full_text = base_text
        else:
            full_text = base_text

        return ParsedArticle(
            url=url,
            title=title,
            text=full_text,
            image_url=image_url,
            published_at=published_at,
            event_end_date=end_ts or published_at,
            source_name="Valencia.es Agenda",
            source_url=BASE_URL,
            region="valencia",
        )

    def _fetch(self, url: str) -> Optional[str]:
        try:
            resp = self._session.get(url, timeout=15)
            resp.raise_for_status()
            return resp.text
        except Exception as exc:
            logger.debug("ValenciaAgenda fetch error %s: %s", url, exc)
            return None

    def _extract_events_json(self, html: str) -> list[dict]:
        match = re.search(r"var eventosInicio = (\[.*?\]);", html, re.DOTALL)
        if not match:
            return []
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError as exc:
            logger.warning("ValenciaAgenda: ошибка парсинга JSON: %s", exc)
            return []

    def _fetch_detail(
        self, url: str
    ) -> Optional[tuple[str, str, str, str]]:
        """
        Возвращает (venue_name, address, schedule_info, description) или None.
        """
        html = self._fetch(url)
        if not html:
            return None

        soup = BeautifulSoup(html, "html.parser")

        # Название площадки
        venue_el = soup.select_one("h3.bloque_subtitulo")
        venue_name = venue_el.get_text(strip=True) if venue_el else ""

        # Адрес — первые 2 элемента списка (улица + почтовый индекс/город)
        addr_items = soup.select("li.elementoLista")
        address_parts = []
        for item in addr_items[:2]:
            text = item.get_text(strip=True)
            # Пропускаем контакты (телефон, email, url)
            if not any(kw in text.lower() for kw in ["teléfono", "fax", "email", "url", "tel:"]):
                address_parts.append(text)
        address = ", ".join(address_parts)

        # Дата/время/место — p.bloque_texto.fecha
        schedule_el = soup.select_one("p.bloque_texto.fecha")
        schedule_info = ""
        if schedule_el:
            schedule_info = schedule_el.get_text(" ", strip=True)
            schedule_info = re.sub(r"\s+", " ", schedule_info).strip()

        # Описание — все p.bloque_texto, кроме .fecha
        desc_parts = []
        for p in soup.select("p.bloque_texto"):
            if "fecha" not in (p.get("class") or []):
                text = p.get_text(" ", strip=True)
                if text:
                    desc_parts.append(text)
        description = " ".join(desc_parts[:3])  # берём первые 3 абзаца

        return venue_name, address, schedule_info, description


# ------------------------------------------------------------------
# Вспомогательные функции
# ------------------------------------------------------------------

def _parse_timestamp(value: object) -> Optional[datetime]:
    if not value:
        return None
    try:
        ms = int(str(value))
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    except (ValueError, TypeError, OSError):
        return None


def _format_date_range(start: Optional[datetime], end: Optional[datetime]) -> str:
    fmt = "%d/%m/%Y"
    if start and end:
        s = start.strftime(fmt)
        e = end.strftime(fmt)
        return s if s == e else f"{s} - {e}"
    if start:
        return start.strftime(fmt)
    return ""


def _build_full_text(
    title: str,
    categoria: str,
    date_str: str,
    venue_name: str,
    address: str,
    schedule_info: str,
    description: str,
) -> str:
    parts = [title]
    if categoria:
        parts.append(f"Categoría: {categoria}.")
    if date_str:
        parts.append(f"Fecha: {date_str}.")
    if venue_name:
        parts.append(f"Lugar: {venue_name}.")
    if address:
        parts.append(f"Dirección: {address}.")
    if schedule_info:
        parts.append(schedule_info)
    if description:
        parts.append(description)
    return " ".join(parts)
