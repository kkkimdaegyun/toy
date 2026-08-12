from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Tile:
    id: str
    color: str
    value: int
    revealed: bool = False


@dataclass
class Player:
    id: str
    nickname: str
    token: str
    socket_id: Optional[str] = None
    connected: bool = True
    host: bool = False
    eliminated: bool = False
    tiles: list[Tile] = field(default_factory=list)


@dataclass
class Room:
    code: str
    players: dict[str, Player] = field(default_factory=dict)
    host_player_id: Optional[str] = None
    phase: str = "lobby"  # lobby, game, finished
    deck: list[Tile] = field(default_factory=list)
    turn_order: list[str] = field(default_factory=list)
    current_turn_index: int = 0
    current_drawn_tile_id: Optional[str] = None
    turn_phase: str = "waiting"  # waiting, guessing, decision, paused
    winner_player_id: Optional[str] = None
    event_log: list[str] = field(default_factory=list)

