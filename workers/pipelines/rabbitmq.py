import json

import pika

from config import DOCUMENT_QUEUE, RABBITMQ_URL


class RabbitMQPipeline:
    def open_spider(self, spider):
        parameters = pika.URLParameters(RABBITMQ_URL)
        self.connection = pika.BlockingConnection(parameters)
        self.channel = self.connection.channel()
        self.channel.queue_declare(queue=DOCUMENT_QUEUE, durable=True)

    def close_spider(self, spider):
        if getattr(self, "connection", None) and not self.connection.is_closed:
            self.connection.close()

    def process_item(self, item, spider):
        payload = json.dumps(dict(item), ensure_ascii=False)
        self.channel.basic_publish(exchange="", routing_key=DOCUMENT_QUEUE, body=payload)
        spider.logger.info("Données envoyées dans %s", DOCUMENT_QUEUE)
        return item
