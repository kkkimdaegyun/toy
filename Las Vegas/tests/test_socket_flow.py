import pytest

from app import (
    app,
    disconnected_players,
    player_to_sid,
    room_manager,
    sid_to_player,
    socketio,
)


@pytest.fixture(autouse=True)
def reset_socket_state():
    room_manager.rooms.clear()
    room_manager.player_rooms.clear()
    sid_to_player.clear()
    player_to_sid.clear()
    disconnected_players.clear()
    yield
    room_manager.rooms.clear()
    room_manager.player_rooms.clear()
    sid_to_player.clear()
    player_to_sid.clear()
    disconnected_players.clear()


def event_payload(events, name):
    event = next(item for item in events if item["name"] == name)
    return event["args"][0]


def test_ui_assets_disable_browser_cache():
    client = app.test_client()
    for path in ("/", "/static/js/socket.js", "/static/css/style.css"):
        response = client.get(path)
        assert response.status_code == 200
        assert "no-store" in response.headers["Cache-Control"]


def create_room_with_four_players():
    clients = [
        socketio.test_client(app, flask_test_client=app.test_client())
        for _ in range(4)
    ]
    colors = ["red", "orange", "yellow", "green"]

    clients[0].emit("create_room", {"nickname": "host", "color": colors[0]})
    created = event_payload(clients[0].get_received(), "room_created")
    room_code = created["room_code"]

    for index in range(1, 4):
        clients[index].emit(
            "join_room",
            {
                "room_code": room_code,
                "nickname": f"player{index}",
                "color": colors[index],
            },
        )
        clients[index].get_received()

    for client in clients:
        client.get_received()

    return clients, room_code


def create_two_player_room():
    clients = [
        socketio.test_client(app, flask_test_client=app.test_client())
        for _ in range(2)
    ]
    clients[0].emit("create_room", {"nickname": "host", "color": "red"})
    created = event_payload(clients[0].get_received(), "room_created")
    clients[1].emit(
        "join_room",
        {
            "room_code": created["room_code"],
            "nickname": "player1",
            "color": "orange",
        },
    )
    clients[1].get_received()
    for client in clients:
        client.get_received()
    return clients, created["room_code"]


def disconnect_all(clients):
    for client in clients:
        if client.is_connected():
            client.disconnect()


def test_host_can_start_when_room_is_full():
    clients, room_code = create_room_with_four_players()
    try:
        clients[0].emit("start_game")
        event_names = [event["name"] for event in clients[0].get_received()]

        assert "game_started" in event_names
        assert "dealer_roll" in event_names
        assert "dealer_result" in event_names
        assert room_manager.get_room(room_code).game is not None
    finally:
        disconnect_all(clients)


def test_room_rejects_a_fifth_player():
    clients, room_code = create_room_with_four_players()
    fifth = socketio.test_client(app, flask_test_client=app.test_client())
    try:
        fifth.emit(
            "join_room",
            {
                "room_code": room_code,
                "nickname": "player5",
                "color": "red",
            },
        )
        error = event_payload(fifth.get_received(), "error")
        assert "4/4명" in error["message"]
    finally:
        disconnect_all([*clients, fifth])


def test_host_can_start_with_two_players_immediately_after_join():
    clients, room_code = create_two_player_room()
    try:
        clients[0].emit("start_game")
        event_names = [event["name"] for event in clients[0].get_received()]

        assert "game_started" in event_names
        assert room_manager.get_room(room_code).game is not None
        assert len(room_manager.get_room(room_code).game.players) == 2
    finally:
        disconnect_all(clients)


def test_placement_snapshot_reaches_every_player_before_next_turn():
    clients, room_code = create_two_player_room()
    try:
        room = room_manager.get_room(room_code)
        clients[0].emit("start_game")
        for client in clients:
            client.get_received()

        while room.game.phase == "DEALER_TIE_REROLL":
            clients[0].emit("dealer_reroll")
            for client in clients:
                client.get_received()

        clients[0].emit("setup_payouts")
        for client in clients:
            client.get_received()

        current_player = room.game.get_current_player()
        actor = clients[0] if current_player == room.host_id else clients[1]
        actor.emit("roll_dice")
        rolled_events = actor.get_received()
        roll_data = event_payload(rolled_events, "dice_rolled")
        other = clients[1] if actor is clients[0] else clients[0]
        other.get_received()

        casino = roll_data["valid_casinos"][0]
        actor.emit("confirm_placement", {"casino": casino})

        for client in clients:
            events = client.get_received()
            names = [event["name"] for event in events]
            placement_index = names.index("placement_confirmed")
            turn_index = names.index("turn_start")
            placement = event_payload(events, "placement_confirmed")

            assert placement_index < turn_index
            assert placement["sequence"] == 1
            assert placement["casino_counts"] == placement["all_casino_dice"][str(casino)]
            assert placement["casino_counts"][current_player]["count"] > 0
    finally:
        disconnect_all(clients)


def test_start_returns_reason_when_only_host_is_present():
    client = socketio.test_client(app, flask_test_client=app.test_client())
    try:
        client.emit("create_room", {"nickname": "host", "color": "red"})
        client.get_received()
        client.emit("start_game")

        error = event_payload(client.get_received(), "error")
        assert "최소 2명이" in error["message"]
    finally:
        disconnect_all([client])


def test_reconnect_response_describes_active_game():
    clients, room_code = create_room_with_four_players()
    reconnecting_client = None
    try:
        clients[0].emit("start_game")
        clients[0].get_received()

        room = room_manager.get_room(room_code)
        token = next(
            token
            for token, player_id in room.reconnect_tokens.items()
            if player_id == room.host_id
        )
        clients[0].disconnect()

        reconnecting_client = socketio.test_client(
            app, flask_test_client=app.test_client()
        )
        reconnecting_client.emit(
            "reconnect_attempt", {"token": token, "room_code": room_code}
        )
        events = reconnecting_client.get_received()

        reconnect_data = event_payload(events, "reconnect_success")
        assert reconnect_data["has_game"] is True
        assert any(event["name"] == "game_state" for event in events)
    finally:
        if reconnecting_client and reconnecting_client.is_connected():
            reconnecting_client.disconnect()
        disconnect_all(clients)


def test_reconnect_replaces_an_existing_tab_instead_of_leaving_a_zombie_session():
    host = socketio.test_client(app, flask_test_client=app.test_client())
    replacement = None
    try:
        host.emit("create_room", {"nickname": "host", "color": "red"})
        created = event_payload(host.get_received(), "room_created")

        replacement = socketio.test_client(app, flask_test_client=app.test_client())
        replacement.emit(
            "reconnect_attempt",
            {"token": created["token"], "room_code": created["room_code"]},
        )
        replacement_events = replacement.get_received()

        assert not host.is_connected()
        assert any(
            event["name"] == "reconnect_success"
            for event in replacement_events
        )
    finally:
        if replacement and replacement.is_connected():
            replacement.disconnect()
        disconnect_all([host])
