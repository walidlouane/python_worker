import scrapy
import json

class IceMarocSpider(scrapy.Spider):
    name = "icemaroc"
    
    # Pour tester, on met l'URL de l'API avec ton mot-clé
    start_urls = ["https://www.icemaroc.com/api/search.php?query=alamitec"]

    def parse(self, response):
        print(f"\n[🚀 ICE API] Interrogation de : {response.url}")
        
        try:
            # Magie pure : on convertit directement la réponse en dictionnaire Python !
            data = response.json()
        except json.JSONDecodeError:
            print("[❌ ICE API] Erreur : La réponse n'est pas un JSON valide.")
            return

        # Si l'API renvoie une liste vide [] (aucun résultat trouvé)
        if not data:
            print("[⚠️ ICE API] Aucun résultat trouvé pour cette recherche.")
            return

        # L'API renvoie une liste, on prend le premier résultat (le plus pertinent)
        entreprise = data[0]

        company_name = entreprise.get("raison_sociale", "").strip()
        ice = entreprise.get("ice", "").strip()
        rc = entreprise.get("num_rc", "").strip()
        city = entreprise.get("ville_rc", "").strip()
        capital = entreprise.get("capital", "").strip()
        
        # Nettoyage rapide du secteur (enlever les \r\n bizarres de l'API)
        raw_sector = entreprise.get("activite", "")
        clean_sector = " ".join(raw_sector.split()).strip('- ')

        print(f"[✅ ICE API] Trouvé : {company_name} | ICE: {ice}")

        # --- LE CONTRAT DE DONNÉES ---
        # On envoie exactement la même structure que le Spider Charika !
        yield {
            "source_url": response.url,
            "company_name": company_name,
            "html_sector": clean_sector,
            "ice": ice,
            "rc": rc,
            "city": city,
            "capital": capital,
            "full_text": "", # Vide ! L'IA n'aura rien à lire, elle passera son tour.
            "status": "ready_for_ai",
        }