from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field
import secrets
import string
import threading
import time
import uuid
from typing import Deque, Iterable


FRUITS = ("strawberry", "banana", "lime", "plum")
FRUIT_NAMES = {
    "strawberry": "딸기",
    "banana": "바나나",
    "lime": "라임",
    "plum": "자두",
}
CARD_DISTRIBUTION = {1: 5, 2: 3, 3: 3, 4: 2, 5: 1}
AVATARS = ("bear", "cat", "dog", "rabbit", "chick", "penguin", "robot", "ghost")

ROOM_CAPACITY = 4
MIN_PLAYERS = 2
MIN_REVEAL_SETTLE_SECONDS = 0.300
RING_RESOLUTION_COOLDOWN_SECONDS = 0.500
PLAYER_RING_DEBOUNCE_SECONDS = 0.250
REACTION_COOLDOWN_SECONDS = 2.0

LOBBY = "LOBBY"
PLAYING = "PLAYING"
PAUSED_DISCONNECT = "PAUSED_DISCONNECT"
GAME_OVER = "GAME_OVER"


class GameError(Exception):
    def __init__(self, message: str, code: str = "invalid_action") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


@dataclass(frozen=True, slots=True)
class Card:
    id: str
    fruit: str
    count: int

    def public(self) -> dict:
        return {"id": self.id, "fruit": self.fruit, "count": self.count}


def build_deck() -> list[Card]:
    """Build the exact 56-card deck. Every physical card has a unique id."""
    deck: list[Card] = []
    for fruit in FRUITS:
        for count, copies in CARD_DISTRIBUTION.items():
            for copy_index in range(copies):
                deck.append(
                    Card(
                        id=f"card_{fruit}_{count}_{copy_index}_{uuid.uuid4().hex[:10]}",
                        fruit=fruit,
                        count=count,
                    )
                )
    return deck


@dataclass(slots=True)
class Player:
    id: str
    reconnect_token: str
    nickname: str
    avatar: str
    seat: int
    sid: str | None
    connected: bool = True
    ready: bool = False
    eliminated: bool = False
    draw_pile: Deque[Card] = field(default_factory=deque)
    face_up: list[Card] = field(default_factory=list)
    last_ring_at: float = -10_000.0
    last_reaction_at: float = -10_000.0

    @property
    def active(self) -> bool:
        return not self.eliminated and bool(self.draw_pile)


class Room:
    def __init__(self, code: str) -> None:
        self.code = code
        self.players: list[Player] = []
        self.host_id: str | None = None
        self.state = LOBBY
        self.state_before_pause = PLAYING
        self.current_player_id: str | None = None
        self.dealer_id: str | None = None
        self.winner_id: str | None = None
        self.board_version = 0
        self.reveal_allowed_at = 0.0
        self.ring_guard_until = 0.0
        self.last_bell_was_correct = False
        self.log: deque[str] = deque(maxlen=12)
        self.action_lock = threading.RLock()
        self.rng = secrets.SystemRandom()

    def player_by_id(self, player_id: str) -> Player | None:
        return next((p for p in self.players if p.id == player_id), None)

    def player_by_sid(self, sid: str) -> Player | None:
        return next((p for p in self.players if p.sid == sid), None)

    def player_by_token(self, token: str) -> Player | None:
        return next((p for p in self.players if secrets.compare_digest(p.reconnect_token, token)), None)

    def _require_player(self, player_id: str) -> Player:
        player = self.player_by_id(player_id)
        if not player:
            raise GameError("플레이어 정보를 찾을 수 없습니다.", "player_not_found")
        return player

    def add_player(self, nickname: str, avatar: str, sid: str) -> Player:
        with self.action_lock:
            nickname = nickname.strip()
            if not nickname:
                raise GameError("닉네임을 입력해주세요.", "empty_nickname")
            if len(nickname) > 12:
                raise GameError("닉네임은 12자까지 입력할 수 있어요.", "nickname_too_long")
            if avatar not in AVATARS:
                raise GameError("캐릭터를 다시 선택해주세요.", "invalid_avatar")
            if len(self.players) >= ROOM_CAPACITY:
                raise GameError("이 방은 최대 인원 4명이 모두 모였어요.", "room_full")
            if any(p.nickname.casefold() == nickname.casefold() for p in self.players):
                raise GameError("같은 닉네임을 사용 중인 플레이어가 있어요.", "duplicate_nickname")
            if self.state != LOBBY:
                raise GameError("이미 게임이 시작된 방입니다.", "game_started")

            occupied = {p.seat for p in self.players}
            seat = next(index for index in range(ROOM_CAPACITY) if index not in occupied)
            player = Player(
                id=f"player_{uuid.uuid4().hex}",
                reconnect_token=secrets.token_urlsafe(32),
                nickname=nickname,
                avatar=avatar,
                seat=seat,
                sid=sid,
            )
            self.players.append(player)
            self.players.sort(key=lambda item: item.seat)
            if self.host_id is None:
                self.host_id = player.id
            self.log.append(f"{nickname}님이 방에 들어왔습니다.")
            return player

    def reconnect(self, reconnect_token: str, sid: str) -> Player:
        with self.action_lock:
            player = self.player_by_token(reconnect_token)
            if not player:
                raise GameError("재접속 정보를 찾지 못했습니다.", "reconnect_failed")
            player.sid = sid
            player.connected = True
            self.log.append(f"{player.nickname}님이 다시 연결되었습니다.")
            self._resume_if_possible()
            return player

    def disconnect(self, sid: str) -> Player | None:
        with self.action_lock:
            player = self.player_by_sid(sid)
            if not player:
                return None
            player.sid = None
            player.connected = False
            player.ready = False if self.state == LOBBY else player.ready
            self.log.append(f"{player.nickname}님의 연결이 끊겼습니다.")
            if self.state == PLAYING:
                self.state_before_pause = PLAYING
                self.state = PAUSED_DISCONNECT
            return player

    def _resume_if_possible(self) -> None:
        if self.state == PAUSED_DISCONNECT and all(p.connected for p in self.players):
            self.state = self.state_before_pause
            self.reveal_allowed_at = time.monotonic() + MIN_REVEAL_SETTLE_SECONDS
            self.log.append("모든 플레이어가 돌아와 게임을 계속합니다.")

    def set_ready(self, player_id: str, ready: bool) -> None:
        with self.action_lock:
            player = self._require_player(player_id)
            if self.state != LOBBY:
                raise GameError("대기실에서만 준비할 수 있어요.")
            if player.id == self.host_id:
                raise GameError("방장은 모두 준비되면 게임을 시작해주세요.")
            player.ready = bool(ready)

    def select_character(self, player_id: str, avatar: str) -> None:
        with self.action_lock:
            player = self._require_player(player_id)
            if self.state != LOBBY:
                raise GameError("게임 중에는 캐릭터를 바꿀 수 없어요.")
            if avatar not in AVATARS:
                raise GameError("캐릭터를 다시 선택해주세요.")
            player.avatar = avatar

    def can_start(self) -> bool:
        return (
            self.state == LOBBY
            and MIN_PLAYERS <= len(self.players) <= ROOM_CAPACITY
            and all(p.connected for p in self.players)
            and all(p.ready for p in self.players if p.id != self.host_id)
        )

    def start_game(self, requester_id: str, *, rematch: bool = False, now: float | None = None) -> dict:
        with self.action_lock:
            if requester_id != self.host_id:
                raise GameError("방장만 게임을 시작할 수 있어요.", "host_only")
            if rematch:
                if self.state != GAME_OVER:
                    raise GameError("게임이 끝난 뒤 다시 시작할 수 있어요.")
                if not (MIN_PLAYERS <= len(self.players) <= ROOM_CAPACITY) or not all(p.connected for p in self.players):
                    raise GameError("참가한 플레이어가 모두 연결되어야 다시 시작할 수 있어요.")
            elif not self.can_start():
                raise GameError("2명 이상 모이고 참가한 플레이어가 모두 준비해야 시작할 수 있어요.", "not_ready")

            deck = build_deck()
            self.rng.shuffle(deck)
            player_count = len(self.players)
            for player in self.players:
                player.draw_pile.clear()
                player.face_up.clear()
                player.eliminated = False
                player.ready = player.id == self.host_id
                player.last_ring_at = -10_000.0
            self.dealer_id = self.rng.choice(self.players).id
            dealer = self._require_player(self.dealer_id)
            dealer_index = self.players.index(dealer)
            first_player_index = (dealer_index + 1) % player_count
            deal_order = self.players[first_player_index:] + self.players[:first_player_index]
            for index, card in enumerate(deck):
                deal_order[index % player_count].draw_pile.append(card)

            self.current_player_id = deal_order[0].id
            self.winner_id = None
            self.board_version = 0
            moment = time.monotonic() if now is None else now
            self.reveal_allowed_at = moment + 0.800
            self.ring_guard_until = moment
            self.last_bell_was_correct = False
            self.state = PLAYING
            self.log.clear()
            self.log.append("게임을 시작합니다.")
            self.log.append(f"{dealer.nickname}님이 카드를 나눴습니다.")
            first = self._require_player(self.current_player_id)
            self.log.append(f"{first.nickname}님의 차례입니다.")
            self.assert_integrity()
            return {
                "dealer_id": dealer.id,
                "first_player_id": first.id,
                "board_version": self.board_version,
            }

    def visible_totals(self) -> dict[str, int]:
        totals = {fruit: 0 for fruit in FRUITS}
        for player in self.players:
            if player.face_up:
                top = player.face_up[-1]
                totals[top.fruit] += top.count
        return totals

    def has_exact_five(self) -> bool:
        return any(total == 5 for total in self.visible_totals().values())

    def _active_players(self) -> list[Player]:
        return [p for p in self.players if p.active]

    def _next_active_after(self, seat: int) -> Player | None:
        for offset in range(1, ROOM_CAPACITY + 1):
            candidate = next((p for p in self.players if p.seat == (seat + offset) % ROOM_CAPACITY), None)
            if candidate and candidate.active:
                return candidate
        return None

    def _mark_eliminations_and_winner(self) -> list[str]:
        eliminated_ids: list[str] = []
        for player in self.players:
            should_be_eliminated = len(player.draw_pile) == 0
            if should_be_eliminated and not player.eliminated:
                player.eliminated = True
                eliminated_ids.append(player.id)
                self.log.append(f"{player.nickname}님은 카드가 없어 관전합니다.")
            elif not should_be_eliminated and player.eliminated:
                player.eliminated = False

        active = self._active_players()
        if len(active) == 1 and self.state in (PLAYING, PAUSED_DISCONNECT):
            self.winner_id = active[0].id
            self.current_player_id = None
            self.state = GAME_OVER
            self.log.append(f"{active[0].nickname}님이 승리했습니다!")
        return eliminated_ids

    def _ensure_current_player_active(self) -> None:
        if self.state != PLAYING or self.current_player_id is None:
            return
        current = self._require_player(self.current_player_id)
        if not current.active:
            next_player = self._next_active_after(current.seat)
            self.current_player_id = next_player.id if next_player else None

    def reveal_card(self, player_id: str, *, now: float | None = None) -> dict:
        with self.action_lock:
            moment = time.monotonic() if now is None else now
            if self.state == PAUSED_DISCONNECT:
                raise GameError("재접속을 기다리는 동안에는 카드를 뒤집을 수 없어요.", "paused")
            if self.state != PLAYING:
                raise GameError("지금은 카드를 뒤집을 수 없어요.", "not_playing")
            if moment < self.ring_guard_until:
                raise GameError("종 판정을 마치는 중이에요.", "bell_resolving")
            player = self._require_player(player_id)
            if not player.connected:
                raise GameError("연결 상태를 확인해주세요.")
            if player.id != self.current_player_id:
                raise GameError("아직 내 차례가 아니에요.", "not_your_turn")
            if not player.active:
                raise GameError("관전 중에는 카드를 뒤집을 수 없어요.", "eliminated")
            # Keep an exact-five board stable until a player rings, even when
            # a reveal request reaches the room lock before the bell request.
            if self.has_exact_five():
                raise GameError("먼저 종을 쳐주세요. 종 판정 후 다음 카드를 뒤집을 수 있어요.", "awaiting_bell")
            if moment < self.reveal_allowed_at:
                raise GameError("새 카드가 모두에게 보일 때까지 잠깐만 기다려주세요.", "settling")

            card = player.draw_pile.popleft()
            player.face_up.append(card)
            self.board_version += 1
            self.log.append(f"{player.nickname}님이 카드를 뒤집었습니다.")
            eliminated_ids = self._mark_eliminations_and_winner()
            if self.state == PLAYING:
                next_player = self._next_active_after(player.seat)
                self.current_player_id = next_player.id if next_player else None
                if next_player:
                    self.log.append(f"{next_player.nickname}님의 차례입니다.")
                self.reveal_allowed_at = moment + MIN_REVEAL_SETTLE_SECONDS
            self.assert_integrity()
            return {
                "status": "revealed",
                "player_id": player.id,
                "card": card.public(),
                "next_player_id": self.current_player_id,
                "eliminated_ids": eliminated_ids,
                "board_version": self.board_version,
                "game_over": self.state == GAME_OVER,
            }

    def _clockwise_active_recipients(self, ringer: Player) -> list[Player]:
        recipients: list[Player] = []
        for offset in range(1, ROOM_CAPACITY + 1):
            seat = (ringer.seat + offset) % ROOM_CAPACITY
            candidate = next((p for p in self.players if p.seat == seat), None)
            if candidate and candidate.id != ringer.id and candidate.active:
                recipients.append(candidate)
        return recipients

    def ring_bell(self, player_id: str, *, now: float | None = None) -> dict:
        with self.action_lock:
            moment = time.monotonic() if now is None else now
            if self.state == PAUSED_DISCONNECT:
                return {"status": "ignored", "reason": "paused", "message": "재접속을 기다리는 중이에요."}
            if self.state != PLAYING:
                return {"status": "ignored", "reason": "not_playing", "message": "지금은 종을 칠 수 없어요."}
            player = self._require_player(player_id)
            if not player.connected or not player.active:
                return {"status": "ignored", "reason": "eliminated", "message": "관전 중에는 종을 칠 수 없어요."}
            if moment - player.last_ring_at < PLAYER_RING_DEBOUNCE_SECONDS:
                return {"status": "ignored", "reason": "spam", "message": "종은 한 번씩 눌러주세요."}
            if moment < self.ring_guard_until:
                message = "조금 늦었어요!" if self.last_bell_was_correct else "이미 종이 처리되었습니다."
                return {"status": "too_late", "reason": "bell_guard", "message": message}

            player.last_ring_at = moment
            self.ring_guard_until = moment + RING_RESOLUTION_COOLDOWN_SECONDS
            self.reveal_allowed_at = max(self.reveal_allowed_at, self.ring_guard_until)
            is_correct = self.has_exact_five()
            self.last_bell_was_correct = is_correct
            self.log.append(f"🔔 {player.nickname}님이 종을 쳤습니다!")

            if is_correct:
                collected: list[Card] = []
                for owner in sorted(self.players, key=lambda item: item.seat):
                    collected.extend(owner.face_up)
                    owner.face_up.clear()
                player.draw_pile.extend(collected)
                player.eliminated = False
                self.current_player_id = player.id
                self.board_version += 1
                self.log.append("정답!")
                self.log.append(f"{player.nickname}님이 공개 카드 {len(collected)}장을 가져갑니다.")
                eliminated_ids = self._mark_eliminations_and_winner()
                self.assert_integrity()
                return {
                    "status": "correct",
                    "player_id": player.id,
                    "collected_count": len(collected),
                    "eliminated_ids": eliminated_ids,
                    "board_version": self.board_version,
                    "game_over": self.state == GAME_OVER,
                }

            recipients = self._clockwise_active_recipients(player)
            transfers: list[dict[str, str]] = []
            for recipient in recipients:
                if not player.draw_pile:
                    break
                hidden_card = player.draw_pile.popleft()
                recipient.draw_pile.append(hidden_card)
                transfers.append({"from_player_id": player.id, "to_player_id": recipient.id})
            if transfers:
                self.board_version += 1
            self.log.append(f"{player.nickname}님이 종을 잘못 눌렀습니다.")
            if transfers:
                self.log.append(f"{player.nickname}님이 다른 플레이어에게 카드 {len(transfers)}장을 줍니다.")
            eliminated_ids = self._mark_eliminations_and_winner()
            self._ensure_current_player_active()
            self.assert_integrity()
            return {
                "status": "wrong",
                "player_id": player.id,
                "transfer_count": len(transfers),
                "recipient_ids": [transfer["to_player_id"] for transfer in transfers],
                "eliminated_ids": eliminated_ids,
                "board_version": self.board_version,
                "game_over": self.state == GAME_OVER,
            }

    def add_reaction(self, player_id: str, reaction: str, *, now: float | None = None) -> dict:
        allowed = ("ㅋㅋ", "헉", "아깝다!", "뭐야!", "굿", "😎")
        with self.action_lock:
            if reaction not in allowed:
                raise GameError("지원하지 않는 반응이에요.")
            player = self._require_player(player_id)
            moment = time.monotonic() if now is None else now
            if moment - player.last_reaction_at < REACTION_COOLDOWN_SECONDS:
                raise GameError("반응은 2초에 한 번 보낼 수 있어요.", "reaction_rate_limit")
            player.last_reaction_at = moment
            return {"player_id": player.id, "reaction": reaction}

    def return_to_lobby(self, requester_id: str) -> None:
        with self.action_lock:
            if requester_id != self.host_id:
                raise GameError("방장만 대기실로 돌아갈 수 있어요.", "host_only")
            if self.state != GAME_OVER:
                raise GameError("게임이 끝난 뒤 대기실로 돌아갈 수 있어요.")
            self.state = LOBBY
            self.current_player_id = None
            self.dealer_id = None
            self.winner_id = None
            self.board_version = 0
            self.ring_guard_until = 0.0
            for player in self.players:
                player.draw_pile.clear()
                player.face_up.clear()
                player.eliminated = False
                player.ready = False
            self.log.clear()
            self.log.append("대기실로 돌아왔습니다.")

    def serialize(self, viewer_id: str | None = None, *, now: float | None = None) -> dict:
        with self.action_lock:
            moment = time.monotonic() if now is None else now
            players = []
            for player in sorted(self.players, key=lambda item: item.seat):
                players.append(
                    {
                        "id": player.id,
                        "nickname": player.nickname,
                        "avatar": player.avatar,
                        "seat": player.seat,
                        "connected": player.connected,
                        "ready": player.ready,
                        "is_host": player.id == self.host_id,
                        "eliminated": player.eliminated,
                        "remaining_card_count": len(player.draw_pile),
                        "face_up_count": len(player.face_up),
                        "visible_card": player.face_up[-1].public() if player.face_up else None,
                    }
                )
            disconnected = [p.id for p in self.players if not p.connected]
            current = self.player_by_id(self.current_player_id) if self.current_player_id else None
            waiting_name = None
            if self.state == PAUSED_DISCONNECT and disconnected:
                waiting_name = self._require_player(disconnected[0]).nickname
            return {
                "room_code": self.code,
                "state": self.state,
                "board_version": self.board_version,
                "host_id": self.host_id,
                "viewer_id": viewer_id,
                "current_player_id": self.current_player_id,
                "current_player_name": current.nickname if current else None,
                "dealer_id": self.dealer_id,
                "winner_id": self.winner_id,
                "players": players,
                "player_count": len(self.players),
                "min_players": MIN_PLAYERS,
                "capacity": ROOM_CAPACITY,
                "can_start": self.can_start(),
                "reveal_blocked_for_bell": self.state in (PLAYING, PAUSED_DISCONNECT) and self.has_exact_five(),
                "reveal_wait_ms": max(0, round((self.reveal_allowed_at - moment) * 1000)),
                "bell_wait_ms": max(0, round((self.ring_guard_until - moment) * 1000)),
                "waiting_for_name": waiting_name,
                "logs": list(self.log),
            }

    def all_cards(self) -> list[Card]:
        cards: list[Card] = []
        for player in self.players:
            cards.extend(player.draw_pile)
            cards.extend(player.face_up)
        return cards

    def assert_integrity(self) -> None:
        cards = self.all_cards()
        if self.state != LOBBY:
            if len(cards) != 56:
                raise AssertionError(f"card conservation failed: {len(cards)}")
            ids = [card.id for card in cards]
            if len(ids) != len(set(ids)):
                raise AssertionError("duplicate physical card ownership")
        if any(len(player.draw_pile) < 0 for player in self.players):
            raise AssertionError("negative card count")


class RoomManager:
    ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

    def __init__(self) -> None:
        self.rooms: dict[str, Room] = {}
        self.lock = threading.RLock()

    def create_room(self) -> Room:
        with self.lock:
            for _ in range(100):
                code = "".join(secrets.choice(self.ALPHABET) for _ in range(4))
                if code not in self.rooms:
                    room = Room(code)
                    self.rooms[code] = room
                    return room
            raise GameError("방 코드를 만들지 못했습니다. 잠시 후 다시 시도해주세요.")

    def get(self, code: str) -> Room | None:
        return self.rooms.get((code or "").strip().upper())

    def require(self, code: str) -> Room:
        room = self.get(code)
        if not room:
            raise GameError("방을 찾을 수 없습니다. 코드를 확인해주세요.", "room_not_found")
        return room


def count_distribution(cards: Iterable[Card]) -> Counter:
    return Counter((card.fruit, card.count) for card in cards)
