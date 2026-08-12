from game.engine import CasinoGame
from game.config import *

def test_full_game_flow():
    game = CasinoGame('ROOM', 'dice', seed=42)
    game.add_player('p1', 'P1', 'red', 0)
    game.add_player('p2', 'P2', 'orange', 1)
    game.add_player('p3', 'P3', 'green', 2)
    game.add_player('p4', 'P4', 'yellow', 3)
    
    game.start_game()
    assert game.phase == DEALER_ROLL
    
    game.do_dealer_roll()
    result = game.resolve_dealer()
    
    while game.phase == DEALER_TIE_REROLL:
        game.do_dealer_roll()
        result = game.resolve_dealer()
        
    assert game.phase == PAYOUT_SETUP
    
    game.setup_payouts()
    assert game.phase == TURN_WAITING
    assert len(game.casino_bills) == NUM_CASINOS
    
    for i in range(1, NUM_CASINOS + 1):
        assert sum(b.value for b in game.casino_bills[i]) >= MIN_CASINO_PAYOUT
        
    rolls = game.do_roll()
    assert game.phase == DICE_ROLLING
    assert len(rolls) == 8
    
    pid = game.get_current_player()
    valid_casinos = game.player_dice[pid].get_valid_casinos()
    assert len(valid_casinos) > 0
    
    game.phase = PLACEMENT_SELECTION
    valid, msg = game.validate_placement(pid, valid_casinos[0])
    assert valid
    
    before = game.player_dice[pid].remaining
    count = game.do_placement(pid, valid_casinos[0])
    assert count > 0
    assert game.player_dice[pid].remaining == before - count
    
    # Simulate round end
    for p in game.players:
        game.player_dice[p].remaining = 0
    
    game.phase = TURN_WAITING
    game.advance_turn()
    assert game.phase == ROUND_COMPLETE
    
    results = game.do_settlement()
    assert game.phase == GAME_OVER
    
    winner = game.get_winner()
    assert isinstance(winner, list)
    assert len(winner) >= 1

def test_casino_setup_minimum():
    """Test that each casino gets at least $100,000."""
    game = CasinoGame('ROOM', 'dice', seed=123)
    game.add_player('p1', 'P1', 'red', 0)
    game.add_player('p2', 'P2', 'orange', 1)
    game.add_player('p3', 'P3', 'green', 2)
    game.add_player('p4', 'P4', 'yellow', 3)
    game.start_game()
    game.do_dealer_roll()
    game.resolve_dealer()
    while game.phase == DEALER_TIE_REROLL:
        game.do_dealer_roll()
        game.resolve_dealer()
    
    game.setup_payouts()
    
    for i in range(1, NUM_CASINOS + 1):
        total = sum(b.value for b in game.casino_bills[i])
        assert total >= 100000, f"Casino {i} has only ${total}"

def test_placement_validation():
    """Test that invalid placements are rejected."""
    game = CasinoGame('ROOM', 'dice', seed=42)
    game.add_player('p1', 'P1', 'red', 0)
    game.add_player('p2', 'P2', 'orange', 1)
    game.add_player('p3', 'P3', 'green', 2)
    game.add_player('p4', 'P4', 'yellow', 3)
    game.start_game()
    game.do_dealer_roll()
    game.resolve_dealer()
    while game.phase == DEALER_TIE_REROLL:
        game.do_dealer_roll()
        game.resolve_dealer()
    game.setup_payouts()
    game.do_roll()
    game.phase = PLACEMENT_SELECTION
    
    pid = game.get_current_player()
    
    # Wrong player
    other = [p for p in game.players if p != pid][0]
    valid, msg = game.validate_placement(other, 1)
    assert not valid

def test_rankings():
    """Test ranking calculation."""
    game = CasinoGame('ROOM', 'dice', seed=42)
    game.add_player('p1', 'P1', 'red', 0)
    game.add_player('p2', 'P2', 'orange', 1)
    game.add_player('p3', 'P3', 'green', 2)
    game.add_player('p4', 'P4', 'yellow', 3)
    
    game.winnings = {'p1': 300000, 'p2': 300000, 'p3': 200000, 'p4': 100000}
    
    rankings = game.get_rankings()
    assert rankings[0]['rank'] == 1
    assert rankings[1]['rank'] == 1  # Tie
    assert rankings[0]['total'] == 300000
    
    winners = game.get_winner()
    assert len(winners) == 2
    assert 'p1' in winners
    assert 'p2' in winners
