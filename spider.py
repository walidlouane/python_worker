import sys
import scrapy
import json
import pika
from scrapy.crawler import CrawlerProcess
import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning)

class UniversalSpider(scrapy.Spider):
    name = 'universal_spider'

    def __init__(self, url=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.start_urls = [url] if url else ['https://quotes.toscrape.com']

    def parse(self, response):
        print(f"\n[⚙️ Scrapy] Scraping agressif activé sur : {response.url}")

        # On capture TOUT le texte visible (sauf code, menus, et footer)
        # Plus aucune limite de caractères ou de balises (th, td, div...)
        xpath_query = '//body//text()[not(ancestor::script|ancestor::style|ancestor::nav|ancestor::header|ancestor::footer)]'
        
        raw_elements = response.xpath(xpath_query).getall()
        
        # NETTOYAGE ULTRA-SIMPLE : On garde TOUT ce qui n'est pas vide
        # On ne supprime plus les mots seuls !
        text_blocks = [t.strip() for t in raw_elements if t.strip()]
        
        clean_text = ' . '.join(text_blocks)
        
        print(f"[🕷️ Scrapy] Données extraites ({len(clean_text)} caractères) !")
        
        document_payload = json.dumps({
            "source_url": response.url,
            "full_text": clean_text,
            "status": "ready_for_ai"
        })

        parameters = pika.URLParameters('amqp://guest:guest@127.0.0.1:5672/%2F')
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()
        
        # On s'assure que la file existe avant d'envoyer
        channel.queue_declare(queue='document_queue', durable=True)
        
        channel.basic_publish(
            exchange='',
            routing_key='document_queue',
            body=document_payload
        )
        connection.close()
        print("[🕷️ Scrapy] Données universelles envoyées dans la file pour l'IA !")

if __name__ == '__main__':
    target_url = sys.argv[1] if len(sys.argv) > 1 else 'https://quotes.toscrape.com'
    
    process = CrawlerProcess(settings={
        'USER_AGENT': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0',
        'LOG_LEVEL': 'WARNING',
        'REQUEST_FINGERPRINTER_IMPLEMENTATION': '2.7'
    })
    
    process.crawl(UniversalSpider, url=target_url)
    process.start()