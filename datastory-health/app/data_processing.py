"""Module de traitement des donnees musique."""

import pandas as pd
import os
from typing import Dict


def _charger_fichier_tabulaire(filepath: str) -> pd.DataFrame:
    """Charge un fichier CSV/JSON/XLSX avec une detection simple du separateur CSV."""
    if filepath.endswith('.csv'):
        # Les exports open data sont souvent separes par ';'.
        try:
            df = pd.read_csv(filepath, sep=';')
            if df.shape[1] == 1:
                df = pd.read_csv(filepath)
        except Exception:
            df = pd.read_csv(filepath)
        return df
    if filepath.endswith('.json'):
        return pd.read_json(filepath)
    if filepath.endswith('.xlsx'):
        return pd.read_excel(filepath)
    raise ValueError(f"Format non supporte: {filepath}")


def charger_tous_les_datasets(dossier_data: str = None, inclure_excel: bool = False) -> Dict[str, pd.DataFrame]:
    """Charge les jeux de donnees trouves dans data.

    Par defaut, les fichiers Excel sont ignores car ils contiennent souvent
    des feuilles de publication (titres, notes, mises en page) peu exploitables
    directement pour les traitements de l'exercice.
    """
    if dossier_data is None:
        dossier_data = os.path.join(os.path.dirname(__file__), '..', 'data')

    jeux = {}
    if not os.path.isdir(dossier_data):
        return jeux

    for nom in os.listdir(dossier_data):
        chemin = os.path.join(dossier_data, nom)
        if not os.path.isfile(chemin):
            continue
        extensions = ('.csv', '.json', '.xlsx') if inclure_excel else ('.csv', '.json')
        if not nom.lower().endswith(extensions):
            continue
        try:
            jeux[nom] = _charger_fichier_tabulaire(chemin)
        except Exception:
            # On ignore les fichiers non lisibles pour ne pas bloquer tout le chargement.
            continue

    return jeux


def load_charts_data(filepath: str = None) -> pd.DataFrame:
    """Charge l'historique unifie des charts."""
    if filepath is None:
        chemin_clean = os.path.join(os.path.dirname(__file__), '..', 'data', 'clean', 'charts_unifies.csv')
        filepath = chemin_clean

    if filepath and os.path.exists(filepath):
        return _charger_fichier_tabulaire(filepath)

    # Fallback: concatener les CSV bruts des charts
    dossier_brut = os.path.join(os.path.dirname(__file__), '..', 'data')
    noms = ["billboard200.csv", "digital_songs.csv", "hot100.csv", "radio.csv", "streaming_songs.csv"]
    frames = []
    for nom in noms:
        chemin = os.path.join(dossier_brut, nom)
        if os.path.exists(chemin):
            df = _charger_fichier_tabulaire(chemin)
            df["source_chart"] = os.path.splitext(nom)[0]
            frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def load_music_complete_data(filepath: str = None) -> pd.DataFrame:
    """Charge la vue globale chart + features audio."""
    if filepath is None:
        filepath = os.path.join(os.path.dirname(__file__), '..', 'data', 'clean', 'musique_complete.csv')
    if filepath and os.path.exists(filepath):
        return _charger_fichier_tabulaire(filepath)
    return pd.DataFrame()


def prepare_charts_data(df: pd.DataFrame) -> pd.DataFrame:
    """Prepare les colonnes utiles pour l'analyse temporelle des genres."""
    if df.empty:
        return df

    df = df.copy()
    df.columns = [col.strip().lower().replace(" ", "_") for col in df.columns]

    if 'date' in df.columns:
        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        df = df.dropna(subset=['date'])
        df['annee'] = df['date'].dt.year
        df['decennie'] = (df['annee'] // 10) * 10

    for col in ['rank', 'last_week', 'peak_position', 'weeks_in_charts']:
        if col in df.columns:
            df[col] = (
                df[col]
                .astype(str)
                .str.strip()
                .replace('-', '0')
            )
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)

    if 'track_genre' in df.columns:
        df['track_genre'] = df['track_genre'].fillna('inconnu').astype(str).str.strip().str.lower()

    return df


if __name__ == "__main__":
    print("Chargement des donnees musique...\n")
    charts = load_charts_data()
    charts = prepare_charts_data(charts)
    print(f"Charts: {len(charts)} lignes")
    print(charts.head())
    print()

    complet = load_music_complete_data()
    complet = prepare_charts_data(complet)
    print(f"Vue globale: {len(complet)} lignes")
    print(complet.head())
    print("\nModule de traitement pret")
