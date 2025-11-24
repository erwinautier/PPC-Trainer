#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Nov 24 13:57:13 2025

@author: erwinautier
"""

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
SCENARIOS = ["open"]  # on pourra plus tard ajouter "bb_vs_open", etc.

# Génération de toutes les mains de type AA, AKs, AKo, ...
def generate_all_hands():
    hands = set()
    # Paires
    for r in RANKS:
        hands.add(r + r)
    # Suited et Offsuited
    for i, r1 in enumerate(RANKS):
        for r2 in RANKS[i + 1 :]:
            hands.add(r1 + r2 + "s")
            hands.add(r1 + r2 + "o")
    return hands

ALL_HANDS = generate_all_hands()


def parse_hand_list(text: str):
    """
    Parse une liste de mains séparées par virgules ou retours à la ligne.
    Ne garde que les mains valides (AA, AKs, AKo, ...).
    Retourne (liste_valides, liste_invalides).
    """
    raw = text.replace("\n", ",").split(",")
    items = [h.strip().upper() for h in raw if h.strip()]
    valid = [h for h in items if h in ALL_HANDS]
    invalid = [h for h in items if h not in ALL_HANDS]
    return sorted(set(valid)), sorted(set(invalid))


def make_spot_key(position: str, stack: int, scenario: str) -> str:
    return f"{position}_{stack}_{scenario}"


# -----------------------------
# Config Streamlit
# -----------------------------
st.set_page_config(
    page_title="Éditeur de ranges",
    page_icon="🧮",
    layout="wide",
)

st.title("🧮 Éditeur de ranges préflop")

st.markdown(
    """
Cette application te permet de **créer / éditer** tes propres ranges et de les
**exporter en fichier JSON**.  
Ce fichier pourra ensuite être utilisé par ton *Poker Trainer* pour afficher une *correction*.
"""
)

# -----------------------------
# État en session
# -----------------------------
if "ranges" not in st.session_state:
    # ranges : dict[spot_key] -> dict{"position","stack","scenario","actions":{...}}
    st.session_state.ranges = {}

# -----------------------------
# Sidebar : chargement / sauvegarde
# -----------------------------
st.sidebar.header("Fichiers de ranges")

uploaded = st.sidebar.file_uploader("Charger un fichier de ranges (.json)", type=["json"])
if uploaded is not None:
    try:
        data = json.load(uploaded)
        spots = data.get("spots", {})
        if isinstance(spots, dict):
            st.session_state.ranges = spots
            st.sidebar.success("Fichier de ranges chargé avec succès ✅")
        else:
            st.sidebar.error("Format JSON inattendu : champ 'spots' absent ou incorrect.")
    except Exception as e:
        st.sidebar.error(f"Erreur de lecture du fichier : {e}")

# Bouton pour réinitialiser tout
if st.sidebar.button("🗑️ Effacer toutes les ranges de la session"):
    st.session_state.ranges = {}
    st.sidebar.success("Toutes les ranges ont été effacées (dans la session).")

# Génération du JSON pour téléchargement
export_data = {
    "version": 1,
    "spots": st.session_state.ranges,
}
export_json = json.dumps(export_data, indent=2)

st.sidebar.download_button(
    label="💾 Télécharger le fichier de ranges",
    data=export_json,
    file_name="ranges_poker_trainer.json",
    mime="application/json",
)

st.sidebar.markdown(
    """
Format des mains attendu : `AA`, `KK`, `AKs`, `AQo`, `T9s`, etc.  
Pas de raccourcis `22+`, `A2s+` pour l'instant.
"""
)

# -----------------------------
# Paramètres du spot en cours d'édition
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
st.markdown(f"*Clé du spot :* `{spot_key}`")

# Récupération ou création du spot
current_spot = st.session_state.ranges.get(
    spot_key,
    {
        "position": position,
        "stack": stack,
        "scenario": scenario,
        "actions": {
            "open": [],
            "call": [],
            "threebet": [],
            "fold": [],
        },
    },
)
actions = current_spot["actions"]

# -----------------------------
# Saisie des mains par action
# -----------------------------
st.subheader("✏️ Édition des mains pour ce spot")

st.markdown(
    """
Entre les mains dans chaque zone, séparées par des virgules ou des retours à la ligne.  
Exemple : `AA, KK, QQ, AKs, AKo, KQs`
"""
)

tab_open, tab_call, tab_3bet, tab_fold = st.tabs(["Open", "Call", "3-bet", "Fold"])

def hands_to_text(hands_list):
    return ", ".join(hands_list)

with tab_open:
    open_text = st.text_area("Mains qui **ouvrent** (open)", value=hands_to_text(actions.get("open", [])), height=120)
with tab_call:
    call_text = st.text_area("Mains qui **call**", value=hands_to_text(actions.get("call", [])), height=120)
with tab_3bet:
    threebet_text = st.text_area("Mains qui **3-bet**", value=hands_to_text(actions.get("threebet", [])), height=120)
with tab_fold:
    fold_text = st.text_area("Mains qui **foldent**", value=hands_to_text(actions.get("fold", [])), height=120)

# Bouton d'analyse / mise à jour
if st.button("✅ Enregistrer ce spot dans la session"):
    open_valid, open_invalid = parse_hand_list(open_text)
    call_valid, call_invalid = parse_hand_list(call_text)
    threebet_valid, threebet_invalid = parse_hand_list(threebet_text)
    fold_valid, fold_invalid = parse_hand_list(fold_text)

    # On pourrait, si on veut, forcer une main à n'appartenir qu'à une seule catégorie,
    # mais pour l'instant on laisse la responsabilité à l'utilisateur.
    current_spot["actions"]["open"] = open_valid
    current_spot["actions"]["call"] = call_valid
    current_spot["actions"]["threebet"] = threebet_valid
    current_spot["actions"]["fold"] = fold_valid

    st.session_state.ranges[spot_key] = current_spot

    st.success("Spot enregistré dans la session ✅")

    # Feedback sur les mains invalides
    invalid_all = {
        "open": open_invalid,
        "call": call_invalid,
        "3-bet": threebet_invalid,
        "fold": fold_invalid,
    }
    for action_name, inv in invalid_all.items():
        if inv:
            st.warning(f"Mains non reconnues pour {action_name} : {', '.join(inv)}")

# -----------------------------
# Aperçu des spots existants
# -----------------------------
st.markdown("---")
st.subheader("📚 Spots actuellement définis")

if not st.session_state.ranges:
    st.info("Aucun spot encore enregistré dans la session.")
else:
    for key, spot in sorted(st.session_state.ranges.items()):
        pos = spot["position"]
        stck = spot["stack"]
        scen = spot["scenario"]
        acts = spot["actions"]
        st.markdown(f"**{key}** – {pos}, {stck} BB, scénario `{scen}`")
        st.markdown(
            f"- Open : {len(acts.get('open', []))} mains\n"
            f"- Call : {len(acts.get('call', []))} mains\n"
            f"- 3-bet : {len(acts.get('threebet', []))} mains\n"
            f"- Fold : {len(acts.get('fold', []))} mains"
        )
