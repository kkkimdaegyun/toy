"""Per-player state serialization.

SECURITY RULE — the whole point of this module
----------------------------------------------
A card's number is written into the payload **only** when the viewer is
legally allowed to see it:

    * it is the viewer's own card, or
    * the card belongs to a player who reached showdown without folding
      (``player.revealed``).

A player who chose 다이 is never revealed, not even after the round ends.
Everybody else's cards serialize to ``{"id": ..., "hidden": true}``.
Card ids are opaque random tokens (see deck.py) so they leak nothing.

Never broadcast a Room object.  Build a fresh view for every viewer.
"""

from __future__ import annotations

from . import betting, config, engine
from .hands import evaluate, preview_discards
from .models import STATUS_LABELS
from .utils import won


def public_config() -> dict:
    """Constants the browser needs to render Korean money strings."""
    return {
        "startingChips": config.STARTING_CHIPS,
        "baseUnit": config.BASE_UNIT,
        "ante": config.ANTE,
        "betAmount": config.BET_AMOUNT,
        "raiseIncrement": config.RAISE_INCREMENT,
        "maxRaises": config.MAX_RAISES,
        "loanAmount": config.LOAN_AMOUNT,
        "loanInterest": config.LOAN_INTEREST,
        "loanNet": config.LOAN_NET,
        "maxLoans": config.MAX_LOANS,
        "minPlayers": config.MIN_PLAYERS,
        "maxPlayers": config.MAX_PLAYERS,
        "nicknameMax": config.NICKNAME_MAX_LEN,
        "characters": config.CHARACTERS,
        "reactions": config.REACTIONS,
        "phaseFlow": [
            {"key": k, "label": config.PHASE_LABELS[k]} for k in config.PHASE_FLOW
        ],
    }


# --------------------------------------------------------------------------- #
# cards
# --------------------------------------------------------------------------- #

def _cards_for_viewer(target, viewer_pid: str) -> list:
    """The ONLY place card numbers may enter a payload."""
    if target.pid == viewer_pid:
        return [c.private() for c in target.cards]
    if target.revealed and not target.folded:
        return [c.private() for c in target.cards]
    return [c.public() for c in target.cards]


# --------------------------------------------------------------------------- #
# players
# --------------------------------------------------------------------------- #

def _badges(room, p) -> list:
    out = []
    if room.host_pid == p.pid:
        out.append({"key": "host", "label": "방장"})
    if room.dealer_pid == p.pid and room.phase != config.PHASE_LOBBY:
        out.append({"key": "dealer", "label": "선"})
    if p.loan_count:
        out.append({"key": f"loan{p.loan_count}", "label": f"대출 {p.loan_count}회"})
    if p.automatic_last_place:
        out.append({"key": "autolast", "label": "최하위 확정"})
    return out


def _status_for(room, p) -> tuple:
    """(status_key, korean_label)"""
    if not p.connected:
        return "disconnected", STATUS_LABELS["disconnected"]
    if room.phase == config.PHASE_LOBBY:
        return "ready", STATUS_LABELS["ready"]
    if p.spectating:
        return "spectating", STATUS_LABELS["spectating"]
    if p.folded:
        return "die", STATUS_LABELS["die"]
    if room.turn_pid == p.pid:
        return "turn", STATUS_LABELS["turn"]
    return p.status_key, STATUS_LABELS.get(p.status_key, "대기")


def _player_view(room, p, viewer_pid: str) -> dict:
    status_key, status_label = _status_for(room, p)
    cards = _cards_for_viewer(p, viewer_pid)

    view = {
        "pid": p.pid,
        "nickname": p.nickname,
        "character": p.character,
        "seat": p.seat,
        "chips": p.chips,
        "chipsText": won(p.chips),
        "loanCount": p.loan_count,
        "autoLast": p.automatic_last_place,
        "connected": p.connected,
        "isHost": room.host_pid == p.pid,
        "isDealer": room.dealer_pid == p.pid,
        "isYou": p.pid == viewer_pid,
        "isTurn": room.turn_pid == p.pid,
        "inRound": p.in_round,
        "folded": p.folded,
        "spectating": p.spectating,
        "revealed": bool(p.revealed and not p.folded),
        "cardCount": len(p.cards),
        "cards": cards,
        "roundContrib": p.round_contrib,
        "phaseContrib": p.phase_contrib,
        "lastAction": p.last_action,
        "statusKey": status_key,
        "status": status_label,
        "badges": _badges(room, p),
        "roundsWon": p.rounds_won,
        "choosingDiscard": p.pid in room.pending_discard,
    }

    # A hand is only ever attached for the viewer themself, or for a player
    # whose cards are legitimately revealed.
    if p.hand is not None and (p.pid == viewer_pid or (p.revealed and not p.folded)):
        view["hand"] = p.hand.to_dict()
    else:
        view["hand"] = None
    return view


# --------------------------------------------------------------------------- #
# the viewer's private block
# --------------------------------------------------------------------------- #

def _you_view(room, me) -> dict:
    cards = [c.private() for c in me.cards]

    hand = None
    if len(me.cards) == config.FINAL_HAND_SIZE:
        hand = evaluate(me.cards).to_dict()

    previews = []
    if len(me.cards) == 3 and room.phase == config.PHASE_DISCARD:
        previews = preview_discards(me.cards)

    actions = []
    if room.turn_pid == me.pid and room.phase in config.BETTING_PHASES:
        actions = betting.legal_actions(room, me)

    to_call = (betting.to_call(room, me)
               if room.phase in config.BETTING_PHASES and me.active else 0)

    can_die = (
        room.phase in config.DAI_ALLOWED_PHASES
        and me.in_round and not me.folded
    )

    loan_allowed, loan_reason = engine.loan_availability(room, me)

    return {
        "pid": me.pid,
        "nickname": me.nickname,
        "character": me.character,
        "seat": me.seat,
        "isHost": room.host_pid == me.pid,
        "isDealer": room.dealer_pid == me.pid,
        "chips": me.chips,
        "chipsText": won(me.chips),
        "loanCount": me.loan_count,
        "autoLast": me.automatic_last_place,
        "inRound": me.in_round,
        "folded": me.folded,
        "spectating": me.spectating,
        "cards": cards,
        "hand": hand,
        "discardPreviews": previews,
        "needsDiscard": me.pid in room.pending_discard,
        "isTurn": room.turn_pid == me.pid,
        "actions": actions,
        "toCall": to_call,
        "toCallText": won(to_call),
        "canDie": can_die,
        "loan": {
            "allowed": loan_allowed,
            "reason": loan_reason,
            "count": me.loan_count,
            "max": config.MAX_LOANS,
            "amount": config.LOAN_AMOUNT,
            "interest": config.LOAN_INTEREST,
            "net": config.LOAN_NET,
            "nextIsPenalty": me.loan_count + 1 >= config.PENALTY_LOAN_INDEX,
        },
        "roundContrib": me.round_contrib,
    }


# --------------------------------------------------------------------------- #
# room block
# --------------------------------------------------------------------------- #

def _waiting_for(room) -> dict | None:
    """Who is blocking the table right now, if they are disconnected."""
    blockers = []
    if room.phase in config.BETTING_PHASES and room.turn_pid:
        blockers = [room.turn_pid]
    elif room.phase == config.PHASE_DISCARD:
        blockers = list(room.pending_discard)

    for pid in blockers:
        p = room.get(pid)
        if p and not p.connected:
            return {"pid": p.pid, "nickname": p.nickname,
                    "text": f"{p.nickname}님의 재접속을 기다리는 중..."}
    return None


def _room_view(room) -> dict:
    turn = room.get(room.turn_pid) if room.turn_pid else None
    dealer = room.get(room.dealer_pid) if room.dealer_pid else None
    try:
        phase_index = config.PHASE_FLOW.index(room.phase)
    except ValueError:
        phase_index = -1

    return {
        "code": room.code,
        "hostPid": room.host_pid,
        "phase": room.phase,
        "phaseLabel": config.PHASE_LABELS.get(room.phase, room.phase),
        "phaseIndex": phase_index,
        "roundNo": room.round_no,
        "started": room.started,
        "finished": room.phase == config.PHASE_FINISHED,
        "pot": room.pot,
        "potText": won(room.pot),
        "currentBet": room.current_bet,
        "currentBetText": won(room.current_bet),
        "raiseCount": room.raise_count,
        "maxRaises": config.MAX_RAISES,
        "turnPid": room.turn_pid,
        "turnNickname": turn.nickname if turn else None,
        "dealerPid": room.dealer_pid,
        "dealerNickname": dealer.nickname if dealer else None,
        "playerCount": room.size,
        "maxPlayers": config.MAX_PLAYERS,
        "minPlayers": config.MIN_PLAYERS,
        "canStart": room.size >= config.MIN_PLAYERS,
        "pendingDiscardCount": len(room.pending_discard),
        "waitingFor": _waiting_for(room),
        "notice": room.notice,
        "usedCharacters": sorted(room.used_characters()),
        "deckRemaining": room.deck.remaining if room.deck else config.DECK_SIZE,
        "discardCount": len(room.deck.discards) if room.deck else 0,
    }


# --------------------------------------------------------------------------- #
# public entry point
# --------------------------------------------------------------------------- #

def serialize_state_for_player(room, viewer_pid: str) -> dict:
    """Build a sanitized snapshot for exactly one viewer."""
    me = room.get(viewer_pid)
    state = {
        "room": _room_view(room),
        "players": [_player_view(room, p, viewer_pid) for p in room.player_list],
        "log": list(room.log),
        "ranking": engine.current_ranking(room),
        "result": _result_view(room),
        "final": room.final,
        "you": _you_view(room, me) if me else None,
    }
    return state


def _result_view(room):
    """The round result is already sanitized by the engine.

    Only players who reached showdown without folding appear in ``reveals``,
    and ``winners[].cards`` is populated only for a real showdown.
    """
    if not room.result:
        return None
    result = dict(room.result)
    if result.get("type") == "allFolded":
        result["winners"] = [
            {k: v for k, v in w.items() if k not in ("cards", "hand")}
            for w in result.get("winners", [])
        ]
        result["reveals"] = []
    return result


def lobby_summary(room) -> dict:
    """Tiny payload used by the join screen."""
    return {
        "code": room.code,
        "playerCount": room.size,
        "maxPlayers": config.MAX_PLAYERS,
        "started": room.started,
        "usedCharacters": sorted(room.used_characters()),
    }
