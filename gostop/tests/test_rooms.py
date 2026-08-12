"""Rooms, nicknames, characters and reconnection."""

import pytest

from game import config, engine, utils
from game.errors import GameError
from game.rooms import RoomManager

from tests.helpers import make_table, play_round, started_table


# --------------------------------------------------------------------------- #
# creating and joining
# --------------------------------------------------------------------------- #

def test_creator_becomes_the_host():
    _m, room, players = make_table(3)
    assert room.host_pid == players[0].pid
    assert players[0].pid == room.seats[0]


def test_room_code_is_short_and_unambiguous():
    manager = RoomManager()
    room, _p = manager.create_room("s", "김대균", "bear")
    assert len(room.code) == config.ROOM_CODE_LEN == 4
    for ch in room.code:
        assert ch in config.ROOM_CODE_ALPHABET
    assert "O" not in config.ROOM_CODE_ALPHABET
    assert "0" not in config.ROOM_CODE_ALPHABET
    assert "1" not in config.ROOM_CODE_ALPHABET
    assert "I" not in config.ROOM_CODE_ALPHABET


def test_room_codes_are_unique():
    manager = RoomManager()
    codes = set()
    for i in range(60):
        room, _p = manager.create_room("s%d" % i, "사람%d" % i, "bear")
        assert room.code not in codes
        codes.add(room.code)


def test_room_lookup_is_case_and_space_insensitive():
    manager = RoomManager()
    room, _p = manager.create_room("s", "김대균", "bear")
    assert manager.get(room.code.lower()) is room
    assert manager.get(" " + room.code + " ") is room


def test_joining_an_unknown_room_is_rejected():
    manager = RoomManager()
    with pytest.raises(GameError) as exc:
        manager.join_room("s", "ZZZZ", "민수", "cat")
    assert "방을 찾을 수 없습니다" in str(exc.value)


def test_room_is_capped_at_six_players():
    manager, room, _p = make_table(6)
    assert room.size == config.MAX_PLAYERS == 6
    with pytest.raises(GameError) as exc:
        manager.join_room("sid9", room.code, "일곱", "ghost")
    assert "가득" in str(exc.value)


# --------------------------------------------------------------------------- #
# nicknames
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("raw,expected", [
    ("  김대균  ", "김대균"),
    ("김  대균", "김 대균"),
    ("\t민수\n", "민수"),
    ("가나다라마바사아자차카타파하", "가나다라마바사아자차카타"),   # clamped to 12
])
def test_nickname_cleaning(raw, expected):
    assert utils.clean_nickname(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "\t\n", None, 123])
def test_empty_nicknames_are_rejected(raw):
    manager = RoomManager()
    with pytest.raises(GameError) as exc:
        manager.create_room("s", raw, "bear")
    assert "닉네임" in str(exc.value)


def test_nickname_is_clamped_to_twelve_characters():
    manager = RoomManager()
    room, player = manager.create_room("s", "가나다라마바사아자차카타파하거너더", "bear")
    assert len(player.nickname) == config.NICKNAME_MAX_LEN == 12


def test_duplicate_nicknames_are_rejected_ignoring_spaces_and_case():
    manager, room, _p = make_table(1)
    with pytest.raises(GameError) as exc:
        manager.join_room("sX", room.code, "  김대균  ", "cat")
    assert "이미 사용 중인 닉네임" in str(exc.value)

    manager2 = RoomManager()
    room2, _host = manager2.create_room("a", "Kim", "bear")
    with pytest.raises(GameError):
        manager2.join_room("b", room2.code, "kim", "cat")


def test_the_same_nickname_is_fine_in_another_room():
    manager = RoomManager()
    room_a, _a = manager.create_room("a", "김대균", "bear")
    room_b, b = manager.create_room("b", "김대균", "bear")
    assert room_a.code != room_b.code
    assert b.nickname == "김대균"


# --------------------------------------------------------------------------- #
# characters
# --------------------------------------------------------------------------- #

def test_there_are_at_least_twelve_characters():
    assert len(config.CHARACTERS) >= 12
    ids = [c["id"] for c in config.CHARACTERS]
    assert len(set(ids)) == len(ids)
    for c in config.CHARACTERS:
        assert c["name"]


@pytest.mark.parametrize("bad", ["", "godzilla", None, 7])
def test_unknown_characters_are_rejected(bad):
    manager = RoomManager()
    with pytest.raises(GameError) as exc:
        manager.create_room("s", "김대균", bad)
    assert "캐릭터" in str(exc.value)


def test_a_character_cannot_be_used_twice_in_one_room():
    manager, room, _p = make_table(1)
    with pytest.raises(GameError) as exc:
        manager.join_room("sX", room.code, "민수", "bear")
    assert "다른 플레이어가 사용 중" in str(exc.value)


def test_the_same_character_is_fine_in_another_room():
    manager = RoomManager()
    manager.create_room("a", "김대균", "bear")
    room_b, player_b = manager.create_room("b", "민수", "bear")
    assert player_b.character == "bear"
    assert room_b.used_characters() == {"bear"}


def test_used_characters_are_reported_to_the_join_screen():
    from game.serializers import lobby_summary
    _m, room, _p = make_table(3)
    summary = lobby_summary(room)
    assert summary["usedCharacters"] == sorted(["bear", "rabbit", "robot"])
    assert summary["playerCount"] == 3
    assert summary["maxPlayers"] == 6


# --------------------------------------------------------------------------- #
# reconnection
# --------------------------------------------------------------------------- #

def test_rejoin_restores_the_same_player_without_duplicating():
    manager, room, players = make_table(3)
    host = players[0]
    manager.mark_disconnected("sid0")
    assert host.connected is False

    room2, restored = manager.rejoin("brand-new-sid", room.code, host.token)

    assert room2 is room
    assert restored is host
    assert room.size == 3
    assert restored.connected is True
    assert restored.nickname == "김대균"
    assert restored.character == "bear"
    assert room.host_pid == restored.pid


def test_rejoin_mid_round_preserves_cards_chips_and_loans():
    manager, room, players = started_table(3)
    host = players[0]
    host.take_loan()
    cards_before = list(host.cards)
    chips_before = host.chips
    phase_before = room.phase

    manager.mark_disconnected("sid0")
    _room, restored = manager.rejoin("sid0-again", room.code, host.token)

    assert restored.cards == cards_before
    assert restored.chips == chips_before
    assert restored.loan_count == 1
    assert room.phase == phase_before
    assert room.size == 3


def test_rejoin_with_an_unknown_token_is_rejected():
    manager, room, _p = make_table(2)
    with pytest.raises(GameError) as exc:
        manager.rejoin("sX", room.code, "not-a-token")
    assert "다시 입장" in str(exc.value)


def test_rejoin_rebinds_the_socket_index():
    manager, room, players = make_table(2)
    manager.rejoin("fresh-sid", room.code, players[0].token)
    found_room, found_player = manager.locate_sid("fresh-sid")
    assert found_room is room
    assert found_player is players[0]
    assert manager.locate_sid("sid0") == (None, None)


def test_disconnect_keeps_the_seat():
    manager, room, players = started_table(3)
    manager.mark_disconnected("sid1")
    assert room.size == 3
    assert players[1].connected is False
    assert players[1].in_round is True


# --------------------------------------------------------------------------- #
# leaving
# --------------------------------------------------------------------------- #

def test_host_migrates_when_the_host_leaves():
    manager, room, players = make_table(3)
    manager.leave("sid0")
    assert room.size == 2
    assert room.host_pid in (players[1].pid, players[2].pid)


def test_seats_are_renumbered_after_a_departure():
    manager, room, _p = make_table(4)
    manager.leave("sid1")
    assert [p.seat for p in room.player_list] == [0, 1, 2]


def test_removing_the_last_player_deletes_the_room():
    manager, room, _p = make_table(1)
    code = room.code
    manager.leave("sid0")
    assert manager.get(code) is None
    assert manager.stats()["rooms"] == 0


def test_leaving_mid_round_folds_the_player():
    manager, room, players = started_table(3)
    victim = next(p for p in room.active_players if p.pid != room.turn_pid)
    sid = victim.sid
    manager.leave(sid)
    assert room.get(victim.pid) is None
    assert victim.pid not in room.needs_action


def test_late_joiner_spectates_until_the_next_round():
    manager, room, players = started_table(2)
    _room, latecomer = manager.join_room("sidL", room.code, "지각", "ghost")
    assert latecomer.spectating is True
    assert latecomer.in_round is False

    play_round(room)
    engine.next_round(room, players[0])
    assert latecomer.spectating is False
    assert latecomer.in_round is True


def test_sweep_drops_lobby_ghosts_but_keeps_started_games():
    import time
    manager, room, players = make_table(3)
    manager.mark_disconnected("sid2")
    players[2].last_seen = time.time() - 999
    manager.sweep(lobby_grace_sec=45)
    assert room.size == 2

    manager2, room2, players2 = started_table(3)
    manager2.mark_disconnected("sid2")
    players2[2].last_seen = time.time() - 999
    manager2.sweep(lobby_grace_sec=45)
    assert room2.size == 3, "a started game must never drop a seat automatically"


def test_stats_counts_rooms_and_players():
    manager = RoomManager()
    manager.create_room("a", "김대균", "bear")
    manager.create_room("b", "민수", "cat")
    assert manager.stats() == {"rooms": 2, "players": 2}


# --------------------------------------------------------------------------- #
# 조사 helper (used all over the Korean log)
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("word,expected", [
    ("김대균", "김대균이"),
    ("민수", "민수가"),
    ("영희", "영희가"),
    ("철수", "철수가"),
    ("지현", "지현이"),
])
def test_korean_particle_selection(word, expected):
    assert utils.josa(word, "이", "가") == expected


def test_money_formatting():
    assert utils.won(10000) == "10,000"
    assert utils.won(300000) == "300,000"
    assert utils.won(0) == "0"
    assert utils.won(None) == "0"
