"""API Flask — DataStory Music."""

import os
import sys
from functools import wraps
from pathlib import Path

import pandas as pd
from flask import Flask, jsonify, request
from flask_cors import CORS
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

# Permet de lancer le fichier directement (python app/api.py) ou de l'importer
sys.path.insert(0, os.path.dirname(__file__))
from auth import (
    create_access_token,
    create_refresh_token,
    decrypt_field,
    encrypt_field,
    hash_password,
    verify_password,
    verify_token,
)
from data_processing import charger_tous_les_datasets, load_music_complete_data, prepare_charts_data
from models import SessionLocal, MusicGenreObservation, User, init_db


# Duree de vie du token d'acces en minutes
ACCESS_TOKEN_TTL_MINUTES = 30

app = Flask(__name__)
CORS(app)

# Valeurs de genre considerees comme "inconnues" — exclues des analyses
GENRES_INCONNUS = ("", "inconnu", "unknown", "unk", "none", "nan")


def token_requis(f):
    """Decorateur qui verifie le token JWT avant d'acceder a une route protegee."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        en_tete = request.headers.get("Authorization", "")
        if not en_tete.startswith("Bearer "):
            return jsonify({"error": "token manquant"}), 401
        token = en_tete.replace("Bearer ", "", 1).strip()
        payload = verify_token(token)
        if not payload:
            return jsonify({"error": "token invalide ou expire"}), 401
        return f(payload, *args, **kwargs)
    return wrapper


def _calculer_decennie(annee):
    """Convertit une annee en chaine de decennie, ex: 1985 -> '1980s'."""
    return f"{(annee // 10) * 10}s"


def _synchroniser_observations_genres_depuis_csv():
    """Charge musique_complete.csv et peuple la table music_genre_observations."""
    import pandas as pd

    data = load_music_complete_data()
    data = prepare_charts_data(data)

    if data.empty:
        return {"inserted": 0, "source_rows": 0}

    # Ajouter les colonnes manquantes avec des valeurs par defaut
    if "track_genre" not in data.columns:
        data["track_genre"] = "inconnu"
    if "genre_source" not in data.columns:
        data["genre_source"] = "inconnu"

    for col in ["source_chart", "date", "song", "artist", "rank", "track_genre", "genre_source"]:
        if col not in data.columns:
            data[col] = None

    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    data = data.dropna(subset=["date", "song", "artist"]).copy()
    data["annee"] = data["date"].dt.year.astype(int)
    data["decennie"] = data["annee"].apply(_calculer_decennie)

    session_db = SessionLocal()
    inserted = 0
    try:
        # Vider la table avant de la reremplir
        session_db.query(MusicGenreObservation).delete()
        session_db.commit()

        # Inserer par lots de 1000 lignes pour ne pas saturer la memoire
        for i in range(0, len(data), 1000):
            chunk = data.iloc[i:i + 1000]
            objets = []
            for _, row in chunk.iterrows():
                obs = MusicGenreObservation(
                    source_chart=str(row.get("source_chart") or ""),
                    date=row["date"].date(),
                    annee=int(row["annee"]),
                    decennie=str(row["decennie"]),
                    song=str(row.get("song") or "").strip(),
                    artist=str(row.get("artist") or "").strip(),
                    rank=int(row.get("rank") or 0),
                    track_genre=str(row.get("track_genre") or "").strip().lower(),
                    genre_source=str(row.get("genre_source") or "inconnu").strip().lower(),
                )
                objets.append(obs)
            session_db.add_all(objets)
            session_db.commit()
            inserted += len(objets)
    except Exception:
        session_db.rollback()
        raise
    finally:
        session_db.close()

    return {"inserted": inserted, "source_rows": len(data)}


# ---------------------------------------------------------------------------
# Routes generales
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return jsonify({"statut": "ok"}), 200


@app.get("/")
def accueil():
    return jsonify({
        "message": "API DataStory Music",
        "endpoints": [
            "/health", "/register", "/login", "/refresh", "/protected",
            "/stats", "/genres/evolution", "/genres/totaux", "/genres/domination", "/genres/longevite", "/genres/popularite",
            "/michael-jackson/heritage", "/michael-jackson/comparaison", "/michael-jackson/thriller", "/datasets",
            "/page/genres", "/page/michael-jackson",
        ],
    }), 200


@app.get("/page/genres")
def page_genres():
    """Page vitrine: evolution des genres musicaux."""
    return """
<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>DataStory Music - Evolution des Genres</title>
  <style>
    :root {
      --bg: #0f172a;
      --surface: #111827;
      --accent: #f59e0b;
      --accent-2: #10b981;
      --text: #f8fafc;
      --muted: #94a3b8;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Georgia, 'Times New Roman', serif;
      color: var(--text);
      background:
        radial-gradient(circle at 10% 10%, #1e293b 0%, transparent 38%),
        radial-gradient(circle at 90% 20%, #14532d 0%, transparent 30%),
        linear-gradient(160deg, #020617 0%, #111827 45%, #1f2937 100%);
      min-height: 100vh;
    }
    .wrap { max-width: 1040px; margin: 0 auto; padding: 32px 18px 44px; }
    .hero { padding: 18px 0 26px; }
    h1 { margin: 0 0 10px; font-size: clamp(2rem, 4vw, 3.3rem); letter-spacing: 0.5px; }
    .sub { color: var(--muted); max-width: 760px; line-height: 1.5; }
    .box {
      background: linear-gradient(180deg, rgba(17,24,39,0.88), rgba(15,23,42,0.88));
      border: 1px solid rgba(148,163,184,0.25);
      border-radius: 16px;
      padding: 16px;
      backdrop-filter: blur(6px);
      animation: in 550ms ease;
    }
    .controls { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
    select, button {
      background: #111827;
      border: 1px solid #334155;
      color: var(--text);
      border-radius: 10px;
      padding: 9px 12px;
      font-size: 14px;
    }
    button { background: linear-gradient(120deg, var(--accent), #f97316); color: #111827; font-weight: 700; cursor: pointer; }
    table { width: 100%; border-collapse: collapse; font-family: 'Trebuchet MS', Verdana, sans-serif; }
    th, td { padding: 9px 8px; border-bottom: 1px solid rgba(148,163,184,0.2); text-align: left; }
    th { color: #fde68a; font-size: 13px; text-transform: uppercase; letter-spacing: 0.7px; }
    tr:hover { background: rgba(16,185,129,0.08); }
    a { color: #86efac; }
    @keyframes in { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="hero">
      <h1>Evolution des genres musicaux</h1>
      <p class="sub">Analyse multi-charts Billboard par decennie ou par annee, avec classement des genres les plus representes.</p>
      <p class="sub">Page bonus: <a href="/page/michael-jackson">Heritage de Michael Jackson</a></p>
    </div>
    <div class="box">
      <div class="controls">
        <select id="period">
          <option value="decennie" selected>Decennie</option>
          <option value="annee">Annee</option>
        </select>
        <select id="chart">
          <option value="all" selected>Tous les charts</option>
          <option value="hot100">Hot 100</option>
          <option value="billboard200">Billboard 200</option>
          <option value="radio">Radio</option>
          <option value="digital_songs">Digital Songs</option>
          <option value="streaming_songs">Streaming Songs</option>
        </select>
        <button onclick="charger()">Analyser</button>
      </div>
      <div id="meta" style="color:#a7f3d0; margin-bottom:10px;"></div>
      <table>
        <thead><tr><th>Periode</th><th>Genre</th><th>Entrees</th><th>Rang moyen</th></tr></thead>
        <tbody id="body"></tbody>
      </table>
    </div>
  </div>
  <script>
    async function charger() {
      const period = document.getElementById('period').value;
      const chart = document.getElementById('chart').value;
      const r = await fetch(`/genres/evolution?period=${period}&chart=${chart}&top_n=10`);
      const data = await r.json();
      document.getElementById('meta').textContent = `${data.resume.lignes_analysees} lignes analysees, ${data.resume.genres_uniques} genres detectes.`;
      const body = document.getElementById('body');
      body.innerHTML = '';
      for (const row of data.resultats) {
        body.innerHTML += `<tr><td>${row.periode}</td><td>${row.track_genre}</td><td>${row.entrees}</td><td>${row.rang_moyen}</td></tr>`;
      }
    }
    charger();
  </script>
</body>
</html>
""", 200, {"Content-Type": "text/html; charset=utf-8"}


@app.get("/page/michael-jackson")
def page_michael_jackson():
    """Page bonus: synthese heritage Michael Jackson."""
    return """
<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Heritage Michael Jackson</title>
  <style>
    :root {
      --bg: #111111;
      --gold: #facc15;
      --crimson: #b91c1c;
      --ice: #f5f5f4;
      --muted: #d6d3d1;
    }
    body {
      margin: 0;
      color: var(--ice);
      font-family: 'Palatino Linotype', 'Book Antiqua', serif;
      min-height: 100vh;
      background:
        radial-gradient(circle at 15% 20%, rgba(250,204,21,0.17), transparent 32%),
        radial-gradient(circle at 80% 25%, rgba(185,28,28,0.22), transparent 36%),
        linear-gradient(160deg, #090909 0%, #151515 55%, #222 100%);
    }
    .wrap { max-width: 980px; margin: 0 auto; padding: 34px 18px; }
    h1 { margin: 0 0 8px; font-size: clamp(2rem, 4vw, 3.1rem); color: var(--gold); }
    p { color: var(--muted); }
    .grid { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); margin-top: 18px; }
    .kpi {
      border-radius: 14px;
      padding: 14px;
      border: 1px solid rgba(250,204,21,0.25);
      background: linear-gradient(180deg, rgba(255,255,255,0.05), rgba(255,255,255,0.01));
    }
    .lab { font-size: 12px; text-transform: uppercase; letter-spacing: 0.7px; color: #fef3c7; }
    .val { font-size: 28px; font-weight: bold; margin-top: 6px; }
    ul { line-height: 1.6; }
    a { color: #fbbf24; }
  </style>
</head>
<body>
  <div class="wrap">
    <h1>Heritage de Michael Jackson</h1>
    <p>Une lecture data des performances charts de l'artiste et des genres qui traversent son empreinte musicale.</p>
    <div class="grid" id="kpi"></div>
    <h3>Top morceaux iconiques (Top 10)</h3>
    <ul id="songs"></ul>
    <h3>Genres dominants</h3>
    <ul id="genres"></ul>
    <p><a href="/page/genres">Revenir a l'evolution des genres</a></p>
  </div>
  <script>
    async function charger() {
      const r = await fetch('/michael-jackson/heritage');
      const data = await r.json();
      const kpi = document.getElementById('kpi');
      kpi.innerHTML = `
        <div class='kpi'><div class='lab'>Entrees</div><div class='val'>${data.entrees_total}</div></div>
        <div class='kpi'><div class='lab'>Top 10</div><div class='val'>${data.top_10_total}</div></div>
        <div class='kpi'><div class='lab'>Meilleur rang</div><div class='val'>#${data.best_rank ?? '-'}</div></div>
        <div class='kpi'><div class='lab'>Periode</div><div class='val' style='font-size:16px'>${data.premiere_apparition ?? '-'} -> ${data.derniere_apparition ?? '-'}</div></div>
      `;
      document.getElementById('songs').innerHTML = data.morceaux_iconiques.map(s => `<li>${s.song} (rang #${s.rank}, ${s.date})</li>`).join('');
      document.getElementById('genres').innerHTML = data.genres_dominants.map(g => `<li>${g.track_genre} (${g.occurrences})</li>`).join('');
    }
    charger();
  </script>
</body>
</html>
""", 200, {"Content-Type": "text/html; charset=utf-8"}


# ---------------------------------------------------------------------------
# Authentification
# ---------------------------------------------------------------------------

@app.post("/register")
def register():
    body = request.get_json(silent=True) or {}
    username = (body.get("username") or "").strip()
    email = (body.get("email") or "").strip()
    password = body.get("password") or ""

    # Validation basique des champs
    if len(username) < 3 or len(username) > 50:
        return jsonify({"error": "nom d'utilisateur invalide (3 a 50 caracteres)"}), 400
    if "@" not in email:
        return jsonify({"error": "email invalide"}), 400
    if len(password) < 8:
        return jsonify({"error": "mot de passe trop court (8 caracteres minimum)"}), 400

    session_db = SessionLocal()
    try:
        if session_db.query(User).filter(User.username == username).first():
            return jsonify({"error": "nom d'utilisateur deja utilise"}), 409

        utilisateur = User(
            username=username,
            email=encrypt_field(email),
            password_hash=hash_password(password),
            role="user",
        )
        session_db.add(utilisateur)
        session_db.commit()
        session_db.refresh(utilisateur)
        return jsonify({"message": "inscription reussie", "id": utilisateur.id, "username": utilisateur.username}), 201
    except IntegrityError:
        session_db.rollback()
        return jsonify({"error": "email deja utilise"}), 409
    finally:
        session_db.close()


@app.post("/login")
def login():
    body = request.get_json(silent=True) or {}
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""

    if not username or not password:
        return jsonify({"error": "username et password requis"}), 400

    session_db = SessionLocal()
    try:
        utilisateur = session_db.query(User).filter(User.username == username).first()
        if not utilisateur or not verify_password(password, utilisateur.password_hash):
            return jsonify({"error": "identifiants invalides"}), 401

        access_token = create_access_token(utilisateur.id, utilisateur.role, expires_minutes=ACCESS_TOKEN_TTL_MINUTES)
        refresh_token = create_refresh_token(utilisateur.id, utilisateur.role)

        return jsonify({
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "Bearer",
            "expires_in_minutes": ACCESS_TOKEN_TTL_MINUTES,
            "refresh_expires_in_minutes": 60 * 24 * 7,
            "user_id": utilisateur.id,
            "username": utilisateur.username,
            "role": utilisateur.role,
        }), 200
    finally:
        session_db.close()


@app.post("/refresh")
def refresh():
    body = request.get_json(silent=True) or {}
    token_recu = body.get("refresh_token") or ""

    if not token_recu:
        return jsonify({"error": "refresh_token requis"}), 400

    payload = verify_token(token_recu, expected_type="refresh")
    if not payload:
        return jsonify({"error": "refresh token invalide ou expire"}), 401

    session_db = SessionLocal()
    try:
        utilisateur = session_db.query(User).filter(User.id == payload.get("user_id")).first()
        if not utilisateur:
            return jsonify({"error": "utilisateur introuvable"}), 404

        nouvel_access = create_access_token(utilisateur.id, utilisateur.role, expires_minutes=ACCESS_TOKEN_TTL_MINUTES)
        nouveau_refresh = create_refresh_token(utilisateur.id, utilisateur.role)

        return jsonify({
            "access_token": nouvel_access,
            "refresh_token": nouveau_refresh,
            "token_type": "Bearer",
            "expires_in_minutes": ACCESS_TOKEN_TTL_MINUTES,
            "refresh_expires_in_minutes": 60 * 24 * 7,
        }), 200
    finally:
        session_db.close()


@app.get("/protected")
@token_requis
def protected(payload):
    session_db = SessionLocal()
    try:
        utilisateur = session_db.query(User).filter(User.id == payload.get("user_id")).first()
        if not utilisateur:
            return jsonify({"error": "utilisateur introuvable"}), 404

        try:
            email = decrypt_field(utilisateur.email)
        except Exception:
            email = None

        return jsonify({
            "id": utilisateur.id,
            "username": utilisateur.username,
            "role": utilisateur.role,
            "email": email,
        }), 200
    finally:
        session_db.close()


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

@app.get("/stats")
def stats():
    session_db = SessionLocal()
    try:
        total_lignes = int(session_db.query(func.count(MusicGenreObservation.id)).scalar() or 0)
        total_artistes = int(session_db.query(func.count(func.distinct(MusicGenreObservation.artist))).scalar() or 0)
        total_morceaux = int(session_db.query(func.count(func.distinct(MusicGenreObservation.song))).scalar() or 0)

        avec_genre = int(
            session_db.query(func.count(MusicGenreObservation.id))
            .filter(MusicGenreObservation.track_genre.isnot(None))
            .filter(func.lower(func.trim(MusicGenreObservation.track_genre)).notin_(GENRES_INCONNUS))
            .scalar() or 0
        )

        sources_rows = (
            session_db.query(MusicGenreObservation.genre_source, func.count(MusicGenreObservation.id))
            .group_by(MusicGenreObservation.genre_source)
            .all()
        )
        sources_genres = {str(src or "inconnu"): int(total) for src, total in sources_rows}

        debut = session_db.query(func.min(MusicGenreObservation.date)).scalar()
        fin = session_db.query(func.max(MusicGenreObservation.date)).scalar()

        return jsonify({
            "total_lignes": total_lignes,
            "total_artistes": total_artistes,
            "total_morceaux": total_morceaux,
            "couverture_genres": {
                "avec_genre": avec_genre,
                "sans_genre": total_lignes - avec_genre,
                "pourcentage_avec_genre": round((avec_genre / total_lignes) * 100, 2) if total_lignes > 0 else 0.0,
            },
            "sources_genres": sources_genres,
            "periode": {
                "debut": str(debut) if debut else None,
                "fin": str(fin) if fin else None,
            },
        }), 200
    finally:
        session_db.close()


@app.get("/genres/evolution")
def genres_evolution():
    period = request.args.get("period", "decennie").lower().strip()
    top_n_str = request.args.get("top_n", "8")
    top_n = int(top_n_str) if top_n_str.isdigit() else 8
    chart = request.args.get("chart", "all").lower().strip()
    genre_source = request.args.get("genre_source", "all").lower().strip()

    if period not in ["decennie", "annee"]:
        return jsonify({"error": "period doit etre 'decennie' ou 'annee'"}), 400

    session_db = SessionLocal()
    try:
        periode_col = MusicGenreObservation.annee if period == "annee" else MusicGenreObservation.decennie

        query = session_db.query(
            periode_col.label("periode"),
            MusicGenreObservation.track_genre,
            func.count(MusicGenreObservation.id).label("entrees"),
            func.avg(MusicGenreObservation.rank).label("rang_moyen"),
        )

        # Filtres optionnels
        if chart != "all":
            query = query.filter(MusicGenreObservation.source_chart == chart)
        if genre_source != "all":
            query = query.filter(MusicGenreObservation.genre_source == genre_source)

        # Exclure les genres inconnus
        query = query.filter(MusicGenreObservation.track_genre.isnot(None))
        query = query.filter(
            func.lower(func.trim(MusicGenreObservation.track_genre)).notin_(GENRES_INCONNUS)
        )

        rows = query.group_by(periode_col, MusicGenreObservation.track_genre).all()

        # Regrouper par periode et garder le top N
        par_periode = {}
        for row in rows:
            p = str(row.periode)
            par_periode.setdefault(p, []).append({
                "periode": p,
                "track_genre": row.track_genre,
                "entrees": int(row.entrees),
                "rang_moyen": round(float(row.rang_moyen or 0), 2),
            })

        resultats = []
        for p in sorted(par_periode.keys()):
            top = sorted(par_periode[p], key=lambda x: x["entrees"], reverse=True)[:top_n]
            resultats.extend(top)

        genres_uniques = len(set(r["track_genre"] for r in resultats))

        return jsonify({
            "periode": period,
            "chart": chart,
            "genre_source": genre_source,
            "resultats": resultats,
            "resume": {
                "lignes_analysees": sum(r["entrees"] for r in resultats),
                "genres_uniques": genres_uniques,
            },
        }), 200
    finally:
        session_db.close()


@app.get("/genres/longevite")
def genres_longevite():
    top_n = min(int(request.args.get("top_n", 10)), 30)
    session_db = SessionLocal()
    try:
        # Total semaines cumulées par genre (source billboard200)
        totaux = (
            session_db.query(
                MusicGenreObservation.track_genre.label("genre"),
                func.count(MusicGenreObservation.id).label("semaines"),
            )
            .filter(MusicGenreObservation.source_chart == "billboard200")
            .filter(MusicGenreObservation.track_genre.isnot(None))
            .filter(func.lower(func.trim(MusicGenreObservation.track_genre)).notin_(GENRES_INCONNUS))
            .group_by(MusicGenreObservation.track_genre)
            .order_by(func.count(MusicGenreObservation.id).desc())
            .limit(top_n)
            .all()
        )
        top_genres = [r.genre for r in totaux]

        # Artiste leader (le plus d'entrées) pour chaque genre
        leaders = {}
        for genre in top_genres:
            leader = (
                session_db.query(
                    MusicGenreObservation.artist,
                    func.count(MusicGenreObservation.id).label("cnt"),
                )
                .filter(MusicGenreObservation.source_chart == "billboard200")
                .filter(MusicGenreObservation.track_genre == genre)
                .group_by(MusicGenreObservation.artist)
                .order_by(func.count(MusicGenreObservation.id).desc())
                .first()
            )
            leaders[genre] = leader.artist if leader else ""

        return jsonify([
            {"genre": r.genre, "semaines": int(r.semaines), "artiste_leader": leaders.get(r.genre, "")}
            for r in totaux
        ]), 200
    finally:
        session_db.close()


@app.get("/genres/popularite")
def genres_popularite():
    """Popularité Spotify moyenne par genre pour les morceaux dans le Top 10 Billboard."""
    top_n = min(int(request.args.get("top_n", 10)), 30)
    # Mapping genres DB -> genres CSV
    GENRE_CSV = {"r&b": "r-n-b"}
    CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "train.csv"
    try:
        df_pop = pd.read_csv(CSV_PATH, usecols=["track_genre", "popularity"])
    except FileNotFoundError:
        return jsonify({"error": "fichier train.csv introuvable"}), 500

    pop_par_genre = df_pop.groupby("track_genre")["popularity"].mean().round(1).to_dict()

    session_db = SessionLocal()
    try:
        rows = (
            session_db.query(
                MusicGenreObservation.track_genre.label("genre"),
                func.count(MusicGenreObservation.id).label("cnt"),
            )
            .filter(MusicGenreObservation.source_chart == "billboard200")
            .filter(MusicGenreObservation.rank <= 10)
            .filter(MusicGenreObservation.track_genre.isnot(None))
            .filter(func.lower(func.trim(MusicGenreObservation.track_genre)).notin_(GENRES_INCONNUS))
            .group_by(MusicGenreObservation.track_genre)
            .order_by(func.count(MusicGenreObservation.id).desc())
            .limit(top_n)
            .all()
        )
        resultats = []
        for r in rows:
            genre_db = r.genre
            genre_csv = GENRE_CSV.get(genre_db, genre_db)
            pop = pop_par_genre.get(genre_csv)
            if pop is not None:
                resultats.append({"genre": genre_db, "popularite_moyenne": float(pop)})
        resultats.sort(key=lambda x: x["popularite_moyenne"], reverse=True)
        return jsonify(resultats), 200
    finally:
        session_db.close()


@app.get("/genres/domination")
def genres_domination():
    top_n = min(int(request.args.get("top_n", 10)), 30)
    session_db = SessionLocal()
    try:
        rows = (
            session_db.query(
                MusicGenreObservation.track_genre.label("genre"),
                func.count(MusicGenreObservation.id).label("nb_apparitions"),
                func.avg(MusicGenreObservation.rank).label("rank_moyen"),
            )
            .filter(MusicGenreObservation.track_genre.isnot(None))
            .filter(func.lower(func.trim(MusicGenreObservation.track_genre)).notin_(GENRES_INCONNUS))
            .filter(MusicGenreObservation.rank.isnot(None))
            .group_by(MusicGenreObservation.track_genre)
            .order_by(func.count(MusicGenreObservation.id).desc())
            .limit(top_n)
            .all()
        )
        return jsonify([
            {"genre": r.genre, "nb_apparitions": int(r.nb_apparitions), "rank_moyen": round(float(r.rank_moyen), 1)}
            for r in rows
        ]), 200
    finally:
        session_db.close()


@app.get("/genres/totaux")
def genres_totaux():
    period = request.args.get("period", "decennie").lower().strip()
    chart = request.args.get("chart", "all").lower().strip()

    if period not in ["decennie", "annee"]:
        return jsonify({"error": "period doit etre 'decennie' ou 'annee'"}), 400

    session_db = SessionLocal()
    try:
        periode_col = MusicGenreObservation.annee if period == "annee" else MusicGenreObservation.decennie

        query = session_db.query(
            periode_col.label("periode"),
            func.count(MusicGenreObservation.id).label("entrees_totales"),
            func.count(func.distinct(MusicGenreObservation.track_genre)).label("genres_uniques"),
        )
        if chart != "all":
            query = query.filter(MusicGenreObservation.source_chart == chart)
        query = query.filter(MusicGenreObservation.track_genre.isnot(None))
        query = query.filter(
            func.lower(func.trim(MusicGenreObservation.track_genre)).notin_(GENRES_INCONNUS)
        )

        rows = query.group_by(periode_col).order_by(periode_col).all()
        totaux = [
            {"periode": str(r.periode), "entrees_totales": int(r.entrees_totales), "genres_uniques": int(r.genres_uniques)}
            for r in rows
        ]

        return jsonify({
            "periode": period,
            "totaux_par_periode": totaux,
            "resume": {
                "lignes_analysees": sum(r["entrees_totales"] for r in totaux),
                "genres_uniques": int(query.with_entities(func.count(func.distinct(MusicGenreObservation.track_genre))).scalar() or 0),
            },
        }), 200
    finally:
        session_db.close()


@app.get("/michael-jackson/heritage")
def michael_jackson_heritage():
    session_db = SessionLocal()
    try:
        base = session_db.query(MusicGenreObservation).filter(
            func.lower(MusicGenreObservation.artist).like("%michael jackson%")
        )

        base_bb = base.filter(MusicGenreObservation.source_chart == "billboard200")

        entrees_total = int(base.count())
        if entrees_total == 0:
            return jsonify({"artiste": "Michael Jackson", "entrees_total": 0}), 200

        # KPIs Billboard 200
        semaines_totales = int(base_bb.count())
        titres_distincts = int(base_bb.with_entities(func.count(func.distinct(MusicGenreObservation.song))).scalar() or 0)
        semaines_rang1 = int(base_bb.filter(MusicGenreObservation.rank == 1).count())

        top_10_total = int(base.filter(MusicGenreObservation.rank <= 10).count())
        best_rank = base.with_entities(func.min(MusicGenreObservation.rank)).scalar()
        premiere = base.with_entities(func.min(MusicGenreObservation.date)).scalar()
        derniere = base.with_entities(func.max(MusicGenreObservation.date)).scalar()

        # Évolution par année (Billboard 200)
        evo_rows = (
            base_bb
            .with_entities(MusicGenreObservation.annee.label("annee"), func.count().label("semaines"))
            .group_by(MusicGenreObservation.annee)
            .order_by(MusicGenreObservation.annee)
            .all()
        )
        evolution_annuelle = [{"annee": int(r.annee), "semaines": int(r.semaines)} for r in evo_rows if r.annee]

        # Top 10 albums par semaines cumulées (Billboard 200)
        albums_rows = (
            base_bb
            .with_entities(MusicGenreObservation.song.label("titre"), func.count().label("semaines"))
            .group_by(MusicGenreObservation.song)
            .order_by(func.count().desc())
            .limit(10)
            .all()
        )
        top_albums = [{"titre": r.titre, "semaines": int(r.semaines)} for r in albums_rows]

        # Morceaux iconiques dedupliques
        rows_icones = (
            base.filter(MusicGenreObservation.rank <= 10)
            .with_entities(MusicGenreObservation.song, MusicGenreObservation.rank, MusicGenreObservation.date)
            .order_by(MusicGenreObservation.rank.asc())
            .all()
        )
        vus = set()
        morceaux = []
        for row in rows_icones:
            key = (row.song or "").strip().lower()
            if key not in vus:
                vus.add(key)
                morceaux.append({"song": row.song, "rank": int(row.rank), "date": str(row.date)})
            if len(morceaux) >= 12:
                break

        # Genres les plus frequents
        genres = (
            base.with_entities(MusicGenreObservation.track_genre, func.count(MusicGenreObservation.id).label("occ"))
            .filter(MusicGenreObservation.track_genre.isnot(None))
            .group_by(MusicGenreObservation.track_genre)
            .order_by(func.count(MusicGenreObservation.id).desc())
            .limit(6)
            .all()
        )

        return jsonify({
            "artiste": "Michael Jackson",
            "entrees_total": entrees_total,
            "semaines_totales": semaines_totales,
            "titres_distincts": titres_distincts,
            "semaines_rang1": semaines_rang1,
            "top_10_total": top_10_total,
            "best_rank": int(best_rank) if best_rank else None,
            "premiere_apparition": str(premiere) if premiere else None,
            "derniere_apparition": str(derniere) if derniere else None,
            "evolution_annuelle": evolution_annuelle,
            "top_albums": top_albums,
            "morceaux_iconiques": morceaux,
            "genres_dominants": [{"track_genre": g.track_genre, "occurrences": int(g.occ)} for g in genres],
        }), 200
    finally:
        session_db.close()


@app.get("/michael-jackson/thriller")
def michael_jackson_thriller():
    session_db = SessionLocal()
    try:
        rows = (
            session_db.query(
                MusicGenreObservation.annee.label("annee"),
                func.count().label("semaines"),
                func.min(MusicGenreObservation.rank).label("best_rank"),
                func.avg(MusicGenreObservation.rank).label("avg_rank"),
            )
            .filter(MusicGenreObservation.source_chart == "billboard200")
            .filter(func.lower(MusicGenreObservation.song).like("%thriller%"))
            .filter(func.lower(MusicGenreObservation.artist).like("%michael jackson%"))
            .group_by(MusicGenreObservation.annee)
            .order_by(MusicGenreObservation.annee)
            .all()
        )
        return jsonify([
            {
                "annee": int(r.annee),
                "semaines": int(r.semaines),
                "best_rank": int(r.best_rank),
                "avg_rank": round(float(r.avg_rank), 1),
            }
            for r in rows if r.annee
        ]), 200
    finally:
        session_db.close()


@app.get("/michael-jackson/comparaison")
def michael_jackson_comparaison():
    ARTISTES = ["The Beatles", "Elton John", "Michael Jackson", "Taylor Swift", "Madonna", "Prince"]
    session_db = SessionLocal()
    try:
        resultats = []
        for artiste in ARTISTES:
            pattern = f"%{artiste.lower()}%"
            sem = session_db.query(func.count()).filter(
                MusicGenreObservation.source_chart == "billboard200",
                func.lower(MusicGenreObservation.artist).like(pattern),
            ).scalar() or 0
            titres = session_db.query(func.count(func.distinct(MusicGenreObservation.song))).filter(
                MusicGenreObservation.source_chart == "billboard200",
                func.lower(MusicGenreObservation.artist).like(pattern),
            ).scalar() or 0
            resultats.append({"artiste": artiste, "semaines": int(sem), "nb_titres": int(titres)})
        resultats.sort(key=lambda x: x["semaines"], reverse=True)
        return jsonify(resultats), 200
    finally:
        session_db.close()


@app.post("/admin/sync-analytics-db")
@token_requis
def sync_analytics_db(_payload):
    """Recharge la table analytics depuis musique_complete.csv (admin uniquement)."""
    try:
        resultat = _synchroniser_observations_genres_depuis_csv()
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"message": "synchronisation terminee", **resultat}), 200


@app.get("/datasets")
@token_requis
def datasets(_payload):
    dossier_clean = os.path.join(os.path.dirname(__file__), "..", "data", "clean")
    jeux = charger_tous_les_datasets(dossier_data=dossier_clean)
    infos = []
    for nom, frame in jeux.items():
        infos.append({
            "fichier": nom,
            "lignes": len(frame),
            "colonnes": list(frame.columns),
        })
    return jsonify({"datasets": infos}), 200


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
