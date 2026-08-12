"""Table builders and play-out helpers shared by the test modules.

The engine's default :class:`InstantHooks` runs every timed transition
synchronously, so a whole round plays out inside one function call — no
sleeping, no threads, no flakiness.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from game import betting, config, engine          # noqa: E402
from game.deck import Card                        # noqa: E402
from game.rooms import RoomManager                # noqa: E402

NAMES = ["김대균", "민수", "영희", "철수", "지현", "상우"]
CHARS = ["bear", "rabbit", "robot", "cat", "fox", "penguin"]


# --------------------------------------------------------------------------- #
# building tables
# --------------------------------------------------------------------------- #

def make_table(count=3, names=None, chars=None):
    """-> (manager, room, [players]) with `count` seated players in the lobby."""
    names = names or NAMES
    chars = chars or CHARS
    manager = RoomManager()
    room, host = manager.create_room("sid0", names[0], chars[0])
    players = [host]
    for i in range(1, count):
        _room, p = manager.join_room("sid%d" % i, room.code, names[i], chars[i])
        players.append(p)
    return manager, room, players


def started_table(count=3, **kw):
    """A table that has already been dealt and is sitting in 1차 베팅."""
    manager, room, players = make_table(count, **kw)
    engine.start_game(room, players[0])
    return manager, room, players


# --------------------------------------------------------------------------- #
# play-out helpers
# --------------------------------------------------------------------------- #

def enabled_actions(room, player):
    return {a["type"]: a for a in betting.legal_actions(room, player) if a["enabled"]}


def act_passively(room, player):
    """체크 if possible, otherwise 콜, otherwise 다이."""
    acts = enabled_actions(room, player)
    if betting.ACTION_CHECK in acts:
        return engine.bet_action(room, player, betting.ACTION_CHECK)
    if betting.ACTION_CALL in acts:
        return engine.bet_action(room, player, betting.ACTION_CALL)
    return engine.fold(room, player)


def finish_betting(room, limit=60):
    """Everybody checks/calls until the current betting phase closes."""
    start_phase = room.phase
    guard = 0
    while room.phase == start_phase and room.turn_pid:
        act_passively(room, room.get(room.turn_pid))
        guard += 1
        assert guard < limit, "betting phase never finished"
    return room.phase


def finish_discards(room, limit=20):
    """Everybody drops their first card."""
    guard = 0
    while room.phase == config.PHASE_DISCARD and room.pending_discard:
        pid = sorted(room.pending_discard)[0]
        player = room.get(pid)
        engine.discard(room, player, player.cards[0].id)
        guard += 1
        assert guard < limit, "discard phase never finished"
    return room.phase


def play_round(room):
    """Drive one complete round from 1차 베팅 to 판 결과."""
    if room.phase == config.PHASE_BET1:
        finish_betting(room)
    if room.phase == config.PHASE_DISCARD:
        finish_discards(room)
    if room.phase == config.PHASE_BET2:
        finish_betting(room)
    return room.phase


def set_hand(player, a, b):
    """Force a player's final two cards to known numbers."""
    player.cards = [
        Card(id="h%d%s" % (a, player.pid[-4:]), number=a),
        Card(id="k%d%s" % (b, player.pid[-4:]), number=b),
    ]
    return player


def total_chips(room):
    return sum(p.chips for p in room.player_list) + room.pot
