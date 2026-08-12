"""Room registry: creation, joining, reconnecting, leaving.

All mutations happen under a single re-entrant lock.  Flask-SocketIO's
threading mode really does run handlers on different threads, and the timed
phase transitions in engine.py fire from background threads too, so this lock
is what keeps the game state coherent.
"""

from __future__ import annotations

import threading
import time

from . import config, engine, errors, utils
from .errors import GameError
from .models import Player, Room


class RoomManager:
    def __init__(self):
        self.rooms: dict[str, Room] = {}
        self.lock = threading.RLock()
        self._sid_index: dict[str, tuple] = {}   # sid -> (room_code, pid)

    # ------------------------------------------------------------------ #
    # lookup
    # ------------------------------------------------------------------ #
    def get(self, code) -> Room | None:
        code = utils.normalize_room_code(code)
        return self.rooms.get(code)

    def require(self, code) -> Room:
        room = self.get(code)
        if room is None:
            raise GameError(errors.ROOM_NOT_FOUND, "no_room")
        return room

    def locate_sid(self, sid):
        """-> (room, player) or (None, None)"""
        entry = self._sid_index.get(sid)
        if not entry:
            return None, None
        room = self.rooms.get(entry[0])
        if room is None:
            self._sid_index.pop(sid, None)
            return None, None
        player = room.get(entry[1])
        if player is None:
            self._sid_index.pop(sid, None)
            return None, None
        return room, player

    def _bind_sid(self, sid, room, player):
        if player.sid and player.sid != sid:
            self._sid_index.pop(player.sid, None)
        player.sid = sid
        player.connected = True
        player.last_seen = time.time()
        if sid:
            self._sid_index[sid] = (room.code, player.pid)

    # ------------------------------------------------------------------ #
    # validation
    # ------------------------------------------------------------------ #
    @staticmethod
    def _validate_identity(room, nickname, character, exclude_pid=None):
        nick = utils.clean_nickname(nickname)
        if not nick:
            raise GameError(errors.NICKNAME_EMPTY, "nickname")
        if room is not None and room.nickname_taken(utils.nickname_key, nick, exclude_pid):
            raise GameError(errors.NICKNAME_TAKEN, "nickname")

        char = character if isinstance(character, str) else ""
        if char not in config.CHARACTER_IDS:
            raise GameError(errors.CHARACTER_INVALID, "character")
        if room is not None and char in room.used_characters(exclude_pid=exclude_pid):
            raise GameError(errors.CHARACTER_TAKEN, "character")
        return nick, char

    # ------------------------------------------------------------------ #
    # create / join
    # ------------------------------------------------------------------ #
    def create_room(self, sid, nickname, character, hooks=None):
        with self.lock:
            nick, char = self._validate_identity(None, nickname, character)
            code = utils.new_room_code(self.rooms.keys())
            room = Room(code=code)
            room.hooks = hooks
            player = Player(
                pid=utils.new_id("p_"),
                token=utils.new_token(),
                nickname=nick,
                character=char,
            )
            room.add_player(player)
            room.host_pid = player.pid
            room.log_line(f"{nick}님이 방을 만들었습니다.")
            self.rooms[code] = room
            self._bind_sid(sid, room, player)
            return room, player

    def join_room(self, sid, code, nickname, character):
        with self.lock:
            room = self.require(code)
            if room.is_full:
                raise GameError(errors.ROOM_FULL, "full")
            nick, char = self._validate_identity(room, nickname, character)
            player = Player(
                pid=utils.new_id("p_"),
                token=utils.new_token(),
                nickname=nick,
                character=char,
            )
            if room.started and room.phase != config.PHASE_FINISHED:
                # Late joiners simply sit out until the next 판.
                player.spectating = True
                player.status_key = "spectating"
            room.add_player(player)
            room.log_line(f"{nick}님이 입장했습니다.")
            self._bind_sid(sid, room, player)
            return room, player

    def rejoin(self, sid, code, token):
        """Reconnect after a refresh.  Never creates a duplicate player."""
        with self.lock:
            room = self.require(code)
            player = room.by_token(token) if token else None
            if player is None:
                raise GameError("이전 자리를 찾을 수 없습니다. 다시 입장해주세요.", "no_seat")
            was_offline = not player.connected
            self._bind_sid(sid, room, player)
            if was_offline:
                room.log_line(f"{player.nickname}님이 다시 접속했습니다.")
            return room, player

    # ------------------------------------------------------------------ #
    # leaving
    # ------------------------------------------------------------------ #
    def mark_disconnected(self, sid):
        with self.lock:
            room, player = self.locate_sid(sid)
            if room is None:
                return None, None
            self._sid_index.pop(sid, None)
            if player.sid == sid:
                player.sid = None
                player.connected = False
                player.last_seen = time.time()
                room.log_line(f"{player.nickname}님의 연결이 끊겼습니다.")
                room.touch()
            return room, player

    def leave(self, sid):
        """Explicit '방 나가기'."""
        with self.lock:
            room, player = self.locate_sid(sid)
            if room is None:
                return None, None
            self._sid_index.pop(sid, None)
            engine.handle_player_removed(room, player)
            room.remove_player(player.pid)
            if not room.players:
                self.rooms.pop(room.code, None)
                return None, player
            return room, player

    def remove_player(self, room, pid):
        with self.lock:
            player = room.get(pid)
            if player is None:
                return
            if player.sid:
                self._sid_index.pop(player.sid, None)
            engine.handle_player_removed(room, player)
            room.remove_player(pid)
            if not room.players:
                self.rooms.pop(room.code, None)

    # ------------------------------------------------------------------ #
    # housekeeping
    # ------------------------------------------------------------------ #
    def sweep(self, lobby_grace_sec: float = 45.0):
        """Drop lobby ghosts and stale empty rooms.  Returns touched rooms."""
        touched = []
        now = time.time()
        with self.lock:
            for code in list(self.rooms.keys()):
                room = self.rooms.get(code)
                if room is None:
                    continue
                if not room.players:
                    if now - room.last_active > 60:
                        self.rooms.pop(code, None)
                    continue
                if not room.started:
                    doomed = [
                        p.pid for p in room.player_list
                        if not p.connected and now - p.last_seen > lobby_grace_sec
                    ]
                    for pid in doomed:
                        name = room.players[pid].nickname
                        self.remove_player(room, pid)
                        if code in self.rooms:
                            room.log_line(f"{name}님이 나갔습니다.")
                    if doomed and code in self.rooms:
                        touched.append(room)
                if code in self.rooms and now - room.last_active > config.ROOM_IDLE_TTL_SEC:
                    self.rooms.pop(code, None)
        return touched

    def stats(self) -> dict:
        with self.lock:
            return {
                "rooms": len(self.rooms),
                "players": sum(r.size for r in self.rooms.values()),
            }


manager = RoomManager()
