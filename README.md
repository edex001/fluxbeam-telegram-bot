# FluxBeam Telegram Bot ⚡

Independent Solana Telegram trading bot with a FluxBeam-style user experience.

Repository: https://github.com/edex001/fluxbeam-telegram-bot
Website reference: https://fluxbeam.xyz/

## Wallet security

- New wallets use a BIP39 12-word recovery phrase and Solana BIP44 derivation.
- The recovery phrase is shown once at creation and is **never stored** by the bot.
- Imported seed phrases are validated as BIP39 and derived to the same Solana path.
- Private-key imports accept base58 or JSON byte arrays (32/64 bytes).
- Only the signing key bytes are stored in SQLite after Fernet authenticated encryption.
- `WALLET_ENCRYPTION_KEY` is required at startup; an invalid/missing key stops the bot instead of silently storing plaintext.
- Sensitive Telegram import messages are deleted immediately when Telegram permits deletion.
- Never put `BOT_TOKEN`, `JUPITER_API_KEY`, `WALLET_ENCRYPTION_KEY`, seed phrases, or private keys in GitHub.

## Configuration

Copy `.env.example` to `.env` and set the values in your deployment environment:

```env
BOT_TOKEN=...
ADMIN_ID=...
WALLET_ENCRYPTION_KEY=...
WALLET_DB_PATH=data/wallets.db
SOLANA_RPC_URL=https://api.mainnet-beta.solana.com
JUPITER_BASE_URL=https://api.jup.ag
JUPITER_API_KEY=...
DEFAULT_SLIPPAGE_BPS=100
FLUXBEAM_API_BASE_URL=
FLUXBEAM_API_KEY=
```

Generate a Fernet encryption key with:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

**Important:** keep the same `WALLET_ENCRYPTION_KEY` permanently. If you change or lose it, existing encrypted wallets cannot be decrypted.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python main.py
```

## Railway

The repository includes `railway.toml`, `railway.json`, and a worker `Procfile`. Deploy the repository as a persistent worker and add all environment variables in Railway's Variables section.

## Features

- Telegram inline trading menu
- Create/import Solana wallet
- Encrypted wallet persistence
- SOL and token balances
- Portfolio view
- Buy/sell flows
- Jupiter quote/swap adapter
- Slippage configuration
- Solscan transaction links
- Admin notifications
- Railway deployment configuration

## Important

This repository is an independent implementation based on public functionality and does **not** copy or claim to contain FluxBeam's proprietary source code. Keep all signing secrets out of GitHub and use a dedicated funded wallet only after thoroughly testing the deployment.
