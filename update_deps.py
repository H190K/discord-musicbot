#!/usr/bin/env python3
"""
🔧 Dependency updater for the music bot.

Keeps the playback toolchain fresh, all inside this folder (no sudo):
  - yt-dlp + yt-dlp-ejs  (pip, into the bot's venv)  → `yt-dlp[default]`
  - Deno                 (bin/deno)  → JS runtime yt-dlp uses for YouTube challenges
  - FFmpeg / FFprobe     (bin/ffmpeg, bin/ffprobe) → newest stable static build

Used by the bot's update command and runnable by hand:
    .venv/bin/python update_deps.py
"""

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BIN_DIR = os.path.join(BASE_DIR, "bin")
FFMPEG_STAMP = os.path.join(BIN_DIR, ".ffmpeg_build")
IS_WINDOWS = sys.platform == "win32"
EXE = ".exe" if IS_WINDOWS else ""

DENO_PATH = os.path.join(BIN_DIR, f"deno{EXE}")
FFMPEG_PATH = os.path.join(BIN_DIR, f"ffmpeg{EXE}")
FFPROBE_PATH = os.path.join(BIN_DIR, f"ffprobe{EXE}")

FFMPEG_RELEASES_API = "https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/tags/latest"
HTTP_HEADERS = {"User-Agent": "music-bot-updater"}


def _machine():
    m = platform.machine().lower()
    if m in ("x86_64", "amd64"):
        return "x86_64"
    if m in ("aarch64", "arm64"):
        return "aarch64"
    return m


def _run(cmd, timeout=300):
    # Explicit UTF-8 + replace: Windows' default code page can't decode pip output.
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout)


def _ssl_context():
    # python.org macOS builds ship without CA certs until "Install Certificates"
    # is run; certifi (pulled in by yt-dlp[default]) fixes that.
    try:
        import certifi
        import ssl
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return None


def _urlopen(url, timeout):
    req = urllib.request.Request(url, headers=HTTP_HEADERS)
    return urllib.request.urlopen(req, timeout=timeout, context=_ssl_context())


def _download(url, dest, timeout=300):
    with _urlopen(url, timeout) as resp, open(dest, "wb") as out:
        shutil.copyfileobj(resp, out, length=1024 * 1024)


def _install_binary(src, dest):
    """Move a freshly extracted binary into place.
    POSIX: atomic rename, running processes keep the old inode.
    Windows: a running .exe can't be overwritten but can be renamed,
    so move it aside first (cleaned up on the next update)."""
    os.chmod(src, 0o755)
    try:
        os.replace(src, dest)
        return
    except PermissionError:
        if not IS_WINDOWS:
            raise
    old = dest + ".old"
    try:
        os.remove(old)
    except OSError:
        pass
    os.replace(dest, old)
    os.replace(src, dest)


def _extract_tar(archive, dest):
    with tarfile.open(archive) as tf:
        if hasattr(tarfile, "data_filter"):  # 3.12+ and recent 3.8-3.11 patch releases
            tf.extractall(dest, filter="data")
        else:
            for member in tf.getmembers():
                root = os.path.realpath(dest)
                target = os.path.realpath(os.path.join(dest, member.name))
                if target != root and not target.startswith(root + os.sep):
                    raise RuntimeError(f"unsafe path in archive: {member.name}")
            tf.extractall(dest)


def _first_line(text):
    lines = (text or "").strip().splitlines()
    return lines[0].strip() if lines else ""


def _last_line(text):
    lines = (text or "").strip().splitlines()
    return lines[-1].strip() if lines else "unknown error"


# ─────────────────────────────────────────────────────────────────
#   VERSIONS
# ─────────────────────────────────────────────────────────────────
def ytdlp_version(python=None):
    result = _run([python or sys.executable, "-c", "import yt_dlp; print(yt_dlp.version.__version__)"], timeout=60)
    return result.stdout.strip() if result.returncode == 0 else None


def deno_version():
    if not os.path.exists(DENO_PATH):
        return None
    result = _run([DENO_PATH, "--version"], timeout=30)
    match = re.search(r"deno (\S+)", result.stdout or "")
    return match.group(1) if match else None


def ffmpeg_version():
    if not os.path.exists(FFMPEG_PATH):
        return None
    result = _run([FFMPEG_PATH, "-version"], timeout=30)
    match = re.search(r"ffmpeg version (\S+)", result.stdout or "")
    return match.group(1) if match else None


# ─────────────────────────────────────────────────────────────────
#   UPDATERS — each returns {"name", "old", "new", "ok", "detail"}
# ─────────────────────────────────────────────────────────────────
def update_ytdlp(python=None):
    python = python or sys.executable
    old = ytdlp_version(python)
    # [default] pulls in yt-dlp-ejs (YouTube challenge solver scripts),
    # curl-cffi/brotli/websockets etc.
    result = _run([python, "-m", "pip", "install", "--upgrade", "--quiet", "yt-dlp[default]"], timeout=300)
    new = ytdlp_version(python)
    ok = result.returncode == 0 and bool(new)
    return {"name": "yt-dlp", "old": old, "new": new, "ok": ok,
            "detail": "" if ok else _last_line(result.stderr or result.stdout)}


def update_deno():
    old = deno_version()
    os.makedirs(BIN_DIR, exist_ok=True)
    try:
        if old:
            result = _run([DENO_PATH, "upgrade", "--quiet"], timeout=300)
            if result.returncode != 0:
                raise RuntimeError(_last_line(result.stderr or result.stdout))
        else:
            arch = _machine()
            if IS_WINDOWS:
                target = f"{arch}-pc-windows-msvc"
            elif sys.platform == "darwin":
                target = f"{arch}-apple-darwin"
            else:
                target = f"{arch}-unknown-linux-gnu"
            url = f"https://github.com/denoland/deno/releases/latest/download/deno-{target}.zip"
            with tempfile.TemporaryDirectory(dir=BIN_DIR) as tmp:
                archive = os.path.join(tmp, "deno.zip")
                _download(url, archive)
                with zipfile.ZipFile(archive) as zf:
                    zf.extract(f"deno{EXE}", tmp)
                _install_binary(os.path.join(tmp, f"deno{EXE}"), DENO_PATH)
        new = deno_version()
        return {"name": "Deno", "old": old, "new": new, "ok": bool(new), "detail": ""}
    except Exception as e:
        return {"name": "Deno", "old": old, "new": deno_version(), "ok": False, "detail": str(e)[:120]}


def _ffmpeg_platform():
    """BtbN build name + archive type for this OS, or None (e.g. macOS: no builds)."""
    arch = _machine()
    if IS_WINDOWS:
        return ("winarm64" if arch == "aarch64" else "win64"), ".zip"
    if sys.platform.startswith("linux"):
        return ("linuxarm64" if arch == "aarch64" else "linux64"), ".tar.xz"
    return None


def _system_ffmpeg_version():
    path = shutil.which("ffmpeg")
    if not path:
        return None
    try:
        result = _run([path, "-version"], timeout=30)
    except Exception:
        return None
    match = re.search(r"ffmpeg version (\S+)", result.stdout or "")
    return match.group(1) if match else None


def _pick_ffmpeg_asset(assets):
    """Newest stable release line (e.g. n9.0) of the static GPL build for this platform."""
    platform_info = _ffmpeg_platform()
    if not platform_info:
        return None
    plat, ext = platform_info
    pattern = re.compile(rf"^ffmpeg-n(\d+)\.(\d+)-latest-{plat}-gpl-\d+\.\d+{re.escape(ext)}$")
    best = None
    for asset in assets:
        match = pattern.match(asset.get("name", ""))
        if match:
            version = (int(match.group(1)), int(match.group(2)))
            if best is None or version > best[0]:
                best = (version, asset)
    return best[1] if best else None


def update_ffmpeg():
    old = ffmpeg_version()
    os.makedirs(BIN_DIR, exist_ok=True)
    try:
        asset = None
        if _ffmpeg_platform():
            with _urlopen(FFMPEG_RELEASES_API, 60) as resp:
                assets = json.load(resp).get("assets", [])
            asset = _pick_ffmpeg_asset(assets)
        if not asset:
            if old:
                return {"name": "FFmpeg", "old": old, "new": old, "ok": True,
                        "detail": "no newer static build for this platform"}
            system = _system_ffmpeg_version()
            hint = " (macOS: `brew install ffmpeg`)" if sys.platform == "darwin" else ""
            return {"name": "FFmpeg", "old": system, "new": system, "ok": bool(system),
                    "detail": ("no static build for this platform, using system ffmpeg" if system
                               else "no static build for this platform and no ffmpeg on PATH" + hint)}

        build_id = f"{asset['name']}@{asset.get('updated_at', '')}"
        try:
            with open(FFMPEG_STAMP) as f:
                if f.read().strip() == build_id and old:
                    return {"name": "FFmpeg", "old": old, "new": old, "ok": True, "detail": ""}
        except OSError:
            pass

        with tempfile.TemporaryDirectory(dir=BIN_DIR) as tmp:
            archive = os.path.join(tmp, asset["name"])
            _download(asset["browser_download_url"], archive, timeout=600)
            if archive.endswith(".zip"):
                with zipfile.ZipFile(archive) as zf:
                    zf.extractall(tmp)
            else:
                _extract_tar(archive, tmp)
            for name, dest in ((f"ffmpeg{EXE}", FFMPEG_PATH), (f"ffprobe{EXE}", FFPROBE_PATH)):
                found = None
                for root, _, files in os.walk(tmp):
                    if name in files and os.path.basename(root) == "bin":
                        found = os.path.join(root, name)
                        break
                if not found:
                    raise RuntimeError(f"{name} missing from {asset['name']}")
                _install_binary(found, dest)

        with open(FFMPEG_STAMP, "w") as f:
            f.write(build_id)
        new = ffmpeg_version()
        return {"name": "FFmpeg", "old": old, "new": new, "ok": bool(new), "detail": ""}
    except Exception as e:
        return {"name": "FFmpeg", "old": old, "new": ffmpeg_version(), "ok": False, "detail": str(e)[:120]}


def update_all(python=None):
    return [update_ytdlp(python), update_deno(), update_ffmpeg()]


def format_result(r):
    if not r["ok"]:
        return f"❌ {r['name']}: {r['detail'] or 'failed'}" + (f" (still `{r['new']}`)" if r.get("new") else "")
    if r["old"] != r["new"]:
        return f"✅ {r['name']}: `{r['old'] or 'not installed'}` → `{r['new']}`"
    return f"✔️ {r['name']}: `{r['new']}` (up to date)" + (f" — {r['detail']}" if r["detail"] else "")


if __name__ == "__main__":
    for res in update_all():
        print(format_result(res))
