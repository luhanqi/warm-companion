from __future__ import annotations

import hashlib
import secrets
from typing import Optional, Tuple


SCRYPT_N = 2 ** 14
SCRYPT_R = 8
SCRYPT_P = 1


def hash_password(password: str) -> str:
    """Create a memory-hard password hash.

    The previous release used one SHA-256 round.  Keep verification support for
    those rows so existing users can still sign in, then transparently upgrade
    them after a successful login.
    """
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32
    )
    return "scrypt:%s:%s:%s:%s:%s" % (
        SCRYPT_N,
        SCRYPT_R,
        SCRYPT_P,
        salt.hex(),
        digest.hex(),
    )


def check_password(password: str, stored: str) -> bool:
    if not stored:
        return False
    if stored.startswith("scrypt:"):
        try:
            _, n, r, p, salt_hex, digest = stored.split(":", 5)
            guess = hashlib.scrypt(
                password.encode("utf-8"),
                salt=bytes.fromhex(salt_hex),
                n=int(n),
                r=int(r),
                p=int(p),
                dklen=len(bytes.fromhex(digest)),
            ).hex()
        except (ValueError, TypeError):
            return False
        return secrets.compare_digest(guess, digest)
    if ":" not in stored:
        return False
    # Legacy SHA-256 rows are accepted only for migration.
    salt, digest = stored.split(":", 1)
    guess = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return secrets.compare_digest(guess, digest)


def password_needs_upgrade(stored: str) -> bool:
    return not (stored or "").startswith("scrypt:")


def new_token() -> str:
    return secrets.token_hex(24)


def token_digest(token: str) -> str:
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


def parse_bearer(header: Optional[str]) -> Optional[str]:
    if not header:
        return None
    text = header.strip()
    if text.lower().startswith("bearer "):
        return text[7:].strip()
    return text
