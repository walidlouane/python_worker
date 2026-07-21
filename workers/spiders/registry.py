from spiders.collectors.charika_spider import CharikaSpider
from spiders.collectors.icemaroc_spider import IcemarocSpider

COLLECTORS = {
    "charika": {
        "label": "Charika.ma",
        "domain": "charika.ma",
        "category": "collectors",
        "class": CharikaSpider,
    },
    "icemaroc": {
        "label": "ICE Maroc API",
        "domain": "icemaroc.com",
        "category": "collectors",
        "class": IcemarocSpider,
    },
}

# Futur Phase 3 : news, tenders, job boards
SIGNALS = {
    # "medias24": {...},
    # "marchespublics": {...},
    # "rekrute": {...},
}

SPIDERS = {**COLLECTORS, **SIGNALS}


def get_spider_class(name: str):
    key = (name or "").lower().strip()
    if key not in SPIDERS:
        available = ", ".join(sorted(SPIDERS))
        raise ValueError(f"Spider inconnu '{name}'. Disponibles: {available}")
    return SPIDERS[key]["class"]


def get_spider_category(name: str) -> str:
    return SPIDERS[get_spider_key(name)]["category"]


def get_spider_key(name: str) -> str:
    key = (name or "").lower().strip()
    if key not in SPIDERS:
        raise ValueError(f"Spider inconnu '{name}'")
    return key


def detect_spider_from_url(url: str) -> str:
    lowered = (url or "").lower()
    for name, config in SPIDERS.items():
        if config["domain"] in lowered:
            return name
    return "charika"


def list_spiders(category: str | None = None) -> list[str]:
    if category == "collectors":
        return sorted(COLLECTORS)
    if category == "signals":
        return sorted(SIGNALS)
    return sorted(SPIDERS)
