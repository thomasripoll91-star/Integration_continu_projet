import sqlite3
import pandas as pd
from src.lvl_1.compute_sum import pipeline_compute
import os

DB_PATH_DEFAULT = "data/lvl_1/transactions.db"

filenames = ["data/lvl_1/transaction_data_1.csv",
             "data/lvl_1/transaction_data_2.csv",
             "data/lvl_1/transaction_data_3.csv"]


def get_connection(db_path: str = DB_PATH_DEFAULT) -> sqlite3.Connection:
    """Ouvre une connexion SQLite avec activation des clés étrangères."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_database(db_path: str = DB_PATH_DEFAULT):
    """
    Crée le schéma relationnel complet :
    - Tables de dimensions & faits (banques, comptes, transactions flaggées)
    - Tables pour accueillir les résultats des agrégats calculés
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        
        # 1. Dimension Banques
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS banques (
            id_banque INTEGER PRIMARY KEY AUTOINCREMENT,
            nom_banque TEXT NOT NULL UNIQUE
        );
        """)

        # 2. Dimension Comptes
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS comptes (
            iban TEXT PRIMARY KEY,
            pays TEXT
        );
        """)

        # 3. Table de faits : Transactions enrichies (avec flag > 5000)
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

        # 4. Tables de résultats d'agrégations (Partie 2)
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

        conn.commit()
    print(f"✅ Schéma de base de données relationnelle initialisé ({db_path}).")


def insert_transactions_batch(df: pd.DataFrame, db_path: str = DB_PATH_DEFAULT):
    """
    Insère un lot de transactions traitées (avec flag) dans la base relationnelle.
    Insère au préalable les banques et comptes pour respecter l'intégrité référentielle.
    """
    # Nettoyage préventif des lignes incomplètes pour éviter les violations SQL
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
    """
    Insère (ou met à jour via REPLACE) les résultats des agrégations calculées.
    Supporte les formats pd.Series ou pd.DataFrame.
    """
    # Conversion en liste de tuples si Series
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