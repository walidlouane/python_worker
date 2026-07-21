import json
import re
import subprocess
import sys
from pathlib import Path

import pika

from config import DEFAULT_SOURCE, RABBITMQ_URL, URL_TO_CRAWL_QUEUE

WORKERS_DIR = Path(__file__).resolve().parent


def parse_job(body: bytes) -> dict:
    decoded = body.decode("utf-8", errors="replace").strip()

    try:
        payload = json.loads(decoded)
        if isinstance(payload, dict):
            payload.setdefault("source", DEFAULT_SOURCE)
            return payload
    except json.JSONDecodeError:
        pass

    match = re.search(r"https?://[^\]\)]+", decoded)
    url = match.group(0) if match else decoded
    source = DEFAULT_SOURCE

    if "icemaroc.com" in url.lower():
        source = "icemaroc"

    return {"source": source, "url": url}


def build_spider_command(job: dict) -> list[str]:
    cmd = [sys.executable, "run_spider.py", "--source", job["source"]]

    if job.get("url"):
        cmd.extend(["--url", job["url"]])
    if job.get("query"):
        cmd.extend(["--query", job["query"]])

    return cmd


def start_worker():
    print("Tentative de connexion à RabbitMQ...")
    connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
    channel = connection.channel()
    channel.queue_declare(queue=URL_TO_CRAWL_QUEUE, durable=True)
    channel.queue_declare(queue="document_queue", durable=True)

    print(f"[*] Connexion RÉUSSIE. En attente sur '{URL_TO_CRAWL_QUEUE}'...")

    def callback(ch, method, _properties, body):
        job = parse_job(body)
        print(f"\n[->] Job reçu: source={job.get('source')} url={job.get('url')} query={job.get('query')}")
        print("[⚙️] Lancement run_spider.py...")

        subprocess.run(build_spider_command(job), check=False, cwd=str(WORKERS_DIR))
        ch.basic_ack(delivery_tag=method.delivery_tag)

    channel.basic_consume(queue=URL_TO_CRAWL_QUEUE, on_message_callback=callback)
    channel.start_consuming()


if __name__ == "__main__":
    start_worker()
