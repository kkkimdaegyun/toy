from __future__ import annotations

import threading

from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit

from game.engine import GameEngine, GameError
from game.rooms import RoomError, RoomManager
from game.utils import preferred_lan_ip


app = Flask(__name__)
app.config["SECRET_KEY"] = "number-code-local-lan-game"
socketio = SocketIO(app, async_mode="threading", cors_allowed_origins="*")
rooms = RoomManager()
engine = GameEngine()
state_lock = threading.RLock()


@app.get("/")
def index():
    return render_template("index.html")


def send_error(message: str):
    emit("error_message", {"message": message})


def send_identity(room, player):
    socketio.emit("identity", {"roomCode": room.code, "token": player.token, "playerId": player.id}, to=player.socket_id)


def broadcast_state(room):
    """Each recipient gets a separate, sanitized payload. Never broadcast Room directly."""
    for player in room.players.values():
        if player.connected and player.socket_id:
            socketio.emit("state", engine.public_view(room, player.id), to=player.socket_id)


def require_player():
    return rooms.by_socket(request.sid)


@socketio.on("create_room")
def create_room(data):
    try:
        with state_lock:
            room, player = rooms.create_room((data or {}).get("nickname"), request.sid)
            send_identity(room, player)
            broadcast_state(room)
    except RoomError as error:
        send_error(str(error))


@socketio.on("join_room")
def join_room_handler(data):
    try:
        with state_lock:
            room, player = rooms.join_room((data or {}).get("roomCode"), (data or {}).get("nickname"), request.sid)
            send_identity(room, player)
            broadcast_state(room)
    except RoomError as error:
        send_error(str(error))


@socketio.on("reconnect_player")
def reconnect_player(data):
    try:
        with state_lock:
            room, player = rooms.reconnect((data or {}).get("roomCode"), (data or {}).get("token"), request.sid)
            engine.resume_if_current_player(room, player.id)
            send_identity(room, player)
            broadcast_state(room)
    except RoomError as error:
        send_error(str(error))


@socketio.on("start_game")
def start_game(_data=None):
    try:
        with state_lock:
            room, player = require_player()
            if room.host_player_id != player.id:
                raise GameError("방장만 게임을 시작할 수 있습니다.")
            if room.phase != "lobby":
                raise GameError("이미 게임이 시작되었습니다.")
            engine.start_game(room)
            broadcast_state(room)
    except (RoomError, GameError) as error:
        send_error(str(error))


@socketio.on("make_guess")
def make_guess(data):
    try:
        with state_lock:
            room, player = require_player()
            payload = data or {}
            result = engine.make_guess(room, player.id, payload.get("targetPlayerId"), payload.get("targetTileId"), payload.get("value"))
            socketio.emit("guess_feedback", result, to=player.socket_id)
            broadcast_state(room)
    except (RoomError, GameError) as error:
        send_error(str(error))


@socketio.on("continue_turn")
def continue_turn(_data=None):
    try:
        with state_lock:
            room, player = require_player()
            engine.continue_turn(room, player.id)
            broadcast_state(room)
    except (RoomError, GameError) as error:
        send_error(str(error))


@socketio.on("end_turn")
def end_turn(_data=None):
    try:
        with state_lock:
            room, player = require_player()
            engine.end_turn(room, player.id)
            broadcast_state(room)
    except (RoomError, GameError) as error:
        send_error(str(error))


@socketio.on("play_again")
def play_again(_data=None):
    try:
        with state_lock:
            room, player = require_player()
            if room.host_player_id != player.id:
                raise GameError("방장만 새 게임을 시작할 수 있습니다.")
            if room.phase != "finished":
                raise GameError("현재 게임이 끝난 뒤에 다시 시작할 수 있습니다.")
            engine.start_game(room)
            broadcast_state(room)
    except (RoomError, GameError) as error:
        send_error(str(error))


@socketio.on("return_to_lobby")
def return_to_lobby(_data=None):
    try:
        with state_lock:
            room, player = require_player()
            if room.host_player_id != player.id:
                raise GameError("방장만 모두를 대기실로 이동시킬 수 있습니다.")
            engine.reset_to_lobby(room)
            broadcast_state(room)
    except (RoomError, GameError) as error:
        send_error(str(error))


@socketio.on("disconnect")
def disconnected():
    with state_lock:
        room = rooms.disconnect(request.sid)
        if room:
            if room.phase == "game" and room.turn_order and engine.current_player(room).connected is False:
                room.turn_phase = "paused"
                room.event_log.append(f"{engine.current_player(room).nickname} 님의 재접속을 기다리고 있습니다.")
            broadcast_state(room)


def print_startup_addresses():
    lan_ip = preferred_lan_ip()
    print("\n" + "=" * 50)
    print("넘버 코드 - 사내망 멀티플레이")
    print("=" * 50)
    print("내 컴퓨터:")
    print("http://127.0.0.1:8697")
    print("\n사내망 공유 주소:")
    if lan_ip:
        print(f"http://{lan_ip}:8697")
    else:
        print("사내망 IPv4 주소를 찾지 못했습니다. ipconfig에서 IPv4 주소를 확인해주세요.")
    print("\n참가자를 기다리고 있습니다...")
    print("=" * 50 + "\n")


if __name__ == "__main__":
    print_startup_addresses()
    socketio.run(app, host="0.0.0.0", port=8697, debug=True, allow_unsafe_werkzeug=True)
