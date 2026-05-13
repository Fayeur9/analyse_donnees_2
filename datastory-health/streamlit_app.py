"""Application Streamlit — DataStory Music."""

import datetime

import pandas as pd
import requests
import streamlit as st

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
API_URL = "http://localhost:5000"
SEUIL_REFRESH_SECONDES = 5 * 60  # rafraîchir si < 5 min restantes
TIMEOUT_REQUETE = 10


# ---------------------------------------------------------------------------
# Gestion de la session
# ---------------------------------------------------------------------------

def _init_session():
    defaults = {
        "access_token": None,
        "refresh_token": None,
        "expires_at": None,
        "username": None,
        "role": None,
        "user_id": None,
        "auth_view": "login",
    }
    for cle, valeur in defaults.items():
        if cle not in st.session_state:
            st.session_state[cle] = valeur


def _stocker_token(token, expires_in_minutes, username, role, user_id, refresh_token=None, **_):
    st.session_state.access_token = token
    st.session_state.refresh_token = refresh_token
    st.session_state.expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=expires_in_minutes)
    st.session_state.username = username
    st.session_state.role = role
    st.session_state.user_id = user_id


def _deconnecter():
    for cle in ["access_token", "refresh_token", "expires_at", "username", "role", "user_id"]:
        st.session_state[cle] = None
    st.session_state.auth_view = "login"


def _est_connecte():
    return bool(st.session_state.get("access_token"))


def _secondes_restantes():
    if not st.session_state.expires_at:
        return 0.0
    delta = st.session_state.expires_at - datetime.datetime.now(datetime.timezone.utc)
    return delta.total_seconds()


def _tenter_refresh():
    """Demande un nouveau token via /refresh. Retourne True si réussi."""
    if not st.session_state.get("refresh_token"):
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
        st.session_state.expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
            minutes=data.get("expires_in_minutes", 30)
        )
        return True

    _deconnecter()
    return False


def _token_valide_ou_refresh():
    """Retourne True si le token est valide (en le rafraîchissant si besoin)."""
    restant = _secondes_restantes()
    if restant <= 0:
        return _tenter_refresh()
    if restant < SEUIL_REFRESH_SECONDES:
        return _tenter_refresh()
    return True


# ---------------------------------------------------------------------------
# Appels API
# ---------------------------------------------------------------------------

def _entete_auth():
    return {"Authorization": f"Bearer {st.session_state.access_token}"}


def _appel_api(methode, chemin, **kwargs):
    if not _token_valide_ou_refresh():
        return None
    try:
        func = getattr(requests, methode.lower())
        return func(f"{API_URL}{chemin}", headers=_entete_auth(), timeout=TIMEOUT_REQUETE, **kwargs)
    except requests.RequestException as exc:
        st.error(f"Erreur réseau : {exc}")
        return None


@st.cache_data(ttl=120, show_spinner=False)
def _get_public_json(chemin, params_items=()):
    params = dict(params_items) if params_items else None
    try:
        rep = requests.get(f"{API_URL}{chemin}", params=params, timeout=TIMEOUT_REQUETE)
        return rep.status_code, rep.json()
    except (requests.RequestException, ValueError):
        return 0, {}


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
            _stocker_token(
                token=data["access_token"],
                expires_in_minutes=data.get("expires_in_minutes", 30),
                username=data.get("username", username),
                role=data.get("role", "user"),
                user_id=data.get("user_id"),
                refresh_token=data.get("refresh_token"),
            )
            st.rerun()
        elif rep.status_code == 401:
            st.error("Identifiants incorrects.")
        else:
            st.error(f"Erreur inattendue ({rep.status_code}).")


# ---------------------------------------------------------------------------
# Page : inscription
# ---------------------------------------------------------------------------

def page_inscription():
    gauche, centre, droite = st.columns([1.5, 1, 1.5])
    del gauche, droite

    with centre:
        st.title("🎵 DataStory Music")
        st.subheader("Créer un compte")

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
    else:
        st.error(f"Erreur inattendue ({rep.status_code}).")


# ---------------------------------------------------------------------------
# Composants sidebar
# ---------------------------------------------------------------------------

def sidebar_session():
    with st.sidebar:
        st.markdown("### 👤 Session")
        st.write(f"**Utilisateur :** {st.session_state.username}")
        st.write(f"**Rôle :** {st.session_state.role}")


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
    status_code, data = _get_public_json("/stats")

    if status_code != 200:
        st.error("Impossible de charger les statistiques.")
        return

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
        st.info(f"Période couverte : **{periode.get('debut')}** → **{periode.get('fin')}**")

    sources_genres = data.get("sources_genres", {})
    if sources_genres:
        st.subheader("Couverture genres par source")
        st.bar_chart(pd.Series(sources_genres).sort_values(ascending=False))


def page_genres():
    st.header("🎼 Évolution des genres musicaux")

    col1, col2 = st.columns(2)
    with col1:
        period = st.selectbox("Période", ["annee", "decennie"], format_func=lambda x: "Année" if x == "annee" else "Décennie")
    with col2:
        top_n = st.slider("Top N genres", min_value=3, max_value=15, value=8)

    params_evolution = (("period", period), ("top_n", str(top_n)))
    params_totaux = (("period", period),)
    status_code, data = _get_public_json("/genres/evolution", params_evolution)
    _, data_totaux = _get_public_json("/genres/totaux", params_totaux)

    if status_code != 200:
        st.error("Impossible de charger les données de genres.")
        return

    resultats = data.get("resultats", [])
    resume = data_totaux.get("resume", data.get("resume", {}))
    totaux_par_periode = data_totaux.get("totaux_par_periode", [])

    st.caption(
        f"{resume.get('lignes_analysees', 0):,} entrées analysées · "
        f"{resume.get('genres_uniques', 0)} genres uniques"
    )

    if totaux_par_periode:
        st.subheader("Volume total d'entrées par période")
        df_totaux = pd.DataFrame(totaux_par_periode)
        if "periode" in df_totaux.columns and "entrees_totales" in df_totaux.columns:
            st.line_chart(df_totaux.set_index("periode")["entrees_totales"])

    if not resultats:
        st.info("Aucune donnée disponible.")
        return

    df = pd.DataFrame(resultats)

    if not df.empty and "periode" in df.columns and "track_genre" in df.columns:
        st.subheader("Parts des genres par période (top N)")
        pivot = df.pivot_table(index="periode", columns="track_genre", values="entrees", fill_value=0)
        st.bar_chart(pivot)

    with st.expander("Voir les données brutes"):
        st.dataframe(df, use_container_width=True)


def page_michael_jackson():
    st.header("🕺 Héritage de Michael Jackson")

    status_code, data = _get_public_json("/michael-jackson/heritage")

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

    morceaux = data.get("morceaux_iconiques", [])
    if morceaux:
        st.subheader("Morceaux iconiques — Timeline")
        df_m = pd.DataFrame(morceaux)
        if "date" in df_m.columns and "rank" in df_m.columns:
            df_m["date"] = pd.to_datetime(df_m["date"], errors="coerce")
            df_m = df_m.dropna(subset=["date"])
            df_m["rang_inv"] = -df_m["rank"].astype(int)
            st.scatter_chart(df_m.rename(columns={"song": "morceau"}), x="date", y="rang_inv", color="morceau")
            st.caption("Axe Y : rang inversé (0 = #1). Plus c'est haut, meilleur le classement.")
        with st.expander("Voir le tableau des morceaux"):
            st.dataframe(df_m.drop(columns=["rang_inv"], errors="ignore"), use_container_width=True)

    genres = data.get("genres_dominants", [])
    if genres:
        st.subheader("Genres dominants")
        df_genres = pd.DataFrame(genres)
        if "track_genre" in df_genres.columns and "occurrences" in df_genres.columns:
            st.bar_chart(df_genres.set_index("track_genre")["occurrences"].sort_values(ascending=False))


# ---------------------------------------------------------------------------
# Application principale
# ---------------------------------------------------------------------------

def main():
    st.set_page_config(page_title="DataStory Music", page_icon="🎵", layout="wide")
    _init_session()

    if not _est_connecte():
        if st.session_state.auth_view == "register":
            page_inscription()
        else:
            page_connexion()
        return

    if not _token_valide_ou_refresh():
        st.warning("Votre session a expiré. Reconnectez-vous.")
        st.rerun()
        return

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
