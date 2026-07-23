import json
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from uuid import uuid4

import pika

from config import (
    DEFAULT_SOURCE,
    HEARTBEAT_INTERVAL_SECONDS,
    RABBITMQ_URL,
    URL_TO_CRAWL_QUEUE,
)
from pipelines.heartbeat import publish_heartbeat
from pipelines.register import publish_spider_registrations

WORKERS_DIR = Path(__file__).resolve().parent


class WorkerState:
    def __init__(self):
        self.lock = threading.Lock()
        self.status = "IDLE"
        self.spider_name = None
        self.current_url = None
        self.job_id = None
        self.processed_jobs = 0
        self.failed_jobs = 0

    def snapshot(self):
        with self.lock:
            return {
                "status": self.status,
                "spider_name": self.spider_name,
                "current_url": self.current_url,
                "job_id": self.job_id,
                "processed_jobs": self.processed_jobs,
                "failed_jobs": self.failed_jobs,
            }

    def set_idle(self):
        with self.lock:
            self.status = "IDLE"
            self.spider_name = None
            self.current_url = None
            self.job_id = None

    def set_running(self, source: str, url: str | None, query: str | None):
        with self.lock:
            self.status = "RUNNING"
            self.spider_name = source
            self.current_url = url or query
            self.job_id = f"run_{uuid4()}"

    def mark_success(self):
        with self.lock:
            self.processed_jobs += 1
            self.status = "IDLE"
            self.spider_name = None
            self.current_url = None
            self.job_id = None

    def mark_failure(self):
        with self.lock:
            self.failed_jobs += 1
            self.status = "ERROR"
            self.spider_name = None
            self.current_url = None
            self.job_id = None


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


def wait_for_rabbitmq(retries: int = 30, delay: float = 2.0) -> None:
    for attempt in range(1, retries + 1):
        try:
            connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
            connection.close()
            return
        except pika.exceptions.AMQPConnectionError:
            print(f"RabbitMQ indisponible ({attempt}/{retries}), nouvel essai dans {delay}s...")
            time.sleep(delay)

    raise SystemExit("Impossible de se connecter à RabbitMQ.")


def send_heartbeat(state: WorkerState) -> None:
    snapshot = state.snapshot()
    publish_heartbeat(
        snapshot["status"],
        spider_name=snapshot["spider_name"],
        current_url=snapshot["current_url"],
        job_id=snapshot["job_id"],
        processed_items=snapshot["processed_jobs"],
        failed_items=snapshot["failed_jobs"],
    )


def heartbeat_loop(state: WorkerState, stop_event: threading.Event) -> None:
    while not stop_event.wait(HEARTBEAT_INTERVAL_SECONDS):
        try:
            send_heartbeat(state)
        except Exception as error:
            print(f"[heartbeat] Erreur: {error}")


def start_worker():
    state = WorkerState()
    stop_event = threading.Event()

    print("Tentative de connexion à RabbitMQ...")
    wait_for_rabbitmq()
    publish_spider_registrations()
    send_heartbeat(state)

    heartbeat_thread = threading.Thread(
        target=heartbeat_loop,
        args=(state, stop_event),
        daemon=True,
    )
    heartbeat_thread.start()

    connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
    channel = connection.channel()
    channel.queue_declare(queue=URL_TO_CRAWL_QUEUE, durable=True)

    print(f"[*] Connexion RÉUSSIE. En attente sur '{URL_TO_CRAWL_QUEUE}'...")

    def callback(ch, method, _properties, body):
        job = parse_job(body)
        print(f"\n[->] Job reçu: source={job.get('source')} url={job.get('url')} query={job.get('query')}")
        print("[⚙️] Lancement run_spider.py...")

        state.set_running(job.get("source", DEFAULT_SOURCE), job.get("url"), job.get("query"))
        try:
            send_heartbeat(state)
            result = subprocess.run(
                build_spider_command(job),
                check=False,
                cwd=str(WORKERS_DIR),
            )
            if result.returncode == 0:
                state.mark_success()
            else:
                state.mark_failure()
        except Exception:
            state.mark_failure()
            raise
        finally:
            try:
                send_heartbeat(state)
            except Exception as error:
                print(f"[heartbeat] Erreur: {error}")
            ch.basic_ack(delivery_tag=method.delivery_tag)

    channel.basic_consume(queue=URL_TO_CRAWL_QUEUE, on_message_callback=callback)

    try:
        channel.start_consuming()
    finally:
        stop_event.set()


if __name__ == "__main__":
    start_worker()
