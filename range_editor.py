# ranges_editor.py
import os
import json
from collections import defaultdict

import streamlit as st

# -----------------------------
# Constantes poker
# -----------------------------
RANKS = ["A", "K", "Q", "J", "T", "9", "8", "7", "6", "5", "4", "3", "2"]
POSITIONS = ["LJ", "HJ", "CO", "BTN", "SB", "BB"]
STACKS = [100, 50, 25, 20, 19, 18, 17, 16, 15, 14, 13, 12, 11, 10]
SCENARIOS = ["open"]  # on pourra étendre plus tard

ACTIONS = ["open", "call", "threebet", "fold"]
ACTION_LABELS = {
    "open": "Open",
    "call": "Call",
    "threebet": "3-bet",
    "fold": "Fold",
}
# Couleurs via emojis (simple & fiable dans Streamlit)
ACTION_SYMBOLS = {
    None: "⬜",       # vide / aucune action
    "open": "🟢",     # vert
    "call": "🟡",     # jaune
    "threebet": "🔴", # rouge
    "fold": "🔵",     # bleu
}

# -----------------------------
# Utilitaires
# -----------------------------
def base_dir():
    return os.path.dirname(os.path.abspath(__file__))


def make_spot_key(position: str, stack: int, scenario: str) -> str:
    return f"{position}_{stack}_{scenario}"


def canonical_hand_from_indices(i: int, j: int) -> str:
    """
    Convertit indices (ligne, colonne) de la matrice 13x13 en main canonique :
    - diagonale : paires (AA, KK, QQ, ...)
    - triangle supérieur : offsuited (AKo, AKo, ...)
    - triangle inférieur : suited (AKs, KQs, ...)
    La convention classique : triangle supérieur = offsuit, inférieur = suited.
    """
    r1 = RANKS[i]
    r2 = RANKS[j]
    if i == j:
        return r1 + r2  # paire
    # on met toujours la plus forte carte en premier dans le code
    idx1 = RANKS.index(r1)
    idx2 = RANKS.index(r2)
    if idx1 < idx2:
        hi, lo = r1, r2
    else:
        hi, lo = r2, r1
    if i < j:
        # triangle supérieur : offsuit
        return hi + lo + "o"
    else:
        # triangle inférieur : suited
        return hi + lo + "s"


def all_hands_set():
    hands = set()
    for i in range(len(RANKS)):
        for j in range(len(RANKS)):
            hands.add(canonical_hand_from_indices(i, j))
    return hands


ALL_HANDS = all_hands_set()


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
Clique sur les cases de la grille pour associer chaque main à une action **Open / Call / 3-bet / Fold**.  
Tu peux ensuite **télécharger** un fichier JSON compatible avec le Poker Trainer.
"""
)

# -----------------------------
# État en session
# -----------------------------
if "spots" not in st.session_state:
    # spots : dict[spot_key] -> {"position","stack","scenario","hand_actions": {hand: action}}
    st.session_state.spots = {}

if "current_spot_key" not in st.session_state:
    st.session_state.current_spot_key = None

if "current_action" not in st.session_state:
    st.session_state.current_action = "open"

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
                        hand_actions[h] = act_name
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

# Bouton pour tout effacer (dans la session)
if st.sidebar.button("🗑️ Effacer toutes les ranges de la session"):
    st.session_state.spots = {}
    st.sidebar.success("Toutes les ranges ont été effacées (dans la session).")

# Préparation export JSON au format ancien (actions -> listes de mains)
export_spots = {}
for key, spot in st.session_state.spots.items():
    pos = spot["position"]
    stack = spot["stack"]
    scen = spot["scenario"]
    hand_actions = spot.get("hand_actions", {})
    actions_dict = defaultdict(list)
    for hand, act in hand_actions.items():
        if act in ACTIONS:
            actions_dict[act].append(hand)
    export_spots[key] = {
        "position": pos,
        "stack": stack,
        "scenario": scen,
        "actions": {
            act: sorted(hands) for act, hands in actions_dict.items()
        },
    }

export_data = {
    "version": 1,
    "spots": export_spots,
}
export_json = json.dumps(export_data, indent=2)

st.sidebar.download_button(
    label="💾 Télécharger le fichier de ranges",
    data=export_json,
    file_name="ranges_poker_trainer.json",
    mime="application/json",
)

# -----------------------------
# Sélection du spot
# -----------------------------
st.subheader("🎯 Sélection du spot à éditer")

col_sel1, col_sel2, col_sel3 = st.columns(3)
with col_sel1:
    position = st.selectbox("Position", POSITIONS, index=0)
with col_sel2:
    stack = st.selectbox("Stack (BB)", STACKS, index=0)
with col_sel3:
    scenario = st.selectbox("Scénario", SCENARIOS, index=0)

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
        "hand_actions": {},  # hand_code -> action
    },
)
hand_actions = current_spot["hand_actions"]

# -----------------------------
# Choix de l'action active
# -----------------------------
st.subheader("🖱️ Action en cours")

action_names = ACTIONS + ["effacer"]
def format_action(a):
    if a == "effacer":
        return "❌ Effacer"
    return f"{ACTION_SYMBOLS[a]} {ACTION_LABELS[a]}"

current_action = st.radio(
    "Cliquer sur la grille appliquera cette action à la main choisie :",
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
st.subheader("🧩 Grille des mains (cliquer pour changer l'action)")

# Ligne d'en-tête des colonnes
header_cols = st.columns(len(RANKS) + 1)
header_cols[0].markdown(" ")
for j, r2 in enumerate(RANKS):
    header_cols[j + 1].markdown(f"<div style='text-align:center;'><b>{r2}</b></div>", unsafe_allow_html=True)

for i, r1 in enumerate(RANKS):
    cols = st.columns(len(RANKS) + 1)
    # En-tête de ligne
    cols[0].markdown(f"<div style='text-align:center;'><b>{r1}</b></div>", unsafe_allow_html=True)
    for j, r2 in enumerate(RANKS):
        hand_code = canonical_hand_from_indices(i, j)
        act = hand_actions.get(hand_code, None)
        symbol = ACTION_SYMBOLS.get(act, "⬜")
        # On affiche juste le symbole coloré sur le bouton
        if cols[j + 1].button(symbol, key=f"{spot_key}_{hand_code}"):
            if st.session_state.current_action == "effacer":
                if hand_code in hand_actions:
                    del hand_actions[hand_code]
            else:
                hand_actions[hand_code] = st.session_state.current_action

# On remet le spot modifié dans la session
current_spot["hand_actions"] = hand_actions
st.session_state.spots[spot_key] = current_spot

# -----------------------------
# Aperçu des spots existants
# -----------------------------
st.markdown("---")
st.subheader("📚 Spots actuellement définis")

if not st.session_state.spots:
    st.info("Aucun spot encore enregistré dans la session.")
else:
    for key, spot in sorted(st.session_state.spots.items()):
        pos = spot["position"]
        stck = spot["stack"]
        scen = spot["scenario"]
        ha = spot.get("hand_actions", {})
        counts = defaultdict(int)
        for act in ha.values():
            if act in ACTIONS:
                counts[act] += 1
        st.markdown(f"**{key}** – {pos}, {stck} BB, scénario `{scen}`")
        st.markdown(
            f"- {ACTION_SYMBOLS['open']} Open : {counts['open']} mains\n"
            f"- {ACTION_SYMBOLS['call']} Call : {counts['call']} mains\n"
            f"- {ACTION_SYMBOLS['threebet']} 3-bet : {counts['threebet']} mains\n"
            f"- {ACTION_SYMBOLS['fold']} Fold : {counts['fold']} mains"
        )

