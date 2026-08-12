from game.config import (
    DEALER_TIE_REROLL,
    GAME_OVER,
    PAYOUT_SETUP,
    PLACEMENT_SELECTION,
    ROUND_COMPLETE,
)
from game.engine import CasinoGame


def test_two_player_game_can_reach_settlement():
    game = CasinoGame("DUO", "dice", seed=7)
    game.add_player("p1", "P1", "red", 0)
    game.add_player("p2", "P2", "orange", 1)

    game.start_game()
    game.do_dealer_roll()
    game.resolve_dealer()
    while game.phase == DEALER_TIE_REROLL:
        game.do_dealer_roll()
        game.resolve_dealer()

    assert game.phase == PAYOUT_SETUP
    game.setup_payouts()
    assert len(game.turn_order) == 2

    while game.phase != ROUND_COMPLETE:
        player_id = game.get_current_player()
        game.do_roll()
        game.phase = PLACEMENT_SELECTION
        casino = game.get_valid_casinos(player_id)[0]
        game.do_placement(player_id, casino)

    game.do_settlement()
    assert game.phase == GAME_OVER
    assert len(game.get_rankings()) == 2
