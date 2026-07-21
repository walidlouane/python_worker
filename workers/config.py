import os

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@127.0.0.1:5672/%2F")
URL_TO_CRAWL_QUEUE = os.getenv("URL_TO_CRAWL_QUEUE", "url_to_crawl")
DOCUMENT_QUEUE = os.getenv("DOCUMENT_QUEUE", "document_queue")

DEFAULT_SOURCE = os.getenv("DEFAULT_SOURCE", "charika")
