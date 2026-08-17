import json
import os
import sqlite3
from pathlib import Path

import base58
from bip_utils import Bip39MnemonicGenerator, Bip39SeedGenerator, Bip39WordsNum, Bip44, Bip44Coins, Bip44Changes
from cryptography.fernet import Fernet, InvalidToken
from solders.keypair import Keypair

DB_PATH = Path(os.getenv("WALLET_DB_PATH", "data/wallets.db"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def _fernet() -> Fernet:
    key = os.getenv("WALLET_ENCRYPTION_KEY", "").strip()
    if not key:
        raise RuntimeError("WALLET_ENCRYPTION_KEY is required for wallet operations")
    try:
        return Fernet(key.encode())
    except Exception as exc:
        raise RuntimeError("WALLET_ENCRYPTION_KEY is not a valid Fernet key") from exc


def init_db() -> None:
    _fernet()
    with sqlite3.connect(DB_PATH) as db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS wallets ("
            "user_id INTEGER PRIMARY KEY, public_key TEXT NOT NULL, secret BLOB NOT NULL)"
        )
        db.commit()


def _store(user_id: int, kp: Keypair) -> str:
    encrypted = _fernet().encrypt(bytes(kp))
    with sqlite3.connect(DB_PATH) as db:
        db.execute(
            "INSERT OR REPLACE INTO wallets(user_id, public_key, secret) VALUES(?,?,?)",
            (user_id, str(kp.pubkey()), encrypted),
        )
        db.commit()
    return str(kp.pubkey())


def _keypair_from_seed_phrase(mnemonic: str) -> Keypair:
    words = " ".join(mnemonic.strip().split())
    count = len(words.split())
    if count not in {12, 15, 18, 21, 24}:
        raise ValueError("Seed phrase must contain 12, 15, 18, 21, or 24 words")

    seed = Bip39SeedGenerator(words).Generate()
    ctx = (
        Bip44.FromSeed(seed, Bip44Coins.SOLANA)
        .Purpose()
        .Coin()
        .Account(0)
        .Change(Bip44Changes.CHAIN_EXT)
        .AddressIndex(0)
    )
    return Keypair.from_seed(ctx.PrivateKey().Raw().ToBytes())


def create_wallet(user_id: int) -> tuple[str, str]:
    """Create a BIP39 12-word Solana wallet and return (address, mnemonic).

    The mnemonic is returned only to the Telegram handler so it can be shown once.
    It is never persisted; only the encrypted signing key is stored.
    """
    mnemonic = Bip39MnemonicGenerator().FromWordsNumber(Bip39WordsNum.WORDS_NUM_12).ToStr()
    kp = _keypair_from_seed_phrase(mnemonic)
    return _store(user_id, kp), mnemonic


def import_seed_phrase(user_id: int, mnemonic: str) -> str:
    kp = _keypair_from_seed_phrase(mnemonic)
    return _store(user_id, kp)


def import_private_key(user_id: int, secret_key: str) -> str:
    raw = secret_key.strip()
    if not raw:
        raise ValueError("Private key is empty")

    try:
        if raw.startswith("["):
            values = json.loads(raw)
            if not isinstance(values, list) or not all(isinstance(x, int) for x in values):
                raise ValueError("Invalid JSON private key")
            key_bytes = bytes(values)
        else:
            key_bytes = base58.b58decode(raw)

        if len(key_bytes) == 64:
            kp = Keypair.from_bytes(key_bytes)
        elif len(key_bytes) == 32:
            kp = Keypair.from_seed(key_bytes)
        else:
            raise ValueError("Private key must decode to 32 or 64 bytes")
    except Exception as exc:
        raise ValueError("Invalid Solana private key") from exc

    return _store(user_id, kp)


def get_wallet(user_id: int) -> tuple[str, Keypair] | None:
    with sqlite3.connect(DB_PATH) as db:
        row = db.execute(
            "SELECT public_key, secret FROM wallets WHERE user_id=?", (user_id,)
        ).fetchone()
    if not row:
        return None
    try:
        secret = _fernet().decrypt(row[1])
        return row[0], Keypair.from_bytes(secret)
    except InvalidToken as exc:
        raise RuntimeError("Wallet could not be decrypted; check WALLET_ENCRYPTION_KEY") from exc


def delete_wallet(user_id: int) -> None:
    with sqlite3.connect(DB_PATH) as db:
        db.execute("DELETE FROM wallets WHERE user_id=?", (user_id,))
        db.commit()
