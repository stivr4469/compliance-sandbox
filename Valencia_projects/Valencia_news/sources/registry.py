"""
Реестр источников: новости Испании/Валенсии, события, туризм, гастрономия.
Каждый источник — словарь с полями name, feed_url, site_url, region, channel.
"""

from typing import TypedDict


class SourceDict(TypedDict):
    name: str
    feed_url: str
    site_url: str
    region: str
    channel: str


# ---------------------------------------------------------------------------
# Национальные испанские новости → канал "news"
# ---------------------------------------------------------------------------
_SPAIN_SOURCES: list[SourceDict] = [
    {
        "name": "El País",
        "feed_url": "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/portada",
        "site_url": "https://elpais.com",
        "region": "spain",
        "channel": "news",
    },
    {
        "name": "El Mundo",
        "feed_url": "https://e00-elmundo.uecdn.es/elmundo/rss/portada.xml",
        "site_url": "https://elmundo.es",
        "region": "spain",
        "channel": "news",
    },
    {
        "name": "ABC",
        "feed_url": "https://www.abc.es/rss/feeds/abcPortada.xml",
        "site_url": "https://www.abc.es",
        "region": "spain",
        "channel": "news",
    },
    {
        "name": "La Vanguardia",
        "feed_url": "https://www.lavanguardia.com/rss/home.xml",
        "site_url": "https://www.lavanguardia.com",
        "region": "spain",
        "channel": "news",
    },
    {
        "name": "20minutos",
        "feed_url": "https://www.20minutos.es/rss/",
        "site_url": "https://www.20minutos.es",
        "region": "spain",
        "channel": "news",
    },
    {
        "name": "El Confidencial",
        "feed_url": "https://rss.elconfidencial.com/espana/",
        "site_url": "https://www.elconfidencial.com",
        "region": "spain",
        "channel": "news",
    },
    {
        "name": "El Español",
        "feed_url": "https://www.elespanol.com/rss/",
        "site_url": "https://www.elespanol.com",
        "region": "spain",
        "channel": "news",
    },
]

# ---------------------------------------------------------------------------
# Культурные новости — анонсы сезонов, премьеры, события мирового уровня
# Сюда попадают статьи типа «Les Arts объявил программу сезона»
# ---------------------------------------------------------------------------
_CULTURE_NEWS_SOURCES: list[SourceDict] = [
    {
        "name": "El País Cultura",
        "feed_url": "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/cultura/portada",
        "site_url": "https://elpais.com/cultura/",
        "region": "spain",
        "channel": "news",
    },
]

# ---------------------------------------------------------------------------
# Региональные источники Валенсии
# Новостные → "news", культурные институции → "events"
# ---------------------------------------------------------------------------
_VALENCIA_SOURCES: list[SourceDict] = [
    # --- Las Provincias: главная газета Валенсии, HTML-парсинг (RSS даёт 403) ---
    {
        "name": "Las Provincias",
        "feed_url": "https://www.lasprovincias.es",
        "site_url": "https://www.lasprovincias.es",
        "region": "valencia",
        "channel": "news",
    },
    {
        "name": "ElDiario.es Valencia",
        "feed_url": "https://www.eldiario.es/rss/comunitat-valenciana/",
        "site_url": "https://www.eldiario.es/comunitat-valenciana/",
        "region": "valencia",
        "channel": "news",
    },
    {
        "name": "Levante EMV",
        "feed_url": "https://www.levante-emv.com/rss/",
        "site_url": "https://www.levante-emv.com",
        "region": "valencia",
        "channel": "news",
    },
    {
        "name": "Valencia Plaza",
        "feed_url": "https://valenciaplaza.com/feed",
        "site_url": "https://valenciaplaza.com",
        "region": "valencia",
        "channel": "news",
    },
    {
        "name": "El Mundo Valencia",
        "feed_url": "https://www.elmundo.es/rss/comunidad-valenciana.xml",
        "site_url": "https://www.elmundo.es/comunidad-valenciana.html",
        "region": "valencia",
        "channel": "news",
    },
    {
        "name": "Valencia Noticias",
        "feed_url": "https://valencianoticias.com/feed/",
        "site_url": "https://valencianoticias.com",
        "region": "valencia",
        "channel": "news",
    },
    {
        "name": "Alicante Plaza",
        "feed_url": "https://alicanteplaza.es/feed",
        "site_url": "https://alicanteplaza.es",
        "region": "valencia",
        "channel": "news",
    },
    {
        "name": "Valencia Bonita",
        "feed_url": "https://valenciabonita.es/feed/",
        "site_url": "https://valenciabonita.es",
        "region": "valencia",
        "channel": "news",
    },
    {
        "name": "Valencia Secreta",
        "feed_url": "https://valenciasecreta.com/feed/",
        "site_url": "https://valenciasecreta.com",
        "region": "valencia",
        "channel": "news",
    },
    {
        "name": "20minutos Valencia",
        "feed_url": "https://www.20minutos.es/rss/valencia/",
        "site_url": "https://www.20minutos.es/comunidad-valenciana/",
        "region": "valencia",
        "channel": "news",
    },
    # À Punt Mèdia убран — RSS содержит расписание передач, а не новости
    {
        "name": "OK Diario Valencia",
        "feed_url": "https://okdiario.com/comunidad-valenciana/feed",
        "site_url": "https://okdiario.com/comunidad-valenciana",
        "region": "valencia",
        "channel": "news",
    },
    # Культурные институции и события → афиша
    {
        "name": "Oceanogràfic Valencia",
        "feed_url": "https://www.oceanografic.org/feed/",
        "site_url": "https://www.oceanografic.org",
        "region": "valencia",
        "channel": "events",
    },
    {
        "name": "Feria Valencia",
        "feed_url": "https://feriavalencia.com/feed/",
        "site_url": "https://feriavalencia.com",
        "region": "valencia",
        "channel": "events",
    },
    {
        "name": "Les Arts",
        "feed_url": "https://www.lesarts.com/es/programacion.html",
        "site_url": "https://www.lesarts.com",
        "region": "valencia",
        "channel": "events",
    },
    {
        "name": "Valencia CF",
        "feed_url": "https://www.valenciacf.com/rss",
        "site_url": "https://www.valenciacf.com",
        "region": "valencia",
        "channel": "events",
    },
    {
        "name": "Palau de la Música",
        "feed_url": "https://palauvalencia.com/programacio-i-vendes/",
        "site_url": "https://palauvalencia.com",
        "region": "valencia",
        "channel": "events",
    },
    {
        "name": "Valencia.es Agenda",
        "feed_url": "https://www.valencia.es/cas/agenda-de-la-ciudad",
        "site_url": "https://www.valencia.es",
        "region": "valencia",
        "channel": "events",
    },
    {
        "name": "IVAM",
        "feed_url": "https://ivam.es/es/exposiciones/",
        "site_url": "https://ivam.es",
        "region": "valencia",
        "channel": "events",
    },
    {
        "name": "CCCC Exposiciones",
        "feed_url": "https://www.consorcimuseus.gva.es/?post_type=exposicion&feed=rss2&lang=es",
        "site_url": "https://www.consorcimuseus.gva.es/centre-del-carme/",
        "region": "valencia",
        "channel": "events",
    },
    {
        "name": "Fundación Bancaja",
        "feed_url": "https://www.fundacionbancaja.es/rss",
        "site_url": "https://www.fundacionbancaja.es",
        "region": "valencia",
        "channel": "events",
    },
    {
        "name": "Museo Bellas Artes Valencia",
        "feed_url": "https://museobellasartesvalencia.gva.es/es/exposiciones",
        "site_url": "https://museobellasartesvalencia.gva.es",
        "region": "valencia",
        "channel": "events",
    },
]

# ---------------------------------------------------------------------------
# Туризм и путешествия по Испании → канал "tourism"
# Только настоящие туристические источники — гиды, маршруты, достопримечательности
# ---------------------------------------------------------------------------
_TOURISM_SOURCES: list[SourceDict] = [
    {
        "name": "El País Viajes",
        "feed_url": "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/viajes/portada",
        "site_url": "https://elpais.com/viajes/",
        "region": "spain",
        "channel": "tourism",
    },
    {
        "name": "El Mundo Viajes",
        "feed_url": "https://www.elmundo.es/rss/viajes.xml",
        "site_url": "https://www.elmundo.es/viajes.html",
        "region": "spain",
        "channel": "tourism",
    },
    {
        "name": "20minutos Viajes",
        "feed_url": "https://www.20minutos.es/rss/viajes/",
        "site_url": "https://www.20minutos.es/viajes/",
        "region": "spain",
        "channel": "tourism",
    },
    {
        "name": "OK Diario Viajes",
        "feed_url": "https://okdiario.com/viajes/feed",
        "site_url": "https://okdiario.com/viajes",
        "region": "spain",
        "channel": "tourism",
    },
]

# ---------------------------------------------------------------------------
# Гастрономия Испании → канал "gastronomy"
# ---------------------------------------------------------------------------
_GASTRONOMY_SOURCES: list[SourceDict] = [
    {
        "name": "Directo al Paladar",
        "feed_url": "https://www.directoalpaladar.com/index.xml",
        "site_url": "https://www.directoalpaladar.com",
        "region": "spain",
        "channel": "gastronomy",
    },
    {
        "name": "El Comidista",
        "feed_url": "https://feeds.elpais.com/mrss-s/pages/ep/site/elcomidista.elpais.com/portada",
        "site_url": "https://elcomidista.elpais.com",
        "region": "spain",
        "channel": "gastronomy",
    },
    {
        "name": "Gastronosfera",
        "feed_url": "https://www.gastronosfera.com/es/feed",
        "site_url": "https://www.gastronosfera.com",
        "region": "spain",
        "channel": "gastronomy",
    },
    {
        "name": "Guía Repsol",
        "feed_url": "https://www.guiarepsol.com/es/feed/",
        "site_url": "https://www.guiarepsol.com",
        "region": "spain",
        "channel": "gastronomy",
    },
]

# ---------------------------------------------------------------------------
# Спорт Испании и Валенсии → канал "sport"
# ---------------------------------------------------------------------------
_SPORT_SOURCES: list[SourceDict] = [
    {
        "name": "Marca",
        "feed_url": "https://www.marca.com/rss/portada.xml",
        "site_url": "https://www.marca.com",
        "region": "spain",
        "channel": "sport",
    },
    {
        "name": "AS",
        "feed_url": "https://as.com/rss/tags/ultimas_noticias.xml",
        "site_url": "https://as.com",
        "region": "spain",
        "channel": "sport",
    },
    {
        "name": "Superdeporte",
        "feed_url": "https://www.superdeporte.es/rss/portada.xml",
        "site_url": "https://www.superdeporte.es",
        "region": "valencia",
        "channel": "sport",
    },
    {
        "name": "Valencia CF Noticias",
        "feed_url": "https://www.valenciacf.com/rss",
        "site_url": "https://www.valenciacf.com",
        "region": "valencia",
        "channel": "sport",
    },
    {
        "name": "Sport",
        "feed_url": "https://www.sport.es/rss/portada.xml",
        "site_url": "https://www.sport.es",
        "region": "spain",
        "channel": "sport",
    },
    {
        "name": "Mundo Deportivo",
        "feed_url": "https://www.mundodeportivo.com/rss/home.xml",
        "site_url": "https://www.mundodeportivo.com",
        "region": "spain",
        "channel": "sport",
    },
]

# ---------------------------------------------------------------------------
# Объединённый список всех источников
# ---------------------------------------------------------------------------
SOURCES: list[SourceDict] = (
    _SPAIN_SOURCES
    + _CULTURE_NEWS_SOURCES
    + _VALENCIA_SOURCES
    + _TOURISM_SOURCES
    + _GASTRONOMY_SOURCES
    + _SPORT_SOURCES
)


def get_all_sources() -> list[SourceDict]:
    """Вернуть все зарегистрированные источники."""
    return list(SOURCES)


def get_sources_by_region(region: str) -> list[SourceDict]:
    """Вернуть источники для заданного региона ('spain' или 'valencia')."""
    return [s for s in SOURCES if s["region"] == region]


def get_sources_by_channel(channel: str) -> list[SourceDict]:
    """Вернуть источники для заданного канала ('news', 'events', 'tourism', 'gastronomy')."""
    return [s for s in SOURCES if s["channel"] == channel]
