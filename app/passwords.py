"""Versioned password hashing; bcrypt remains read-only for existing accounts."""

import bcrypt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

MIN_PASSWORD_LENGTH = 15
MAX_PASSWORD_LENGTH = 128
HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=1)
# An unrelated random credential, never an account password. Unknown accounts
# still perform the same expensive verification as new Argon2 accounts.
DUMMY_HASH = "$argon2id$v=19$m=65536,t=3,p=1$ovrgJitUEaVqF92mvPAKTw$clcQVUyaE4oPtv29/GJbUf9i2pjrDtCrUkwJKFjEFNQ"

# Local baseline only, not a substitute for a comprehensive breached-password
# corpus. Compare without common separators, but never normalize the hash input.
COMMON_PASSWORDS = frozenset({
    "password123456789", "password1234567890", "123456789012345",
    "1234567890123456", "qwerty1234567890", "qwertyuiopasdfgh",
    "iloveyou123456789", "letmein123456789", "admin1234567890",
    "пароль1234567890", "turbotears123456", "formulaone123456",
})


def password_policy_error(password: str) -> str | None:
    if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        return "Пароль должен содержать от 15 до 128 символов"
    if any(ord(char) < 32 or 0x7f <= ord(char) < 0xa0 or 0xd800 <= ord(char) <= 0xdfff for char in password):
        return "Пароль не должен содержать управляющие символы"
    compact = "".join(char for char in password.casefold() if char.isalnum())
    if len(set(compact)) < 3 or compact in COMMON_PASSWORDS:
        return "Этот пароль слишком распространён. Выберите уникальную длинную фразу"
    return None


def verify_password(password: str, password_hash: str) -> bool:
    # Login preserves old credentials, including those shorter than today's
    # policy. Explicitly reject the bcrypt truncation ambiguity instead of
    # accepting any suffix after byte 72.
    if not password or len(password) > MAX_PASSWORD_LENGTH:
        return False
    try:
        if password_hash.startswith(("$2a$", "$2b$", "$2y$")):
            encoded = password.encode("utf-8")
            return len(encoded) <= 72 and bcrypt.checkpw(encoded, password_hash.encode("ascii"))
        return HASHER.verify(password_hash, password)
    except (InvalidHashError, VerificationError, ValueError, TypeError, UnicodeError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return not password_hash.startswith("$argon2id$") or HASHER.check_needs_rehash(password_hash)
