import re

import scrapy


def extract_charika_address(response) -> str | None:
    address = response.xpath(
        'normalize-space(//b[contains(normalize-space(.), "Adresse")]/following::label[1]/text())'
    ).get()
    if address:
        return address.strip()
    return None


def city_from_address(address: str | None) -> str | None:
    if not address:
        return None

    parts = [part.strip() for part in address.split("-") if part.strip()]
    if not parts:
        return None

    city = parts[-1].strip()
    if len(city) < 2:
        return None

    return city.title()


class CharikaSpider(scrapy.Spider):
    """Collecte fiches entreprises depuis charika.ma."""

    name = "charika"
    category = "collectors"

    def __init__(self, url=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not url:
            raise ValueError("CharikaSpider requiert url=...")
        self.start_urls = [url]

    def parse(self, response):
        print(f"\n[CharikaSpider] Scraping: {response.url}")

        raw_title = response.xpath("//title/text()").get() or ""
        company_name = re.split(r"(?i)\s*-\s*charika|\s*-\s*fiche|\s*\|", raw_title)[0].strip()

        if ":" in company_name and "Identité" in company_name:
            company_name = company_name.split(":", 1)[-1].strip()

        company_name = re.sub(
            r"(?i)^.*?fiche\s+d['’]?identit[ée]\s+soci[ée]t[ée]\s*[:\-\s]*",
            "",
            company_name,
        ).strip()

        translate_lower = 'translate(text(), "ACTIVÉ", "activé")'
        h2_text = response.xpath(
            f'//b[contains({translate_lower}, "activit")]/following-sibling::h2[1]//text()'
        ).get()

        xpath_sector = None
        if h2_text and len(h2_text.strip()) > 3:
            xpath_sector = h2_text
        else:
            text_node = response.xpath(
                f'//b[contains({translate_lower}, "activit")]/following-sibling::text()[1]'
            ).get()
            if text_node and len(text_node.strip()) > 3:
                xpath_sector = text_node

        if xpath_sector:
            xpath_sector = re.sub(r"[\r\n\t]+", " ", xpath_sector).strip().strip('":- ').strip()

        xpath_query = (
            '//body//text()[not(ancestor::script|ancestor::style|'
            "ancestor::nav|ancestor::header|ancestor::footer)]"
        )
        raw_elements = response.xpath(xpath_query).getall()
        clean_text = " . ".join(t.strip() for t in raw_elements if t.strip())

        address = extract_charika_address(response)
        city = city_from_address(address)

        print(f"[CharikaSpider] Entreprise: {company_name}")
        if city:
            print(f"[CharikaSpider] Ville: {city}")

        yield {
            "source": "charika",
            "category": self.category,
            "source_url": response.url,
            "company_name": company_name,
            "html_sector": xpath_sector,
            "city": city,
            "address": address,
            "full_text": clean_text,
            "status": "ready_for_ai",
        }
