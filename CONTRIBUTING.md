# Contributing

Thanks for helping out! Bug reports, fixes and small focused features are all welcome.

## Dev setup

```bash
git clone https://github.com/H190K/discordMbot.git
cd discordMbot

python3 launcher.py   # 1st run: creates config.txt from config.example.txt, then stops
# edit config.txt (token + owner), then:
python3 launcher.py   # creates .venv, installs packages, fetches Deno/FFmpeg into bin/, runs the bot
```

Or set it up by hand:

```bash
cp config.example.txt config.txt   # then edit it
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python update_deps.py    # yt-dlp[default], Deno and FFmpeg into bin/
.venv/bin/python music_bot.py
```

On Windows, use `.venv\Scripts\python` instead of `.venv/bin/python`.

**Use a separate test bot.** Create one in the [Discord Developer Portal](https://discord.com/developers/applications), invite it to a private test server, and put its token in your local `config.txt`. Don't develop against a bot that real people are using. If another bot shares the server, change `prefix`.

## Project layout

There is **one codebase for all operating systems**, so there are no platform copies to keep in sync.

| File | What it is |
|------|------------|
| `music_bot.py` | The bot. Almost all changes go here. |
| `launcher.py` | Cross-platform launcher (setup, auto-restart). Must keep working on Windows, macOS and Linux. |
| `update_deps.py` | Installs/updates yt-dlp, Deno and FFmpeg into `bin/` |
| `config.example.txt` | Settings template. Add every new config key here, with a short comment. |
| `start.bat`, `start.command`, `start.sh` | One-click starters for each OS |

If you add a config key, add it to `config.example.txt` **and** to the config table in `README.md`.

If you touch `launcher.py`, `update_deps.py` or a start script, keep all three OSes in mind (paths, `.exe` suffixes, `.venv\Scripts` vs `.venv/bin`). Say in your PR which OSes you tested on.

## Testing before a PR

There's no automated test suite, so please test by hand on your test server. Before opening a PR, check at least:

- [ ] `python -m py_compile music_bot.py launcher.py update_deps.py` passes
- [ ] **YouTube**: a text search, a video link and a playlist
- [ ] **YouTube Mix** (`list=RD...`) loads
- [ ] **SoundCloud**: a track (you should actually hear it) and a set
- [ ] **Spotify**: a track, an album and a playlist (first song starts fast, the rest get added, and the summary appears)
- [ ] `skip`, `stop`, `queue`, `clear`, `volume`, `loop` / `stoploop`
- [ ] **Player panel**: every button (Pause, Skip, Stop, Queue, Volume, Clear, Loop, Reset Player) still works, and the panel updates when songs change
- [ ] Slash commands still work if you touched command code

**Never break the player panel flow.** It's what most users interact with. If your change touches playback, the queue or messages, test the buttons too.

Mention in the PR what you tested and on which OS.

## Code style

- **Match the surrounding code.** Same naming, logging style (`logger.info` with the existing emoji prefixes), and structure.
- Keep changes focused. Don't reformat or reorganize unrelated code in the same PR.
- Don't add new dependencies unless you really need them. If you do, add them to `requirements.txt`.
- Long blocking work (yt-dlp, network, file I/O) must not block the event loop. Use `run_in_executor` or async libraries like the existing code does.

## Pull request process

1. Fork the repo and create a branch from `main` (e.g. `fix/soundcloud-sets`).
2. Make your change.
3. Test it (see the checklist above).
4. Open a PR with:
   - what the change does and why
   - how you tested it, and on which OS
   - any new config keys or behavior changes
5. Keep each PR to one topic. Smaller PRs get reviewed faster.

## No secrets in commits

- `config.txt` is git-ignored. Keep it that way, and **never commit a real bot token** anywhere.
- `config.example.txt` must keep `token=YOUR_BOT_TOKEN_HERE` and an empty `owner=`.
- Never commit cookie files (`cookies.txt`, `cookies.json`), `.venv/` or `bin/`.
- Run `git diff --cached` before every commit and look for tokens, user IDs and personal paths.

If you accidentally pushed a token, reset it right away in the Developer Portal. See [SECURITY.md](SECURITY.md).

## Reporting bugs

Open an issue with:

- your OS and Python version, and the output of `update_deps.py` (versions)
- the link or search that failed (if it's public)
- the relevant part of the bot's console log, with **tokens and personal info removed**

For security issues, follow [SECURITY.md](SECURITY.md) instead of opening a public issue.

By contributing, you agree that your contributions are licensed under the [MIT License](LICENSE).
