import argparse
import sys
import warnings
from pathlib import Path

from scrapy.crawler import CrawlerProcess

warnings.filterwarnings("ignore", category=DeprecationWarning)

WORKERS_DIR = Path(__file__).resolve().parent
if str(WORKERS_DIR) not in sys.path:
    sys.path.insert(0, str(WORKERS_DIR))

from spiders.registry import detect_spider_from_url, get_spider_class, list_spiders  # noqa: E402
from pipelines.register import publish_spider_registrations  # noqa: E402

SCRAPY_SETTINGS = {
    "USER_AGENT": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "LOG_LEVEL": "WARNING",
    "REQUEST_FINGERPRINTER_IMPLEMENTATION": "2.7",
    "DOWNLOAD_DELAY": 2.0,
    "RANDOMIZE_DOWNLOAD_DELAY": True,
    "CONCURRENT_REQUESTS": 2,
    "CONCURRENT_REQUESTS_PER_DOMAIN": 1,
    "AUTOTHROTTLE_ENABLED": True,
    "AUTOTHROTTLE_START_DELAY": 2.0,
    "AUTOTHROTTLE_MAX_DELAY": 30.0,
    "AUTOTHROTTLE_TARGET_CONCURRENCY": 0.5,
    "RETRY_ENABLED": True,
    "RETRY_TIMES": 2,
    "DOWNLOAD_TIMEOUT": 30,
    "ITEM_PIPELINES": {
        "pipelines.cleaning.DataCleaningPipeline": 300,
        "pipelines.rabbitmq.RabbitMQPipeline": 800,
    },
}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Lanceur Scrapy — sélectionne le spider par source"
    )
    parser.add_argument(
        "--category",
        choices=["collectors", "signals"],
        help="Filtrer par type de spider",
    )
    parser.add_argument(
        "--source",
        default="charika",
        choices=list_spiders(),
        help="Spider / source (registry)",
    )
    parser.add_argument("--url", help="URL cible")
    parser.add_argument("--query", help="Requête ICE Maroc")
    return parser.parse_args()


def main():
    args = parse_args()
    source = args.source or detect_spider_from_url(args.url or "")

    spider_cls = get_spider_class(source)
    crawl_kwargs = {}
    if args.url:
        crawl_kwargs["url"] = args.url
    if args.query:
        crawl_kwargs["query"] = args.query

    publish_spider_registrations()

    process = CrawlerProcess(settings=SCRAPY_SETTINGS)
    process.crawl(spider_cls, **crawl_kwargs)
    process.start()


if __name__ == "__main__":
    main()
