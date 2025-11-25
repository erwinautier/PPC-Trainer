# ranges_editor.py
import os
import json
from collections import defaultdict

import streamlit as st

# -----------------------------
# Constantes poker
# -----------------------------
RANKS = ["A", "K", "Q", "J", "T", "9", "8", "7", "6", "5", "4", "3", "2"]

# Positions pour chaque format
POSITIONS_6MAX = ["LJ", "HJ", "CO", "BTN", "SB", "BB"]
POSITIONS_8MAX = ["UTG", "UTG+1", "LJ", "HJ", "CO", "BTN", "SB", "BB"]

STACKS = [100, 50, 25, 20, 19, 18, 17, 16, 15, 14, 13, 12, 11, 10]

# Actions (hors fold qui reste implicite)
ACTIONS = ["open", "call", "threebet", "open_shove", "threebet_shove"]
ACTION_LABELS = {
    "open": "Open",
    "call": "Call",
    "threebet": "3-bet",
    "open_shove": "Open shove",
    "threebet_shove": "3-bet shove",
}
ACTION_EMOJI = {
    "open": "🟢",
    "call": "🟡",
    "threebet": "🔴",
    "open_shove": "🟣",       # violet
    "threebet_shove": "⚫",   # noir
    "fold": "❌"
}
EMPTY_EMOJI = "⬜"


# -----------------------------
# Utilitaires
# -----------------------------
def base_dir():
    return os.path.dirname(os.path.abspath(__file__))


def make_spot_key(position: str, stack: int, scenario: str) -> str:
    # On ne met pas le format dans la clé -> un même spot peut exister
    # dans deux fichiers différents si besoin.
    return f"{position}_{stack}_{scenario}"


def canonical_hand_from_indices(i: int, j: int) -> str:
    """
    Convertit indices (ligne, colonne) en main canonique :
    - diagonale : paires (AA, KK, ...)
    - triangle supérieur : suited (AKs, AQs, ...)
    - triangle inférieur : offsuit (AKo, AQo, ...)
    (comme dans la majorité des rangers : haut = suited, bas = off)
    """
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
        return hi + lo + "s"   # triangle supérieur = suited
    else:
        return hi + lo + "o"   # triangle inférieur = offsuit


def all_hands_set():
    hands = set()
    for i in range(len(RANKS)):
        for j in range(len(RANKS)):
            hands.add(canonical_hand_from_indices(i, j))
    return hands


ALL_HANDS = all_hands_set()


# -----------------------------
# Callback pour un clic sur une main
# -----------------------------
def update_hand_action(spot_key: str, hand_code: str):
    """Callback appelé quand on clique sur un bouton de la grille."""
    spots = st.session_state.spots
    position, stack_str, scenario = spot_key.split("_", 2)
    stack = int(stack_str)

    spot = spots.get(
        spot_key,
        {
            "position": position,
            "stack": stack,
            "scenario": scenario,
            "hand_actions": {},
        },
    )
    hand_actions = spot.get("hand_actions", {})
    current_action = st.session_state.current_action

    if current_action == "effacer":
        # enlever toutes les actions pour cette main
        if hand_code in hand_actions:
            del hand_actions[hand_code]
    else:
        act = current_action
        s = hand_actions.get(hand_code, set())
        if act in s:
            s.remove(act)
        else:
            s.add(act)
        if s:
            hand_actions[hand_code] = s
        elif hand_code in hand_actions:
            del hand_actions[hand_code]

    spot["hand_actions"] = hand_actions
    spots[spot_key] = spot
    st.session_state.spots = spots


# -----------------------------
# Config Streamlit
# -----------------------------
st.set_page_config(
    page_title="Éditeur de ranges (grille)",
    page_icon="🧮",
    layout="wide",
)

st.title("🧮 Éditeur de ranges préflop – mode grille cliquable")

st.markdown(
    """
- **Choisis 6-max ou 8-max**, puis la position, le stack et le scénario.  
- **Clique** sur les cases pour affecter des actions (Open / Call / 3-bet / Open shove / 3-bet shove).  
- Une case peut avoir **plusieurs actions** (mix : par ex. Open + 3-bet).  
- Toute case **non cochée** sera considérée comme **Fold** par défaut dans le fichier exporté.  
- Tu peux créer **une liste de ranges** (spots) : un spot = Position + Stack + Scénario.
"""
)

# -----------------------------
# État en session
# -----------------------------
if "spots" not in st.session_state:
    # spot_key -> {"position","stack","scenario","hand_actions": {hand: set(actions)}}
    st.session_state.spots = {}

if "current_spot_key" not in st.session_state:
    st.session_state.current_spot_key = None

if "current_action" not in st.session_state:
    st.session_state.current_action = "open"

if "table_type" not in st.session_state:
    st.session_state.table_type = "6-max"

if "scenario" not in st.session_state:
    st.session_state.scenario = "open"

# -----------------------------
# Sidebar : chargement / sauvegarde
# -----------------------------
st.sidebar.header("Fichiers de ranges")

uploaded = st.sidebar.file_uploader(
    "Charger un fichier de ranges (.json)", type=["json"]
)
if uploaded is not None:
    try:
        data = json.load(uploaded)
        spots_json = data.get("spots", {})
        new_spots = {}
        for key, spot in spots_json.items():
            pos = spot.get("position")
            stack = spot.get("stack")
            scen = spot.get("scenario", "open")
            actions = spot.get("actions", {})
            hand_actions = {}
            for act_name in ACTIONS:
                for h in actions.get(act_name, []):
                    if h in ALL_HANDS:
                        hand_actions.setdefault(h, set()).add(act_name)
            new_spots[key] = {
                "position": pos,
                "stack": stack,
                "scenario": scen,
                "hand_actions": hand_actions,
            }
        st.session_state.spots = new_spots
        st.sidebar.success("Fichier de ranges chargé avec succès ✅")
    except Exception as e:
        st.sidebar.error(f"Erreur de lecture du fichier : {e}")

if st.sidebar.button("🗑️ Effacer toutes les ranges de la session"):
    st.session_state.spots = {}
    st.sidebar.success("Toutes les ranges ont été effacées (dans la session).")

# Préparation export JSON (cases vides -> fold)
export_spots = {}
for key, spot in st.session_state.spots.items():
    pos = spot["position"]
    stack = spot["stack"]
    scen = spot["scenario"]
    hand_actions = spot.get("hand_actions", {})

    actions_dict = defaultdict(list)
    for h in ALL_HANDS:
        acts = hand_actions.get(h, set())
        if not acts:
            actions_dict["fold"].append(h)
        else:
            for act in acts:
                if act in ACTIONS:
                    actions_dict[act].append(h)

    export_spots[key] = {
        "position": pos,
        "stack": stack,
        "scenario": scen,
        "actions": {
            act: sorted(hands) for act, hands in actions_dict.items()
        },
    }

export_data = {"version": 1, "spots": export_spots}
export_json = json.dumps(export_data, indent=2)

st.sidebar.download_button(
    label="💾 Télécharger le fichier de ranges",
    data=export_json,
    file_name="ranges_poker_trainer.json",
    mime="application/json",
)

# -----------------------------
# Format de table & sélection du spot
# -----------------------------
st.subheader("🎯 Sélection du spot à éditer")

table_type = st.radio(
    "Format de table",
    ["6-max", "8-max"],
    index=0 if st.session_state.table_type == "6-max" else 1,
    horizontal=True,
)
st.session_state.table_type = table_type

if table_type == "6-max":
    positions_list = POSITIONS_6MAX
else:
    positions_list = POSITIONS_8MAX

col_sel1, col_sel2, col_sel3 = st.columns(3)
with col_sel1:
    position = st.selectbox("Position", positions_list, index=0)
with col_sel2:
    stack = st.selectbox("Stack (BB)", STACKS, index=0)

# Scénarios dépendants de la position (open + vs_open_X pour tous les X avant)
pos_index = positions_list.index(position)
previous_positions = positions_list[:pos_index]
available_scenarios = ["open"] + [f"vs_open_{p}" for p in previous_positions]

with col_sel3:
    default_idx = (
        available_scenarios.index(st.session_state.scenario)
        if st.session_state.scenario in available_scenarios
        else 0
    )
    scenario = st.selectbox(
        "Scénario",
        available_scenarios,
        index=default_idx,
    )

st.session_state.scenario = scenario

spot_key = make_spot_key(position, stack, scenario)
st.session_state.current_spot_key = spot_key
st.markdown(f"*Clé du spot :* `{spot_key}`")

# Récupération / création du spot courant
current_spot = st.session_state.spots.get(
    spot_key,
    {
        "position": position,
        "stack": stack,
        "scenario": scenario,
        "hand_actions": {},  # hand_code -> set(actions)
    },
)
hand_actions = current_spot["hand_actions"]

if st.button("💾 Enregistrer cette range (ce spot)"):
    st.session_state.spots[spot_key] = current_spot
    st.success(f"Range enregistrée pour {spot_key}. Tu peux passer à une autre.")

# -----------------------------
# Choix de l'action active
# -----------------------------
st.subheader("🖱️ Action en cours")

action_names = ACTIONS + ["effacer"]


def format_action(a):
    if a == "effacer":
        return "❌ Effacer"
    return f"{ACTION_EMOJI[a]} {ACTION_LABELS[a]}"


current_action = st.radio(
    "Cliquer sur la grille appliquera / enlèvera cette action pour la main choisie :",
    options=action_names,
    index=0,
    format_func=format_action,
    horizontal=True,
)
st.session_state.current_action = current_action

if st.button("🧹 Effacer toutes les mains de ce spot"):
    hand_actions.clear()
    st.success("Toutes les mains de ce spot ont été effacées.")

# -----------------------------
# Grille 13x13
# -----------------------------
st.subheader("🧩 Grille des mains")

# En-tête colonnes
header_cols = st.columns(len(RANKS) + 1)
header_cols[0].markdown(" ")
for j, r2 in enumerate(RANKS):
    header_cols[j + 1].markdown(
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
        hand_code = canonical_hand_from_indices(i, j)
        acts = hand_actions.get(hand_code, set())
        if not acts:
            prefix = EMPTY_EMOJI
        else:
            prefix = "".join(
                ACTION_EMOJI[a] for a in sorted(acts) if a in ACTION_EMOJI
            )
        label = f"{prefix} {hand_code}"

        cols[j + 1].button(
            label,
            key=f"{spot_key}_{hand_code}",
            on_click=update_hand_action,
            args=(spot_key, hand_code),
        )

# remettre le spot modifié en session
current_spot["hand_actions"] = st.session_state.spots.get(spot_key, current_spot)[
    "hand_actions"
]
st.session_state.spots[spot_key] = current_spot

# -----------------------------
# Aperçu des spots existants + stats %
# -----------------------------
st.markdown("---")
st.subheader("📚 Spots actuellement définis")

TOTAL_HANDS = len(ALL_HANDS)  # 169

if not st.session_state.spots:
    st.info("Aucun spot encore enregistré dans la session.")
else:
    for key, spot in sorted(st.session_state.spots.items()):
        pos = spot["position"]
        stck = spot["stack"]
        scen = spot["scenario"]
        ha = spot.get("hand_actions", {})
        counts = defaultdict(int)

        # compter les actions (mains non marquées -> fold)
        for h in ALL_HANDS:
            acts = ha.get(h, set())
            if not acts:
                counts["fold"] += 1
            else:
                for act in acts:
                    if act in ACTIONS:
                        counts[act] += 1

        # % open = open + open_shove
        open_like = counts["open"] + counts["open_shove"]
        threebet_like = counts["threebet"] + counts["threebet_shove"]

        open_pct = (open_like / TOTAL_HANDS * 100.0)
        threebet_pct = (threebet_like / TOTAL_HANDS * 100.0)

        st.markdown(f"**{key}** – {pos}, {stck} BB, scénario `{scen}`")
        st.markdown(
            f"- {ACTION_EMOJI['open']} Open (incl. shove) : {open_like} mains, soit **{open_pct:.1f}%**\n"
            f"- {ACTION_EMOJI['threebet']} 3-bet (incl. shove) : {threebet_like} mains, soit **{threebet_pct:.1f}%**\n"
            f"- {ACTION_EMOJI['call']} Call : {counts['call']} mains\n"
            f"- {ACTION_EMOJI['fold']} Fold : {counts['fold']} mains"
        )
