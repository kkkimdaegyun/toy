"""Round state machine.

    참가비 → 카드 2장 → 1차 베팅 → 카드 1장 추가 → 3장 중 1장 버리기
          → 2차 베팅 → 카드 공개 → 승자 결정 → 판돈 지급 → 결과 → 다음 판

The engine is deliberately transport-agnostic.  Timed transitions (so players
can actually watch the cards fly) go through ``room.hooks``:

    hooks.later(delay_seconds, fn)  -> schedule
    hooks.notify(room)              -> broadcast state to everybody

:class:`InstantHooks` (the default) runs ``later`` synchronously, which makes
the whole machine trivially testable.
"""

from __future__ import annotations

import random

from . import betting, config, errors
from .deck import Deck
from .errors import GameError
from .hands import evaluate
from .utils import josa, name_with, won

# --------------------------------------------------------------------------- #
# hooks
# --------------------------------------------------------------------------- #


class InstantHooks:
    """Default: no delays, no broadcasting.  Used by the tests."""

    def later(self, delay, fn):
        fn()

    def notify(self, room):
        pass


def _hooks(room):
    return room.hooks or InstantHooks()


def _later(room, delay, fn):
    """Schedule a delayed transition and broadcast the current state first."""
    _hooks(room).notify(room)
    _hooks(room).later(delay, fn)


# --------------------------------------------------------------------------- #
# game / round lifecycle
# --------------------------------------------------------------------------- #

def start_game(room, player) -> None:
    if room.host_pid != player.pid:
        raise GameError(errors.NOT_HOST, "not_host")
    if room.started and room.phase != config.PHASE_FINISHED:
        raise GameError(errors.GAME_ALREADY_STARTED, "started")
    if room.size < config.MIN_PLAYERS:
        raise GameError(errors.NOT_ENOUGH_PLAYERS, "too_few")

    room.started = True
    room.final = None
    room.round_no = 0
    room.log.clear()
    room.log_line("게임이 시작되었습니다.")
    room.dealer_pid = random.choice(room.seats)
    start_round(room, rotate_dealer=False)


def next_round(room, player) -> None:
    if room.host_pid != player.pid:
        raise GameError(errors.NOT_HOST, "not_host")
    if room.phase not in (config.PHASE_ROUND_END, config.PHASE_LOBBY):
        raise GameError("아직 다음 판을 시작할 수 없습니다.", "phase")
    if room.size < config.MIN_PLAYERS:
        raise GameError(errors.NOT_ENOUGH_PLAYERS, "too_few")
    start_round(room, rotate_dealer=True)


def start_round(room, rotate_dealer: bool = True) -> None:
    if rotate_dealer:
        room.dealer_pid = _next_dealer(room)
    if room.dealer_pid not in room.players:
        room.dealer_pid = room.seats[0] if room.seats else None

    room.round_no += 1
    room.result = None
    room.notice = None
    room.pot = 0
    room.current_bet = 0
    room.raise_count = 0
    room.turn_pid = None
    room.turn_seat = -1
    room.needs_action = set()
    room.pending_discard = set()
    room.deck = Deck()
    for p in room.player_list:
        p.reset_for_round()

    room.phase = config.PHASE_ANTE
    room.log_line(f"── {room.round_no}번째 판 ──")
    dealer = room.get(room.dealer_pid)
    if dealer:
        room.log_line(f"{name_with(dealer.nickname, '이', '가')} 선입니다.")

    funded = [p for p in room.player_list if p.chips >= config.ANTE]
    if len(funded) < config.MIN_PLAYERS:
        room.phase = config.PHASE_ROUND_END
        room.result = {
            "type": "noGame",
            "pot": 0,
            "winners": [],
            "reveals": [],
            "headline": "이번 판은 시작할 수 없어요",
            "explain": (
                "참가비를 낼 수 있는 사람이 2명보다 적습니다. "
                "은행(?) 찬스로 칩을 채우거나 게임을 종료해주세요."
            ),
            "tie": False,
        }
        room.log_line("참가비를 낼 수 있는 사람이 부족해 판을 시작하지 못했습니다.")
        _hooks(room).notify(room)
        return

    ante_fx = []
    for p in room.player_list:
        if p.chips >= config.ANTE:
            p.in_round = True
            p.spectating = False
            paid = p.pay(config.ANTE)
            room.pot += paid
            p.status_key = "wait"
            ante_fx.append({"pid": p.pid, "amount": paid})
        else:
            p.in_round = False
            p.spectating = True
            p.status_key = "spectating"

    room.push_fx("ante", players=ante_fx, pot=room.pot)
    room.log_line(
        f"참가비 {won(config.ANTE)}씩 모아 판돈 {won(room.pot)}으로 시작합니다."
    )
    _later(room, 0.75, lambda: _deal_two(room))


def _next_dealer(room):
    if not room.seats:
        return None
    if room.dealer_pid not in room.players:
        return room.seats[0]
    seat = room.seat_of(room.dealer_pid)
    return room.seats[(seat + 1) % len(room.seats)]


def _deal_two(room) -> None:
    if room.phase != config.PHASE_ANTE:
        return
    room.phase = config.PHASE_DEAL2
    order = [pid for pid in room.seat_order_from(room.seat_of(room.dealer_pid))
             if room.players[pid].in_round]
    fx_cards = []
    for round_idx in range(config.CARDS_FIRST_DEAL):
        for pid in order:
            p = room.players[pid]
            card = room.deck.draw()
            p.cards.append(card)
            fx_cards.append({"pid": pid, "cardId": card.id, "index": round_idx})
    room.push_fx("deal", stage=1, cards=fx_cards)
    room.log_line("카드 2장씩 나눠줍니다.")
    _later(room, 0.30 + 0.12 * len(fx_cards), lambda: _begin_bet(room, config.PHASE_BET1))


def _begin_bet(room, phase: str) -> None:
    expected = config.PHASE_DEAL2 if phase == config.PHASE_BET1 else config.PHASE_DISCARD
    if room.phase not in (expected, phase):
        return
    if _maybe_finish_by_folds(room):
        return
    room.phase = phase
    betting.start_phase(room)
    room.log_line("1차 베팅을 시작합니다." if phase == config.PHASE_BET1
                  else "2차 베팅을 시작합니다.")
    if betting.is_complete(room):
        _after_betting(room, phase)
    else:
        _hooks(room).notify(room)


def _deal_third(room) -> None:
    if room.phase != config.PHASE_BET1:
        return
    room.phase = config.PHASE_DEAL3
    room.turn_pid = None
    fx_cards = []
    order = [pid for pid in room.seat_order_from(room.seat_of(room.dealer_pid))
             if room.players[pid].active]
    for pid in order:
        p = room.players[pid]
        card = room.deck.draw()
        p.cards.append(card)
        fx_cards.append({"pid": pid, "cardId": card.id, "index": 2})
    room.push_fx("deal", stage=2, cards=fx_cards)
    room.log_line("세 번째 카드를 나눠줍니다.")
    _later(room, 0.30 + 0.12 * len(fx_cards), lambda: _begin_discard(room))


def _begin_discard(room) -> None:
    if room.phase != config.PHASE_DEAL3:
        return
    if _maybe_finish_by_folds(room):
        return
    room.phase = config.PHASE_DISCARD
    room.pending_discard = {p.pid for p in room.active_players}
    for p in room.active_players:
        p.status_key = "discarding"
    room.log_line("3장 중 1장을 버릴 차례입니다.")
    if not room.pending_discard:
        _begin_bet(room, config.PHASE_BET2)
    else:
        _hooks(room).notify(room)


def _after_betting(room, phase: str) -> None:
    """A betting phase just finished cleanly."""
    if _maybe_finish_by_folds(room):
        return
    if phase == config.PHASE_BET1:
        _later(room, 0.5, lambda: _deal_third(room))
    else:
        _later(room, 0.4, lambda: _showdown(room))


def _showdown(room) -> None:
    if room.phase != config.PHASE_BET2:
        return
    if _maybe_finish_by_folds(room):
        return
    room.phase = config.PHASE_SHOWDOWN
    room.turn_pid = None
    for p in room.active_players:
        p.hand = evaluate(p.cards)
        p.revealed = True
    room.push_fx("reveal", pids=[p.pid for p in room.active_players])
    room.log_line("카드 공개!")
    _later(room, 1.5, lambda: _resolve(room))


def _resolve(room) -> None:
    if room.phase != config.PHASE_SHOWDOWN:
        return
    contenders = [p for p in room.active_players if p.hand is not None]
    if not contenders:
        _finish_round(room, [], all_folded=True)
        return

    top = max(p.hand.score for p in contenders)
    winners = [p for p in contenders if p.hand.score == top]
    _finish_round(room, winners, all_folded=False)


def _maybe_finish_by_folds(room) -> bool:
    """If everybody but one has said 다이, end the round right now."""
    if room.phase in (config.PHASE_ROUND_END, config.PHASE_FINISHED,
                      config.PHASE_LOBBY):
        return False
    active = room.active_players
    if len(active) <= 1:
        _finish_round(room, active, all_folded=True)
        return True
    return False


def _finish_round(room, winners, all_folded: bool) -> None:
    pot = room.pot
    room.turn_pid = None
    room.needs_action = set()
    room.pending_discard = set()

    if not winners:
        # Degenerate case (everybody left the table): give the chips back
        # rather than making them disappear.
        for p in room.round_players:
            p.chips += p.round_contrib
        room.pot = 0
        room.result = {
            "type": "noGame", "pot": pot, "winners": [], "reveals": [],
            "headline": "이번 판은 무효입니다",
            "explain": "참가자가 남지 않아 참가비를 모두 돌려드렸습니다.",
            "tie": False,
        }
        room.phase = config.PHASE_ROUND_END
        room.log_line("참가자가 남지 않아 이번 판은 무효 처리되었습니다.")
        _hooks(room).notify(room)
        return

    payouts = _split_pot(room, winners, pot)
    for p in winners:
        p.chips += payouts.get(p.pid, 0)
        p.status_key = "winner"
        p.rounds_won += 1
    room.pot = 0

    winner_rows = []
    for p in winners:
        winner_rows.append({
            "pid": p.pid,
            "nickname": p.nickname,
            "character": p.character,
            "amount": payouts.get(p.pid, 0),
            "hand": p.hand.to_dict() if (p.hand and not all_folded) else None,
            "cards": ([c.private() for c in p.cards]
                      if (p.hand and not all_folded) else None),
        })

    reveals = []
    if not all_folded:
        ranked = sorted(
            [p for p in room.active_players if p.hand],
            key=lambda x: x.hand.score, reverse=True,
        )
        for p in ranked:
            reveals.append({
                "pid": p.pid,
                "nickname": p.nickname,
                "character": p.character,
                "cards": [c.private() for c in p.cards],
                "hand": p.hand.to_dict(),
                "winner": p in winners,
            })

    headline, explain = _explain_result(room, winners, reveals, pot, all_folded)

    room.result = {
        "type": "allFolded" if all_folded else "showdown",
        "pot": pot,
        "winners": winner_rows,
        "reveals": reveals,
        "headline": headline,
        "explain": explain,
        "tie": len(winners) > 1,
    }
    room.phase = config.PHASE_ROUND_END
    room.push_fx("winner", pids=[p.pid for p in winners], pot=pot,
                 allFolded=all_folded)

    if all_folded and winners:
        room.log_line("모두 다이했습니다!")
    for row in winner_rows:
        who = name_with(row["nickname"], "이", "가")
        if row["hand"]:
            room.log_line(f"{row['nickname']}님 - {row['hand']['name']}")
        room.log_line(f"{who} {won(row['amount'])} 칩을 획득했습니다.")

    _hooks(room).notify(room)


def _split_pot(room, winners, pot: int) -> dict:
    """Even split; the remainder goes clockwise starting from 선."""
    if not winners or pot <= 0:
        return {}
    share = pot // len(winners)
    rest = pot - share * len(winners)
    payouts = {p.pid: share for p in winners}
    if rest:
        dealer_seat = room.seat_of(room.dealer_pid)
        if dealer_seat < 0:
            dealer_seat = 0
        order = [pid for pid in room.seat_order_from(dealer_seat)
                 if pid in payouts]
        for i in range(rest):
            payouts[order[i % len(order)]] += 1
    return payouts


def _explain_result(room, winners, reveals, pot, all_folded):
    if not winners:
        return "이번 판은 무승부입니다", "판돈이 그대로 남았습니다."

    names = " / ".join(p.nickname for p in winners)

    if all_folded:
        return (
            f"{names}님 승리!",
            f"다른 분들이 모두 다이했습니다. {name_with(names, '이', '가')} "
            f"판돈 {won(pot)}을 그대로 가져갑니다. 카드는 공개하지 않아요!",
        )

    top = winners[0]
    hand_name = top.hand.name if top.hand else ""
    if len(winners) > 1:
        return (
            f"{names}님 공동 승리!",
            f"똑같이 {hand_name}이라서 판돈 {won(pot)}을 나눠 가집니다.",
        )

    parts = [top.hand.explain] if top.hand else []
    runner = next((r for r in reveals if not r["winner"]), None)
    if runner:
        subject = josa(hand_name, "은", "는")
        parts.append(f"{subject} {runner['hand']['name']}보다 높은 족보입니다.")
    amount = pot
    parts.append(f"획득: +{won(amount)} 칩")
    return f"{top.nickname}님 승리!", " ".join(parts)


# --------------------------------------------------------------------------- #
# player actions
# --------------------------------------------------------------------------- #

def bet_action(room, player, action_type: str) -> dict:
    """체크 / 베팅 / 콜 / 레이즈.  다이 goes through :func:`fold`."""
    if action_type == betting.ACTION_DIE:
        return fold(room, player)

    info = betting.apply_bet_action(room, player, action_type)
    room.log_line(betting.describe_action(player, info))
    room.push_fx("bet", pid=player.pid, action=action_type,
                 amount=info["paid"], pot=room.pot)
    room.touch()

    phase = room.phase
    complete = betting.advance_turn(room)
    if _maybe_finish_by_folds(room):
        return info
    if complete:
        _after_betting(room, phase)
    else:
        _hooks(room).notify(room)
    return info


def fold(room, player) -> dict:
    """다이 — allowed out of turn, and during the discard phase.

    Contributed chips stay in the pot, cards are never revealed.
    """
    if room.phase not in config.DAI_ALLOWED_PHASES:
        raise GameError(errors.CANNOT_BET_NOW, "phase")
    if not player.in_round:
        raise GameError(errors.NOT_IN_ROUND, "not_in_round")
    if player.folded:
        raise GameError(errors.ALREADY_FOLDED, "folded")

    was_turn = room.turn_pid == player.pid
    player.folded = True
    player.status_key = "die"
    player.last_action = betting.ACTION_DIE
    betting.drop_from_action(room, player)

    room.push_fx("die", pid=player.pid, wasTurn=was_turn)
    early = room.phase in (config.PHASE_DEAL2, config.PHASE_DEAL3) or not was_turn
    who = name_with(player.nickname, "이", "가")
    room.log_line(f"{who} {'바로 ' if early else ''}다이했습니다.")
    room.touch()

    if _maybe_finish_by_folds(room):
        return {"action": "die"}

    phase = room.phase
    if phase in config.BETTING_PHASES:
        # Only re-run the cursor when the folder WAS the current actor.
        # Otherwise turn_pid is still a valid pending player and advancing
        # would wrongly skip them.
        if room.turn_pid is None:
            complete = betting.advance_turn(room)
        else:
            complete = False
        if complete:
            _after_betting(room, phase)
        else:
            _hooks(room).notify(room)
    elif phase == config.PHASE_DISCARD:
        if not room.pending_discard:
            _begin_bet(room, config.PHASE_BET2)
        else:
            _hooks(room).notify(room)
    else:
        _hooks(room).notify(room)
    return {"action": "die"}


def discard(room, player, card_id: str) -> dict:
    if room.phase != config.PHASE_DISCARD:
        raise GameError(errors.CANNOT_DISCARD_NOW, "phase")
    if not player.active:
        raise GameError(errors.NOT_IN_ROUND, "not_in_round")
    if player.pid not in room.pending_discard:
        raise GameError("이미 카드를 선택했습니다.", "already")
    card = next((c for c in player.cards if c.id == card_id), None)
    if card is None:
        raise GameError(errors.CARD_NOT_YOURS, "bad_card")
    if len(player.cards) != 3:
        raise GameError(errors.CANNOT_DISCARD_NOW, "bad_state")

    player.cards = [c for c in player.cards if c.id != card_id]
    player.discarded = card
    room.deck.discard(card)
    player.hand = evaluate(player.cards)
    player.status_key = "discarded"
    room.pending_discard.discard(player.pid)

    room.push_fx("discard", pid=player.pid, cardId=card.id)
    room.log_line(f"{name_with(player.nickname, '이', '가')} 카드 선택을 완료했습니다.")
    room.touch()

    if not room.pending_discard:
        _later(room, 0.5, lambda: _begin_bet(room, config.PHASE_BET2))
    else:
        _hooks(room).notify(room)
    return {"discarded": card.id}


# --------------------------------------------------------------------------- #
# loans
# --------------------------------------------------------------------------- #

def loan_availability(room, player) -> tuple:
    """(allowed: bool, reason: str)"""
    if not player.can_loan:
        return False, errors.LOAN_MAX
    if room.phase in (config.PHASE_LOBBY, config.PHASE_ROUND_END):
        return True, ""
    if room.phase in (config.PHASE_SHOWDOWN, config.PHASE_FINISHED,
                      config.PHASE_ANTE):
        return False, errors.LOAN_NOT_NOW
    if not player.in_round or player.folded:
        return True, ""
    if room.phase in config.BETTING_PHASES:
        need = betting.to_call(room, player) or config.BET_AMOUNT
        if player.chips < need:
            return True, ""
        return False, "지금은 칩이 넉넉해서 대출이 필요하지 않아요."
    if room.phase in (config.PHASE_DEAL2, config.PHASE_DEAL3, config.PHASE_DISCARD):
        if player.chips < config.BASE_UNIT:
            return True, ""
        return False, "지금은 칩이 넉넉해서 대출이 필요하지 않아요."
    return False, errors.LOAN_NOT_NOW


def take_loan(room, player) -> dict:
    allowed, reason = loan_availability(room, player)
    if not allowed:
        raise GameError(reason or errors.LOAN_NOT_NOW, "loan")
    info = player.take_loan()
    room.push_fx("loan", pid=player.pid, net=info["net"],
                 loanCount=info["loanCount"])
    room.log_line(
        f"{name_with(player.nickname, '이', '가')} 은행(?) 찬스로 "
        f"{won(info['net'])} 칩을 받았습니다. (대출 {info['loanCount']}/{config.MAX_LOANS})"
    )
    if info["autoLast"]:
        room.log_line(f"{player.nickname}님은 최종 순위에서 최하위 그룹으로 들어갑니다.")
    room.touch()
    _hooks(room).notify(room)
    return info


# --------------------------------------------------------------------------- #
# leaving / disconnect handling
# --------------------------------------------------------------------------- #

def force_fold(room, player, reason: str = "자리 비움") -> None:
    """Used when a disconnected player is blocking the table."""
    if not player.active or room.phase not in config.DAI_ALLOWED_PHASES:
        return
    try:
        fold(room, player)
    except GameError:
        return
    room.log_line(f"{player.nickname}님이 {reason}으로 이번 판 다이 처리되었습니다.")


def handle_player_removed(room, player) -> None:
    """A player fully left the room mid-round."""
    if player.active and room.phase in config.DAI_ALLOWED_PHASES:
        player.folded = True
        betting.drop_from_action(room, player)
        room.log_line(f"{player.nickname}님이 방을 나갔습니다.")
        if _maybe_finish_by_folds(room):
            return
        phase = room.phase
        if phase in config.BETTING_PHASES and room.turn_pid is None:
            if betting.advance_turn(room):
                _after_betting(room, phase)
        elif phase == config.PHASE_DISCARD and not room.pending_discard:
            _begin_bet(room, config.PHASE_BET2)
    else:
        room.log_line(f"{player.nickname}님이 방을 나갔습니다.")


# --------------------------------------------------------------------------- #
# end of session
# --------------------------------------------------------------------------- #

def end_game(room, player) -> None:
    if room.host_pid != player.pid:
        raise GameError(errors.NOT_HOST, "not_host")
    room.phase = config.PHASE_FINISHED
    room.turn_pid = None
    room.needs_action = set()
    room.pending_discard = set()
    room.pot = 0
    room.final = {"standings": final_standings(room)}
    room.log_line("게임이 종료되었습니다.")
    _hooks(room).notify(room)


def final_standings(room) -> list:
    """Normal players by chips desc, then the 2-loan crowd, also by chips."""
    normal = [p for p in room.player_list if not p.automatic_last_place]
    penalised = [p for p in room.player_list if p.automatic_last_place]
    normal.sort(key=lambda p: (-p.chips, p.seat))
    penalised.sort(key=lambda p: (-p.chips, p.seat))

    rows = []
    for i, p in enumerate(normal + penalised, start=1):
        rows.append({
            "rank": i,
            "pid": p.pid,
            "nickname": p.nickname,
            "character": p.character,
            "chips": p.chips,
            "loanCount": p.loan_count,
            "autoLast": p.automatic_last_place,
            "roundsWon": p.rounds_won,
            "penalty": "두 번째 대출로 최하위 그룹" if p.automatic_last_place else "",
        })
    return rows


def current_ranking(room) -> list:
    rows = sorted(room.player_list, key=lambda p: (-p.chips, p.seat))
    return [{
        "rank": i,
        "pid": p.pid,
        "nickname": p.nickname,
        "character": p.character,
        "chips": p.chips,
        "loanCount": p.loan_count,
        "autoLast": p.automatic_last_place,
    } for i, p in enumerate(rows, start=1)]
