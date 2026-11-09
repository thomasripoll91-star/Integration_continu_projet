import os
import sys

# Modules existants du projet
import insert_data
import compute_sum
import db

def run_pipeline(db_path: str = "data/lvl_1/transactions.db") -> bool:
    print("=" * 60)
    print("🚀 DÉMARRAGE DE LA PIPELINE AUTOMATISÉE")
    print("=" * 60)

    # -------------------------------------------------------------------------
    # 1. Génération des fichiers CSV bruts (insert_data)
    # -------------------------------------------------------------------------
    print("\n[1/4] 📄 Génération des fichiers CSV...")
    fichiers = [
        ("data/lvl_1/transaction_data_1.csv", insert_data.data_1),
        ("data/lvl_1/transaction_data_2.csv", insert_data.data_2),
        ("data/lvl_1/transaction_data_3.csv", insert_data.data_3)
    ]
    for filename, dataset in fichiers:
        insert_data.generate_csv_transition(dataset, filename)

    # -------------------------------------------------------------------------
    # 2. Chargement et traitements (compute_sum)
    # -------------------------------------------------------------------------
    print("\n[2/4] ⚙️  Chargement et traitements...")
    liste_chemins = [filename for filename, _ in fichiers]
    df_flagged, s_origine, s_banque, s_dest = compute_sum.pipeline_compute(liste_chemins)

    # -------------------------------------------------------------------------
    # 3. Initialisation de la base relationnelle (db_3)
    # -------------------------------------------------------------------------
    print(f"\n[3/4] 🗄️  Initialisation du schéma de la BDD ({db_path})...")
    db.init_database(db_path)

    # -------------------------------------------------------------------------
    # 4. Insertion des données traitées et des agrégats (db_3)
    # -------------------------------------------------------------------------
    print("\n[4/4] 💾 Insertion des données dans la base relationnelle...")
    db.insert_transactions_batch(df_flagged, db_path)
    db.insert_aggregated_results(s_origine, s_banque, s_dest, db_path)

    print("\n" + "=" * 60)
    print("✅ PIPELINE TERMINÉE AVEC SUCCÈS")
    print("=" * 60)
    return True

if __name__ == "__main__":
    run_pipeline()