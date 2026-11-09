import os
import gc
import sqlite3
import pytest
import pandas as pd

import src.lvl_1.insert_data as insert_data
import src.lvl_1.compute_sum as compute_sum
import src.lvl_1.db as db

TEST_DB_PATH = "data/lvl_1/test_ci_transactions.db"


@pytest.fixture(scope="session", autouse=True)
def setup_and_teardown_pipeline():
    """Initialise les données et la base temporaire avant les tests,

    puis la nettoie sans blocage sous Windows à la fin de la session.
    """
    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except PermissionError:
            pass

    # 1. Génération des fichiers CSV
    insert_data.generate_csv_transition(insert_data.data_1, "data/lvl_1/transaction_data_1.csv")
    insert_data.generate_csv_transition(insert_data.data_2, "data/lvl_1/transaction_data_2.csv")
    insert_data.generate_csv_transition(insert_data.data_3, "data/lvl_1/transaction_data_3.csv")

    # 2. Traitements et calculs purs
    fichiers = [
        "data/lvl_1/transaction_data_1.csv",
        "data/lvl_1/transaction_data_2.csv",
        "data/lvl_1/transaction_data_3.csv"
    ]
    df_flagged, s_origine, s_banque, s_dest = compute_sum.pipeline_compute(fichiers)

    # 3. Initialisation de la BDD et insertions
    db.init_database(TEST_DB_PATH)
    db.insert_transactions_batch(df_flagged, TEST_DB_PATH)
    db.insert_aggregated_results(s_origine, s_banque, s_dest, TEST_DB_PATH)

    yield {
        "df_flagged": df_flagged,
        "s_origine": s_origine,
        "s_banque": s_banque,
        "s_dest": s_dest
    }

    # Nettoyage sécurisé pour Windows (évite WinError 32)
    gc.collect()
    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except PermissionError:
            pass


@pytest.fixture
def db_conn():
    """Fournit une connexion SQLite active fermée automatiquement après chaque test."""
    conn = sqlite3.connect(TEST_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


# ============================================================================
# 1. VÉRIFICATION DE L'INSERTION DES DONNÉES
# ============================================================================
def test_data_insertion_counts(db_conn):
    """Vérifie que les transactions valides et les dimensions sont bien insérées."""
    cur = db_conn.cursor()

    # 15 lignes brutes - 3 lignes avec champs obligatoires vides = 12 insérées
    cur.execute("SELECT COUNT(*) FROM transactions;")
    assert cur.fetchone()[0] == 12

    # 5 banques distinctes
    cur.execute("SELECT COUNT(*) FROM banques;")
    assert cur.fetchone()[0] == 5

    # 8 comptes distincts (émetteurs + destinataires uniques)
    cur.execute("SELECT COUNT(*) FROM comptes;")
    assert cur.fetchone()[0] == 8


# ============================================================================
# 2. VÉRIFICATION DE L'EXACTITUDE DES VALEURS ENREGISTRÉES
# ============================================================================
def test_recorded_values_integrity(db_conn):
    """Vérifie la conformité des données insérées et la jointure avec la table banques."""
    cur = db_conn.cursor()

    cur.execute("""
        SELECT t.datetime_transaction, t.montant, b.nom_banque, t.iban_origine, t.iban_destinataire
        FROM transactions t
        JOIN banques b ON t.id_banque_source = b.id_banque
        WHERE t.montant = 25000.0;
    """)
    row = cur.fetchone()
    assert row is not None
    assert row["datetime_transaction"] == "2023-10-02 03:14:00"
    assert row["nom_banque"] == "BNP Paribas"
    assert row["iban_origine"] == "FR1420041010050500013M02606"
    assert row["iban_destinataire"] == "KY12ISB00000012345678"


# ============================================================================
# 3. VÉRIFICATION DES TRAITEMENTS ET RÉSULTATS ATTENDUS
# ============================================================================
def test_aggregated_results(db_conn, setup_and_teardown_pipeline):
    """Vérifie que les sommes calculées correspondent aux attentes métier et sont bien persistées."""
    s_banque = setup_and_teardown_pipeline["s_banque"]
    cur = db_conn.cursor()

    # Somme pour BNP Paribas
    cur.execute("SELECT total_envoye FROM resultats_sommes_banque WHERE banque_source = 'BNP Paribas';")
    total_bnp = cur.fetchone()[0]
    assert total_bnp == pytest.approx(28211.0, rel=1e-3)
    assert total_bnp == pytest.approx(s_banque["BNP Paribas"], rel=1e-3)

    # Somme pour l'IBAN des Caïmans
    cur.execute("SELECT total_recu FROM resultats_sommes_iban_destinataire WHERE iban_destinataire = 'KY12ISB00000012345678';")
    total_caimans = cur.fetchone()[0]
    assert total_caimans == pytest.approx(25000.0, rel=1e-3)


# ============================================================================
# 4. VÉRIFICATION DU POSITIONNEMENT DES FLAGS
# ============================================================================
def test_high_amount_flags(db_conn):
    """Vérifie que le flag is_high_amount est activé uniquement si montant > 5000."""
    cur = db_conn.cursor()

    # Aucune transaction avec montant <= 5000 ne doit avoir is_high_amount = 1
    cur.execute("SELECT COUNT(*) FROM transactions WHERE montant <= 5000 AND is_high_amount = 1;")
    assert cur.fetchone()[0] == 0

    # Toutes les transactions avec montant > 5000 doivent avoir is_high_amount = 1
    cur.execute("SELECT COUNT(*) FROM transactions WHERE montant > 5000 AND is_high_amount = 0;")
    assert cur.fetchone()[0] == 0

    # Exactement 2 transactions dépassent 5 000 € (25000.00 et 9999.99)
    cur.execute("SELECT COUNT(*) FROM transactions WHERE is_high_amount = 1;")
    assert cur.fetchone()[0] == 2