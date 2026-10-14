#!/usr/bin/env python3
"""
🎵 Music Bot Launcher (Linux, macOS, Windows)
- Creates a local virtual environment (.venv) and installs dependencies
- Checks FFmpeg, voice support, playback tools and config.txt
- Runs the bot with auto-restart on crash / freeze
- Shows bot output for debugging
"""

import os
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'

import sys

MIN_PYTHON = (3, 10)
if sys.version_info < MIN_PYTHON:
    sys.stderr.write(
        "Python %d.%d or newer is required (found %d.%d).\n"
        "Download it from https://www.python.org/downloads/\n"
        % (MIN_PYTHON[0], MIN_PYTHON[1], sys.version_info[0], sys.version_info[1])
    )
    sys.exit(1)

import platform
import shutil
import signal
import subprocess
import threading
import time
from collections import deque

IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"

# Never let emoji / box-drawing output crash on a legacy Windows console
# code page (cp1252 etc.) or a redirected stream.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

if IS_WINDOWS:
    # Enables ANSI colour (VT) processing in the classic Windows console.
    try:
        os.system("")
    except Exception:
        pass
    # Child Python processes (bot, pip, update_deps) print emoji too.
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    os.environ.setdefault("PYTHONUTF8", "1")

BOT_FILE = "music_bot.py"
CONFIG_FILE = "config.txt"
CONFIG_EXAMPLE_FILE = "config.example.txt"
REQUIREMENTS_FILE = "requirements.txt"
VENV_DIR = ".venv"
BOT_PYTHON_ENV = "BOT_PYTHON"
RESTART_DELAY = 5
MAX_RESTART_DELAY = 60
STARTUP_TIMEOUT = 20
CHECK_INTERVAL = 3
HEARTBEAT_FILE = ".bot_heartbeat"
BOT_PID_FILE = ".launcher_bot.pid"
RESTART_PENDING_FILE = ".restart_pending"
PYTHON_DOWNLOAD_URL = "https://www.python.org/downloads/"
HOMEBREW_URL = "https://brew.sh"
# Where Homebrew puts binaries (Apple Silicon, Intel).
HOMEBREW_BIN_DIRS = ("/opt/homebrew/bin", "/usr/local/bin")

# ANSI colors
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
RESET = "\033[0m"


def parse_config(config_path):
    config = {}
    try:
        with open(config_path, "r", encoding="utf-8-sig") as file_obj:
            for line in file_obj:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, value = line.split("=", 1)
                    config[key.strip()] = value.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return config


config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), CONFIG_FILE)
config = parse_config(config_path)
HEARTBEAT_TIMEOUT = float(config.get("heartbeat_timeout", "90.0"))
HEARTBEAT_GRACE = max(CHECK_INTERVAL * 3, 15.0)
INTENTIONAL_RESTART_TIMEOUT = max(STARTUP_TIMEOUT, HEARTBEAT_TIMEOUT)


def get_script_dir():
    return os.path.dirname(os.path.abspath(__file__))


def get_bot_pid_path():
    return os.path.join(get_script_dir(), BOT_PID_FILE)


def get_heartbeat_path():
    return os.path.join(get_script_dir(), HEARTBEAT_FILE)


def get_restart_pending_path():
    return os.path.join(get_script_dir(), RESTART_PENDING_FILE)


def exe_name(name):
    return f"{name}.exe" if IS_WINDOWS else name


def get_venv_python():
    venv_dir = os.path.join(get_script_dir(), VENV_DIR)
    if IS_WINDOWS:
        candidates = (os.path.join(venv_dir, "Scripts", "python.exe"),)
    else:
        candidates = (
            os.path.join(venv_dir, "bin", "python3"),
            os.path.join(venv_dir, "bin", "python"),
        )
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    return None


def ensure_python_bin():
    override = os.environ.get(BOT_PYTHON_ENV)
    if override:
        return override

    if sys.prefix != sys.base_prefix or os.environ.get("VIRTUAL_ENV"):
        return sys.executable

    venv_python = get_venv_python()
    if venv_python:
        return venv_python

    print(f"[{timestamp()}] 🐍 Creating local virtual environment...")
    venv_dir = os.path.join(get_script_dir(), VENV_DIR)
    result = subprocess.run(
        [sys.executable, "-m", "venv", venv_dir],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        venv_python = get_venv_python()
        if venv_python:
            print_step("Created local virtual environment")
            return venv_python

    details = (result.stderr or result.stdout or "").strip().splitlines()
    if details:
        print_step(f"Could not create local virtual environment: {details[-1]}", False)
    else:
        print_step("Could not create local virtual environment", False)
    if not IS_WINDOWS and not IS_MAC:
        print(f"   {YELLOW}On Debian/Ubuntu install it with: sudo apt-get install python3-venv{RESET}")
    return None


def detached_kwargs():
    """Run installers in their own process group/session so a Ctrl+C in the
    launcher doesn't kill them half-way."""
    if IS_WINDOWS:
        return {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)}
    return {"start_new_session": True}


def run_python(args, check=True, capture=True):
    python_bin = ensure_python_bin()
    if not python_bin:
        return False, ""

    try:
        if capture:
            result = subprocess.run(
                [python_bin, *args],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=check,
            )
            return result.returncode == 0, result.stdout
        result = subprocess.run(
            [python_bin, *args],
            check=check,
            **detached_kwargs(),
        )
        return result.returncode == 0, ""
    except subprocess.CalledProcessError:
        return False, ""
    except OSError:
        return False, ""
    except KeyboardInterrupt:
        return False, ""


def timestamp():
    return time.strftime("%H:%M:%S")


def print_step(msg, success=True):
    icon = f"{GREEN}✓{RESET}" if success else f"{RED}✗{RESET}"
    print(f"[{timestamp()}] {icon} {msg}")


def run_cmd(cmd, check=True, capture=True):
    """Run a command. `cmd` is a list (preferred) or a shell string."""
    shell = isinstance(cmd, str)
    try:
        if capture:
            result = subprocess.run(
                cmd, shell=shell, capture_output=True, text=True,
                encoding="utf-8", errors="replace", check=check,
            )
            return result.returncode == 0, result.stdout
        else:
            result = subprocess.run(
                cmd, shell=shell, check=check,
                **detached_kwargs(),
            )
            return result.returncode == 0, ""
    except subprocess.CalledProcessError:
        return False, ""
    except OSError:
        return False, ""
    except KeyboardInterrupt:
        return False, ""


def add_to_path(directory):
    """Prepend a directory to PATH for this launcher and the bot it starts."""
    if not directory or not os.path.isdir(directory):
        return
    parts = os.environ.get("PATH", "").split(os.pathsep)
    if directory not in parts:
        os.environ["PATH"] = os.pathsep.join([directory] + [p for p in parts if p])


def find_brew():
    path = shutil.which("brew")
    if path:
        return path
    for directory in HOMEBREW_BIN_DIRS:
        candidate = os.path.join(directory, "brew")
        if os.path.exists(candidate):
            return candidate
    return None


def find_ffmpeg():
    """Bundled bin/ffmpeg first (what the bot prefers), then PATH."""
    base = get_script_dir()
    bundled = os.path.join(base, "bin", exe_name("ffmpeg"))
    if os.path.exists(bundled):
        return bundled
    if IS_WINDOWS:
        local = os.path.join(base, "ffmpeg", "bin", "ffmpeg.exe")
        if os.path.exists(local):
            return local
    return shutil.which("ffmpeg")


def run_update_deps():
    """Fetch Deno / static FFmpeg / yt-dlp[default] into this folder."""
    update_script = os.path.join(get_script_dir(), "update_deps.py")
    if not os.path.exists(update_script):
        print_step("update_deps.py not found", False)
        return False
    success, _ = run_python([update_script], check=False, capture=False)
    return success


def check_ffmpeg_linux():
    if shutil.which("ffmpeg"):
        print_step("FFmpeg found")
        return True

    print_step("FFmpeg not found - installing...", False)

    pkg_mgrs = [
        ("apt-get", "apt-get update && apt-get install -y ffmpeg"),
        ("yum", "yum install -y ffmpeg"),
        ("dnf", "dnf install -y ffmpeg"),
        ("apk", "apk add ffmpeg"),
        ("pacman", "pacman -S --noconfirm ffmpeg"),
    ]

    for pkg_name, install_cmd in pkg_mgrs:
        if shutil.which(pkg_name):
            print(f"[{timestamp()}] 📦 Installing FFmpeg via {pkg_name}...")
            success, _ = run_cmd(install_cmd, check=False)
            if success:
                print_step(f"FFmpeg installed via {pkg_name}")
                return True
            break

    print_step("Could not install FFmpeg automatically", False)
    return False


def check_ffmpeg_mac():
    for directory in HOMEBREW_BIN_DIRS:
        add_to_path(directory)

    if find_ffmpeg():
        print_step("FFmpeg found")
        return True

    print_step("FFmpeg not found - installing...", False)
    brew = find_brew()
    if brew:
        print(f"[{timestamp()}] 📦 Installing FFmpeg via Homebrew (this can take a few minutes)...")
        success, _ = run_cmd([brew, "install", "ffmpeg"], check=False, capture=False)
        if success and find_ffmpeg():
            print_step("FFmpeg installed via Homebrew")
            return True
        print_step("Homebrew could not install FFmpeg", False)
        print(f"   {YELLOW}Run 'brew install ffmpeg' in Terminal, then start the bot again.{RESET}")
        return False

    print_step("Homebrew is not installed", False)
    print(f"   {YELLOW}Install Homebrew from {HOMEBREW_URL}, then run: brew install ffmpeg{RESET}")
    return False


def check_ffmpeg_windows():
    if find_ffmpeg():
        print_step("FFmpeg found")
        return True

    print_step("FFmpeg not found - downloading a static build into bin\\ ...", False)
    run_update_deps()
    if find_ffmpeg():
        print_step("FFmpeg installed into bin\\")
        return True

    winget = shutil.which("winget")
    if winget:
        print(f"[{timestamp()}] 📦 Installing FFmpeg via winget (Gyan.FFmpeg)...")
        run_cmd(
            [winget, "install", "-e", "--id", "Gyan.FFmpeg",
             "--accept-source-agreements", "--accept-package-agreements"],
            check=False, capture=False,
        )
        # winget links new tools here, but this console's PATH is stale.
        local_appdata = os.environ.get("LOCALAPPDATA", "")
        if local_appdata:
            add_to_path(os.path.join(local_appdata, "Microsoft", "WinGet", "Links"))
        if find_ffmpeg():
            print_step("FFmpeg installed via winget")
            return True

    print_step("Could not install FFmpeg automatically", False)
    print(f"   {YELLOW}Download it from https://www.gyan.dev/ffmpeg/builds/ and put ffmpeg.exe in the bin folder,{RESET}")
    print(f"   {YELLOW}or run: winget install Gyan.FFmpeg  (then open a new terminal){RESET}")
    return False


def check_ffmpeg():
    print(f"\n{CYAN}╔═══════════════════════════════════════════════════════════╗")
    print(f"║              🔧 Checking Dependencies                        ║")
    print(f"╚═══════════════════════════════════════════════════════════╝{RESET}")

    print(f"[{timestamp()}] 🎧 Checking FFmpeg...")
    if IS_WINDOWS:
        return check_ffmpeg_windows()
    if IS_MAC:
        return check_ffmpeg_mac()
    return check_ffmpeg_linux()


def voice_deps_ok():
    success, output = run_python(
        ["-c", "from nacl.bindings import SODIUM_VERSION; print('ok')"],
        check=False,
    )
    return success and "ok" in output


def check_voice_deps():
    """Voice needs PyNaCl + libsodium. Windows/macOS wheels bundle libsodium;
    on Linux the system library may be needed."""
    print(f"[{timestamp()}] 🔊 Checking voice dependencies...")

    if voice_deps_ok():
        print_step("Voice dependencies OK")
        return True

    if IS_WINDOWS or IS_MAC:
        print(f"[{timestamp()}] 📦 Installing PyNaCl for voice support...")
        run_python(["-m", "pip", "install", "--upgrade", "PyNaCl"], check=False, capture=False)
    else:
        print(f"[{timestamp()}] 📦 Installing libsodium for voice support...")
        pkg_mgrs = [
            ("apt-get", "apt-get update && apt-get install -y libsodium-dev"),
            ("yum", "yum install -y libsodium-devel"),
            ("dnf", "dnf install -y libsodium-devel"),
            ("apk", "apk add libsodium-dev"),
            ("pacman", "pacman -S --noconfirm libsodium"),
        ]

        for pkg_name, install_cmd in pkg_mgrs:
            if shutil.which(pkg_name):
                run_cmd(install_cmd, check=False)
                break

        print(f"[{timestamp()}] 📦 Reinstalling PyNaCl with voice support...")
        run_python(["-m", "pip", "install", "--force-reinstall", "PyNaCl"], check=False, capture=False)

    # Verify nacl actually works now
    if voice_deps_ok():
        print_step("Voice dependencies OK")
        return True

    print_step("Voice dependencies may not be fully working", False)
    return True


def check_python_deps():
    print(f"[{timestamp()}] 🐍 Checking Python packages...")

    # (package, import name, required to start)
    packages = [
        ("discord.py", "discord", True),
        ("yt-dlp", "yt_dlp", True),
        ("aiohttp", "aiohttp", True),
        ("PyNaCl", "nacl", True),
        ("davey", "davey", False),  # discord.py voice encryption (DAVE)
    ]

    def find_missing():
        return [
            (name, required) for name, import_name, required in packages
            if not run_python(["-c", f"import {import_name}"], check=False)[0]
        ]

    missing = find_missing()
    if not missing:
        print_step("All Python packages installed")
        return True

    print(f"[{timestamp()}] 📦 Installing missing packages: {', '.join(name for name, _ in missing)}")

    requirements = os.path.join(get_script_dir(), REQUIREMENTS_FILE)
    if os.path.exists(requirements):
        run_python(["-m", "pip", "install", "-q", "-r", requirements], check=False, capture=False)
    else:
        run_python(["-m", "pip", "install", "-q", *[name for name, _ in missing]], check=False, capture=False)

    missing = find_missing()
    if not any(required for _, required in missing):
        print_step("Python packages installed")
        for name, _ in missing:
            print_step(f"Optional package {name} could not be installed", False)
        return True

    print_step("Could not install Python packages automatically", False)
    print(f"   {YELLOW}Try manually: \"{ensure_python_bin()}\" -m pip install -r {REQUIREMENTS_FILE}{RESET}")
    return False


def check_playback_tools():
    """Bundled Deno + FFmpeg (bin/) and yt-dlp's YouTube solver scripts.
    Missing pieces are fetched once by update_deps.py; the bot's update
    command keeps them current afterwards."""
    print(f"[{timestamp()}] 🎬 Checking playback tools (Deno, FFmpeg, yt-dlp-ejs)...")
    base = get_script_dir()
    have_deno = os.path.exists(os.path.join(base, "bin", exe_name("deno")))
    # macOS has no static build: Homebrew/system ffmpeg counts.
    have_ffmpeg = (
        os.path.exists(os.path.join(base, "bin", exe_name("ffmpeg")))
        or (IS_MAC and shutil.which("ffmpeg") is not None)
    )
    have_ejs, _ = run_python(["-c", "import yt_dlp_ejs"], check=False)

    if have_deno and have_ffmpeg and have_ejs:
        print_step("Playback tools ready")
        return True

    print(f"[{timestamp()}] 📦 Installing playback tools (one-time download)...")
    run_update_deps()

    if os.path.exists(os.path.join(base, "bin", exe_name("deno"))):
        print_step("Playback tools ready")
    else:
        # Not fatal: the bot falls back to system ffmpeg / Node and wider YouTube clients.
        print_step("Playback tools incomplete - bot will use slower fallbacks", False)
    return True


def ensure_config_file():
    """First run: create config.txt from config.example.txt and stop so the
    user can fill in the token. Returns True when config.txt exists."""
    if os.path.exists(config_path):
        return True

    example_path = os.path.join(get_script_dir(), CONFIG_EXAMPLE_FILE)
    print()
    if os.path.exists(example_path):
        try:
            shutil.copyfile(example_path, config_path)
        except OSError as e:
            print(f"{RED}❌ Could not create {config_path}: {e}{RESET}")
            return False
        print(f"{YELLOW}╔═══════════════════════════════════════════════════════════╗")
        print(f"║           📝 Fill in your token in config.txt               ║")
        print(f"╚═══════════════════════════════════════════════════════════╝{RESET}")
        print(f"Created: {config_path}")
        print("Open it in a text editor, set token= (and owner=), save, then start the bot again.")
    else:
        print(f"{RED}❌ {CONFIG_FILE} and {CONFIG_EXAMPLE_FILE} are both missing in {get_script_dir()}{RESET}")
    return False


def check_config():
    print(f"[{timestamp()}] ⚙️  Checking config.txt...")

    token = config.get("token", "")
    if token and token != "YOUR_BOT_TOKEN_HERE":
        print_step("Bot token found")
        return True

    print_step("Bot token not configured!", False)
    print(f"   {YELLOW}Fill in your token in config.txt: {config_path}{RESET}")
    return False


def run_prerequisites():
    print(f"\n{GREEN}╔═══════════════════════════════════════════════════════════╗")
    print(f"║                   🎵 MUSIC BOT LAUNCHER                      ║")
    print(f"╠═══════════════════════════════════════════════════════════╣")
    print(f"║  Auto-installs dependencies & runs the bot                 ║")
    print(f"╚═══════════════════════════════════════════════════════════╝{RESET}\n")

    if not ensure_python_bin():
        print(f"\n{RED}❌ Python environment is not ready. Fix errors above and try again.{RESET}")
        return False

    checks = [
        ("FFmpeg", check_ffmpeg),
        ("Python Packages", check_python_deps),
        ("Voice Dependencies", check_voice_deps),
        ("Playback Tools", check_playback_tools),
        ("Config", check_config),
    ]

    all_passed = True
    for name, check_func in checks:
        try:
            if not check_func():
                all_passed = False
        except Exception as e:
            print(f"[{timestamp()}] {RED}✗{RESET} {name} check failed: {e}")
            all_passed = False

    if not all_passed:
        print(f"\n{RED}❌ Prerequisites not met. Fix errors above and try again.{RESET}")
        return False

    print(f"\n{GREEN}✅ All checks passed! Starting bot...{RESET}\n")
    return True


def remove_file(path):
    try:
        os.remove(path)
    except (FileNotFoundError, OSError):
        pass


def write_pid(pid):
    try:
        with open(get_bot_pid_path(), "w", encoding="utf-8") as f:
            f.write(str(pid))
    except OSError:
        pass


def read_pid():
    try:
        with open(get_bot_pid_path(), "r", encoding="utf-8") as f:
            return int(f.read().strip())
    except (FileNotFoundError, ValueError, OSError):
        return None


def _windows_pid_exists(pid):
    # NOTE: os.kill(pid, 0) must never be used on Windows - it sends CTRL_C_EVENT.
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        ERROR_ACCESS_DENIED = 5

        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            # Exists but belongs to someone else.
            return ctypes.get_last_error() == ERROR_ACCESS_DENIED
        try:
            exit_code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return True
            return exit_code.value == STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        pass
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH", "/FO", "CSV"],
            capture_output=True, text=True, errors="replace", check=False,
        )
        return f'"{pid}"' in result.stdout
    except OSError:
        return False


def pid_exists(pid):
    if not pid or pid <= 0:
        return False
    if IS_WINDOWS:
        return _windows_pid_exists(pid)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def is_zombie(pid):
    """Check if a process is a zombie (needs reaping)."""
    if IS_WINDOWS:
        return False
    try:
        with open(f"/proc/{pid}/status", "r") as f:
            for line in f:
                if line.startswith("State:"):
                    return "Z" in line
    except (OSError, IOError):
        pass
    else:
        return False
    if os.path.isdir("/proc"):
        return False
    # macOS / BSD: no /proc
    try:
        result = subprocess.run(
            ["ps", "-o", "stat=", "-p", str(pid)],
            capture_output=True, text=True, check=False,
        )
        return result.stdout.strip().startswith("Z")
    except OSError:
        return False


def _list_python_processes():
    """Yield (pid, process name, command line) for running Python processes."""
    if IS_WINDOWS:
        import base64
        script = (
            "Get-CimInstance Win32_Process | "
            "Where-Object { $_.Name -like 'python*' } | "
            "ForEach-Object { [string]$_.ProcessId + \"`t\" + $_.Name + \"`t\" + $_.CommandLine }"
        )
        encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                check=False, timeout=30,
            )
        except (OSError, subprocess.SubprocessError):
            return
        for line in result.stdout.splitlines():
            parts = line.strip().split("\t", 2)
            if len(parts) == 3:
                yield parts[0], parts[1], parts[2]
        return

    # macOS' "comm" is the full executable path (may contain spaces);
    # "ucomm" is just the name there.
    columns = "pid=,ucomm=,args=" if IS_MAC else "pid=,comm=,args="
    try:
        result = subprocess.run(
            ["ps", "-eo", columns],
            capture_output=True, text=True, check=False,
        )
    except OSError:
        return
    for line in result.stdout.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) == 3:
            yield parts[0], parts[1], parts[2]


def _is_our_bot(args):
    """True only for the bot started from THIS folder. A bot running from
    another folder (a second bot, an old install) is never touched."""
    own_path = os.path.normcase(os.path.abspath(os.path.join(get_script_dir(), BOT_FILE)))
    normalized = os.path.normcase(args.replace('"', "").replace("'", ""))
    return own_path in normalized

def find_bot_pids():
    pids = []
    for pid_text, command_name, args in _list_python_processes():
        if not command_name.lower().startswith("python"):
            continue
        if BOT_FILE not in args or not _is_our_bot(args):
            continue
        try:
            pids.append(int(pid_text))
        except ValueError:
            continue
    own_pid = os.getpid()
    return sorted(set(pid for pid in pids if pid != own_pid))


def get_managed_bot_pid():
    pid = read_pid()
    if pid_exists(pid):
        return pid
    remove_file(get_bot_pid_path())
    discovered = find_bot_pids()
    if len(discovered) == 1:
        pid = discovered[0]
        write_pid(pid)
        return pid
    return None


def _wait_for_exit(pid, timeout):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not pid_exists(pid):
            return True
        if is_zombie(pid):
            return True
        time.sleep(0.25)
    return False


def terminate_pid(pid):
    if not pid_exists(pid):
        return
    if IS_WINDOWS:
        # /T also ends the real interpreter behind a venv's python.exe redirector.
        try:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True, check=False,
            )
        except OSError:
            return
        _wait_for_exit(pid, 8)
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return
    if _wait_for_exit(pid, 8):
        return
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass


def terminate_bot(expected_pid=None):
    targets = []
    if pid_exists(expected_pid):
        targets.append(expected_pid)
    for pid in find_bot_pids():
        if pid not in targets:
            targets.append(pid)
    for pid in targets:
        terminate_pid(pid)
    remove_file(get_bot_pid_path())


_certifi_path = None


def get_certifi_path():
    """python.org macOS builds have no CA bundle until 'Install Certificates'
    is run, which breaks aiohttp/discord.py SSL. certifi fixes that."""
    global _certifi_path
    if _certifi_path is None:
        success, output = run_python(["-c", "import certifi; print(certifi.where())"], check=False)
        path = output.strip() if success else ""
        _certifi_path = path if path and os.path.exists(path) else ""
    return _certifi_path


def launch_bot():
    """Launch the bot with output visible."""
    script_dir = get_script_dir()
    bot_path = os.path.join(script_dir, BOT_FILE)
    python_bin = ensure_python_bin() or sys.executable

    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    if IS_MAC and not env.get("SSL_CERT_FILE"):
        cert_path = get_certifi_path()
        if cert_path:
            env["SSL_CERT_FILE"] = cert_path

    proc = subprocess.Popen(
        [python_bin, "-u", bot_path],
        cwd=script_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
        universal_newlines=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    return proc


class OutputReader:
    """Collects the bot's output without blocking the monitor loop.
    POSIX polls the pipe with select(); Windows can't select() on pipes,
    so a background thread reads it into a queue there."""

    def __init__(self, proc):
        self.proc = proc
        self.queue = None
        if IS_WINDOWS:
            import queue
            self.queue = queue.Queue()
            thread = threading.Thread(target=self._pump, daemon=True)
            thread.start()

    def _pump(self):
        try:
            for line in iter(self.proc.stdout.readline, ""):
                self.queue.put(line)
        except Exception:
            pass

    def read_lines(self):
        lines = []
        if self.queue is not None:
            import queue
            while True:
                try:
                    lines.append(self.queue.get_nowait())
                except queue.Empty:
                    break
            return lines

        import select
        while True:
            ready, _, _ = select.select([self.proc.stdout], [], [], 0.1)
            if not ready:
                break
            line = self.proc.stdout.readline()
            if not line:
                break
            lines.append(line)
        return lines


def is_bot_healthy(launch_time=None):
    heartbeat_path = get_heartbeat_path()
    if not os.path.exists(heartbeat_path):
        # During startup, no heartbeat yet is OK
        if launch_time and time.time() - launch_time < STARTUP_TIMEOUT:
            return True
        return False
    try:
        with open(heartbeat_path, "r", encoding="utf-8") as f:
            heartbeat_time = float(f.read().strip())
    except (OSError, ValueError):
        # Corrupted heartbeat = unhealthy
        if launch_time and time.time() - launch_time < STARTUP_TIMEOUT:
            return True
        return False
    age = time.time() - heartbeat_time
    return age < (HEARTBEAT_TIMEOUT + HEARTBEAT_GRACE)


def get_heartbeat_age():
    """Return seconds since last heartbeat, or None if unavailable."""
    try:
        with open(get_heartbeat_path(), "r", encoding="utf-8") as f:
            heartbeat_time = float(f.read().strip())
        return time.time() - heartbeat_time
    except (OSError, ValueError):
        return None


def is_intentional_restart_pending():
    restart_pending_path = get_restart_pending_path()
    if not os.path.exists(restart_pending_path):
        return False
    try:
        pending_age = time.time() - os.path.getmtime(restart_pending_path)
    except OSError:
        return False
    return pending_age < INTENTIONAL_RESTART_TIMEOUT


def cleanup_state(keep_restart_pending=False):
    remove_file(get_bot_pid_path())
    remove_file(get_heartbeat_path())
    if not keep_restart_pending:
        remove_file(get_restart_pending_path())


def get_bot_memory_mb(bot_pid):
    """Get the bot's memory usage in MB (Linux /proc, macOS ps; 0 elsewhere)."""
    if not bot_pid or IS_WINDOWS:
        return 0
    try:
        with open(f"/proc/{bot_pid}/status", "r") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024
    except (OSError, IOError):
        pass
    if IS_MAC:
        try:
            result = subprocess.run(
                ["ps", "-o", "rss=", "-p", str(bot_pid)],
                capture_output=True, text=True, check=False,
            )
            return int(result.stdout.strip() or 0) / 1024
        except (OSError, ValueError):
            pass
    return 0


_shutdown_requested = False

def _signal_handler(signum, frame):
    global _shutdown_requested
    _shutdown_requested = True


def main():
    # Handle SIGTERM gracefully instead of ignoring it
    try:
        signal.signal(signal.SIGTERM, _signal_handler)
    except (ValueError, OSError, AttributeError):
        pass
    # Ignore SIGHUP to survive SSH disconnects (not available on Windows)
    if hasattr(signal, "SIGHUP"):
        try:
            signal.signal(signal.SIGHUP, signal.SIG_IGN)
        except (ValueError, OSError):
            pass

    script_dir = get_script_dir()
    bot_path = os.path.join(script_dir, BOT_FILE)

    if not os.path.exists(bot_path):
        print(f"{RED}❌ {BOT_FILE} not found in {script_dir}{RESET}")
        return 1

    if not ensure_config_file():
        return 1

    if not run_prerequisites():
        return 1

    restart_delay = RESTART_DELAY
    total_restarts = 0

    try:
        while True:
            if _shutdown_requested:
                break

            print(f"[{timestamp()}] 🧹 Cleaning previous bot state...")
            terminate_bot(get_managed_bot_pid())

            print(f"[{timestamp()}] 🚀 Starting bot...")
            bot_proc = launch_bot()
            output = OutputReader(bot_proc)

            bot_pid = bot_proc.pid
            write_pid(bot_pid)
            total_restarts += 1

            print(f"[{timestamp()}] ✅ Bot running (PID {bot_pid}) | Restart #{total_restarts}")
            print(f"[{timestamp()}] 👀 Monitoring...\n")

            restart_wait_logged = False
            crash_count = 0
            launch_time = time.time()
            startup_healthy = False
            restart_command_exit = False

            last_output_time = time.time()
            last_output_lines = deque(maxlen=200)
            last_mem_check = time.time()

            while True:
                if _shutdown_requested:
                    break

                time.sleep(CHECK_INTERVAL)

                # Read and print bot output in real-time
                try:
                    for line in output.read_lines():
                        line = line.rstrip()
                        if line:
                            print(f"[{timestamp()}] │ {line}")
                            last_output_lines.append(line)
                            last_output_time = time.time()
                except Exception:
                    pass

                # Detect successful startup: first heartbeat observed
                if not startup_healthy:
                    hb_age = get_heartbeat_age()
                    if hb_age is not None and hb_age < HEARTBEAT_TIMEOUT:
                        startup_healthy = True
                        crash_count = 0
                        restart_delay = RESTART_DELAY
                        uptime = int(time.time() - launch_time)
                        print(f"[{timestamp()}] 💚 Bot healthy (startup took {uptime}s)")

                # Log bot memory every 60s
                if time.time() - last_mem_check > 60:
                    bot_mem = get_bot_memory_mb(bot_pid)
                    if bot_mem > 0:
                        uptime = int(time.time() - launch_time)
                        print(f"[{timestamp()}] 💾 Bot RSS: {bot_mem:.0f}MB | Uptime: {uptime}s")
                    last_mem_check = time.time()

                # Check if process died
                if bot_proc.poll() is not None:
                    # Reap the child to prevent zombie
                    try:
                        bot_proc.wait()
                    except Exception:
                        pass

                    # Windows has no real exec(): the bot's restart command
                    # (os.execv) spawns a new process and the original exits.
                    # Treat that as the intentional restart it is: clear the
                    # stray child and relaunch right away under our control.
                    if IS_WINDOWS and is_intentional_restart_pending():
                        print()
                        print(f"{CYAN}[{timestamp()}] 🔄 Bot restart command detected...{RESET}")
                        restart_command_exit = True
                        restart_delay = 0
                        break

                    print()
                    print(f"{YELLOW}[{timestamp()}] ⚠️ Bot process stopped!{RESET}")
                    crash_count += 1

                    if last_output_lines:
                        print(f"\n{RED}━━━ Bot Output (last errors) ━━━{RESET}")
                        for line in list(last_output_lines)[-15:]:
                            print(f"  {line}")
                        print(f"{RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RESET}\n")

                    # Exponential backoff
                    restart_delay = min(MAX_RESTART_DELAY, RESTART_DELAY * (2 ** min(crash_count - 1, 5)))
                    print(f"{YELLOW}   Crash #{crash_count} | Waiting {restart_delay}s before retry...{RESET}")

                    break

                if is_intentional_restart_pending():
                    if not restart_wait_logged:
                        print()
                        print(f"{CYAN}[{timestamp()}] 🔄 Bot restart command detected...{RESET}")
                        restart_wait_logged = True
                    continue

                if restart_wait_logged:
                    print(f"[{timestamp()}] ✅ Restart completed; resuming monitoring")
                    restart_wait_logged = False
                    crash_count = 0
                    restart_delay = RESTART_DELAY
                    launch_time = time.time()
                    startup_healthy = False

                if not is_bot_healthy(launch_time=launch_time):
                    hb_age = get_heartbeat_age()
                    age_str = f" (last heartbeat {int(hb_age)}s ago)" if hb_age else ""
                    print()
                    print(f"{YELLOW}[{timestamp()}] ⚠️ Bot frozen{age_str}! Restarting...{RESET}")
                    terminate_bot(bot_pid)
                    crash_count += 1
                    restart_delay = min(MAX_RESTART_DELAY, RESTART_DELAY * (2 ** min(crash_count - 1, 5)))
                    break

            # Keep .restart_pending so the relaunched bot can post its
            # "restarted" confirmation (it deletes the file itself).
            cleanup_state(keep_restart_pending=restart_command_exit)

            if _shutdown_requested:
                break

            if restart_command_exit:
                continue

            print()
            print(f"{YELLOW}[{timestamp()}] 🔄 Restarting in {restart_delay}s...{RESET}")
            time.sleep(restart_delay)
            print()

    except KeyboardInterrupt:
        pass
    finally:
        print()
        print(f"{RED}[{timestamp()}] 🛑 Launcher stopped{RESET}")
        terminate_bot(get_managed_bot_pid())
        cleanup_state()
    return 0


if __name__ == "__main__":
    sys.exit(main())
