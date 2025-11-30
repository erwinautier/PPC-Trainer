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
    # 1) Vérif des secrets
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
    for i in range(le
