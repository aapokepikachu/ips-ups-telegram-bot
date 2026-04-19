# 🎮 IPS/UPS/BPS GBA ROM Patcher — Telegram Bot

A production-ready async Telegram bot that applies **IPS**, **UPS**, and **BPS** patches to GBA ROM files. Built with Python 3.11+, python-telegram-bot, Motor (async MongoDB), and designed for deployment on **Render** (free tier).

> **Legal note:** This bot is designed exclusively for files the user owns or has permission to use. It does not facilitate bypassing copyright protections.

---

## ✨ Features

| Feature | Description |
|---|---|
| **Auto-detect** | Detects `.ips` / `.ups` / `.bps` format on upload |
| **Pure-Python patching** | No external binaries — IPS, UPS & BPS applied in-memory |
| **BPS support** | Full Beat Patching System with all 4 action types |
| **Inline ROM selection** | Admin-managed ROM list via `/inedit` |
| **Job queue** | Sequential processing with live position updates |
| **Explicit job states** | `received → queued → downloading → patching → uploading → completed` |
| **Caching** | SHA-256 cache key avoids re-patching identical combos |
| **Timeout hardening** | Explicit timeouts on all API calls (120s for files) |
| **Cancel anytime** | Graceful cancel at queue or processing stage |
| **Thumbnail** | Configurable thumbnail sent on both fresh and cached results |
| **Admin dashboard** | Broadcast, user stats, DB stats, thumbnail & caption |
| **Large file support** | Optional local Bot API server for files > 20 MB |
| **Health check** | HTTP endpoint for Render uptime |

---

## 📁 Project Structure

```
├── bot/
│   ├── __init__.py
│   ├── main.py              # Application factory & lifecycle hooks
│   ├── config.py             # Environment variable loader
│   ├── database.py           # Motor MongoDB layer
│   ├── patching/
│   │   ├── ips.py            # IPS patch applier
│   │   ├── ups.py            # UPS patch applier
│   │   ├── bps.py            # BPS patch applier
│   │   └── engine.py         # Detect + async apply wrapper
│   ├── services/
│   │   ├── queue_manager.py  # Async job queue with state tracking
│   │   ├── cache.py          # Hash-based cache with in-progress markers
│   │   └── progress.py       # Unicode progress bar
│   ├── handlers/
│   │   ├── user_commands.py  # /start, /help, /about, /ping, etc.
│   │   ├── admin_commands.py # /broadcast, /inedit, /db, /users, etc.
│   │   ├── patch_flow.py     # Document handler → patch detection
│   │   ├── callbacks.py      # Inline button callback router
│   │   └── errors.py         # Global error handler
│   └── utils/
│       ├── constants.py      # Magic bytes, limits, timeouts
│       └── helpers.py        # Formatting, hashing, sanitization
├── run.py                    # Entry point
├── requirements.txt
├── Procfile
├── render.yaml
├── .env.example
├── test_patching.py          # Functional tests
└── README.md
```

---

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- A [Telegram Bot Token](https://t.me/BotFather)
- A [MongoDB Atlas](https://www.mongodb.com/atlas) free-tier cluster
- A private Telegram channel for ROM storage (bot must be an **admin** of this channel)

### 1. Clone & install

```bash
git clone https://github.com/aapokepikachu/ips-ups-telegram-bot.git
cd ips-ups-telegram-bot
pip install -r requirements.txt
```

### 2. Configure environment

Copy `.env.example` to `.env` and fill in:

```bash
cp .env.example .env
```

| Variable | Required | Description |
|---|---|---|
| `BOT_TOKEN` | ✅ | Telegram bot token from BotFather |
| `MONGO_URI` | ✅ | MongoDB connection string (SRV format) |
| `ADMIN_ID` | ✅ | Your Telegram user ID (integer) |
| `CHANNEL_ID` | ✅ | Private channel ID for ROM files (starts with `-100`) |
| `DB_NAME` | ❌ | Database name (default: `ips_ups_bot`) |
| `CACHE_CHANNEL_ID` | ❌ | Channel for cached outputs (default: same as `CHANNEL_ID`) |
| `MAX_QUEUE_SIZE` | ❌ | Max queued jobs (default: `10`) |
| `MAX_FILE_SIZE` | ❌ | Max file size in bytes (default: `104857600` = 100 MB) |
| `LOG_LEVEL` | ❌ | Logging level (default: `INFO`) |
| `OWNER_NAME` | ❌ | Displayed in `/about` |
| `PORT` | ❌ | HTTP port for health-check (auto-set by Render) |
| `LOCAL_API_URL` | ❌ | Local Bot API server URL (see below) |
| `LOCAL_API_FILE_URL` | ❌ | Local Bot API file URL (default: `LOCAL_API_URL/file`) |

### 3. Run locally

```bash
python run.py
```

---

## 🔄 Patch Workflow

```
User sends .ips/.ups/.bps file
        │
        ▼
Bot detects type → "IPS/UPS/BPS file detected"
        │
        ▼
┌─────────────────────────┐
│ [📂 Select Rom file]     │
│ [▶️ Proceed] [❌ Cancel] │
└─────────────────────────┘
        │
User taps "Select Rom file"
        │
        ▼
┌─────────────────────────┐
│ [🎮 FireRed v1.0]       │
│ [🎮 Emerald]            │
│ [🎮 Ruby]               │
│ [« Back]                │
└─────────────────────────┘
        │
User picks "FireRed v1.0"
        │
        ▼
┌─────────────────────────┐
│ [✅ FireRed v1.0]        │ ← button text updated
│ [▶️ Proceed] [❌ Cancel] │
└─────────────────────────┘
        │
User taps "Proceed patching"
        │
        ▼
[Check cache] → HIT → send cached file (with thumbnail)
        │
       MISS
        │
        ▼
[Download ROM → Apply patch → Upload result]
        │
Progress bar updates live with state:
  📥 Downloading ROM...
  📥 Downloading patch...
  🔧 Applying patch...
  📤 Uploading patched file...
  💾 Caching result...
        │
        ▼
Patched .gba sent to user ✅
```

If the user presses **Proceed** without selecting a ROM, a **popup alert** appears:
> Select a ROM file from the "Select Rom file" button

---

## 🎮 Managing ROMs (`/inedit`)

The inline ROM buttons are **not hardcoded**. Admins manage them dynamically:

1. Send `/inedit` to the bot
2. Tap **➕ Add ROM**
3. Send the display name (e.g., `FireRed v1.0`)
4. Forward or send the `.gba` ROM file from your private channel
5. Done! The ROM now appears in the user's selection list

To **remove** a ROM: `/inedit` → **➖ Remove ROM** → tap the one to delete.

To **list** all ROMs: `/inedit` → **📋 List ROMs**.

---

## 💾 Caching

- When a patch is applied, the bot computes: `cache_key = SHA256(patch_hash + rom_file_id)`
- The patched output is uploaded to the cache channel and the `file_id` is stored in MongoDB
- Next time the **same patch + same ROM** combo is requested, the bot serves the cached file instantly (with thumbnail)
- No re-downloading or re-patching needed
- **In-progress markers** prevent concurrent duplicate patching of the same combo
- If a job fails, the in-progress marker is cleaned up automatically

---

## ⏱ Timeout & Error Handling

| Operation | Timeout | On Failure |
|---|---|---|
| File download (ROM/patch) | 120 seconds | Clear error: "ROM download timed out" |
| File upload (result) | 120 seconds | Clear error: "File upload timed out" |
| Message edits (progress) | 60 seconds | Silently swallowed — job continues |
| Patch application | No limit (thread) | Wrapped PatchError with details |
| API calls (general) | 30 seconds | Default python-telegram-bot handling |

All Telegram API calls during patching have explicit timeouts. The event loop is never blocked — patching runs in a thread executor.

---

## 📋 User Commands

| Command | Description |
|---|---|
| `/start` | Welcome message and quick instructions |
| `/help` | Full command and workflow reference |
| `/patch` | Instructions (or reply to a patch file to start) |
| `/status` | Check your current job status |
| `/queue` | View queue length and your position |
| `/cancel` | Cancel your active or queued job |
| `/formats` | Explain IPS, UPS, and BPS formats |
| `/about` | Bot info, host, database, source code |
| `/ping` | Bot latency |

## 🔐 Admin Commands

| Command | Description |
|---|---|
| `/broadcast` | Reply to a message → send to all users |
| `/inedit` | Add / remove / list ROM buttons |
| `/db` | MongoDB usage and collection stats |
| `/users` | Total, active, blocked, recent user counts |
| `/current` | Active job details and queue listing |
| `/thumbnail` | Reply to an image → set as file thumbnail |
| `/caption <template>` | Set caption with placeholders |
| `/helpa` | Detailed admin command reference |

### Caption Placeholders

```
{filename}  — output file name
{filesize}  — formatted file size
{user}      — user's display name
{romname}   — selected ROM name
{patchtype} — IPS, UPS, or BPS
{time}      — UTC timestamp
```

---

## 🗄 Database (MongoDB)

### Collections

| Collection | Purpose |
|---|---|
| `users` | All bot users with activity and block status |
| `settings` | Key-value store (caption, thumbnail, etc.) |
| `rom_mappings` | ROM name → file_id mappings |
| `patch_jobs` | Job history with explicit states |
| `cache` | SHA-256 key → cached output (with status field) |

### Setup

1. Create a **free** MongoDB Atlas cluster at [mongodb.com/atlas](https://www.mongodb.com/atlas)
2. Create a database user
3. Whitelist IP `0.0.0.0/0` (required for Render)
4. Copy the connection string into `MONGO_URI`

Indexes are created automatically on first boot.

---

## ☁️ Deploy to Render (Free Tier)

### Step-by-step (Manual — Free)

1. Push your repo to GitHub
2. Go to [Render Dashboard](https://dashboard.render.com)
3. Click **New +** → **Web Service**
4. Connect your GitHub repo
5. Configure:

| Setting | Value |
|---|---|
| **Name** | `ips-ups-patcher-bot` |
| **Region** | Choose closest |
| **Runtime** | `Python 3` |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `python run.py` |
| **Instance Type** | **Free** |

6. Go to **Environment** tab and add these variables:

| Key | Value |
|---|---|
| `BOT_TOKEN` | Your bot token |
| `MONGO_URI` | Your MongoDB connection string |
| `ADMIN_ID` | Your Telegram user ID |
| `CHANNEL_ID` | Your private channel ID |

7. Click **Deploy** — done!

> **Note:** Render provides the `PORT` variable automatically for Web Services. The bot binds to it and serves a health-check endpoint alongside the Telegram polling.

### Keeping the bot alive (important!)

Render free-tier Web Services **spin down after 15 minutes of inactivity**. To keep your bot running 24/7:

1. Go to [UptimeRobot](https://uptimerobot.com) (free)
2. Create a new **HTTP(s) monitor**
3. Set URL to: `https://your-service-name.onrender.com/`
4. Set interval to **5 minutes**
5. Save — UptimeRobot will ping your bot, keeping it awake

---

## 📦 Large File Support (Local Bot API)

By default, the Telegram Bot API has these limits:
- **Download:** 20 MB (bot downloading files)
- **Upload:** 50 MB (bot sending files)

Most GBA ROMs (FireRed, Emerald, Ruby) are ~16 MB and work fine with the standard API.

### When you need the local Bot API

If you have ROMs or patched outputs **larger than 20 MB**, you need to run a [local Telegram Bot API server](https://core.telegram.org/bots/api#using-a-local-bot-api-server):

### Setup

1. Build and run the local Bot API server:
```bash
# Clone and build
git clone --recursive https://github.com/tdlib/telegram-bot-api.git
cd telegram-bot-api
mkdir build && cd build
cmake -DCMAKE_BUILD_TYPE=Release ..
cmake --build .

# Run (get api_id and api_hash from https://my.telegram.org)
./telegram-bot-api --api-id=YOUR_API_ID --api-hash=YOUR_API_HASH --local
```

2. Add to your `.env`:
```bash
LOCAL_API_URL=http://localhost:8081
LOCAL_API_FILE_URL=http://localhost:8081/file
```

3. With local API, limits increase to:
    - **Download:** ~2 GB
    - **Upload:** ~2 GB

### Cloud vs Local API comparison

| Feature | Standard (Cloud) API | Local Bot API |
|---|---|---|
| Download limit | 20 MB | ~2 GB |
| Upload limit | 50 MB | ~2 GB |
| Setup required | None | Build + run server |
| Render compatible | ✅ | ❌ (needs VPS) |
| Cost | Free | VPS cost |

> **Recommendation:** Use standard API for typical GBA patching. Only set up local API if you need ROMs > 20 MB.

---

## ⚙️ Queue System

- Only **1 job** runs at a time (configurable via `MAX_QUEUE_SIZE`)
- Users see their **live queue position** which updates as jobs complete
- **Duplicate prevention:** one active job per user
- **Cancel anytime:** the cancel button sets an `asyncio.Event` checked between processing stages
- **Idempotent retries:** if a job was already completed, the cached output is reused

### Job States

```
received → queued → downloading_rom → downloading_patch →
patching → uploading → completed
                                   ↘ failed
                                   ↘ cancelled
```

---

## 🔒 Security & Reliability

- File type validated by extension (`.ips` / `.ups` / `.bps` only)
- File size capped at 100 MB (configurable)
- Invalid/corrupted patches return user-friendly errors
- CRC-32 verification for UPS and BPS patches
- All errors logged; bot never crashes on bad input
- Admin commands restricted to `ADMIN_ID`
- Temp data freed from memory after each job
- No subprocess usage — pure Python patching
- Cache in-progress markers prevent concurrent double-patching
- Explicit timeouts on all file operations (120s)
- Thread executor for CPU-bound patching (event loop stays responsive)

---

## 📝 Notes

- **Motor deprecation:** Motor is deprecated in favor of `pymongo[async]`. The current implementation uses Motor 3.6 which is fully functional. Migration to PyMongo Async is straightforward when needed.
- **Render cold starts:** Free-tier Render services take ~30 seconds to warm up after sleeping. The first message after a sleep period may be slow.

---

## 📄 License

This project is provided as-is for personal use with files you own or have permission to use.
