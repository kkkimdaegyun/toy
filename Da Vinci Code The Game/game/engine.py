from __future__ import annotations

import random
import uuid

from .models import Room, Tile
from .utils import sort_tiles


class GameError(ValueError):
    pass


class GameEngine:
    """All rules and hidden information live on this server-side engine."""

    @staticmethod
    def create_deck() -> list[Tile]:
        return [
            Tile(id=uuid.uuid4().hex, color=color, value=value)
            for color in ("black", "white")
            for value in range(12)
        ]

    def start_game(self, room: Room) -> None:
        if len(room.players) < 2:
            raise GameError("게임을 시작하려면 최소 두 명이 필요합니다.")
        room.phase = "game"
        room.deck = self.create_deck()
        random.shuffle(room.deck)
        room.turn_order = list(room.players.keys())
        random.shuffle(room.turn_order)
        room.current_turn_index = 0
        room.current_drawn_tile_id = None
        room.winner_player_id = None
        room.event_log = ["게임이 시작되었습니다."]
        for player in room.players.values():
            player.tiles = [room.deck.pop() for _ in range(4)]
            player.tiles = sort_tiles(player.tiles)
            player.eliminated = False
        room.event_log.append(f"{self.current_player(room).nickname} 님이 먼저 시작합니다.")
        self.begin_turn(room)

    def current_player(self, room: Room):
        return room.players[room.turn_order[room.current_turn_index]]

    def begin_turn(self, room: Room) -> None:
        player = self.current_player(room)
        if not player.connected:
            room.turn_phase = "paused"
            room.event_log.append(f"{player.nickname} 님의 재접속을 기다리고 있습니다.")
            return
        room.current_drawn_tile_id = None
        if room.deck:
            tile = room.deck.pop()
            player.tiles.append(tile)
            player.tiles = sort_tiles(player.tiles)
            room.current_drawn_tile_id = tile.id
            room.event_log.append(f"{player.nickname} 님이 타일을 한 장 뽑았습니다.")
        else:
            room.event_log.append("덱이 비어 있어 이번 턴에는 타일을 뽑지 않습니다.")
        room.turn_phase = "guessing"

    def resume_if_current_player(self, room: Room, player_id: str) -> bool:
        if room.phase == "game" and room.turn_phase == "paused" and self.current_player(room).id == player_id:
            # A refresh must resume the existing turn, not grant a second draw.
            room.turn_phase = "guessing"
            room.event_log.append(f"{self.current_player(room).nickname} 님의 턴이 재개되었습니다.")
            return True
        return False

    def _tile(self, player, tile_id: str) -> Tile:
        for tile in player.tiles:
            if tile.id == tile_id:
                return tile
        raise GameError("선택한 타일을 찾을 수 없습니다.")

    def _assert_guess(self, room: Room, actor_id: str, target_player_id: str, target_tile_id: str, value) -> tuple:
        if room.phase != "game" or room.turn_phase != "guessing":
            raise GameError("지금은 추리할 수 없습니다.")
        if actor_id != self.current_player(room).id:
            raise GameError("내 차례가 아닙니다.")
        actor = room.players[actor_id]
        if actor.eliminated:
            raise GameError("탈락한 플레이어는 추리할 수 없습니다.")
        if target_player_id not in room.players or target_player_id == actor_id:
            raise GameError("상대방의 숨겨진 타일을 선택하세요.")
        target_player = room.players[target_player_id]
        if target_player.eliminated:
            raise GameError("해당 플레이어는 이미 탈락했습니다.")
        target = self._tile(target_player, target_tile_id)
        if target.revealed:
            raise GameError("이미 공개된 타일입니다.")
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 11:
            raise GameError("0부터 11 사이의 숫자를 선택하세요.")
        return actor, target_player, target

    def make_guess(self, room: Room, actor_id: str, target_player_id: str, target_tile_id: str, value: int) -> dict:
        actor, target_player, target = self._assert_guess(room, actor_id, target_player_id, target_tile_id, value)
        color = "검정" if target.color == "black" else "흰색"
        room.event_log.append(f"{actor.nickname} 님이 {target_player.nickname} 님의 {color} 타일을 {value}로 추리했습니다.")
        if target.value == value:
            target.revealed = True
            room.event_log.append(f"정답! {target_player.nickname} 님의 {color} {target.value} 타일이 공개되었습니다.")
            self.update_eliminations(room)
            if self.check_winner(room):
                return {"correct": True, "ended": True, "message": "정답입니다! 게임이 종료되었습니다."}
            room.turn_phase = "decision"
            return {"correct": True, "ended": False, "message": f"정답! {color} {target.value} 타일이 공개되었습니다."}

        room.event_log.append(f"{actor.nickname} 님이 틀렸습니다.")
        revealed = self.reveal_penalty_tile(room, actor)
        if revealed:
            revealed_color = "검정" if revealed.color == "black" else "흰색"
            room.event_log.append(f"{actor.nickname} 님이 뽑은 {revealed_color} {revealed.value} 타일이 공개되었습니다.")
        self.update_eliminations(room)
        if self.check_winner(room):
            return {"correct": False, "ended": True, "message": "틀렸습니다. 게임이 종료되었습니다."}
        self.advance_turn(room)
        return {"correct": False, "ended": False, "message": "틀렸습니다! 새로 뽑은 타일이 공개되었습니다."}

    def reveal_penalty_tile(self, room: Room, player) -> Tile | None:
        if room.current_drawn_tile_id:
            tile = self._tile(player, room.current_drawn_tile_id)
        else:
            hidden = [tile for tile in player.tiles if not tile.revealed]
            tile = random.choice(hidden) if hidden else None
        if tile:
            tile.revealed = True
        return tile

    def continue_turn(self, room: Room, actor_id: str) -> None:
        if room.phase != "game" or room.turn_phase != "decision" or self.current_player(room).id != actor_id:
            raise GameError("지금은 계속 추리할 수 없습니다.")
        room.turn_phase = "guessing"
        room.event_log.append(f"{room.players[actor_id].nickname} 님이 계속 추리합니다.")

    def end_turn(self, room: Room, actor_id: str) -> None:
        if room.phase != "game" or room.turn_phase != "decision" or self.current_player(room).id != actor_id:
            raise GameError("지금은 턴을 끝낼 수 없습니다.")
        room.event_log.append(f"{room.players[actor_id].nickname} 님이 턴을 끝냈습니다.")
        self.advance_turn(room)

    def update_eliminations(self, room: Room) -> None:
        for player in room.players.values():
            if player.tiles and all(tile.revealed for tile in player.tiles) and not player.eliminated:
                player.eliminated = True
                room.event_log.append(f"{player.nickname} 님이 탈락했습니다.")

    def check_winner(self, room: Room) -> bool:
        survivors = [player for player in room.players.values() if not player.eliminated]
        if len(survivors) == 1:
            room.phase = "finished"
            room.turn_phase = "waiting"
            room.current_drawn_tile_id = None
            room.winner_player_id = survivors[0].id
            room.event_log.append(f"{survivors[0].nickname} 님이 승리했습니다!")
            return True
        return False

    def advance_turn(self, room: Room) -> None:
        room.current_drawn_tile_id = None
        active_ids = {player.id for player in room.players.values() if not player.eliminated}
        if not active_ids:
            room.phase, room.turn_phase = "finished", "waiting"
            return
        for _ in range(len(room.turn_order)):
            room.current_turn_index = (room.current_turn_index + 1) % len(room.turn_order)
            if room.turn_order[room.current_turn_index] in active_ids:
                room.event_log.append(f"{self.current_player(room).nickname} 님의 턴입니다.")
                self.begin_turn(room)
                return

    def reset_to_lobby(self, room: Room) -> None:
        room.phase = "lobby"
        room.deck.clear()
        room.turn_order.clear()
        room.current_turn_index = 0
        room.current_drawn_tile_id = None
        room.turn_phase = "waiting"
        room.winner_player_id = None
        room.event_log = ["대기실로 돌아왔습니다."]
        for player in room.players.values():
            player.tiles.clear()
            player.eliminated = False

    def public_view(self, room: Room, viewer_id: str) -> dict:
        """Return a view that intentionally omits every hidden opponent value."""
        viewer = room.players[viewer_id]
        players = []
        for player in room.players.values():
            own = player.id == viewer_id
            tiles = []
            for tile in player.tiles:
                tile_data = {"id": tile.id, "color": tile.color, "revealed": tile.revealed}
                if own or tile.revealed:
                    tile_data["value"] = tile.value
                tiles.append(tile_data)
            players.append({
                "id": player.id, "nickname": player.nickname, "host": player.host,
                "connected": player.connected, "eliminated": player.eliminated, "tiles": tiles,
            })
        current = self.current_player(room) if room.phase == "game" and room.turn_order else None
        return {
            "roomCode": room.code, "phase": room.phase, "selfId": viewer_id,
            "hostPlayerId": room.host_player_id, "players": players,
            "currentPlayerId": current.id if current else None,
            "turnPhase": room.turn_phase, "deckCount": len(room.deck),
            "winnerPlayerId": room.winner_player_id, "eventLog": room.event_log[-18:],
        }
