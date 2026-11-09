import os
import time
import hashlib
import sqlite3
import pandas as pd

DB_PATH_DEFAULT = "data/lvl_1/transactions.db"


def get_connection(db_path: str = DB_PATH_DEFAULT) -> sqlite3.Connection:
    """Ouvre une connexion SQLite avec activation des clés étrangères."""
    dirname = os.path.dirname(db_path)
    if dirname:
        os.makedirs(dirname, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_database(db_path: str = DB_PATH_DEFAULT):
    """
    Crée le schéma relationnel complet :
    - Tables de dimensions & faits (banques, comptes, transactions)
    - Tables d'agrégats
    - Table de traçabilité des fichiers (processed_files) pour l'anti-doublon
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS banques (
            id_banque INTEGER PRIMARY KEY AUTOINCREMENT,
            nom_banque TEXT NOT NULL UNIQUE
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS comptes (
            iban TEXT PRIMARY KEY,
            pays TEXT
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id_transaction INTEGER PRIMARY KEY AUTOINCREMENT,
            datetime_transaction TEXT NOT NULL,
            iban_origine TEXT NOT NULL,
            id_banque_source INTEGER NOT NULL,
            iban_destinataire TEXT NOT NULL,
            pays_destinataire TEXT,
            montant REAL NOT NULL,
            is_high_amount INTEGER NOT NULL CHECK (is_high_amount IN (0, 1)),
            FOREIGN KEY (iban_origine) REFERENCES comptes(iban),
            FOREIGN KEY (id_banque_source) REFERENCES banques(id_banque),
            FOREIGN KEY (iban_destinataire) REFERENCES comptes(iban)
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS resultats_sommes_iban_origine (
            iban_origine TEXT PRIMARY KEY,
            total_envoye REAL NOT NULL
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS resultats_sommes_banque (
            banque_source TEXT PRIMARY KEY,
            total_envoye REAL NOT NULL
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS resultats_sommes_iban_destinataire (
            iban_destinataire TEXT PRIMARY KEY,
            total_recu REAL NOT NULL
        );
        """)

        # Table anti-doublon (traçabilité par nom et hash SHA-256)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS processed_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_name TEXT UNIQUE NOT NULL,
            file_hash TEXT UNIQUE NOT NULL,
            processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        conn.commit()
    print(f"✅ Schéma de base de données relationnelle initialisé ({db_path}).")


def calculate_file_hash(filepath: str) -> str:
    """Calcule l'empreinte SHA-256 d'un fichier CSV."""
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192):
            sha256.update(chunk)
    return sha256.hexdigest()


def is_file_processed(filepath: str, db_path: str = DB_PATH_DEFAULT) -> bool:
    """Vérifie si le fichier a déjà été traité avec succès."""
    filename = os.path.basename(filepath)
    file_hash = calculate_file_hash(filepath)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM processed_files WHERE file_name = ? OR file_hash = ?;",
            (filename, file_hash)
        )
        return cursor.fetchone()[0] > 0


def insert_file_with_retry(
    df: pd.DataFrame, 
    filepath: str, 
    db_path: str = DB_PATH_DEFAULT,
    max_retries: int = 3,
    delay_seconds: float = 1.5,
    simulate_lock_failures: int = 0
) -> bool:
    """
    Insère un lot de transactions avec gestion des retries et anti-doublon atomique.
    """
    # 1. Vérification anti-doublon préalable
    if is_file_processed(filepath, db_path):
        print(f"⏭️  [ANTI-DOUBLON] Fichier déjà traité avec succès : {filepath}. Insertion ignorée.")
        return False

    df_clean = df.dropna(subset=['datetime_transaction', 'iban_origine', 'banque_source', 'iban_destinataire', 'montant']).copy()
    filename = os.path.basename(filepath)
    file_hash = calculate_file_hash(filepath)  # Calcul du hash SHA-256

    # 2. Boucle de Retry
    for attempt in range(1, max_retries + 1):
        try:
            print(f"🔄 Tentative {attempt}/{max_retries} pour l'insertion de {filename}...")

            # Simulation de panne temporaire si demandée
            if attempt <= simulate_lock_failures:
                raise sqlite3.OperationalError("Simulation : database is locked (erreur temporaire)")

            # Utilisation d'une connexion unique pour tout le bloc transactionnel
            with get_connection(db_path) as conn:
                cursor = conn.cursor()

                # Insertion banques
                banques_uniques = [(b,) for b in df_clean['banque_source'].unique()]
                cursor.executemany("INSERT OR IGNORE INTO banques (nom_banque) VALUES (?);", banques_uniques)

                # Insertion comptes
                comptes_origine = df_clean[['iban_origine', 'pays_source']].drop_duplicates().values.tolist()
                comptes_dest = df_clean[['iban_destinataire', 'pays_destinataire']].drop_duplicates().values.tolist()
                cursor.executemany("INSERT OR IGNORE INTO comptes (iban, pays) VALUES (?, ?);", comptes_origine)
                cursor.executemany("INSERT OR IGNORE INTO comptes (iban, pays) VALUES (?, ?);", comptes_dest)

                cursor.execute("SELECT nom_banque, id_banque FROM banques;")
                banque_map = dict(cursor.fetchall())

                records = [
                    (
                        str(row['datetime_transaction']),
                        str(row['iban_origine']),
                        banque_map[row['banque_source']],
                        str(row['iban_destinataire']),
                        str(row['pays_destinataire']) if pd.notna(row['pays_destinataire']) else None,
                        float(row['montant']),
                        1 if row.get('is_high_amount', False) else 0
                    )
                    for _, row in df_clean.iterrows()
                ]

                cursor.executemany("""
                INSERT INTO transactions (
                    datetime_transaction, iban_origine, id_banque_source,
                    iban_destinataire, pays_destinataire, montant, is_high_amount
                ) VALUES (?, ?, ?, ?, ?, ?, ?);
                """, records)

                # CORRECTION : On insère dans processed_files avec la MEME connexion et le MEME curseur
                cursor.execute(
                    "INSERT INTO processed_files (file_name, file_hash) VALUES (?, ?);",
                    (filename, file_hash)
                )

                # Validation globale de la transaction atomique
                conn.commit()

            print(f"✅ Insertion réussie pour {filename} à la tentative {attempt} ({len(records)} lignes).")
            return True

        except sqlite3.OperationalError as e:
            print(f"⚠️  Erreur détectée à la tentative {attempt}/{max_retries} : {e}")
            if attempt < max_retries:
                print(f"⏳ Attente de {delay_seconds}s avant la nouvelle tentative...")
                time.sleep(delay_seconds)
            else:
                print(f"❌ ÉCHEC CRITIQUE : Nombre maximal de tentatives ({max_retries}) dépassé pour {filename}.")
                raise RuntimeError(f"Arrêt de la pipeline : échec d'insertion persistant pour {filename}.") from e


def insert_transactions_batch(df: pd.DataFrame, db_path: str = DB_PATH_DEFAULT):
    """
    Insère un lot de transactions traitées (avec flag) dans la base relationnelle.
    Insère au préalable les banques et comptes pour respecter l'intégrité référentielle.
    """
    df_clean = df.dropna(subset=['datetime_transaction', 'iban_origine', 'banque_source', 'iban_destinataire', 'montant']).copy()

    with get_connection(db_path) as conn:
        cursor = conn.cursor()

        # 1. Insertion par lot des banques uniques
        banques_uniques = [(b,) for b in df_clean['banque_source'].unique()]
        cursor.executemany("INSERT OR IGNORE INTO banques (nom_banque) VALUES (?);", banques_uniques)

        # 2. Insertion par lot des comptes uniques (origine et destinataire)
        comptes_origine = df_clean[['iban_origine', 'pays_source']].drop_duplicates().values.tolist()
        comptes_dest = df_clean[['iban_destinataire', 'pays_destinataire']].drop_duplicates().values.tolist()
        cursor.executemany("INSERT OR IGNORE INTO comptes (iban, pays) VALUES (?, ?);", comptes_origine)
        cursor.executemany("INSERT OR IGNORE INTO comptes (iban, pays) VALUES (?, ?);", comptes_dest)

        # Récupération du mapping {nom_banque: id_banque} pour la clé étrangère
        cursor.execute("SELECT nom_banque, id_banque FROM banques;")
        banque_map = dict(cursor.fetchall())

        # 3. Préparation des tuples de transactions
        records = [
            (
                str(row['datetime_transaction']),
                str(row['iban_origine']),
                banque_map[row['banque_source']],
                str(row['iban_destinataire']),
                str(row['pays_destinataire']) if pd.notna(row['pays_destinataire']) else None,
                float(row['montant']),
                1 if row.get('is_high_amount', False) else 0
            )
            for _, row in df_clean.iterrows()
        ]

        cursor.executemany("""
        INSERT INTO transactions (
            datetime_transaction, iban_origine, id_banque_source,
            iban_destinataire, pays_destinataire, montant, is_high_amount
        ) VALUES (?, ?, ?, ?, ?, ?, ?);
        """, records)

        conn.commit()
    print(f"✅ {len(records)} transactions insérées avec succès.")

def insert_aggregated_results(
    sommes_origine: pd.Series | pd.DataFrame,
    sommes_banques: pd.Series | pd.DataFrame,
    sommes_dest: pd.Series | pd.DataFrame,
    db_path: str = DB_PATH_DEFAULT
):
    to_tuples = lambda s: list(s.items()) if isinstance(s, pd.Series) else list(s.itertuples(index=False, name=None))

    with get_connection(db_path) as conn:
        cursor = conn.cursor()

        cursor.executemany(
            "INSERT OR REPLACE INTO resultats_sommes_iban_origine (iban_origine, total_envoye) VALUES (?, ?);",
            to_tuples(sommes_origine)
        )
        cursor.executemany(
            "INSERT OR REPLACE INTO resultats_sommes_banque (banque_source, total_envoye) VALUES (?, ?);",
            to_tuples(sommes_banques)
        )
        cursor.executemany(
            "INSERT OR REPLACE INTO resultats_sommes_iban_destinataire (iban_destinataire, total_recu) VALUES (?, ?);",
            to_tuples(sommes_dest)
        )

        conn.commit()
    print("✅ Résultats d'agrégations insérés avec succès.")