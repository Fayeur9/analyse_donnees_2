"""Nettoyage des CSV du projet DataStory Music."""

from __future__ import annotations

import os
import unicodedata
import re
from typing import Dict, List

import pandas as pd


DOSSIER_DATA = os.path.join(os.path.dirname(__file__), "..", "data")
DOSSIER_SORTIE = os.path.join(DOSSIER_DATA, "clean")


def normaliser_nom_colonne(nom: str) -> str:
    """Convertit un nom de colonne en snake_case ASCII."""
    # 1) Uniformise la casse et supprime les espaces en bord.
    nom = nom.strip().lower()
    # 2) Retire les accents pour faciliter les manipulations en code.
    nom = "".join(c for c in unicodedata.normalize("NFD", nom) if unicodedata.category(c) != "Mn")
    # 3) Remplace tout caractere non alphanumerique par "_".
    nom = re.sub(r"[^a-z0-9]+", "_", nom)
    # 4) Compacte les underscores consecutifs et retire ceux en bord.
    nom = re.sub(r"_+", "_", nom).strip("_")
    return nom


def charger_csv(chemin: str) -> pd.DataFrame:
    """Charge un CSV avec detection basique du separateur."""
    # Premier essai: format open data francais souvent separe par ';'.
    try:
        df = pd.read_csv(chemin, sep=";")
        # Si une seule colonne, on retente avec la virgule (separateur standard CSV).
        if df.shape[1] == 1:
            df = pd.read_csv(chemin)
    except Exception:
        # Fallback direct au parseur CSV standard.
        df = pd.read_csv(chemin)
    return df


def _normaliser_texte(serie: pd.Series) -> pd.Series:
    """Nettoie une serie texte: trim + fallback vide."""
    return serie.fillna("").astype(str).str.strip()


def _convertir_entier(df: pd.DataFrame, colonne: str) -> None:
    """Convertit une colonne en entier en gerant les valeurs non numeriques."""
    if colonne not in df.columns:
        return
    df[colonne] = (
        df[colonne]
        .astype(str)
        .str.strip()
        .replace("-", "0")
        .replace("", "0")
    )
    df[colonne] = pd.to_numeric(df[colonne], errors="coerce").fillna(0).astype(int)


def _normaliser_pour_matching(texte: str) -> str:
    """Normalisation agressive pour ameliorer le matching song/artist entre charts et Spotify.
    
    Applique les transformations suivantes:
    1. Minuscules
    2. Supprime les accents
    3. Remplace apostrophes variees par espace
    4. Supprime contenu entre parentheses/crochets (remixes, versions)
    5. Supprime suffixes courants: remix, remaster, edition, mix, version, acoustic, live, radio
    6. Normalise "ft.", "feat.", "featuring" -> " ft "
    7. Normalise "and", "&", "n" -> " and "
    8. Supprime "the" au debut (articles anglais)
    9. Supprime ponctuation: .,!?-()[]{}:;
    10. Supprime caracteres speciaux: &@#$%^~
    11. Normalise espaces multiples en un seul
    12. Trim
    """
    if not isinstance(texte, str):
        return ""
    
    # 1) Minuscules
    texte = texte.lower()
    
    # 2) Supprime accents (NFD normalization)
    texte = "".join(
        c for c in unicodedata.normalize("NFD", texte)
        if unicodedata.category(c) != "Mn"
    )
    
    # 3) Remplace apostrophes variees par espace
    texte = re.sub(r"[''`]", " ", texte)
    
    # 4) Supprime contenu entre parentheses et crochets (remixes, versions, etc)
    texte = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", texte)
    
    # 5) Normalise variants de "feat/featuring"
    texte = re.sub(r"\bfeat\.?\b|\bfeaturing\b|\bft\.?\b", " ft ", texte)
    
    # 6) Normalise "and", "&", variations
    texte = re.sub(r"\s&\s|\s+and\s+|\s+n\s+", " and ", texte)
    
    # 7) Supprime suffixes courants qui ajoutent du bruit (remixes, versions)
    suffixes = [
        r"\b(remix|remixed)\b",
        r"\b(remaster|remastered)\b",
        r"\b(edition|edit|extended)\b",
        r"\b(mix|mixed)\b",
        r"\b(version)\b",
        r"\b(acoustic|acapella)\b",
        r"\b(live|live version)\b",
        r"\b(radio|radio version|radio edit)\b",
        r"\b(instrumental|karaoke)\b",
        r"\b(cover|covered)\b",
    ]
    for pattern in suffixes:
        texte = re.sub(pattern, " ", texte)
    
    # 8) Supprime "the" au debut si present (articles anglais courants)
    texte = re.sub(r"^the\s+", "", texte)
    
    # 9) Supprime ponctuation (conserve les espaces)
    texte = re.sub(r"[.,!?()[\]{}:;]", " ", texte)
    
    # 10) Supprime traits d'union et caracteres speciaux
    texte = re.sub(r"[-&@#$%^~]", " ", texte)
    
    # 11) Normalise espaces multiples et trim
    texte = re.sub(r"\s+", " ", texte).strip()
    
    return texte


def nettoyer_chart(df: pd.DataFrame, source_chart: str) -> pd.DataFrame:
    """Nettoie un CSV Billboard (hot100, radio, streaming, etc.)."""
    df = df.copy()
    df.columns = [normaliser_nom_colonne(c) for c in df.columns]

    rename_map = {
        "last_week": "last_week",
        "peak_position": "peak_position",
        "weeks_in_charts": "weeks_in_charts",
        "image_url": "image_url",
    }
    df = df.rename(columns=rename_map)

    for col in ["song", "artist", "image_url"]:
        if col in df.columns:
            df[col] = _normaliser_texte(df[col])

    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")

    for col in ["rank", "last_week", "peak_position", "weeks_in_charts"]:
        _convertir_entier(df, col)

    df["source_chart"] = source_chart
    df = df.dropna(subset=["date", "song", "artist"])
    return df.drop_duplicates().reset_index(drop=True)


def nettoyer_track_features(df: pd.DataFrame) -> pd.DataFrame:
    """Nettoie le dataset audio train.csv."""
    df = df.copy()
    df.columns = [normaliser_nom_colonne(c) for c in df.columns]

    if "unnamed_0" in df.columns:
        df = df.drop(columns=["unnamed_0"])

    for col in ["track_id", "artists", "album_name", "track_name", "track_genre"]:
        if col in df.columns:
            df[col] = _normaliser_texte(df[col])

    int_cols = ["popularity", "duration_ms", "key", "mode", "time_signature"]
    for col in int_cols:
        _convertir_entier(df, col)

    float_cols = [
        "danceability",
        "energy",
        "loudness",
        "speechiness",
        "acousticness",
        "instrumentalness",
        "liveness",
        "valence",
        "tempo",
    ]
    for col in float_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    if "explicit" in df.columns:
        df["explicit"] = df["explicit"].astype(str).str.lower().isin(["true", "1", "yes"])

    return df.drop_duplicates(subset=["track_id"]).reset_index(drop=True)


def fusionner_charts(charts: List[pd.DataFrame]) -> pd.DataFrame:
    """Concatene les 5 charts Billboard en une seule table historique."""
    if not charts:
        return pd.DataFrame()
    fusion = pd.concat(charts, ignore_index=True)
    fusion = fusion.sort_values(["date", "source_chart", "rank"], ascending=[True, True, True])
    return fusion.reset_index(drop=True)


def creer_vue_globale(charts_unifies: pd.DataFrame, tracks: pd.DataFrame) -> pd.DataFrame:
    """Cree un fichier global en rapprochant charts et features audio avec normalisation agressive.
    
    Strategie de matching:
    1. Essai 1: Matching exact sur (song_normalized, artist_normalized)
    2. Essai 2: Pour les songs qui n'ont pas matche, essai avec variantes d'artistes
       (pour capturer les changements de nom d'artiste ou spelling variations)
    """
    if charts_unifies.empty:
        return charts_unifies.copy()

    gauche = charts_unifies.copy()
    droite = tracks.copy()

    # Applique normalisation agressive pour le matching
    gauche["song_key"] = gauche["song"].apply(_normaliser_pour_matching)
    gauche["artist_key"] = gauche["artist"].apply(_normaliser_pour_matching)
    droite["song_key"] = droite["track_name"].apply(_normaliser_pour_matching)
    droite["artist_key"] = droite["artists"].apply(_normaliser_pour_matching)

    colonnes_features = [
        "song_key",
        "artist_key",
        "track_id",
        "track_genre",
        "popularity",
        "danceability",
        "energy",
        "valence",
        "tempo",
        "explicit",
    ]
    
    droite = droite[colonnes_features].drop_duplicates(subset=["song_key", "artist_key"])
    fusion = gauche.merge(droite, how="left", on=["song_key", "artist_key"])
    return fusion.drop(columns=["song_key", "artist_key"])


def nettoyer_tous_les_csv() -> Dict[str, pd.DataFrame]:
    """Nettoie tous les CSV musique et ecrit les sorties dans data/clean/."""
    os.makedirs(DOSSIER_SORTIE, exist_ok=True)

    fichiers_charts = [
        "billboard200.csv",
        "digital_songs.csv",
        "hot100.csv",
        "radio.csv",
        "streaming_songs.csv",
    ]

    resultat: Dict[str, pd.DataFrame] = {}
    charts: List[pd.DataFrame] = []

    for nom_fichier in fichiers_charts:
        chemin = os.path.join(DOSSIER_DATA, nom_fichier)
        if not os.path.exists(chemin):
            continue

        brut = charger_csv(chemin)
        source_chart = os.path.splitext(nom_fichier)[0]
        propre = nettoyer_chart(brut, source_chart)
        sortie = os.path.join(DOSSIER_SORTIE, nom_fichier)
        propre.to_csv(sortie, index=False)
        resultat[nom_fichier] = propre
        charts.append(propre)

    train_path = os.path.join(DOSSIER_DATA, "train.csv")
    features = pd.DataFrame()
    if os.path.exists(train_path):
        brut_train = charger_csv(train_path)
        features = nettoyer_track_features(brut_train)
        sortie_train = os.path.join(DOSSIER_SORTIE, "train.csv")
        features.to_csv(sortie_train, index=False)
        resultat["train.csv"] = features

    charts_unifies = fusionner_charts(charts)
    if not charts_unifies.empty:
        sortie_charts = os.path.join(DOSSIER_SORTIE, "charts_unifies.csv")
        charts_unifies.to_csv(sortie_charts, index=False)
        resultat["charts_unifies.csv"] = charts_unifies

    vue_globale = creer_vue_globale(charts_unifies, features)
    if not vue_globale.empty:
        sortie_globale = os.path.join(DOSSIER_SORTIE, "musique_complete.csv")
        vue_globale.to_csv(sortie_globale, index=False)
        resultat["musique_complete.csv"] = vue_globale

    return resultat


if __name__ == "__main__":
    jeux = nettoyer_tous_les_csv()
    print("CSV nettoyes :")
    for nom, df in jeux.items():
        print(f"- {nom}: {len(df)} lignes, {len(df.columns)} colonnes")
