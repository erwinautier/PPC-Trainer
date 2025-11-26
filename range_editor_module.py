# range_editor_module.py

import os
import sys
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
    "open_shove": "🟣",
    "threebet_shove": "⚫",
    "fold": "❌",  # pour l'affichage des stats
}
EMPTY_EMOJI = "⬜"


# -----------------------------
# Utilitaires fichier
# -----------------------------
def base_dir():
    """Dossier racine de l'appli (compatible exécutable)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def user_ranges_path(username: str) -> str:
    """Chemin du fichier de ranges perso pour un utilisateur."""
    safe = "".join(c for c in username if c.isalnum() or c in ("_", "-"))
    return os.path.join(base_dir(), f"ranges_{safe}.json")


def default_ranges_path() -> str:
    """Chemin éventuel d'un fichier de ranges par défaut global."""
    return os.path.join(base_dir(), "default_ranges.json")


def make_spot_key(table_type: str, position: str, stack: int, scenario: str) -> str:
    """ID de spot incluant le format (6-max/8-max)."""
    return f"{table_type}_{position}_{stack}_{scenario}"


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


def hand_weight(hand: str) -> int:
    """
    Renvoie le nombre de combos pour une main donnée :
    - Paires (AA, KK, ...) : 6 combos
    - Suited (AKs, QJs, ...) : 4 combos
    - Offsuit (AKo, QJo, ...) : 12 combos
    """
    hand = hand.strip().upper()
    if len(hand) == 2:
        return 6
    if len(hand) == 3:
        if hand.endswith("S"):
            return 4
        if hand.endswith("O"):
            return 12
    return 0  # cas anormal, au pire on ne compte pas


def all_hands_set():
    hands = set()
    for i in range(len(RANKS)):
        for j in range(len(RANKS)):
            hands.add(canonical_hand_from_indices(i, j))
    return hands


ALL_HANDS = all_hands_set()


# -----------------------------
# Conversion depuis un JSON exporté
# -----------------------------
def spots_from_exported_data(data: dict) -> dict:
    """
    Convertit un JSON de ranges exporté en structure interne :
    spot_key -> { table_type, position, stack, scenario, hand_actions:{hand:set(actions)} }

    On accepte deux formats :
    1) {"version":2, "spots":{...}}
    2) {"spot_key1": {...}, "spot_key2": {...}} (sans clé "spots")
    """
    # Cas 1 : format avec clé "spots"
    if "spots" in data and isinstance(data["spots"], dict):
        spots_json = data["spots"]
    else:
        # Cas 2 : on suppose que data EST directement le dict de spots
        # (on vérifie grossièrement que les valeurs ressemblent à des spots)
        if any(isinstance(v, dict) and "position" in v for v in data.values()):
            spots_json = data
        else:
            # Format inconnu
            return {}

    new_spots = {}
    for old_key, spot in spots_json.items():
        pos = spot.get("position")
        stack = spot.get("stack")
        scen = spot.get("scenario", "open")
        table_type = spot.get("table_type", "6-max")  # défaut
        actions = spot.get("actions", {})
        hand_actions = {}
        for act_name in ACTIONS:
            for h in actions.get(act_name, []):
                if h in ALL_HANDS:
                    hand_actions.setdefault(h, set()).add(act_name)
        new_key = make_spot_key(table_type, pos, stack, scen)
        new_spots[new_key] = {
            "table_type": table_type,
            "position": pos,
            "stack": stack,
            "scenario": scen,
            "hand_actions": hand_actions,
        }
    return new_spots


# -----------------------------
# Callback pour un clic sur une main
# -----------------------------
def update_hand_action(spot_key: str, hand_code: str):
    """Callback appelé quand on clique sur un bouton de la grille."""
    spots = st.session_state.spots

    # table_type, position, stack, scenario
    table_type, position, stack_str, scenario = spot_key.split("_", 3)
    stack = int(stack_str)

    spot = spots.get(
        spot_key,
        {
            "table_type": table_type,
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

    # 🔁 IMPORTANT : on relance immédiatement le script
    st.rerun()


# =========================================================
#  FONCTION PRINCIPALE APPELÉE PAR app.py
# =========================================================
def run_range_editor(username: str):
    """
    Module d'édition de ranges.
    À appeler depuis app.py avec : run_range_editor(username)
    """

    # -----------------------------------------------------
    # Bandeau d'en-tête
    # -----------------------------------------------------
    st.markdown(f"*Éditeur de ranges – profil **{username}***")
    st.markdown("### 🧮 Éditeur de ranges préflop – mode grille cliquable")

    st.markdown(
        """
- **Choisis 6-max ou 8-max**, puis la position, le stack et le scénario.  
- **Clique** sur les cases pour affecter des actions (Open / Call / 3-bet / Open shove / 3-bet shove).  
- Une case peut avoir **plusieurs actions** (mix).  
- Toute case **non cochée** sera considérée comme **Fold** par défaut dans le fichier exporté.  
- Tu peux créer **une liste de ranges** (spots) : un spot = Format + Position + Stack + Scénario.
"""
    )

    # -----------------------------------------------------
    # État en session
    # -----------------------------------------------------
    if "range_editor_user" not in st.session_state:
        st.session_state.range_editor_user = username
    elif st.session_state.range_editor_user != username:
        st.session_state.range_editor_user = username
        st.session_state.spots = {}

    # Chargement initial depuis ranges_{username}.json (une seule fois)
    if "spots" not in st.session_state:
        st.session_state.spots = {}
        user_path = user_ranges_path(username)
        if os.path.exists(user_path):
            try:
                with open(user_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                new_spots = spots_from_exported_data(data)
                st.session_state.spots = new_spots
                if new_spots:
                    st.info(f"Ranges perso chargées : {len(new_spots)} spots trouvés.")
                    # Se placer sur le premier spot disponible
                    first_key = sorted(new_spots.keys())[0]
                    t, p, s_str, scen = first_key.split("_", 4)
                    st.session_state.table_type = t
                    st.session_state.scenario = scen
                    st.session_state.current_spot_key = first_key
            except Exception as e:
                st.warning(f"Impossible de charger les ranges perso : {e}")

    if "current_spot_key" not in st.session_state:
        st.session_state.current_spot_key = None
    if "current_action" not in st.session_state:
        st.session_state.current_action = "open"
    if "table_type" not in st.session_state:
        st.session_state.table_type = "6-max"
    if "scenario" not in st.session_state:
        st.session_state.scenario = "open"

    # -----------------------------------------------------
    # Sidebar : chargement / sauvegarde
    # -----------------------------------------------------
    st.sidebar.header("Fichiers de ranges")

    uploaded = st.sidebar.file_uploader(
        "Charger un fichier de ranges (.json)", type=["json"]
    )
    if uploaded is not None:
        try:
            data = json.load(uploaded)
            new_spots = spots_from_exported_data(data)
            if not new_spots:
                st.sidebar.error(
                    "Fichier lu mais aucun spot reconnu. "
                    "Vérifie qu'il contient bien un objet 'spots' ou des clés de spots."
                )
            else:
                st.session_state.spots = new_spots
                # Se placer sur le premier spot importé
                first_key = sorted(new_spots.keys())[0]
                t, p, s_str, scen = first_key.split("_", 4)
                st.session_state.table_type = t
                st.session_state.scenario = scen
                st.session_state.current_spot_key = first_key
                st.sidebar.success(
                    f"Fichier de ranges chargé avec succès ✅ ({len(new_spots)} spots)"
                )
                st.rerun()
        except Exception as e:
            st.sidebar.error(f"Erreur de lecture du fichier : {e}")

    if st.sidebar.button("🗑️ Effacer toutes les ranges de la session"):
        st.session_state.spots = {}
        st.session_state.current_spot_key = None
        st.sidebar.success("Toutes les ranges ont été effacées (dans la session).")

    # Préparation export JSON (cases vides -> fold)
    export_spots = {}
    for key, spot in st.session_state.spots.items():
        table_type = spot.get("table_type", "6-max")
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
            "table_type": table_type,
            "position": pos,
            "stack": stack,
            "scenario": scen,
            "actions": {
                act: sorted(hands) for act, hands in actions_dict.items()
            },
        }

    export_data = {"version": 2, "spots": export_spots}
    export_json = json.dumps(export_data, indent=2)

    # Sauvegarde automatique dans ranges_{username}.json
    user_path = user_ranges_path(username)
    try:
        with open(user_path, "w", encoding="utf-8") as f:
            f.write(export_json)
    except Exception as e:
        st.sidebar.warning(f"Impossible de sauvegarder le fichier utilisateur : {e}")

    st.sidebar.download_button(
        label="💾 Télécharger le fichier de ranges",
        data=export_json,
        file_name="ranges_poker_trainer.json",
        mime="application/json",
    )

    # -----------------------------------------------------
    # Format de table & sélection du spot
    # -----------------------------------------------------
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

    spot_key = make_spot_key(table_type, position, stack, scenario)
    st.session_state.current_spot_key = spot_key
    st.markdown(f"*Clé du spot :* `{spot_key}`")

    # Récupération / création du spot courant
    current_spot = st.session_state.spots.get(
        spot_key,
        {
            "table_type": table_type,
            "position": position,
            "stack": stack,
            "scenario": scenario,
            "hand_actions": {},  # hand_code -> set(actions)
        },
    )
    hand_actions = current_spot["hand_actions"]

    # -----------------------------------------------------
    # Copie d'un spot vers le spot courant
    # -----------------------------------------------------
    st.markdown("#### 📋 Copier une range existante vers ce spot")

    existing_keys = sorted(st.session_state.spots.keys())
    copy_options = ["(Aucune)"] + existing_keys

    copy_from_key = st.selectbox(
        "Copier depuis le spot :", copy_options, index=0, key="copy_from_key"
    )

    if st.button("📥 Copier cette range dans le spot courant"):
        if copy_from_key != "(Aucune)" and copy_from_key in st.session_state.spots:
            src_spot = st.session_state.spots[copy_from_key]
            src_actions = src_spot.get("hand_actions", {})
            hand_actions = {h: set(acts) for h, acts in src_actions.items()}
            current_spot["hand_actions"] = hand_actions
            st.session_state.spots[spot_key] = current_spot
            st.success(f"Range copiée depuis {copy_from_key} vers {spot_key}.")
        else:
            st.info("Choisis un spot de départ pour copier sa range.")

    # Bouton d'enregistrement explicite du spot courant
    if st.button("💾 Enregistrer cette range (ce spot)"):
        current_spot["hand_actions"] = hand_actions
        st.session_state.spots[spot_key] = current_spot
        st.success(f"Range enregistrée pour {spot_key}. Tu peux passer à une autre.")

    # -----------------------------------------------------
    # Choix de l'action active
    # -----------------------------------------------------
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

    # -----------------------------------------------------
    # Grille 13x13
    # -----------------------------------------------------
    st.subheader("🧩 Grille des mains")

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

    current_spot["hand_actions"] = st.session_state.spots.get(spot_key, current_spot)[
        "hand_actions"
    ]
    current_spot["table_type"] = table_type
    current_spot["position"] = position
    current_spot["stack"] = stack
    current_spot["scenario"] = scenario
    st.session_state.spots[spot_key] = current_spot

    # -----------------------------------------------------
    # Aperçu des stats (pour un spot choisi, pondéré en combos)
    # -----------------------------------------------------
    st.markdown("---")
    st.subheader("📊 Statistiques d'un spot (pondérées en combos)")

    TOTAL_COMBOS = sum(hand_weight(h) for h in ALL_HANDS)

    if not st.session_state.spots:
        st.info("Aucun spot encore enregistré dans la session.")
    else:
        stats_options = ["Spot courant"] + sorted(st.session_state.spots.keys())
        selected_stats_key = st.selectbox(
            "Choisir le spot pour afficher les statistiques :",
            stats_options,
            index=0,
        )

        if selected_stats_key == "Spot courant":
            stats_key = spot_key
        else:
            stats_key = selected_stats_key

        spot = st.session_state.spots.get(stats_key, current_spot)
        table_type_stats = spot.get("table_type", "6-max")
        pos = spot["position"]
        stck = spot["stack"]
        scen = spot["scenario"]
        ha = spot.get("hand_actions", {})

        combo_counts = defaultdict(int)

        for h in ALL_HANDS:
            w = hand_weight(h)
            acts = ha.get(h, set())
            if not acts:
                combo_counts["fold"] += w
            else:
                if "open" in acts or "open_shove" in acts:
                    combo_counts["open_like"] += w
                if "threebet" in acts or "threebet_shove" in acts:
                    combo_counts["threebet_like"] += w
                if "call" in acts:
                    combo_counts["call"] += w

        open_like = combo_counts["open_like"]
        threebet_like = combo_counts["threebet_like"]
        call_combos = combo_counts["call"]
        fold_combos = combo_counts["fold"]

        open_pct = open_like / TOTAL_COMBOS * 100.0
        threebet_pct = threebet_like / TOTAL_COMBOS * 100.0
        call_pct = call_combos / TOTAL_COMBOS * 100.0
        fold_pct = fold_combos / TOTAL_COMBOS * 100.0

        st.markdown(
            f"**Spot :** `{stats_key}`  \n"
            f"Format : **{table_type_stats}**, Position : **{pos}**, "
            f"Stack : **{stck} BB**, Scénario : `{scen}`"
        )
        st.markdown(
            f"- {ACTION_EMOJI['open']} Open (incl. shove) : {open_like} combos, "
            f"soit **{open_pct:.1f}%** des 1326 combos\n"
            f"- {ACTION_EMOJI['threebet']} 3-bet (incl. shove) : {threebet_like} combos, "
            f"soit **{threebet_pct:.1f}%**\n"
            f"- {ACTION_EMOJI['call']} Call : {call_combos} combos, "
            f"soit **{call_pct:.1f}%**\n"
            f"- {ACTION_EMOJI['fold']} Fold : {fold_combos} combos, "
            f"soit **{fold_pct:.1f}%**"
        )
