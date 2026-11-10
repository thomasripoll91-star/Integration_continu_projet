import time
from datetime import datetime
from src.lvl_2.pipeline_S3 import run_s3_pipeline
import schedule

def job():
    horodatage = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n---------------------------------------------------------")
    print(f"⏰ [NIVEAU 3 - CRON] Lancement à : {horodatage}")
    print(f"---------------------------------------------------------")
    
    try:
        # --- Appelle ici ta fonction de pipeline S3 ---
        run_s3_pipeline()
        horodatage_fin = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"✅ [NIVEAU 3 - CRON] Exécution terminée avec succès à {horodatage_fin}.")
        
    except Exception as e:
        print(f"❌ [NIVEAU 3 - CRON] Erreur : {e}")

if __name__ == "__main__":
    print("🚀 Démarrage du planificateur de production...")
    
    # 1. Tu planifies la tâche (par exemple toutes les 5 secondes pour tester, ou 5 minutes en prod)
    schedule.every(30).seconds.do(job)
    
    # (Optionnel) Tu peux lancer un job immédiat si tu veux
    # job()
    
    # 2. La boucle infinie obligatoire pour que le scheduler reste actif en arrière-plan
    while True:
        schedule.run_pending()
        time.sleep(1)