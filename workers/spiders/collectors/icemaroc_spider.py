import json
from urllib.parse import quote

import scrapy

API_BASE = "https://www.icemaroc.com/api/search.php"


class IcemarocSpider(scrapy.Spider):
    """Collecte entreprises depuis l'API icemaroc.com."""

    name = "icemaroc"
    category = "collectors"

    def __init__(self, url=None, query=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if url:
            self.start_urls = [url]
        elif query:
            self.start_urls = [f"{API_BASE}?query={quote(query)}"]
        else:
            raise ValueError("IcemarocSpider requiert url= ou query=")

    def parse(self, response):
        print(f"\n[IcemarocSpider] API: {response.url}")

        try:
            data = response.json()
        except json.JSONDecodeError:
            print("[IcemarocSpider] Réponse JSON invalide.")
            return

        if not data:
            print("[IcemarocSpider] Aucun résultat.")
            return

        entreprise = data[0]
        company_name = entreprise.get("raison_sociale", "").strip()
        ice = entreprise.get("ice", "").strip()
        rc = entreprise.get("num_rc", "").strip()
        city = entreprise.get("ville_rc", "").strip()
        capital = entreprise.get("capital", "").strip()
        raw_sector = entreprise.get("activite", "")
        clean_sector = " ".join(raw_sector.split()).strip("- ")

        print(f"[IcemarocSpider] Trouvé: {company_name} | ICE: {ice}")

        yield {
            "source": "icemaroc",
            "category": self.category,
            "source_url": response.url,
            "company_name": company_name,
            "html_sector": clean_sector,
            "ice": ice,
            "rc": rc,
            "city": city,
            "capital": capital,
            "full_text": "",
            "status": "ready_for_ai",
        }
