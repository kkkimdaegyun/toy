"""MANDATORY: no hidden card number may ever reach the wrong browser.

Every assertion here inspects the *serialized payload* — the exact dict that
app.py hands to socketio.emit — rather than internal state, because the payload
is what actually crosses the wire.
"""

import json

import pytest

from game import betting, config, engine
from game.serializers import serialize_state_for_player

from tests.helpers import (finish_betting, finish_discards, make_table,
                           set_hand, started_table)


# --------------------------------------------------------------------------- #
# the core assertion
# --------------------------------------------------------------------------- #

def assert_no_leak(room, viewer_pid, moment=""):
    """Verify one viewer's payload exposes nothing they may not see."""
    state = serialize_state_for_player(room, viewer_pid)

    for player in room.player_list:
        view = next(v for v in state["players"] if v["pid"] == player.pid)

        if player.pid == viewer_pid:
            for card, real in zip(view["cards"], player.cards):
                assert card["hidden"] is False, "%s: I cannot see my own card" % moment
                assert card["number"] == real.number
            continue

        may_see = bool(player.revealed and not player.folded)
        for card in view["cards"]:
            if may_see:
                assert card["hidden"] is False
            else:
                assert card["hidden"] is True, (
                    "%s: %s's card was face-up for %s" % (moment, player.nickname, viewer_pid)
                )
                assert "number" not in card, (
                    "%s: %s's number leaked to %s" % (moment, player.nickname, viewer_pid)
                )
                assert "label" not in card
        if not may_see:
            assert view["hand"] is None, (
                "%s: %s's 족보 leaked to %s" % (moment, player.nickname, viewer_pid)
            )
    return state


def assert_table_is_clean(room, moment=""):
    for viewer in room.player_list:
        assert_no_leak(room, viewer.pid, moment)


def hidden_numbers_of(room, viewer_pid):
    """The numbers this viewer is NOT allowed to know."""
    out = []
    for p in room.player_list:
        if p.pid == viewer_pid:
            continue
        if p.revealed and not p.folded:
            continue
        out.extend(c.number for c in p.cards)
    return out


# --------------------------------------------------------------------------- #
# every phase of a full round
# --------------------------------------------------------------------------- #

def test_no_leak_at_any_point_of_a_full_round():
    _m, room, players = started_table(4)

    assert_table_is_clean(room, "카드 2장 배분 직후")

    # 1차 베팅 — somebody bets, somebody folds out of turn
    engine.bet_action(room, room.get(room.turn_pid), betting.ACTION_BET)
    assert_table_is_clean(room, "1차 베팅 중")

    early = next(p for p in room.active_players if p.pid != room.turn_pid)
    engine.fold(room, early)
    assert_table_is_clean(room, "턴 밖 다이 직후")

    finish_betting(room)
    assert room.phase == config.PHASE_DISCARD
    assert_table_is_clean(room, "세 번째 카드 배분 후 / 버리기")

    # one player quits during the discard phase and keeps all three cards
    quitter = room.get(sorted(room.pending_discard)[0])
    engine.fold(room, quitter)
    assert len(quitter.cards) == 3
    assert_table_is_clean(room, "버리기 중 다이")

    finish_discards(room)
    assert room.phase == config.PHASE_BET2
    assert_table_is_clean(room, "2차 베팅")

    finish_betting(room)
    assert room.phase == config.PHASE_ROUND_END
    assert_table_is_clean(room, "판 결과")


@pytest.mark.parametrize("count", [2, 3, 4, 5, 6])
def test_no_leak_immediately_after_the_deal(count):
    _m, room, _p = started_table(count)
    assert_table_is_clean(room, "%d인 테이블" % count)


# --------------------------------------------------------------------------- #
# raw payload scan
# --------------------------------------------------------------------------- #

def test_hidden_numbers_never_appear_in_the_players_block():
    _m, room, players = started_table(4)
    finish_betting(room)
    finish_discards(room)

    for viewer in room.player_list:
        state = serialize_state_for_player(room, viewer.pid)
        others = [v for v in state["players"] if v["pid"] != viewer.pid]
        blob = json.dumps(others, ensure_ascii=False)
        assert '"number"' not in blob, "an opponent card number reached %s" % viewer.nickname

        # a face-down card object must carry nothing but its opaque id
        for view in others:
            for card in view["cards"]:
                assert set(card.keys()) == {"id", "hidden"}
                assert card["hidden"] is True


def test_card_ids_are_reminted_every_round():
    """So a viewer cannot learn an id->number mapping and reuse it later."""
    _m, room, players = started_table(3)
    round_one = {c.id for p in room.player_list for c in p.cards}
    round_one |= {c.id for c in room.deck.cards}

    finish_betting(room)
    finish_discards(room)
    finish_betting(room)
    engine.next_round(room, players[0])

    round_two = {c.id for p in room.player_list for c in p.cards}
    round_two |= {c.id for c in room.deck.cards}

    assert len(round_one) == 20
    assert len(round_two) == 20
    assert not (round_one & round_two), "card ids were reused across rounds"


# --------------------------------------------------------------------------- #
# a player who said 다이 is never revealed
# --------------------------------------------------------------------------- #

def test_folded_player_is_never_revealed_even_after_showdown():
    _m, room, players = started_table(3)
    folder = next(p for p in room.active_players if p.pid != room.turn_pid)
    engine.fold(room, folder)
    finish_betting(room)
    finish_discards(room)
    finish_betting(room)
    assert room.phase == config.PHASE_ROUND_END
    assert room.result["type"] == "showdown"

    for viewer in room.player_list:
        if viewer.pid == folder.pid:
            continue
        state = serialize_state_for_player(room, viewer.pid)
        view = next(v for v in state["players"] if v["pid"] == folder.pid)
        assert all(c["hidden"] is True for c in view["cards"])
        assert view["hand"] is None
        assert view["revealed"] is False

        reveal_pids = [r["pid"] for r in state["result"]["reveals"]]
        assert folder.pid not in reveal_pids
        winner_pids = [w["pid"] for w in state["result"]["winners"]]
        assert folder.pid not in winner_pids


def test_all_folded_win_hides_even_the_winner():
    _m, room, players = started_table(3)
    survivor = room.get(room.turn_pid)
    for p in list(room.active_players):
        if p.pid != survivor.pid:
            engine.fold(room, p)

    assert room.phase == config.PHASE_ROUND_END
    assert room.result["type"] == "allFolded"
    assert room.result["reveals"] == []

    for viewer in room.player_list:
        state = serialize_state_for_player(room, viewer.pid)
        assert state["result"]["reveals"] == []
        for winner in state["result"]["winners"]:
            assert "cards" not in winner
            assert "hand" not in winner
        if viewer.pid != survivor.pid:
            view = next(v for v in state["players"] if v["pid"] == survivor.pid)
            assert all(c["hidden"] is True for c in view["cards"])
            assert view["hand"] is None


# --------------------------------------------------------------------------- #
# the log
# --------------------------------------------------------------------------- #

def test_the_game_log_never_prints_a_hidden_card_number():
    _m, room, players = started_table(3)
    folder = next(p for p in room.active_players if p.pid != room.turn_pid)
    hidden = [c.number for c in folder.cards]
    engine.fold(room, folder)
    finish_betting(room)
    finish_discards(room)
    finish_betting(room)

    text = " ".join(entry["text"] for entry in room.log)
    assert folder.nickname in text            # the fold itself is logged
    for line in room.log:
        if folder.nickname in line["text"]:
            for number in hidden:
                assert ("%d땡" % number) not in line["text"]
                assert ("%d끗" % number) not in line["text"] or "다이" not in line["text"]
    # a folded player's 족보 is never named in the log at all
    assert not any(
        folder.nickname in entry["text"] and "족보" in entry["text"]
        for entry in room.log
    )


def test_the_log_only_names_a_hand_for_revealed_players():
    _m, room, players = started_table(2)
    finish_betting(room)
    finish_discards(room)
    active = room.active_players
    set_hand(active[0], 3, 8)
    set_hand(active[1], 9, 9)
    finish_betting(room)

    text = " ".join(entry["text"] for entry in room.log)
    assert "38광땡" in text                    # the winner revealed, so this is fine
    for p in room.player_list:
        if p.folded:
            assert p.nickname + "님 - " not in text


# --------------------------------------------------------------------------- #
# the view is genuinely per-viewer
# --------------------------------------------------------------------------- #

def test_each_viewer_gets_a_different_you_block():
    _m, room, players = started_table(3)
    a = serialize_state_for_player(room, players[0].pid)
    b = serialize_state_for_player(room, players[1].pid)

    assert a["you"]["pid"] != b["you"]["pid"]
    assert a["you"]["nickname"] == players[0].nickname
    assert b["you"]["nickname"] == players[1].nickname
    assert [c["number"] for c in a["you"]["cards"]] == [c.number for c in players[0].cards]
    assert [c["number"] for c in b["you"]["cards"]] == [c.number for c in players[1].cards]


def test_only_my_own_entry_carries_numbers():
    _m, room, players = started_table(4)
    for viewer in players:
        state = serialize_state_for_player(room, viewer.pid)
        with_numbers = [
            v["pid"] for v in state["players"]
            if any("number" in c for c in v["cards"])
        ]
        assert with_numbers == [viewer.pid]


def test_discard_previews_are_only_in_my_own_block():
    _m, room, players = started_table(3)
    finish_betting(room)
    assert room.phase == config.PHASE_DISCARD
    for viewer in players:
        state = serialize_state_for_player(room, viewer.pid)
        assert len(state["you"]["discardPreviews"]) == 3
        blob = json.dumps(state["players"], ensure_ascii=False)
        assert "discardPreviews" not in blob
        assert "keepNumbers" not in blob


def test_a_spectator_sees_no_card_numbers_at_all():
    manager, room, players = started_table(2)
    _room, watcher = manager.join_room("sidW", room.code, "구경", "ghost")
    state = serialize_state_for_player(room, watcher.pid)
    for view in state["players"]:
        for card in view["cards"]:
            assert card["hidden"] is True
            assert "number" not in card
    assert state["you"]["cards"] == []
    assert state["you"]["hand"] is None


def test_serialized_state_is_json_safe():
    """Everything we emit must survive json.dumps without a custom encoder."""
    _m, room, players = started_table(3)
    finish_betting(room)
    finish_discards(room)
    finish_betting(room)
    for viewer in players:
        state = serialize_state_for_player(room, viewer.pid)
        json.dumps(state, ensure_ascii=False)      # must not raise


def test_public_config_leaks_nothing_about_a_live_game():
    from game.serializers import public_config
    blob = json.dumps(public_config(), ensure_ascii=False)
    assert "number" not in blob
    assert public_config()["startingChips"] == config.STARTING_CHIPS
    assert len(public_config()["characters"]) >= 12
