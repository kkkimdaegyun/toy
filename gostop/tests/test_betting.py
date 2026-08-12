"""One betting phase — and above all, 다이 (including out of turn)."""

import random

import pytest

from game import betting, config, engine
from game.errors import GameError

from tests.helpers import (act_passively, enabled_actions, finish_betting,
                           make_table, started_table)


def labels(room, player):
    return {a["type"]: a for a in betting.legal_actions(room, player)}


# --------------------------------------------------------------------------- #
# opening state
# --------------------------------------------------------------------------- #

def test_round_opens_in_first_betting_with_the_dealer_to_act():
    _m, room, _p = started_table(3)
    assert room.phase == config.PHASE_BET1
    assert room.turn_pid == room.dealer_pid
    assert room.current_bet == 0
    assert room.raise_count == 0
    assert room.needs_action == {p.pid for p in room.active_players}


def test_turn_pid_is_always_inside_needs_action():
    _m, room, _p = started_table(4)
    assert room.turn_pid in room.needs_action


# --------------------------------------------------------------------------- #
# check
# --------------------------------------------------------------------------- #

def test_check_is_free_and_only_offered_with_nothing_to_call():
    _m, room, _p = started_table(3)
    actor = room.get(room.turn_pid)
    before = actor.chips
    assert labels(room, actor)["check"]["enabled"] is True
    engine.bet_action(room, actor, betting.ACTION_CHECK)
    assert actor.chips == before
    assert actor.pid not in room.needs_action

    nxt = room.get(room.turn_pid)
    engine.bet_action(room, nxt, betting.ACTION_BET)
    third = room.get(room.turn_pid)
    assert "check" not in labels(room, third)
    with pytest.raises(GameError):
        engine.bet_action(room, third, betting.ACTION_CHECK)


def test_everyone_checking_closes_the_phase():
    _m, room, _p = started_table(3)
    finish_betting(room)
    assert room.phase != config.PHASE_BET1
    assert room.pot == config.ANTE * 3


# --------------------------------------------------------------------------- #
# bet / call / raise
# --------------------------------------------------------------------------- #

def test_bet_moves_chips_and_reopens_the_action():
    _m, room, _p = started_table(3)
    actor = room.get(room.turn_pid)
    before_chips, before_pot = actor.chips, room.pot

    engine.bet_action(room, actor, betting.ACTION_BET)

    assert actor.chips == before_chips - config.BET_AMOUNT
    assert room.pot == before_pot + config.BET_AMOUNT
    assert room.current_bet == config.BET_AMOUNT
    assert room.needs_action == {p.pid for p in room.active_players if p.pid != actor.pid}


def test_call_matches_exactly():
    _m, room, _p = started_table(3)
    engine.bet_action(room, room.get(room.turn_pid), betting.ACTION_BET)
    caller = room.get(room.turn_pid)
    before = caller.chips
    assert labels(room, caller)["call"]["amount"] == config.BET_AMOUNT
    engine.bet_action(room, caller, betting.ACTION_CALL)
    assert caller.chips == before - config.BET_AMOUNT
    assert caller.phase_contrib == room.current_bet
    assert caller.pid not in room.needs_action


def test_raise_costs_call_plus_increment_and_reopens():
    _m, room, _p = started_table(3)
    engine.bet_action(room, room.get(room.turn_pid), betting.ACTION_BET)
    raiser = room.get(room.turn_pid)
    before = raiser.chips
    cost = labels(room, raiser)["raise"]["amount"]
    assert cost == config.BET_AMOUNT + config.RAISE_INCREMENT

    engine.bet_action(room, raiser, betting.ACTION_RAISE)

    assert raiser.chips == before - cost
    assert room.raise_count == 1
    assert room.current_bet == config.BET_AMOUNT + config.RAISE_INCREMENT
    assert room.needs_action == {p.pid for p in room.active_players if p.pid != raiser.pid}


def test_max_three_raises_per_phase():
    _m, room, _p = started_table(3)
    engine.bet_action(room, room.get(room.turn_pid), betting.ACTION_BET)
    for _ in range(config.MAX_RAISES):
        engine.bet_action(room, room.get(room.turn_pid), betting.ACTION_RAISE)
    assert room.raise_count == config.MAX_RAISES

    actor = room.get(room.turn_pid)
    entry = labels(room, actor)["raise"]
    assert entry["enabled"] is False
    assert "3번" in entry["reason"]
    with pytest.raises(GameError):
        engine.bet_action(room, actor, betting.ACTION_RAISE)


def test_a_raise_gives_an_already_acted_player_another_turn():
    _m, room, _p = started_table(3)
    first = room.get(room.turn_pid)
    engine.bet_action(room, first, betting.ACTION_CHECK)
    assert first.pid not in room.needs_action

    engine.bet_action(room, room.get(room.turn_pid), betting.ACTION_BET)
    assert first.pid in room.needs_action          # the action re-opened

    seen = set()
    guard = 0
    while room.phase == config.PHASE_BET1 and room.turn_pid:
        seen.add(room.turn_pid)
        act_passively(room, room.get(room.turn_pid))
        guard += 1
        assert guard < 30
    assert first.pid in seen


# --------------------------------------------------------------------------- #
# button labels carry real money
# --------------------------------------------------------------------------- #

def test_action_labels_show_the_amount():
    _m, room, _p = started_table(3)
    actor = room.get(room.turn_pid)
    entries = labels(room, actor)
    assert entries["check"]["label"] == "체크"
    assert entries["bet"]["label"] == "베팅 10,000"
    assert entries["die"]["label"] == "다이"

    engine.bet_action(room, actor, betting.ACTION_BET)
    nxt = labels(room, room.get(room.turn_pid))
    assert nxt["call"]["label"] == "콜 10,000"
    assert nxt["raise"]["label"] == "레이즈 +10,000"


def test_die_is_always_offered_to_an_active_player():
    _m, room, _p = started_table(4)
    for player in room.active_players:
        entries = labels(room, player)
        if player.pid == room.turn_pid:
            assert entries["die"]["enabled"] is True
        # and every active player may fold out of turn:
        assert room.phase in config.DAI_ALLOWED_PHASES


# --------------------------------------------------------------------------- #
# insufficient chips
# --------------------------------------------------------------------------- #

def test_call_is_blocked_when_short_of_chips_but_die_still_works():
    _m, room, _p = started_table(3)
    engine.bet_action(room, room.get(room.turn_pid), betting.ACTION_BET)
    broke = room.get(room.turn_pid)
    broke.chips = 500

    entry = labels(room, broke)["call"]
    assert entry["enabled"] is False
    assert entry["reason"] == "칩이 부족합니다."
    with pytest.raises(GameError):
        engine.bet_action(room, broke, betting.ACTION_CALL)

    engine.fold(room, broke)
    assert broke.folded is True


# --------------------------------------------------------------------------- #
# illegal actions
# --------------------------------------------------------------------------- #

def test_acting_out_of_turn_is_rejected():
    _m, room, _p = started_table(3)
    other = next(p for p in room.active_players if p.pid != room.turn_pid)
    with pytest.raises(GameError):
        engine.bet_action(room, other, betting.ACTION_CHECK)


def test_betting_outside_a_betting_phase_is_rejected():
    _m, room, players = make_table(3)
    player = players[0]
    with pytest.raises(GameError):
        engine.bet_action(room, player, betting.ACTION_CHECK)


def test_unknown_action_is_rejected():
    _m, room, _p = started_table(3)
    with pytest.raises(GameError):
        engine.bet_action(room, room.get(room.turn_pid), "샤우팅")


# --------------------------------------------------------------------------- #
# 다이
# --------------------------------------------------------------------------- #

def test_die_in_turn_advances_the_turn():
    _m, room, _p = started_table(3)
    actor = room.get(room.turn_pid)
    engine.fold(room, actor)
    assert actor.folded is True
    assert actor.status_key == "die"
    assert room.turn_pid != actor.pid
    assert actor.pid not in room.needs_action


def test_die_out_of_turn_does_not_steal_the_current_turn():
    """The invariant that makes early 다이 safe."""
    _m, room, _p = started_table(4)
    current = room.turn_pid
    folder = next(p for p in room.active_players if p.pid != current)

    engine.fold(room, folder)

    assert room.turn_pid == current, "the current actor was wrongly skipped"
    assert folder.folded is True
    assert folder.pid not in room.needs_action
    assert len(folder.cards) == 2            # cards untouched

    finish_betting(room)
    assert room.phase != config.PHASE_BET1   # play continued normally


def test_several_players_die_before_anyone_acts():
    _m, room, _p = started_table(4)
    order = [p for p in room.active_players if p.pid != room.turn_pid]
    engine.fold(room, order[0])
    engine.fold(room, order[1])
    assert len(room.active_players) == 2
    assert room.turn_pid in room.needs_action
    finish_betting(room)
    assert room.phase in (config.PHASE_DISCARD, config.PHASE_ROUND_END,
                          config.PHASE_DEAL3)


def test_contributed_chips_stay_in_the_pot_after_die():
    _m, room, _p = started_table(3)
    actor = room.get(room.turn_pid)
    engine.bet_action(room, actor, betting.ACTION_BET)
    pot_before = room.pot
    engine.fold(room, actor)
    assert room.pot == pot_before
    assert actor.round_contrib == config.ANTE + config.BET_AMOUNT


def test_last_player_standing_wins_immediately():
    _m, room, _p = started_table(3)
    pot = room.pot
    losers = [p for p in room.active_players][:2]
    survivor = next(p for p in room.active_players if p not in losers)
    before = survivor.chips

    for p in losers:
        engine.fold(room, p)

    assert room.phase == config.PHASE_ROUND_END
    assert survivor.chips == before + pot
    assert room.pot == 0
    assert room.result["type"] == "allFolded"
    assert room.result["reveals"] == []
    assert room.result["winners"][0]["pid"] == survivor.pid
    assert room.result["winners"][0]["hand"] is None


def test_folding_twice_is_rejected():
    _m, room, _p = started_table(3)
    actor = room.get(room.turn_pid)
    engine.fold(room, actor)
    with pytest.raises(GameError) as exc:
        engine.fold(room, actor)
    assert "이미 다이" in str(exc.value)


def test_folding_when_not_in_the_round_is_rejected():
    _m, room, players = started_table(3)
    outsider = players[0]
    outsider.in_round = False
    with pytest.raises(GameError):
        engine.fold(room, outsider)


def test_folded_player_is_skipped_by_the_turn_cursor():
    _m, room, _p = started_table(4)
    first = room.get(room.turn_pid)
    engine.bet_action(room, first, betting.ACTION_CHECK)
    second = room.get(room.turn_pid)
    engine.fold(room, second)
    assert room.turn_pid != second.pid
    guard = 0
    while room.phase == config.PHASE_BET1 and room.turn_pid:
        assert room.turn_pid != second.pid
        act_passively(room, room.get(room.turn_pid))
        guard += 1
        assert guard < 30


# --------------------------------------------------------------------------- #
# randomised invariant sweep
# --------------------------------------------------------------------------- #

def test_invariants_hold_through_randomised_play():
    rng = random.Random(1234)
    for run in range(60):
        n = rng.choice([2, 3, 4, 5, 6])
        _m, room, _p = started_table(n)
        start_total = sum(p.chips for p in room.player_list) + room.pot

        guard = 0
        while room.phase not in (config.PHASE_ROUND_END, config.PHASE_FINISHED):
            guard += 1
            assert guard < 200, "round never finished (run %d)" % run

            if room.phase in config.BETTING_PHASES:
                # invariant: the actor always owes an action
                if room.turn_pid:
                    assert room.turn_pid in room.needs_action
                    assert room.get(room.turn_pid).active
                actor = room.get(room.turn_pid) if room.turn_pid else None
                if actor is None:
                    break
                acts = enabled_actions(room, actor)
                choice = rng.choice(sorted(acts.keys()))
                if choice == betting.ACTION_DIE:
                    engine.fold(room, actor)
                else:
                    engine.bet_action(room, actor, choice)
            elif room.phase == config.PHASE_DISCARD:
                pid = sorted(room.pending_discard)[0]
                player = room.get(pid)
                if rng.random() < 0.2:
                    engine.fold(room, player)
                else:
                    engine.discard(room, player, rng.choice(player.cards).id)
            else:
                break

            # nobody inactive may linger in the pending sets
            for pid in room.needs_action:
                assert room.get(pid).active
            for pid in room.pending_discard:
                assert room.get(pid).active

        assert room.phase == config.PHASE_ROUND_END
        assert room.pot == 0
        assert sum(p.chips for p in room.player_list) == start_total, (
            "chips were created or destroyed in run %d" % run
        )
