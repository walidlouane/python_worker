"""
Suite de tests du moteur de scoring, SANS dépendance à GLiNER.
Chaque test simule directement des RawEntity comme si GLiNER les avait
extraites, ce qui permet de valider toute la logique de désambiguïsation
sans télécharger de modèle.
"""

import sys
sys.path.insert(0, ".")

from ai_worker import RawEntity, disambiguate, select_final_entities

FAILURES = 0


def check(condition: bool, message: str):
    global FAILURES
    status = "✅" if condition else "❌ FAIL"
    print(f"{status} {message}")
    if not condition:
        FAILURES += 1


def make_raw_text(total_length: int, inserts: dict) -> str:
    """
    Construit une chaîne de `total_length` caractères remplie de 'x' (filler
    neutre, ne matche jamais le pattern de complétion d'adresse), avec des
    fragments de texte réel insérés aux offsets fournis.
    inserts: {offset: texte_à_insérer}
    """
    chars = list("x" * total_length)
    for offset, text in inserts.items():
        chars[offset:offset + len(text)] = list(text)
    return "".join(chars)


# ---------------------------------------------------------------------------
# Test 1 : bruit (menu de régions + partenaire) vs vraies données proches de l'ancre
# ---------------------------------------------------------------------------

entities_1 = [
    RawEntity("CITY", "Tanger-Tétouan-Al Hoceïma", 100, 125, 0.55),
    RawEntity("CITY", "Oriental", 140, 148, 0.50),
    RawEntity("CITY", "Fès-Meknès", 160, 170, 0.52),
    RawEntity("CITY", "Rabat-Salé-Kénitra", 190, 210, 0.51),
    RawEntity("CITY", "Béni Mellal-Khénifra", 220, 241, 0.53),
    RawEntity("CITY", "Casablanca-Settat", 260, 278, 0.60),
    RawEntity("CITY", "Marrakech-Safi", 300, 314, 0.50),
    RawEntity("CITY", "Casablanca", 4950, 4960, 0.70),
    RawEntity("COMPANY", "Bank Al-Maghrib", 50, 65, 0.65),
    RawEntity("COMPANY", "Inforisk", 700, 708, 0.40),
    RawEntity("COMPANY", "Akwa Group", 4900, 4910, 0.75),
]

raw_text_1 = make_raw_text(5100, {})
result_1 = select_final_entities(disambiguate(entities_1, anchors=[5000]), raw_text_1)

print("Test 1 : bruit vs vraies données")
check(result_1["company"] == "Akwa Group", f"company = {result_1['company']}")
check(result_1["city"] == "Casablanca", f"city = {result_1['city']}")


# ---------------------------------------------------------------------------
# Test 2 : CITY chevauche un fragment de l'ADDRESS retenue -> exclu (null)
# ---------------------------------------------------------------------------

entities_2 = [
    RawEntity("ADDRESS", "Immeuble Tafrrouti, Km 7,5 Route De Rabat Ain Sebaa", 990, 1042, 0.72),
    RawEntity("CITY", "Immeuble Tafrrouti", 990, 1009, 0.58),
]

raw_text_2 = make_raw_text(1200, {990: "Immeuble Tafrrouti, Km 7,5 Route De Rabat Ain Sebaa"})
result_2 = select_final_entities(disambiguate(entities_2, anchors=[1000]), raw_text_2)

print("\nTest 2 : chevauchement ADDRESS/CITY")
check(result_2["address"] is not None, f"address = {result_2['address']}")
check(result_2["city"] is None, f"city aurait dû être null, obtenu {result_2['city']}")


# ---------------------------------------------------------------------------
# Test 3 : SECTOR n'a que des candidats en cluster -> null, pas de faux positif
# ---------------------------------------------------------------------------

entities_3 = [
    RawEntity("SECTOR", "Représentants légaux", 8000, 8020, 0.50),
    RawEntity("SECTOR", "Représentants légaux", 8300, 8320, 0.50),
    RawEntity("SECTOR", "Représentants légaux", 8600, 8620, 0.50),
    RawEntity("SECTOR", "Représentants légaux", 8900, 8920, 0.50),
]

raw_text_3 = make_raw_text(9000, {})
result_3 = select_final_entities(disambiguate(entities_3, anchors=[1000]), raw_text_3)

print("\nTest 3 : cluster sans alternative (SECTOR)")
check(result_3["sector"] is None, f"sector = {result_3['sector']}")


# ---------------------------------------------------------------------------
# Test 4 : liste de pays éparse (seulement 2 au-dessus du seuil GLiNER)
# ---------------------------------------------------------------------------

entities_4 = [
    RawEntity("CITY", "Chypre", 200, 206, 0.45),
    RawEntity("CITY", "Chypre Du Nord", 215, 230, 0.48),
]

raw_text_4 = make_raw_text(5100, {})
result_4 = select_final_entities(disambiguate(entities_4, anchors=[5000]), raw_text_4)

print("\nTest 4 : liste de pays éparse")
check(result_4["city"] is None, f"city = {result_4['city']}")


# ---------------------------------------------------------------------------
# Test 5 : PERSON exempté du cluster (plusieurs dirigeants rapprochés = normal)
# ---------------------------------------------------------------------------

entities_5 = [
    RawEntity("PERSON", "M. Aziz Akhenouch", 5000, 5018, 0.70),
    RawEntity("PERSON", "M. Karim Bennani", 5025, 5042, 0.65),
    RawEntity("PERSON", "M. Yassine Alaoui", 5050, 5068, 0.60),
]

raw_text_5 = make_raw_text(5100, {})
result_5 = select_final_entities(disambiguate(entities_5, anchors=[5000]), raw_text_5)

print("\nTest 5 : plusieurs dirigeants rapprochés")
check(len(result_5["directors"]) == 3, f"directors = {result_5['directors']}")


# ---------------------------------------------------------------------------
# Test 6 : complétion d'adresse -> dérivation de ville (cas réel Total Energies)
# "146, Boulevard Mohamed Zerktouni - 20000" + " - Casablanca" en toute fin
# ---------------------------------------------------------------------------

addr_6 = "146, Boulevard Mohamed Zerktouni - 20000"
start_6 = 900
end_6 = start_6 + len(addr_6)
raw_text_6 = make_raw_text(
    2000,
    {start_6: addr_6, end_6: " - Casablanca Tél 0522352290"},
)

entities_6 = [RawEntity("ADDRESS", addr_6, start_6, end_6, 0.72)]
result_6 = select_final_entities(disambiguate(entities_6, anchors=[start_6]), raw_text_6)

print("\nTest 6 : complétion d'adresse (Total Energies)")
print(f"  address -> {result_6['address']}")
print(f"  city    -> {result_6['city']}")
check(result_6["address"] == f"{addr_6} - Casablanca", f"address = {result_6['address']}")
check(result_6["city"] == "Casablanca", f"city = {result_6['city']}")


# ---------------------------------------------------------------------------
# Test 7 : complétion d'adresse avec suffixe de langue à nettoyer (cas Akwa Group)
# "... Ain Sebaa" + " - Aîn-Sebaâ (AR)" -> ville = "Aîn-Sebaâ" (sans le "(AR)")
# ---------------------------------------------------------------------------

addr_7 = "Immeuble Tafrrouti, Km 7,5 Route De Rabat Ain Sebaa"
start_7 = 900
end_7 = start_7 + len(addr_7)
raw_text_7 = make_raw_text(
    2000,
    {start_7: addr_7, end_7: " - Aîn-Sebaâ (AR) Tél 0522352290"},
)

entities_7 = [RawEntity("ADDRESS", addr_7, start_7, end_7, 0.72)]
result_7 = select_final_entities(disambiguate(entities_7, anchors=[start_7]), raw_text_7)

print("\nTest 7 : complétion d'adresse avec tag de langue (Akwa Group)")
print(f"  address -> {result_7['address']}")
print(f"  city    -> {result_7['city']}")
check(result_7["city"] == "Aîn-Sebaâ", f"city = {result_7['city']}")


# ---------------------------------------------------------------------------
print(f"\n{'='*60}")
if FAILURES == 0:
    print("✅ TOUS LES TESTS PASSENT")
else:
    print(f"❌ {FAILURES} TEST(S) EN ÉCHEC")
    sys.exit(1)