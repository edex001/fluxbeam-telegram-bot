import os
import sqlite3
from pathlib import Path
from cryptography.fernet import Fernet
from solders.keypair import Keypair

DB_PATH = Path(os.getenv("WALLET_DB_PATH", "data/wallets.db"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def _fernet() -> Fernet:
    key = os.getenv("WALLET_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError("WALLET_ENCRYPTION_KEY is required for wallet operations")
    return Fernet(key.encode())


def init_db() -> None:
    with sqlite3.connect(DB_PATH) as db:
        db.execute("CREATE TABLE IF NOT EXISTS wallets (user_id INTEGER PRIMARY KEY, public_key TEXT NOT NULL, secret BLOB NOT NULL)")
        db.commit()


def create_wallet(user_id: int) -> str:
    kp = Keypair()
    secret = _fernet().encrypt(bytes(kp))
    with sqlite3.connect(DB_PATH) as db:
        db.execute("INSERT OR REPLACE INTO wallets(user_id, public_key, secret) VALUES(?,?,?)", (user_id, str(kp.pubkey()), secret))
        db.commit()
    return str(kp.pubkey())


def import_wallet(user_id: int, secret_key: str) -> str:
    raw = secret_key.strip()
    try:
        if raw.startswith("["):
            import json
            kp = Keypair.from_bytes(bytes(json.loads(raw)))
        else:
            from base58 import b58decode
            kp = Keypair.from_bytes(b58decode(raw))
    except Exception as exc:
        raise ValueError("Invalid Solana private key") from exc
    encrypted = _fernet().encrypt(bytes(kp))
    with sqlite3.connect(DB_PATH) as db:
        db.execute("INSERT OR REPLACE INTO wallets(user_id, public_key, secret) VALUES(?,?,?)", (user_id, str(kp.pubkey()), encrypted))
        db.commit()
    return str(kp.pubkey())


def get_wallet(user_id: int) -> tuple[str, Keypair] | None:
    with sqlite3.connect(DB_PATH) as db:
        row = db.execute("SELECT public_key, secret FROM wallets WHERE user_id=?", (user_id,)).fetchone()
    if not row:
        return None
    return row[0], Keypair.from_bytes(_fernet().decrypt(row[1]))


def delete_wallet(user_id: int) -> None:
    with sqlite3.connect(DB_PATH) as db:
        db.execute("DELETE FROM wallets WHERE user_id=?", (user_id,))
        db.commit()
