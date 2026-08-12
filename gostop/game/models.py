"""Core mutable state: Player and Room.

These objects hold state only.  All rule enforcement lives in
``betting.py`` (one betting phase) and ``engine.py`` (the round state machine).
Nothing here ever touches Flask or Socket.IO.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from . import config
from .deck import Card, Deck
from .hands import Hand

# --- player status ----------------------------------------------------------

STATUS_LABELS = {
    "ready": "준비",
    "wait": "대기",
    "turn": "내 차례",
    "check": "체크",
    "bet": "베팅",
    "call": "콜",
    "raise": "레이즈",
    "die": "다이",
    "discarding": "카드 선택 중",
    "discarded": "선택 완료",
    "spectating": "관전 중",
    "disconnected": "연결 끊김",
    "winner": "승리!",
}


@dataclass
class Player:
    pid: str
    token: str
    nickname: str
    character: str
    seat: int = 0

    # --- session-long state -------------------------------------------------
    chips: int = config.STARTING_CHIPS
    loan_count: int = 0
    automatic_last_place: bool = False
    connected: bool = True
    sid: str | None = None
    joined_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    rounds_won: int = 0

    # --- per-round state ----------------------------------------------------
    in_round: bool = False
    folded: bool = False
    spectating: bool = False
    cards: list = field(default_factory=list)
    discarded: Card | None = None
    round_contrib: int = 0
    phase_contrib: int = 0
    last_action: str | None = None
    status_key: str = "ready"
    hand: Hand | None = None
    revealed: bool = False

    # --- ephemeral ----------------------------------------------------------
    last_reaction_at: float = 0.0
    dai_confirm_disabled: bool = False

    # ------------------------------------------------------------------ #
    @property
    def active(self) -> bool:
        """Still competing for this round's pot."""
        return self.in_round and not self.folded

    @property
    def status_label(self) -> str:
        if not self.connected:
            return STATUS_LABELS["disconnected"]
        return STATUS_LABELS.get(self.status_key, "대기")

    def reset_for_round(self) -> None:
        self.in_round = False
        self.folded = False
        self.spectating = False
        self.cards = []
        self.discarded = None
        self.round_contrib = 0
        self.phase_contrib = 0
        self.last_action = None
        self.status_key = "wait"
        self.hand = None
        self.revealed = False

    def reset_phase_contrib(self) -> None:
        self.phase_contrib = 0

    def pay(self, amount: int) -> int:
        """Move chips from the player into the pot.  Never goes negative."""
        amount = max(0, min(int(amount), self.chips))
        self.chips -= amount
        self.round_contrib += amount
        self.phase_contrib += amount
        return amount

    def can_afford(self, amount: int) -> bool:
        return self.chips >= amount

    @property
    def can_loan(self) -> bool:
        return self.loan_count < config.MAX_LOANS

    def take_loan(self) -> dict:
        """Apply one virtual loan.  Caller must have checked ``can_loan``."""
        self.loan_count += 1
        self.chips += config.LOAN_NET
        if self.loan_count >= config.PENALTY_LOAN_INDEX:
            self.automatic_last_place = True
        return {
            "amount": config.LOAN_AMOUNT,
            "interest": config.LOAN_INTEREST,
            "net": config.LOAN_NET,
            "loanCount": self.loan_count,
            "autoLast": self.automatic_last_place,
        }


@dataclass
class Room:
    code: str
    host_pid: str | None = None

    players: dict = field(default_factory=dict)     # pid -> Player
    seats: list = field(default_factory=list)       # ordered pids
    tokens: dict = field(default_factory=dict)      # token -> pid

    phase: str = config.PHASE_LOBBY
    round_no: int = 0
    dealer_pid: str | None = None

    deck: Deck | None = None
    pot: int = 0

    # --- current betting phase ---------------------------------------------
    current_bet: int = 0
    raise_count: int = 0
    turn_pid: str | None = None
    turn_seat: int = -1
    needs_action: set = field(default_factory=set)

    # --- discard phase ------------------------------------------------------
    pending_discard: set = field(default_factory=set)

    log: list = field(default_factory=list)
    fx: list = field(default_factory=list)          # animation events, drained per broadcast
    result: dict | None = None
    final: dict | None = None
    started: bool = False
    notice: str | None = None                       # transient headline for everyone
    hooks: object | None = None                     # injected scheduler/notifier

    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)
    fx_seq: int = 0
    state_seq: int = 0

    # ------------------------------------------------------------------ #
    # membership
    # ------------------------------------------------------------------ #
    def touch(self) -> None:
        self.last_active = time.time()

    @property
    def player_list(self) -> list:
        """Players in seat order."""
        return [self.players[pid] for pid in self.seats if pid in self.players]

    @property
    def size(self) -> int:
        return len(self.seats)

    @property
    def is_full(self) -> bool:
        return self.size >= config.MAX_PLAYERS

    def get(self, pid) -> Player | None:
        return self.players.get(pid)

    def by_token(self, token) -> Player | None:
        pid = self.tokens.get(token)
        return self.players.get(pid) if pid else None

    def by_sid(self, sid) -> Player | None:
        for p in self.players.values():
            if p.sid == sid:
                return p
        return None

    def add_player(self, player: Player) -> None:
        player.seat = len(self.seats)
        self.players[player.pid] = player
        self.seats.append(player.pid)
        self.tokens[player.token] = player.pid
        if self.host_pid is None:
            self.host_pid = player.pid
        self.touch()

    def remove_player(self, pid: str) -> None:
        player = self.players.pop(pid, None)
        if player is not None:
            self.tokens.pop(player.token, None)
        if pid in self.seats:
            self.seats.remove(pid)
        self.needs_action.discard(pid)
        self.pending_discard.discard(pid)
        for i, spid in enumerate(self.seats):
            self.players[spid].seat = i
        if self.host_pid == pid:
            self.host_pid = self.seats[0] if self.seats else None
        if self.dealer_pid == pid:
            self.dealer_pid = self.seats[0] if self.seats else None
        if self.turn_pid == pid:
            self.turn_pid = None
        self.touch()

    def used_characters(self, exclude_pid=None) -> set:
        return {
            p.character for p in self.players.values()
            if p.character and p.pid != exclude_pid
        }

    def nickname_taken(self, key_fn, nickname, exclude_pid=None) -> bool:
        wanted = key_fn(nickname)
        return any(
            key_fn(p.nickname) == wanted
            for p in self.players.values()
            if p.pid != exclude_pid
        )

    # ------------------------------------------------------------------ #
    # round helpers
    # ------------------------------------------------------------------ #
    @property
    def active_players(self) -> list:
        return [p for p in self.player_list if p.active]

    @property
    def round_players(self) -> list:
        return [p for p in self.player_list if p.in_round]

    def seat_of(self, pid) -> int:
        try:
            return self.seats.index(pid)
        except ValueError:
            return -1

    def seat_order_from(self, start_seat: int) -> list:
        """Pids clockwise starting AT ``start_seat``."""
        n = len(self.seats)
        if n == 0:
            return []
        start = start_seat % n
        return [self.seats[(start + i) % n] for i in range(n)]

    # ------------------------------------------------------------------ #
    # logging
    # ------------------------------------------------------------------ #
    def log_line(self, text: str) -> None:
        """Append one Korean log line.  Never include a hidden card number."""
        if not text:
            return
        self.log.append({"seq": len(self.log) + 1, "text": text})
        if len(self.log) > config.LOG_MAX_ENTRIES:
            del self.log[: len(self.log) - config.LOG_MAX_ENTRIES]

    def next_fx(self) -> int:
        self.fx_seq += 1
        return self.fx_seq

    def push_fx(self, kind: str, **payload) -> None:
        """Queue one animation event for the next broadcast."""
        payload["type"] = kind
        payload["seq"] = self.next_fx()
        self.fx.append(payload)

    def drain_fx(self) -> list:
        out = self.fx
        self.fx = []
        return out
