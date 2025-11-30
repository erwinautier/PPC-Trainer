# trainer_module.py

import os
import sys
import json
import random
from collections import defaultdict
from datetime import datetime

import streamlit as st
from supabase import create_client, Client

# -----------------------------
#  Config Supabase pour les stats
# -----------------------------
SUPABASE_URL = st.secrets.get("SUPABASE_URL")
SUPABASE_ANON_KEY = st.secrets.get("SUPABASE_ANON_KEY")

SUPABASE_STATS_TABLE = "trainer_stats"
SUPABASE_STATS_COLUMN = "stats"   # 👉 mets "data" si ta colonne s'appelle data


@st.cache_resource
def get_supabase() -> Client | None:
    """
    Client Supabase partagé (caché par Streamlit).
    Retourne None si la config est incomplète ou si l'init échoue.
    """
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        st.sidebar.error(
            "⚠️ SUPABASE_URL ou SUPABASE_ANON_KEY manquent dans st.secrets. "
            "Les stats seront uniquement stockées en local."
        )
        return None

    try:
        client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
        st.sidebar.caption("[DEBUG] Client Supabase (trainer) initialisé.")
        return client
    except Exception as e:
        st.sidebar.error(f"⚠️ Erreur d'initialisation Supabase (trainer) : {e}")
        return None


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
ACTION_EMOJI = {
    "open": "🟢",
    "call": "🟡",
    "threebet": "🔴",
    "open_shove": "🟣",
    "threebet_shove": "⚫",
    "fold": "❌",
}


def load_user_ranges_from_supabase(username: str) -> dict:
    client = get_supabase()
    if client is None:
        return {}

    try:
        resp = (
            client.table("user_ranges")
            .select("ranges_json")
            .eq("username", username)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        if not rows:
            return {}

        data = rows[0].get("ranges_json") or {}
        if "spots" in data and isinstance(data["spots"], dict):
            return data
        if isinstance(data, dict) and any(
            isinstance(v, dict) and "position" in v for v in data.values()
        ):
            return {"version": 2, "spots": data}
        return {}
    except Exception as e:
        st.sidebar.warning(f"[Supabase user_ranges] Erreur lecture : {e}")
        return {}


def base_dir():
    """Dossier racine (compatible exécutable)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def user_ranges_path(username: str) -> str:
    """Chemin du fichier de ranges perso pour un utilisateur (fallback)."""
    safe = "".join(c for c in username if c.isalnum() or c in ("_", "-"))
    return os.path.join(base_dir(), f"ranges_{safe}.json")


def default_ranges_path() -> str:
    """Chemin du fichier de ranges par défaut (fallback)."""
    return os.path.join(base_dir(), "default_ranges.json")


def trainer_stats_path(username: str) -> str:
    """Chemin du fichier de stats / Leitner pour le trainer (fallback)."""
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


ALL_HANDS = {
    canonical_hand_from_indices(i, j)
    for i in range(len(RANKS))
    for j in range(len(RANKS))
}

HAND_TO_COORD = {}
for i in range(len(RANKS)):
    for j in range(len(RANKS)):
        h = canonical_hand_from_indices(i, j)
        HAND_TO_COORD[h] = (i, j)


# =========================================================
#  Chargement des ranges (défaut + perso, fallback fichiers)
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
        if isinstance(data, dict) and any(
            isinstance(v, dict) and "position" in v for v in data.values()
        ):
            return {"version": 2, "spots": data}
    except Exception:
        pass
    return {"version": 2, "spots": {}}


# =========================================================
#  Stats / Leitner (Supabase + fallback fichier)
# =========================================================

def default_stats_dict() -> dict:
    return {
        "spots": {},
        "total": {"success": 0, "fail": 0},
        "history": [],   # historique des coups pour les graphes
    }


def load_trainer_stats_from_file(username: str) -> dict:
    path = trainer_stats_path(username)
    if not os.path.exists(path):
        return default_stats_dict()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "spots" in data and "total" in data:
            return data
    except Exception:
        pass
    return default_stats_dict()


def save_trainer_stats_to_file(username: str, stats: dict):
    path = trainer_stats_path(username)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2)
    except Exception:
        pass


def load_trainer_stats_from_supabase(username: str) -> dict:
    """
    Charge les stats depuis Supabase.
    Si rien trouvé, renvoie un dict par défaut.
    Si erreur, renvoie None (pour permettre un fallback local).
    """
    client = get_supabase()
    if client is None:
        st.sidebar.warning("[DEBUG] Supabase non disponible pour charger les stats.")
        return None

    try:
        res = (
            client.table(SUPABASE_STATS_TABLE)
            .select(SUPABASE_STATS_COLUMN)
            .eq("username", username)
            .execute()
        )
        rows = res.data or []

        if not rows:
            st.sidebar.caption(f"[DEBUG] Aucune ligne trainer_stats pour {username} (Supabase).")
            return default_stats_dict()

        stats = rows[0].get(SUPABASE_STATS_COLUMN)

        if isinstance(stats, dict) and "spots" in stats and "total" in stats:
            st.sidebar.caption(f"[DEBUG] Stats Supabase trouvées pour {username}.")
            return stats

        st.sidebar.warning(
            f"[DEBUG] Format de stats invalide en base pour {username}, "
            "on repart sur des stats vierges."
        )
        return default_stats_dict()

    except Exception as e:
        st.sidebar.error(f"[Supabase trainer_stats] Erreur lors du SELECT : {e}")
        return None


def save_trainer_stats_to_supabase(username: str, stats: dict):
    """
    Sauvegarde les stats dans Supabase (table trainer_stats).
    Affiche les erreurs en clair dans la sidebar.
    """
    client = get_supabase()
    if client is None:
        st.sidebar.warning("[DEBUG] Supabase non disponible (client=None) – stats seulement en local.")
        return

    try:
        payload = {
            "username": username,
            SUPABASE_STATS_COLUMN: stats,
        }

        _ = (
            client.table(SUPABASE_STATS_TABLE)
            .upsert(payload)
            .execute()
        )

        st.sidebar.caption(f"[DEBUG] Sauvegarde stats Supabase OK pour {username}.")
    except Exception as e:
        st.sidebar.error(f"[Supabase trainer_stats] Erreur lors de l'upsert : {e}")


def load_trainer_stats(username: str) -> dict:
    """
    Charge les stats du trainer en priorité depuis Supabase.
    Si Supabase n'est pas dispo ou échoue, on retombe sur le fichier JSON.
    """
    stats = load_trainer_stats_from_supabase(username)
    if stats is not None:
        return stats
    return load_trainer_stats_from_file(username)


def save_trainer_stats(username: str, stats: dict):
    """
    Sauvegarde les stats dans Supabase + fallback fichier.
    """
    save_trainer_stats_to_supabase(username, stats)
    save_trainer_stats_to_file(username, stats)


def update_stats(stats: dict, spot_key: str, success: bool):
    spots = stats.setdefault("spots", {})
    s = spots.setdefault(spot_key, {"success": 0, "fail": 0})
    if success:
        s["success"] += 1
        stats["total"]["success"] += 1
    else:
        s["fail"] += 1
        stats["total"]["fail"] += 1

    # Historique temporel pour les graphes
    history = stats.setdefault("history", [])
    history.append(
        {
            "ts": datetime.utcnow().isoformat(),
            "spot_key": spot_key,
            "success": bool(success),
        }
    )


def reset_trainer_stats(username: str) -> dict:
    """Remet toutes les stats du joueur à zéro (Supabase + fichier)."""
    stats = default_stats_dict()
    save_trainer_stats(username, stats)
    return stats


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

        # Filtre type de table
        if table_type_filter and ttype != table_type_filter:
            continue

        # Filtre position
        if pos_choice not in (None, "", "Aléatoire") and pos != pos_choice:
            continue

        # Filtre stack
        if stack_choice is not None and stack != stack_choice:
            continue

        # Filtrage des scénarios impossibles : open en BB
        if scen == "open" and pos == "BB":
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

def render_correction_range_html(
    actions_for_spot: dict,
    hero_hand: str = None,
    highlight_color: str | None = None,
) -> str:
    """
    Grille 13x13 compacte, avec cellules carrées.
    Si hero_hand est fourni, la cellule correspondante est surlignée.
    highlight_color permet de choisir la couleur de surlignage
    (par ex. vert/rouge translucide selon bonne/mauvaise réponse).
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
                if highlight_color:
                    highlight_style = f"background-color:{highlight_color};border-radius:4px;"
                else:
                    highlight_style = "background-color:#E5E7EB;border-radius:4px;"

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
    Transforme 'open', 'vs_open_HJ', 'vs_limp_SB', 'libre', etc. en phrase lisible.
    """
    if scenario == "libre":
        return "Mode libre : situation générique sans range de correction."

    if scenario == "open":
        if position == "BB":
            return (
                "Scénario incohérent (open depuis la BB). "
                "Vérifie tes ranges pour ce spot."
            )
        return (
            f"Personne n'a parlé avant toi : tu es en {position} et tu peux ouvrir le pot."
        )

    if scenario.startswith("vs_open_"):
        vil_pos = scenario.split("_", 2)[2]
        return f"{vil_pos} a open avant toi : tu joues en {position} face à son open."

    if scenario.startswith("vs_limp_"):
        vil_pos = scenario.split("_", 2)[2]
        return f"{vil_pos} a limpé avant toi : tu es en {position} et tu joues contre son limp."

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
            positions_all = POSITIONS_6MAX
        else:
            positions_all = POSITIONS_8MAX

        if pos_choice == "Aléatoire":
            position = random.choice(positions_all)
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

    # ----- Modes basés sur les ranges (correction ou focus leak) -----
    if ranges_source == "Ranges personnelles":
        spots = user_ranges.get("spots", {})
        if not spots:
            spots = default_ranges.get("spots", {})
    else:
        spots = default_ranges.get("spots", {})

    if not spots:
        return None

    available_spot_keys = list(spots.keys())

    # Spécifique au mode "Focus leak" : filtrage par leak + filtres
    if mode == "Focus leak":
        focus_threshold = st.session_state.get("focus_threshold", 80)
        focus_scenario = st.session_state.get("focus_scenario", "Tous")

        filtered_keys = []
        for key in available_spot_keys:
            try:
                ttype, pos, stack_str, scen = key.split("_", 3)
                stack_val = int(stack_str)
            except Exception:
                continue

            # Filtre format
            if table_type and ttype != table_type:
                continue

            # Filtre position
            if pos_choice not in (None, "", "Aléatoire") and pos != pos_choice:
                continue

            # Filtre stack
            if stack_choice_label not in (None, "", "Aléatoire"):
                try:
                    stack_target = int(stack_choice_label)
                    if stack_val != stack_target:
                        continue
                except ValueError:
                    pass

            # Filtre scénario ciblé
            if focus_scenario != "Tous" and scen != focus_scenario:
                continue

            # Filtre "leak" : on ne garde que les spots sous le seuil
            s = stats.get("spots", {}).get(
                key, {"success": 0, "fail": 0}
            )
            total = s["success"] + s["fail"]
            acc = (s["success"] / total * 100.0) if total > 0 else 0.0

            # Si on a peu d'essais, on le considère comme un leak à travailler
            if total >= 5 and acc >= focus_threshold:
                # Spot maîtrisé -> on ne le met pas dans la liste
                continue

            filtered_keys.append(key)

        if not filtered_keys:
            st.info(
                "🎉 Tu as atteint ton seuil de réussite sur les spots ciblés.\n"
                "Augmente le seuil ou change de filtre de scénario / position / stack."
            )
            return None

        available_spot_keys = filtered_keys

    # Sélection avec Leitner & filtres généraux
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
    # DEBUG : lister les clés de secrets sans montrer les valeurs
    try:
        secret_keys = list(st.secrets.keys())
    except Exception:
        secret_keys = []
    st.sidebar.caption(f"[DEBUG] Secrets présents : {secret_keys}")

    # ----------- Initialisation état session -----------
    if "trainer_user" not in st.session_state:
        st.session_state.trainer_user = username
    elif st.session_state.trainer_user != username:
        st.session_state.trainer_user = username
        st.session_state.trainer_stats = load_trainer_stats(username)
        st.session_state.current_spot = None
        st.session_state.last_feedback = None
        st.session_state.answered_current_spot = False

    if "trainer_stats" not in st.session_state:
        st.session_state.trainer_stats = load_trainer_stats(username)

    if "current_spot" not in st.session_state:
        st.session_state.current_spot = None

    if "last_feedback" not in st.session_state:
        st.session_state.last_feedback = None

    if "answered_current_spot" not in st.session_state:
        st.session_state.answered_current_spot = False

    # ----------- Chargement des ranges -----------
    default_ranges = load_ranges_file(default_ranges_path())

    user_ranges = load_user_ranges_from_supabase(username)
    if not user_ranges.get("spots"):
        # fallback local
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
            ["Entraînement libre", "Avec ranges de correction", "Focus leak"],
            index=1,
            key="trainer_mode",
        )

        # Format de table
        table_type = st.radio(
            "Format de table",
            ["6-max", "8-max"],
            index=0,
            horizontal=True,
            key="trainer_table_type",
        )

        # Position
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

        # Stack
        stack_choice_label = st.selectbox(
            "Stack (BB) (ou Aléatoire)",
            ["Aléatoire"] + [str(s) for s in STACKS],
            index=0,
            key="trainer_stack_choice",
        )

        # Source de ranges
        ranges_source = st.radio(
            "Source des ranges (modes correction / focus leak)",
            ["Ranges par défaut", "Ranges personnelles"],
            index=0,
            key="trainer_ranges_source",
        )

        # Mode Focus leak : paramètres spécifiques
        if mode == "Focus leak":
            st.markdown("---")
            focus_threshold = st.slider(
                "Seuil de réussite pour considérer le leak résolu (%)",
                min_value=50,
                max_value=100,
                value=80,
                step=5,
                key="focus_threshold",
            )

            # Récupérer les scénarios disponibles à partir des ranges
            all_spots = {}
            all_spots.update(default_ranges.get("spots", {}))
            all_spots.update(user_ranges.get("spots", {}))

            all_scenarios = sorted(
                {key.split("_", 3)[3] for key in all_spots.keys()}
            ) if all_spots else []

            focus_scenario = st.selectbox(
                "Scénario ciblé (type de coup)",
                ["Tous"] + all_scenarios,
                index=0,
                key="focus_scenario",
            )
        else:
            st.session_state.setdefault("focus_threshold", 80)
            st.session_state.setdefault("focus_scenario", "Tous")

        # Avertissements si ranges manquantes
        if mode in ("Avec ranges de correction", "Focus leak"):
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
                        "Les modes avec ranges ne pourront pas fonctionner."
                    )

        st.markdown("---")
        # Stats globales
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
        st.markdown("---")

        if st.button("🔄 Remettre toutes mes stats à zéro"):
            new_stats = reset_trainer_stats(username)
            st.session_state.trainer_stats = new_stats
            st.session_state.current_spot = None
            st.session_state.last_feedback = None
            st.session_state.answered_current_spot = False
            st.success("Stats remises à zéro pour ce profil.")

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
                if mode == "Focus leak":
                    st.warning(
                        "Impossible de générer un spot : aucun spot en-dessous du seuil "
                        "dans les filtres choisis (position/stack/scénario)."
                    )
                else:
                    st.warning(
                        "Impossible de générer un spot avec les ranges (aucun spot trouvé). "
                        "Tu peux passer en 'Entraînement libre'."
                    )
            else:
                st.session_state.current_spot = new_spot
                st.session_state.last_feedback = None
                st.session_state.answered_current_spot = False

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
            if st.session_state.get("answered_current_spot", False):
                return  # sécurité supplémentaire

            hero_hand = current_spot["hand"]
            actions_for_spot = current_spot.get("actions_for_spot")

            correct = evaluate_answer(action_key, hero_hand, actions_for_spot)

            stats_local = st.session_state.trainer_stats
            # On met à jour les stats pour tous les modes avec ranges
            if mode != "Entraînement libre" and current_spot.get("spot_key"):
                update_stats(stats_local, current_spot["spot_key"], success=correct)
                save_trainer_stats(username, stats_local)

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

            # On bloque les boutons jusqu'à la prochaine main
            st.session_state.answered_current_spot = True

        # Boutons uniquement si on n'a pas encore répondu à cette main
        if not st.session_state.get("answered_current_spot", False):
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
        else:
            st.info(
                "Tu as déjà répondu à cette main. "
                "Clique sur **Nouvelle main** pour continuer l'entraînement."
            )

        fb = st.session_state.last_feedback
        if fb is not None:
            st.markdown("---")
            if fb["correct"] is True:
                st.success(fb["message"])
            elif fb["correct"] is False:
                st.error(fb["message"])
            else:
                st.info(fb["message"])

            # Range de correction affichée dans tous les cas (modes avec ranges)
            if (
                mode != "Entraînement libre"
                and spot.get("actions_for_spot")
            ):
                st.markdown("#### 📚 Range de correction pour ce spot")

                # Couleur de surlignage de la main jouée
                if fb["correct"] is True:
                    highlight_color = "rgba(34,197,94,0.35)"   # vert translucide
                elif fb["correct"] is False:
                    highlight_color = "rgba(239,68,68,0.35)"  # rouge translucide
                else:
                    highlight_color = None

                html_table = render_correction_range_html(
                    spot["actions_for_spot"],
                    hero_hand=spot["hand"],
                    highlight_color=highlight_color,
                )
                st.markdown(html_table, unsafe_allow_html=True)

        # ===============================
        # Spots à retravailler
        # ===============================
        st.markdown("### 📌 Spots à retravailler")

        stats_dict = st.session_state.trainer_stats
        spot_stats = stats_dict.get("spots", {})
        rows = []
        for sk, s in spot_stats.items():
            total = s.get("success", 0) + s.get("fail", 0)
            if total < 5:
                continue  # on ignore les spots peu vus
            acc = s.get("success", 0) / total * 100.0
            rows.append((acc, total, sk))

        if not rows:
            st.info("Pas encore assez de données pour détecter des leaks.")
        else:
            rows.sort()  # du plus faible au plus fort
            worst = rows[:5]
            for acc, total, sk in worst:
                st.markdown(
                    f"- `{sk}` – {acc:.1f}% de réussite sur {total} essais"
                )

        # ===============================
        # Courbes de progression
        # ===============================
        st.markdown("### 📈 Progression")

        history = st.session_state.trainer_stats.get("history", [])
        if not history:
            st.info("Pas encore d'historique de mains pour tracer des courbes.")
        else:
            import pandas as pd
            import altair as alt

            df = pd.DataFrame(history)
            df["ts"] = pd.to_datetime(df["ts"], errors="coerce")
            df["date"] = df["ts"].dt.date

            # Courbe de précision globale par jour
            agg_acc = (
                df.groupby("date")["success"]
                .agg(["count", "mean"])
                .reset_index()
                .rename(columns={"count": "nb_mains", "mean": "accuracy"})
            )
            agg_acc["accuracy"] = agg_acc["accuracy"] * 100.0

            st.line_chart(
                agg_acc.set_index("date")[["accuracy"]],
                height=200,
            )

            # Histogramme empilé : bonnes vs mauvaises réponses par jour
            df["success_bool"] = df["success"].astype(bool)
            agg_counts = (
                df.groupby(["date", "success_bool"])
                .size()
                .reset_index(name="nb")
            )

            # Pour Altair : date en datetime
            agg_counts["date"] = pd.to_datetime(agg_counts["date"])

            # Labels lisibles
            agg_counts["type"] = agg_counts["success_bool"].map(
                {True: "Bonnes réponses", False: "Mauvaises réponses"}
            )

            chart = (
                alt.Chart(agg_counts)
                .mark_bar()
                .encode(
                    x=alt.X("date:T", title="Date"),
                    y=alt.Y("nb:Q", stack="zero", title="Nombre de mains"),
                    color=alt.Color(
                        "type:N",
                        scale=alt.Scale(
                            domain=["Bonnes réponses", "Mauvaises réponses"],
                            range=["#16A34A", "#EF4444"],
                        ),
                        legend=alt.Legend(title="Résultat"),
                    ),
                    tooltip=[
                        alt.Tooltip("date:T", title="Date"),
                        alt.Tooltip("type:N", title="Type"),
                        alt.Tooltip("nb:Q", title="Nombre"),
                    ],
                )
                .properties(height=220)
            )

            st.altair_chart(chart, use_container_width=True)
