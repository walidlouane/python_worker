"""
Worker IDP (Intelligent Document Processing) — version 100% locale.

Architecture :
    RabbitMQ (full_text) -> [1] Regex (ICE/RC/Téléphone/Capital/Secteur)
                          -> [2] GLiNER (extraction brute)
                          -> [3] Scoring de saillance & Fallback Scrapy
                          -> Fusion -> JSON structuré
"""

from __future__ import annotations

import json
import logging
import os
import re
import warnings
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import pika
from pydantic import BaseModel, Field

warnings.filterwarnings("ignore")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("ai_worker")

# ---------------------------------------------------------------------------
# 0. CONFIGURATION
# ---------------------------------------------------------------------------

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@127.0.0.1:5672/%2F")
QUEUE_NAME = os.getenv("IDP_QUEUE_NAME", "document_queue")

GLINER_MODEL_NAME = os.getenv("GLINER_MODEL_NAME", "urchade/gliner_small-v2.1")
GLINER_LABELS = ["company", "person", "address", "city", "sector", "position", "capital"]
GLINER_THRESHOLD = float(os.getenv("GLINER_THRESHOLD", "0.40"))

CHUNK_SIZE_CHARS = 1200
CHUNK_OVERLAP_CHARS = 200

ANCHOR_PROXIMITY_SCALE = 300
CLUSTER_WINDOW_CHARS = 400
CLUSTER_MIN_COUNT = 3
CLUSTER_PENALTY_FACTOR = 0.15

MIN_ACCEPT_SCORE = 0.20

MIN_WORDS_BY_LABEL = {
    "ADDRESS": 3,
    "PERSON": 2,
}

_STRUCTURAL_LABEL_PATTERN = re.compile(
    r"\b(adresse|activit[ée]|t[ée]l(?:[ée]phone)?|fax|secteur|ville|"
    r"forme\s+juridique|capital|raison\s+sociale|directeur|g[ée]rant)\b",
    re.IGNORECASE,
)

_ADDRESS_SUFFIX_PATTERN = re.compile(
    r'^[\s,]*-\s*'                                         
    r'(?P<city>[A-ZÀ-ÿa-z]+(?:[\s\-]+[A-ZÀ-ÿa-z]+){0,2})'  
    r'(?:\s*\([A-Z]{1,3}\))?'                              
    r'(?=[\s,]*(?:T[ée]l|Tel|Fax|GSM|0[5-7]|\+212|ICE|RC|Patente|IF|-|$))', 
    re.IGNORECASE
)

# CORRECTIONS REGEX
# Capital : Tolère jusqu'à 50 caractères de bruit (ex: " social . \n ") entre le mot et le chiffre
_CAPITAL_PATTERN = re.compile(r"(?i)capital[^0-9]{0,50}?([0-9][\d\s\.,\xa0]{2,30}(?:dhs?|mad|dirhams?))")
# Secteur : Capture tout après "Activité" jusqu'au prochain point inséré par Scrapy ( \. )
_SECTOR_PATTERN = re.compile(r"(?i)activit[ée]s?[^a-zA-Z0-9]+((?:(?!\s\.\s).)+)")

# ---------------------------------------------------------------------------
# 1. MODELE DE SORTIE
# ---------------------------------------------------------------------------

class Director(BaseModel):
    name: str
    position: Optional[str] = None

class FinalExtraction(BaseModel):
    source_url: Optional[str] = None
    company: Optional[str] = None
    directors: List[Director] = Field(default_factory=list)
    address: Optional[str] = None
    city: Optional[str] = None
    sector: Optional[str] = None
    phone: List[str] = Field(default_factory=list)
    ice: Optional[str] = None
    rc: Optional[str] = None
    capital: Optional[str] = None

# ---------------------------------------------------------------------------
# 2. MODULE REGEX
# ---------------------------------------------------------------------------

_ICE_PATTERN = re.compile(r"\b\d{15}\b")
_RC_PATTERN = re.compile(r"(?i)r\.?c\.?\s*:?\s*(\d+)")
_PHONE_PATTERN = re.compile(r"(?:(?:\+|00)212|0)\s*[5-7](?:\s*\d{2}){4}")

@dataclass
class Identifiers:
    ice: Optional[str] = None
    rc: Optional[str] = None
    phones: List[str] = field(default_factory=list)
    anchor_positions: List[int] = field(default_factory=list)

def extract_identifiers(raw_text: str) -> Identifiers:
    anchors: List[int] = []
    text_length = len(raw_text)

    ice_match = _ICE_PATTERN.search(raw_text)
    ice = ice_match.group(0) if ice_match else None
    if ice_match: anchors.append(ice_match.start())

    rc_match = _RC_PATTERN.search(raw_text)
    rc = rc_match.group(1) if rc_match else None
    if rc_match: anchors.append(rc_match.start())

    phones: List[str] = []
    for m in _PHONE_PATTERN.finditer(raw_text):
        if m.start() < text_length * 0.85:
            phones.append(m.group(0).replace(" ", ""))
            anchors.append(m.start())

    for m in _STRUCTURAL_LABEL_PATTERN.finditer(raw_text):
        anchors.append(m.start())
        
    cap_match = _CAPITAL_PATTERN.search(raw_text)
    if cap_match:
        anchors.append(cap_match.start())

    return Identifiers(ice=ice, rc=rc, phones=list(dict.fromkeys(phones)), anchor_positions=anchors)

# ---------------------------------------------------------------------------
# 3. MODULE GLiNER
# ---------------------------------------------------------------------------

@dataclass
class RawEntity:
    label: str
    text: str
    start: int
    end: int
    score: float

_GLINER_MODEL = None

def _load_gliner_model():
    global _GLINER_MODEL
    if _GLINER_MODEL is None:
        logger.info("Chargement du modèle GLiNER '%s'...", GLINER_MODEL_NAME)
        from gliner import GLiNER
        _GLINER_MODEL = GLiNER.from_pretrained(GLINER_MODEL_NAME)
    return _GLINER_MODEL

def _sliding_windows(text: str, size: int, overlap: int) -> List[Tuple[int, str]]:
    if len(text) <= size: return [(0, text)]
    windows = []
    step = size - overlap
    for start in range(0, len(text), step):
        chunk = text[start:start + size]
        if chunk.strip(): windows.append((start, chunk))
        if start + size >= len(text): break
    return windows

def run_gliner_extraction(raw_text: str) -> List[RawEntity]:
    model = _load_gliner_model()
    raw_entities: List[RawEntity] = []
    seen: set = set()

    for window_offset, chunk in _sliding_windows(raw_text, CHUNK_SIZE_CHARS, CHUNK_OVERLAP_CHARS):
        entities = model.predict_entities(chunk, GLINER_LABELS, threshold=GLINER_THRESHOLD)

        for ent in entities:
            global_start = window_offset + ent["start"]
            global_end = window_offset + ent["end"]
            key = (ent["label"].upper(), global_start, global_end)
            if key in seen: continue
            seen.add(key)

            txt = ent["text"].strip()
            if len(txt) < 3: continue

            label_upper = ent["label"].upper()
            min_words = MIN_WORDS_BY_LABEL.get(label_upper)
            if min_words and len(txt.split()) < min_words: continue

            if label_upper == "COMPANY" and len(txt.split()) == 1 and txt.islower():
                continue
                
            formes_juridiques = ["société anonyme", "societe anonyme", "sarl", "s.a.r.l", "s.a", "s.n.c", "succursale"]
            if label_upper == "COMPANY" and txt.lower() in formes_juridiques:
                continue

            raw_entities.append(
                RawEntity(label=label_upper, text=txt, start=global_start, end=global_end, score=float(ent.get("score", 0.0)))
            )

    return raw_entities

# ---------------------------------------------------------------------------
# 4. MODULE DE SCORING
# ---------------------------------------------------------------------------

def _distance_to_nearest_anchor(position: int, anchors: List[int]) -> float:
    if not anchors: return float(position)
    return float(min(abs(position - a) for a in anchors))

def _flag_list_clusters(entities: List[RawEntity]) -> Dict[int, bool]:
    in_cluster = {i: False for i in range(len(entities))}
    by_label: Dict[str, List[int]] = {}
    
    for i, ent in enumerate(entities):
        if ent.label == "PERSON":
            continue
        by_label.setdefault(ent.label, []).append(i)

    for label, indices in by_label.items():
        indices_sorted = sorted(indices, key=lambda i: entities[i].start)
        for pos in range(len(indices_sorted)):
            i = indices_sorted[pos]
            center = entities[i].start
            neighbours = 1
            for other_pos in range(len(indices_sorted)):
                if other_pos == pos: continue
                j = indices_sorted[other_pos]
                if abs(entities[j].start - center) <= CLUSTER_WINDOW_CHARS: neighbours += 1
            if neighbours >= CLUSTER_MIN_COUNT: in_cluster[i] = True
    return in_cluster

def _composite_score(entity: RawEntity, anchors: List[int], is_clustered: bool, text_length: int) -> float:
    if entity.start > text_length * 0.85:
        return 0.0

    distance = _distance_to_nearest_anchor(entity.start, anchors)
    proximity_factor = 1.0 / (1.0 + distance / ANCHOR_PROXIMITY_SCALE)
    cluster_factor = CLUSTER_PENALTY_FACTOR if is_clustered else 1.0
    
    return entity.score * proximity_factor * cluster_factor

@dataclass
class ScoredCandidate:
    text: str
    start: int
    end: int
    score: float
    is_clustered: bool

def disambiguate(entities: List[RawEntity], anchors: List[int], text_length: int) -> Dict[str, List[ScoredCandidate]]:
    cluster_flags = _flag_list_clusters(entities)
    scored: Dict[str, List[ScoredCandidate]] = {
        label: [] for label in ["COMPANY", "PERSON", "ADDRESS", "CITY", "SECTOR", "POSITION", "CAPITAL"]
    }

    for i, ent in enumerate(entities):
        score = _composite_score(ent, anchors, cluster_flags[i], text_length)
        scored.setdefault(ent.label, []).append(
            ScoredCandidate(ent.text, ent.start, ent.end, score, cluster_flags[i])
        )

    for label in scored: scored[label].sort(key=lambda c: c.score, reverse=True)
    return scored

def _spans_overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return not (a_end <= b_start or b_end <= a_start)

def select_final_entities(scored: Dict[str, List[ScoredCandidate]], raw_text: str = "") -> Dict[str, object]:
    def best_single(label: str, exclude_spans: Optional[List[Tuple[int, int]]] = None) -> Tuple[Optional[str], Optional[Tuple[int, int]]]:
        exclude_spans = exclude_spans or []
        for c in scored.get(label, []):
            if any(_spans_overlap(c.start, c.end, s0, s1) for s0, s1 in exclude_spans): continue
            if c.is_clustered or c.score < MIN_ACCEPT_SCORE: return None, None
            return c.text, (c.start, c.end)
        return None, None

    directors_mapped = []
    people = [c for c in scored.get("PERSON", []) if not c.is_clustered and c.score >= MIN_ACCEPT_SCORE]
    positions = [c for c in scored.get("POSITION", []) if not c.is_clustered and c.score >= MIN_ACCEPT_SCORE]
    
    seen_names = set()
    for p in people:
        name_lower = p.text.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)
        
        best_pos = None
        min_dist = 100
        
        # 1. Tentative avec l'IA GLiNER
        for pos in positions:
            dist = abs(p.start - pos.start)
            if dist < min_dist:
                min_dist = dist
                best_pos = pos.text
                
        # 2. Fallback structurel (Nom -> Scrapy séparateur -> Fonction)
        if not best_pos and raw_text:
            idx = raw_text.find(p.text)
            if idx != -1:
                snippet = raw_text[idx + len(p.text) : idx + len(p.text) + 80]
                snippet = re.sub(r'^[\s\.\-:]+', '', snippet)
                pos_text = re.split(r'\s\.\s|\s-\s|\sM\.', snippet)[0].strip()
                if 3 < len(pos_text) < 50:
                    best_pos = pos_text
                    
        directors_mapped.append({"name": p.text, "position": best_pos})

    address_text, address_span = best_single("ADDRESS")
    city_text = None

    if address_text and address_span and raw_text:
        rest_of_text = raw_text[address_span[1] : address_span[1] + 150]
        line_end = rest_of_text.find('\n')
        lookahead = rest_of_text[:line_end] if line_end != -1 else rest_of_text
        
        match = _ADDRESS_SUFFIX_PATTERN.match(lookahead)
        if match:
            city_text = match.group("city").strip()
            if city_text.isupper() or city_text.islower():
                city_text = city_text.title()
            address_text += lookahead[:match.end()].rstrip()

    if not city_text and address_span:
        for c in scored.get("CITY", []):
            if _spans_overlap(c.start, c.end, address_span[0], address_span[1]):
                if c.end >= address_span[1] - 30:
                    city_text = c.text
                    break
                
    if not city_text:
        city_text, _ = best_single("CITY")

    company_text, _ = best_single("COMPANY")
    
    sector_text = None
    if raw_text:
        sec_match = _SECTOR_PATTERN.search(raw_text)
        if sec_match:
            sector_text = sec_match.group(1).strip()
            if len(sector_text) < 5:
                sector_text = None
                
    if not sector_text:
        sector_text, _ = best_single("SECTOR")
    
    # CORRECTION CAPITAL : Nettoyage complet
    capital_text = None
    if raw_text:
        cap_match = _CAPITAL_PATTERN.search(raw_text)
        if cap_match:
            capital_text = cap_match.group(1)
            # Nettoyage des espaces insécables et normalisation des retours à la ligne
            capital_text = capital_text.replace('\xa0', ' ').strip()
            capital_text = re.sub(r'\s+', ' ', capital_text)
            
    if not capital_text:
        capital_text, _ = best_single("CAPITAL")

    return {
        "company": company_text,
        "address": address_text,
        "city": city_text,
        "sector": sector_text,
        "directors": directors_mapped,
        "capital": capital_text
    }

# ---------------------------------------------------------------------------
# 5. PIPELINE COMPLET
# ---------------------------------------------------------------------------

def process_raw_text(raw_text: str, source_url: Optional[str] = None) -> FinalExtraction:
    identifiers = extract_identifiers(raw_text)
    raw_entities = run_gliner_extraction(raw_text)
    scored = disambiguate(raw_entities, identifiers.anchor_positions, len(raw_text))
    selected = select_final_entities(scored, raw_text)

    return FinalExtraction(
        source_url=source_url,
        company=selected["company"],
        directors=[Director(**d) for d in selected["directors"]],
        address=selected["address"],
        city=selected["city"],
        sector=selected["sector"],
        phone=identifiers.phones[:2],
        ice=identifiers.ice,
        rc=identifiers.rc,
        capital=selected["capital"]
    )

# ---------------------------------------------------------------------------
# 6. CONSOMMATEUR RABBITMQ
# ---------------------------------------------------------------------------

def parse_message_body(body: bytes) -> Tuple[str, Optional[str]]:
    decoded = body.decode("utf-8", errors="replace")
    try:
        payload = json.loads(decoded)
    except json.JSONDecodeError:
        return decoded, None

    if isinstance(payload, dict):
        raw_text = payload.get("full_text") or payload.get("raw_text") or ""
        source_url = payload.get("source_url")
        return raw_text, source_url

    return decoded, None

def on_message(channel, method, properties, body):
    try:
        raw_text, source_url = parse_message_body(body)

        if not raw_text or not raw_text.strip():
            logger.warning("Message vide reçu, acquittement sans traitement.")
            channel.basic_ack(delivery_tag=method.delivery_tag)
            return

        logger.info("Traitement de : %s", source_url or "(source inconnue)")
        extraction = process_raw_text(raw_text, source_url=source_url)

        print(json.dumps(extraction.model_dump(), ensure_ascii=False, indent=2))
        channel.basic_ack(delivery_tag=method.delivery_tag)

    except Exception:
        logger.exception("Échec du traitement du message — renvoi en file (requeue).")
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

def main():
    _load_gliner_model()
    parameters = pika.URLParameters(RABBITMQ_URL)
    connection = pika.BlockingConnection(parameters)
    channel = connection.channel()
    channel.queue_declare(queue=QUEUE_NAME, durable=True)
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue=QUEUE_NAME, on_message_callback=on_message)

    logger.info("Worker IDP démarré. En attente sur '%s'...", QUEUE_NAME)

    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        logger.info("Arrêt demandé, fermeture propre de la connexion.")
        channel.stop_consuming()
    finally:
        connection.close()

if __name__ == "__main__":
    main()