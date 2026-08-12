from game.dice import PlayerDice
from game.rng import create_rng

def test_player_dice():
    pd = PlayerDice('p1', 'red')
    assert pd.total == 8
    assert pd.remaining == 8
    
    rng = create_rng(42)
    roll = pd.roll(rng)
    assert len(roll) == 8
    assert pd.remaining == 8
    
    valid = pd.get_valid_casinos()
    assert len(valid) == len(set(roll))
    
    num = valid[0]
    count = pd.count_matching(num)
    assert count > 0
    
    placed = pd.place(num)
    assert placed == count
    assert pd.remaining == 8 - count
    assert pd.current_roll == []
    
    if pd.remaining > 0:
        assert pd.has_dice()
