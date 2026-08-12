from game.engine import CasinoGame
from game.utils import generate_room_code, generate_reconnect_token
from game.config import MAX_PLAYERS

class Room:
    def __init__(self, code: str, host_id: str, game_mode: str = 'dice'):
        self.code = code
        self.host_id = host_id
        self.players = {}
        self.game = None
        self.reconnect_tokens = {}
        self.game_mode = game_mode
        self.seats = [False] * MAX_PLAYERS
        
    def generate_code(self) -> str:
        return self.code
        
    def add_player(self, player_id: str, nickname: str, color: str) -> int:
        if self.is_full() or player_id in self.players:
            return -1
        seat = self.seats.index(False)
        self.seats[seat] = True
        self.players[player_id] = {'nickname': nickname, 'color': color, 'seat': seat}
        return seat
        
    def remove_player(self, player_id: str):
        if player_id in self.players:
            seat = self.players[player_id]['seat']
            self.seats[seat] = False
            del self.players[player_id]
            
    def is_full(self) -> bool:
        return not (False in self.seats)
        
    def get_available_colors(self) -> list:
        used = [p['color'] for p in self.players.values()]
        from game.config import PLAYER_COLORS
        return [c for c in PLAYER_COLORS if c not in used]
        
    def create_game(self) -> CasinoGame:
        self.game = CasinoGame(self.code, self.game_mode)
        for pid, p in self.players.items():
            self.game.add_player(pid, p['nickname'], p['color'], p['seat'])
        return self.game
        
    def generate_reconnect_token(self, player_id: str) -> str:
        token = generate_reconnect_token()
        self.reconnect_tokens[token] = player_id
        return token
        
    def get_player_by_token(self, token: str):
        return self.reconnect_tokens.get(token)
        
    def to_dict(self):
        return {
            'code': self.code,
            'host_id': self.host_id,
            'players': self.players,
            'game_mode': self.game_mode
        }

class RoomManager:
    def __init__(self):
        self.rooms = {}
        self.player_rooms = {}
        
    def create_room(self, host_id: str, nickname: str, color: str, game_mode: str = 'dice') -> Room:
        code = generate_room_code()
        while code in self.rooms:
            code = generate_room_code()
        room = Room(code, host_id, game_mode)
        room.add_player(host_id, nickname, color)
        self.rooms[code] = room
        self.player_rooms[host_id] = code
        return room
        
    def join_room(self, code: str, player_id: str, nickname: str, color: str) -> Room:
        if code in self.rooms:
            room = self.rooms[code]
            if room.add_player(player_id, nickname, color) != -1:
                self.player_rooms[player_id] = code
                return room
        return None
        
    def get_room(self, code: str) -> Room:
        return self.rooms.get(code)
        
    def get_player_room(self, player_id: str) -> Room:
        code = self.player_rooms.get(player_id)
        if code:
            return self.rooms.get(code)
        return None
        
    def remove_player(self, player_id: str):
        code = self.player_rooms.get(player_id)
        if code and code in self.rooms:
            room = self.rooms[code]
            room.remove_player(player_id)
            del self.player_rooms[player_id]
            if not room.players:
                del self.rooms[code]
