import json
from datetime import datetime, timezone
from uuid import uuid4

import pika

from config import ADD_COMPANY_QUEUE, DEFAULT_COUNTRY, RABBITMQ_URL, WORKER_ID


def _first_value(value):
    if isinstance(value, list):
        return value[0] if value else None
    return value


def build_add_company_message(item: dict, spider) -> dict | None:
    name = (item.get("company_name") or item.get("name") or "").strip()
    if not name:
        return None

    spider_name = item.get("source") or getattr(spider, "name", "unknown")
    sector = item.get("html_sector") or item.get("sector")
    phone = _first_value(item.get("phones")) or item.get("phone")
    source_url = item.get("source_url")

    data = {
        "schemaVersion": "1.0",
        "jobId": item.get("jobId") or f"run_{uuid4()}",
        "traceId": item.get("traceId") or f"trace_{uuid4()}",
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "workerId": WORKER_ID,
        "spiderName": spider_name,
        "name": name,
        "phone": phone,
        "ice": item.get("ice"),
        "sector": sector,
        "city": item.get("city"),
        "country": item.get("country") or DEFAULT_COUNTRY,
        "source": f"scrapy:{spider_name}",
        "description": item.get("description")
        or (f"Discovered from {source_url}" if source_url else None),
    }

    if source_url and spider_name in {"charika", "icemaroc"}:
        data["website"] = item.get("website")

    return {
        "pattern": "add_company",
        "data": {key: value for key, value in data.items() if value not in (None, "")},
    }


class RabbitMQPipeline:
    def open_spider(self, spider):
        parameters = pika.URLParameters(RABBITMQ_URL)
        self.connection = pika.BlockingConnection(parameters)
        self.channel = self.connection.channel()
        self.channel.queue_declare(queue=ADD_COMPANY_QUEUE, durable=True)

    def close_spider(self, spider):
        if getattr(self, "connection", None) and not self.connection.is_closed:
            self.connection.close()

    def process_item(self, item, spider):
        message = build_add_company_message(dict(item), spider)
        if not message:
            spider.logger.warning("Item ignoré: company name manquant.")
            return item

        payload = json.dumps(message, ensure_ascii=False)
        self.channel.basic_publish(
            exchange="",
            routing_key=ADD_COMPANY_QUEUE,
            body=payload,
        )
        spider.logger.info("Company envoyée vers %s: %s", ADD_COMPANY_QUEUE, message["data"]["name"])
        return item
