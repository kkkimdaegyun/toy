from game.engine import CasinoGame
from game.config import DEALER_ROLL, DEALER_TIE_REROLL, PAYOUT_SETUP

def test_dealer_roll_lowest_wins():
    """Test that the LOWEST roller becomes 선."""
    game = CasinoGame('ROOM', 'dice', seed=42)
    game.add_player('p1', 'P1', 'red', 0)
    game.add_player('p2', 'P2', 'orange', 1)
    game.add_player('p3', 'P3', 'green', 2)
    game.add_player('p4', 'P4', 'yellow', 3)
    
    game.start_game()
    assert game.phase == DEALER_ROLL
    
    rolls = game.do_dealer_roll()
    assert len(rolls) == 4
    
    # All rolls should be 1-6
    for roll in rolls.values():
        assert 1 <= roll <= 6
    
    winner, reroll_list = game.resolve_dealer()
    
    while game.phase == DEALER_TIE_REROLL:
        game.do_dealer_roll()
        winner, reroll_list = game.resolve_dealer()
        
    assert game.phase == PAYOUT_SETUP
    assert winner is not None
    assert winner in game.players

def test_dealer_eventual_resolution():
    """Test that dealer roll eventually resolves even with many ties."""
    # Try multiple seeds to ensure resolution always works
    for seed in range(100):
        game = CasinoGame('ROOM', 'dice', seed=seed)
        game.add_player('p1', 'P1', 'red', 0)
        game.add_player('p2', 'P2', 'orange', 1)
        game.add_player('p3', 'P3', 'green', 2)
        game.add_player('p4', 'P4', 'yellow', 3)
        
        game.start_game()
        game.do_dealer_roll()
        winner, _ = game.resolve_dealer()
        
        attempts = 0
        while game.phase == DEALER_TIE_REROLL and attempts < 100:
            game.do_dealer_roll()
            winner, _ = game.resolve_dealer()
            attempts += 1
        
        assert game.phase == PAYOUT_SETUP, f"Failed to resolve dealer with seed {seed}"
        assert winner is not None

def test_lowest_roll_is_winner():
    """Verify the lowest roll wins, not the highest."""
    game = CasinoGame('ROOM', 'dice', seed=42)
    game.add_player('p1', 'P1', 'red', 0)
    game.add_player('p2', 'P2', 'orange', 1)
    game.add_player('p3', 'P3', 'green', 2)
    game.add_player('p4', 'P4', 'yellow', 3)
    game.start_game()
    
    # Manually set rolls to test
    game.dealer_rolls = {'p1': 4, 'p2': 2, 'p3': 6, 'p4': 5}
    winner, _ = game.resolve_dealer()
    
    assert winner == 'p2', "Lowest roller (2) should be 선"

def test_tie_only_rerolls_tied():
    """Verify only tied players for lowest reroll."""
    game = CasinoGame('ROOM', 'dice', seed=42)
    game.add_player('p1', 'P1', 'red', 0)
    game.add_player('p2', 'P2', 'orange', 1)
    game.add_player('p3', 'P3', 'green', 2)
    game.add_player('p4', 'P4', 'yellow', 3)
    game.start_game()
    
    game.dealer_rolls = {'p1': 2, 'p2': 2, 'p3': 4, 'p4': 6}
    winner, reroll_list = game.resolve_dealer()
    
    assert winner is None
    assert game.phase == DEALER_TIE_REROLL
    assert set(reroll_list) == {'p1', 'p2'}
    assert 'p3' not in reroll_list
    assert 'p4' not in reroll_list
