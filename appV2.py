# app.py
import os
import sys
import json
import random
import hashlib
from collections import defaultdict

import streamlit as st

# -----------------------------
# Constantes Poker
# -----------------------------
RANKS = ["A", "K", "Q", "J", "T", "9", "8", "7", "6", "5", "4", "3", "2"]
SUITS = ["♠", "♥", "♦", "♣"]

POSITIONS_6MAX = ["LJ", "HJ", "CO", "BTN", "SB", "BB"]
POSITIONS_8MAX = ["UTG", "UTG+1", "LJ", "HJ", "CO", "BTN", "SB", "BB"]

STACKS = [100, 50, 25, 20, 19, 18, 17, 16, 15, 14, 13, 12, 11, 10]

ACTIONS = ["fold", "call", "open", "threebet", "open_shove", "threebet_shove"]
ACTION_LABELS = {
    "fold": "Fold",
    "call": "Call",
    "open": "Open",
    "threebet": "3-bet",
    "open_shove": "Open shove",
    "threebet_shove": "3-bet shove",
}
ACTION_EMOJI = {
    "fold": "❌",
    "call": "🟡",
    "open": "🟢",
    "threebet": "🔴",
    "open_shove": "🟣",
    "threebet_shove": "⚫",
}

# -----------------------------
# Utils cartes / mains
# -----------------------------
def build_deck():
    return [f"{r}{s}" for r in RANKS for s in SUITS]


def canonical_from_cards(card1: str, card2: str) -> str:
    """Convertit 2 cartes (ex: A♠, K♦) en code type AA, AKs, AKo."""
    r1, s1 = card1[0], card1[1]
    r2, s2 = card2[0], card2[1]
    if r1 == r2:
        return r1 + r2
    i1, i2 = RANKS.index(r1), RANKS.index(r2)
    if i1 < i2:
        hi, lo = r1, r2
    else:
        hi, lo = r2, r1
    suited = s1 == s2
    return hi + lo + ("s" if suited else "o")


def canonical_hand_from_indices(i: int, j: int) -> str:
    """Pour afficher une grille de range (suited en haut, off en bas)."""
    r1 = RANKS[i]
    r2 = RANKS[j]
    if i == j:
        return r1 + r2
    idx1 = RANKS.index(r1)
    idx2 = RANKS.index(r2)
    if idx1 < idx2:
        hi, lo = r1, r2
    else:
        hi, lo = r2, r1
    if i < j:
        return hi + lo + "s"
    else:
        return hi + lo + "o"


# -----------------------------
# Gestion chemins / fichiers
# -----------------------------
def base_dir():
    if getattr(sys, "frozen", False):  # pour un éventuel exécutable
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


USERS_FILE = os.path.join(base_dir(), "users.json")


def sanitize_profile(name: str) -> str:
    name = name.strip() or "default"
    return "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in name)


def get_save_path(username: str) -> str:
    safe = sanitize_profile(username)
    return os.path.join(base_dir(), f"leitner_data_{safe}.json")


# -----------------------------
# Gestion utilisateurs
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
# Sauvegarde stats / poids (mode libre)
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
# Tirages (mode libre)
# -----------------------------
def weighted_stack_choice(selected_stack):
    if selected_stack is not None and random.random() < 0.5:
        return selected_stack
    if selected_stack is None:
        others = STACKS
    else:
        others = [s for s in STACKS if s != selected_stack]
    return random.choice(others)


def weighted_position_stack_choice(weights, available_positions):
    all_cases = [(p, s) for p in available_positions for s in STACKS]
    effective_weights = {}
    for p, s in all_cases:
        effective_weights[(p, s)] = weights.get((p, s), 1.0)
    total = sum(effective_weights.values())
    r = random.uniform(0, total)
    cum = 0
    for case, w in effective_weights.items():
        cum += w
        if r <= cum:
            return case
    return random.choice(all_cases)


def roll_free(weights, selected_stack, table_type):
    positions = POSITIONS_6MAX if table_type == "6-max" else POSITIONS_8MAX

    if random.random() < 0.5:
        pos, stack = weighted_position_stack_choice(weights, positions)
    else:
        pos = random.choice(positions)
        stack = weighted_stack_choice(selected_stack)

    deck = build_deck()
    random.shuffle(deck)
    c1, c2 = deck[:2]

    def colorize(card):
        suit = card[-1]
        color = "#DC2626" if suit in {"♥", "♦"} else "#111827"
        return f"<span style='color:{color}'>{card}</span>"

    hand_html = f"{colorize(c1)}&nbsp;&nbsp;{colorize(c2)}"

    extra = ""
    scenario_label = "Open"

    if pos == "BB":
        open_from = random.choice([p for p in positions if p != pos])
        extra = f"Open de {open_from}"
        scenario_label = f"Vs open {open_from}"

    return (pos, stack, hand_html, extra, scenario_label, (c1, c2))


# -----------------------------
# Ranges JSON (mode correction)
# -----------------------------
def load_ranges_from_json_file(file):
    try:
        data = json.load(file)
    except Exception:
        return {}
    spots_json = data.get("spots", {})
    ranges = {}
    for key, spot in spots_json.items():
        table_type = spot.get("table_type", "6-max")
        pos = spot.get("position")
        stack = spot.get("stack")
        scen = spot.get("scenario", "open")
        actions = spot.get("actions", {})

        cleaned = {
            "table_type": table_type,
            "position": pos,
            "stack": int(stack),
            "scenario": scen,
            "actions": {
                act: [h for h in hands] for act, hands in actions.items()
            },
        }
        ranges[key] = cleaned
    return ranges


def choose_random_spot(ranges_data, table_type):
    candidates = [
        (key, spot)
        for key, spot in ranges_data.items()
        if spot.get("table_type", "6-max") == table_type
    ]
    if not candidates:
        return None, None
    return random.choice(candidates)


def get_correct_actions_for_hand(spot, hand_code):
    actions = spot.get("actions", {})
    non_fold_actions = set()
    for act_key in ["open", "call", "threebet", "open_shove", "threebet_shove"]:
        for h in actions.get(act_key, []):
            if h == hand_code:
                non_fold_actions.add(act_key)

    if not non_fold_actions:
        return {"fold"}
    else:
        result = set(non_fold_actions)
        if hand_code in actions.get("fold", []):
            result.add("fold")
        return result


def scenario_pretty_label(scenario: str):
    if scenario == "open":
        return "Open"
    if scenario.startswith("vs_open_"):
        vil = scenario[len("vs_open_") :]
        return f"Vs open {vil}"
    return scenario


# -----------------------------
# Affichage grille de range
# -----------------------------
def render_range_grid(spot, highlight_hand=None):
    """Affiche la range du spot sous forme de grille 13x13, proprement alignée."""
    actions = spot.get("actions", {})
    st.markdown("##### Range de correction")

    # main -> set(actions)
    hand_actions = defaultdict(set)
    for act_name, hands in actions.items():
        for h in hands:
            hand_actions[h].add(act_name)

    # En-tête colonnes
    header_cols = st.columns(len(RANKS) + 1)
    header_cols[0].markdown(" ")
    for j, r2 in enumerate(RANKS):
        header_cols[j + 1].markdown(
            f"<div style='text-align:center;'><b>{r2}</b></div>",
            unsafe_allow_html=True,
        )

    # Lignes de la grille
    for i, r1 in enumerate(RANKS):
        cols = st.columns(len(RANKS) + 1)
        # En-tête de ligne
        cols[0].markdown(
            f"<div style='text-align:center;'><b>{r1}</b></div>",
            unsafe_allow_html=True,
        )

        for j, r2 in enumerate(RANKS):
            hand_code = canonical_hand_from_indices(i, j)
            acts = hand_actions.get(hand_code, set())

            # --- Choix du symbole + couleur (UN seul symbole par case) ---
            if not acts:
                # Fold par défaut
                symbol = "✕"
                color = "#EF4444"  # rouge
            else:
                # Priorité visuelle pour la couleur
                if "open_shove" in acts or "threebet_shove" in acts:
                    color = "#111827"  # noir (shove)
                elif "threebet" in acts:
                    color = "#DC2626"  # rouge foncé (3-bet)
                elif "open" in acts:
                    color = "#16A34A"  # vert (open)
                elif "call" in acts:
                    color = "#FACC15"  # jaune (call)
                else:
                    color = "#6B7280"  # gris
                symbol = "●"

            # Surlignage si c'est la main fautive
            highlight_style = ""
            if highlight_hand is not None and hand_code == highlight_hand:
                highlight_style = "background-color:#E5E7EB;border-radius:6px;"

            cell_html = f"""
            <div style="font-size:11px;line-height:1.1;text-align:center;{highlight_style}">
              <span style="color:{color};font-size:14px;">{symbol}</span><br>
              <span>{hand_code}</span>
            </div>
            """

            cols[j + 1].markdown(cell_html, unsafe_allow_html=True)


# -----------------------------
# Config Streamlit
# -----------------------------
st.set_page_config(
    page_title="Poker Trainer – Ranges & Leitner",
    page_icon="♠",
    layout="centered",
)

# -----------------------------
# Sidebar : logo + auth
# -----------------------------
if "user" not in st.session_state:
    st.session_state.user = None

logo_path = "logo_penthievre.png"
logo_full_path = os.path.join(base_dir(), logo_path)
if os.path.exists(logo_full_path):
    st.sidebar.image(logo_full_path, use_column_width=True)

st.sidebar.markdown("---")

if st.session_state.user:
    st.sidebar.markdown(f"### Connecté : `{st.session_state.user}`")
    if st.sidebar.button("Se déconnecter"):
        st.session_state.user = None
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
    else:
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

if not st.session_state.user:
    st.title("🃏 Poker Trainer – Ranges & Leitner")
    st.info("Crée un profil ou connecte-toi dans la colonne de gauche pour commencer.")
    st.stop()

username = st.session_state.user

# -----------------------------
# Sidebar : options générales
# -----------------------------
st.sidebar.markdown("---")
st.sidebar.markdown("### Options générales")

table_type = st.sidebar.radio(
    "Format de table",
    ["6-max", "8-max"],
    index=0,
)

mode_jeu = st.sidebar.radio(
    "Mode de jeu",
    ["Libre (sans ranges)", "Avec ranges de correction"],
    index=0,
)

# Sélecteur stack favori (mode libre)
selected_stack = None
if mode_jeu == "Libre (sans ranges)":
    stack_favori = st.sidebar.radio(
        "Stack surreprésenté (≈ 50 % des tirages)",
        options=["Aucun"] + [str(s) for s in STACKS],
        index=0,
    )
    selected_stack = None if stack_favori == "Aucun" else int(stack_favori)

# Fichier de ranges (mode correction)
if mode_jeu == "Avec ranges de correction":
    st.sidebar.markdown("### Fichier de ranges (.json)")
    ranges_file = st.sidebar.file_uploader(
        "Charger un fichier de ranges (JSON v2)", type=["json"]
    )
else:
    ranges_file = None

# Reset profil (mode libre)
if st.sidebar.button("♻️ Remettre à zéro ce profil (mode libre)"):
    st.session_state.weights = defaultdict(lambda: 1.0)
    st.session_state.stats = {"good": 0, "bad": 0}
    save_data(username, st.session_state.weights, st.session_state.stats)
    st.sidebar.success("Progrès (mode libre) remis à zéro pour ce profil.")

# -----------------------------
# Initialisation des états
# -----------------------------
if "weights" not in st.session_state or "stats" not in st.session_state:
    st.session_state.weights, st.session_state.stats = load_data(username)

# états communs
default_values = {
    "current_case": None,
    "current_pos": None,
    "current_stack": None,
    "current_hand_html": "",
    "current_extra": "",
    "current_scenario_label": "",
    "current_cards": ("A♠", "K♠"),
}
for key, val in default_values.items():
    if key not in st.session_state:
        st.session_state[key] = val

# états spécifiques mode correction
for key, val in [
    ("ranges_data", {}),
    ("range_spot_keys", []),
    ("current_spot_key", None),
    ("current_hand_code", None),
    ("current_correct_actions", set()),
    ("show_correction", False),
    ("last_correction_spot", None),
    ("last_correction_hand", None),
    ("last_result", None),
]:
    if key not in st.session_state:
        st.session_state[key] = val

# stats mode correction (non persistées pour l'instant)
if "range_stats" not in st.session_state:
    st.session_state.range_stats = {
        "played": 0,
        "correct": 0,
        "wrong": 0,
        "errors_by_pos": defaultdict(int),
        "errors_by_stack": defaultdict(int),
        "errors_by_hand": defaultdict(int),
    }

weights = st.session_state.weights
stats = st.session_state.stats

# -----------------------------
# Chargement ranges si besoin
# -----------------------------
if mode_jeu == "Avec ranges de correction":
    if ranges_file is not None:
        ranges_data = load_ranges_from_json_file(ranges_file)
        st.session_state.ranges_data = ranges_data
        st.session_state.range_spot_keys = list(ranges_data.keys())
    else:
        st.session_state.ranges_data = {}
        st.session_state.range_spot_keys = []

# -----------------------------
# Affichage du spot courant
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
extra_text = st.session_state.current_extra or ""
scenario_label = st.session_state.current_scenario_label or ""

card_html = f"""
<div style="
    background-color:#f5f5f5;
    border-radius:18px;
    padding:18px 22px;
    margin-bottom:6px;
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
  </div>
</div>
"""

st.markdown(card_html, unsafe_allow_html=True)

if extra_text:
    st.caption(extra_text)

if scenario_label:
    st.caption(f"Scénario : {scenario_label}")

st.markdown("---")

# -----------------------------
# Fonctions de tirage
# -----------------------------
def do_roll_free():
    pos, stack, hand_html_new, extra, scen_label, cards = roll_free(
        weights, selected_stack, table_type
    )
    st.session_state.current_case = (pos, stack)
    st.session_state.current_pos = pos
    st.session_state.current_stack = stack
    st.session_state.current_hand_html = hand_html_new
    st.session_state.current_extra = extra
    st.session_state.current_scenario_label = scen_label
    st.session_state.current_cards = cards
    st.session_state.show_correction = False
    st.session_state.last_result = None


def do_roll_range():
    ranges_data = st.session_state.ranges_data
    if not ranges_data:
        st.warning(
            "Aucune range chargée. Merci de fournir un fichier JSON dans la colonne de gauche."
        )
        return

    spot_key, spot = choose_random_spot(ranges_data, table_type)
    if spot_key is None or spot is None:
        st.warning(f"Aucun spot pour le format {table_type} dans ce fichier de ranges.")
        return

    pos = spot["position"]
    stack = spot["stack"]
    scenario = spot["scenario"]

    deck = build_deck()
    random.shuffle(deck)
    c1, c2 = deck[:2]
    hand_code = canonical_from_cards(c1, c2)

    def colorize(card):
        suit = card[-1]
        color = "#DC2626" if suit in {"♥", "♦"} else "#111827"
        return f"<span style='color:{color}'>{card}</span>"

    hand_html_new = f"{colorize(c1)}&nbsp;&nbsp;{colorize(c2)}"

    scen_label = scenario_pretty_label(scenario)
    extra = ""
    if scenario.startswith("vs_open_"):
        vil = scenario[len("vs_open_") :]
        extra = f"Open de {vil}"

    correct_actions = get_correct_actions_for_hand(spot, hand_code)

    st.session_state.current_pos = pos
    st.session_state.current_stack = stack
    st.session_state.current_hand_html = hand_html_new
    st.session_state.current_extra = extra
    st.session_state.current_scenario_label = scen_label
    st.session_state.current_cards = (c1, c2)
    st.session_state.current_spot_key = spot_key
    st.session_state.current_hand_code = hand_code
    st.session_state.current_correct_actions = correct_actions
    st.session_state.show_correction = False
    st.session_state.last_result = None


# Première main si rien encore
if st.session_state.current_pos is None:
    if mode_jeu == "Libre (sans ranges)":
        do_roll_free()
    else:
        do_roll_range()

# -----------------------------
# Interaction selon le mode
# -----------------------------
if mode_jeu == "Libre (sans ranges)":
    c1, c2, c3 = st.columns(3)
    clicked_good = c1.button("✅ Bonne réponse")
    clicked_bad = c2.button("❌ Mauvaise réponse")
    clicked_new = c3.button("Nouvelle donne")

    if clicked_good:
        if st.session_state.current_case is not None:
            stats["good"] += 1
            weights[st.session_state.current_case] = max(
                0.2, weights[st.session_state.current_case] * 0.8
            )
            save_data(username, weights, stats)
        do_roll_free()

    elif clicked_bad:
        if st.session_state.current_case is not None:
            stats["bad"] += 1
            weights[st.session_state.current_case] = min(
                5.0, weights[st.session_state.current_case] * 1.5
            )
            save_data(username, weights, stats)
        do_roll_free()

    elif clicked_new:
        do_roll_free()

else:
    # ---------- Mode "Avec ranges de correction" ----------
    st.markdown("### Que fais-tu dans ce spot ?")

    col_a1, col_a2, col_a3 = st.columns(3)
    col_b1, col_b2, col_b3 = st.columns(3)

    actions_clicked = {}
    actions_clicked["fold"] = col_a1.button(f"{ACTION_EMOJI['fold']} Fold")
    actions_clicked["call"] = col_a2.button(f"{ACTION_EMOJI['call']} Call")
    actions_clicked["open"] = col_a3.button(f"{ACTION_EMOJI['open']} Open")
    actions_clicked["threebet"] = col_b1.button(f"{ACTION_EMOJI['threebet']} 3-bet")
    actions_clicked["open_shove"] = col_b2.button(
        f"{ACTION_EMOJI['open_shove']} Open shove"
    )
    actions_clicked["threebet_shove"] = col_b3.button(
        f"{ACTION_EMOJI['threebet_shove']} 3-bet shove"
    )

    clicked_new_range = st.button("Nouvelle main (mode ranges)")

    def handle_answer(chosen_action):
        rs = st.session_state.range_stats
        rs["played"] += 1
        pos = st.session_state.current_pos
        stack = st.session_state.current_stack
        hand_code = st.session_state.current_hand_code
        correct = st.session_state.current_correct_actions

        if chosen_action in correct:
            rs["correct"] += 1
            st.session_state.show_correction = False
            st.session_state.last_result = "good"
        else:
            rs["wrong"] += 1
            rs["errors_by_pos"][pos] += 1
            rs["errors_by_stack"][stack] += 1
            rs["errors_by_hand"][hand_code] += 1
            st.session_state.show_correction = True
            st.session_state.last_correction_spot = st.session_state.ranges_data.get(
                st.session_state.current_spot_key
            )
            st.session_state.last_correction_hand = hand_code
            st.session_state.last_result = "bad"

        st.session_state.range_stats = rs

    # Gestion des clics sur actions
    for act_key, pressed in actions_clicked.items():
        if pressed:
            handle_answer(act_key)
            break

    # Bouton pour passer à la main suivante
    if clicked_new_range:
        do_roll_range()

    # Feedback textuel
    if st.session_state.last_result == "good":
        st.success("Bonne réponse ✅")
    elif st.session_state.last_result == "bad":
        corr = ", ".join(
            ACTION_LABELS[a]
            for a in sorted(st.session_state.current_correct_actions)
        )
        st.error(f"Mauvaise réponse ❌ — actions correctes possibles : {corr}")

# -----------------------------
# Affichage de la correction (mode ranges)
# -----------------------------
if mode_jeu == "Avec ranges de correction" and st.session_state.show_correction:
    spot = st.session_state.last_correction_spot
    hand_code = st.session_state.last_correction_hand
    if spot is not None and hand_code is not None:
        with st.expander(
            "Voir la range de correction pour ce spot (après erreur)", expanded=True
        ):
            st.markdown(
                f"*Spot :* **{spot.get('table_type','?')}**, "
                f"Position **{spot.get('position','?')}**, "
                f"Stack **{spot.get('stack','?')} BB**, "
                f"Scénario `{spot.get('scenario','?')}`"
            )
            render_range_grid(spot, highlight_hand=hand_code)

# -----------------------------
# Statistiques mode libre
# -----------------------------
st.markdown("---")
st.subheader("📊 Statistiques – Mode libre")

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

# -----------------------------
# Statistiques mode ranges
# -----------------------------
st.markdown("---")
st.subheader("📊 Statistiques – Mode ranges de correction")

rs = st.session_state.range_stats
st.write(f"- Mains jouées : **{rs['played']}**")
st.write(f"- Bonnes réponses : **{rs['correct']}**")
st.write(f"- Mauvaises réponses : **{rs['wrong']}**")
if rs["played"]:
    st.write(
        f"- Taux de réussite : **{rs['correct'] / rs['played'] * 100:.1f} %**"
    )

if rs["played"] >= 10 and rs["wrong"] > 0:
    st.markdown("#### Erreurs les plus fréquentes")

    if rs["errors_by_pos"]:
        st.write("**Par position :**")
        for pos, cnt in sorted(
            rs["errors_by_pos"].items(), key=lambda kv: kv[1], reverse=True
        )[:5]:
            st.write(f"- {pos} : {cnt} erreurs")

    if rs["errors_by_stack"]:
        st.write("**Par stack :**")
        for stck, cnt in sorted(
            rs["errors_by_stack"].items(), key=lambda kv: kv[1], reverse=True
        )[:5]:
            st.write(f"- {stck} BB : {cnt} erreurs")

    if rs["errors_by_hand"]:
        st.write("**Par main (top 10) :**")
        for h, cnt in sorted(
            rs["errors_by_hand"].items(), key=lambda kv: kv[1], reverse=True
        )[:10]:
            st.write(f"- {h} : {cnt} erreurs")
else:
    st.info(
        "Les statistiques détaillées apparaîtront après au moins 10 mains jouées en mode ranges."
    )
