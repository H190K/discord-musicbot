# Discord Music Bot

A self-hosted Discord music bot written in Python ([discord.py](https://github.com/Rapptz/discord.py) + [yt-dlp](https://github.com/yt-dlp/yt-dlp)). Paste a link or type a song name and it plays in your voice channel, with a button panel, a queue, loop, volume and slash commands.

![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)

## Features

- **YouTube**: videos, search by name, playlists, Mixes (`list=RD...`), live streams
- **SoundCloud**: tracks, sets/playlists, `on.soundcloud.com` short links
- **Spotify links, played from YouTube**: tracks, albums and playlists (`open.spotify.com`, `spotify:` URIs, `spotify.link` short links). See [How Spotify links work](#how-spotify-links-work).
- **Fast start**: a song usually starts 2–3 seconds after `play`, and the next song is prepared while the current one plays. See [OPTIMIZATION_SUMMARY.md](OPTIMIZATION_SUMMARY.md).
- **Queue**: big playlists start playing right away while the rest loads in the background
- **Loop**: loop forever or a set number of times
- **Volume**: 0–200%
- **Player panel**: a "Now Playing" message with buttons for Pause, Skip, Stop, Queue, Volume, Clear, Loop and Reset Player
- **Slash commands** plus classic prefix commands (default prefix `!!`)
- **Self-updating toolchain**: one owner command updates yt-dlp, Deno and FFmpeg
- **One launcher for Windows, macOS and Linux**: sets everything up on first run and restarts the bot if it crashes

## How it works

1. You type `!!play <song or link>` (or `/play`).
2. The bot finds the song. A text search uses a fast YouTube search. A YouTube or SoundCloud link goes to [yt-dlp](https://github.com/yt-dlp/yt-dlp), which reads the stream address.
3. [FFmpeg](https://ffmpeg.org) streams the audio into your Discord voice channel. While it plays, the bot already prepares the next song.
4. **Spotify links**: the bot reads the track names from Spotify's public page, finds each one on YouTube and plays that. No Spotify account or audio is used. See [How Spotify links work](#how-spotify-links-work).

## What you need

| What | Install it yourself? | Where to get it |
|------|----------------------|-----------------|
| **Python 3.10+** | Yes | <https://www.python.org/downloads/> (details per OS below) |
| **A Discord bot token** | Yes (free) | <https://discord.com/developers/applications>, see [Create the Discord bot](#create-the-discord-bot) |
| **Homebrew + FFmpeg** | macOS only | <https://brew.sh>, then `brew install ffmpeg` |
| **Git** | Optional | <https://git-scm.com/downloads>, or use **Code → Download ZIP** on GitHub |
| [Deno](https://deno.com) | No, automatic | Downloaded into `bin/`. yt-dlp needs it to solve YouTube's JavaScript challenges. |
| [FFmpeg](https://ffmpeg.org) (Linux/Windows) | No, automatic | Static build from [BtbN/FFmpeg-Builds](https://github.com/BtbN/FFmpeg-Builds), downloaded into `bin/` |
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) and other Python packages | No, automatic | Installed into a private `.venv/` from `requirements.txt` |

One codebase runs on every OS. The **launcher** (`launcher.py`, started by the `start` script for your OS) does the setup:

1. **First run:** it copies `config.example.txt` to `config.txt` and asks you to add your bot token. Then it stops.
2. **Next runs:**
   - It creates `.venv/` and installs the Python packages from `requirements.txt`.
   - It runs `update_deps.py`, which downloads Deno (and FFmpeg on Linux/Windows) into `bin/`.
   - It starts the bot and **restarts it automatically** if it crashes or hangs.

`config.txt` is git-ignored, so your token can't be committed by accident.

To keep the tools current later, the bot owner runs `!!update` in Discord (the command is `updateytdlp`, with aliases `update`, `u` and `upd`). See [Updating](#updating).

## Install

| OS      | Start the bot with |
|---------|--------------------|
| Windows | double-click `start.bat` |
| macOS   | double-click `start.command` |
| Linux   | `./start.sh` |

### Windows

1. **Install Python 3.10+** from <https://www.python.org/downloads/>. In the installer, tick **"Add python.exe to PATH"**. Or, in a terminal, run:
   ```bat
   winget install Python.Python.3.12
   ```
2. **Get the bot.** Either click **Code → Download ZIP** on GitHub and unzip it, or run:
   ```bat
   git clone https://github.com/H190K/discordMbot.git
   ```
3. **Create your Discord bot** and copy its token. See [Create the Discord bot](#create-the-discord-bot).
4. **Double-click `start.bat`.** On this first run it creates `config.txt` and asks for your token.
5. **Open `config.txt`** in Notepad and fill in:
   - `token=YOUR_BOT_TOKEN_HERE`: replace the placeholder with your token
   - `owner=YOUR_DISCORD_USER_ID`: your user ID ([how to find it](#find-your-discord-user-id))
6. **Double-click `start.bat` again.** The first real start takes a minute or two while it installs packages and downloads Deno and FFmpeg. After that the bot comes online.

### macOS

1. **Install Homebrew** from <https://brew.sh>. Paste the command from that page into Terminal.
2. **Install Python and FFmpeg.** macOS has no bundled FFmpeg build, so Homebrew provides it:
   ```bash
   brew install python ffmpeg
   ```
3. **Get the bot.** Either click **Code → Download ZIP** on GitHub and unzip it, or run:
   ```bash
   git clone https://github.com/H190K/discordMbot.git
   ```
4. **Create your Discord bot** and copy its token. See [Create the Discord bot](#create-the-discord-bot).
5. **Double-click `start.command`.** If macOS blocks it the first time, right-click it, choose **Open**, then confirm. This first run creates `config.txt`.
6. **Edit `config.txt`** (e.g. `open -e config.txt`):
   - `token=YOUR_BOT_TOKEN_HERE`: replace the placeholder with your token
   - `owner=YOUR_DISCORD_USER_ID`: your user ID ([how to find it](#find-your-discord-user-id))
7. **Double-click `start.command` again** to start the bot.

### Linux

1. **Install Python** (Debian/Ubuntu shown; use your distro's package manager otherwise):
   ```bash
   sudo apt install python3 python3-venv git
   ```
2. **Get the bot:**
   ```bash
   git clone https://github.com/H190K/discordMbot.git
   cd discordMbot
   ```
3. **Create your Discord bot** and copy its token. See [Create the Discord bot](#create-the-discord-bot).
4. **Run it once** to create `config.txt`:
   ```bash
   ./start.sh          # or: python3 launcher.py
   ```
5. **Edit `config.txt`** (e.g. `nano config.txt`):
   - `token=YOUR_BOT_TOKEN_HERE`: replace the placeholder with your token
   - `owner=YOUR_DISCORD_USER_ID`: your user ID ([how to find it](#find-your-discord-user-id))
6. **Start it again:** `./start.sh`

**Running on a server:** `setup.sh` is an optional helper that installs the bot as a **systemd service**, so it starts on boot and restarts on its own. Read the script before you run it. For a quick test, `tmux` or `screen` also work.

## Create the Discord bot

1. Open the **[Discord Developer Portal](https://discord.com/developers/applications)** and click **New Application**. Give it a name.
2. Open the **Bot** tab:
   - Click **Reset Token**, then copy the token into `config.txt` as `token=...`. **Never share or commit this token.** Anyone who has it controls your bot.
   - Under **Privileged Gateway Intents**, turn on **MESSAGE CONTENT INTENT**, then save. Without it, prefix commands like `!!play` are ignored.
3. Open **OAuth2 → URL Generator**:
   - **Scopes:** `bot` and `applications.commands`
   - **Bot permissions:** View Channels, Send Messages, Embed Links, Read Message History, Connect, Speak
4. Copy the generated URL, open it in your browser and add the bot to your server.

### Find your Discord user ID

The `owner=` setting unlocks the admin commands (`update`, `clearcache`, `restart`) for you. To find your ID:

1. In Discord, open **User Settings → Advanced** and turn on **Developer Mode**.
2. Right-click your name (in a member list or on a message) and pick **Copy User ID**.
3. Paste it into `config.txt` as `owner=...`.

Discord's guide: <https://support.discord.com/hc/en-us/articles/206346498>

## Configuration

Settings live in `config.txt` in the project folder (created from `config.example.txt` on first run), one `key=value` per line. Lines starting with `#` are comments. Keys you leave out use the default.

| Key | Default | Description |
|-----|---------|-------------|
| `token` | `YOUR_BOT_TOKEN_HERE` | **Required.** Your Discord bot token. |
| `prefix` | `!!` | Command prefix. Separate several with commas, e.g. `!!,!` |
| `owner` | *(empty)* | Your Discord user ID, e.g. `owner=YOUR_DISCORD_USER_ID`. Needed for the owner-only commands. |
| `game` | `Music Bot` | Activity text shown on the bot's profile. |
| `status` | `online` | `online`, `idle`, `dnd` or `invisible` |
| `use_slash_commands` | `true` | Register `/play`, `/skip`, and the other slash commands. |
| `use_loop_feature` | `true` | Enable `loop` / `stoploop` and the Loop button. |
| `ffmpeg_threads` | `2` | FFmpeg threads (1–4). |
| `buffer_size` | `256` | Audio buffer in KB (128–512). |
| `sample_rate` | `48000` | `44100` or `48000` |
| `playlist_limit` | `250` | Max tracks loaded from a playlist (also caps Spotify playlists). |
| `mix_limit` | `250` | Max tracks loaded from a YouTube Mix. |
| `heartbeat_timeout` | `60.0` | Discord heartbeat timeout in seconds. The launcher also uses it to detect a hung bot. |
| `proxy` | *(empty)* | HTTP/HTTPS proxy, e.g. `http://proxy.example.com:8080` |
| `cookie_file` | *(empty)* | Path to a `cookies.txt` for YouTube. A relative path is resolved from the project folder. See [COOKIE_README.md](COOKIE_README.md). |
| `use_browser_cookies` | `false` | `true` reads YouTube cookies straight from a local browser (Firefox, Chrome, Edge, Brave, ...). Only works when the bot runs on the same machine as the browser. |
| `youtube_player_clients` | *(empty)* | **Leave empty** for yt-dlp's fast default. It needs Deno or Node; without one the bot falls back to the old list. The old list `web,web_embedded,mweb,android,ios,default` is much slower. |
| `youtube_format_flags` | *(empty)* | Advanced: yt-dlp YouTube `formats` extractor-arg. Only applied when `youtube_player_clients` is set. |
| `idle_clear_hours` | *(empty = off)* | Leave voice channels after this many hours of inactivity. Empty or `0` turns it off. |
| `metadata_cache_limit` | `150` | Max in-memory metadata cache entries. |
| `metadata_cache_trim` | `25` | Entries dropped when the cache is full. |
| `metadata_cache_ttl` | `180` | Seconds a cached song lookup is kept. |
| `playlist_cache_ttl` | `900` | Seconds a cached playlist/Spotify lookup is kept. |
| `cmd_play`, `cmd_pause`, `cmd_resume`, `cmd_skip`, `cmd_stop`, `cmd_queue`, `cmd_clear`, `cmd_join`, `cmd_leave`, `cmd_volume` | *(empty)* | Extra comma-separated aliases, added on top of the built-in ones. |
| `cmd_loop` | `lo,lp` | Aliases for `loop`. |
| `cmd_stoploop` | `stlo,sloop,stopl,sl` | Aliases for `stoploop`. |
| `cmd_update` | `update,u,upd` | Aliases for `updateytdlp`. |
| `cmd_clearcache` | `cc,clearc,ccache,purge` | Aliases for `clearcache`. |
| `cmd_restart` | `rbot,reboot` | Aliases for `restart`. |
| `cmd_embedreset` | `epr` | Aliases for `resetplayer`. |

> If you set a `cmd_loop`, `cmd_stoploop`, `cmd_update`, `cmd_clearcache`, `cmd_restart` or `cmd_embedreset` line to an empty value, that command's default aliases are **not** used. Delete the line instead to keep them.

## Commands

The examples use the default prefix `!!`.

| Command | Aliases | What it does |
|---------|---------|--------------|
| `!!play <name or link>` | `p` | Play or queue a song, playlist, Mix, SoundCloud or Spotify link |
| `!!pause` | | Pause |
| `!!resume` | `r` | Resume |
| `!!skip [n]` | `next`, `s` | Skip the current song (or `n` songs) |
| `!!stop` | `st` | Stop and clear the queue |
| `!!queue` | `q`, `list` | Show the queue |
| `!!clear` | `clr` | Clear the queue (keeps the current song, stops loop) |
| `!!volume [0-200]` | `vol`, `v` | Show or set the volume |
| `!!loop [n]` | `lo`, `lp` | Loop the current song forever, or `n` times. Run it again to turn loop off. |
| `!!stoploop` | `stlo`, `sloop`, `stopl`, `sl` | Stop looping and continue the queue |
| `!!join` | `j`, `connect` | Join your voice channel |
| `!!leave` | `disconnect`, `dc` | Leave the voice channel |
| `!!resetplayer` | `epr` | Re-post the player panel if it got lost |
| `!!help` | `h`, `commands` | Show help |

**Owner-only** (needs `owner=` in `config.txt`):

| Command | Aliases | What it does |
|---------|---------|--------------|
| `!!updateytdlp` | `update`, `u`, `upd` | Update yt-dlp (with its YouTube solver scripts), Deno and FFmpeg |
| `!!clearcache` | `cc`, `clearc`, `ccache`, `purge` | Clear the in-memory caches |
| `!!restart` | `rbot`, `reboot` | Restart the bot process |

**Slash commands:** `/play`, `/pause`, `/resume`, `/skip`, `/stop`, `/queue`, `/clear`, `/volume`, `/join`, `/leave`, `/loop`, `/stoploop`

## How Spotify links work

Spotify doesn't allow streaming its audio to Discord, so the bot does the following:

1. It reads the public track names from Spotify's embed page. No Spotify login, API key or Spotify audio is involved.
2. It finds each track on YouTube and plays that.
3. For albums and playlists, the first track starts right away. The rest are matched in the background, 4 at a time, and added in order. Tracks it can't find are skipped and listed in a summary.

Limits:

- The link must be **public**. Private playlists can't be read.
- Spotify's public embed shows at most **100 tracks** of a playlist. Albums load completely.
- `playlist_limit` also applies.

## Updating

**Bot code:** run `git pull`, or download the ZIP again and copy your `config.txt` over. Then restart the bot. If `config.example.txt` gained new settings, copy the ones you want into your `config.txt`.

**Playback tools** (yt-dlp, Deno, FFmpeg). YouTube changes often, so update these when songs stop working. Use either:

- **In Discord (owner only):** `!!update` (the command is `updateytdlp`, with aliases `update`, `u` and `upd`). It updates all three and prints the old and new versions. If yt-dlp changed, run `!!restart` afterwards.
- **From a terminal** in the project folder:
  - Linux/macOS: `.venv/bin/python update_deps.py`
  - Windows: `.venv\Scripts\python update_deps.py`

## Troubleshooting

| Problem | Fix |
|---------|-----|
| **"Sign in to confirm you're not a bot"** (YouTube) | YouTube is blocking your server's IP. Give the bot cookies from a logged-in browser with `cookie_file=` or `use_browser_cookies=true`. See [COOKIE_README.md](COOKIE_README.md). Updating yt-dlp (`!!update`) also helps. |
| **Bot joins but there's no sound** | FFmpeg is missing or broken. Check that `bin/ffmpeg` exists (Linux/Windows) or that `ffmpeg -version` works (macOS/system). Re-run `update_deps.py`. Also check that `PyNaCl` is installed. |
| **Songs take long to start** | Keep `youtube_player_clients=` **empty** and make sure Deno is installed (`bin/deno`, or `deno` on your PATH). Without a JS runtime the bot falls back to the slow client list. |
| **Bot ignores `!!` commands** | Turn on **Message Content Intent** in the Developer Portal (Bot page). |
| **Slash commands don't show up** | Invite the bot with the `applications.commands` scope. Global commands can take a while to appear the first time. |
| **"Owner not configured"** | Set `owner=` to your Discord user ID and restart. |
| **"Couldn't read that Spotify link"** | Make sure the playlist or album is public. |
| **Launcher says "Bot token not configured"** | Open `config.txt` (created from `config.example.txt` on first run) and set `token=`. |
| **`start.command` / `start.sh` won't run** | Make it executable with `chmod +x start.command` (or `start.sh`). On macOS, right-click it and choose **Open** the first time. |
| **Windows: `python` not found** | Reinstall Python with **"Add python.exe to PATH"** ticked, or use `winget install Python.Python.3.12`. |
| **Player panel is missing or frozen** | Run `!!resetplayer`. |

## Project structure

```
music_bot.py          The bot
launcher.py           Cross-platform launcher: creates .venv, installs packages,
                      runs update_deps.py, starts and watches the bot
update_deps.py        Installs/updates yt-dlp[default], Deno and FFmpeg (into bin/)
requirements.txt      Python packages
config.example.txt    Settings template, copied to config.txt on first run
config.txt            Your settings (created for you, git-ignored)
start.bat             Windows: double-click to start
start.command         macOS: double-click to start
start.sh              Linux: ./start.sh
setup.sh              Optional: install as a systemd service on a Linux server
extract_cookies.py    Optional: export YouTube cookies from Firefox (see COOKIE_README.md)
get_cookies.sh        Wrapper around extract_cookies.py
bin/                  Deno and FFmpeg, downloaded automatically (git-ignored)
.venv/                Python virtual environment, created automatically (git-ignored)
```

## Contributing, security and license

- Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).
- Found a security issue? Please report it privately. See [SECURITY.md](SECURITY.md).
- Licensed under the [MIT License](LICENSE).

This project is not affiliated with Discord, YouTube, SoundCloud or Spotify. Make sure your use follows their terms of service.
