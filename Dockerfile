FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copie de tout le code source et des données
COPY src/ ./src/
COPY tests/ ./tests/
COPY data/ ./data/

# Le conteneur exécute le scheduler de production (Niveau 3)
CMD ["python", "-m", "src.lvl_3.scheduler"]