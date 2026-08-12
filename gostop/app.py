"""숫자 섯다 — 사내 멀티플레이 카드 게임.

실행:
    py -m pip install -r requirements.txt
    py app.py

하나의 서버, 하나의 포트(3949)로 웹페이지와 실시간 통신을 모두 처리합니다.
"""

from __future__ import annotations

import sys
import time
import traceback

from flask import Flask, render_template, request
from flask_socketio import SocketIO

from game import config, engine, serializers, utils
from game.errors import GameError
from game.rooms import manager

app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["SECRET_KEY"] = utils.new_token()
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0     # office LAN: never serve stale JS
app.config["JSON_AS_ASCII"] = False

socketio = SocketIO(
    app,
    async_mode="threading",
    cors_allowed_origins="*",
    ping_timeout=25,
    ping_interval=10,
    logger=False,
    engineio_logger=False,
)


# --------------------------------------------------------------------------- #
# scheduling hooks — lets engine.py stage its timed transitions
# --------------------------------------------------------------------------- #

class SocketHooks:
    """Per-room bridge between the pure engine and Socket.IO."""

    __slots__ = ("room",)

    def __init__(self, room):
        self.room = room

    def notify(self, room):
        broadcast(room)

    def later(self, delay, fn):
        socketio.start_background_task(self._run, delay, fn)

    def _run(self, delay, fn):
        try:
            socketio.sleep(delay)
        except Exception:
            time.sleep(delay)
        room = self.room
        try:
            with manager.lock:
                if room.code not in manager.rooms:
                    return
                fn()
        except GameError:
            pass
        except Exception:
            traceback.print_exc()
        try:
            broadcast(room)
        except Exception:
            traceback.print_exc()


# --------------------------------------------------------------------------- #
# broadcasting
# --------------------------------------------------------------------------- #

def broadcast(room, fx=None):
    """Send every connected player their OWN sanitized view of the room."""
    if room is None:
        return
    events = room.drain_fx()
    if fx:
        events = events + list(fx)
    room.state_seq += 1
    seq = room.state_seq
    for player in list(room.player_list):
        if not player.sid:
            continue
        try:
            payload = serializers.serialize_state_for_player(room, player.pid)
        except Exception:
            traceback.print_exc()
            continue
        payload["fx"] = events
        payload["seq"] = seq
        socketio.emit("state", payload, to=player.sid)


def send_state(room, player):
    payload = serializers.serialize_state_for_player(room, player.pid)
    payload["fx"] = []
    payload["seq"] = room.state_seq
    socketio.emit("state", payload, to=player.sid)


def fail(message, code="error"):
    socketio.emit("game_error", {"message": message, "code": code}, to=request.sid)


def handler(fn):
    """Wrap a socket handler: translate GameError into a friendly Korean toast."""
    def wrapped(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except GameError as exc:
            fail(exc.message, exc.code)
        except Exception:
            traceback.print_exc()
            fail("문제가 생겼어요. 잠시 후 다시 시도해주세요.", "internal")
    wrapped.__name__ = fn.__name__
    return wrapped


def _payload(data) -> dict:
    return data if isinstance(data, dict) else {}


def _me():
    """(room, player) for the current socket, or raise."""
    room, player = manager.locate_sid(request.sid)
    if room is None or player is None:
        raise GameError("방에 접속되어 있지 않습니다. 새로고침 해주세요.", "no_session")
    return room, player


# --------------------------------------------------------------------------- #
# http
# --------------------------------------------------------------------------- #

@app.route("/")
def index():
    return render_template(
        "index.html",
        game_config=serializers.public_config(),
        characters=config.CHARACTERS,
        reactions=config.REACTIONS,
    )


@app.route("/healthz")
def healthz():
    return {"ok": True, **manager.stats()}


# --------------------------------------------------------------------------- #
# socket.io
# --------------------------------------------------------------------------- #

@socketio.on("connect")
def on_connect():
    socketio.emit("hello", {"config": serializers.public_config()}, to=request.sid)


@socketio.on("disconnect")
def on_disconnect(*_args):
    with manager.lock:
        room, _player = manager.mark_disconnected(request.sid)
        if room is not None:
            broadcast(room)


@socketio.on("create_room")
@handler
def on_create_room(data):
    data = _payload(data)
    with manager.lock:
        room, player = manager.create_room(
            request.sid, data.get("nickname"), data.get("character")
        )
        room.hooks = SocketHooks(room)
        socketio.emit("joined", {
            "roomCode": room.code,
            "token": player.token,
            "pid": player.pid,
            "isHost": True,
        }, to=request.sid)
        broadcast(room)


@socketio.on("join_room")
@handler
def on_join_room(data):
    data = _payload(data)
    with manager.lock:
        room, player = manager.join_room(
            request.sid,
            data.get("roomCode"),
            data.get("nickname"),
            data.get("character"),
        )
        if room.hooks is None:
            room.hooks = SocketHooks(room)
        socketio.emit("joined", {
            "roomCode": room.code,
            "token": player.token,
            "pid": player.pid,
            "isHost": room.host_pid == player.pid,
        }, to=request.sid)
        broadcast(room)


@socketio.on("rejoin")
@handler
def on_rejoin(data):
    data = _payload(data)
    with manager.lock:
        room, player = manager.rejoin(
            request.sid, data.get("roomCode"), data.get("token")
        )
        if room.hooks is None:
            room.hooks = SocketHooks(room)
        socketio.emit("joined", {
            "roomCode": room.code,
            "token": player.token,
            "pid": player.pid,
            "isHost": room.host_pid == player.pid,
            "restored": True,
        }, to=request.sid)
        broadcast(room)


@socketio.on("room_info")
@handler
def on_room_info(data):
    """Used by the join screen to grey out characters already in use."""
    data = _payload(data)
    with manager.lock:
        room = manager.get(data.get("roomCode"))
        if room is None:
            socketio.emit("room_info", {"found": False}, to=request.sid)
            return
        info = serializers.lobby_summary(room)
        info["found"] = True
        socketio.emit("room_info", info, to=request.sid)


@socketio.on("leave_room")
@handler
def on_leave_room(_data=None):
    with manager.lock:
        room, _player = manager.leave(request.sid)
        socketio.emit("left", {}, to=request.sid)
        if room is not None:
            broadcast(room)


@socketio.on("request_state")
@handler
def on_request_state(_data=None):
    with manager.lock:
        room, player = _me()
        send_state(room, player)


@socketio.on("start_game")
@handler
def on_start_game(_data=None):
    with manager.lock:
        room, player = _me()
        engine.start_game(room, player)
        broadcast(room)


@socketio.on("next_round")
@handler
def on_next_round(_data=None):
    with manager.lock:
        room, player = _me()
        engine.next_round(room, player)
        broadcast(room)


@socketio.on("end_game")
@handler
def on_end_game(_data=None):
    with manager.lock:
        room, player = _me()
        engine.end_game(room, player)
        broadcast(room)


@socketio.on("bet_action")
@handler
def on_bet_action(data):
    data = _payload(data)
    with manager.lock:
        room, player = _me()
        engine.bet_action(room, player, str(data.get("action", "")))
        broadcast(room)


@socketio.on("die")
@handler
def on_die(_data=None):
    with manager.lock:
        room, player = _me()
        engine.fold(room, player)
        broadcast(room)


@socketio.on("discard_card")
@handler
def on_discard_card(data):
    data = _payload(data)
    with manager.lock:
        room, player = _me()
        engine.discard(room, player, str(data.get("cardId", "")))
        broadcast(room)


@socketio.on("take_loan")
@handler
def on_take_loan(_data=None):
    with manager.lock:
        room, player = _me()
        engine.take_loan(room, player)
        broadcast(room)


@socketio.on("reaction")
@handler
def on_reaction(data):
    data = _payload(data)
    key = str(data.get("key", ""))
    with manager.lock:
        room, player = _me()
        if key not in config.REACTION_KEYS:
            return
        now = time.time()
        if now - player.last_reaction_at < config.REACTION_COOLDOWN_SEC:
            raise GameError("잠시 후에 다시 눌러주세요.", "cooldown")
        player.last_reaction_at = now
        room.push_fx("reaction", pid=player.pid, text=config.REACTION_TEXT[key])
        broadcast(room)


@socketio.on("force_fold")
@handler
def on_force_fold(data):
    """방장 only — unblock the table when someone's browser died."""
    data = _payload(data)
    with manager.lock:
        room, player = _me()
        if room.host_pid != player.pid:
            raise GameError("방장만 할 수 있습니다.", "not_host")
        target = room.get(str(data.get("pid", "")))
        if target is None:
            raise GameError("해당 플레이어를 찾을 수 없습니다.", "no_player")
        if target.connected:
            raise GameError("아직 접속 중인 플레이어입니다.", "connected")
        engine.force_fold(room, target)
        broadcast(room)


@socketio.on("kick_player")
@handler
def on_kick_player(data):
    """방장 only — remove a player who left for good."""
    data = _payload(data)
    with manager.lock:
        room, player = _me()
        if room.host_pid != player.pid:
            raise GameError("방장만 할 수 있습니다.", "not_host")
        pid = str(data.get("pid", ""))
        target = room.get(pid)
        if target is None or target.pid == player.pid:
            raise GameError("내보낼 수 없는 플레이어입니다.", "no_player")
        if target.sid:
            socketio.emit("kicked", {}, to=target.sid)
        manager.remove_player(room, pid)
        if room.code in manager.rooms:
            broadcast(room)


# --------------------------------------------------------------------------- #
# housekeeping thread
# --------------------------------------------------------------------------- #

def _sweeper():
    while True:
        socketio.sleep(15)
        try:
            with manager.lock:
                for room in manager.sweep():
                    broadcast(room)
        except Exception:
            traceback.print_exc()


# --------------------------------------------------------------------------- #
# startup banner
# --------------------------------------------------------------------------- #

def print_banner(port: int) -> None:
    lan_ip = utils.detect_lan_ip()
    line = "=" * 50
    print("")
    print(line)
    print("  숫자 섯다 - 사내 멀티플레이")
    print(line)
    print("")
    print("  내 PC:")
    print(f"      http://127.0.0.1:{port}")
    print("")
    if lan_ip:
        print("  사내 접속 주소:")
        print(f"      http://{lan_ip}:{port}")
    else:
        print("  사내 접속 주소를 찾지 못했습니다.")
        print("      ipconfig 명령어에서 IPv4 주소를 확인해주세요.")
    print("")
    print("  게임 서버가 실행되었습니다.")
    print("  종료하려면 Ctrl + C 를 누르세요.")
    print(line)
    print("", flush=True)


if __name__ == "__main__":
    PORT = config.DEFAULT_PORT
    if len(sys.argv) > 1:
        try:
            PORT = int(sys.argv[1])
        except ValueError:
            pass

    print_banner(PORT)
    socketio.start_background_task(_sweeper)
    socketio.run(
        app,
        host=config.DEFAULT_HOST,
        port=PORT,
        debug=True,
        use_reloader=False,      # keeps the game state alive while you edit
        allow_unsafe_werkzeug=True,
    )
