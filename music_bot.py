"""
🎵 Discord Music Bot
Supports YouTube, SoundCloud and Spotify links (played via YouTube)
Features: Playlists, Volume Control, Loop, Queue Management
"""

import os
import sys
import asyncio
import logging
import yt_dlp
try:
    from yt_dlp import cookies as ytdl_cookies
except Exception:
    ytdl_cookies = None
import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import Button, View
import subprocess
import shutil
import aiohttp
import time
import re
import json
import urllib.parse
from collections import deque
import gc
import threading

# ═══════════════════════════════════════════════════════════════════
#                           LOGGING SETUP (CLEAN)
# ═══════════════════════════════════════════════════════════════════
def setup_logging():
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # Remove ALL existing handlers to prevent duplicate log lines
    for h in list(root.handlers):
        root.removeHandler(h)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter(
        fmt="%(asctime)s │ %(levelname)-7s │ %(message)s",
        datefmt="%H:%M:%S"
    ))
    root.addHandler(handler)

    # Silence noisy libraries (prevents the extra "2025-..." style lines)
    noisy = [
        "discord",
        "discord.gateway",
        "discord.client",
        "discord.http",
        "discord.player",
        "discord.voice_state",
        "discord.state",
        "discord.opus",
        "asyncio",
        "websockets",
        "yt_dlp",
    ]
    for name in noisy:
        lg = logging.getLogger(name)
        lg.setLevel(logging.WARNING)
        for h in list(lg.handlers):
            lg.removeHandler(h)
        lg.propagate = True

setup_logging()
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════
#                           PATH SETUP
# ═══════════════════════════════════════════════════════════════════
def get_base_path():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

BASE_PATH = get_base_path()

# ═══════════════════════════════════════════════════════════════════
#                        CONFIG PARSER
# ═══════════════════════════════════════════════════════════════════
def parse_config(config_path):
    config = {}
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, value = line.split("=", 1)
                    config[key.strip()] = value.strip().strip('"').strip("'")
        return config
    except FileNotFoundError:
        logger.error("❌ Config file not found!")
        return {}

config_path = os.path.join(BASE_PATH, "config.txt")
config = parse_config(config_path)

# ═══════════════════════════════════════════════════════════════════
#                      CONFIGURATION VALUES
# ═══════════════════════════════════════════════════════════════════
def parse_bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}

def resolve_config_path(raw_value):
    value = (raw_value or "").strip()
    if not value:
        return None
    value = os.path.expanduser(value)
    if not os.path.isabs(value):
        value = os.path.join(BASE_PATH, value)
    return value

class _SilentCookieProbeLogger:
    def debug(self, *args, **kwargs):
        pass

    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass

def browser_cookie_looks_relevant(cookie_jar):
    relevant_domains = (
        "youtube.com",
        "youtu.be",
        "google.com",
        "accounts.google.com",
    )
    for cookie in cookie_jar:
        domain = (getattr(cookie, "domain", "") or "").lower()
        if any(token in domain for token in relevant_domains):
            return True
    return False

TOKEN = config.get("token")
if not TOKEN:
    logger.error("❌ Discord token not found in config.txt!")
    sys.exit(1)

PREFIX_RAW = config.get("prefix", "!!")
PREFIXES = [p.strip() for p in PREFIX_RAW.split(",") if p.strip()]
PREFIX = PREFIXES[0]
GAME = config.get("game", "Music Bot")
STATUS = config.get("status", "online")
OWNER_ID = config.get("owner")
PROXY = config.get("proxy")
HEARTBEAT_TIMEOUT = float(config.get("heartbeat_timeout", "60.0"))
COOKIE_FILE = resolve_config_path(config.get("cookie_file", ""))
if COOKIE_FILE and not os.path.exists(COOKIE_FILE):
    logger.warning(f"⚠️ Cookie file not found: {COOKIE_FILE} (continuing without it)")
    COOKIE_FILE = None
USE_BROWSER_COOKIES = parse_bool(config.get("use_browser_cookies", "false"))
# Empty = let yt-dlp pick its own (fast) client set. That needs a JS runtime
# (Deno/Node) to solve YouTube's challenges; without one we fall back to the
# old wide client list further below.
YOUTUBE_PLAYER_CLIENTS = [
    c.strip()
    for c in config.get("youtube_player_clients", "").split(",")
    if c.strip()
]
LEGACY_YOUTUBE_PLAYER_CLIENTS = ["web", "web_embedded", "mweb", "android", "ios", "default"]
YOUTUBE_FORMAT_FLAGS = [
    flag.strip()
    for flag in config.get("youtube_format_flags", "").split(",")
    if flag.strip()
]

USE_SLASH_COMMANDS = config.get("use_slash_commands", "true").lower() == "true"
USE_LOOP_FEATURE = config.get("use_loop_feature", "true").lower() == "true"

def parse_idle_clear_hours(raw_value):
    value = (raw_value or "").strip()
    if not value:
        return None
    try:
        hours = int(value)
    except ValueError:
        logger.warning(f"⚠️ Invalid idle_clear_hours value: {value!r}. Idle cleanup disabled.")
        return None
    if hours <= 0:
        logger.warning(f"⚠️ idle_clear_hours must be greater than 0: {value!r}. Idle cleanup disabled.")
        return None
    return hours

IDLE_CLEAR_HOURS = parse_idle_clear_hours(config.get("idle_clear_hours", ""))

FFMPEG_THREADS = int(config.get("ffmpeg_threads", "2"))
BUFFER_SIZE = int(config.get("buffer_size", "256"))
SAMPLE_RATE = int(config.get("sample_rate", "48000"))

PLAYLIST_LIMIT = int(config.get("playlist_limit", "250"))
MIX_LIMIT = int(config.get("mix_limit", "250"))
METADATA_CACHE_LIMIT = int(config.get("metadata_cache_limit", "150"))
METADATA_CACHE_TRIM = int(config.get("metadata_cache_trim", "25"))
METADATA_CACHE_TTL = int(config.get("metadata_cache_ttl", "180"))
PLAYLIST_CACHE_TTL = int(config.get("playlist_cache_ttl", "900"))

# ✅ Force Opus bitrate request (kbps)
FORCE_OPUS_BITRATE_KBPS = 256

def get_aliases(key, default=""):
    return [a.strip() for a in config.get(key, default).split(",") if a.strip()]

CMD_PLAY_ALIASES = get_aliases("cmd_play")
CMD_PAUSE_ALIASES = get_aliases("cmd_pause")
CMD_RESUME_ALIASES = get_aliases("cmd_resume")
CMD_SKIP_ALIASES = get_aliases("cmd_skip")
CMD_STOP_ALIASES = get_aliases("cmd_stop")
CMD_QUEUE_ALIASES = get_aliases("cmd_queue")
CMD_CLEAR_ALIASES = get_aliases("cmd_clear")
CMD_JOIN_ALIASES = get_aliases("cmd_join")
CMD_LEAVE_ALIASES = get_aliases("cmd_leave")
CMD_VOLUME_ALIASES = get_aliases("cmd_volume")
CMD_EMBEDRESET_ALIASES = get_aliases("cmd_embedreset", "epr")
CMD_UPDATE_ALIASES = get_aliases("cmd_update", "update,u,upd")
CMD_LOOP_ALIASES = get_aliases("cmd_loop", "lo,lp")
CMD_STOPLOOP_ALIASES = get_aliases("cmd_stoploop", "stlo,sloop,stopl,sl")
CMD_CLEARCACHE_ALIASES = get_aliases("cmd_clearcache", "cc,clearc,ccache,purge")
CMD_RESTART_ALIASES = get_aliases("cmd_restart", "rbot,reboot")

# ═══════════════════════════════════════════════════════════════════
#                         FFMPEG SETUP
# ═══════════════════════════════════════════════════════════════════
BIN_DIR = os.path.join(BASE_PATH, "bin")
EXE_SUFFIX = ".exe" if sys.platform == "win32" else ""

def find_ffmpeg():
    # Bundled build (kept fresh by update_deps.py) wins over the system one.
    bundled = os.path.join(BIN_DIR, f"ffmpeg{EXE_SUFFIX}")
    if os.path.exists(bundled):
        return bundled
    if sys.platform == "win32":
        local = os.path.join(BASE_PATH, "ffmpeg", "bin", "ffmpeg.exe")
        if os.path.exists(local):
            return local
    path = shutil.which("ffmpeg")
    if path:
        return path
    for p in [
        "/usr/bin/ffmpeg",
        "/usr/local/bin/ffmpeg",
        "C:\\ffmpeg\\bin\\ffmpeg.exe",
        "C:\\Program Files\\ffmpeg\\bin\\ffmpeg.exe",
    ]:
        if os.path.exists(p):
            return p
    return "ffmpeg"

FFMPEG_PATH = find_ffmpeg()

# ═══════════════════════════════════════════════════════════════════
#                        YT-DLP CONFIG
# ═══════════════════════════════════════════════════════════════════
_thread_local = threading.local()

def detect_js_runtimes():
    """JS runtime for yt-dlp's YouTube challenge solver: bundled Deno, then any Deno/Node on PATH."""
    candidates = [
        ("deno", os.path.join(BIN_DIR, f"deno{EXE_SUFFIX}")),
        ("deno", shutil.which("deno")),
        ("node", shutil.which("node")),
    ]
    for name, path in candidates:
        if path and os.path.exists(path):
            return {name: {"path": path}}
    return {}

JS_RUNTIMES = detect_js_runtimes()
if not JS_RUNTIMES and not YOUTUBE_PLAYER_CLIENTS:
    YOUTUBE_PLAYER_CLIENTS = LEGACY_YOUTUBE_PLAYER_CLIENTS

ytdl_format_options = {
    # Keep the selector broad so odd uploads still resolve, then let ffmpeg handle playback.
    "format": "bestaudio/best",
    "outtmpl": "%(extractor)s-%(id)s-%(title)s.%(ext)s",
    "restrictfilenames": True,
    "noplaylist": True,
    "nocheckcertificate": True,
    "ignoreerrors": True,
    "logtostderr": False,
    "quiet": True,
    "no_warnings": True,
    "verbose": False,
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",
    "socket_timeout": 30,
    "retries": 3,
    "fragment_retries": 2,
    "skip_unavailable_fragments": True,
    "keepvideo": False,
    "geo_bypass": True,
    "age_limit": None,
    "prefer_ffmpeg": True,
    "js_runtimes": JS_RUNTIMES,

    "extractaudio": True,
    "skip_download": True,
    "writethumbnail": False,
    "writeinfojson": False,
    "http_headers": {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-us,en;q=0.5",
        "DNT": "1",
        "Connection": "keep-alive",
    },
}

if PROXY:
    ytdl_format_options["proxy"] = PROXY

def resolve_browser_cookie_spec():
    if not USE_BROWSER_COOKIES or ytdl_cookies is None:
        return None, None

    browser_candidates = [
        "firefox",
        "chrome",
        "chromium",
        "edge",
        "brave",
        "opera",
        "vivaldi",
        "whale",
        "safari",
    ]

    probe_logger = _SilentCookieProbeLogger()
    for browser_name in browser_candidates:
        try:
            jar = ytdl_cookies.extract_cookies_from_browser(browser_name, logger=probe_logger)
            if len(jar) > 0 and browser_cookie_looks_relevant(jar):
                return (browser_name,), browser_name
        except Exception:
            continue

    return None, None

COOKIE_BROWSER_SPEC, COOKIE_BROWSER_LABEL = resolve_browser_cookie_spec()
HAS_COOKIE_SOURCES = bool(COOKIE_FILE or COOKIE_BROWSER_SPEC)

def build_ytdl_options(extra_options=None, use_cookie_sources=False, skip_youtube_manifests=True):
    opts = ytdl_format_options.copy()
    if extra_options:
        for key, value in extra_options.items():
            if (
                key == "extractor_args"
                and isinstance(value, dict)
                and isinstance(opts.get("extractor_args"), dict)
            ):
                merged = {k: (v.copy() if isinstance(v, dict) else v) for k, v in opts["extractor_args"].items()}
                for extractor_key, extractor_value in value.items():
                    if isinstance(extractor_value, dict) and isinstance(merged.get(extractor_key), dict):
                        merged[extractor_key].update(extractor_value)
                    else:
                        merged[extractor_key] = extractor_value
                opts["extractor_args"] = merged
            else:
                opts[key] = value
    if use_cookie_sources and COOKIE_FILE:
        opts["cookiefile"] = COOKIE_FILE
    if use_cookie_sources and COOKIE_BROWSER_SPEC:
        opts["cookiesfrombrowser"] = COOKIE_BROWSER_SPEC
    if skip_youtube_manifests:
        # Audio comes from the adaptive formats; fetching the HLS/DASH
        # manifests costs ~0.5s per song. Live streams need them, so callers
        # retry with skip_youtube_manifests=False when nothing playable came back.
        youtube_args = opts.setdefault("extractor_args", {}).setdefault("youtube", {})
        youtube_args.setdefault("skip", ["hls", "dash"])
    if YOUTUBE_PLAYER_CLIENTS:
        extractor_args = opts.setdefault("extractor_args", {})
        youtube_args = extractor_args.setdefault("youtube", {})
        youtube_args["player_client"] = YOUTUBE_PLAYER_CLIENTS
        if YOUTUBE_FORMAT_FLAGS:
            youtube_args["formats"] = YOUTUBE_FORMAT_FLAGS
    return opts

COOKIE_STATUS_PARTS = []
if COOKIE_FILE:
    COOKIE_STATUS_PARTS.append(f"File ✓ {os.path.basename(COOKIE_FILE)}")
if COOKIE_BROWSER_LABEL:
    COOKIE_STATUS_PARTS.append(f"Browser ✓ {COOKIE_BROWSER_LABEL}")
COOKIE_STATUS = " + ".join(COOKIE_STATUS_PARTS) if COOKIE_STATUS_PARTS else "None"
if COOKIE_STATUS_PARTS:
    COOKIE_STATUS = f"{COOKIE_STATUS} (YouTube only)"
YOUTUBE_FORMAT_STATUS = ", ".join(YOUTUBE_FORMAT_FLAGS) if YOUTUBE_FORMAT_FLAGS else "none"

def build_raw_ytdl_options(extra_options=None, use_cookie_sources=False):
    opts = build_ytdl_options(extra_options, use_cookie_sources=use_cookie_sources, skip_youtube_manifests=False)
    # Raw extraction avoids yt-dlp's final format selection. We pick the stream ourselves.
    opts.pop("format", None)
    return opts

def is_missing_pot_format(fmt):
    if not isinstance(fmt, dict):
        return False
    return "missing pot" in ((fmt.get("format_note") or "").lower())

def score_audio_format(fmt, extractor_name="", allow_missing_pot=False):
    if not isinstance(fmt, dict):
        return None
    if not fmt.get("url"):
        return None
    if fmt.get("acodec") in (None, "none"):
        return None
    if fmt.get("has_drm"):
        return None
    if not allow_missing_pot and is_missing_pot_format(fmt):
        return None

    protocol = (fmt.get("protocol") or "").lower()
    ext = (fmt.get("ext") or "").lower()
    format_note = (fmt.get("format_note") or "").lower()
    extractor_name = (extractor_name or "").lower()

    soundcloud_bonus = 0
    if extractor_name == "soundcloud":
        soundcloud_bonus = (
            1 if protocol == "http" and ext == "mp3" else 0,
            1 if protocol == "http" else 0,
            0 if protocol in {"m3u8_native", "m3u8"} else 1,
        )
    else:
        soundcloud_bonus = (0, 0, 0)

    return (
        1 if fmt.get("vcodec") == "none" else 0,
        1 if "missing pot" not in format_note else 0,
        *soundcloud_bonus,
        1 if protocol in {"https", "http", "m3u8_native", "m3u8"} else 0,
        0 if protocol == "http_dash_segments" else 1,
        0 if ext == "mhtml" else 1,
        float(fmt.get("source_preference") or 0),
        float(fmt.get("preference") or 0),
        float(fmt.get("abr") or 0),
        float(fmt.get("tbr") or 0),
        float(fmt.get("quality") or 0),
    )

def iter_best_audio_formats(data, allow_missing_pot=False):
    formats = data.get("formats") or []
    extractor_name = data.get("extractor", "")
    scored_formats = []

    for fmt in formats:
        score = score_audio_format(fmt, extractor_name=extractor_name, allow_missing_pot=allow_missing_pot)
        if score is None:
            continue
        scored_formats.append((score, fmt))

    scored_formats.sort(key=lambda item: item[0], reverse=True)
    return [fmt for _, fmt in scored_formats]

def select_best_audio_format(data, allow_missing_pot=False):
    candidates = iter_best_audio_formats(data, allow_missing_pot=allow_missing_pot)
    return candidates[0] if candidates else None

def has_usable_media_url(data):
    if not isinstance(data, dict):
        return False
    if data.get("url") and not is_missing_pot_format(data):
        return True
    return select_best_audio_format(data, allow_missing_pot=False) is not None

def is_youtube_request(target):
    value = (target or "").lower()
    return (
        "youtube.com" in value
        or "youtu.be" in value
        or "m.youtube.com" in value
        or value.startswith("ytsearch")
        or value.startswith("ytmsearch")
    )

def get_primary_entry(info):
    if isinstance(info, dict) and info.get("entries"):
        for entry in info["entries"]:
            if entry:
                return entry
        return None
    return info if isinstance(info, dict) else None

def should_retry_youtube_with_cookies(url, error=None):
    if not is_youtube_request(url) or not HAS_COOKIE_SOURCES:
        return False
    if error is None:
        return True

    message = str(error).lower()
    retry_markers = (
        "sign in",
        "sign-in",
        "login",
        "log in",
        "age-restricted",
        "age restricted",
        "confirm your age",
        "content warning",
        "inappropriate",
        "use --cookies",
        "http error 403",
        "forbidden",
    )
    return any(marker in message for marker in retry_markers)

YDL_INSTANCES_PER_THREAD = 8

def _get_thread_ydl(opts):
    """Reuse YoutubeDL objects per worker thread (they aren't thread-safe).
    A warm instance keeps YouTube's player JS and cookies between songs,
    which saves a download on every extraction."""
    key = json.dumps(opts, sort_keys=True, default=str)
    instances = getattr(_thread_local, "ydl_instances", None)
    if instances is None:
        instances = _thread_local.ydl_instances = {}
    ydl = instances.pop(key, None)
    if ydl is None:
        ydl = yt_dlp.YoutubeDL(opts)
        while len(instances) >= YDL_INSTANCES_PER_THREAD:
            old = instances.pop(next(iter(instances)))
            try:
                old.close()
            except Exception:
                pass
    instances[key] = ydl  # most recently used last
    return ydl

def _needs_manifest_retry(url, info):
    """Live YouTube streams only exist as HLS; retry those with manifests on.
    Also retry when the manifest-less request came back empty."""
    if not is_youtube_request(url):
        return False
    if info is None:
        return not (url or "").lower().startswith(("ytsearch", "ytmsearch"))
    if not isinstance(info, dict):
        return False
    entry = get_primary_entry(info)
    if not entry:
        return False
    return bool(entry.get("is_live") or entry.get("live_status") in ("is_live", "is_upcoming")) or not has_usable_media_url(entry)

async def extract_info_raw(url, timeout=60.0, extra_options=None, use_cookie_sources=False):
    opts = build_raw_ytdl_options(extra_options, use_cookie_sources=use_cookie_sources)
    loop = asyncio.get_event_loop()
    return await asyncio.wait_for(
        loop.run_in_executor(None, lambda: _get_thread_ydl(opts).extract_info(url, download=False, process=False)),
        timeout=timeout,
    )

async def extract_info_processed(url, timeout=60.0, extra_options=None, use_cookie_sources=False):
    opts = build_ytdl_options(extra_options, use_cookie_sources=use_cookie_sources)
    loop = asyncio.get_event_loop()
    info = await asyncio.wait_for(
        loop.run_in_executor(None, lambda: _get_thread_ydl(opts).extract_info(url, download=False)),
        timeout=timeout,
    )
    flat = (extra_options or {}).get("extract_flat")
    if not flat and _needs_manifest_retry(url, info):
        full_opts = build_ytdl_options(extra_options, use_cookie_sources=use_cookie_sources, skip_youtube_manifests=False)
        info = await asyncio.wait_for(
            loop.run_in_executor(None, lambda: _get_thread_ydl(full_opts).extract_info(url, download=False)),
            timeout=timeout,
        )
    return info

async def extract_info_with_cookie_fallback(url, timeout=60.0, extra_options=None):
    try:
        info = await extract_info_processed(
            url,
            timeout=timeout,
            extra_options=extra_options,
            use_cookie_sources=False,
        )
    except Exception as e:
        if not should_retry_youtube_with_cookies(url, e):
            raise
        logger.info("🍪 Cookie fallback: retrying this YouTube extraction with cookies")
        return await extract_info_processed(
            url,
            timeout=timeout,
            extra_options=extra_options,
            use_cookie_sources=True,
        )

    if not should_retry_youtube_with_cookies(url):
        return info

    candidate = get_primary_entry(info)
    if candidate and has_usable_media_url(candidate):
        return info

    logger.info("🍪 Cookie fallback: retrying this YouTube extraction with cookies")
    retry_info = await extract_info_processed(
        url,
        timeout=timeout,
        extra_options=extra_options,
        use_cookie_sources=True,
    )
    retry_candidate = get_primary_entry(retry_info)
    if retry_candidate and has_usable_media_url(retry_candidate):
        return retry_info
    return info

async def extract_processed_info_with_cookie_fallback(url, timeout=60.0, extra_options=None):
    if not is_youtube_request(url):
        return await extract_info_processed(
            url,
            timeout=timeout,
            extra_options=extra_options,
            use_cookie_sources=False,
        )

    try:
        return await extract_info_processed(
            url,
            timeout=timeout,
            extra_options=extra_options,
            use_cookie_sources=False,
        )
    except Exception as e:
        if not should_retry_youtube_with_cookies(url, e):
            raise
        logger.info("🍪 Cookie fallback: retrying this YouTube extraction with cookies")
        return await extract_info_processed(
            url,
            timeout=timeout,
            extra_options=extra_options,
            use_cookie_sources=True,
        )

ffmpeg_options = {
    "before_options": f"-thread_queue_size {BUFFER_SIZE} "
                      f"-reconnect 1 -reconnect_streamed 1 "
                      f"-reconnect_delay_max 5 "
                      f"-reconnect_on_network_error 1 "
                      f"-reconnect_at_eof 1 "
                      f"-threads {FFMPEG_THREADS} "
                      f"-probesize 500000 -analyzeduration 500000",
    "options": "-vn",
}

ffmpeg_fallback_options = {
    "before_options": f"-thread_queue_size {BUFFER_SIZE} "
                      f"-reconnect 1 -reconnect_streamed 1 "
                      f"-reconnect_delay_max 5 "
                      f"-reconnect_on_network_error 1 "
                      f"-reconnect_at_eof 1 "
                      f"-threads {FFMPEG_THREADS} "
                      f"-probesize 500000 -analyzeduration 500000",
    "options": "-vn",
}

# ═══════════════════════════════════════════════════════════════════
#                         CACHING SYSTEM
# ═══════════════════════════════════════════════════════════════════
_cache = {}
_cache_lock = asyncio.Lock()

def get_cache_key(url, extra=""):
    return f"{url}:{extra}"

async def get_cached_info(key):
    async with _cache_lock:
        if key in _cache:
            data, ts, ttl = _cache[key]
            if time.time() - ts < ttl:
                return data
            del _cache[key]
    return None

async def cache_info(key, data, ttl=None):
    if ttl is None:
        ttl = METADATA_CACHE_TTL
    async with _cache_lock:
        _cache[key] = (data, time.time(), ttl)
        if len(_cache) > METADATA_CACHE_LIMIT:
            oldest = sorted(_cache.keys(), key=lambda k: _cache[k][1])[:METADATA_CACHE_TRIM]
            for k in oldest:
                del _cache[k]

# ═══════════════════════════════════════════════════════════════════
#                     STREAM RESOLUTION (in-memory)
#   One extraction per song: whatever already extracted a song (search,
#   link lookup, prefetch) hands its stream info to playback. Stream
#   links rotate/expire, so every reuse is checked against the link's own
#   expiry and re-extracted when it is too close to it.
# ═══════════════════════════════════════════════════════════════════
STREAM_EXPIRY_MARGIN = 120        # re-extract when a link has < 2 min left
STREAM_UNKNOWN_EXPIRY_TTL = 300   # links without an expiry param: trust for 5 min
STREAM_MAX_CACHE_TTL = 3 * 3600
STREAM_KEEP_FORMATS = 6
STREAM_INFO_KEYS = (
    "id", "title", "url", "duration", "webpage_url", "original_url", "extractor",
    "extractor_key", "thumbnail", "cover", "uploader", "channel", "http_headers",
    "format_id", "format_note", "protocol", "ext", "acodec", "vcodec", "abr", "tbr",
)
_stream_inflight = {}

def stream_url_expiry(url):
    """Epoch seconds when a signed media URL stops working, if the URL says."""
    if not url:
        return None
    try:
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    except Exception:
        return None
    for key in ("expire", "expires", "Expires"):
        values = query.get(key)
        if values and values[0].isdigit():
            return int(values[0])
    return None

def _primary_stream_url(data):
    if data.get("url"):
        return data["url"]
    best = select_best_audio_format(data, allow_missing_pot=False)
    return best.get("url") if best else None

def stream_info_seconds_left(data):
    """How long cached stream info stays usable (<= 0 means re-extract)."""
    if not isinstance(data, dict):
        return 0
    expiry = stream_url_expiry(_primary_stream_url(data))
    if expiry:
        return expiry - time.time() - STREAM_EXPIRY_MARGIN
    return data.get("_extracted_at", 0) + STREAM_UNKNOWN_EXPIRY_TTL - time.time()

def slim_stream_info(data):
    """Keep only what playback + embeds use (full yt-dlp info is ~100s of KB)."""
    data = get_primary_entry(data) or {}
    slim = {k: data[k] for k in STREAM_INFO_KEYS if data.get(k) is not None}
    if not slim.get("thumbnail") and data.get("thumbnails"):
        slim["thumbnail"] = (data["thumbnails"][-1] or {}).get("url")
    slim["formats"] = iter_best_audio_formats(data, allow_missing_pot=False)[:STREAM_KEEP_FORMATS]
    slim["_extracted_at"] = data.get("_extracted_at") or time.time()
    return slim

async def remember_stream_info(url, info):
    """Store already-extracted info so playback doesn't extract the song again."""
    entry = get_primary_entry(info)
    if not url or not entry or not has_usable_media_url(entry):
        return None
    slim = slim_stream_info(entry)
    ttl = min(stream_info_seconds_left(slim), STREAM_MAX_CACHE_TTL)
    if ttl <= 0:
        return None
    for key_url in {url, slim.get("webpage_url")}:
        if key_url:
            await cache_info(get_cache_key(key_url, "audio"), slim, ttl=ttl)
    return slim

async def forget_stream_info(url):
    async with _cache_lock:
        _cache.pop(get_cache_key(url, "audio"), None)

async def _extract_stream_info(url):
    data = await extract_info_with_cookie_fallback(
        url,
        timeout=60.0,
        extra_options={"extract_flat": False, "ignoreerrors": True},
    )
    if not data:
        raise ValueError("Could not extract audio")
    entry = get_primary_entry(data)
    if not entry:
        raise ValueError("Could not extract audio")
    entry["_extracted_at"] = time.time()
    return await remember_stream_info(url, entry) or slim_stream_info(entry)

async def resolve_stream_info(url, force=False):
    """Fresh stream info for a song URL. Concurrent callers share one extraction."""
    if not force:
        cached = await get_cached_info(get_cache_key(url, "audio"))
        if cached and stream_info_seconds_left(cached) > 0:
            return cached
    task = _stream_inflight.get(url)
    if task is None or (force and task.done()):
        task = asyncio.ensure_future(_extract_stream_info(url))
        _stream_inflight[url] = task
        task.add_done_callback(lambda t, u=url: _stream_inflight.pop(u, None) if _stream_inflight.get(u) is t else None)
    return await asyncio.shield(task)

def warm_stream_soon(url):
    """Resolve a song's stream in the background (errors are ignored; playback retries)."""
    if not url:
        return None
    async def _warm():
        try:
            await resolve_stream_info(url)
        except Exception as e:
            logger.debug(f"Prefetch failed for {url}: {e}")
    return asyncio.ensure_future(_warm())

# ═══════════════════════════════════════════════════════════════════
#                        AUDIO SOURCE
# ═══════════════════════════════════════════════════════════════════
import subprocess
import os

class SilentFFmpegPCMAudio(discord.FFmpegPCMAudio):
    """FFmpeg audio source with stderr suppression to prevent console spam."""

    def __init__(self, source, *, executable="ffmpeg", args=None, **kwargs):
        # Properly suppress stderr by using subprocess.PIPE and consuming it
        # Open a null writer that discards all input
        self._null_file = open(os.devnull, 'w')
        kwargs['stderr'] = self._null_file
        self.frames_read = 0
        super().__init__(source, executable=executable, **kwargs)

    def read(self):
        data = super().read()
        if data:
            self.frames_read += 1
        return data

    def failed_without_audio(self):
        """True when ffmpeg exited with an error before producing any audio
        (expired/rotated link, 403...). A user skip leaves ffmpeg running."""
        if self.frames_read > 0:
            return False
        process = getattr(self, "_process", None)
        if process is None:
            return False
        for _ in range(10):
            code = process.poll()
            if code is not None:
                return code != 0
            time.sleep(0.02)
        return False

    def cleanup(self):
        """Clean up the null file."""
        try:
            self._null_file.close()
        except Exception:
            pass
        try:
            super().cleanup()
        except Exception:
            pass

class YTDLSource(discord.PCMVolumeTransformer):
    __slots__ = ("data", "title", "url", "duration", "webpage_url", "extractor", "thumbnail")

    def __init__(self, source, *, data, volume=1.0):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get("title")
        self.url = data.get("url")
        self.duration = data.get("duration")
        self.webpage_url = data.get("webpage_url")
        self.extractor = data.get("extractor", "unknown")
        # Get thumbnail - try multiple possible keys
        self.thumbnail = (data.get("thumbnail") or
                         data.get("cover") or
                         (data.get("thumbnails", [{}])[0].get("url") if data.get("thumbnails") else None))

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=True, volume=1.0):
        loop = loop or asyncio.get_event_loop()

        try:
            data = await resolve_stream_info(url)
        except Exception as e:
            logger.error(f"❌ Audio extraction failed: {e}")
            raise

        if "entries" in data:
            data = data["entries"][0]

        extractor_name = (data.get("extractor") or "").lower()
        candidate_formats = iter_best_audio_formats(data, allow_missing_pot=False)
        fallback_url = data.get("url")
        fallback_headers = data.get("http_headers", {})
        candidate_urls = []

        if extractor_name == "soundcloud":
            # SoundCloud often exposes a direct URL that resolves to an HLS AAC
            # stream, which is the one most likely to open silently here.
            # Prefer ranked formats first so we can pick the direct MP3 HTTP
            # stream before falling back to the extractor's default URL.
            for fmt in candidate_formats:
                candidate_urls.append(
                    {
                        "audio_url": fmt.get("url"),
                        "http_headers": fmt.get("http_headers", {}),
                        "format_id": fmt.get("format_id"),
                        "format_note": fmt.get("format_note"),
                        "protocol": fmt.get("protocol"),
                        "ext": fmt.get("ext"),
                    }
                )
            if fallback_url:
                candidate_urls.append(
                    {
                        "audio_url": fallback_url,
                        "http_headers": fallback_headers,
                        "format_id": data.get("format_id"),
                        "format_note": data.get("format_note"),
                        "protocol": data.get("protocol"),
                        "ext": data.get("ext"),
                    }
                )
        else:
            if fallback_url:
                candidate_urls.append(
                    {
                        "audio_url": fallback_url,
                        "http_headers": fallback_headers,
                        "format_id": data.get("format_id"),
                        "format_note": data.get("format_note"),
                        "protocol": data.get("protocol"),
                        "ext": data.get("ext"),
                    }
                )

            for fmt in candidate_formats:
                candidate_urls.append(
                    {
                        "audio_url": fmt.get("url"),
                        "http_headers": fmt.get("http_headers", {}),
                        "format_id": fmt.get("format_id"),
                        "format_note": fmt.get("format_note"),
                        "protocol": fmt.get("protocol"),
                        "ext": fmt.get("ext"),
                    }
                )

        if not candidate_urls:
            raise ValueError("No audio URL found")

        base_opts = ffmpeg_options.copy()
        last_error = None

        for candidate in candidate_urls:
            audio_url = candidate["audio_url"]
            http_headers = candidate["http_headers"] or {}
            opts = base_opts.copy()
            is_hls = "m3u8" in (candidate.get("protocol") or "") or ".m3u8" in (audio_url or "")
            if is_hls:
                # Every HLS segment ends in EOF; with -reconnect_at_eof ffmpeg
                # reconnects forever and never outputs audio (silent SoundCloud).
                opts["before_options"] = opts["before_options"].replace("-reconnect_at_eof 1 ", "")
            if http_headers:
                # Pass ALL headers yt-dlp extracted (not just UA/Referer).
                # YouTube requires Accept, Accept-Language, Sec-Fetch-Mode, etc.
                header_args = ""
                for key, value in http_headers.items():
                    header_args += f"-headers '{key}: {value}' "
                ua = http_headers.get("User-Agent", "Mozilla/5.0")
                ref = http_headers.get("Referer", "https://www.youtube.com/")
                opts["before_options"] = f"{header_args}-user_agent \"{ua}\" -referer \"{ref}\" " + opts["before_options"]

            try:
                if sys.platform == "win32":
                    source = SilentFFmpegPCMAudio(audio_url, **opts, executable=FFMPEG_PATH)
                else:
                    source = (
                        SilentFFmpegPCMAudio(audio_url, **opts)
                        if FFMPEG_PATH == "ffmpeg"
                        else SilentFFmpegPCMAudio(audio_url, **opts, executable=FFMPEG_PATH)
                    )
                logger.info(
                    f"🎧 {extractor_name or 'stream'} selected: {candidate.get('format_id') or 'direct'}"
                    + (f" ({candidate.get('format_note')})" if candidate.get("format_note") else "")
                )
                return cls(source, data={**data, "url": audio_url, "http_headers": http_headers}, volume=volume)
            except Exception as e:
                last_error = e
                logger.debug(
                    f"SoundCloud candidate failed: {candidate.get('format_id')} / {candidate.get('format_note')}: {e}"
                )

        logger.error(f"❌ FFmpeg failed: {last_error}")
        raise last_error

# ═══════════════════════════════════════════════════════════════════
#                          BOT SETUP
# ═══════════════════════════════════════════════════════════════════
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.voice_states = True

def get_prefix(bot, message):
    return commands.when_mentioned_or(*PREFIXES)(bot, message)

bot = commands.Bot(
    command_prefix=get_prefix,
    description="Music Bot",
    intents=intents,
    help_command=None,
    heartbeat_timeout=HEARTBEAT_TIMEOUT,
    chunk_guilds_at_startup=False,
    max_messages=100,
)

# ═══════════════════════════════════════════════════════════════════
#                        MUSIC STATE
# ═══════════════════════════════════════════════════════════════════
class GuildMusicState:
    __slots__ = (
        "queue",
        "current",
        "is_playing",
        "loop_mode",
        "loop_count",
        "loop_remaining",
        "loop_announced",
        "volume",
        "skipped_count",
        "was_stopped",
        "is_fetching_playlist",
        "current_playlist_id",
        "playlist_groups",
        "idle_since",
    )

    def __init__(self):
        self.queue = deque()
        self.current = None
        self.is_playing = False
        self.loop_mode = False
        self.loop_count = None
        self.loop_remaining = 0
        self.loop_announced = False
        self.volume = 1.0
        self.skipped_count = 0
        self.was_stopped = False
        self.is_fetching_playlist = False
        self.current_playlist_id = 0
        self.playlist_groups = {}
        self.idle_since = None

    def add_song(self, url, title, playlist_id=None):
        song = {"url": url, "title": title}
        if playlist_id is not None:
            song["playlist_id"] = playlist_id
        self.queue.append(song)
        if playlist_id is not None:
            if playlist_id not in self.playlist_groups:
                self.playlist_groups[playlist_id] = []
            self.playlist_groups[playlist_id].append(song)

    def next_song(self):
        return self.queue.popleft() if self.queue else None

    def clear(self):
        self.queue.clear()
        self.current = None
        self.is_playing = False
        self.skipped_count = 0
        self.is_fetching_playlist = False
        self.idle_since = None
        self.playlist_groups.clear()
        self.current_playlist_id = 0
        self.reset_loop()

    def reset_loop(self):
        self.loop_mode = False
        self.loop_count = None
        self.loop_remaining = 0
        self.loop_announced = False

    def enable_loop(self, count=None):
        self.loop_mode = True
        self.loop_count = count
        self.loop_remaining = count if count else 0
        self.loop_announced = False

    def disable_loop(self):
        self.reset_loop()

    def should_loop(self):
        if not self.loop_mode:
            return False
        if self.loop_count is None:
            return True
        return self.loop_remaining > 0

    def decrement_loop(self):
        if self.loop_count is not None and self.loop_remaining > 0:
            self.loop_remaining -= 1
            if self.loop_remaining <= 0:
                self.reset_loop()
                return True
        return False

    def get_loop_status(self):
        if not self.loop_mode:
            return None
        return "∞" if self.loop_count is None else f"{self.loop_remaining}/{self.loop_count}"

    def set_volume(self, vol):
        self.volume = max(0.0, min(2.0, vol))

    def get_volume_percent(self):
        return int(self.volume * 100)

music_states = {}
background_tasks = {}
playlist_fetch_queues = {}
prefetch_tasks = {}

# Per-guild lock to prevent concurrent play_next races
_play_next_locks = {}

def get_play_next_lock(guild_id):
    lock = _play_next_locks.get(guild_id)
    if lock is None:
        lock = asyncio.Lock()
        _play_next_locks[guild_id] = lock
    return lock

def get_state(guild_id):
    if guild_id not in music_states:
        music_states[guild_id] = GuildMusicState()
    return music_states[guild_id]

def cancel_prefetch(guild_id):
    task = prefetch_tasks.pop(guild_id, None)
    if task and not task.done():
        task.cancel()

def schedule_prefetch(guild_id, current_duration=None):
    """Resolve the next song's stream while the current one plays, so the
    transition doesn't wait on extraction. Re-checked near the end of the
    current song in case the link would expire before it's needed."""
    cancel_prefetch(guild_id)

    async def _prefetch():
        started = time.time()
        try:
            await asyncio.sleep(1.5)  # let the current stream get going first
            for attempt in range(2):
                state = music_states.get(guild_id)
                if state and state.queue and not state.should_loop():
                    url = state.queue[0].get("url")
                    if url:
                        try:
                            await resolve_stream_info(url)
                        except Exception as e:
                            logger.debug(f"Prefetch failed for {url}: {e}")
                if attempt == 0:
                    if not current_duration or current_duration < 90:
                        return
                    await asyncio.sleep(max(0, started + current_duration - 45 - time.time()))
        except asyncio.CancelledError:
            pass

    prefetch_tasks[guild_id] = asyncio.ensure_future(_prefetch())

def cancel_background_tasks(guild_id):
    cancel_prefetch(guild_id)
    if guild_id in background_tasks:
        task = background_tasks[guild_id]
        if not task.done():
            task.cancel()
        del background_tasks[guild_id]
    if guild_id in playlist_fetch_queues:
        playlist_fetch_queues[guild_id].clear()
        del playlist_fetch_queues[guild_id]

# ═══════════════════════════════════════════════════════════════════
#                     MUSIC CONTROLS VIEW
# ═══════════════════════════════════════════════════════════════════
class MusicControlView(View):
    """Interactive buttons for music control."""

    def __init__(self, guild_id, bot_ref):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.bot = bot_ref
        self.message = None  # Store the message this view is attached to
        self.update_buttons()

    def update_buttons(self):
        """Update button states based on current music state."""
        state = get_state(self.guild_id)
        vc = get_guild_voice_client(self.guild_id)

        is_paused = vc and vc.is_paused() if vc else False
        is_playing = vc and vc.is_playing() if vc else False
        has_queue = len(state.queue) > 0

        # Pause/Resume button
        self.pause_resume_button.label = "Resume" if is_paused else "Pause"
        self.pause_resume_button.style = discord.ButtonStyle.green if is_paused else discord.ButtonStyle.secondary
        self.pause_resume_button.emoji = "▶️" if is_paused else "⏸️"

        # Skip button
        self.skip_button.disabled = not (is_playing or is_paused)

        # Stop button
        self.stop_button.disabled = not (is_playing or is_paused)

        # Queue button
        self.queue_button.disabled = not has_queue and not state.current

        # Volume button
        self.volume_button.disabled = not (is_playing or is_paused)

        # Clear button
        self.clear_button.disabled = not has_queue

        # Loop button
        if state.loop_mode:
            self.loop_button.style = discord.ButtonStyle.success
            loop_status = state.get_loop_status()
            self.loop_button.label = f"Loop {loop_status}" if loop_status != "∞" else "Loop ∞"
        else:
            self.loop_button.style = discord.ButtonStyle.secondary
            self.loop_button.label = "Loop"

        # Reset button
        self.reset_player_button.disabled = not (state.current or is_playing or is_paused)

    @discord.ui.button(label="Pause", style=discord.ButtonStyle.secondary, emoji="⏸️", row=0)
    async def pause_resume_button(self, interaction: discord.Interaction, button: Button):
        state = get_state(self.guild_id)
        vc = None

        for guild in self.bot.guilds:
            if guild.id == self.guild_id:
                vc = guild.voice_client
                break

        if not vc:
            await interaction.response.send_message("❌ Not in voice channel", ephemeral=True)
            return

        if vc.is_paused():
            # Resume
            vc.resume()
            state.is_playing = True
            _log_action("RESUMED", "▶️")
        elif vc.is_playing():
            # Pause
            vc.pause()
            state.is_playing = False
            _log_action("PAUSED", "⏸️")
        else:
            await interaction.response.send_message("❌ Nothing playing", ephemeral=True)
            return

        self.update_buttons()
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="Skip", style=discord.ButtonStyle.secondary, emoji="⏭️", row=0)
    async def skip_button(self, interaction: discord.Interaction, button: Button):
        state = get_state(self.guild_id)
        vc = None

        for guild in self.bot.guilds:
            if guild.id == self.guild_id:
                vc = guild.voice_client
                break

        if not vc:
            await interaction.response.send_message("❌ Not in voice channel", ephemeral=True)
            return

        if not vc.is_playing() and not vc.is_paused():
            await interaction.response.send_message("❌ Nothing playing", ephemeral=True)
            return

        if state.loop_mode:
            state.disable_loop()

        vc.stop()
        _log_action("SKIPPED 1 SONG", "⏭️")

        self.update_buttons()
        await interaction.response.edit_message(view=self)

    async def update_embed(self, title, extractor, duration=None, thumbnail=None, url=None):
        """Update the embed with new song info."""
        state = get_state(self.guild_id)
        if not self.message:
            return

        emoji = get_platform_emoji(extractor)
        vol = f" {get_volume_emoji(state.volume)}" if state.volume != 1.0 else ""
        loop_info = ""

        if state.loop_mode:
            loop_status = state.get_loop_status()
            loop_info = f" 🔁 {loop_status}"

        # Create new embed
        embed = discord.Embed(
            title=f"{emoji} Now Playing",
            description=f"**{title}**{vol}",
            color=0x5865F2,
            url=url  # Click title to open song
        )

        # Add thumbnail if available
        if thumbnail:
            embed.set_thumbnail(url=thumbnail)

        # Add song link
        if url:
            embed.add_field(name="🔗 Link", value=f"[Click here]({url})", inline=True)

        # Add queue info (just count, clean format)
        queue_len = len(state.queue)
        if queue_len > 0:
            embed.add_field(
                name="📜 Queue",
                value=f"{queue_len} song{'s' if queue_len != 1 else ''} queued",
                inline=False
            )
        else:
            embed.add_field(
                name="📜 Queue",
                value="0 songs queued",
                inline=False
            )

        # Add loop info if active
        if state.loop_mode:
            embed.add_field(name="🔁 Loop", value=state.get_loop_status(), inline=True)

        # Add volume info
        embed.add_field(name="🔊 Volume", value=f"{state.get_volume_percent()}%", inline=True)

        try:
            await self.message.edit(embed=embed, view=self)
        except Exception:
            pass

    @discord.ui.button(label="Stop", style=discord.ButtonStyle.danger, emoji="⏹️", row=0)
    async def stop_button(self, interaction: discord.Interaction, button: Button):
        state = get_state(self.guild_id)
        vc = None

        for guild in self.bot.guilds:
            if guild.id == self.guild_id:
                vc = guild.voice_client
                break

        if not vc:
            await interaction.response.send_message("❌ Not in voice channel", ephemeral=True)
            return

        cancel_background_tasks(self.guild_id)
        state.was_stopped = True
        state.clear()

        if vc.is_playing():
            vc.stop()

        await interaction.response.edit_message(content="⏹️ Stopped", embed=None, view=None)
        _log_action("STOPPED & CLEARED QUEUE", "⏹️")

    @discord.ui.button(label="Queue", style=discord.ButtonStyle.blurple, emoji="📜", row=0)
    async def queue_button(self, interaction: discord.Interaction, button: Button):
        state = get_state(self.guild_id)

        if not state.queue and not state.current:
            await interaction.response.send_message("📭 Queue is empty", ephemeral=True)
            return

        total = len(state.queue) + (1 if state.current else 0)
        embed = discord.Embed(
            title="🎵 Queue",
            description=f"**{total} track{'s' if total != 1 else ''} total**",
            color=0x7289DA,
        )

        if state.current:
            loop_info = f" 🔁 {state.get_loop_status()}" if state.loop_mode else ""
            embed.add_field(
                name="🎶 Now Playing",
                value=f"**{state.current['title'][:60]}**{loop_info}",
                inline=False,
            )

        if state.queue:
            songs = list(state.queue)[:10]
            text = "\n".join([f"`{i+1:>2}.` {s['title'][:50]}" for i, s in enumerate(songs)])
            if len(state.queue) > 10:
                text += f"\n`   ` *…and {len(state.queue) - 10} more*"
            embed.add_field(name=f"📜 Up Next ({len(state.queue)})", value=text, inline=False)

        footer_parts = []
        if state.loop_mode:
            footer_parts.append(f"🔁 Loop: {state.get_loop_status()}")
        footer_parts.append(f"🔊 {state.get_volume_percent()}%")
        embed.set_footer(text=" • ".join(footer_parts))
        embed.timestamp = discord.utils.utcnow()

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Volume", style=discord.ButtonStyle.success, emoji="🔊", row=1)
    async def volume_button(self, interaction: discord.Interaction, button: Button):
        state = get_state(self.guild_id)
        vol = state.get_volume_percent()

        await interaction.response.send_message(
            f"🔊 Current Volume: **{vol}%**\n"
            f"Use `{PREFIX}volume <0-200>` to change it.",
            ephemeral=True
        )

    @discord.ui.button(label="Clear", style=discord.ButtonStyle.secondary, emoji="🗑️", row=1)
    async def clear_button(self, interaction: discord.Interaction, button: Button):
        state = get_state(self.guild_id)

        if not state.queue and not state.loop_mode:
            await interaction.response.send_message("❌ Queue already empty", ephemeral=True)
            return

        cancel_background_tasks(self.guild_id)
        count = len(state.queue)
        state.queue.clear()

        loop_stopped = False
        if state.loop_mode:
            state.disable_loop()
            loop_stopped = True

        parts = []
        if count > 0:
            parts.append(f"🗑️ Cleared **{count}** song{'s' if count != 1 else ''}")
        if loop_stopped:
            parts.append("🔁 Loop stopped")

        _log_action(f"CLEARED {count} SONGS" + (" & LOOP" if loop_stopped else ""), "🗑️")

        self.update_buttons()
        embed = await build_now_playing_embed(self.guild_id)
        if embed:
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.edit_message(view=self)

    @discord.ui.button(label="Loop", style=discord.ButtonStyle.secondary, emoji="🔁", row=1)
    async def loop_button(self, interaction: discord.Interaction, button: Button):
        state = get_state(self.guild_id)
        vc = None

        for guild in self.bot.guilds:
            if guild.id == self.guild_id:
                vc = guild.voice_client
                break

        if not vc or (not vc.is_playing() and not vc.is_paused()):
            await interaction.response.send_message("❌ Nothing playing", ephemeral=True)
            return

        if not state.current:
            await interaction.response.send_message("❌ No track to loop", ephemeral=True)
            return

        if state.loop_mode:
            # Disable loop
            state.disable_loop()
            button.style = discord.ButtonStyle.secondary
            button.label = "Loop"
            _log_action("LOOP DISABLED", "🔁")
        else:
            # Enable loop (infinite)
            state.enable_loop(None)
            button.style = discord.ButtonStyle.success
            button.label = "Loop ∞"
            _log_action("LOOP ENABLED: ∞", "🔁")

        self.update_buttons()
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="Reset Player", style=discord.ButtonStyle.secondary, emoji="♻️", row=1)
    async def reset_player_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer(ephemeral=True)
        ok, message = await reset_player_panel_message(interaction.channel, self.guild_id)
        if not ok:
            await interaction.followup.send(message, ephemeral=True)
            return

        await interaction.followup.send(message, ephemeral=True)

# Store active views for each guild
active_music_views = {}

# Track the current player panel message for each guild.
player_panel_messages = {}
player_message_locks = {}

# Store "Queue finished" messages to delete them when new songs queue
queue_finished_messages = {}

def get_player_message_lock(guild_id):
    lock = player_message_locks.get(guild_id)
    if lock is None:
        lock = asyncio.Lock()
        player_message_locks[guild_id] = lock
    return lock

async def cleanup_queue_finished_message(guild_id):
    message = queue_finished_messages.pop(guild_id, None)
    if not message:
        return
    try:
        await message.delete()
    except discord.NotFound:
        pass
    except Exception as e:
        logger.debug(f"Could not delete queue finished message {message.id}: {e}")

async def cleanup_player_messages(guild_id, keep_message=None):
    message = player_panel_messages.get(guild_id)
    if not message:
        return

    keep_id = keep_message.id if keep_message else None

    if keep_id and message.id == keep_id:
        return
    try:
        await message.delete()
    except discord.NotFound:
        pass
    except Exception as e:
        logger.debug(f"Could not delete old player message {message.id}: {e}")

    player_panel_messages.pop(guild_id, None)

async def remove_player_panel(guild_id):
    message = player_panel_messages.get(guild_id)
    channel = message.channel if message else None
    await cleanup_player_messages(guild_id)
    view = active_music_views.pop(guild_id, None)
    if view:
        view.message = None
    if channel:
        await cleanup_channel_player_messages(channel)

def is_music_panel_message(message):
    if not message or not bot.user or message.author.id != bot.user.id or not message.embeds:
        return False
    title = message.embeds[0].title or ""
    return title.endswith("Now Playing") or title.endswith("Queued")

async def cleanup_channel_player_messages(channel, keep_message=None, limit=50):
    if not channel or not hasattr(channel, "history"):
        return

    keep_id = keep_message.id if keep_message else None

    try:
        async for message in channel.history(limit=limit):
            if keep_id and message.id == keep_id:
                continue
            if not is_music_panel_message(message):
                continue
            try:
                await message.delete()
            except discord.NotFound:
                pass
            except Exception as e:
                logger.debug(f"Could not delete scanned player message {message.id}: {e}")
    except Exception as e:
        logger.debug(f"Could not scan channel history for player cleanup: {e}")

def get_guild_voice_client(guild_id):
    guild = bot.get_guild(guild_id)
    return guild.voice_client if guild else None

def is_guild_idle(guild_id, state=None, vc=None):
    if state is None:
        state = get_state(guild_id)
    if vc is None:
        vc = get_guild_voice_client(guild_id)
    if not vc or not vc.is_connected():
        return False
    if state.queue or state.is_fetching_playlist or state.is_playing:
        return False
    if vc.is_playing() or vc.is_paused():
        return False
    return True

async def clear_idle_guild(guild_id):
    state = music_states.get(guild_id)
    vc = get_guild_voice_client(guild_id)
    if not state:
        return

    cancel_background_tasks(guild_id)
    state.was_stopped = True
    state.clear()

    await cleanup_queue_finished_message(guild_id)
    await remove_player_panel(guild_id)

    if vc and vc.is_connected():
        try:
            if vc.is_playing() or vc.is_paused():
                vc.stop()
        except Exception as e:
            logger.debug(f"Could not stop voice client for idle cleanup in guild {guild_id}: {e}")

        try:
            await vc.disconnect()
        except Exception as e:
            logger.debug(f"Could not disconnect idle voice client in guild {guild_id}: {e}")

    logger.info(f"🛌 Idle cleanup completed for guild {guild_id}")

async def build_now_playing_embed(guild_id):
    state = get_state(guild_id)
    if not state.current:
        return None

    vc = get_guild_voice_client(guild_id)
    source = getattr(vc, "source", None) if vc else None

    title = getattr(source, "title", None) or state.current.get("title", "Unknown")
    url = getattr(source, "webpage_url", None) or state.current.get("url", "")
    duration = getattr(source, "duration", None)
    thumbnail = getattr(source, "thumbnail", None)
    extractor = getattr(source, "extractor", None) or state.current.get("extractor", "generic")

    if state.current.get("url") and (not thumbnail or not duration or extractor == "generic"):
        # Use cache only — avoid a blocking yt-dlp extraction that would
        # stall commands (pause/resume/volume/queue/etc.) for up to 30s.
        try:
            current_data = await get_cached_info(get_cache_key(state.current["url"], "single"))
        except Exception:
            current_data = None

        if current_data:
            url = url or current_data.get("webpage_url") or state.current.get("url", "")
            duration = duration or current_data.get("duration")
            thumbnail = thumbnail or current_data.get("thumbnail")
            extractor = current_data.get("extractor", extractor)

    emoji = get_platform_emoji(extractor)
    vol = f" {get_volume_emoji(state.volume)}" if state.volume != 1.0 else ""

    embed = discord.Embed(
        title=f"{emoji} Now Playing",
        description=f"**{rtl_format(title)}**{vol}",
        color=0x5865F2,
        url=url
    )

    if thumbnail:
        embed.set_thumbnail(url=thumbnail)

    if url:
        embed.add_field(name="🔗 Link", value=f"[Click here]({url})", inline=True)

    if duration:
        minutes, seconds = divmod(duration, 60)
        embed.add_field(name="⏱️ Duration", value=f"{int(minutes)}:{int(seconds):02d}", inline=True)

    queue_len = len(state.queue)
    if queue_len > 0:
        up_next_title = state.queue[0]["title"][:50]
        embed.add_field(
            name="📜 Queue",
            value=f"{queue_len} song{'s' if queue_len != 1 else ''} queued\n🎵 **Up next:** {up_next_title}",
            inline=False
        )
    else:
        embed.add_field(
            name="📜 Queue",
            value="0 songs queued",
            inline=False
        )

    if state.loop_mode:
        embed.add_field(name="🔁 Loop", value=state.get_loop_status(), inline=True)

    embed.add_field(name="🔊 Volume", value=f"{state.get_volume_percent()}%", inline=True)

    # Footer with context
    footer_parts = []
    if queue_len > 0:
        footer_parts.append(f"{queue_len} in queue")
    if state.loop_mode:
        footer_parts.append(f"🔁 {state.get_loop_status()}")
    footer_parts.append(f"🔊 {state.get_volume_percent()}%")
    embed.set_footer(text=" • ".join(footer_parts))

    embed.timestamp = discord.utils.utcnow()
    return embed


async def send_fresh_music_message(ctx, guild_id, embed, cleanup_stale=False):
    """Send a new music embed at channel bottom and replace old control message."""
    async with get_player_message_lock(guild_id):
        previous_message = player_panel_messages.get(guild_id)
        view = active_music_views.get(guild_id)
        if not view:
            view = MusicControlView(guild_id, bot)
            active_music_views[guild_id] = view

        view.update_buttons()

        message = await ctx.send(embed=embed, view=view)
        view.message = message
        if previous_message:
            await cleanup_player_messages(guild_id, keep_message=message)
        player_panel_messages[guild_id] = message
        if cleanup_stale or previous_message is None:
            channel = getattr(ctx, "channel", None)
            if channel is None and hasattr(message, "channel"):
                channel = message.channel
            await cleanup_channel_player_messages(channel, keep_message=message)

async def refresh_player_panel(ctx, guild_id):
    embed = await build_now_playing_embed(guild_id)
    if embed:
        await send_fresh_music_message(ctx, guild_id, embed)

async def reset_player_panel_message(channel, guild_id):
    state = get_state(guild_id)
    vc = get_guild_voice_client(guild_id)

    if not state.current and not (vc and (vc.is_playing() or vc.is_paused())):
        return False, "❌ Nothing to reset"

    embed = await build_now_playing_embed(guild_id)
    if not embed:
        return False, "❌ Could not rebuild player"

    await send_fresh_music_message(channel, guild_id, embed, cleanup_stale=True)
    return True, "♻️ Player reset"

# RTL (Right-to-Left) support for Arabic text
def is_arabic(text):
    """Check if text contains Arabic characters."""
    if not text:
        return False
    return any('\u0600' <= char <= '\u06FF' for char in text)

def rtl_format(text):
    """Format text with RTL markers if Arabic."""
    if is_arabic(text):
        return f"\u202B{text}\u202C"  # RTL Embedding markers
    return text

# ═══════════════════════════════════════════════════════════════════
#                       HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════
def is_bot_owner():
    async def predicate(ctx):
        if not OWNER_ID:
            await ctx.send("❌ Owner not configured")
            return False
        return str(ctx.author.id) == OWNER_ID
    return commands.check(predicate)

def create_volume_bar(volume):
    filled = int(volume * 20)
    chars = ["▁", "▃", "▅", "▇"]
    char = chars[min(filled // 5, 3)]
    return f"`╣{char * filled}{'░' * (20 - filled)}╠`"

def get_volume_emoji(volume):
    pct = int(volume * 100)
    if pct == 0:
        return "🔇"
    if pct <= 30:
        return "🔈"
    if pct <= 70:
        return "🔉"
    if pct <= 100:
        return "🔊"
    return "📢"

def is_youtube_mix(url):
    return "list=RD" in url or "list=rd" in url.lower()

def is_playlist_url(url):
    indicators = ["list=", "playlist", "set/", "/album", "/album/", "/sets", "sets/", "/playlist/", "on.soundcloud.com"]
    return any(i in url.lower() for i in indicators)

def is_youtube_url(url):
    return any(d in url.lower() for d in ["youtube.com", "youtu.be", "m.youtube.com"])

def is_soundcloud_url(url):
    return "soundcloud.com" in url.lower()

def is_soundcloud_short_url(url):
    return "on.soundcloud.com" in (url or "").lower()

async def resolve_soundcloud_url(url, timeout=15.0):
    if not is_soundcloud_short_url(url):
        return url

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    try:
        timeout_obj = aiohttp.ClientTimeout(total=timeout)
        async with aiohttp.ClientSession(headers=headers, timeout=timeout_obj) as session:
            async with session.get(url, allow_redirects=True) as resp:
                final_url = str(resp.url)
                return final_url or url
    except Exception:
        return url

# ─────────────────────────────────────────────────────────────────
#   SPOTIFY → YOUTUBE
#   Spotify audio needs a login, so we only read public metadata
#   (title/artist/duration) from the embed page and play the
#   matching track from YouTube instead.
# ─────────────────────────────────────────────────────────────────
SPOTIFY_URL_RE = re.compile(
    r"(?:open\.spotify\.com/(?:intl-[a-z]{2}(?:-[a-z]{2})?/)?(?:embed/)?|spotify:)"
    r"(track|album|playlist)[/:]([A-Za-z0-9]{22})",
    re.IGNORECASE,
)
SPOTIFY_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S
)
SPOTIFY_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
SPOTIFY_RESOLVE_CONCURRENCY = 4
# Words that mark a different version of a song; penalised unless the
# Spotify title itself contains them.
SPOTIFY_VERSION_WORDS = (
    "live", "cover", "remix", "karaoke", "instrumental", "8d", "slowed",
    "sped up", "reverb", "nightcore", "1 hour", "loop", "432hz", "acapella",
    "a cappella", "bass boosted", "bassboosted", "reaction",
)
SPOTIFY_TOKEN_RE = re.compile(r"\w+", re.UNICODE)

# ─────────────────────────────────────────────────────────────────
#   FAST YOUTUBE SEARCH
#   Asks YouTube's own search endpoint directly over a reused HTTPS
#   connection (~0.5s vs ~1.5s through yt-dlp). If YouTube changes the
#   response shape we fall back to yt-dlp's search, so nothing breaks.
# ─────────────────────────────────────────────────────────────────
YT_SEARCH_ENDPOINT = "https://www.youtube.com/youtubei/v1/search?prettyPrint=false"
YT_SEARCH_CLIENT = {"clientName": "WEB", "clientVersion": "2.20251001.01.00", "hl": "en", "gl": "US"}
YT_SEARCH_VIDEOS_ONLY = "EgIQAQ%3D%3D"
_http_session = None

def get_http_session():
    global _http_session
    if _http_session is None or _http_session.closed:
        _http_session = aiohttp.ClientSession(
            headers={
                "User-Agent": SPOTIFY_HEADERS["User-Agent"],
                "Accept-Language": "en-US,en;q=0.9",
            },
            timeout=aiohttp.ClientTimeout(total=10),
        )
    return _http_session

def _parse_length_text(text):
    try:
        seconds = 0
        for part in (text or "").split(":"):
            seconds = seconds * 60 + int(part)
        return seconds or None
    except ValueError:
        return None

def _collect_video_renderers(node, out, limit):
    if len(out) >= limit:
        return
    if isinstance(node, dict):
        video = node.get("videoRenderer")
        if isinstance(video, dict) and video.get("videoId"):
            runs = (video.get("title") or {}).get("runs") or []
            owner = (video.get("ownerText") or video.get("longBylineText") or {}).get("runs") or []
            thumbs = (video.get("thumbnail") or {}).get("thumbnails") or []
            out.append({
                "id": video["videoId"],
                "title": "".join(r.get("text", "") for r in runs),
                "duration": _parse_length_text((video.get("lengthText") or {}).get("simpleText")),
                "channel": owner[0].get("text", "") if owner else "",
                "thumbnail": thumbs[-1].get("url") if thumbs else None,
            })
            return
        for value in node.values():
            _collect_video_renderers(value, out, limit)
    elif isinstance(node, list):
        for value in node:
            _collect_video_renderers(value, out, limit)
            if len(out) >= limit:
                return

async def _innertube_search(query, limit):
    payload = {"context": {"client": YT_SEARCH_CLIENT}, "query": query, "params": YT_SEARCH_VIDEOS_ONLY}
    kwargs = {"json": payload}
    if PROXY:
        kwargs["proxy"] = PROXY
    async with get_http_session().post(YT_SEARCH_ENDPOINT, **kwargs) as resp:
        if resp.status != 200:
            raise ValueError(f"HTTP {resp.status}")
        data = await resp.json(content_type=None)
    results = []
    _collect_video_renderers(data.get("contents") or data, results, limit)
    return results

async def _ytdlp_search(query, limit):
    info = await extract_processed_info_with_cookie_fallback(
        f"ytsearch{limit}:{query}",
        timeout=30.0,
        extra_options={
            "noplaylist": True,
            "extract_flat": "in_playlist",
            "ignoreerrors": True,
            "skip_download": True,
        },
    )
    results = []
    for entry in (info or {}).get("entries") or []:
        if entry and entry.get("id"):
            results.append({
                "id": entry["id"],
                "title": entry.get("title") or "",
                "duration": entry.get("duration"),
                "channel": entry.get("channel") or entry.get("uploader") or "",
                "thumbnail": (entry.get("thumbnails") or [{}])[-1].get("url"),
            })
    return results

async def search_youtube(query, limit=1):
    """[{"id", "title", "duration", "channel", "thumbnail", "url"}], best first."""
    results = []
    try:
        results = await _innertube_search(query, limit)
    except Exception as e:
        logger.debug(f"Fast search failed ({e}), using yt-dlp search")
    if not results:
        try:
            results = await _ytdlp_search(query, limit)
        except Exception as e:
            logger.debug(f"yt-dlp search failed for {query}: {e}")
            results = []
    for r in results:
        r["url"] = f"https://www.youtube.com/watch?v={r['id']}"
    return results

def is_spotify_url(url):
    lowered = (url or "").lower()
    return (
        "open.spotify.com/" in lowered
        or "spotify.link/" in lowered
        or "spotify.app.link/" in lowered
        or lowered.startswith("spotify:")
    )

async def resolve_spotify_url(url, timeout=15.0):
    """Follow spotify.link / spotify.app.link short links to the open.spotify.com URL."""
    if SPOTIFY_URL_RE.search(url):
        return url
    try:
        timeout_obj = aiohttp.ClientTimeout(total=timeout)
        async with aiohttp.ClientSession(headers=SPOTIFY_HEADERS, timeout=timeout_obj) as session:
            async with session.get(url, allow_redirects=True) as resp:
                final_url = str(resp.url)
                if SPOTIFY_URL_RE.search(final_url):
                    return final_url
                # Some short links land on an HTML page that holds the real URL
                body = await resp.text(errors="ignore")
                match = SPOTIFY_URL_RE.search(body)
                if match:
                    return f"https://open.spotify.com/{match.group(1)}/{match.group(2)}"
    except Exception as e:
        logger.debug(f"Spotify short link resolve failed: {e}")
    return url

async def fetch_spotify_metadata(url, timeout=15.0):
    """Return {"kind", "title", "tracks": [{"title", "artist", "duration"}]} or None."""
    url = await resolve_spotify_url(url)
    match = SPOTIFY_URL_RE.search(url)
    if not match:
        return None
    kind, spotify_id = match.group(1).lower(), match.group(2)

    cache_key = get_cache_key(f"spotify:{kind}:{spotify_id}", "meta")
    cached = await get_cached_info(cache_key)
    if cached:
        return cached

    embed_url = f"https://open.spotify.com/embed/{kind}/{spotify_id}"
    try:
        async with get_http_session().get(
            embed_url,
            headers=SPOTIFY_HEADERS,
            timeout=aiohttp.ClientTimeout(total=timeout),
            **({"proxy": PROXY} if PROXY else {}),
        ) as resp:
            if resp.status != 200:
                logger.error(f"❌ Spotify embed returned HTTP {resp.status} for {kind} {spotify_id}")
                return None
            html = await resp.text()
        data_match = SPOTIFY_NEXT_DATA_RE.search(html)
        if not data_match:
            logger.error("❌ Spotify embed page had no metadata")
            return None
        entity = json.loads(data_match.group(1))["props"]["pageProps"]["state"]["data"]["entity"]
    except Exception as e:
        logger.error(f"❌ Spotify metadata fetch failed: {e}")
        return None

    tracks = []
    if kind == "track":
        artists = ", ".join(a.get("name", "") for a in entity.get("artists") or [] if a.get("name"))
        tracks.append({
            "title": entity.get("name") or entity.get("title") or "",
            "artist": artists,
            "duration": (entity.get("duration") or 0) / 1000,
        })
    else:
        for item in entity.get("trackList") or []:
            if item.get("entityType", "track") != "track":
                continue  # skip podcast episodes
            tracks.append({
                "title": item.get("title") or "",
                "artist": re.sub(r"\s*,\s*", ", ", (item.get("subtitle") or "").replace("\xa0", " ")).strip(),
                "duration": (item.get("duration") or 0) / 1000,
            })
    tracks = [t for t in tracks if t["title"]]
    if not tracks:
        return None

    result = {
        "kind": kind,
        "title": entity.get("name") or entity.get("title") or "Spotify",
        "tracks": tracks[:PLAYLIST_LIMIT],
    }
    await cache_info(cache_key, result, ttl=PLAYLIST_CACHE_TTL)
    return result

def spotify_display_title(track):
    return f"{track['artist']} - {track['title']}" if track.get("artist") else track["title"]

def _spotify_tokens(text):
    return set(SPOTIFY_TOKEN_RE.findall((text or "").lower()))

def _score_youtube_match(entry, track):
    """Lower is better; None means the candidate is probably a different song."""
    yt_title = (entry.get("title") or "").lower()
    sp_title = track["title"].lower()
    yt_tokens = _spotify_tokens(yt_title)

    # Compare the core title (no "(feat. X)" / "- Remastered" suffixes) by tokens,
    # so mixed Arabic/Latin titles still match.
    core_tokens = _spotify_tokens(re.split(r" [(\[]| - ", sp_title)[0]) or _spotify_tokens(sp_title)
    title_hit = len(core_tokens & yt_tokens) / max(len(core_tokens), 1) >= 0.5

    artists = [a.strip().lower() for a in (track.get("artist") or "").split(",") if a.strip()]
    channel = (entry.get("channel") or entry.get("uploader") or "").lower()
    artist_hit = any(a in channel or a in yt_title for a in artists)

    yt_duration = entry.get("duration")
    diff = abs(yt_duration - track["duration"]) if (yt_duration and track.get("duration")) else None

    if not title_hit and not (artist_hit and diff is not None and diff <= 5):
        return None

    score = 30.0 if diff is None else (diff if diff <= 15 else 15 + diff * 2)
    for word in SPOTIFY_VERSION_WORDS:
        pattern = rf"(?<!\w){re.escape(word)}(?!\w)"
        if re.search(pattern, yt_title) and not re.search(pattern, sp_title):
            score += 60
    if not title_hit:
        score += 25
    if artist_hit:
        score -= 10
    return score

async def _search_youtube_candidates(query):
    return await search_youtube(query, limit=5)

async def find_spotify_track_on_youtube(track):
    """Search YouTube for a Spotify track. Returns {"url", "title"} or None."""
    base_query = spotify_display_title(track)
    cache_key = get_cache_key(f"spotify_yt:{base_query}:{int(track.get('duration') or 0)}", "match")
    cached = await get_cached_info(cache_key)
    if cached:
        return cached

    for query in (base_query, f"{base_query} audio"):
        scored = []
        for entry in await _search_youtube_candidates(query):
            score = _score_youtube_match(entry, track)
            if score is not None:
                scored.append((score, entry))
        if scored:
            best = min(scored, key=lambda item: item[0])[1]
            result = {
                "url": f"https://www.youtube.com/watch?v={best['id']}",
                "title": best.get("title") or base_query,
            }
            await cache_info(cache_key, result, ttl=PLAYLIST_CACHE_TTL)
            return result
    return None

def get_platform_emoji(extractor):
    icons = {
        "youtube": "🎬",
        "soundcloud": "☁️",
        "spotify": "🟢",
    }
    return icons.get((extractor or "").lower(), "🎵")

def _format_queue_preview(state, limit=5):
    if not state.queue:
        return "empty"
    items = list(state.queue)[:limit]
    preview = " | ".join([f"{i+1}:{s['title'][:45]}" for i, s in enumerate(items)])
    remaining = len(state.queue) - limit
    if remaining > 0:
        preview += f" | +{remaining} more"
    return preview

def _log_vc_action(ctx, action: str, channel_name: str):
    try:
        gname = ctx.guild.name if getattr(ctx, "guild", None) else "UnknownGuild"
        uname = str(ctx.author) if getattr(ctx, "author", None) else "UnknownUser"
        logger.info(f"🎤 {action} — Guild: {gname} | VC: {channel_name} | By: {uname}")
    except Exception:
        pass

def _log_song_table(title: str, url: str, action: str = "NOW PLAYING"):
    """Log song info in a clean table format."""
    try:
        # Extract short ID from YouTube URL for cleaner display
        short_url = url
        if "youtube.com/watch?v=" in url or "youtu.be/" in url:
            if "v=" in url:
                vid_id = url.split("v=")[1].split("&")[0][:11]
                short_url = f"youtu.be/{vid_id}"
            elif "youtu.be/" in url:
                vid_id = url.split("youtu.be/")[1][:11]
                short_url = f"youtu.be/{vid_id}"

        # Truncate title if too long (max 45 chars)
        display_title = title[:45] + "..." if len(title) > 45 else title

        # Clean table format - fits in 80 chars
        logger.info(f"┌─ {'═' * 76} ─┐")
        logger.info(f"│ {action:^76} │")
        logger.info(f"├─ {'═' * 76} ─┤")
        logger.info(f"│ 🎵 {display_title:<70} │")
        logger.info(f"│ 🔗 {short_url:<70} │")
        logger.info(f"└─ {'═' * 76} ─┘")
    except Exception:
        pass

def _log_action(action: str, emoji: str = "▶️"):
    """Log action in a clean table format."""
    try:
        logger.info(f"┌─ {'═' * 76} ─┐")
        logger.info(f"│ {emoji} {action:^74} │")
        logger.info(f"└─ {'═' * 76} ─┘")
    except Exception:
        pass

def _log_playlist(playlist_title: str, songs: list, emoji: str = "📋"):
    """Log playlist with all songs and links in a clean table format."""
    try:
        # Truncate playlist title if too long (max 50 chars)
        display_title = playlist_title[:50] + "..." if len(playlist_title) > 50 else playlist_title

        logger.info(f"┌─ {'═' * 76} ─┐")
        logger.info(f"│ {emoji} PLAYLIST: {display_title:<63} │")
        logger.info(f"│ {'─' * 76} │")
        logger.info(f"│ 📊 Total: {len(songs)} songs{' ' * (62 - len(str(len(songs))))}│")
        logger.info(f"├─ {'═' * 76} ─┤")

        for i, song in enumerate(songs[:50], 1):  # Max 50 songs to avoid spam
            title = song.get("title", "Unknown")
            url = song.get("url", "")

            # Shorten URL
            short_url = url
            if "youtube.com/watch?v=" in url or "youtu.be/" in url:
                if "v=" in url:
                    vid_id = url.split("v=")[1].split("&")[0][:11]
                    short_url = f"youtu.be/{vid_id}"
                elif "youtu.be/" in url:
                    vid_id = url.split("youtu.be/")[1][:11]
                    short_url = f"youtu.be/{vid_id}"

            # Truncate title (max 40 chars)
            display_title = title[:40] + "..." if len(title) > 40 else title

            logger.info(f"│ {i:3}. {display_title:<40} │ {short_url:<22} │")

        if len(songs) > 50:
            logger.info(f"│ ... and {len(songs) - 50} more songs{' ' * (52 - len(str(len(songs) - 50)))}│")

        logger.info(f"└─ {'═' * 76} ─┘")
    except Exception:
        pass

def _log_now_playing(ctx, state, player):
    try:
        _log_song_table(player.title, player.webpage_url or player.url, "♪ NOW PLAYING ♪")
    except Exception:
        pass

def play_with_forced_bitrate(vc: discord.VoiceClient, source, after):
    """
    Force/request 256 kbps when the library supports it.
    If the library doesn't accept bitrate=..., fallback to normal vc.play().
    """
    cap_kbps = None
    try:
        cap_kbps = (vc.channel.bitrate // 1000) if vc.channel else None
    except Exception:
        cap_kbps = None

    try:
        # discord.py supports encoder options on play() for PCM sources
        vc.play(source, after=after, bitrate=FORCE_OPUS_BITRATE_KBPS, signal_type="music")
        logger.info(
            f"🎧 Opus bitrate requested: {FORCE_OPUS_BITRATE_KBPS} kbps"
            + (f" (channel cap={cap_kbps} kbps)" if cap_kbps else "")
        )
    except TypeError:
        # Some forks/versions don't support these kwargs
        vc.play(source, after=after)
        logger.info("🎧 Voice library doesn't support bitrate=... on vc.play(); using default encoder settings.")
    except Exception:
        raise

# ═══════════════════════════════════════════════════════════════════
#                    PLAYLIST EXTRACTION
# ═══════════════════════════════════════════════════════════════════
async def extract_youtube_mix(url, max_entries=None):
    max_entries = max_entries or MIX_LIMIT
    cache_key = get_cache_key(url, f"mix_{max_entries}")
    cached = await get_cached_info(cache_key)
    if cached:
        return cached

    try:
        info = await extract_processed_info_with_cookie_fallback(
            url,
            timeout=60.0,
            extra_options={
                "noplaylist": False,
                "extract_flat": "in_playlist",
                "ignoreerrors": True,
                "playlistend": max_entries,
                "playliststart": 1,
                "skip_download": True,
            },
        )
        if info:
            await cache_info(cache_key, info, ttl=PLAYLIST_CACHE_TTL)
        return info
    except Exception as e:
        logger.error(f"❌ Mix extraction failed: {e}")
        return None

async def extract_playlist_first(url, is_yt=True):
    if is_soundcloud_short_url(url):
        url = await resolve_soundcloud_url(url)

    cache_key = get_cache_key(url, "first")
    cached = await get_cached_info(cache_key)
    if cached:
        return cached

    unavailable = [
        "[Deleted video]",
        "[Private video]",
        "Private video",
        "Deleted video",
        "Unavailable",
        "Video unavailable",
    ]

    try:
        info = await extract_processed_info_with_cookie_fallback(
            url,
            timeout=30.0,
            extra_options={
                "noplaylist": False,
                "extract_flat": False if not is_yt else "in_playlist",
                "ignoreerrors": True,
                "playlistend": 1,
                "playliststart": 1,
                "skip_download": True,
            },
        )
        if not info:
            return None

        entries = info.get("entries", [])

        # Non-flat (SoundCloud) entries are fully extracted already; let
        # playback reuse them instead of extracting the first track again.
        if not is_yt:
            for entry in entries or [info]:
                if entry and entry.get("webpage_url"):
                    entry["_extracted_at"] = time.time()
                    await remember_stream_info(entry["webpage_url"], entry)
                    break

        # For SoundCloud single tracks (no entries), use the info directly
        if not entries and not is_yt:
            result = {
                "entries": [info],
                "playlist_count": 1,
                "title": info.get("title", "Track"),
                "extractor": info.get("extractor", "soundcloud"),
            }
            await cache_info(cache_key, result, ttl=PLAYLIST_CACHE_TTL)
            return result

        for entry in entries:
            if entry and entry.get("title") not in unavailable:
                title = entry.get("title", "").lower()
                if not any(p in title for p in ["private", "deleted", "unavailable"]):
                    result = {
                        "entries": [entry],
                        "playlist_count": info.get("playlist_count", 0),
                        "title": info.get("title", "Playlist"),
                        "extractor": info.get("extractor", "youtube" if is_yt else "soundcloud"),
                    }
                    await cache_info(cache_key, result, ttl=PLAYLIST_CACHE_TTL)
                    return result
        return None
    except Exception as e:
        logger.error(f"❌ Playlist first track failed: {e}")
        return None

async def extract_playlist_info(url, max_entries=None):
    max_entries = max_entries or PLAYLIST_LIMIT
    if is_soundcloud_short_url(url):
        url = await resolve_soundcloud_url(url)

    is_sc = is_soundcloud_url(url)

    try:
        return await extract_processed_info_with_cookie_fallback(
            url,
            timeout=90.0,
            extra_options={
                "noplaylist": False,
                "extract_flat": False if is_sc else "in_playlist",
                "ignoreerrors": True,
                "playlistend": max_entries,
                "skip_download": True,
            },
        )
    except Exception as e:
        logger.error(f"❌ Playlist extraction failed: {e}")
        return None

async def extract_single_track(url):
    if is_soundcloud_short_url(url):
        url = await resolve_soundcloud_url(url)

    cache_key = get_cache_key(url, "single")
    cached = await get_cached_info(cache_key)
    if cached:
        return cached

    try:
        info = await extract_info_with_cookie_fallback(
            url,
            timeout=30.0,
            extra_options={"noplaylist": True, "extract_flat": False, "ignoreerrors": True},
        )
        if info:
            entry = get_primary_entry(info)
            if entry:
                entry["_extracted_at"] = time.time()
            # Playback reuses this extraction instead of doing it again.
            await remember_stream_info(url, info)
            await cache_info(cache_key, info)
        return info
    except Exception as e:
        logger.error(f"❌ Track extraction failed: {e}")
        return None

# ═══════════════════════════════════════════════════════════════════
#                    BACKGROUND TASKS
# ═══════════════════════════════════════════════════════════════════
async def clear_all_caches():
    """Clear all non-essential caches. Returns dict with counts of cleared items."""
    cleared = {
        "metadata_cache": 0,
        "queue_messages": 0,
        "music_views": 0,
        "total": 0
    }

    try:
        # Clear metadata cache (_cache) under the lock to avoid races
        async with _cache_lock:
            cache_count = len(_cache)
            _cache.clear()
            cleared["metadata_cache"] = cache_count

        # Clear queue finished message references.
        msg_count = len(queue_finished_messages)
        queue_finished_messages.clear()
        cleared["queue_messages"] = msg_count

        # Prune inactive runtime objects instead of clearing active player state.
        views_count = prune_runtime_state()
        cleared["music_views"] = views_count

        cleared["total"] = cache_count + msg_count + views_count

        logger.info(
            f"🧹 Cache cleared: {cleared['metadata_cache']} metadata, "
            f"{cleared['queue_messages']} messages, "
            f"{cleared['music_views']} views"
        )
    except Exception as e:
        logger.error(f"❌ Cache clear error: {e}")

    return cleared

def prune_runtime_state():
    removed = 0
    inactive_guild_ids = []

    for guild_id in list(music_states.keys()):
        guild = bot.get_guild(guild_id)
        vc = guild.voice_client if guild else None
        state = music_states[guild_id]
        has_activity = (
            state.current
            or state.queue
            or state.is_fetching_playlist
            or (vc and vc.is_connected())
        )
        if has_activity:
            continue
        inactive_guild_ids.append(guild_id)

    for guild_id in inactive_guild_ids:
        if guild_id in music_states:
            del music_states[guild_id]
            removed += 1
        if guild_id in active_music_views:
            del active_music_views[guild_id]
        if guild_id in player_panel_messages:
            del player_panel_messages[guild_id]
        if guild_id in player_message_locks:
            del player_message_locks[guild_id]
        if guild_id in queue_finished_messages:
            del queue_finished_messages[guild_id]
        if guild_id in background_tasks:
            del background_tasks[guild_id]
        if guild_id in playlist_fetch_queues:
            del playlist_fetch_queues[guild_id]

    return removed

async def connection_monitor():
    await bot.wait_until_ready()

    # Heartbeat file path
    heartbeat_path = os.path.join(BASE_PATH, ".bot_heartbeat")

    # Write heartbeat more frequently than the timeout so a busy event loop
    # never trips the launcher's "frozen" detection (timeout + grace).
    heartbeat_interval = max(10.0, HEARTBEAT_TIMEOUT / 3.0)

    last_prune_time = time.time()
    prune_interval = 600  # 10 minutes

    while not bot.is_closed():
        try:
            current_time = time.time()

            # Update heartbeat timestamp
            with open(heartbeat_path, "w") as f:
                f.write(str(current_time))

            if IDLE_CLEAR_HOURS is not None:
                idle_timeout_seconds = IDLE_CLEAR_HOURS * 3600
                for guild_id, state in list(music_states.items()):
                    vc = get_guild_voice_client(guild_id)
                    if not vc or not vc.is_connected():
                        state.idle_since = None
                        continue

                    if is_guild_idle(guild_id, state=state, vc=vc):
                        if state.idle_since is None:
                            state.idle_since = current_time
                        elif current_time - state.idle_since >= idle_timeout_seconds:
                            await clear_idle_guild(guild_id)
                    else:
                        state.idle_since = None

            if current_time - last_prune_time >= prune_interval:
                prune_runtime_state()
                last_prune_time = current_time

            if len(music_states) > 5:
                gc.collect()
            await asyncio.sleep(heartbeat_interval)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"❌ Connection monitor error: {e}")
            await asyncio.sleep(10)

async def process_spotify_fetch(fetch_data):
    """Resolve the rest of a Spotify playlist/album on YouTube in the background.
    Matches are inserted in playlist order right after the songs already queued
    from this playlist, a few searches at a time."""
    ctx = fetch_data["ctx"]
    state = fetch_data["state"]
    tracks = fetch_data["spotify_tracks"]
    playlist_id = fetch_data["playlist_id"]
    playlist_title = fetch_data.get("playlist_title", "Spotify")
    fetching_message = fetch_data.get("fetching_message")
    guild_id = ctx.guild.id

    def insert_songs(songs):
        queue_list = list(state.queue)
        insert_pos = None
        for i, song in enumerate(queue_list):
            if song.get("playlist_id") == playlist_id:
                insert_pos = i + 1
        if insert_pos is None:
            # Everything from this playlist already left the queue: keep it
            # next in line if we're still playing from it, otherwise append.
            current = state.current or {}
            insert_pos = 0 if current.get("playlist_id") == playlist_id else len(queue_list)
        for song in songs:
            song_data = {"url": song["url"], "title": song["title"], "playlist_id": playlist_id}
            queue_list.insert(insert_pos, song_data)
            state.playlist_groups.setdefault(playlist_id, []).append(song_data)
            insert_pos += 1
        state.queue = deque(queue_list)

    added = []
    missing = 0
    for start in range(0, len(tracks), SPOTIFY_RESOLVE_CONCURRENCY):
        batch = tracks[start:start + SPOTIFY_RESOLVE_CONCURRENCY]
        results = await asyncio.gather(
            *(find_spotify_track_on_youtube(t) for t in batch), return_exceptions=True
        )
        found = []
        for track, match in zip(batch, results):
            if isinstance(match, dict):
                found.append({"url": match["url"], "title": spotify_display_title(track)})
            else:
                missing += 1
        if not found:
            continue

        insert_songs(found)
        added.extend(found)

        # Queue ran dry while we were searching: pick playback back up.
        vc = get_guild_voice_client(guild_id)
        if (
            vc and vc.is_connected()
            and not state.is_playing and not state.was_stopped
            and not vc.is_playing() and not vc.is_paused()
        ):
            await play_next(ctx)

    if added:
        _log_playlist(playlist_title, added, "🟢")

    if fetching_message:
        try:
            await fetching_message.delete()
        except Exception:
            pass

    summary = f"🟢 Added **{len(added)}** track{'s' if len(added) != 1 else ''} from **{playlist_title}**"
    if missing:
        summary += f" • {missing} not found on YouTube"
    await _safe_send(ctx.channel.id if getattr(ctx, "channel", None) else None, summary)
    if state.current:
        await refresh_player_panel(ctx, guild_id)

async def process_playlist_queue(guild_id):
    while playlist_fetch_queues.get(guild_id):
        try:
            fetch_data = playlist_fetch_queues[guild_id].popleft()
            if not fetch_data:
                continue

            ctx = fetch_data.get("ctx")
            url = fetch_data.get("url")
            state = fetch_data.get("state")
            already_added = fetch_data.get("already_added", 0)
            playlist_id = fetch_data.get("playlist_id")
            playlist_title = fetch_data.get("playlist_title", "Playlist")
            is_mix = fetch_data.get("is_mix", False)
            fetching_message = fetch_data.get("fetching_message")

            if not ctx or not state:
                continue

            if fetch_data.get("spotify_tracks") is not None:
                try:
                    await process_spotify_fetch(fetch_data)
                finally:
                    state.is_fetching_playlist = False
                continue

            if not url:
                continue

            if is_mix:
                info = await extract_youtube_mix(url, max_entries=MIX_LIMIT)
            else:
                info = await extract_playlist_info(url, max_entries=PLAYLIST_LIMIT)

            if not info or "entries" not in info:
                state.is_fetching_playlist = False
                continue

            entries = info.get("entries", [])
            playlist_title = info.get("title", playlist_title)

            unavailable = [
                "[Deleted video]",
                "[Private video]",
                "Private video",
                "Deleted video",
                "Unavailable",
                "Video unavailable",
                "NA",
            ]

            fetched = []
            for idx, entry in enumerate(entries[already_added:], start=already_added):
                if not entry:
                    continue

                if entry.get("_type") == "url":
                    entry_id = entry.get("id", "")
                    if entry_id and not entry_id.startswith("http"):
                        if "youtube" in url.lower():
                            webpage_url = f"https://www.youtube.com/watch?v={entry_id}"
                        else:
                            webpage_url = entry.get("url", "")
                    else:
                        webpage_url = entry.get("url", entry_id)
                    title = entry.get("title", f"Track {idx + 1}")
                else:
                    title = entry.get("title", "")
                    webpage_url = entry.get("webpage_url") or entry.get("url")

                if not webpage_url or not title:
                    continue
                if title in unavailable:
                    continue
                if any(p in title.lower() for p in ["private", "deleted", "unavailable"]):
                    continue

                fetched.append({"url": webpage_url, "title": title})
                await asyncio.sleep(0.001)

            if fetched and playlist_id is not None:
                insert_pos = len(state.queue)
                for i, song in enumerate(state.queue):
                    if song.get("playlist_id") == playlist_id:
                        insert_pos = i + 1
                        break

                queue_list = list(state.queue)
                for song in fetched:
                    song_data = {"url": song["url"], "title": song["title"], "playlist_id": playlist_id}
                    queue_list.insert(insert_pos, song_data)
                    insert_pos += 1
                state.queue = deque(queue_list)

                # Log playlist with all songs
                _log_playlist(playlist_title, fetched, "🎛️" if is_mix else "📋")

                # Queue ran dry while we were fetching (e.g. skipped the first
                # track early): pick playback back up with the fetched songs.
                vc_now = get_guild_voice_client(ctx.guild.id)
                if (
                    vc_now and vc_now.is_connected()
                    and not state.is_playing and not state.was_stopped
                    and not vc_now.is_playing() and not vc_now.is_paused()
                ):
                    await play_next(ctx)

                # Delete the fetching message if it exists
                if fetching_message:
                    try:
                        await fetching_message.delete()
                    except Exception:
                        pass

                # Send a fresh Now Playing embed with updated queue count
                guild_id = ctx.guild.id
                if state.current:
                    try:
                        emoji = get_platform_emoji(state.current.get("extractor", "generic"))
                        vol = f" {get_volume_emoji(state.volume)}" if state.volume != 1.0 else ""

                        # Use cached metadata only — avoid blocking extraction
                        current_data = await get_cached_info(
                            get_cache_key(state.current.get("url", ""), "single")
                        ) if state.current.get("url") else None
                        thumbnail = current_data.get("thumbnail") if current_data else None
                        duration = current_data.get("duration") if current_data else None

                        title_display = rtl_format(state.current['title'])

                        embed = discord.Embed(
                            title=f"{emoji} Now Playing",
                            description=f"**{title_display}**{vol}",
                            color=0x5865F2,
                            url=state.current.get("url", "")
                        )

                        if thumbnail:
                            embed.set_thumbnail(url=thumbnail)

                        embed.add_field(name="🔗 Link", value=f"[Click here]({state.current.get('url', '')})", inline=True)

                        if duration:
                            minutes, seconds = divmod(duration, 60)
                            embed.add_field(name="⏱️ Duration", value=f"{int(minutes)}:{int(seconds):02d}", inline=True)

                        queue_len = len(state.queue)
                        if queue_len > 0:
                            embed.add_field(
                                name="📜 Queue",
                                value=f"{queue_len} song{'s' if queue_len != 1 else ''} queued",
                                inline=False
                            )
                        else:
                            embed.add_field(
                                name="📜 Queue",
                                value="0 songs queued",
                                inline=False
                            )

                        if state.loop_mode:
                            embed.add_field(name="🔁 Loop", value=state.get_loop_status(), inline=True)

                        embed.add_field(name="🔊 Volume", value=f"{state.get_volume_percent()}%", inline=True)

                        await send_fresh_music_message(ctx, guild_id, embed)
                    except Exception as e:
                        logger.debug(f"Could not refresh embed after playlist fetch: {e}")

            state.is_fetching_playlist = False

        except Exception as e:
            logger.error(f"❌ Playlist queue error: {e}")

        await asyncio.sleep(0.1)

# ═══════════════════════════════════════════════════════════════════
#                      CORE PLAYBACK
# ═══════════════════════════════════════════════════════════════════
async def _safe_send(channel_id, content=None, embed=None):
    """Send a message to a channel by ID, gracefully handling deleted channels."""
    if not channel_id:
        return None
    channel = bot.get_channel(channel_id)
    if not channel:
        return None
    try:
        return await channel.send(content=content, embed=embed)
    except (discord.NotFound, discord.Forbidden):
        return None
    except Exception as e:
        logger.debug(f"Could not send to channel {channel_id}: {e}")
        return None

async def _play_next_from_callback(guild_id, channel_id, retry_song=None):
    """Called from after_play's run_coroutine_threadsafe.
    Rebuilds a minimal ctx-like object from guild_id/channel_id so play_next
    doesn't depend on a stale ctx from the original command."""
    guild = bot.get_guild(guild_id)
    if not guild:
        return
    if retry_song is not None:
        state = get_state(guild_id)
        if not state.was_stopped:
            # The stream link died before any audio (rotated/expired):
            # drop the stale link and play the same song again, once.
            logger.info(f"🔄 Stream link failed, re-fetching: {retry_song.get('title', '')[:50]}")
            await forget_stream_info(retry_song.get("url", ""))
            if not state.should_loop():
                state.queue.appendleft({**retry_song, "_stream_retry": True})
    channel = bot.get_channel(channel_id) if channel_id else None
    if not channel:
        # Try the first text channel the bot can send to
        for ch in guild.text_channels:
            if ch.permissions_for(guild.me).send_messages:
                channel = ch
                break
    if not channel:
        return
    # Build a fake ctx with just what play_next needs
    class _FakeCtx:
        pass
    fake_ctx = _FakeCtx()
    fake_ctx.guild = guild
    fake_ctx.channel = channel
    fake_ctx.bot = bot
    fake_ctx.send = channel.send
    await play_next(fake_ctx)

async def play_next(ctx, retry=0, max_retries=3):
    guild_id = ctx.guild.id
    channel_id = ctx.channel.id if getattr(ctx, "channel", None) else None
    state = get_state(guild_id)

    # Use a per-guild lock so only one play_next runs at a time.
    # This prevents the after_play callback and retry path from racing.
    lock = get_play_next_lock(guild_id)
    async with lock:
        vc = get_guild_voice_client(guild_id)

        # Delete "Queue finished!" message if it exists
        await cleanup_queue_finished_message(guild_id)

        if not vc or not vc.is_connected():
            state.is_playing = False
            return

        if state.should_loop() and state.current:
            next_song = state.current.copy()
            loop_finished = state.decrement_loop()

            if loop_finished:
                await _safe_send(channel_id, f"🔁 Loop complete for **{next_song['title']}**")
                state.loop_announced = False
        else:
            next_song = state.next_song()
            state.loop_announced = False

        if not next_song:
            state.is_playing = False
            if state.was_stopped:
                state.was_stopped = False
                return
            msg = "✅ **Queue finished!** 🎵"
            if state.skipped_count > 0:
                msg += f"\n📊 {state.skipped_count} unavailable track{'s' if state.skipped_count != 1 else ''} skipped"
                state.skipped_count = 0
            msg += f"\n💡 Use `{PREFIX}play <song>` to add more music"
            sent = await _safe_send(channel_id, msg)
            if sent:
                queue_finished_messages[guild_id] = sent
            return

        state.current = next_song
        state.is_playing = True

        try:
            player = await YTDLSource.from_url(
                next_song["url"], loop=bot.loop, stream=True, volume=state.volume
            )

            # Cache the extracted data so build_now_playing_embed can use it
            # without doing another blocking extraction (slim, so it can live
            # as long as the song does).
            await cache_info(
                get_cache_key(next_song["url"], "single"),
                player.data,
                ttl=max(METADATA_CACHE_TTL, int(player.duration or 0) + 600),
            )

            # Capture guild_id/channel_id for the callback — NOT ctx.
            # ctx can go stale (deleted channel, user left, etc.) by the
            # time this fires from discord.py's voice worker thread.
            def after_play(error):
                if error:
                    logger.error(f"❌ Playback error: {error}")
                retry_song = None
                try:
                    source = getattr(player, "original", None)
                    if (
                        not next_song.get("_stream_retry")
                        and source is not None
                        and hasattr(source, "failed_without_audio")
                        and source.failed_without_audio()
                    ):
                        retry_song = next_song
                except Exception:
                    retry_song = None
                asyncio.run_coroutine_threadsafe(
                    _play_next_from_callback(guild_id, channel_id, retry_song=retry_song), bot.loop
                )

            # ✅ Force/request 256 kbps (fallback-safe)
            play_with_forced_bitrate(vc, player, after_play)
            schedule_prefetch(guild_id, player.duration)

            # ✅ LOG: VC name + now playing + queue preview
            _log_now_playing(ctx, state, player)

            emoji = get_platform_emoji(player.extractor)
            vol = f" {get_volume_emoji(state.volume)}" if state.volume != 1.0 else ""
            loop_info = ""

            if state.loop_mode:
                loop_status = state.get_loop_status()
                loop_info = f" 🔁 {loop_status}"

            # Create embed with song info (RTL support for Arabic)
            title_display = rtl_format(player.title)
            embed = discord.Embed(
                title=f"{emoji} Now Playing",
                description=f"**{title_display}**{vol}",
                color=0x5865F2,
                url=player.webpage_url  # Click title to open song
            )

            # Add thumbnail if available
            if player.thumbnail:
                embed.set_thumbnail(url=player.thumbnail)

            # Add song link
            embed.add_field(name="🔗 Link", value=f"[Click here]({player.webpage_url})", inline=True)

            # Add duration if available
            if player.duration:
                minutes, seconds = divmod(player.duration, 60)
                embed.add_field(name="⏱️ Duration", value=f"{int(minutes)}:{int(seconds):02d}", inline=True)

            # Add queue info with up-next preview
            queue_len = len(state.queue)
            if queue_len > 0:
                up_next_title = state.queue[0]["title"][:50]
                embed.add_field(
                    name="📜 Queue",
                    value=f"{queue_len} song{'s' if queue_len != 1 else ''} queued\n🎵 **Up next:** {up_next_title}",
                    inline=False
                )
            else:
                embed.add_field(
                    name="📜 Queue",
                    value="0 songs queued",
                    inline=False
                )

            # Add loop info if active
            if state.loop_mode:
                embed.add_field(name="🔁 Loop", value=state.get_loop_status(), inline=True)

            # Add volume info
            embed.add_field(name="🔊 Volume", value=f"{state.get_volume_percent()}%", inline=True)

            # Footer with context
            footer_parts = []
            if queue_len > 0:
                footer_parts.append(f"{queue_len} in queue")
            if state.loop_mode:
                footer_parts.append(f"🔁 {state.get_loop_status()}")
            footer_parts.append(f"🔊 {state.get_volume_percent()}%")
            embed.set_footer(text=" • ".join(footer_parts))

            embed.timestamp = discord.utils.utcnow()
            await send_fresh_music_message(ctx, guild_id, embed)

            state.skipped_count = 0

        except Exception as e:
            logger.error(f"❌ Failed to play: {next_song['title'][:30]} - {e}")
            state.skipped_count += 1
            if retry < max_retries and state.queue:
                state.is_playing = False
                await _safe_send(channel_id, f"⏭️ Skipped: {next_song['title'][:50]}")
                await play_next(ctx, retry + 1, max_retries)
            else:
                await _safe_send(channel_id, f"⏭️ Skipped: {next_song['title'][:50]}")
                state.is_playing = False
                await play_next(ctx)

# ═══════════════════════════════════════════════════════════════════
#                          EVENTS
# ═══════════════════════════════════════════════════════════════════
_extractor_warmed = False

async def warm_up_extractor():
    """One throwaway YouTube extraction at startup: loads the player JS and
    starts the JS runtime path so the first real song starts faster."""
    global _extractor_warmed
    if _extractor_warmed:
        return
    _extractor_warmed = True
    try:
        await asyncio.sleep(2)
        t0 = time.time()
        await extract_info_processed(
            "https://www.youtube.com/watch?v=jNQXAC9IVRw",
            timeout=60.0,
            extra_options={"extract_flat": False, "ignoreerrors": True},
        )
        logger.info(f"🔥 Extractor warmed up in {time.time() - t0:.1f}s")
    except Exception as e:
        logger.debug(f"Extractor warm-up failed: {e}")

@bot.event
async def on_ready():
    asyncio.ensure_future(warm_up_extractor())
    try:
        if GAME and GAME != "DEFAULT":
            activity_type = discord.ActivityType.listening
            if "playing" in GAME.lower():
                activity_type = discord.ActivityType.playing
                game_name = GAME.replace("playing ", "", 1).strip()
            elif "listening" in GAME.lower():
                game_name = GAME.replace("listening to ", "", 1).strip()
            else:
                game_name = GAME.strip()

            status = getattr(discord.Status, STATUS.lower(), discord.Status.online)
            await bot.change_presence(
                activity=discord.Activity(type=activity_type, name=game_name),
                status=status,
            )
    except Exception:
        pass

    if USE_SLASH_COMMANDS:
        try:
            synced = await bot.tree.sync()
            logger.info(f"✅ Synced {len(synced)} slash commands")
        except Exception as e:
            logger.error(f"❌ Slash sync failed: {e}")

    logger.info("═" * 50)
    logger.info(f"🤖 Bot: {bot.user.name} (ID: {bot.user.id})")
    logger.info(f"🌐 Servers: {len(bot.guilds)}")
    logger.info(f"📝 Prefix: {', '.join(PREFIXES)}")
    logger.info(f"🔗 Slash Commands: {'✓' if USE_SLASH_COMMANDS else '✗'}")
    logger.info(f"🔁 Loop Feature: {'✓' if USE_LOOP_FEATURE else '✗'}")
    logger.info(f"📈 Limits: {PLAYLIST_LIMIT} playlist / {MIX_LIMIT} mix")
    logger.info(f"🎧 Forced Opus bitrate request: {FORCE_OPUS_BITRATE_KBPS} kbps")
    logger.info(f"🍪 Cookie Status: {COOKIE_STATUS}")
    logger.info(f"🎛️ YouTube Format Flags: {YOUTUBE_FORMAT_STATUS}")
    if IDLE_CLEAR_HOURS is None:
        logger.info("🧹 Idle Auto-Clear: ✗")
    else:
        logger.info(f"🧹 Idle Auto-Clear: ✓ ({IDLE_CLEAR_HOURS}h)")
    logger.info("═" * 50)
    logger.info("🎵 Ready to play music!")

    # Check if bot was restarted and send confirmation message
    if os.path.exists(RESTART_PENDING_FILE):
        try:
            # Only send if file was created recently (within 60 seconds)
            file_time = os.path.getmtime(RESTART_PENDING_FILE)
            file_age = time.time() - file_time

            if file_age < 60:  # File must be less than 60 seconds old
                with open(RESTART_PENDING_FILE, "r") as f:
                    lines = f.readlines()
                    if len(lines) >= 3:
                        guild_id = int(lines[0].strip())
                        channel_id = int(lines[1].strip())

                # Try to send restart confirmation message
                try:
                    await asyncio.sleep(0.5)  # Brief delay to ensure ready
                    guild = bot.get_guild(guild_id)
                    if guild:
                        channel = guild.get_channel(channel_id)
                        if channel and channel.permissions_for(guild.me).send_messages:
                            await channel.send("✅ **Bot restarted successfully!**")
                            logger.info(f"✓ Restart confirmation sent")
                except Exception as e:
                    logger.debug(f"Could not send restart confirmation: {e}")
            else:
                logger.debug("Restart file too old, ignoring")
        except Exception as e:
            logger.debug(f"Error reading restart pending file: {e}")
        finally:
            # Always clean up the restart file
            try:
                os.remove(RESTART_PENDING_FILE)
            except Exception:
                pass

    bot.loop.create_task(connection_monitor())

@bot.event
async def on_voice_state_update(member, before, after):
    if member.id != bot.user.id:
        return
    if before.channel and not after.channel:
        guild_id = before.channel.guild.id
        state = get_state(guild_id)
        cancel_background_tasks(guild_id)
        state.clear()

        # Clean up to prevent memory accumulation
        for registry in (active_music_views, player_panel_messages,
                         player_message_locks, queue_finished_messages,
                         music_states):
            registry.pop(guild_id, None)

@bot.event
async def on_guild_remove(guild):
    """Clean up all state when the bot is removed from a guild."""
    guild_id = guild.id
    cancel_background_tasks(guild_id)
    state = music_states.get(guild_id)
    if state:
        state.was_stopped = True
        state.clear()
    for registry in (active_music_views, player_panel_messages,
                     player_message_locks, queue_finished_messages,
                     music_states, background_tasks, playlist_fetch_queues):
        registry.pop(guild_id, None)
    logger.info(f"👋 Removed from guild {guild_id}, cleaned up state")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("❌ Missing arguments")
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Missing permissions")
    else:
        await ctx.send(f"❌ Error: {str(error)[:100]}")

# ═══════════════════════════════════════════════════════════════════
#                      SLASH COMMANDS
# ═══════════════════════════════════════════════════════════════════
if USE_SLASH_COMMANDS:

    @bot.tree.command(name="play", description="🎵 Play music from URL or search")
    async def play_slash(interaction: discord.Interaction, query: str):
        ctx = await bot.get_context(interaction)
        ctx.author = interaction.user
        await interaction.response.defer()
        await play(ctx, query=query)

    @bot.tree.command(name="skip", description="⏭️ Skip current song")
    async def skip_slash(interaction: discord.Interaction):
        ctx = await bot.get_context(interaction)
        ctx.author = interaction.user
        await interaction.response.defer()
        await skip(ctx)

    @bot.tree.command(name="stop", description="⏹️ Stop and clear queue")
    async def stop_slash(interaction: discord.Interaction):
        ctx = await bot.get_context(interaction)
        ctx.author = interaction.user
        await interaction.response.defer()
        await stop(ctx)

    @bot.tree.command(name="pause", description="⏸️ Pause playback")
    async def pause_slash(interaction: discord.Interaction):
        ctx = await bot.get_context(interaction)
        ctx.author = interaction.user
        await interaction.response.defer()
        await pause(ctx)

    @bot.tree.command(name="resume", description="▶️ Resume playback")
    async def resume_slash(interaction: discord.Interaction):
        ctx = await bot.get_context(interaction)
        ctx.author = interaction.user
        await interaction.response.defer()
        await resume(ctx)

    @bot.tree.command(name="queue", description="📜 Show queue")
    async def queue_slash(interaction: discord.Interaction):
        ctx = await bot.get_context(interaction)
        ctx.author = interaction.user
        await interaction.response.defer()
        await queue_list(ctx)

    @bot.tree.command(name="volume", description="🔊 Set volume (0-200)")
    async def volume_slash(interaction: discord.Interaction, level: int = None):
        ctx = await bot.get_context(interaction)
        ctx.author = interaction.user
        state = get_state(ctx.guild.id)

        if level is None:
            vol = state.get_volume_percent()
            bar = create_volume_bar(state.volume)
            emoji = get_volume_emoji(state.volume)
            await interaction.response.send_message(f"{emoji} **{vol}%**\n{bar}")
            return

        if level < 0 or level > 200:
            await interaction.response.send_message("❌ Volume: 0-200%", ephemeral=True)
            return

        await interaction.response.defer()
        state.set_volume(level / 100.0)
        vc = ctx.guild.voice_client
        if vc and vc.source:
            vc.source.volume = state.volume

        bar = create_volume_bar(state.volume)
        emoji = get_volume_emoji(state.volume)
        _log_action(f"VOLUME SET TO {level}%", "🔊")
        await ctx.send(f"{emoji} Volume: **{level}%**\n{bar}")
        await refresh_player_panel(ctx, ctx.guild.id)

    @bot.tree.command(name="join", description="🎤 Join voice channel")
    async def join_slash(interaction: discord.Interaction):
        ctx = await bot.get_context(interaction)
        ctx.author = interaction.user
        await interaction.response.defer()
        await join(ctx)

    @bot.tree.command(name="leave", description="👋 Leave voice channel")
    async def leave_slash(interaction: discord.Interaction):
        ctx = await bot.get_context(interaction)
        ctx.author = interaction.user
        await interaction.response.defer()
        await leave(ctx)

    @bot.tree.command(name="clear", description="🗑️ Clear queue (keeps current track, stops loop)")
    async def clear_slash(interaction: discord.Interaction):
        ctx = await bot.get_context(interaction)
        ctx.author = interaction.user
        await interaction.response.defer()
        await clear_queue(ctx)

    if USE_LOOP_FEATURE:

        @bot.tree.command(name="loop", description="🔁 Loop current song")
        @app_commands.describe(count="Times to loop (empty = infinite)")
        async def loop_slash(interaction: discord.Interaction, count: int = None):
            ctx = await bot.get_context(interaction)
            ctx.author = interaction.user
            await interaction.response.defer()
            await loop_command(ctx, count=count)

        @bot.tree.command(name="stoploop", description="⏹️ Stop looping")
        async def stoploop_slash(interaction: discord.Interaction):
            ctx = await bot.get_context(interaction)
            ctx.author = interaction.user
            await interaction.response.defer()
            await stoploop(ctx)

# ═══════════════════════════════════════════════════════════════════
#                      TEXT COMMANDS
# ═══════════════════════════════════════════════════════════════════
@bot.command(name="join", aliases=["j", "connect"] + CMD_JOIN_ALIASES)
async def join(ctx):
    """🎤 Join voice channel"""
    if not ctx.author.voice:
        return await ctx.send("❌ Join a voice channel first")

    channel = ctx.author.voice.channel
    vc = ctx.guild.voice_client

    if vc:
        if vc.channel == channel:
            _log_vc_action(ctx, "Already in", channel.name)
            return await ctx.send(f"✅ Already in **{channel.name}**")
        await vc.move_to(channel)
        _log_vc_action(ctx, "Moved to", channel.name)
        return await ctx.send(f"🎤 Moved to **{channel.name}**")

    try:
        await asyncio.wait_for(channel.connect(), timeout=10.0)
        _log_vc_action(ctx, "Joined", channel.name)
        await ctx.send(f"🎤 Joined **{channel.name}**")
    except Exception:
        await ctx.send("❌ Failed to join")

@bot.command(name="leave", aliases=["disconnect", "dc"] + CMD_LEAVE_ALIASES)
async def leave(ctx):
    """👋 Leave voice channel"""
    vc = ctx.guild.voice_client
    if not vc:
        return await ctx.send("❌ Not in a voice channel")

    state = get_state(ctx.guild.id)
    cancel_background_tasks(ctx.guild.id)
    state.clear()
    old = vc.channel.name if vc.channel else "UnknownVC"
    await vc.disconnect()
    _log_vc_action(ctx, "Disconnected from", old)
    await ctx.send("👋 Disconnected")

def start_early_lookup(query):
    """Kick off the slow lookup for a play request right away, so it runs while
    we join voice and post "Searching...". Returns (kind, task) or (None, None).
    The task never raises; it yields None on failure and callers fall back."""
    query = (query or "").strip()
    is_url = query.startswith(("http://", "https://"))

    async def _safe(coro):
        try:
            return await coro
        except Exception as e:
            logger.debug(f"Early lookup failed: {e}")
            return None

    if not is_url:
        return "search", asyncio.ensure_future(_safe(search_youtube(query, 1)))
    if is_spotify_url(query):
        return "spotify", asyncio.ensure_future(_safe(fetch_spotify_metadata(query)))
    if (
        (is_youtube_url(query) or (is_soundcloud_url(query) and not is_soundcloud_short_url(query)))
        and not is_playlist_url(query)
    ):
        return "single", asyncio.ensure_future(_safe(extract_single_track(query)))
    return None, None

async def take_early_lookup(early, kind):
    early_kind, task = early
    if early_kind != kind or task is None:
        return None
    return await task

async def play_spotify(ctx, query, msg, vc, state, meta_task=None):
    """Spotify link → play the first track found on YouTube right away,
    then resolve the rest of the playlist/album in the background."""
    guild_id = ctx.guild.id
    meta = (await meta_task) if meta_task else None
    if not meta:
        meta = await fetch_spotify_metadata(query)
    if not meta:
        await msg.delete()
        return await ctx.send("❌ Couldn't read that Spotify link (is it public?)")

    tracks = meta["tracks"]
    is_collection = meta["kind"] != "track"

    # Start playback ASAP: take the first track that YouTube can match.
    first_index, first_match = None, None
    progress_edit = None
    for i, track in enumerate(tracks[:10]):
        if is_collection:
            if progress_edit:
                await progress_edit
            # Progress text updates alongside the search instead of before it.
            progress_edit = asyncio.ensure_future(
                msg.edit(content=f"🟢 **Finding on YouTube:** {spotify_display_title(track)[:80]}")
            )
        first_match = await find_spotify_track_on_youtube(track)
        if first_match:
            first_index = i
            break

    if first_match:
        warm_stream_soon(first_match["url"])
    if progress_edit:
        try:
            await progress_edit
        except Exception:
            pass
    await msg.delete()
    if not first_match:
        return await ctx.send("❌ Couldn't find this on YouTube")

    first_title = spotify_display_title(tracks[first_index])
    remaining = tracks[first_index + 1:]
    await cleanup_queue_finished_message(guild_id)

    if not is_collection or not remaining:
        state.add_song(first_match["url"], first_title)
        _log_song_table(first_title, first_match["url"], "🟢 SPOTIFY → YT")
        if state.is_playing or vc.is_playing():
            await ctx.send(f"🟢 **Queued:** {rtl_format(first_title)}")
            await refresh_player_panel(ctx, guild_id)
    else:
        playlist_id = state.current_playlist_id
        state.current_playlist_id += 1
        state.add_song(first_match["url"], first_title, playlist_id=playlist_id)

        already_playing = state.is_playing or vc.is_playing()
        verb = "Queued" if already_playing else "Playing"
        fetching_message = await ctx.send(
            f"🟢 **{verb}:** {rtl_format(first_title)}\n"
            f"🔄 Finding **{len(remaining)}** more from **{meta['title']}** on YouTube..."
        )

        state.is_fetching_playlist = True
        playlist_fetch_queues.setdefault(guild_id, deque()).append(
            {
                "ctx": ctx,
                "state": state,
                "playlist_id": playlist_id,
                "playlist_title": meta["title"],
                "spotify_tracks": remaining,
                "fetching_message": fetching_message,
            }
        )
        if guild_id not in background_tasks or background_tasks[guild_id].done():
            background_tasks[guild_id] = bot.loop.create_task(process_playlist_queue(guild_id))

        logger.info(f"🟢 Spotify {meta['kind']} — {meta['title']} ({len(tracks)} tracks) | First: {first_title}")

    if not state.is_playing and not vc.is_playing():
        await play_next(ctx)

@bot.command(name="play", aliases=["p"] + CMD_PLAY_ALIASES)
async def play(ctx, *, query: str = None):
    """🎵 Play music from URL or search"""
    if not query:
        return await ctx.send(f"❌ Usage: `{PREFIX}play <song/URL>`")

    if not ctx.author.voice:
        return await ctx.send("❌ Join a voice channel first")

    user_channel = ctx.author.voice.channel
    vc = ctx.guild.voice_client
    guild_id = ctx.guild.id
    state = get_state(guild_id)

    # Start searching now; it overlaps with joining voice and the status message.
    early = start_early_lookup(query)

    if vc and vc.is_connected():
        if vc.channel != user_channel:
            was_playing = (vc.is_playing() or vc.is_paused()) or state.is_playing
            old_channel_name = vc.channel.name if vc.channel else "previous channel"

            if was_playing:
                cancel_background_tasks(guild_id)
                state.was_stopped = True
                state.clear()
                if vc.is_playing() or vc.is_paused():
                    vc.stop()
                await ctx.send(
                    f"⏹️ **Stopped playback** and cleared queue\n"
                    f"🚚 **Moving to {user_channel.name}** (from {old_channel_name})"
                )
            else:
                await ctx.send(f"🚚 **Moving to {user_channel.name}** (from {old_channel_name})")

            await vc.move_to(user_channel)
            _log_vc_action(ctx, "Moved to", user_channel.name)
            await asyncio.sleep(0.5)

    elif not vc:
        await ctx.invoke(join)
        await asyncio.sleep(0.5)

    vc = ctx.guild.voice_client
    if not vc or not vc.is_connected():
        return await ctx.send("❌ Failed to connect")

    if state.was_stopped:
        cancel_background_tasks(guild_id)
        state.clear()
        state.was_stopped = False

    try:
        msg = await ctx.send("🔍 **Searching...**")

        is_url = query.startswith(("http://", "https://"))
        if is_url and is_soundcloud_short_url(query):
            resolved_query = await resolve_soundcloud_url(query)
            if resolved_query and resolved_query != query:
                query = resolved_query
        is_playlist = is_url and is_playlist_url(query)
        is_yt = is_youtube_url(query) if is_url else False
        is_sc = is_soundcloud_url(query) if is_url else False
        is_mix = is_youtube_mix(query) if is_yt else False

        if is_url and is_spotify_url(query):
            meta_task = early[1] if early[0] == "spotify" else None
            await play_spotify(ctx, query, msg, vc, state, meta_task=meta_task)
            return

        if is_playlist and (is_yt or is_sc):
            first_info = await extract_playlist_first(query, is_yt)

            if not first_info or not first_info.get("entries"):
                await msg.delete()
                return await ctx.send("❌ No playable tracks found")

            entry = first_info["entries"][0]
            url = entry.get("webpage_url") or entry.get("url")
            title = entry.get("title", "Unknown")
            playlist_title = first_info.get("title", "Playlist")
            if not state.is_fetching_playlist and not state.is_playing and not vc.is_playing():
                warm_stream_soon(url)
            total = first_info.get("playlist_count") or "?"

            await msg.delete()

            if state.is_fetching_playlist:
                await ctx.send(f"📋 **Queued:** {playlist_title} (will fetch after current)")

                playlist_id = state.current_playlist_id
                state.current_playlist_id += 1
                state.playlist_groups[playlist_id] = []

                if guild_id not in playlist_fetch_queues:
                    playlist_fetch_queues[guild_id] = deque()

                playlist_fetch_queues[guild_id].append(
                    {
                        "ctx": ctx,
                        "url": query,
                        "state": state,
                        "already_added": 0,
                        "playlist_id": playlist_id,
                        "playlist_title": playlist_title,
                        "is_mix": is_mix,
                    }
                )

                if guild_id not in background_tasks or background_tasks[guild_id].done():
                    background_tasks[guild_id] = bot.loop.create_task(process_playlist_queue(guild_id))

                logger.info(f"📋 Playlist queued — {playlist_title} ({total} tracks) | Queue({len(state.queue)}): {_format_queue_preview(state)}")
            else:
                state.add_song(url, title)

                playlist_id = state.current_playlist_id
                state.current_playlist_id += 1
                state.playlist_groups[playlist_id] = []

                emoji = "🎛️" if is_mix else "📋"
                fetching_message = await ctx.send(f"{emoji} **Playing:** {title}\n🔄 Fetching **{playlist_title}** ({total} tracks)...")

                state.is_fetching_playlist = True

                if guild_id not in playlist_fetch_queues:
                    playlist_fetch_queues[guild_id] = deque()

                playlist_fetch_queues[guild_id].append(
                    {
                        "ctx": ctx,
                        "url": query,
                        "state": state,
                        "already_added": 1,
                        "playlist_id": playlist_id,
                        "playlist_title": playlist_title,
                        "is_mix": is_mix,
                        "fetching_message": fetching_message,
                    }
                )

                if guild_id not in background_tasks or background_tasks[guild_id].done():
                    background_tasks[guild_id] = bot.loop.create_task(process_playlist_queue(guild_id))

                vc_name = vc.channel.name if vc.channel else "UnknownVC"
                logger.info(f"📋 Playlist start — VC: {vc_name} | First: {title} | Fetching: {playlist_title} ({total}) | Queue({len(state.queue)}): {_format_queue_preview(state)}")

            if not state.is_playing and not vc.is_playing():
                await play_next(ctx)
            return

        if is_url:
            info = await take_early_lookup(early, "single")
            if not info:
                info = await extract_single_track(query)
        else:
            results = await take_early_lookup(early, "search")
            if not results:
                results = await search_youtube(query, 1)
            info = None
            if results:
                top = results[0]
                info = {
                    "webpage_url": top["url"],
                    "title": top["title"] or query,
                    "extractor": "youtube",
                    "duration": top.get("duration"),
                    "thumbnail": top.get("thumbnail"),
                }

        # Start resolving the audio stream now if this song is up next.
        if info:
            primary = get_primary_entry(info) or {}
            next_url = primary.get("webpage_url") or primary.get("url")
            if not state.queue and (not is_url or not has_usable_media_url(primary)):
                warm_stream_soon(next_url)

        await msg.delete()

        if not info:
            return await ctx.send("❌ No results found")

        if "entries" in info:
            info = info["entries"][0] if info["entries"] else None

        if not info:
            return await ctx.send("❌ No results found")

        url = info.get("webpage_url") or info.get("url")
        title = info.get("title", "Unknown")
        emoji = get_platform_emoji(info.get("extractor", "generic"))

        state.add_song(url, title)
        _log_song_table(title, url, "➕ QUEUED")

        # RTL support for queued message
        title_display = rtl_format(title) if is_arabic(title) else title

        # Delete "Queue finished!" message if it exists
        await cleanup_queue_finished_message(guild_id)

        # If already playing, refresh Now Playing embed with updated queue count at channel bottom.
        if state.is_playing or vc.is_playing():
            try:
                if state.current:
                    player_title = state.current['title']
                    player_webpage_url = state.current.get('url', '')

                    # Use cached metadata only — avoid a blocking yt-dlp extraction
                    # that would stall the event loop and miss the heartbeat deadline.
                    current_data = await get_cached_info(get_cache_key(player_webpage_url, "single")) \
                        if player_webpage_url else None
                    thumbnail = current_data.get('thumbnail') if current_data else None
                    duration = current_data.get('duration') if current_data else None

                    platform_emoji = get_platform_emoji(state.current.get('extractor', 'generic'))
                    vol = f" {get_volume_emoji(state.volume)}" if state.volume != 1.0 else ""
                    player_title_display = rtl_format(player_title)

                    embed = discord.Embed(
                        title=f"{platform_emoji} Now Playing",
                        description=f"**{player_title_display}**{vol}",
                        color=0x5865F2,
                        url=player_webpage_url
                    )

                    if thumbnail:
                        embed.set_thumbnail(url=thumbnail)

                    embed.add_field(name="🔗 Link", value=f"[Click here]({player_webpage_url})", inline=True)

                    if duration:
                        minutes, seconds = divmod(duration, 60)
                        embed.add_field(name="⏱️ Duration", value=f"{int(minutes)}:{int(seconds):02d}", inline=True)

                    queue_len = len(state.queue)
                    if queue_len > 0:
                        up_next_title = state.queue[0]["title"][:50]
                        embed.add_field(
                            name="📜 Queue",
                            value=f"{queue_len} song{'s' if queue_len != 1 else ''} queued\n🎵 **Up next:** {up_next_title}",
                            inline=False
                        )
                    else:
                        embed.add_field(name="📜 Queue", value="0 songs queued", inline=False)

                    if state.loop_mode:
                        embed.add_field(name="🔁 Loop", value=state.get_loop_status(), inline=True)

                    embed.add_field(name="🔊 Volume", value=f"{state.get_volume_percent()}%", inline=True)

                    footer_parts = []
                    if queue_len > 0:
                        footer_parts.append(f"{queue_len} in queue")
                    if state.loop_mode:
                        footer_parts.append(f"🔁 {state.get_loop_status()}")
                    footer_parts.append(f"🔊 {state.get_volume_percent()}%")
                    embed.set_footer(text=" • ".join(footer_parts))
                    embed.timestamp = discord.utils.utcnow()
                    await send_fresh_music_message(ctx, guild_id, embed)
                else:
                    embed = discord.Embed(
                        title=f"{emoji} Queued",
                        description=f"**{title_display}**",
                        color=0x5865F2,
                        url=url
                    )
                    queue_len = len(state.queue)
                    embed.add_field(
                        name="📜 Queue",
                        value=f"{queue_len} song{'s' if queue_len != 1 else ''} queued",
                        inline=False
                    )
                    embed.add_field(name="🔊 Volume", value=f"{state.get_volume_percent()}%", inline=True)
                    embed.set_footer(text=f"🔊 {state.get_volume_percent()}%")
                    embed.timestamp = discord.utils.utcnow()
                    await send_fresh_music_message(ctx, guild_id, embed)
            except Exception as e:
                logger.error(f"❌ Failed to refresh embed after queue add: {e}")

        if not state.is_playing and not vc.is_playing():
            await play_next(ctx)

    except asyncio.TimeoutError:
        cancel_background_tasks(guild_id)
        await ctx.send("⏱️ Request timed out")
    except Exception as e:
        cancel_background_tasks(guild_id)
        logger.error(f"❌ Play error: {e}")
        await ctx.send(f"❌ Error: {str(e)[:100]}")

@bot.command(name="pause", aliases=CMD_PAUSE_ALIASES)
async def pause(ctx):
    vc = ctx.guild.voice_client
    if not vc or not vc.is_playing():
        return await ctx.send("❌ Nothing playing")
    state = get_state(ctx.guild.id)
    vc.pause()
    _log_action("PAUSED", "⏸️")

    # Update view buttons
    guild_id = ctx.guild.id
    if guild_id in active_music_views:
        view = active_music_views[guild_id]
        view.update_buttons()
        if view.message:
            try:
                await view.message.edit(view=view)
            except Exception:
                pass

    title = state.current["title"][:50] if state.current else ""
    await ctx.send(f"⏸️ Paused{f' **{title}**' if title else ''}")
    await refresh_player_panel(ctx, ctx.guild.id)

@bot.command(name="resume", aliases=["r"] + CMD_RESUME_ALIASES)
async def resume(ctx):
    vc = ctx.guild.voice_client
    if not vc or not vc.is_paused():
        return await ctx.send("❌ Nothing paused")
    state = get_state(ctx.guild.id)
    vc.resume()
    _log_action("RESUMED", "▶️")

    # Update view buttons
    guild_id = ctx.guild.id
    if guild_id in active_music_views:
        view = active_music_views[guild_id]
        view.update_buttons()
        if view.message:
            try:
                await view.message.edit(view=view)
            except Exception:
                pass

    title = state.current["title"][:50] if state.current else ""
    await ctx.send(f"▶️ Resumed{f' **{title}**' if title else ''}")
    await refresh_player_panel(ctx, ctx.guild.id)

@bot.command(name="skip", aliases=["next", "s"] + CMD_SKIP_ALIASES)
async def skip(ctx, amount: int = 1):
    vc = ctx.guild.voice_client
    if not vc or not vc.is_playing():
        return await ctx.send("❌ Nothing playing")

    state = get_state(ctx.guild.id)

    # Capture current song title before skipping
    current_title = state.current["title"] if state.current else None

    if state.loop_mode:
        state.disable_loop()
        await ctx.send("🔁 Loop disabled")

    if amount > 1:
        skip_count = min(amount - 1, len(state.queue))
        for _ in range(skip_count):
            state.queue.popleft()

    # Peek at what's coming next
    up_next = state.queue[0] if state.queue else None

    vc.stop()
    _log_action(f"SKIPPED {amount} {'SONG' if amount == 1 else 'SONGS'}", "⏭️")

    if current_title:
        msg = f"⏭️ Skipped **{current_title[:50]}**"
    else:
        msg = f"⏭️ Skipped{f' {amount} songs' if amount > 1 else ''}"

    if up_next:
        msg += f"\n🎵 **Up next:** {up_next['title'][:50]}"
    else:
        msg += f"\n📭 Queue is empty"

    await ctx.send(msg)

@bot.command(name="stop", aliases=["st"] + CMD_STOP_ALIASES)
async def stop(ctx):
    vc = ctx.guild.voice_client
    if not vc:
        return await ctx.send("❌ Not in voice")

    state = get_state(ctx.guild.id)
    queue_count = len(state.queue)
    cancel_background_tasks(ctx.guild.id)
    state.was_stopped = True
    state.clear()

    if vc.is_playing():
        vc.stop()

    _log_action("STOPPED & CLEARED QUEUE", "⏹️")
    msg = "⏹️ Stopped"
    if queue_count > 0:
        msg += f" • Cleared **{queue_count}** song{'s' if queue_count != 1 else ''}"
    await ctx.send(msg)

@bot.command(name="queue", aliases=["q", "list"] + CMD_QUEUE_ALIASES)
async def queue_list(ctx):
    state = get_state(ctx.guild.id)

    if not state.queue and not state.current:
        return await ctx.send("📭 Queue is empty")

    total = len(state.queue) + (1 if state.current else 0)
    embed = discord.Embed(
        title="🎵 Queue",
        description=f"**{total} track{'s' if total != 1 else ''} total**",
        color=0x7289DA,
    )

    if state.current:
        loop_info = f" 🔁 {state.get_loop_status()}" if state.loop_mode else ""
        embed.add_field(
            name="🎶 Now Playing",
            value=f"**{state.current['title'][:60]}**{loop_info}",
            inline=False,
        )

    if state.queue:
        songs = list(state.queue)[:10]
        text = "\n".join([f"`{i+1:>2}.` {s['title'][:50]}" for i, s in enumerate(songs)])
        if len(state.queue) > 10:
            text += f"\n`   ` *…and {len(state.queue) - 10} more*"
        embed.add_field(name=f"📜 Up Next ({len(state.queue)})", value=text, inline=False)

    footer_parts = []
    if state.loop_mode:
        footer_parts.append(f"🔁 Loop: {state.get_loop_status()}")
    footer_parts.append(f"🔊 {state.get_volume_percent()}%")
    embed.set_footer(text=" • ".join(footer_parts))
    embed.timestamp = discord.utils.utcnow()

    await ctx.send(embed=embed)
    await refresh_player_panel(ctx, ctx.guild.id)

@bot.command(name="clear", aliases=["clr"] + CMD_CLEAR_ALIASES)
async def clear_queue(ctx):
    state = get_state(ctx.guild.id)

    if not state.queue and not state.loop_mode:
        return await ctx.send("❌ Queue already empty")

    cancel_background_tasks(ctx.guild.id)
    count = len(state.queue)
    state.queue.clear()

    loop_stopped = False
    if state.loop_mode:
        state.disable_loop()
        loop_stopped = True

    parts = []
    if count > 0:
        parts.append(f"🗑️ Cleared **{count}** song{'s' if count != 1 else ''}")
    if loop_stopped:
        parts.append("🔁 Loop stopped")
    msg = "\n".join(parts) if parts else "✅ Queue cleared"

    _log_action(f"CLEARED {count} SONGS" + (" & LOOP" if loop_stopped else ""), "🗑️")
    await ctx.send(msg)
    await refresh_player_panel(ctx, ctx.guild.id)

@bot.command(name="volume", aliases=["vol", "v"] + CMD_VOLUME_ALIASES)
async def volume(ctx, level: str = None):
    state = get_state(ctx.guild.id)

    if level is None:
        vol = state.get_volume_percent()
        bar = create_volume_bar(state.volume)
        emoji = get_volume_emoji(state.volume)
        return await ctx.send(f"{emoji} **{vol}%**\n{bar}")

    try:
        level = int(level.rstrip("%"))
        if level < 0 or level > 200:
            return await ctx.send("❌ Volume: 0-200%")

        state.set_volume(level / 100.0)
        vc = ctx.guild.voice_client
        if vc and vc.source:
            vc.source.volume = state.volume

        bar = create_volume_bar(state.volume)
        emoji = get_volume_emoji(state.volume)
        _log_action(f"VOLUME SET TO {level}%", "🔊")
        await ctx.send(f"{emoji} Volume: **{level}%**\n{bar}")
        await refresh_player_panel(ctx, ctx.guild.id)
    except ValueError:
        await ctx.send(f"❌ Usage: `{PREFIX}volume <0-200>`")

@bot.command(name="resetplayer", aliases=CMD_EMBEDRESET_ALIASES)
async def reset_player_command(ctx):
    ok, message = await reset_player_panel_message(ctx.channel, ctx.guild.id)
    if ok:
        await ctx.send(message, delete_after=8)
    else:
        await ctx.send(message)

if USE_LOOP_FEATURE:

    @bot.command(name="loop", aliases=CMD_LOOP_ALIASES)
    async def loop_command(ctx, count: int = None):
        vc = ctx.guild.voice_client
        state = get_state(ctx.guild.id)

        if not vc or (not vc.is_playing() and not vc.is_paused()):
            return await ctx.send("❌ Nothing playing")

        if not state.current:
            return await ctx.send("❌ No track to loop")

        if state.loop_mode and count is None:
            state.disable_loop()
            _log_action("LOOP DISABLED", "🔁")
            await ctx.send("🔁 Loop disabled")
            await refresh_player_panel(ctx, ctx.guild.id)
            return

        if count is not None:
            if count < 1:
                return await ctx.send("❌ Count must be at least 1")
            if count > 1000:
                return await ctx.send("❌ Max 1000 loops")

        state.enable_loop(count)
        title = state.current["title"]

        loop_info = "∞" if count is None else f"{count}x"
        _log_action(f"LOOP ENABLED: {loop_info}", "🔁")

        msg = f"🔁 Looping **{title}** ∞" if count is None else f"🔁 Looping **{title}** {count}x"
        if state.queue:
            msg += f"\n💡 Use `{PREFIX}stoploop` to continue queue"

        await ctx.send(msg)
        await refresh_player_panel(ctx, ctx.guild.id)

    @bot.command(name="stoploop", aliases=CMD_STOPLOOP_ALIASES)
    async def stoploop(ctx):
        state = get_state(ctx.guild.id)

        if not state.loop_mode:
            return await ctx.send("❌ Not looping")

        state.disable_loop()

        msg = "🔁 Loop stopped"
        if state.queue:
            msg += f" • {len(state.queue)} in queue"

        _log_action("LOOP STOPPED", "🔁")
        await ctx.send(msg)
        await refresh_player_panel(ctx, ctx.guild.id)

@bot.command(name="help", aliases=["h", "commands"])
async def help_command(ctx):
    embed = discord.Embed(
        title="🎵 Music Bot Help",
        description=f"**Prefix:** `{PREFIX}` • Type `{PREFIX}<command>` or use `/` slash commands",
        color=0x5865F2,
    )

    embed.add_field(
        name="🎧 Playback",
        value=(
            f"`{PREFIX}play <query>` — Play music\n"
            f"`{PREFIX}pause` — Pause\n"
            f"`{PREFIX}resume` — Resume\n"
            f"`{PREFIX}skip [n]` — Skip song(s)\n"
            f"`{PREFIX}stop` — Stop & clear queue"
        ),
        inline=False,
    )

    embed.add_field(
        name="📋 Queue",
        value=(
            f"`{PREFIX}queue` — Show queue\n"
            f"`{PREFIX}clear` — Clear queue\n"
            f"`{PREFIX}volume [0-200]` — Set/get volume"
        ),
        inline=False,
    )

    embed.add_field(
        name="🎤 Voice",
        value=(
            f"`{PREFIX}join` — Join VC\n"
            f"`{PREFIX}leave` — Leave VC\n"
            f"`{PREFIX}resetplayer` — Reset player panel"
        ),
        inline=False,
    )

    if USE_LOOP_FEATURE:
        embed.add_field(
            name="🔁 Loop",
            value=(
                f"`{PREFIX}loop [n]` — Loop current track\n"
                f"`{PREFIX}stoploop` — Stop looping"
            ),
            inline=False,
        )

    embed.add_field(
        name="🌐 Supported Sources",
        value="YouTube, SoundCloud, Spotify (via YouTube)",
        inline=False,
    )

    footer = "💡 Also supports / slash commands!" if USE_SLASH_COMMANDS else f"Owner commands: {PREFIX}update, {PREFIX}clearcache, {PREFIX}restart"
    embed.set_footer(text=footer)
    embed.timestamp = discord.utils.utcnow()

    await ctx.send(embed=embed)

@bot.command(name="updateytdlp", aliases=CMD_UPDATE_ALIASES)
@is_bot_owner()
async def update_ytdlp(ctx):
    """Update yt-dlp (+ YouTube solver scripts), Deno and FFmpeg."""
    try:
        import update_deps
        current = yt_dlp.version.__version__
        msg = await ctx.send(
            f"🔄 **Updating playback tools...** (yt-dlp `{current}`, Deno, FFmpeg)\n"
            "This can take a minute."
        )
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(None, lambda: update_deps.update_all(sys.executable))
        lines = [update_deps.format_result(r) for r in results]
        changed = any(r["ok"] and r["old"] != r["new"] for r in results)
        ytdlp_changed = any(r["name"] == "yt-dlp" and r["ok"] and r["old"] != r["new"] for r in results)

        # Deno/FFmpeg are picked up by the next song; yt-dlp needs a restart.
        global FFMPEG_PATH
        FFMPEG_PATH = find_ffmpeg()
        global YOUTUBE_PLAYER_CLIENTS
        runtimes = detect_js_runtimes()
        if runtimes:
            ytdl_format_options["js_runtimes"] = runtimes
            # Deno just got installed: switch off the slow fallback client list.
            if YOUTUBE_PLAYER_CLIENTS == LEGACY_YOUTUBE_PLAYER_CLIENTS and not config.get("youtube_player_clients", "").strip():
                YOUTUBE_PLAYER_CLIENTS = []

        footer = ""
        if ytdlp_changed:
            footer = f"\n💡 Use `{PREFIX}restart` to load the new yt-dlp."
        elif not changed:
            footer = "\n✅ Everything is up to date."
        for r in results:
            logger.info(f"🔧 Update: {update_deps.format_result(r)}")
        await msg.edit(content="**🔧 Update results**\n" + "\n".join(lines) + footer)
    except Exception as e:
        logger.error(f"❌ Update error: {e}")
        await ctx.send(f"❌ Error: {str(e)[:100]}")

@bot.command(name="clearcache", aliases=CMD_CLEARCACHE_ALIASES)
@is_bot_owner()
async def clear_cache_command(ctx):
    """Manually clear all caches (metadata, messages, views)."""
    cleared = await clear_all_caches()
    await ctx.send(
        f"🧹 **Cache Cleared:**\n"
        f"• Metadata: `{cleared['metadata_cache']}` entries\n"
        f"• Messages: `{cleared['queue_messages']}` entries\n"
        f"• Views: `{cleared['music_views']}` entries\n"
        f"• **Total:** `{cleared['total']}` items"
    )

# Restart tracking file
RESTART_PENDING_FILE = os.path.join(BASE_PATH, ".restart_pending")

@bot.command(name="restart", aliases=CMD_RESTART_ALIASES)
@is_bot_owner()
async def restart_bot(ctx):
    """Restart the bot - clears ALL persistent data and reconnects."""
    # Store restart info for post-restart message
    with open(RESTART_PENDING_FILE, "w") as f:
        f.write(f"{ctx.guild.id}\n{ctx.channel.id}\n{ctx.author.id}")

    msg = await ctx.send("🔄 **Restarting bot...**")

    # Fast disconnect - don't wait for each VC, just kill all
    tasks = []
    for vc in bot.voice_clients:
        if vc.is_connected():
            tasks.append(vc.disconnect())

    # Wait max 1 second for disconnects, then force close
    if tasks:
        try:
            await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=1.0)
        except asyncio.TimeoutError:
            pass  # Force close anyway

    # Clear console for clean restart
    print("\033c", end="", flush=True)
    print("╔═══════════════════════════════════════════════════════════════╗")
    print("║                   🔄 Restarting Bot...                       ║")
    print("╚═══════════════════════════════════════════════════════════════╝\n")

    # Instant restart - don't wait for bot.close(), just replace process
    # This is like manual restart (Ctrl+C + run again)
    os.execv(sys.executable, [sys.executable] + sys.argv)

# ═══════════════════════════════════════════════════════════════════
#                            RUN
# ═══════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print(
        """
╔═══════════════════════════════════════════════════════════════╗
║                   🎵 Music Bot Starting                       ║
╚═══════════════════════════════════════════════════════════════╝
    """
    )

    if not TOKEN or TOKEN == "YOUR_BOT_TOKEN_HERE":
        logger.error("❌ Invalid token! Edit config.txt")
        sys.exit(1)

    try:
        bot.run(TOKEN)
    except discord.LoginFailure:
        logger.error("❌ Invalid token!")
    except Exception as e:
        logger.error(f"❌ Fatal: {e}")
