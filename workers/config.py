import os

ADD_COMPANY_QUEUE = os.getenv("ADD_COMPANY_QUEUE", os.getenv("RABBITMQ_ADD_COMPANY_QUEUE", "add_company"))
SCRAPER_REGISTER_QUEUE = os.getenv(
    "SCRAPER_REGISTER_QUEUE",
    os.getenv("RABBITMQ_SCRAPER_REGISTER_QUEUE", "scraper.register"),
)
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@127.0.0.1:5672/%2F")
URL_TO_CRAWL_QUEUE = os.getenv("URL_TO_CRAWL_QUEUE", "url_to_crawl")

# Legacy queue used by ai_worker (optional enrichment step)
DOCUMENT_QUEUE = os.getenv("DOCUMENT_QUEUE", "document_queue")

DEFAULT_SOURCE = os.getenv("DEFAULT_SOURCE", "charika")
WORKER_ID = os.getenv("WORKER_ID", "scrapy-worker-local-1")
DEFAULT_COUNTRY = os.getenv("DEFAULT_COUNTRY", "Morocco")
