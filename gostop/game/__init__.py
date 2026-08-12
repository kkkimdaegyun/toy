"""숫자 섯다 — a casual office LAN party card game.

Package layout
--------------
config       tunable numbers and Korean labels
utils        pure helpers (money formatting, 조사, room codes, LAN IP)
errors       GameError + every Korean error string
deck         the 20-card number deck (0..9 x2), opaque card ids
hands        the 광땡 / 땡 / 끗 evaluator (no 49파토)
models       Player + Room state containers
betting      a single betting phase, including out-of-turn 다이 safety
engine       the round state machine
serializers  per-player, leak-proof state snapshots
rooms        the room registry
"""

from . import config  # noqa: F401

__all__ = [
    "config", "utils", "errors", "deck", "hands",
    "models", "betting", "engine", "serializers", "rooms",
]
