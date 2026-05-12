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
        "expires_at": None,
        "username": None,
        "role": None,
        "user_id": None,
        "auth_view": "login",
        "login_error": "",
    }
    for cle, valeur in defaults.items():
        if cle not in st.session_state:
            st.session_state[cle] = valeur


def _stocker_token(token: str, expires_in_minutes: int, username: str, role: str, user_id: int):
    """Enregistre le token et ses métadonnées dans session_state."""
    st.session_state.access_token = token
    st.session_state.expires_at = datetime.datetime.utcnow() + datetime.timedelta(minutes=expires_in_minutes)
    st.session_state.username = username
    st.session_state.role = role
    st.session_state.user_id = user_id
    st.session_state.login_error = ""
    _sauvegarder_session_locale()


def _deconnecter():
    """Efface toutes les données de session."""
    for cle in ["access_token", "expires_at", "username", "role", "user_id"]:
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
        "expires_at": st.session_state.expires_at.isoformat() if st.session_state.expires_at else None,
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
        expires_at = datetime.datetime.fromisoformat(expires_raw) if expires_raw else None
    except Exception:
        return False

    if not payload.get("access_token") or not expires_at or expires_at <= datetime.datetime.utcnow():
        return False

    st.session_state.access_token = payload.get("access_token")
    st.session_state.expires_at = expires_at
    st.session_state.username = payload.get("username")
    st.session_state.role = payload.get("role")
    st.session_state.user_id = payload.get("user_id")
    return True


def _est_connecte() -> bool:
    return bool(st.session_state.get("access_token"))


def _secondes_restantes() -> float:
    """Retourne le nombre de secondes avant expiration du token (peut être négatif)."""
    if not st.session_state.expires_at:
        return 0.0
    delta = st.session_state.expires_at - datetime.datetime.utcnow()
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
    try:
        rep = requests.post(
            f"{API_URL}/refresh",
            headers=_entete_auth(),
            timeout=TIMEOUT_REQUETE,
        )
    except requests.RequestException:
        return False

    if rep.status_code == 200:
        data = rep.json()
        st.session_state.access_token = data["access_token"]
        st.session_state.expires_at = datetime.datetime.utcnow() + datetime.timedelta(
            minutes=data.get("expires_in_minutes", 30)
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
    if restant <= 0:
        _deconnecter()
        return False
    if restant < SEUIL_REFRESH_SECONDES:
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
        if st.button("Créer un compte", use_container_width=True):
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

        if st.button("Retour à la connexion", use_container_width=True):
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

        restant = _secondes_restantes()
        if restant > 0:
            mins = int(restant // 60)
            secs = int(restant % 60)
            couleur = "green" if restant > 120 else "orange"
            st.markdown(
                f"**Token expire dans :** :{couleur}[{mins}m {secs:02d}s]"
            )
        else:
            st.markdown("**Token :** :red[expiré]")

        if st.button("🔄 Rafraîchir le token"):
            ok = _tenter_refresh()
            if ok:
                st.success("Token renouvelé.")
            else:
                st.error("Impossible de renouveler — reconnectez-vous.")
                st.rerun()

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
        rep = requests.get(f"{API_URL}/stats", timeout=TIMEOUT_REQUETE)
    except requests.RequestException as exc:
        st.error(f"Erreur réseau : {exc}")
        return

    if rep.status_code == 200:
        data = rep.json()
        col1, col2, col3 = st.columns(3)
        col1.metric("Entrées totales", f"{data.get('total_lignes', 0):,}")
        col2.metric("Artistes uniques", f"{data.get('total_artistes', 0):,}")
        col3.metric("Morceaux uniques", f"{data.get('total_morceaux', 0):,}")

        couverture = data.get("couverture_genres", {})
        col4, col5, col6 = st.columns(3)
        col4.metric("Avec genre", f"{couverture.get('avec_genre', 0):,}")
        col5.metric("Sans genre", f"{couverture.get('sans_genre', 0):,}")
        col6.metric("Couverture", f"{couverture.get('pourcentage_avec_genre', 0):.2f}%")

        sources = data.get("sources_genres", {})
        if sources:
            st.subheader("Sources des genres")
            st.bar_chart(sources)

        periode = data.get("periode") or {}
        if periode:
            st.info(
                f"Période couverte : **{periode.get('debut')}** → **{periode.get('fin')}**"
            )
    else:
        st.error("Impossible de charger les statistiques.")


def page_genres():
    st.header("🎼 Évolution des genres musicaux")

    col1, col2, col3 = st.columns(3)
    with col1:
        period = st.selectbox("Période", ["decennie", "annee"], format_func=lambda x: "Décennie" if x == "decennie" else "Année")
    with col2:
        top_n = st.slider("Top N genres", min_value=3, max_value=15, value=8)
    with col3:
        source = st.selectbox(
            "Source du genre",
            ["all", "track", "artiste"],
            format_func=lambda x: "Toutes" if x == "all" else ("Track matché" if x == "track" else "Genre artiste"),
        )

    try:
        rep = requests.get(
            f"{API_URL}/genres/evolution",
            params={"period": period, "top_n": top_n, "genre_source": source},
            timeout=TIMEOUT_REQUETE,
        )
    except requests.RequestException as exc:
        st.error(f"Erreur réseau : {exc}")
        return

    if rep.status_code != 200:
        st.error("Impossible de charger les données de genres.")
        return

    data = rep.json()
    resultats = data.get("resultats", [])
    resume = data.get("resume", {})

    st.caption(
        f"{resume.get('lignes_analysees', 0):,} entrées analysées · "
        f"{resume.get('genres_uniques', 0)} genres uniques"
    )

    if not resultats:
        st.info("Aucune donnée disponible.")
        return

    import pandas as pd
    df = pd.DataFrame(resultats)

    # Graphique en barres empilées
    if not df.empty and "periode" in df.columns and "track_genre" in df.columns:
        pivot = df.pivot_table(index="periode", columns="track_genre", values="entrees", fill_value=0)
        st.bar_chart(pivot)

    with st.expander("Voir les données brutes"):
        st.dataframe(df, use_container_width=True)


def page_michael_jackson():
    st.header("🕺 Héritage de Michael Jackson")

    try:
        rep = requests.get(f"{API_URL}/michael-jackson/heritage", timeout=TIMEOUT_REQUETE)
    except requests.RequestException as exc:
        st.error(f"Erreur réseau : {exc}")
        return

    if rep.status_code != 200:
        st.error("Impossible de charger les données.")
        return

    data = rep.json()

    col1, col2, col3 = st.columns(3)
    col1.metric("Entrées charts", data.get("entrees_total", 0))
    col2.metric("Top 10", data.get("top_10_total", 0))
    col3.metric("Meilleur rang", data.get("best_rank") or "—")

    st.write(
        f"Première apparition : **{data.get('premiere_apparition')}** · "
        f"Dernière : **{data.get('derniere_apparition')}**"
    )

    morceaux = data.get("morceaux_iconiques", [])
    if morceaux:
        st.subheader("Morceaux iconiques (top 10)")
        import pandas as pd
        st.dataframe(pd.DataFrame(morceaux), use_container_width=True)

    genres = data.get("genres_dominants", [])
    if genres:
        st.subheader("Genres dominants")
        import pandas as pd
        df_genres = pd.DataFrame(genres)
        st.bar_chart(df_genres.set_index("track_genre")["occurrences"])


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
    pages[choix]()


if __name__ == "__main__":
    main()
