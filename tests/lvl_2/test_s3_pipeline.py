import os
import pytest
import src.lvl_1.insert_data as insert_data
import src.lvl_1.compute_sum as compute_sum
import src.lvl_1.db as db
import src.lvl_2.s3_manager as s3_manager
import src.lvl_2.pipeline_S3 as pipeline_S3

TEST_S3_DB = "data/lvl_2/test_s3_ci.db"


@pytest.fixture(autouse=True)
def setup_s3_and_db():
    """Prépare le bucket S3 et une base SQLite propre avant chaque test."""
    if os.path.exists(TEST_S3_DB):
        try:
            os.remove(TEST_S3_DB)
        except PermissionError:
            pass
    db.init_database(TEST_S3_DB)
    pipeline_S3.ensure_s3_service_started()
    s3_manager.ensure_bucket_exists()

    # Upload d'un fichier de test dans S3
    tmp_csv = "data/lvl_2/tmp_test_1.csv"
    insert_data.generate_csv_transition(insert_data.data_1, tmp_csv)
    s3_manager.upload_csv_to_s3(tmp_csv, "transaction_data_1.csv")
    if os.path.exists(tmp_csv):
        os.remove(tmp_csv)
    yield


def test_s3_upload_and_presence():
    """Vérifie que les fichiers sont bien présents dans le bucket S3 (Partie 2)."""
    files = s3_manager.list_s3_files()
    assert "transaction_data_1.csv" in files


def test_s3_fetch_retry_success():
    """Vérifie que le retry S3 réussit après 2 pannes temporaires simulées (Partie 4)."""
    df, file_hash = s3_manager.fetch_csv_from_s3_with_retry(
        s3_key="transaction_data_1.csv",
        max_retries=3,
        delay_seconds=0.1,
        simulate_s3_failures=2
    )
    assert len(df) == 5
    assert len(file_hash) == 64


def test_s3_fetch_retry_stops_when_max_exceeded():
    """Vérifie que le traitement s'arrête proprement si le fichier S3 reste inaccessible (Partie 4)."""
    with pytest.raises(RuntimeError, match="Arrêt du traitement"):
        s3_manager.fetch_csv_from_s3_with_retry(
            s3_key="transaction_data_1.csv",
            max_retries=3,
            delay_seconds=0.1,
            simulate_s3_failures=3
        )


def test_s3_anti_duplicate_in_db():
    """Vérifie que le même fichier récupéré depuis S3 n'est pas traité deux fois (Partie 3)."""
    df, file_hash = s3_manager.fetch_csv_from_s3_with_retry("transaction_data_1.csv")
    df_flagged = compute_sum.add_high_amount_flag(df)

    assert pipeline_S3.insert_s3_dataframe_to_db(df_flagged, "transaction_data_1.csv", file_hash, TEST_S3_DB) is True
    assert pipeline_S3.insert_s3_dataframe_to_db(df_flagged, "transaction_data_1.csv", file_hash, TEST_S3_DB) is False