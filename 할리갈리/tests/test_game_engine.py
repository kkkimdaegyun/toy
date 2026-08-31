import json
import threading
import unittest

from game_engine import (
    CARD_DISTRIBUTION,
    FRUITS,
    GAME_OVER,
    PAUSED_DISCONNECT,
    PLAYING,
    Card,
    GameError,
    Room,
    build_deck,
    count_distribution,
)


def make_started_room(now=0.0, player_count=4):
    room = Room("TEST")
    avatars = ("bear", "cat", "dog", "rabbit")
    for index in range(player_count):
        player = room.add_player(f"플레이어{index + 1}", avatars[index], f"sid-{index}")
        if index:
            player.ready = True
    room.start_game(room.host_id, now=now)
    return room


def take_card(room, fruit, count):
    for player in room.players:
        for card in list(player.draw_pile):
            if card.fruit == fruit and card.count == count:
                player.draw_pile.remove(card)
                return card
    raise AssertionError(f"missing card {fruit} {count}")


def expose(room, player_index, fruit, count):
    card = take_card(room, fruit, count)
    room.players[player_index].face_up.append(card)
    return card


class DeckTests(unittest.TestCase):
    def test_exact_deck_distribution_and_unique_ids(self):
        deck = build_deck()
        self.assertEqual(56, len(deck))
        self.assertEqual(56, len({card.id for card in deck}))
        distribution = count_distribution(deck)
        for fruit in FRUITS:
            self.assertEqual(14, sum(amount for (name, _), amount in distribution.items() if name == fruit))
            for count, copies in CARD_DISTRIBUTION.items():
                self.assertEqual(copies, distribution[(fruit, count)])

    def test_four_player_deal_has_no_duplicates(self):
        room = make_started_room()
        self.assertEqual([14, 14, 14, 14], [len(player.draw_pile) for player in room.players])
        cards = room.all_cards()
        self.assertEqual(56, len(cards))
        self.assertEqual(56, len({card.id for card in cards}))

    def test_two_three_and_four_player_deals_use_all_cards(self):
        expected_counts = {
            2: [28, 28],
            3: [18, 19, 19],
            4: [14, 14, 14, 14],
        }
        for player_count, expected in expected_counts.items():
            with self.subTest(player_count=player_count):
                room = make_started_room(player_count=player_count)
                actual = sorted(len(player.draw_pile) for player in room.players)
                self.assertEqual(expected, actual)
                self.assertEqual(56, len(room.all_cards()))
                self.assertEqual(56, len({card.id for card in room.all_cards()}))

    def test_game_requires_at_least_two_ready_players(self):
        room = Room("MIN2")
        host = room.add_player("방장", "bear", "host-sid")
        self.assertFalse(room.can_start())
        with self.assertRaises(GameError):
            room.start_game(host.id, now=0.0)

        guest = room.add_player("친구", "cat", "guest-sid")
        self.assertFalse(room.can_start())
        room.set_ready(guest.id, True)
        self.assertTrue(room.can_start())
        room.start_game(host.id, now=0.0)
        self.assertEqual([28, 28], [len(player.draw_pile) for player in room.players])


class FruitRuleTests(unittest.TestCase):
    def make_visible_room(self):
        room = Room("RULE")
        for index, avatar in enumerate(("bear", "cat", "dog", "rabbit")):
            room.add_player(f"규칙{index}", avatar, f"rule-{index}")
        return room

    def test_exactly_five_is_valid_but_six_is_not(self):
        room = self.make_visible_room()
        room.players[0].face_up.append(Card("a", "strawberry", 2))
        room.players[1].face_up.append(Card("b", "strawberry", 3))
        self.assertTrue(room.has_exact_five())
        room.players[1].face_up[-1] = Card("c", "strawberry", 4)
        self.assertFalse(room.has_exact_five())

    def test_single_five_and_multiple_exact_fives(self):
        room = self.make_visible_room()
        room.players[0].face_up.append(Card("a", "banana", 5))
        self.assertTrue(room.has_exact_five())
        room.players[1].face_up.append(Card("b", "lime", 2))
        room.players[2].face_up.append(Card("c", "lime", 3))
        totals = room.visible_totals()
        self.assertEqual(5, totals["banana"])
        self.assertEqual(5, totals["lime"])
        self.assertTrue(room.has_exact_five())

    def test_only_top_card_counts_and_covering_can_create_five(self):
        room = self.make_visible_room()
        room.players[0].face_up.append(Card("old", "banana", 3))
        room.players[1].face_up.append(Card("five", "banana", 5))
        self.assertEqual(8, room.visible_totals()["banana"])
        room.players[0].face_up.append(Card("new", "strawberry", 2))
        totals = room.visible_totals()
        self.assertEqual(5, totals["banana"])
        self.assertEqual(2, totals["strawberry"])
        self.assertTrue(room.has_exact_five())


class BellAndTurnTests(unittest.TestCase):
    def test_correct_bell_collects_all_face_up_cards_to_bottom(self):
        room = make_started_room()
        expose(room, 0, "strawberry", 2)
        expose(room, 1, "strawberry", 3)
        expose(room, 2, "banana", 4)
        winner = room.players[3]
        original = list(winner.draw_pile)
        exposed_ids = [card.id for player in room.players for card in player.face_up]

        result = room.ring_bell(winner.id, now=1.0)

        self.assertEqual("correct", result["status"])
        self.assertEqual(3, result["collected_count"])
        self.assertTrue(all(not player.face_up for player in room.players))
        self.assertEqual([card.id for card in original], [card.id for card in list(winner.draw_pile)[: len(original)]])
        self.assertEqual(exposed_ids, [card.id for card in list(winner.draw_pile)[-3:]])
        self.assertEqual(winner.id, room.current_player_id)

    def test_wrong_bell_transfers_hidden_cards_and_keeps_table(self):
        room = make_started_room()
        expose(room, 0, "strawberry", 2)
        expose(room, 1, "strawberry", 4)
        ringer = room.players[0]
        table_ids = [[card.id for card in player.face_up] for player in room.players]
        before = [len(player.draw_pile) for player in room.players]

        result = room.ring_bell(ringer.id, now=1.0)

        self.assertEqual("wrong", result["status"])
        self.assertEqual(3, result["transfer_count"])
        self.assertEqual(before[0] - 3, len(ringer.draw_pile))
        for index in (1, 2, 3):
            self.assertEqual(before[index] + 1, len(room.players[index].draw_pile))
        self.assertEqual(table_ids, [[card.id for card in player.face_up] for player in room.players])

    def test_insufficient_wrong_bell_penalty_follows_clockwise_order(self):
        room = make_started_room()
        ringer = room.players[0]
        while len(ringer.draw_pile) > 2:
            room.players[3].draw_pile.append(ringer.draw_pile.pop())
        before = [len(player.draw_pile) for player in room.players]

        result = room.ring_bell(ringer.id, now=1.0)

        self.assertEqual("wrong", result["status"])
        self.assertEqual([room.players[1].id, room.players[2].id], result["recipient_ids"])
        self.assertEqual(0, len(ringer.draw_pile))
        self.assertTrue(ringer.eliminated)
        self.assertEqual(before[1] + 1, len(room.players[1].draw_pile))
        self.assertEqual(before[2] + 1, len(room.players[2].draw_pile))
        self.assertEqual(before[3], len(room.players[3].draw_pile))

    def test_last_revealed_card_stays_visible_after_elimination(self):
        room = make_started_room()
        player = room.players[0]
        room.current_player_id = player.id
        while len(player.draw_pile) > 1:
            room.players[1].draw_pile.append(player.draw_pile.pop())

        result = room.reveal_card(player.id, now=1.0)

        self.assertIn(player.id, result["eliminated_ids"])
        self.assertTrue(player.eliminated)
        self.assertEqual(0, len(player.draw_pile))
        self.assertEqual(1, len(player.face_up))
        self.assertNotEqual(player.id, room.current_player_id)

    def test_game_ends_when_only_one_draw_pile_survives(self):
        room = make_started_room()
        last_revealer = room.players[0]
        survivor = room.players[1]
        room.current_player_id = last_revealer.id
        for player in (room.players[2], room.players[3]):
            while player.draw_pile:
                survivor.draw_pile.append(player.draw_pile.popleft())
            player.eliminated = True
        while len(last_revealer.draw_pile) > 1:
            survivor.draw_pile.append(last_revealer.draw_pile.pop())

        result = room.reveal_card(last_revealer.id, now=1.0)

        self.assertTrue(result["game_over"])
        self.assertEqual(GAME_OVER, room.state)
        self.assertEqual(survivor.id, room.winner_id)
        self.assertEqual(1, len(last_revealer.face_up))

    def test_server_debounce_and_resolution_guard_block_space_spam(self):
        room = make_started_room()
        ringer = room.players[0]
        first = room.ring_bell(ringer.id, now=1.0)
        second = room.ring_bell(ringer.id, now=1.1)
        self.assertEqual("wrong", first["status"])
        self.assertEqual("ignored", second["status"])
        self.assertEqual("spam", second["reason"])


class ExactFiveRevealLockTests(unittest.TestCase):
    def exact_five_room(self):
        room = make_started_room(player_count=2)
        expose(room, 0, "strawberry", 2)
        expose(room, 1, "strawberry", 3)
        room.current_player_id = room.players[0].id
        return room

    def test_exact_five_blocks_repeated_reveals_without_changing_board(self):
        room = self.exact_five_room()
        before = room.serialize(now=1.0)
        before_cards = [card.id for card in room.all_cards()]
        self.assertTrue(before["reveal_blocked_for_bell"])
        for moment in (1.0, 2.0, 30.0):
            with self.assertRaises(GameError) as raised:
                room.reveal_card(room.current_player_id, now=moment)
            self.assertEqual("awaiting_bell", raised.exception.code)
        self.assertEqual(before, room.serialize(now=1.0))
        self.assertEqual(before_cards, [card.id for card in room.all_cards()])

    def test_correct_bell_unlocks_reveal_after_resolution_guard(self):
        room = self.exact_five_room()
        winner = room.players[1]
        result = room.ring_bell(winner.id, now=1.0)
        self.assertEqual("correct", result["status"])
        self.assertFalse(room.serialize(now=1.0)["reveal_blocked_for_bell"])
        self.assertEqual(winner.id, room.current_player_id)
        with self.assertRaises(GameError) as raised:
            room.reveal_card(winner.id, now=1.1)
        self.assertEqual("bell_resolving", raised.exception.code)
        self.assertEqual("revealed", room.reveal_card(winner.id, now=1.5)["status"])
        room.assert_integrity()

    def test_six_does_not_block_reveal(self):
        room = make_started_room(player_count=2)
        expose(room, 0, "strawberry", 2)
        expose(room, 1, "strawberry", 4)
        self.assertFalse(room.serialize(now=1.0)["reveal_blocked_for_bell"])
        self.assertEqual("revealed", room.reveal_card(room.current_player_id, now=1.0)["status"])

    def test_covering_a_card_can_lock_the_next_reveal(self):
        room = make_started_room(player_count=2)
        expose(room, 0, "banana", 3)
        expose(room, 1, "banana", 5)
        room.players[0].draw_pile.appendleft(take_card(room, "strawberry", 2))
        room.current_player_id = room.players[0].id
        self.assertFalse(room.has_exact_five())
        room.reveal_card(room.players[0].id, now=1.0)
        self.assertTrue(room.serialize(now=1.0)["reveal_blocked_for_bell"])
        with self.assertRaises(GameError) as raised:
            room.reveal_card(room.players[1].id, now=2.0)
        self.assertEqual("awaiting_bell", raised.exception.code)

    def test_reconnect_preserves_lock_and_rematch_clears_it(self):
        room = self.exact_five_room()
        player = room.players[0]
        room.disconnect(player.sid)
        self.assertTrue(room.serialize()["reveal_blocked_for_bell"])
        room.reconnect(player.reconnect_token, "restored")
        self.assertTrue(room.serialize()["reveal_blocked_for_bell"])
        room.state = GAME_OVER
        room.start_game(room.host_id, rematch=True, now=2.0)
        self.assertFalse(room.serialize(now=2.0)["reveal_blocked_for_bell"])


class ConcurrencyTests(unittest.TestCase):
    def test_existing_five_cannot_be_overwritten_in_reveal_bell_race(self):
        for _ in range(20):
            room = make_started_room(player_count=2)
            expose(room, 0, "strawberry", 2)
            expose(room, 1, "strawberry", 3)
            room.current_player_id = room.players[0].id
            barrier = threading.Barrier(3)
            outcomes = []

            def reveal():
                barrier.wait()
                try:
                    outcomes.append(room.reveal_card(room.players[0].id, now=1.0))
                except GameError as error:
                    outcomes.append({"status": "blocked", "code": error.code})

            def ring():
                barrier.wait()
                outcomes.append(room.ring_bell(room.players[1].id, now=1.0))

            threads = [threading.Thread(target=reveal), threading.Thread(target=ring)]
            for thread in threads:
                thread.start()
            barrier.wait()
            for thread in threads:
                thread.join(timeout=2)
                self.assertFalse(thread.is_alive())
            self.assertEqual(["blocked", "correct"], sorted(item["status"] for item in outcomes))
            self.assertEqual(1, room.board_version)
            self.assertTrue(all(not player.face_up for player in room.players))
            room.assert_integrity()

    def test_simultaneous_bell_has_exactly_one_winner(self):
        room = make_started_room()
        expose(room, 0, "strawberry", 2)
        expose(room, 1, "strawberry", 3)
        barrier = threading.Barrier(3)
        results = []

        def ring(player_id):
            barrier.wait()
            results.append(room.ring_bell(player_id, now=1.0))

        threads = [threading.Thread(target=ring, args=(room.players[index].id,)) for index in (2, 3)]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join()

        self.assertEqual(1, sum(result["status"] == "correct" for result in results))
        self.assertEqual(1, sum(result["status"] == "too_late" for result in results))
        self.assertTrue(all(not player.face_up for player in room.players))
        room.assert_integrity()

    def test_reveal_and_bell_race_is_serialized_without_corruption(self):
        room = make_started_room()
        current = room._require_player(room.current_player_id)
        visible_owner = next(player for player in room.players if player.id != current.id)
        visible_owner.face_up.append(take_card(room, "strawberry", 4))
        one = take_card(room, "strawberry", 1)
        current.draw_pile.appendleft(one)
        barrier = threading.Barrier(3)
        outcomes = []

        def reveal():
            barrier.wait()
            try:
                outcomes.append(("reveal", room.reveal_card(current.id, now=1.0)))
            except GameError as error:
                outcomes.append(("reveal_error", error.code))

        def ring():
            barrier.wait()
            outcomes.append(("ring", room.ring_bell(room.players[2].id, now=1.0)))

        threads = [threading.Thread(target=reveal), threading.Thread(target=ring)]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join()

        room.assert_integrity()
        self.assertEqual(56, len(room.all_cards()))
        self.assertEqual(56, len({card.id for card in room.all_cards()}))
        ring_result = next(value for kind, value in outcomes if kind == "ring")
        self.assertIn(ring_result["status"], ("correct", "wrong"))
        if ring_result["status"] == "wrong":
            self.assertTrue(any(kind == "reveal_error" for kind, _ in outcomes))


class ReconnectAndPrivacyTests(unittest.TestCase):
    def test_refresh_reconnect_restores_same_player_and_resumes(self):
        room = make_started_room()
        player = room.players[2]
        token = player.reconnect_token
        room.disconnect(player.sid)
        self.assertEqual(PAUSED_DISCONNECT, room.state)

        restored = room.reconnect(token, "new-sid")

        self.assertIs(restored, player)
        self.assertEqual("new-sid", player.sid)
        self.assertEqual(PLAYING, room.state)
        self.assertEqual(4, len(room.players))

    def test_serialized_state_never_contains_hidden_deck_values(self):
        room = make_started_room()
        hidden_ids = {card.id for player in room.players for card in player.draw_pile}
        state = room.serialize(room.players[0].id, now=0.0)
        encoded = json.dumps(state, ensure_ascii=False)
        self.assertNotIn("draw_pile", encoded)
        self.assertNotIn("reconnect_token", encoded)
        self.assertTrue(hidden_ids.isdisjoint(set(encoded.split('"'))))
        for player in state["players"]:
            self.assertIn("remaining_card_count", player)
            self.assertNotIn("cards", player)


if __name__ == "__main__":
    unittest.main()
