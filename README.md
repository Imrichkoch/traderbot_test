# Discord Trader Calculator Bot

Discord bot with step-by-step risk management wizard for traders.

## Command

- Text command (no slash): `start`
- Usage:
  - write only `start`
  - click `Open Calculator`
  - fill modal: `account size`, `entry price`, `SL pips`
  - continue with dropdown/buttons (risk, leverage, category, instrument, lots/micro, R:R)

The wizard then calculates:
- position size
- max loss / max profit
- stop-loss / take-profit levels
- required margin
- min win-rate
- pip value model note (direct/inverse/cross)

## Install

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Run

Linux/macOS:
```bash
export DISCORD_BOT_TOKEN="your_token"
python bot.py
```

Windows PowerShell:
```powershell
$env:DISCORD_BOT_TOKEN="your_token"
python bot.py
```

## Discord Developer Portal

Required bot settings:
- Privileged Gateway Intents:
  - Message Content Intent = ON
- Bot permissions:
  - Send Messages
  - Use Application Commands
  - Read Message History
  - Embed Links