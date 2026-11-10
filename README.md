#  Projet EFREI M2  intégration et déploiement continus

Projet académique de fin d'études visant à concevoir une pipeline de données financières robuste, conteneurisée, testée et automatisée, couvrant l'ensemble des niveaux d'exigence (Gestion des erreurs, Stockage S3, CI/CD, Déploiement conteneurisé et Intelligence Artificielle par SLM).

---

## 🛠️ Architecture et Niveaux du Projet

Le projet est structuré de manière modulaire :

* **`src/lvl_1/` (Niveau 1)** : Gestion des erreurs, insertion unitaire sécurisée avec retry sur SQLite, hachage SHA-256 et table d'anti-doublon `processed_files`.
* **`src/lvl_2/` (Niveau 2)** : Stockage objet S3 local avec **SeaweedFS** via Docker, lecture en mémoire via `io.BytesIO` et mécanisme de retry spécifique aux pannes de récupération S3.
* **`src/lvl_3/` (Niveau 3)** : 
  * **Option 1 (CD & Automatisation)** : Conteneurisation globale (`Dockerfile`, `docker-compose.yml`) et orchestration d'un worker de production piloté par un planificateur (`schedule`).
  * **Option 3 (Extraction SLM)** : Ingestion de données non structurées textuelles converties en flux tabulaires via un Small Language Model (`google/flan-t5-small`).

---

## 📁 Structure du Répertoire

```text
Integration_continu_projet/
├── .github/
│   └── workflows/
│       └── ci.yml            # Pipeline CI/CD GitHub Actions
├── data/                     # Stockage local et bases SQLite
├── src/
│   ├── lvl_1/                # Logique base de données & règles métiers
│   ├── lvl_2/                # Client S3, manager & pipeline S3
│   └── lvl_3/                # Scheduler de production & extracteur SLM
├── tests/                    # Tests unitaires et d'intégration (pytest)
├── Dockerfile                # Image de conteneurisation globale (Prod)
├── docker-compose.yml        # Orchestration S3 (SeaweedFS) & Worker
├── requirements.txt          # Dépendances du projet
└── README.md
```

---

## ⚙️ Prérequis

Assurez-vous d'avoir installé sur votre machine :
* Python 3.11+
* Docker & Docker Compose

---

##  Guide d'Utilisation et Lancement

### 1. Installation des dépendances
```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 2. Lancement de l'infrastructure S3 locale (SeaweedFS)
```powershell
docker compose up -d
```
* **Interface Web SeaweedFS** : `http://localhost:8888/buckets/`

### 3. Exécution de la Pipeline S3 (Niveau 2)
```powershell
python -m src.lvl_2.pipeline_S3
```

### 4. Test de l'Extracteur SLM (Niveau 3)
Pour tester l'extraction de transactions à partir de texte brut :
```powershell
python -m src.lvl_3.slm_extractor
```

### 5. Lancement des Tests Automatisés
Tous les tests des différents niveaux s'exécutent via `pytest` :
```powershell
python -m pytest -v
```

---

## 🔄 CI/CD et Déploiement Continu

Le projet intègre un workflow GitHub Actions complet (`.github/workflows/ci.yml`) qui s'exécute à chaque `push` :
1. Installation de l'environnement Python et des dépendances.
2. Démarrage du conteneur S3 SeaweedFS.
3. Exécution de la suite de tests unitaires et d'intégration (Niveaux 1, 2 et 3).
4. Validation de la configuration Docker Compose pour le déploiement de production.