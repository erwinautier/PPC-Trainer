import os
import sys
import json
import hashlib
import secrets  # pour générer le salt des mdp

import streamlit as st
from supabase import create_client, Client

# =========================================================
# Configuration globale
# =========================================================
st.set_page_config(
    page_title="Poker Trainer Suite",
    page_icon="♠",
    layout="wide",   # wide pour que l'éditeur de ranges ait de la place
)

SUPABASE_URL = st.secrets.get("SUPABASE_URL", "")
SUPABASE_ANON_KEY = st.secrets.get("SUPABASE_ANON_KEY", "")

# Salt pour le "remember me" (tu peux le mettre dans st.secrets si tu veux)
REMEMBER_ME_SALT = st.secrets.get(
    "REMEMBER_ME_SALT",
    "change-moi-en-une-chaine-longue-et-peu-devinable"
)


@st.cache_resource
def get_supabase() -> Client | None:
    """
    Client Supabase partagé. Retourne None si la config est absente
    ou si l'initialisation échoue.
    """
    url = (SUPABASE_URL or "").strip()
    key = (SUPABASE_ANON_KEY or "").strip()

    # Petit debug sans exposer les secrets :
    st.sidebar.caption(
        f"[DEBUG] SUPABASE_URL défini: {bool(url)} | SUPABASE_ANON_KEY défini: {bool(key)}"
    )

    if not url or not key:
        st.sidebar.error(
            "⚠️ SUPABASE_URL ou SUPABASE_ANON_KEY manquent dans st.secrets. "
            "Les comptes utilisateurs ne peuvent pas être vérifiés."
        )
        return None

    try:
        client = create_client(url, key)
        st.sidebar.caption("[DEBUG] Client Supabase global initialisé ✅")
        return client
    except Exception as e:
        st.sidebar.error(f"⚠️ Erreur d'initialisation Supabase (global) : {e}")
        return None


# =========================================================
# Outils communs
# =========================================================
def base_dir():
    """
    Dossier de base de l'application (utile aussi en exécutable).
    On l'utilise pour les fichiers logo, etc.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def hash_pw(pwd: str, salt: str) -> str:
    return hashlib.sha256((salt + pwd).encode("utf-8")).hexdigest()


# =========================================================
# Gestion du "remember me" via query params
# =========================================================
def make_remember_token(username: str) -> str:
    """
    Génère un token pseudo-secret à partir du username + sel.
    (Usage perso, pas pour de la prod bancaire.)
    """
    raw = f"{username}::{REMEMBER_ME_SALT}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def set_remember_me(username: str):
    """
    Stocke user + token dans l'URL (query params).
    """
    token = make_remember_token(username)
    st.experimental_set_query_params(u=username, t=token)


def clear_remember_me():
    """
    Efface les query params pour un vrai logout.
    """
    st.experimental_set_query_params()


def try_auto_login_from_query_params() -> str | None:
    """
    Si possible, re-crée un login utilisateur à partir des query params.
    Retourne le username si auto-login effectué, sinon None.
    """
    params = st.experimental_get_query_params()
    username_list = params.get("u", [])
    token_list = params.get("t", [])
    if not username_list or not token_list:
        return None

    username = username_list[0]
    token = token_list[0]
    expected = make_remember_token(username)
    if token != expected:
        return None  # token invalide ou URL modifiée

    # On considère l'utilisateur loggé
    st.session_state.user = username
    return username


# =========================================================
# Gestion des utilisateurs (Supabase)
# =========================================================
def create_user(username: str, pwd: str) -> bool:
    """
    Crée un utilisateur dans la table app_users (Supabase).
    Retourne True si tout va bien, False sinon.
    """
    username = (username or "").strip()
    if not username or not pwd:
        return False

    client = get_supabase()
    if client is None:
        st.sidebar.error("Supabase indisponible : impossible de créer le profil en ligne.")
        return False

    # même logique de hash que tu avais avant, mais avec secrets.token_hex
    salt = secrets.token_hex(16)
    password_hash = hash_pw(pwd, salt)

    try:
        _ = (
            client.table("app_users")
            .insert(
                {
                    "username": username,
                    "salt": salt,
                    "password_hash": password_hash,
                }
            )
            .execute()
        )
        # Si ça ne plante pas, on considère que c'est OK
        return True
    except Exception as e:
        st.sidebar.error(f"[Supabase app_users] Erreur lors de la création du profil : {e}")
        return False


def check_login(username: str, pwd: str) -> bool:
    """
    Vérifie les identifiants en interrogeant la table app_users.
    Retourne True si (username, pwd) sont corrects.
    """
    username = (username or "").strip()
    if not username or not pwd:
        return False

    client = get_supabase()
    if client is None:
        st.sidebar.error("Supabase indisponible : impossible de vérifier le login.")
        return False

    try:
        resp = (
            client.table("app_users")
            .select("salt, password_hash")
            .eq("username", username)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        if not rows:
            return False

        row = rows[0]
        salt = row["salt"]
        expected_hash = row["password_hash"]

        given_hash = hash_pw(pwd, salt)
        return given_hash == expected_hash

    except Exception as e:
        st.sidebar.error(f"[Supabase app_users] Erreur lors de la vérification du login : {e}")
        return False


# =========================================================
# Import des modules enfant
# =========================================================
try:
    from trainer_module import run_trainer
except ImportError:
    run_trainer = None

try:
    # tu m'as envoyé range_editor_module.py
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

# Tentative d'auto-login depuis les query params si pas déjà loggé
if st.session_state.user is None:
    try_auto_login_from_query_params()


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
        # on efface l'état et les query params
        st.session_state.user = None
        clear_remember_me()
        st.rerun()
else:
    st.sidebar.markdown("### Connexion / création de profil")
    mode_auth = st.sidebar.radio("Action", ["Se connecter", "Créer un profil"])
    user_input = st.sidebar.text_input("Identifiant")
    pwd_input = st.sidebar.text_input("Mot de passe", type="password")

    if st.sidebar.button("Valider"):
        if mode_auth == "Créer un profil":
            if create_user(user_input, pwd_input):
                username_clean = user_input.strip()
                st.session_state.user = username_clean
                set_remember_me(username_clean)
                st.sidebar.success("Profil créé et connecté.")
                st.rerun()
            else:
                st.sidebar.error("Identifiant déjà utilisé ou invalide.")
        else:
            if check_login(user_input, pwd_input):
                username_clean = user_input.strip()
                st.session_state.user = username_clean
                set_remember_me(username_clean)
                st.sidebar.success("Connexion réussie.")
                st.rerun()
            else:
                st.sidebar.error("Identifiant ou mot de passe incorrect.")

    # Si pas connecté, on bloque l'accès au reste de l'app ici
    st.stop()

# À partir d'ici, on a forcément un user connecté
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
col_left, col_center, col_right = st.columns([1, 4, 1])

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
