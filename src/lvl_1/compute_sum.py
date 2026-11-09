import pandas as pd
import os

filenames = [
    "data/lvl_1/transaction_data_1.csv",
    "data/lvl_1/transaction_data_2.csv",
    "data/lvl_1/transaction_data_3.csv"
]

def load_csv(filename: str) -> pd.DataFrame:
    """Charge un fichier CSV unique en DataFrame."""
    if not os.path.exists(filename):
        raise FileNotFoundError(f"Impossible de charger le dataset, fichier introuvable : {filename}")
    return pd.read_csv(filename)

def load_multiple_csvs(filenames: list[str]) -> pd.DataFrame:
    """Charge et fusionne une liste de fichiers CSV."""
    dfs = [load_csv(f) for f in filenames]
    return pd.concat(dfs, ignore_index=True)

def compute_sum_by_iban_origine(df: pd.DataFrame) -> pd.Series:
    """Calcule la somme des montants reçus par iban_origine"""
    return df.groupby('iban_origine')['montant'].sum()

def compute_sum_by_banque_source(df: pd.DataFrame) -> pd.Series:
    """Calcule la somme des montants reçus par banque_source"""
    return df.groupby('banque_source')['montant'].sum()

def compute_sum_by_iban_destinataire(df: pd.DataFrame) -> pd.Series:
    """Calcule la somme des montants reçus par iban_destinataire"""
    return df.groupby('iban_destinataire')['montant'].sum()

def add_high_amount_flag(df: pd.DataFrame, threshold: float = 5000.0) -> pd.DataFrame:
    """
    Ajoute un flag booléen lorsque le montant dépasse le seuil 
    Ne modifie pas le DataFrame d'origine grâce à .copy().
    """
    df_transformed = df.copy()
    df_transformed['is_high_amount'] = df_transformed['montant'] > threshold
    return df_transformed

def pipeline_compute(
    filenames: list[str]
) -> tuple[pd.DataFrame, pd.Series, pd.Series, pd.Series]:
    """
    Charge les données, exécute les calculs et enrichit le dataset.
    Retourne le DataFrame enrichi ainsi que les résultats d'agrégations.
    """
    # 1. Chargement
    df_transactions = load_multiple_csvs(filenames)

    # 2. Enrichissement (Flag > 5000)
    df_avec_flag = add_high_amount_flag(df_transactions, threshold=5000.0)

    # 3. Calculs des agrégats (sur lignes avec IBAN / banques valides)
    df_valid = df_avec_flag.dropna(subset=['iban_origine', 'banque_source', 'iban_destinataire', 'montant'])
    sommes_origine = compute_sum_by_iban_origine(df_valid)
    sommes_banque = compute_sum_by_banque_source(df_valid)
    sommes_dest = compute_sum_by_iban_destinataire(df_valid)

    # 4. Affichages de contrôle
    print("--- Sommes par IBAN origine ---")
    print(sommes_origine)
    print("\n--- Sommes par banque source ---")
    print(sommes_banque)
    print("\n--- Sommes par IBAN destinataire ---")
    print(sommes_dest)
    print("\n--- Transactions avec flag (> 5000) ---")
    print(df_avec_flag[['datetime_transaction', 'montant', 'is_high_amount']])

    return df_avec_flag, sommes_origine, sommes_banque, sommes_dest
