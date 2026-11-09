import os
import sys

# Modules existants du projet
import src.lvl_1.insert_data as insert_data
import src.lvl_1.compute_sum as compute_sum
import src.lvl_1.db as db

def run_pipeline(db_path: str = "data/lvl_1/transactions.db") -> bool:
    print("=" * 60)
    print("🚀 DÉMARRAGE DE LA PIPELINE AUTOMATISÉE (AVEC RETRY & ANTI-DOUBLONS)")
    print("=" * 60)

    # 1. Génération des fichiers CSV bruts
    print("\n[1/4] 📄 Génération des fichiers CSV...")
    fichiers = [
        ("data/lvl_1/transaction_data_1.csv", insert_data.data_1),
        ("data/lvl_1/transaction_data_2.csv", insert_data.data_2),
        ("data/lvl_1/transaction_data_3.csv", insert_data.data_3)
    ]
    for filename, dataset in fichiers:
        insert_data.generate_csv_transition(dataset, filename)

    # 2. Initialisation de la base relationnelle
    print(f"\n[2/4] 🗄️ Initialisation du schéma de la BDD ({db_path})...")
    db.init_database(db_path)

    # 3. Traitement et insertion unitaire sécurisée (Retry + Anti-doublons)
    print("\n[3/4] ⚙️ Traitement et insertion sécurisée par fichier...")
    liste_chemins = [filename for filename, _ in fichiers]
    
    for filename in liste_chemins:
        print(f"\n--- Traitement de : {filename} ---")
        df_raw = compute_sum.load_csv(filename)
        df_flagged = compute_sum.add_high_amount_flag(df_raw, threshold=5000.0)
        
        db.insert_file_with_retry(
            df=df_flagged,
            filepath=filename,
            db_path=db_path,
            max_retries=3,
            delay_seconds=1.5
        )

    # 4. Calcul global des agrégats et mise à jour des tables de résultats
    print("\n[4/4] 📊 Calcul et insertion des agrégats globaux...")
    df_global = compute_sum.load_multiple_csvs(liste_chemins)
    df_global_flagged = compute_sum.add_high_amount_flag(df_global, threshold=5000.0)

    df_valid = df_global_flagged.dropna(subset=['iban_origine', 'banque_source', 'iban_destinataire', 'montant'])
    s_origine = compute_sum.compute_sum_by_iban_origine(df_valid)
    s_banque = compute_sum.compute_sum_by_banque_source(df_valid)
    s_dest = compute_sum.compute_sum_by_iban_destinataire(df_valid)

    db.insert_aggregated_results(s_origine, s_banque, s_dest, db_path)

    print("\n" + "=" * 60)
    print("✅ PIPELINE TERMINÉE AVEC SUCCÈS")
    print("=" * 60)
    return True

if __name__ == "__main__":
    run_pipeline()