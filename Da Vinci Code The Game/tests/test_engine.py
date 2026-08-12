import unittest

from game.engine import GameEngine
from game.models import Player, Room


def room_with_players(count=2):
    room = Room(code="TEST")
    for index in range(count):
        player = Player(id=f"p{index}", nickname=f"Player {index}", token=f"t{index}", host=index == 0)
        room.players[player.id] = player
    room.host_player_id = "p0"
    return room


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = GameEngine()

    def test_deck_has_all_24_unique_tiles(self):
        deck = self.engine.create_deck()
        self.assertEqual(24, len(deck))
        self.assertEqual(24, len({tile.id for tile in deck}))
        self.assertEqual({tile.value for tile in deck if tile.color == "black"}, set(range(12)))
        self.assertEqual({tile.value for tile in deck if tile.color == "white"}, set(range(12)))

    def test_start_deals_sorted_tiles_and_shuffle_preserves_deck(self):
        room = room_with_players(3)
        self.engine.start_game(room)
        # 12 remain after dealing, then the first player immediately draws one.
        self.assertEqual(11, len(room.deck))
        self.assertTrue(all(len(player.tiles) == 4 or len(player.tiles) == 5 for player in room.players.values()))
        for player in room.players.values():
            keys = [(tile.value, 0 if tile.color == "black" else 1) for tile in player.tiles]
            self.assertEqual(keys, sorted(keys))

    def test_black_precedes_white_on_equal_value(self):
        deck = self.engine.create_deck()
        pair = [tile for tile in deck if tile.value == 4]
        sorted_pair = sorted(pair, key=lambda tile: (tile.value, 0 if tile.color == "black" else 1))
        self.assertEqual(["black", "white"], [tile.color for tile in sorted_pair])

    def test_correct_guess_reveals_target(self):
        room = room_with_players()
        self.engine.start_game(room)
        actor = self.engine.current_player(room)
        target_player = next(player for player in room.players.values() if player.id != actor.id)
        target = target_player.tiles[0]
        result = self.engine.make_guess(room, actor.id, target_player.id, target.id, target.value)
        self.assertTrue(result["correct"])
        self.assertTrue(target.revealed)
        self.assertEqual("decision", room.turn_phase)

    def test_wrong_guess_only_reveals_drawn_tile_and_advances(self):
        room = room_with_players(3)
        self.engine.start_game(room)
        actor = self.engine.current_player(room)
        drawn = next(tile for tile in actor.tiles if tile.id == room.current_drawn_tile_id)
        target_player = next(player for player in room.players.values() if player.id != actor.id)
        target = target_player.tiles[0]
        wrong = (target.value + 1) % 12
        self.engine.make_guess(room, actor.id, target_player.id, target.id, wrong)
        self.assertFalse(target.revealed)
        self.assertTrue(drawn.revealed)
        self.assertNotEqual(actor.id, self.engine.current_player(room).id)

    def test_voluntary_end_keeps_draw_hidden(self):
        room = room_with_players(3)
        self.engine.start_game(room)
        actor = self.engine.current_player(room)
        drawn = next(tile for tile in actor.tiles if tile.id == room.current_drawn_tile_id)
        target_player = next(player for player in room.players.values() if player.id != actor.id)
        target = target_player.tiles[0]
        self.engine.make_guess(room, actor.id, target_player.id, target.id, target.value)
        self.engine.end_turn(room, actor.id)
        self.assertFalse(drawn.revealed)

    def test_eliminated_player_is_skipped_and_winner_detected(self):
        room = room_with_players(3)
        self.engine.start_game(room)
        current = self.engine.current_player(room)
        next_id = room.turn_order[(room.current_turn_index + 1) % 3]
        room.players[next_id].eliminated = True
        self.engine.advance_turn(room)
        self.assertNotEqual(next_id, self.engine.current_player(room).id)
        two = room_with_players(2)
        self.engine.start_game(two)
        for tile in two.players["p1"].tiles:
            tile.revealed = True
        self.engine.update_eliminations(two)
        self.assertTrue(self.engine.check_winner(two))
        self.assertEqual("p0", two.winner_player_id)

    def test_reset_and_sanitized_view_hide_opponent_values(self):
        room = room_with_players()
        self.engine.start_game(room)
        opponent = room.players["p1"]
        view = self.engine.public_view(room, "p0")
        opponent_view = next(player for player in view["players"] if player["id"] == opponent.id)
        self.assertTrue(all("value" not in tile for tile in opponent_view["tiles"] if not tile["revealed"]))
        self.engine.reset_to_lobby(room)
        self.assertEqual("lobby", room.phase)
        self.assertEqual([], room.deck)
        self.assertTrue(all(not player.tiles for player in room.players.values()))


if __name__ == "__main__":
    unittest.main()
