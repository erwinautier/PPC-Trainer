import os
import sys
import json
import hashlib

import streamlit as st

# =========================================================
# Configuration globale
# =========================================================
st.set_page_config(
    page_title="Préflop Trainer Suite",
    page_icon="♠",
    layout="centered",
)

# =========================================================
# Outils communs
# =========================================================
def base_dir():
    """
    Dossier de base de l'application (utile aussi en exécutable).
    On l'utilise pour les fichiers users.json, ranges, etc.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


USERS_FILE = os.path.join(base_dir(), "users.json")


def load_users():
    if os.path.exists(USERS_FILE):
        try:
            return json.load(open(USERS_FILE, "r", encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_users(users):
    json.dump(users, open(USERS_FILE, "w", encoding="utf-8"), indent=2)


def hash_pw(pwd, salt):
    return hashlib.sha256((salt + pwd).encode()).hexdigest()


def create_user(username, pwd):
    users = load_users()
    username = username.strip()
    if not username or username in users:
        return False
    salt = os.urandom(16).hex()
    users[username] = {"salt": salt, "hash": hash_pw(pwd, salt)}
    save_users(users)
    return True


def check_login(username, pwd):
    users = load_users()
    username = username.strip()
    info = users.get(username)
    if not info:
        return False
    return info["hash"] == hash_pw(pwd, info["salt"])


# =========================================================
# Import des modules enfant
# =========================================================
try:
    from trainer_module import run_trainer
except ImportError:
    run_trainer = None

try:
    from range_editor_module import run_range_editor
except ImportError:
    run_range_editor = None


# =========================================================
# États Streamlit globaux
# =========================================================
if "user" not in st.session_state:
    st.session_state.user = None

if "global_mode" not in st.session_state:
    st.session_state.global_mode = "S'entraîner"


# =========================================================
# Sidebar : logo + auth
# =========================================================
logo_path = os.path.join(base_dir(), "logo-penthievre.jpeg")
if os.path.exists(logo_path):
    st.sidebar.image(logo_path, use_column_width=True)

st.sidebar.markdown("---")

# ----- Authentification -----
if st.session_state.user:
    st.sidebar.markdown(f"### Connecté : `{st.session_state.user}`")
    if st.sidebar.button("Se déconnecter"):
        st.session_state.user = None
        st.experimental_rerun()
else:
    st.sidebar.markdown("### Connexion / création de profil")
    mode_auth = st.sidebar.radio("Action", ["Se connecter", "Créer un profil"])
    user = st.sidebar.text_input("Identifiant")
    pwd = st.sidebar.text_input("Mot de passe", type="password")
    if st.sidebar.button("Valider"):
        if mode_auth == "Créer un profil":
            if create_user(user, pwd):
                st.session_state.user = user.strip()
                st.sidebar.success("Profil créé et connecté.")
                st.experimental_rerun()
            else:
                st.sidebar.error("Identifiant déjà utilisé ou invalide.")
        else:
            if check_login(user, pwd):
                st.session_state.user = user.strip()
                st.sidebar.success("Connexion réussie.")
                st.experimental_rerun()
            else:
                st.sidebar.error("Identifiant ou mot de passe incorrect.")
    st.stop()

username = st.session_state.user

# =========================================================
# Contenu principal : écran d’accueil + routing
# =========================================================

# Petit bandeau discret en haut
st.markdown(
    f"<div style='font-size:13px;color:#555;'>Connecté en tant que "
    f"<b>{username}</b></div>",
    unsafe_allow_html=True,
)

st.markdown("<hr style='margin:0.5rem 0 1rem 0;'/>", unsafe_allow_html=True)

# ----- Écran d’accueil / choix du module -----
col_left, col_center, col_right = st.columns([1, 3, 1])

with col_center:
    st.markdown(
        """
        <div style="
            text-align:center;
            margin-bottom:1.5rem;">
          <h2 style="margin-bottom:0.5rem;">Poker Trainer Suite</h2>
          <p style="margin:0; font-size:13px; color:#666;">
            Choisis ton module : entraînement aux spots ou édition de tes ranges.
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    mode_global = st.radio(
        "Que veux-tu faire ?",
        options=["S'entraîner", "Éditer mes ranges"],
        index=0 if st.session_state.global_mode == "S'entraîner" else 1,
        horizontal=True,
    )
    st.session_state.global_mode = mode_global

    st.markdown("<br/>", unsafe_allow_html=True)

# Séparation visuelle
st.markdown("---")

# =========================================================
# Appel du module choisi
# =========================================================
if st.session_state.global_mode == "S'entraîner":
    if run_trainer is None:
        st.error(
            "Le module `trainer_module.py` est introuvable ou ne contient pas "
            "de fonction `run_trainer(username)`."
        )
    else:
        run_trainer(username)

else:  # "Éditer mes ranges"
    if run_range_editor is None:
        st.error(
            "Le module `range_editor_module.py` est introuvable ou ne contient pas "
            "de fonction `run_range_editor(username)`."
        )
    else:
        run_range_editor(username)
