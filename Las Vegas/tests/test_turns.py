from game.engine import CasinoGame
from game.config import *

def test_turn_order():
    """Test clockwise turn order starting from 선."""
    game = CasinoGame('ROOM', 'dice', seed=42)
    game.add_player('p1', 'P1', 'red', 0)
    game.add_player('p2', 'P2', 'orange', 1)
    game.add_player('p3', 'P3', 'green', 2)
    game.add_player('p4', 'P4', 'yellow', 3)
    
    order = game.get_turn_order('p2')
    assert order == ['p2', 'p3', 'p4', 'p1']
    
    order = game.get_turn_order('p4')
    assert order == ['p4', 'p1', 'p2', 'p3']

def test_skip_finished_players():
    """Test that players with 0 dice are skipped."""
    game = CasinoGame('ROOM', 'dice', seed=42)
    game.add_player('p1', 'P1', 'red', 0)
    game.add_player('p2', 'P2', 'orange', 1)
    game.add_player('p3', 'P3', 'green', 2)
    game.add_player('p4', 'P4', 'yellow', 3)
    game.start_game()
    
    game.turn_order = ['p1', 'p2', 'p3', 'p4']
    game.current_player_idx = 0
    
    # p2 and p3 have no dice
    game.player_dice['p2'].remaining = 0
    game.player_dice['p3'].remaining = 0
    
    next_pid = game.advance_turn()
    assert next_pid == 'p4'
    
def test_round_ends_when_all_done():
    """Test round completes when all players have 0 dice."""
    game = CasinoGame('ROOM', 'dice', seed=42)
    game.add_player('p1', 'P1', 'red', 0)
    game.add_player('p2', 'P2', 'orange', 1)
    game.add_player('p3', 'P3', 'green', 2)
    game.add_player('p4', 'P4', 'yellow', 3)
    game.start_game()
    
    game.turn_order = ['p1', 'p2', 'p3', 'p4']
    game.current_player_idx = 0
    
    # All have 0 dice
    for pid in game.player_dice:
        game.player_dice[pid].remaining = 0
    
    game.advance_turn()
    assert game.phase == ROUND_COMPLETE
