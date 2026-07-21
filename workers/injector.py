import argparse
import json

import pika

from config import RABBITMQ_URL, URL_TO_CRAWL_QUEUE


def build_urls(base_url, start_id, end_id):
    for identifier in range(start_id, end_id + 1):
        yield f"{base_url.rstrip('/')}/societe-{identifier}"


def inject_jobs(source, base_url, start_id, end_id, query=None):
    connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
    channel = connection.channel()
    channel.queue_declare(queue=URL_TO_CRAWL_QUEUE, durable=True)

    total = 0

    if source == "icemaroc" and query:
        payload = json.dumps({"source": "icemaroc", "query": query})
        channel.basic_publish(exchange="", routing_key=URL_TO_CRAWL_QUEUE, body=payload)
        total = 1
        print(f"[injector] Job ICE Maroc poussé: query={query}")
    else:
        for url in build_urls(base_url, start_id, end_id):
            payload = json.dumps({"source": source, "url": url})
            channel.basic_publish(exchange="", routing_key=URL_TO_CRAWL_QUEUE, body=payload)
            total += 1
            print(f"[injector] Job poussé: source={source} url={url}")

    connection.close()
    print(f"[injector] Terminé: {total} job(s) envoyé(s) vers {URL_TO_CRAWL_QUEUE}")


def parse_args():
    parser = argparse.ArgumentParser(description="Injecteur de jobs crawl (multi-sources)")
    parser.add_argument("--source", default="charika", choices=["charika", "icemaroc"])
    parser.add_argument("--base-url", default="https://charika.ma", help="Base URL Charika")
    parser.add_argument("--start", type=int, help="Premier identifiant Charika")
    parser.add_argument("--end", type=int, help="Dernier identifiant Charika")
    parser.add_argument("--query", help="Requête ICE Maroc (ex: alamitec)")
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()

    if arguments.source == "icemaroc":
        if not arguments.query:
            raise SystemExit("ICE Maroc requiert --query (ex: --query alamitec)")
        inject_jobs("icemaroc", arguments.base_url, 0, 0, query=arguments.query)
    else:
        if arguments.start is None or arguments.end is None:
            raise SystemExit("Charika requiert --start et --end")
        inject_jobs(arguments.source, arguments.base_url, arguments.start, arguments.end)
