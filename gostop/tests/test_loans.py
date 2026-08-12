"""The playful virtual 대출 system."""

import pytest

from game import betting, config, engine
from game.errors import GameError

from tests.helpers import (finish_betting, finish_discards, make_table,
                           play_round, started_table)


# --------------------------------------------------------------------------- #
# the numbers
# --------------------------------------------------------------------------- #

def test_interest_maths():
    assert config.LOAN_AMOUNT == 100_000
    assert config.LOAN_INTEREST == 10_000
    assert config.LOAN_NET == 90_000
    assert config.LOAN_INTEREST == int(config.LOAN_AMOUNT * config.LOAN_INTEREST_RATE)
    assert config.LOAN_NET == config.LOAN_AMOUNT - config.LOAN_INTEREST


def test_first_loan_pays_ninety_thousand_with_no_penalty():
    _m, room, players = make_table(2)
    player = players[0]
    before = player.chips

    info = player.take_loan()

    assert player.chips == before + 90_000
    assert player.loan_count == 1
    assert player.automatic_last_place is False
    assert info == {"amount": 100_000, "interest": 10_000, "net": 90_000,
                    "loanCount": 1, "autoLast": False}


def test_second_loan_pays_out_but_locks_in_last_place():
    _m, room, players = make_table(2)
    player = players[0]
    player.take_loan()
    before = player.chips

    info = player.take_loan()

    assert player.chips == before + 90_000
    assert player.loan_count == 2
    assert player.automatic_last_place is True
    assert info["autoLast"] is True


def test_third_loan_is_refused():
    _m, room, players = make_table(2)
    player = players[0]
    player.take_loan()
    player.take_loan()
    assert player.can_loan is False

    allowed, reason = engine.loan_availability(room, player)
    assert allowed is False
    assert "2번" in reason
    with pytest.raises(GameError) as exc:
        engine.take_loan(room, player)
    assert "2번" in str(exc.value)


# --------------------------------------------------------------------------- #
# when a loan is offered
# --------------------------------------------------------------------------- #

def test_loan_is_available_in_the_lobby():
    _m, room, players = make_table(2)
    allowed, _reason = engine.loan_availability(room, players[0])
    assert allowed is True


def test_loan_is_available_between_rounds():
    _m, room, players = started_table(3)
    play_round(room)
    assert room.phase == config.PHASE_ROUND_END
    allowed, _reason = engine.loan_availability(room, players[0])
    assert allowed is True


def test_loan_is_refused_when_the_player_is_flush():
    _m, room, _p = started_table(3)
    actor = room.get(room.turn_pid)
    allowed, reason = engine.loan_availability(room, actor)
    assert allowed is False
    assert "넉넉" in reason


def test_loan_is_offered_when_the_call_is_unaffordable():
    _m, room, _p = started_table(3)
    engine.bet_action(room, room.get(room.turn_pid), betting.ACTION_BET)
    broke = room.get(room.turn_pid)
    broke.chips = 500

    allowed, _reason = engine.loan_availability(room, broke)
    assert allowed is True

    engine.take_loan(room, broke)
    assert broke.chips == 90_500
    # ...and now the call button is live again
    entry = {a["type"]: a for a in betting.legal_actions(room, broke)}["call"]
    assert entry["enabled"] is True


def test_loan_is_refused_during_showdown():
    _m, room, players = started_table(2)
    finish_betting(room)
    finish_discards(room)
    room.phase = config.PHASE_SHOWDOWN
    players[0].chips = 0
    allowed, reason = engine.loan_availability(room, players[0])
    assert allowed is False
    assert reason


def test_spectating_player_may_stock_up_and_rejoins_next_round():
    _m, room, players = started_table(3)
    play_round(room)
    broke = players[1]
    broke.chips = 0
    engine.next_round(room, players[0])
    assert broke.spectating is True

    allowed, _reason = engine.loan_availability(room, broke)
    assert allowed is True
    engine.take_loan(room, broke)
    assert broke.chips == 90_000

    play_round(room)
    engine.next_round(room, players[0])
    assert broke.spectating is False
    assert broke.in_round is True
    assert len(broke.cards) == 2


def test_loan_is_written_into_the_korean_game_log():
    _m, room, players = started_table(3)
    play_round(room)
    engine.take_loan(room, players[0])
    text = " ".join(entry["text"] for entry in room.log)
    assert "은행(?)" in text
    assert "90,000" in text
    assert "대출 1/2" in text


def test_second_loan_log_warns_about_last_place():
    _m, room, players = started_table(3)
    play_round(room)
    engine.take_loan(room, players[0])
    engine.take_loan(room, players[0])
    text = " ".join(entry["text"] for entry in room.log)
    assert "최하위" in text


# --------------------------------------------------------------------------- #
# effect on the final table
# --------------------------------------------------------------------------- #

def test_two_loan_player_is_pushed_into_the_last_group():
    _m, room, players = make_table(3)
    borrower, clean_a, clean_b = players
    borrower.take_loan()
    borrower.take_loan()
    borrower.chips = 10_000_000
    clean_a.chips = 100
    clean_b.chips = 50

    standings = engine.final_standings(room)
    assert [s["nickname"] for s in standings] == [
        clean_a.nickname, clean_b.nickname, borrower.nickname
    ]
    last = standings[-1]
    assert last["autoLast"] is True
    assert last["loanCount"] == 2
    assert "최하위" in last["penalty"]


def test_one_loan_player_keeps_a_normal_rank():
    _m, room, players = make_table(3)
    borrower = players[0]
    borrower.take_loan()
    borrower.chips = 500_000
    players[1].chips = 100
    players[2].chips = 50

    standings = engine.final_standings(room)
    assert standings[0]["nickname"] == borrower.nickname
    assert standings[0]["autoLast"] is False
    assert standings[0]["penalty"] == ""
    assert standings[0]["loanCount"] == 1


def test_serialized_loan_block_matches_config():
    from game.serializers import serialize_state_for_player
    _m, room, players = make_table(2)
    state = serialize_state_for_player(room, players[0].pid)
    loan = state["you"]["loan"]
    assert loan["amount"] == 100_000
    assert loan["interest"] == 10_000
    assert loan["net"] == 90_000
    assert loan["max"] == 2
    assert loan["count"] == 0
    assert loan["nextIsPenalty"] is False

    players[0].take_loan()
    state = serialize_state_for_player(room, players[0].pid)
    assert state["you"]["loan"]["nextIsPenalty"] is True
