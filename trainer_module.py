# trainer_module.py

import os
import sys
import json
import random
from collections import defaultdict

import streamlit as st

# =========================================================
#  Constantes & utilitaires communs
# =========================================================

RANKS = ["A", "K", "Q", "J", "T", "9", "8", "7", "6", "5", "4", "3", "2"]

POSITIONS_6MAX = ["LJ", "HJ", "CO", "BTN", "SB", "BB"]
POSITIONS_8MAX = ["UTG", "UTG+1", "LJ", "HJ", "CO", "BTN", "SB", "BB"]

STACKS = [100, 50, 25, 20, 19, 18, 17, 16, 15, 14, 13, 12, 11, 10]

ACTIONS = ["fold", "open", "call", "threebet", "open_shove", "threebet_shove"]
ACTION_LABELS = {
    "fold": "Fold",
    "open": "Open",
    "call": "Call",
    "threebet": "3-bet",
    "open_shove": "Open shove",
    "threebet_shove": "3-bet shove",
}
ACTION_COLORS = {
    "fold": "#FFFFFF",          # fond blanc
    "open": "#16A34A",          # vert
    "call": "#FBBF24",          # jaune/orangé
    "threebet": "#EF4444",      # rouge
    "open_shove": "#8B5CF6",    # violet
    "threebet_shove": "#111827" # noir
}
# mêmes icônes que dans le range_editor
ACTION_EMOJI = {
    "open": "🟢",
    "call": "🟡",
    "threebet": "🔴",
    "open_shove": "🟣",
    "threebet_shove": "⚫",
    "fold": "❌",
}


def base_dir():
    """Dossier racine (compatible exécutable)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def user_ranges_path(username: str) -> str:
    """Chemin du fichier de ranges perso pour un utilisateur."""
    safe = "".join(c for c in username if c.isalnum() or c in ("_", "-"))
    return os.path.join(base_dir(), f"ranges_{safe}.json")


def default_ranges_path() -> str:
    """Chemin du fichier de ranges par défaut."""
    return os.path.join(base_dir(), "default_ranges.json")


def trainer_stats_path(username: str) -> str:
    """Chemin du fichier de stats / Leitner pour le trainer."""
    safe = "".join(c for c in username if c.isalnum() or c in ("_", "-"))
    return os.path.join(base_dir(), f"trainer_stats_{safe}.json")


def canonical_hand_from_indices(i: int, j: int) -> str:
    """
    Convention identique à l'éditeur :
    - diagonale : paires (AA, KK, ...)
    - triangle supérieur : suited (AKs, AQs, ...)
    - triangle inférieur : offsuit (AKo, AQo, ...)
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
        return hi + lo + "s"
    else:
        return hi + lo + "o"


# Ensemble de toutes les mains canoniques de la grille
ALL_HANDS = {
    canonical_hand_from_indices(i, j)
    for i in range(len(RANKS))
    for j in range(len(RANKS))
}

# Coordonnées (i, j) associées à chaque main canonique
HAND_TO_COORD = {}
for i in range(len(RANKS)):
    for j in range(len(RANKS)):
        h = canonical_hand_from_indices(i, j)
        HAND_TO_COORD[h] = (i, j)


# =========================================================
#  Chargement des ranges (défaut + perso)
# =========================================================

def load_ranges_file(path: str) -> dict:
    """
    Charge un fichier de ranges au format {version, spots}
    ou retourne {"version": 2, "spots": {}} en cas de souci.
    """
    if not os.path.exists(path):
        return {"version": 2, "spots": {}}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "spots" in data and isinstance(data["spots"], dict):
            return data
        # Cas rare : data est directement le dict de spots
        if isinstance(data, dict) and any(
            isinstance(v, dict) and "position" in v for v in data.values()
        ):
            return {"version": 2, "spots": data}
    except Exception:
        pass
    return {"version": 2, "spots": {}}


# =========================================================
#  Stats / Leitner simplifié
# =========================================================

def load_trainer_stats(username: str) -> dict:
    """
    Charge les stats du trainer. Format :
    {
      "spots": {
        spot_key: {"success": int, "fail": int}
      },
      "total": {"success": int, "fail": int}
    }
    """
    path = trainer_stats_path(username)
    if not os.path.exists(path):
        return {"spots": {}, "total": {"success": 0, "fail": 0}}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "spots" in data and "total" in data:
            return data
    except Exception:
        pass
    return {"spots": {}, "total": {"success": 0, "fail": 0}}


def save_trainer_stats(username: str, stats: dict):
    path = trainer_stats_path(username)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2)
    except Exception:
        pass


def update_stats(stats: dict, spot_key: str, success: bool):
    spots = stats.setdefault("spots", {})
    s = spots.setdefault(spot_key, {"success": 0, "fail": 0})
    if success:
        s["success"] += 1
        stats["total"]["success"] += 1
    else:
        s["fail"] += 1
        stats["total"]["fail"] += 1


def get_spot_weight(stats: dict, spot_key: str) -> float:
    """
    Donne un poids pour un spot : plus il y a d'erreurs, plus le poids augmente.
    Simple approximation type Leitner.
    """
    s = stats.get("spots", {}).get(spot_key, {"success": 0, "fail": 0})
    fail = s.get("fail", 0)
    success = s.get("success", 0)
    w = 1.0 + fail - 0.3 * success
    return max(w, 0.2)


# =========================================================
#  Sélection de mains "proches" de la range qui joue
# =========================================================

def get_candidate_hands_for_spot(actions_for_spot: dict, max_distance: int = 2):
    """
    Renvoie l'ensemble des mains qui peuvent être tirées pour ce spot :
    - toutes les mains avec action ≠ fold
    - + toutes les mains situées à distance <= max_distance
      dans la grille 13x13 de ces mains qui jouent.
    Si aucune main jouée n'est définie, renvoie ALL_HANDS (fallback).
    """
    non_fold_hands = set()
    for act, hands in actions_for_spot.items():
        if act == "fold":
            continue
        for h in hands:
            if h in ALL_HANDS:
                non_fold_hands.add(h)

    if not non_fold_hands:
        return set(ALL_HANDS)

    candidates = set(non_fold_hands)

    for h in ALL_HANDS:
        if h in non_fold_hands:
            continue
        if h not in HAND_TO_COORD:
            continue
        i, j = HAND_TO_COORD[h]
        for played in non_fold_hands:
            pi, pj = HAND_TO_COORD[played]
            if max(abs(i - pi), abs(j - pj)) <= max_distance:
                candidates.add(h)
                break

    return candidates


def draw_hand_for_spot(actions_for_spot: dict) -> str:
    candidates = list(get_candidate_hands_for_spot(actions_for_spot))
    if not candidates:
        candidates = list(ALL_HANDS)
    return random.choice(candidates)


# =========================================================
#  Sélection de spot en fonction filtres + Leitner
# =========================================================

def pick_spot_for_training(
    available_spot_keys,
    pos_choice: str,
    stack_choice_label: str,
    stats: dict,
    table_type_filter=None,
):
    filtered = []
    stack_choice = None
    if stack_choice_label not in (None, "", "Aléatoire"):
        try:
            stack_choice = int(stack_choice_label)
        except ValueError:
            stack_choice = None

    for key in available_spot_keys:
        try:
            ttype, pos, stack_str, scen = key.split("_", 3)
            stack = int(stack_str)
        except Exception:
            continue

        if table_type_filter and ttype != table_type_filter:
            continue
        if pos_choice not in (None, "", "Aléatoire") and pos != pos_choice:
            continue
        if stack_choice is not None and stack != stack_choice:
            continue

        filtered.append(key)

    if not filtered:
        filtered = list(available_spot_keys)

    if not filtered:
        return None

    weights = [get_spot_weight(stats, k) for k in filtered]
    total_w = sum(weights)
    if total_w <= 0:
        return random.choice(filtered)

    r = random.uniform(0, total_w)
    acc = 0.0
    for k, w in zip(filtered, weights):
        acc += w
        if r <= acc:
            return k
    return filtered[-1]


# =========================================================
#  Rendu de la range de correction (grille HTML compacte)
# =========================================================

def render_correction_range_html(actions_for_spot: dict, hero_hand: str = None) -> str:
    """
    Grille 13x13 compacte, avec cellules carrées.
    """
    hand_to_actions = defaultdict(set)
    for act, hands in actions_for_spot.items():
        for h in hands:
            if h in ALL_HANDS:
                hand_to_actions[h].add(act)

    html = []
    html.append(
        "<div style='overflow-x:auto;max-width:100%;'>"
        "<table style='border-collapse:collapse;font-size:9px;"
        "text-align:center;margin:0 auto;table-layout:fixed;'>"
        "<thead><tr><th style='padding:2px 4px;'></th>"
    )
    for r in RANKS:
        html.append(
            f"<th style='padding:2px 4px;text-align:center;'>{r}</th>"
        )
    html.append("</tr></thead><tbody>")

    for i, r1 in enumerate(RANKS):
        html.append("<tr>")
        html.append(
            f"<th style='padding:2px 4px;text-align:center;'>{r1}</th>"
        )
        for j, r2 in enumerate(RANKS):
            hand = canonical_hand_from_indices(i, j)
            acts = hand_to_actions.get(hand, set())

            if not acts:
                color = "#FFFFFF"
            else:
                if len(acts) == 1:
                    act = list(acts)[0]
                    color = ACTION_COLORS.get(act, "#6B7280")
                else:
                    color = "#6B7280"

            highlight_style = ""
            if hero_hand and hand.upper() == hero_hand.upper():
                highlight_style = "background-color:#FF9499;border-radius:4px;"

            cell = (
                f"<td style='padding:1px;width:32px;height:32px;"
                f"text-align:center;{highlight_style}'>"
                "<div style='font-size:8px;line-height:1.1;"
                "display:flex;flex-direction:column;align-items:center;"
                "justify-content:center;height:100%;'>"
                f"<span style='display:inline-block;width:16px;height:16px;"
                f"border-radius:999px;background-color:{color};"
                "border:1px solid #D1D5DB;'></span>"
                f"<span>{hand}</span>"
                "</div></td>"
            )
            html.append(cell)
        html.append("</tr>")
    html.append("</tbody></table></div>")
    return "".join(html)


# =========================================================
#  Affichage "gros" de la main
# =========================================================

def render_hand_big_html(hand: str) -> str:
    hand = hand.upper()
    r1 = hand[0]
    r2 = hand[1]
    suffix = hand[2] if len(hand) == 3 else ""

    suit1 = "♠"
    suit2 = "♥"
    color1 = "#111827"  # noir
    color2 = "#DC2626"  # rouge

    if suffix == "S":
        suit2 = "♠"
        color2 = "#111827"

    return (
        "<div style='font-size:40px;font-weight:600;letter-spacing:1px;'>"
        f"<span style='color:{color1};'>{r1}{suit1}</span>"
        "&nbsp;"
        f"<span style='color:{color2};'>{r2}{suit2}</span>"
        "</div>"
    )


# =========================================================
#  Phrase lisible pour le scénario
# =========================================================

def scenario_to_sentence(table_type: str, position: str, scenario: str) -> str:
    """
    Transforme 'open', 'vs_open_HJ', 'libre', etc. en phrase lisible.
    """
    if scenario == "libre":
        return "Mode libre : situation générique sans range de correction."

    if scenario == "open":
        return f"Personne n'a parlé avant toi : tu es en {position} et tu peux ouvrir le pot."

    if scenario.startswith("vs_open_"):
        vil_pos = scenario.split("_", 2)[2]
        return (
            f"{vil_pos} a open avant toi : tu joues en {position} face à son open."
        )

    return f"Scénario : {scenario}"


# =========================================================
#  Logique principale : tirer une nouvelle main
# =========================================================

def new_spot_and_hand(
    mode: str,
    table_type: str,
    pos_choice: str,
    stack_choice_label: str,
    ranges_source: str,
    default_ranges: dict,
    user_ranges: dict,
    stats: dict,
):
    # ----- Mode libre : pas de ranges -----
    if mode == "Entraînement libre":
        if table_type == "6-max":
            positions = POSITIONS_6MAX
        else:
            positions = POSITIONS_8MAX

        if pos_choice == "Aléatoire":
            position = random.choice(positions)
        else:
            position = pos_choice

        if stack_choice_label == "Aléatoire":
            stack = random.choice(STACKS)
        else:
            try:
                stack = int(stack_choice_label)
            except ValueError:
                stack = random.choice(STACKS)

        hand = random.choice(list(ALL_HANDS))

        return {
            "table_type": table_type,
            "position": position,
            "stack": stack,
            "scenario": "libre",
            "hand": hand,
            "spot_key": None,
            "actions_for_spot": None,
        }

    # ----- Mode avec ranges -----
    if ranges_source == "Ranges personnelles":
        spots = user_ranges.get("spots", {})
        if not spots:
            spots = default_ranges.get("spots", {})
    else:
        spots = default_ranges.get("spots", {})

    if not spots:
        return None

    available_spot_keys = list(spots.keys())

    spot_key = pick_spot_for_training(
        available_spot_keys,
        pos_choice=pos_choice,
        stack_choice_label=stack_choice_label,
        stats=stats,
        table_type_filter=table_type,
    )

    if spot_key is None:
        return None

    spot = spots[spot_key]
    position = spot.get("position")
    stack = spot.get("stack")
    scenario = spot.get("scenario", "open")
    actions_for_spot = spot.get("actions", {})

    hand = draw_hand_for_spot(actions_for_spot)

    return {
        "table_type": table_type,
        "position": position,
        "stack": stack,
        "scenario": scenario,
        "hand": hand,
        "spot_key": spot_key,
        "actions_for_spot": actions_for_spot,
    }


# =========================================================
#  Vérification de la réponse
# =========================================================

def evaluate_answer(hero_action: str, hero_hand: str, actions_for_spot: dict) -> bool:
    if actions_for_spot is None:
        # mode libre : tout est "correct"
        return True

    non_fold_actions = [a for a in actions_for_spot.keys() if a != "fold"]
    non_fold_hands = set()
    for act in non_fold_actions:
        for h in actions_for_spot.get(act, []):
            non_fold_hands.add(h.upper())

    hero_hand_u = hero_hand.upper()

    if hero_action == "fold":
        return hero_hand_u not in non_fold_hands

    allowed_hands = set(
        h.upper() for h in actions_for_spot.get(hero_action, [])
    )
    return hero_hand_u in allowed_hands


# =========================================================
#  Fonction principale appelée par l'app globale
# =========================================================

def run_trainer(username: str):
    # ----------- Initialisation état session -----------
    if "trainer_user" not in st.session_state:
        st.session_state.trainer_user = username
    elif st.session_state.trainer_user != username:
        st.session_state.trainer_user = username
        st.session_state.trainer_stats = load_trainer_stats(username)
        st.session_state.current_spot = None
        st.session_state.last_feedback = None

    if "trainer_stats" not in st.session_state:
        st.session_state.trainer_stats = load_trainer_stats(username)

    if "current_spot" not in st.session_state:
        st.session_state.current_spot = None

    if "last_feedback" not in st.session_state:
        st.session_state.last_feedback = None

    # ----------- Chargement des ranges -----------
    default_ranges = load_ranges_file(default_ranges_path())
    user_ranges = load_ranges_file(user_ranges_path(username))

    st.markdown(f"*Trainer – profil **{username}***")
    st.markdown("### 🧠 Poker Trainer – Ranges & Leitner")

    col_left, col_right = st.columns([1, 2])

    # ===============================
    # Colonne gauche : paramètres
    # ===============================
    with col_left:
        st.subheader("⚙️ Paramètres d'entraînement")

        mode = st.radio(
            "Mode d'entraînement",
            ["Entraînement libre", "Avec ranges de correction"],
            index=1,
            key="trainer_mode",
        )

        table_type = st.radio(
            "Format de table",
            ["6-max", "8-max"],
            index=0,
            horizontal=True,
            key="trainer_table_type",
        )

        if table_type == "6-max":
            positions_list = POSITIONS_6MAX
        else:
            positions_list = POSITIONS_8MAX

        pos_choice = st.selectbox(
            "Position (ou Aléatoire)",
            ["Aléatoire"] + positions_list,
            index=0,
            key="trainer_pos_choice",
        )

        stack_choice_label = st.selectbox(
            "Stack (BB) (ou Aléatoire)",
            ["Aléatoire"] + [str(s) for s in STACKS],
            index=0,
            key="trainer_stack_choice",
        )

        ranges_source = st.radio(
            "Source des ranges (mode correction)",
            ["Ranges par défaut", "Ranges personnelles"],
            index=0,
            key="trainer_ranges_source",
        )

        if mode == "Avec ranges de correction":
            if ranges_source == "Ranges personnelles":
                if not user_ranges.get("spots"):
                    st.warning(
                        "Aucune range personnelle trouvée. "
                        "Les ranges par défaut seront utilisées si disponibles."
                    )
            else:
                if not default_ranges.get("spots"):
                    st.error(
                        "Aucune range par défaut trouvée. "
                        "Le mode 'Avec ranges de correction' ne pourra pas fonctionner."
                    )

        st.markdown("---")
        stats = st.session_state.trainer_stats
        total_s = stats["total"]["success"]
        total_f = stats["total"]["fail"]
        total = total_s + total_f
        acc = (total_s / total * 100.0) if total > 0 else 0.0
        st.markdown(
            f"**Stats globales :**  \n"
            f"- Bonnes réponses : **{total_s}**  \n"
            f"- Mauvaises réponses : **{total_f}**  \n"
            f"- Précision : **{acc:.1f}%**"
        )

    # ===============================
    # Colonne droite : spot + actions
    # ===============================
    with col_right:
        st.subheader("🎯 Spot actuel")

        if st.button("🔁 Nouvelle main"):
            new_spot = new_spot_and_hand(
                mode=mode,
                table_type=table_type,
                pos_choice=pos_choice,
                stack_choice_label=stack_choice_label,
                ranges_source=ranges_source,
                default_ranges=default_ranges,
                user_ranges=user_ranges,
                stats=st.session_state.trainer_stats,
            )
            if new_spot is None:
                st.warning(
                    "Impossible de générer un spot avec les ranges (aucun spot trouvé). "
                    "Tu peux passer en 'Entraînement libre'."
                )
            else:
                st.session_state.current_spot = new_spot
                st.session_state.last_feedback = None

        spot = st.session_state.current_spot

        if not spot:
            st.info("Clique sur **Nouvelle main** pour commencer.")
            return

        table_type_s = spot["table_type"]
        position_s = spot["position"]
        stack_s = spot["stack"]
        scenario_s = spot["scenario"]
        hand_s = spot["hand"]
        spot_key_s = spot.get("spot_key") or "libre"

        # ----- Carte visuelle -----
        card_html = (
            "<div style='background:#F9FAFB;border-radius:20px;"
            "padding:24px 32px;margin:8px 0 12px 0;border:1px solid #E5E7EB;'>"
            "<div style='display:flex;justify-content:space-between;"
            "align-items:center;flex-wrap:wrap;row-gap:4px;font-size:12px;"
            "color:#6B7280;'>"
            "<div>"
            f"Format : <b>{table_type_s}</b><br/>"
            f"Scénario brut : <code>{scenario_s}</code>"
            "</div>"
            "<div style='text-align:right;'>"
            f"Spot : <span style='font-family:monospace;'>{spot_key_s}</span>"
            "</div>"
            "</div>"
            "<div style='margin-top:16px;display:flex;justify-content:space-around;"
            "align-items:center;flex-wrap:wrap;row-gap:16px;'>"
            "<div style='text-align:center;min-width:110px;'>"
            "<div style='font-size:13px;color:#6B7280;'>Position</div>"
            f"<div style='font-size:28px;font-weight:600;color:#111827;'>{position_s}</div>"
            "</div>"
            "<div style='text-align:center;min-width:160px;'>"
            "<div style='font-size:13px;color:#6B7280;'>Main</div>"
            f"{render_hand_big_html(hand_s)}"
            "</div>"
            "<div style='text-align:center;min-width:110px;'>"
            "<div style='font-size:13px;color:#6B7280;'>Stack (BB)</div>"
            f"<div style='font-size:28px;font-weight:600;color:#111827;'>{stack_s}</div>"
            "</div>"
            "</div>"
            "</div>"
        )
        st.markdown(card_html, unsafe_allow_html=True)

        # ----- Phrase de scénario bien visible -----
        scenario_sentence = scenario_to_sentence(table_type_s, position_s, scenario_s)
        st.markdown(
            f"<div style='font-size:16px;font-weight:500;margin:4px 0 16px 0;'>"
            f"{scenario_sentence}"
            "</div>",
            unsafe_allow_html=True,
        )

        # ----- Choix d'action -----
        st.markdown("#### 🤔 Que fais-tu dans ce spot ?")

        actions_row1 = ["fold", "open", "call"]
        actions_row2 = ["threebet", "open_shove", "threebet_shove"]

        def button_label(act: str) -> str:
            return f"{ACTION_EMOJI.get(act, '')} {ACTION_LABELS[act]}"

        def on_answer(action_key: str):
            current_spot = st.session_state.current_spot
            if not current_spot:
                return
            hero_hand = current_spot["hand"]
            actions_for_spot = current_spot.get("actions_for_spot")

            correct = evaluate_answer(action_key, hero_hand, actions_for_spot)

            stats = st.session_state.trainer_stats
            if (
                mode == "Avec ranges de correction"
                and current_spot["spot_key"]
            ):
                update_stats(stats, current_spot["spot_key"], success=correct)
                save_trainer_stats(username, stats)

            if mode == "Entraînement libre":
                st.session_state.last_feedback = {
                    "correct": None,
                    "hero_action": action_key,
                    "message": (
                        f"Tu as choisi : **{ACTION_LABELS[action_key]}** "
                        "(mode libre)."
                    ),
                }
            else:
                if correct:
                    msg = (
                        f"✅ Bonne réponse : **{ACTION_LABELS[action_key]}** "
                        f"pour {hero_hand}."
                    )
                else:
                    msg = (
                        f"❌ Mauvaise réponse : **{ACTION_LABELS[action_key]}** "
                        f"pour {hero_hand}."
                    )
                st.session_state.last_feedback = {
                    "correct": correct,
                    "hero_action": action_key,
                    "message": msg,
                }

        c1, c2, c3 = st.columns(3)
        for col, act in zip((c1, c2, c3), actions_row1):
            with col:
                if st.button(button_label(act), key=f"btn_{act}"):
                    on_answer(act)

        c4, c5, c6 = st.columns(3)
        for col, act in zip((c4, c5, c6), actions_row2):
            with col:
                if st.button(button_label(act), key=f"btn_{act}"):
                    on_answer(act)

        fb = st.session_state.last_feedback
        if fb is not None:
            st.markdown("---")
            if fb["correct"] is True:
                st.success(fb["message"])
            elif fb["correct"] is False:
                st.error(fb["message"])
            else:
                st.info(fb["message"])

            if (
                mode == "Avec ranges de correction"
                and fb["correct"] is False
                and spot.get("actions_for_spot")
            ):
                st.markdown("#### 📚 Range de correction pour ce spot")
                html_table = render_correction_range_html(
                    spot["actions_for_spot"],
                    hero_hand=spot["hand"],
                )
                st.markdown(html_table, unsafe_allow_html=True)
