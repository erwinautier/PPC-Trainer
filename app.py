# app.py
import os
import sys
import json
import random
import hashlib
from collections import defaultdict

import streamlit as st

# -----------------------------
# Données du trainer
# -----------------------------
POSITIONS = ["LJ", "HJ", "CO", "BTN", "SB", "BB"]
STACKS = [100, 50, 25, 20, 19, 18, 17, 16, 15, 14, 13, 12, 11, 10]
RANKS = ["A", "K", "Q", "J", "T", "9", "8", "7", "6", "5", "4", "3", "2"]
SUITS = ["♠", "♥", "♦", "♣"]


def build_deck():
    return [f"{r}{s}" for r in RANKS for s in SUITS]


# -----------------------------
# Gestion des chemins & fichiers
# -----------------------------
def base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


USERS_FILE = os.path.join(base_dir(), "users.json")


def sanitize_profile(name: str) -> str:
    """Nom de fichier sûr à partir d'un identifiant."""
    name = name.strip() or "default"
    return "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in name)


def get_save_path(username: str) -> str:
    """Chemin JSON pour un utilisateur donné."""
    safe = sanitize_profile(username)
    return os.path.join(base_dir(), f"leitner_data_{safe}.json")


# -----------------------------
# Gestion des utilisateurs (id + mdp)
# -----------------------------
def load_users():
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)


def hash_password(password: str, salt: str) -> str:
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()


def create_user(username: str, password: str) -> bool:
    """Crée un nouvel utilisateur. Renvoie False si déjà existant."""
    users = load_users()
    uname = username.strip()
    if uname in users:
        return False
    salt = os.urandom(16).hex()
    pwd_hash = hash_password(password, salt)
    users[uname] = {"salt": salt, "pwd_hash": pwd_hash}
    save_users(users)
    return True


def check_login(username: str, password: str) -> bool:
    users = load_users()
    uname = username.strip()
    info = users.get(uname)
    if not info:
        return False
    expected = info["pwd_hash"]
    salt = info["salt"]
    return hash_password(password, salt) == expected


# -----------------------------
# Sauvegarde des stats / poids
# -----------------------------
def load_data(username: str):
    weights = defaultdict(lambda: 1.0)
    stats = {"good": 0, "bad": 0}
    path = get_save_path(username)
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                data = json.load(f)
            stats = data.get("stats", stats)
            weights.clear()
            for key, val in data.get("weights", {}).items():
                pos, stack_str = key.split("|", 1)
                weights[(pos, int(stack_str))] = float(val)
        except Exception:
            weights = defaultdict(lambda: 1.0)
            stats = {"good": 0, "bad": 0}
    return weights, stats


def save_data(username: str, weights, stats):
    path = get_save_path(username)
    data = {
        "stats": stats,
        "weights": {
            f"{pos}|{stack}": float(w) for (pos, stack), w in weights.items()
        },
    }
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


# -----------------------------
# Logique de tirage
# -----------------------------
def weighted_stack_choice(selected_stack):
    if selected_stack is not None and random.random() < 0.5:
        return selected_stack
    if selected_stack is None:
        others = STACKS
    else:
        others = [s for s in STACKS if s != selected_stack]
    return random.choice(others)


def weighted_position_stack_choice(weights):
    all_cases = list(weights.keys()) or [
        (p, s) for p in POSITIONS for s in STACKS
    ]
    total = sum(weights[c] for c in all_cases)
    r = random.uniform(0, total)
    cum = 0
    for case in all_cases:
        cum += weights[case]
        if r <= cum:
            return case
    return random.choice(all_cases)


def roll(weights, selected_stack, ranges_mode):
    if random.random() < 0.5:
        pos, stack = weighted_position_stack_choice(weights)
    else:
        pos = random.choice(POSITIONS)
        stack = weighted_stack_choice(selected_stack)

    deck = build_deck()
    random.shuffle(deck)
    c1, c2 = deck[:2]

    def colorize(card):
        suit = card[-1]
        color = "#DC2626" if suit in {"♥", "♦"} else "#111827"
        return f"<span style='color:{color}'>{card}</span>"

    hand_html = f"{colorize(c1)}&nbsp;&nbsp;{colorize(c2)}"

    if pos == "BB" or (ranges_mode and pos in ["SB", "BTN", "CO", "HJ"]):
        open_from = random.choice([p for p in POSITIONS if p != pos])
        extra = f"Open de {open_from}"
    else:
        extra = ""

    return (pos, stack, hand_html, extra)


# -----------------------------
# Config Streamlit
# -----------------------------
st.set_page_config(
    page_title="Poker Trainer",
    page_icon="♠",
    layout="centered",
)

# -----------------------------
# Sidebar : logo + auth
# -----------------------------
if "user" not in st.session_state:
    st.session_state.user = None

logo_path = "logo-penthievre.jpeg"  # change si besoin
logo_full_path = os.path.join(base_dir(), logo_path)
if os.path.exists(logo_full_path):
    st.sidebar.image(logo_full_path, use_column_width=True)

st.sidebar.markdown("---")

if st.session_state.user:
    st.sidebar.markdown(f"### Connecté : `{st.session_state.user}`")
    if st.sidebar.button("Se déconnecter"):
        st.session_state.user = None
        # La page sera recalculée à la prochaine interaction
else:
    st.sidebar.markdown("### Connexion / création de profil")

    auth_mode = st.sidebar.radio(
        "Choisir une action",
        ["Se connecter", "Créer un profil"],
        index=0,
    )

    if auth_mode == "Se connecter":
        with st.sidebar.form("login_form"):
            login_user = st.text_input("Identifiant")
            login_pwd = st.text_input("Mot de passe", type="password")
            submit_login = st.form_submit_button("Se connecter")
        if submit_login:
            if check_login(login_user, login_pwd):
                st.session_state.user = login_user.strip()
                st.sidebar.success("Connexion réussie ✅")
            else:
                st.sidebar.error("Identifiant ou mot de passe incorrect.")

    else:  # Créer un profil
        with st.sidebar.form("signup_form"):
            new_user = st.text_input("Nouvel identifiant")
            new_pwd = st.text_input("Mot de passe", type="password")
            new_pwd2 = st.text_input("Confirmation mot de passe", type="password")
            submit_signup = st.form_submit_button("Créer le profil")
        if submit_signup:
            if not new_user.strip():
                st.sidebar.error("L'identifiant ne peut pas être vide.")
            elif new_pwd != new_pwd2:
                st.sidebar.error("Les mots de passe ne correspondent pas.")
            elif len(new_pwd) < 4:
                st.sidebar.error("Mot de passe trop court (min. 4 caractères).")
            else:
                ok = create_user(new_user, new_pwd)
                if not ok:
                    st.sidebar.error("Cet identifiant existe déjà.")
                else:
                    st.sidebar.success("Profil créé. Vous êtes maintenant connecté.")
                    st.session_state.user = new_user.strip()

# Si pas connecté → bloquer l'accès au reste
if not st.session_state.user:
    st.title("🃏 Poker Trainer – Connexion requise")
    st.info("Crée un profil ou connecte-toi dans la colonne de gauche pour commencer.")
    st.stop()

username = st.session_state.user

# -----------------------------
# Options de l'utilisateur (sidebar suite)
# -----------------------------
st.sidebar.markdown("---")
st.sidebar.markdown("### Options de tirage")

stack_favori = st.sidebar.radio(
    "Stack surreprésenté (≈ 50 % des tirages)",
    options=["Aucun"] + [str(s) for s in STACKS],
    index=0,
)
selected_stack = None if stack_favori == "Aucun" else int(stack_favori)

ranges_mode = st.sidebar.checkbox("Ranges de call et 3-bet", value=False)

if st.sidebar.button("♻️ Remettre à zéro ce profil"):
    st.session_state.weights = defaultdict(lambda: 1.0)
    st.session_state.stats = {"good": 0, "bad": 0}
    save_data(username, st.session_state.weights, st.session_state.stats)
    st.sidebar.success("Progrès remis à zéro pour ce profil.")

# -----------------------------
# Initialisation de la session
# -----------------------------
if "weights" not in st.session_state or "stats" not in st.session_state:
    st.session_state.weights, st.session_state.stats = load_data(username)

# Si on change d'utilisateur, recharger ses données
if st.session_state.get("last_user") != username:
    st.session_state.weights, st.session_state.stats = load_data(username)
    st.session_state.last_user = username
    st.session_state.current_case = None
    st.session_state.current_pos = None
    st.session_state.current_stack = None
    st.session_state.current_hand_html = ""
    st.session_state.current_extra = ""

weights = st.session_state.weights
stats = st.session_state.stats

for key, val in [
    ("current_case", None),
    ("current_pos", None),
    ("current_stack", None),
    ("current_hand_html", ""),
    ("current_extra", ""),
]:
    if key not in st.session_state:
        st.session_state[key] = val

# -----------------------------
# Affichage principal : CARD grisée
# -----------------------------
st.title("🃏 Poker Trainer – Ranges & Leitner")
st.markdown(f"*Profil connecté : **{username}***")

pos_text = st.session_state.current_pos or "--"
stack_text = (
    st.session_state.current_stack
    if st.session_state.current_stack is not None
    else "--"
)
hand_html = st.session_state.current_hand_html or "--"
extra_html = (
    f"<div style='margin-top:4px;color:#555;font-style:italic;'>{st.session_state.current_extra}</div>"
    if st.session_state.current_extra
    else ""
)

card_html = f"""
<div style="
    background-color:#f5f5f5;
    border-radius:18px;
    padding:18px 22px;
    margin-bottom:18px;
    border:1px solid #e5e7eb;">
  <div style="display:flex;justify-content:space-between;gap:16px;">
    <div style="flex:1;text-align:center;">
      <div style="font-size:12px;color:#666;">Position</div>
      <div style="font-size:32px;font-weight:bold;">{pos_text}</div>
    </div>
    <div style="flex:1;text-align:center;">
      <div style="font-size:12px;color:#666;">Stack (BB)</div>
      <div style="font-size:32px;font-weight:bold;">{stack_text}</div>
    </div>
  </div>
  <div style="margin-top:14px;text-align:center;">
    <div style="font-size:12px;color:#666;">Main</div>
    <div style="font-size:32px;font-weight:bold;">{hand_html}</div>
    {extra_html}
  </div>
</div>
"""

st.markdown(card_html, unsafe_allow_html=True)

st.markdown("---")

# -----------------------------
# Boutons de feedback
# -----------------------------
c1, c2, c3 = st.columns(3)
clicked_good = c1.button("✅ Bonne réponse")
clicked_bad = c2.button("❌ Mauvaise réponse")
clicked_new = c3.button("Nouvelle donne")


def do_roll():
    pos, stack, hand_html_new, extra = roll(weights, selected_stack, ranges_mode)
    st.session_state.current_case = (pos, stack)
    st.session_state.current_pos = pos
    st.session_state.current_stack = stack
    st.session_state.current_hand_html = hand_html_new
    st.session_state.current_extra = extra


if st.session_state.current_pos is None:
    do_roll()

if clicked_good:
    if st.session_state.current_case is not None:
        stats["good"] += 1
        weights[st.session_state.current_case] = max(
            0.2, weights[st.session_state.current_case] * 0.8
        )
        save_data(username, weights, stats)
    do_roll()

elif clicked_bad:
    if st.session_state.current_case is not None:
        stats["bad"] += 1
        weights[st.session_state.current_case] = min(
            5.0, weights[st.session_state.current_case] * 1.5
        )
        save_data(username, weights, stats)
    do_roll()

elif clicked_new:
    do_roll()

# -----------------------------
# Statistiques
# -----------------------------
st.markdown("---")
st.subheader("📊 Statistiques du profil")

total = stats["good"] + stats["bad"]
success_rate = (stats["good"] / total * 100) if total else 0.0
st.write(f"- Bonnes réponses : **{stats['good']}**")
st.write(f"- Mauvaises réponses : **{stats['bad']}**")
st.write(f"- Taux de réussite : **{success_rate:.1f} %**")

if weights:
    avg_weight = sum(weights.values()) / len(weights)
    st.write(f"- Poids moyen (difficulté globale) : **{avg_weight:.2f}**")

    hardest = sorted(weights.items(), key=lambda kv: kv[1], reverse=True)[:3]
    if hardest:
        st.write("**Cas les plus souvent revus (les plus difficiles) :**")
        for (pos, stack), w in hardest:
            st.write(f"- {pos} – {stack} BB (poids {w:.2f})")
else:
    st.info("Pas encore de données suffisantes pour afficher les difficultés.")
