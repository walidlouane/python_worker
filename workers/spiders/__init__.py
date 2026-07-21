from spiders.collectors import CharikaSpider, IcemarocSpider
from spiders.registry import (
    COLLECTORS,
    SIGNALS,
    SPIDERS,
    detect_spider_from_url,
    get_spider_category,
    get_spider_class,
    list_spiders,
)

__all__ = [
    "COLLECTORS",
    "SIGNALS",
    "SPIDERS",
    "CharikaSpider",
    "IcemarocSpider",
    "detect_spider_from_url",
    "get_spider_category",
    "get_spider_class",
    "list_spiders",
]
