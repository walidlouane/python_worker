import json
import logging
from datetime import datetime, timezone
from uuid import uuid4

import pika

from config import RABBITMQ_URL, SCRAPER_REGISTER_QUEUE, WORKER_ID
from spiders.registry import list_spider_registrations

logger = logging.getLogger(__name__)


def build_register_message(spiders: list[dict] | None = None) -> dict:
    return {
        "pattern": "scraper.register",
        "data": {
            "schemaVersion": "1.0",
            "traceId": f"trace_{uuid4()}",
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "workerId": WORKER_ID,
            "spiders": spiders if spiders is not None else list_spider_registrations(),
        },
    }


def publish_spider_registrations(spiders: list[dict] | None = None) -> dict:
    message = build_register_message(spiders)
    parameters = pika.URLParameters(RABBITMQ_URL)
    connection = pika.BlockingConnection(parameters)
    channel = connection.channel()
    channel.queue_declare(queue=SCRAPER_REGISTER_QUEUE, durable=True)

    channel.basic_publish(
        exchange="",
        routing_key=SCRAPER_REGISTER_QUEUE,
        body=json.dumps(message, ensure_ascii=False),
    )
    connection.close()

    spider_names = [spider["spiderName"] for spider in message["data"]["spiders"]]
    logger.info("Spiders enregistrés sur %s: %s", SCRAPER_REGISTER_QUEUE, spider_names)
    print(f"[register] Spiders envoyés vers {SCRAPER_REGISTER_QUEUE}: {', '.join(spider_names)}")
    return message
