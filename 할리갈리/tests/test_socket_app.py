import json
import unittest

from app import app, connections, rooms, socketio


def event_payload(client, event_name):
    events = client.get_received()
    matches = [event for event in events if event["name"] == event_name]
    return matches[-1]["args"][0] if matches else None


class SocketIntegrationTests(unittest.TestCase):
    def setUp(self):
        rooms.rooms.clear()
        connections.clear()
        self.clients = []

    def tearDown(self):
        for client in self.clients:
            if client.is_connected():
                client.disconnect()

    def client(self):
        client = socketio.test_client(app)
        self.clients.append(client)
        return client

    def test_four_clients_start_and_receive_same_public_reveal(self):
        clients = [self.client() for _ in range(4)]
        clients[0].emit("create_room", {"nickname": "하나", "avatar": "bear"})
        host_session = event_payload(clients[0], "session_established")
        self.assertIsNotNone(host_session)
        code = host_session["room_code"]

        sessions = [host_session]
        for index, client in enumerate(clients[1:], start=2):
            client.emit("join_room", {"room_code": code, "nickname": f"손님{index}", "avatar": "cat"})
            sessions.append(event_payload(client, "session_established"))

        for client in clients[1:]:
            client.emit("set_ready", {"ready": True})
        clients[0].get_received()
        clients[0].emit("start_game")
        host_events = clients[0].get_received()
        states = [event["args"][0] for event in host_events if event["name"] == "room_state"]
        self.assertTrue(states)
        state = states[-1]
        self.assertEqual([14, 14, 14, 14], [player["remaining_card_count"] for player in state["players"]])
        encoded = json.dumps(state)
        self.assertNotIn("draw_pile", encoded)
        self.assertNotIn("reconnect_token", encoded)

        current_id = state["current_player_id"]
        current_client = clients[next(i for i, session in enumerate(sessions) if session["player_id"] == current_id)]
        room = rooms.require(code)
        room.reveal_allowed_at = 0
        for client in clients:
            client.get_received()
        current_client.emit("reveal_card")

        revealed_ids = []
        versions = []
        for client in clients:
            events = client.get_received()
            revealed = next(event["args"][0] for event in events if event["name"] == "card_revealed")
            public_state = next(event["args"][0] for event in events if event["name"] == "room_state")
            revealed_ids.append(revealed["card"]["id"])
            versions.append(public_state["board_version"])
        self.assertEqual(1, len(set(revealed_ids)))
        self.assertEqual([1, 1, 1, 1], versions)

    def test_two_clients_can_start_with_twenty_eight_cards_each(self):
        host = self.client()
        guest = self.client()
        host.emit("create_room", {"nickname": "둘이방장", "avatar": "bear"})
        host_session = event_payload(host, "session_established")
        guest.emit("join_room", {"room_code": host_session["room_code"], "nickname": "둘이친구", "avatar": "cat"})
        event_payload(guest, "session_established")
        guest.emit("set_ready", {"ready": True})
        host.get_received()

        host.emit("start_game")
        state = event_payload(host, "room_state")

        self.assertEqual("PLAYING", state["state"])
        self.assertEqual(2, state["player_count"])
        self.assertEqual(2, state["min_players"])
        self.assertEqual(4, state["capacity"])
        self.assertEqual([28, 28], [player["remaining_card_count"] for player in state["players"]])

    def test_duplicate_nickname_is_rejected(self):
        host = self.client()
        guest = self.client()
        host.emit("create_room", {"nickname": "같은이름", "avatar": "bear"})
        session = event_payload(host, "session_established")
        guest.emit("join_room", {"room_code": session["room_code"], "nickname": " 같은이름 ", "avatar": "cat"})
        error = event_payload(guest, "error_message")
        self.assertEqual("duplicate_nickname", error["code"])

    def test_five_blocks_card_packet_then_bell_succeeds_for_both_clients(self):
        host, guest = self.client(), self.client()
        host.emit("create_room", {"nickname": "방장", "avatar": "bear"})
        session = event_payload(host, "session_established")
        guest.emit("join_room", {"room_code": session["room_code"], "nickname": "친구", "avatar": "cat"})
        event_payload(guest, "session_established")
        guest.emit("set_ready", {"ready": True})
        host.emit("start_game")
        room = rooms.require(session["room_code"])
        host_player = room.players[0]
        card = next(card for card in room.all_cards() if card.fruit == "banana" and card.count == 5)
        for player in room.players:
            if card in player.draw_pile:
                player.draw_pile.remove(card)
                break
        host_player.draw_pile.appendleft(card)
        room.current_player_id = host_player.id
        room.reveal_allowed_at = 0
        for client in (host, guest):
            client.get_received()

        host.emit("reveal_card")
        for client in (host, guest):
            state = event_payload(client, "room_state")
            self.assertTrue(state["reveal_blocked_for_bell"])
            self.assertNotIn("fruit_totals", state)
        room.reveal_allowed_at = 0
        guest.emit("reveal_card")
        rejected = event_payload(guest, "error_message")
        self.assertEqual("awaiting_bell", rejected["code"])
        self.assertEqual([], host.get_received())
        self.assertEqual(1, room.board_version)
        self.assertEqual(card, host_player.face_up[-1])

        guest.emit("ring_bell")
        for client in (host, guest):
            events = client.get_received()
            result = next(event["args"][0] for event in events if event["name"] == "bell_result")
            state = next(event["args"][0] for event in events if event["name"] == "room_state")
            self.assertEqual("correct", result["status"])
            self.assertFalse(state["reveal_blocked_for_bell"])
        room.assert_integrity()

    def test_reconnect_token_restores_same_player_without_duplicate(self):
        first = self.client()
        first.emit("create_room", {"nickname": "새로고침", "avatar": "robot"})
        session = event_payload(first, "session_established")
        code = session["room_code"]
        player_id = session["player_id"]
        first.disconnect()

        restored = self.client()
        restored.emit("reconnect_player", {"room_code": code, "reconnect_token": session["reconnect_token"]})
        restored_session = event_payload(restored, "session_established")
        self.assertEqual(player_id, restored_session["player_id"])
        self.assertEqual(1, len(rooms.require(code).players))


if __name__ == "__main__":
    unittest.main()
