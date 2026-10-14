# Security Policy

## Reporting a vulnerability

Please **don't open a public issue** for security problems.

Report them privately through GitHub instead:

1. Go to the repository's **Security** tab.
2. Click **Report a vulnerability**. This opens a private Security Advisory: <https://github.com/H190K/discordMbot/security/advisories/new>

Please include:

- what the problem is and where it is (file and function, if you know)
- steps to reproduce it
- what an attacker could do with it

You'll get a reply as soon as possible. Please give the maintainer reasonable time to fix the issue before you disclose it publicly.

## Supported versions

Only the latest code on the `main` branch is supported. Please update to the latest `main` before reporting, in case the problem is already fixed.

| Version | Supported |
|---------|-----------|
| latest `main` | Yes |
| older commits / forks | No |

## Keeping your bot safe

The bot runs on **your** machine with **your** credentials. Most real-world problems come from leaked secrets, not code bugs.

### Never commit your token

- Your token lives in `config.txt`, which is created from `config.example.txt` on first run and is **git-ignored**. Don't remove it from `.gitignore`, and never put a real token in `config.example.txt` or any other tracked file.
- Check `git diff` before every commit. If you see a real token, stop.
- Don't paste your token or a full `config.txt` into Discord, issues, pastebins or screenshots.

### If your token leaks, reset it right away

1. Open the [Discord Developer Portal](https://discord.com/developers/applications) and select your application.
2. Go to **Bot** and click **Reset Token**. The old token stops working immediately.
3. Put the new token in your local `config.txt` and restart the bot.
4. If the token was ever pushed to git, treat it as public **forever**, even after you delete the commit. Resetting the token is the only real fix.

Discord also scans public GitHub repos and may reset leaked tokens for you, but don't count on it.

### Cookie files are credentials

A YouTube `cookies.txt` (see [COOKIE_README.md](COOKIE_README.md)) gives anyone who has it access to that Google account.

- Never commit or share it. Keep it readable only by you (`chmod 600 cookies.txt`).
- Consider using a separate Google account just for the bot.
- If a cookie file leaks, sign out of all sessions for that Google account. That invalidates the cookies.

### Owner-only commands

`updateytdlp`/`update`, `clearcache` and `restart` only work for the Discord user ID set as `owner=` in `config.txt`. The update command installs packages and downloads binaries on your host.

- Set `owner=` to **your own** user ID only.
- If `owner=` is empty, these commands are refused for everyone.

### General tips

- Run the bot as a normal user, not root or Administrator.
- Give the bot only the Discord permissions it needs: View Channels, Send Messages, Embed Links, Read Message History, Connect, Speak.
- Keep yt-dlp, Deno and FFmpeg up to date with `!!update` or `update_deps.py`.
