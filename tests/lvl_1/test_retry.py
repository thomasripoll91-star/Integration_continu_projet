import os
import sqlite3
import pytest
import pandas as pd

import src.lvl_1.insert_data as insert_data
import src.lvl_1.compute_sum as compute_sum
import src.lvl_1.db as db

RETRY_DB_PATH = "data/lvl_1/test_retry_robustness.db"


@pytest.fixture(autouse=True)
def clean_db():
    """Nettoie la base de test avant chaque exécution."""
    if os.path.exists(RETRY_DB_PATH):
        try:
            os.remove(RETRY_DB_PATH)
        except PermissionError:
            pass
    db.init_database(RETRY_DB_PATH)
    yield
    if os.path.exists(RETRY_DB_PATH):
        try:
            os.remove(RETRY_DB_PATH)
        except PermissionError:
            pass


def test_retry_success_after_temporary_failure():
    """Vérifie que l'insertion réussit après plusieurs échecs temporaires simulés."""
    csv_path = "data/lvl_1/transaction_data_1.csv"
    if not os.path.exists(csv_path):
        insert_data.generate_csv_transition(insert_data.data_1, csv_path)

    df = compute_sum.add_high_amount_flag(compute_sum.load_csv(csv_path))

    # Simule 2 échecs, puis réussit à la 3e tentative (max_retries=3)
    success = db.insert_file_with_retry(
        df=df,
        filepath=csv_path,
        db_path=RETRY_DB_PATH,
        max_retries=3,
        delay_seconds=0.1,
        simulate_lock_failures=2
    )
    assert success is True


def test_anti_duplicate_mechanism():
    """Vérifie qu'un fichier déjà traité ne peut pas être inséré une seconde fois."""
    csv_path = "data/lvl_1/transaction_data_1.csv"
    if not os.path.exists(csv_path):
        insert_data.generate_csv_transition(insert_data.data_1, csv_path)

    df = compute_sum.add_high_amount_flag(compute_sum.load_csv(csv_path))

    # S'assurer que la base est propre pour ce test spécifique
    with sqlite3.connect(RETRY_DB_PATH) as conn:
        conn.execute("DELETE FROM processed_files;")
        conn.execute("DELETE FROM transactions;")
        conn.commit()

    # 1ère insertion : doit réussir et retourner True
    res_first = db.insert_file_with_retry(df, csv_path, db_path=RETRY_DB_PATH)
    assert res_first is True

    # 2ème insertion du même fichier : bloqué par l'anti-doublon, doit retourner False
    res_second = db.insert_file_with_retry(df, csv_path, db_path=RETRY_DB_PATH)
    assert res_second is False

def test_retry_stops_pipeline_when_max_exceeded():
    """Vérifie que la pipeline s'arrête (RuntimeError) si les tentatives max sont dépassées."""
    csv_path = "data/lvl_1/transaction_data_2.csv"
    if not os.path.exists(csv_path):
        insert_data.generate_csv_transition(insert_data.data_2, csv_path)

    df = compute_sum.add_high_amount_flag(compute_sum.load_csv(csv_path))

    # Simule 4 pannes alors que max_retries = 3 -> Doit lever RuntimeError
    with pytest.raises(RuntimeError, match="Arrêt de la pipeline"):
        db.insert_file_with_retry(
            df=df,
            filepath=csv_path,
            db_path=RETRY_DB_PATH,
            max_retries=3,
            delay_seconds=0.1,
            simulate_lock_failures=4
        )