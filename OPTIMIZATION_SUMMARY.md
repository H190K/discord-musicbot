# Performance Notes

This document explains how the bot gets a song playing quickly and what changed compared to older versions. All of the code below lives in `music_bot.py`.

## Measured results

| Action | Before | Now |
|--------|--------|-----|
| `play <text search>` | ~10.5 s | **~2.0 s** |
| `play <YouTube link>` | ~10.7 s | **~3.0 s** |
| `play <SoundCloud link>` | silent (no audio) | **~3.2 s** |
| `play <Spotify album>` | ~7.5 s | **~2.6 s** |
| Next song after `skip` | several seconds | **< 1 s** |
| YouTube extraction alone | ~6.4 s (old 6-client list) | **~1.3 s** (yt-dlp default clients + Deno) |

Times are from `play` until audio starts. They depend on your network and server.

## How it works

### 1. Extract each song once

Older versions extracted a song several times: once to search, once to read metadata and once more to play. Now whatever looks a song up first (search, link lookup or prefetch) keeps the stream info in memory and hands it to playback. Concurrent requests for the same song share one in-flight extraction.

### 2. Prepare the next song while the current one plays

Shortly after a song starts, the bot resolves the **next** song's stream in the background. Pressing Skip, or reaching the end of a song, then starts the next one in under a second. If the current song is long, the prepared link is checked again near the end, in case it would expire before it's needed.

### 3. Fast YouTube search

Text searches go straight to YouTube's own search endpoint, which is much quicker than a full yt-dlp search. If that fails, the bot falls back to yt-dlp's `ytsearch`.

### 4. In-memory only, with expiry checks

There is no disk cache. Everything is kept in memory and cleared on restart or with `!!clearcache`.

- YouTube and SoundCloud stream links are signed and **expire or rotate**. Before a stored link is reused, the bot reads its expiry time and re-extracts the song if fewer than 2 minutes are left. Links without an expiry are trusted for 5 minutes.
- If a link still fails before any audio plays (for example a 403 because it rotated), the bot drops it and **re-fetches the same song once automatically**.
- Metadata and playlist lookups have their own short TTLs (`metadata_cache_ttl`, `playlist_cache_ttl`) and a size cap (`metadata_cache_limit`).

### 5. Fast yt-dlp settings for YouTube

- `youtube_player_clients=` is **empty** by default, so yt-dlp picks its own small, fast set of clients. That set needs a JavaScript runtime to solve YouTube's challenges, so `update_deps.py` installs **Deno** into `bin/` and `yt-dlp[default]` (which includes `yt-dlp-ejs`, the challenge solver scripts).
- The old wide list (`web,web_embedded,mweb,android,ios,default`) still works but is about 5x slower (~6.4 s vs ~1.3 s). The bot only falls back to it automatically when no Deno or Node is found.
- HLS/DASH manifests are skipped for normal videos, which saves about 0.5 s per song, because audio comes from the regular formats. Live streams still get their manifests (see below).

### 6. Playlists and Spotify start right away

- **YouTube/SoundCloud playlists and Mixes**: the first track plays immediately and the rest load in the background.
- **Spotify**: track names come from Spotify's public embed page (no login or API key). The first track that matches on YouTube starts right away. The rest are matched **4 at a time** in the background and inserted in playlist order. Tracks with no match are skipped and counted in a summary message. Spotify's embed lists at most 100 tracks per playlist, while albums are complete.

## Fixes in this version

- **SoundCloud** HLS streams used to connect but play silence. They now play correctly.
- **YouTube live streams** play. When the fast path returns no usable audio, the bot retries with manifests enabled.

## Bundled toolchain

`update_deps.py` keeps the playback tools current without needing `sudo`:

| Tool | Where | Notes |
|------|-------|-------|
| `yt-dlp[default]` | the bot's Python env (pip) | Includes `yt-dlp-ejs` (YouTube challenge solver scripts) |
| Deno | `bin/deno` | JS runtime yt-dlp uses for YouTube |
| FFmpeg / FFprobe | `bin/ffmpeg`, `bin/ffprobe` | Static build on Linux and Windows. macOS uses Homebrew/system FFmpeg. |

The launcher runs it on first start. Afterwards, the owner can run `!!update` (aliases `updateytdlp`, `u`, `upd`) to update all three. New Deno and FFmpeg builds are used from the next song on. A new yt-dlp needs `!!restart`.

## Tips

- Keep `youtube_player_clients=` empty.
- Make sure `bin/deno` exists (or `deno`/`node` is on your PATH).
- Run `!!update` now and then. YouTube changes often.
- On a small VPS, `ffmpeg_threads=2` and `buffer_size=256` are good defaults.
