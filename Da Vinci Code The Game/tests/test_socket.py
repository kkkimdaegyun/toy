import unittest

from app import app, rooms, socketio


def last_event(client, name):
    events = [event for event in client.get_received() if event["name"] == name]
    return events[-1]["args"][0]


class SocketPrivacyTests(unittest.TestCase):
    def setUp(self):
        rooms.rooms.clear()
        rooms.socket_to_player.clear()
        self.host = socketio.test_client(app)
        self.host.emit("create_room", {"nickname": "Host"})
        identity = last_event(self.host, "identity")
        self.code = identity["roomCode"]
        self.guest = socketio.test_client(app)
        self.guest.emit("join_room", {"nickname": "Guest", "roomCode": self.code})
        self.guest.get_received()

    def tearDown(self):
        self.host.disconnect()
        self.guest.disconnect()

    def test_game_state_never_sends_hidden_opponent_values(self):
        self.host.get_received()  # discard lobby update caused by joining
        self.host.emit("start_game")
        host_view = last_event(self.host, "state")
        guest_view = last_event(self.guest, "state")
        for view in (host_view, guest_view):
            for player in view["players"]:
                if player["id"] == view["selfId"]:
                    self.assertTrue(all("value" in tile for tile in player["tiles"]))
                else:
                    self.assertTrue(all("value" not in tile for tile in player["tiles"] if not tile["revealed"]))


if __name__ == "__main__":
    unittest.main()
