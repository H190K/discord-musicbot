# YouTube Cookies

Most of the time the bot works fine **without** cookies. You only need them when YouTube starts refusing your server, usually with:

- `Sign in to confirm you're not a bot`
- `Requested format is not available`
- age-restricted videos that won't play

Before you set up cookies, try updating first: `!!update` (owner only), then `!!restart`.

> **Warning: cookie files are account credentials.** A `cookies.txt` lets anyone who has it act as your logged-in Google account. Never commit it to git, never paste it in Discord or an issue, and keep it readable only by you. Consider using a separate, throwaway Google account for the bot.

## Option 1: Read cookies straight from a browser

Use this when the bot runs on the same computer as a browser where you're logged into YouTube. In `config.txt`:

```ini
use_browser_cookies=true
```

At startup the bot tries Firefox, Chrome, Chromium, Edge, Brave, Opera, Vivaldi, Whale and Safari, in that order. It uses the first one that has YouTube/Google cookies, and the startup log shows which browser it picked. Firefox is the most reliable. Chromium-based browsers can fail if they're open or encrypt their cookies.

This doesn't work on a headless server. Use option 2 there.

## Option 2: Use a `cookies.txt` file

### A. Export from Firefox with the included script (Linux)

`extract_cookies.py` and `get_cookies.sh` are in the project folder. They read YouTube/Google cookies from your Firefox profile (LibreWolf and Waterfox are also detected) and write a Netscape-format `cookies.txt` that yt-dlp understands.

1. Log into YouTube in Firefox.
2. **Close Firefox completely**, because its cookie database is locked while it runs.
3. Run the script from the project folder:

   ```bash
   chmod +x get_cookies.sh
   ./get_cookies.sh
   ```

   This writes `cookies.txt` to the folder you ran it from. Keep it next to `config.txt` and lock it down:

   ```bash
   chmod 600 cookies.txt
   ```

4. In `config.txt`, set:

   ```ini
   cookie_file=cookies.txt
   ```

   > The scripts print `cookie = cookies.txt` at the end. That key name is outdated. The bot reads **`cookie_file=`**.

5. Restart the bot. The startup log should mention the cookie file. If the path is wrong, the bot logs `Cookie file not found` and continues without it.

Other ways to run the script:

```bash
python3 extract_cookies.py --list-profiles                     # show Firefox profiles
python3 extract_cookies.py --output cookies.txt                # export (default)
python3 extract_cookies.py --profile /path/to/firefox/profile  # pick a profile
```

### B. Export with a browser extension (any OS)

On Windows or macOS, or with any browser, install a "Get cookies.txt" style extension and export the cookies for `youtube.com` in **Netscape** format. Save the file as `cookies.txt` in the project folder (next to `config.txt`) and set `cookie_file=cookies.txt`.

### Where the file goes

`cookie_file` can be:

- a relative path, resolved from the project folder (where `music_bot.py` and `config.txt` are), e.g. `cookie_file=cookies.txt`
- an absolute path, e.g. `cookie_file=/path/to/cookies.txt`

Leave it empty to turn cookies off.

## Test your cookies

```bash
yt-dlp --cookies cookies.txt --no-download "https://www.youtube.com/watch?v=VIDEO_ID"
```

If it prints video info without a "sign in" error, the cookies work.

## Expiry

Cookies expire. Logging out, changing your password, or YouTube rotating sessions can also invalidate them. Export them again when the "not a bot" errors come back. Delete the old file before you export a new one.

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `Firefox profile not found` | Run `python3 extract_cookies.py --list-profiles`, or find one with `find ~/.mozilla/firefox -name cookies.sqlite`, then pass `--profile <path>`. |
| `database is locked` | Firefox is still running. Close it (`pkill firefox`) and try again. |
| `No cookies found` | Make sure you're logged into YouTube in that Firefox profile. |
| Bot logs `Cookie file not found` | The path in `cookie_file=` is wrong. Relative paths start at the project folder. |
| Still blocked with cookies | Run `!!update`, export fresh cookies, or try another account. Some server IPs are heavily rate-limited by YouTube. |

## Keep cookies out of git

The repository's `.gitignore` doesn't list cookie files by default. Before committing, check `git status` and make sure no `cookies.txt` or `cookies.json` shows up. For extra safety, add them to `.gitignore` yourself:

```gitignore
cookies*.txt
cookies*.json
```

If you ever push a cookie file, log out of all sessions for that Google account (this invalidates the cookies), then remove the file from the repo.
