import pika
import re
import subprocess
import sys

def start_worker():
    print("Tentative de connexion à RabbitMQ (Python)...")
    
    # Configuration ultra-robuste avec identifiants et port forcé (5672)
    parameters = pika.URLParameters('amqp://guest:guest@127.0.0.1:5672/%2F')
    
    # Connexion au serveur
    connection = pika.BlockingConnection(parameters)
    channel = connection.channel()

    # Déclaration des files d'attente
    channel.queue_declare(queue='url_to_crawl', durable=True)
    channel.queue_declare(queue='document_queue', durable=True)

    print("[*] Connexion RÉUSSIE ! Robot Python prêt.")
    print("[*] En attente d'URLs dans 'url_to_crawl'...")

    # Fonction qui s'exécute à chaque message reçu
    def callback(ch, method, properties, body):
        raw_message = body.decode('utf-8')
        
        match = re.search(r'https?://[^\]\)]+', raw_message)
        url = match.group(0) if match else raw_message.strip()
        
        print(f"\n[->] Réception de l'ordre : {url}")
        print("[⚙️] Lancement du moteur Scrapy...")
        
        # On lance le fichier spider.py en lui passant l'URL
        subprocess.run([sys.executable, "spider.py", url], check=False)
        
        # Validation du message pour le retirer de la file
        ch.basic_ack(delivery_tag=method.delivery_tag)

    # Écoute de la file
    channel.basic_consume(queue='url_to_crawl', on_message_callback=callback)
    
    # Lancement de la boucle infinie
    channel.start_consuming()

if __name__ == '__main__':
    start_worker()