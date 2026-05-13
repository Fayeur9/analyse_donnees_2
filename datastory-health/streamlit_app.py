"""Application Streamlit — DataStory Music.

Gestion du cycle de vie complet du jeton JWT :
  - Écran de connexion (login)
  - Stockage du token dans st.session_state
  - Rafraîchissement automatique (POST /refresh) quand il reste < 5 min
  - Déconnexion explicite
  - Redirection vers le login si le token est expiré
"""

import datetime
import json
from pathlib import Path

import requests
import streamlit as st

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
API_URL = "http://localhost:5000"
SEUIL_REFRESH_SECONDES = 5 * 60   # rafraîchir si < 5 min restantes
TIMEOUT_REQUETE = 10               # secondes max par appel HTTP
SESSION_FILE = Path(__file__).resolve().parent / ".streamlit_auth_session.json"

# ---------------------------------------------------------------------------
# Helpers — gestion du session_state
# ---------------------------------------------------------------------------

def _init_session():
    """Initialise les clés session_state si elles sont absentes."""
    defaults = {
        "access_token": None,
        "refresh_token": None,
        "expires_at": None,
        "refresh_expires_at": None,
        "access_ttl_seconds": 30 * 60,
        "username": None,
        "role": None,
        "user_id": None,
        "auth_view": "login",
        "login_error": "",
    }
    for cle, valeur in defaults.items():
        if cle not in st.session_state:
            st.session_state[cle] = valeur


def _stocker_token(
    token: str,
    expires_in_minutes: int,
    username: str,
    role: str,
    user_id: int,
    refresh_token: str | None = None,
    refresh_expires_in_minutes: int = 60 * 24 * 7,
):
    """Enregistre le token et ses métadonnées dans session_state."""
    st.session_state.access_token = token
    st.session_state.refresh_token = refresh_token
    st.session_state.access_ttl_seconds = max(1, int(expires_in_minutes * 60))
    st.session_state.expires_at = datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=expires_in_minutes)
    if refresh_token:
        st.session_state.refresh_expires_at = datetime.datetime.now(datetime.UTC) + datetime.timedelta(
            minutes=refresh_expires_in_minutes
        )
    else:
        st.session_state.refresh_expires_at = None
    st.session_state.username = username
    st.session_state.role = role
    st.session_state.user_id = user_id
    st.session_state.login_error = ""
    _sauvegarder_session_locale()


def _deconnecter():
    """Efface toutes les données de session."""
    for cle in [
        "access_token",
        "refresh_token",
        "expires_at",
        "refresh_expires_at",
        "access_ttl_seconds",
        "username",
        "role",
        "user_id",
    ]:
        st.session_state[cle] = None
    st.session_state.auth_view = "login"
    st.session_state.login_error = ""
    if SESSION_FILE.exists():
        SESSION_FILE.unlink()


def _sauvegarder_session_locale():
    """Sauvegarde la session auth localement pour survivre a un refresh navigateur."""
    if not st.session_state.get("access_token"):
        return

    payload = {
        "access_token": st.session_state.access_token,
        "refresh_token": st.session_state.refresh_token,
        "expires_at": st.session_state.expires_at.isoformat() if st.session_state.expires_at else None,
        "refresh_expires_at": st.session_state.refresh_expires_at.isoformat() if st.session_state.refresh_expires_at else None,
        "access_ttl_seconds": st.session_state.access_ttl_seconds,
        "username": st.session_state.username,
        "role": st.session_state.role,
        "user_id": st.session_state.user_id,
    }
    SESSION_FILE.write_text(json.dumps(payload), encoding="utf-8")


def _restaurer_session_locale() -> bool:
    """Recharge une session auth sauvegardee si elle est encore valide."""
    if not SESSION_FILE.exists() or st.session_state.get("access_token"):
        return False

    try:
        payload = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
        expires_raw = payload.get("expires_at")
        refresh_expires_raw = payload.get("refresh_expires_at")
        def _lire_dt(raw):
            if not raw:
                return None
            dt = datetime.datetime.fromisoformat(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.UTC)
            return dt

        expires_at = _lire_dt(expires_raw)
        refresh_expires_at = _lire_dt(refresh_expires_raw)
    except Exception:
        return False

    if not payload.get("access_token") or not expires_at or expires_at <= datetime.datetime.now(datetime.UTC):
        if (
            payload.get("refresh_token")
            and refresh_expires_at
            and refresh_expires_at > datetime.datetime.now(datetime.UTC)
        ):
            st.session_state.refresh_token = payload.get("refresh_token")
            st.session_state.refresh_expires_at = refresh_expires_at
            st.session_state.access_ttl_seconds = int(payload.get("access_ttl_seconds") or 30 * 60)
            st.session_state.username = payload.get("username")
            st.session_state.role = payload.get("role")
            st.session_state.user_id = payload.get("user_id")
            return True
        return False

    st.session_state.access_token = payload.get("access_token")
    st.session_state.refresh_token = payload.get("refresh_token")
    st.session_state.expires_at = expires_at
    st.session_state.refresh_expires_at = refresh_expires_at
    st.session_state.access_ttl_seconds = int(payload.get("access_ttl_seconds") or 30 * 60)
    st.session_state.username = payload.get("username")
    st.session_state.role = payload.get("role")
    st.session_state.user_id = payload.get("user_id")
    return True


def _est_connecte() -> bool:
    has_access = bool(st.session_state.get("access_token"))
    has_refresh = bool(st.session_state.get("refresh_token"))
    return has_access or has_refresh


def _secondes_restantes() -> float:
    """Retourne le nombre de secondes avant expiration du token (peut être négatif)."""
    if not st.session_state.expires_at:
        return 0.0
    delta = st.session_state.expires_at - datetime.datetime.now(datetime.UTC)
    return delta.total_seconds()


# ---------------------------------------------------------------------------
# Helpers — appels API
# ---------------------------------------------------------------------------

def _entete_auth() -> dict:
    return {"Authorization": f"Bearer {st.session_state.access_token}"}


def _tenter_refresh() -> bool:
    """Tente de rafraîchir le token via POST /refresh.
    Retourne True si réussi, False sinon (token expiré → déconnexion).
    """
    if not st.session_state.get("refresh_token"):
        return False

    if st.session_state.get("refresh_expires_at") and st.session_state.refresh_expires_at <= datetime.datetime.now(datetime.UTC):
        _deconnecter()
        return False

    try:
        rep = requests.post(
            f"{API_URL}/refresh",
            json={"refresh_token": st.session_state.refresh_token},
            timeout=TIMEOUT_REQUETE,
        )
    except requests.RequestException:
        return False

    if rep.status_code == 200:
        data = rep.json()
        st.session_state.access_token = data["access_token"]
        st.session_state.refresh_token = data.get("refresh_token", st.session_state.refresh_token)
        st.session_state.expires_at = datetime.datetime.now(datetime.UTC) + datetime.timedelta(
            minutes=data.get("expires_in_minutes", 30)
        )
        st.session_state.refresh_expires_at = datetime.datetime.now(datetime.UTC) + datetime.timedelta(
            minutes=data.get("refresh_expires_in_minutes", 60 * 24 * 7)
        )
        _sauvegarder_session_locale()
        return True

    # Token expiré ou invalide → déconnexion
    _deconnecter()
    return False


def _token_valide_ou_refresh() -> bool:
    """Vérifie la validité du token et le rafraîchit si nécessaire.
    Retourne False si l'utilisateur doit se reconnecter.
    """
    restant = _secondes_restantes()
    if not st.session_state.get("refresh_token"):
        if restant <= 0:
            _deconnecter()
            return False
        return True

    if restant <= 0:
        return _tenter_refresh()

    ttl = max(1, int(st.session_state.get("access_ttl_seconds") or 30 * 60))
    # Seuil effectif: 20% de la durée de vie (min 5s), plafonné par la config globale.
    seuil_effectif = min(SEUIL_REFRESH_SECONDES, max(5, int(ttl * 0.20)))
    if restant < seuil_effectif:
        return _tenter_refresh()
    return True


def _appel_api(methode: str, chemin: str, **kwargs) -> requests.Response | None:
    """Wrapper qui gère automatiquement le refresh avant l'appel."""
    if not _token_valide_ou_refresh():
        return None
    try:
        func = getattr(requests, methode.lower())
        return func(
            f"{API_URL}{chemin}",
            headers=_entete_auth(),
            timeout=TIMEOUT_REQUETE,
            **kwargs,
        )
    except requests.RequestException as exc:
        st.error(f"Erreur réseau : {exc}")
        return None


@st.cache_data(ttl=120, show_spinner=False)
def _get_public_json(chemin: str, params_items: tuple = ()):
    """Cache léger pour les endpoints publics afin de limiter les appels répétés."""
    params = dict(params_items) if params_items else None
    rep = requests.get(f"{API_URL}{chemin}", params=params, timeout=TIMEOUT_REQUETE)
    try:
        data = rep.json()
    except ValueError:
        data = {}
    return rep.status_code, data


# ---------------------------------------------------------------------------
# Page : connexion
# ---------------------------------------------------------------------------

def page_connexion():
    gauche, centre, droite = st.columns([1.5, 1, 1.5])
    del gauche, droite

    with centre:
        st.title("🎵 DataStory Music")
        st.subheader("Connexion")

        with st.form("form_login"):
            username = st.text_input("Nom d'utilisateur")
            password = st.text_input("Mot de passe", type="password")
            soumettre = st.form_submit_button("Se connecter", use_container_width=True)

        st.caption("Pas encore de compte ?")
        if st.button("Créer un compte"):
            st.session_state.auth_view = "register"
            st.rerun()

    if soumettre:
        if not username or not password:
            st.error("Veuillez remplir les deux champs.")
            return

        try:
            rep = requests.post(
                f"{API_URL}/login",
                json={"username": username, "password": password},
                timeout=TIMEOUT_REQUETE,
            )
        except requests.RequestException as exc:
            st.error(f"Impossible de joindre l'API : {exc}")
            return

        if rep.status_code == 200:
            data = rep.json()
            # Récupérer le profil pour avoir user_id et role
            token_tmp = data["access_token"]
            try:
                profil_rep = requests.get(
                    f"{API_URL}/protected",
                    headers={"Authorization": f"Bearer {token_tmp}"},
                    timeout=TIMEOUT_REQUETE,
                )
                profil = profil_rep.json() if profil_rep.status_code == 200 else {}
            except requests.RequestException:
                profil = {}

            _stocker_token(
                token=token_tmp,
                expires_in_minutes=data.get("expires_in_minutes", 30),
                username=profil.get("username", username),
                role=profil.get("role", "user"),
                user_id=profil.get("id"),
                refresh_token=data.get("refresh_token"),
                refresh_expires_in_minutes=data.get("refresh_expires_in_minutes", 60 * 24 * 7),
            )
            st.rerun()

        elif rep.status_code == 401:
            st.error("Identifiants incorrects.")
        elif rep.status_code == 429:
            st.warning("Trop de tentatives. Réessayez dans une minute.")
        else:
            st.error(f"Erreur inattendue ({rep.status_code}).")


def page_inscription():
    gauche, centre, droite = st.columns([1.5, 1, 1.5])
    del gauche, droite

    with centre:
        st.title("🎵 DataStory Music")
        st.subheader("Inscription")

        with st.form("form_register"):
            username = st.text_input("Nom d'utilisateur")
            email = st.text_input("Email")
            password = st.text_input("Mot de passe", type="password")
            soumettre = st.form_submit_button("Créer le compte", use_container_width=True)

        if st.button("Retour à la connexion"):
            st.session_state.auth_view = "login"
            st.rerun()

    if not soumettre:
        return

    if not username or not email or not password:
        st.error("Veuillez remplir tous les champs.")
        return

    try:
        rep = requests.post(
            f"{API_URL}/register",
            json={"username": username, "email": email, "password": password},
            timeout=TIMEOUT_REQUETE,
        )
    except requests.RequestException as exc:
        st.error(f"Impossible de joindre l'API : {exc}")
        return

    if rep.status_code == 201:
        st.success("Compte créé avec succès. Vous pouvez vous connecter.")
        st.session_state.auth_view = "login"
        st.rerun()
    elif rep.status_code == 400:
        st.error("Données invalides (vérifiez email, username et mot de passe).")
    elif rep.status_code == 409:
        st.warning("Nom d'utilisateur ou email déjà utilisé.")
    elif rep.status_code == 429:
        st.warning("Trop de tentatives. Réessayez dans une minute.")
    else:
        st.error(f"Erreur inattendue ({rep.status_code}).")


# ---------------------------------------------------------------------------
# Composant : barre latérale (info token + déconnexion)
# ---------------------------------------------------------------------------

def sidebar_session():
    with st.sidebar:
        st.markdown("### 👤 Session")
        st.write(f"**Utilisateur :** {st.session_state.username}")
        st.write(f"**Rôle :** {st.session_state.role}")
        restantes = max(0, int(_secondes_restantes()))
        minutes, secondes = divmod(restantes, 60)
        st.write(f"**Jeton (temps restant) :** {minutes:02d}:{secondes:02d}")


def sidebar_logout():
    with st.sidebar:
        st.markdown("---")
        if st.button("🚪 Se déconnecter"):
            _deconnecter()
            st.rerun()


# ---------------------------------------------------------------------------
# Pages protégées
# ---------------------------------------------------------------------------

def page_profil():
    st.header("Mon profil")
    rep = _appel_api("GET", "/protected")
    if rep is None:
        st.warning("Session expirée. Veuillez vous reconnecter.")
        st.rerun()
        return
    if rep.status_code == 200:
        profil = rep.json()
        col1, col2 = st.columns(2)
        col1.metric("Identifiant", profil.get("id"))
        col1.metric("Nom d'utilisateur", profil.get("username"))
        col2.metric("Rôle", profil.get("role"))
        col2.metric("Email", profil.get("email") or "—")
    else:
        st.error(f"Impossible de charger le profil ({rep.status_code}).")


def page_stats():
    st.header("📊 Statistiques globales")
    try:
        status_code, data = _get_public_json("/stats")
    except requests.RequestException as exc:
        st.error(f"Erreur réseau : {exc}")
        return

    if status_code != 200:
        st.error("Impossible de charger les statistiques.")
        return

    import pandas as pd

    col1, col2, col3 = st.columns(3)
    col1.metric("Entrées totales", f"{data.get('total_lignes', 0):,}")
    col2.metric("Artistes uniques", f"{data.get('total_artistes', 0):,}")
    col3.metric("Morceaux uniques", f"{data.get('total_morceaux', 0):,}")

    couverture = data.get("couverture_genres", {})
    col4, col5, col6 = st.columns(3)
    col4.metric("Avec genre", f"{couverture.get('avec_genre', 0):,}")
    col5.metric("Sans genre", f"{couverture.get('sans_genre', 0):,}")
    col6.metric("Couverture", f"{couverture.get('pourcentage_avec_genre', 0):.2f}%")

    periode = data.get("periode") or {}
    if periode:
        st.info(
            f"Période couverte : **{periode.get('debut')}** → **{periode.get('fin')}**"
        )

    sources_genres = data.get("sources_genres", {})
    if sources_genres:
        st.subheader("Couverture genres par source")
        st.caption(
            "**track** = genre issu des métadonnées Spotify directement sur le morceau · "
            "**artiste** = genre déduit depuis l'artiste (fallback) · "
            "**inconnu** = aucun genre disponible"
        )
        serie = pd.Series(sources_genres).sort_values(ascending=False)
        st.bar_chart(serie)


def page_genres():
    st.header("🎼 Évolution des genres musicaux")

    col1, col2 = st.columns(2)
    with col1:
        period = st.selectbox("Période", ["decennie", "annee"], format_func=lambda x: "Décennie" if x == "decennie" else "Année")
    with col2:
        top_n = st.slider("Top N genres", min_value=3, max_value=15, value=8)

    try:
        params_evolution = (("period", period), ("top_n", str(top_n)))
        params_totaux = (("period", period),)
        status_code, data = _get_public_json("/genres/evolution", params_evolution)
        _, data_totaux = _get_public_json("/genres/totaux", params_totaux)
    except requests.RequestException as exc:
        st.error(f"Erreur réseau : {exc}")
        return

    if status_code != 200:
        st.error("Impossible de charger les données de genres.")
        return

    import pandas as pd

    resultats = data.get("resultats", [])
    resume = data_totaux.get("resume", data.get("resume", {}))
    totaux_par_periode = data_totaux.get("totaux_par_periode", [])

    st.caption(
        f"{resume.get('lignes_analysees', 0):,} entrées analysées · "
        f"{resume.get('genres_uniques', 0)} genres uniques"
    )

    # Chart 3 — Volume total d'entrées par période
    if totaux_par_periode:
        st.subheader("Volume total d'entrées par période")
        df_totaux = pd.DataFrame(totaux_par_periode)
        if "periode" in df_totaux.columns and "entrees_totales" in df_totaux.columns:
            df_totaux["periode"] = df_totaux["periode"].astype(str)
            st.line_chart(df_totaux.set_index("periode")["entrees_totales"])

    if not resultats:
        st.info("Aucune donnée disponible.")
        return

    df = pd.DataFrame(resultats)

    # Chart 2 — Parts des genres par période (barres empilées)
    if not df.empty and "periode" in df.columns and "track_genre" in df.columns:
        st.subheader("Parts des genres par période (top N)")
        pivot = df.pivot_table(index="periode", columns="track_genre", values="entrees", fill_value=0)
        pivot.index = pivot.index.astype(str)
        st.bar_chart(pivot)

    with st.expander("Voir les données brutes"):
        st.dataframe(df, width="stretch")


def page_michael_jackson():
    st.header("🕺 Héritage de Michael Jackson")

    try:
        status_code, data = _get_public_json("/michael-jackson/heritage")
    except requests.RequestException as exc:
        st.error(f"Erreur réseau : {exc}")
        return

    if status_code != 200:
        st.error("Impossible de charger les données.")
        return

    col1, col2, col3 = st.columns(3)
    col1.metric("Entrées charts", data.get("entrees_total", 0))
    col2.metric("Top 10", data.get("top_10_total", 0))
    col3.metric("Meilleur rang", data.get("best_rank") or "—")

    st.write(
        f"Première apparition : **{data.get('premiere_apparition')}** · "
        f"Dernière : **{data.get('derniere_apparition')}**"
    )

    import pandas as pd

    # Chart 4 — Timeline des morceaux iconiques
    morceaux = data.get("morceaux_iconiques", [])
    if morceaux:
        st.subheader("Morceaux iconiques — Timeline")
        df_m = pd.DataFrame(morceaux)
        if "date" in df_m.columns and "rank" in df_m.columns:
            df_m["date"] = pd.to_datetime(df_m["date"], errors="coerce")
            df_m = df_m.dropna(subset=["date"])
            df_m["rang_inv"] = -df_m["rank"].astype(int)
            st.scatter_chart(
                df_m.rename(columns={"song": "morceau"}),
                x="date",
                y="rang_inv",
                color="morceau",
            )
            st.caption("Axe Y : rang inversé (0 = #1, -10 = #10). Plus c'est haut, meilleur le classement.")
        with st.expander("Voir le tableau des morceaux"):
            st.dataframe(df_m.drop(columns=["rang_inv"], errors="ignore"), width="stretch")

    # Chart 5 — Genres dominants
    genres = data.get("genres_dominants", [])
    if genres:
        st.subheader("Genres dominants")
        df_genres = pd.DataFrame(genres)
        if "track_genre" in df_genres.columns and "occurrences" in df_genres.columns:
            st.bar_chart(
                df_genres.set_index("track_genre")["occurrences"].sort_values(ascending=False)
            )


# ---------------------------------------------------------------------------
# Application principale
# ---------------------------------------------------------------------------

def main():
    st.set_page_config(
        page_title="DataStory Music",
        page_icon="🎵",
        layout="wide",
    )
    _init_session()
    _restaurer_session_locale()

    # -----------------------------------------------------------------------
    # Si non connecté → écran de login
    # -----------------------------------------------------------------------
    if not _est_connecte():
        if st.session_state.auth_view == "register":
            page_inscription()
        else:
            page_connexion()
        return

    # -----------------------------------------------------------------------
    # Vérification / rafraîchissement automatique du token
    # -----------------------------------------------------------------------
    if not _token_valide_ou_refresh():
        st.warning("Votre session a expiré. Reconnectez-vous.")
        st.rerun()
        return

    # -----------------------------------------------------------------------
    # Navigation principale
    # -----------------------------------------------------------------------
    sidebar_session()

    pages = {
        "📊 Statistiques": page_stats,
        "🎼 Genres musicaux": page_genres,
        "🕺 Michael Jackson": page_michael_jackson,
        "👤 Mon profil": page_profil,
    }

    choix = st.sidebar.radio("Navigation", list(pages.keys()))
    sidebar_logout()
    pages[choix]()


if __name__ == "__main__":
    main()
