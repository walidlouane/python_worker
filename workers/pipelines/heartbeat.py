import json
import logging
import os
import socket
from datetime import datetime, timezone
from uuid import uuid4

import pika

from config import RABBITMQ_URL, SCRAPER_HEARTBEAT_QUEUE, WORKER_ID, WORKER_VERSION

logger = logging.getLogger(__name__)


def _memory_mb() -> int | None:
    try:
        with open("/proc/self/status", encoding="utf-8") as status_file:
            for line in status_file:
                if line.startswith("VmRSS:"):
                    kb = int(line.split()[1])
                    return max(1, kb // 1024)
    except OSError:
        pass

    try:
        import psutil

        return max(1, int(psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)))
    except Exception:
        return None


def build_heartbeat_message(
    status: str,
    *,
    spider_name: str | None = None,
    current_url: str | None = None,
    job_id: str | None = None,
    processed_items: int = 0,
    failed_items: int = 0,
) -> dict:
    data = {
        "schemaVersion": "1.0",
        "jobId": job_id or f"heartbeat_{uuid4()}",
        "traceId": f"trace_{uuid4()}",
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "workerId": WORKER_ID,
        "status": status,
        "host": socket.gethostname(),
        "version": WORKER_VERSION,
        "processedItems": processed_items,
        "failedItems": failed_items,
    }

    if spider_name:
        data["spiderName"] = spider_name
    if current_url:
        data["currentUrl"] = current_url

    memory_mb = _memory_mb()
    if memory_mb is not None:
        data["memoryMb"] = memory_mb

    return {"pattern": "scraper.heartbeat", "data": data}


def publish_heartbeat(
    status: str,
    *,
    spider_name: str | None = None,
    current_url: str | None = None,
    job_id: str | None = None,
    processed_items: int = 0,
    failed_items: int = 0,
) -> dict:
    message = build_heartbeat_message(
        status,
        spider_name=spider_name,
        current_url=current_url,
        job_id=job_id,
        processed_items=processed_items,
        failed_items=failed_items,
    )
    parameters = pika.URLParameters(RABBITMQ_URL)
    connection = pika.BlockingConnection(parameters)
    channel = connection.channel()
    channel.queue_declare(queue=SCRAPER_HEARTBEAT_QUEUE, durable=True)
    channel.basic_publish(
        exchange="",
        routing_key=SCRAPER_HEARTBEAT_QUEUE,
        body=json.dumps(message, ensure_ascii=False),
    )
    connection.close()
    logger.info("Heartbeat envoyé: status=%s worker=%s", status, WORKER_ID)
    return message
