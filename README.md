# VC Monitor Bot

Production-grade Telegram bot for Voice Chat monitoring and network testing.

## Features

- 🔍 **Automatic Voice Chat Detection**: Monitors your Voice Chat activity
- ⚡ **High-Performance Attack Engine**: Multi-threaded request generation
- 🔒 **Fixed Configuration**: Immutable request/thread limits (owner-only)
- 📊 **Real-time Statistics**: Live attack progress and completion reports
- ✅ **Manual Approval**: Owner must confirm before any action
- 🤖 **Dual Client Architecture**: User client for detection + Bot for control

## Architecture

```
main.py           - Entry point & lifecycle management
config.py         - Environment-based configuration
attack_engine.py  - Multi-threaded attack implementation
vc_detector.py    - Voice Chat monitoring
bot_handler.py    - Telegram UI/handlers
utils.py          - Helper functions
```

## Deployment

### 1. Generate Session String (Local)

```bash
pip install pyrogram tgcrypto
python3 << 'EOF'
from pyrogram import Client

API_ID = 1234567  # Your API ID
API_HASH = "your_api_hash"

with Client("session", api_id=API_ID, api_hash=API_HASH) as app:
    session = app.export_session_string()
    print(f"\nYour Session String:\n{session}\n")
EOF
```

### 2. Heroku Deploy

[![Deploy](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/Oxeigns/Telegram_vc_ddos/tree/main)

**Or manual:**

```bash
heroku create your-vc-bot
heroku config:set API_ID=1234567
heroku config:set API_HASH=your_hash
heroku config:set SESSION_STRING="your_long_session_string"
heroku config:set BOT_TOKEN="your_bot_token"
heroku config:set ADMIN_USER_ID=123456789
heroku config:set MAX_REQUESTS=100000
heroku config:set THREAD_COUNT=50
heroku config:set ATTACK_TIMEOUT=300

git push heroku main
heroku ps:scale worker=1
```

## Configuration

All settings via environment variables (immutable in deployment):

| Variable | Description | Default |
|----------|-------------|---------|
| `API_ID` | Telegram API ID | Required |
| `API_HASH` | Telegram API Hash | Required |
| `SESSION_STRING` | Pyrogram session | Required |
| `BOT_TOKEN` | BotFather token | Required |
| `ADMIN_USER_ID` | Your user ID | Required |
| `MAX_REQUESTS` | Fixed request limit | 100000 |
| `THREAD_COUNT` | Attack threads | 50 |
| `ATTACK_TIMEOUT` | Max duration (sec) | 300 |

## Commands

| Command | Description |
|---------|-------------|
| `/start` | Show main menu & status |
| `/status` | Check attack progress |
| `/stop` | Halt active attack |

## Usage Flow

1. **Bot starts** → Sends startup notification to admin
2. **Admin joins Voice Chat** → Bot detects and notifies
3. **Confirmation prompt** → "Attack this IP? YES/NO"
4. **Click YES** → Attack starts with fixed MAX_REQUESTS
5. **Real-time updates** → Progress every 10 seconds
6. **Completion** → Final statistics sent

## Security

- ✅ Owner verification on all actions
- ✅ Manual approval required for attacks
- ✅ Fixed limits (immutable by users)
- ✅ No hardcoded credentials
- ✅ Session string authentication
- ✅ Daemon threads with cleanup

## Logs

View logs:
```bash
heroku logs --tail
```

## License

For authorized security testing only. Ensure compliance with local laws and platform ToS.
