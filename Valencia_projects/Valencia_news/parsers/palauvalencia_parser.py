"""
Парсер Palau de la Música — главного концертного зала Валенсии.

Использует Playwright для рендеринга JavaScript-страницы с событиями.
Принимает cookie-согласие автоматически, затем парсит карточки событий.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

from bs4 import BeautifulSoup

from parsers.base import ParsedArticle

logger = logging.getLogger(__name__)

BASE_URL = "https://palauvalencia.com"
EVENTS_URL = f"{BASE_URL}/programacio-i-vendes/"


class PalauValenciaParser:
    """
    Парсит афишу Palau de la Música Valencia.

    Стратегия:
    1. Загружает страницу через Playwright (JavaScript-рендеринг)
    2. Принимает cookie-согласие
    3. Извлекает карточки событий (div.card.h-100)
    4. Парсит дату DD/MM/YYYY, время HH:MM, заголовок, изображение, URL
    5. Пропускает прошедшие события
    """

    def parse(self, known_urls: Optional[set] = None) -> list[ParsedArticle]:
        known_urls = known_urls or set()
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.error("PalauValencia: playwright не установлен")
            return []

        articles: list[ParsedArticle] = []
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                try:
                    page = browser.new_page()
                    page.goto(EVENTS_URL, wait_until="networkidle", timeout=30000)

                    # Принимаем cookie-согласие
                    try:
                        btn = page.query_selector(
                            "button:has-text('Aceptar'), button:has-text('Acceptar')"
                        )
                        if btn:
                            btn.click()
                            page.wait_for_timeout(1500)
                    except Exception:
                        pass

                    html = page.content()
                    articles = _parse_html(html, known_urls)
                    logger.info("PalauValencia: %d событий", len(articles))
                finally:
                    browser.close()
        except Exception as exc:
            logger.error("PalauValencia: ошибка парсинга: %s", exc)

        return articles


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def _parse_html(html: str, known_urls: set) -> list[ParsedArticle]:
    soup = BeautifulSoup(html, "html.parser")
    now = datetime.now(timezone.utc)
    articles: list[ParsedArticle] = []
    seen_urls: set[str] = set()

    # Карточки событий: div.card.h-100
    cards = soup.find_all(
        "div",
        class_=lambda c: c and "card" in c.split() and "h-100" in c.split(),
    )

    for card in cards:
        try:
            article = _parse_card(card, known_urls, seen_urls, now)
            if article:
                articles.append(article)
        except Exception as exc:
            logger.debug("PalauValencia: ошибка карточки: %s", exc)

    return articles


def _parse_card(
    card,
    known_urls: set,
    seen_urls: set,
    now: datetime,
) -> Optional[ParsedArticle]:
    # URL события — нормализуем: убираем mod= (timestamp обновления, меняется при редактах)
    link = card.find("a", href=lambda h: h and "/event?id=" in h)
    if not link:
        return None
    raw_url = link.get("href", "")
    if not raw_url:
        return None
    url = _normalize_url(raw_url)
    if url in seen_urls or url in known_urls:
        return None

    # Изображение
    img = card.find("img")
    image_url = img.get("src") if img else None

    # Дата и время
    date_text = ""
    time_text = ""
    for p_tag in card.find_all("p", class_="card-text"):
        strong = p_tag.find("strong")
        if not strong:
            continue
        label = strong.get_text(strip=True).rstrip(":")
        val = p_tag.get_text(strip=True)
        val = val.replace(strong.get_text(strip=True), "").strip().lstrip(":")

        if label == "Data":
            date_text = val.strip()
        elif label == "Hora":
            time_text = val.strip()

    # Парсим дату
    event_dt: Optional[datetime] = None
    if date_text:
        event_dt = _parse_date(date_text, time_text)

    # Пропускаем прошедшие события
    if event_dt and event_dt < now:
        return None

    # Заголовок — берём испанскую версию из span.notranslate.es
    title_el = card.find("h5", class_="card-title")
    title = _extract_title(title_el)
    if not title:
        return None

    # Описание (subtitle)
    desc_el = card.find("p", class_=lambda c: c and "card-text" not in (c or "") and "subtitle" in (c or "").lower())
    # Fallback: просто card-body текст без дат
    subtitle = ""
    card_body = card.find("div", class_="card-body")
    if card_body:
        for p_tag in card_body.find_all("p"):
            cls = " ".join(p_tag.get("class", []))
            if "card-text" not in cls:
                t = p_tag.get_text(strip=True)
                if t and len(t) > 5:
                    subtitle = t
                    break

    # Формируем текст для AI
    parts = [title]
    if subtitle:
        parts.append(subtitle)
    if date_text:
        parts.append(f"Fecha: {date_text}")
    if time_text:
        parts.append(f"Hora: {time_text}h")
    parts.append("Palau de la Música de València.")

    seen_urls.add(url)
    published_at = event_dt or now
    return ParsedArticle(
        url=url,
        title=title,
        text=" | ".join(parts),
        image_url=image_url,
        published_at=published_at,
        event_end_date=published_at,
        source_name="Palau de la Música",
        source_url=BASE_URL,
        region="valencia",
    )


def _normalize_url(url: str) -> str:
    """Убирает mod= из URL Palau, чтобы один концерт имел один стабильный URL."""
    parsed = urlparse(url)
    params = {k: v for k, v in parse_qs(parsed.query).items() if k != "mod"}
    clean_query = urlencode({k: v[0] for k, v in params.items()})
    return urlunparse(parsed._replace(query=clean_query))


def _extract_title(title_el) -> str:
    if not title_el:
        return ""

    # Предпочитаем испанскую версию span.notranslate.es прямо в DOM
    es_span = title_el.find(
        "span",
        class_=lambda c: c and "notranslate" in c.split() and "es" in c.split(),
    )
    target = es_span if es_span else title_el

    text = target.get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _parse_date(date_text: str, time_text: str) -> Optional[datetime]:
    """
    Парсит DD/MM/YYYY + HH:MM → datetime UTC.
    """
    try:
        day, month, year = date_text.split("/")
        if time_text and ":" in time_text:
            h, m = time_text.split(":")[:2]
        else:
            h, m = "20", "0"
        return datetime(int(year), int(month), int(day), int(h), int(m), tzinfo=timezone.utc)
    except Exception:
        return None
