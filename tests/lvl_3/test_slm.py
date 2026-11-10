import pytest
from src.lvl_3.slm_extractor import convert_text_to_dataframe

def test_slm_extraction_format():
    """Vérifie que le SLM convertit bien le texte en DataFrame tabulaire structuré."""
    textes_tests = [
        "Le 12 septembre à 14h30, le compte FR761234567890 a envoyé 6200 € vers le compte DE987654321."
    ]
    df = convert_text_to_dataframe(textes_tests)
    
    # Vérification des colonnes indispensables pour la pipeline
    assert "datetime_transaction" in df.columns
    assert "montant" in df.columns
    assert "iban_origine" in df.columns
    assert len(df) == 1
    assert df.loc[0, "montant"] == 6200.0