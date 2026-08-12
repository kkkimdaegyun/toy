from __future__ import annotations

import secrets
import string
import uuid

from .models import Player, Room


class RoomError(ValueError):
    pass


class RoomManager:
    def __init__(self):
        self.rooms: dict[str, Room] = {}
        self.socket_to_player: dict[str, tuple[str, str]] = {}

    def _code(self) -> str:
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        while True:
            code = "".join(secrets.choice(alphabet) for _ in range(4))
            if code not in self.rooms:
                return code

    @staticmethod
    def validate_nickname(nickname) -> str:
        if not isinstance(nickname, str):
            raise RoomError("닉네임을 입력해주세요.")
        cleaned = " ".join(nickname.strip().split())
        if not 2 <= len(cleaned) <= 20:
            raise RoomError("닉네임은 2~20자로 입력해주세요.")
        return cleaned

    def create_room(self, nickname: str, socket_id: str) -> tuple[Room, Player]:
        nickname = self.validate_nickname(nickname)
        room = Room(code=self._code())
        player = Player(id=uuid.uuid4().hex, nickname=nickname, token=secrets.token_urlsafe(32), socket_id=socket_id, host=True)
        room.players[player.id] = player
        room.host_player_id = player.id
        room.event_log.append(f"{nickname} 님이 방을 만들었습니다.")
        self.rooms[room.code] = room
        self.socket_to_player[socket_id] = (room.code, player.id)
        return room, player

    def join_room(self, code: str, nickname: str, socket_id: str) -> tuple[Room, Player]:
        code = str(code or "").strip().upper()
        nickname = self.validate_nickname(nickname)
        room = self.rooms.get(code)
        if not room:
            raise RoomError("방을 찾을 수 없습니다.")
        if room.phase != "lobby":
            raise RoomError("이미 게임이 시작되었습니다.")
        if len(room.players) >= 4:
            raise RoomError("방이 가득 찼습니다. 최대 4명까지 참가할 수 있습니다.")
        if any(p.nickname.casefold() == nickname.casefold() for p in room.players.values()):
            raise RoomError("이미 사용 중인 닉네임입니다.")
        player = Player(id=uuid.uuid4().hex, nickname=nickname, token=secrets.token_urlsafe(32), socket_id=socket_id)
        room.players[player.id] = player
        room.event_log.append(f"{nickname} 님이 참가했습니다.")
        self.socket_to_player[socket_id] = (room.code, player.id)
        return room, player

    def reconnect(self, code: str, token: str, socket_id: str) -> tuple[Room, Player]:
        room = self.rooms.get(str(code or "").strip().upper())
        if not room:
            raise RoomError("이 방은 더 이상 사용할 수 없습니다.")
        player = next((p for p in room.players.values() if secrets.compare_digest(p.token, str(token or ""))), None)
        if not player:
            raise RoomError("저장된 접속 정보를 확인할 수 없습니다.")
        if player.socket_id:
            self.socket_to_player.pop(player.socket_id, None)
        player.socket_id, player.connected = socket_id, True
        self.socket_to_player[socket_id] = (room.code, player.id)
        room.event_log.append(f"{player.nickname} 님이 다시 접속했습니다.")
        return room, player

    def by_socket(self, socket_id: str) -> tuple[Room, Player]:
        pair = self.socket_to_player.get(socket_id)
        if not pair or pair[0] not in self.rooms or pair[1] not in self.rooms[pair[0]].players:
            raise RoomError("먼저 방에 참가해주세요.")
        room = self.rooms[pair[0]]
        return room, room.players[pair[1]]

    def disconnect(self, socket_id: str) -> Room | None:
        pair = self.socket_to_player.pop(socket_id, None)
        if not pair or pair[0] not in self.rooms:
            return None
        room = self.rooms[pair[0]]
        player = room.players.get(pair[1])
        if player and player.socket_id == socket_id:
            player.connected, player.socket_id = False, None
            room.event_log.append(f"{player.nickname} 님의 연결이 끊겼습니다.")
        return room
