from __future__ import annotations

import os
import socket
import threading
from typing import Any

from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room as socket_join_room

from game_engine import GAME_OVER, GameError, Room, RoomManager


PORT = 1337

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("FRUIT_BELL_SECRET", os.urandom(32))
socketio = SocketIO(
    app,
    async_mode="threading",
    cors_allowed_origins=None,
    ping_interval=10,
    ping_timeout=20,
    logger=False,
    engineio_logger=False,
)

rooms = RoomManager()
connections: dict[str, tuple[str, str]] = {}
connections_lock = threading.RLock()


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/health")
def health():
    return {"ok": True, "service": "과일 땡!", "port": PORT}


def clean_payload(data: Any) -> dict:
    return data if isinstance(data, dict) else {}


def send_error(error: GameError | Exception) -> None:
    if isinstance(error, GameError):
        emit("error_message", {"message": error.message, "code": error.code})
    else:
        app.logger.exception("Socket handler failed", exc_info=error)
        emit("error_message", {"message": "잠시 문제가 생겼어요. 다시 시도해주세요.", "code": "server_error"})


def remember_connection(sid: str, room: Room, player_id: str) -> None:
    with connections_lock:
        previous = next(
            (old_sid for old_sid, value in connections.items() if value == (room.code, player_id) and old_sid != sid),
            None,
        )
        if previous:
            connections.pop(previous, None)
        connections[sid] = (room.code, player_id)


def current_membership() -> tuple[Room, str]:
    with connections_lock:
        membership = connections.get(request.sid)
    if not membership:
        raise GameError("먼저 방에 들어가주세요.", "not_in_room")
    room_code, player_id = membership
    return rooms.require(room_code), player_id


def broadcast_state(room: Room) -> None:
    socketio.emit("room_state", room.serialize(), to=room.code)


def establish_session(room: Room, player) -> None:
    socket_join_room(room.code)
    remember_connection(request.sid, room, player.id)
    emit(
        "session_established",
        {
            "room_code": room.code,
            "player_id": player.id,
            "reconnect_token": player.reconnect_token,
            "nickname": player.nickname,
            "avatar": player.avatar,
        },
    )


@socketio.on("create_room")
def handle_create_room(data=None):
    try:
        payload = clean_payload(data)
        room = rooms.create_room()
        player = room.add_player(payload.get("nickname", ""), payload.get("avatar", ""), request.sid)
        establish_session(room, player)
        broadcast_state(room)
    except Exception as error:
        send_error(error)


@socketio.on("join_room")
def handle_join_room(data=None):
    try:
        payload = clean_payload(data)
        room = rooms.require(payload.get("room_code", ""))
        player = room.add_player(payload.get("nickname", ""), payload.get("avatar", ""), request.sid)
        establish_session(room, player)
        broadcast_state(room)
    except Exception as error:
        send_error(error)


@socketio.on("reconnect_player")
def handle_reconnect(data=None):
    try:
        payload = clean_payload(data)
        room = rooms.require(payload.get("room_code", ""))
        player = room.reconnect(payload.get("reconnect_token", ""), request.sid)
        establish_session(room, player)
        emit("reconnect_result", {"ok": True, "message": "게임에 다시 연결되었습니다."})
        broadcast_state(room)
    except Exception as error:
        emit("reconnect_result", {"ok": False})
        send_error(error)


@socketio.on("set_ready")
def handle_set_ready(data=None):
    try:
        room, player_id = current_membership()
        room.set_ready(player_id, bool(clean_payload(data).get("ready", True)))
        broadcast_state(room)
    except Exception as error:
        send_error(error)


@socketio.on("select_character")
def handle_select_character(data=None):
    try:
        room, player_id = current_membership()
        room.select_character(player_id, clean_payload(data).get("avatar", ""))
        broadcast_state(room)
    except Exception as error:
        send_error(error)


@socketio.on("start_game")
def handle_start_game():
    try:
        room, player_id = current_membership()
        with room.action_lock:
            result = room.start_game(player_id)
            socketio.emit("game_started", result, to=room.code)
            broadcast_state(room)
    except Exception as error:
        send_error(error)


@socketio.on("reveal_card")
def handle_reveal_card():
    try:
        room, player_id = current_membership()
        with room.action_lock:
            result = room.reveal_card(player_id)
            socketio.emit("card_revealed", result, to=room.code)
            broadcast_state(room)
            if result["game_over"]:
                socketio.emit("game_ended", {"winner_id": room.winner_id}, to=room.code)
    except Exception as error:
        send_error(error)


@socketio.on("ring_bell")
def handle_ring_bell():
    try:
        room, player_id = current_membership()
        with room.action_lock:
            result = room.ring_bell(player_id)
            if result["status"] in ("ignored", "too_late"):
                emit("bell_feedback", result)
                return
            socketio.emit("bell_result", result, to=room.code)
            broadcast_state(room)
            if result["game_over"]:
                socketio.emit("game_ended", {"winner_id": room.winner_id}, to=room.code)
    except Exception as error:
        send_error(error)


@socketio.on("send_reaction")
def handle_reaction(data=None):
    try:
        room, player_id = current_membership()
        result = room.add_reaction(player_id, clean_payload(data).get("reaction", ""))
        socketio.emit("reaction", result, to=room.code)
    except Exception as error:
        send_error(error)


@socketio.on("request_rematch")
def handle_rematch():
    try:
        room, player_id = current_membership()
        with room.action_lock:
            result = room.start_game(player_id, rematch=True)
            socketio.emit("game_started", result, to=room.code)
            broadcast_state(room)
    except Exception as error:
        send_error(error)


@socketio.on("return_to_lobby")
def handle_return_to_lobby():
    try:
        room, player_id = current_membership()
        with room.action_lock:
            room.return_to_lobby(player_id)
            broadcast_state(room)
    except Exception as error:
        send_error(error)


@socketio.on("disconnect")
def handle_disconnect():
    with connections_lock:
        membership = connections.pop(request.sid, None)
    if not membership:
        return
    room = rooms.get(membership[0])
    if not room:
        return
    room.disconnect(request.sid)
    broadcast_state(room)


def detect_lan_ipv4() -> str | None:
    candidates: list[str] = []
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            address = info[4][0]
            if not address.startswith("127.") and address != "0.0.0.0":
                candidates.append(address)
    except OSError:
        pass

    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.settimeout(0.2)
        probe.connect(("10.255.255.255", 1))
        address = probe.getsockname()[0]
        if not address.startswith("127."):
            candidates.insert(0, address)
        probe.close()
    except OSError:
        pass

    for address in candidates:
        if address.startswith(("10.", "192.168.", "172.")):
            return address
    return candidates[0] if candidates else None


def print_startup_banner() -> None:
    lan_ip = detect_lan_ipv4()
    line = "=" * 48
    print(f"\n{line}")
    print("과일 땡! - 사내 멀티플레이")
    print(line)
    print(f"\n내 PC:\nhttp://127.0.0.1:{PORT}")
    if lan_ip:
        print(f"\n사내 접속 주소:\nhttp://{lan_ip}:{PORT}")
    else:
        print("\n사내 접속 주소를 자동으로 찾지 못했습니다.")
        print("ipconfig 명령어에서 IPv4 주소를 확인해주세요.")
    print("\n게임 서버가 실행되었습니다.")
    print("SPACE = 종 치기\n")


if __name__ == "__main__":
    print_startup_banner()
    socketio.run(
        app,
        host="0.0.0.0",
        port=PORT,
        debug=True,
        use_reloader=False,
        allow_unsafe_werkzeug=True,
    )
