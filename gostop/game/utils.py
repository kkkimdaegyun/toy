"""Small pure helpers shared across the game package."""

from __future__ import annotations

import re
import secrets
import socket
import unicodedata

from . import config

_WS_RE = re.compile(r"\s+")


# --- formatting -------------------------------------------------------------

def won(amount: int) -> str:
    """10000 -> '10,000'.  Used for every Korean money string the user sees."""
    try:
        return f"{int(amount):,}"
    except (TypeError, ValueError):
        return "0"


def josa(word: str, with_batchim: str, without_batchim: str) -> str:
    """Pick the correct Korean particle for `word`.

    josa('김대균', '이', '가') -> '김대균이'
    josa('민수',   '이', '가') -> '민수가'
    """
    if not word:
        return word + without_batchim
    last = word[-1]
    code = ord(last)
    if 0xAC00 <= code <= 0xD7A3:
        has_batchim = (code - 0xAC00) % 28 != 0
    elif last.isdigit():
        # 0,1,3,6,7,8 end in a batchim when read aloud in Korean
        has_batchim = last in "013678"
    elif last.isalpha():
        has_batchim = last.lower() in "lmnr"
    else:
        has_batchim = False
    return word + (with_batchim if has_batchim else without_batchim)


def name_with(word: str, with_batchim: str, without_batchim: str) -> str:
    """Convenience: '김대균님' + correct particle."""
    return josa(f"{word}님", with_batchim, without_batchim)


# --- identity ---------------------------------------------------------------

def clean_nickname(raw) -> str:
    """Trim / collapse whitespace and clamp length. Returns '' when unusable."""
    if not isinstance(raw, str):
        return ""
    text = unicodedata.normalize("NFC", raw)
    text = "".join(ch for ch in text if ch.isprintable())
    text = _WS_RE.sub(" ", text).strip()
    if not text:
        return ""
    return text[: config.NICKNAME_MAX_LEN]


def nickname_key(nickname: str) -> str:
    """Case/space-insensitive key used for duplicate detection inside a room."""
    return _WS_RE.sub("", nickname).casefold()


def new_token() -> str:
    """Secure reconnect token stored in the browser's localStorage."""
    return secrets.token_urlsafe(24)


def new_id(prefix: str = "") -> str:
    return f"{prefix}{secrets.token_hex(5)}"


def new_room_code(exclude=()) -> str:
    """Short, human-readable, unambiguous room code (e.g. 'A7K4')."""
    excluded = set(exclude)
    alphabet = config.ROOM_CODE_ALPHABET
    for _ in range(2000):
        code = "".join(secrets.choice(alphabet) for _ in range(config.ROOM_CODE_LEN))
        if code not in excluded:
            return code
    # Astronomically unlikely; fall back to a longer code.
    while True:
        code = "".join(secrets.choice(alphabet) for _ in range(config.ROOM_CODE_LEN + 2))
        if code not in excluded:
            return code


def normalize_room_code(raw) -> str:
    if not isinstance(raw, str):
        return ""
    return _WS_RE.sub("", raw).upper()[:8]


# --- networking -------------------------------------------------------------

def detect_lan_ip():
    """Best-effort LAN IPv4 of this machine. Returns None instead of raising."""
    candidates = []

    # 1) The routing-table trick: no packets are actually sent.
    for probe in ("10.255.255.255", "8.8.8.8", "192.168.1.1"):
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(0.3)
            sock.connect((probe, 1))
            ip = sock.getsockname()[0]
            if _usable_ip(ip):
                return ip
        except Exception:
            pass
        finally:
            if sock is not None:
                try:
                    sock.close()
                except Exception:
                    pass

    # 2) Fall back to whatever the hostname resolves to.
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if _usable_ip(ip):
                candidates.append(ip)
    except Exception:
        pass

    # Prefer private ranges most likely to be the office LAN.
    for ip in candidates:
        if ip.startswith("192.168."):
            return ip
    for ip in candidates:
        if ip.startswith("10."):
            return ip
    return candidates[0] if candidates else None


def _usable_ip(ip) -> bool:
    return bool(ip) and isinstance(ip, str) and not ip.startswith("127.") and ip != "0.0.0.0"
