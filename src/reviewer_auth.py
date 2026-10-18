"""Reviewer authentication and authorization foundation.

Standalone security prototype. No database integration or
review-writing enforcement is enabled by this module.
"""

from dataclasses import dataclass, field
import hashlib
import hmac
import re
import secrets


SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 32
SALT_BYTES = 16

ROLES = frozenset({
    "administrator",
    "reviewer",
    "viewer",
})

PERMISSIONS = {
    "administrator": frozenset({
        "read_opportunities",
        "read_reviews",
        "approve_opportunity",
        "reject_opportunity",
        "manage_reviewers",
    }),
    "reviewer": frozenset({
        "read_opportunities",
        "read_reviews",
        "approve_opportunity",
        "reject_opportunity",
    }),
    "viewer": frozenset({
        "read_opportunities",
        "read_reviews",
    }),
}

# Delivery authorization is intentionally outside reviewer roles.
KNOWN_ACTIONS = frozenset().union(*PERMISSIONS.values())

ACCOUNT_ID_PATTERN = re.compile(
    r"^[a-zA-Z0-9_-]{3,64}$"
)


@dataclass(frozen=True)
class ReviewerAccount:
    """Account snapshot supplied by a future trusted identity store."""

    account_id: str
    role: str
    password_hash: str = field(repr=False)
    active: bool = True


def hash_password(password):
    """Hash a password with a random salt and scrypt."""

    if not isinstance(password, str):
        raise TypeError("Password must be a string.")

    if not 12 <= len(password) <= 128:
        raise ValueError(
            "Password must contain 12 to 128 characters."
        )

    salt = secrets.token_bytes(SALT_BYTES)

    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=SCRYPT_DKLEN,
    )

    return (
        f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}$"
        f"{salt.hex()}${digest.hex()}"
    )


def verify_password(password, stored_hash):
    """Verify a password without comparing plaintext secrets."""

    if not isinstance(password, str):
        return False

    if not isinstance(stored_hash, str):
        return False

    try:
        parts = stored_hash.split("$")

        if len(parts) != 6 or parts[0] != "scrypt":
            return False

        _, n_text, r_text, p_text, salt_hex, digest_hex = parts

        # Only accept the approved parameters. Never accept arbitrary
        # attacker-controlled work factors from a stored string.
        if (
            n_text != str(SCRYPT_N)
            or r_text != str(SCRYPT_R)
            or p_text != str(SCRYPT_P)
            or len(salt_hex) != SALT_BYTES * 2
            or len(digest_hex) != SCRYPT_DKLEN * 2
        ):
            return False

        salt = bytes.fromhex(salt_hex)
        expected_digest = bytes.fromhex(digest_hex)

        actual_digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=SCRYPT_N,
            r=SCRYPT_R,
            p=SCRYPT_P,
            dklen=SCRYPT_DKLEN,
        )

        return hmac.compare_digest(
            actual_digest,
            expected_digest,
        )

    except (ValueError, UnicodeError):
        return False


def validate_account(account):
    """Validate a trusted account snapshot's basic structure."""

    if not isinstance(account, ReviewerAccount):
        return False

    return (
        isinstance(account.account_id, str)
        and ACCOUNT_ID_PATTERN.fullmatch(account.account_id)
        is not None
        and account.role in ROLES
        and isinstance(account.password_hash, str)
        and isinstance(account.active, bool)
    )


def authenticate_reviewer(account, password):
    """Authenticate the supplied trusted account snapshot."""

    if not validate_account(account):
        return False

    if not account.active:
        return False

    return verify_password(
        password,
        account.password_hash,
    )


def authorize_reviewer(account, password, action):
    """Require both authentication and role permission.

    The account object must originate from a trusted identity store.
    Callers must not construct their own account or choose their role.
    """

    if not isinstance(action, str) or action not in KNOWN_ACTIONS:
        return False

    if not authenticate_reviewer(account, password):
        return False

    return action in PERMISSIONS[account.role]