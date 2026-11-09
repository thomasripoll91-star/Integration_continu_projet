import io
import os
import time
import hashlib
import boto3
import pandas as pd
from botocore.exceptions import ClientError, EndpointConnectionError

AWS_ACCESS_KEY_ID = "admin"
AWS_SECRET_ACCESS_KEY = "password123"
ENDPOINT_URL = "http://localhost:9000"
BUCKET_NAME = "finance-transactions-bucket"


def get_s3_client(endpoint_url: str = ENDPOINT_URL):
    """Initialise le client S3 pointant vers le service S3 local (SeaweedFS)."""
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name="us-east-1"
    )


def ensure_bucket_exists(bucket_name: str = BUCKET_NAME):
    """Crée le bucket S3 s'il n'existe pas encore."""
    s3 = get_s3_client()
    try:
        s3.head_bucket(Bucket=bucket_name)
        print(f"📁 Le bucket '{bucket_name}' est prêt.")
    except ClientError:
        s3.create_bucket(Bucket=bucket_name)
        print(f"✅ Bucket '{bucket_name}' créé avec succès.")


def upload_csv_to_s3(local_path: str, s3_key: str, bucket_name: str = BUCKET_NAME):
    """Envoie un fichier CSV généré vers le bucket S3."""
    s3 = get_s3_client()
    s3.upload_file(local_path, bucket_name, s3_key)
    print(f"⬆️  [UPLOAD S3] '{local_path}' -> s3://{bucket_name}/{s3_key}")


def list_s3_files(bucket_name: str = BUCKET_NAME) -> list[str]:
    """Retourne la liste des clés (fichiers) présentes dans le bucket S3."""
    s3 = get_s3_client()
    response = s3.list_objects_v2(Bucket=bucket_name)
    if "Contents" not in response:
        return []
    return [obj["Key"] for obj in response["Contents"]]


def fetch_csv_from_s3_with_retry(
    s3_key: str,
    bucket_name: str = BUCKET_NAME,
    max_retries: int = 3,
    delay_seconds: float = 1.5,
    simulate_s3_failures: int = 0
) -> tuple[pd.DataFrame, str]:
    """
    Partie 3 & 4 : Récupère un CSV directement depuis S3 en mémoire (sans disque local)
    avec mécanisme de retry en cas d'indisponibilité ou d'erreur réseau.
    Retourne (DataFrame, sha256_hash).
    """
    s3 = get_s3_client()

    for attempt in range(1, max_retries + 1):
        try:
            print(f"🔄 [S3 GET] Tentative {attempt}/{max_retries} de récupération de '{s3_key}'...")

            # Simulation d'une panne réseau / S3 temporairement inaccessible (Partie 4)
            if attempt <= simulate_s3_failures:
                raise ConnectionError(f"Simulation : Service S3 temporairement indisponible ou timeout pour '{s3_key}'")

            response = s3.get_object(Bucket=bucket_name, Key=s3_key)
            raw_bytes = response["Body"].read()

            # Calcul de l'empreinte SHA-256 directement sur le flux S3 pour l'anti-doublon
            file_hash = hashlib.sha256(raw_bytes).hexdigest()

            # Lecture du CSV en mémoire avec Pandas (aucun fichier local utilisé)
            df = pd.read_csv(io.BytesIO(raw_bytes))
            print(f"⬇️  [S3 GET] '{s3_key}' récupéré avec succès à la tentative {attempt} ({len(df)} lignes).")
            return df, file_hash

        except (ClientError, EndpointConnectionError, ConnectionError) as e:
            print(f"⚠️  Erreur de récupération S3 (tentative {attempt}/{max_retries}) : {e}")
            if attempt < max_retries:
                print(f"⏳ Attente de {delay_seconds}s avant nouvelle tentative...")
                time.sleep(delay_seconds)
            else:
                print(f"❌ ÉCHEC CRITIQUE S3 : Impossible de récupérer '{s3_key}' après {max_retries} tentatives.")
                raise RuntimeError(f"Arrêt du traitement : fichier S3 '{s3_key}' inaccessible.") from e