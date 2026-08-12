"""One betting phase.

Design notes
------------
* ``room.needs_action`` is the set of players who still owe an action *at the
  current bet level*.  A 베팅/레이즈 refills it with every other active player,
  which is what "a raise re-opens the action" means.
* ``room.turn_pid`` is ALWAYS a member of ``needs_action`` while a betting
  phase is running.  That single invariant is what makes out-of-turn 다이 safe.
* 다이 is handled by :func:`drop_from_action`, which is deliberately callable
  from *any* phase and from *any* player — in turn or not.
"""

from __future__ import annotations

from . import config, errors
from .errors import GameError
from .utils import won

ACTION_CHECK = "check"
ACTION_BET = "bet"
ACTION_CALL = "call"
ACTION_RAISE = "raise"
ACTION_DIE = "die"

ALL_ACTIONS = (ACTION_CHECK, ACTION_BET, ACTION_CALL, ACTION_RAISE, ACTION_DIE)

ACTION_VERB = {
    ACTION_CHECK: "체크",
    ACTION_BET: "베팅",
    ACTION_CALL: "콜",
    ACTION_RAISE: "레이즈",
    ACTION_DIE: "다이",
}


# --------------------------------------------------------------------------- #
# phase lifecycle
# --------------------------------------------------------------------------- #

def start_phase(room) -> None:
    """Open a fresh betting phase (1차 or 2차)."""
    room.current_bet = 0
    room.raise_count = 0
    for p in room.player_list:
        p.reset_phase_contrib()
        if p.active:
            p.status_key = "wait"
            p.last_action = None
    room.needs_action = {p.pid for p in room.active_players}
    dealer_seat = room.seat_of(room.dealer_pid)
    if dealer_seat < 0:
        dealer_seat = 0
    # Sit the cursor just *before* the dealer so 선 acts first.
    room.turn_seat = (dealer_seat - 1) % max(1, len(room.seats))
    room.turn_pid = None
    advance_turn(room)


def advance_turn(room) -> bool:
    """Move the turn to the next player who owes an action.

    Returns ``True`` when the betting phase is finished.
    """
    n = len(room.seats)
    if n == 0:
        room.turn_pid = None
        return True

    # Housekeeping: nobody inactive may linger in needs_action.
    room.needs_action = {
        pid for pid in room.needs_action
        if (pid in room.players and room.players[pid].active)
    }

    if not room.needs_action:
        room.turn_pid = None
        return True

    start = room.turn_seat if room.turn_seat >= 0 else -1
    for step in range(1, n + 1):
        idx = (start + step) % n
        pid = room.seats[idx]
        if pid in room.needs_action:
            room.turn_pid = pid
            room.turn_seat = idx
            # "내 차례" always wins over a stale 체크/콜 badge from earlier in
            # this same phase (a raise can re-open the action).
            room.players[pid].status_key = "turn"
            return False

    room.turn_pid = None
    return True


def is_complete(room) -> bool:
    return not room.needs_action


def drop_from_action(room, player) -> None:
    """Remove a player from the pending-action bookkeeping.

    Safe to call at any time, for any reason (다이, disconnect-fold, leaving).
    """
    was_turn = room.turn_pid == player.pid
    room.needs_action.discard(player.pid)
    room.pending_discard.discard(player.pid)
    if was_turn:
        # Leave turn_seat where it is so advance_turn() continues clockwise.
        room.turn_seat = room.seat_of(player.pid)
        room.turn_pid = None


# --------------------------------------------------------------------------- #
# amounts
# --------------------------------------------------------------------------- #

def to_call(room, player) -> int:
    return max(0, room.current_bet - player.phase_contrib)


def raise_cost(room, player) -> int:
    return to_call(room, player) + config.RAISE_INCREMENT


def bet_cost(room, player) -> int:
    return config.BET_AMOUNT


# --------------------------------------------------------------------------- #
# legal actions (also drives the button labels the player sees)
# --------------------------------------------------------------------------- #

def legal_actions(room, player) -> list[dict]:
    """Every candidate action with an ``enabled`` flag and a Korean reason.

    Disabled entries are still returned so the UI can explain *why* a button
    is unavailable instead of silently hiding it.
    """
    if room.phase not in config.BETTING_PHASES:
        return []
    if not player.active:
        return []

    need = to_call(room, player)
    out: list[dict] = []

    if need == 0:
        out.append({
            "type": ACTION_CHECK,
            "label": "체크",
            "amount": 0,
            "enabled": True,
            "reason": "",
            "hint": "추가 칩 없이 넘깁니다.",
        })
        cost = bet_cost(room, player)
        out.append({
            "type": ACTION_BET,
            "label": f"베팅 {won(cost)}",
            "amount": cost,
            "enabled": player.can_afford(cost),
            "reason": "" if player.can_afford(cost) else errors.NOT_ENOUGH_CHIPS,
            "hint": "처음으로 판돈을 올립니다.",
        })
    else:
        out.append({
            "type": ACTION_CALL,
            "label": f"콜 {won(need)}",
            "amount": need,
            "enabled": player.can_afford(need),
            "reason": "" if player.can_afford(need) else errors.NOT_ENOUGH_CHIPS,
            "hint": "현재 베팅 금액을 맞춥니다.",
        })
        cost = raise_cost(room, player)
        can_raise = room.raise_count < config.MAX_RAISES
        out.append({
            "type": ACTION_RAISE,
            "label": f"레이즈 +{won(config.RAISE_INCREMENT)}",
            "amount": cost,
            "enabled": can_raise and player.can_afford(cost),
            "reason": (
                "" if (can_raise and player.can_afford(cost))
                else (errors.MAX_RAISE_REACHED if not can_raise else errors.NOT_ENOUGH_CHIPS)
            ),
            "hint": f"총 {won(cost)} 칩을 냅니다.",
        })

    out.append({
        "type": ACTION_DIE,
        "label": "다이",
        "amount": 0,
        "enabled": True,
        "reason": "",
        "hint": "이번 판만 포기합니다. 넣은 칩은 판돈에 남습니다.",
    })
    return out


def find_action(actions, action_type):
    for a in actions:
        if a["type"] == action_type:
            return a
    return None


# --------------------------------------------------------------------------- #
# applying an action
# --------------------------------------------------------------------------- #

def apply_bet_action(room, player, action_type: str) -> dict:
    """Validate + apply one betting action.

    Returns a small dict describing what happened; the caller (engine) is
    responsible for logging, effects and advancing the phase.
    Raises :class:`GameError` on anything illegal.
    """
    if action_type not in ALL_ACTIONS:
        raise GameError(errors.UNKNOWN_ACTION, "unknown_action")
    if action_type == ACTION_DIE:
        raise GameError(errors.UNKNOWN_ACTION, "unknown_action")  # handled by engine

    if room.phase not in config.BETTING_PHASES:
        raise GameError(errors.CANNOT_BET_NOW, "phase")
    if not player.in_round:
        raise GameError(errors.NOT_IN_ROUND, "not_in_round")
    if player.folded:
        raise GameError(errors.ALREADY_FOLDED, "folded")
    if room.turn_pid != player.pid:
        raise GameError(errors.NOT_YOUR_TURN, "not_turn")

    actions = legal_actions(room, player)
    entry = find_action(actions, action_type)
    if entry is None:
        raise GameError(errors.CANNOT_BET_NOW, "illegal")
    if not entry["enabled"]:
        raise GameError(entry["reason"] or errors.CANNOT_BET_NOW, "illegal")

    paid = 0
    if action_type == ACTION_CHECK:
        room.needs_action.discard(player.pid)

    elif action_type == ACTION_BET:
        paid = player.pay(entry["amount"])
        room.pot += paid
        room.current_bet = player.phase_contrib
        # Opening the betting re-opens the action for everybody else.
        room.needs_action = {p.pid for p in room.active_players if p.pid != player.pid}

    elif action_type == ACTION_CALL:
        paid = player.pay(entry["amount"])
        room.pot += paid
        room.needs_action.discard(player.pid)

    elif action_type == ACTION_RAISE:
        paid = player.pay(entry["amount"])
        room.pot += paid
        room.current_bet = player.phase_contrib
        room.raise_count += 1
        room.needs_action = {p.pid for p in room.active_players if p.pid != player.pid}

    player.last_action = action_type
    player.status_key = action_type
    room.turn_seat = room.seat_of(player.pid)
    room.turn_pid = None

    return {
        "action": action_type,
        "verb": ACTION_VERB[action_type],
        "paid": paid,
        "currentBet": room.current_bet,
        "raiseCount": room.raise_count,
    }


def describe_action(player, info: dict) -> str:
    """Korean game-log sentence for a betting action."""
    from .utils import name_with

    who = name_with(player.nickname, "이", "가")
    kind = info["action"]
    if kind == ACTION_CHECK:
        return f"{who} 체크했습니다."
    if kind == ACTION_BET:
        return f"{who} {won(info['paid'])} 베팅했습니다."
    if kind == ACTION_CALL:
        return f"{who} {won(info['paid'])} 콜했습니다."
    if kind == ACTION_RAISE:
        return f"{who} 레이즈해서 {won(info['paid'])}을 냈습니다."
    return f"{who} 행동했습니다."
