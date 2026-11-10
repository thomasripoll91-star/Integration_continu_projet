import re
import pandas as pd
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

EXTRACTOR_MODEL_NAME = "google/flan-t5-small"

_tokenizer = None
_model = None

def get_slm_model_and_tokenizer():
    global _tokenizer, _model
    if _tokenizer is None or _model is None:
        print("🤖 Chargement du modèle SLM Google Flan-T5...")
        _tokenizer = AutoTokenizer.from_pretrained(EXTRACTOR_MODEL_NAME)
        _model = AutoModelForSeq2SeqLM.from_pretrained(EXTRACTOR_MODEL_NAME)
    return _tokenizer, _model

def convert_text_date_to_iso(date_text: str, default_year: int = 2023) -> str:
    """
    Convertit une date textuelle en français (ex: '12 septembre à 14h30') 
    au format SQL/ISO : YYYY-MM-DD HH:MM:SS.
    """
    if not date_text:
        return None
        
    months = {
        'janvier': '01', 'février': '02', 'mars': '03', 'avril': '04',
        'mai': '05', 'juin': '06', 'juillet': '07', 'août': '08',
        'septembre': '09', 'octobre': '10', 'novembre': '11', 'décembre': '12'
    }
    
    text_lower = date_text.lower()
    
    # 1. Extraction du jour
    day_match = re.search(r'(\d{1,2})', text_lower)
    day = day_match.group(1).zfill(2) if day_match else "01"
    
    # 2. Recherche du mois
    month = "01"
    for m, num in months.items():
        if m in text_lower:
            month = num
            break
            
    # 3. Extraction de l'heure et des minutes (ex: 14h30 ou 14:30)
    time_match = re.search(r'(\d{1,2})[hH:](\d{2})', text_lower)
    hour = time_match.group(1).zfill(2) if time_match else "00"
    minute = time_match.group(2) if time_match else "00"
    
    return f"{default_year}-{month}-{day} {hour}:{minute}:00"

def extract_transaction_from_text(raw_text: str) -> dict:
    """
    Extrait les informations d'une transaction du texte brut 
    et normalise la date au format ISO (YYYY-MM-DD HH:MM:SS).
    """
    tokenizer, model = get_slm_model_and_tokenizer()
    
    prompt = f"Extrais les données de cette transaction financière : {raw_text}"
    inputs = tokenizer(prompt, return_tensors="pt", max_length=512, truncation=True)
    outputs = model.generate(**inputs, max_new_tokens=128)
    extracted_str = tokenizer.decode(outputs[0], skip_special_tokens=True)
    
    transaction_dict = {
        "datetime_transaction": None,
        "iban_origine": None,
        "pays_source": None,
        "banque_source": None,
        "iban_destinataire": None,
        "pays_destinataire": None,
        "montant": None
    }
    
    # 1. Extraction des IBAN
    ibans = re.findall(r'([A-Z]{2}\d{2}[A-Z0-9]{10,30})', raw_text)
    if len(ibans) > 0:
        transaction_dict["iban_origine"] = ibans[0]
    if len(ibans) > 1:
        transaction_dict["iban_destinataire"] = ibans[1]
        
    # 2. Extraction du montant
    montant_match = re.search(r'([\d\s]+(?:[.,]\d+)?)\s*(?:€|EUR)', raw_text, re.IGNORECASE)
    if montant_match:
        val_str = montant_match.group(1).replace(" ", "").replace(",", ".")
        try:
            transaction_dict["montant"] = float(val_str)
        except ValueError:
            pass

    # 3. Détection des pays
    if "allemande" in raw_text.lower() or "allemagne" in raw_text.lower():
        transaction_dict["pays_destinataire"] = "Allemagne"
    if "france" in raw_text.lower():
        transaction_dict["pays_source"] = "France"

    # 4. Extraction de la date et conversion ISO
    date_match = re.search(r'(\d{1,2}\s+(?:janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)(?:\s+(?:à|vers)\s+\d{1,2}[hH:]\d{2})?)', raw_text, re.IGNORECASE)
    if date_match:
        raw_date_text = date_match.group(1)
        transaction_dict["datetime_transaction"] = convert_text_date_to_iso(raw_date_text)

    return transaction_dict

def convert_text_to_dataframe(text_list: list[str]) -> pd.DataFrame:
    """
    Convertit une liste de textes bruts en DataFrame Pandas structuré.
    """
    records = [extract_transaction_from_text(t) for t in text_list]
    df = pd.DataFrame(records)
    print(f"🤖 [SLM] DataFrame final extrait :\n{df}")
    return df