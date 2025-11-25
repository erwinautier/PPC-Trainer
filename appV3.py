import os
import sys
import json
import random
import hashlib
import streamlit as st
import streamlit.components.v1 as components

from collections import defaultdict

import streamlit as st

# =========================================================
# Configuration globale
# =========================================================
st.set_page_config(
    page_title="Poker Trainer – Ranges & Leitner",
    page_icon="♠",
    layout="centered",
)

# --------------------- Constantes Poker -------------------
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
    "fold": "⚪",      # point blanc pour fold
    "call": "🟡",
    "open": "🟢",
    "threebet": "🔴",
    "open_shove": "🟣",
    "threebet_shove": "⚫",
}


# =========================================================
# Fonctions utilitaires générales
# =========================================================
def base_dir():
    """Dossier de base de l'application (utile aussi en exécutable)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def build_deck():
    """Construit un paquet de 52 cartes."""
    return [f"{r}{s}" for r in RANKS for s in SUITS]


def canonical_from_cards(c1, c2):
    """Convertit deux cartes (ex: A♠, K♦) en code type AA, AKs, AKo, etc."""
    r1, s1 = c1[0], c1[1]
    r2, s2 = c2[0], c2[1]
    if r1 == r2:
        return r1 + r2
    hi, lo = sorted([r1, r2], key=lambda x: RANKS.index(x))
    return hi + lo + ("s" if s1 == s2 else "o")


def canonical_grid(i, j):
    """
    Code de main pour la grille :
    - diagonale : AA, KK, ...
    - au-dessus : suited (AKs, AQs, ...)
    - en-dessous : offsuit (AKo, AQo, ...)
    """
    r1 = RANKS[i]
    r2 = RANKS[j]
    if i == j:
        return r1 + r2
    hi = min(r1, r2, key=lambda x: RANKS.index(x))
    lo = max(r1, r2, key=lambda x: RANKS.index(x))
    return hi + lo + ("s" if i < j else "o")


def scenario_pretty_label(scenario: str):
    """Label lisible pour le scénario (open, vs_open_BTN, etc.)."""
    if scenario == "open":
        return "Open"
    if scenario.startswith("vs_open_"):
        vil = scenario[len("vs_open_"):]
        return f"Vs open {vil}"
    return scenario


# =========================================================
# Authentification
# =========================================================
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
# Gestion fichiers ranges (défaut & perso)
# =========================================================
def user_ranges_path(username: str) -> str:
    """Chemin du fichier de ranges personnel d'un profil."""
    safe = "".join(c for c in username if c.isalnum() or c in ("_", "-"))
    return os.path.join(base_dir(), f"ranges_{safe}.json")


def default_ranges_path() -> str:
    """Chemin du fichier de ranges par défaut global."""
    return os.path.join(base_dir(), "default_ranges.json")


def load_spots_from_path(path: str) -> dict:
    """Charge un fichier JSON de ranges depuis un chemin (retourne spots)."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        spots = data.get("spots", {})
        if isinstance(spots, dict):
            return spots
        return {}
    except Exception:
        return {}


def load_ranges_from_filelike(filelike) -> dict:
    """Charge les spots depuis un fichier streamlit uploadé."""
    try:
        data = json.load(filelike)
    except Exception:
        return {}
    spots = data.get("spots", {})
    return spots if isinstance(spots, dict) else {}


# =========================================================
# Sauvegarde Leitner (mode libre)
# =========================================================
def leitner_file(username):
    safe = "".join(c for c in username if c.isalnum() or c in ("_", "-"))
    return os.path.join(base_dir(), f"leitner_{safe}.json")


def load_leitner(username):
    f = leitner_file(username)
    if os.path.exists(f):
        try:
            return json.load(open(f, "r", encoding="utf-8"))
        except Exception:
            pass
    return {"weights": {}, "stats": {"good": 0, "bad": 0}}


def save_leitner(username, data):
    json.dump(data, open(leitner_file(username), "w", encoding="utf-8"), indent=2)


def get_weight(leitner_data, pos, stack):
    return float(leitner_data["weights"].get(f"{pos}|{stack}", 1.0))


def update_weight(leitner_data, pos, stack, factor, min_val=0.2, max_val=5.0):
    key = f"{pos}|{stack}"
    w = leitner_data["weights"].get(key, 1.0)
    w *= factor
    w = max(min_val, min(max_val, w))
    leitner_data["weights"][key] = w


def weighted_position_stack_choice(leitner_data, positions):
    cases = [(p, s) for p in positions for s in STACKS]
    weights = [get_weight(leitner_data, p, s) for (p, s) in cases]
    total = sum(weights)
    r = random.uniform(0, total)
    cum = 0
    for (p, s), w in zip(cases, weights):
        cum += w
        if r <= cum:
            return p, s
    return random.choice(cases)


def weighted_stack_choice(selected_stack):
    if selected_stack is not None and random.random() < 0.5:
        return selected_stack
    if selected_stack is None:
        return random.choice(STACKS)
    others = [s for s in STACKS if s != selected_stack]
    return random.choice(others) if others else selected_stack


# =========================================================
# Ranges : choix du spot et correction
# =========================================================
def choose_random_spot(ranges_data, table_type):
    """Choisit un spot au hasard parmi ceux du bon format (6-max / 8-max)."""
    candidates = [
        (key, spot)
        for key, spot in ranges_data.items()
        if spot.get("table_type", "6-max") == table_type
    ]
    if not candidates:
        return None, None
    return random.choice(candidates)


def get_correct_actions_for_hand(spot_def, hand_code):
    """Retourne l'ensemble des actions correctes pour une main donnée dans un spot."""
    actions = spot_def.get("actions", {})
    non_fold = set()
    for act in ["open", "call", "threebet", "open_shove", "threebet_shove"]:
        for h in actions.get(act, []):
            if h == hand_code:
                non_fold.add(act)
    if not non_fold:
        return {"fold"}
    res = set(non_fold)
    if hand_code in actions.get("fold", []):
        res.add("fold")
    return res


def render_range_grid(spot_def, highlight_hand=None):
    """Affiche la range sous forme de tableau HTML très compact (mobile-friendly)."""
    from collections import defaultdict

    actions = spot_def.get("actions", {})

    st.markdown("##### Range de correction")

    if not actions:
        st.info("Aucune action définie pour ce spot.")
        return

    # main -> set(actions)
    hand_actions = defaultdict(set)
    for act_name, hands in actions.items():
        for h in hands:
            hand_actions[h].add(act_name)

    html_parts = []

    # Conteneur scrollable. On garde overflow-x:auto au cas où, mais on compresse au max.
    html_parts.append(
        "<div style='overflow-x:auto; max-width:100%; "
        "border:1px solid #e5e7eb; border-radius:8px; "
        "padding:4px; background-color:#fafafa;'>"
    )
    # min-width très réduite pour que ça tienne sur téléphone
    html_parts.append(
        "<table style='border-collapse:collapse; font-size:9px; min-width:260px;'>"
    )

    # En-tête colonnes
    html_parts.append("<thead><tr>")
    html_parts.append("<th style='padding:2px; text-align:center;'></th>")
    for r2 in RANKS:
        html_parts.append(
            f"<th style='padding:2px; text-align:center;'>{r2}</th>"
        )
    html_parts.append("</tr></thead>")

    # Corps du tableau
    html_parts.append("<tbody>")
    for i, r1 in enumerate(RANKS):
        html_parts.append("<tr>")
        # Tête de ligne (rang)
        html_parts.append(
            f"<th style='padding:2px; text-align:center;'>{r1}</th>"
        )

        for j, r2 in enumerate(RANKS):
            hand = canonical_grid(i, j)
            acts = hand_actions.get(hand, set())

            if not acts:
                color = "#FFFFFF"          # fold = blanc
                border = "1px solid #D1D5DB"
            else:
                border = "none"
                if "open_shove" in acts or "threebet_shove" in acts:
                    color = "#111827"      # shove = noir
                elif "threebet" in acts:
                    color = "#DC2626"      # 3-bet = rouge
                elif "open" in acts:
                    color = "#16A34A"      # open = vert
                elif "call" in acts:
                    color = "#FACC15"      # call = jaune
                else:
                    color = "#6B7280"      # autre = gris

            # Surlignage de la main fautive (tout le fond de la cellule)
            highlight_style = ""
            if highlight_hand is not None and hand == highlight_hand:
                highlight_style = "background-color:#E5E7EB; border-radius:4px;"

            cell_html = f"""
            <td style="padding:1px; text-align:center; {highlight_style}">
              <span style="
                  display:inline-block;
                  width:10px; height:10px;
                  border-radius:999px;
                  background-color:{color};
                  border:{border};
              "></span>
            </td>
            """
            html_parts.append(cell_html)

        html_parts.append("</tr>")
    html_parts.append("</tbody></table></div>")

    table_html = "".join(html_parts)

    # Affichage en HTML brut dans un iframe Streamlit
    components.html(table_html, height=260, scrolling=True)




# =========================================================
# Initialisation des états Streamlit
# =========================================================
if "user" not in st.session_state:
    st.session_state.user = None

if "ranges_default" not in st.session_state:
    st.session_state.ranges_default = {}

if "ranges_personal" not in st.session_state:
    st.session_state.ranges_personal = {}

if "ranges_data" not in st.session_state:
    st.session_state.ranges_data = {}

if "current_spot" not in st.session_state:
    st.session_state.current_spot = None  # dict avec infos du spot actuel

if "current_mode" not in st.session_state:
    st.session_state.current_mode = None  # "Libre" ou "Ranges"

if "range_stats" not in st.session_state:
    st.session_state.range_stats = {
        "played": 0,
        "correct": 0,
        "wrong": 0,
        "errors_by_pos": defaultdict(int),
        "errors_by_stack": defaultdict(int),
        "errors_by_hand": defaultdict(int),
    }

if "show_correction" not in st.session_state:
    st.session_state.show_correction = False
if "last_correction_spot" not in st.session_state:
    st.session_state.last_correction_spot = None
if "last_correction_hand" not in st.session_state:
    st.session_state.last_correction_hand = None
if "last_result" not in st.session_state:
    st.session_state.last_result = None

# =========================================================
# Sidebar : logo + auth
# =========================================================
logo_path = "logo-penthievre.jpeg"
logo_full = os.path.join(base_dir(), logo_path)
if os.path.exists(logo_full):
    st.sidebar.image(logo_full, use_column_width=True)

st.sidebar.markdown("---")

# Authentification
if st.session_state.user:
    st.sidebar.markdown(f"### Connecté : `{st.session_state.user}`")
    if st.sidebar.button("Se déconnecter"):
        st.session_state.user = None
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
            else:
                st.sidebar.error("Identifiant déjà utilisé ou invalide.")
        else:
            if check_login(user, pwd):
                st.session_state.user = user.strip()
                st.sidebar.success("Connexion réussie.")
            else:
                st.sidebar.error("Identifiant ou mot de passe incorrect.")
    st.stop()

username = st.session_state.user
leitner = load_leitner(username)

# =========================================================
# Sidebar : options générales
# =========================================================
st.sidebar.markdown("---")
st.sidebar.markdown("### Options générales")

table_type = st.sidebar.radio("Format de table", ["6-max", "8-max"])
mode = st.sidebar.radio("Mode de jeu", ["Libre", "Ranges"])

selected_stack = None
if mode == "Libre":
    fav = st.sidebar.radio(
        "Stack surreprésenté (≈ 50 % des tirages)",
        options=["Aucun"] + [str(s) for s in STACKS],
    )
    selected_stack = None if fav == "Aucun" else int(fav)

# Gestion des ranges (défaut / perso + upload)
if mode == "Ranges":
    st.sidebar.markdown("### Source des ranges")

    ranges_source = st.sidebar.radio(
        "Choix des ranges",
        options=["Ranges par défaut", "Ranges perso"],
    )

    # On pré-charge les fichiers sur disque si possible
    user_path = user_ranges_path(username)
    default_path = default_ranges_path()

    if not st.session_state.ranges_default and os.path.exists(default_path):
        st.session_state.ranges_default = load_spots_from_path(default_path)

    if not st.session_state.ranges_personal and os.path.exists(user_path):
        st.session_state.ranges_personal = load_spots_from_path(user_path)

    st.sidebar.markdown("### Importer / mettre à jour vos ranges perso")
    ranges_file = st.sidebar.file_uploader(
        "Charger un JSON exporté du range_editor",
        type=["json"],
        key="ranges_file_uploader",
    )

    # Si l'utilisateur importe un fichier -> on l'enregistre comme ranges perso
    if ranges_file is not None:
        spots = load_ranges_from_filelike(ranges_file)
        if spots:
            # On sauvegarde en dur pour ce profil
            try:
                ranges_file.seek(0)
                content = ranges_file.getvalue()
                with open(user_path, "wb") as f:
                    f.write(content)
            except Exception:
                pass
            st.session_state.ranges_personal = spots
            st.sidebar.success("Ranges perso mises à jour pour ce profil.")
        else:
            st.sidebar.error("Fichier de ranges invalide (clé 'spots' manquante ou incorrecte).")

    # Choix effectif des ranges à utiliser (avec fallback)
    active_ranges = {}
    error_personal = False

    if ranges_source == "Ranges perso":
        if st.session_state.ranges_personal:
            active_ranges = st.session_state.ranges_personal
        else:
            error_personal = True
            st.sidebar.error("Aucune ranges perso enregistrée. On utilise les ranges par défaut.")
            if st.session_state.ranges_default:
                active_ranges = st.session_state.ranges_default
            else:
                active_ranges = {}
    else:  # Ranges par défaut
        if st.session_state.ranges_default:
            active_ranges = st.session_state.ranges_default
        elif st.session_state.ranges_personal:
            st.sidebar.info("Pas de default_ranges.json, utilisation des ranges perso.")
            active_ranges = st.session_state.ranges_personal
        else:
            active_ranges = {}

    st.session_state.ranges_data = active_ranges

else:
    ranges_source = None
    ranges_file = None

# Reset Leitner (mode libre)
if st.sidebar.button("♻️ Reset profil (mode libre)"):
    leitner = {"weights": {}, "stats": {"good": 0, "bad": 0}}
    save_leitner(username, leitner)
    st.sidebar.success("Progrès mode libre remis à zéro.")


# =========================================================
# Gestion changement de mode
# =========================================================
if st.session_state.current_mode != mode:
    st.session_state.current_mode = mode
    st.session_state.current_spot = None
    st.session_state.show_correction = False
    st.session_state.last_result = None


# =========================================================
# Fonctions de tirage de spots
# =========================================================
def new_free_spot():
    """Crée un nouveau spot pour le mode libre (Leitner)."""
    positions = POSITIONS_6MAX if table_type == "6-max" else POSITIONS_8MAX

    # 50% Leitner pondéré, 50% stack favori
    if random.random() < 0.5:
        pos, stack = weighted_position_stack_choice(leitner, positions)
    else:
        pos = random.choice(positions)
        stack = weighted_stack_choice(selected_stack)

    deck = build_deck()
    random.shuffle(deck)
    c1, c2 = deck[:2]
    hand_code = canonical_from_cards(c1, c2)

    extra = ""
    scenario_label = "Open"
    if pos == "BB":
        open_from = random.choice([p for p in positions if p != "BB"])
        extra = f"Open de {open_from}"
        scenario_label = f"Vs open {open_from}"

    return {
        "mode": "Libre",
        "position": pos,
        "stack": stack,
        "cards": (c1, c2),
        "hand_code": hand_code,
        "scenario_label": scenario_label,
        "extra": extra,
    }


def new_range_spot():
    """Crée un nouveau spot pour le mode ranges (en s'appuyant sur ranges_data)."""
    ranges_data = st.session_state.ranges_data
    if not ranges_data:
        return None

    key, spot_def = choose_random_spot(ranges_data, table_type)
    if key is None:
        return None

    pos = spot_def["position"]
    stack = spot_def["stack"]
    scenario = spot_def["scenario"]

    deck = build_deck()
    random.shuffle(deck)
    c1, c2 = deck[:2]
    hand_code = canonical_from_cards(c1, c2)
    correct_actions = get_correct_actions_for_hand(spot_def, hand_code)

    extra = ""
    scen_label = scenario_pretty_label(scenario)
    if scenario.startswith("vs_open_"):
        vil = scenario[len("vs_open_"):]
        extra = f"Open de {vil}"

    return {
        "mode": "Ranges",
        "spot_key": key,
        "spot_def": spot_def,
        "position": pos,
        "stack": stack,
        "cards": (c1, c2),
        "hand_code": hand_code,
        "scenario_label": scen_label,
        "extra": extra,
        "correct_actions": correct_actions,
    }


# =========================================================
# UI principale : titre + conteneurs
# =========================================================
st.title("🃏 Poker Trainer – Ranges & Leitner")
st.markdown(f"*Profil : **{username}***")

card_container = st.empty()
info_container = st.empty()

st.markdown("---")

# =========================================================
# Gestion des boutons AVANT affichage du spot
# =========================================================
need_new_spot = False
spot = st.session_state.current_spot

if mode == "Libre":
    col1, col2, col3 = st.columns(3)
    clicked_good = col1.button("✅ Bonne réponse")
    clicked_bad = col2.button("❌ Mauvaise réponse")
    clicked_new = col3.button("Nouvelle donne")

    if clicked_good and spot and spot["mode"] == "Libre":
        leitner["stats"]["good"] += 1
        update_weight(leitner, spot["position"], spot["stack"], factor=0.8)
        save_leitner(username, leitner)
        need_new_spot = True

    elif clicked_bad and spot and spot["mode"] == "Libre":
        leitner["stats"]["bad"] += 1
        update_weight(leitner, spot["position"], spot["stack"], factor=1.5)
        save_leitner(username, leitner)
        need_new_spot = True

    elif clicked_new:
        need_new_spot = True

else:
    # Mode Ranges : boutons d'action + nouvelle main
    st.markdown("### Que fais-tu dans ce spot ?")
    colA1, colA2, colA3 = st.columns(3)
    colB1, colB2, colB3 = st.columns(3)

    actions_clicked = {
        "fold": colA1.button(f"{ACTION_EMOJI['fold']} Fold"),
        "call": colA2.button(f"{ACTION_EMOJI['call']} Call"),
        "open": colA3.button(f"{ACTION_EMOJI['open']} Open"),
        "threebet": colB1.button(f"{ACTION_EMOJI['threebet']} 3-bet"),
        "open_shove": colB2.button(f"{ACTION_EMOJI['open_shove']} Open shove"),
        "threebet_shove": colB3.button(
            f"{ACTION_EMOJI['threebet_shove']} 3-bet shove"
        ),
    }

    clicked_new_range = st.button("Nouvelle main (mode ranges)")

    if spot and spot["mode"] == "Ranges":
        # Évaluation de la réponse sur le spot courant (pas de tirage ici)
        for act_key, pressed in actions_clicked.items():
            if pressed:
                rs = st.session_state.range_stats
                rs["played"] += 1
                pos = spot["position"]
                stack = spot["stack"]
                hand_code = spot["hand_code"]
                correct = spot["correct_actions"]

                if act_key in correct:
                    rs["correct"] += 1
                    st.session_state.show_correction = False
                    st.session_state.last_result = "good"
                else:
                    rs["wrong"] += 1
                    rs["errors_by_pos"][pos] += 1
                    rs["errors_by_stack"][stack] += 1
                    rs["errors_by_hand"][hand_code] += 1
                    st.session_state.show_correction = True
                    st.session_state.last_correction_spot = spot["spot_def"]
                    st.session_state.last_correction_hand = hand_code
                    st.session_state.last_result = "bad"

                st.session_state.range_stats = rs
                break

    if clicked_new_range:
        need_new_spot = True
        st.session_state.show_correction = False
        st.session_state.last_result = None

# =========================================================
# Création / renouvellement de spot si nécessaire
# =========================================================
if st.session_state.current_spot is None or need_new_spot:
    if mode == "Libre":
        st.session_state.current_spot = new_free_spot()
        st.session_state.show_correction = False
        st.session_state.last_result = None
    else:
        new_spot = new_range_spot()
        if new_spot is not None:
            st.session_state.current_spot = new_spot
            st.session_state.show_correction = False
            st.session_state.last_result = None

spot = st.session_state.current_spot

# =========================================================
# Affichage du spot
# =========================================================
if not spot:
    st.warning("Impossible de générer un spot (vérifie les ranges en mode Ranges).")
else:
    pos = spot["position"]
    stack = spot["stack"]
    c1, c2 = spot["cards"]
    hand_code = spot["hand_code"]

    def colorize(card):
        suit = card[-1]
        color = "#DC2626" if suit in {"♥", "♦"} else "#111827"
        return f"<span style='color:{color}'>{card}</span>"

    hand_html = f"{colorize(c1)}&nbsp;&nbsp;{colorize(c2)}"
    scenario_label = spot.get("scenario_label", "")
    extra_text = spot.get("extra", "")

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
          <div style="font-size:32px;font-weight:bold;">{pos}</div>
        </div>
        <div style="flex:1;text-align:center;">
          <div style="font-size:12px;color:#666;">Stack (BB)</div>
          <div style="font-size:32px;font-weight:bold;">{stack}</div>
        </div>
      </div>
      <div style="margin-top:14px;text-align:center;">
        <div style="font-size:12px;color:#666;">Main</div>
        <div style="font-size:32px;font-weight:bold;">{hand_html}</div>
      </div>
    </div>
    """
    card_container.markdown(card_html, unsafe_allow_html=True)

    info_lines = []
    if extra_text:
        info_lines.append(extra_text)
    if scenario_label:
        info_lines.append(f"Scénario : {scenario_label}")
    if mode == "Ranges":
        info_lines.append(f"Spot : `{spot['spot_key']}`")

    if info_lines:
        info_container.markdown("<br>".join(info_lines))

# =========================================================
# Feedback / correction (mode ranges)
# =========================================================
if mode == "Ranges":
    if st.session_state.last_result == "good":
        st.success("Bonne réponse ✅")
    elif st.session_state.last_result == "bad":
        correct_actions = spot["correct_actions"]
        corr = ", ".join(ACTION_LABELS[a] for a in sorted(correct_actions))
        st.error(f"Mauvaise réponse ❌ — actions possibles : {corr}")

    if st.session_state.show_correction:
        sdef = st.session_state.last_correction_spot
        hcode = st.session_state.last_correction_hand
        if sdef is not None and hcode is not None:
            with st.expander("Voir la range de correction pour ce spot", expanded=True):
                st.markdown(
                    f"*Spot :* **{sdef.get('table_type','?')}**, "
                    f"Position **{sdef.get('position','?')}**, "
                    f"Stack **{sdef.get('stack','?')} BB**, "
                    f"Scénario `{sdef.get('scenario','?')}`"
                )
                render_range_grid(sdef, highlight_hand=hcode)

# =========================================================
# Statistiques mode libre
# =========================================================
st.markdown("---")
st.subheader("📊 Statistiques – Mode libre")

g = leitner["stats"]["good"]
b = leitner["stats"]["bad"]
tot = g + b
rate = (g / tot * 100) if tot else 0.0
st.write(f"- Bonnes réponses : **{g}**")
st.write(f"- Mauvaises réponses : **{b}**")
st.write(f"- Taux de réussite : **{rate:.1f}%**")

if leitner["weights"]:
    avg_w = sum(leitner["weights"].values()) / len(leitner["weights"])
    st.write(f"- Poids moyen (difficulté) : **{avg_w:.2f}**")
    hardest = sorted(leitner["weights"].items(), key=lambda kv: kv[1], reverse=True)[:3]
    if hardest:
        st.write("**Spots les plus difficiles (souvent revus) :**")
        for key, w in hardest:
            pos_, stack_ = key.split("|")
            st.write(f"- {pos_} – {stack_} BB (poids {w:.2f})")

# =========================================================
# Statistiques mode ranges
# =========================================================
st.markdown("---")
st.subheader("📊 Statistiques – Mode ranges de correction")

rs = st.session_state.range_stats
st.write(f"- Mains jouées : **{rs['played']}**")
st.write(f"- Bonnes réponses : **{rs['correct']}**")
st.write(f"- Mauvaises réponses : **{rs['wrong']}**")
if rs["played"]:
    st.write(f"- Taux de réussite : **{rs['correct'] / rs['played'] * 100:.1f}%**")

if rs["played"] >= 10 and rs["wrong"] > 0:
    st.markdown("#### Erreurs les plus fréquentes")
    if rs["errors_by_pos"]:
        st.write("**Par position :**")
        for pos_, cnt in sorted(rs["errors_by_pos"].items(), key=lambda kv: kv[1], reverse=True)[:5]:
            st.write(f"- {pos_} : {cnt} erreurs")
    if rs["errors_by_stack"]:
        st.write("**Par stack :**")
        for stck, cnt in sorted(rs["errors_by_stack"].items(), key=lambda kv: kv[1], reverse=True)[:5]:
            st.write(f"- {stck} BB : {cnt} erreurs")
    if rs["errors_by_hand"]:
        st.write("**Par main (top 10) :**")
        for h, cnt in sorted(rs["errors_by_hand"].items(), key=lambda kv: kv[1], reverse=True)[:10]:
            st.write(f"- {h} : {cnt} erreurs")
else:
    st.info("Les stats détaillées apparaîtront après au moins 10 mains jouées en mode ranges.")
