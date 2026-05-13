"""Application Streamlit — DataStory Music."""

import datetime
import json
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

SESSION_FILE = Path(__file__).parent / ".session.json"


def _sauvegarder_session():
    if not st.session_state.get("access_token"):
        return
    data = {
        "access_token": st.session_state.access_token,
        "refresh_token": st.session_state.refresh_token,
        "expires_at": st.session_state.expires_at.isoformat() if st.session_state.expires_at else None,
        "username": st.session_state.username,
        "role": st.session_state.role,
        "user_id": st.session_state.user_id,
    }
    SESSION_FILE.write_text(json.dumps(data), encoding="utf-8")


def _charger_session():
    if st.session_state.get("access_token"):
        return
    if not SESSION_FILE.exists():
        return
    try:
        data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
        expires_at = None
        if data.get("expires_at"):
            expires_at = datetime.datetime.fromisoformat(data["expires_at"])
        st.session_state.access_token = data.get("access_token")
        st.session_state.refresh_token = data.get("refresh_token")
        st.session_state.expires_at = expires_at
        st.session_state.username = data.get("username")
        st.session_state.role = data.get("role")
        st.session_state.user_id = data.get("user_id")
    except Exception:
        SESSION_FILE.unlink(missing_ok=True)

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
    _charger_session()


def _stocker_token(token, expires_in_minutes, username, role, user_id, refresh_token=None, **_):
    st.session_state.access_token = token
    st.session_state.refresh_token = refresh_token
    st.session_state.expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=expires_in_minutes)
    st.session_state.username = username
    st.session_state.role = role
    st.session_state.user_id = user_id
    _sauvegarder_session()


def _deconnecter():
    for cle in ["access_token", "refresh_token", "expires_at", "username", "role", "user_id"]:
        st.session_state[cle] = None
    st.session_state.auth_view = "login"
    SESSION_FILE.unlink(missing_ok=True)


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
        _sauvegarder_session()
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


def page_introduction():
    import plotly.graph_objects as go

    st.header("🏠 Introduction")

    status_code, data = _get_public_json("/stats")
    if status_code != 200:
        st.error("Impossible de charger les données.")
        return

    # --- KPIs dataset ---
    col1, col2, col3 = st.columns(3)
    col1.metric("Entrées totales", f"{data.get('total_lignes', 0):,}")
    col2.metric("Artistes uniques", f"{data.get('total_artistes', 0):,}")
    col3.metric("Morceaux uniques", f"{data.get('total_morceaux', 0):,}")

    periode = data.get("periode") or {}
    if periode:
        st.info(f"Période couverte : **{periode.get('debut')}** → **{periode.get('fin')}**")

    couverture = data.get("couverture_genres", {})
    pct = couverture.get("pourcentage_avec_genre", 0)
    avec = couverture.get("avec_genre", 0)
    sans = couverture.get("sans_genre", 0)

    total = data.get("total_lignes", 0)
    sources = data.get("sources_genres", {})

    col_a, col_b = st.columns(2)

    with col_a:
        # Pie : distribution par type de match
        labels_map = {"track": "Par morceau", "artiste": "Par artiste", "inconnu": "Non trouvé"}
        labels = [labels_map.get(k, k) for k in sources]
        values = list(sources.values())
        couleurs = ["#3b82f6", "#10b981", "#6b7280"]
        fig_pie = go.Figure(go.Pie(
            labels=labels,
            values=values,
            hole=0.45,
            marker=dict(colors=couleurs),
            textinfo="label+percent",
            hovertemplate="%{label}<br>%{value:,} entrées<br>%{percent}<extra></extra>",
        ))
        fig_pie.update_layout(
            title="Distribution des genres par type de correspondance",
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#e2e8f0"),
            legend=dict(orientation="h", yanchor="bottom", y=-0.15),
            margin=dict(t=60, b=40),
        )
        st.plotly_chart(fig_pie, use_container_width=True)

    with col_b:
        # Jauge : pourcentage de match global
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number+delta",
            value=pct,
            delta={"reference": 80, "valueformat": ".1f"},
            number={"suffix": "%", "valueformat": ".2f"},
            title={"text": "Taux de correspondance genre"},
            gauge={
                "axis": {"range": [0, 100]},
                "bar": {"color": "#10b981"},
                "steps": [
                    {"range": [0, 50], "color": "#374151"},
                    {"range": [50, 80], "color": "#1f2937"},
                    {"range": [80, 100], "color": "#111827"},
                ],
                "threshold": {
                    "line": {"color": "#f59e0b", "width": 4},
                    "thickness": 0.75,
                    "value": 80,
                },
            },
        ))
        fig_gauge.update_layout(
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#e2e8f0"),
            margin=dict(t=40, b=20),
        )
        st.plotly_chart(fig_gauge, use_container_width=True)
        st.caption(
            f"**{avec:,}** entrées avec genre identifié · "
            f"**{sans:,}** sans genre · "
            f"Total : **{total:,}**"
        )


def page_stats():
    import plotly.graph_objects as go

    st.header("📊 Statistiques globales")

    _, domination = _get_public_json("/genres/domination", (("top_n", "10"),))
    _, evo = _get_public_json("/genres/evolution", (("period", "annee"), ("top_n", "8")))

    col_a, col_b = st.columns(2)

    with col_a:
        if isinstance(domination, list) and domination:
            genres_labels = [d["genre"] for d in domination]
            nb_app = [d["nb_apparitions"] for d in domination]
            rank_moy = [d["rank_moyen"] for d in domination]
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=genres_labels, y=nb_app,
                name="Nombre d'apparitions",
                marker_color="#3b82f6",
                text=[f"{v:,}" for v in nb_app],
                textposition="outside",
                yaxis="y1",
            ))
            fig.add_trace(go.Scatter(
                x=genres_labels, y=rank_moy,
                name="Rang moyen",
                mode="lines+markers",
                line=dict(color="#dc2626", width=2),
                marker=dict(size=6),
                yaxis="y2",
            ))
            fig.update_layout(
                title="Domination des genres : volume vs performance",
                xaxis=dict(title=""),
                yaxis=dict(title="Nombre d'apparitions", showgrid=False),
                yaxis2=dict(title="Rang moyen", overlaying="y", side="right", showgrid=False),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#e2e8f0"), margin=dict(t=60),
            )
            st.plotly_chart(fig, use_container_width=True)

    with col_b:
        resultats = evo.get("resultats", []) if isinstance(evo, dict) else []
        if resultats:
            df_evo = pd.DataFrame(resultats)
            if not df_evo.empty and "periode" in df_evo.columns and "track_genre" in df_evo.columns:
                pivot = df_evo.pivot_table(index="periode", columns="track_genre", values="entrees", fill_value=0)
                pivot.index = pivot.index.astype(str)
                st.subheader("Top genres par année")
                st.bar_chart(pivot, height=430)


def page_genres_tendances():
    import plotly.graph_objects as go

    st.header("🎼 Genres & Tendances")

    _, longevite = _get_public_json("/genres/longevite", (("top_n", "10"),))
    _, popularite = _get_public_json("/genres/popularite", (("top_n", "10"),))

    col_c, col_d = st.columns(2)

    with col_c:
        if isinstance(longevite, list) and longevite:
            longevite_sorted = sorted(longevite, key=lambda x: x["semaines"])
            genres_l = [d["genre"].capitalize() for d in longevite_sorted]
            semaines_l = [d["semaines"] for d in longevite_sorted]
            leaders_l = [d["artiste_leader"] for d in longevite_sorted]
            fig2 = go.Figure(go.Bar(
                y=genres_l, x=semaines_l, orientation="h",
                marker=dict(color=semaines_l, colorscale="Teal", showscale=True,
                            colorbar=dict(title="Semaines cumulées", tickformat=".0s")),
                text=leaders_l, textposition="inside", insidetextanchor="end",
                textfont=dict(size=11, color="white"),
            ))
            fig2.update_layout(
                title="Leaders de la longévité (Billboard 200)",
                xaxis=dict(title="Semaines cumulées", tickformat=".0s"),
                yaxis=dict(title=""),
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#e2e8f0"), showlegend=False, margin=dict(t=60),
            )
            st.plotly_chart(fig2, use_container_width=True)

    with col_d:
        if isinstance(popularite, list) and popularite:
            pop_sorted = sorted(popularite, key=lambda x: x["popularite_moyenne"])
            genres_p = [d["genre"].capitalize() for d in pop_sorted]
            scores_p = [d["popularite_moyenne"] for d in pop_sorted]
            fig3 = go.Figure(go.Bar(
                y=genres_p, x=scores_p, orientation="h",
                marker=dict(color=scores_p, colorscale="Viridis", showscale=True,
                            colorbar=dict(title="Score popularité")),
                text=[str(v) for v in scores_p], textposition="outside",
                textfont=dict(size=11),
            ))
            fig3.update_layout(
                title="Popularité moyenne (Top 10 Billboard) par genre",
                xaxis=dict(title="Score de popularité moyen (Spotify)"),
                yaxis=dict(title=""),
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#e2e8f0"), showlegend=False, margin=dict(t=60),
            )
            st.plotly_chart(fig3, use_container_width=True)
def page_mj_heritage():
    import plotly.graph_objects as go

    st.header("🕴️ Michael Jackson — Héritage")

    status_code, data = _get_public_json("/michael-jackson/heritage")
    if status_code != 200:
        st.error("Impossible de charger les données.")
        return

    col1, col2, col3 = st.columns(3)
    col1.metric("Semaines totales", f"{data.get('semaines_totales', 0):,}", help="Présence cumulée Billboard 200")
    col2.metric("Titres distincts", data.get("titres_distincts", "—"), help="Albums/Chansons")
    col3.metric("Semaines au rang #1", data.get("semaines_rang1", "—"), help="Sommet du chart")
    st.caption(
        f"Première apparition : **{data.get('premiere_apparition')}** · "
        f"Dernière : **{data.get('derniere_apparition')}**"
    )

    col_a, col_b = st.columns(2)

    with col_a:
        evo = data.get("evolution_annuelle", [])
        if evo:
            df_evo = pd.DataFrame(evo)
            fig_evo = go.Figure(go.Scatter(
                x=df_evo["annee"], y=df_evo["semaines"],
                mode="lines",
                fill="tozeroy",
                line=dict(color="#facc15", width=2),
                fillcolor="rgba(250,204,21,0.25)",
            ))
            fig_evo.update_layout(
                title="Évolution de la présence au Billboard 200",
                xaxis=dict(title="Année"),
                yaxis=dict(title="Semaines cumulées"),
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#e2e8f0"), margin=dict(t=60),
            )
            st.plotly_chart(fig_evo, use_container_width=True)
            top5 = sorted(evo, key=lambda x: x["semaines"], reverse=True)[:5]
            st.caption("Top 5 années : " + ", ".join(f"{r['annee']} ({r['semaines']} sem.)" for r in top5))

    with col_b:
        _, compa = _get_public_json("/michael-jackson/comparaison")
        if isinstance(compa, list) and compa:
            artistes_c = [d["artiste"] for d in compa]
            semaines_c = [d["semaines"] for d in compa]
            titres_c = [d["nb_titres"] for d in compa]
            labels_c = [f"{s:,} sem.<br>({t} titres)" for s, t in zip(semaines_c, titres_c)]
            fig_compa = go.Figure(go.Bar(
                x=artistes_c, y=semaines_c,
                marker=dict(color=titres_c, colorscale="Viridis", showscale=True,
                            colorbar=dict(title="Nb titres")),
                text=labels_c, textposition="outside",
                textfont=dict(size=11),
                customdata=list(zip(artistes_c, semaines_c, titres_c)),
                hovertemplate="Artiste=%{customdata[0]}<br>Semaines=%{customdata[1]}<br>Titres=%{customdata[2]}<extra></extra>",
            ))
            fig_compa.update_layout(
                title="MJ vs autres artistes : longévité et volume",
                xaxis=dict(title="Artiste"),
                yaxis=dict(title="Cumul des semaines"),
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#e2e8f0"), showlegend=False, margin=dict(t=60),
            )
            st.plotly_chart(fig_compa, use_container_width=True)


def page_mj_discographie():
    import plotly.graph_objects as go

    st.header("🎵 Michael Jackson — Discographie & Thriller")

    status_code, data = _get_public_json("/michael-jackson/heritage")
    if status_code != 200:
        st.error("Impossible de charger les données.")
        return

    col_a, col_b = st.columns(2)

    with col_a:
        albums = data.get("top_albums", [])
        if albums:
            albums_sorted = sorted(albums, key=lambda x: x["semaines"])
            titres_a = [d["titre"] for d in albums_sorted]
            semaines_a = [d["semaines"] for d in albums_sorted]
            fig_albums = go.Figure(go.Bar(
                y=titres_a, x=semaines_a, orientation="h",
                marker=dict(color=semaines_a, colorscale="Blues", showscale=True,
                            colorbar=dict(title="Semaines")),
                text=semaines_a, textposition="outside",
                textfont=dict(size=11),
            ))
            fig_albums.update_layout(
                title="Top 10 albums au Billboard 200 (semaines cumulées)",
                xaxis=dict(title="Semaines"),
                yaxis=dict(title=""),
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#e2e8f0"), showlegend=False, margin=dict(t=60),
            )
            st.plotly_chart(fig_albums, use_container_width=True)

    with col_b:
        _, thriller = _get_public_json("/michael-jackson/thriller")
        if isinstance(thriller, list) and thriller:
            df_t = pd.DataFrame(thriller)
            fig_t = go.Figure()
            fig_t.add_trace(go.Bar(
                x=df_t["annee"], y=df_t["semaines"],
                name="Semaines présent",
                marker_color="rgba(250,204,21,0.7)",
                yaxis="y1",
            ))
            fig_t.add_trace(go.Scatter(
                x=df_t["annee"], y=df_t["best_rank"],
                name="Meilleur rang",
                mode="lines+markers",
                line=dict(color="#3b82f6", width=2),
                marker=dict(size=6),
                yaxis="y2",
            ))
            fig_t.update_layout(
                title="Évolution de Thriller au Billboard 200",
                xaxis=dict(title="Année", dtick=5),
                yaxis=dict(title="Semaines présent", showgrid=False),
                yaxis2=dict(title="Position (#1 = sommet)", overlaying="y", side="right",
                            autorange="reversed", showgrid=False),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#e2e8f0"), margin=dict(t=70),
            )
            st.plotly_chart(fig_t, use_container_width=True)
            st.caption("Barres jaunes : semaines présent · Courbe bleue : meilleur rang (axe inversé)")


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
        "🏠 Introduction": page_introduction,
        "📊 Statistiques": page_stats,
        "🎼 Genres & Tendances": page_genres_tendances,
        "🕴️ MJ — Héritage": page_mj_heritage,
        "🎵 MJ — Discographie": page_mj_discographie,
    }

    choix = st.sidebar.radio("Navigation", list(pages.keys()))
    sidebar_logout()
    pages[choix]()


if __name__ == "__main__":
    main()
