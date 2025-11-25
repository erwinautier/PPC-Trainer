import os
import sys
import json
import random
import hashlib
from collections import defaultdict

import streamlit as st

# --------------------- CONFIG GLOBALE ---------------------
st.set_page_config(
    page_title="Poker Trainer – Ranges & Leitner",
    page_icon="♠",
    layout="centered",
)

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


# --------------------- UTILITAIRES GÉNÉRAUX ---------------------
def base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def build_deck():
    return [f"{r}{s}" for r in RANKS for s in SUITS]


def canonical_from_cards(c1, c2):
    """AA, AKs, AKo, etc."""
    r1, s1 = c1[0], c1[1]
    r2, s2 = c2[0], c2[1]
    if r1 == r2:
        return r1 + r2
    hi, lo = sorted([r1, r2], key=lambda x: RANKS.index(x))
    return hi + lo + ("s" if s1 == s2 else "o")


def canonical_grid(i, j):
    """AA sur la diagonale, suited en haut, offsuit en bas."""
    r1 = RANKS[i]
    r2 = RANKS[j]
    if i == j:
        return r1 + r2
    hi = min(r1, r2, key=lambda x: RANKS.index(x))
    lo = max(r1, r2, key=lambda x: RANKS.index(x))
    return hi + lo + ("s" if i < j else "o")


def scenario_pretty_label(scenario: str):
    if scenario == "open":
        return "Open"
    if scenario.startswith("vs_open_"):
        vil = scenario[len("vs_open_"):]
        return f"Vs open {vil}"
    return scenario


# --------------------- AUTHENTIFICATION ---------------------
USERS_FILE = os.path.join(base_dir(), "users.json")


def load_users():
    if os.path.exists(USERS_FILE):
        try:
            return json.load(open(USERS_FILE))
        except Exception:
            return {}
    return {}


def save_users(users):
    json.dump(users, open(USERS_FILE, "w"), indent=2)


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


# --------------------- SAUVEGARDE LEITNER ---------------------
def leitner_file(username):
    safe = "".join(c for c in username if c.isalnum() or c in ("_", "-"))
    return os.path.join(base_dir(), f"leitner_{safe}.json")


def load_leitner(username):
    f = leitner_file(username)
    if os.path.exists(f):
        try:
            return json.load(open(f))
        except Exception:
            pass
    return {"weights": {}, "stats": {"good": 0, "bad": 0}}


def save_leitner(username, data):
    json.dump(data, open(leitner_file(username), "w"), indent=2)


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


# --------------------- RANGES JSON ---------------------
def load_ranges_from_filelike(filelike):
    try:
        data = json.load(filelike)
    except Exception:
        return {}
    spots = data.get("spots", {})
    # on laisse la structure telle quelle, le range_editor génère déjà ce qu'il faut
    return spots


def choose_random_spot(ranges_data, table_type):
    candidates = [
        (key, spot)
        for key, spot in ranges_data.items()
        if spot.get("table_type", "6-max") == table_type
    ]
    if not candidates:
        return None, None
    return random.choice(candidates)


def get_correct_actions_for_hand(spot_def, hand_code):
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


# --------------------- AFFICHAGE GRILLE DE RANGE ---------------------
def render_range_grid(spot_def, highlight_hand=None):
    actions = spot_def.get("actions", {})
    st.markdown("##### Range de correction")

    hand_actions = defaultdict(set)
    for act_name, hands in actions.items():
        for h in hands:
            hand_actions[h].add(act_name)

    header = st.columns(len(RANKS) + 1)
    header[0].markdown(" ")
    for j, r2 in enumerate(RANKS):
        header[j + 1].markdown(
            f"<div style='text-align:center;'><b>{r2}</b></div>",
            unsafe_allow_html=True,
        )

    for i, r1 in enumerate(RANKS):
        cols = st.columns(len(RANKS) + 1)
        cols[0].markdown(
            f"<div style='text-align:center;'><b>{r1}</b></div>",
            unsafe_allow_html=True,
        )
        for j, r2 in enumerate(RANKS):
            hand = canonical_grid(i, j)
            acts = hand_actions.get(hand, set())

            if not acts:
                # fold par défaut : point blanc cerclé
                color = "#FFFFFF"
                border = "1px solid #D1D5DB"
            else:
                border = "none"
                if "open_shove" in acts or "threebet_shove" in acts:
                    color = "#111827"
                elif "threebet" in acts:
                    color = "#DC2626"
                elif "open" in acts:
                    color = "#16A34A"
                elif "call" in acts:
                    color = "#FACC15"
                else:
                    color = "#6B7280"

            highlight_style = ""
            if highlight_hand is not None and hand == highlight_hand:
                highlight_style = "background-color:#E5E7EB;border-radius:6px;"

            cell_html = f"""
            <div style="font-size:11px;line-height:1.1;text-align:center;{highlight_style}">
              <span style="display:inline-block;width:18px;height:18px;
                           border-radius:999px;background-color:{color};
                           border:{border};"></span><br>
              <span>{hand}</span>
            </div>
            """
            cols[j + 1].markdown(cell_html, unsafe_allow_html=True)


# --------------------- INITIALISATION SESSION ---------------------
if "user" not in st.session_state:
    st.session_state.user = None

# Ranges en mémoire
if "ranges_data" not in st.session_state:
    st.session_state.ranges_data = {}

# Spot actuel
if "current_spot" not in st.session_state:
    st.session_state.current_spot = None  # dict

# Mode courant
if "current_mode" not in st.session_state:
    st.session_state.current_mode = None  # "Libre" / "Ranges"

# Stats ranges
if "range_stats" not in st.session_state:
    st.session_state.range_stats = {
        "played": 0,
        "correct": 0,
        "wrong": 0,
        "errors_by_pos": defaultdict(int),
        "errors_by_stack": defaultdict(int),
        "errors_by_hand": defaultdict(int),
    }

# Correction
if "show_correction" not in st.session_state:
    st.session_state.show_correction = False
if "last_correction_spot" not in st.session_state:
    st.session_state.last_correction_spot = None
if "last_correction_hand" not in st.session_state:
    st.session_state.last_correction_hand = None
if "last_result" not in st.session_state:
    st.session_state.last_result = None


# --------------------- SIDEBAR : LOGO + AUTH ---------------------
logo_path = "logo-penthievre.jpeg"
logo_full = os.path.join(base_dir(), logo_path)
if os.path.exists(logo_full):
    st.sidebar.image(logo_full, use_column_width=True)

st.sidebar.markdown("---")

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
                st.sidebar.error("Impossible de créer le profil (identifiant déjà pris ?)")
        else:
            if check_login(user, pwd):
                st.session_state.user = user.strip()
                st.sidebar.success("Connexion réussie.")
            else:
                st.sidebar.error("Identifiant ou mot de passe incorrect.")
    st.stop()

username = st.session_state.user
leitner = load_leitner(username)

# --------------------- SIDEBAR : OPTIONS ---------------------
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

if mode == "Ranges":
    st.sidebar.markdown("### Fichier ranges (.json)")
    ranges_file = st.sidebar.file_uploader(
        "Charger un fichier de ranges (JSON du range_editor)", type=["json"]
    )
    if ranges_file is not None:
        st.session_state.ranges_data = load_ranges_from_filelike(ranges_file)
else:
    ranges_file = None

# Reset Leitner
if st.sidebar.button("♻️ Reset profil (mode libre)"):
    leitner = {"weights": {}, "stats": {"good": 0, "bad": 0}}
    save_leitner(username, leitner)
    st.sidebar.success("Progrès mode libre remis à zéro.")


# --------------------- CHANGEMENT DE MODE ---------------------
if st.session_state.current_mode != mode:
    st.session_state.current_mode = mode
    st.session_state.current_spot = None
    st.session_state.show_correction = False
    st.session_state.last_result = None

# --------------------- TIRAGE DE SPOT ---------------------
def new_free_spot():
    positions = POSITIONS_6MAX if table_type == "6-max" else POSITIONS_8MAX
    # 50% du temps : Leitner pondéré, 50% : stack favori
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


# --------------------- MAIN UI ---------------------
st.title("🃏 Poker Trainer – Ranges & Leitner")
st.markdown(f"*Profil : **{username}***")

# Conteneur pour la carte (affiché en haut)
card_container = st.empty()
info_container = st.empty()

st.markdown("---")

# --------------------- BOUTONS / LOGIQUE AVANT AFFICHAGE ---------------------
need_new_spot = False

if mode == "Libre":
    # Boutons mode libre
    col1, col2, col3 = st.columns(3)
    clicked_good = col1.button("✅ Bonne réponse")
    clicked_bad = col2.button("❌ Mauvaise réponse")
    clicked_new = col3.button("Nouvelle donne")

    # On utilise le spot avant éventuel changement
    spot = st.session_state.current_spot

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
    # Mode Ranges : boutons actions + nouvelle main
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

    spot = st.session_state.current_spot

    # Gestion des réponses
    if spot and spot["mode"] == "Ranges":
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

    if mode == "Ranges" and clicked_new_range:
        need_new_spot = True
        st.session_state.show_correction = False
        st.session_state.last_result = None

# --------------------- CRÉATION / RENOUVELLEMENT DU SPOT ---------------------
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

# --------------------- AFFICHAGE DU SPOT (CARTE) ---------------------
if not spot:
    st.warning("Impossible de générer un spot (vérifie le fichier de ranges en mode Ranges).")
else:
    pos = spot["position"]
    stack = spot["stack"]
    c1, c2 = spot["cards"]
    hand_code = spot["hand_code"]

    # Couleurs cartes
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

# --------------------- FEEDBACK / CORRECTION ---------------------
if mode == "Ranges":
    if st.session_state.last_result == "good":
        st.success("Bonne réponse ✅")
    elif st.session_state.last_result == "bad":
        correct_actions = st.session_state.current_spot["correct_actions"]
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

# --------------------- STATISTIQUES MODE LIBRE ---------------------
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

# --------------------- STATISTIQUES MODE RANGES ---------------------
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
