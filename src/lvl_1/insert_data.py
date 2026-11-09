import pandas as pd 
import os
# Définition des colonnes
cols = ["datetime_transaction", "iban_origine", "pays_source", "banque_source", "iban_destinataire", "pays_destinataire", "montant"]

data_1 = [
    ["2023-10-01 08:30:00", "FR1420041010050500013M02606", "France", "BNP Paribas", "FR1430004028371920384750192", "France", 120.50],
    ["2023-10-01 09:15:00", "FR1420041010050500013M02606", "France", "BNP Paribas", "DE89370400440532013000", "Allemagne", 45.00],
    ["2023-10-01 12:00:00", "DE89370400440532013000", "Allemagne", "Deutsche Bank", "FR1420041010050500013M02606", "France", 200.00],
    ["2023-10-01 14:20:00", "FR1430004028371920384750192", "France", "Societe Generale", "ES9121000418401234567891", "Espagne", 15.99],
    ["2023-10-01 18:45:00", "ES9121000418401234567891", "Espagne", "Banco Santander", "FR1420041010050500013M02606", "France", 85.00]
]

data_2 = [
    ["2023-10-02 03:14:00", "FR1420041010050500013M02606", "France", "BNP Paribas", "KY12ISB00000012345678", "Iles Caimans", 25000.00], 
    ["2023-10-02 10:00:00", "FR1430004028371920384750192", "France", "Societe Generale", "FR1430004028371920384750192", "France", 500.00],
    ["2023-10-02 11:30:00", "CH9308100000001234567", "Suisse", "UBS", "FR1420041010050500013M02606", "France", 9999.99],
    ["2023-10-02 23:55:00", "FR1420041010050500013M02606", "France", "BNP Paribas", "US1234567890123456789012", "Etats-Unis", 1500.00],
    ["2023-10-03 00:01:00", "FR1420041010050500013M02606", "France", "BNP Paribas", "US1234567890123456789012", "Etats-Unis", 1500.00]
]

data_3 = [
    ["2023-10-04 09:00:00", "FR1420041010050500013M02606", "France", "BNP Paribas", "FR1430004028371920384750192", "France", -50.00],
    ["2023-10-04 10:15:00", "", "France", "Societe Generale", "DE89370400440532013000", "Allemagne", 100.00],
    ["2023-10-04 11:45:00", "FR1420", "France", "BNP Paribas", "FR1430004028371920384750192", "France", 20.0],
    ["", "FR1420041010050500013M02606", "France", "BNP Paribas", "DE89370400440532013000", "Allemagne", 75.50], 
    ["2023-10-04 15:30:00", "FR1420041010050500013M02606", "", "", "FR1430004028371920384750192", "France", 300.00]
]    

def generate_csv_transition(data: list, filename: str, col: list[str] = cols):
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    df_data = pd.DataFrame(data, columns=col)
    df_data.to_csv(filename, index=False)
    print(f"✅ {filename} généré avec succès ({len(df_data)} lignes).")


