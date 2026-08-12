from game.money import MoneyDeck
from game.rng import create_rng

def test_money_deck():
    deck = MoneyDeck()
    assert len(deck.bills) == 54
    assert deck.remaining() == 54
    
    ids = [b.id for b in deck.bills]
    assert len(set(ids)) == 54
    
    denoms = {}
    for b in deck.bills:
        denoms[b.value] = denoms.get(b.value, 0) + 1
        
    assert len(denoms) == 9
    for val, count in denoms.items():
        assert count == 6
        
    rng = create_rng(42)
    original_ids = list(ids)
    deck.shuffle(rng)
    assert [b.id for b in deck.bills] != original_ids
    
    bill = deck.draw()
    assert bill is not None
    assert deck.remaining() == 53
