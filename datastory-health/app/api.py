"""API Flask du projet DataStory Music."""

from functools import wraps
import os

from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from pydantic import BaseModel, EmailStr, ValidationError, field_validator
from sqlalchemy.exc import IntegrityError

try:
    from .auth import create_token, decrypt_field, encrypt_field, hash_password, verify_password, verify_token
    from .data_processing import charger_tous_les_datasets, load_music_complete_data, prepare_charts_data
    from .models import SessionLocal, User, init_db
except ImportError:
    from auth import create_token, decrypt_field, encrypt_field, hash_password, verify_password, verify_token
    from data_processing import charger_tous_les_datasets, load_music_complete_data, prepare_charts_data
    from models import SessionLocal, User, init_db


app = Flask(__name__)
CORS(app)

limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=["600 per day", "120 per hour"],
    storage_uri="memory://",
)


@app.errorhandler(429)
def gerer_rate_limit(_erreur):
    """Retour JSON uniforme quand une limite de requetes est atteinte."""
    return jsonify({"error": "trop_de_requetes", "message": "Rate limit depasse, reessayez plus tard."}), 429


class RegisterRequest(BaseModel):
    """Corps attendu pour l'inscription."""

    username: str
    email: EmailStr
    password: str

    @field_validator("username")
    @classmethod
    def username_length(cls, valeur: str) -> str:
        valeur = valeur.strip()
        if len(valeur) < 3:
            raise ValueError("le nom d'utilisateur doit contenir au moins 3 caracteres")
        if len(valeur) > 50:
            raise ValueError("le nom d'utilisateur doit contenir au maximum 50 caracteres")
        return valeur

    @field_validator("password")
    @classmethod
    def password_length(cls, valeur: str) -> str:
        if len(valeur) < 8:
            raise ValueError("le mot de passe doit contenir au moins 8 caracteres")
        return valeur


class RequeteConnexion(BaseModel):
    """Corps attendu pour la connexion."""

    username: str
    password: str


def erreur_validation(erreur: ValidationError):
    """Retourne une reponse uniforme quand la validation Pydantic echoue."""
    return jsonify({"error": "erreur_validation", "details": erreur.errors()}), 400


def token_requis(func):
    """Verifie le JWT dans l'en-tete Authorization avant d'acceder a la route."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        en_tete_auth = request.headers.get("Authorization", "")
        if not en_tete_auth.startswith("Bearer "):
            return jsonify({"error": "entete_authorization_absent_ou_invalide"}), 401

        token = en_tete_auth.replace("Bearer ", "", 1).strip()
        charge_utile = verify_token(token)
        if not charge_utile:
            return jsonify({"error": "token_invalide_ou_expire"}), 401

        return func(charge_utile, *args, **kwargs)

    return wrapper


def _calculer_evolution_genres(period: str = "decennie", chart: str = "all", top_n: int = 8):
    """Agrege l'evolution des genres selon la periode demandee."""
    data = load_music_complete_data()
    data = prepare_charts_data(data)
    if data.empty:
        return {
            "periode": period,
            "chart": chart,
            "resultats": [],
            "resume": {"lignes_analysees": 0, "genres_uniques": 0},
        }

    if chart != "all" and "source_chart" in data.columns:
        data = data[data["source_chart"] == chart]

    if "track_genre" not in data.columns:
        data["track_genre"] = "inconnu"
    data["track_genre"] = data["track_genre"].fillna("inconnu")

    if period == "annee":
        data["periode"] = data["annee"].astype(int).astype(str)
    else:
        data["periode"] = data["decennie"].astype(int).astype(str) + "s"

    group = (
        data.groupby(["periode", "track_genre"], as_index=False)
        .agg(entrees=("song", "count"), rang_moyen=("rank", "mean"))
        .sort_values(["periode", "entrees"], ascending=[True, False])
    )

    top = group.groupby("periode", as_index=False).head(top_n).copy()
    top["rang_moyen"] = top["rang_moyen"].round(2)

    return {
        "periode": period,
        "chart": chart,
        "resultats": top.to_dict(orient="records"),
        "resume": {
            "lignes_analysees": int(len(data)),
            "genres_uniques": int(data["track_genre"].nunique()),
        },
    }


def _calculer_heritage_michael_jackson():
    """Construit des indicateurs sur l'heritage chart de Michael Jackson."""
    data = load_music_complete_data()
    data = prepare_charts_data(data)
    if data.empty:
        return {
            "artiste": "Michael Jackson",
            "entrees_total": 0,
            "top_10_total": 0,
            "best_rank": None,
            "premiere_apparition": None,
            "derniere_apparition": None,
            "morceaux_iconiques": [],
            "genres_dominants": [],
        }

    masque = data["artist"].astype(str).str.contains("michael jackson", case=False, na=False)
    mj = data[masque].copy()

    if mj.empty:
        return {
            "artiste": "Michael Jackson",
            "entrees_total": 0,
            "top_10_total": 0,
            "best_rank": None,
            "premiere_apparition": None,
            "derniere_apparition": None,
            "morceaux_iconiques": [],
            "genres_dominants": [],
        }

    morceaux_iconiques = (
        mj[mj["rank"] <= 10]
        .sort_values(["rank", "date"])
        .drop_duplicates(subset=["song"])
        .head(12)[["song", "rank", "date"]]
    )
    morceaux_iconiques["date"] = morceaux_iconiques["date"].astype(str)

    genres = (
        mj.groupby("track_genre", as_index=False)
        .size()
        .sort_values("size", ascending=False)
        .head(6)
        .rename(columns={"size": "occurrences"})
        .to_dict(orient="records")
    )

    return {
        "artiste": "Michael Jackson",
        "entrees_total": int(len(mj)),
        "top_10_total": int((mj["rank"] <= 10).sum()),
        "best_rank": int(mj["rank"].min()),
        "premiere_apparition": str(mj["date"].min().date()),
        "derniere_apparition": str(mj["date"].max().date()),
        "morceaux_iconiques": morceaux_iconiques.to_dict(orient="records"),
        "genres_dominants": genres,
    }


@app.get("/health")
def health():
    return jsonify({"statut": "ok", "theme": "musique"}), 200


@app.get("/")
def accueil():
    return (
        jsonify(
            {
                "message": "API DataStory Music active",
                "theme": "Evolution des genres musicaux par periodes",
                "pages": ["/page/genres", "/page/michael-jackson"],
                "endpoints_utiles": [
                    "/health",
                    "/docs",
                    "/register",
                    "/login",
                    "/genres/evolution",
                    "/michael-jackson/heritage",
                ],
            }
        ),
        200,
    )


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


@app.post("/register")
@limiter.limit("3 per minute")
def register():
    try:
        donnees = RegisterRequest(**(request.get_json(silent=True) or {}))
    except ValidationError as erreur:
        return erreur_validation(erreur)

    session_db = SessionLocal()
    try:
        utilisateur_existant = session_db.query(User).filter(User.username == donnees.username).first()
        if utilisateur_existant:
            return jsonify({"error": "nom_utilisateur_deja_existant"}), 409

        courriel_chiffre = encrypt_field(donnees.email)
        empreinte_mot_de_passe = hash_password(donnees.password)

        utilisateur = User(
            username=donnees.username,
            email=courriel_chiffre,
            password_hash=empreinte_mot_de_passe,
            role="user",
        )
        session_db.add(utilisateur)
        session_db.commit()
        session_db.refresh(utilisateur)

        return jsonify({"id": utilisateur.id, "username": utilisateur.username, "role": utilisateur.role}), 201
    except IntegrityError:
        session_db.rollback()
        return jsonify({"error": "conflit_creation_utilisateur"}), 409
    except Exception:
        session_db.rollback()
        return jsonify({"error": "echec_inscription"}), 500
    finally:
        session_db.close()


@app.post("/login")
@limiter.limit("5 per minute")
def login():
    try:
        donnees = RequeteConnexion(**(request.get_json(silent=True) or {}))
    except ValidationError as erreur:
        return erreur_validation(erreur)

    session_db = SessionLocal()
    try:
        utilisateur = session_db.query(User).filter(User.username == donnees.username).first()
        if not utilisateur or not verify_password(donnees.password, utilisateur.password_hash):
            return jsonify({"error": "identifiants_invalides"}), 401

        token = create_token(utilisateur.id, utilisateur.role, expires_minutes=30)
        return jsonify({"access_token": token, "token_type": "Bearer", "expires_in_minutes": 30}), 200
    finally:
        session_db.close()


@app.get("/protected")
@limiter.limit("30 per minute")
@token_requis
def protected(charge_utile):
    session_db = SessionLocal()
    try:
        utilisateur = session_db.query(User).filter(User.id == charge_utile.get("user_id")).first()
        if not utilisateur:
            return jsonify({"error": "utilisateur_introuvable"}), 404

        courriel = None
        try:
            courriel = decrypt_field(utilisateur.email)
        except Exception:
            courriel = None

        return jsonify({"id": utilisateur.id, "username": utilisateur.username, "role": utilisateur.role, "email": courriel}), 200
    finally:
        session_db.close()


@app.get("/stats")
@limiter.limit("60 per minute")
def stats():
    data = load_music_complete_data()
    data = prepare_charts_data(data)
    if data.empty:
        return jsonify({"total_lignes": 0, "total_artistes": 0, "total_morceaux": 0, "periode": None}), 200

    return (
        jsonify(
            {
                "total_lignes": int(len(data)),
                "total_artistes": int(data["artist"].nunique()),
                "total_morceaux": int(data["song"].nunique()),
                "periode": {
                    "debut": str(data["date"].min().date()),
                    "fin": str(data["date"].max().date()),
                },
            }
        ),
        200,
    )


@app.get("/datasets")
@limiter.limit("20 per minute")
@token_requis
def datasets(_charge_utile):
    dossier_clean = os.path.join(os.path.dirname(__file__), "..", "data", "clean")
    jeux = charger_tous_les_datasets(dossier_data=dossier_clean)

    infos = []
    for nom_fichier, frame in jeux.items():
        infos.append(
            {
                "fichier": nom_fichier,
                "lignes": int(len(frame)),
                "colonnes": list(frame.columns),
                "types": {colonne: str(dtype) for colonne, dtype in frame.dtypes.items()},
            }
        )

    return jsonify({"dossier": "data/clean", "nb_datasets": len(infos), "datasets": infos}), 200


@app.get("/genres/evolution")
@limiter.limit("60 per minute")
def genres_evolution():
    period = request.args.get("period", "decennie").lower().strip()
    chart = request.args.get("chart", "all").lower().strip()
    top_n = request.args.get("top_n", "8").strip()

    if period not in ["decennie", "annee"]:
        return jsonify({"error": "period doit etre 'decennie' ou 'annee'"}), 400
    if not top_n.isdigit():
        return jsonify({"error": "top_n doit etre un entier positif"}), 400

    resultat = _calculer_evolution_genres(period=period, chart=chart, top_n=max(1, int(top_n)))
    return jsonify(resultat), 200


@app.get("/michael-jackson/heritage")
@limiter.limit("60 per minute")
def michael_jackson_heritage():
    return jsonify(_calculer_heritage_michael_jackson()), 200


@app.get("/docs")
@limiter.limit("120 per minute")
def docs():
    return (
        jsonify(
            {
                "title": "API DataStory Music",
                "version": "2.0.0",
                "theme": "Evolution des genres musicaux",
                "endpoints": [
                    {"method": "GET", "path": "/health", "auth": False, "description": "Verifier que l'API repond"},
                    {"method": "POST", "path": "/register", "auth": False, "rate_limit": "3/min", "description": "Inscrire un utilisateur"},
                    {"method": "POST", "path": "/login", "auth": False, "rate_limit": "5/min", "description": "Obtenir un token JWT"},
                    {"method": "GET", "path": "/protected", "auth": True, "rate_limit": "30/min", "description": "Acceder au profil utilisateur"},
                    {"method": "GET", "path": "/stats", "auth": False, "rate_limit": "60/min", "description": "Statistiques globales musique"},
                    {"method": "GET", "path": "/datasets", "auth": True, "rate_limit": "20/min", "description": "Lister les datasets nettoyes"},
                    {"method": "GET", "path": "/genres/evolution", "auth": False, "rate_limit": "60/min", "description": "Evolution des genres par periode"},
                    {"method": "GET", "path": "/michael-jackson/heritage", "auth": False, "rate_limit": "60/min", "description": "Page bonus Michael Jackson"},
                    {"method": "GET", "path": "/page/genres", "auth": False, "description": "Page narrative evolution des genres"},
                    {"method": "GET", "path": "/page/michael-jackson", "auth": False, "description": "Page heritage Michael Jackson"},
                ],
                "auth": {"type": "JWT Bearer", "header": "Authorization: Bearer <token>"},
            }
        ),
        200,
    )


@app.post("/refresh")
@limiter.limit("10 per minute")
@token_requis
def refresh_token(charge_utile):
    """Emet un nouveau JWT valide 30 min si le token courant est encore valide."""
    nouveau_token = create_token(charge_utile["user_id"], charge_utile["role"], expires_minutes=30)
    return jsonify({"access_token": nouveau_token, "token_type": "Bearer", "expires_in_minutes": 30}), 200


if __name__ == "__main__":
    init_db()
    app.run(host="127.0.0.1", port=5000, debug=True)
