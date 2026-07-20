import sys
import scrapy
import json
import pika
import re
import warnings
from datetime import datetime, timezone
from scrapy.crawler import CrawlerProcess

warnings.filterwarnings("ignore", category=DeprecationWarning)

# ---------------------------------------------------------------------------
# 1. PIPELINE DE NETTOYAGE (La consigne de l'encadrant)
# ---------------------------------------------------------------------------
class DataCleaningPipeline:
    PHONE_PATTERN = re.compile(r"(?:\+212|0)\s*(?:\(?\d{1,2}\)?[\s\-\.]*)?\d{2}[\s\-\.]?\d{2}[\s\-\.]?\d{2}[\s\-\.]?\d{2}")
    ICE_PATTERN = re.compile(r"\bICE\s*[:\-]?\s*(\d{15})\b", re.IGNORECASE)
    RC_PATTERN = re.compile(r"\bRC\s*[:\-]?\s*(\d{1,10})\b", re.IGNORECASE)
    
    # NOUVEAU : Regex super puissante pour l'Activité
    # Elle gère "Activité :", "Secteur d'activité :", et ignore les points insérés par Scrapy
    SECTOR_PATTERN = re.compile(r"(?i)(?:secteur d['’]\s*)?activit[ée]s?\s*[:\-]?\s*(?:\.\s*)?([^\.]{5,150})")

    @staticmethod
    def _normalize_text(text):
        return re.sub(r"\s+", " ", text or "").strip()

    @staticmethod
    def _normalize_phone(phone):
        digits = re.sub(r"\D", "", phone)
        if digits.startswith("212") and len(digits) >= 12:
            digits = "0" + digits[3:]
        return digits

    def process_item(self, item, spider):
        full_text = self._normalize_text(item.get("full_text", ""))

        phones = []
        for match in self.PHONE_PATTERN.findall(full_text):
            normalized = self._normalize_phone(match)
            if normalized not in phones:
                phones.append(normalized)

        ice_match = self.ICE_PATTERN.search(full_text)
        rc_match = self.RC_PATTERN.search(full_text)
        
        # NOUVEAU : Extraction du Secteur
        sector_match = self.SECTOR_PATTERN.search(full_text)
        sector = sector_match.group(1).strip() if sector_match else None

        item["full_text"] = full_text
        item["phones"] = phones
        item["ice"] = ice_match.group(1) if ice_match else None
        item["rc"] = rc_match.group(1) if rc_match else None
        item["sector"] = sector  # NOUVEAU : On l'ajoute au message pour RabbitMQ !
        item["cleaning_status"] = "cleaned"
        
        return item

# ---------------------------------------------------------------------------
# 2. PIPELINE D'EXPÉDITION (Connexion RabbitMQ)
# ---------------------------------------------------------------------------
class RabbitMQPipeline:
    def open_spider(self, spider):
        parameters = pika.URLParameters("amqp://guest:guest@127.0.0.1:5672/%2F")
        self.connection = pika.BlockingConnection(parameters)
        self.channel = self.connection.channel()
        self.channel.queue_declare(queue="document_queue", durable=True)

    def close_spider(self, spider):
        if getattr(self, "connection", None) and not self.connection.is_closed:
            self.connection.close()

    def process_item(self, item, spider):
        payload = json.dumps(item, ensure_ascii=False)
        self.channel.basic_publish(exchange="", routing_key="document_queue", body=payload)
        spider.logger.info("✅ Données nettoyées envoyées dans document_queue")
        return item


# ---------------------------------------------------------------------------
# 3. LE SPIDER (Extraction des balises)
# ---------------------------------------------------------------------------
class UniversalSpider(scrapy.Spider):
    name = 'universal_spider'

    def __init__(self, url=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.start_urls = [url] if url else ['https://quotes.toscrape.com']

    def parse(self, response):
        print(f"\n[⚙️ Scrapy] Scraping agressif activé sur : {response.url}")

        # --- 1. EXTRACTION DU NOM (HACHOIR ABSOLU) ---
        raw_title = response.xpath('//title/text()').get() or ""
        
        # Découpage classique sur les suffixes
        company_name = re.split(r'(?i)\s*-\s*charika|\s*-\s*fiche|\s*\|', raw_title)[0].strip()
        
        # Si on détecte "Fiche d'identité", on coupe brutalement aux deux-points (:)
        if ":" in company_name and "Identité" in company_name:
            company_name = company_name.split(':', 1)[-1].strip()
            
        # Sécurité supplémentaire pour nettoyer le préfixe s'il reste des morceaux
        company_name = re.sub(r"(?i)^.*?fiche\s+d['’]?identit[ée]\s+soci[ée]t[ée]\s*[:\-\s]*", "", company_name).strip()

        # --- 2. EXTRACTION DU SECTEUR (D'après ton Screenshot) ---
        xpath_sector = None
        
        # Astuce XPath pour ignorer les majuscules/minuscules
        translate_lower = 'translate(text(), "ACTIVÉ", "activé")'
        
        # Tentative principale : On cherche le <b>Activité :</b>, puis on regarde le texte DANS le <h2> qui le suit
        h2_text = response.xpath(f'//b[contains({translate_lower}, "activit")]/following-sibling::h2[1]//text()').get()
        
        if h2_text and len(h2_text.strip()) > 3:
            xpath_sector = h2_text
        else:
            # Fallback : Si ce n'est pas dans un <h2>, mais juste posé à côté
            text_node = response.xpath(f'//b[contains({translate_lower}, "activit")]/following-sibling::text()[1]').get()
            if text_node and len(text_node.strip()) > 3:
                xpath_sector = text_node

        if xpath_sector:
            # Nettoyage des espaces, retours à la ligne et des guillemets inutiles
            xpath_sector = re.sub(r'[\r\n\t]+', ' ', xpath_sector).strip()
            xpath_sector = xpath_sector.strip('":- ').strip()

        # --- 3. EXTRACTION DU TEXTE BRUT ---
        xpath_query = '//body//text()[not(ancestor::script|ancestor::style|ancestor::nav|ancestor::header|ancestor::footer)]'
        raw_elements = response.xpath(xpath_query).getall()
        clean_text = ' . '.join([t.strip() for t in raw_elements if t.strip()])
        
        print(f"[🕷️ Scrapy] Entreprise : {company_name}")
        if xpath_sector:
            print(f"[🕷️ Scrapy] Secteur trouvé via HTML : {xpath_sector}")

        # --- 4. ENVOI À RABBITMQ ---
        yield {
            "source_url": response.url,
            "company_name": company_name,
            "html_sector": xpath_sector, # La donnée propre part vers l'IA
            "full_text": clean_text,
            "status": "ready_for_ai",
        }
# ---------------------------------------------------------------------------
# 4. LANCEMENT ET CONFIGURATION ANTI-BAN
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    target_url = sys.argv[1] if len(sys.argv) > 1 else 'https://quotes.toscrape.com'
    
    process = CrawlerProcess(settings={
        'USER_AGENT': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'LOG_LEVEL': 'WARNING',
        'REQUEST_FINGERPRINTER_IMPLEMENTATION': '2.7',
        
        # --- SÉCURITÉ ANTI-BAN POUR LE SCRAPING DE MASSE ---
        'DOWNLOAD_DELAY': 2.0,
        'RANDOMIZE_DOWNLOAD_DELAY': True,
        'CONCURRENT_REQUESTS': 2,
        'CONCURRENT_REQUESTS_PER_DOMAIN': 1,
        'AUTOTHROTTLE_ENABLED': True,
        'AUTOTHROTTLE_START_DELAY': 2.0,
        'AUTOTHROTTLE_MAX_DELAY': 30.0,
        'AUTOTHROTTLE_TARGET_CONCURRENCY': 0.5,
        'RETRY_ENABLED': True,
        'RETRY_TIMES': 2,
        'DOWNLOAD_TIMEOUT': 30,
        
        # --- ORDRE DES PIPELINES (CRUCIAL) ---
        'ITEM_PIPELINES': {
            '__main__.DataCleaningPipeline': 300, # 1. On nettoie d'abord (Priorité 300)
            '__main__.RabbitMQPipeline': 800,     # 2. On expédie ensuite (Priorité 800)
        },
    })
    
    process.crawl(UniversalSpider, url=target_url)
    process.start()