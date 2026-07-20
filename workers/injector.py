import argparse

import pika


def build_urls(base_url, start_id, end_id):
    for identifier in range(start_id, end_id + 1):
        yield f"{base_url.rstrip('/')}/societe-{identifier}"


def inject_urls(base_url, start_id, end_id):
    parameters = pika.URLParameters("amqp://guest:guest@127.0.0.1:5672/%2F")
    connection = pika.BlockingConnection(parameters)
    channel = connection.channel()
    channel.queue_declare(queue="url_to_crawl", durable=True)

    total = 0
    for url in build_urls(base_url, start_id, end_id):
        channel.basic_publish(exchange="", routing_key="url_to_crawl", body=url)
        total += 1
        print(f"[injector] URL poussée: {url}")

    connection.close()
    print(f"[injector] Terminé: {total} URL(s) envoyée(s) vers url_to_crawl")


def parse_args():
    parser = argparse.ArgumentParser(description="Injecteur d'URLs incrémentales pour Charika")
    parser.add_argument("--base-url", default="https://charika.ma", help="Base URL du site")
    parser.add_argument("--start", type=int, required=True, help="Premier identifiant incrémental")
    parser.add_argument("--end", type=int, required=True, help="Dernier identifiant incrémental")
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    inject_urls(arguments.base_url, arguments.start, arguments.end)