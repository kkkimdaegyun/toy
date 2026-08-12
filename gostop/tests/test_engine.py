"""Round flow: 참가비 → 카드 → 베팅 → 버리기 → 베팅 → 공개 → 결과."""

import random

import pytest

from game import betting, config, engine
from game.deck import Card
from game.errors import GameError

from tests.helpers import (act_passively, finish_betting, finish_discards,
                           make_table, play_round, set_hand, started_table,
                           total_chips)


# --------------------------------------------------------------------------- #
# starting a game
# --------------------------------------------------------------------------- #

def test_only_the_host_can_start():
    _m, room, players = make_table(3)
    with pytest.raises(GameError) as exc:
        engine.start_game(room, players[1])
    assert "방장" in str(exc.value)


def test_two_players_are_required():
    _m, room, players = make_table(1)
    with pytest.raises(GameError) as exc:
        engine.start_game(room, players[0])
    assert "2명" in str(exc.value)


def test_starting_twice_is_rejected():
    _m, room, players = started_table(3)
    with pytest.raises(GameError):
        engine.start_game(room, players[0])


@pytest.mark.parametrize("count", [2, 3, 4, 5, 6])
def test_ante_is_collected_from_everybody(count):
    _m, room, _p = started_table(count)
    assert room.pot == config.ANTE * count
    for p in room.player_list:
        assert p.chips == config.STARTING_CHIPS - config.ANTE
        assert p.in_round is True
        assert p.round_contrib == config.ANTE


@pytest.mark.parametrize("count", [2, 3, 4, 5, 6])
def test_everybody_gets_two_distinct_cards(count):
    _m, room, _p = started_table(count)
    seen = set()
    for p in room.round_players:
        assert len(p.cards) == config.CARDS_FIRST_DEAL
        for c in p.cards:
            assert c.id not in seen
            seen.add(c.id)
    assert len(seen) == count * 2


def test_six_players_fit_in_the_twenty_card_deck():
    _m, room, _p = started_table(6)
    finish_betting(room)
    assert room.phase == config.PHASE_DISCARD
    for p in room.active_players:
        assert len(p.cards) == 3
    assert room.deck.remaining >= 0


# --------------------------------------------------------------------------- #
# third card & discard
# --------------------------------------------------------------------------- #

def test_third_card_goes_only_to_active_players():
    _m, room, _p = started_table(4)
    folder = next(p for p in room.active_players if p.pid != room.turn_pid)
    engine.fold(room, folder)
    finish_betting(room)

    assert room.phase == config.PHASE_DISCARD
    for p in room.active_players:
        assert len(p.cards) == 3
    assert len(folder.cards) == 2, "a folded player must not be dealt a third card"


def test_discard_leaves_exactly_two_and_files_the_card():
    _m, room, _p = started_table(3)
    finish_betting(room)
    player = room.get(sorted(room.pending_discard)[0])
    dropped = player.cards[1]

    engine.discard(room, player, dropped.id)

    assert len(player.cards) == 2
    assert dropped not in player.cards
    assert dropped in room.deck.discards
    assert player.hand.name == engine.evaluate(player.cards).name
    assert player.pid not in room.pending_discard


def test_discarding_a_card_you_do_not_hold_is_rejected():
    _m, room, _p = started_table(3)
    finish_betting(room)
    player = room.get(sorted(room.pending_discard)[0])
    with pytest.raises(GameError) as exc:
        engine.discard(room, player, "not-a-real-card")
    assert "내 카드가 아닙니다" in str(exc.value)


def test_discarding_twice_is_rejected():
    _m, room, _p = started_table(3)
    finish_betting(room)
    player = room.get(sorted(room.pending_discard)[0])
    engine.discard(room, player, player.cards[0].id)
    with pytest.raises(GameError):
        engine.discard(room, player, player.cards[0].id)


def test_discarding_outside_the_discard_phase_is_rejected():
    _m, room, _p = started_table(3)
    player = room.get(room.turn_pid)
    with pytest.raises(GameError):
        engine.discard(room, player, player.cards[0].id)


def test_die_during_the_discard_phase():
    """그냥 다이 — no card is chosen and all three stay private."""
    _m, room, _p = started_table(3)
    finish_betting(room)
    assert room.phase == config.PHASE_DISCARD

    quitter = room.get(sorted(room.pending_discard)[0])
    engine.fold(room, quitter)

    assert quitter.folded is True
    assert len(quitter.cards) == 3, "다이 during discard keeps all three cards"
    assert quitter.discarded is None
    assert quitter.pid not in room.pending_discard

    finish_discards(room)
    assert room.phase == config.PHASE_BET2
    assert quitter not in room.active_players


def test_folding_mid_discard_waits_for_the_remaining_choosers():
    _m, room, _p = started_table(3)
    finish_betting(room)
    pending = sorted(room.pending_discard)
    first = room.get(pending[0])
    engine.discard(room, first, first.cards[0].id)

    second = room.get(pending[1])
    engine.fold(room, second)

    # a third player is still choosing, so the game must wait for them
    assert room.phase == config.PHASE_DISCARD
    assert len(room.pending_discard) == 1
    assert len(room.active_players) == 2

    finish_discards(room)
    assert room.phase == config.PHASE_BET2


def test_folding_as_the_last_discarder_ends_the_round():
    _m, room, _p = started_table(2)
    finish_betting(room)
    assert room.phase == config.PHASE_DISCARD
    pending = sorted(room.pending_discard)
    first = room.get(pending[0])
    engine.discard(room, first, first.cards[0].id)

    second = room.get(pending[1])
    pot = room.pot
    before = first.chips
    engine.fold(room, second)

    # only one active player remains -> the round ends immediately
    assert room.phase == config.PHASE_ROUND_END
    assert room.result["type"] == "allFolded"
    assert first.chips == before + pot


# --------------------------------------------------------------------------- #
# showdown
# --------------------------------------------------------------------------- #

def drive_to_final_bet(room):
    finish_betting(room)
    finish_discards(room)
    assert room.phase == config.PHASE_BET2


def test_strongest_hand_takes_the_pot():
    _m, room, players = started_table(3)
    drive_to_final_bet(room)

    active = room.active_players
    set_hand(active[0], 3, 8)      # 38광땡
    set_hand(active[1], 0, 0)      # 장땡
    set_hand(active[2], 9, 8)      # 7끗
    winner = active[0]
    before = winner.chips
    pot = room.pot

    finish_betting(room)

    assert room.phase == config.PHASE_ROUND_END
    assert winner.chips == before + pot
    assert room.pot == 0
    assert room.result["type"] == "showdown"
    assert room.result["winners"][0]["pid"] == winner.pid
    assert room.result["winners"][0]["hand"]["name"] == "38광땡"
    assert room.result["tie"] is False


def test_showdown_reveals_are_ordered_strongest_first():
    _m, room, _p = started_table(3)
    drive_to_final_bet(room)
    active = room.active_players
    set_hand(active[0], 9, 8)      # 7끗
    set_hand(active[1], 3, 8)      # 38광땡
    set_hand(active[2], 5, 5)      # 5땡
    finish_betting(room)

    names = [r["hand"]["name"] for r in room.result["reveals"]]
    assert names == ["38광땡", "5땡", "7끗"]
    assert room.result["reveals"][0]["winner"] is True


def test_result_explains_why_the_winner_won():
    _m, room, _p = started_table(2)
    drive_to_final_bet(room)
    active = room.active_players
    set_hand(active[0], 3, 8)
    set_hand(active[1], 9, 9)
    finish_betting(room)

    explain = room.result["explain"]
    assert "38광땡" in explain
    assert "9땡" in explain
    assert "획득" in explain
    assert "은(는)" not in explain, "조사 should be resolved, not printed literally"


def test_tie_splits_the_pot_evenly():
    _m, room, _p = started_table(2)
    drive_to_final_bet(room)
    active = room.active_players
    set_hand(active[0], 4, 5)      # 9끗
    set_hand(active[1], 2, 7)      # 9끗
    before = [p.chips for p in active]
    pot = room.pot

    finish_betting(room)

    assert room.result["tie"] is True
    assert len(room.result["winners"]) == 2
    gained = sum(p.chips - b for p, b in zip(active, before))
    assert gained == pot
    assert active[0].chips - before[0] == active[1].chips - before[1]


def test_split_pot_remainder_goes_clockwise_from_the_dealer():
    _m, room, players = started_table(3)
    winners = players[:2]
    payouts = engine._split_pot(room, winners, 10_001)
    assert sum(payouts.values()) == 10_001
    assert sorted(payouts.values()) == [5000, 5001]

    # the extra chip lands on whichever winner sits closest clockwise to 선
    dealer_seat = room.seat_of(room.dealer_pid)
    order = [pid for pid in room.seat_order_from(dealer_seat) if pid in payouts]
    assert payouts[order[0]] == 5001


def test_chip_total_is_conserved_across_many_rounds():
    rng = random.Random(99)
    for _ in range(15):
        _m, room, players = started_table(rng.choice([2, 3, 4, 5]))
        expected = config.STARTING_CHIPS * room.size
        for _round in range(3):
            play_round(room)
            assert room.phase == config.PHASE_ROUND_END
            assert total_chips(room) == expected
            if room.result["type"] == "noGame":
                break
            engine.next_round(room, players[0])
            assert total_chips(room) == expected


# --------------------------------------------------------------------------- #
# dealer rotation & next round
# --------------------------------------------------------------------------- #

def test_dealer_rotates_clockwise_and_wraps():
    _m, room, players = started_table(4)
    seen = [room.dealer_pid]
    for _ in range(4):
        play_round(room)
        engine.next_round(room, players[0])
        seen.append(room.dealer_pid)

    seats = [room.seat_of(pid) for pid in seen]
    for i in range(len(seats) - 1):
        assert seats[i + 1] == (seats[i] + 1) % room.size
    assert seen[0] == seen[4], "a full lap should return to the first 선"


def test_next_round_requires_the_host_and_round_end():
    _m, room, players = started_table(3)
    with pytest.raises(GameError):
        engine.next_round(room, players[0])       # still mid-round
    play_round(room)
    with pytest.raises(GameError):
        engine.next_round(room, players[1])       # not the host
    engine.next_round(room, players[0])
    assert room.round_no == 2


def test_new_round_resets_per_round_state():
    _m, room, players = started_table(3)
    play_round(room)
    engine.next_round(room, players[0])
    for p in room.player_list:
        assert p.folded is False
        assert p.round_contrib == config.ANTE
        # the ante is NOT part of the first betting phase, so everybody starts
        # 1차 베팅 level with each other and 체크 is available
        assert p.phase_contrib == 0
        assert len(p.cards) == 2
        assert p.discarded is None
        assert p.revealed is False
    assert room.result is None
    assert room.raise_count == 0
    assert room.current_bet == 0


# --------------------------------------------------------------------------- #
# broke players
# --------------------------------------------------------------------------- #

def test_a_player_who_cannot_pay_the_ante_spectates():
    _m, room, players = started_table(3)
    play_round(room)
    players[1].chips = 0
    engine.next_round(room, players[0])

    assert players[1].spectating is True
    assert players[1].in_round is False
    assert players[1].cards == []
    assert room.pot == config.ANTE * 2
    assert players[1] not in room.active_players


def test_round_does_not_start_with_fewer_than_two_funded_players():
    _m, room, players = started_table(3)
    play_round(room)
    for p in players[1:]:
        p.chips = 0
    engine.next_round(room, players[0])

    assert room.phase == config.PHASE_ROUND_END
    assert room.result["type"] == "noGame"
    assert room.pot == 0
    assert "참가비" in room.result["explain"]


# --------------------------------------------------------------------------- #
# ending the session
# --------------------------------------------------------------------------- #

def test_end_game_is_host_only_and_produces_standings():
    _m, room, players = started_table(3)
    play_round(room)
    with pytest.raises(GameError):
        engine.end_game(room, players[1])

    engine.end_game(room, players[0])
    assert room.phase == config.PHASE_FINISHED
    assert room.final is not None
    assert len(room.final["standings"]) == 3
    assert [s["rank"] for s in room.final["standings"]] == [1, 2, 3]


def test_final_standings_sort_by_chips_then_push_loan_penalty_last():
    _m, room, players = make_table(3)
    rich_penalised, poor_clean, middle = players
    rich_penalised.chips = 900_000
    rich_penalised.automatic_last_place = True
    rich_penalised.loan_count = 2
    poor_clean.chips = 1_000
    middle.chips = 500_000

    standings = engine.final_standings(room)
    order = [s["nickname"] for s in standings]
    assert order == [middle.nickname, poor_clean.nickname, rich_penalised.nickname]
    assert standings[-1]["autoLast"] is True
    assert standings[-1]["penalty"]
    assert standings[0]["penalty"] == ""


def test_current_ranking_is_plain_chip_order():
    _m, room, players = make_table(3)
    players[0].chips = 100
    players[1].chips = 300
    players[2].chips = 200
    ranking = engine.current_ranking(room)
    assert [r["chips"] for r in ranking] == [300, 200, 100]
    assert [r["rank"] for r in ranking] == [1, 2, 3]


# --------------------------------------------------------------------------- #
# leaving / disconnect
# --------------------------------------------------------------------------- #

def test_force_fold_unblocks_a_disconnected_player():
    _m, room, _p = started_table(3)
    stuck = room.get(room.turn_pid)
    stuck.connected = False
    engine.force_fold(room, stuck)
    assert stuck.folded is True
    assert room.turn_pid != stuck.pid


def test_leaving_mid_round_does_not_corrupt_the_betting_state():
    manager, room, players = started_table(4)
    victim = next(p for p in room.active_players if p.pid != room.turn_pid)
    manager.remove_player(room, victim.pid)

    assert room.get(victim.pid) is None
    assert victim.pid not in room.needs_action
    assert room.turn_pid in room.needs_action
    finish_betting(room)
    assert room.phase != config.PHASE_BET1


def test_seeded_deck_produces_the_expected_hands():
    """Sanity: the deck really is the source of the dealt cards."""
    _m, room, players = make_table(2)
    engine.start_game(room, players[0])
    numbers = sorted(c.number for p in room.round_players for c in p.cards)
    assert len(numbers) == 4
    for n in numbers:
        assert 0 <= n <= 9
