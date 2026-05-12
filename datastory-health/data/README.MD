# 📊 DataStory Music - Datasets

Ce dossier contient les **6 fichiers essentiels** pour le projet d'analyse musicale DataStory Music : **5 charts de classement + Spotify**.

## 📥 Téléchargement des données

**Tous les fichiers proviennent d'une unique source Kaggle** :  
🔗 https://www.kaggle.com/datasets/dhruvildave/billboard-the-hot-100-songs

### 5 Charts à télécharger

| Fichier Kaggle | Renommer en | Contenu | Rows |
|---|---|---|---|
| `billboard_data.csv` | `billboard200.csv` | Billboard 200 Albums | 638,872 |
| `digital_songs.csv` | `digital_songs.csv` | Digital Songs Charts | 52,075 |
| `hot100.csv` | `hot100.csv` | Billboard Hot 100 Singles | 350,387 |
| `radio.csv` | `radio.csv` | Radio Airplay Charts | 91,100 |
| `streaming_songs.csv` | `streaming_songs.csv` | Streaming Songs Charts | 33,100 |

**Subtotal: 1,165,534 entrées de charts**

### Fichier Spotify (features & genres)

| Fichier Kaggle | Renommer en | Contenu | Rows |
|---|---|---|---|
| `spotify_data.csv` | `train.csv` | Audio Features + Genres Spotify | 89,741 |

---

## 📋 Structure des données

### Fichiers bruts à télécharger (placer dans `/data/`)
```
data/
├── billboard200.csv          (638,872 rows - Billboard 200)
├── digital_songs.csv         (52,075 rows - Digital songs)
├── hot100.csv                (350,387 rows - Hot 100 singles)
├── radio.csv                 (91,100 rows - Radio airplay)
├── streaming_songs.csv       (33,100 rows - Streaming songs)
├── train.csv                 (89,741 rows - Spotify features)
└── README.MD                 (ce fichier)
```

### Fichiers générés après nettoyage (dans `/data/clean/`)
```
data/clean/
└── musique_complete.csv      (1,165,534 rows - 5 charts + Spotify features fusionnés)
```

**Note** : Seul le fichier final `musique_complete.csv` est sauvegardé. Les fichiers intermédiaires restent en mémoire pendant le traitement pour optimiser les I/O disque.

---

## 🔧 Installation & Utilisation

### 1. Télécharger les datasets
**Via Kaggle directement** :
1. Accédez à https://www.kaggle.com/datasets/dhruvildave/billboard-the-hot-100-songs
**Via Kaggle CLI** :
```bash
kaggle datasets download -d dhruvildave/billboard-the-hot-100-songs
unzip billboard-the-hot-100-songs.zip -d data/
# Puis renommez les fichiers selon les conventions
```

### 2. Nettoyer et fusionner les données
```bash
python app/nettoyage_csv.py
```

Cela générera automatiquement :
- `data/clean/musique_complete.csv` (fusion de 5 charts + Spotify avec matching)

### 3. Lancer l'API
```bash
python app/api.py
```

L'API sera disponible sur `http://localhost:5000`

### 4. Exécuter la démo
```bash
python main.py
```

---

## 📊 Pipeline et Statistiques

### Processus de fusion
```
5 charts bruts (1,165,534 rows)
    ↓
Nettoyage individuels + normalisation agressive
    ↓
Fusion en mémoire (déduplication)
    ↓
Matching avec Spotify (89,741 chansons)
    ↓
musique_complete.csv (1,165,534 rows)
```

### Résultats du matching
- **Total rows** : 1,165,534 (fusion de 5 charts)
- **Matchés avec Spotify** : ~95,000 (8.14%)
- **Avec genre musical** : ~95,000 ✅
- **Sans genre (NULL)** : ~1,070,534 (92%)

**Pourquoi 5 charts ?** : Augmente les chances de match (même chanson peut apparaître sur plusieurs charts avec variations de noms) → 95k chansons avec genres au lieu de 16k avec 1 seul chart.

---

## 📊 Colonnes des données

### Charts (Billboard, Digital, Hot100, Radio, Streaming)
| Colonne | Type | Description |
|---------|------|-------------|
| `date` | datetime | Date de classement |
| `song` | string | Nom de la chanson |
| `artist` | string | Nom de l'artiste |
| `rank` | int | Position au classement |
| `last_week` | int | Position semaine précédente |
| `peak_position` | int | Meilleure position atteinte |
| `weeks_in_charts` | int | Nombre de semaines au classement |
| `source_chart` | string | Source : "billboard200", "digital_songs", "hot100", "radio", "streaming_songs" |

### Spotify Audio Features & Genres (`train.csv`)
| Colonne | Type | Description |
|---------|------|-------------|
| `track_id` | string | ID unique Spotify |
| `track_name` | string | Nom de la chanson |
| `artists` | string | Artistes (comma-separated) |
| `album_name` | string | Nom de l'album |
| `track_genre` | string | **Genre musical** ⭐ (ex: "pop", "rock", "hip-hop") |
| `popularity` | int | Score de popularité Spotify (0-100) |
| `duration_ms` | int | Durée en millisecondes |
| `danceability` | float | Facilité à danser (0.0-1.0) |
| `energy` | float | Intensité/activité (0.0-1.0) |
| `loudness` | float | Décibels moyens |
| `acousticness` | float | Qualité acoustique (0.0-1.0) |
| `instrumentalness` | float | Absence de voix (0.0-1.0) |
| `liveness` | float | Présence d'audience (0.0-1.0) |
| `valence` | float | Positivité musicale (0.0-1.0) |
| `tempo` | float | BPM (battements par minute) |
| `explicit` | bool | Contient contenu explicite |
| `key` | int | Tonalité (0-11) |
| `mode` | int | Mode (0=mineur, 1=majeur) |
| `time_signature` | int | Signature temporelle |

### Fichier Unifié (`musique_complete.csv`)
Combine **5 charts + Spotify features** avec matching sur (song, artist) normalisés :

- **Colonnes charts** : `date`, `song`, `artist`, `rank`, `weeks_in_charts`, `source_chart`
- **Colonnes Spotify** : `track_id`, `track_genre`, `popularity`, `danceability`, `energy`, `valence`, `tempo`, `explicit` (NULL si pas de match)

---

## 🔍 Normalisation des données

La pipeline `app/nettoyage_csv.py` applique une **normalisation agressive** pour améliorer le matching entre charts et Spotify :

### Transformations appliquées (11 étapes)
✅ Conversion minuscules  
✅ Suppression des accents  
✅ Normalisation apostrophes (`'` → espace)  
✅ Suppression contenu parentheses `(remix)`, `[version]`, `(live)`  
✅ Suppression suffixes : `remix`, `remaster`, `live`, `radio edit`, `acoustic`, `cover`  
✅ Normalisation `feat.`, `featuring`, `ft.` → `ft`  
✅ Normalisation `&`, `and` → `and`  
✅ Suppression ponctuation : `.,!?:;-()[]{}@#$%^~`  
✅ Normalisation espaces multiples  
✅ Suppression tirets (hyphens)  
✅ Trim des whitespaces  

### Raison : Données multiples sources
Même chanson/artiste peuvent être écrites différemment sur différents charts :
- `The Beatles` vs `Beatles`
- `John Legend Feat. Chrissy Teigen` vs `John Legend & Chrissy Teigen`
- `Blinding Lights (Radio Edit)` vs `Blinding Lights`
- `The Weeknd - Blinding Lights` vs `The Weeknd Blinding Lights`

La normalisation agressive permet à ces variantes d'être appariées avec succès à la version Spotify.

---

## 🚀 Endpoints API

### Publics
- `GET /health` - Vérifier l'état de l'API
- `GET /docs` - Documentation API

### Authentifiés (JWT Bearer Token)
- `POST /register` - Inscription utilisateur
- `POST /login` - Connexion & JWT token
- `GET /protected` - Profile utilisateur
- `GET /stats` - Statistiques datasets
- `GET /datasets` - Métadonnées des datasets

### Analyse musicale (Publiques)
- `GET /genres/evolution?period=decennie&top_n=10` - Évolution des genres par décennie
- `GET /genres/evolution?period=annee&top_n=10` - Évolution des genres par année
- `GET /michael-jackson/heritage` - Héritage Michael Jackson
- `GET /page/genres` - Page HTML interactive - Évolution des genres
- `GET /page/michael-jackson` - Page HTML interactive - Michael Jackson

---

## 🛠️ Prérequis techniques

- Python 3.8+
- pandas >= 2.0
- SQLAlchemy >= 2.0
- Flask >= 3.0
- bcrypt >= 4.0
- PyJWT >= 2.8
- python-dotenv >= 1.0

Installer les dépendances:
```bash
pip install pandas sqlalchemy flask bcrypt pyjwt python-dotenv flask-cors flask-limiter
```

---

## ❓ FAQ

**Q: Pourquoi 5 charts et pas 1 seul?**  
A: Pour améliorer la couverture des genres musicaux. Avec 1 chart (Billboard200), seulement 2.52% des chansons ont un genre. Avec 5 charts, on atteint 8.14% (95k chansons) car les mêmes chansons apparaissent sur plusieurs charts avec des variations de noms qui se normalisent mieux collectivement.

**Q: Pourquoi le matching est à 8% et non 100%?**  
A: Les sources sont indépendantes (Billboard vs Spotify) :
- Pas toutes les chansons Billboard sont sur Spotify (ou vice-versa)
- Spotify peut avoir des données obsolètes ou différentes classifications
- Dates de sortie décalées entre sources
- Certaines chansons sont régionales ou indisponibles

8% avec normalisation agressive (sans fuzzy matching) est réaliste pour 2 sources indépendantes massives.

**Q: Que se passe-t-il avec les 92% sans genres?**  
A: Ils sont conservés dans `musique_complete.csv` mais ne peuvent pas être utilisés pour :
- Analyse d'évolution des genres (nécessite genre non-NULL)
- Comparaisons par genre

Ils sont utiles pour :
- Analyses temporelles globales (tendances charts sans genre)
- Statistiques par artiste
- Analyses de popularité

---

## 📝 Notes importantes

1. **Encodage** : Les fichiers CSV doivent être en UTF-8
2. **Séparateur** : Le script détecte automatiquement `;` ou `,`
3. **Dates** : Format `YYYY-MM-DD` ou compatible ISO
4. **Base SQLite** : Créée automatiquement au premier lancement (`music_data.db`)
5. **Variables d'env** : Créez un `.env` avec `JWT_SECRET` et `FERNET_KEY`
6. **Dossier `/clean/`** : Créé automatiquement s'il n'existe pas

---

## 📚 Ressources additionnelles

- 🔗 [Kaggle: Billboard Datasets](https://www.kaggle.com/datasets/dhruvildave/billboard-the-hot-100-songs)
- 🔗 [Spotify Web API](https://developer.spotify.com/documentation/web-api)
- 🔗 [Spotify Audio Features Documentation](https://developer.spotify.com/documentation/web-api/reference/get-audio-features)

---

## 📄 Licence

Données publiques Kaggle - Respectez les conditions d'usage Kaggle.

---

**Dernière mise à jour** : 2026-05-12  
**Version** : 3.0 - Multi-Chart Pipeline (5 charts + Spotify avec normalisation agressive)  
**Approche** : 5 charts fusionnés en mémoire → 1 fichier final (musique_complete.csv)  
**Responsable** : DataStory Music Team
