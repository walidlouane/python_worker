import re


class DataCleaningPipeline:
    PHONE_PATTERN = re.compile(
        r"(?:\+212|0)\s*(?:\(?\d{1,2}\)?[\s\-\.]*)?"
        r"\d{2}[\s\-\.]?\d{2}[\s\-\.]?\d{2}[\s\-\.]?\d{2}"
    )
    ICE_PATTERN = re.compile(r"\bICE\s*[:\-]?\s*(\d{15})\b", re.IGNORECASE)
    RC_PATTERN = re.compile(r"\bRC\s*[:\-]?\s*(\d{1,10})\b", re.IGNORECASE)
    SECTOR_PATTERN = re.compile(
        r"(?i)(?:secteur d['’]\s*)?activit[ée]s?\s*[:\-]?\s*(?:\.\s*)?([^\.]{5,150})"
    )
    CITY_PATTERN = re.compile(
        r"(?i)(?:ville|city|localit[ée])\s*[:\-]\s*([A-Za-zÀ-ÿ'\-\s]{2,60})"
    )

    @staticmethod
    def _normalize_city(value):
        city = re.sub(r"\s+", " ", value or "").strip(" .,-")
        if not city or city.lower() in {"unknown", "n/a", "na"}:
            return None
        return city.title()

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
        item["full_text"] = full_text

        if not item.get("phones"):
            phones = []
            for match in self.PHONE_PATTERN.findall(full_text):
                normalized = self._normalize_phone(match)
                if normalized not in phones:
                    phones.append(normalized)
            item["phones"] = phones

        if not item.get("ice"):
            ice_match = self.ICE_PATTERN.search(full_text)
            item["ice"] = ice_match.group(1) if ice_match else None

        if not item.get("rc"):
            rc_match = self.RC_PATTERN.search(full_text)
            item["rc"] = rc_match.group(1) if rc_match else None

        if not item.get("sector"):
            sector_match = self.SECTOR_PATTERN.search(full_text)
            item["sector"] = sector_match.group(1).strip() if sector_match else None

        if not item.get("html_sector") and item.get("sector"):
            item["html_sector"] = item["sector"]

        if not item.get("city"):
            city_match = self.CITY_PATTERN.search(full_text)
            if city_match:
                item["city"] = self._normalize_city(city_match.group(1))
        elif item.get("city"):
            item["city"] = self._normalize_city(item["city"])

        item["cleaning_status"] = "cleaned"
        item.setdefault("status", "ready_for_ai")
        return item
