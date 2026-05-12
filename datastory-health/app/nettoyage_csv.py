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
    """Nettoie le dataset audio songs.csv (550k chansons Spotify avec genres/niche_genres)."""
    import json
    
    df = df.copy()
    df.columns = [normaliser_nom_colonne(c) for c in df.columns]

    # Renommer colonnes songs.csv pour compatibilité
    colonnes_renommage = {
        "id": "track_id",
        "name": "track_name",
        "genre": "track_genre",
    }
    for ancien, nouveau in colonnes_renommage.items():
        if ancien in df.columns:
            df = df.rename(columns={ancien: nouveau})

    if "unnamed_0" in df.columns:
        df = df.drop(columns=["unnamed_0"])

    # IMPORTANT: Dans songs.csv, 'artists' est au format JSON ["Artist1", "Artist2", ...]
    # Il faut extraire le premier artiste (ou concaténer) et le normaliser
    if "artists" in df.columns:
        def parse_artists_json(val):
            if pd.isna(val):
                return ""
            try:
                val_str = str(val).strip()
                if val_str.startswith('['):
                    artists_list = json.loads(val_str)
                    # Prendre le premier artiste ou tous concaténés
                    if isinstance(artists_list, list) and len(artists_list) > 0:
                        return " ".join(artists_list) if len(artists_list) > 1 else artists_list[0]
                    return ""
                else:
                    return val_str
            except (json.JSONDecodeError, ValueError):
                return ""
        
        df["artists"] = df["artists"].apply(parse_artists_json)

    # Normaliser texte
    for col in ["track_id", "artists", "album_name", "track_name", "track_genre", "niche_genres"]:
        if col in df.columns:
            df[col] = _normaliser_texte(df[col])

    # Convertir en entier
    int_cols = ["popularity", "duration_ms", "key", "mode", "year"]
    for col in int_cols:
        if col in df.columns:
            _convertir_entier(df, col)

    # Convertir en float
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

    # Garder seulement les colonnes utiles (genre + niche_genres + features)
    colonnes_gardees = [
        "track_id",
        "track_name",
        "artists",
        "album_name",
        "track_genre",
        "niche_genres",
        "popularity",
        "danceability",
        "energy",
        "loudness",
        "speechiness",
        "acousticness",
        "instrumentalness",
        "liveness",
        "valence",
        "tempo",
        "duration_ms",
        "year",
    ]
    df = df[[col for col in colonnes_gardees if col in df.columns]]

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

    # Colonnes de features - adaptées au dataset disponible
    colonnes_features = ["song_key", "artist_key", "track_id", "track_genre"]
    
    # Ajouter niche_genres si présent (nouveau dans songs.csv)
    if "niche_genres" in droite.columns:
        colonnes_features.append("niche_genres")
    
    # Ajouter colonnes audio features (communes)
    for col in ["popularity", "danceability", "energy", "valence", "tempo", "duration_ms", "year"]:
        if col in droite.columns:
            colonnes_features.append(col)
    
    # Ajouter explicit si présent (ancien dataset train.csv)
    if "explicit" in droite.columns:
        colonnes_features.append("explicit")
    
    # Filtrer pour colonnes qui existent vraiment
    colonnes_features = [col for col in colonnes_features if col in droite.columns]
    
    droite = droite[colonnes_features].drop_duplicates(subset=["song_key", "artist_key"])
    fusion = gauche.merge(droite, how="left", on=["song_key", "artist_key"])
    return fusion.drop(columns=["song_key", "artist_key"])


def enrichir_avec_genre_artiste(vue: pd.DataFrame) -> pd.DataFrame:
    """Fallback : remplit track_genre manquant avec le genre principal de l'artiste (df_merged.csv).

    Pour chaque ligne sans track_genre, on cherche dans df_merged le genre de l'artiste
    sur la même chanson/artiste/date. Si trouvé, on remplit track_genre et on marque
    genre_source = 'artiste' (vs 'track' pour les matchs songs.csv).
    """
    df_merged_path = os.path.join(DOSSIER_DATA, "df_merged.csv")
    if not os.path.exists(df_merged_path):
        vue["genre_source"] = vue["track_genre"].apply(lambda x: "track" if pd.notna(x) else "inconnu")
        return vue

    merged = pd.read_csv(df_merged_path, usecols=["Date", "Song", "Artist", "main_genre"])
    merged.columns = ["date_m", "song_m", "artist_m", "main_genre"]

    # Normalisation pour jointure insensible à la casse
    merged["song_key"] = merged["song_m"].apply(_normaliser_pour_matching)
    merged["artist_key"] = merged["artist_m"].apply(_normaliser_pour_matching)
    merged["date_key"] = merged["date_m"].astype(str).str.strip()

    # Dédupliquer : un artiste → un genre (le plus fréquent par clé artiste)
    genre_par_artiste = (
        merged[merged["main_genre"] != "inconnu"]
        .groupby("artist_key")["main_genre"]
        .agg(lambda s: s.value_counts().index[0])
        .reset_index()
    )

    result = vue.copy()
    result["song_key"] = result["song"].apply(_normaliser_pour_matching)
    result["artist_key"] = result["artist"].apply(_normaliser_pour_matching)

    # Marquer la source des genres déjà remplis
    result["genre_source"] = result["track_genre"].apply(lambda x: "track" if pd.notna(x) else "inconnu")

    # Jointure avec genre_par_artiste sur artist_key
    result = result.merge(genre_par_artiste, on="artist_key", how="left")

    # Remplir les track_genre manquants avec main_genre de l'artiste
    masque_manquant = result["track_genre"].isna() & result["main_genre"].notna()
    result.loc[masque_manquant, "track_genre"] = result.loc[masque_manquant, "main_genre"]
    result.loc[masque_manquant, "genre_source"] = "artiste"

    result = result.drop(columns=["song_key", "artist_key", "main_genre"])
    return result


def nettoyer_tous_les_csv() -> Dict[str, pd.DataFrame]:
    """Nettoie les 5 charts + songs.csv, fusionne en mémoire, sort SEULEMENT musique_complete.csv."""
    os.makedirs(DOSSIER_SORTIE, exist_ok=True)

    # Charger et nettoyer les 5 charts (en mémoire uniquement)
    fichiers_charts = [
        "billboard200.csv",
        "digital_songs.csv",
        "hot100.csv",
        "radio.csv",
        "streaming_songs.csv",
    ]
    
    charts: List[pd.DataFrame] = []
    
    for nom_fichier in fichiers_charts:
        chemin = os.path.join(DOSSIER_DATA, nom_fichier)
        if not os.path.exists(chemin):
            continue
        
        brut = charger_csv(chemin)
        source_chart = os.path.splitext(nom_fichier)[0]
        propre = nettoyer_chart(brut, source_chart)
        charts.append(propre)

    # Nettoyer songs.csv (550k chansons Spotify avec genres + niche_genres)
    songs_path = os.path.join(DOSSIER_DATA, "songs.csv")
    features = pd.DataFrame()
    if os.path.exists(songs_path):
        brut_songs = charger_csv(songs_path)
        features = nettoyer_track_features(brut_songs)
    else:
        # Fallback si songs.csv n'existe pas, essayer train.csv (ancien dataset)
        train_path = os.path.join(DOSSIER_DATA, "train.csv")
        if os.path.exists(train_path):
            brut_train = charger_csv(train_path)
            features = nettoyer_track_features(brut_train)

    # Fusionner les 5 charts en mémoire
    charts_unifies = fusionner_charts(charts)

    # Créer le fichier unifié (SEUL fichier sauvegardé sur disque)
    vue_globale = creer_vue_globale(charts_unifies, features)

    # Enrichir les genres manquants avec le genre principal de l'artiste (df_merged.csv)
    if not vue_globale.empty:
        vue_globale = enrichir_avec_genre_artiste(vue_globale)
    
    resultat: Dict[str, pd.DataFrame] = {}
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
