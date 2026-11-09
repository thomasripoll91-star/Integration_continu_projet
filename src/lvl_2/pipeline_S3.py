import os
import subprocess
import time
import sqlite3
import pandas as pd

import src.lvl_1.insert_data as insert_data
import src.lvl_1.compute_sum as compute_sum
import src.lvl_1.db as db
import src.lvl_2.s3_manager as s3_manager

DB_PATH_LVL2 = "data/lvl_2/transactions_s3.db"


def ensure_s3_service_started():
    """Démarre ou vérifie que le conteneur S3 est bien actif."""
    s3 = s3_manager.get_s3_client()
    try:
        s3.list_buckets()
        print("✅ Service S3 déjà actif et accessible.")
    except Exception:
        print("⚙️  Service S3 non détecté, démarrage via docker compose...")
        subprocess.run(["docker", "compose", "up", "-d"], check=True)
        time.sleep(3)
        print("✅ Service S3 démarré.")


def is_s3_file_already_processed(s3_key: str, file_hash: str, db_path: str) -> bool:
    """Vérifie dans processed_files si l'objet S3 (nom ou hash) a déjà été traité."""
    with db.get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM processed_files WHERE file_name = ? OR file_hash = ?;",
            (s3_key, file_hash)
        )
        return cursor.fetchone()[0] > 0


def insert_s3_dataframe_to_db(df: pd.DataFrame, s3_key: str, file_hash: str, db_path: str) -> bool:
    """Insère les données issues du S3 en base avec protection anti-doublon atomique."""
    if is_s3_file_already_processed(s3_key, file_hash, db_path):
        print(f"⏭️  [ANTI-DOUBLON] Le fichier S3 '{s3_key}' a déjà été traité. Ignoré.")
        return False

    df_clean = df.dropna(
        subset=["datetime_transaction", "iban_origine", "banque_source", "iban_destinataire", "montant"]
    ).copy()

    with db.get_connection(db_path) as conn:
        cursor = conn.cursor()

        banques_uniques = [(b,) for b in df_clean["banque_source"].unique()]
        cursor.executemany("INSERT OR IGNORE INTO banques (nom_banque) VALUES (?);", banques_uniques)

        comptes_origine = df_clean[["iban_origine", "pays_source"]].drop_duplicates().values.tolist()
        comptes_dest = df_clean[["iban_destinataire", "pays_destinataire"]].drop_duplicates().values.tolist()
        cursor.executemany("INSERT OR IGNORE INTO comptes (iban, pays) VALUES (?, ?);", comptes_origine)
        cursor.executemany("INSERT OR IGNORE INTO comptes (iban, pays) VALUES (?, ?);", comptes_dest)

        cursor.execute("SELECT nom_banque, id_banque FROM banques;")
        banque_map = dict(cursor.fetchall())

        records = [
            (
                str(row["datetime_transaction"]),
                str(row["iban_origine"]),
                banque_map[row["banque_source"]],
                str(row["iban_destinataire"]),
                str(row["pays_destinataire"]) if pd.notna(row["pays_destinataire"]) else None,
                float(row["montant"]),
                1 if row.get("is_high_amount", False) else 0
            )
            for _, row in df_clean.iterrows()
        ]

        cursor.executemany("""
        INSERT INTO transactions (
            datetime_transaction, iban_origine, id_banque_source,
            iban_destinataire, pays_destinataire, montant, is_high_amount
        ) VALUES (?, ?, ?, ?, ?, ?, ?);
        """, records)

        cursor.execute(
            "INSERT INTO processed_files (file_name, file_hash) VALUES (?, ?);",
            (s3_key, file_hash)
        )
        conn.commit()

    print(f"✅ [BDD] {len(records)} transactions insérées depuis s3://{s3_manager.BUCKET_NAME}/{s3_key}.")
    return True


def run_s3_pipeline(db_path: str = DB_PATH_LVL2) -> bool:
    print("=" * 65)
    print("🚀 DÉMARRAGE DE LA PIPELINE NIVEAU 2 (STOCKAGE S3 & RETRY)")
    print("=" * 65)

    # 1. Démarrer / vérifier le service S3 et créer le bucket
    print("\n[1/5] 🔌 Démarrage S3 & configuration du bucket...")
    ensure_s3_service_started()
    s3_manager.ensure_bucket_exists()

    # 2. Générer les CSV et les envoyer dans S3 (puis supprimer les fichiers locaux temporaires)
    print("\n[2/5] 📄 Génération des CSV et Upload automatique vers S3...")
    datasets = [
        ("transaction_data_1.csv", insert_data.data_1),
        ("transaction_data_2.csv", insert_data.data_2),
        ("transaction_data_3.csv", insert_data.data_3),
    ]
    for s3_key, data in datasets:
        temp_path = f"data/lvl_2/tmp_{s3_key}"
        insert_data.generate_csv_transition(data, temp_path)
        s3_manager.upload_csv_to_s3(temp_path, s3_key)
        os.remove(temp_path)  # Supprime le fichier local : seul S3 détient désormais la donnée

    # 3. Vérifier que les fichiers sont présents dans le stockage S3
    print("\n[3/5] 🔍 Vérification des fichiers dans le bucket S3...")
    s3_files = s3_manager.list_s3_files()
    for s3_key, _ in datasets:
        if s3_key not in s3_files:
            raise AssertionError(f"Fichier manquant dans S3 : {s3_key}")
    print(f"✔ Fichiers présents sur S3 : {s3_files}")

    # 4. Récupération depuis S3 (avec retry) -> Traitement -> Insertion BDD
    print("\n[4/5] ⚙️  Flux S3 -> Récupération -> Traitement -> Base de données...")
    db.init_database(db_path)
    all_dfs = []

    for s3_key in s3_files:
        if not s3_key.endswith(".csv"):
            continue
        df_raw, file_hash = s3_manager.fetch_csv_from_s3_with_retry(s3_key)
        df_flagged = compute_sum.add_high_amount_flag(df_raw, threshold=5000.0)
        insert_s3_dataframe_to_db(df_flagged, s3_key, file_hash, db_path)
        all_dfs.append(df_flagged)

    # 5. Mise à jour des agrégats en base
    print("\n[5/5] 📊 Calcul et enregistrement des agrégats...")
    df_global = pd.concat(all_dfs, ignore_index=True)
    df_valid = df_global.dropna(subset=["iban_origine", "banque_source", "iban_destinataire", "montant"])
    db.insert_aggregated_results(
        compute_sum.compute_sum_by_iban_origine(df_valid),
        compute_sum.compute_sum_by_banque_source(df_valid),
        compute_sum.compute_sum_by_iban_destinataire(df_valid),
        db_path
    )

    print("\n" + "=" * 65)
    print("✅ PIPELINE S3 TERMINÉE AVEC SUCCÈS")
    print("=" * 65)
    return True


if __name__ == "__main__":
    run_s3_pipeline()