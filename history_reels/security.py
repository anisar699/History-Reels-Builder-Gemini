"""Small, dependency-free security helpers for the Streamlit dashboard."""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
from pathlib import Path


TRUE_VALUES = {"1", "true", "yes", "on"}
PBKDF2_ALGORITHM = "pbkdf2_sha256"
PBKDF2_ITERATIONS = 600_000


def env_flag(name: str, default: bool = False) -> bool:
    """Read a boolean environment variable without exposing its value."""
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in TRUE_VALUES


def dashboard_auth_required() -> bool:
    return env_flag("DASHBOARD_REQUIRE_AUTH")


def session_key_override_allowed() -> bool:
    """Whether the dashboard may accept/persist browser-supplied API keys.

    Explicit ``DASHBOARD_ALLOW_SESSION_KEY_OVERRIDE`` always wins.
    When unset, local desktop use (auth off) may save keys; public auth mode
    blocks browser key entry unless the operator opts in.
    """
    raw = os.environ.get("DASHBOARD_ALLOW_SESSION_KEY_OVERRIDE")
    if raw is not None and str(raw).strip() != "":
        return str(raw).strip().lower() in TRUE_VALUES
    return not dashboard_auth_required()


def save_local_env_values(env_path: str | os.PathLike[str], updates: dict[str, str]) -> list[str]:
    """Persist non-empty environment values locally without logging their contents."""
    from dotenv import set_key

    target = Path(env_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []
    for name, raw_value in updates.items():
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", str(name)):
            raise ValueError(f"Invalid environment variable name: {name}")
        value = str(raw_value).strip()
        if not value:
            continue
        set_key(str(target), str(name), value, quote_mode="auto")
        saved.append(str(name))
    return saved


def hash_password(password: str, *, salt: bytes | None = None, iterations: int = PBKDF2_ITERATIONS) -> str:
    """Create a salted PBKDF2 password hash suitable for environment storage."""
    if not password:
        raise ValueError("Password cannot be empty.")
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"{PBKDF2_ALGORITHM}${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, expected_hash: str) -> bool:
    """Verify PBKDF2 hashes, retaining compatibility with legacy SHA-256."""
    if not password or not expected_hash:
        return False
    stored = expected_hash.strip().lower()
    if stored.startswith(f"{PBKDF2_ALGORITHM}$"):
        try:
            _, iteration_text, salt_hex, digest_hex = stored.split("$", 3)
            iterations = int(iteration_text)
            if iterations < 100_000:
                return False
            salt = bytes.fromhex(salt_hex)
            expected = bytes.fromhex(digest_hex)
            actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        except (TypeError, ValueError):
            return False
        return hmac.compare_digest(actual, expected)

    if len(stored) != 64:
        return False
    legacy_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()
    return hmac.compare_digest(legacy_hash, stored)


def require_dashboard_auth(st) -> None:
    """Stop unauthenticated access when public-hosting auth is enabled."""
    if not dashboard_auth_required() or st.session_state.get("dashboard_authenticated"):
        return

    expected_hash = os.environ.get("DASHBOARD_PASSWORD_HASH", "").strip()
    st.title("Dashboard access")
    if not expected_hash:
        st.error("Access is not configured. Set DASHBOARD_PASSWORD_HASH before exposing this dashboard publicly.")
        st.stop()

    password = st.text_input("Dashboard password", type="password", key="dashboard_password")
    if st.button("Sign in", type="primary", width="stretch"):
        if verify_password(password, expected_hash):
            st.session_state["dashboard_authenticated"] = True
            st.rerun()
        st.error("Incorrect password.")
    st.stop()


def main() -> int:
    """Interactively generate a hash without exposing the password in shell history."""
    import getpass

    password = getpass.getpass("Dashboard password: ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        print("Passwords do not match.")
        return 1
    try:
        print(hash_password(password))
    except ValueError as error:
        print(error)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
