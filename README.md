# FluxBeam Telegram Bot ⚡

Telegram trading-bot starter for a Solana/FluxBeam-style experience.

Repository: https://github.com/edex001/fluxbeam-telegram-bot
Website: https://fluxbeam.xyz/

## Included

- Telegram UI with inline trading menu
- `/start`, `/help`, `/price`, `/swap`
- SOL price lookup through Jupiter's public API interface
- Admin notification hook via `ADMIN_ID`
- Environment-based secrets
- Docker + Render worker deployment files
- Configurable FluxBeam API adapter variables
- Private keys are **not** stored in the repository

## Configuration

Copy `.env.example` to `.env` and set:

```env
BOT_TOKEN=...
ADMIN_ID=...
SOLANA_RPC_URL=https://api.mainnet-beta.solana.com
JUPITER_BASE_URL=https://api.jup.ag
JUPITER_API_KEY=...
FLUXBEAM_API_BASE_URL=...
FLUXBEAM_API_KEY=...
```

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python main.py
```

## Important

This repository is an implementation built around the public FluxBeam concept; it does **not** copy or claim to contain FluxBeam's proprietary source code. Live swap execution should only be enabled after the official FluxBeam API/SDK endpoint and signing model are confirmed. Keep signing keys out of GitHub and use an encrypted signer or dedicated wallet service in production.
