"""
YouTube Search Browser — Recherche YouTube avec filtres avancés
Streamlit UI + YouTube Data API v3 + post-filtrage côté client
"""

import streamlit as st
import json
import os
from datetime import datetime, timedelta
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# ─── Configuration ───────────────────────────────────────────

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")


def load_api_key():
    """Charge la clé API depuis config.json."""
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            config = json.load(f)
        return config.get("youtube_api_key", "")
    return ""


# ─── YouTube API ─────────────────────────────────────────────


@st.cache_data(ttl=300, show_spinner=False)
def search_youtube(api_key, query, max_results, published_after, published_before,
                   video_duration, video_definition, video_caption,
                   video_license, order, region_code, relevance_language):
    """Recherche via l'API YouTube Data v3 avec les filtres natifs."""
    youtube = build("youtube", "v3", developerKey=api_key)

    request_params = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "maxResults": min(max_results, 50),
        "order": order,
    }

    if published_after:
        request_params["publishedAfter"] = published_after.isoformat() + "T00:00:00Z"
    if published_before:
        request_params["publishedBefore"] = published_before.isoformat() + "T00:00:00Z"
    if video_duration != "any":
        request_params["videoDuration"] = video_duration
    if video_definition != "any":
        request_params["videoDefinition"] = video_definition
    if video_caption != "any":
        request_params["videoCaption"] = video_caption
    if video_license:
        request_params["videoLicense"] = video_license
    if region_code:
        request_params["regionCode"] = region_code
    if relevance_language:
        request_params["relevanceLanguage"] = relevance_language

    search_response = youtube.search().list(**request_params).execute()

    video_ids = [item["id"]["videoId"] for item in search_response["items"]]
    if not video_ids:
        return []

    # Récupérer les stats détaillées (vues, durée, etc.)
    videos_response = youtube.videos().list(
        part="snippet,statistics,contentDetails",
        id=",".join(video_ids)
    ).execute()

    # Récupérer les infos des chaînes (abonnés)
    channel_ids = list(set(v["snippet"]["channelId"] for v in videos_response["items"]))
    channels_response = youtube.channels().list(
        part="statistics,snippet",
        id=",".join(channel_ids)
    ).execute()
    channel_subs = {}
    for ch in channels_response["items"]:
        channel_subs[ch["id"]] = int(ch["statistics"].get("subscriberCount", 0))

    results = []
    for video in videos_response["items"]:
        vid = video["id"]
        snippet = video["snippet"]
        stats = video["statistics"]
        details = video["contentDetails"]

        # Calculer la durée en secondes
        duration_iso = details["duration"]  # ex: "PT4M13S"
        duration_secs = parse_duration(duration_iso)

        # Formater la durée
        minutes = duration_secs // 60
        seconds = duration_secs % 60
        duration_str = f"{minutes}:{seconds:02d}"

        results.append({
            "id": vid,
            "title": snippet["title"],
            "channel": snippet["channelTitle"],
            "channel_id": snippet["channelId"],
            "channel_subs": channel_subs.get(snippet["channelId"], 0),
            "views": int(stats.get("viewCount", 0)),
            "likes": int(stats.get("likeCount", 0)),
            "comments": int(stats.get("commentCount", 0)),
            "duration_secs": duration_secs,
            "duration_str": duration_str,
            "published": snippet["publishedAt"],
            "description": snippet["description"],
            "thumbnail": snippet["thumbnails"]["medium"]["url"],
        })

    return results


def parse_duration(iso_duration):
    """Convertit une durée ISO 8601 (PT4M13S, P1DT2H, PT0S) en secondes."""
    import re
    # Formats possibles : PT#H#M#S, P#DT#H#M#S, PT0S (lives)
    match = re.match(r'P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?', iso_duration)
    if match is None:
        return 0
    days = int(match.group(1) or 0)
    hours = int(match.group(2) or 0)
    minutes = int(match.group(3) or 0)
    seconds = int(match.group(4) or 0)
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def format_views(n):
    """Formate un nombre de vues en notation lisible."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    elif n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def format_date(iso_date):
    """Formate une date ISO en format lisible."""
    dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
    return dt.strftime("%d/%m/%Y")


# ─── UI Streamlit ────────────────────────────────────────────

st.set_page_config(
    page_title="YouTube Search Browser",
    page_icon="🔍",
    layout="wide",
)

st.title("🔍 YouTube Search Browser")
st.caption("Recherche avancée avec filtres précis — powered by YouTube Data API v3")

# ── Barre latérale : API Key + Filtres ──────────────────────

with st.sidebar:
    st.header("⚙️ Configuration")

    saved_key = load_api_key()
    api_key = st.text_input(
        "Clé API YouTube",
        value=saved_key,
        type="password",
        help="YouTube Data API v3 key depuis Google Cloud Console",
        placeholder="AIzaSy..."
    )

    if api_key and api_key != saved_key:
        # Sauvegarder automatiquement
        with open(CONFIG_PATH, "w") as f:
            json.dump({"youtube_api_key": api_key}, f, indent=4)
        st.success("✅ Clé sauvegardée !")

    st.divider()

    st.header("🎚️ Filtres API (natifs)")

    # Plage de dates
    st.subheader("📅 Date de publication")
    date_col1, date_col2 = st.columns(2)
    with date_col1:
        date_after = st.date_input("Après le", value=None)
    with date_col2:
        date_before = st.date_input("Avant le", value=None)

    # Type de durée
    st.subheader("⏱️ Durée")
    video_duration = st.selectbox(
        "Type de durée",
        options=["any", "short", "medium", "long"],
        format_func=lambda x: {
            "any": "Toutes",
            "short": "< 4 minutes",
            "medium": "4-20 minutes",
            "long": "> 20 minutes"
        }.get(x, x)
    )

    # Qualité
    st.subheader("🎥 Qualité & options")
    video_definition = st.selectbox(
        "Définition",
        options=["any", "high", "standard"],
        format_func=lambda x: {
            "any": "Toutes",
            "high": "HD (720p+)",
            "standard": "Standard"
        }.get(x, x)
    )

    video_caption = st.selectbox(
        "Sous-titres",
        options=["any", "closedCaption", "none"],
        format_func=lambda x: {
            "any": "Peu importe",
            "closedCaption": "Sous-titré",
            "none": "Sans sous-titres"
        }.get(x, x)
    )

    video_license = st.selectbox(
        "Licence",
        options=["", "creativeCommon", "youtube"],
        format_func=lambda x: {
            "": "Toutes",
            "creativeCommon": "Creative Commons",
            "youtube": "Standard YouTube"
        }.get(x, x)
    )

    # Région et langue
    st.subheader("🌍 Localisation")
    region_col1, region_col2 = st.columns(2)
    with region_col1:
        region_code = st.selectbox(
            "Pays",
            options=["", "FR", "US", "GB", "DE", "JP", "CA", "BE", "CH"],
            format_func=lambda x: {
                "": "Tous",
                "FR": "🇫🇷 France",
                "US": "🇺🇸 USA",
                "GB": "🇬🇧 UK",
                "DE": "🇩🇪 Allemagne",
                "JP": "🇯🇵 Japon",
                "CA": "🇨🇦 Canada",
                "BE": "🇧🇪 Belgique",
                "CH": "🇨🇭 Suisse"
            }.get(x, x)
        )
    with region_col2:
        relevance_language = st.selectbox(
            "Langue",
            options=["", "fr", "en", "es", "de", "ja", "it", "pt"],
            format_func=lambda x: {
                "": "Toutes",
                "fr": "Français",
                "en": "Anglais",
                "es": "Espagnol",
                "de": "Allemand",
                "ja": "Japonais",
                "it": "Italien",
                "pt": "Portugais"
            }.get(x, x)
        )

    # Tri
    st.subheader("📈 Tri")
    order = st.selectbox(
        "Trier par",
        options=["relevance", "date", "viewCount", "rating"],
        format_func=lambda x: {
            "relevance": "Pertinence",
            "date": "Date",
            "viewCount": "Vues",
            "rating": "Note"
        }.get(x, x)
    )

    st.divider()

    # Filtres post-API (appliqués côté client)
    st.header("🔬 Filtres avancés (post-API)")

    st.subheader("👁️ Vues")
    views_col1, views_col2 = st.columns(2)
    with views_col1:
        views_min = st.number_input("Min", min_value=0, value=0, step=1000, format="%d")
    with views_col2:
        views_max = st.number_input("Max", min_value=0, value=0, step=1000, format="%d",
                                    help="0 = pas de limite")

    st.subheader("⏱️ Durée exacte (secondes)")
    dur_col1, dur_col2 = st.columns(2)
    with dur_col1:
        dur_min = st.number_input("Min (s)", min_value=0, value=0, step=30)
    with dur_col2:
        dur_max = st.number_input("Max (s)", min_value=0, value=0, step=30,
                                  help="0 = pas de limite")

    st.subheader("👤 Chaîne")
    subs_min = st.number_input("Abonnés minimum", min_value=0, value=0, step=1000, format="%d")

    # Nombre de résultats
    st.subheader("📊 Résultats")
    max_results = st.slider("Nombre max", min_value=5, max_value=50, value=25, step=5)

# ── Zone principale : Recherche + Résultats ──────────────────

query = st.text_input("🔎 Rechercher sur YouTube", placeholder="Ex: python tutorial, dark techno mix...")

if query and api_key:
    try:
        with st.spinner("Recherche en cours..."):
            results = search_youtube(
                api_key=api_key,
                query=query,
                max_results=max_results,
                published_after=date_after if date_after else None,
                published_before=date_before if date_before else None,
                video_duration=video_duration,
                video_definition=video_definition,
                video_caption=video_caption,
                video_license=video_license or None,
                order=order,
                region_code=region_code or None,
                relevance_language=relevance_language or None,
            )

        # ── Post-filtrage ──────────────────────────────────

        if views_min > 0:
            results = [r for r in results if r["views"] >= views_min]
        if views_max > 0:
            results = [r for r in results if r["views"] <= views_max]
        if dur_min > 0:
            results = [r for r in results if r["duration_secs"] >= dur_min]
        if dur_max > 0:
            results = [r for r in results if r["duration_secs"] <= dur_max]
        if subs_min > 0:
            results = [r for r in results if r["channel_subs"] >= subs_min]

        # ── Affichage ──────────────────────────────────────

        st.subheader(f"📺 {len(results)} résultat(s) pour « {query} »")

        if not results:
            st.info("Aucun résultat avec ces filtres. Essaye d'élargir les critères.")
        else:
            for video in results:
                col1, col2 = st.columns([1, 4])
                with col1:
                    st.image(video["thumbnail"], use_container_width=True)
                with col2:
                    st.markdown(f"### [{video['title']}](https://youtube.com/watch?v={video['id']})")
                    st.markdown(
                        f"**{video['channel']}** · "
                        f"{format_views(video['views'])} vues · "
                        f"{format_date(video['published'])} · "
                        f"🕐 {video['duration_str']}"
                    )

                    # Barre de stats
                    likes_str = format_views(video["likes"])
                    comments_str = format_views(video["comments"])
                    subs_str = format_views(video["channel_subs"])

                    st.caption(
                        f"👍 {likes_str}  |  💬 {comments_str}  |  "
                        f"👥 {subs_str} abonnés"
                    )

                    with st.expander("📝 Description"):
                        desc = video["description"]
                        if len(desc) > 500:
                            desc = desc[:500] + "..."
                        st.text(desc if desc else "Pas de description")

                st.divider()

    except HttpError as e:
        error_reason = str(e)
        if "quotaExceeded" in error_reason:
            st.error("🚫 Quota API dépassé (10 000 unités/jour). Réessaie demain ou crée une autre clé.")
        elif "apiKeyInvalid" in error_reason:
            st.error("🔑 Clé API invalide. Vérifie ta clé dans config.json.")
        else:
            st.error(f"❌ Erreur API YouTube : {e}")

elif query and not api_key:
    st.warning("⚠️ Entre ta clé API YouTube dans la barre latérale (ou dans config.json)")

# ── Footer ───────────────────────────────────────────────────

st.divider()
st.caption(
    "💡 **Astuce** : Les filtres « avancés » (vues min/max, durée exacte, abonnés min) "
    "sont appliqués **après** la recherche API. Si tu as peu de résultats, élargis d'abord "
    "les filtres API natifs."
)

# ── Instructions de lancement ───────────────────────────────
# Lancer avec : streamlit run youtube_search_browser.py
